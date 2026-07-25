from __future__ import annotations

import importlib
import json
import re
import unittest
from pathlib import Path
from unittest import mock

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


class FamilySpecTests(unittest.TestCase):
    """The per-family specification is the single authority for family limits."""

    def test_unknown_family_raises_instead_of_substituting(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        for model in ("CB", "80", "ALICE"):
            self.assertEqual(model, mapping.family_spec(model).model)
        # A caller holding a real device must never be handed another device's
        # geometry, which is what a silent fallback would do.
        with self.assertRaises(KeyError):
            mapping.family_spec("NEON")

    def test_track_colors_come_from_the_layouts_not_a_second_copy(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        self.assertEqual(200, mapping.family_spec("CB").track_colors("frames"))
        self.assertEqual(90, mapping.family_spec("CB").track_colors("keyframes"))
        self.assertEqual(24, mapping.family_spec("80").track_colors("spotlight_frames"))
        self.assertEqual(
            ("keyframes", "frames"), mapping.family_spec("CB").authored_tracks
        )
        self.assertEqual(
            ("keyframes", "spotlight_frames"), mapping.family_spec("80").authored_tracks
        )

    def test_unrecognised_product_falls_back_without_raising(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        for value in (None, "", 17, "NOT-A-BOARD"):
            spec = mapping.spec_for_product(value)
            self.assertEqual("", spec.model)
            self.assertEqual(90, spec.track_colors("keyframes"))
        self.assertEqual("CB", mapping.spec_for_product("CB04").model)
        self.assertEqual("80", mapping.spec_for_product("AM21").model)


class BrowserSpecMirrorsPythonTests(unittest.TestCase):
    """The browser carries its own copy of the family spec; it must not drift.

    `am_configurator/web/lighting_targets.js` cannot import from Python, so it
    embeds the same numbers as a strict-JSON literal. Python owns them; this
    parses the literal and asserts the two sides still agree.
    """

    def _browser_spec(self):
        source = (ROOT / "am_configurator/web/lighting_targets.js").read_text(
            encoding="utf-8"
        )
        match = re.search(r"const SPEC_SOURCE = `(.*?)`;", source, re.DOTALL)
        self.assertIsNotNone(
            match, "lighting_targets.js no longer embeds a SPEC_SOURCE literal"
        )
        return json.loads(match.group(1))

    def test_browser_families_match_the_python_authority(self):
        mapping = importlib.import_module("am_configurator.device_mapping")
        browser = self._browser_spec()

        self.assertEqual(
            sorted(mapping._FAMILY_SPECS), sorted(browser["families"])
        )
        for model, mirrored in browser["families"].items():
            with self.subTest(model=model):
                spec = mapping.family_spec(model)
                self.assertEqual(spec.transport, mirrored["transport"])
                self.assertEqual(spec.frame_cap, mirrored["frameCap"])
                self.assertEqual(spec.macro_tracks, mirrored["macroTracks"])
                self.assertEqual(spec.macro_events, mirrored["macroEvents"])
                self.assertEqual(
                    list(spec.authored_tracks), list(mirrored["trackColors"])
                )
                for field, colors in mirrored["trackColors"].items():
                    self.assertEqual(spec.track_colors(field), colors)

    def test_browser_shared_and_unknown_values_match(self):
        mapping = importlib.import_module("am_configurator.device_mapping")
        browser = self._browser_spec()

        self.assertEqual(
            mapping._SHARED_TRACK_COLORS, browser["sharedTrackColors"]
        )
        self.assertEqual(
            mapping._UNKNOWN_FAMILY_SPEC.frame_cap, browser["unknownFrameCap"]
        )


class ValidationUsesFamilySpecTests(unittest.TestCase):
    """`validate_config` must size tracks per family, not from a fixed tuple.

    Every shipped family currently happens to share the same track counts, so a
    test written against them would pass even with the old hardcoded tuple. This
    registers a synthetic family whose counts differ, which is the only way to
    prove the lookup is real.
    """

    def _config(self, product_id, colors):
        return {
            "product_info": {"product_id": product_id},
            "key_layer": {
                "layer_num": 1,
                "layer_data": [{"layer": ["#00000000"] * 200}],
            },
            "macro_key": [],
            "page_data": [
                {
                    "page_index": 0,
                    "keyframes": {
                        "frame_num": 1,
                        "frame_data": [
                            {"frame_index": 0, "frame_RGB": ["#000000"] * colors}
                        ],
                    },
                }
            ],
        }

    def test_track_size_follows_the_configured_family(self):
        mapping = importlib.import_module("am_configurator.device_mapping")
        server = importlib.import_module("am_configurator.server")

        synthetic = mapping.FamilySpec(
            model="SYNTH",
            transport=mapping.SERIAL_TRANSPORT,
            frame_cap=256,
            macro_tracks=4,
            macro_events=9,
        )
        layouts = dict(mapping._LAYOUTS)
        layouts["SYNTH"] = {"keyframes": {"size": (7, 7), "map": (), "pixels": 49}}
        specs = dict(mapping._FAMILY_SPECS)
        specs["SYNTH"] = synthetic

        with (
            mock.patch.object(mapping, "_LAYOUTS", layouts),
            mock.patch.object(mapping, "_FAMILY_SPECS", specs),
            mock.patch.object(mapping, "led_model", lambda product_id: "SYNTH"),
        ):
            self.assertEqual(49, synthetic.track_colors("keyframes"))

            # The synthetic family wants 49 colors; the historical hardcoded
            # value was 90. Assert on the track-size error specifically: this
            # minimal config does not satisfy the wire encoder, and that is not
            # what this test is about.
            good = server.validate_config(self._config("SYNTH", 49))
            self.assertEqual(
                [], [error for error in good["errors"] if "colors" in error]
            )

            bad = server.validate_config(self._config("SYNTH", 90))
            self.assertTrue(
                any("must contain 49 colors" in error for error in bad["errors"]),
                bad["errors"],
            )

    def test_macro_ceilings_follow_the_configured_family(self):
        mapping = importlib.import_module("am_configurator.device_mapping")
        server = importlib.import_module("am_configurator.server")

        synthetic = mapping.FamilySpec(
            model="SYNTH",
            transport=mapping.SERIAL_TRANSPORT,
            frame_cap=256,
            macro_tracks=2,
            macro_events=3,
        )
        specs = dict(mapping._FAMILY_SPECS)
        specs["SYNTH"] = synthetic

        config = self._config("SYNTH", 90)
        config["macro_key"] = [
            {"original_key": f"#1100000{index}", "layer_key": ["#11000000"], "intvel_ms": []}
            for index in range(3)
        ]

        with (
            mock.patch.object(mapping, "_FAMILY_SPECS", specs),
            mock.patch.object(mapping, "led_model", lambda product_id: "SYNTH"),
        ):
            result = server.validate_config(config)

        # Three macros against a ceiling of two: the message must cite the
        # family's own limit, not the historical 32.
        self.assertTrue(
            any("more than 2 macros" in error for error in result["errors"]),
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
