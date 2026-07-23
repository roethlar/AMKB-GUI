"""Local-first providers for the shared procedural animation recipe."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from . import ai_catalog, llm, procedural
from .ollama_client import OllamaClient, OllamaError, OllamaModel
from .recipe_inference import (
    LOCAL_MAX_RETRIES,
    LOCAL_OUTPUT_TOKENS,
    MAX_LOCAL_RESPONSE_BYTES,
    MAX_RECIPE_PROMPT_CHARS,
    build_ollama_recipe_payload,
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
        try:
            payload = build_ollama_recipe_payload(
                model_id=self._model.model_id,
                prompt=prompt,
                system_prompt=system_prompt,
                schema=schema,
                width=request.width,
                height=request.height,
                frame_count=request.frame_count,
                attempt=attempt,
                validation_reason=validation_reason,
            )
        except ValueError as error:
            raise llm.ProviderError("config", str(error)) from None
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
