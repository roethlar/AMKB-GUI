"""LLM-backed LED effect generation: provider types, constants, and validation.

This is the provider layer for the natural-language LED effect generator
(design: ``docs/design/llm-led-generator.md``). It is stdlib-only and performs
no network I/O at import time.

This module establishes the shared data model (``RasterSpec`` / ``EffectPlan``
/ ``RenderedFrames``), the typed :class:`ProviderError`, the pinned design
constants, and the independent :func:`plan_from_json` validator that vets a
provider's structured output *before* any paid image render. The xAI transport
and the concrete interpreter/renderer implementations arrive in later tasks and
register themselves into ``INTERPRETERS`` / ``RENDERERS``.
"""

from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only; Pillow is a runtime-optional dep
    from PIL import Image


# --- Pinned design constants -------------------------------------------------
#
# Fixed by design v3 (docs/design/llm-led-generator.md); do not re-derive here.

MAX_RENDERED_KEYFRAMES = 16  # hard ceiling on paid image renders per generation
MODEL_FRAME_CAPS = {"CB": 80, "80": 200, "ALICE": 186}  # per-model firmware caps
MAX_PROVIDER_RESPONSE = 25_000_000  # bounded read cap on any upstream body (bytes)
MAX_IMAGE_BYTES = 12_000_000  # decoded-image size cap before Pillow open (bytes)
LLM_TOTAL_BUDGET = 120.0  # monotonic deadline budget across both phases (seconds)
PER_CALL_TIMEOUT = 30.0  # hard ceiling on any single upstream call; the deadline caps it lower

# Firmware LED speed steps. Duplicated from ``server._LED_SPEEDS_MS`` so this
# module stays importable without ``server``; a drift-guard test keeps the two
# tuples identical.
LED_SPEEDS_MS = (255, 240, 224, 208, 192, 176, 160, 146, 132, 118, 100, 90, 76, 62, 48, 34)

# Pinned model IDs (verified against docs.x.ai 2026-07-20, current versions per
# user direction). Bumping these is a deliberate one-line change.
XAI_MODELS = {"interpreter": "grok-4.5", "renderer": "grok-imagine-image"}

# Canonical provider / key-provider names. ``store.py`` keeps its own copies of
# these allowlists because it must stay stdlib-core-only and cannot import this
# module; a drift-guard test keeps the two in sync. The registries below are
# keyed by these same names once populated.
INTERPRETER_PROVIDERS: tuple[str, ...] = ("grok",)
RENDERER_PROVIDERS: tuple[str, ...] = ("grok",)
KEY_PROVIDERS: tuple[str, ...] = ("xai",)

# Provider registries, keyed by the canonical names above. Populated in later
# tasks with the concrete Interpreter/Renderer implementations.
INTERPRETERS: dict[str, object] = {}
RENDERERS: dict[str, object] = {}

# Stable ProviderError codes (design §Typed errors), each mapped to a local
# HTTP status by the server. Listed here as the contract of record.
PROVIDER_ERROR_CODES = (
    "config",
    "auth",
    "rate_limited",
    "timeout",
    "offline",
    "moderation",
    "bad_response",
    "unavailable",
)

_MAX_PLAN_STRING = 2000  # per-field character cap on interpreter-supplied text


class ProviderError(Exception):
    """A typed provider failure carrying a stable ``code`` for HTTP mapping.

    ``code`` is one of :data:`PROVIDER_ERROR_CODES`. ``retry_after`` is set only
    for ``rate_limited`` (seconds parsed from an upstream ``Retry-After``).
    Messages must never contain an API key: callers redact before constructing.
    """

    def __init__(self, code: str, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class RasterSpec:
    """Per-generation raster description, built server-side from ``_GIF_LAYOUTS``.

    One ``RasterSpec`` covers a single generation. ``target`` is the primary
    semantic target and ``extra_targets`` are same-raster copies driven from it
    (e.g. the Relic per-key/spotlight pair, the AFA body-light copy).
    ``mapped_positions`` is a sparse visibility mask for targets that only light
    a subset of positions. ``max_frames`` is the per-model firmware cap and is a
    ceiling, never a target.
    """

    model: str
    target: str
    extra_targets: tuple[str, ...]
    width: int
    height: int
    mapped_positions: tuple[tuple[int, int], ...] | None
    output_len: int
    max_frames: int


@dataclass(frozen=True)
class EffectPlan:
    """Validated interpreter output describing the effect to render and expand.

    ``frame_count`` is the number of OUTPUT frames the effect plays;
    ``keyframe_prompts`` are the (paid) image renders that are expanded locally
    to ``frame_count`` via ``tween``. Frame durations come from ``frame_ms``,
    which must be one of :data:`LED_SPEEDS_MS`.
    """

    subject: str
    palette: str
    motion: str
    frame_count: int
    frame_ms: int
    keyframe_prompts: tuple[str, ...]
    tween: str
    notes: str


@dataclass(frozen=True)
class RenderedFrames:
    """Rendered keyframes; ``len(images)`` equals ``len(plan.keyframe_prompts)``.

    Durations are not carried here — they derive from the validated
    :class:`EffectPlan`, not from the renderer.
    """

    images: tuple[Image.Image, ...]


def _require(data: dict, field: str) -> object:
    if field not in data:
        raise ProviderError("bad_response", f"plan missing required field {field!r}")
    return data[field]


def _require_str(data: dict, field: str) -> str:
    value = _require(data, field)
    if not isinstance(value, str):
        raise ProviderError("bad_response", f"plan field {field!r} must be a string")
    if len(value) > _MAX_PLAN_STRING:
        raise ProviderError(
            "bad_response",
            f"plan field {field!r} exceeds {_MAX_PLAN_STRING} characters",
        )
    return value


def _require_int(data: dict, field: str) -> int:
    value = _require(data, field)
    # bool is an int subclass; reject it so JSON true/false is not read as 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProviderError("bad_response", f"plan field {field!r} must be an integer")
    return value


def plan_from_json(data: object, spec: RasterSpec) -> EffectPlan:
    """Validate an interpreter's structured output into an :class:`EffectPlan`.

    Independent of any provider's own claims (design §EffectPlan validation):
    checks required fields and types, per-field string caps, ``frame_ms``
    against the firmware speed steps, ``1 <= frame_count <= spec.max_frames``,
    ``1 <= len(keyframe_prompts) <= min(frame_count, MAX_RENDERED_KEYFRAMES)``,
    a legal ``tween``, and non-empty prompt strings. Any violation raises
    ``ProviderError('bad_response', ...)`` so a schema-valid-but-inconsistent
    plan fails before any paid image render.
    """
    if not isinstance(data, dict):
        raise ProviderError("bad_response", "plan must be a JSON object")

    subject = _require_str(data, "subject")
    palette = _require_str(data, "palette")
    motion = _require_str(data, "motion")
    notes = _require_str(data, "notes")
    frame_count = _require_int(data, "frame_count")
    frame_ms = _require_int(data, "frame_ms")
    tween = _require_str(data, "tween")

    if not (1 <= frame_count <= spec.max_frames):
        raise ProviderError(
            "bad_response", f"frame_count {frame_count} outside 1..{spec.max_frames}"
        )
    if frame_ms not in LED_SPEEDS_MS:
        raise ProviderError(
            "bad_response", f"frame_ms {frame_ms} is not a firmware speed step"
        )
    if tween not in ("crossfade", "step"):
        raise ProviderError("bad_response", f"tween {tween!r} is not 'crossfade' or 'step'")

    prompts_raw = _require(data, "keyframe_prompts")
    if not isinstance(prompts_raw, (list, tuple)):
        raise ProviderError("bad_response", "keyframe_prompts must be a list")
    prompts: list[str] = []
    for entry in prompts_raw:
        if not isinstance(entry, str):
            raise ProviderError(
                "bad_response", "keyframe_prompts entries must be strings"
            )
        if not entry:
            raise ProviderError(
                "bad_response", "keyframe_prompts entries must be non-empty"
            )
        if len(entry) > _MAX_PLAN_STRING:
            raise ProviderError(
                "bad_response",
                f"a keyframe prompt exceeds {_MAX_PLAN_STRING} characters",
            )
        prompts.append(entry)

    ceiling = min(frame_count, MAX_RENDERED_KEYFRAMES)
    if not (1 <= len(prompts) <= ceiling):
        raise ProviderError(
            "bad_response",
            f"keyframe_prompts count {len(prompts)} outside 1..{ceiling}",
        )

    return EffectPlan(
        subject=subject,
        palette=palette,
        motion=motion,
        frame_count=frame_count,
        frame_ms=frame_ms,
        keyframe_prompts=tuple(prompts),
        tween=tween,
        notes=notes,
    )


# --- xAI HTTP transport ------------------------------------------------------
#
# ``_xai_request`` is the single choke point through which every xAI call
# flows. It POSTs a JSON payload, enforces the monotonic deadline and a bounded
# response read, and maps every failure to a typed :class:`ProviderError`
# (design §Typed errors). It never retries — paid image POSTs have no upstream
# idempotency guarantee, so a single invocation is always exactly one call.
# Secrets are scrubbed from every error message before it is raised.


def _redact(text: str, secret: str | None) -> str:
    """Scrub an API key out of a message before it can reach an error or log."""
    if secret and secret in text:
        text = text.replace(secret, "<redacted>")
    return text


def _parse_retry_after(value: str | None) -> int | None:
    """Parse a ``Retry-After`` header into whole seconds, or ``None`` if absent
    or not an integer-seconds value (the form xAI emits)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    return None


def _close_quietly(response: object) -> None:
    """Close a response/HTTPError if it exposes ``close``, ignoring OS errors so
    cleanup never masks the error we are already handling."""
    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except OSError:
            pass


def _default_opener():
    """Build the real urllib opener over a default-verifying TLS context.

    Only used when ``opener=None`` in production; tests always inject a fake
    opener, so this path is never exercised under test.
    """
    context = ssl.create_default_context()
    director = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
    return director.open


def _xai_request(
    url: str,
    payload: dict,
    api_key: str,
    deadline: float,
    opener=None,
) -> dict:
    """POST ``payload`` as JSON to ``url`` and return the parsed JSON object.

    ``deadline`` is an absolute :func:`time.monotonic` value shared across both
    generation phases. If it has already passed, this raises
    ``ProviderError('timeout')`` *without* contacting the network. Otherwise the
    per-call socket timeout is ``min(remaining, PER_CALL_TIMEOUT)``.

    ``opener`` is a callable ``opener(request, timeout=...)`` matching the real
    urllib opener; when ``None`` the real opener is built via
    :func:`_default_opener`. The opener is invoked exactly once — there is no
    auto-retry.

    Every failure is mapped to a typed :class:`ProviderError`
    (``auth`` / ``rate_limited`` / ``unavailable`` / ``bad_response`` /
    ``offline`` / ``timeout``) and the API key is redacted from every message.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderError(
            "timeout", "provider deadline exceeded before the request started"
        )

    if opener is None:
        opener = _default_opener()

    timeout = min(remaining, PER_CALL_TIMEOUT)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        response = opener(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        code = exc.code
        retry_after = _parse_retry_after(exc.headers.get("Retry-After"))
        _close_quietly(exc)
        if code in (401, 403):
            raise ProviderError(
                "auth", "provider rejected the API key; check the key in Settings"
            ) from exc
        if code == 429:
            raise ProviderError(
                "rate_limited",
                "provider rate limit reached; retry later",
                retry_after=retry_after,
            ) from exc
        if 500 <= code <= 599:
            raise ProviderError(
                "unavailable", f"provider is temporarily unavailable (HTTP {code})"
            ) from exc
        raise ProviderError(
            "bad_response", f"provider returned an unexpected status (HTTP {code})"
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise ProviderError(
                "timeout", _redact(f"provider request timed out: {exc}", api_key)
            ) from exc
        raise ProviderError(
            "offline", _redact(f"could not reach the provider: {exc}", api_key)
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderError(
            "timeout", _redact(f"provider request timed out: {exc}", api_key)
        ) from exc
    except (ssl.SSLError, OSError) as exc:
        raise ProviderError(
            "offline", _redact(f"could not reach the provider: {exc}", api_key)
        ) from exc

    try:
        raw = response.read(MAX_PROVIDER_RESPONSE + 1)
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderError(
            "timeout", _redact(f"provider response read timed out: {exc}", api_key)
        ) from exc
    except (ssl.SSLError, OSError) as exc:
        raise ProviderError(
            "offline", _redact(f"provider response read failed: {exc}", api_key)
        ) from exc
    finally:
        _close_quietly(response)

    if len(raw) > MAX_PROVIDER_RESPONSE:
        raise ProviderError(
            "bad_response",
            f"provider response exceeded the {MAX_PROVIDER_RESPONSE}-byte cap",
        )

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProviderError(
            "bad_response", _redact(f"provider response was not valid JSON: {exc}", api_key)
        ) from exc

    if not isinstance(parsed, dict):
        raise ProviderError("bad_response", "provider response was not a JSON object")

    return parsed
