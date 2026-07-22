"""Hardened fixed-loopback client for an already-running local Ollama service."""

from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODELS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
MAX_OLLAMA_RESPONSE_BYTES = 1_000_000
MAX_OLLAMA_MODELS = 512
DISCOVERY_TIMEOUT_SECONDS = 5.0
CHAT_TIMEOUT_SECONDS = 180.0

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class _NoOllamaRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OLLAMA_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoOllamaRedirects(),
)


class OllamaError(RuntimeError):
    """One stable, pathless local Ollama failure."""

    def __init__(self, code: str, message: str) -> None:
        if code not in {
            "unavailable",
            "timeout",
            "cancelled",
            "model_unavailable",
            "bad_response",
        }:
            code = "unavailable"
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OllamaModel:
    model_id: str
    digest: str
    size_bytes: int
    parameter_size: str | None
    quantization: str | None

    def public(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
        }


def valid_model_id(value: object) -> bool:
    return isinstance(value, str) and _MODEL_ID.fullmatch(value) is not None


def valid_model_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _bounded_detail(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 80:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    return value


def _model_from_tag(value: object) -> OllamaModel | None:
    if not isinstance(value, dict):
        return None
    if "remote_model" in value or "remote_host" in value:
        return None
    model_id = value.get("model")
    if value.get("name") != model_id or not valid_model_id(model_id):
        return None
    if model_id.lower().endswith(":cloud"):
        return None
    digest = value.get("digest")
    if not valid_model_digest(digest):
        return None
    size = value.get("size")
    if type(size) is not int or size <= 0:
        return None
    capabilities = value.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or "completion" not in capabilities
        or any(not isinstance(item, str) for item in capabilities)
    ):
        return None
    details = value.get("details")
    if not isinstance(details, dict):
        details = {}
    return OllamaModel(
        model_id=model_id,
        digest=digest,
        size_bytes=size,
        parameter_size=_bounded_detail(details.get("parameter_size")),
        quantization=_bounded_detail(details.get("quantization_level")),
    )


class OllamaClient:
    """The only production transport to Ollama's fixed local HTTP API."""

    def __init__(self, *, opener: Callable[..., Any] | Any = _OLLAMA_OPENER) -> None:
        self._opener = opener

    @staticmethod
    def _timeout(deadline: float, ceiling: float) -> float:
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise OllamaError("timeout", "The local Ollama deadline is invalid.")
        remaining = float(deadline) - time.monotonic()
        if remaining <= 0:
            raise OllamaError("timeout", "The local Ollama request timed out.")
        return min(ceiling, remaining)

    def _open(self, request: urllib.request.Request, *, timeout: float):
        opener = self._opener
        if callable(opener):
            return opener(request, timeout=timeout)
        return opener.open(request, timeout=timeout)

    def _request(
        self,
        request: urllib.request.Request,
        *,
        deadline: float,
        timeout_ceiling: float,
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if cancelled is not None and cancelled():
            raise OllamaError("cancelled", "The local Ollama request was cancelled.")
        timeout = self._timeout(deadline, timeout_ceiling)
        try:
            with self._open(request, timeout=timeout) as response:
                payload = response.read(MAX_OLLAMA_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            code = "model_unavailable" if exc.code == 404 else "unavailable"
            raise OllamaError(code, "The local Ollama request was rejected.") from None
        except (TimeoutError, socket.timeout):
            raise OllamaError("timeout", "The local Ollama request timed out.") from None
        except (OSError, urllib.error.URLError):
            raise OllamaError("unavailable", "The local Ollama service is unavailable.") from None
        if cancelled is not None and cancelled():
            raise OllamaError("cancelled", "The local Ollama request was cancelled.")
        if len(payload) > MAX_OLLAMA_RESPONSE_BYTES:
            raise OllamaError("bad_response", "The local Ollama response was too large.")
        try:
            parsed = json.loads(payload)
        except (UnicodeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict):
            raise OllamaError("bad_response", "The local Ollama response was invalid.")
        return parsed

    def list_models(self, *, deadline: float) -> tuple[OllamaModel, ...]:
        request = urllib.request.Request(
            OLLAMA_MODELS_URL,
            headers={"Accept": "application/json"},
            method="GET",
        )
        response = self._request(
            request,
            deadline=deadline,
            timeout_ceiling=DISCOVERY_TIMEOUT_SECONDS,
        )
        values = response.get("models")
        if not isinstance(values, list) or len(values) > MAX_OLLAMA_MODELS:
            raise OllamaError("bad_response", "The local Ollama model list was invalid.")
        models = [model for value in values if (model := _model_from_tag(value)) is not None]
        models.sort(key=lambda model: (model.model_id.casefold(), model.model_id))
        return tuple(models)

    def chat(
        self,
        payload: dict[str, Any],
        *,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise OllamaError("bad_response", "The local Ollama request was invalid.")
        request = urllib.request.Request(
            OLLAMA_CHAT_URL,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        return self._request(
            request,
            deadline=deadline,
            timeout_ceiling=CHAT_TIMEOUT_SECONDS,
            cancelled=cancelled,
        )


__all__ = [
    "MAX_OLLAMA_RESPONSE_BYTES",
    "OLLAMA_BASE_URL",
    "OLLAMA_CHAT_URL",
    "OLLAMA_MODELS_URL",
    "OllamaClient",
    "OllamaError",
    "OllamaModel",
    "valid_model_digest",
    "valid_model_id",
]
