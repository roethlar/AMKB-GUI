from __future__ import annotations

import unittest
from pathlib import Path

from am_configurator.recipe_inference import (
    LOCAL_MAX_RETRIES,
    LOCAL_OUTPUT_TOKENS,
    build_ollama_recipe_payload,
)


class RecipeInferenceContractTests(unittest.TestCase):
    def _payload(self, *, attempt: int, validation_reason: str | None):
        return build_ollama_recipe_payload(
            model_id="ornith:latest",
            prompt="  Blue stars over a dark field  ",
            system_prompt="Return one strict recipe.",
            schema={"type": "object", "additionalProperties": False},
            width=18,
            height=7,
            frame_count=200,
            attempt=attempt,
            validation_reason=validation_reason,
        )

    def test_payload_is_deterministic_and_retries_use_one_fresh_message_shape(self) -> None:
        initial = self._payload(attempt=0, validation_reason=None)
        repeated = self._payload(attempt=0, validation_reason=None)
        retry = self._payload(
            attempt=1,
            validation_reason="peak brightness was too low /private/model.gguf",
        )

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
        self.assertEqual(2, len(retry["messages"]))
        self.assertNotEqual(initial["options"]["seed"], retry["options"]["seed"])
        self.assertIn("Retry correction:", retry["messages"][1]["content"])
        self.assertIn("peak brightness was too low", retry["messages"][1]["content"])
        self.assertNotIn("/private/model.gguf", retry["messages"][1]["content"])

    def test_invalid_attempt_or_retry_reason_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._payload(attempt=LOCAL_MAX_RETRIES + 1, validation_reason="invalid")
        with self.assertRaises(ValueError):
            self._payload(attempt=0, validation_reason="unexpected")
        with self.assertRaises(ValueError):
            self._payload(attempt=1, validation_reason=None)

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


if __name__ == "__main__":
    unittest.main()
