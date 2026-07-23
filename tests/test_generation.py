from __future__ import annotations

import hashlib
import io
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from am_configurator import generation
from am_configurator.library import GeneratedAssetLibrary
from am_configurator.llm import ProviderError, ProviderUsage, VideoStatus
from am_configurator.media import DownloadedVideo, MediaError, ProcessedAnimation


TARGET = {
    "family": "CB",
    "product_id": "CB_TEST",
    "raster": {"width": 40, "height": 5},
    "targets": ["frames"],
}
HISTORICAL_MODELS = {
    "interpreter": "grok-4.5",
    "concept": "grok-imagine-image",
    "video": "grok-imagine-video-1.5",
}


def _png_bytes(color: tuple[int, int, int] = (32, 64, 128)) -> bytes:
    output = io.BytesIO()
    with Image.new("RGB", (40, 5), color) as image:
        image.save(output, format="PNG")
    return output.getvalue()


class _AdvancingClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class _CompletedWorker:
    def join(self, _timeout=None) -> None:
        return None

    def is_alive(self) -> bool:
        return False


def _run_synchronously(target):
    target()
    return _CompletedWorker()


class _VideoStatusProvider:
    def __init__(self, request_id: str = "video_request_123") -> None:
        self.request_id = request_id
        self.poll_calls: list[tuple[str, float]] = []
        self.outcomes: list[VideoStatus | ProviderError] = [
            VideoStatus(
                request_id=request_id,
                status="done",
                usage=ProviderUsage(43, True),
                video_url="https://vidgen.x.ai/generated/video.mp4?signature=secret",
                duration=1,
            )
        ]

    def poll(self, request_id: object, deadline: float) -> VideoStatus:
        assert isinstance(request_id, str)
        self.poll_calls.append((request_id, deadline))
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
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
        return DownloadedVideo(
            path=path,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )


class _Processor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

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
            "width": int(width),
            "height": int(height),
            "frame_count": int(frame_count),
            "loop_mode": loop_mode,
            "deadline": deadline,
            "cancelled": cancelled,
        }
        self.calls.append(call)
        destination = call["destination"]
        destination.mkdir(mode=0o700)
        frame_paths = []
        for index in range(call["frame_count"]):
            path = destination / f"frame-{index + 1:04d}.png"
            with Image.new(
                "RGB",
                (call["width"], call["height"]),
                ((index * 3) % 256, (index * 5) % 256, (index * 7) % 256),
            ) as image:
                image.save(path, format="PNG")
            frame_paths.append(path)
        return ProcessedAnimation(
            directory=destination,
            frame_paths=tuple(frame_paths),
            frame_count=call["frame_count"],
            width=call["width"],
            height=call["height"],
            loop_mode=loop_mode,
        )


class HistoricalGenerationRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "library"
        self.library = GeneratedAssetLibrary(self.root, minimum_free_bytes=1)
        self.gate = generation.OperationGate()
        self.provider = _VideoStatusProvider()
        self.downloader = _Downloader()
        self.processor = _Processor()
        self.clock = _AdvancingClock()
        self.provider_factory_calls: list[tuple[str, str]] = []

        def provider_factory(api_key: str, historical_model: str):
            self.provider_factory_calls.append((api_key, historical_model))
            return self.provider

        self.coordinator = generation.GenerationCoordinator(
            self.library,
            video_provider_factory=provider_factory,
            downloader=self.downloader,
            processor=self.processor,
            ffmpeg_resolver=lambda: Path(__file__),
            operation_gate=self.gate,
            launcher=_run_synchronously,
            monotonic=self.clock,
            sleeper=self.clock.sleep,
            poll_interval_seconds=5,
            foreground_timeout_seconds=2,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _historical_job(self) -> tuple[dict, str]:
        manifest = self.library.create_job(
            prompt="A calm ember ribbon",
            target=TARGET,
            models=HISTORICAL_MODELS,
            loop_mode="smooth",
        )
        asset = self.library.bank_asset(
            manifest["job_id"],
            kind="concept",
            data=_png_bytes(),
            mime_type="image/png",
            origin="historical_concept",
        )

        def publish(current: dict) -> None:
            current["selected_candidate_id"] = asset["asset_id"]
            current["candidates"].append(
                {
                    "candidate_id": asset["asset_id"],
                    "asset_id": asset["asset_id"],
                    "batch_id": str(uuid.uuid4()),
                    "prompt": "A calm ember ribbon concept",
                    "revised_prompt": None,
                    "width": 40,
                    "height": 5,
                    "mime_type": "image/png",
                    "status": "complete",
                    "created_at": asset["created_at"],
                }
            )
            current["status"] = "awaiting_selection"
            current["phase"] = "awaiting_selection"

        return self.library.update_manifest(manifest["job_id"], publish), asset["asset_id"]

    def _accepted_video_job(self) -> dict:
        manifest, candidate_id = self._historical_job()
        attempt_id = str(uuid.uuid4())

        def accepted(current: dict) -> None:
            current["animation_attempts"].append(
                {
                    "attempt_id": attempt_id,
                    "candidate_id": candidate_id,
                    "loop_mode": "smooth",
                    "status": "polling",
                    "phase": "video_polling",
                    "motion": None,
                    "plan": None,
                    "request_id": self.provider.request_id,
                    "selected_still_asset_id": None,
                    "source_video_asset_id": None,
                    "frame_asset_ids": [],
                    "preview_asset_id": None,
                    "mapped_result_asset_id": None,
                    "created_at": current["updated_at"],
                    "completed_at": None,
                }
            )
            current["provider_requests"]["video"] = {
                "request_id": self.provider.request_id,
                "status": "pending",
                "poll_failures": 0,
                "download_failures": 0,
            }
            current["status"] = "in_progress"
            current["phase"] = "video_polling"
            current["progress"] = {"completed": 0, "total": 80}

        return self.library.update_manifest(manifest["job_id"], accepted)

    def test_startup_resumes_only_the_accepted_request_and_banks_local_artifacts(self) -> None:
        manifest = self._accepted_video_job()

        with patch("am_configurator.writer.write_config") as write_config:
            actions = self.coordinator.reconcile_startup(api_key="video-secret-key")

        self.assertEqual(
            [
                {
                    "job_id": manifest["job_id"],
                    "action": "resume_video_poll",
                    "request_id": self.provider.request_id,
                }
            ],
            actions,
        )
        final = self.library.load_manifest(manifest["job_id"])
        attempt = final["animation_attempts"][-1]
        self.assertEqual("ready", final["status"])
        self.assertEqual(80, len(attempt["frame_asset_ids"]))
        self.assertIsInstance(attempt["preview_asset_id"], str)
        self.assertIsInstance(attempt["mapped_result_asset_id"], str)
        self.assertEqual(1, len(self.provider.poll_calls))
        self.assertEqual(1, len(self.downloader.calls))
        self.assertEqual(1, len(self.processor.calls))
        self.assertEqual(
            [("video-secret-key", HISTORICAL_MODELS["video"])],
            self.provider_factory_calls,
        )
        write_config.assert_not_called()

    def test_recovery_retries_safe_reads_without_replaying_a_submission(self) -> None:
        manifest = self._accepted_video_job()
        self.provider.outcomes = [
            ProviderError("unavailable", "poll unavailable"),
            VideoStatus(
                request_id=self.provider.request_id,
                status="done",
                usage=ProviderUsage(45, True),
                video_url="https://vidgen.x.ai/generated/retry.mp4",
                duration=1,
            ),
        ]
        self.downloader.failures = 1

        self.coordinator.reconcile_startup(api_key="video-secret-key")

        final = self.library.load_manifest(manifest["job_id"])
        self.assertEqual("ready", final["status"])
        self.assertEqual(2, len(self.provider.poll_calls))
        self.assertEqual(2, len(self.downloader.calls))
        self.assertFalse(hasattr(self.provider, "submit"))

    def test_banked_concept_response_is_adopted_without_a_provider(self) -> None:
        manifest = self.library.create_job(
            prompt="Response banked before candidate publication",
            target=TARGET,
            models=HISTORICAL_MODELS,
            loop_mode="smooth",
        )
        batch_id = "22222222-2222-4222-8222-222222222222"

        def mark_response_received(current: dict) -> None:
            current["status"] = "in_progress"
            current["phase"] = "concept_generation"
            current["progress"] = {"completed": 0, "total": 1}
            current["concept_batches"].append(
                {
                    "batch_id": batch_id,
                    "kind": "initial",
                    "status": "generating",
                    "requested_count": 1,
                    "visual_brief": "Recovered brief",
                    "candidate_prompts": ["Recovered candidate prompt"],
                    "candidate_ids": [],
                    "created_at": current["created_at"],
                    "completed_at": None,
                }
            )
            operation = f"candidate_attempt:{batch_id}:0"
            current["provider_requests"]["concept_plan"] = {"status": "complete"}
            current["provider_requests"][operation] = {"status": "response_received"}
            current["costs"]["actual_by_operation"] = {
                "concept_plan": 11,
                operation: 22,
            }

        self.library.update_manifest(manifest["job_id"], mark_response_received)
        asset = self.library.bank_asset(
            manifest["job_id"],
            kind="concept",
            data=_png_bytes(),
            mime_type="image/png",
            origin=f"xai_concept:{batch_id}:0",
        )

        self.assertEqual([], self.coordinator.reconcile_startup())

        recovered = self.library.load_manifest(manifest["job_id"])
        self.assertEqual("partial", recovered["status"])
        self.assertEqual(asset["asset_id"], recovered["candidates"][0]["asset_id"])
        self.assertEqual(33, sum(recovered["costs"]["actual_by_operation"].values()))
        self.assertFalse(recovered["costs"]["actual_incomplete"])
        self.assertEqual([], self.provider_factory_calls)

    def test_reconciliation_reclassifies_interrupted_planning_without_paid_work(self) -> None:
        manifest, candidate_id = self._historical_job()
        attempt_id = str(uuid.uuid4())

        def interrupted(current: dict) -> None:
            current["animation_attempts"].append(
                {
                    "attempt_id": attempt_id,
                    "candidate_id": candidate_id,
                    "loop_mode": "smooth",
                    "status": "planning",
                    "phase": "video_planning",
                    "motion": None,
                    "plan": None,
                    "request_id": None,
                    "selected_still_asset_id": None,
                    "source_video_asset_id": None,
                    "frame_asset_ids": [],
                    "preview_asset_id": None,
                    "mapped_result_asset_id": None,
                    "created_at": current["updated_at"],
                    "completed_at": None,
                }
            )
            current["provider_requests"]["video_plan"] = {"status": "submitting"}
            current["status"] = "in_progress"
            current["phase"] = "video_planning"

        self.library.update_manifest(manifest["job_id"], interrupted)

        self.assertEqual([], self.coordinator.reconcile_startup())

        current = self.library.load_manifest(manifest["job_id"])
        self.assertEqual("interrupted", current["status"])
        self.assertEqual("interrupted", current["animation_attempts"][-1]["status"])
        self.assertEqual([], self.provider_factory_calls)

    def test_banked_animation_recovery_is_idempotent(self) -> None:
        manifest = self._accepted_video_job()
        self.coordinator.reconcile_startup(api_key="video-secret-key")
        complete = self.library.load_manifest(manifest["job_id"])
        completed_at = complete["animation_attempts"][-1]["completed_at"]

        def simulate_interruption(current: dict) -> None:
            attempt = current["animation_attempts"][-1]
            attempt["status"] = "processing"
            attempt["phase"] = "local_processing"
            attempt["frame_asset_ids"] = []
            attempt["preview_asset_id"] = None
            attempt["mapped_result_asset_id"] = None
            attempt["completed_at"] = completed_at
            current["status"] = "in_progress"
            current["phase"] = "local_processing"

        self.library.update_manifest(manifest["job_id"], simulate_interruption)
        self.assertEqual([], self.coordinator.reconcile_startup())
        repaired = self.library.load_manifest(manifest["job_id"])
        self.assertEqual("ready", repaired["status"])
        self.assertEqual(80, len(repaired["animation_attempts"][-1]["frame_asset_ids"]))
        self.assertEqual(completed_at, repaired["animation_attempts"][-1]["completed_at"])

        manifest_path = self.root / "jobs" / manifest["job_id"] / "manifest.json"
        before = manifest_path.read_bytes()
        self.assertEqual([], self.coordinator.reconcile_startup())
        self.assertEqual(before, manifest_path.read_bytes())

    def test_cancel_marks_only_the_active_historical_request(self) -> None:
        manifest = self._accepted_video_job()
        token, _cancelled = self.gate.begin(manifest["job_id"])
        try:
            cancelled = self.coordinator.cancel(manifest["job_id"])
            self.assertEqual("cancelled", cancelled["status"])
            self.assertEqual("background_retrieval", cancelled["phase"])
            with self.assertRaises(generation.GenerationNotActiveError):
                self.coordinator.cancel("00000000-0000-4000-8000-000000000000")
        finally:
            self.gate.finish(token)

    def test_startup_reconciliation_never_mutates_while_admission_is_active(self) -> None:
        token, _cancelled = self.gate.begin("live-generation")
        try:
            with (
                patch.object(self.library, "reconcile", wraps=self.library.reconcile) as reconcile,
                self.assertRaises(generation.GenerationBusyError),
            ):
                self.coordinator.reconcile_startup()
            reconcile.assert_not_called()
        finally:
            self.gate.finish(token)


if __name__ == "__main__":
    unittest.main()
