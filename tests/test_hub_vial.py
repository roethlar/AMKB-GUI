"""Fixture-backed contract for the OpenKeeb Vial hub spoke."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from am_configurator import hub_vial, vial_lighting
from am_configurator.hub_profile import uncovered_leaves, validate_hub_profile


FIXTURE = Path(__file__).with_name("fixtures") / "vial" / "minimal_snapshot.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class VialSnapshotTests(unittest.TestCase):
    def test_discovery_snapshot_validates_definition_and_projects_layout(self) -> None:
        with mock.patch(
            "am_configurator.hid_transport._hid",
            side_effect=AssertionError("fixture path touched hardware"),
        ):
            snapshot = hub_vial.load_snapshot(_fixture())

        self.assertEqual(snapshot.name, "Fixture Pad")
        self.assertEqual(snapshot.matrix_rows, 2)
        self.assertEqual(snapshot.matrix_cols, 3)
        self.assertEqual(snapshot.keys_per_layer, 6)
        self.assertEqual(snapshot.via_protocol, 9)
        self.assertEqual(snapshot.vial_protocol, 6)
        self.assertEqual(snapshot.firmware_uid, "0123456789abcdef")
        self.assertEqual(
            [(key["matrix_row"], key["matrix_col"]) for key in snapshot.key_layout],
            [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)],
        )
        self.assertGreater(snapshot.key_layout[2]["width"], snapshot.key_layout[1]["width"])

    def test_snapshot_rejects_untrusted_shape_and_buffer_lengths(self) -> None:
        cases = []

        missing_layout = _fixture()
        del missing_layout["definition"]["layouts"]
        cases.append((missing_layout, "layout"))

        wrong_keymap = _fixture()
        wrong_keymap["keymap_hex"] = "0000"
        cases.append((wrong_keymap, "keymap buffer"))

        wrong_macros = _fixture()
        wrong_macros["macro_buffer_bytes"] += 1
        cases.append((wrong_macros, "macro buffer"))

        bad_uid = _fixture()
        bad_uid["firmware_uid"] = "not-a-uid"
        cases.append((bad_uid, "firmware UID"))

        unsupported_via = _fixture()
        unsupported_via["via_protocol"] = 12
        cases.append((unsupported_via, "VIA protocol 12"))

        for value, phrase in cases:
            with self.subTest(phrase=phrase):
                with self.assertRaises(hub_vial.VialSpokeError) as caught:
                    hub_vial.load_snapshot(value)
                self.assertIn(phrase, str(caught.exception))


class VialHubReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = hub_vial.load_snapshot(_fixture())
        self.profile = hub_vial.build_hub_profile(self.snapshot)

    def test_snapshot_becomes_a_fully_covered_hub_profile(self) -> None:
        self.assertEqual(self.profile, validate_hub_profile(self.profile))
        self.assertEqual(uncovered_leaves(self.profile), [])
        self.assertEqual(
            self.profile["identity"],
            {
                "ecosystem": "vial",
                "family": "Fixture Pad",
                "wire_identity": "0123456789abcdef",
                "endpoint": {"vid": 51966, "pid": 48879, "transport": "hid"},
                "protocol": {"via_protocol": 9, "vial_protocol": 6},
                "definition": {
                    "source": "device",
                    "hash": self.snapshot.definition_hash,
                },
            },
        )
        self.assertEqual(
            self.profile["capabilities"],
            {
                "keymap": {"layers": 2, "keys_per_layer": 6},
                "macros": {
                    "budget": {"model": "bytes", "slots": 3, "buffer_bytes": 20},
                    "delays": True,
                },
                "lighting": {"surfaces": []},
            },
        )

    def test_keymap_keeps_qmk_values_and_matrix_identity(self) -> None:
        first = self.profile["keymap"]["layers"][0]["keys"]
        self.assertEqual(
            [(entry["key"], entry["code"]) for entry in first],
            [
                ("K_R0_C0", 0x0029),
                ("K_R0_C1", 0x0004),
                ("K_R0_C2", 0x5203),
                ("K_R1_C0", 0x7700),
                ("K_R1_C1", 0x5101),
                ("K_R1_C2", 0x0000),
            ],
        )
        self.assertEqual(
            self.profile["keymap"]["matrix"],
            {
                "rows": 2,
                "cols": 3,
                "map": {
                    "K_R0_C0": [0, 0],
                    "K_R0_C1": [0, 1],
                    "K_R0_C2": [0, 2],
                    "K_R1_C0": [1, 0],
                    "K_R1_C1": [1, 1],
                    "K_R1_C2": [1, 2],
                },
            },
        )

    def test_macro_buffer_becomes_normalized_events(self) -> None:
        self.assertEqual(
            self.profile["macros"],
            [
                {
                    "slot": 0,
                    "events": [
                        {"tap": 0x0004},
                        {"delay_ms": 250},
                        {"down": 0x5203},
                        {"up": 0x5203},
                    ],
                },
                {"slot": 1, "events": [{"text": "ok"}]},
            ],
        )


class VialHubWritePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = hub_vial.load_snapshot(_fixture())
        self.profile = hub_vial.build_hub_profile(self.snapshot)

    def test_same_board_plan_is_byte_exact_without_a_transport(self) -> None:
        plan = hub_vial.plan_vial_write(self.profile, target=self.snapshot)

        self.assertEqual(plan.keymap_buffer, self.snapshot.keymap_buffer)
        self.assertEqual(plan.macro_buffer, self.snapshot.macro_buffer)
        self.assertTrue(plan.report["items"])
        self.assertEqual({item["verdict"] for item in plan.report["items"]}, {"carried"})

    def test_unaddressable_keys_are_dropped_not_guessed(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["keymap"]["layers"][0]["keys"][0]["key"] = "K_ENTER"
        profile["keymap"]["matrix"]["map"]["K_ENTER"] = profile["keymap"]["matrix"][
            "map"
        ].pop("K_R0_C0")
        plan = hub_vial.plan_vial_write(profile, target=self.snapshot)

        self.assertEqual(
            plan.keymap_buffer[:2],
            self.snapshot.keymap_buffer[:2],
            "an unaddressable source key must leave the target cell unchanged",
        )
        finding = next(
            item for item in plan.report["items"] if item["path"].endswith("[K_ENTER]")
        )
        self.assertEqual(finding["verdict"], "dropped")
        self.assertIn("overlay", finding["reason"])

    def test_macro_overflow_fails_before_a_write_plan_exists(self) -> None:
        target_value = _fixture()
        target_value["macro_buffer_bytes"] = 8
        target_value["macro_hex"] = "00" * 8
        target = hub_vial.load_snapshot(target_value)

        with self.assertRaises(hub_vial.VialSpokeError) as caught:
            hub_vial.plan_vial_write(self.profile, target=target)
        self.assertIn("Nothing was written", str(caught.exception))

    def test_macro_trigger_is_adapted_to_the_target_vial_protocol(self) -> None:
        target_value = _fixture()
        target_value["vial_protocol"] = 5
        target = hub_vial.load_snapshot(target_value)

        plan = hub_vial.plan_vial_write(self.profile, target=target)

        self.assertEqual(plan.keymap_buffer[6:8], b"\x5f\x12")
        finding = next(
            item
            for item in plan.report["items"]
            if item["path"] == "keymap.layers[0].keys[K_R1_C0]"
        )
        self.assertEqual(finding["verdict"], "adapted")
        self.assertIn("protocol 5", finding["reason"])


class VialLightingCodecTests(unittest.TestCase):
    def test_embedded_legacy_definition_exposes_two_independent_surfaces(self) -> None:
        value = _fixture()
        value["definition"]["lighting"] = "qmk_backlight_rgblight"
        profile = hub_vial.build_hub_profile(hub_vial.load_snapshot(value))

        surfaces = profile["capabilities"]["lighting"]["surfaces"]
        self.assertEqual([surface["id"] for surface in surfaces], ["backlight", "underglow"])
        self.assertEqual(surfaces[0]["generation"], "qmk_backlight")
        self.assertEqual(surfaces[1]["generation"], "qmk_rgblight")

    def test_vialrgb_requires_all_four_proofs_and_bounded_pixel_count(self) -> None:
        definition = {"lighting": "vialrgb"}
        info = vial_lighting.VialRGBInfo(
            protocol_version=1,
            maximum_brightness=128,
            effect_ids=(0, 1, 7),
            pixel_count=12,
        )

        self.assertEqual(
            vial_lighting.capabilities_from_definition(
                definition,
                vial_protocol=3,
                feature_flags=1,
                vialrgb_info=info,
            ),
            {"surfaces": []},
        )
        capabilities = vial_lighting.capabilities_from_definition(
            definition,
            vial_protocol=4,
            feature_flags=1,
            vialrgb_info=info,
        )
        surface = capabilities["surfaces"][0]
        self.assertEqual(surface["stream"]["pixel_count"], 12)
        self.assertEqual(surface["stream"]["max_chunk_pixels"], 9)
        self.assertTrue(surface["stream"]["volatile"])

    def test_pure_legacy_write_plan_contains_only_changed_allowlisted_values(self) -> None:
        capabilities = vial_lighting.capabilities_from_definition(
            {"lighting": "qmk_rgblight"},
            vial_protocol=6,
        )
        target = {
            "capabilities": {"lighting": capabilities},
            "lighting": {
                "surfaces": [
                    {
                        "id": "underglow",
                        "effect_id": 0,
                        "brightness": 10,
                        "speed": 20,
                        "color": [30, 40],
                    }
                ]
            },
        }
        source = copy.deepcopy(target)
        source["lighting"]["surfaces"][0].update(
            {"effect_id": 1, "brightness": 11, "color": [31, 41]}
        )

        plan = vial_lighting.plan_write(source, target)

        self.assertEqual(
            [(command.value_id, command.payload) for command in plan.commands],
            [
                (vial_lighting.QMK_RGBLIGHT_EFFECT, b"\x01"),
                (vial_lighting.QMK_RGBLIGHT_BRIGHTNESS, b"\x0b"),
                (vial_lighting.QMK_RGBLIGHT_COLOR, b"\x1f\x29"),
            ],
        )
        self.assertTrue(plan.save)

    def test_direct_effect_is_never_a_persistent_vialrgb_write(self) -> None:
        capabilities = vial_lighting.capabilities_from_definition(
            {"lighting": "vialrgb"},
            vial_protocol=4,
            feature_flags=1,
            vialrgb_info=vial_lighting.VialRGBInfo(1, 128, (0, 1), 2),
        )
        target = {
            "capabilities": {"lighting": capabilities},
            "lighting": {
                "surfaces": [
                    {
                        "id": "vialrgb",
                        "effect_id": 0,
                        "brightness": 64,
                        "speed": 2,
                        "color": [3, 4],
                    }
                ]
            },
        }
        source = copy.deepcopy(target)
        source["lighting"]["surfaces"][0]["effect_id"] = 1

        with self.assertRaises(vial_lighting.VialLightingError) as caught:
            vial_lighting.plan_write(source, target)
        self.assertIn("volatile", str(caught.exception))


class VialNormalizedMacroCodecTests(unittest.TestCase):
    def test_extended_keycodes_and_zero_low_byte_round_trip(self) -> None:
        events = [
            {"tap": 0x5200},
            {"down": 0x5203},
            {"delay_ms": 300},
            {"up": 0x5203},
            {"text": "é"},
        ]
        encoded = hub_vial.encode_macro_events(events, vial_protocol=6)
        self.assertNotIn(b"\x00", encoded)
        self.assertEqual(
            hub_vial.decode_macro_events(encoded, vial_protocol=6, slot=0), events
        )

    def test_old_protocol_refuses_extended_keycode(self) -> None:
        with self.assertRaises(hub_vial.VialSpokeError) as caught:
            hub_vial.encode_macro_events([{"tap": 0x5203}], vial_protocol=4)
        self.assertIn("protocol 5", str(caught.exception))

    def test_vial_v1_pair_encoding_round_trips_and_refuses_delays(self) -> None:
        events = [{"text": "ok"}, {"down": 0x04}, {"up": 0x04}]
        encoded = hub_vial.encode_macro_events(events, vial_protocol=1)
        self.assertEqual(encoded, b"ok\x02\x04\x03\x04")
        self.assertEqual(
            hub_vial.decode_macro_events(encoded, vial_protocol=1, slot=0), events
        )

        with self.assertRaises(hub_vial.VialSpokeError) as caught:
            hub_vial.encode_macro_events([{"delay_ms": 1}], vial_protocol=1)
        self.assertIn("protocol 2", str(caught.exception))

    def test_ambiguous_ff_range_is_refused(self) -> None:
        with self.assertRaises(hub_vial.VialSpokeError) as caught:
            hub_vial.encode_macro_events([{"tap": 0xFF52}], vial_protocol=6)
        self.assertIn("0xFF", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
