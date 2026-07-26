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

        for model in ("CB", "80", "ALICE", "NEON"):
            self.assertEqual(model, mapping.family_spec(model).model)
        # A caller holding a real device must never be handed another device's
        # geometry, which is what a silent fallback would do. (This used to use
        # "NEON" as its example of an unknown family; registering that family
        # made the test pass vacuously, and the failure is what caught it.)
        with self.assertRaises(KeyError):
            mapping.family_spec("NOT-A-REGISTERED-FAMILY")

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
                    spec.macro_buffer_bytes, mirrored.get("macroBufferBytes", 0)
                )
                self.assertEqual(spec.keys_per_layer, mirrored["keysPerLayer"])
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


class MacroCapacityIsAlwaysEnforceableTests(unittest.TestCase):
    """No family may opt out of the macro ceilings.

    A `None` limit meaning "device-reported" reads as flexible but is not: it
    silently disables the checks in `validate_config`, and the editor renders it
    as an empty limit with a permanently tripped meter. A Vial device's real
    capacity is a byte budget, which is a separate field — see plan task N7.
    """

    def test_every_registered_family_declares_integer_ceilings(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        specs = dict(mapping._FAMILY_SPECS)
        specs[""] = mapping._UNKNOWN_FAMILY_SPEC
        for model, spec in specs.items():
            with self.subTest(model=model or "<unknown>"):
                self.assertIsInstance(spec.macro_tracks, int)
                self.assertIsInstance(spec.macro_events, int)
                self.assertGreater(spec.macro_tracks, 0)
                self.assertGreater(spec.macro_events, 0)

    def test_validation_enforces_the_ceiling_for_every_family(self):
        mapping = importlib.import_module("am_configurator.device_mapping")
        server = importlib.import_module("am_configurator.server")

        for model, spec in mapping._FAMILY_SPECS.items():
            with self.subTest(model=model):
                config = {
                    "product_info": {"product_id": model},
                    "key_layer": {
                        "layer_num": 1,
                        "layer_data": [{"layer": ["#00000000"] * 200}],
                    },
                    "macro_key": [
                        {
                            "original_key": f"#11{index:06X}",
                            "layer_key": ["#11000000"],
                            "intvel_ms": [],
                        }
                        for index in range(spec.macro_tracks + 1)
                    ],
                    "page_data": [],
                }
                errors = server.validate_config(config)["errors"]
                self.assertTrue(
                    any(f"more than {spec.macro_tracks} macros" in e for e in errors),
                    errors,
                )


class BlankConfigUsesFamilySpecTests(unittest.TestCase):
    """A blank profile must be shaped for the device that will receive it.

    Every shipped family shares the same keyframes length, so a test written
    against them would pass even with the historical hardcoded 90 and 24. This
    registers a synthetic family whose track sizes differ, which is the only way
    to prove the lookup is real.
    """

    def _blank(self, device_id):
        server = importlib.import_module("am_configurator.server")
        return server.blank_config(device_id, [["#00000000"] * 200] * 7, [])

    def _custom_pages(self, config):
        return [page for page in config["page_data"] if page["page_index"] >= 5]

    def test_tracks_the_function_never_mentions_are_still_emitted(self):
        """The names must come from the specification, not from this function.

        A guard using `keyframes` and `spotlight_frames` proves nothing here:
        those are exactly the names the code spells out. This uses two names the
        implementation has never heard of, shaped like the Neon 80's axial and
        head tracks, which is the case the finding predicted would fail.
        """

        mapping = importlib.import_module("am_configurator.device_mapping")

        synthetic = mapping.FamilySpec(
            model="SYNTH",
            transport=mapping.SERIAL_TRANSPORT,
            frame_cap=64,
            macro_tracks=32,
            macro_events=200,
        )
        layouts = dict(mapping._LAYOUTS)
        layouts["SYNTH"] = {
            "axial": {"size": (89, 1), "map": (), "pixels": 89},
            "head": {"size": (23, 10), "map": (), "pixels": 230},
        }
        specs = dict(mapping._FAMILY_SPECS)
        specs["SYNTH"] = synthetic

        with (
            mock.patch.object(mapping, "_LAYOUTS", layouts),
            mock.patch.object(mapping, "_FAMILY_SPECS", specs),
            mock.patch.object(mapping, "led_model", lambda device_id: "SYNTH"),
        ):
            config = self._blank("SYNTH")

        custom = self._custom_pages(config)
        self.assertTrue(custom)
        for page in custom:
            self.assertEqual(89, len(page["axial"]["frame_data"][0]["frame_RGB"]))
            self.assertEqual(230, len(page["head"]["frame_data"][0]["frame_RGB"]))
        # Non-custom slots carry no authored extra track, as before.
        for page in config["page_data"]:
            if page["page_index"] < 5:
                self.assertNotIn("axial", page)
                self.assertNotIn("head", page)

    def test_track_sizes_and_extra_tracks_follow_the_family(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        synthetic = mapping.FamilySpec(
            model="SYNTH",
            transport=mapping.SERIAL_TRANSPORT,
            frame_cap=64,
            macro_tracks=32,
            macro_events=200,
        )
        layouts = dict(mapping._LAYOUTS)
        layouts["SYNTH"] = {
            "keyframes": {"size": (7, 7), "map": (), "pixels": 49},
            "spotlight_frames": {"size": (11, 1), "map": (), "pixels": 11},
        }
        specs = dict(mapping._FAMILY_SPECS)
        specs["SYNTH"] = synthetic

        with (
            mock.patch.object(mapping, "_LAYOUTS", layouts),
            mock.patch.object(mapping, "_FAMILY_SPECS", specs),
            mock.patch.object(mapping, "led_model", lambda device_id: "SYNTH"),
        ):
            pages = self._custom_pages(self._blank("SYNTH"))

        self.assertTrue(pages)
        for page in pages:
            self.assertEqual(49, len(page["keyframes"]["frame_data"][0]["frame_RGB"]))
            self.assertEqual(
                11, len(page["spotlight_frames"]["frame_data"][0]["frame_RGB"])
            )

    def test_a_family_without_an_edge_track_gets_none(self):
        for page in self._custom_pages(self._blank("ALICE")):
            self.assertNotIn("spotlight_frames", page)

    def test_shipped_families_keep_their_current_shape(self):
        """Regression guard: the conversion must not resize a real device."""

        for device_id, edge in (("CB04", False), ("AM21", True), ("80", True)):
            with self.subTest(device_id=device_id):
                pages = self._custom_pages(self._blank(device_id))
                for page in pages:
                    self.assertEqual(
                        90, len(page["keyframes"]["frame_data"][0]["frame_RGB"])
                    )
                    self.assertEqual(edge, "spotlight_frames" in page)
                    if edge:
                        self.assertEqual(
                            24,
                            len(page["spotlight_frames"]["frame_data"][0]["frame_RGB"]),
                        )

    def test_the_stored_product_id_is_the_wire_identifier_not_the_family(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        # A Relic probes as AM21 but its configurations name 80.
        self.assertEqual("80", mapping.config_product_id("AM21"))
        self.assertEqual("80", self._blank("AM21")["product_info"]["product_id"])
        # A CyberBoard keeps its own identifier even though its family is CB.
        self.assertEqual("CB04", mapping.config_product_id("CB04"))
        self.assertEqual("CB", mapping.led_model("CB04"))
        self.assertEqual("CB04", self._blank("CB04")["product_info"]["product_id"])


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



class NeonFamilyRegistrationTests(unittest.TestCase):
    """Plan task N4: exactly two authored tracks, and axial payload order.

    The side zone is the trap. It is a real zone the device lights, but it is
    derived from the head frames at transmit time and is never independently
    authored, so publishing it would offer the user a track the device cannot
    receive.
    """

    def test_neon_publishes_exactly_the_two_authored_tracks(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        spec = mapping.family_spec("NEON")
        self.assertEqual(("axial", "head"), spec.authored_tracks)
        self.assertNotIn("side", spec.authored_tracks)

        published = mapping.target_capabilities()["NEON"]["targets"]
        names = [target["name"] for target in published]
        self.assertEqual(["axial", "head"], names)
        self.assertNotIn("side", names)

    def test_neon_track_sizes_match_the_wire_payloads(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        spec = mapping.family_spec("NEON")
        self.assertEqual(89, spec.track_colors("axial"))
        self.assertEqual(230, spec.track_colors("head"))
        self.assertEqual(256, spec.frame_cap)
        self.assertEqual(mapping.HID_TRANSPORT, spec.transport)

    def test_axial_payload_order_round_trips_to_grid_positions(self):
        """Array index is payload index; the grid must preserve that exactly."""

        mapping = importlib.import_module("am_configurator.device_mapping")

        grid = mapping._NEON_AXIAL_MAP
        width, height = 19, 6
        self.assertEqual(width * height, len(grid))

        placed = [value for value in grid if value >= 0]
        self.assertEqual(89, len(placed))
        # Every payload index appears exactly once: no LED is dropped and none
        # is written twice, which is what a bad quantization would cause.
        self.assertEqual(sorted(placed), list(range(89)))

        for x, y, payload_index in mapping._NEON_AXIAL_PLACEMENTS:
            with self.subTest(payload_index=payload_index):
                self.assertEqual(payload_index, grid[y * width + x])

        # The assertions above are self-consistent by construction: the grid is
        # built from these same placements, so they pass however wrong the
        # placements are. These check the placements against structure taken
        # from the source coordinates instead.
        rows: dict[int, list[tuple[int, int]]] = {}
        for x, y, payload_index in mapping._NEON_AXIAL_PLACEMENTS:
            rows.setdefault(y, []).append((x, payload_index))

        self.assertEqual([17, 17, 17, 13, 13, 12], [len(rows[y]) for y in sorted(rows)])

        for y, cells in sorted(rows.items()):
            with self.subTest(row=y):
                by_position = [index for _, index in sorted(cells)]
                self.assertEqual(
                    sorted(by_position),
                    by_position,
                    "payload order must ascend left-to-right within a row",
                )

        # Rows are contiguous runs of payload indices, in top-to-bottom order.
        starts = [min(index for _, index in rows[y]) for y in sorted(rows)]
        self.assertEqual(sorted(starts), starts)
        self.assertEqual(0, starts[0])

    def test_the_head_matrix_is_row_major_with_no_remapping(self):
        """The host sends head values row-major, so any map here must be identity."""

        mapping = importlib.import_module("am_configurator.device_mapping")

        self.assertEqual(tuple(range(230)), mapping._NEON_HEAD_MAP)

    def test_neon_capacity_is_the_measured_device_capacity(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        spec = mapping.family_spec("NEON")
        # Measured by read-only VIA reads on the owner's board, not defaulted
        # from the serial families, which would claim 32 macros.
        self.assertEqual(16, spec.macro_tracks)
        self.assertEqual(6677, spec.macro_buffer_bytes)
        self.assertNotEqual(32, spec.macro_tracks)


class ServedGeometryTests(unittest.TestCase):
    """The browser lays out any family from what the server publishes.

    Copying LED maps into JavaScript would create a second authority for tables
    Python already owns, which is the drift the cross-language spec guard exists
    to prevent. So the maps travel over the capabilities payload instead.
    """

    def test_every_published_target_carries_its_pixel_map(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        published = mapping.target_capabilities()
        for family, entry in published.items():
            for target in entry["targets"]:
                with self.subTest(family=family, target=target["name"]):
                    self.assertIn("map", target)
                    self.assertEqual(
                        target["width"] * target["height"], len(target["map"])
                    )
                    mapped = [index for index in target["map"] if index >= 0]
                    # `pixels` is the payload length. A map covers a subset of
                    # it — several families have payload slots with no source
                    # pixel — so the invariants are that no payload slot is
                    # written twice and none is out of range.
                    self.assertEqual(len(mapped), len(set(mapped)))
                    self.assertLess(max(mapped), target["pixels"])
                    self.assertGreaterEqual(min(mapped), 0)

    def test_the_neon_is_fully_describable_without_any_browser_table(self):
        """N4's browser half depends on this being sufficient on its own."""

        mapping = importlib.import_module("am_configurator.device_mapping")

        neon = {t["name"]: t for t in mapping.target_capabilities()["NEON"]["targets"]}
        self.assertEqual({"axial", "head"}, set(neon))
        self.assertEqual((19, 6), (neon["axial"]["width"], neon["axial"]["height"]))
        self.assertEqual(89, neon["axial"]["pixels"])
        self.assertEqual((46, 5), (neon["head"]["width"], neon["head"]["height"]))
        self.assertEqual(230, neon["head"]["pixels"])
        # Head is row-major, so its map is the identity: any other map here
        # would remap a payload the firmware already expects in order.
        self.assertEqual(list(range(230)), neon["head"]["map"])

    def test_the_browser_carries_no_copy_of_a_led_map(self):
        app = (ROOT / "am_configurator/web/app.js").read_text(encoding="utf-8")

        self.assertNotIn("NEON_AXIAL", app)
        self.assertIn("servedGeometry", app)


class FamilyAwareValidationTests(unittest.TestCase):
    """`validate_config` must not judge one family by another family's shape.

    Finding n567-2, and a repeat: this was recorded as known open work under
    or-1 and left unscheduled. Recording a gap is not closing it.
    """

    def _config(self, product_id, keys, *, pages=None):
        return {
            "product_info": {"product_id": product_id},
            "key_layer": {
                "layer_num": 4,
                "layer_data": [{"layer": ["#00070004"] * keys} for _ in range(4)],
            },
            "macro_key": [],
            "page_data": pages if pages is not None else [],
        }

    def test_a_native_neon_keymap_validates(self):
        """Four layers of ninety keys, which is what the device actually reports."""

        server = importlib.import_module("am_configurator.server")

        result = server.validate_config(self._config("NEON80", 90))
        self.assertTrue(result["ok"], result["errors"])

    def test_a_serial_keymap_still_requires_two_hundred(self):
        server = importlib.import_module("am_configurator.server")

        errors = server.validate_config(self._config("CB04", 90))["errors"]
        self.assertTrue(
            any("exactly 200 keycodes" in error for error in errors), errors
        )

    def test_a_neon_keymap_of_two_hundred_keys_is_rejected(self):
        """The check is the family's own count, not a minimum."""

        server = importlib.import_module("am_configurator.server")

        errors = server.validate_config(self._config("NEON80", 200))["errors"]
        self.assertTrue(
            any("exactly 90 keycodes" in error for error in errors), errors
        )

    def test_the_serial_wire_encoder_does_not_judge_a_hid_configuration(self):
        """It is one family's encoder, not a general validator.

        Running it against a Neon configuration rejected every valid one,
        because it looks for AM serial page structure the Neon does not have.
        """

        server = importlib.import_module("am_configurator.server")

        result = server.validate_config(self._config("NEON80", 90))
        self.assertTrue(result["ok"], result["errors"])
        self.assertIsNone(result.get("frame_plan"))
        self.assertEqual(
            [], [e for e in result["errors"] if "Wire encoder" in e]
        )

    def test_keys_per_layer_comes_from_the_specification(self):
        mapping = importlib.import_module("am_configurator.device_mapping")

        self.assertEqual(90, mapping.family_spec("NEON").keys_per_layer)
        for model in ("CB", "80", "ALICE"):
            with self.subTest(model=model):
                self.assertEqual(200, mapping.family_spec(model).keys_per_layer)


if __name__ == "__main__":
    unittest.main()
