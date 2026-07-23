"""Durable local-first procedural generation and crash reconciliation."""

from __future__ import annotations

import copy
import contextlib
import io
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from PIL import Image

from . import ai_catalog, procedural
from .generation import (
    PROCESS_OPERATION_GATE,
    GenerationBusyError,
    GenerationError,
    GenerationNotActiveError,
    GenerationValidationError,
    OperationGate,
    canonical_target_snapshot,
)
from .library import GeneratedAssetLibrary, ManifestError
from .llm import LED_SPEEDS_MS, ProviderError, ProviderUsage
from .recipe_provider import (
    LOCAL_MAX_RETRIES,
    MAX_RECIPE_PROMPT_CHARS,
    RecipeRequest,
    RecipeResult,
)


DEFAULT_OPERATION_TIMEOUT_SECONDS = 180.0
FASTEST_FRAME_DURATION_MS = min(LED_SPEEDS_MS)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_launcher(target: Callable[[], None]):
    worker = threading.Thread(
        target=target,
        name="am-procedural-generation",
        daemon=True,
    )
    worker.start()
    return worker


def _attempt(manifest: dict, attempt_id: str) -> dict:
    matches = [
        item
        for item in manifest["procedural_attempts"]
        if item.get("attempt_id") == attempt_id
    ]
    if len(matches) != 1:
        raise ManifestError("The procedural attempt was not found.")
    return matches[0]


def _usage_ticks(value: object) -> int | None:
    if isinstance(value, dict) and set(value) == {"cost_in_usd_ticks"}:
        ticks = value["cost_in_usd_ticks"]
        return ticks if type(ticks) is int and ticks >= 0 else None
    if isinstance(value, ProviderUsage) and value.reported is True:
        ticks = value.cost_in_usd_ticks
        return ticks if type(ticks) is int and ticks >= 0 else None
    return None


def _gif_bytes(frames: list[Image.Image], durations: list[int]) -> bytes:
    output = io.BytesIO()
    procedural.write_gif(frames, output, durations)  # type: ignore[arg-type]
    return output.getvalue()


class ProceduralGenerationCoordinator:
    """Bank one exact procedural result without ever auto-replaying API work."""

    def __init__(
        self,
        library: GeneratedAssetLibrary,
        capability,
        *,
        operation_gate: OperationGate = PROCESS_OPERATION_GATE,
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
        self._capability = capability
        self._gate = operation_gate
        self._launcher = launcher
        self._monotonic = monotonic
        self._operation_timeout_seconds = float(operation_timeout_seconds)
        self._workers: dict[str, object] = {}
        self._workers_lock = threading.Lock()

    @property
    def active_job_id(self) -> str | None:
        return self._gate.active_job_id

    @staticmethod
    def _request_values(prompt: object, target: object, loop_mode: object) -> tuple[str, dict, str]:
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > MAX_RECIPE_PROMPT_CHARS
        ):
            raise GenerationValidationError(
                f"prompt must be a non-empty string of at most {MAX_RECIPE_PROMPT_CHARS} characters"
            )
        snapshot = canonical_target_snapshot(target)
        if loop_mode not in {"smooth", "none", "ping_pong"}:
            raise GenerationValidationError("loop_mode is unsupported")
        return prompt.strip(), snapshot, loop_mode

    @staticmethod
    def _model_record(status: dict[str, Any]) -> dict[str, str]:
        backend = status["backend"]
        if backend == "local":
            model_id = status["local"].get("model_id")
            provider = status["local"].get("provider")
            if (
                not isinstance(model_id, str)
                or not model_id
                or provider != "ollama"
            ):
                raise GenerationValidationError("the selected local model is unavailable")
            return {
                "backend": "local",
                "provider": provider,
                "model_id": model_id,
            }
        if backend == "api":
            return {
                "backend": "api",
                "provider": status["api"]["provider"],
                "model_id": status["api"]["model_id"],
            }
        raise GenerationValidationError("an AI backend is not selected")

    def start_effect(
        self,
        *,
        prompt: object,
        target: object,
        loop_mode: object,
    ) -> dict:
        prompt, snapshot, loop_mode = self._request_values(prompt, target, loop_mode)
        capability = self._capability.require_ready()
        models = self._model_record(capability)
        provider = self._capability.provider_for_generation()
        self._library.preflight()
        token, cancelled = self._gate.begin()
        job_id: str | None = None
        try:
            manifest = self._library.create_job(
                prompt=prompt,
                target=snapshot,
                models=models,
                loop_mode=loop_mode,
                pipeline="procedural",
            )
            job_id = manifest["job_id"]
            self._gate.bind(token, job_id)

            def initialize(current: dict) -> None:
                if models["backend"] == "api":
                    current["costs"]["estimated_ticks"] = (
                        ai_catalog.recipe_max_cost_usd_ticks(
                            models["provider"], models["model_id"]
                        )
                    )
                current["status"] = "in_progress"
                current["phase"] = "queued"
                current["progress"] = {
                    "completed": 0,
                    "total": snapshot["frame_cap"],
                }

            self._library.update_manifest(job_id, initialize)
            self._launch(job_id, provider, token, cancelled)
            return self._library.get_job(job_id)
        except BaseException:
            self._gate.finish(token)
            raise

    def _launch(
        self,
        job_id: str,
        provider,
        token: object,
        cancelled: threading.Event,
    ) -> None:
        deadline = self._monotonic() + self._operation_timeout_seconds

        def target() -> None:
            try:
                self._run(job_id, provider, deadline, cancelled)
            except Exception as error:
                with contextlib.suppress(Exception):
                    self._library.record_error(
                        job_id,
                        code="procedural_interrupted",
                        message=error,
                    )
                with contextlib.suppress(Exception):
                    self._reconcile_job(job_id)
            finally:
                self._gate.finish(token)
                with self._workers_lock:
                    self._workers.pop(job_id, None)

        try:
            worker = self._launcher(target)
        except Exception as error:
            self._finish_job_failure(
                job_id,
                None,
                "worker_start_failed",
                error,
            )
            raise GenerationError("the generation worker could not be started") from None
        if self._gate.active_job_id == job_id:
            with self._workers_lock:
                self._workers[job_id] = worker

    def _begin_attempt(self, job_id: str, index: int) -> tuple[str, str]:
        attempt_id = str(uuid.uuid4())
        operation = f"recipe:{attempt_id}"
        timestamp = _now_iso()

        def begin(manifest: dict) -> None:
            manifest["procedural_attempts"].append({
                "attempt_id": attempt_id,
                "index": index,
                "status": "in_progress",
                "phase": "recipe_about_to_start",
                "started_at": timestamp,
                "completed_at": None,
                "recipe_asset_id": None,
                "raster_asset_id": None,
                "preview_asset_id": None,
                "mapped_result_asset_id": None,
                "quality": None,
                "usage": None,
                "error_code": None,
            })
            manifest["provider_requests"][operation] = {
                "status": "about_to_start",
                "submitted_at": timestamp,
            }
            manifest["status"] = "in_progress"
            manifest["phase"] = "recipe_about_to_start"

        self._library.update_manifest(job_id, begin)

        def generating(manifest: dict) -> None:
            _attempt(manifest, attempt_id)["phase"] = "recipe_generating"
            manifest["provider_requests"][operation]["status"] = "in_progress"
            manifest["phase"] = "recipe_generating"

        self._library.update_manifest(job_id, generating)
        return attempt_id, operation

    @staticmethod
    def _matches_selection(result: RecipeResult, models: dict[str, str]) -> bool:
        return (
            isinstance(result, RecipeResult)
            and result.backend == models["backend"]
            and result.provider == models["provider"]
            and result.model_id == models["model_id"]
        )

    def _record_provider_result(
        self,
        job_id: str,
        attempt_id: str,
        operation: str,
        usage: object,
    ) -> None:
        timestamp = _now_iso()
        ticks = _usage_ticks(usage)

        def update(manifest: dict) -> None:
            attempt = _attempt(manifest, attempt_id)
            attempt["usage"] = (
                None if ticks is None else {"cost_in_usd_ticks": ticks}
            )
            request = manifest["provider_requests"][operation]
            request["status"] = "complete"
            request["completed_at"] = timestamp
            if ticks is not None:
                manifest["costs"]["actual_by_operation"][operation] = ticks
            elif manifest["models"]["backend"] == "api":
                manifest["costs"]["actual_incomplete"] = True

        self._library.update_manifest(job_id, update)

    def _fail_attempt(
        self,
        job_id: str,
        attempt_id: str,
        operation: str,
        code: str,
        *,
        usage: object = None,
        quality: dict | None = None,
        recipe_asset_id: str | None = None,
    ) -> None:
        timestamp = _now_iso()
        ticks = _usage_ticks(usage)

        def update(manifest: dict) -> None:
            attempt = _attempt(manifest, attempt_id)
            attempt["status"] = "failed"
            attempt["phase"] = "attempt_failed"
            attempt["completed_at"] = timestamp
            attempt["error_code"] = code
            attempt["quality"] = copy.deepcopy(quality)
            attempt["recipe_asset_id"] = recipe_asset_id
            attempt["usage"] = (
                None if ticks is None else {"cost_in_usd_ticks": ticks}
            )
            request = manifest["provider_requests"][operation]
            request["status"] = "failed"
            request["completed_at"] = timestamp
            request["error_code"] = code
            if ticks is not None:
                manifest["costs"]["actual_by_operation"][operation] = ticks
            elif manifest["models"]["backend"] == "api":
                manifest["costs"]["actual_incomplete"] = True

        self._library.update_manifest(job_id, update)

    def _finish_cancelled(self, job_id: str, attempt_id: str | None) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            manifest["status"] = "cancelled"
            manifest["phase"] = "cancelled"
            manifest["cancelled_at"] = timestamp
            if attempt_id is not None:
                attempt = _attempt(manifest, attempt_id)
                attempt["status"] = "cancelled"
                attempt["phase"] = "cancelled"
                attempt["completed_at"] = timestamp

        self._library.update_manifest(job_id, update)

    def _finish_job_failure(
        self,
        job_id: str,
        attempt_id: str | None,
        code: str,
        error: object,
    ) -> None:
        timestamp = _now_iso()

        def update(manifest: dict) -> None:
            manifest["status"] = "failed"
            manifest["phase"] = "effect_failed"
            if attempt_id is not None:
                attempt = _attempt(manifest, attempt_id)
                if attempt["status"] == "in_progress":
                    attempt["status"] = "failed"
                    attempt["phase"] = "attempt_failed"
                    attempt["completed_at"] = timestamp
                    attempt["error_code"] = code

        self._library.update_manifest(job_id, update)
        self._library.record_error(job_id, code=code, message=error)

    def _run(
        self,
        job_id: str,
        provider,
        deadline: float,
        cancelled: threading.Event,
    ) -> None:
        manifest = self._library.load_manifest(job_id)
        models = manifest["models"]
        target = manifest["target"]
        backend = models["backend"]
        max_attempt = LOCAL_MAX_RETRIES if backend == "local" else 0
        retry_reason: str | None = None
        request = RecipeRequest(
            prompt=manifest["prompt"],
            width=target["raster"]["width"],
            height=target["raster"]["height"],
            frame_count=target["frame_cap"],
            density_default="balanced",
        )

        for index in range(max_attempt + 1):
            if cancelled.is_set() and backend == "local":
                self._finish_cancelled(job_id, None)
                return
            attempt_id, operation = self._begin_attempt(job_id, index)
            try:
                if index == 0:
                    result = provider.generate(
                        request, deadline, cancelled.is_set
                    )
                else:
                    result = provider.generate_attempt(
                        request,
                        deadline,
                        cancelled.is_set,
                        attempt=index,
                        validation_reason=retry_reason,
                    )
            except ProviderError as error:
                self._fail_attempt(
                    job_id,
                    attempt_id,
                    operation,
                    error.code,
                    usage=error.usage,
                )
                if cancelled.is_set():
                    self._finish_cancelled(job_id, attempt_id)
                    return
                if backend == "local" and error.code == "bad_response" and index < max_attempt:
                    retry_reason = "recipe schema or semantic validation"
                    continue
                self._finish_job_failure(job_id, attempt_id, error.code, error)
                return
            except Exception as error:
                self._fail_attempt(job_id, attempt_id, operation, "provider_failed")
                self._finish_job_failure(
                    job_id, attempt_id, "provider_failed", error
                )
                return

            if not self._matches_selection(result, models):
                self._fail_attempt(job_id, attempt_id, operation, "backend_mismatch")
                self._finish_job_failure(
                    job_id,
                    attempt_id,
                    "backend_mismatch",
                    "The recipe backend changed during generation.",
                )
                return
            self._record_provider_result(
                job_id, attempt_id, operation, result.usage
            )
            if cancelled.is_set() and backend == "local":
                self._finish_cancelled(job_id, attempt_id)
                return

            recipe_bytes = (
                json.dumps(result.recipe, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            recipe_asset = self._library.bank_asset(
                job_id,
                kind="recipe",
                data=recipe_bytes,
                mime_type="application/json",
                origin=f"procedural:{attempt_id}:recipe",
            )
            try:
                frames = procedural.render_recipe(
                    result.recipe,
                    width=request.width,
                    height=request.height,
                    frame_count=request.frame_count,
                )
                quality = procedural.validate_quality(
                    result.recipe,
                    frames,
                    width=request.width,
                    height=request.height,
                    frame_count=request.frame_count,
                )
            except procedural.QualityError as error:
                metrics = None if error.metrics is None else error.metrics.to_dict()
                self._fail_attempt(
                    job_id,
                    attempt_id,
                    operation,
                    "quality_failed",
                    usage=result.usage,
                    quality=metrics,
                    recipe_asset_id=recipe_asset["asset_id"],
                )
                if backend == "local" and index < max_attempt and not cancelled.is_set():
                    retry_reason = ", ".join(error.failures)
                    continue
                self._finish_job_failure(
                    job_id, attempt_id, "quality_failed", error
                )
                return
            except Exception as error:
                self._fail_attempt(
                    job_id,
                    attempt_id,
                    operation,
                    "render_failed",
                    usage=result.usage,
                    recipe_asset_id=recipe_asset["asset_id"],
                )
                self._finish_job_failure(
                    job_id, attempt_id, "render_failed", error
                )
                return

            if cancelled.is_set() and backend == "local":
                self._finish_cancelled(job_id, attempt_id)
                return
            quality_value = quality.to_dict()

            def rendering_complete(current: dict) -> None:
                attempt = _attempt(current, attempt_id)
                attempt["quality"] = quality_value
                attempt["recipe_asset_id"] = recipe_asset["asset_id"]
                attempt["phase"] = "artifact_banking"
                current["phase"] = "artifact_banking"

            self._library.update_manifest(job_id, rendering_complete)
            durations = procedural.gif_durations(
                request.frame_count, FASTEST_FRAME_DURATION_MS
            )
            raster_bytes = _gif_bytes(frames, durations)
            if cancelled.is_set() and backend == "local":
                self._finish_cancelled(job_id, attempt_id)
                return
            preview_frames = [
                frame.resize(
                    (request.width * 40, request.height * 40),
                    Image.Resampling.NEAREST,
                )
                for frame in frames
            ]
            preview_bytes = _gif_bytes(preview_frames, durations)
            if cancelled.is_set() and backend == "local":
                self._finish_cancelled(job_id, attempt_id)
                return
            mapped = procedural.map_frames_to_led_tracks(
                frames,
                duration_ms=FASTEST_FRAME_DURATION_MS,
                product_id=target["product_id"],
                targets=target["targets"],
            )
            mapped_bytes = (
                json.dumps(mapped, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("utf-8")
            raster_asset = self._library.bank_asset(
                job_id,
                kind="raster_animation",
                data=raster_bytes,
                mime_type="image/gif",
                origin=f"procedural:{attempt_id}:raster",
            )
            preview_asset = self._library.bank_asset(
                job_id,
                kind="preview_animation",
                data=preview_bytes,
                mime_type="image/gif",
                origin=f"procedural:{attempt_id}:preview",
            )
            mapped_asset = self._library.bank_asset(
                job_id,
                kind="mapped_result",
                data=mapped_bytes,
                mime_type="application/json",
                origin=f"procedural:{attempt_id}:mapped",
            )
            timestamp = _now_iso()

            def finish(current: dict) -> None:
                attempt = _attempt(current, attempt_id)
                attempt["status"] = "complete"
                attempt["phase"] = "ready_for_review"
                attempt["completed_at"] = timestamp
                attempt["raster_asset_id"] = raster_asset["asset_id"]
                attempt["preview_asset_id"] = preview_asset["asset_id"]
                attempt["mapped_result_asset_id"] = mapped_asset["asset_id"]
                current["progress"] = {
                    "completed": request.frame_count,
                    "total": request.frame_count,
                }
                if cancelled.is_set():
                    current["status"] = "cancelled_saved"
                    current["phase"] = "cancelled_saved"
                    current["cancelled_at"] = timestamp
                else:
                    current["status"] = "ready"
                    current["phase"] = "ready_for_review"

            self._library.update_manifest(job_id, finish)
            return

    def cancel(self, job_id: str) -> dict:
        if not self._gate.request_cancel(job_id):
            raise GenerationNotActiveError(
                "the generation operation is no longer active"
            )
        timestamp = _now_iso()

        def request(current: dict) -> None:
            if current["pipeline"] != "procedural" or current["status"] != "in_progress":
                raise GenerationNotActiveError(
                    "the procedural job completed before cancellation could be accepted"
                )
            if current["cancel_requested_at"] is None:
                current["cancel_requested_at"] = timestamp

        return self._library.update_manifest(job_id, request)

    def _valid_origin_asset(
        self, manifest: dict, attempt_id: str, suffix: str, kind: str
    ) -> dict | None:
        matches = [
            asset
            for asset in manifest["assets"]
            if asset["kind"] == kind
            and asset["origin"] == f"procedural:{attempt_id}:{suffix}"
            and asset["status"] == "complete"
        ]
        if len(matches) != 1:
            return None
        try:
            self._library.resolve_asset(manifest["job_id"], matches[0]["asset_id"])
        except Exception:
            return None
        return matches[0]

    def _reconcile_job(self, job_id: str) -> dict | None:
        manifest = self._library.load_manifest(job_id)
        if manifest["pipeline"] != "procedural":
            return None
        if manifest["status"] in {
            "ready",
            "cancelled",
            "cancelled_saved",
            "failed",
            "interrupted",
        }:
            return None
        if not manifest["procedural_attempts"]:
            backend = manifest["models"].get("backend")
            phase = (
                "retryable_local"
                if backend == "local"
                else "interrupted_api_no_replay"
            )

            def interrupt_empty(current: dict) -> None:
                current["status"] = "interrupted"
                current["phase"] = phase

            self._library.update_manifest(job_id, interrupt_empty)
            return None
        attempt = manifest["procedural_attempts"][-1]
        attempt_id = attempt["attempt_id"]
        if attempt["status"] == "failed":

            def settle_failed(current: dict) -> None:
                current["status"] = "failed"
                current["phase"] = "effect_failed"

            self._library.update_manifest(job_id, settle_failed)
            return None
        assets = {
            "recipe_asset_id": self._valid_origin_asset(
                manifest, attempt_id, "recipe", "recipe"
            ),
            "raster_asset_id": self._valid_origin_asset(
                manifest, attempt_id, "raster", "raster_animation"
            ),
            "preview_asset_id": self._valid_origin_asset(
                manifest, attempt_id, "preview", "preview_animation"
            ),
            "mapped_result_asset_id": self._valid_origin_asset(
                manifest, attempt_id, "mapped", "mapped_result"
            ),
        }
        if attempt["quality"] is not None and all(assets.values()):
            timestamp = _now_iso()

            def adopt(current: dict) -> None:
                current_attempt = _attempt(current, attempt_id)
                for field, asset in assets.items():
                    assert asset is not None
                    current_attempt[field] = asset["asset_id"]
                current_attempt["status"] = "complete"
                current_attempt["phase"] = "ready_for_review"
                current_attempt["completed_at"] = timestamp
                current["progress"] = {
                    "completed": current["target"]["frame_cap"],
                    "total": current["target"]["frame_cap"],
                }
                if current["cancel_requested_at"] is not None:
                    current["status"] = "cancelled_saved"
                    current["phase"] = "cancelled_saved"
                    current["cancelled_at"] = timestamp
                else:
                    current["status"] = "ready"
                    current["phase"] = "ready_for_review"

            self._library.update_manifest(job_id, adopt)
            return {"job_id": job_id, "action": "adopted_banked_procedural"}

        backend = manifest["models"].get("backend")
        phase = "retryable_local" if backend == "local" else "interrupted_api_no_replay"
        timestamp = _now_iso()

        def interrupt(current: dict) -> None:
            current_attempt = _attempt(current, attempt_id)
            current_attempt["status"] = "interrupted"
            current_attempt["phase"] = phase
            if current_attempt["completed_at"] is None:
                current_attempt["completed_at"] = timestamp
            current["status"] = "interrupted"
            current["phase"] = phase

        self._library.update_manifest(job_id, interrupt)
        return None

    def reconcile_startup(
        self,
        *,
        _admission_token: object | None = None,
    ) -> list[dict]:
        owns_admission = _admission_token is None
        if owns_admission:
            token, _cancelled = self._gate.begin()
        else:
            token = _admission_token
            self._gate.require(token)
        try:
            self._library.reconcile()
            actions: list[dict] = []
            for job in self._library.scan()["jobs"]:
                if job.get("pipeline") != "procedural":
                    continue
                action = self._reconcile_job(job["job_id"])
                if action is not None:
                    actions.append(action)
            return actions
        finally:
            if owns_admission:
                self._gate.finish(token)


__all__ = [
    "DEFAULT_OPERATION_TIMEOUT_SECONDS",
    "FASTEST_FRAME_DURATION_MS",
    "ProceduralGenerationCoordinator",
]
