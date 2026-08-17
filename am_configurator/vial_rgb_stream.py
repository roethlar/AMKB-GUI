"""Bounded volatile VialRGB preview scheduling and lifecycle ownership.

This module knows nothing about HID packets.  A transport supplies four narrow
callbacks: enter direct mode, send one sequential pixel chunk, restore the
captured mode, and (through :class:`StreamManager`) execute one prepared target.
No callback is retried.  In particular there is no SAVE callback in this API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import math
import re
import secrets
import threading
import time
from typing import Any, Callable, Protocol, Sequence


MAX_PIXELS = 1024
MAX_FRAMES = 1024
MAX_DURATION_MS = 30_000
MAX_CHUNK_PIXELS = 9
REPORTS_PER_SECOND = 30
_RGB = re.compile(r"^#[0-9A-F]{6}$")
_TERMINAL_STATES = frozenset({"completed", "stopped", "error", "cancelled"})


class StreamError(RuntimeError):
    """A volatile preview cannot be prepared or executed safely."""


class StreamTokenError(StreamError):
    """The opaque preview token is absent or no longer current."""


class StreamBusyError(StreamError):
    """One preview worker already owns the volatile stream slot."""


class StreamConfirmationError(StreamError):
    """The exact volatile-preview phrase was not supplied."""


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def wait(self, event: threading.Event, timeout: float) -> bool: ...


class SystemClock:
    """Real monotonic clock with interruptible waits."""

    @staticmethod
    def monotonic() -> float:
        return time.monotonic()

    @staticmethod
    def wait(event: threading.Event, timeout: float) -> bool:
        return event.wait(max(0.0, timeout))


@dataclass(frozen=True)
class StreamPlan:
    frames: tuple[tuple[tuple[int, int, int], ...], ...]
    frame_ms: int
    maximum_duration_ms: int
    pixel_count: int
    max_chunk_pixels: int = MAX_CHUNK_PIXELS
    reports_per_second: int = REPORTS_PER_SECOND


@dataclass(frozen=True)
class StreamOutcome:
    state: str
    frames_presented: int = 0
    frames_skipped: int = 0
    reports_sent: int = 0
    reports_skipped: int = 0
    elapsed_ms: int = 0
    restoration: str = "not_attempted"
    error: str | None = None
    restoration_error: str | None = None


def _rounded_byte(value: float) -> int:
    return max(0, min(255, math.floor(value + 0.5)))


def rgb_to_hsv8(color: str, *, brightness: int = 100) -> tuple[int, int, int]:
    """Convert canonical ``#RRGGBB`` to deterministic VialRGB HSV bytes."""

    if not isinstance(color, str) or not _RGB.fullmatch(color):
        raise ValueError("A stream color must be uppercase #RRGGBB.")
    if isinstance(brightness, bool) or not isinstance(brightness, int):
        raise ValueError("Animation brightness must be an integer.")
    if not 0 <= brightness <= 100:
        raise ValueError("Animation brightness must be in 0..100.")
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    maximum = max(red, green, blue)
    minimum = min(red, green, blue)
    delta = maximum - minimum
    value = _rounded_byte(maximum * brightness / 100)
    if maximum == 0 or delta == 0:
        return (0, 0, value)
    saturation = _rounded_byte(delta * 255 / maximum)
    if maximum == red:
        hue_degrees = (60 * (green - blue) / delta) % 360
    elif maximum == green:
        hue_degrees = 60 * (blue - red) / delta + 120
    else:
        hue_degrees = 60 * (red - green) / delta + 240
    hue = _rounded_byte(hue_degrees * 255 / 360) % 256
    return (hue, saturation, value)


def build_plan(
    frames: Sequence[Sequence[str]],
    *,
    frame_ms: int,
    brightness: int = 100,
    maximum_duration_ms: int = MAX_DURATION_MS,
    max_chunk_pixels: int = MAX_CHUNK_PIXELS,
    reports_per_second: int = REPORTS_PER_SECOND,
) -> StreamPlan:
    """Validate canonical animation frames and freeze their HSV8 projection."""

    if not isinstance(frames, (list, tuple)) or not 1 <= len(frames) <= MAX_FRAMES:
        raise ValueError(f"A stream must contain 1..{MAX_FRAMES} frames.")
    if isinstance(frame_ms, bool) or not isinstance(frame_ms, int) or not 1 <= frame_ms <= 65_535:
        raise ValueError("Stream frame time must be an integer in 1..65535 ms.")
    if (
        isinstance(maximum_duration_ms, bool)
        or not isinstance(maximum_duration_ms, int)
        or not 1 <= maximum_duration_ms <= MAX_DURATION_MS
    ):
        raise ValueError(
            f"Stream duration must be an integer in 1..{MAX_DURATION_MS} ms."
        )
    if (
        isinstance(max_chunk_pixels, bool)
        or not isinstance(max_chunk_pixels, int)
        or not 1 <= max_chunk_pixels <= MAX_CHUNK_PIXELS
    ):
        raise ValueError(f"Stream chunks must contain 1..{MAX_CHUNK_PIXELS} pixels.")
    if (
        isinstance(reports_per_second, bool)
        or not isinstance(reports_per_second, int)
        or not 1 <= reports_per_second <= REPORTS_PER_SECOND
    ):
        raise ValueError(
            f"Stream rate must be an integer in 1..{REPORTS_PER_SECOND} reports per second."
        )
    pixel_count = len(frames[0])
    if not 1 <= pixel_count <= MAX_PIXELS:
        raise ValueError(f"A stream frame must contain 1..{MAX_PIXELS} pixels.")
    converted: list[tuple[tuple[int, int, int], ...]] = []
    for index, frame in enumerate(frames):
        if not isinstance(frame, (list, tuple)) or len(frame) != pixel_count:
            raise ValueError(f"Stream frame {index + 1} has the wrong pixel count.")
        converted.append(tuple(rgb_to_hsv8(color, brightness=brightness) for color in frame))
    return StreamPlan(
        frames=tuple(converted),
        frame_ms=frame_ms,
        maximum_duration_ms=maximum_duration_ms,
        pixel_count=pixel_count,
        max_chunk_pixels=max_chunk_pixels,
        reports_per_second=reports_per_second,
    )


def _chunks(
    frame: tuple[tuple[int, int, int], ...], size: int
) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    return tuple(frame[index : index + size] for index in range(0, len(frame), size))


def run_stream(
    plan: StreamPlan,
    *,
    stop_event: threading.Event,
    enter_direct: Callable[[], None],
    send_chunk: Callable[[int, tuple[tuple[int, int, int], ...]], None],
    restore: Callable[[], None],
    clock: Clock | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> StreamOutcome:
    """Run a bounded looping preview and attempt restoration exactly once."""

    active_clock = clock or SystemClock()
    started = active_clock.monotonic()
    ends_at = started + plan.maximum_duration_ms / 1000
    frame_seconds = plan.frame_ms / 1000
    report_seconds = 1 / plan.reports_per_second
    next_report_at = started
    ordinal = 0
    frames_presented = 0
    frames_skipped = 0
    reports_sent = 0
    reports_skipped = 0
    previous: tuple[tuple[tuple[int, int, int], ...], ...] | None = None
    state = "completed"
    error_message: str | None = None
    restoration = "not_attempted"
    restoration_error: str | None = None
    restoration_required = False

    def publish() -> None:
        if progress is not None:
            progress(
                {
                    "state": "running",
                    "frames_presented": frames_presented,
                    "frames_skipped": frames_skipped,
                    "reports_sent": reports_sent,
                    "reports_skipped": reports_skipped,
                    "elapsed_ms": max(
                        0, round((active_clock.monotonic() - started) * 1000)
                    ),
                }
            )

    try:
        restoration_required = True
        enter_direct()
        while not stop_event.is_set():
            now = active_clock.monotonic()
            if now >= ends_at:
                break
            if ordinal:
                scheduled = started + ordinal * frame_seconds
                if scheduled >= ends_at:
                    break
                if now < scheduled:
                    active_clock.wait(stop_event, min(scheduled, ends_at) - now)
                    if stop_event.is_set():
                        state = "stopped"
                        break
                    now = active_clock.monotonic()
                due = max(ordinal, math.floor((now - started) / frame_seconds))
                if due > ordinal:
                    frames_skipped += due - ordinal
                    ordinal = due
                if active_clock.monotonic() >= ends_at:
                    break
            frame = plan.frames[ordinal % len(plan.frames)]
            chunks = _chunks(frame, plan.max_chunk_pixels)
            interrupted = False
            for chunk_index, chunk in enumerate(chunks):
                if stop_event.is_set():
                    state = "stopped"
                    interrupted = True
                    break
                if previous is not None and previous[chunk_index] == chunk:
                    reports_skipped += 1
                    continue
                now = active_clock.monotonic()
                if now < next_report_at:
                    active_clock.wait(stop_event, next_report_at - now)
                    if stop_event.is_set():
                        state = "stopped"
                        interrupted = True
                        break
                send_chunk(chunk_index * plan.max_chunk_pixels, chunk)
                reports_sent += 1
                next_report_at = max(next_report_at, active_clock.monotonic()) + report_seconds
            if interrupted:
                break
            previous = chunks
            frames_presented += 1
            ordinal += 1
            publish()
        if stop_event.is_set() and state == "completed":
            state = "stopped"
    except BaseException as exc:  # noqa: BLE001 - outcome owns worker failure
        state = "error"
        error_message = str(exc) or exc.__class__.__name__
    finally:
        if restoration_required:
            try:
                restore()
                restoration = "restored"
            except BaseException as exc:  # noqa: BLE001 - report, never retry
                restoration = "failed"
                restoration_error = str(exc) or exc.__class__.__name__
                state = "error"

    return StreamOutcome(
        state=state,
        frames_presented=frames_presented,
        frames_skipped=frames_skipped,
        reports_sent=reports_sent,
        reports_skipped=reports_skipped,
        elapsed_ms=max(0, round((active_clock.monotonic() - started) * 1000)),
        restoration=restoration,
        error=error_message,
        restoration_error=restoration_error,
    )


class StreamManager:
    """Own exactly one opaque preflight token and at most one worker thread."""

    def __init__(
        self,
        *,
        runner: Callable[
            [Any, threading.Event, Callable[[dict[str, Any]], None]], StreamOutcome
        ],
        token_factory: Callable[[], str] | None = None,
        join_timeout: float = 5.0,
    ) -> None:
        self._runner = runner
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._join_timeout = join_timeout
        self._lock = threading.Lock()
        self._token: str | None = None
        self._prepared: Any = None
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._status: dict[str, Any] = {"state": "idle"}

    def _matches(self, token: object) -> bool:
        return (
            isinstance(token, str)
            and isinstance(self._token, str)
            and secrets.compare_digest(token, self._token)
        )

    def _require(self, token: object) -> None:
        if not self._matches(token):
            raise StreamTokenError("The volatile preview token is absent or stale.")

    @property
    def active(self) -> bool:
        with self._lock:
            return self._status.get("state") in {"starting", "running", "stopping"}

    def preflight(self, prepared: Any) -> str:
        confirmation = getattr(prepared, "confirmation", None)
        if not isinstance(confirmation, str) or not confirmation:
            raise StreamError("A prepared stream needs an exact confirmation phrase.")
        with self._lock:
            if self._status.get("state") in {"starting", "running", "stopping"}:
                raise StreamBusyError("A volatile keyboard preview is already active.")
            token = self._token_factory()
            if not isinstance(token, str) or len(token) < 16:
                raise StreamError("The volatile preview token factory failed.")
            self._token = token
            self._prepared = prepared
            self._stop_event = None
            self._thread = None
            self._status = {
                "state": "ready",
                "subject": str(getattr(prepared, "subject", "VialRGB preview")),
                "frames_presented": 0,
                "frames_skipped": 0,
                "reports_sent": 0,
                "reports_skipped": 0,
                "elapsed_ms": 0,
                "restoration": "not_attempted",
                "error": None,
                "restoration_error": None,
            }
            return token

    def status(self, token: object) -> dict[str, Any]:
        with self._lock:
            self._require(token)
            return copy.deepcopy(self._status)

    def _progress(self, token: str, update: dict[str, Any]) -> None:
        with self._lock:
            if not self._matches(token) or self._status.get("state") not in {
                "starting",
                "running",
                "stopping",
            }:
                return
            self._status.update(copy.deepcopy(update))
            if self._status.get("state") != "stopping":
                self._status["state"] = "running"

    def _work(self, token: str, prepared: Any, stop_event: threading.Event) -> None:
        with self._lock:
            if not self._matches(token):
                return
            self._status["state"] = "running"
        try:
            outcome = self._runner(
                prepared,
                stop_event,
                lambda update: self._progress(token, update),
            )
            terminal = asdict(outcome)
        except BaseException as exc:  # noqa: BLE001 - worker status owns failure
            terminal = {
                "state": "error",
                "error": str(exc) or exc.__class__.__name__,
                "restoration": "not_attempted",
            }
        with self._lock:
            if self._matches(token):
                self._status.update(terminal)

    def start(self, token: object, confirmation: object) -> dict[str, Any]:
        with self._lock:
            self._require(token)
            if self._status.get("state") != "ready":
                raise StreamBusyError("This volatile preview token was already used.")
            expected = getattr(self._prepared, "confirmation", "")
            if not isinstance(confirmation, str) or not secrets.compare_digest(
                confirmation, expected
            ):
                raise StreamConfirmationError(
                    f"Type {expected} exactly to start volatile preview."
                )
            stop_event = threading.Event()
            prepared = self._prepared
            current_token = self._token
            if current_token is None:
                raise StreamTokenError("The volatile preview token is absent.")
            self._stop_event = stop_event
            self._status["state"] = "starting"
            thread = threading.Thread(
                target=self._work,
                args=(current_token, prepared, stop_event),
                name="openkeeb-vialrgb-preview",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return copy.deepcopy(self._status)

    def stop(self, token: object, *, wait: bool = True) -> dict[str, Any]:
        with self._lock:
            self._require(token)
            state = self._status.get("state")
            if state == "ready":
                self._status["state"] = "cancelled"
                return copy.deepcopy(self._status)
            if state in _TERMINAL_STATES:
                return copy.deepcopy(self._status)
            self._status["state"] = "stopping"
            stop_event = self._stop_event
            thread = self._thread
            if stop_event is not None:
                stop_event.set()
        if wait and thread is not None:
            thread.join(timeout=self._join_timeout)
        return self.status(token)

    def close(self) -> None:
        with self._lock:
            stop_event = self._stop_event
            thread = self._thread
            if stop_event is not None:
                stop_event.set()
        if thread is not None:
            thread.join(timeout=self._join_timeout)
