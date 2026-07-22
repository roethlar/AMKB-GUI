"""Shared provider types, validation, and xAI transports for lighting assets.

The active procedural generator and the historical durable asset library share
the types and bounded transports in this module. Importing it performs no
network I/O.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .ai_catalog import DEFAULT_MODELS, validate_model

if TYPE_CHECKING:  # pragma: no cover - typing only; Pillow is a runtime-optional dep
    from PIL import Image


# --- Pinned design constants -------------------------------------------------
#
# Fixed by design v3 (docs/design/llm-led-generator.md); do not re-derive here.

MODEL_FRAME_CAPS = {"CB": 80, "80": 200, "ALICE": 186}  # per-model firmware caps
MAX_PROVIDER_RESPONSE = 25_000_000  # bounded read cap on any upstream body (bytes)
MAX_IMAGE_BYTES = 12_000_000  # decoded-image byte cap before Pillow open (bytes)
MAX_IMAGE_PIXELS = 4_000_000  # decoded-image pixel cap (width*height) before load()
PER_CALL_TIMEOUT = 30.0  # hard ceiling on any single upstream call; the deadline caps it lower
MAX_CONCEPT_PROMPT_CHARS = 4000
MAX_CONCEPT_CANDIDATES = 8
MAX_CONCEPT_PLAN_STRING = 2000
MAX_VIDEO_PLAN_STRING = 2000
MAX_VIDEO_MOTION_CHARS = 2000
VIDEO_LOOP_MODES = ("smooth", "none", "ping_pong")
_VIDEO_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,199}", re.ASCII)

# Firmware LED speed steps. Duplicated from ``server._LED_SPEEDS_MS`` so this
# module stays importable without ``server``; a drift-guard test keeps the two
# tuples identical.
LED_SPEEDS_MS = (255, 240, 224, 208, 192, 176, 160, 146, 132, 118, 100, 90, 76, 62, 48, 34)

# Pinned xAI endpoints. Bumping a host/path is a deliberate one-line change.
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
XAI_IMAGES_URL = "https://api.x.ai/v1/images/generations"
XAI_VIDEO_GENERATIONS_URL = "https://api.x.ai/v1/videos/generations"
XAI_VIDEO_STATUS_URL = "https://api.x.ai/v1/videos/{request_id}"

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
class ConceptPlan:
    """Validated concept-planning output with exactly the requested candidates."""

    visual_brief: str
    candidate_prompts: tuple[str, ...]


@dataclass(frozen=True)
class ConceptPlanResult:
    plan: ConceptPlan
    usage: ProviderUsage


@dataclass(frozen=True)
class VideoAnimationPlan:
    """Validated one-second animation instructions anchored to a selected still."""

    subject_lock: str
    style_lock: str
    video_prompt: str


@dataclass(frozen=True)
class VideoAnimationPlanResult:
    plan: VideoAnimationPlan
    usage: ProviderUsage


@dataclass(frozen=True)
class VideoSubmission:
    """Accepted paid video submission; ``pending`` is the only local start state."""

    request_id: str
    status: str
    usage: ProviderUsage


@dataclass(frozen=True)
class VideoStatus:
    """One status observation; an ephemeral signed URL exists only when done."""

    request_id: str
    status: str
    usage: ProviderUsage
    video_url: str | None = field(default=None, repr=False)
    duration: int | None = None


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


def _video_plan_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError(
            "bad_response", f"video plan field {field!r} must be a non-empty string"
        )
    if len(value) > MAX_VIDEO_PLAN_STRING:
        raise ProviderError(
            "bad_response",
            f"video plan field {field!r} exceeds {MAX_VIDEO_PLAN_STRING} characters",
        )
    return value


def video_animation_plan_from_json(data: object) -> VideoAnimationPlan:
    """Strictly validate the three-field animation plan returned by Responses."""
    if not isinstance(data, dict):
        raise ProviderError("bad_response", "video animation plan must be a JSON object")
    expected = {"subject_lock", "style_lock", "video_prompt"}
    if set(data) != expected:
        raise ProviderError(
            "bad_response", "video animation plan fields did not match the schema"
        )
    return VideoAnimationPlan(
        subject_lock=_video_plan_string(data["subject_lock"], "subject_lock"),
        style_lock=_video_plan_string(data["style_lock"], "style_lock"),
        video_prompt=_video_plan_string(data["video_prompt"], "video_prompt"),
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


def _call_poll_provider(transport, url: str, api_key: str, deadline: float) -> dict:
    """Invoke the independent status-GET seam with typed, redacted failures."""
    failure: ProviderError | None = None
    try:
        response = transport(url, api_key, deadline)
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
            _redact(f"provider status call failed: {exc}", api_key),
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


def _xai_get_request(
    url: str,
    api_key: str,
    deadline: float,
    opener=None,
) -> dict:
    """GET one xAI JSON response under the shared deadline, without retrying."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderError(
            "timeout", "provider deadline exceeded before the request started"
        )

    if opener is None:
        opener = _default_opener()

    timeout = min(remaining, PER_CALL_TIMEOUT)
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {api_key}"},
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


def _curated_model(role: str, model: object) -> str:
    try:
        return validate_model(role, model)
    except ValueError as exc:
        raise ProviderError("config", f"selected {role} model is not available") from exc


def _concept_led_constraints(spec: RasterSpec) -> str:
    """Return the non-optional image constraints for an LED-sized concept."""
    _video_raster_context(spec)
    paired_targets = ", ".join(spec.extra_targets) if spec.extra_targets else "none"
    lines = [
        "Design an addressable keyboard LED source texture, not a cinematic "
        "still, landscape, or photographed scene.",
        f"The image will be cover-downsampled to {spec.width}x{spec.height}; "
        f"{spec.output_len} LED samples drive the primary {spec.target} target, "
        f"and the same texture also drives these paired targets: {paired_targets}.",
        "Translate the requested subject into a flat 2D emissive motif on a "
        "dark ground. Use broad high-contrast color fields, bold silhouettes, "
        "and trails at least one final raster cell thick; prefer features two "
        "to four cells wide.",
        "Do not depict a keyboard or device. Do not add horizons, scenery, "
        "water, clouds, reflections, realistic depth, perspective, lens effects, "
        "fine texture, tiny stars, text, borders, or photographic detail.",
        "Every important shape and color change must remain legible after the "
        "tiny raster reduction. Treat semantic nouns as symbolic light patterns, "
        "not literal environments.",
    ]
    if spec.mapped_positions:
        positions = ", ".join(f"({x},{y})" for x, y in spec.mapped_positions)
        lines.append(
            "Only these final raster coordinates emit light; concentrate the "
            f"motif on them and leave other cells dark: {positions}."
        )
    return " ".join(lines)


def _steered_concept_prompt(prompt: str, spec: RasterSpec) -> str:
    """Make device constraints survive even when the interpreter drifts."""
    return (
        f"Creative motif: {prompt}\n\n"
        "NON-NEGOTIABLE LED OUTPUT: "
        f"{_concept_led_constraints(spec)}"
    )


class GrokConceptPlanner:
    """Create a strict, exactly-N concept plan through the xAI Responses API."""

    def __init__(self, api_key: str, model: str | None = None, transport=None) -> None:
        self._api_key = api_key
        self._model = _curated_model(
            "interpreter", DEFAULT_MODELS["interpreter"] if model is None else model
        )
        self._transport = transport if transport is not None else _xai_request

    def plan(
        self,
        prompt: object,
        candidate_count: object,
        deadline: float,
        *,
        spec: RasterSpec | None = None,
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
        led_constraints = _concept_led_constraints(spec) if spec is not None else None
        instruction = (
            "You are a lighting concept designer. Return exactly "
            f"{count} unique, meaningfully distinct, closely related minor "
            "variations of one shared visual brief. Keep the central subject, "
            "composition, palette, and mood coherent; vary only minor "
            "execution details. Do not propose unrelated alternative concepts. "
            "Each prompt must describe a complete standalone image, use a "
            "wide 20:9 composition, and keep important content in the safe "
            "central horizontal band."
        )
        if led_constraints is not None:
            instruction = f"{instruction}\n\n{led_constraints}"
        payload = {
            "model": self._model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": instruction,
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
            if spec is not None:
                plan = ConceptPlan(
                    visual_brief=plan.visual_brief,
                    candidate_prompts=tuple(
                        _steered_concept_prompt(candidate, spec)
                        for candidate in plan.candidate_prompts
                    ),
                )
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


# --- Video planning and asynchronous generation -----------------------------


def _selected_image_data_uri(original_bytes: object, mime_type: object) -> str:
    """Validate selected original PNG/JPEG bytes and return their exact data URI."""
    from PIL import Image, UnidentifiedImageError

    expected_format = {"image/png": "PNG", "image/jpeg": "JPEG"}.get(mime_type)
    if expected_format is None:
        raise ProviderError("config", "selected still must be a PNG or JPEG image")
    if not isinstance(original_bytes, bytes) or not original_bytes:
        raise ProviderError("config", "selected still bytes are missing or invalid")
    if len(original_bytes) > MAX_IMAGE_BYTES:
        raise ProviderError(
            "config", f"selected still exceeds the {MAX_IMAGE_BYTES}-byte cap"
        )

    source = None
    try:
        source = Image.open(io.BytesIO(original_bytes))
        if source.format != expected_format:
            raise ProviderError(
                "config", "selected still MIME type does not match its image bytes"
            )
        width, height = source.size
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            raise ProviderError(
                "config", f"selected still exceeds the {MAX_IMAGE_PIXELS}-pixel cap"
            )
        source.load()
    except ProviderError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProviderError("config", "selected still is not a valid PNG or JPEG") from exc
    finally:
        if source is not None:
            source.close()

    encoded = base64.b64encode(original_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def prepare_led_video_source(
    image_bytes: object,
    mime_type: object,
    spec: object,
) -> bytes:
    """Pixel-reduce a selected concept before it reaches image-to-video.

    The provider still receives a normal full-size PNG, but its information
    budget already matches the device raster. This prevents it from inventing
    motion around photographic detail that the keyboard will discard.
    """
    _video_raster_context(spec)
    _selected_image_data_uri(image_bytes, mime_type)
    if not isinstance(spec, RasterSpec) or not isinstance(image_bytes, bytes):
        raise ProviderError("config", "selected LED source inputs are invalid")

    from PIL import Image, ImageOps, UnidentifiedImageError

    source = None
    try:
        source = Image.open(io.BytesIO(image_bytes))
        source.load()
        rgb = source.convert("RGB")
        width, height = rgb.size
        coarse_width = min(width, spec.width)
        coarse_height = min(
            height,
            max(min(spec.height, height), round(coarse_width * height / width)),
        )
        coarse = ImageOps.fit(
            rgb,
            (coarse_width, coarse_height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        if spec.mapped_positions:
            masked = Image.new("RGB", coarse.size, (0, 0, 0))
            visible_height = min(coarse_height, spec.height)
            top = max(0, (coarse_height - visible_height) // 2)
            for x, y in spec.mapped_positions:
                source_x = min(
                    coarse_width - 1,
                    round(x * (coarse_width - 1) / max(1, spec.width - 1)),
                )
                source_y = min(
                    coarse_height - 1,
                    top
                    + round(y * (visible_height - 1) / max(1, spec.height - 1)),
                )
                masked.putpixel(
                    (source_x, source_y), coarse.getpixel((source_x, source_y))
                )
            coarse = masked
        prepared = coarse.resize((width, height), Image.Resampling.NEAREST)
        output = io.BytesIO()
        prepared.save(output, format="PNG", optimize=False)
        payload = output.getvalue()
        if not payload or len(payload) > MAX_IMAGE_BYTES:
            raise ProviderError("config", "prepared LED source exceeds the image byte cap")
        return payload
    except ProviderError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProviderError("config", "selected still could not be prepared for LEDs") from exc
    finally:
        if source is not None:
            source.close()


def _video_raster_context(spec: object) -> str:
    if not isinstance(spec, RasterSpec):
        raise ProviderError("config", "validated device geometry is required")
    if not isinstance(spec.model, str) or not spec.model:
        raise ProviderError("config", "device model geometry is invalid")
    if not isinstance(spec.target, str) or not spec.target:
        raise ProviderError("config", "device target geometry is invalid")
    if not isinstance(spec.extra_targets, tuple) or any(
        not isinstance(target, str) or not target for target in spec.extra_targets
    ):
        raise ProviderError("config", "device extra-target geometry is invalid")
    for value in (spec.width, spec.height, spec.output_len, spec.max_frames):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ProviderError("config", "device raster geometry is invalid")
    if spec.mapped_positions is not None:
        if not isinstance(spec.mapped_positions, tuple):
            raise ProviderError("config", "device mapped-position geometry is invalid")
        for position in spec.mapped_positions:
            if (
                not isinstance(position, tuple)
                or len(position) != 2
                or any(isinstance(value, bool) or not isinstance(value, int) for value in position)
                or not 0 <= position[0] < spec.width
                or not 0 <= position[1] < spec.height
            ):
                raise ProviderError("config", "device mapped-position geometry is invalid")

    extra = ",".join(spec.extra_targets) if spec.extra_targets else "none"
    mapped = len(spec.mapped_positions) if spec.mapped_positions is not None else "all"
    return (
        f"model={spec.model}; target={spec.target}; extra_targets={extra}; "
        f"raster={spec.width}x{spec.height}; output_len={spec.output_len}; "
        f"max_frames={spec.max_frames}; mapped_positions={mapped}"
    )


def _steered_video_prompt(
    creative_prompt: str,
    spec: RasterSpec,
    loop_mode: str,
) -> str:
    """Bind a planner's creative motion to the non-negotiable LED contract."""
    _video_raster_context(spec)
    loop_instruction = {
        "smooth": (
            "Use one gentle periodic motion cycle whose phase returns naturally "
            "to its starting state; reserve the ending for a very short local blend."
        ),
        "none": (
            "There is no transition padding, so complete one closed cycle and "
            "make the last state meet the first without a cut."
        ),
        "ping_pong": (
            "Use reversible bounded motion that remains convincing when the sampled "
            "frames play forward and then backward; nothing may enter or leave frame."
        ),
    }.get(loop_mode)
    if loop_instruction is None:
        raise ProviderError("config", "video loop mode is invalid")
    constraints = (
        "NON-NEGOTIABLE KEYBOARD LED LOOP: Generate a functional addressable-keyboard "
        "LED loop, not conventional video. The full frame is a flat 2D emission "
        "texture; do not depict a keyboard, device, photographed scene, landscape, "
        "horizon, or physical environment. Treat the supplied still only as a palette "
        "and symbolic light motif. "
        f"Every frame will be cover-downsampled to {spec.width}x{spec.height} and only "
        f"{spec.output_len} primary samples survive. Use broad high-contrast luminous "
        "fields, bold silhouettes, and trails at least one final raster cell thick. "
        "Keep the frame coordinates, composition, and camera perfectly fixed: no pan, "
        "tilt, zoom, roll, parallax, depth motion, reframing, cut, focus pull, shake, "
        "object reveal, or new element. Motion is limited to local 2D brightness, hue, "
        "and shape-phase changes. Complete exactly one closed cycle in one second; the "
        "first and final frames must match in subject position, composition, shape, "
        f"color, and brightness. {loop_instruction}"
    )
    prefix = "Creative motion motif: "
    separator = "\n\n"
    available = MAX_VIDEO_PLAN_STRING - len(prefix) - len(separator) - len(constraints)
    if available <= 1:
        raise ProviderError("config", "video steering prompt exceeds its safe bound")
    creative = creative_prompt.strip()
    if len(creative) > available:
        creative = creative[: available - 1].rstrip() + "…"
    return f"{prefix}{creative}{separator}{constraints}"


class GrokVideoPlanner:
    """Create a strict animation plan with the selected still as image context."""

    def __init__(self, api_key: str, model: str | None = None, transport=None) -> None:
        self._api_key = api_key
        self._model = _curated_model(
            "interpreter", DEFAULT_MODELS["interpreter"] if model is None else model
        )
        self._transport = transport if transport is not None else _xai_request

    def plan(
        self,
        original_prompt: object,
        motion: object,
        selected_image_bytes: object,
        selected_image_mime_type: object,
        spec: object,
        loop_mode: object,
        deadline: float,
    ) -> VideoAnimationPlanResult:
        if (
            not isinstance(original_prompt, str)
            or not original_prompt.strip()
            or len(original_prompt) > MAX_CONCEPT_PROMPT_CHARS
        ):
            raise ProviderError(
                "config",
                f"original prompt must be a non-empty string of at most {MAX_CONCEPT_PROMPT_CHARS} characters",
            )
        if motion is not None and (
            not isinstance(motion, str) or len(motion) > MAX_VIDEO_MOTION_CHARS
        ):
            raise ProviderError(
                "config",
                f"motion guidance must be omitted or at most {MAX_VIDEO_MOTION_CHARS} characters",
            )
        if loop_mode not in VIDEO_LOOP_MODES:
            raise ProviderError("config", "video loop mode is invalid")

        geometry = _video_raster_context(spec)
        data_uri = _selected_image_data_uri(
            selected_image_bytes, selected_image_mime_type
        )
        motion_text = motion if isinstance(motion, str) and motion.strip() else "none supplied"
        context = (
            f"Original prompt: {original_prompt}\n"
            f"Motion guidance: {motion_text}\n"
            f"Device geometry: {geometry}\n"
            f"Loop mode: {loop_mode}\n"
            "Duration: exactly one second.\n"
            "Camera: locked camera with no pan, tilt, zoom, roll, cut, or reframing.\n"
            "Output purpose: a functional LED loop, not a shot, scene, or miniature movie.\n"
            "Raster behavior: the full frame is a 2D light-emission texture that must "
            "remain legible after the stated tiny-raster reduction."
        )
        payload = {
            "model": self._model,
            "store": False,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You plan a one-second addressable-keyboard LED texture animation "
                        "from the supplied selected still. This is a functional cyclic light "
                        "map, never a conventional video scene. Preserve the still's symbolic "
                        "subject motif and palette, but flatten it into broad emissive 2D "
                        "forms that survive the stated raster. The camera and composition are "
                        "locked. Return a subject lock, a style lock, and exactly one concrete "
                        "standalone video prompt. Describe one complete closed motion cycle "
                        "whose final state matches its start and respect the requested loop "
                        "mode. Do not introduce scenery, physical depth, new subjects, cuts, "
                        "camera movement, text, borders, or watermarks."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": context},
                        {"type": "input_image", "image_url": data_uri},
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "video_animation_plan",
                    "strict": True,
                    "schema": self._schema(),
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
            plan = video_animation_plan_from_json(parsed)
            plan = VideoAnimationPlan(
                subject_lock=plan.subject_lock,
                style_lock=plan.style_lock,
                video_prompt=_steered_video_prompt(
                    plan.video_prompt, spec, loop_mode
                ),
            )
        except ProviderError as exc:
            raise ProviderError(
                exc.code,
                _redact(str(exc), self._api_key),
                retry_after=exc.retry_after,
                usage=usage,
            ) from exc
        except ValueError as exc:
            raise ProviderError(
                "bad_response",
                _redact(f"video planner output was not valid JSON: {exc}", self._api_key),
                usage=usage,
            ) from exc
        return VideoAnimationPlanResult(plan=plan, usage=usage)

    @staticmethod
    def _schema() -> dict:
        properties = {
            field: {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_VIDEO_PLAN_STRING,
            }
            for field in ("subject_lock", "style_lock", "video_prompt")
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": ["subject_lock", "style_lock", "video_prompt"],
        }

    @staticmethod
    def _extract_output_text(response: dict) -> str:
        output = response.get("output")
        if not isinstance(output, list):
            raise ProviderError("bad_response", "video response missing an output list")
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
                        "the provider declined this animation; try rephrasing it",
                    )
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        if not texts:
            raise ProviderError("bad_response", "video response contained no output text")
        return "".join(texts)


def _video_request_id(value: object, code: str, usage: ProviderUsage) -> str:
    if not isinstance(value, str) or _VIDEO_REQUEST_ID_RE.fullmatch(value) is None:
        raise ProviderError(code, "video request ID is invalid", usage=usage)
    return value


class XaiVideoProvider:
    """Submit one paid image-to-video request and poll it through separate seams."""

    _STATUSES = ("pending", "done", "failed", "expired")

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        submit_transport=None,
        poll_transport=None,
    ) -> None:
        self._api_key = api_key
        self._model = _curated_model(
            "video", DEFAULT_MODELS["video"] if model is None else model
        )
        self._submit_transport = (
            submit_transport if submit_transport is not None else _xai_request
        )
        self._poll_transport = (
            poll_transport if poll_transport is not None else _xai_get_request
        )

    def submit(
        self,
        plan: object,
        selected_image_bytes: object,
        selected_image_mime_type: object,
        deadline: float,
    ) -> VideoSubmission:
        if not isinstance(plan, VideoAnimationPlan):
            raise ProviderError("config", "a validated video animation plan is required")
        try:
            plan = video_animation_plan_from_json(
                {
                    "subject_lock": plan.subject_lock,
                    "style_lock": plan.style_lock,
                    "video_prompt": plan.video_prompt,
                }
            )
        except ProviderError as exc:
            raise ProviderError("config", "video animation plan is invalid") from exc
        data_uri = _selected_image_data_uri(
            selected_image_bytes, selected_image_mime_type
        )
        payload = {
            "model": self._model,
            "prompt": plan.video_prompt,
            "image": {"url": data_uri},
            "duration": 1,
            "resolution": "480p",
        }
        response = _call_provider(
            self._submit_transport,
            XAI_VIDEO_GENERATIONS_URL,
            payload,
            self._api_key,
            deadline,
        )
        usage = _provider_usage(response)
        request_id = _video_request_id(response.get("request_id"), "bad_response", usage)
        return VideoSubmission(request_id=request_id, status="pending", usage=usage)

    def poll(self, request_id: object, deadline: float) -> VideoStatus:
        request_id = _video_request_id(
            request_id, "config", MISSING_PROVIDER_USAGE
        )
        url = XAI_VIDEO_STATUS_URL.format(request_id=request_id)
        response = _call_poll_provider(
            self._poll_transport, url, self._api_key, deadline
        )
        usage = _provider_usage(response)
        if "request_id" in response:
            echoed_request_id = _video_request_id(
                response["request_id"], "bad_response", usage
            )
            if echoed_request_id != request_id:
                raise ProviderError(
                    "bad_response",
                    "video status response did not match the requested ID",
                    usage=usage,
                )
        status = response.get("status")
        if status not in self._STATUSES:
            raise ProviderError(
                "bad_response", "video status was not recognized", usage=usage
            )
        if status != "done":
            return VideoStatus(request_id=request_id, status=status, usage=usage)

        video = response.get("video")
        if not isinstance(video, dict):
            raise ProviderError(
                "bad_response", "completed video response omitted video metadata", usage=usage
            )
        video_url = video.get("url")
        duration = video.get("duration")
        if not isinstance(video_url, str) or not video_url.startswith("https://"):
            raise ProviderError(
                "bad_response", "completed video response omitted a secure video URL", usage=usage
            )
        if isinstance(duration, bool) or not isinstance(duration, int) or duration != 1:
            raise ProviderError(
                "bad_response", "completed video duration was not exactly one second", usage=usage
            )
        return VideoStatus(
            request_id=request_id,
            status=status,
            usage=usage,
            video_url=video_url,
            duration=duration,
        )


# --- Shared image validation -------------------------------------------------
#
# Historical durable concept assets still use the xAI Images API. Paid image
# POSTs are never auto-retried, and URL response mode is never requested or
# fetched. Every response runs the full validation chain before it is trusted:
#
#   shape (data/b64_json) -> base64 decode -> byte-size cap (MAX_IMAGE_BYTES)
#   -> Pillow open with a PNG/JPEG format whitelist -> pixel cap
#   (MAX_IMAGE_PIXELS) -> full load()
#
# Any deviation raises ``ProviderError('bad_response', ...)``. Pillow is imported
# lazily inside the decode path so this module stays importable without it.


class Cancelled(Exception):
    """Raised when a supplied cancel predicate reports an operation was cancelled.

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
