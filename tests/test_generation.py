from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from am_configurator import generation
from am_configurator.library import GeneratedAssetLibrary, LibraryRootError
from am_configurator.llm import (
    ConceptImageResult,
    ConceptPlan,
    ConceptPlanResult,
    ImageMetadata,
    ProviderError,
    ProviderUsage,
    VideoAnimationPlan,
    VideoAnimationPlanResult,
    VideoStatus,
    VideoSubmission,
)
from am_configurator.media import DownloadedVideo, MediaError, ProcessedAnimation


TARGET = {
    "family": "CB",
    "product_id": "CB_TEST",
    "raster": {"width": 40, "height": 5},
    "targets": ["frames"],
}
MODELS = {
    "interpreter": "grok-4.5",
    "concept": "grok-imagine-image",
    "video": "grok-imagine-video-1.5",
}


def _png_bytes() -> bytes:
    output = io.BytesIO()
    with Image.new("RGB", (20, 9), (32, 64, 128)) as image:
        image.save(output, format="PNG")
    return output.getvalue()


class _Planner:
    def __init__(self, usages: list[ProviderUsage] | None = None) -> None:
        self.usages = usages or [ProviderUsage(11, True)]
        self.calls: list[tuple[str, int, float]] = []
        self.before_call = None
        self.failure: ProviderError | None = None

    def plan(self, prompt: object, candidate_count: object, deadline: float) -> ConceptPlanResult:
        assert isinstance(prompt, str)
        assert isinstance(candidate_count, int)
        if self.before_call is not None:
            self.before_call()
        self.calls.append((prompt, candidate_count, deadline))
        if self.failure is not None:
            raise self.failure
        call_number = len(self.calls)
        prompts = tuple(
            f"{prompt} — batch {call_number}, variation {index + 1}"
            for index in range(candidate_count)
        )
        usage = self.usages[min(call_number - 1, len(self.usages) - 1)]
        return ConceptPlanResult(
            plan=ConceptPlan(
                visual_brief=f"Shared brief {call_number}",
                candidate_prompts=prompts,
            ),
            usage=usage,
        )


class _ImageProvider:
    def __init__(self, usages: list[ProviderUsage] | None = None) -> None:
        self.usages = usages or [ProviderUsage(22, True)]
        self.calls: list[tuple[str, float]] = []
        self.before_call = None
        self.block_call: int | None = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.fail_call: int | None = None
        self.failure_usage = ProviderUsage(None, False)
        self.payload = _png_bytes()

    def generate_one(self, prompt: object, deadline: float) -> ConceptImageResult:
        assert isinstance(prompt, str)
        index = len(self.calls)
        if self.before_call is not None:
            self.before_call(index)
        self.calls.append((prompt, deadline))
        if self.block_call == index:
            self.entered.set()
            if not self.release.wait(5):
                raise AssertionError("test image provider was not released")
        if self.fail_call == index:
            raise ProviderError(
                "unavailable",
                "provider failed without leaking https://signed.example/private",
                usage=self.failure_usage,
            )
        usage = self.usages[min(index, len(self.usages) - 1)]
        return ConceptImageResult(
            original_bytes=self.payload,
            metadata=ImageMetadata(
                format="PNG",
                mime_type="image/png",
                width=20,
                height=9,
                revised_prompt=f"revised {index + 1}",
            ),
            image=Image.open(io.BytesIO(self.payload)).convert("RGB"),
            usage=usage,
        )


class _VideoPlanner:
    def __init__(self, usage: ProviderUsage = ProviderUsage(31, True)) -> None:
        self.usage = usage
        self.calls: list[tuple] = []
        self.before_call = None
        self.failure: ProviderError | None = None

    def plan(
        self,
        prompt: object,
        motion: object,
        image_bytes: object,
        mime_type: object,
        spec: object,
        loop_mode: object,
        deadline: float,
    ) -> VideoAnimationPlanResult:
        if self.before_call is not None:
            self.before_call()
        self.calls.append(
            (prompt, motion, image_bytes, mime_type, spec, loop_mode, deadline)
        )
        if self.failure is not None:
            raise self.failure
        return VideoAnimationPlanResult(
            plan=VideoAnimationPlan(
                subject_lock="Keep the ember ribbon unchanged.",
                style_lock="Keep the original palette and texture.",
                video_prompt="Animate a gentle one-second ember pulse with a locked camera.",
            ),
            usage=self.usage,
        )


class _VideoProvider:
    def __init__(self) -> None:
        self.request_id = "video_request_123"
        self.submit_usage = ProviderUsage(41, True)
        self.poll_outcomes: list[VideoStatus | ProviderError] = [
            VideoStatus(
                request_id=self.request_id,
                status="done",
                usage=ProviderUsage(43, True),
                video_url="https://vidgen.x.ai/generated/video.mp4?signature=secret",
                duration=1,
            )
        ]
        self.submit_calls: list[tuple] = []
        self.poll_calls: list[tuple[str, float]] = []
        self.before_poll = None
        self.submit_failure: ProviderError | None = None

    def submit(
        self,
        plan: object,
        image_bytes: object,
        mime_type: object,
        deadline: float,
    ) -> VideoSubmission:
        self.submit_calls.append((plan, image_bytes, mime_type, deadline))
        if self.submit_failure is not None:
            raise self.submit_failure
        return VideoSubmission(
            request_id=self.request_id,
            status="pending",
            usage=self.submit_usage,
        )

    def poll(self, request_id: object, deadline: float) -> VideoStatus:
        assert isinstance(request_id, str)
        if self.before_poll is not None:
            self.before_poll()
        self.poll_calls.append((request_id, deadline))
        outcome = self.poll_outcomes.pop(0) if len(self.poll_outcomes) > 1 else self.poll_outcomes[0]
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


class _Downloader:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.failures = 0

    def __call__(
        self,
        source_url: object,
        destination: object,
        deadline: float,
        *,
        cancelled=None,
    ) -> DownloadedVideo:
        self.calls.append((source_url, destination, deadline, cancelled))
        if self.failures:
            self.failures -= 1
            raise MediaError("unavailable", "temporary media failure")
        path = Path(destination)
        payload = b"\x00\x00\x00\x18ftypisomdurable-video"
        path.write_bytes(payload)
        import hashlib

        return DownloadedVideo(
            path=path,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )


class _Processor:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.failures = 0

    def __call__(
        self,
        source_path: object,
        destination_directory: object,
        work_directory: object,
        *,
        ffmpeg_path: object,
        width: object,
        height: object,
        frame_count: object,
        loop_mode: str,
        deadline: float,
        cancelled=None,
    ) -> ProcessedAnimation:
        call = {
            "source_path": Path(source_path),
            "destination": Path(destination_directory),
            "work": Path(work_directory),
            "ffmpeg_path": ffmpeg_path,
            "width": width,
            "height": height,
            "frame_count": frame_count,
            "loop_mode": loop_mode,
            "deadline": deadline,
            "cancelled": cancelled,
        }
        self.calls.append(call)
        if self.failures:
            self.failures -= 1
            raise MediaError("ffmpeg_failed", "local processing failed")
        destination = call["destination"]
        destination.mkdir(mode=0o700)
        frame_paths = []
        for index in range(int(frame_count)):
            path = destination / f"frame-{index + 1:04d}.png"
            with Image.new(
                "RGB",
                (int(width), int(height)),
                ((index * 3) % 256, (index * 5) % 256, (index * 7) % 256),
            ) as image:
                image.save(path, format="PNG")
            frame_paths.append(path)
        return ProcessedAnimation(
            directory=destination,
            frame_paths=tuple(frame_paths),
            frame_count=int(frame_count),
            width=int(width),
            height=int(height),
            loop_mode=loop_mode,
        )


class DurableConceptGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "library"
        self.library = GeneratedAssetLibrary(self.root, minimum_free_bytes=1)
        self.planner = _Planner()
        self.images = _ImageProvider()
        self.planner_factory_calls: list[tuple[str, str]] = []
        self.image_factory_calls: list[tuple[str, str]] = []

        def planner_factory(api_key: str, model: str):
            self.planner_factory_calls.append((api_key, model))
            return self.planner

        def image_factory(api_key: str, model: str):
            self.image_factory_calls.append((api_key, model))
            return self.images

        self.gate = generation.OperationGate()
        self.coordinator = generation.GenerationCoordinator(
            self.library,
            planner_factory=planner_factory,
            image_provider_factory=image_factory,
            operation_gate=self.gate,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _start(self, **overrides: object) -> dict:
        values = {
            "prompt": "A calm ember ribbon",
            "candidate_count": 2,
            "target": TARGET,
            "models": MODELS,
            "loop_mode": "smooth",
            "api_key": "super-secret-key",
            "privacy_acknowledged": True,
        }
        values.update(overrides)
        return self.coordinator.start_concepts(**values)

    def _wait(self, job_id: str) -> dict:
        return self.coordinator.wait(job_id, timeout=5)

    def test_validation_is_before_manifest_and_spend_and_manifest_is_before_provider(self) -> None:
        invalid = (
            {"candidate_count": 0},
            {"candidate_count": 9},
            {"api_key": ""},
            {"privacy_acknowledged": False},
            {"models": {**MODELS, "concept": "unknown-model"}},
            {"target": {**TARGET, "family": "UNKNOWN"}},
            {"target": {**TARGET, "raster": {"width": 0, "height": 5}}},
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(generation.GenerationValidationError):
                    self._start(**values)
        self.assertEqual([], self.library.scan()["jobs"])
        self.assertEqual([], self.planner_factory_calls)
        self.assertEqual([], self.image_factory_calls)

        unavailable_calls: list[str] = []
        unavailable = generation.GenerationCoordinator(
            GeneratedAssetLibrary(None),
            planner_factory=lambda *_args: unavailable_calls.append("planner"),
            image_provider_factory=lambda *_args: unavailable_calls.append("image"),
            operation_gate=generation.OperationGate(),
        )
        with self.assertRaises(LibraryRootError):
            unavailable.start_concepts(
                prompt="Valid request but no configured library",
                candidate_count=1,
                target=TARGET,
                models=MODELS,
                loop_mode="smooth",
                api_key="secret",
                privacy_acknowledged=True,
            )
        self.assertEqual([], unavailable_calls)

        def assert_manifest_exists() -> None:
            jobs = self.library.scan()["jobs"]
            self.assertEqual(1, len(jobs))
            manifest = jobs[0]
            self.assertEqual("in_progress", manifest["status"])
            self.assertEqual("concept_generation", manifest["phase"])
            self.assertEqual(1, len(manifest["concept_batches"]))
            requests = manifest["provider_requests"]
            self.assertEqual(1, len(requests))
            self.assertEqual("submitting", next(iter(requests.values()))["status"])
            self.assertNotIn("super-secret-key", json.dumps(manifest))

        self.planner.before_call = assert_manifest_exists
        started = self._start()
        final = self._wait(started["job_id"])
        self.assertEqual("awaiting_selection", final["status"])
        self.assertEqual([("super-secret-key", "grok-4.5")], self.planner_factory_calls)
        self.assertEqual(
            [("super-secret-key", "grok-imagine-image")], self.image_factory_calls
        )

    def test_target_snapshot_must_match_the_canonical_product_layout(self) -> None:
        invalid_targets = (
            {key: value for key, value in TARGET.items() if key != "product_id"},
            {**TARGET, "product_id": "AM21"},
            {**TARGET, "targets": ["not_a_real_target"]},
            {**TARGET, "raster": {"width": 41, "height": 5}},
            {**TARGET, "frame_cap": 200},
            {
                "family": "CB",
                "product_id": "CB_TEST",
                "raster": {"width": 40, "height": 6},
                "targets": ["frames", "keyframes"],
            },
        )
        for target in invalid_targets:
            with self.subTest(target=target):
                with self.assertRaises(generation.GenerationValidationError):
                    generation.canonical_target_snapshot(target)
        self.assertEqual(
            {**TARGET, "frame_cap": 80},
            generation.canonical_target_snapshot(TARGET),
        )

    def test_single_flight_sequential_calls_and_banking_before_the_next_call(self) -> None:
        self.images.block_call = 0
        first = self._start()
        self.assertTrue(self.images.entered.wait(5))
        with self.assertRaises(generation.GenerationBusyError):
            self._start(prompt="A second paid operation")
        second_coordinator = generation.GenerationCoordinator(
            self.library,
            planner_factory=lambda _key, _model: self.planner,
            image_provider_factory=lambda _key, _model: self.images,
            operation_gate=self.gate,
        )
        with self.assertRaises(generation.GenerationBusyError):
            second_coordinator.start_concepts(
                prompt="A second coordinator in the same process",
                candidate_count=1,
                target=TARGET,
                models=MODELS,
                loop_mode="smooth",
                api_key="another-secret",
                privacy_acknowledged=True,
            )
        self.assertEqual(1, len(self.library.scan()["jobs"]))
        self.images.release.set()
        self.assertEqual("awaiting_selection", self._wait(first["job_id"])["status"])

        observed: list[tuple[int, int, int]] = []
        second_job_id: dict[str, str] = {}

        def before_call(index: int) -> None:
            manifest = self.library.load_manifest(second_job_id["value"])
            observed.append((index, len(manifest["candidates"]), len(manifest["assets"])))

        self.images = _ImageProvider()
        def before_plan() -> None:
            matching = [
                job
                for job in self.library.scan()["jobs"]
                if job["prompt"] == "A sequential bank test"
            ]
            self.assertEqual(1, len(matching))
            second_job_id["value"] = matching[0]["job_id"]
            self.images.before_call = before_call

        self.planner.before_call = before_plan
        second = self._start(prompt="A sequential bank test", candidate_count=3)
        final = self._wait(second["job_id"])
        self.assertEqual("awaiting_selection", final["status"])
        self.assertEqual([(0, 0, 0), (1, 1, 1), (2, 2, 2)], observed)
        self.assertEqual(3, len(final["candidates"]))
        for candidate in final["candidates"]:
            owned = self.library.resolve_asset(second["job_id"], candidate["asset_id"])
            self.assertEqual(self.images.payload, owned.path.read_bytes())

    def test_partial_failure_and_planner_failure_are_durable_and_sanitized(self) -> None:
        self.images.fail_call = 1
        self.images.failure_usage = ProviderUsage(44, True)
        started = self._start(candidate_count=3)
        partial = self._wait(started["job_id"])
        self.assertEqual("partial", partial["status"])
        self.assertEqual("concepts_partial", partial["phase"])
        self.assertEqual(1, partial["progress"]["completed"])
        self.assertEqual(1, len(partial["candidates"]))
        self.assertEqual(2, len(self.images.calls))
        self.assertEqual("unavailable", partial["errors"][-1]["code"])
        serialized = json.dumps(partial)
        self.assertNotIn("signed.example", serialized)
        self.assertNotIn("super-secret-key", serialized)
        self.assertEqual(11 + 22 + 44, sum(partial["costs"]["actual_by_operation"].values()))

        failed_planner = _Planner()
        failed_planner.failure = ProviderError(
            "moderation", "planner refused", usage=ProviderUsage(None, False)
        )
        fresh = generation.GenerationCoordinator(
            self.library,
            planner_factory=lambda _key, _model: failed_planner,
            image_provider_factory=lambda _key, _model: self.images,
            operation_gate=generation.OperationGate(),
        )
        failed = fresh.start_concepts(
            prompt="A separate failed plan",
            candidate_count=2,
            target=TARGET,
            models=MODELS,
            loop_mode="none",
            api_key="secret-two",
            privacy_acknowledged=True,
        )
        failed = fresh.wait(failed["job_id"], timeout=5)
        self.assertEqual("failed", failed["status"])
        self.assertEqual("moderation", failed["errors"][-1]["code"])
        self.assertTrue(failed["costs"]["actual_incomplete"])
        self.assertEqual([], failed["candidates"])

    def test_cancellation_between_paid_calls_keeps_the_completed_candidate(self) -> None:
        self.images.block_call = 0
        started = self._start(candidate_count=3)
        self.assertTrue(self.images.entered.wait(5))
        requested = self.coordinator.cancel(started["job_id"])
        self.assertIsNotNone(requested["cancel_requested_at"])
        self.images.release.set()
        final = self._wait(started["job_id"])
        self.assertEqual("cancelled", final["status"])
        self.assertEqual("concepts_cancelled", final["phase"])
        self.assertIsNotNone(final["cancelled_at"])
        self.assertEqual(1, len(final["candidates"]))
        self.assertEqual(1, len(self.images.calls))

        self.images = _ImageProvider()
        self.images.block_call = 0
        last = self._start(prompt="Cancel during the final call", candidate_count=1)
        self.assertTrue(self.images.entered.wait(5))
        self.coordinator.cancel(last["job_id"])
        self.images.release.set()
        last = self._wait(last["job_id"])
        self.assertEqual("cancelled", last["status"])
        self.assertEqual(1, len(last["candidates"]))

    def test_more_like_this_appends_a_paid_batch_without_replacing_lineage(self) -> None:
        self.planner.usages = [ProviderUsage(10, True), ProviderUsage(40, True)]
        self.images.usages = [
            ProviderUsage(20, True),
            ProviderUsage(30, True),
            ProviderUsage(50, True),
        ]
        initial = self._start(candidate_count=2)
        initial = self._wait(initial["job_id"])
        original_ids = [candidate["asset_id"] for candidate in initial["candidates"]]

        more = self.coordinator.more_like_this(
            initial["job_id"],
            candidate_count=1,
            api_key="super-secret-key",
            privacy_acknowledged=True,
        )
        final = self._wait(more["job_id"])
        self.assertEqual("awaiting_selection", final["status"])
        self.assertEqual(2, len(final["concept_batches"]))
        self.assertEqual(3, len(final["candidates"]))
        self.assertEqual(original_ids, [item["asset_id"] for item in final["candidates"][:2]])
        self.assertEqual(
            ["A calm ember ribbon", "A calm ember ribbon"],
            [call[0] for call in self.planner.calls],
        )
        expected_estimate = generation.estimate_concept_batch_ticks(
            "grok-imagine-image", 3
        )
        self.assertEqual(expected_estimate, final["costs"]["estimated_ticks"])
        self.assertEqual(10 + 20 + 30 + 40 + 50, sum(final["costs"]["actual_by_operation"].values()))
        self.assertFalse(final["costs"]["actual_incomplete"])
        self.assertEqual(5, len(final["costs"]["actual_by_operation"]))

    def test_more_like_this_rechecks_the_owning_historical_root_before_spend(self) -> None:
        initial = self._start(candidate_count=1)
        initial = self._wait(initial["job_id"])
        self.assertEqual(1, len(self.planner.calls))

        new_root = Path(self._tmp.name) / "new-current-library"

        def disk_usage(path: str | Path):
            free = 0 if Path(path).resolve() == self.root.resolve() else 10_000
            return SimpleNamespace(total=10_000, used=10_000 - free, free=free)

        relocated_library = GeneratedAssetLibrary(
            new_root,
            historical_roots=[self.root],
            minimum_free_bytes=100,
            disk_usage=disk_usage,
        )
        relocated = generation.GenerationCoordinator(
            relocated_library,
            planner_factory=lambda _key, _model: self.planner,
            image_provider_factory=lambda _key, _model: self.images,
            operation_gate=generation.OperationGate(),
        )
        try:
            with self.assertRaises(LibraryRootError):
                relocated.more_like_this(
                    initial["job_id"],
                    candidate_count=1,
                    api_key="super-secret-key",
                    privacy_acknowledged=True,
                )
        finally:
            if relocated.active_job_id == initial["job_id"]:
                relocated.wait(initial["job_id"], timeout=5)
        self.assertEqual(1, len(self.planner.calls))
        self.assertEqual(1, len(relocated_library.load_manifest(initial["job_id"])["concept_batches"]))

    def test_missing_usage_marks_exact_total_incomplete_and_estimates_stay_integer(self) -> None:
        self.planner.usages = [ProviderUsage(101, True)]
        self.images.usages = [ProviderUsage(202, True), ProviderUsage(None, False)]
        started = self._start(
            candidate_count=2,
            models={**MODELS, "concept": "grok-imagine-image-quality"},
        )
        final = self._wait(started["job_id"])
        self.assertEqual(303, sum(final["costs"]["actual_by_operation"].values()))
        self.assertTrue(final["costs"]["actual_incomplete"])
        self.assertEqual(
            2 * 500_000_000,
            final["costs"]["estimated_ticks"],
        )
        self.assertIsInstance(final["costs"]["estimated_ticks"], int)

    def test_banked_response_is_recovered_if_candidate_publication_is_interrupted(self) -> None:
        real_update = self.library.update_manifest
        interrupted = False

        def fail_once_after_banking(job_id: str, change):
            nonlocal interrupted
            current = self.library.load_manifest(job_id)
            response_received = any(
                request["status"] == "response_received"
                for request in current["provider_requests"].values()
            )
            if current["assets"] and not current["candidates"] and response_received and not interrupted:
                interrupted = True
                raise OSError("simulated interruption after durable image banking")
            return real_update(job_id, change)

        with patch.object(self.library, "update_manifest", side_effect=fail_once_after_banking):
            started = self._start(candidate_count=2)
            final = self._wait(started["job_id"])
        self.assertTrue(interrupted)
        self.assertEqual("partial", final["status"])
        self.assertEqual(1, len(final["assets"]))
        self.assertEqual(1, len(final["candidates"]))
        candidate = final["candidates"][0]
        self.assertEqual(final["assets"][0]["asset_id"], candidate["asset_id"])
        self.assertEqual(1, final["progress"]["completed"])
        self.assertEqual(1, len(self.images.calls))
        self.assertEqual(11 + 22, sum(final["costs"]["actual_by_operation"].values()))
        self.assertFalse(final["costs"]["actual_incomplete"])

    def test_startup_reconciles_without_paid_retry_or_device_write(self) -> None:
        interrupted = self.library.create_job(
            prompt="Interrupted before provider response",
            target=TARGET,
            models=MODELS,
            loop_mode="smooth",
        )

        def mark_in_progress(manifest: dict) -> None:
            manifest["status"] = "in_progress"
            manifest["phase"] = "concept_generation"
            manifest["progress"] = {"completed": 0, "total": 2}
            manifest["concept_batches"].append(
                {
                    "batch_id": "11111111-1111-4111-8111-111111111111",
                    "kind": "initial",
                    "status": "planning",
                    "requested_count": 2,
                    "visual_brief": None,
                    "candidate_prompts": [],
                    "candidate_ids": [],
                    "created_at": manifest["created_at"],
                    "completed_at": None,
                }
            )
            manifest["provider_requests"]["concept_plan"] = {"status": "submitting"}
            manifest["costs"]["actual_incomplete"] = True

        self.library.update_manifest(interrupted["job_id"], mark_in_progress)

        banked = self.library.create_job(
            prompt="Response banked before candidate publication",
            target=TARGET,
            models=MODELS,
            loop_mode="smooth",
        )
        banked_batch = "22222222-2222-4222-8222-222222222222"

        def mark_response_received(manifest: dict) -> None:
            manifest["status"] = "in_progress"
            manifest["phase"] = "concept_generation"
            manifest["progress"] = {"completed": 0, "total": 1}
            manifest["concept_batches"].append(
                {
                    "batch_id": banked_batch,
                    "kind": "initial",
                    "status": "generating",
                    "requested_count": 1,
                    "visual_brief": "Recovered brief",
                    "candidate_prompts": ["Recovered candidate prompt"],
                    "candidate_ids": [],
                    "created_at": manifest["created_at"],
                    "completed_at": None,
                }
            )
            operation = f"candidate_attempt:{banked_batch}:0"
            manifest["provider_requests"]["concept_plan"] = {"status": "complete"}
            manifest["provider_requests"][operation] = {"status": "response_received"}
            manifest["costs"]["actual_by_operation"] = {
                "concept_plan": 11,
                operation: 22,
            }

        self.library.update_manifest(banked["job_id"], mark_response_received)
        banked_asset = self.library.bank_asset(
            banked["job_id"],
            kind="concept",
            data=self.images.payload,
            mime_type="image/png",
            origin=f"xai_concept:{banked_batch}:0",
        )
        paid_calls: list[str] = []
        coordinator = generation.GenerationCoordinator(
            self.library,
            planner_factory=lambda *_args: paid_calls.append("planner"),
            image_provider_factory=lambda *_args: paid_calls.append("image"),
            operation_gate=generation.OperationGate(),
        )
        with patch("am_configurator.writer.write_config") as write_config:
            actions = coordinator.reconcile_startup()
        self.assertEqual([], actions)
        self.assertEqual([], paid_calls)
        write_config.assert_not_called()
        reconciled = self.library.load_manifest(interrupted["job_id"])
        self.assertEqual("interrupted", reconciled["status"])
        self.assertEqual("interrupted", reconciled["phase"])
        recovered = self.library.load_manifest(banked["job_id"])
        self.assertEqual("partial", recovered["status"])
        self.assertEqual("interrupted", recovered["phase"])
        self.assertEqual(
            banked_asset["asset_id"], recovered["candidates"][0]["asset_id"]
        )
        self.assertEqual(33, sum(recovered["costs"]["actual_by_operation"].values()))
        self.assertFalse(recovered["costs"]["actual_incomplete"])


class _AdvancingClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class _DeferredWorker:
    def __init__(self, target) -> None:
        self._target = target
        self._ran = False

    def join(self, _timeout=None) -> None:
        if not self._ran:
            self._ran = True
            self._target()

    def is_alive(self) -> bool:
        return False


class DurableVideoGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "library"
        self.library = GeneratedAssetLibrary(self.root, minimum_free_bytes=1)
        self.planner = _VideoPlanner()
        self.video = _VideoProvider()
        self.downloader = _Downloader()
        self.processor = _Processor()
        self.clock = _AdvancingClock()
        self.planner_factory_calls: list[tuple[str, str]] = []
        self.video_factory_calls: list[tuple[str, str]] = []
        self.coordinator = self._coordinator()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _coordinator(self, **overrides: object) -> generation.GenerationCoordinator:
        def planner_factory(api_key: str, model: str):
            self.planner_factory_calls.append((api_key, model))
            return self.planner

        def video_factory(api_key: str, model: str):
            self.video_factory_calls.append((api_key, model))
            return self.video

        values = {
            "video_planner_factory": planner_factory,
            "video_provider_factory": video_factory,
            "downloader": self.downloader,
            "processor": self.processor,
            "ffmpeg_resolver": lambda: Path(__file__),
            "operation_gate": generation.OperationGate(),
            "monotonic": self.clock,
            "sleeper": self.clock.sleep,
            "poll_interval_seconds": 5,
            "foreground_timeout_seconds": 2,
        }
        values.update(overrides)
        return generation.GenerationCoordinator(self.library, **values)

    def _selectable_job(
        self,
        *,
        target: dict = TARGET,
        loop_mode: str = "smooth",
    ) -> tuple[dict, str]:
        manifest = self.library.create_job(
            prompt="A calm ember ribbon",
            target=target,
            models=MODELS,
            loop_mode=loop_mode,
        )
        asset = self.library.bank_asset(
            manifest["job_id"],
            kind="concept",
            data=_png_bytes(),
            mime_type="image/png",
            origin="test_concept",
        )

        def publish(current: dict) -> None:
            current["candidates"].append(
                {
                    "candidate_id": asset["asset_id"],
                    "asset_id": asset["asset_id"],
                    "batch_id": str(uuid.uuid4()),
                    "prompt": "A calm ember ribbon concept",
                    "revised_prompt": None,
                    "width": 20,
                    "height": 9,
                    "mime_type": "image/png",
                    "status": "complete",
                    "created_at": asset["created_at"],
                }
            )
            current["status"] = "awaiting_selection"
            current["phase"] = "awaiting_selection"

        return (
            self.library.update_manifest(manifest["job_id"], publish),
            asset["asset_id"],
        )

    def _start_animation(
        self,
        manifest: dict,
        candidate_id: str,
        **overrides: object,
    ) -> dict:
        values = {
            "candidate_id": candidate_id,
            "motion": "A gentle pulse",
            "loop_mode": manifest["loop_mode"],
            "api_key": "video-secret-key",
            "privacy_acknowledged": True,
        }
        values.update(overrides)
        return self.coordinator.start_animation(manifest["job_id"], **values)

    def test_selection_ownership_is_fail_closed_and_persisted_before_provider(self) -> None:
        manifest, candidate_id = self._selectable_job()
        other, other_candidate = self._selectable_job()
        with self.assertRaises(generation.GenerationValidationError):
            self._start_animation(manifest, other_candidate)
        self.assertIsNone(
            self.library.load_manifest(manifest["job_id"])["selected_candidate_id"]
        )
        self.assertEqual([], self.planner_factory_calls)
        self.assertEqual([], self.video_factory_calls)

        def assert_selection_is_durable() -> None:
            current = self.library.load_manifest(manifest["job_id"])
            self.assertEqual(candidate_id, current["selected_candidate_id"])
            self.assertEqual("video_planning", current["phase"])
            self.assertEqual(1, len(current["animation_attempts"]))
            self.assertEqual(candidate_id, current["animation_attempts"][0]["candidate_id"])
            self.assertEqual(900_000_000, current["costs"]["estimated_ticks"])
            self.assertEqual("submitting", current["provider_requests"]["video_plan"]["status"])

        self.planner.before_call = assert_selection_is_durable
        with patch("am_configurator.writer.write_config") as write_config:
            started = self._start_animation(manifest, candidate_id)
            final = self.coordinator.wait(started["job_id"], timeout=10)
        write_config.assert_not_called()
        self.assertEqual("ready", final["status"])
        self.assertEqual("ready_for_review", final["phase"])
        self.assertEqual({"video_plan": 31, self.video.request_id: 43}, final["costs"]["actual_by_operation"])
        self.assertFalse(final["costs"]["actual_incomplete"])
        self.assertNotIn("vidgen.x.ai", json.dumps(final))
        self.assertNotIn("signature", json.dumps(final).lower())
        self.assertNotEqual(other["job_id"], manifest["job_id"])

    def test_request_id_is_persisted_before_poll_and_poll_cost_replaces_observations(self) -> None:
        manifest, candidate_id = self._selectable_job()
        self.video.poll_outcomes = [
            VideoStatus(
                request_id=self.video.request_id,
                status="pending",
                usage=ProviderUsage(42, True),
            ),
            VideoStatus(
                request_id=self.video.request_id,
                status="done",
                usage=ProviderUsage(44, True),
                video_url="https://vidgen.x.ai/generated/final.mp4?token=ephemeral",
                duration=1,
            ),
        ]

        def assert_request_id_is_durable() -> None:
            current = self.library.load_manifest(manifest["job_id"])
            request = current["provider_requests"]["video"]
            self.assertEqual(self.video.request_id, request["request_id"])
            self.assertEqual(self.video.request_id, current["animation_attempts"][0]["request_id"])

        self.video.before_poll = assert_request_id_is_durable
        started = self._start_animation(manifest, candidate_id)
        final = self.coordinator.wait(started["job_id"], timeout=10)
        self.assertEqual(2, len(self.video.poll_calls))
        self.assertEqual(44, final["costs"]["actual_by_operation"][self.video.request_id])
        self.assertEqual(75, sum(final["costs"]["actual_by_operation"].values()))

    def test_transient_acceptance_write_failure_keeps_the_known_request_id(self) -> None:
        manifest, candidate_id = self._selectable_job()
        original_update = self.library.update_manifest
        failed_once = False

        def fail_first_accept(job_id: str, changes):
            nonlocal failed_once
            if getattr(changes, "__name__", "") == "accept" and not failed_once:
                failed_once = True
                raise OSError("transient manifest write failure")
            return original_update(job_id, changes)

        with patch.object(self.library, "update_manifest", side_effect=fail_first_accept):
            started = self._start_animation(manifest, candidate_id)
            final = self.coordinator.wait(started["job_id"], timeout=10)
        self.assertTrue(failed_once)
        self.assertEqual("ready", final["status"])
        self.assertEqual(1, len(self.video.submit_calls))
        self.assertEqual(self.video.request_id, final["provider_requests"]["video"]["request_id"])
        self.assertEqual(self.video.request_id, final["animation_attempts"][-1]["request_id"])

    def test_ambiguous_submit_is_never_retried_automatically(self) -> None:
        manifest, candidate_id = self._selectable_job()
        self.video.submit_failure = ProviderError(
            "unavailable", "the submit response was lost", usage=ProviderUsage(None, False)
        )
        started = self._start_animation(manifest, candidate_id)
        final = self.coordinator.wait(started["job_id"], timeout=10)
        self.assertEqual("submission_unknown", final["status"])
        self.assertEqual("interrupted", final["phase"])
        self.assertEqual(1, len(self.video.submit_calls))
        self.assertEqual([], self.video.poll_calls)
        self.assertEqual([], self.coordinator.reconcile_startup(api_key="video-secret-key"))
        self.assertEqual(1, len(self.video.submit_calls))

    def test_startup_resumes_accepted_request_without_replaying_paid_posts(self) -> None:
        manifest, candidate_id = self._selectable_job()
        attempt_id = str(uuid.uuid4())

        def accepted(current: dict) -> None:
            current["selected_candidate_id"] = candidate_id
            current["animation_attempts"].append(
                {
                    "attempt_id": attempt_id,
                    "candidate_id": candidate_id,
                    "loop_mode": "smooth",
                    "status": "polling",
                    "phase": "video_polling",
                    "motion": None,
                    "request_id": self.video.request_id,
                    "source_video_asset_id": None,
                    "frame_asset_ids": [],
                    "preview_asset_id": None,
                    "mapped_result_asset_id": None,
                    "created_at": current["updated_at"],
                    "completed_at": None,
                }
            )
            current["provider_requests"]["video"] = {
                "request_id": self.video.request_id,
                "status": "pending",
            }
            current["status"] = "in_progress"
            current["phase"] = "video_polling"

        self.library.update_manifest(manifest["job_id"], accepted)
        actions = self.coordinator.reconcile_startup(api_key="video-secret-key")
        self.assertEqual(
            [{"job_id": manifest["job_id"], "action": "resume_video_poll", "request_id": self.video.request_id}],
            actions,
        )
        final = self.coordinator.wait(manifest["job_id"], timeout=10)
        self.assertEqual("ready", final["status"])
        self.assertEqual([], self.planner.calls)
        self.assertEqual([], self.video.submit_calls)
        self.assertEqual(1, len(self.video.poll_calls))

    def test_foreground_timeout_and_bounded_safe_retries_do_not_abandon_video(self) -> None:
        manifest, candidate_id = self._selectable_job()
        self.video.poll_outcomes = [
            ProviderError("unavailable", "poll unavailable"),
            ProviderError("timeout", "poll timeout"),
            VideoStatus(
                request_id=self.video.request_id,
                status="pending",
                usage=ProviderUsage(None, False),
            ),
            VideoStatus(
                request_id=self.video.request_id,
                status="done",
                usage=ProviderUsage(45, True),
                video_url="https://vidgen.x.ai/generated/retry.mp4",
                duration=1,
            ),
        ]
        self.downloader.failures = 2
        observed_phases: list[str] = []

        def observe_phase() -> None:
            observed_phases.append(
                self.library.load_manifest(manifest["job_id"])["phase"]
            )

        self.video.before_poll = observe_phase
        started = self._start_animation(manifest, candidate_id)
        final = self.coordinator.wait(started["job_id"], timeout=10)
        self.assertEqual("ready", final["status"])
        self.assertIn("background_retrieval", observed_phases)
        self.assertEqual(4, len(self.video.poll_calls))
        self.assertEqual(3, len(self.downloader.calls))
        request = final["provider_requests"]["video"]
        self.assertEqual(2, request["poll_failures"])
        self.assertEqual(2, request["download_failures"])

    def test_cancel_after_acceptance_banks_video_without_local_processing(self) -> None:
        manifest, candidate_id = self._selectable_job()
        entered = threading.Event()
        release = threading.Event()
        self.video.poll_outcomes = [
            VideoStatus(
                request_id=self.video.request_id,
                status="pending",
                usage=ProviderUsage(None, False),
            ),
            VideoStatus(
                request_id=self.video.request_id,
                status="done",
                usage=ProviderUsage(46, True),
                video_url="https://vidgen.x.ai/generated/cancelled.mp4",
                duration=1,
            ),
        ]

        def block_first_poll() -> None:
            if not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(5))

        self.video.before_poll = block_first_poll
        started = self._start_animation(manifest, candidate_id)
        self.assertTrue(entered.wait(5))
        visible = self.coordinator.cancel(manifest["job_id"])
        self.assertEqual("cancelled", visible["status"])
        self.assertEqual("background_retrieval", visible["phase"])
        release.set()
        final = self.coordinator.wait(started["job_id"], timeout=10)
        self.assertEqual("cancelled_saved", final["status"])
        self.assertEqual([], self.processor.calls)
        videos = [asset for asset in final["assets"] if asset["kind"] == "source_video"]
        self.assertEqual(1, len(videos))
        self.assertEqual("cancelled_saved", videos[0]["status"])
        self.assertTrue(
            self.library.resolve_asset(manifest["job_id"], videos[0]["asset_id"]).path.is_file()
        )

    def test_cancel_before_worker_start_prevents_the_paid_video_plan(self) -> None:
        manifest, candidate_id = self._selectable_job()
        self.coordinator = self._coordinator(
            launcher=lambda target: _DeferredWorker(target)
        )
        started = self._start_animation(manifest, candidate_id)
        self.coordinator.cancel(manifest["job_id"])
        final = self.coordinator.wait(started["job_id"], timeout=10)
        self.assertEqual("cancelled", final["status"])
        self.assertEqual("video_cancelled", final["phase"])
        self.assertEqual([], self.planner.calls)
        self.assertEqual([], self.video.submit_calls)

    def test_local_failure_retains_mp4_and_explicit_retry_makes_no_provider_call(self) -> None:
        manifest, candidate_id = self._selectable_job()
        self.processor.failures = 1
        started = self._start_animation(manifest, candidate_id)
        failed = self.coordinator.wait(started["job_id"], timeout=10)
        self.assertEqual("ready_to_process", failed["status"])
        videos = [asset for asset in failed["assets"] if asset["kind"] == "source_video"]
        self.assertEqual(1, len(videos))
        self.assertTrue(
            self.library.resolve_asset(manifest["job_id"], videos[0]["asset_id"]).path.is_file()
        )
        paid_counts = (
            len(self.planner.calls),
            len(self.video.submit_calls),
            len(self.video.poll_calls),
        )
        retried = self.coordinator.retry_local(manifest["job_id"])
        final = self.coordinator.wait(retried["job_id"], timeout=10)
        self.assertEqual("ready", final["status"])
        self.assertEqual(
            paid_counts,
            (len(self.planner.calls), len(self.video.submit_calls), len(self.video.poll_calls)),
        )
        self.assertEqual(80, len([asset for asset in final["assets"] if asset["kind"] == "frame"]))
        self.assertEqual(1, len([asset for asset in final["assets"] if asset["kind"] == "preview_poster"]))
        results = [asset for asset in final["assets"] if asset["kind"] == "mapped_result"]
        self.assertEqual(1, len(results))
        mapped = json.loads(
            self.library.resolve_asset(manifest["job_id"], results[0]["asset_id"]).path.read_text()
        )
        self.assertEqual(80, mapped["source_frames"])
        self.assertEqual(34, mapped["duration_ms"])
        self.assertEqual(80 * 34, mapped["source_duration_ms"])
        self.assertFalse(mapped["timing_resampled"])

    def test_startup_adopts_banked_frames_and_mapping_after_final_manifest_interruption(self) -> None:
        manifest, candidate_id = self._selectable_job()
        started = self._start_animation(manifest, candidate_id)
        complete = self.coordinator.wait(started["job_id"], timeout=10)
        attempt_id = complete["animation_attempts"][-1]["attempt_id"]
        paid_counts = (
            len(self.planner.calls),
            len(self.video.submit_calls),
            len(self.video.poll_calls),
        )

        def simulate_interruption(current: dict) -> None:
            attempt = current["animation_attempts"][-1]
            attempt["status"] = "processing"
            attempt["phase"] = "local_processing"
            attempt["frame_asset_ids"] = []
            attempt["preview_asset_id"] = None
            attempt["mapped_result_asset_id"] = None
            attempt["completed_at"] = None
            current["status"] = "in_progress"
            current["phase"] = "local_processing"
            current["progress"] = {"completed": 0, "total": 80}

        self.library.update_manifest(manifest["job_id"], simulate_interruption)
        actions = self.coordinator.reconcile_startup()
        self.assertEqual([], actions)
        recovered = self.library.load_manifest(manifest["job_id"])
        attempt = recovered["animation_attempts"][-1]
        self.assertEqual(attempt_id, attempt["attempt_id"])
        self.assertEqual("ready", recovered["status"])
        self.assertEqual("ready_for_review", recovered["phase"])
        self.assertEqual(80, len(attempt["frame_asset_ids"]))
        self.assertIsNotNone(attempt["preview_asset_id"])
        self.assertIsNotNone(attempt["mapped_result_asset_id"])
        self.assertEqual(
            paid_counts,
            (len(self.planner.calls), len(self.video.submit_calls), len(self.video.poll_calls)),
        )

    def test_every_loop_and_device_family_uses_exact_cap_and_mapping_parity(self) -> None:
        cases = (
            (TARGET, "smooth", 80),
            (
                {
                    "family": "80",
                    "product_id": "AM21",
                    "raster": {"width": 18, "height": 7},
                    "targets": ["keyframes", "spotlight_frames"],
                },
                "none",
                200,
            ),
            (
                {
                    "family": "ALICE",
                    "product_id": "ALICE",
                    "raster": {"width": 16, "height": 5},
                    "targets": ["keyframes"],
                },
                "ping_pong",
                186,
            ),
        )
        with patch("am_configurator.writer.write_config") as write_config:
            for target, loop_mode, frame_cap in cases:
                with self.subTest(family=target["family"], loop_mode=loop_mode):
                    self.planner = _VideoPlanner()
                    self.video = _VideoProvider()
                    self.downloader = _Downloader()
                    self.processor = _Processor()
                    self.coordinator = self._coordinator()
                    manifest, candidate_id = self._selectable_job(
                        target=target, loop_mode=loop_mode
                    )
                    started = self._start_animation(manifest, candidate_id)
                    final = self.coordinator.wait(started["job_id"], timeout=20)
                    call = self.processor.calls[-1]
                    self.assertEqual(frame_cap, call["frame_count"])
                    self.assertEqual(loop_mode, call["loop_mode"])
                    self.assertEqual(target["raster"]["width"], call["width"])
                    self.assertEqual(target["raster"]["height"], call["height"])
                    frames = [asset for asset in final["assets"] if asset["kind"] == "frame"]
                    self.assertEqual(frame_cap, len(frames))
                    result_asset = next(
                        asset for asset in final["assets"] if asset["kind"] == "mapped_result"
                    )
                    mapped = json.loads(
                        self.library.resolve_asset(
                            manifest["job_id"], result_asset["asset_id"]
                        ).path.read_text()
                    )
                    self.assertEqual(frame_cap, mapped["source_frames"])
                    self.assertEqual(frame_cap, mapped["decoded_frames"])
                    self.assertEqual(34, mapped["duration_ms"])
                    self.assertEqual(frame_cap * 34, mapped["source_duration_ms"])
                    self.assertFalse(mapped["timing_resampled"])
                    self.assertEqual(set(target["targets"]), set(mapped["tracks"]))
                    for track in mapped["tracks"].values():
                        self.assertEqual(frame_cap, track["frame_count"])
                        self.assertEqual(frame_cap, len(track["frames"]))
        write_config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
