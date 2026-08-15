from __future__ import annotations

import inspect
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from am_configurator import server, store


ROOT = Path(__file__).resolve().parents[1]


class LegacyInlineGeneratorRemovalTests(unittest.TestCase):
    def test_legacy_llm_pipeline_is_not_importable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("am_configurator.llm"))
        self.assertIsNone(importlib.util.find_spec("am_configurator.ai_catalog"))

    def test_legacy_server_worker_is_not_injectable_or_callable(self) -> None:
        self.assertFalse(hasattr(server, "_default_llm_factories"))
        self.assertNotIn("llm_factories", inspect.signature(server._State).parameters)
        self.assertNotIn("llm_factories", inspect.signature(server.create_server).parameters)
        for name in (
            "start_generation",
            "finish_generation",
            "generation_status",
            "cancel_generation",
            "join_generation",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(server._State, name))
        for name in ("_start_generation", "_generation_status", "_cancel_generation"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(server._Handler, name))

    def test_browser_has_no_legacy_preview_or_refine_state(self) -> None:
        source = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )
        for token in (
            "pendingGeneration",
            "previousPlan",
            "aiFrameCount",
            "refine-generation",
            "AI result ready",
            "/api/led/generate",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_retired_paid_mutation_stack_is_not_importable_or_configurable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("am_configurator.generation"))
        self.assertIsNone(importlib.util.find_spec("am_configurator.llm"))
        self.assertIsNone(importlib.util.find_spec("am_configurator.ai_catalog"))

        with (
            patch.object(store, "_mutate_settings") as mutate,
            self.assertRaises(ValueError),
        ):
            store.update_preferences({"models": {"interpreter": "grok-4.5"}})
        mutate.assert_not_called()
        with (
            patch.object(store, "_mutate_settings") as mutate,
            self.assertRaises(ValueError),
        ):
            store.update_preferences({"candidate_count": 4})
        mutate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
