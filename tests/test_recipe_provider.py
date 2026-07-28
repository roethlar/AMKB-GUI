from __future__ import annotations

import json
import time
import unittest

from am_configurator import ai_catalog, llm, procedural
from am_configurator.ollama_client import OllamaModel
from am_configurator.recipe_inference import build_ollama_recipe_payload
from am_configurator.recipe_provider import (
    AnthropicRecipeProvider,
    GeminiRecipeProvider,
    KimiRecipeProvider,
    OllamaRecipeProvider,
    OpenAIRecipeProvider,
    RecipeRequest,
    XaiRecipeProvider,
)


def _recipe() -> dict:
    return {
        "schema_version": 1,
        "name": "Blue sweep",
        "density": "balanced",
        "background": "#000008",
        "palette": ["#0066FF", "#00FFFF"],
        "layers": [
            {
                "kind": "sweep",
                "color_index": 0,
                "secondary_color_index": 1,
                "speed": 1,
                "phase": 0.0,
                "direction_degrees": 0.0,
                "center_x": 0.5,
                "center_y": 0.5,
                "scale": 1.0,
                "width": 0.4,
                "trail": 0.5,
                "count": 2,
                "intensity": 1.0,
                "seed": 7,
            }
        ],
    }


def _request() -> RecipeRequest:
    return RecipeRequest(
        prompt="A bright blue scanner",
        width=18,
        height=7,
        frame_count=200,
        density_default="balanced",
    )


def _xai_response(recipe: dict, *, cost: int | None = 123) -> dict:
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps(recipe)}
                ],
            }
        ]
    }
    if cost is not None:
        response["usage"] = {"cost_in_usd_ticks": cost}
    return response


def _anthropic_response(
    recipe: dict,
    *,
    stop_reason: str = "end_turn",
    usage: dict | None = None,
) -> dict:
    response = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": json.dumps(recipe)}],
        "stop_reason": stop_reason,
    }
    if usage is not None:
        response["usage"] = usage
    return response


def _openai_response(
    recipe: dict,
    *,
    status: str = "completed",
    usage: dict | None = None,
) -> dict:
    response = {
        "object": "response",
        "status": status,
        "error": None,
        "incomplete_details": (
            None if status == "completed" else {"reason": "max_output_tokens"}
        ),
        "output": [
            {"type": "reasoning", "id": "rs_test", "summary": []},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(recipe),
                        "annotations": [],
                    }
                ],
            },
        ],
    }
    if usage is not None:
        response["usage"] = usage
    return response


def _gemini_response(
    recipe: dict,
    *,
    status: str = "completed",
    usage: dict | None = None,
) -> dict:
    response = {
        "object": "interaction",
        "status": status,
        "steps": [
            {
                "type": "thought",
                "signature": "opaque-provider-signature",
                "summary": [],
            },
            {
                "type": "model_output",
                "content": [{"type": "text", "text": json.dumps(recipe)}],
            },
        ],
    }
    if usage is not None:
        response["usage"] = usage
    return response


def _kimi_response(
    recipe: dict,
    *,
    finish_reason: str = "stop",
    usage: dict | None = None,
) -> dict:
    response = {
        "id": "chatcmpl_test",
        "object": "chat.completion",
        "model": "kimi-k3",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(recipe),
                    "reasoning_content": "provider-private-reasoning",
                },
            }
        ],
    }
    if usage is not None:
        response["usage"] = usage
    return response


class XaiRecipeProviderTests(unittest.TestCase):
    def test_curated_api_recipe_cost_ceiling_uses_integer_ticks(self) -> None:
        self.assertEqual(
            747_520_000,
            ai_catalog.recipe_max_cost_usd_ticks("xai", "grok-4.5"),
        )
        with self.assertRaises(ValueError):
            ai_catalog.recipe_max_cost_usd_ticks("other", "grok-4.5")

    def test_one_strict_call_returns_validated_recipe_and_exact_usage(self) -> None:
        calls: list[tuple] = []

        def transport(url, payload, api_key, deadline):
            calls.append((url, payload, api_key, deadline))
            return _xai_response(_recipe())

        provider = XaiRecipeProvider("sk-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(calls))
        url, payload, api_key, _deadline = calls[0]
        self.assertEqual(llm.XAI_RESPONSES_URL, url)
        self.assertEqual("sk-private", api_key)
        self.assertEqual("grok-4.5", payload["model"])
        self.assertIs(payload["store"], False)
        self.assertEqual(1536, payload["max_output_tokens"])
        self.assertEqual(
            procedural.recipe_schema(), payload["text"]["format"]["schema"]
        )
        self.assertIs(payload["text"]["format"]["strict"], True)
        self.assertIn("18x7", payload["input"][0]["content"])
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("api", result.backend)
        self.assertEqual("xai", result.provider)
        self.assertEqual("grok-4.5", result.model_id)
        self.assertEqual({"cost_in_usd_ticks": 123}, result.usage)

    def test_cancelled_or_invalid_output_never_retries_or_leaks_content(self) -> None:
        calls = 0

        def transport(url, payload, api_key, deadline):
            nonlocal calls
            calls += 1
            return _xai_response({"raw_secret": "provider-body-secret"}, cost=222)

        provider = XaiRecipeProvider("sk-private", transport=transport)
        with self.assertRaises(llm.ProviderError) as cancelled:
            provider.generate(_request(), time.monotonic() + 10, lambda: True)
        self.assertEqual(0, calls)
        self.assertNotIn("sk-private", str(cancelled.exception))

        with self.assertRaises(llm.ProviderError) as invalid:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual(1, calls)
        self.assertEqual("bad_response", invalid.exception.code)
        self.assertEqual(222, invalid.exception.usage.cost_in_usd_ticks)
        self.assertNotIn("provider-body-secret", str(invalid.exception))

    def test_cancellation_after_the_one_paid_call_preserves_exact_usage(self) -> None:
        checks = iter((False, True))
        provider = XaiRecipeProvider(
            "sk-private",
            transport=lambda *_args: _xai_response(_recipe(), cost=456),
        )

        with self.assertRaises(llm.ProviderError) as captured:
            provider.generate(
                _request(),
                time.monotonic() + 10,
                lambda: next(checks),
            )

        self.assertEqual("unavailable", captured.exception.code)
        self.assertEqual(456, captured.exception.usage.cost_in_usd_ticks)


class AnthropicRecipeProviderTests(unittest.TestCase):
    def test_current_catalog_and_one_messages_call_use_the_strict_contract(
        self,
    ) -> None:
        catalog = ai_catalog.catalog_view()["providers"]["anthropic"]
        self.assertEqual("claude-sonnet-5", catalog["default_model"])
        self.assertEqual(
            ["claude-sonnet-5", "claude-opus-5"],
            [model["id"] for model in catalog["models"]],
        )
        self.assertTrue(
            all(model["reasoning_effort"] == "medium" for model in catalog["models"])
        )
        self.assertEqual(
            808_960_000,
            ai_catalog.recipe_max_cost_usd_ticks(
                "anthropic",
                "claude-sonnet-5",
            ),
        )

        calls: list[tuple] = []
        usage = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }

        def transport(spec, payload, api_key, deadline):
            calls.append((spec, payload, api_key, deadline))
            return _anthropic_response(_recipe(), usage=usage)

        provider = AnthropicRecipeProvider("anthropic-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(calls))
        spec, payload, api_key, _deadline = calls[0]
        self.assertIs(llm.ANTHROPIC_MESSAGES_TRANSPORT, spec)
        self.assertEqual("anthropic-private", api_key)
        self.assertEqual("claude-sonnet-5", payload["model"])
        self.assertEqual(1536, payload["max_tokens"])
        self.assertIs(payload["stream"], False)
        self.assertIn("18x7", payload["system"])
        self.assertEqual(
            [{"role": "user", "content": _request().prompt}],
            payload["messages"],
        )
        self.assertEqual("medium", payload["output_config"]["effort"])
        output_format = payload["output_config"]["format"]
        self.assertEqual("json_schema", output_format["type"])
        sent_schema = output_format["schema"]
        self.assertEqual(False, sent_schema["additionalProperties"])

        def schema_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from schema_keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from schema_keys(child)

        sent_keys = set(schema_keys(sent_schema))
        self.assertTrue(
            {
                "minimum",
                "maximum",
                "multipleOf",
                "minLength",
                "maxLength",
                "maxItems",
            }.isdisjoint(sent_keys)
        )
        self.assertIn("maximum", set(schema_keys(procedural.recipe_schema())))
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("api", result.backend)
        self.assertEqual("anthropic", result.provider)
        self.assertEqual("claude-sonnet-5", result.model_id)
        self.assertEqual({"cost_in_usd_ticks": 40_000_000}, result.usage)

    def test_missing_usage_succeeds_and_malformed_usage_fails_once(self) -> None:
        calls = 0
        responses = iter(
            (
                _anthropic_response(_recipe()),
                _anthropic_response(
                    _recipe(),
                    usage={"input_tokens": True, "output_tokens": 10},
                ),
            )
        )

        def transport(*_args):
            nonlocal calls
            calls += 1
            return next(responses)

        provider = AnthropicRecipeProvider("anthropic-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertIsNone(result.usage)

        with self.assertRaises(llm.ProviderError) as captured:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", captured.exception.code)
        self.assertEqual(2, calls)
        self.assertNotIn("anthropic-private", str(captured.exception))

    def test_refusal_and_incomplete_stop_are_typed_and_never_retried(self) -> None:
        usage = {"input_tokens": 100, "output_tokens": 20}
        responses = (
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "refusal",
                        "refusal": "provider-body-secret",
                    }
                ],
                "stop_reason": "refusal",
                "usage": usage,
            },
            _anthropic_response(
                _recipe(),
                stop_reason="max_tokens",
                usage=usage,
            ),
        )
        expected_codes = ("moderation", "bad_response")
        for response, code in zip(responses, expected_codes, strict=True):
            calls = 0

            def transport(*_args):
                nonlocal calls
                calls += 1
                return response

            provider = AnthropicRecipeProvider(
                "anthropic-private",
                transport=transport,
            )
            with self.subTest(code=code):
                with self.assertRaises(llm.ProviderError) as captured:
                    provider.generate(
                        _request(),
                        time.monotonic() + 10,
                        lambda: False,
                    )
                self.assertEqual(code, captured.exception.code)
                self.assertEqual(1, calls)
                self.assertTrue(captured.exception.usage.reported)
                self.assertNotIn("provider-body-secret", str(captured.exception))

    def test_cancellation_and_invalid_recipe_never_make_a_paid_retry(self) -> None:
        calls = 0

        def invalid_transport(*_args):
            nonlocal calls
            calls += 1
            return _anthropic_response(
                {"provider-body-secret": "never expose this"},
                usage={"input_tokens": 100, "output_tokens": 20},
            )

        provider = AnthropicRecipeProvider(
            "anthropic-private",
            transport=invalid_transport,
        )
        with self.assertRaises(llm.ProviderError) as cancelled:
            provider.generate(_request(), time.monotonic() + 10, lambda: True)
        self.assertEqual("unavailable", cancelled.exception.code)
        self.assertEqual(0, calls)

        with self.assertRaises(llm.ProviderError) as invalid:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", invalid.exception.code)
        self.assertEqual(1, calls)
        self.assertNotIn("provider-body-secret", str(invalid.exception))

        checks = iter((False, True))
        post_call = AnthropicRecipeProvider(
            "anthropic-private",
            transport=lambda *_args: _anthropic_response(
                _recipe(),
                usage={"input_tokens": 100, "output_tokens": 20},
            ),
        )
        with self.assertRaises(llm.ProviderError) as late:
            post_call.generate(
                _request(),
                time.monotonic() + 10,
                lambda: next(checks),
            )
        self.assertEqual("unavailable", late.exception.code)
        self.assertTrue(late.exception.usage.reported)


class OpenAIRecipeProviderTests(unittest.TestCase):
    def test_current_catalog_and_one_responses_call_use_the_strict_contract(
        self,
    ) -> None:
        catalog = ai_catalog.catalog_view()["providers"]["openai"]
        self.assertEqual("gpt-5.6-sol", catalog["default_model"])
        self.assertEqual(
            ["gpt-5.6-sol", "gpt-5.6-terra"],
            [model["id"] for model in catalog["models"]],
        )
        self.assertTrue(
            all(model["reasoning_effort"] == "medium" for model in catalog["models"])
        )
        self.assertEqual(
            2_099_200_000,
            ai_catalog.recipe_max_cost_usd_ticks("openai", "gpt-5.6-sol"),
        )

        calls: list[tuple] = []
        usage = {
            "input_tokens": 1000,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 0,
            },
            "output_tokens": 200,
            "output_tokens_details": {"reasoning_tokens": 50},
            "total_tokens": 1200,
        }

        def transport(spec, payload, api_key, deadline):
            calls.append((spec, payload, api_key, deadline))
            return _openai_response(_recipe(), usage=usage)

        provider = OpenAIRecipeProvider("openai-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(calls))
        spec, payload, api_key, _deadline = calls[0]
        self.assertIs(llm.OPENAI_RESPONSES_TRANSPORT, spec)
        self.assertEqual("openai-private", api_key)
        self.assertEqual("gpt-5.6-sol", payload["model"])
        self.assertIs(payload["store"], False)
        self.assertIs(payload["stream"], False)
        self.assertEqual(1536, payload["max_output_tokens"])
        self.assertEqual({"effort": "medium"}, payload["reasoning"])
        self.assertIn("18x7", payload["input"][0]["content"])
        self.assertEqual(_request().prompt, payload["input"][1]["content"])
        output_format = payload["text"]["format"]
        self.assertEqual("json_schema", output_format["type"])
        self.assertEqual("animation_recipe", output_format["name"])
        self.assertIs(output_format["strict"], True)
        self.assertEqual(procedural.recipe_schema(), output_format["schema"])
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("api", result.backend)
        self.assertEqual("openai", result.provider)
        self.assertEqual("gpt-5.6-sol", result.model_id)
        self.assertEqual({"cost_in_usd_ticks": 110_000_000}, result.usage)

    def test_missing_usage_succeeds_and_malformed_usage_fails_once(self) -> None:
        calls = 0
        responses = iter(
            (
                _openai_response(_recipe()),
                _openai_response(
                    _recipe(),
                    usage={"input_tokens": True, "output_tokens": 10},
                ),
            )
        )

        def transport(*_args):
            nonlocal calls
            calls += 1
            return next(responses)

        provider = OpenAIRecipeProvider("openai-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertIsNone(result.usage)

        with self.assertRaises(llm.ProviderError) as captured:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", captured.exception.code)
        self.assertEqual(2, calls)
        self.assertNotIn("openai-private", str(captured.exception))

    def test_refusal_and_incomplete_response_are_typed_and_never_retried(
        self,
    ) -> None:
        usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
        refusal = _openai_response(_recipe(), usage=usage)
        refusal["output"] = [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "refusal",
                        "refusal": "provider-body-secret",
                    }
                ],
            }
        ]
        incomplete = _openai_response(
            _recipe(),
            status="incomplete",
            usage=usage,
        )
        for response, code in (
            (refusal, "moderation"),
            (incomplete, "bad_response"),
        ):
            calls = 0

            def transport(*_args):
                nonlocal calls
                calls += 1
                return response

            provider = OpenAIRecipeProvider("openai-private", transport=transport)
            with self.subTest(code=code):
                with self.assertRaises(llm.ProviderError) as captured:
                    provider.generate(
                        _request(),
                        time.monotonic() + 10,
                        lambda: False,
                    )
                self.assertEqual(code, captured.exception.code)
                self.assertEqual(1, calls)
                self.assertTrue(captured.exception.usage.reported)
                self.assertNotIn("provider-body-secret", str(captured.exception))

    def test_cancellation_and_invalid_recipe_never_make_a_paid_retry(self) -> None:
        calls = 0

        def invalid_transport(*_args):
            nonlocal calls
            calls += 1
            return _openai_response(
                {"provider-body-secret": "never expose this"},
                usage={"input_tokens": 100, "output_tokens": 20},
            )

        provider = OpenAIRecipeProvider(
            "openai-private",
            transport=invalid_transport,
        )
        with self.assertRaises(llm.ProviderError) as cancelled:
            provider.generate(_request(), time.monotonic() + 10, lambda: True)
        self.assertEqual("unavailable", cancelled.exception.code)
        self.assertEqual(0, calls)

        with self.assertRaises(llm.ProviderError) as invalid:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", invalid.exception.code)
        self.assertEqual(1, calls)
        self.assertNotIn("provider-body-secret", str(invalid.exception))

        checks = iter((False, True))
        post_call = OpenAIRecipeProvider(
            "openai-private",
            transport=lambda *_args: _openai_response(
                _recipe(),
                usage={"input_tokens": 100, "output_tokens": 20},
            ),
        )
        with self.assertRaises(llm.ProviderError) as late:
            post_call.generate(
                _request(),
                time.monotonic() + 10,
                lambda: next(checks),
            )
        self.assertEqual("unavailable", late.exception.code)
        self.assertTrue(late.exception.usage.reported)


class GeminiRecipeProviderTests(unittest.TestCase):
    def test_current_catalog_and_one_interactions_call_use_the_schema_contract(
        self,
    ) -> None:
        catalog = ai_catalog.catalog_view()["providers"]["gemini"]
        self.assertEqual("gemini-3.6-flash", catalog["default_model"])
        self.assertEqual(
            ["gemini-3.6-flash", "gemini-3.5-flash-lite"],
            [model["id"] for model in catalog["models"]],
        )
        self.assertEqual(
            ["medium", "minimal"],
            [model["reasoning_effort"] for model in catalog["models"]],
        )
        self.assertEqual(
            606_720_000,
            ai_catalog.recipe_max_cost_usd_ticks("gemini", "gemini-3.6-flash"),
        )

        calls: list[tuple] = []
        usage = {
            "total_input_tokens": 1000,
            "total_output_tokens": 200,
            "total_thought_tokens": 50,
            "total_tokens": 1250,
        }

        def transport(spec, payload, api_key, deadline):
            calls.append((spec, payload, api_key, deadline))
            return _gemini_response(_recipe(), usage=usage)

        provider = GeminiRecipeProvider("gemini-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(calls))
        spec, payload, api_key, _deadline = calls[0]
        self.assertIs(llm.GEMINI_INTERACTIONS_TRANSPORT, spec)
        self.assertEqual("gemini-private", api_key)
        self.assertEqual("gemini-3.6-flash", payload["model"])
        self.assertIs(payload["store"], False)
        self.assertIs(payload["stream"], False)
        self.assertIs(payload["background"], False)
        self.assertEqual(_request().prompt, payload["input"])
        self.assertIn("18x7", payload["system_instruction"])
        self.assertEqual(
            {
                "max_output_tokens": 1536,
                "thinking_level": "medium",
                "thinking_summaries": "none",
            },
            payload["generation_config"],
        )
        response_format = payload["response_format"]
        self.assertEqual("text", response_format["type"])
        self.assertEqual("application/json", response_format["mime_type"])
        projected_schema = response_format["schema"]
        serialized_schema = json.dumps(projected_schema, sort_keys=True)
        self.assertNotIn('"pattern"', serialized_schema)
        self.assertNotIn('"const"', serialized_schema)
        self.assertEqual(
            [1],
            projected_schema["properties"]["schema_version"]["enum"],
        )
        self.assertEqual(
            6,
            projected_schema["properties"]["layers"]["maxItems"],
        )
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("api", result.backend)
        self.assertEqual("gemini", result.provider)
        self.assertEqual("gemini-3.6-flash", result.model_id)
        self.assertEqual({"cost_in_usd_ticks": 33_750_000}, result.usage)

    def test_lite_model_sends_its_documented_minimal_thinking_level(self) -> None:
        calls: list[dict] = []

        def transport(_spec, payload, _api_key, _deadline):
            calls.append(payload)
            return _gemini_response(_recipe())

        provider = GeminiRecipeProvider(
            "gemini-private",
            model_id="gemini-3.5-flash-lite",
            transport=transport,
        )
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(calls))
        self.assertEqual(
            "minimal",
            calls[0]["generation_config"]["thinking_level"],
        )
        self.assertEqual("gemini-3.5-flash-lite", result.model_id)

    def test_missing_usage_succeeds_and_malformed_usage_fails_once(self) -> None:
        calls = 0
        responses = iter(
            (
                _gemini_response(_recipe()),
                _gemini_response(
                    _recipe(),
                    usage={
                        "total_input_tokens": True,
                        "total_output_tokens": 10,
                    },
                ),
            )
        )

        def transport(*_args):
            nonlocal calls
            calls += 1
            return next(responses)

        provider = GeminiRecipeProvider("gemini-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertIsNone(result.usage)

        with self.assertRaises(llm.ProviderError) as captured:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", captured.exception.code)
        self.assertEqual(2, calls)
        self.assertNotIn("gemini-private", str(captured.exception))

    def test_noncompleted_or_unsupported_output_fails_once_without_body_text(
        self,
    ) -> None:
        usage = {
            "total_input_tokens": 100,
            "total_output_tokens": 20,
            "total_thought_tokens": 5,
        }
        failed = _gemini_response(
            _recipe(),
            status="failed",
            usage=usage,
        )
        failed["error"] = {"message": "provider-body-secret"}
        unsupported = _gemini_response(_recipe(), usage=usage)
        unsupported["steps"] = [
            {
                "type": "function_call",
                "name": "provider-body-secret",
                "arguments": {},
            }
        ]
        for response in (failed, unsupported):
            calls = 0

            def transport(*_args):
                nonlocal calls
                calls += 1
                return response

            provider = GeminiRecipeProvider(
                "gemini-private",
                transport=transport,
            )
            with self.subTest(status=response["status"]):
                with self.assertRaises(llm.ProviderError) as captured:
                    provider.generate(
                        _request(),
                        time.monotonic() + 10,
                        lambda: False,
                    )
                self.assertEqual("bad_response", captured.exception.code)
                self.assertEqual(1, calls)
                self.assertTrue(captured.exception.usage.reported)
                self.assertNotIn("provider-body-secret", str(captured.exception))

    def test_cancellation_and_invalid_recipe_never_make_a_paid_retry(self) -> None:
        calls = 0

        def invalid_transport(*_args):
            nonlocal calls
            calls += 1
            return _gemini_response(
                {"provider-body-secret": "never expose this"},
                usage={
                    "total_input_tokens": 100,
                    "total_output_tokens": 20,
                    "total_thought_tokens": 5,
                },
            )

        provider = GeminiRecipeProvider(
            "gemini-private",
            transport=invalid_transport,
        )
        with self.assertRaises(llm.ProviderError) as cancelled:
            provider.generate(_request(), time.monotonic() + 10, lambda: True)
        self.assertEqual("unavailable", cancelled.exception.code)
        self.assertEqual(0, calls)

        with self.assertRaises(llm.ProviderError) as invalid:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", invalid.exception.code)
        self.assertEqual(1, calls)
        self.assertNotIn("provider-body-secret", str(invalid.exception))

        checks = iter((False, True))
        post_call = GeminiRecipeProvider(
            "gemini-private",
            transport=lambda *_args: _gemini_response(
                _recipe(),
                usage={
                    "total_input_tokens": 100,
                    "total_output_tokens": 20,
                    "total_thought_tokens": 5,
                },
            ),
        )
        with self.assertRaises(llm.ProviderError) as late:
            post_call.generate(
                _request(),
                time.monotonic() + 10,
                lambda: next(checks),
            )
        self.assertEqual("unavailable", late.exception.code)
        self.assertTrue(late.exception.usage.reported)


class KimiRecipeProviderTests(unittest.TestCase):
    def test_current_catalog_and_one_chat_call_use_json_object_contract(
        self,
    ) -> None:
        catalog = ai_catalog.catalog_view()["providers"]["moonshot"]
        self.assertEqual("kimi-k3", catalog["default_model"])
        self.assertEqual(["kimi-k3"], [model["id"] for model in catalog["models"]])
        self.assertEqual("max", catalog["models"][0]["reasoning_effort"])
        self.assertEqual(
            1_213_440_000,
            ai_catalog.recipe_max_cost_usd_ticks("moonshot", "kimi-k3"),
        )

        calls: list[tuple] = []
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 250,
            "total_tokens": 1250,
            "cached_tokens": 400,
        }

        def transport(spec, payload, api_key, deadline):
            calls.append((spec, payload, api_key, deadline))
            return _kimi_response(_recipe(), usage=usage)

        provider = KimiRecipeProvider("moonshot-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(calls))
        spec, payload, api_key, _deadline = calls[0]
        self.assertIs(llm.MOONSHOT_CHAT_COMPLETIONS_TRANSPORT, spec)
        self.assertEqual("moonshot-private", api_key)
        self.assertEqual("kimi-k3", payload["model"])
        self.assertIs(payload["stream"], False)
        self.assertEqual(1536, payload["max_completion_tokens"])
        self.assertNotIn("max_tokens", payload)
        self.assertEqual("max", payload["reasoning_effort"])
        self.assertEqual({"type": "json_object"}, payload["response_format"])
        self.assertEqual("system", payload["messages"][0]["role"])
        self.assertIn('"schema_version":1', payload["messages"][0]["content"])
        self.assertIn('"secondary_color_index":1', payload["messages"][0]["content"])
        self.assertEqual(
            {"role": "user", "content": _request().prompt},
            payload["messages"][1],
        )
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("api", result.backend)
        self.assertEqual("moonshot", result.provider)
        self.assertEqual("kimi-k3", result.model_id)
        self.assertEqual({"cost_in_usd_ticks": 56_700_000}, result.usage)

    def test_missing_usage_succeeds_and_malformed_usage_fails_once(self) -> None:
        calls = 0
        responses = iter(
            (
                _kimi_response(_recipe()),
                _kimi_response(
                    _recipe(),
                    usage={
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "cached_tokens": 11,
                    },
                ),
            )
        )

        def transport(*_args):
            nonlocal calls
            calls += 1
            return next(responses)

        provider = KimiRecipeProvider("moonshot-private", transport=transport)
        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertIsNone(result.usage)

        with self.assertRaises(llm.ProviderError) as captured:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", captured.exception.code)
        self.assertEqual(2, calls)
        self.assertNotIn("moonshot-private", str(captured.exception))

    def test_nonstop_or_ambiguous_output_fails_once_without_body_text(self) -> None:
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "cached_tokens": 0,
        }
        length = _kimi_response(
            _recipe(),
            finish_reason="length",
            usage=usage,
        )
        length["provider_error"] = "provider-body-secret"
        ambiguous = _kimi_response(_recipe(), usage=usage)
        ambiguous["choices"].append(dict(ambiguous["choices"][0]))
        for response in (length, ambiguous):
            calls = 0

            def transport(*_args):
                nonlocal calls
                calls += 1
                return response

            provider = KimiRecipeProvider(
                "moonshot-private",
                transport=transport,
            )
            with self.subTest(choices=len(response["choices"])):
                with self.assertRaises(llm.ProviderError) as captured:
                    provider.generate(
                        _request(),
                        time.monotonic() + 10,
                        lambda: False,
                    )
                self.assertEqual("bad_response", captured.exception.code)
                self.assertEqual(1, calls)
                self.assertTrue(captured.exception.usage.reported)
                self.assertNotIn("provider-body-secret", str(captured.exception))

    def test_cancellation_and_invalid_recipe_never_make_a_paid_retry(self) -> None:
        calls = 0

        def invalid_transport(*_args):
            nonlocal calls
            calls += 1
            return _kimi_response(
                {"provider-body-secret": "never expose this"},
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "cached_tokens": 0,
                },
            )

        provider = KimiRecipeProvider(
            "moonshot-private",
            transport=invalid_transport,
        )
        with self.assertRaises(llm.ProviderError) as cancelled:
            provider.generate(_request(), time.monotonic() + 10, lambda: True)
        self.assertEqual("unavailable", cancelled.exception.code)
        self.assertEqual(0, calls)

        with self.assertRaises(llm.ProviderError) as invalid:
            provider.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", invalid.exception.code)
        self.assertEqual(1, calls)
        self.assertNotIn("provider-body-secret", str(invalid.exception))

        checks = iter((False, True))
        post_call = KimiRecipeProvider(
            "moonshot-private",
            transport=lambda *_args: _kimi_response(
                _recipe(),
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "cached_tokens": 0,
                },
            ),
        )
        with self.assertRaises(llm.ProviderError) as late:
            post_call.generate(
                _request(),
                time.monotonic() + 10,
                lambda: next(checks),
            )
        self.assertEqual("unavailable", late.exception.code)
        self.assertTrue(late.exception.usage.reported)


class _OllamaClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple] = []

    def chat(self, payload, *, deadline, cancelled):
        self.calls.append((payload, deadline, cancelled))
        return self.response


class OllamaRecipeProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = OllamaModel(
            model_id="ornith:latest",
            digest="a" * 64,
            size_bytes=5_629_110_568,
            parameter_size="9.0B",
            quantization="Q4_K_M",
        )

    def test_strict_recipe_request_uses_selected_installed_model(self) -> None:
        client = _OllamaClient({"message": {"content": json.dumps(_recipe())}})
        provider = OllamaRecipeProvider(self.model, client=client)

        result = provider.generate(_request(), time.monotonic() + 10, lambda: False)

        self.assertEqual(1, len(client.calls))
        payload, _deadline, _cancelled = client.calls[0]
        request = _request()
        self.assertEqual(
            build_ollama_recipe_payload(
                model_id="ornith:latest",
                prompt=request.prompt,
                system_prompt=procedural.recipe_system_prompt(
                    request.width,
                    request.height,
                    request.frame_count,
                    density_default=request.density_default,
                ),
                schema=procedural.recipe_schema(),
                width=request.width,
                height=request.height,
                frame_count=request.frame_count,
                attempt=0,
                validation_reason=None,
            ),
            payload,
        )
        self.assertEqual("ornith:latest", payload["model"])
        self.assertIs(payload["stream"], False)
        self.assertEqual(procedural.recipe_schema(), payload["format"])
        self.assertEqual(1536, payload["options"]["num_predict"])
        self.assertIn("18x7", payload["messages"][0]["content"])
        self.assertEqual(_recipe(), result.recipe)
        self.assertEqual("local", result.backend)
        self.assertEqual("ollama", result.provider)
        self.assertEqual("ornith:latest", result.model_id)
        self.assertIsNone(result.usage)

    def test_retry_changes_seed_adds_bounded_reason_and_rejects_bad_output(self) -> None:
        client = _OllamaClient({"message": {"content": json.dumps(_recipe())}})
        provider = OllamaRecipeProvider(self.model, client=client)
        provider.generate(_request(), time.monotonic() + 10, lambda: False)
        provider.generate_attempt(
            _request(),
            time.monotonic() + 10,
            lambda: False,
            attempt=1,
            validation_reason="peak brightness was too low /private/model.gguf",
        )

        first, second = (call[0] for call in client.calls)
        request = _request()
        common = {
            "model_id": self.model.model_id,
            "prompt": request.prompt,
            "system_prompt": procedural.recipe_system_prompt(
                request.width,
                request.height,
                request.frame_count,
                density_default=request.density_default,
            ),
            "schema": procedural.recipe_schema(),
            "width": request.width,
            "height": request.height,
            "frame_count": request.frame_count,
        }
        self.assertEqual(
            build_ollama_recipe_payload(
                **common, attempt=0, validation_reason=None
            ),
            first,
        )
        self.assertEqual(
            build_ollama_recipe_payload(
                **common,
                attempt=1,
                validation_reason="peak brightness was too low /private/model.gguf",
            ),
            second,
        )
        self.assertNotEqual(first["options"]["seed"], second["options"]["seed"])
        self.assertIn("peak brightness was too low", second["messages"][1]["content"])
        self.assertNotIn("/private/model.gguf", second["messages"][1]["content"])

        invalid = OllamaRecipeProvider(
            self.model,
            client=_OllamaClient({"message": {"content": '{"private":"secret"}'}}),
        )
        with self.assertRaises(llm.ProviderError) as captured:
            invalid.generate(_request(), time.monotonic() + 10, lambda: False)
        self.assertEqual("bad_response", captured.exception.code)
        self.assertNotIn("secret", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
