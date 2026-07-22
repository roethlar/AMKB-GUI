"""Local-first providers for the shared procedural animation recipe."""

from __future__ import annotations

import atexit
import contextlib
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from . import ai_catalog, llm, procedural
from .local_ai_runtime import (
    LocalRuntimeError,
    RuntimePaths,
    get_local_ai_runtime,
)
from .local_model import LocalModelError, LocalModelManager, SelectedModel
from .ollama_client import OllamaClient, OllamaError, OllamaModel


MAX_RECIPE_PROMPT_CHARS = 4000
MAX_LOCAL_RESPONSE_BYTES = 1_000_000
MAX_LOCAL_DIAGNOSTIC_BYTES = 1_000_000
LOCAL_CONTEXT_TOKENS = 4096
LOCAL_OUTPUT_TOKENS = 1536
LOCAL_IDLE_SECONDS = 120.0
LOCAL_MAX_RETRIES = 2


class _NoLoopbackRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_LOOPBACK_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoLoopbackRedirects(),
)


@dataclass(frozen=True)
class RecipeRequest:
    prompt: str
    width: int
    height: int
    frame_count: int
    density_default: str


@dataclass(frozen=True)
class RecipeResult:
    recipe: dict[str, Any]
    backend: str
    provider: str
    model_id: str
    usage: dict[str, int] | None


class RecipeProvider(Protocol):
    def generate(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> RecipeResult: ...


def _request_parts(request: RecipeRequest) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(request, RecipeRequest):
        raise llm.ProviderError("config", "Recipe request is invalid.")
    prompt = request.prompt
    if (
        not isinstance(prompt, str)
        or not prompt.strip()
        or len(prompt) > MAX_RECIPE_PROMPT_CHARS
        or any(ord(character) < 32 and character not in "\n\r\t" for character in prompt)
    ):
        raise llm.ProviderError("config", "Recipe prompt is invalid.")
    try:
        system_prompt = procedural.recipe_system_prompt(
            request.width,
            request.height,
            request.frame_count,
            density_default=request.density_default,
        )
    except (TypeError, ValueError):
        system_prompt = None
    if system_prompt is None:
        raise llm.ProviderError("config", "Recipe dimensions are invalid.")
    return prompt.strip(), system_prompt, procedural.recipe_schema()


def _check_start(deadline: float, cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise llm.ProviderError("unavailable", "Recipe generation was cancelled.")
    if deadline <= time.monotonic():
        raise llm.ProviderError("timeout", "Recipe generation deadline expired.")


def _validated_recipe_text(text: object) -> dict[str, Any]:
    if not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_LOCAL_RESPONSE_BYTES:
        raise llm.ProviderError("bad_response", "Recipe output was invalid.")
    try:
        value = json.loads(text)
    except (UnicodeError, ValueError):
        value = None
    if value is None:
        # JSONDecodeError retains the raw document; raise after the handler so
        # provider output cannot survive in an exception context.
        raise llm.ProviderError("bad_response", "Recipe output was not valid JSON.")
    try:
        normalized = procedural.validate_recipe(value)
    except (TypeError, ValueError):
        normalized = None
    if normalized is None:
        raise llm.ProviderError("bad_response", "Recipe output failed validation.")
    return normalized


def _xai_output_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        raise llm.ProviderError("bad_response", "Recipe response omitted output.")
    texts: list[str] = []
    refused = False
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
                refused = True
            elif part.get("type") == "output_text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
    if refused:
        raise llm.ProviderError("moderation", "The provider declined this prompt.")
    if not texts:
        raise llm.ProviderError("bad_response", "Recipe response contained no text.")
    return "".join(texts)


class XaiRecipeProvider:
    """Exactly one bounded xAI Responses request for one strict recipe."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = "grok-4.5",
        transport=None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise llm.ProviderError("config", "API credential is missing.")
        try:
            self._model_id = llm.validate_model("interpreter", model_id)
        except ValueError:
            raise llm.ProviderError("config", "API recipe model is unavailable.") from None
        self._api_key = api_key
        self._transport = llm._xai_request if transport is None else transport

    def generate(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> RecipeResult:
        prompt, system_prompt, schema = _request_parts(request)
        _check_start(deadline, cancelled)
        payload = {
            "model": self._model_id,
            "store": False,
            "max_output_tokens": ai_catalog.RECIPE_API_MAX_OUTPUT_TOKENS,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "animation_recipe",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = llm._call_provider(
            self._transport,
            llm.XAI_RESPONSES_URL,
            payload,
            self._api_key,
            deadline,
        )
        usage = llm._provider_usage(response)
        failure: llm.ProviderError | None = None
        try:
            recipe = _validated_recipe_text(_xai_output_text(response))
        except llm.ProviderError as error:
            failure = llm.ProviderError(
                error.code,
                str(error),
                retry_after=error.retry_after,
                usage=usage,
            )
            recipe = None
        if failure is not None:
            raise failure
        if recipe is None:
            raise llm.ProviderError("bad_response", "Recipe output failed validation.")
        if cancelled():
            # The paid request is never retried. The coordinator may hide the
            # result after cancellation, but this provider makes no second call.
            raise llm.ProviderError(
                "unavailable",
                "Recipe generation was cancelled.",
                usage=usage,
            )
        usage_value = (
            {"cost_in_usd_ticks": usage.cost_in_usd_ticks}
            if usage.reported and usage.cost_in_usd_ticks is not None
            else None
        )
        return RecipeResult(
            recipe=recipe,
            backend="api",
            provider="xai",
            model_id=self._model_id,
            usage=usage_value,
        )


def _pick_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _no_window_creation_flags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _drain_process_output(stream, process) -> None:
    total = 0
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            total += len(chunk)
            if total > MAX_LOCAL_DIAGNOSTIC_BYTES:
                with contextlib.suppress(Exception):
                    process.terminate()
                return
    except Exception:
        return


def _stop_server_process(process) -> None:
    if process is None:
        return
    if process.poll() is None:
        with contextlib.suppress(Exception):
            process.terminate()
        try:
            process.wait(timeout=1)
        except Exception:
            with contextlib.suppress(Exception):
                process.kill()
            with contextlib.suppress(Exception):
                process.wait(timeout=1)
    for stream in (getattr(process, "stdout", None), getattr(process, "stderr", None)):
        if stream is not None:
            with contextlib.suppress(Exception):
                stream.close()


def _ready_probe(port, token, deadline, process, cancelled) -> None:
    url = f"http://127.0.0.1:{port}/health"
    while True:
        if cancelled():
            raise llm.ProviderError("unavailable", "Local inference was cancelled.")
        if process.poll() is not None:
            raise llm.ProviderError("unavailable", "Local inference could not start.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise llm.ProviderError("timeout", "Local inference startup timed out.")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            response = _LOOPBACK_OPENER.open(
                request, timeout=min(0.25, remaining)
            )
            try:
                response.read(4097)
                if getattr(response, "status", 200) == 200:
                    return
            finally:
                response.close()
        except Exception:
            pass
        time.sleep(min(0.05, max(0.0, remaining)))


def _post_loopback(port: int, token: str, payload: dict, deadline: float) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise llm.ProviderError("timeout", "Local inference deadline expired.")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    response = None
    failed = False
    try:
        response = _LOOPBACK_OPENER.open(request, timeout=remaining)
        raw = response.read(MAX_LOCAL_RESPONSE_BYTES + 1)
    except Exception:
        raw = b""
        failed = True
    finally:
        if response is not None:
            with contextlib.suppress(Exception):
                response.close()
    if failed:
        raise llm.ProviderError("unavailable", "Local inference request failed.")
    if len(raw) > MAX_LOCAL_RESPONSE_BYTES:
        raise llm.ProviderError("bad_response", "Local inference response was too large.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        value = None
    if not isinstance(value, dict):
        raise llm.ProviderError("bad_response", "Local inference response was invalid.")
    return value


def _loopback_exchange(port, token, payload, deadline, cancelled, abort) -> dict:
    result: dict[str, Any] = {}

    def request_worker() -> None:
        try:
            result["value"] = _post_loopback(port, token, payload, deadline)
        except llm.ProviderError as error:
            result["error"] = llm.ProviderError(error.code, str(error))
        except Exception:
            result["error"] = llm.ProviderError(
                "unavailable", "Local inference request failed."
            )

    worker = threading.Thread(target=request_worker, daemon=True)
    worker.start()
    failure: llm.ProviderError | None = None
    while worker.is_alive():
        if cancelled():
            abort()
            failure = llm.ProviderError("unavailable", "Local inference was cancelled.")
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            abort()
            failure = llm.ProviderError("timeout", "Local inference timed out.")
            break
        worker.join(timeout=min(0.05, remaining))
    if failure is not None:
        worker.join(timeout=1)
        raise failure
    if "error" in result:
        raise result["error"]
    value = result.get("value")
    if not isinstance(value, dict):
        raise llm.ProviderError("bad_response", "Local inference response was invalid.")
    return value


class ManagedLlamaServer:
    """One authenticated, single-slot llama-server kept warm for a short idle."""

    def __init__(
        self,
        *,
        process_factory=None,
        readiness_probe=None,
        exchange=None,
        port_picker=None,
        token_factory=None,
        idle_seconds: float = LOCAL_IDLE_SECONDS,
    ) -> None:
        if idle_seconds <= 0 or idle_seconds > 3600:
            raise ValueError("Local inference idle timeout is invalid.")
        self._process_factory = subprocess.Popen if process_factory is None else process_factory
        self._readiness_probe = _ready_probe if readiness_probe is None else readiness_probe
        self._exchange = _loopback_exchange if exchange is None else exchange
        self._port_picker = _pick_loopback_port if port_picker is None else port_picker
        self._token_factory = (
            (lambda: secrets.token_urlsafe(32)) if token_factory is None else token_factory
        )
        self._idle_seconds = float(idle_seconds)
        self._lock = threading.RLock()
        self._process = None
        self._key: tuple[str, str, str] | None = None
        self._port: int | None = None
        self._token: str | None = None
        self._idle_timer: threading.Timer | None = None
        self._idle_generation = 0
        atexit.register(self.close)

    def _cancel_idle_locked(self) -> None:
        self._idle_generation += 1
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _stop_locked(self) -> None:
        self._cancel_idle_locked()
        process = self._process
        self._process = None
        self._key = None
        self._port = None
        self._token = None
        _stop_server_process(process)

    def _abort_locked(self) -> None:
        with self._lock:
            self._stop_locked()

    def _idle_stop(self, generation: int) -> None:
        with self._lock:
            if generation == self._idle_generation:
                self._stop_locked()

    def _schedule_idle_locked(self) -> None:
        self._cancel_idle_locked()
        generation = self._idle_generation
        timer = threading.Timer(
            self._idle_seconds,
            self._idle_stop,
            args=(generation,),
        )
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _start_locked(
        self,
        runtime: RuntimePaths,
        model: SelectedModel,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> None:
        _check_start(deadline, cancelled)
        port = int(self._port_picker())
        token = self._token_factory()
        if not 1 <= port <= 65535 or not isinstance(token, str) or len(token) < 16:
            raise llm.ProviderError("config", "Local inference launch data was invalid.")
        arguments = (
            str(runtime.server),
            "--model",
            str(model.path),
            "--offline",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--api-key",
            token,
            "--parallel",
            "1",
            "--no-slots",
            "--no-webui",
            "--ctx-size",
            str(LOCAL_CONTEXT_TOKENS),
            "--predict",
            str(LOCAL_OUTPUT_TOKENS),
            "--gpu-layers",
            "all",
            "--fit",
            "off",
            "--flash-attn",
            "on",
            "--reasoning",
            "off",
            "--no-jinja",
        )
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        }
        creationflags = _no_window_creation_flags()
        if creationflags:
            kwargs["creationflags"] = creationflags
        try:
            process = self._process_factory(arguments, **kwargs)
        except Exception:
            process = None
        if process is None:
            raise llm.ProviderError("unavailable", "Local inference could not start.")
        self._process = process
        self._key = (str(runtime.server), str(model.path), model.sha256)
        self._port = port
        self._token = token
        for stream in (getattr(process, "stdout", None), getattr(process, "stderr", None)):
            if stream is not None:
                threading.Thread(
                    target=_drain_process_output,
                    args=(stream, process),
                    daemon=True,
                ).start()
        try:
            self._readiness_probe(port, token, deadline, process, cancelled)
        except llm.ProviderError:
            self._stop_locked()
            raise
        except Exception:
            self._stop_locked()
            raise llm.ProviderError(
                "unavailable", "Local inference could not start."
            ) from None

    def complete(
        self,
        runtime: RuntimePaths,
        model: SelectedModel,
        payload: dict[str, Any],
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> dict[str, Any]:
        key = (str(runtime.server), str(model.path), model.sha256)
        with self._lock:
            self._cancel_idle_locked()
            if self._process is not None and self._process.poll() is not None:
                self._stop_locked()
            if self._process is not None and self._key != key:
                self._stop_locked()
            if self._process is None:
                self._start_locked(runtime, model, deadline, cancelled)
            if self._port is None or self._token is None:
                self._stop_locked()
                raise llm.ProviderError("unavailable", "Local inference is unavailable.")
            try:
                response = self._exchange(
                    self._port,
                    self._token,
                    payload,
                    deadline,
                    cancelled,
                    self._abort_locked,
                )
            except llm.ProviderError:
                raise
            except Exception:
                raise llm.ProviderError(
                    "unavailable", "Local inference request failed."
                ) from None
            finally:
                if self._process is not None and self._process.poll() is None:
                    self._schedule_idle_locked()
            if not isinstance(response, dict):
                raise llm.ProviderError("bad_response", "Local inference response was invalid.")
            return response

    def close(self) -> None:
        with self._lock:
            self._stop_locked()


def _local_output_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise llm.ProviderError("bad_response", "Local recipe response was invalid.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise llm.ProviderError("bad_response", "Local recipe response was invalid.")
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise llm.ProviderError("bad_response", "Local recipe response contained no text.")
    return message["content"]


def _ollama_output_text(response: dict[str, Any]) -> str:
    message = response.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise llm.ProviderError("bad_response", "Local recipe response contained no text.")
    return message["content"]


def _local_retry_content(prompt: str, attempt: int, validation_reason: str | None) -> str:
    if type(attempt) is not int or not 0 <= attempt <= LOCAL_MAX_RETRIES:
        raise llm.ProviderError("config", "Local recipe attempt is invalid.")
    if attempt == 0:
        if validation_reason is not None:
            raise llm.ProviderError("config", "Initial recipe attempt is invalid.")
        return prompt
    if not isinstance(validation_reason, str) or not validation_reason.strip():
        raise llm.ProviderError("config", "Local recipe retry reason is missing.")
    reason = "".join(
        character
        for character in validation_reason.strip()[:200]
        if character.isalnum() or character in " .,:;_()-"
    ).strip()
    if not reason:
        reason = "the recipe did not pass validation"
    return (
        prompt
        + "\n\nRetry correction: the previous recipe failed because "
        + f"{reason}. Return a different corrected recipe."
    )


def _local_seed(request: RecipeRequest, attempt: int) -> int:
    material = (
        f"{request.prompt.strip()}\0{request.width}\0{request.height}\0"
        f"{request.frame_count}\0{attempt}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "big") & 0x7FFF_FFFF


class OllamaRecipeProvider:
    """Generate strict recipes through one already-installed local Ollama model."""

    def __init__(
        self,
        model: OllamaModel,
        *,
        client: OllamaClient | None = None,
    ) -> None:
        if not isinstance(model, OllamaModel):
            raise llm.ProviderError("config", "The selected Ollama model is invalid.")
        self._model = model
        self._client = OllamaClient() if client is None else client

    def generate(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> RecipeResult:
        return self.generate_attempt(
            request,
            deadline,
            cancelled,
            attempt=0,
            validation_reason=None,
        )

    def generate_attempt(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
        *,
        attempt: int,
        validation_reason: str | None,
    ) -> RecipeResult:
        prompt, system_prompt, schema = _request_parts(request)
        _check_start(deadline, cancelled)
        user_content = _local_retry_content(prompt, attempt, validation_reason)
        payload = {
            "model": self._model.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "format": schema,
            "options": {
                "temperature": 0.2,
                "seed": _local_seed(request, attempt),
                "num_predict": LOCAL_OUTPUT_TOKENS,
            },
        }
        try:
            response = self._client.chat(
                payload,
                deadline=deadline,
                cancelled=cancelled,
            )
        except OllamaError as error:
            codes = {
                "timeout": "timeout",
                "cancelled": "unavailable",
                "model_unavailable": "config",
                "bad_response": "bad_response",
                "unavailable": "offline",
            }
            raise llm.ProviderError(
                codes.get(error.code, "unavailable"),
                "Local Ollama recipe generation failed.",
            ) from None
        recipe = _validated_recipe_text(_ollama_output_text(response))
        return RecipeResult(
            recipe=recipe,
            backend="local",
            provider="ollama",
            model_id=self._model.model_id,
            usage=None,
        )


class ManagedLocalRecipeProvider:
    """Generate through the pinned runtime and current private model selection."""

    def __init__(
        self,
        *,
        model_manager: LocalModelManager | None = None,
        runtime_resolver=None,
        server: ManagedLlamaServer | None = None,
    ) -> None:
        self._model_manager = LocalModelManager() if model_manager is None else model_manager
        self._runtime_resolver = (
            get_local_ai_runtime if runtime_resolver is None else runtime_resolver
        )
        self._server = ManagedLlamaServer() if server is None else server

    def generate(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> RecipeResult:
        return self.generate_attempt(
            request,
            deadline,
            cancelled,
            attempt=0,
            validation_reason=None,
        )

    def generate_attempt(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
        *,
        attempt: int,
        validation_reason: str | None,
    ) -> RecipeResult:
        """Run one of at most three coordinator-owned local attempts."""

        prompt, system_prompt, schema = _request_parts(request)
        _check_start(deadline, cancelled)
        try:
            model = self._model_manager.resolve_selected()
            runtime = self._runtime_resolver()
        except (LocalModelError, LocalRuntimeError, OSError, RuntimeError):
            model = None
            runtime = None
        if model is None or runtime is None:
            raise llm.ProviderError(
                "config", "Verified local inference components are unavailable."
            )
        user_content = _local_retry_content(prompt, attempt, validation_reason)
        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "temperature": 0.2,
            "seed": _local_seed(request, attempt),
            "max_tokens": LOCAL_OUTPUT_TOKENS,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "animation_recipe",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        response = self._server.complete(
            runtime,
            model,
            payload,
            deadline,
            cancelled,
        )
        recipe = _validated_recipe_text(_local_output_text(response))
        if cancelled():
            raise llm.ProviderError("unavailable", "Recipe generation was cancelled.")
        return RecipeResult(
            recipe=recipe,
            backend="local",
            provider="llama.cpp",
            model_id=model.filename,
            usage=None,
        )

    def close(self) -> None:
        self._server.close()


__all__ = [
    "LOCAL_CONTEXT_TOKENS",
    "LOCAL_IDLE_SECONDS",
    "LOCAL_MAX_RETRIES",
    "LOCAL_OUTPUT_TOKENS",
    "MAX_RECIPE_PROMPT_CHARS",
    "ManagedLlamaServer",
    "ManagedLocalRecipeProvider",
    "OllamaRecipeProvider",
    "RecipeProvider",
    "RecipeRequest",
    "RecipeResult",
    "XaiRecipeProvider",
]
