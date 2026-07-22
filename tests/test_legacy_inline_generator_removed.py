from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from am_configurator import llm, server


ROOT = Path(__file__).resolve().parents[1]


class LegacyInlineGeneratorRemovalTests(unittest.TestCase):
    def test_legacy_llm_pipeline_is_not_importable(self) -> None:
        retired = (
            "EffectPlan",
            "RenderedFrames",
            "GrokInterpreter",
            "GrokImagineRenderer",
            "plan_from_json",
            "expand_keyframes",
            "generate_effect",
            "MAX_RENDERED_KEYFRAMES",
            "MAX_LLM_FRAMES",
            "LLM_TOTAL_BUDGET",
            "INTERPRETERS",
            "RENDERERS",
        )
        for name in retired:
            with self.subTest(name=name):
                self.assertFalse(hasattr(llm, name))

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


if __name__ == "__main__":
    unittest.main()
