"""Local-first providers for the shared procedural animation recipe."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from . import ai_catalog, llm, procedural
from .ollama_client import OllamaClient, OllamaError, OllamaModel


MAX_RECIPE_PROMPT_CHARS = 4000
MAX_LOCAL_RESPONSE_BYTES = 1_000_000
LOCAL_OUTPUT_TOKENS = 1536
LOCAL_MAX_RETRIES = 2


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
            self._model_id = ai_catalog.validate_model("interpreter", model_id)
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


__all__ = [
    "LOCAL_MAX_RETRIES",
    "LOCAL_OUTPUT_TOKENS",
    "MAX_RECIPE_PROMPT_CHARS",
    "OllamaRecipeProvider",
    "RecipeProvider",
    "RecipeRequest",
    "RecipeResult",
    "XaiRecipeProvider",
]
