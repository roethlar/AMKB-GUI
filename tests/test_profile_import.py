from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from am_configurator import profile_import, server, writer


FIXTURE = Path(__file__).parent / "fixtures" / "am_master_import_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _layer(fill: str = "#00000000") -> dict:
    return {"layer": [fill] * 200}


def _placeholder(kind: str) -> dict:
    frame_index: int | str = "0" if kind in {"string", "malformed"} else 0
    color = "not-a-color" if kind == "malformed" else "#000000"
    return {
        "valid": False,
        "frame_num": 0,
        "frame_data": [{"frame_index": frame_index, "frame_RGB": [color]}],
    }


def _synthetic_afa(case: dict) -> dict:
    order = case["placeholder_order"]
    pages = []
    placeholder_index = 0
    for index in range(8):
        page = {
            "//": f"page {index}",
            "valid": 1 if index < 3 or index >= 5 else 0,
            "page_index": index,
            "lightness": 100,
            "speed_ms": 90 if index >= 5 else 50,
            "color": {
                "default": False,
                "back_rgb": "#abcdef" if index == 0 else "#000000",
                "rgb": "#FFFFFF" if index == 2 else "#000000",
            },
            "word_page": {"valid": 0, "word_len": 0, "unicode": []},
            "frames": {"valid": 0, "frame_num": 0, "frame_data": []},
            "keyframes": {"valid": 0, "frame_num": 0, "frame_data": []},
        }
        if index < 5:
            for track in ("frames", "keyframes"):
                page[track] = _placeholder(order[placeholder_index % len(order)])
                placeholder_index += 1
        pages.append(page)
    layers = [_layer() for _ in range(7)]
    layers[0]["layer"][0] = "#0007000a"
    return {
        "product_info": {
            "product_info_addr": "product_info_addr",
            "product_id": "ALICE",
            "synthetic_case": case["case"],
        },
        "page_num": len(pages),
        "page_data": pages,
        "key_layer": {
            "//": "seven synthetic layers",
            "valid": 1,
            "layer_num": len(layers),
            "layer_data": layers,
        },
        "tab_key": [],
        "tab_key_num": 0,
        "macro_key": [],
        "exchange_num": 0,
        "exchange_key": [],
        "Fn_key_num": 0,
        "Fn_key": [],
        "MACRO_key_num": 0,
        "MACRO_key": [],
        "swap_key_num": 0,
        "swap_key": [],
    }


def _synthetic_color(frame_index: int, color_index: int, salt: int) -> str:
    return f"{(frame_index * 4099 + color_index * 17 + salt) & 0xFFFFFF:06x}"


def _synthetic_lighting(case: dict) -> dict:
    count = case["frame_count"]
    result = {
        "speed": case["speed"],
        "brightness": case["brightness"],
        "frames": [
            [_synthetic_color(frame, pixel, 0x123456) for pixel in range(230)]
            for frame in range(count)
        ],
        "frames_axial": [
            [_synthetic_color(frame, pixel, 0x654321) for pixel in range(89)]
            for frame in range(count)
        ],
    }
    if "description" in case:
        result["description"] = case["description"]
    return result


def _import(value: object) -> profile_import.ImportReport:
    return profile_import.import_json_bytes(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        profile_validator=server._validated_profile_config,
    )


class ProfileImportTests(unittest.TestCase):
    def test_four_synthetic_afa_shapes_normalize_only_vendor_conventions(self) -> None:
        for case in CASES["full_profiles"]:
            with self.subTest(case=case["case"]):
                source = _synthetic_afa(case)
                before = server.validate_config(source)
                self.assertFalse(before["ok"])
                self.assertTrue(
                    any("frame_num does not match frame_data" in error for error in before["errors"])
                )

                report = _import(source)
                self.assertEqual(profile_import.AM_MASTER_PROFILE, report.source_format)
                self.assertEqual(profile_import.PROFILE_KIND, report.kind)
                normalized = report.profile()
                self.assertEqual(case["case"], normalized["product_info"]["synthetic_case"])
                self.assertNotIn("//", normalized["key_layer"])
                self.assertTrue(all("//" not in page for page in normalized["page_data"]))
                self.assertEqual("#0007000A", normalized["key_layer"]["layer_data"][0]["layer"][0])
                self.assertEqual("#ABCDEF", normalized["page_data"][0]["color"]["back_rgb"])
                placeholders = [
                    page[track]
                    for page in normalized["page_data"][:5]
                    for track in ("frames", "keyframes")
                ]
                self.assertTrue(all(track["frame_data"] == [] for track in placeholders))
                self.assertTrue(server.validate_config(normalized)["ok"])
                self.assertGreater(writer.plan(normalized).total, 0)
                notes = {note["code"]: note["count"] for note in report.to_response()["normalizations"]}
                self.assertEqual(9, notes["am_master_comments_removed"])
                self.assertEqual(10, notes["am_master_disabled_placeholders"])
                self.assertEqual(1, notes["assignment_case"])
                self.assertEqual(1, notes["rgb_case"])
                messages = [
                    note["message"]
                    for note in report.to_response()["normalizations"]
                ]
                self.assertIn("AM Master comments removed: 9.", messages)
                self.assertIn(
                    "Disabled zero-frame placeholders normalized: 10.",
                    messages,
                )
                self.assertFalse(any("removeds" in message for message in messages))

    def test_enabled_malformed_track_is_never_treated_as_a_placeholder(self) -> None:
        source = _synthetic_afa(CASES["full_profiles"][0])
        source["page_data"][0]["frames"]["valid"] = True
        with self.assertRaisesRegex(ValueError, "frame_num does not match frame_data"):
            _import(source)

    def test_app_native_profile_round_trips_without_normalization(self) -> None:
        source = _synthetic_afa(CASES["full_profiles"][0])
        for page in source["page_data"]:
            page.pop("//")
            for track in ("frames", "keyframes"):
                if track in page and page[track].get("valid") is False:
                    page[track]["frame_data"] = []
        source["key_layer"].pop("//")
        source["key_layer"]["layer_data"][0]["layer"][0] = "#0007000A"
        source["page_data"][0]["color"]["back_rgb"] = "#ABCDEF"

        report = _import(source)
        self.assertEqual(profile_import.AM_CONFIGURATOR_PROFILE, report.source_format)
        self.assertEqual([], report.to_response()["normalizations"])
        self.assertEqual(source, report.profile())
        first = report.profile()
        first["product_info"]["product_id"] = "changed"
        self.assertEqual("ALICE", report.profile()["product_info"]["product_id"])

    def test_confirmed_lighting_shapes_preserve_exact_tracks_timing_and_order(self) -> None:
        for case in CASES["lighting"]:
            with self.subTest(case=case["case"]):
                source = _synthetic_lighting(case)
                report = _import(source)
                self.assertEqual(profile_import.AM_MASTER_AM80_LIGHTING, report.source_format)
                self.assertEqual(profile_import.LIGHTING_KIND, report.kind)
                lighting = report.lighting()
                mapped = lighting["mapped_result"]
                destination = lighting["destination"]
                self.assertEqual("NEON80", destination["product_id"])
                self.assertEqual("NEON", destination["family"])
                self.assertIsNone(destination["slot"])
                self.assertEqual(case["frame_count"], mapped["source_frames"])
                self.assertEqual(case["frame_count"], mapped["decoded_frames"])
                self.assertEqual(case["speed"], mapped["duration_ms"])
                self.assertEqual(case["frame_count"] * case["speed"], mapped["source_duration_ms"])
                self.assertEqual(case["frame_count"], mapped["tracks"]["head"]["frame_count"])
                self.assertEqual(case["frame_count"], mapped["tracks"]["axial"]["frame_count"])
                self.assertTrue(all(len(frame) == 230 for frame in mapped["tracks"]["head"]["frames"]))
                self.assertTrue(all(len(frame) == 89 for frame in mapped["tracks"]["axial"]["frames"]))
                for target, source_field in (("head", "frames"), ("axial", "frames_axial")):
                    self.assertEqual(
                        f"#{source[source_field][0][0].upper()}",
                        mapped["tracks"][target]["frames"][0][0],
                    )
                    self.assertEqual(
                        f"#{source[source_field][-1][-1].upper()}",
                        mapped["tracks"][target]["frames"][-1][-1],
                    )
                expected_brightness = 100 if case["brightness"] == 255 else case["brightness"]
                self.assertEqual(expected_brightness, destination["lightness"])
                self.assertEqual(case.get("description"), lighting["description"])
                self.assertIn(
                    f"AM Master RGB values converted to #RRGGBB: {case['frame_count'] * 319}.",
                    [
                        note["message"]
                        for note in report.to_response()["normalizations"]
                    ],
                )
                defensive = report.lighting()
                defensive["mapped_result"]["tracks"]["head"]["frames"][0][0] = "#000000"
                self.assertEqual(
                    f"#{source['frames'][0][0].upper()}",
                    report.lighting()["mapped_result"]["tracks"]["head"]["frames"][0][0],
                )

    def test_lighting_brightness_accepts_percent_and_255_only(self) -> None:
        base = _synthetic_lighting(CASES["lighting"][1])
        for brightness in (0, 1, 99, 100, 255):
            with self.subTest(brightness=brightness):
                source = copy.deepcopy(base)
                source["brightness"] = brightness
                report = _import(source)
                self.assertEqual(
                    100 if brightness == 255 else brightness,
                    report.lighting()["destination"]["lightness"],
                )
        for brightness in (101, 127, 254):
            with self.subTest(brightness=brightness), self.assertRaisesRegex(
                ValueError,
                "brightness",
            ):
                source = copy.deepcopy(base)
                source["brightness"] = brightness
                _import(source)

    def test_strict_parser_and_lighting_schema_reject_before_returning_content(self) -> None:
        base = _synthetic_lighting(CASES["lighting"][1])
        cases: list[tuple[str, bytes]] = [
            ("duplicate key", b'{"speed":90,"speed":100,"brightness":100,"frames":[],"frames_axial":[]}'),
            ("nonstandard number", b'{"speed":NaN,"brightness":100,"frames":[],"frames_axial":[]}'),
            ("non-object", b"[]"),
            ("invalid UTF-8", b'{"product_info":"\xff"}'),
            ("oversize", b" " * (profile_import.MAX_JSON_BYTES + 1)),
        ]
        mutations = {
            "unknown field": lambda value: value.update({"unexpected": True}),
            "invalid color": lambda value: value["frames"][0].__setitem__(0, "GG0000"),
            "unequal tracks": lambda value: value["frames_axial"].append(value["frames_axial"][0]),
            "wrong head pixels": lambda value: value["frames"][0].pop(),
            "wrong axial pixels": lambda value: value["frames_axial"][0].pop(),
            "unsupported speed": lambda value: value.__setitem__("speed", 91),
            "malformed description": lambda value: value.__setitem__("description", ["not text"]),
        }
        for label, mutate in mutations.items():
            value = copy.deepcopy(base)
            mutate(value)
            cases.append((label, json.dumps(value).encode("utf-8")))
        too_many = copy.deepcopy(base)
        too_many["frames"] = [too_many["frames"][0]] * 257
        too_many["frames_axial"] = [too_many["frames_axial"][0]] * 257
        cases.append(("excess frames", json.dumps(too_many).encode("utf-8")))

        too_deep: dict[str, object] = {}
        cursor = too_deep
        for _ in range(66):
            child: dict[str, object] = {}
            cursor["nested"] = child
            cursor = child
        cases.append(("excess nesting", json.dumps(too_deep).encode("utf-8")))

        for label, payload in cases:
            with self.subTest(label=label), self.assertRaises(ValueError):
                profile_import.import_json_bytes(
                    payload,
                    profile_validator=server._validated_profile_config,
                )

        with patch.object(profile_import, "_MAX_JSON_VALUES", 4), self.assertRaisesRegex(
            ValueError,
            "too many values",
        ):
            profile_import.import_json_bytes(
                b'{"product_info":[1,2,3,4]}',
                profile_validator=server._validated_profile_config,
            )


if __name__ == "__main__":
    unittest.main()
