from __future__ import annotations

import json
import time
import unittest

from am_configurator import ai_catalog, llm, procedural
from am_configurator.ollama_client import OllamaModel
from am_configurator.recipe_inference import build_ollama_recipe_payload
from am_configurator.recipe_provider import (
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
