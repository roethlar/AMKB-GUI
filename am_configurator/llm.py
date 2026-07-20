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

import base64
import binascii
import io
import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .ai_catalog import DEFAULT_MODELS, validate_model

if TYPE_CHECKING:  # pragma: no cover - typing only; Pillow is a runtime-optional dep
    from PIL import Image


# --- Pinned design constants -------------------------------------------------
#
# Fixed by design v3 (docs/design/llm-led-generator.md); do not re-derive here.

MAX_RENDERED_KEYFRAMES = 16  # hard ceiling on paid image renders per generation
MODEL_FRAME_CAPS = {"CB": 80, "80": 200, "ALICE": 186}  # per-model firmware caps
MAX_LLM_FRAMES = max(MODEL_FRAME_CAPS.values())  # global output-frame ceiling (200)
MAX_PROVIDER_RESPONSE = 25_000_000  # bounded read cap on any upstream body (bytes)
MAX_IMAGE_BYTES = 12_000_000  # decoded-image byte cap before Pillow open (bytes)
MAX_IMAGE_PIXELS = 4_000_000  # decoded-image pixel cap (width*height) before load()
LLM_TOTAL_BUDGET = 120.0  # monotonic deadline budget across both phases (seconds)
PER_CALL_TIMEOUT = 30.0  # hard ceiling on any single upstream call; the deadline caps it lower
MAX_CONCEPT_PROMPT_CHARS = 4000
MAX_CONCEPT_CANDIDATES = 8
MAX_CONCEPT_PLAN_STRING = 2000

# Firmware LED speed steps. Duplicated from ``server._LED_SPEEDS_MS`` so this
# module stays importable without ``server``; a drift-guard test keeps the two
# tuples identical.
LED_SPEEDS_MS = (255, 240, 224, 208, 192, 176, 160, 146, 132, 118, 100, 90, 76, 62, 48, 34)

# Pinned model IDs (verified against docs.x.ai 2026-07-20, current versions per
# user direction). Bumping these is a deliberate one-line change.
XAI_MODELS = {"interpreter": "grok-4.5", "renderer": "grok-imagine-image"}

# Pinned xAI endpoints (design v3). The interpreter posts structured output to
# the Responses API and the renderer posts one image request per keyframe to
# the Images API; bumping a host/path is a deliberate one-line change.
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
XAI_IMAGES_URL = "https://api.x.ai/v1/images/generations"

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


@dataclass(frozen=True)
class ProviderUsage:
    """Exact provider-reported response cost, or an explicit missing marker."""

    cost_in_usd_ticks: int | None
    reported: bool


MISSING_PROVIDER_USAGE = ProviderUsage(cost_in_usd_ticks=None, reported=False)


class ProviderError(Exception):
    """A typed provider failure carrying a stable ``code`` for HTTP mapping.

    ``code`` is one of :data:`PROVIDER_ERROR_CODES`. ``retry_after`` is set only
    for ``rate_limited`` (seconds parsed from an upstream ``Retry-After``).
    Messages must never contain an API key: callers redact before constructing.
    """

    def __init__(
        self,
        code: str,
        message: str,
        retry_after: int | None = None,
        usage: ProviderUsage = MISSING_PROVIDER_USAGE,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.usage = usage


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
class ConceptPlan:
    """Validated concept-planning output with exactly the requested candidates."""

    visual_brief: str
    candidate_prompts: tuple[str, ...]


@dataclass(frozen=True)
class ConceptPlanResult:
    plan: ConceptPlan
    usage: ProviderUsage


@dataclass(frozen=True)
class ImageMetadata:
    format: str
    mime_type: str
    width: int
    height: int
    revised_prompt: str | None


@dataclass(frozen=True)
class ConceptImageResult:
    original_bytes: bytes
    metadata: ImageMetadata
    image: Image.Image
    usage: ProviderUsage


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


def _concept_count(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_CONCEPT_CANDIDATES
    ):
        raise ProviderError(
            "config", f"concept candidate count must be an integer from 1 to {MAX_CONCEPT_CANDIDATES}"
        )
    return value


def _concept_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError("bad_response", f"concept field {field!r} must be a non-empty string")
    if len(value) > MAX_CONCEPT_PLAN_STRING:
        raise ProviderError(
            "bad_response",
            f"concept field {field!r} exceeds {MAX_CONCEPT_PLAN_STRING} characters",
        )
    return value


def concept_plan_from_json(data: object, candidate_count: object) -> ConceptPlan:
    """Strictly validate a concept plan independently of provider-side schema checks."""
    count = _concept_count(candidate_count)
    if not isinstance(data, dict):
        raise ProviderError("bad_response", "concept plan must be a JSON object")
    expected = {"visual_brief", "candidate_prompts"}
    if set(data) != expected:
        raise ProviderError("bad_response", "concept plan fields did not match the schema")

    visual_brief = _concept_string(data["visual_brief"], "visual_brief")
    raw_prompts = data["candidate_prompts"]
    if not isinstance(raw_prompts, list) or len(raw_prompts) != count:
        raise ProviderError(
            "bad_response", f"concept plan must contain exactly {count} candidate prompts"
        )
    prompts = tuple(
        _concept_string(prompt, "candidate_prompts") for prompt in raw_prompts
    )
    normalized = {prompt.strip().casefold() for prompt in prompts}
    if len(normalized) != count:
        raise ProviderError("bad_response", "concept candidate prompts must be unique")
    return ConceptPlan(visual_brief=visual_brief, candidate_prompts=prompts)


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


def _provider_usage(response: dict) -> ProviderUsage:
    """Read exact integer USD ticks without estimating or coercing provider data."""
    if "usage" not in response:
        return MISSING_PROVIDER_USAGE
    usage = response["usage"]
    if not isinstance(usage, dict):
        raise ProviderError("bad_response", "provider usage was not an object")
    if "cost_in_usd_ticks" not in usage:
        return MISSING_PROVIDER_USAGE
    ticks = usage["cost_in_usd_ticks"]
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 0:
        raise ProviderError(
            "bad_response",
            "provider cost_in_usd_ticks must be a nonnegative integer",
        )
    return ProviderUsage(cost_in_usd_ticks=ticks, reported=True)


def _provider_error_usage(error: urllib.error.HTTPError) -> ProviderUsage:
    """Best-effort exact usage from a bounded HTTP error body; never reclassify."""
    try:
        raw = error.read(MAX_PROVIDER_RESPONSE + 1)
    except Exception:
        return MISSING_PROVIDER_USAGE
    if not isinstance(raw, bytes) or len(raw) > MAX_PROVIDER_RESPONSE:
        return MISSING_PROVIDER_USAGE
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return MISSING_PROVIDER_USAGE
    if not isinstance(parsed, dict):
        return MISSING_PROVIDER_USAGE
    try:
        return _provider_usage(parsed)
    except ProviderError:
        return MISSING_PROVIDER_USAGE


def _call_provider(transport, url: str, payload: dict, api_key: str, deadline: float) -> dict:
    """Invoke an injected transport while preserving typed, redacted failures."""
    failure: ProviderError | None = None
    try:
        response = transport(url, payload, api_key, deadline)
    except ProviderError as exc:
        code = exc.code if exc.code in PROVIDER_ERROR_CODES else "unavailable"
        failure = ProviderError(
            code,
            _redact(str(exc), api_key),
            retry_after=exc.retry_after,
            usage=exc.usage,
        )
    except Exception as exc:
        failure = ProviderError(
            "unavailable",
            _redact(f"provider call failed: {exc}", api_key),
        )
    if failure is not None:
        raise failure from None
    if not isinstance(response, dict):
        raise ProviderError("bad_response", "provider response was not a JSON object")
    return response


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
        usage = _provider_error_usage(exc)
        _close_quietly(exc)
        if code in (401, 403):
            raise ProviderError(
                "auth",
                "provider rejected the API key; check the key in Settings",
                usage=usage,
            ) from exc
        if code == 429:
            raise ProviderError(
                "rate_limited",
                "provider rate limit reached; retry later",
                retry_after=retry_after,
                usage=usage,
            ) from exc
        if 500 <= code <= 599:
            raise ProviderError(
                "unavailable",
                f"provider is temporarily unavailable (HTTP {code})",
                usage=usage,
            ) from exc
        raise ProviderError(
            "bad_response",
            f"provider returned an unexpected status (HTTP {code})",
            usage=usage,
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


# --- Grok interpreter (prompt -> EffectPlan) ---------------------------------
#
# ``GrokInterpreter`` turns a natural-language prompt into a validated
# :class:`EffectPlan` via the xAI Responses API (``store: false`` + a strict
# JSON schema; ``additionalProperties: false``). Structured output is never
# trusted on the provider's word: the parsed object is re-validated by
# :func:`plan_from_json`, so a schema-valid-but-inconsistent plan fails as
# ``bad_response`` *before* any paid image render. The ``transport`` is
# injectable (default :func:`_xai_request`) so request building, output
# extraction, refusal handling, and the Refine flow are tested without network.

_INTERPRETER_SYSTEM_INTRO = (
    "You are an LED effect designer for a mechanical keyboard's addressable "
    "RGB LEDs."
)


class GrokInterpreter:
    """xAI Responses interpreter: a prompt becomes a validated :class:`EffectPlan`.

    ``transport`` is a callable ``(url, payload, api_key, deadline) -> dict``
    matching :func:`_xai_request` (the production default). Tests inject a fake
    so no real request is ever made.
    """

    def __init__(self, api_key: str, transport=None) -> None:
        self._api_key = api_key
        self._transport = transport if transport is not None else _xai_request

    def interpret(
        self,
        prompt: str,
        spec: RasterSpec,
        deadline: float,
        previous_plan: EffectPlan | None = None,
    ) -> EffectPlan:
        """Request a structured plan for ``prompt`` and return a validated
        :class:`EffectPlan`.

        ``previous_plan`` (the Refine flow) embeds the prior plan's summary so
        the model produces a delta rather than starting over. Provider errors
        propagate as typed :class:`ProviderError`; a refusal maps to
        ``moderation`` and any inconsistent plan to ``bad_response``.
        """
        payload = {
            "model": XAI_MODELS["interpreter"],
            "store": False,
            "input": [
                {"role": "system", "content": self._system_prompt(spec)},
                {"role": "user", "content": self._user_prompt(prompt, previous_plan)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "effect_plan",
                    "strict": True,
                    "schema": self._plan_schema(spec),
                }
            },
        }
        response = self._transport(XAI_RESPONSES_URL, payload, self._api_key, deadline)
        text = self._extract_output_text(response)
        try:
            data = json.loads(text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProviderError(
                "bad_response",
                _redact(f"interpreter output was not valid JSON: {exc}", self._api_key),
            ) from exc
        return plan_from_json(data, spec)

    # -- request building --------------------------------------------------

    @staticmethod
    def _system_prompt(spec: RasterSpec) -> str:
        speed_steps = ", ".join(str(step) for step in LED_SPEEDS_MS)
        lines = [
            _INTERPRETER_SYSTEM_INTRO,
            f"The animation is rendered onto a {spec.width}x{spec.height} pixel "
            f"raster (model {spec.model}, target {spec.target}).",
            "Return an EffectPlan describing a short looping animation.",
            f"Use at most {spec.max_frames} output frames: this cap is a limit, "
            "not a goal — use the fewest frames that clearly express the effect.",
            "The keyframe_prompts are the images actually rendered (at most "
            f"{MAX_RENDERED_KEYFRAMES}); the remaining frames are interpolated "
            "locally, so list only the distinct poses the motion needs.",
            "frame_ms must be exactly one of these firmware speed steps, in "
            f"milliseconds: {speed_steps}.",
            "Keep the content within a wide horizontal band so it survives the "
            "center-crop down to the raster.",
        ]
        if spec.mapped_positions:
            positions = ", ".join(f"({x}, {y})" for x, y in spec.mapped_positions)
            lines.append(
                "Only the following raster positions are visible on this "
                f"target; place all content there: {positions}."
            )
        return "\n".join(lines)

    def _user_prompt(self, prompt: str, previous_plan: EffectPlan | None) -> str:
        if previous_plan is None:
            return prompt
        return (
            "Refine the previous effect described below rather than starting "
            "over.\n"
            f"{self._summarize_plan(previous_plan)}\n\n"
            f"New request: {prompt}"
        )

    @staticmethod
    def _summarize_plan(plan: EffectPlan) -> str:
        prompts = "; ".join(plan.keyframe_prompts)
        return (
            "Previous plan — "
            f"subject: {plan.subject}; palette: {plan.palette}; "
            f"motion: {plan.motion}; frame_count: {plan.frame_count}; "
            f"frame_ms: {plan.frame_ms}; tween: {plan.tween}; "
            f"keyframe_prompts: {prompts}"
        )

    @staticmethod
    def _plan_schema(spec: RasterSpec) -> dict:
        max_prompts = min(spec.max_frames, MAX_RENDERED_KEYFRAMES)
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "subject": {"type": "string"},
                "palette": {"type": "string"},
                "motion": {"type": "string"},
                "frame_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": spec.max_frames,
                },
                "frame_ms": {"type": "integer", "enum": list(LED_SPEEDS_MS)},
                "keyframe_prompts": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": max_prompts,
                    "items": {"type": "string"},
                },
                "tween": {"type": "string", "enum": ["crossfade", "step"]},
                "notes": {"type": "string"},
            },
            "required": [
                "subject",
                "palette",
                "motion",
                "frame_count",
                "frame_ms",
                "keyframe_prompts",
                "tween",
                "notes",
            ],
        }

    # -- response extraction ----------------------------------------------

    def _extract_output_text(self, response: dict) -> str:
        """Pull the assistant's ``output_text`` out of a Responses envelope.

        A ``refusal`` content part maps to :class:`ProviderError` ``moderation``;
        a missing/empty text body maps to ``bad_response``. URL and other
        unexpected content parts are ignored — this path never fetches anything.
        """
        output = response.get("output")
        if not isinstance(output, list):
            raise ProviderError(
                "bad_response", "interpreter response missing an output list"
            )
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type == "refusal":
                    raise ProviderError(
                        "moderation",
                        "the provider declined this prompt; try rephrasing it",
                    )
                if part_type == "output_text":
                    piece = part.get("text")
                    if isinstance(piece, str):
                        texts.append(piece)
        if not texts:
            raise ProviderError(
                "bad_response", "interpreter response contained no output text"
            )
        return "".join(texts)


INTERPRETERS["grok"] = GrokInterpreter


def _curated_model(role: str, model: object) -> str:
    try:
        return validate_model(role, model)
    except ValueError as exc:
        raise ProviderError("config", f"selected {role} model is not available") from exc


class GrokConceptPlanner:
    """Create a strict, exactly-N concept plan through the xAI Responses API."""

    def __init__(self, api_key: str, model: str | None = None, transport=None) -> None:
        self._api_key = api_key
        self._model = _curated_model(
            "interpreter", DEFAULT_MODELS["interpreter"] if model is None else model
        )
        self._transport = transport if transport is not None else _xai_request

    def plan(
        self, prompt: object, candidate_count: object, deadline: float
    ) -> ConceptPlanResult:
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > MAX_CONCEPT_PROMPT_CHARS
        ):
            raise ProviderError(
                "config",
                f"concept prompt must be a non-empty string of at most {MAX_CONCEPT_PROMPT_CHARS} characters",
            )
        count = _concept_count(candidate_count)
        payload = {
            "model": self._model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a lighting concept designer. Return exactly "
                        f"{count} unique, meaningfully distinct, closely related minor "
                        "variations of one shared visual brief. Keep the central subject, "
                        "composition, palette, and mood coherent; vary only minor "
                        "execution details. Do not propose unrelated alternative concepts. "
                        "Each prompt must describe a complete standalone image, use a "
                        "wide 20:9 composition, and keep important content in the safe "
                        "central horizontal band."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "concept_plan",
                    "strict": True,
                    "schema": self._schema(count),
                }
            },
        }
        response = _call_provider(
            self._transport, XAI_RESPONSES_URL, payload, self._api_key, deadline
        )
        usage = _provider_usage(response)
        try:
            text = self._extract_output_text(response)
            parsed = json.loads(text)
            plan = concept_plan_from_json(parsed, count)
        except ProviderError as exc:
            raise ProviderError(
                exc.code,
                _redact(str(exc), self._api_key),
                retry_after=exc.retry_after,
                usage=usage,
            ) from exc
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProviderError(
                "bad_response",
                _redact(f"concept planner output was not valid JSON: {exc}", self._api_key),
                usage=usage,
            ) from exc
        return ConceptPlanResult(plan=plan, usage=usage)

    @staticmethod
    def _schema(count: int) -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "visual_brief": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_CONCEPT_PLAN_STRING,
                },
                "candidate_prompts": {
                    "type": "array",
                    "minItems": count,
                    "maxItems": count,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_CONCEPT_PLAN_STRING,
                    },
                },
            },
            "required": ["visual_brief", "candidate_prompts"],
        }

    @staticmethod
    def _extract_output_text(response: dict) -> str:
        output = response.get("output")
        if not isinstance(output, list):
            raise ProviderError("bad_response", "concept response missing an output list")
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "refusal":
                    raise ProviderError(
                        "moderation",
                        "the provider declined this prompt; try rephrasing it",
                    )
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        if not texts:
            raise ProviderError("bad_response", "concept response contained no output text")
        return "".join(texts)


# --- Grok Imagine renderer (EffectPlan -> RenderedFrames) --------------------
#
# ``GrokImagineRenderer`` turns each of ``plan.keyframe_prompts`` into one
# decoded RGB image via the xAI Images API (``response_format: "b64_json"``,
# ``n: 1``), issuing exactly one request per keyframe sequentially under the
# shared monotonic deadline. Paid image POSTs are never auto-retried, and the
# URL response mode is never requested nor fetched, so the SSRF / redirect /
# oversized-download class is removed entirely. Every response runs the full
# defense-in-depth validation chain before the image is trusted:
#
#   shape (data/b64_json) -> base64 decode -> byte-size cap (MAX_IMAGE_BYTES)
#   -> Pillow open with a PNG/JPEG format whitelist -> pixel cap
#   (MAX_IMAGE_PIXELS) -> full load()
#
# Any deviation raises ``ProviderError('bad_response', ...)``. On a partial
# failure (keyframe k of K) the exception propagates and every image rendered so
# far is discarded — nothing partial ever leaks. A supplied ``cancelled``
# predicate is polled between keyframes so a cancel is honored cleanly without a
# mid-download abort. Pillow is imported lazily inside the decode path so this
# module stays importable in a Pillow-less core install.


class Cancelled(Exception):
    """Raised when a supplied cancel predicate reports the generation was cancelled.

    Distinct from :class:`ProviderError`: cancellation is a user action, not a
    provider failure, so it carries no error code and no HTTP mapping. The job
    layer turns it into a cancelled job state and discards any partial work.
    """


def _validated_image_result(
    response: dict,
    api_key: str,
    usage: ProviderUsage,
    *,
    require_exactly_one: bool,
) -> ConceptImageResult:
    """Validate inline image bytes and retain both the original and RGB decode."""
    from PIL import Image, UnidentifiedImageError  # lazy optional dependency

    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise ProviderError("bad_response", "image response missing a data list", usage=usage)
    if require_exactly_one and len(data) != 1:
        raise ProviderError(
            "bad_response", "image response must contain exactly one result", usage=usage
        )
    entry = data[0]
    if not isinstance(entry, dict):
        raise ProviderError(
            "bad_response", "image response entry was not an object", usage=usage
        )
    b64 = entry.get("b64_json")
    if not isinstance(b64, str) or not b64:
        raise ProviderError(
            "bad_response",
            "image response carried no inline base64 image (b64_json)",
            usage=usage,
        )
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProviderError(
            "bad_response",
            _redact(f"image payload was not valid base64: {exc}", api_key),
            usage=usage,
        ) from exc
    if not raw:
        raise ProviderError(
            "bad_response", "image payload decoded to zero bytes", usage=usage
        )
    if len(raw) > MAX_IMAGE_BYTES:
        raise ProviderError(
            "bad_response",
            f"decoded image exceeded the {MAX_IMAGE_BYTES}-byte cap",
            usage=usage,
        )

    try:
        source = Image.open(io.BytesIO(raw))
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProviderError(
            "bad_response",
            _redact(f"image payload could not be opened: {exc}", api_key),
            usage=usage,
        ) from exc

    image_format = source.format
    if image_format not in ("PNG", "JPEG"):
        source.close()
        raise ProviderError(
            "bad_response",
            f"image format {image_format!r} is not PNG or JPEG",
            usage=usage,
        )
    width, height = source.size
    if width * height > MAX_IMAGE_PIXELS:
        source.close()
        raise ProviderError(
            "bad_response",
            f"decoded image {width}x{height} exceeds the {MAX_IMAGE_PIXELS}-pixel cap",
            usage=usage,
        )
    try:
        source.load()
        rgb = source.convert("RGB")
    except (OSError, ValueError) as exc:
        source.close()
        raise ProviderError(
            "bad_response",
            _redact(f"image payload could not be decoded: {exc}", api_key),
            usage=usage,
        ) from exc
    finally:
        source.close()

    mime_type = "image/png" if image_format == "PNG" else "image/jpeg"
    declared_mime = entry.get("mime_type")
    if declared_mime is not None and declared_mime != mime_type:
        rgb.close()
        raise ProviderError(
            "bad_response", "image MIME metadata did not match its bytes", usage=usage
        )
    revised_prompt = entry.get("revised_prompt")
    if revised_prompt is not None and not isinstance(revised_prompt, str):
        rgb.close()
        raise ProviderError(
            "bad_response", "image revised_prompt metadata was not a string", usage=usage
        )
    if revised_prompt is not None:
        revised_prompt = _redact(revised_prompt, api_key)
    return ConceptImageResult(
        original_bytes=raw,
        metadata=ImageMetadata(
            format=image_format,
            mime_type=mime_type,
            width=width,
            height=height,
            revised_prompt=revised_prompt,
        ),
        image=rgb,
        usage=usage,
    )


class GrokConceptImageProvider:
    """Generate and validate one bankable concept still per paid Images POST."""

    def __init__(self, api_key: str, model: str | None = None, transport=None) -> None:
        self._api_key = api_key
        self._model = _curated_model(
            "concept", DEFAULT_MODELS["concept"] if model is None else model
        )
        self._transport = transport if transport is not None else _xai_request

    def generate_one(self, prompt: object, deadline: float) -> ConceptImageResult:
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > MAX_CONCEPT_PROMPT_CHARS
        ):
            raise ProviderError(
                "config",
                f"concept image prompt must be a non-empty string of at most {MAX_CONCEPT_PROMPT_CHARS} characters",
            )
        payload = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "aspect_ratio": "20:9",
            "resolution": "1k",
            "response_format": "b64_json",
        }
        response = _call_provider(
            self._transport, XAI_IMAGES_URL, payload, self._api_key, deadline
        )
        usage = _provider_usage(response)
        try:
            return _validated_image_result(
                response, self._api_key, usage, require_exactly_one=True
            )
        except ProviderError as exc:
            raise ProviderError(
                exc.code,
                _redact(str(exc), self._api_key),
                retry_after=exc.retry_after,
                usage=usage,
            ) from exc

    def generate_candidates(
        self,
        plan: ConceptPlan,
        deadline: float,
        *,
        on_candidate=None,
        cancelled=None,
    ) -> tuple[ConceptImageResult, ...]:
        if not isinstance(plan, ConceptPlan) or not isinstance(
            plan.candidate_prompts, tuple
        ):
            raise ProviderError("config", "a validated ConceptPlan is required")
        try:
            plan = concept_plan_from_json(
                {
                    "visual_brief": plan.visual_brief,
                    "candidate_prompts": list(plan.candidate_prompts),
                },
                len(plan.candidate_prompts),
            )
        except ProviderError as exc:
            raise ProviderError("config", "concept candidate batch is invalid") from exc
        results: list[ConceptImageResult] = []
        for index, prompt in enumerate(plan.candidate_prompts):
            if cancelled is not None and cancelled():
                raise Cancelled("concept generation cancelled between image calls")
            result = self.generate_one(prompt, deadline)
            if on_candidate is not None:
                on_candidate(index, prompt, result)
            results.append(result)
        return tuple(results)


# Shared style prefix applied to every keyframe prompt for cross-frame
# coherence and to steer content into a wide horizontal band (design §Renderer,
# "Aspect fit"): the existing center-crop pipeline reduces the rendered image to
# the short, wide LED raster, so content outside a central strip is lost.
_IMAGE_STYLE_PREFIX = (
    "Compose as a wide horizontal band on a solid black background; keep all "
    "content within a short, centered horizontal strip so it survives a "
    "center-crop down to a short, wide LED raster."
)


class GrokImagineRenderer:
    """xAI Images renderer: each keyframe prompt becomes one decoded RGB image.

    ``transport`` is a callable ``(url, payload, api_key, deadline) -> dict``
    matching :func:`_xai_request` (the production default). Tests inject a fake
    so no real request is ever made.
    """

    def __init__(self, api_key: str, transport=None) -> None:
        self._api_key = api_key
        self._transport = transport if transport is not None else _xai_request

    def render(
        self,
        plan: EffectPlan,
        spec: RasterSpec,
        deadline: float,
        cancelled=None,
    ) -> RenderedFrames:
        """Render every prompt in ``plan.keyframe_prompts`` to a decoded RGB image.

        One sequential upstream call per prompt (``1 + K`` provider calls per
        generation together with the interpret call), each validated through the
        full chain before it is trusted. ``cancelled`` — a zero-argument
        predicate — is polled *before* each keyframe; a truthy result raises
        :class:`Cancelled` and discards any images rendered so far. Provider or
        validation failure propagates as a typed :class:`ProviderError`,
        likewise discarding partial work; the per-call deadline is enforced by
        the transport. ``spec`` is part of the ``Renderer`` protocol and reserved
        for raster-aware prompting; it is not sent upstream today.
        """
        images: list[Image.Image] = []
        for prompt in plan.keyframe_prompts:
            if cancelled is not None and cancelled():
                raise Cancelled("generation cancelled before all keyframes rendered")
            response = self._transport(
                XAI_IMAGES_URL,
                self._image_payload(plan, prompt),
                self._api_key,
                deadline,
            )
            images.append(self._decode_image(response))
        return RenderedFrames(images=tuple(images))

    # -- request building --------------------------------------------------

    def _image_payload(self, plan: EffectPlan, keyframe_prompt: str) -> dict:
        prompt = (
            f"{plan.subject}. Palette: {plan.palette}. {_IMAGE_STYLE_PREFIX} "
            f"This frame: {keyframe_prompt}"
        )
        return {
            "model": XAI_MODELS["renderer"],
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }

    # -- response validation ----------------------------------------------

    def _extract_b64(self, response: dict) -> str:
        """Pull the inline base64 image out of an Images envelope.

        A missing ``data`` list, empty list, non-object entry, or an entry that
        carries no ``b64_json`` string (e.g. a ``url``-only entry) all map to
        ``bad_response`` — URL mode is never requested and never fetched.
        """
        data = response.get("data")
        if not isinstance(data, list) or not data:
            raise ProviderError("bad_response", "image response missing a data list")
        entry = data[0]
        if not isinstance(entry, dict):
            raise ProviderError("bad_response", "image response entry was not an object")
        b64 = entry.get("b64_json")
        if not isinstance(b64, str) or not b64:
            raise ProviderError(
                "bad_response",
                "image response carried no inline base64 image (b64_json)",
            )
        return b64

    def _decode_image(self, response: dict) -> Image.Image:
        """Validate and decode one image response into an RGB Pillow image.

        Runs the full chain (shape → base64 → byte cap → format whitelist →
        pixel cap → load) and returns an RGB image. Pillow is imported here so
        the module imports without Pillow in a core install.
        """
        return _validated_image_result(
            response,
            self._api_key,
            MISSING_PROVIDER_USAGE,
            require_exactly_one=False,
        ).image


RENDERERS["grok"] = GrokImagineRenderer


# --- Tween expansion + generation orchestrator -------------------------------
#
# ``expand_keyframes`` is the pure, deterministic interpolation from K rendered
# keyframes to the plan's ``frame_count`` output frames. ``generate_effect``
# wires the two provider phases together under a single monotonic deadline and
# is the one place the whole spend ceiling is enforced — even against a rogue or
# faked interpreter, so at most ``1 + MAX_RENDERED_KEYFRAMES`` provider calls and
# ``MAX_LLM_FRAMES`` output frames are ever produced. ``frames_to_led_tracks`` is
# imported lazily inside ``generate_effect`` to avoid a ``server`` <-> ``llm``
# import cycle, and Pillow stays a lazy import on the render/tween path so this
# module remains importable in a Pillow-less core install.


def expand_keyframes(images, frame_count: int, tween: str) -> list:
    """Expand K rendered keyframes into ``frame_count`` output frames.

    The keyframes are placed at evenly spaced positions on the output timeline
    and the gaps between them are filled per ``tween``:

    - ``"step"`` holds the nearest keyframe at or to the left of each output
      position (a hard cut on each keyframe boundary);
    - ``"crossfade"`` blends the two bracketing keyframes with Pillow
      :func:`PIL.Image.blend` at the fractional position between them.

    ``K == 1`` repeats the single keyframe for every output frame, and
    ``K == frame_count`` is the identity — the exact input images are returned
    unchanged. Callers must pass same-size RGB images:
    :func:`generate_effect` normalizes rendered keyframes to the generation
    raster first, which is what makes the crossfade blend well-defined even when
    the renderer returns differently sized images. Pure and deterministic — no
    I/O, no provider state.
    """
    frames = list(images)
    count = len(frames)
    if count == 0:
        raise ValueError("expand_keyframes requires at least one keyframe image.")
    if frame_count < 1:
        raise ValueError("frame_count must be at least 1.")
    if count == frame_count:
        return frames  # identity: every output frame is a rendered keyframe
    if frame_count == 1:
        return [frames[0]]
    if tween not in ("crossfade", "step"):
        raise ValueError("tween must be 'crossfade' or 'step'.")

    span = count - 1  # keyframe-index distance spanned by the output timeline
    blend = None
    out: list = []
    for index in range(frame_count):
        position = index * span / (frame_count - 1)  # in [0, span]
        left = int(position)  # floor; position is non-negative
        if left >= span:
            out.append(frames[span])  # final (or beyond) keyframe
            continue
        if tween == "step":
            out.append(frames[left])
            continue
        frac = position - left
        if frac == 0.0:
            out.append(frames[left])
            continue
        if blend is None:
            from PIL import Image  # lazy: Pillow only needed for the crossfade blend

            blend = Image.blend
        out.append(blend(frames[left], frames[left + 1], frac))
    return out


def _fit_cover(image, width: int, height: int):
    """Center-crop ``image`` to the target aspect, then resize to ``width`` x ``height``.

    Mirrors the aspect-fit (crop-cover) that :func:`server.frames_to_led_tracks`
    applies per frame. It is used to normalize each rendered keyframe to the
    generation raster before tweening, so the crossfade blend operates on
    same-size images regardless of what dimensions the renderer returned. Pillow
    is imported lazily so this module stays importable without it.
    """
    from PIL import Image  # lazy: Pillow only needed on the render/tween path

    source_ratio = image.width / image.height
    target_ratio = width / height
    fitted = image
    if source_ratio > target_ratio:
        crop_width = max(1, round(image.height * target_ratio))
        left = (image.width - crop_width) // 2
        fitted = image.crop((left, 0, left + crop_width, image.height))
    elif source_ratio < target_ratio:
        crop_height = max(1, round(image.width / target_ratio))
        top = (image.height - crop_height) // 2
        fitted = image.crop((0, top, image.width, top + crop_height))
    if fitted.size != (width, height):
        fitted = fitted.resize((width, height), Image.Resampling.BOX)
    return fitted


def generate_effect(
    prompt: str,
    spec: RasterSpec,
    targets,
    product_id: str,
    api_key: str,
    factories: dict,
    progress=None,
    cancelled=None,
) -> dict:
    """Run the full text-to-LED pipeline and return an ``/api/led/gif``-shaped dict.

    Wires interpreter -> renderer -> tween -> frame mapping under one monotonic
    deadline (``time.monotonic() + LLM_TOTAL_BUDGET``) shared verbatim by both
    provider phases. ``factories`` maps ``"interpreter"`` and ``"renderer"`` to
    callables ``(api_key) -> provider`` (the registry classes in production,
    injected fakes under test).

    ``progress`` is an optional ``(phase: str) -> None`` callback that reports
    ``"interpreting"``, then ``"rendering k/K"`` once per keyframe, then
    ``"tweening"`` and ``"mapping"``, in order. ``cancelled`` is an optional
    zero-argument predicate polled between phases and — via the renderer's
    between-keyframe hook — between keyframes; a truthy result raises
    :class:`Cancelled` and discards any partial work.

    The spend ceiling is enforced here against the *returned* plan, independent
    of the interpreter's own validation, so a rogue or faked interpreter can
    never exceed the budget: at most ``1 + MAX_RENDERED_KEYFRAMES`` provider
    calls and ``MAX_LLM_FRAMES`` output frames, and never more keyframes than
    output frames. Provider failures propagate as typed :class:`ProviderError`;
    nothing partial ever leaks.

    Generated-path values for the GIF-shape fields follow from feeding exactly
    ``frame_count`` frames each of duration ``frame_ms``: ``source_frames`` and
    ``decoded_frames`` equal ``frame_count``, ``source_duration_ms`` equals
    ``frame_count * frame_ms``, and ``timing_resampled`` is ``False``.
    ``duration_ms`` stays the per-frame firmware speed (``frame_ms``), the value
    the UI consumes as ``speed_ms``. The result additionally carries ``"plan"``
    and ``"usage"`` summaries for the UI.
    """

    def _emit(phase: str) -> None:
        if progress is not None:
            progress(phase)

    def _check_cancel() -> None:
        if cancelled is not None and cancelled():
            raise Cancelled("generation cancelled")

    deadline = time.monotonic() + LLM_TOTAL_BUDGET
    interpreter = factories["interpreter"](api_key)
    renderer = factories["renderer"](api_key)

    _check_cancel()
    _emit("interpreting")
    plan = interpreter.interpret(prompt, spec, deadline)

    # Spend ceiling, re-checked against the plan the interpreter actually
    # returned. The real GrokInterpreter already validates via plan_from_json,
    # but generate_effect must hold the line for *any* provider so tabs, direct
    # calls, or a misbehaving model can never amplify cost past the ceiling.
    keyframes = len(plan.keyframe_prompts)
    if not (1 <= keyframes <= MAX_RENDERED_KEYFRAMES):
        raise ProviderError(
            "bad_response",
            f"plan requested {keyframes} rendered keyframes outside "
            f"1..{MAX_RENDERED_KEYFRAMES}",
        )
    if not (1 <= plan.frame_count <= spec.max_frames) or plan.frame_count > MAX_LLM_FRAMES:
        raise ProviderError(
            "bad_response",
            f"plan frame_count {plan.frame_count} exceeds the generation budget "
            f"(model cap {spec.max_frames}, global cap {MAX_LLM_FRAMES})",
        )
    if keyframes > plan.frame_count:
        raise ProviderError(
            "bad_response",
            f"plan has more rendered keyframes ({keyframes}) than output frames "
            f"({plan.frame_count})",
        )

    _check_cancel()

    # The renderer polls this once before each keyframe (Task 6 contract): use it
    # both to report per-keyframe progress and to forward the user's cancel flag.
    rendered = 0

    def _render_gate() -> bool:
        nonlocal rendered
        rendered += 1
        _emit(f"rendering {rendered}/{keyframes}")
        return cancelled is not None and cancelled()

    frames = renderer.render(plan, spec, deadline, cancelled=_render_gate)

    _emit("tweening")
    normalized = [
        _fit_cover(image, spec.width, spec.height) for image in frames.images
    ]
    expanded = expand_keyframes(normalized, plan.frame_count, plan.tween)

    _emit("mapping")
    from am_configurator.server import frames_to_led_tracks  # lazy: avoid import cycle

    durations = [plan.frame_ms] * plan.frame_count
    result = frames_to_led_tracks(expanded, durations, targets, "box", product_id)

    result["plan"] = {
        "subject": plan.subject,
        "frame_count": plan.frame_count,
        "rendered_keyframes": keyframes,
        "tween": plan.tween,
        "frame_ms": plan.frame_ms,
    }
    result["usage"] = {
        "provider_calls": 1 + keyframes,
        "rendered_keyframes": keyframes,
        "output_frames": plan.frame_count,
    }
    return result
