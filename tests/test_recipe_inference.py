from __future__ import annotations

import importlib.util
import inspect
import unittest
from pathlib import Path

from am_configurator import recipe_inference
from am_configurator.recipe_inference import (
    LOCAL_OUTPUT_TOKENS,
    build_ollama_recipe_payload,
)


class RecipeInferenceContractTests(unittest.TestCase):
    def _payload(self):
        return build_ollama_recipe_payload(
            model_id="ornith:latest",
            prompt="  Blue stars over a dark field  ",
            system_prompt="Return one strict recipe.",
            schema={"type": "object", "additionalProperties": False},
            width=18,
            height=7,
            frame_count=200,
        )

    def test_single_payload_is_deterministic_with_one_message_shape(self) -> None:
        initial = self._payload()
        repeated = self._payload()

        self.assertEqual(initial, repeated)
        self.assertEqual(
            {"temperature": 0.2, "seed": initial["options"]["seed"], "num_predict": 1536},
            initial["options"],
        )
        self.assertEqual(LOCAL_OUTPUT_TOKENS, initial["options"]["num_predict"])
        self.assertEqual(
            ["system", "user"],
            [message["role"] for message in initial["messages"]],
        )
        self.assertEqual(
            "Blue stars over a dark field",
            initial["messages"][1]["content"],
        )

    def test_retry_protocol_has_no_definition_export_or_payload_surface(self) -> None:
        source = inspect.getsource(recipe_inference)
        for forbidden in (
            "LOCAL_MAX_RETRIES",
            "_retry_content",
            "Retry correction:",
            "validation_reason",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertNotIn("attempt", inspect.signature(build_ollama_recipe_payload).parameters)

    def test_only_production_provider_owns_ollama_inference_details(self) -> None:
        root = Path(__file__).resolve().parents[1]
        provider_source = (root / "am_configurator" / "recipe_provider.py").read_text(
            encoding="utf-8"
        )
        qualification_source = (
            root / "build_tools" / "qualify_recipe_model.py"
        ).read_text(encoding="utf-8")
        retired_adapter = "local_" + "animation"

        self.assertIn("build_ollama_recipe_payload(", provider_source)
        for source in (provider_source, qualification_source):
            self.assertNotIn('"temperature"', source)
            self.assertNotIn('"num_predict"', source)
            self.assertNotIn("7319 +", source)
            self.assertNotIn("generate_attempt", source)
            self.assertNotIn("validation_reason", source)
        self.assertNotIn("build_ollama_recipe_payload", qualification_source)
        self.assertIn("OllamaRecipeProvider", qualification_source)
        self.assertIn("RecipeRequest(", qualification_source)
        if retired_adapter in qualification_source:
            self.fail("Qualification imports the retired developer adapter.")
        self.assertFalse(
            (root / "am_configurator" / f"{retired_adapter}.py").exists()
        )
        self.assertIsNone(
            importlib.util.find_spec(f"am_configurator.{retired_adapter}")
        )


if __name__ == "__main__":
    unittest.main()
