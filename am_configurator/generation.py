"""Durable, injected orchestration for Lighting Studio generation jobs.

The coordinator owns operation ordering and manifest state, not HTTP or device
I/O.  Paid collaborators are factories so API keys remain ephemeral, and the
default process gate permits exactly one provider/local operation at a time.
Startup reconciliation delegates to the library and never schedules paid work.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Mapping

from .ai_catalog import MODEL_CATALOG, validate_model
from .library import GeneratedAssetLibrary, ManifestError
from .llm import (
    MAX_CONCEPT_CANDIDATES,
    MAX_CONCEPT_PROMPT_CHARS,
    MODEL_FRAME_CAPS,
    VIDEO_LOOP_MODES,
    ConceptImageResult,
    ConceptPlanResult,
    GrokConceptImageProvider,
    GrokConceptPlanner,
    ProviderError,
    ProviderUsage,
)


DEFAULT_OPERATION_TIMEOUT_SECONDS = 10 * 60
_MODEL_ROLES = frozenset(MODEL_CATALOG)


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


def _target_snapshot(value: object) -> dict:
    if not isinstance(value, Mapping):
        raise GenerationValidationError("target must be an object")
    allowed = {"family", "product_id", "raster", "targets", "frame_cap"}
    if not {"family", "raster", "targets"}.issubset(value) or not set(value).issubset(
        allowed
    ):
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
    product_id = value.get("product_id")
    if product_id is not None and (
        not isinstance(product_id, str)
        or not product_id
        or len(product_id) > 200
        or any(character.isspace() for character in product_id)
    ):
        raise GenerationValidationError("target product ID is invalid")
    snapshot = {
        "family": family,
        "raster": {"width": width, "height": height},
        "targets": list(targets),
        "frame_cap": expected_cap,
    }
    if product_id is not None:
        snapshot["product_id"] = product_id
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
    snapshot = _target_snapshot(target)
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


def _usage_cost(usage: object) -> int | None:
    if not isinstance(usage, ProviderUsage) or usage.reported is not True:
        return None
    cost = usage.cost_in_usd_ticks
    if not isinstance(cost, int) or isinstance(cost, bool) or cost < 0:
        return None
    return cost


def _refresh_cost_completeness(manifest: dict) -> None:
    actual = manifest["costs"]["actual_by_operation"]
    manifest["costs"]["actual_incomplete"] = any(
        operation not in actual for operation in manifest["provider_requests"]
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
        operation_gate: OperationGate = _PROCESS_OPERATION_GATE,
        launcher: Callable[[Callable[[], None]], object] = _default_launcher,
        monotonic: Callable[[], float] = time.monotonic,
        operation_timeout_seconds: float = DEFAULT_OPERATION_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(library, GeneratedAssetLibrary):
            raise TypeError("library must be a GeneratedAssetLibrary")
        if (
            isinstance(operation_timeout_seconds, bool)
            or not isinstance(operation_timeout_seconds, (int, float))
            or not 1 <= operation_timeout_seconds <= 3600
        ):
            raise ValueError("operation_timeout_seconds is invalid")
        self._library = library
        self._planner_factory = planner_factory
        self._image_provider_factory = image_provider_factory
        self._gate = operation_gate
        self._launcher = launcher
        self._monotonic = monotonic
        self._operation_timeout_seconds = float(operation_timeout_seconds)
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

        return self._library.update_manifest(job_id, update)

    def reconcile_startup(self) -> list[dict]:
        """Reconcile durable state without invoking any provider or local worker."""
        actions = self._library.reconcile()
        for job in self._library.scan()["jobs"]:
            try:
                self._recover_banked_candidates(job["job_id"])
            except Exception:
                # The library scan/reconciliation error surface remains the
                # authority; one unreadable job must not hide the others.
                continue
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
    "DEFAULT_OPERATION_TIMEOUT_SECONDS",
    "GenerationBusyError",
    "GenerationCoordinator",
    "GenerationError",
    "GenerationNotActiveError",
    "GenerationValidationError",
    "MAX_CONCEPT_CANDIDATES",
    "OperationGate",
    "estimate_concept_batch_ticks",
]
