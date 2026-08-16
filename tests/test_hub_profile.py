"""Hub profile format: validation, canonical round-trips, provenance coverage."""

from __future__ import annotations

import copy
import json
import unittest

from am_configurator import hub_profile
from am_configurator.hub_profile import (
    HubProfileError,
    dumps_hub_profile,
    loads_hub_profile,
    uncovered_leaves,
    validate_hub_profile,
    validate_transfer_report,
)


def _identity() -> dict:
    return {
        "ecosystem": "vial",
        "family": "keychron_v6",
        "wire_identity": "keychron/v6",
        "endpoint": {"vid": 0x3434, "pid": 0x0361, "transport": "hid"},
        "protocol": {"via_protocol": 9, "vial_protocol": 6, "keycode_spec": "0.0.8"},
        "definition": {"source": "device", "hash": "sha256-" + "ab" * 32},
    }


def _profile() -> dict:
    return {
        "schema_version": 1,
        "identity": _identity(),
        "capabilities": {
            "keymap": {"layers": 4, "keys_per_layer": 108, "encoders": 1},
            "macros": {
                "budget": {"model": "bytes", "slots": 16, "buffer_bytes": 900},
                "delays": True,
            },
            "lighting": {
                "static_color": "per_key",
                "hardware_effects": [{"generation": "rgb_matrix", "ids": [0, 1, 5]}],
                "per_key_direct": True,
                "custom_animation": False,
            },
        },
        "keymap": {
            "layers": [
                {
                    "index": 0,
                    "keys": [
                        {"key": "K_ESC", "code": 0x0029},
                        {"key": "K_ENTER", "code": 0x5203},
                        {"key": "K_VENDOR", "code": 0x7E01, "carried": False},
                    ],
                }
            ],
            "matrix": {
                "rows": 6,
                "cols": 21,
                "map": {"K_ESC": [0, 0], "K_ENTER": [3, 12], "K_VENDOR": [5, 20]},
            },
            "encoders": [{"key": "K_ENC0", "cw": 0x00E9, "ccw": 0x00EA}],
        },
        "macros": [
            {
                "slot": 0,
                "events": [
                    {"down": 0x00E0},
                    {"tap": 0x0004},
                    {"up": 0x00E0},
                    {"text": "hello"},
                    {"delay_ms": 250},
                ],
            }
        ],
        "lighting": {
            "static": {"mode": "per_key", "per_key": {"K_ESC": [0, 255, 255]}},
            "hardware_effect": {"generation": "rgb_matrix", "id": 5, "speed": 128, "color": [10, 200]},
            "animations": [
                {
                    "name": "pulse",
                    "frames": [["#FF0000", "#00FF00"], ["#0000FF", "#FFFFFF"]],
                    "placement": "geometry_seam",
                }
            ],
        },
        "provenance": {
            "/keymap": "device",
            "/macros": "user",
            "/lighting/static": "user",
            "/lighting/hardware_effect": "device",
            "/lighting/animations": "user",
        },
    }


class HubProfileRoundTripTests(unittest.TestCase):
    def test_round_trip_is_identity(self) -> None:
        text = dumps_hub_profile(_profile())
        reloaded = loads_hub_profile(text)
        self.assertEqual(reloaded, validate_hub_profile(_profile()))
        self.assertEqual(dumps_hub_profile(reloaded), text)

    def test_dumps_is_canonical_sorted_json(self) -> None:
        text = dumps_hub_profile(_profile())
        parsed = json.loads(text)
        self.assertEqual(list(parsed), sorted(parsed))
        self.assertTrue(text.endswith("\n"))

    def test_validate_returns_independent_copy(self) -> None:
        source = _profile()
        validated = validate_hub_profile(source)
        source["keymap"]["layers"][0]["keys"][0]["code"] = 0
        self.assertEqual(validated["keymap"]["layers"][0]["keys"][0]["code"], 0x0029)

    def test_composed_keycodes_survive_verbatim(self) -> None:
        reloaded = loads_hub_profile(dumps_hub_profile(_profile()))
        codes = {key["key"]: key["code"] for key in reloaded["keymap"]["layers"][0]["keys"]}
        self.assertEqual(codes["K_ENTER"], 0x5203)
        self.assertEqual(codes["K_VENDOR"], 0x7E01)

    def test_minimal_profile_needs_only_version_and_identity(self) -> None:
        minimal = {"schema_version": 1, "identity": _identity()}
        self.assertEqual(loads_hub_profile(dumps_hub_profile(minimal))["identity"]["family"], "keychron_v6")


class HubProfileRejectionTests(unittest.TestCase):
    def _rejects(self, mutate, message_part: str) -> None:
        profile = _profile()
        mutate(profile)
        with self.assertRaises(HubProfileError) as caught:
            validate_hub_profile(profile)
        self.assertIn(message_part, str(caught.exception))

    def test_wrong_schema_version(self) -> None:
        self._rejects(lambda p: p.update(schema_version=2), "schema_version")

    def test_unknown_top_level_field(self) -> None:
        self._rejects(lambda p: p.update(extra=1), "unsupported fields")

    def test_spoke_addressing_is_never_stored(self) -> None:
        self._rejects(
            lambda p: p["keymap"].update(spoke_addressing={}),
            "re-derived from the pinned definition",
        )

    def test_keycode_above_16_bits(self) -> None:
        self._rejects(
            lambda p: p["keymap"]["layers"][0]["keys"][0].update(code=0x10000), "0..65535"
        )

    def test_duplicate_key_identity_in_layer(self) -> None:
        self._rejects(
            lambda p: p["keymap"]["layers"][0]["keys"].append({"key": "K_ESC", "code": 1}),
            "more than once",
        )

    def test_non_canonical_key_identity(self) -> None:
        self._rejects(
            lambda p: p["keymap"]["layers"][0]["keys"][0].update(key="Escape"),
            "canonical key identity",
        )

    def test_matrix_position_outside_declared_size(self) -> None:
        self._rejects(lambda p: p["keymap"]["matrix"]["map"].update(K_ESC=[6, 0]), "row")

    def test_macro_event_with_unknown_kind(self) -> None:
        self._rejects(
            lambda p: p["macros"][0]["events"].append({"hold": 4}), "exactly one of"
        )

    def test_macro_event_with_two_kinds(self) -> None:
        self._rejects(
            lambda p: p["macros"][0]["events"].append({"tap": 4, "delay_ms": 1}),
            "exactly one of",
        )

    def test_ragged_animation_frames(self) -> None:
        self._rejects(
            lambda p: p["lighting"]["animations"][0]["frames"].append(["#FF0000"]),
            "same number of colors",
        )

    def test_lowercase_rgb_rejected(self) -> None:
        self._rejects(
            lambda p: p["lighting"]["animations"][0]["frames"][0].__setitem__(0, "#ff0000"),
            "#RRGGBB",
        )

    def test_provenance_pointer_must_resolve(self) -> None:
        self._rejects(
            lambda p: p["provenance"].update({"/keymap/nope": "device"}),
            "does not resolve",
        )

    def test_provenance_origin_must_be_known(self) -> None:
        self._rejects(
            lambda p: p["provenance"].update({"/keymap": "guessed"}), "one of"
        )

    def test_bad_definition_hash(self) -> None:
        self._rejects(
            lambda p: p["identity"]["definition"].update(hash="sha256-short"), "sha256-"
        )

    def test_duplicate_json_field_rejected_on_load(self) -> None:
        text = dumps_hub_profile(_profile())
        doubled = text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1)
        with self.assertRaises(HubProfileError) as caught:
            loads_hub_profile(doubled)
        self.assertIn("repeats", str(caught.exception))

    def test_not_json_rejected_plainly(self) -> None:
        with self.assertRaises(HubProfileError) as caught:
            loads_hub_profile(b"not a profile")
        self.assertIn("not valid JSON", str(caught.exception))

    def test_oversized_payload_rejected(self) -> None:
        with self.assertRaises(HubProfileError) as caught:
            loads_hub_profile(b" " * (hub_profile.MAX_BYTES + 1))
        self.assertIn("MiB", str(caught.exception))


class ProvenanceCoverageTests(unittest.TestCase):
    def test_full_ancestor_coverage_leaves_nothing_uncovered(self) -> None:
        self.assertEqual(uncovered_leaves(_profile()), [])

    def test_missing_section_pointer_is_reported(self) -> None:
        profile = _profile()
        del profile["provenance"]["/macros"]
        uncovered = uncovered_leaves(profile)
        self.assertTrue(uncovered)
        self.assertTrue(all(pointer.startswith("/macros/") for pointer in uncovered))

    def test_sibling_prefix_does_not_leak_coverage(self) -> None:
        profile = {
            "schema_version": 1,
            "identity": _identity(),
            "lighting": {
                "static": {"mode": "global", "color": [1, 2, 3]},
                "hardware_effect": {"generation": "rgblight", "id": 1},
            },
            "provenance": {"/lighting/static": "user"},
        }
        uncovered = uncovered_leaves(profile)
        self.assertTrue(all(p.startswith("/lighting/hardware_effect") for p in uncovered))
        self.assertTrue(uncovered)


class TransferReportTests(unittest.TestCase):
    def _report(self) -> dict:
        return {
            "source": _identity(),
            "target": {"ecosystem": "am", "family": "NEON", "wire_identity": "80"},
            "items": [
                {"path": "keymap.layers[0].keys[K_ENTER]", "verdict": "carried"},
                {
                    "path": "macros[2].events[4]",
                    "verdict": "adapted",
                    "reason": "delays unsupported on VIA protocol 9; delay dropped",
                },
                {
                    "path": "lighting.animations[0]",
                    "verdict": "dropped",
                    "reason": "target has no custom_animation capability",
                },
            ],
        }

    def test_valid_report_round_trips_inside_profile(self) -> None:
        profile = {"schema_version": 1, "identity": _identity(), "transfer_report": self._report()}
        reloaded = loads_hub_profile(dumps_hub_profile(profile))
        verdicts = [item["verdict"] for item in reloaded["transfer_report"]["items"]]
        self.assertEqual(verdicts, ["carried", "adapted", "dropped"])

    def test_adapted_requires_a_reason(self) -> None:
        report = self._report()
        del report["items"][1]["reason"]
        with self.assertRaises(HubProfileError) as caught:
            validate_transfer_report(report)
        self.assertIn("reason", str(caught.exception))

    def test_dropped_requires_a_reason(self) -> None:
        report = self._report()
        del report["items"][2]["reason"]
        with self.assertRaises(HubProfileError):
            validate_transfer_report(report)

    def test_unknown_verdict_rejected(self) -> None:
        report = self._report()
        report["items"][0]["verdict"] = "skipped"
        with self.assertRaises(HubProfileError):
            validate_transfer_report(report)


if __name__ == "__main__":
    unittest.main()
