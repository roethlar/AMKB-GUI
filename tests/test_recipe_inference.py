from __future__ import annotations

import unittest
import inspect
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

    def test_ollama_recipe_callers_do_not_redeclare_sampling_parameters(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "am_configurator/recipe_provider.py",
            "am_configurator/local_animation.py",
        ):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertIn("build_ollama_recipe_payload(", source)
            self.assertNotIn('"temperature"', source)
            self.assertNotIn('"num_predict"', source)
            self.assertNotIn("7319 +", source)
            self.assertNotIn("generate_attempt", source)
            self.assertNotIn("validation_reason", source)


if __name__ == "__main__":
    unittest.main()
