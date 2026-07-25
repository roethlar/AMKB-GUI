from __future__ import annotations

import importlib
import unittest
from pathlib import Path

from am_configurator import llm, server


ROOT = Path(__file__).resolve().parents[1]


class DeviceMappingArchitectureTests(unittest.TestCase):
    def test_mapping_core_is_lower_level_and_http_independent(self) -> None:
        mapping = importlib.import_module("am_configurator.device_mapping")

        self.assertEqual("CB", mapping.led_model("CB04"))
        spec, targets = mapping.generation_spec("AM21", ["keyframes"], 80)
        self.assertIsInstance(spec, mapping.RasterSpec)
        self.assertEqual("80", spec.model)
        self.assertEqual(["keyframes"], targets)

        mapping_source = Path(mapping.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from .server", mapping_source)
        self.assertNotIn("from am_configurator.server", mapping_source)
        for relative in (
            "am_configurator/generation.py",
            "am_configurator/procedural.py",
            "build_tools/qualify_recipe_model.py",
        ):
            with self.subTest(relative=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn("from .server import", source)
                self.assertNotIn("from am_configurator.server import", source)

        for name in (
            "RasterSpec",
            "MODEL_FRAME_CAPS",
            "LED_SPEEDS_MS",
        ):
            with self.subTest(retired_llm_owner=name):
                self.assertFalse(hasattr(llm, name))
        for name in (
            "frames_to_led_tracks",
            "generation_spec",
            "_led_model",
            "_GIF_LAYOUTS",
        ):
            with self.subTest(retired_http_owner=name):
                self.assertFalse(hasattr(server, name))

    def test_generation_specs_enforce_device_raster_and_frame_caps(self) -> None:
        mapping = importlib.import_module("am_configurator.device_mapping")

        relic, targets = mapping.generation_spec(
            "AM21",
            ["keyframes", "spotlight_frames", "keyframes"],
            999,
        )
        self.assertEqual(["keyframes", "spotlight_frames"], targets)
        self.assertEqual((18, 7), (relic.width, relic.height))
        self.assertEqual(("spotlight_frames",), relic.extra_targets)
        self.assertEqual(200, relic.max_frames)
        self.assertIsNone(relic.mapped_positions)

        edge, targets = mapping.generation_spec("80", ["spotlight_frames"], 0)
        self.assertEqual(["spotlight_frames"], targets)
        self.assertEqual(7, edge.output_len)
        self.assertEqual(1, edge.max_frames)
        self.assertEqual(7, len(edge.mapped_positions or ()))

        with self.assertRaisesRegex(ValueError, "different rasters"):
            mapping.generation_spec("CB04", ["keyframes", "frames"], None)


if __name__ == "__main__":
    unittest.main()
