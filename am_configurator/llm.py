"""Shared provider types and xAI transports for lighting assets.

The active procedural generator and the historical durable asset library share
the bounded transport and historical video-status types in this module.
Importing it performs no network I/O.
"""

from __future__ import annotations

import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# --- Pinned design constants -------------------------------------------------
#
# Fixed by design v3 (docs/design/llm-led-generator.md); do not re-derive here.

MAX_PROVIDER_RESPONSE = 25_000_000  # bounded read cap on any upstream body (bytes)
MAX_PROVIDER_REQUEST = 25_000_000
PER_CALL_TIMEOUT = 30.0  # hard ceiling on any single upstream call; the deadline caps it lower
_VIDEO_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,199}", re.ASCII)

# Pinned xAI endpoints. Bumping a host/path is a deliberate one-line change.
XAI_API_HOST = "api.x.ai"
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
XAI_VIDEO_STATUS_URL = "https://api.x.ai/v1/videos/{request_id}"
ANTHROPIC_API_HOST = "api.anthropic.com"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"

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
class ProviderTransportSpec:
    """One compiled HTTPS origin and authentication contract."""

    provider: str
    url: str
    host: str
    auth_header: str
    auth_prefix: str
    static_headers: tuple[tuple[str, str], ...] = ()
    path_prefix: str = "/v1/"


ANTHROPIC_MESSAGES_TRANSPORT = ProviderTransportSpec(
    provider="anthropic",
    url=ANTHROPIC_MESSAGES_URL,
    host=ANTHROPIC_API_HOST,
    auth_header="x-api-key",
    auth_prefix="",
    static_headers=(("anthropic-version", ANTHROPIC_API_VERSION),),
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
class VideoStatus:
    """One status observation; an ephemeral signed URL exists only when done."""

    request_id: str
    status: str
    usage: ProviderUsage
    video_url: str | None = field(default=None, repr=False)
    duration: int | None = None

# --- xAI HTTP transport ------------------------------------------------------
#
# ``_xai_request`` is the single choke point through which every xAI call
# flows. It POSTs a JSON payload, enforces the monotonic deadline and a bounded
# response read, and maps every failure to a typed :class:`ProviderError`
# (design §Typed errors). It never retries. Secrets are scrubbed from every
# error message before it is raised.


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


def _call_provider(
    transport,
    endpoint: object,
    payload: dict,
    api_key: str,
    deadline: float,
) -> dict:
    """Invoke an injected transport while preserving typed, redacted failures."""
    failure: ProviderError | None = None
    try:
        response = transport(endpoint, payload, api_key, deadline)
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


class _NoXaiRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so Authorization never crosses an origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_xai_url(value: object) -> str:
    """Accept only the fixed xAI HTTPS origin used by curated API calls."""
    if not isinstance(value, str) or not value:
        raise ProviderError("config", "provider URL is missing or invalid")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ProviderError("config", "provider URL contains invalid characters")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        raise ProviderError("config", "provider URL is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.netloc != XAI_API_HOST
        or parsed.hostname != XAI_API_HOST
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/v1/")
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderError("config", "provider URL is not an allowed HTTPS URL")
    try:
        if parsed.port is not None:
            raise ProviderError("config", "provider URL must not specify a port")
    except ValueError:
        raise ProviderError("config", "provider URL has an invalid port") from None
    return value


def _default_opener():
    """Build a verifying, proxy-free opener that refuses every redirect."""
    context = ssl.create_default_context()
    director = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
        _NoXaiRedirects(),
    )
    return director.open


def _validate_provider_spec(spec: ProviderTransportSpec) -> None:
    if not isinstance(spec, ProviderTransportSpec):
        raise ProviderError("config", "provider transport specification is invalid")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", spec.provider):
        raise ProviderError("config", "provider identifier is invalid")
    if (
        not isinstance(spec.host, str)
        or not spec.host
        or not isinstance(spec.path_prefix, str)
        or not spec.path_prefix.startswith("/")
    ):
        raise ProviderError("config", "provider origin is invalid")
    try:
        parsed = urllib.parse.urlsplit(spec.url)
    except (TypeError, ValueError):
        raise ProviderError("config", "provider URL is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.netloc != spec.host
        or parsed.hostname != spec.host
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith(spec.path_prefix)
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderError("config", "provider URL is not an allowed HTTPS URL")
    try:
        if parsed.port is not None:
            raise ProviderError("config", "provider URL must not specify a port")
    except ValueError:
        raise ProviderError("config", "provider URL has an invalid port") from None
    header_token = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", re.ASCII)
    if not isinstance(spec.auth_header, str) or not header_token.fullmatch(
        spec.auth_header
    ):
        raise ProviderError("config", "provider authentication header is invalid")
    if (
        not isinstance(spec.auth_prefix, str)
        or "\r" in spec.auth_prefix
        or "\n" in spec.auth_prefix
    ):
        raise ProviderError("config", "provider authentication scheme is invalid")
    for name, value in spec.static_headers:
        if (
            not isinstance(name, str)
            or not header_token.fullmatch(name)
            or not isinstance(value, str)
            or not value
            or "\r" in value
            or "\n" in value
        ):
            raise ProviderError("config", "provider static header is invalid")
        if name.lower() in {"authorization", "content-type", spec.auth_header.lower()}:
            raise ProviderError("config", "provider static header is reserved")


def _provider_json_request(
    spec: ProviderTransportSpec,
    payload: dict,
    api_key: str,
    deadline: float,
    *,
    opener=None,
) -> dict:
    """Perform exactly one bounded, proxy-free JSON POST to a compiled origin."""

    _validate_provider_spec(spec)
    if (
        not isinstance(api_key, str)
        or not api_key
        or any(ord(character) < 32 or ord(character) == 127 for character in api_key)
    ):
        raise ProviderError("config", "provider credential is invalid")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderError(
            "timeout", "provider deadline exceeded before the request started"
        )
    try:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise ProviderError("config", "provider request payload is invalid") from None
    if len(body) > MAX_PROVIDER_REQUEST:
        raise ProviderError(
            "config",
            f"provider request exceeded the {MAX_PROVIDER_REQUEST}-byte cap",
        )
    if opener is None:
        opener = _default_opener()
    headers = {
        "Content-Type": "application/json",
        spec.auth_header: f"{spec.auth_prefix}{api_key}",
    }
    headers.update(dict(spec.static_headers))
    request = urllib.request.Request(
        spec.url,
        data=body,
        method="POST",
        headers=headers,
    )
    timeout = min(remaining, PER_CALL_TIMEOUT)
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
            ) from None
        if code == 429:
            raise ProviderError(
                "rate_limited",
                "provider rate limit reached; retry later",
                retry_after=retry_after,
                usage=usage,
            ) from None
        if 500 <= code <= 599:
            raise ProviderError(
                "unavailable",
                f"provider is temporarily unavailable (HTTP {code})",
                usage=usage,
            ) from None
        raise ProviderError(
            "bad_response",
            f"provider returned an unexpected status (HTTP {code})",
            usage=usage,
        ) from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise ProviderError(
                "timeout", _redact(f"provider request timed out: {exc}", api_key)
            ) from None
        raise ProviderError(
            "offline", _redact(f"could not reach the provider: {exc}", api_key)
        ) from None
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderError(
            "timeout", _redact(f"provider request timed out: {exc}", api_key)
        ) from None
    except (ssl.SSLError, OSError) as exc:
        raise ProviderError(
            "offline", _redact(f"could not reach the provider: {exc}", api_key)
        ) from None

    try:
        raw = response.read(MAX_PROVIDER_RESPONSE + 1)
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderError(
            "timeout", _redact(f"provider response read timed out: {exc}", api_key)
        ) from None
    except (ssl.SSLError, OSError) as exc:
        raise ProviderError(
            "offline", _redact(f"provider response read failed: {exc}", api_key)
        ) from None
    finally:
        _close_quietly(response)

    if len(raw) > MAX_PROVIDER_RESPONSE:
        raise ProviderError(
            "bad_response",
            f"provider response exceeded the {MAX_PROVIDER_RESPONSE}-byte cap",
        )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ProviderError(
            "bad_response", "provider response was not valid JSON"
        ) from None
    if not isinstance(parsed, dict):
        raise ProviderError("bad_response", "provider response was not a JSON object")
    return parsed


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
    return _provider_json_request(
        ProviderTransportSpec(
            provider="xai",
            url=url,
            host=XAI_API_HOST,
            auth_header="Authorization",
            auth_prefix="Bearer ",
        ),
        payload,
        api_key,
        deadline,
        opener=opener,
    )


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

    url = _validate_xai_url(url)
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




def _video_request_id(value: object, code: str, usage: ProviderUsage) -> str:
    if not isinstance(value, str) or _VIDEO_REQUEST_ID_RE.fullmatch(value) is None:
        raise ProviderError(code, "video request ID is invalid", usage=usage)
    return value


class XaiVideoProvider:
    """Poll an already-accepted historical video request without new paid work."""

    _STATUSES = ("pending", "done", "failed", "expired")

    def __init__(
        self,
        api_key: str,
        poll_transport=None,
    ) -> None:
        self._api_key = api_key
        self._poll_transport = (
            poll_transport if poll_transport is not None else _xai_get_request
        )

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
