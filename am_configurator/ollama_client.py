"""Hardened client for one user-configured Ollama server."""

from __future__ import annotations

import http.client
import ipaddress
import json
import queue
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_BASE_URL = DEFAULT_OLLAMA_BASE_URL
OLLAMA_MODELS_PATH = "/api/tags"
OLLAMA_CHAT_PATH = "/api/chat"
MAX_OLLAMA_RESPONSE_BYTES = 1_000_000
MAX_OLLAMA_MODELS = 512
MAX_OLLAMA_BASE_URL_LENGTH = 2_048
DISCOVERY_TIMEOUT_SECONDS = 5.0
CHAT_TIMEOUT_SECONDS = 180.0
OLLAMA_CANCEL_POLL_SECONDS = 0.05

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class _NoOllamaRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _build_ollama_opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoOllamaRedirects(),
    )


_OLLAMA_OPENER = _build_ollama_opener()


def normalize_ollama_base_url(value: object) -> str:
    """Validate and normalize one credential-free HTTP(S) Ollama origin."""

    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_OLLAMA_BASE_URL_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("Ollama server URL is invalid.")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("Ollama server URL is invalid.") from None
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Ollama server URL must use HTTP or HTTPS.")
    if (
        not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Ollama server URL must be one HTTP(S) origin.")

    raw_host = parsed.hostname
    if raw_host.endswith(".") or "%" in raw_host:
        raise ValueError("Ollama server host is invalid.")
    bracketed = False
    try:
        address = ipaddress.ip_address(raw_host)
    except ValueError:
        try:
            host = raw_host.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError("Ollama server host is invalid.") from None
        labels = host.split(".")
        if (
            len(host) > 253
            or any(not label or _DNS_LABEL.fullmatch(label) is None for label in labels)
            or all(label.isdigit() for label in labels)
        ):
            raise ValueError("Ollama server host is invalid.")
    else:
        if address.is_unspecified:
            raise ValueError("Ollama server host cannot be unspecified.")
        host = address.compressed
        bracketed = address.version == 6

    default_port = 80 if scheme == "http" else 443
    if port is None:
        port = default_port
    if not 1 <= port <= 65_535:
        raise ValueError("Ollama server port is invalid.")
    rendered_host = f"[{host}]" if bracketed else host
    rendered_port = "" if port == default_port else f":{port}"
    return f"{scheme}://{rendered_host}{rendered_port}"


class OllamaError(RuntimeError):
    """One stable, pathless local Ollama failure."""

    def __init__(self, code: str, message: str) -> None:
        if code not in {
            "unavailable",
            "timeout",
            "cancelled",
            "model_unavailable",
            "upgrade_required",
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


def _local_tag_missing_capabilities(value: object) -> bool:
    """Identify an otherwise valid local tag from an older Ollama contract."""
    if not isinstance(value, dict) or "capabilities" in value:
        return False
    if "remote_model" in value or "remote_host" in value:
        return False
    model_id = value.get("model")
    return (
        value.get("name") == model_id
        and valid_model_id(model_id)
        and not model_id.lower().endswith(":cloud")
        and valid_model_digest(value.get("digest"))
        and type(value.get("size")) is int
        and value["size"] > 0
    )


class OllamaClient:
    """The only production transport to one normalized Ollama origin."""

    def __init__(
        self,
        *,
        base_url: object = DEFAULT_OLLAMA_BASE_URL,
        opener: Callable[..., Any] | Any = _OLLAMA_OPENER,
        connection_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = normalize_ollama_base_url(base_url)
        parsed = urllib.parse.urlsplit(self.base_url)
        self._host = parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._models_url = f"{self.base_url}{OLLAMA_MODELS_PATH}"
        self._opener = opener
        self._connection_factory = connection_factory or (
            http.client.HTTPSConnection
            if parsed.scheme == "https"
            else http.client.HTTPConnection
        )

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

    @staticmethod
    def _abort_connection(connection: object) -> None:
        sock = getattr(connection, "sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except (AttributeError, OSError, ValueError):
                pass
        try:
            connection.close()
        except (AttributeError, OSError, ValueError):
            pass

    def _chat_exchange(
        self,
        body: bytes,
        *,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> tuple[int, bytes]:
        if cancelled():
            raise OllamaError("cancelled", "The local Ollama request was cancelled.")
        timeout = self._timeout(deadline, CHAT_TIMEOUT_SECONDS)
        try:
            connection = self._connection_factory(
                self._host,
                self._port,
                timeout=timeout,
            )
        except (OSError, ValueError):
            raise OllamaError(
                "unavailable", "The local Ollama service is unavailable."
            ) from None

        outcome: queue.Queue[tuple[object, object, Exception | None]] = queue.Queue(
            maxsize=1
        )

        def exchange() -> None:
            result: tuple[object, object, Exception | None]
            try:
                connection.request(
                    "POST",
                    OLLAMA_CHAT_PATH,
                    body=body,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
                response = connection.getresponse()
                result = (
                    getattr(response, "status", None),
                    response.read(MAX_OLLAMA_RESPONSE_BYTES + 1),
                    None,
                )
            except Exception as error:
                result = (None, None, error)
            finally:
                self._abort_connection(connection)
            outcome.put_nowait(result)

        worker = threading.Thread(
            target=exchange,
            name="ollama-exchange",
            daemon=True,
        )
        worker.start()

        def stop(code: str, message: str) -> None:
            self._abort_connection(connection)
            worker.join(timeout=OLLAMA_CANCEL_POLL_SECONDS * 2)
            raise OllamaError(code, message)

        while True:
            if cancelled():
                stop("cancelled", "The local Ollama request was cancelled.")
            remaining = float(deadline) - time.monotonic()
            if remaining <= 0:
                stop("timeout", "The local Ollama request timed out.")
            try:
                status, payload, error = outcome.get(
                    timeout=min(OLLAMA_CANCEL_POLL_SECONDS, remaining)
                )
            except queue.Empty:
                continue
            if cancelled():
                stop("cancelled", "The local Ollama request was cancelled.")
            if float(deadline) - time.monotonic() <= 0:
                stop("timeout", "The local Ollama request timed out.")
            break

        worker.join(timeout=OLLAMA_CANCEL_POLL_SECONDS)
        if error is not None:
            if isinstance(error, (TimeoutError, socket.timeout)):
                raise OllamaError(
                    "timeout", "The local Ollama request timed out."
                ) from None
            raise OllamaError(
                "unavailable", "The local Ollama service is unavailable."
            ) from None
        if type(status) is not int or not isinstance(payload, bytes):
            raise OllamaError(
                "bad_response", "The local Ollama response was invalid."
            )
        return status, payload

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
            self._models_url,
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
        if not models and any(_local_tag_missing_capabilities(value) for value in values):
            raise OllamaError(
                "upgrade_required",
                "Ollama must be upgraded before local models can be discovered.",
            )
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
        try:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        except (TypeError, UnicodeError, ValueError):
            raise OllamaError(
                "bad_response", "The local Ollama request was invalid."
            ) from None
        status, response = self._chat_exchange(
            body,
            deadline=deadline,
            cancelled=cancelled,
        )
        if not 200 <= status <= 299:
            code = "model_unavailable" if status == 404 else "unavailable"
            raise OllamaError(code, "The local Ollama request was rejected.")
        if len(response) > MAX_OLLAMA_RESPONSE_BYTES:
            raise OllamaError("bad_response", "The local Ollama response was too large.")
        try:
            parsed = json.loads(response)
        except (UnicodeError, ValueError):
            parsed = None
        if not isinstance(parsed, dict):
            raise OllamaError("bad_response", "The local Ollama response was invalid.")
        return parsed


__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "MAX_OLLAMA_RESPONSE_BYTES",
    "OLLAMA_BASE_URL",
    "OLLAMA_CHAT_PATH",
    "OLLAMA_MODELS_PATH",
    "OllamaClient",
    "OllamaError",
    "OllamaModel",
    "normalize_ollama_base_url",
    "valid_model_digest",
    "valid_model_id",
]
