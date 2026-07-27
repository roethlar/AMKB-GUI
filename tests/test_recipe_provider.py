from __future__ import annotations

import json
import time
import unittest

from am_configurator import ai_catalog, llm, procedural
from am_configurator.ollama_client import OllamaModel
from am_configurator.recipe_inference import build_ollama_recipe_payload
from am_configurator.recipe_provider import (
    AnthropicRecipeProvider,
    OllamaRecipeProvider,
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
