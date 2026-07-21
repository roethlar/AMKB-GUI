"""Durable, injected orchestration for Lighting Studio generation jobs.

The coordinator owns operation ordering and manifest state, not HTTP or device
I/O.  Paid collaborators are factories so API keys remain ephemeral, and the
default process gate permits exactly one provider/local operation at a time.
Startup reconciliation delegates to the library and never schedules paid work.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from .ai_catalog import MODEL_CATALOG, validate_model
from .library import GeneratedAssetLibrary, LibraryError, ManifestError
from .llm import (
    MAX_CONCEPT_CANDIDATES,
    MAX_CONCEPT_PROMPT_CHARS,
    MAX_VIDEO_MOTION_CHARS,
    MODEL_FRAME_CAPS,
    VIDEO_LOOP_MODES,
    ConceptImageResult,
    ConceptPlanResult,
    GrokConceptImageProvider,
    GrokConceptPlanner,
    GrokVideoPlanner,
    ProviderError,
    ProviderUsage,
    VideoAnimationPlan,
    VideoAnimationPlanResult,
    VideoStatus,
    VideoSubmission,
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
_MODEL_ROLES = frozenset(MODEL_CATALOG)
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


def _candidate_count(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= MAX_CONCEPT_CANDIDATES
    ):
        raise GenerationValidationError(
            f"candidate_count must be between 1 and {MAX_CONCEPT_CANDIDATES}"
        )
    return value


def _models(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _MODEL_ROLES:
        raise GenerationValidationError("models must contain the three curated roles")
    normalized: dict[str, str] = {}
    try:
        for role in sorted(_MODEL_ROLES):
            normalized[role] = validate_model(role, value[role])
    except (KeyError, ValueError):
        raise GenerationValidationError("a selected generation model is unavailable") from None
    return normalized


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


def _request_values(
    *,
    prompt: object,
    candidate_count: object,
    target: object,
    models: object,
    loop_mode: object,
    api_key: object,
    privacy_acknowledged: object,
) -> tuple[str, int, dict, dict[str, str], str, str]:
    if (
        not isinstance(prompt, str)
        or not prompt.strip()
        or len(prompt) > MAX_CONCEPT_PROMPT_CHARS
    ):
        raise GenerationValidationError(
            f"prompt must be a non-empty string of at most {MAX_CONCEPT_PROMPT_CHARS} characters"
        )
    count = _candidate_count(candidate_count)
    snapshot = canonical_target_snapshot(target)
    selected_models = _models(models)
    if not isinstance(loop_mode, str) or loop_mode not in VIDEO_LOOP_MODES:
        raise GenerationValidationError("loop_mode is unsupported")
    if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096:
        raise GenerationValidationError("an xAI API key is required")
    if privacy_acknowledged is not True:
        raise GenerationValidationError("the current privacy disclosure must be acknowledged")
    return prompt.strip(), count, snapshot, selected_models, loop_mode, api_key


def estimate_concept_batch_ticks(model_id: object, candidate_count: object) -> int:
    """Return the integer catalog estimate for one text-to-image batch."""
    count = _candidate_count(candidate_count)
    try:
        model = validate_model("concept", model_id)
    except ValueError:
        raise GenerationValidationError("the concept model is unavailable") from None
    choices = MODEL_CATALOG["concept"]["choices"]
    choice = next(item for item in choices if item["id"] == model)
    pricing = choice["pricing"]
    return int(pricing["output_per_1k_image_usd_ticks"]) * count


def estimate_video_animation_ticks(model_id: object) -> int:
    """Return the catalog estimate for one image input and one 480p second."""
    try:
        model = validate_model("video", model_id)
    except ValueError:
        raise GenerationValidationError("the video model is unavailable") from None
    choices = MODEL_CATALOG["video"]["choices"]
    choice = next(item for item in choices if item["id"] == model)
    pricing = choice["pricing"]
    return int(pricing["input_per_image_usd_ticks"]) + int(
        pricing["output_per_second_480p_usd_ticks"]
    )


class OperationGate:
    """One non-blocking process operation lease with a shared cancel event."""

    def __init__(self) -> None:
        self._lease = threading.Lock()
        self._state_lock = threading.Lock()
        self._token: object | None = None
        self._job_id: str | None = None
        self._cancelled: threading.Event | None = None

    @property
    def active_job_id(self) -> str | None:
        with self._state_lock:
            return self._job_id

    def begin(self, job_id: str | None = None) -> tuple[object, threading.Event]:
        if not self._lease.acquire(blocking=False):
            raise GenerationBusyError("another generation operation is already active")
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

    def request_cancel(self, job_id: str) -> bool:
        with self._state_lock:
            if self._job_id != job_id or self._cancelled is None:
                return False
            self._cancelled.set()
            return True

    def finish(self, token: object) -> None:
        with self._state_lock:
            if self._token is not token:
                return
            self._token = None
            self._job_id = None
            self._cancelled = None
        self._lease.release()


_PROCESS_OPERATION_GATE = OperationGate()


def _default_planner_factory(api_key: str, model: str):
    return GrokConceptPlanner(api_key, model=model)


def _default_image_provider_factory(api_key: str, model: str):
    return GrokConceptImageProvider(api_key, model=model)


def _default_video_planner_factory(api_key: str, model: str):
    return GrokVideoPlanner(api_key, model=model)


def _default_video_provider_factory(api_key: str, model: str):
    return XaiVideoProvider(api_key, model=model)


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
    """Start durable concept batches and serialize all paid/local operations."""

    def __init__(
        self,
        library: GeneratedAssetLibrary,
        *,
        planner_factory: Callable[[str, str], object] = _default_planner_factory,
        image_provider_factory: Callable[[str, str], object] = _default_image_provider_factory,
        video_planner_factory: Callable[[str, str], object] = _default_video_planner_factory,
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
        self._planner_factory = planner_factory
        self._image_provider_factory = image_provider_factory
        self._video_planner_factory = video_planner_factory
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
        self._workers: dict[str, object] = {}
        self._workers_lock = threading.Lock()

    @property
    def active_job_id(self) -> str | None:
        return self._gate.active_job_id

    def _prepare_batch(self, job_id: str, count: int, kind: str) -> tuple[dict, str]:
        batch_id = str(uuid.uuid4())
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            manifest["concept_batches"].append(
                {
                    "batch_id": batch_id,
                    "kind": kind,
                    "status": "planning",
                    "requested_count": count,
                    "visual_brief": None,
                    "candidate_prompts": [],
                    "candidate_ids": [],
                    "created_at": timestamp,
                    "completed_at": None,
                }
            )
            manifest["status"] = "in_progress"
            manifest["phase"] = "concept_generation"
            manifest["progress"] = {"completed": 0, "total": count}
            manifest["cancel_requested_at"] = None
            manifest["cancelled_at"] = None
            manifest["costs"]["estimated_ticks"] += estimate_concept_batch_ticks(
                manifest["models"]["concept"], count
            )

        return self._library.update_manifest(job_id, update), batch_id

    def _launch_batch(
        self,
        job_id: str,
        batch_id: str,
        api_key: str,
        token: object,
        cancelled: threading.Event,
    ) -> None:
        deadline = self._monotonic() + self._operation_timeout_seconds

        def target() -> None:
            try:
                self._run_batch(job_id, batch_id, api_key, deadline, cancelled)
            finally:
                self._gate.finish(token)

        try:
            worker = self._launcher(target)
        except Exception as exc:
            self._fail_local(job_id, batch_id, "worker_start_failed", exc, api_key)
            self._gate.finish(token)
            raise GenerationError("the generation worker could not be started") from None
        with self._workers_lock:
            self._workers[job_id] = worker

    def start_concepts(
        self,
        *,
        prompt: object,
        candidate_count: object,
        target: object,
        models: object,
        loop_mode: object,
        api_key: object,
        privacy_acknowledged: object,
    ) -> dict:
        prompt, count, snapshot, selected_models, loop_mode, api_key = _request_values(
            prompt=prompt,
            candidate_count=candidate_count,
            target=target,
            models=models,
            loop_mode=loop_mode,
            api_key=api_key,
            privacy_acknowledged=privacy_acknowledged,
        )
        token, cancelled = self._gate.begin()
        job_id: str | None = None
        try:
            manifest = self._library.create_job(
                prompt=prompt,
                target=snapshot,
                models=selected_models,
                loop_mode=loop_mode,
            )
            job_id = manifest["job_id"]
            self._gate.bind(token, job_id)
            manifest, batch_id = self._prepare_batch(job_id, count, "initial")
            self._launch_batch(job_id, batch_id, api_key, token, cancelled)
            return manifest
        except BaseException:
            if job_id is None or self._gate.active_job_id == job_id:
                self._gate.finish(token)
            raise

    def more_like_this(
        self,
        job_id: str,
        *,
        candidate_count: object,
        api_key: object,
        privacy_acknowledged: object,
    ) -> dict:
        count = _candidate_count(candidate_count)
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096:
            raise GenerationValidationError("an xAI API key is required")
        if privacy_acknowledged is not True:
            raise GenerationValidationError("the current privacy disclosure must be acknowledged")
        original = self._library.load_manifest(job_id)
        _models(original["models"])
        if not original["candidates"]:
            raise GenerationValidationError("more-like-this requires a completed concept")
        if original["status"] not in {
            "awaiting_selection",
            "partial",
            "cancelled",
            "failed",
            "interrupted",
        }:
            raise GenerationValidationError("this job is not ready for another concept batch")
        token, cancelled = self._gate.begin(job_id)
        try:
            current = self._library.load_manifest(job_id)
            if current["status"] != original["status"] or not current["candidates"]:
                raise GenerationBusyError("the generation job changed before it could start")
            self._library.preflight_job(job_id)
            manifest, batch_id = self._prepare_batch(job_id, count, "more_like_this")
            self._launch_batch(job_id, batch_id, api_key, token, cancelled)
            return manifest
        except BaseException:
            if self._gate.active_job_id == job_id:
                self._gate.finish(token)
            raise

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

    def _candidate_asset(self, manifest: dict, candidate_id: object):
        if not isinstance(candidate_id, str):
            raise GenerationValidationError("the selected concept is invalid")
        matches = [
            candidate
            for candidate in manifest["candidates"]
            if candidate.get("candidate_id") == candidate_id
            and candidate.get("asset_id") == candidate_id
            and candidate.get("status") == "complete"
        ]
        if len(matches) != 1:
            raise GenerationValidationError("the selected concept is not owned by this job")
        try:
            owned = self._library.resolve_asset(manifest["job_id"], candidate_id)
        except LibraryError:
            raise GenerationValidationError(
                "the selected concept is not owned by this job"
            ) from None
        if (
            owned.record["kind"] != "concept"
            or owned.record["mime_type"] != matches[0].get("mime_type")
        ):
            raise GenerationValidationError("the selected concept asset is invalid")
        return owned

    @staticmethod
    def _video_plan_operation(manifest: dict, attempt_id: str) -> str:
        if "video_plan" not in manifest["provider_requests"]:
            return "video_plan"
        return f"video_plan:{attempt_id}"

    @staticmethod
    def _has_unresolved_video_request(manifest: dict) -> bool:
        request = manifest["provider_requests"].get("video")
        if not isinstance(request, dict) or not isinstance(request.get("request_id"), str):
            return False
        if request.get("status") in {"failed", "expired"}:
            return False
        request_id = request["request_id"]
        matching_attempts = [
            attempt
            for attempt in manifest["animation_attempts"]
            if attempt.get("request_id") == request_id
        ]
        source_ids = {
            attempt.get("source_video_asset_id") for attempt in matching_attempts
        }
        source_ids.add(manifest["recovery"].get("source_video_asset_id"))
        return not any(isinstance(asset_id, str) for asset_id in source_ids)

    def _launch_video_worker(
        self,
        job_id: str,
        token: object,
        api_key: str,
        target: Callable[[], None],
    ) -> None:
        def run() -> None:
            try:
                target()
            finally:
                self._gate.finish(token)

        try:
            worker = self._launcher(run)
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
        with self._workers_lock:
            self._workers[job_id] = worker

    def start_animation(
        self,
        job_id: str,
        *,
        candidate_id: object,
        motion: object,
        loop_mode: object,
        api_key: object,
        privacy_acknowledged: object,
    ) -> dict:
        """Persist a selected still, then launch exactly one paid video attempt."""
        if motion is not None and (
            not isinstance(motion, str) or len(motion) > MAX_VIDEO_MOTION_CHARS
        ):
            raise GenerationValidationError(
                f"motion must be omitted or at most {MAX_VIDEO_MOTION_CHARS} characters"
            )
        normalized_motion = motion.strip() if isinstance(motion, str) and motion.strip() else None
        if not isinstance(loop_mode, str) or loop_mode not in VIDEO_LOOP_MODES:
            raise GenerationValidationError("loop_mode is unsupported")
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096:
            raise GenerationValidationError("an xAI API key is required")
        if privacy_acknowledged is not True:
            raise GenerationValidationError(
                "the current privacy disclosure must be acknowledged"
            )
        original = self._library.load_manifest(job_id)
        _models(original["models"])
        self._video_spec(original)
        self._candidate_asset(original, candidate_id)
        if self._has_unresolved_video_request(original):
            raise GenerationValidationError(
                "this job still has an accepted video request to retrieve"
            )
        if original["status"] == "in_progress":
            raise GenerationValidationError("this job already has an active operation")

        token, cancelled = self._gate.begin(job_id)
        try:
            self._library.preflight_job(job_id)
            current = self._library.load_manifest(job_id)
            if current["status"] == "in_progress":
                raise GenerationBusyError("the generation job changed before animation started")
            self._candidate_asset(current, candidate_id)
            if self._has_unresolved_video_request(current):
                raise GenerationValidationError(
                    "this job still has an accepted video request to retrieve"
                )
            attempt_id = str(uuid.uuid4())
            operation = self._video_plan_operation(current, attempt_id)
            timestamp = _now_iso()

            def prepare(manifest: dict) -> None:
                manifest["selected_candidate_id"] = candidate_id
                manifest["loop_mode"] = loop_mode
                manifest["animation_attempts"].append(
                    {
                        "attempt_id": attempt_id,
                        "candidate_id": candidate_id,
                        "loop_mode": loop_mode,
                        "status": "planning",
                        "phase": "video_planning",
                        "motion": normalized_motion,
                        "plan": None,
                        "request_id": None,
                        "source_video_asset_id": None,
                        "frame_asset_ids": [],
                        "preview_asset_id": None,
                        "mapped_result_asset_id": None,
                        "created_at": timestamp,
                        "completed_at": None,
                    }
                )
                manifest["provider_requests"][operation] = {
                    "status": "submitting",
                    "submitted_at": timestamp,
                }
                manifest["costs"]["estimated_ticks"] += estimate_video_animation_ticks(
                    manifest["models"]["video"]
                )
                _refresh_cost_completeness(manifest)
                manifest["status"] = "in_progress"
                manifest["phase"] = "video_planning"
                manifest["progress"] = {
                    "completed": 0,
                    "total": MODEL_FRAME_CAPS[manifest["target"]["family"]],
                }
                manifest["cancel_requested_at"] = None
                manifest["cancelled_at"] = None

            prepared = self._library.update_manifest(job_id, prepare)
            self._launch_video_worker(
                job_id,
                token,
                api_key,
                lambda: self._run_animation(
                    job_id,
                    attempt_id,
                    operation,
                    api_key,
                    cancelled,
                ),
            )
            return prepared
        except BaseException:
            if self._gate.active_job_id == job_id:
                self._gate.finish(token)
            raise

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

    def _fail_video_plan(
        self,
        job_id: str,
        attempt_id: str,
        operation: str,
        error: ProviderError,
        api_key: str,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            request = manifest["provider_requests"][operation]
            request["status"] = "failed"
            request["error_code"] = error.code
            request["completed_at"] = timestamp
            _record_usage(manifest, operation, error.usage)
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["status"] = "failed"
            attempt["phase"] = "video_plan_failed"
            attempt["completed_at"] = timestamp
            manifest["status"] = "failed"
            manifest["phase"] = "video_plan_failed"

        self._library.update_manifest(job_id, update)
        self._record_video_error(
            job_id,
            code=error.code,
            message=error.message,
            api_key=api_key,
        )

    def _record_submission_unknown(
        self,
        job_id: str,
        attempt_id: str,
        error: ProviderError,
        api_key: str,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            request = manifest["provider_requests"].setdefault(
                "video", {"status": "submitting", "submitted_at": timestamp}
            )
            request["status"] = "submission_unknown"
            request["error_code"] = error.code
            request["completed_at"] = timestamp
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["status"] = "submission_unknown"
            attempt["phase"] = "interrupted"
            attempt["completed_at"] = timestamp
            manifest["status"] = "submission_unknown"
            manifest["phase"] = "interrupted"
            _refresh_cost_completeness(manifest)

        self._library.update_manifest(job_id, update)
        self._record_video_error(
            job_id,
            code="submission_unknown",
            message=error.message,
            api_key=api_key,
        )

    def _finish_before_video_submit(
        self,
        job_id: str,
        attempt_id: str,
        unsubmitted_operation: str | None = None,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            if unsubmitted_operation is not None:
                manifest["provider_requests"].pop(unsubmitted_operation, None)
                manifest["costs"]["actual_by_operation"].pop(
                    unsubmitted_operation, None
                )
                _refresh_cost_completeness(manifest)
            attempt = _animation_attempt(manifest, attempt_id)
            attempt["status"] = "cancelled"
            attempt["phase"] = "video_cancelled"
            attempt["completed_at"] = timestamp
            manifest["status"] = "cancelled"
            manifest["phase"] = "video_cancelled"
            manifest["cancelled_at"] = timestamp

        self._library.update_manifest(job_id, update)

    def _run_animation(
        self,
        job_id: str,
        attempt_id: str,
        plan_operation: str,
        api_key: str,
        cancelled: threading.Event,
    ) -> None:
        try:
            manifest = self._library.load_manifest(job_id)
            owned = self._candidate_asset(manifest, manifest["selected_candidate_id"])
            image_bytes = owned.path.read_bytes()
            mime_type = owned.record["mime_type"]
            spec, _targets = self._video_spec(manifest)
            attempt = _animation_attempt(manifest, attempt_id)
            if cancelled.is_set():
                self._finish_before_video_submit(
                    job_id, attempt_id, unsubmitted_operation=plan_operation
                )
                return
            planner = self._video_planner_factory(
                api_key, manifest["models"]["interpreter"]
            )
            provider = self._video_provider_factory(api_key, manifest["models"]["video"])
            try:
                result = planner.plan(
                    manifest["prompt"],
                    attempt["motion"],
                    image_bytes,
                    mime_type,
                    spec,
                    attempt["loop_mode"],
                    self._monotonic() + self._operation_timeout_seconds,
                )
                if (
                    not isinstance(result, VideoAnimationPlanResult)
                    or not isinstance(result.plan, VideoAnimationPlan)
                ):
                    raise ProviderError(
                        "bad_response", "video planner returned an invalid result"
                    )
            except ProviderError as error:
                self._fail_video_plan(
                    job_id, attempt_id, plan_operation, error, api_key
                )
                return

            timestamp = _now_iso()

            def complete_plan(current: dict) -> None:
                request = current["provider_requests"][plan_operation]
                request["status"] = "complete"
                request["completed_at"] = timestamp
                _record_usage(current, plan_operation, result.usage)
                current_attempt = _animation_attempt(current, attempt_id)
                current_attempt["status"] = "planned"
                current_attempt["phase"] = "video_submitting"
                current_attempt["plan"] = {
                    "subject_lock": result.plan.subject_lock,
                    "style_lock": result.plan.style_lock,
                    "video_prompt": result.plan.video_prompt,
                }
                current["phase"] = "video_submitting"

            self._library.update_manifest(job_id, complete_plan)
            if cancelled.is_set():
                self._finish_before_video_submit(job_id, attempt_id)
                return

            submitted_at = _now_iso()

            def mark_submit(current: dict) -> None:
                current["provider_requests"]["video"] = {
                    "status": "submitting",
                    "submitted_at": submitted_at,
                    "poll_failures": 0,
                    "download_failures": 0,
                    "foreground_deadline_at": (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=self._foreground_timeout_seconds)
                    ).isoformat(),
                }
                _refresh_cost_completeness(current)
                current["phase"] = "video_submitting"

            self._library.update_manifest(job_id, mark_submit)
            if cancelled.is_set():
                def discard_submit(current: dict) -> None:
                    current["provider_requests"].pop("video", None)
                    _refresh_cost_completeness(current)

                self._library.update_manifest(job_id, discard_submit)
                self._finish_before_video_submit(job_id, attempt_id)
                return
            try:
                submission = provider.submit(
                    result.plan,
                    image_bytes,
                    mime_type,
                    self._monotonic() + self._operation_timeout_seconds,
                )
                if not isinstance(submission, VideoSubmission) or submission.status != "pending":
                    raise ProviderError(
                        "bad_response", "video provider returned an invalid submission"
                    )
            except ProviderError as error:
                self._record_submission_unknown(job_id, attempt_id, error, api_key)
                return

            accepted_at = _now_iso()

            def accept(current: dict) -> None:
                request = current["provider_requests"]["video"]
                request["request_id"] = submission.request_id
                request["status"] = "pending"
                request["submitted_at"] = accepted_at
                _record_usage(current, submission.request_id, submission.usage)
                current_attempt = _animation_attempt(current, attempt_id)
                current_attempt["request_id"] = submission.request_id
                current_attempt["status"] = "polling"
                current_attempt["phase"] = "video_polling"
                current["phase"] = "video_polling"

            acceptance_persisted = False
            for _attempt in range(self._safe_retry_limit):
                try:
                    self._library.update_manifest(job_id, accept)
                    acceptance_persisted = True
                    break
                except (LibraryError, OSError):
                    continue
            if not acceptance_persisted:
                try:
                    self._record_video_error(
                        job_id,
                        code="acceptance_persist_failed",
                        message=(
                            "The accepted video request ID could not be persisted; "
                            "the paid submission was not replayed."
                        ),
                        api_key=api_key,
                    )
                except (LibraryError, OSError):
                    pass
                return
            self._poll_and_retrieve(
                job_id,
                attempt_id,
                provider,
                submission.request_id,
                api_key,
                cancelled,
            )
        except (LibraryError, OSError, ValueError) as exc:
            self._fail_video_local(
                job_id,
                attempt_id,
                code="animation_failed",
                error=exc,
                api_key=api_key,
                ready_to_process=False,
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
                    if not background:
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
                frame_assets.append(
                    self._library.bank_asset(
                        job_id,
                        kind="frame",
                        data=path.read_bytes(),
                        mime_type="image/png",
                        origin=f"local_frame:{attempt_id}:{index}",
                    )
                )
            preview_asset = self._library.bank_asset(
                job_id,
                kind="preview_poster",
                data=processed.frame_paths[0].read_bytes(),
                mime_type="image/png",
                origin=f"local_preview:{attempt_id}",
            )
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

    def retry_local(self, job_id: str) -> dict:
        """Explicitly rerun only local conversion from a retained source MP4."""
        original = self._library.load_manifest(job_id)
        if original["status"] not in {"ready_to_process", "cancelled_saved"}:
            raise GenerationValidationError("this job has no retained video to process")
        attempt = _animation_attempt(original)
        source_asset_id = attempt.get("source_video_asset_id") or original["recovery"].get(
            "source_video_asset_id"
        )
        if not isinstance(source_asset_id, str):
            raise GenerationValidationError("this job has no retained video to process")
        try:
            source = self._library.resolve_asset(job_id, source_asset_id)
        except LibraryError:
            raise GenerationValidationError("the retained video is unavailable") from None
        if source.record["kind"] != "source_video":
            raise GenerationValidationError("the retained video is invalid")
        token, cancelled = self._gate.begin(job_id)
        try:
            self._library.preflight_job(job_id)

            def prepare(manifest: dict) -> None:
                current_attempt = _animation_attempt(manifest, attempt["attempt_id"])
                current_attempt["status"] = "processing"
                current_attempt["phase"] = "local_processing"
                manifest["status"] = "in_progress"
                manifest["phase"] = "local_processing"
                manifest["cancel_requested_at"] = None
                manifest["cancelled_at"] = None

            prepared = self._library.update_manifest(job_id, prepare)
            self._launch_video_worker(
                job_id,
                token,
                "",
                lambda: self._process_local(
                    job_id,
                    attempt["attempt_id"],
                    source_asset_id,
                    "",
                    cancelled,
                ),
            )
            return prepared
        except BaseException:
            if self._gate.active_job_id == job_id:
                self._gate.finish(token)
            raise

    def _resume_video_poll(
        self,
        job_id: str,
        request_id: str,
        api_key: str,
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
        frames = [
            asset
            for asset in manifest["assets"]
            if asset["kind"] == "frame"
            and asset["origin"].startswith(f"local_frame:{attempt_id}:")
        ]
        frames.sort(key=lambda asset: int(asset["origin"].rsplit(":", 1)[1]))
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

        timestamp = _now_iso()

        def update(current: dict) -> None:
            current_attempt = _animation_attempt(current, attempt_id)
            current_attempt["source_video_asset_id"] = source["asset_id"]
            current["recovery"]["source_video_asset_id"] = source["asset_id"]
            if complete:
                current_attempt["frame_asset_ids"] = [
                    asset["asset_id"] for asset in frames
                ]
                current_attempt["preview_asset_id"] = preview["asset_id"]
                current_attempt["mapped_result_asset_id"] = mapped_asset["asset_id"]
                current_attempt["status"] = "complete"
                current_attempt["phase"] = "ready_for_review"
                current_attempt["completed_at"] = timestamp
                current["status"] = "ready"
                current["phase"] = "ready_for_review"
                current["progress"] = {
                    "completed": frame_count,
                    "total": frame_count,
                }
            elif current["cancel_requested_at"] is not None or current["status"] == "cancelled":
                current_attempt["status"] = "cancelled_saved"
                current_attempt["phase"] = "cancelled_saved"
                current["status"] = "cancelled_saved"
                current["phase"] = "cancelled_saved"
            else:
                current_attempt["status"] = "ready_to_process"
                current_attempt["phase"] = "ready_to_process"
                current["status"] = "ready_to_process"
                current["phase"] = "ready_to_process"

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

    def wait(self, job_id: str, timeout: float | None = None) -> dict:
        with self._workers_lock:
            worker = self._workers.get(job_id)
        join = getattr(worker, "join", None)
        if callable(join):
            join(timeout)
            is_alive = getattr(worker, "is_alive", None)
            if callable(is_alive) and is_alive():
                raise TimeoutError("generation operation is still active")
        return self._library.load_manifest(job_id)

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

    def reconcile_startup(self, *, api_key: str | None = None) -> list[dict]:
        """Reconcile state and optionally resume one accepted request without POSTs."""
        if api_key is not None and (
            not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096
        ):
            raise GenerationValidationError("an xAI API key is required")
        actions = self._library.reconcile()
        for job in self._library.scan()["jobs"]:
            try:
                self._reconcile_interrupted_animation(job["job_id"])
                self._recover_banked_candidates(job["job_id"])
                self._recover_banked_animation(job["job_id"])
            except Exception:
                # The library scan/reconciliation error surface remains the
                # authority; one unreadable job must not hide the others.
                continue
        if api_key is not None and actions:
            first = actions[0]
            self._resume_video_poll(first["job_id"], first["request_id"], api_key)
        return actions

    @staticmethod
    def _planner_operation(manifest: dict, batch_id: str) -> str:
        if "concept_plan" not in manifest["provider_requests"]:
            return "concept_plan"
        return f"concept_plan:{batch_id}"

    def _mark_submitting(self, job_id: str, operation: str) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            manifest["provider_requests"][operation] = {
                "status": "submitting",
                "submitted_at": timestamp,
            }
            _refresh_cost_completeness(manifest)

        self._library.update_manifest(job_id, update)

    def _discard_unsubmitted(self, job_id: str, operation: str) -> None:
        def update(manifest: dict) -> None:
            manifest["provider_requests"].pop(operation, None)
            manifest["costs"]["actual_by_operation"].pop(operation, None)
            _refresh_cost_completeness(manifest)

        self._library.update_manifest(job_id, update)

    def _complete_plan(
        self,
        job_id: str,
        batch_id: str,
        operation: str,
        result: ConceptPlanResult,
    ) -> None:
        if not isinstance(result, ConceptPlanResult):
            raise ProviderError("bad_response", "concept planner returned an invalid result")
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            record = _batch(manifest, batch_id)
            if len(result.plan.candidate_prompts) != record["requested_count"]:
                raise ProviderError(
                    "bad_response",
                    "concept planner returned the wrong count",
                    usage=result.usage,
                )
            record["status"] = "generating"
            record["visual_brief"] = result.plan.visual_brief
            record["candidate_prompts"] = list(result.plan.candidate_prompts)
            manifest["provider_requests"][operation]["status"] = "complete"
            manifest["provider_requests"][operation]["completed_at"] = timestamp
            _record_usage(manifest, operation, result.usage)
            manifest["phase"] = "concept_generation"

        self._library.update_manifest(job_id, update)

    def _record_provider_failure(
        self,
        job_id: str,
        batch_id: str,
        operation: str,
        error: ProviderError,
        api_key: str,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            request = manifest["provider_requests"].setdefault(
                operation, {"status": "submitting", "submitted_at": timestamp}
            )
            request["status"] = "failed"
            request["error_code"] = error.code
            request["completed_at"] = timestamp
            _record_usage(manifest, operation, error.usage)
            record = _batch(manifest, batch_id)
            record["status"] = "partial" if record["candidate_ids"] else "failed"
            record["completed_at"] = timestamp
            if manifest["candidates"]:
                manifest["status"] = "partial"
                manifest["phase"] = "concepts_partial"
            else:
                manifest["status"] = "failed"
                manifest["phase"] = "concepts_failed"

        self._library.update_manifest(job_id, update)
        self._library.record_error(
            job_id,
            code=error.code,
            message=error.message,
            sensitive_values=(api_key,),
        )

    def _fail_local(
        self,
        job_id: str,
        batch_id: str,
        code: str,
        error: object,
        api_key: str,
    ) -> None:
        try:
            self._library.record_error(
                job_id,
                code=code,
                message=str(error) or "The local generation operation failed.",
                sensitive_values=(api_key,),
            )
            timestamp = _now_iso()

            def update(manifest: dict) -> None:
                record = _batch(manifest, batch_id)
                record["status"] = "partial" if record["candidate_ids"] else "failed"
                record["completed_at"] = timestamp
                if manifest["candidates"]:
                    manifest["status"] = "partial"
                    manifest["phase"] = "concepts_partial"
                else:
                    manifest["status"] = "failed"
                    manifest["phase"] = "concepts_failed"

            self._library.update_manifest(job_id, update)
            self._recover_banked_candidates(job_id)
        except Exception:
            pass

    def _finish_cancelled(self, job_id: str, batch_id: str) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            record = _batch(manifest, batch_id)
            record["status"] = "cancelled"
            record["completed_at"] = timestamp
            manifest["status"] = "cancelled"
            manifest["phase"] = "concepts_cancelled"
            manifest["cancelled_at"] = timestamp

        self._library.update_manifest(job_id, update)

    def _finish_success(
        self,
        job_id: str,
        batch_id: str,
        cancelled: threading.Event,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            record = _batch(manifest, batch_id)
            if cancelled.is_set():
                record["status"] = "cancelled"
                record["completed_at"] = timestamp
                manifest["status"] = "cancelled"
                manifest["phase"] = "concepts_cancelled"
                manifest["cancelled_at"] = timestamp
                return
            record["status"] = "complete"
            record["completed_at"] = timestamp
            manifest["status"] = "awaiting_selection"
            manifest["phase"] = "awaiting_selection"
            manifest["progress"]["completed"] = record["requested_count"]

        self._library.update_manifest(job_id, update)

    def _record_response_usage(
        self,
        job_id: str,
        operation: str,
        usage: ProviderUsage,
    ) -> None:
        def update(manifest: dict) -> None:
            manifest["provider_requests"][operation]["status"] = "response_received"
            _record_usage(manifest, operation, usage)

        self._library.update_manifest(job_id, update)

    def _publish_candidate(
        self,
        job_id: str,
        batch_id: str,
        index: int,
        operation: str,
        prompt: str,
        result: ConceptImageResult,
    ) -> None:
        asset = self._library.bank_asset(
            job_id,
            kind="concept",
            data=result.original_bytes,
            mime_type=result.metadata.mime_type,
            origin=f"xai_concept:{batch_id}:{index}",
        )
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            record = _batch(manifest, batch_id)
            asset_id = asset["asset_id"]
            manifest["candidates"].append(
                {
                    "candidate_id": asset_id,
                    "asset_id": asset_id,
                    "batch_id": batch_id,
                    "prompt": prompt,
                    "revised_prompt": result.metadata.revised_prompt,
                    "width": result.metadata.width,
                    "height": result.metadata.height,
                    "mime_type": result.metadata.mime_type,
                    "status": "complete",
                    "created_at": asset["created_at"],
                }
            )
            record["candidate_ids"].append(asset_id)
            request = manifest["provider_requests"].pop(operation)
            request["status"] = "complete"
            request["completed_at"] = timestamp
            manifest["provider_requests"][asset_id] = request
            actual = manifest["costs"]["actual_by_operation"]
            if operation in actual:
                actual[asset_id] = actual.pop(operation)
            _refresh_cost_completeness(manifest)
            manifest["progress"]["completed"] = len(record["candidate_ids"])

        self._library.update_manifest(job_id, update)

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

    def _run_batch(
        self,
        job_id: str,
        batch_id: str,
        api_key: str,
        deadline: float,
        cancelled: threading.Event,
    ) -> None:
        try:
            if cancelled.is_set():
                self._finish_cancelled(job_id, batch_id)
                return
            manifest = self._library.load_manifest(job_id)
            planner_operation = self._planner_operation(manifest, batch_id)
            planner = self._planner_factory(api_key, manifest["models"]["interpreter"])
            image_provider = self._image_provider_factory(api_key, manifest["models"]["concept"])
            self._mark_submitting(job_id, planner_operation)
            if cancelled.is_set():
                self._discard_unsubmitted(job_id, planner_operation)
                self._finish_cancelled(job_id, batch_id)
                return
            try:
                plan_result = planner.plan(
                    manifest["prompt"],
                    _batch(manifest, batch_id)["requested_count"],
                    deadline,
                )
                self._complete_plan(job_id, batch_id, planner_operation, plan_result)
            except ProviderError as error:
                self._record_provider_failure(
                    job_id, batch_id, planner_operation, error, api_key
                )
                return
            plan = plan_result.plan
            for index, prompt in enumerate(plan.candidate_prompts):
                if cancelled.is_set():
                    self._finish_cancelled(job_id, batch_id)
                    return
                operation = f"candidate_attempt:{batch_id}:{index}"
                self._mark_submitting(job_id, operation)
                if cancelled.is_set():
                    self._discard_unsubmitted(job_id, operation)
                    self._finish_cancelled(job_id, batch_id)
                    return
                try:
                    result = image_provider.generate_one(prompt, deadline)
                    if not isinstance(result, ConceptImageResult):
                        raise ProviderError(
                            "bad_response", "concept image provider returned an invalid result"
                        )
                    self._record_response_usage(job_id, operation, result.usage)
                    try:
                        self._publish_candidate(
                            job_id, batch_id, index, operation, prompt, result
                        )
                    finally:
                        close = getattr(result.image, "close", None)
                        if callable(close):
                            close()
                except ProviderError as error:
                    self._record_provider_failure(job_id, batch_id, operation, error, api_key)
                    return
            if cancelled.is_set():
                self._finish_cancelled(job_id, batch_id)
                return
            self._finish_success(job_id, batch_id, cancelled)
        except Exception as error:
            self._fail_local(job_id, batch_id, "generation_failed", error, api_key)


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
    "MAX_CONCEPT_CANDIDATES",
    "OperationGate",
    "canonical_target_snapshot",
    "estimate_concept_batch_ticks",
    "estimate_video_animation_ticks",
]
