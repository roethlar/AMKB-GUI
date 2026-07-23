"""Shared generation admission, errors, and canonical target validation."""

from __future__ import annotations

import threading
from typing import Callable, Mapping

from . import device_mapping


class GenerationError(RuntimeError):
    """Base class for safe coordinator failures before a worker owns the job."""


class GenerationValidationError(GenerationError):
    """A request was invalid and no provider call was made."""


class GenerationBusyError(GenerationError):
    """Another paid or local generation operation currently owns the process."""


class GenerationNotActiveError(GenerationError):
    """Cancellation targeted a job that does not own the active operation."""


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
    if not isinstance(family, str) or family not in device_mapping.MODEL_FRAME_CAPS:
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
    expected_cap = device_mapping.MODEL_FRAME_CAPS[family]
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
        spec, resolved_targets = device_mapping.generation_spec(
            product_id,
            list(targets),
            None,
        )
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
    return {
        "family": family,
        "product_id": product_id,
        "raster": {"width": width, "height": height},
        "targets": resolved_targets,
        "frame_cap": expected_cap,
    }


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
PROCESS_OPERATION_GATE = _PROCESS_OPERATION_GATE


__all__ = [
    "GenerationBusyError",
    "GenerationError",
    "GenerationNotActiveError",
    "GenerationValidationError",
    "OperationGate",
    "PROCESS_OPERATION_GATE",
    "canonical_target_snapshot",
]
