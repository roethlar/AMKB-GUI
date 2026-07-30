"""Local-first providers for the shared procedural animation recipe."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from . import ai_catalog, llm, procedural
from .ollama_client import OllamaClient, OllamaError, OllamaModel
from .recipe_inference import (
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


_ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS = {
    "exclusiveMaximum",
    "exclusiveMinimum",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minContains",
    "minLength",
    "minProperties",
    "minimum",
    "multipleOf",
    "uniqueItems",
}


def _anthropic_output_schema(value: object) -> object:
    """Project the local recipe schema onto Anthropic's documented subset."""

    if isinstance(value, dict):
        projected = {}
        for key, child in value.items():
            if key in _ANTHROPIC_UNSUPPORTED_SCHEMA_KEYS:
                continue
            if key == "minItems" and child not in (0, 1):
                continue
            projected[key] = _anthropic_output_schema(child)
        return projected
    if isinstance(value, list):
        return [_anthropic_output_schema(child) for child in value]
    return value


def _anthropic_usage(
    response: dict[str, Any],
    model_id: str,
) -> llm.ProviderUsage:
    if "usage" not in response:
        return llm.MISSING_PROVIDER_USAGE
    usage = response["usage"]
    if not isinstance(usage, dict):
        raise llm.ProviderError("bad_response", "provider usage was not an object")
    values: dict[str, int] = {}
    for field in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        value = usage.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise llm.ProviderError(
                "bad_response",
                "provider token usage was invalid",
            )
        values[field] = value
    if "input_tokens" not in usage or "output_tokens" not in usage:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was incomplete",
        )
    try:
        cost = ai_catalog.recipe_usage_cost_usd_ticks(
            "anthropic",
            model_id,
            input_tokens=(
                values["input_tokens"]
                + values["cache_creation_input_tokens"]
                + values["cache_read_input_tokens"]
            ),
            output_tokens=values["output_tokens"],
        )
    except ValueError:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was invalid",
        ) from None
    return llm.ProviderUsage(cost_in_usd_ticks=cost, reported=True)


def _anthropic_output_text(response: dict[str, Any]) -> str:
    if response.get("type") != "message" or response.get("role") != "assistant":
        raise llm.ProviderError("bad_response", "Recipe response was not a message.")
    content = response.get("content")
    if not isinstance(content, list):
        raise llm.ProviderError("bad_response", "Recipe response omitted content.")
    stop_reason = response.get("stop_reason")
    refused = stop_reason == "refusal"
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            raise llm.ProviderError(
                "bad_response",
                "Recipe response contained an invalid content block.",
            )
        block_type = block["type"]
        if block_type == "refusal":
            refused = True
        elif block_type == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif block_type not in {"thinking", "redacted_thinking"}:
            raise llm.ProviderError(
                "bad_response",
                "Recipe response contained unsupported content.",
            )
    if refused:
        raise llm.ProviderError("moderation", "The provider declined this prompt.")
    if stop_reason != "end_turn":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response ended before completion.",
        )
    if len(texts) != 1 or not texts[0]:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained no complete text.",
        )
    return texts[0]


def _openai_usage(
    response: dict[str, Any],
    model_id: str,
) -> llm.ProviderUsage:
    if "usage" not in response:
        return llm.MISSING_PROVIDER_USAGE
    usage = response["usage"]
    if not isinstance(usage, dict):
        raise llm.ProviderError("bad_response", "provider usage was not an object")
    values: dict[str, int] = {}
    for field in ("input_tokens", "output_tokens"):
        value = usage.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise llm.ProviderError(
                "bad_response",
                "provider token usage was invalid",
            )
        values[field] = value
    try:
        cost = ai_catalog.recipe_usage_cost_usd_ticks(
            "openai",
            model_id,
            input_tokens=values["input_tokens"],
            output_tokens=values["output_tokens"],
        )
    except ValueError:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was invalid",
        ) from None
    return llm.ProviderUsage(cost_in_usd_ticks=cost, reported=True)


def _openai_output_text(response: dict[str, Any]) -> str:
    if response.get("object") != "response":
        raise llm.ProviderError("bad_response", "Recipe response was not a response.")
    if response.get("status") != "completed":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response ended before completion.",
        )
    output = response.get("output")
    if not isinstance(output, list):
        raise llm.ProviderError("bad_response", "Recipe response omitted output.")
    texts: list[str] = []
    refused = False
    messages = 0
    for item in output:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise llm.ProviderError(
                "bad_response",
                "Recipe response contained an invalid output item.",
            )
        item_type = item["type"]
        if item_type == "reasoning":
            continue
        if item_type != "message":
            raise llm.ProviderError(
                "bad_response",
                "Recipe response contained unsupported output.",
            )
        messages += 1
        if (
            item.get("role") != "assistant"
            or item.get("status") != "completed"
            or not isinstance(item.get("content"), list)
        ):
            raise llm.ProviderError(
                "bad_response",
                "Recipe response contained an incomplete message.",
            )
        for block in item["content"]:
            if not isinstance(block, dict) or not isinstance(block.get("type"), str):
                raise llm.ProviderError(
                    "bad_response",
                    "Recipe response contained an invalid content block.",
                )
            block_type = block["type"]
            if block_type == "refusal":
                refused = True
            elif block_type == "output_text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
            else:
                raise llm.ProviderError(
                    "bad_response",
                    "Recipe response contained unsupported content.",
                )
    if refused:
        raise llm.ProviderError("moderation", "The provider declined this prompt.")
    if messages != 1 or len(texts) != 1 or not texts[0]:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained no complete text.",
        )
    return texts[0]


_GEMINI_UNSUPPORTED_SCHEMA_KEYS = {
    "maxLength",
    "minLength",
    "pattern",
}


def _gemini_output_schema(value: object) -> object:
    """Project the recipe schema onto Gemini's documented JSON Schema subset."""

    if isinstance(value, dict):
        projected = {}
        for key, child in value.items():
            if key in _GEMINI_UNSUPPORTED_SCHEMA_KEYS:
                continue
            if key == "const":
                projected["enum"] = [_gemini_output_schema(child)]
                continue
            projected[key] = _gemini_output_schema(child)
        return projected
    if isinstance(value, list):
        return [_gemini_output_schema(child) for child in value]
    return value


def _gemini_usage(
    response: dict[str, Any],
    model_id: str,
) -> llm.ProviderUsage:
    if "usage" not in response:
        return llm.MISSING_PROVIDER_USAGE
    usage = response["usage"]
    if not isinstance(usage, dict):
        raise llm.ProviderError("bad_response", "provider usage was not an object")
    values: dict[str, int] = {}
    for field in (
        "total_input_tokens",
        "total_output_tokens",
        "total_thought_tokens",
    ):
        value = usage.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise llm.ProviderError(
                "bad_response",
                "provider token usage was invalid",
            )
        values[field] = value
    if "total_input_tokens" not in usage or "total_output_tokens" not in usage:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was incomplete",
        )
    try:
        cost = ai_catalog.recipe_usage_cost_usd_ticks(
            "gemini",
            model_id,
            input_tokens=values["total_input_tokens"],
            output_tokens=(
                values["total_output_tokens"] + values["total_thought_tokens"]
            ),
        )
    except ValueError:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was invalid",
        ) from None
    return llm.ProviderUsage(cost_in_usd_ticks=cost, reported=True)


def _gemini_output_text(response: dict[str, Any]) -> str:
    if response.get("object") != "interaction":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response was not an interaction.",
        )
    if response.get("status") != "completed":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response ended before completion.",
        )
    steps = response.get("steps")
    if not isinstance(steps, list):
        raise llm.ProviderError("bad_response", "Recipe response omitted steps.")
    texts: list[str] = []
    model_outputs = 0
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("type"), str):
            raise llm.ProviderError(
                "bad_response",
                "Recipe response contained an invalid step.",
            )
        step_type = step["type"]
        if step_type == "thought":
            if not isinstance(step.get("signature"), str):
                raise llm.ProviderError(
                    "bad_response",
                    "Recipe response contained an invalid thought step.",
                )
            summary = step.get("summary", [])
            if not isinstance(summary, list):
                raise llm.ProviderError(
                    "bad_response",
                    "Recipe response contained an invalid thought step.",
                )
            continue
        if step_type != "model_output":
            raise llm.ProviderError(
                "bad_response",
                "Recipe response contained unsupported output.",
            )
        model_outputs += 1
        content = step.get("content")
        if not isinstance(content, list):
            raise llm.ProviderError(
                "bad_response",
                "Recipe response omitted model content.",
            )
        for block in content:
            if (
                not isinstance(block, dict)
                or block.get("type") != "text"
                or not isinstance(block.get("text"), str)
            ):
                raise llm.ProviderError(
                    "bad_response",
                    "Recipe response contained unsupported content.",
                )
            texts.append(block["text"])
    if model_outputs < 1 or not texts or not all(texts):
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained no complete text.",
        )
    return "".join(texts)


_JSON_OBJECT_RECIPE_EXAMPLE = (
    '{"schema_version":1,"name":"Example","density":"balanced",'
    '"background":"#000000","palette":["#FF0000","#0000FF"],'
    '"layers":[{"kind":"sweep","color_index":0,'
    '"secondary_color_index":1,"speed":1,"phase":0.0,'
    '"direction_degrees":0.0,"center_x":0.5,"center_y":0.5,'
    '"scale":1.0,"width":0.4,"trail":0.5,"count":2,'
    '"intensity":1.0,"seed":7}]}'
)


def _json_object_recipe_system_prompt(system_prompt: str) -> str:
    return (
        f"{system_prompt}\n"
        "Return exactly one JSON object and no surrounding text. "
        "Use this compact shape example:\n"
        f"{_JSON_OBJECT_RECIPE_EXAMPLE}"
    )


def _kimi_usage(
    response: dict[str, Any],
    model_id: str,
) -> llm.ProviderUsage:
    if "usage" not in response:
        return llm.MISSING_PROVIDER_USAGE
    usage = response["usage"]
    if not isinstance(usage, dict):
        raise llm.ProviderError("bad_response", "provider usage was not an object")
    values: dict[str, int] = {}
    for field in ("prompt_tokens", "completion_tokens", "cached_tokens"):
        value = usage.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise llm.ProviderError(
                "bad_response",
                "provider token usage was invalid",
            )
        values[field] = value
    if "prompt_tokens" not in usage or "completion_tokens" not in usage:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was incomplete",
        )
    if values["cached_tokens"] > values["prompt_tokens"]:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was invalid",
        )
    try:
        cost = ai_catalog.recipe_usage_cost_usd_ticks(
            "moonshot",
            model_id,
            input_tokens=values["prompt_tokens"],
            output_tokens=values["completion_tokens"],
            cached_input_tokens=values["cached_tokens"],
        )
    except ValueError:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was invalid",
        ) from None
    return llm.ProviderUsage(cost_in_usd_ticks=cost, reported=True)


def _kimi_output_text(response: dict[str, Any]) -> str:
    if response.get("object") != "chat.completion":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response was not a chat completion.",
        )
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained an ambiguous result.",
        )
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("index") != 0:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained an invalid choice.",
        )
    if choice.get("finish_reason") != "stop":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response ended before completion.",
        )
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response omitted the assistant message.",
        )
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained no complete text.",
        )
    return content


def _deepseek_usage(
    response: dict[str, Any],
    model_id: str,
) -> llm.ProviderUsage:
    if "usage" not in response:
        return llm.MISSING_PROVIDER_USAGE
    usage = response["usage"]
    if not isinstance(usage, dict):
        raise llm.ProviderError("bad_response", "provider usage was not an object")
    fields = (
        "prompt_tokens",
        "completion_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    )
    values: dict[str, int] = {}
    for field in fields:
        value = usage.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise llm.ProviderError(
                "bad_response",
                "provider token usage was invalid",
            )
        values[field] = value
    if values["prompt_tokens"] != (
        values["prompt_cache_hit_tokens"] + values["prompt_cache_miss_tokens"]
    ):
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was inconsistent",
        )
    try:
        cost = ai_catalog.recipe_usage_cost_usd_ticks(
            "deepseek",
            model_id,
            input_tokens=values["prompt_tokens"],
            output_tokens=values["completion_tokens"],
            cached_input_tokens=values["prompt_cache_hit_tokens"],
        )
    except ValueError:
        raise llm.ProviderError(
            "bad_response",
            "provider token usage was invalid",
        ) from None
    return llm.ProviderUsage(cost_in_usd_ticks=cost, reported=True)


def _deepseek_output_text(response: dict[str, Any]) -> str:
    if response.get("object") != "chat.completion":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response was not a chat completion.",
        )
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained an ambiguous result.",
        )
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("index") != 0:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained an invalid choice.",
        )
    finish_reason = choice.get("finish_reason")
    if finish_reason == "content_filter":
        raise llm.ProviderError(
            "moderation",
            "The provider declined the prompt.",
        )
    if finish_reason == "insufficient_system_resource":
        raise llm.ProviderError(
            "unavailable",
            "The provider could not complete the request.",
        )
    if finish_reason != "stop":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response ended before completion.",
        )
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise llm.ProviderError(
            "bad_response",
            "Recipe response omitted the assistant message.",
        )
    content = message.get("content")
    if not isinstance(content, str) or not content:
        raise llm.ProviderError(
            "bad_response",
            "Recipe response contained no complete text.",
        )
    return content


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


class AnthropicRecipeProvider:
    """Exactly one Anthropic Messages request for one validated recipe."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = "claude-sonnet-5",
        transport=None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise llm.ProviderError("config", "API credential is missing.")
        try:
            normalized = ai_catalog.validate_provider_model("anthropic", model_id)
            metadata = ai_catalog.provider_model_metadata("anthropic", normalized)
        except ValueError:
            raise llm.ProviderError(
                "config",
                "API recipe model is unavailable.",
            ) from None
        assert isinstance(normalized, str)
        self._model_id = normalized
        self._max_output_tokens = int(metadata["max_output_tokens"])
        self._reasoning_effort = str(metadata["reasoning_effort"])
        self._api_key = api_key
        self._transport = (
            llm._provider_json_request if transport is None else transport
        )

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
            "max_tokens": self._max_output_tokens,
            "stream": False,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "effort": self._reasoning_effort,
                "format": {
                    "type": "json_schema",
                    "schema": _anthropic_output_schema(schema),
                },
            },
        }
        response = llm._call_provider(
            self._transport,
            llm.ANTHROPIC_MESSAGES_TRANSPORT,
            payload,
            self._api_key,
            deadline,
        )
        usage = _anthropic_usage(response, self._model_id)
        failure: llm.ProviderError | None = None
        try:
            recipe = _validated_recipe_text(_anthropic_output_text(response))
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
            raise llm.ProviderError(
                "bad_response",
                "Recipe output failed validation.",
                usage=usage,
            )
        if cancelled():
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
            provider="anthropic",
            model_id=self._model_id,
            usage=usage_value,
        )


class OpenAIRecipeProvider:
    """Exactly one OpenAI Responses request for one validated recipe."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = "gpt-5.6-sol",
        transport=None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise llm.ProviderError("config", "API credential is missing.")
        try:
            normalized = ai_catalog.validate_provider_model("openai", model_id)
            metadata = ai_catalog.provider_model_metadata("openai", normalized)
        except ValueError:
            raise llm.ProviderError(
                "config",
                "API recipe model is unavailable.",
            ) from None
        assert isinstance(normalized, str)
        self._model_id = normalized
        self._max_output_tokens = int(metadata["max_output_tokens"])
        self._reasoning_effort = str(metadata["reasoning_effort"])
        self._api_key = api_key
        self._transport = (
            llm._provider_json_request if transport is None else transport
        )

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
            "stream": False,
            "max_output_tokens": self._max_output_tokens,
            "reasoning": {"effort": self._reasoning_effort},
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
            llm.OPENAI_RESPONSES_TRANSPORT,
            payload,
            self._api_key,
            deadline,
        )
        usage = _openai_usage(response, self._model_id)
        failure: llm.ProviderError | None = None
        try:
            recipe = _validated_recipe_text(_openai_output_text(response))
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
            raise llm.ProviderError(
                "bad_response",
                "Recipe output failed validation.",
                usage=usage,
            )
        if cancelled():
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
            provider="openai",
            model_id=self._model_id,
            usage=usage_value,
        )


class GeminiRecipeProvider:
    """Exactly one Gemini Interactions request for one validated recipe."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = "gemini-3.6-flash",
        transport=None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise llm.ProviderError("config", "API credential is missing.")
        try:
            normalized = ai_catalog.validate_provider_model("gemini", model_id)
            metadata = ai_catalog.provider_model_metadata("gemini", normalized)
        except ValueError:
            raise llm.ProviderError(
                "config",
                "API recipe model is unavailable.",
            ) from None
        assert isinstance(normalized, str)
        self._model_id = normalized
        self._max_output_tokens = int(metadata["max_output_tokens"])
        self._thinking_level = str(metadata["reasoning_effort"])
        self._api_key = api_key
        self._transport = (
            llm._provider_json_request if transport is None else transport
        )

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
            "input": prompt,
            "system_instruction": system_prompt,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": _gemini_output_schema(schema),
            },
            "stream": False,
            "store": False,
            "background": False,
            "generation_config": {
                "max_output_tokens": self._max_output_tokens,
                "thinking_level": self._thinking_level,
                "thinking_summaries": "none",
            },
        }
        response = llm._call_provider(
            self._transport,
            llm.GEMINI_INTERACTIONS_TRANSPORT,
            payload,
            self._api_key,
            deadline,
        )
        usage = _gemini_usage(response, self._model_id)
        failure: llm.ProviderError | None = None
        try:
            recipe = _validated_recipe_text(_gemini_output_text(response))
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
            raise llm.ProviderError(
                "bad_response",
                "Recipe output failed validation.",
                usage=usage,
            )
        if cancelled():
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
            provider="gemini",
            model_id=self._model_id,
            usage=usage_value,
        )


class KimiRecipeProvider:
    """Exactly one Moonshot Chat Completions request for one recipe."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = "kimi-k3",
        transport=None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise llm.ProviderError("config", "API credential is missing.")
        try:
            normalized = ai_catalog.validate_provider_model("moonshot", model_id)
            metadata = ai_catalog.provider_model_metadata("moonshot", normalized)
        except ValueError:
            raise llm.ProviderError(
                "config",
                "API recipe model is unavailable.",
            ) from None
        assert isinstance(normalized, str)
        self._model_id = normalized
        self._max_output_tokens = int(metadata["max_output_tokens"])
        self._reasoning_effort = str(metadata["reasoning_effort"])
        self._api_key = api_key
        self._transport = (
            llm._provider_json_request if transport is None else transport
        )

    def generate(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> RecipeResult:
        prompt, system_prompt, _schema = _request_parts(request)
        _check_start(deadline, cancelled)
        payload = {
            "model": self._model_id,
            "messages": [
                {
                    "role": "system",
                    "content": _json_object_recipe_system_prompt(system_prompt),
                },
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": self._max_output_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
            "reasoning_effort": self._reasoning_effort,
        }
        response = llm._call_provider(
            self._transport,
            llm.MOONSHOT_CHAT_COMPLETIONS_TRANSPORT,
            payload,
            self._api_key,
            deadline,
        )
        usage = _kimi_usage(response, self._model_id)
        failure: llm.ProviderError | None = None
        try:
            recipe = _validated_recipe_text(_kimi_output_text(response))
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
            raise llm.ProviderError(
                "bad_response",
                "Recipe output failed validation.",
                usage=usage,
            )
        if cancelled():
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
            provider="moonshot",
            model_id=self._model_id,
            usage=usage_value,
        )


class DeepSeekRecipeProvider:
    """Exactly one DeepSeek Chat Completions request for one recipe."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = "deepseek-v4-pro",
        transport=None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise llm.ProviderError("config", "API credential is missing.")
        try:
            normalized = ai_catalog.validate_provider_model("deepseek", model_id)
            metadata = ai_catalog.provider_model_metadata("deepseek", normalized)
        except ValueError:
            raise llm.ProviderError(
                "config",
                "API recipe model is unavailable.",
            ) from None
        assert isinstance(normalized, str)
        self._model_id = normalized
        self._max_output_tokens = int(metadata["max_output_tokens"])
        self._thinking = str(metadata["thinking"])
        self._api_key = api_key
        self._transport = (
            llm._provider_json_request if transport is None else transport
        )

    def generate(
        self,
        request: RecipeRequest,
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> RecipeResult:
        prompt, system_prompt, _schema = _request_parts(request)
        _check_start(deadline, cancelled)
        payload = {
            "model": self._model_id,
            "messages": [
                {
                    "role": "system",
                    "content": _json_object_recipe_system_prompt(system_prompt),
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self._max_output_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
            "thinking": {"type": self._thinking},
        }
        response = llm._call_provider(
            self._transport,
            llm.DEEPSEEK_CHAT_COMPLETIONS_TRANSPORT,
            payload,
            self._api_key,
            deadline,
        )
        usage = _deepseek_usage(response, self._model_id)
        failure: llm.ProviderError | None = None
        try:
            recipe = _validated_recipe_text(_deepseek_output_text(response))
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
            raise llm.ProviderError(
                "bad_response",
                "Recipe output failed validation.",
                usage=usage,
            )
        if cancelled():
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
            provider="deepseek",
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
            backend="ollama",
            provider="ollama",
            model_id=self._model.model_id,
            usage=None,
        )


__all__ = [
    "AnthropicRecipeProvider",
    "DeepSeekRecipeProvider",
    "GeminiRecipeProvider",
    "KimiRecipeProvider",
    "LOCAL_OUTPUT_TOKENS",
    "MAX_RECIPE_PROMPT_CHARS",
    "OllamaRecipeProvider",
    "OpenAIRecipeProvider",
    "RecipeProvider",
    "RecipeRequest",
    "RecipeResult",
    "XaiRecipeProvider",
]
