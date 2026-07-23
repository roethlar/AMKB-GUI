from __future__ import annotations

import copy
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from PIL import Image

from am_configurator.generation import OperationGate
from am_configurator.library import GeneratedAssetLibrary
from am_configurator.llm import ProviderError
from am_configurator.procedural_generation import ProceduralGenerationCoordinator
from am_configurator.recipe_provider import RecipeResult


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

        started = coordinator.start_effect(
            prompt="Dense aurora across the whole keyboard",
            target=TARGET,
            loop_mode="smooth",
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

    def test_local_quality_failure_retries_twice_at_most_with_reason(self) -> None:
        provider = _Provider([_dim_recipe(), _dense_recipe()])
        coordinator = self._coordinator(provider)

        started = coordinator.start_effect(
            prompt="Aurora",
            target=TARGET,
            loop_mode="smooth",
        )
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual("ready", manifest["status"])
        self.assertEqual(2, len(manifest["procedural_attempts"]))
        self.assertEqual("failed", manifest["procedural_attempts"][0]["status"])
        self.assertEqual("complete", manifest["procedural_attempts"][1]["status"])
        self.assertEqual(0, provider.calls[0][0])
        self.assertEqual(1, provider.calls[1][0])
        self.assertIn("brightness", provider.calls[1][1])

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
                loop_mode="smooth",
            )

        self.assertEqual([], provider.calls)
        self.assertFalse((Path(self.temporary.name) / "library").exists())

    def test_reconcile_adopts_completely_banked_procedural_artifacts(self) -> None:
        provider = _Provider([_dense_recipe()])
        coordinator = self._coordinator(provider)
        started = coordinator.start_effect(
            prompt="Recover banked result",
            target=TARGET,
            loop_mode="smooth",
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
            loop_mode="smooth",
        )
        self.assertTrue(provider.entered.wait(2))

        coordinator.cancel(started["job_id"])
        gate.wait_until_idle()
        manifest = self.library.load_manifest(started["job_id"])

        self.assertEqual([(0, None)], provider.calls)
        self.assertEqual("cancelled", manifest["status"])
        self.assertEqual([], manifest["assets"])

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
            loop_mode="smooth",
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
