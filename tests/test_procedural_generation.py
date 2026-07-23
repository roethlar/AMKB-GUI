from __future__ import annotations

import copy
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from am_configurator import procedural
from am_configurator.generation import (
    GenerationBusyError,
    GenerationError,
    GenerationNotActiveError,
    OperationGate,
)
from am_configurator.library import GeneratedAssetLibrary
from am_configurator.llm import ProviderError
from am_configurator.ollama_client import OllamaClient, OllamaModel
from am_configurator.procedural_generation import ProceduralGenerationCoordinator
from am_configurator.recipe_provider import OllamaRecipeProvider, RecipeResult


TARGET = {
    "family": "80",
    "product_id": "AM21",
    "raster": {"width": 18, "height": 7},
    "targets": ["keyframes", "spotlight_frames"],
}
ORNITH_RECIPE = Path(__file__).parent / "fixtures" / "ornith_dense_aurora_recipe.json"


def _dense_recipe() -> dict:
    return json.loads(ORNITH_RECIPE.read_text("utf-8"))


def _dim_recipe() -> dict:
    recipe = _dense_recipe()
    recipe["background"] = "#000000"
    recipe["palette"] = ["#000000" for _color in recipe["palette"]]
    return recipe


class _Provider:
    def __init__(self, recipes: list[dict], *, backend: str = "local") -> None:
        self.recipes = [copy.deepcopy(recipe) for recipe in recipes]
        self.backend = backend
        self.calls: list[tuple[int, str | None]] = []

    def _result(self, attempt: int, reason: str | None) -> RecipeResult:
        self.calls.append((attempt, reason))
        recipe = self.recipes[min(attempt, len(self.recipes) - 1)]
        return RecipeResult(
            recipe=copy.deepcopy(recipe),
            backend=self.backend,
            provider="ollama" if self.backend == "local" else "xai",
            model_id="ornith:latest" if self.backend == "local" else "grok-4.5",
            usage=None if self.backend == "local" else {"cost_in_usd_ticks": 42},
        )

    def generate(self, request, deadline, cancelled):
        return self._result(0, None)

    def generate_attempt(
        self,
        request,
        deadline,
        cancelled,
        *,
        attempt,
        validation_reason,
    ):
        return self._result(attempt, validation_reason)


class _BlockingProvider(_Provider):
    def __init__(self) -> None:
        super().__init__([_dense_recipe()])
        self.entered = threading.Event()

    def generate(self, request, deadline, cancelled):
        self.calls.append((0, None))
        self.entered.set()
        while not cancelled():
            time.sleep(0.005)
        raise ProviderError("unavailable", "Local inference was cancelled.")


class _Capability:
    def __init__(self, provider: _Provider, *, enabled: bool = True) -> None:
        self.provider = provider
        self.enabled = enabled

    def require_ready(self):
        if not self.enabled:
            raise RuntimeError("disabled")
        backend = self.provider.backend
        return {
            "enabled": True,
            "ready": True,
            "backend": backend,
            "local": {
                "model_id": "ornith:latest",
                "provider": "ollama",
            },
            "api": {"provider": "xai", "model_id": "grok-4.5"},
        }

    def provider_for_generation(self):
        self.require_ready()
        return self.provider


class ProceduralGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="am-procedural-jobs-")
        self.library = GeneratedAssetLibrary(
            Path(self.temporary.name) / "library",
            minimum_free_bytes=1,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _inline(target):
        target()
        return object()

    def _coordinator(self, provider: _Provider) -> ProceduralGenerationCoordinator:
        return ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=OperationGate(),
            launcher=self._inline,
            operation_timeout_seconds=30,
        )

    def test_local_job_banks_exact_recipe_raster_preview_and_mapping(self) -> None:
        provider = _Provider([_dense_recipe()])
        coordinator = self._coordinator(provider)
        progress_updates: list[tuple[str, int, int]] = []
        original_update_manifest = self.library.update_manifest

        def observe_progress(job_id: str, change):
            current = original_update_manifest(job_id, change)
            progress = current.get("progress")
            if current.get("phase") in {"rendering", "quality_check", "banking"} and progress:
                progress_updates.append(
                    (current["phase"], progress["completed"], progress["total"])
                )
            return current

        self.library.update_manifest = observe_progress

        started = coordinator.start_effect(
            prompt="Dense aurora across the whole keyboard",
            target=TARGET,
        )
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual("procedural", manifest["pipeline"])
        self.assertEqual("ready", manifest["status"])
        self.assertEqual("ready_for_review", manifest["phase"])
        self.assertEqual({"completed": 200, "total": 200}, manifest["progress"])
        self.assertEqual([(0, None)], provider.calls)
        attempt = manifest["procedural_attempts"][0]
        self.assertEqual("complete", attempt["status"])
        self.assertEqual(200, attempt["quality"]["frame_count"])
        assets = {asset["kind"]: asset for asset in manifest["assets"]}
        self.assertEqual(
            {"recipe", "raster_animation", "preview_animation", "mapped_result"},
            set(assets),
        )
        raster = self.library.resolve_asset(
            manifest["job_id"], assets["raster_animation"]["asset_id"]
        )
        with Image.open(raster.path) as image:
            self.assertEqual((18, 7), image.size)
            self.assertEqual(200, image.n_frames)
        mapped = json.loads(
            self.library.resolve_asset(
                manifest["job_id"], assets["mapped_result"]["asset_id"]
            ).path.read_text("utf-8")
        )
        self.assertEqual(200, mapped["source_frames"])
        self.assertEqual(200 * 34, mapped["source_duration_ms"])
        self.assertEqual(34, mapped["duration_ms"])
        self.assertFalse(mapped["timing_resampled"])
        self.assertEqual(200, mapped["tracks"]["keyframes"]["frame_count"])
        self.assertEqual(200, mapped["tracks"]["spotlight_frames"]["frame_count"])
        for phase in ("rendering", "quality_check", "banking"):
            self.assertTrue(
                any(
                    current_phase == phase and 0 < completed < total
                    for current_phase, completed, total in progress_updates
                ),
                phase,
            )

    def test_invalid_mapped_timeline_is_rejected_before_result_assets_are_banked(self) -> None:
        provider = _Provider([_dense_recipe()])
        coordinator = self._coordinator(provider)
        real_mapper = procedural.map_frames_to_led_tracks

        def invalid_mapper(*args, **kwargs):
            mapped = real_mapper(*args, **kwargs)
            mapped["tracks"]["keyframes"]["frame_count"] -= 1
            return mapped

        with patch.object(procedural, "map_frames_to_led_tracks", invalid_mapper):
            started = coordinator.start_effect(
                prompt="Reject invalid mapped output",
                target=TARGET,
            )
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual("failed", manifest["status"])
        self.assertEqual("artifact_failed", manifest["errors"][-1]["code"])
        self.assertEqual(
            {"recipe"},
            {asset["kind"] for asset in manifest["assets"]},
        )

    def test_local_quality_failure_retries_twice_at_most_with_reason(self) -> None:
        provider = _Provider([_dim_recipe(), _dense_recipe()])
        coordinator = self._coordinator(provider)

        started = coordinator.start_effect(
            prompt="Aurora",
            target=TARGET,
        )
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual("ready", manifest["status"])
        self.assertEqual(2, len(manifest["procedural_attempts"]))
        self.assertEqual("failed", manifest["procedural_attempts"][0]["status"])
        self.assertEqual("complete", manifest["procedural_attempts"][1]["status"])
        self.assertEqual(0, provider.calls[0][0])
        self.assertEqual(1, provider.calls[1][0])
        self.assertIn("brightness", provider.calls[1][1])

    def test_real_ollama_provider_stops_after_two_corrected_retries(self) -> None:
        class SequencedOllamaClient:
            def __init__(self) -> None:
                self.responses = [
                    {"message": {"content": "{}"}},
                    {"message": {"content": json.dumps(_dim_recipe())}},
                    {"message": {"content": json.dumps(_dim_recipe())}},
                ]
                self.calls: list[dict] = []

            def chat(self, payload, *, deadline, cancelled):
                del deadline, cancelled
                self.calls.append(copy.deepcopy(payload))
                if len(self.calls) > len(self.responses):
                    raise AssertionError("the coordinator made a fourth Ollama call")
                return self.responses[len(self.calls) - 1]

        model = OllamaModel(
            model_id="ornith:latest",
            digest="a" * 64,
            size_bytes=5_629_110_568,
            parameter_size="9.0B",
            quantization="Q4_K_M",
        )
        client = SequencedOllamaClient()
        provider = OllamaRecipeProvider(model, client=client)

        class Capability:
            @staticmethod
            def require_ready():
                return {
                    "enabled": True,
                    "ready": True,
                    "backend": "local",
                    "local": {
                        "model_id": model.model_id,
                        "provider": "ollama",
                    },
                    "api": {"provider": "xai", "model_id": "grok-4.5"},
                }

            @staticmethod
            def provider_for_generation():
                return provider

        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            Capability(),
            operation_gate=gate,
            launcher=self._inline,
            operation_timeout_seconds=30,
        )

        started = coordinator.start_effect(
            prompt="Exhaust the local correction budget",
            target=TARGET,
        )
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual(3, len(client.calls))
        seeds = [call["options"]["seed"] for call in client.calls]
        self.assertEqual(3, len(set(seeds)))
        prompts = [call["messages"][1]["content"] for call in client.calls]
        self.assertNotIn("Retry correction:", prompts[0])
        self.assertIn("recipe schema or semantic validation", prompts[1])
        self.assertIn("brightness", prompts[2])
        self.assertNotEqual(prompts[1], prompts[2])

        self.assertEqual("failed", manifest["status"])
        self.assertEqual("effect_failed", manifest["phase"])
        self.assertEqual(3, len(manifest["procedural_attempts"]))
        self.assertEqual(
            ["bad_response", "quality_failed", "quality_failed"],
            [attempt["error_code"] for attempt in manifest["procedural_attempts"]],
        )
        self.assertTrue(
            all(
                attempt["status"] == "failed"
                for attempt in manifest["procedural_attempts"]
            )
        )
        self.assertEqual("quality_failed", manifest["errors"][-1]["code"])
        self.assertFalse(gate.is_active)
        replacement, _cancelled = gate.begin("after-retry-ceiling")
        gate.finish(replacement)

    def test_disabled_capability_creates_no_library_or_provider_work(self) -> None:
        provider = _Provider([_dense_recipe()])
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider, enabled=False),
            operation_gate=OperationGate(),
            launcher=self._inline,
        )

        with self.assertRaises(RuntimeError):
            coordinator.start_effect(
                prompt="Do not start",
                target=TARGET,
            )

        self.assertEqual([], provider.calls)
        self.assertFalse((Path(self.temporary.name) / "library").exists())

    def test_reconcile_adopts_completely_banked_procedural_artifacts(self) -> None:
        provider = _Provider([_dense_recipe()])
        coordinator = self._coordinator(provider)
        started = coordinator.start_effect(
            prompt="Recover banked result",
            target=TARGET,
        )
        attempt_id = self.library.load_manifest(started["job_id"])[
            "procedural_attempts"
        ][0]["attempt_id"]

        def simulate_final_manifest_loss(current: dict) -> None:
            attempt = current["procedural_attempts"][0]
            attempt["status"] = "in_progress"
            attempt["phase"] = "artifact_banking"
            attempt["completed_at"] = None
            attempt["raster_asset_id"] = None
            attempt["preview_asset_id"] = None
            attempt["mapped_result_asset_id"] = None
            current["status"] = "in_progress"
            current["phase"] = "artifact_banking"
            current["progress"] = {"completed": 0, "total": 200}

        self.library.update_manifest(started["job_id"], simulate_final_manifest_loss)
        actions = coordinator.reconcile_startup()
        recovered = self.library.load_manifest(started["job_id"])

        self.assertEqual(
            [{"job_id": started["job_id"], "action": "adopted_banked_procedural"}],
            actions,
        )
        self.assertEqual("ready", recovered["status"])
        attempt = recovered["procedural_attempts"][0]
        self.assertEqual(attempt_id, attempt["attempt_id"])
        self.assertIsNotNone(attempt["raster_asset_id"])
        self.assertIsNotNone(attempt["preview_asset_id"])
        self.assertIsNotNone(attempt["mapped_result_asset_id"])

    def test_local_cancellation_stops_without_retry_or_ready_artifacts(self) -> None:
        provider = _BlockingProvider()
        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=gate,
            operation_timeout_seconds=30,
        )
        started = coordinator.start_effect(
            prompt="Cancel this local inference",
            target=TARGET,
        )
        self.assertTrue(provider.entered.wait(2))

        coordinator.cancel(started["job_id"])
        gate.wait_until_idle()
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual([(0, None)], provider.calls)
        self.assertEqual("cancelled", manifest["status"])
        self.assertEqual([], manifest["assets"])

    def test_mid_render_cancellation_releases_admission_promptly(self) -> None:
        provider = _Provider([_dense_recipe()])
        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=gate,
            operation_timeout_seconds=30,
        )
        rendering = threading.Event()

        def controlled_render(*args, work=None, progress=None, **kwargs):
            self.assertIsNotNone(work)
            self.assertIsNotNone(progress)
            rendering.set()
            while True:
                work.check()
                time.sleep(0.001)

        with patch.object(procedural, "render_recipe", controlled_render):
            started = coordinator.start_effect(
                prompt="Cancel bounded local rendering",
                target=TARGET,
            )
            self.assertTrue(rendering.wait(1))
            coordinator.cancel(started["job_id"])
            idle = threading.Event()
            waiter = threading.Thread(
                target=lambda: (gate.wait_until_idle(), idle.set()),
                daemon=True,
            )
            waiter.start()
            self.assertTrue(idle.wait(1))

        manifest = self.library.load_manifest(started["job_id"])
        replacement, _cancelled = gate.begin("after-render-cancel")
        gate.finish(replacement)
        self.assertEqual("cancelled", manifest["status"])
        self.assertEqual("cancelled", manifest["procedural_attempts"][0]["status"])
        self.assertEqual(["recipe"], [asset["kind"] for asset in manifest["assets"]])

    def test_rendering_cannot_outlive_the_shared_operation_deadline(self) -> None:
        rendering = threading.Event()

        def monotonic() -> float:
            return 2.0 if rendering.is_set() else 0.0

        def controlled_render(*args, work=None, progress=None, **kwargs):
            self.assertIsNotNone(work)
            rendering.set()
            work.check()
            self.fail("the expired render budget did not stop work")

        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(_Provider([_dense_recipe()])),
            operation_gate=gate,
            launcher=self._inline,
            monotonic=monotonic,
            operation_timeout_seconds=1,
        )

        with patch.object(procedural, "render_recipe", controlled_render):
            started = coordinator.start_effect(
                prompt="Bound this local render",
                target=TARGET,
            )
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual("failed", manifest["status"])
        self.assertEqual("timeout", manifest["procedural_attempts"][0]["error_code"])
        self.assertEqual("timeout", manifest["errors"][-1]["code"])
        self.assertEqual(["recipe"], [asset["kind"] for asset in manifest["assets"]])
        replacement, _cancelled = gate.begin("after-render-timeout")
        gate.finish(replacement)

    def test_ollama_cancellation_releases_admission_and_discards_late_output(self) -> None:
        entered = threading.Event()
        released = threading.Event()
        closed = threading.Event()
        response_bytes = json.dumps(
            {"message": {"content": json.dumps(_dense_recipe())}}
        ).encode("utf-8")

        class Response:
            status = 200

            def read(self, limit):
                return response_bytes[:limit]

        class Connection:
            sock = None

            def request(self, method, path, *, body, headers):
                self.request_values = (method, path, body, headers)

            def getresponse(self):
                entered.set()
                released.wait(5)
                return Response()

            def close(self):
                closed.set()
                released.set()

        connection = Connection()
        client = OllamaClient(
            connection_factory=lambda host, port, timeout: connection
        )
        provider = OllamaRecipeProvider(
            OllamaModel(
                model_id="ornith:latest",
                digest="a" * 64,
                size_bytes=1,
                parameter_size="9B",
                quantization="Q4",
            ),
            client=client,
        )
        provider.backend = "local"
        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=gate,
            operation_timeout_seconds=30,
        )
        started = coordinator.start_effect(
            prompt="Cancel blocked Ollama inference",
            target=TARGET,
        )
        self.assertTrue(entered.wait(1))

        coordinator.cancel(started["job_id"])
        idle = threading.Event()
        waiter = threading.Thread(
            target=lambda: (gate.wait_until_idle(), idle.set()),
            daemon=True,
        )
        waiter.start()
        self.assertTrue(idle.wait(1))
        final = self.library.load_manifest(started["job_id"])
        replacement_token, _replacement_cancelled = gate.begin("replacement")
        gate.finish(replacement_token)

        self.assertTrue(closed.is_set())
        self.assertEqual("cancelled", final["status"])
        self.assertEqual([], final["assets"])

    def test_response_snapshot_failure_happens_before_worker_launch(self) -> None:
        gate = OperationGate()
        launches: list[object] = []
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(_Provider([_dense_recipe()])),
            operation_gate=gate,
            launcher=lambda target: launches.append(target),
        )
        original_get_job = self.library.get_job

        def fail_get_job(_job_id):
            raise OSError("simulated response read failure")

        self.library.get_job = fail_get_job
        try:
            with self.assertRaises(OSError):
                coordinator.start_effect(
                    prompt="Fail before launch",
                    target=TARGET,
                )
        finally:
            self.library.get_job = original_get_job

        self.assertEqual([], launches)
        self.assertFalse(gate.is_active)

    def test_launcher_failure_releases_admission_without_an_orphan_worker(self) -> None:
        gate = OperationGate()

        def fail_launcher(_target):
            raise OSError("simulated launcher failure")

        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(_Provider([_dense_recipe()])),
            operation_gate=gate,
            launcher=fail_launcher,
        )

        with self.assertRaises(GenerationError):
            coordinator.start_effect(
                prompt="Fail at launch",
                target=TARGET,
            )

        self.assertFalse(gate.is_active)
        manifest = self.library.scan()["jobs"][0]
        self.assertEqual("failed", manifest["status"])

    def test_post_launch_failure_keeps_admission_with_the_worker(self) -> None:
        gate = OperationGate()
        targets: list[object] = []

        def defer(target):
            targets.append(target)
            return object()

        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(_Provider([_dense_recipe()])),
            operation_gate=gate,
            launcher=defer,
        )

        class BrokenLock:
            def __enter__(self):
                raise OSError("simulated post-launch bookkeeping failure")

            def __exit__(self, *_args):
                return False

        coordinator._workers_lock = BrokenLock()
        with self.assertRaises(OSError):
            coordinator.start_effect(
                prompt="Worker owns this lease",
                target=TARGET,
            )

        self.assertEqual(1, len(targets))
        self.assertTrue(gate.is_active)
        with self.assertRaises(GenerationBusyError):
            gate.begin("second-operation")
        job_id = gate.active_job_id
        self.assertIsInstance(job_id, str)
        self.assertTrue(gate.request_cancel(job_id))
        with self.assertRaises(OSError):
            targets[0]()
        self.assertFalse(gate.is_active)
        self.assertEqual("cancelled", self.library.load_manifest(job_id)["status"])

    def test_rejected_cancellation_never_mutates_ready_or_interrupted_jobs(self) -> None:
        provider = _Provider([_dense_recipe()])
        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=gate,
            launcher=self._inline,
        )
        started = coordinator.start_effect(
            prompt="Already complete",
            target=TARGET,
        )
        job_id = started["job_id"]
        manifest_path = (
            Path(self.temporary.name) / "library" / "jobs" / job_id / "manifest.json"
        )

        token, _cancelled = gate.begin(job_id)
        try:
            ready_bytes = manifest_path.read_bytes()
            with self.assertRaises(GenerationNotActiveError):
                coordinator.cancel(job_id)
            self.assertEqual(ready_bytes, manifest_path.read_bytes())
            self.assertIsNone(self.library.load_manifest(job_id)["cancel_requested_at"])
        finally:
            gate.finish(token)

        def interrupt(current: dict) -> None:
            current["status"] = "interrupted"
            current["phase"] = "interrupted"

        self.library.update_manifest(job_id, interrupt)
        interrupted_bytes = manifest_path.read_bytes()
        with self.assertRaises(GenerationNotActiveError):
            coordinator.cancel(job_id)
        self.assertEqual(interrupted_bytes, manifest_path.read_bytes())
        self.assertIsNone(self.library.load_manifest(job_id)["cancel_requested_at"])

    def test_reconcile_never_replays_an_interrupted_api_request(self) -> None:
        provider = _Provider([_dense_recipe()], backend="api")
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=OperationGate(),
            launcher=self._inline,
        )
        manifest = self.library.create_job(
            prompt="Interrupted API",
            target=TARGET,
            models={"backend": "api", "provider": "xai", "model_id": "grok-4.5"},
            pipeline="procedural",
        )
        attempt_id = str(uuid.uuid4())

        def interrupt(current: dict) -> None:
            current["status"] = "in_progress"
            current["phase"] = "recipe_generating"
            current["procedural_attempts"].append({
                "attempt_id": attempt_id,
                "index": 0,
                "status": "in_progress",
                "phase": "recipe_generating",
                "started_at": "2026-07-21T00:00:00+00:00",
                "completed_at": None,
                "recipe_asset_id": None,
                "raster_asset_id": None,
                "preview_asset_id": None,
                "mapped_result_asset_id": None,
                "quality": None,
                "usage": None,
                "error_code": None,
            })

        self.library.update_manifest(manifest["job_id"], interrupt)
        actions = coordinator.reconcile_startup()
        recovered = self.library.load_manifest(manifest["job_id"])

        self.assertEqual([], provider.calls)
        self.assertEqual([], actions)
        self.assertEqual("interrupted", recovered["status"])
        self.assertEqual("interrupted_api_no_replay", recovered["phase"])

    def test_local_interruption_reconciliation_is_byte_stable_and_actionless(self) -> None:
        provider = _Provider([_dense_recipe()])
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=OperationGate(),
            launcher=self._inline,
        )
        empty = self.library.create_job(
            prompt="Interrupted before attempt",
            target=TARGET,
            models={"backend": "local", "provider": "ollama", "model_id": "ornith:latest"},
            pipeline="procedural",
        )
        started = self.library.create_job(
            prompt="Interrupted during attempt",
            target=TARGET,
            models={"backend": "local", "provider": "ollama", "model_id": "ornith:latest"},
            pipeline="procedural",
        )
        attempt_id = str(uuid.uuid4())

        def begin_attempt(current: dict) -> None:
            current["status"] = "in_progress"
            current["phase"] = "recipe_generating"
            current["procedural_attempts"].append({
                "attempt_id": attempt_id,
                "index": 0,
                "status": "in_progress",
                "phase": "recipe_generating",
                "started_at": "2026-07-21T00:00:00+00:00",
                "completed_at": None,
                "recipe_asset_id": None,
                "raster_asset_id": None,
                "preview_asset_id": None,
                "mapped_result_asset_id": None,
                "quality": None,
                "usage": None,
                "error_code": None,
            })

        self.library.update_manifest(started["job_id"], begin_attempt)

        first_actions = coordinator.reconcile_startup()
        first_manifests = {
            job_id: self.library.load_manifest(job_id)
            for job_id in (empty["job_id"], started["job_id"])
        }
        first_bytes = {
            job_id: (
                Path(self.temporary.name)
                / "library"
                / "jobs"
                / job_id
                / "manifest.json"
            ).read_bytes()
            for job_id in first_manifests
        }
        second_actions = coordinator.reconcile_startup()

        self.assertEqual([], first_actions)
        self.assertEqual([], second_actions)
        for job_id, manifest in first_manifests.items():
            with self.subTest(job_id=job_id):
                self.assertEqual("interrupted", manifest["status"])
                path = (
                    Path(self.temporary.name)
                    / "library"
                    / "jobs"
                    / job_id
                    / "manifest.json"
                )
                self.assertEqual(first_bytes[job_id], path.read_bytes())
        attempt = first_manifests[started["job_id"]]["procedural_attempts"][0]
        self.assertIsNotNone(attempt["completed_at"])

    def test_reconcile_preserves_a_failed_attempt_and_its_completion_time(self) -> None:
        coordinator = self._coordinator(_Provider([_dense_recipe()]))
        manifest = self.library.create_job(
            prompt="Failed before job settlement",
            target=TARGET,
            models={"backend": "local", "provider": "ollama", "model_id": "ornith:latest"},
            pipeline="procedural",
        )
        attempt_id = str(uuid.uuid4())
        completed_at = "2026-07-21T01:02:03+00:00"

        def fail_attempt_only(current: dict) -> None:
            current["status"] = "in_progress"
            current["phase"] = "recipe_generating"
            current["procedural_attempts"].append({
                "attempt_id": attempt_id,
                "index": 0,
                "status": "failed",
                "phase": "attempt_failed",
                "started_at": "2026-07-21T00:00:00+00:00",
                "completed_at": completed_at,
                "recipe_asset_id": None,
                "raster_asset_id": None,
                "preview_asset_id": None,
                "mapped_result_asset_id": None,
                "quality": None,
                "usage": None,
                "error_code": "invalid_recipe",
            })

        self.library.update_manifest(manifest["job_id"], fail_attempt_only)
        self.assertEqual([], coordinator.reconcile_startup())
        settled = self.library.load_manifest(manifest["job_id"])
        path = (
            Path(self.temporary.name)
            / "library"
            / "jobs"
            / manifest["job_id"]
            / "manifest.json"
        )
        settled_bytes = path.read_bytes()

        self.assertEqual("failed", settled["status"])
        self.assertEqual("failed", settled["procedural_attempts"][0]["status"])
        self.assertEqual(completed_at, settled["procedural_attempts"][0]["completed_at"])
        self.assertEqual([], coordinator.reconcile_startup())
        self.assertEqual(settled_bytes, path.read_bytes())

    def test_reconcile_uses_the_shared_gate_and_releases_it_on_failure(self) -> None:
        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(_Provider([_dense_recipe()])),
            operation_gate=gate,
        )
        active_token, _active_cancelled = gate.begin("active-generation")
        try:
            with self.assertRaises(GenerationBusyError):
                coordinator.reconcile_startup()
        finally:
            gate.finish(active_token)

        original_reconcile = self.library.reconcile

        def fail_reconcile():
            raise OSError("simulated reconciliation failure")

        self.library.reconcile = fail_reconcile
        try:
            with self.assertRaises(OSError):
                coordinator.reconcile_startup()
        finally:
            self.library.reconcile = original_reconcile
        self.assertFalse(gate.is_active)

    def test_reconcile_holds_admission_against_a_concurrent_generation(self) -> None:
        gate = OperationGate()
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(_Provider([_dense_recipe()])),
            operation_gate=gate,
        )
        entered = threading.Event()
        release = threading.Event()
        original_reconcile = self.library.reconcile
        failures: list[BaseException] = []

        def blocking_reconcile():
            entered.set()
            if not release.wait(2):
                raise TimeoutError("test did not release reconciliation")
            return original_reconcile()

        def run_reconcile() -> None:
            try:
                coordinator.reconcile_startup()
            except BaseException as error:
                failures.append(error)

        self.library.reconcile = blocking_reconcile
        worker = threading.Thread(target=run_reconcile)
        worker.start()
        admitted = None
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(GenerationBusyError):
                admitted = gate.begin("concurrent-generation")
            self.assertEqual([], self.library.scan()["jobs"])
        finally:
            if admitted is not None:
                gate.finish(admitted[0])
            release.set()
            worker.join(2)
            self.library.reconcile = original_reconcile

        self.assertFalse(worker.is_alive())
        self.assertEqual([], failures)
        self.assertFalse(gate.is_active)

    def test_api_quality_failure_is_one_charged_call_and_never_retried(self) -> None:
        provider = _Provider([_dim_recipe(), _dense_recipe()], backend="api")
        coordinator = ProceduralGenerationCoordinator(
            self.library,
            _Capability(provider),
            operation_gate=OperationGate(),
            launcher=self._inline,
        )

        started = coordinator.start_effect(
            prompt="One API request only",
            target=TARGET,
        )
        manifest = self.library.load_manifest(started["job_id"])
        coordinator.reconcile_startup()

        self.assertEqual([(0, None)], provider.calls)
        self.assertEqual("failed", manifest["status"])
        self.assertEqual(1, len(manifest["procedural_attempts"]))
        operation = next(iter(manifest["costs"]["actual_by_operation"]))
        self.assertEqual(42, manifest["costs"]["actual_by_operation"][operation])
        self.assertGreater(manifest["costs"]["estimated_ticks"], 0)


if __name__ == "__main__":
    unittest.main()
