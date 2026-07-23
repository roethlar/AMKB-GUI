"""Shared admission and historical Lighting Studio job recovery.

Legacy paid concept/video creation is retired.  This module retains the
process-wide operation gate plus the smallest poll, download, local processing,
and banked-asset recovery surface needed for already-accepted historical jobs.
"""
from __future__ import annotations

import copy
import json
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from .library import GeneratedAssetLibrary, LibraryError, ManifestError
from .llm import (
    MODEL_FRAME_CAPS,
    ProviderError,
    ProviderUsage,
    VideoStatus,
    XaiVideoProvider,
)
from .media import (
    DownloadedVideo,
    MediaCancelled,
    MediaError,
    ProcessedAnimation,
    download_video,
    process_video_frames,
)


DEFAULT_OPERATION_TIMEOUT_SECONDS = 10 * 60
DEFAULT_FOREGROUND_TIMEOUT_SECONDS = 10 * 60
DEFAULT_VIDEO_POLL_INTERVAL_SECONDS = 5
DEFAULT_SAFE_RETRY_LIMIT = 3
ANIMATION_FRAME_DURATION_MS = 34
_SAFE_RETRY_CODES = frozenset({"rate_limited", "timeout", "unavailable"})


class GenerationError(RuntimeError):
    """Base class for safe coordinator failures before a worker owns the job."""


class GenerationValidationError(GenerationError):
    """A request was invalid and no provider call was made."""


class GenerationBusyError(GenerationError):
    """Another paid or local generation operation currently owns the process."""


class GenerationNotActiveError(GenerationError):
    """Cancellation targeted a job that does not own the active operation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_target_snapshot(value: object) -> dict:
    """Validate a durable target against the app's canonical device layouts."""
    if not isinstance(value, Mapping):
        raise GenerationValidationError("target must be an object")
    allowed = {"family", "product_id", "raster", "targets", "frame_cap"}
    if not {"family", "product_id", "raster", "targets"}.issubset(value) or not set(
        value
    ).issubset(allowed):
        raise GenerationValidationError("target snapshot is incomplete")
    family = value["family"]
    if not isinstance(family, str) or family not in MODEL_FRAME_CAPS:
        raise GenerationValidationError("target device family is unsupported")
    raster = value["raster"]
    if not isinstance(raster, Mapping) or set(raster) != {"width", "height"}:
        raise GenerationValidationError("target raster is invalid")
    width = raster["width"]
    height = raster["height"]
    if any(
        not isinstance(item, int)
        or isinstance(item, bool)
        or not 1 <= item <= 4096
        for item in (width, height)
    ):
        raise GenerationValidationError("target raster is invalid")
    targets = value["targets"]
    if (
        not isinstance(targets, (list, tuple))
        or not 1 <= len(targets) <= 16
        or not all(
            isinstance(item, str)
            and item
            and len(item) <= 200
            and not any(character.isspace() for character in item)
            for item in targets
        )
        or len(set(targets)) != len(targets)
    ):
        raise GenerationValidationError("target names are invalid")
    expected_cap = MODEL_FRAME_CAPS[family]
    if "frame_cap" in value and value["frame_cap"] != expected_cap:
        raise GenerationValidationError("target frame cap does not match its family")
    product_id = value["product_id"]
    if (
        not isinstance(product_id, str)
        or not product_id
        or len(product_id) > 200
        or any(character.isspace() for character in product_id)
    ):
        raise GenerationValidationError("target product ID is invalid")
    try:
        # Imported lazily so server.py can inject this coordinator in Task 9
        # without creating an import-time cycle.
        from .server import generation_spec

        spec, resolved_targets = generation_spec(product_id, list(targets), None)
    except (TypeError, ValueError):
        raise GenerationValidationError(
            "the product and LED targets are not a supported generation layout"
        ) from None
    if (
        spec.model != family
        or spec.width != width
        or spec.height != height
        or spec.max_frames != expected_cap
        or resolved_targets != list(targets)
    ):
        raise GenerationValidationError(
            "the target snapshot does not match the product's generation layout"
        )
    snapshot = {
        "family": family,
        "product_id": product_id,
        "raster": {"width": width, "height": height},
        "targets": resolved_targets,
        "frame_cap": expected_cap,
    }
    return snapshot


class OperationGate:
    """One non-blocking process operation lease with a shared cancel event."""

    def __init__(self) -> None:
        self._lease = threading.Lock()
        self._state_lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._idle_callbacks: list[Callable[[], None]] = []
        self._token: object | None = None
        self._job_id: str | None = None
        self._cancelled: threading.Event | None = None

    @property
    def active_job_id(self) -> str | None:
        with self._state_lock:
            return self._job_id

    @property
    def is_active(self) -> bool:
        with self._state_lock:
            return self._token is not None

    def wait_until_idle(self) -> None:
        """Block a background reconciler until the current lease is released."""
        self._idle.wait()

    def call_when_idle(self, callback: Callable[[], None]) -> None:
        """Run ``callback`` now or once after the current lease finishes."""
        run_now = False
        with self._state_lock:
            if self._token is None and not self._lease.locked():
                run_now = True
            else:
                self._idle_callbacks.append(callback)
        if run_now:
            callback()

    def begin(self, job_id: str | None = None) -> tuple[object, threading.Event]:
        if not self._lease.acquire(blocking=False):
            raise GenerationBusyError("another generation operation is already active")
        self._idle.clear()
        token = object()
        cancelled = threading.Event()
        with self._state_lock:
            self._token = token
            self._job_id = job_id
            self._cancelled = cancelled
        return token, cancelled

    def bind(self, token: object, job_id: str) -> None:
        with self._state_lock:
            if self._token is not token:
                raise GenerationError("the generation operation lease was lost")
            self._job_id = job_id

    def require(self, token: object) -> None:
        """Prove that a caller owns the current admission lease."""
        with self._state_lock:
            if self._token is not token:
                raise GenerationError("the generation operation lease was lost")

    def request_cancel(self, job_id: str) -> bool:
        with self._state_lock:
            if self._job_id != job_id or self._cancelled is None:
                return False
            self._cancelled.set()
            return True

    def finish(self, token: object) -> None:
        callbacks: list[Callable[[], None]] = []
        with self._state_lock:
            if self._token is not token:
                return
            self._token = None
            self._job_id = None
            self._cancelled = None
            self._lease.release()
            self._idle.set()
            callbacks = self._idle_callbacks
            self._idle_callbacks = []
        for callback in callbacks:
            try:
                callback()
            except Exception:
                # Admission release must never be lost because a deferred
                # recovery callback failed; the durable manifest remains the
                # source for a later startup reconciliation.
                continue


_PROCESS_OPERATION_GATE = OperationGate()
# Shared by historical recovery and procedural generation so provider/local
# work remains single-flight across both pipelines.
PROCESS_OPERATION_GATE = _PROCESS_OPERATION_GATE


def _default_video_provider_factory(api_key: str, _historical_model: str):
    return XaiVideoProvider(api_key)


def _default_ffmpeg_resolver() -> Path:
    from .ffmpeg_runtime import get_ffmpeg_runtime

    return get_ffmpeg_runtime()


def _default_mapper(images, durations_ms, targets, *, product_id):
    from .server import frames_to_led_tracks

    return frames_to_led_tracks(
        images,
        durations_ms,
        targets,
        resample="box",
        product_id=product_id,
    )


def _default_launcher(target: Callable[[], None]):
    worker = threading.Thread(
        target=target,
        name="am-lighting-generation",
        daemon=True,
    )
    worker.start()
    return worker


def _batch(manifest: dict, batch_id: str) -> dict:
    matches = [item for item in manifest["concept_batches"] if item.get("batch_id") == batch_id]
    if len(matches) != 1:
        raise ManifestError("The concept batch was not found.")
    return matches[0]


def _animation_attempt(manifest: dict, attempt_id: str | None = None) -> dict:
    attempts = manifest["animation_attempts"]
    if attempt_id is None:
        if not attempts:
            raise ManifestError("The animation attempt was not found.")
        return attempts[-1]
    matches = [item for item in attempts if item.get("attempt_id") == attempt_id]
    if len(matches) != 1:
        raise ManifestError("The animation attempt was not found.")
    return matches[0]


def _usage_cost(usage: object) -> int | None:
    if not isinstance(usage, ProviderUsage) or usage.reported is not True:
        return None
    cost = usage.cost_in_usd_ticks
    if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
        return None
    return cost


def _refresh_cost_completeness(manifest: dict) -> None:
    actual = manifest["costs"]["actual_by_operation"]
    charged_operations: list[str] = []
    for operation, request in manifest["provider_requests"].items():
        if operation == "video" and isinstance(request.get("request_id"), str):
            charged_operations.append(request["request_id"])
        else:
            charged_operations.append(operation)
    manifest["costs"]["actual_incomplete"] = any(
        operation not in actual for operation in charged_operations
    )


def _record_usage(manifest: dict, operation: str, usage: object) -> None:
    cost = _usage_cost(usage)
    if cost is not None:
        manifest["costs"]["actual_by_operation"][operation] = cost
    _refresh_cost_completeness(manifest)


class GenerationCoordinator:
    """Recover historical jobs without retaining paid mutation entry points."""

    def __init__(
        self,
        library: GeneratedAssetLibrary,
        *,
        video_provider_factory: Callable[[str, str], object] = _default_video_provider_factory,
        downloader: Callable[..., object] = download_video,
        processor: Callable[..., object] = process_video_frames,
        ffmpeg_resolver: Callable[[], object] = _default_ffmpeg_resolver,
        mapper: Callable[..., object] = _default_mapper,
        operation_gate: OperationGate = _PROCESS_OPERATION_GATE,
        launcher: Callable[[Callable[[], None]], object] = _default_launcher,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
        foreground_timeout_seconds: float = DEFAULT_FOREGROUND_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_VIDEO_POLL_INTERVAL_SECONDS,
        safe_retry_limit: int = DEFAULT_SAFE_RETRY_LIMIT,
    ) -> None:
        if not isinstance(library, GeneratedAssetLibrary):
            raise TypeError("library must be a GeneratedAssetLibrary")
        if (
            isinstance(operation_timeout_seconds, bool)
            or not isinstance(operation_timeout_seconds, (int, float))
            or not 1 <= operation_timeout_seconds <= 3600
        ):
            raise ValueError("operation_timeout_seconds is invalid")
        if (
            isinstance(foreground_timeout_seconds, bool)
            or not isinstance(foreground_timeout_seconds, (int, float))
            or not 0 < foreground_timeout_seconds <= 3600
        ):
            raise ValueError("foreground_timeout_seconds is invalid")
        if (
            isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or not 0 <= poll_interval_seconds <= 60
        ):
            raise ValueError("poll_interval_seconds is invalid")
        if (
            isinstance(safe_retry_limit, bool)
            or not isinstance(safe_retry_limit, int)
            or not 1 <= safe_retry_limit <= 10
        ):
            raise ValueError("safe_retry_limit is invalid")
        self._library = library
        self._video_provider_factory = video_provider_factory
        self._downloader = downloader
        self._processor = processor
        self._ffmpeg_resolver = ffmpeg_resolver
        self._mapper = mapper
        self._gate = operation_gate
        self._launcher = launcher
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._operation_timeout_seconds = float(operation_timeout_seconds)
        self._foreground_timeout_seconds = float(foreground_timeout_seconds)
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._safe_retry_limit = safe_retry_limit

    @property
    def active_job_id(self) -> str | None:
        return self._gate.active_job_id

    @staticmethod
    def _video_spec(manifest: dict):
        snapshot = canonical_target_snapshot(manifest["target"])
        from .server import generation_spec

        spec, targets = generation_spec(
            snapshot["product_id"], snapshot["targets"], snapshot["frame_cap"]
        )
        if spec.max_frames != MODEL_FRAME_CAPS[snapshot["family"]]:
            raise GenerationValidationError("the target frame cap is invalid")
        return spec, targets

    def _launch_video_worker(
        self,
        job_id: str,
        token: object,
        api_key: str,
        target: Callable[[], None],
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        def run() -> None:
            try:
                target()
            finally:
                self._gate.finish(token)
                if on_finished is not None:
                    try:
                        on_finished()
                    except Exception:
                        pass

        try:
            self._launcher(run)
        except Exception as exc:
            try:
                self._library.record_error(
                    job_id,
                    code="worker_start_failed",
                    message=str(exc) or "The animation worker could not be started.",
                    sensitive_values=(api_key,),
                )
                self._library.update_manifest(
                    job_id, {"status": "failed", "phase": "worker_start_failed"}
                )
            finally:
                self._gate.finish(token)
            raise GenerationError("the animation worker could not be started") from None

    def _record_video_error(
        self,
        job_id: str,
        *,
        code: str,
        message: object,
        api_key: str,
    ) -> None:
        self._library.record_error(
            job_id,
            code=code,
            message=message,
            sensitive_values=(api_key,),
        )

    def _mark_background_retrieval(
        self,
        job_id: str,
        attempt_id: str,
        *,
        cancelled: threading.Event,
        foreground_deadline: float,
    ) -> bool:
        background = cancelled.is_set() or self._monotonic() >= foreground_deadline
        if not background:
            return False

        def update(manifest: dict) -> None:
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["phase"] = "background_retrieval"
            if attempt["status"] != "cancelled":
                attempt["status"] = "retrieving"
            manifest["phase"] = "background_retrieval"
            if cancelled.is_set():
                manifest["status"] = "cancelled"
                attempt["status"] = "cancelled"
                if manifest["cancel_requested_at"] is None:
                    manifest["cancel_requested_at"] = _now_iso()

        self._library.update_manifest(job_id, update)
        return True

    def _record_video_retry(
        self,
        job_id: str,
        request_id: str,
        *,
        field: str,
        error: ProviderError | MediaError,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            request = manifest["provider_requests"]["video"]
            request[field] = int(request.get(field, 0)) + 1
            request["error_code"] = error.code
            if field == "poll_failures":
                request["last_polled_at"] = timestamp
                if isinstance(error, ProviderError):
                    _record_usage(manifest, request_id, error.usage)

        self._library.update_manifest(job_id, update)

    def _pause_accepted_request(
        self,
        job_id: str,
        attempt_id: str,
        *,
        code: str,
        message: object,
        api_key: str,
        cancelled: threading.Event,
    ) -> None:
        def update(manifest: dict) -> None:
            attempt = _animation_attempt(manifest, attempt_id)
            if cancelled.is_set() or manifest["cancel_requested_at"] is not None:
                manifest["status"] = "cancelled"
                manifest["phase"] = "background_retrieval"
                attempt["status"] = "cancelled"
                attempt["phase"] = "background_retrieval"
            else:
                manifest["status"] = "interrupted"
                manifest["phase"] = "video_polling"
                attempt["status"] = "interrupted"
                attempt["phase"] = "video_polling"

        self._library.update_manifest(job_id, update)
        self._record_video_error(
            job_id, code=code, message=message, api_key=api_key
        )

    def _poll_and_retrieve(
        self,
        job_id: str,
        attempt_id: str,
        provider: object,
        request_id: str,
        api_key: str,
        cancelled: threading.Event,
    ) -> None:
        foreground_deadline = self._monotonic() + self._foreground_timeout_seconds
        consecutive_failures = 0
        while True:
            background = self._mark_background_retrieval(
                job_id,
                attempt_id,
                cancelled=cancelled,
                foreground_deadline=foreground_deadline,
            )
            try:
                observation = provider.poll(
                    request_id,
                    self._monotonic() + self._operation_timeout_seconds,
                )
                if (
                    not isinstance(observation, VideoStatus)
                    or observation.request_id != request_id
                ):
                    raise ProviderError(
                        "bad_response", "video provider returned an invalid status"
                    )
            except ProviderError as error:
                if error.code not in _SAFE_RETRY_CODES:
                    self._finish_video_terminal(
                        job_id, attempt_id, request_id, error, api_key
                    )
                    return
                consecutive_failures += 1
                self._record_video_retry(
                    job_id,
                    request_id,
                    field="poll_failures",
                    error=error,
                )
                if consecutive_failures >= self._safe_retry_limit:
                    self._pause_accepted_request(
                        job_id,
                        attempt_id,
                        code="video_poll_interrupted",
                        message=error.message,
                        api_key=api_key,
                        cancelled=cancelled,
                    )
                    return
                self._sleeper(self._poll_interval_seconds)
                continue

            consecutive_failures = 0
            polled_at = _now_iso()

            def record_observation(manifest: dict) -> None:
                request = manifest["provider_requests"]["video"]
                request["status"] = observation.status
                request["last_polled_at"] = polled_at
                request.pop("error_code", None)
                _record_usage(manifest, request_id, observation.usage)
                attempt = _animation_attempt(manifest, attempt_id)
                attempt["status"] = observation.status
                if observation.status == "pending":
                    request["next_poll_at"] = (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=self._poll_interval_seconds)
                    ).isoformat()
                    if cancelled.is_set() or manifest["cancel_requested_at"] is not None:
                        manifest["status"] = "cancelled"
                        manifest["phase"] = "background_retrieval"
                        attempt["status"] = "cancelled"
                        attempt["phase"] = "background_retrieval"
                    elif not background:
                        manifest["status"] = "in_progress"
                        manifest["phase"] = "video_polling"
                        attempt["phase"] = "video_polling"
                else:
                    request.pop("next_poll_at", None)

            self._library.update_manifest(job_id, record_observation)
            if observation.status == "pending":
                self._sleeper(self._poll_interval_seconds)
                continue
            if observation.status in {"failed", "expired"}:
                self._finish_video_status(job_id, attempt_id, observation.status)
                return
            if observation.status != "done" or observation.video_url is None:
                self._finish_video_terminal(
                    job_id,
                    attempt_id,
                    request_id,
                    ProviderError("bad_response", "completed video omitted its media URL"),
                    api_key,
                )
                return
            self._download_and_bank(
                job_id,
                attempt_id,
                request_id,
                observation.video_url,
                api_key,
                cancelled,
            )
            return

    def _finish_video_status(
        self, job_id: str, attempt_id: str, status: str
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            request = manifest["provider_requests"]["video"]
            request["status"] = status
            request["completed_at"] = timestamp
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["status"] = status
            attempt["phase"] = "video_terminal"
            attempt["completed_at"] = timestamp
            manifest["status"] = status
            manifest["phase"] = "video_terminal"

        self._library.update_manifest(job_id, update)

    def _finish_video_terminal(
        self,
        job_id: str,
        attempt_id: str,
        request_id: str,
        error: ProviderError,
        api_key: str,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            request = manifest["provider_requests"]["video"]
            request["status"] = "failed"
            request["error_code"] = error.code
            request["completed_at"] = timestamp
            _record_usage(manifest, request_id, error.usage)
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["status"] = "failed"
            attempt["phase"] = "video_terminal"
            attempt["completed_at"] = timestamp
            manifest["status"] = "failed"
            manifest["phase"] = "video_terminal"

        self._library.update_manifest(job_id, update)
        self._record_video_error(
            job_id, code=error.code, message=error.message, api_key=api_key
        )

    def _download_and_bank(
        self,
        job_id: str,
        attempt_id: str,
        request_id: str,
        video_url: str,
        api_key: str,
        cancelled: threading.Event,
    ) -> None:
        job_dir = self._library.preflight_job(job_id)

        def mark_downloading(manifest: dict) -> None:
            attempt = _animation_attempt(manifest, attempt_id)
            if cancelled.is_set() or manifest["cancel_requested_at"] is not None:
                manifest["status"] = "cancelled"
                manifest["phase"] = "background_retrieval"
                attempt["status"] = "cancelled"
                attempt["phase"] = "background_retrieval"
            else:
                manifest["status"] = "in_progress"
                manifest["phase"] = "video_downloading"
                attempt["status"] = "downloading"
                attempt["phase"] = "video_downloading"

        self._library.update_manifest(job_id, mark_downloading)
        destination = job_dir / ".work" / f"video-{attempt_id}.mp4"
        downloaded = None
        for retry_index in range(self._safe_retry_limit):
            try:
                downloaded = self._downloader(
                    video_url,
                    destination,
                    self._monotonic() + self._operation_timeout_seconds,
                    cancelled=None,
                )
                break
            except MediaError as error:
                self._record_video_retry(
                    job_id,
                    request_id,
                    field="download_failures",
                    error=error,
                )
                if error.code not in _SAFE_RETRY_CODES or retry_index + 1 >= self._safe_retry_limit:
                    self._pause_accepted_request(
                        job_id,
                        attempt_id,
                        code="video_download_interrupted",
                        message=error.message,
                        api_key=api_key,
                        cancelled=cancelled,
                    )
                    return
                self._sleeper(self._poll_interval_seconds)
        if (
            not isinstance(downloaded, DownloadedVideo)
            or downloaded.path != destination
            or not downloaded.path.is_file()
        ):
            self._pause_accepted_request(
                job_id,
                attempt_id,
                code="video_download_interrupted",
                message="The video download did not produce a local file.",
                api_key=api_key,
                cancelled=cancelled,
            )
            return

        try:
            payload = downloaded.path.read_bytes()
            current = self._library.load_manifest(job_id)
            was_cancelled = cancelled.is_set() or current["cancel_requested_at"] is not None
            asset = self._library.bank_asset(
                job_id,
                kind="source_video",
                data=payload,
                mime_type="video/mp4",
                origin=f"xai_video:{attempt_id}",
                status="cancelled_saved" if was_cancelled else "complete",
            )
        except (LibraryError, OSError) as exc:
            self._pause_accepted_request(
                job_id,
                attempt_id,
                code="video_bank_failed",
                message=exc,
                api_key=api_key,
                cancelled=cancelled,
            )
            return
        finally:
            try:
                downloaded.path.unlink(missing_ok=True)
            except OSError:
                pass

        downloaded_at = _now_iso()

        def record_video(manifest: dict) -> None:
            request = manifest["provider_requests"]["video"]
            request["status"] = "done"
            request["downloaded_at"] = downloaded_at
            request["completed_at"] = downloaded_at
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["source_video_asset_id"] = asset["asset_id"]
            manifest["recovery"]["source_video_asset_id"] = asset["asset_id"]
            if cancelled.is_set() or manifest["cancel_requested_at"] is not None:
                for record in manifest["assets"]:
                    if record["asset_id"] == asset["asset_id"]:
                        record["status"] = "cancelled_saved"
                attempt["status"] = "cancelled_saved"
                attempt["phase"] = "cancelled_saved"
                attempt["completed_at"] = downloaded_at
                manifest["status"] = "cancelled_saved"
                manifest["phase"] = "cancelled_saved"
                manifest["cancelled_at"] = downloaded_at
            else:
                attempt["status"] = "ready_to_process"
                attempt["phase"] = "ready_to_process"
                manifest["status"] = "ready_to_process"
                manifest["phase"] = "ready_to_process"

        final = self._library.update_manifest(job_id, record_video)
        if final["status"] == "cancelled_saved":
            return
        self._process_local(job_id, attempt_id, asset["asset_id"], api_key, cancelled)

    def _validate_mapping(self, mapped: object, manifest: dict, frame_count: int) -> dict:
        if not isinstance(mapped, dict):
            raise GenerationError("animation mapping returned an invalid result")
        if (
            mapped.get("source_frames") != frame_count
            or mapped.get("decoded_frames") != frame_count
            or mapped.get("duration_ms") != ANIMATION_FRAME_DURATION_MS
            or mapped.get("source_duration_ms")
            != frame_count * ANIMATION_FRAME_DURATION_MS
            or mapped.get("timing_resampled") is not False
            or set(mapped.get("tracks", {})) != set(manifest["target"]["targets"])
        ):
            raise GenerationError("animation mapping changed the exact frame timeline")
        for track in mapped["tracks"].values():
            if (
                not isinstance(track, dict)
                or track.get("frame_count") != frame_count
                or not isinstance(track.get("frames"), list)
                or len(track["frames"]) != frame_count
            ):
                raise GenerationError("animation mapping changed the exact frame count")
        return mapped

    def _process_local(
        self,
        job_id: str,
        attempt_id: str,
        source_video_asset_id: str,
        api_key: str,
        cancelled: threading.Event,
    ) -> None:
        processed: ProcessedAnimation | None = None
        images = []
        try:
            manifest = self._library.load_manifest(job_id)
            if cancelled.is_set() or manifest["cancel_requested_at"] is not None:
                self._finish_cancelled_saved(job_id, attempt_id)
                return
            job_dir = self._library.preflight_job(job_id)
            source = self._library.resolve_asset(job_id, source_video_asset_id)
            if source.record["kind"] != "source_video":
                raise GenerationError("the retained source video is invalid")
            spec, targets = self._video_spec(manifest)

            def mark_processing(current: dict) -> None:
                attempt = _animation_attempt(current, attempt_id)
                attempt["status"] = "processing"
                attempt["phase"] = "local_processing"
                current["status"] = "in_progress"
                current["phase"] = "local_processing"

            self._library.update_manifest(job_id, mark_processing)
            processed = self._processor(
                source.path,
                job_dir / ".work" / f"processed-{attempt_id}",
                job_dir / ".work",
                ffmpeg_path=self._ffmpeg_resolver(),
                width=spec.width,
                height=spec.height,
                frame_count=spec.max_frames,
                loop_mode=manifest["loop_mode"],
                deadline=self._monotonic() + self._operation_timeout_seconds,
                cancelled=cancelled.is_set,
            )
            if not isinstance(processed, ProcessedAnimation):
                raise GenerationError("animation processor returned an invalid result")
            if (
                processed.frame_count != spec.max_frames
                or processed.width != spec.width
                or processed.height != spec.height
                or processed.loop_mode != manifest["loop_mode"]
                or len(processed.frame_paths) != spec.max_frames
            ):
                raise GenerationError("animation processor changed the requested geometry")
            if cancelled.is_set():
                self._finish_cancelled_saved(job_id, attempt_id)
                return

            from PIL import Image

            for path in processed.frame_paths:
                with Image.open(path) as frame:
                    frame.load()
                    images.append(frame.copy())
            mapped = self._mapper(
                images,
                [ANIMATION_FRAME_DURATION_MS] * spec.max_frames,
                targets,
                product_id=manifest["target"]["product_id"],
            )
            mapped = self._validate_mapping(mapped, manifest, spec.max_frames)
            if cancelled.is_set():
                self._finish_cancelled_saved(job_id, attempt_id)
                return

            frame_assets = []
            for index, path in enumerate(processed.frame_paths):
                if cancelled.is_set():
                    self._finish_cancelled_saved(job_id, attempt_id)
                    return
                frame_assets.append(
                    self._library.bank_asset(
                        job_id,
                        kind="frame",
                        data=path.read_bytes(),
                        mime_type="image/png",
                        origin=f"local_frame:{attempt_id}:{index}",
                    )
                )
                if cancelled.is_set():
                    self._finish_cancelled_saved(job_id, attempt_id)
                    return
            preview_asset = self._library.bank_asset(
                job_id,
                kind="preview_poster",
                data=processed.frame_paths[0].read_bytes(),
                mime_type="image/png",
                origin=f"local_preview:{attempt_id}",
            )
            if cancelled.is_set():
                self._finish_cancelled_saved(job_id, attempt_id)
                return
            mapped_asset = self._library.bank_asset(
                job_id,
                kind="mapped_result",
                data=json.dumps(
                    mapped, sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
                mime_type="application/json",
                origin=f"local_mapping:{attempt_id}",
            )
            completed_at = _now_iso()

            def finish(current: dict) -> None:
                attempt = _animation_attempt(current, attempt_id)
                attempt["frame_asset_ids"] = [
                    asset["asset_id"] for asset in frame_assets
                ]
                attempt["preview_asset_id"] = preview_asset["asset_id"]
                attempt["mapped_result_asset_id"] = mapped_asset["asset_id"]
                if cancelled.is_set() or current["cancel_requested_at"] is not None:
                    attempt["status"] = "cancelled_saved"
                    attempt["phase"] = "cancelled_saved"
                    attempt["completed_at"] = completed_at
                    current["status"] = "cancelled_saved"
                    current["phase"] = "cancelled_saved"
                    current["cancelled_at"] = completed_at
                    return
                attempt["status"] = "complete"
                attempt["phase"] = "ready_for_review"
                attempt["completed_at"] = completed_at
                current["status"] = "ready"
                current["phase"] = "ready_for_review"
                current["progress"] = {
                    "completed": spec.max_frames,
                    "total": spec.max_frames,
                }

            self._library.update_manifest(job_id, finish)
        except MediaCancelled:
            self._finish_cancelled_saved(job_id, attempt_id)
        except (GenerationError, LibraryError, MediaError, OSError, ValueError) as exc:
            self._fail_video_local(
                job_id,
                attempt_id,
                code=getattr(exc, "code", "local_processing_failed"),
                error=exc,
                api_key=api_key,
                ready_to_process=True,
            )
        finally:
            for image in images:
                image.close()
            if processed is not None:
                try:
                    shutil.rmtree(processed.directory)
                except OSError:
                    pass

    def _finish_cancelled_saved(self, job_id: str, attempt_id: str) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["status"] = "cancelled_saved"
            attempt["phase"] = "cancelled_saved"
            attempt["completed_at"] = timestamp
            manifest["status"] = "cancelled_saved"
            manifest["phase"] = "cancelled_saved"
            manifest["cancelled_at"] = timestamp

        self._library.update_manifest(job_id, update)

    def _fail_video_local(
        self,
        job_id: str,
        attempt_id: str,
        *,
        code: str,
        error: object,
        api_key: str,
        ready_to_process: bool,
    ) -> None:
        try:
            safe_code = code if isinstance(code, str) and code.isidentifier() else "local_processing_failed"
            self._record_video_error(
                job_id,
                code=safe_code,
                message=str(error) or "The local animation operation failed.",
                api_key=api_key,
            )
            timestamp = _now_iso()

            def update(manifest: dict) -> None:
                attempt = _animation_attempt(manifest, attempt_id)
                if ready_to_process and attempt.get("source_video_asset_id"):
                    attempt["status"] = "ready_to_process"
                    attempt["phase"] = "local_failed"
                    manifest["status"] = "ready_to_process"
                    manifest["phase"] = "local_failed"
                else:
                    attempt["status"] = "failed"
                    attempt["phase"] = "animation_failed"
                    attempt["completed_at"] = timestamp
                    manifest["status"] = "failed"
                    manifest["phase"] = "animation_failed"

            self._library.update_manifest(job_id, update)
        except Exception:
            pass

    def _resume_video_poll(
        self,
        job_id: str,
        request_id: str,
        api_key: str,
        *,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        token, cancelled = self._gate.begin(job_id)
        try:
            manifest = self._library.load_manifest(job_id)
            attempt = _animation_attempt(manifest)
            if attempt.get("request_id") not in {None, request_id}:
                raise GenerationValidationError("the resumable request does not match its job")
            if manifest["cancel_requested_at"] is not None or manifest["status"] == "cancelled":
                cancelled.set()
            provider = self._video_provider_factory(
                api_key, manifest["models"]["video"]
            )

            def prepare(current: dict) -> None:
                current_attempt = _animation_attempt(current, attempt["attempt_id"])
                current_attempt["request_id"] = request_id
                if cancelled.is_set():
                    current_attempt["status"] = "cancelled"
                    current_attempt["phase"] = "background_retrieval"
                    current["status"] = "cancelled"
                    current["phase"] = "background_retrieval"
                else:
                    current_attempt["status"] = "polling"
                    current_attempt["phase"] = "video_polling"
                    current["status"] = "in_progress"
                    current["phase"] = "video_polling"

            self._library.update_manifest(job_id, prepare)
            self._launch_video_worker(
                job_id,
                token,
                api_key,
                lambda: self._poll_and_retrieve(
                    job_id,
                    attempt["attempt_id"],
                    provider,
                    request_id,
                    api_key,
                    cancelled,
                ),
                on_finished=on_finished,
            )
        except BaseException:
            if self._gate.active_job_id == job_id:
                self._gate.finish(token)
            raise

    def _recover_banked_animation(self, job_id: str) -> None:
        """Adopt fully banked local outputs for the latest animation attempt."""
        manifest = self._library.load_manifest(job_id)
        if not manifest["animation_attempts"]:
            return
        attempt = _animation_attempt(manifest)
        attempt_id = attempt.get("attempt_id")
        if not isinstance(attempt_id, str):
            return
        source = next(
            (
                asset
                for asset in reversed(manifest["assets"])
                if asset["kind"] == "source_video"
                and asset["origin"] == f"xai_video:{attempt_id}"
            ),
            None,
        )
        if source is None:
            recovery_id = manifest["recovery"].get("source_video_asset_id")
            source = next(
                (
                    asset
                    for asset in manifest["assets"]
                    if asset["asset_id"] == recovery_id
                    and asset["kind"] == "source_video"
                ),
                None,
            )
        if source is None:
            return
        try:
            self._library.resolve_asset(job_id, source["asset_id"])
        except LibraryError:
            return

        frame_count = MODEL_FRAME_CAPS[manifest["target"]["family"]]
        frames_by_index: dict[int, dict] = {}
        frame_origin_prefix = f"local_frame:{attempt_id}:"
        for asset in manifest["assets"]:
            if asset["kind"] != "frame" or not asset["origin"].startswith(
                frame_origin_prefix
            ):
                continue
            try:
                index = int(asset["origin"][len(frame_origin_prefix) :])
            except ValueError:
                continue
            if 0 <= index < frame_count:
                # Retried local processing appends a newer complete sequence;
                # one retained asset per exact index keeps earlier partial
                # publications from poisoning crash adoption.
                frames_by_index[index] = asset
        frames = [
            frames_by_index[index]
            for index in range(frame_count)
            if index in frames_by_index
        ]
        preview = next(
            (
                asset
                for asset in reversed(manifest["assets"])
                if asset["kind"] == "preview_poster"
                and asset["origin"] == f"local_preview:{attempt_id}"
            ),
            None,
        )
        mapped_asset = next(
            (
                asset
                for asset in reversed(manifest["assets"])
                if asset["kind"] == "mapped_result"
                and asset["origin"] == f"local_mapping:{attempt_id}"
            ),
            None,
        )
        complete = len(frames) == frame_count and preview is not None and mapped_asset is not None
        if complete:
            try:
                for asset in [*frames, preview, mapped_asset]:
                    self._library.resolve_asset(job_id, asset["asset_id"])
                mapped_path = self._library.resolve_asset(
                    job_id, mapped_asset["asset_id"]
                ).path
                mapped = json.loads(mapped_path.read_text(encoding="utf-8"))
                self._validate_mapping(mapped, manifest, frame_count)
            except (GenerationError, LibraryError, OSError, UnicodeError, json.JSONDecodeError):
                complete = False

        completion_timestamp = _now_iso()

        def update(current: dict) -> None:
            current_attempt = _animation_attempt(current, attempt_id)
            current_attempt["source_video_asset_id"] = source["asset_id"]
            current["recovery"]["source_video_asset_id"] = source["asset_id"]
            was_cancelled = (
                current["cancel_requested_at"] is not None
                or current["status"] in {"cancelled", "cancelled_saved"}
            )
            if complete:
                current_attempt["frame_asset_ids"] = [
                    asset["asset_id"] for asset in frames
                ]
                current_attempt["preview_asset_id"] = preview["asset_id"]
                current_attempt["mapped_result_asset_id"] = mapped_asset["asset_id"]
                if was_cancelled:
                    current_attempt["status"] = "cancelled_saved"
                    current_attempt["phase"] = "cancelled_saved"
                    current["status"] = "cancelled_saved"
                    current["phase"] = "cancelled_saved"
                    return
                current_attempt["status"] = "complete"
                current_attempt["phase"] = "ready_for_review"
                if not current_attempt.get("completed_at"):
                    current_attempt["completed_at"] = completion_timestamp
                current["status"] = "ready"
                current["phase"] = "ready_for_review"
                current["progress"] = {
                    "completed": frame_count,
                    "total": frame_count,
                }
            elif was_cancelled:
                current_attempt["status"] = "cancelled_saved"
                current_attempt["phase"] = "cancelled_saved"
                current["status"] = "cancelled_saved"
                current["phase"] = "cancelled_saved"
            else:
                current_attempt["status"] = "ready_to_process"
                current_attempt["phase"] = "ready_to_process"
                current["status"] = "ready_to_process"
                current["phase"] = "ready_to_process"

        candidate = copy.deepcopy(manifest)
        update(candidate)
        if candidate == manifest:
            return
        self._library.update_manifest(job_id, update)

    def _reconcile_interrupted_animation(self, job_id: str) -> None:
        """Classify paid-planner crashes without inventing a video submission."""
        manifest = self._library.load_manifest(job_id)
        if not manifest["animation_attempts"]:
            return
        attempt = _animation_attempt(manifest)
        planning_interrupted = (
            manifest["status"] == "in_progress"
            and manifest["phase"] == "video_planning"
            and attempt.get("phase") == "video_planning"
        )
        planned_before_submit = (
            manifest["status"] == "submission_unknown"
            and manifest["phase"] == "interrupted"
            and "video" not in manifest["provider_requests"]
            and attempt.get("phase") == "video_submitting"
            and attempt.get("request_id") is None
        )
        if not planning_interrupted and not planned_before_submit:
            return

        def update(current: dict) -> None:
            current_attempt = _animation_attempt(current, attempt["attempt_id"])
            current_attempt["status"] = "interrupted"
            current_attempt["phase"] = "interrupted"
            current["status"] = "interrupted"
            current["phase"] = "interrupted"
            for operation, request in current["provider_requests"].items():
                if operation == "video_plan" or operation.startswith("video_plan:"):
                    if request["status"] == "submitting":
                        request["status"] = "interrupted"

        self._library.update_manifest(job_id, update)

    def cancel(self, job_id: str) -> dict:
        if not self._gate.request_cancel(job_id):
            raise GenerationNotActiveError("this job does not own the active operation")
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            if manifest["status"] != "in_progress":
                raise GenerationNotActiveError(
                    "this job completed before cancellation could be accepted"
                )
            if manifest["cancel_requested_at"] is None:
                manifest["cancel_requested_at"] = timestamp
            video = manifest["provider_requests"].get("video")
            if isinstance(video, dict) and isinstance(video.get("request_id"), str):
                manifest["status"] = "cancelled"
                manifest["phase"] = "background_retrieval"
                if manifest["animation_attempts"]:
                    attempt = _animation_attempt(manifest)
                    attempt["status"] = "cancelled"
                    attempt["phase"] = "background_retrieval"

        return self._library.update_manifest(job_id, update)

    def reconcile_startup(
        self,
        *,
        api_key: str | None = None,
        _admission_token: object | None = None,
    ) -> list[dict]:
        """Reconcile state and optionally resume one accepted request without POSTs."""
        if api_key is not None and (
            not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096
        ):
            raise GenerationValidationError("an xAI API key is required")
        owns_admission = _admission_token is None
        if owns_admission:
            token, _cancelled = self._gate.begin()
        else:
            token = _admission_token
            self._gate.require(token)
        try:
            actions = self._library.reconcile()["actions"]
            for job in self._library.scan()["jobs"]:
                try:
                    self._reconcile_interrupted_animation(job["job_id"])
                    self._recover_banked_candidates(job["job_id"])
                    self._recover_banked_animation(job["job_id"])
                except Exception:
                    # The library scan/reconciliation error surface remains the
                    # authority; one unreadable job must not hide the others.
                    continue
        finally:
            if owns_admission:
                self._gate.finish(token)
        if api_key is not None and actions:
            def resume_at(index: int) -> None:
                if index >= len(actions):
                    return
                action = actions[index]
                try:
                    self._resume_video_poll(
                        action["job_id"],
                        action["request_id"],
                        api_key,
                        on_finished=lambda: resume_at(index + 1),
                    )
                except GenerationBusyError:
                    self._gate.call_when_idle(lambda: resume_at(index))
                except (GenerationError, LibraryError):
                    resume_at(index + 1)

            resume_at(0)
        return actions

    def _recover_banked_candidates(self, job_id: str) -> int:
        """Adopt banked concept bytes whose final candidate update was interrupted."""
        from PIL import Image, UnidentifiedImageError

        manifest = self._library.load_manifest(job_id)
        known = {
            candidate.get("asset_id")
            for candidate in manifest["candidates"]
            if isinstance(candidate, dict)
        }
        recovered: list[dict] = []
        for asset in manifest["assets"]:
            origin = asset.get("origin")
            asset_id = asset.get("asset_id")
            if (
                asset.get("kind") != "concept"
                or not isinstance(asset_id, str)
                or asset_id in known
                or not isinstance(origin, str)
                or not origin.startswith("xai_concept:")
            ):
                continue
            try:
                prefix, batch_id, index_text = origin.split(":", 2)
                if prefix != "xai_concept" or not index_text.isdigit():
                    continue
                index = int(index_text)
                record = _batch(manifest, batch_id)
                prompts = record["candidate_prompts"]
                if not 0 <= index < len(prompts):
                    continue
                owned = self._library.resolve_asset(job_id, asset_id)
                with Image.open(owned.path) as image:
                    image.load()
                    width, height = image.size
                    image_format = image.format
                expected_format = "PNG" if asset["mime_type"] == "image/png" else "JPEG"
                if image_format != expected_format:
                    continue
            except (KeyError, ValueError, ManifestError, OSError, UnidentifiedImageError):
                continue
            recovered.append(
                {
                    "asset_id": asset_id,
                    "batch_id": batch_id,
                    "index": index,
                    "prompt": prompts[index],
                    "mime_type": asset["mime_type"],
                    "width": width,
                    "height": height,
                    "created_at": asset["created_at"],
                }
            )
        if not recovered:
            return 0

        def update(current: dict) -> None:
            current_ids = {
                candidate.get("asset_id")
                for candidate in current["candidates"]
                if isinstance(candidate, dict)
            }
            recovered_count = 0
            for item in sorted(recovered, key=lambda value: (value["batch_id"], value["index"])):
                asset_id = item["asset_id"]
                if asset_id in current_ids:
                    continue
                record = _batch(current, item["batch_id"])
                current["candidates"].append(
                    {
                        "candidate_id": asset_id,
                        "asset_id": asset_id,
                        "batch_id": item["batch_id"],
                        "prompt": item["prompt"],
                        "revised_prompt": None,
                        "width": item["width"],
                        "height": item["height"],
                        "mime_type": item["mime_type"],
                        "status": "complete",
                        "created_at": item["created_at"],
                    }
                )
                if asset_id not in record["candidate_ids"]:
                    record["candidate_ids"].append(asset_id)
                record["status"] = "partial"
                operation = f"candidate_attempt:{item['batch_id']}:{item['index']}"
                request = current["provider_requests"].pop(operation, None)
                if request is not None:
                    request["status"] = "complete"
                    request["completed_at"] = _now_iso()
                    current["provider_requests"][asset_id] = request
                actual = current["costs"]["actual_by_operation"]
                if operation in actual:
                    actual[asset_id] = actual.pop(operation)
                current_ids.add(asset_id)
                recovered_count += 1
                current["progress"]["completed"] = len(record["candidate_ids"])
            if recovered_count:
                if current["status"] == "interrupted":
                    current["status"] = "partial"
                    current["phase"] = "interrupted"
                elif current["status"] == "failed":
                    current["status"] = "partial"
                    current["phase"] = "concepts_partial"
                _refresh_cost_completeness(current)

        self._library.update_manifest(job_id, update)
        return len(recovered)

__all__ = [
    "ANIMATION_FRAME_DURATION_MS",
    "DEFAULT_FOREGROUND_TIMEOUT_SECONDS",
    "DEFAULT_OPERATION_TIMEOUT_SECONDS",
    "DEFAULT_SAFE_RETRY_LIMIT",
    "DEFAULT_VIDEO_POLL_INTERVAL_SECONDS",
    "GenerationBusyError",
    "GenerationCoordinator",
    "GenerationError",
    "GenerationNotActiveError",
    "GenerationValidationError",
    "OperationGate",
    "canonical_target_snapshot",
]
