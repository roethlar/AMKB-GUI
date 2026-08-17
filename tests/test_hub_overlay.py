"""Pure cross-board first-pass overlay and worklist tests."""

from __future__ import annotations

import copy
import json
from collections import Counter
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import parse_qs, urlparse
import shutil
import tempfile
import threading
import unittest

from am_configurator import hub_overlay
from am_configurator.hub_profile import validate_hub_profile
from am_configurator.server import create_server


FIXTURE = Path(__file__).parent / "fixtures" / "hub_overlay_108_to_40.json"


def _identity(spec: dict, *, target: bool = False) -> dict:
    endpoint = {"transport": "hid" if target else "serial"}
    if target:
        endpoint.update({"vid": 0x1234, "pid": 0x5678})
    return {
        "ecosystem": spec["ecosystem"],
        "family": spec["family"],
        "wire_identity": spec["wire_identity"],
        "endpoint": endpoint,
    }


def _fixture_profiles() -> tuple[dict, dict, dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source_spec = fixture["source"]
    start, stop = source_spec["base_code_range"]
    source_codes = list(range(start, stop))
    assert len(source_codes) == source_spec["key_count"] == 108
    source = {
        "schema_version": 1,
        "identity": _identity(source_spec),
        "capabilities": {
            "keymap": {"layers": 1, "keys_per_layer": len(source_codes)}
        },
        "keymap": {
            "layers": [
                {
                    "index": 0,
                    "keys": [
                        {"key": f"K_I{index:03d}", "code": code}
                        for index, code in enumerate(source_codes)
                    ],
                }
            ]
        },
        "provenance": {"/keymap": "device"},
    }

    target_spec = fixture["target"]
    rows = target_spec["rows"]
    cols = target_spec["cols"]
    identities = [f"K_R{index // cols}_C{index % cols}" for index in range(rows * cols)]
    target = {
        "schema_version": 1,
        "identity": _identity(target_spec, target=True),
        "capabilities": {
            "keymap": {
                "layers": len(target_spec["layers"]),
                "keys_per_layer": len(identities),
            }
        },
        "keymap": {
            "layers": [
                {
                    "index": layer_index,
                    "keys": [
                        {"key": identity, "code": code}
                        for identity, code in zip(identities, codes, strict=True)
                    ],
                }
                for layer_index, codes in enumerate(target_spec["layers"])
            ],
            "matrix": {
                "rows": rows,
                "cols": cols,
                "map": {
                    identity: [index // cols, index % cols]
                    for index, identity in enumerate(identities)
                },
            },
        },
        "provenance": {"/keymap": "device"},
    }
    return source, target, fixture["expected"]


def _codes(profile: dict, layer_index: int) -> dict[str, int]:
    layer = next(
        layer for layer in profile["keymap"]["layers"] if layer["index"] == layer_index
    )
    return {entry["key"]: entry["code"] for entry in layer["keys"]}


class FullToFortyFixtureTests(unittest.TestCase):
    def test_first_pass_maps_all_alphanumerics_and_reports_every_source_key(self) -> None:
        source, target, expected = _fixture_profiles()

        result = hub_overlay.overlay_profile(source, target)

        verdicts = Counter(item["verdict"] for item in result.report["items"])
        self.assertEqual(len(result.report["items"]), expected["report_items"])
        self.assertEqual(verdicts["carried"], expected["carried"])
        self.assertEqual(verdicts["adapted"], expected["adapted"])
        self.assertEqual(verdicts["dropped"], expected["dropped"])
        target_codes = {
            code
            for layer in result.profile["keymap"]["layers"]
            for code in _codes(result.profile, layer["index"]).values()
        }
        self.assertTrue(set(expected["alphanumeric_codes"]).issubset(target_codes))
        self.assertEqual(result.profile["identity"], target["identity"])
        self.assertEqual(result.profile, validate_hub_profile(result.profile))
        self.assertEqual(result.profile["transfer_report"], result.report)

    def test_f_row_nav_and_numpad_are_worklist_items_with_target_suggestions(self) -> None:
        source, target, _expected = _fixture_profiles()

        result = hub_overlay.overlay_profile(source, target)

        worklist = {item["path"]: item for item in result.worklist}
        f1 = worklist["keymap.layers[0].keys[K_I054]"]
        self.assertEqual(
            f1["source"],
            {"layer": 0, "key": "K_I054", "code": 0x003A},
        )
        self.assertEqual(
            f1["suggestions"],
            [{"target_key": "K_R1_C0", "target_layer": 1}],
        )
        f11 = worklist["keymap.layers[0].keys[K_I064]"]
        self.assertEqual(f11["suggestions"], [])
        nav = worklist["keymap.layers[0].keys[K_I069]"]
        self.assertEqual(nav["suggestions"][0]["target_layer"], 1)
        numpad = worklist["keymap.layers[0].keys[K_I079]"]
        self.assertEqual(numpad["suggestions"][0]["target_layer"], 1)

    def test_overlay_does_not_mutate_either_input(self) -> None:
        source, target, _expected = _fixture_profiles()
        before_source = copy.deepcopy(source)
        before_target = copy.deepcopy(target)

        hub_overlay.overlay_profile(source, target)

        self.assertEqual(source, before_source)
        self.assertEqual(target, before_target)


class OverlayIdentityAndSafetyTests(unittest.TestCase):
    def test_semantic_identity_wins_even_when_current_codes_differ(self) -> None:
        source, target, _expected = _fixture_profiles()
        source["keymap"]["layers"][0]["keys"] = [
            {"key": "K_ENTER", "code": 0x1234}
        ]
        source["capabilities"]["keymap"]["keys_per_layer"] = 1
        target["keymap"]["layers"][0]["keys"][0] = {
            "key": "K_ENTER",
            "code": 0x0028,
        }
        target["keymap"]["matrix"]["map"]["K_ENTER"] = [0, 0]

        result = hub_overlay.overlay_profile(source, target)

        self.assertEqual(_codes(result.profile, 0)["K_ENTER"], 0x1234)
        self.assertEqual(result.report["items"][0]["verdict"], "carried")

    def test_matrix_identity_is_not_mistaken_for_semantic_identity(self) -> None:
        source, target, _expected = _fixture_profiles()
        source["keymap"]["layers"][0]["keys"] = [{"key": "K_R0_C0", "code": 4}]
        source["capabilities"]["keymap"]["keys_per_layer"] = 1
        target["keymap"]["layers"][0]["keys"][0]["code"] = 5
        target["keymap"]["layers"][0]["keys"][1]["code"] = 4

        result = hub_overlay.overlay_profile(source, target)

        self.assertEqual(_codes(result.profile, 0)["K_R0_C1"], 4)
        self.assertEqual(_codes(result.profile, 0)["K_R0_C0"], 5)

    def test_per_board_custom_keycode_is_never_silently_carried(self) -> None:
        source, target, _expected = _fixture_profiles()
        source["keymap"]["layers"][0]["keys"][0]["code"] = 0x7E01

        result = hub_overlay.overlay_profile(source, target)

        finding = result.report["items"][0]
        self.assertEqual(finding["verdict"], "dropped")
        self.assertIn("per-board custom", finding["reason"])

    def test_duplicate_source_semantics_are_not_guessed(self) -> None:
        source, target, _expected = _fixture_profiles()
        source["keymap"]["layers"][0]["keys"][1]["code"] = 4

        result = hub_overlay.overlay_profile(source, target)

        findings = result.report["items"][:2]
        self.assertTrue(all(item["verdict"] == "dropped" for item in findings))
        self.assertTrue(all("more than one source key" in item["reason"] for item in findings))

    def test_base_alphanumeric_adaptation_wins_a_later_layer_collision(self) -> None:
        source, target, _expected = _fixture_profiles()
        source["capabilities"]["keymap"]["layers"] = 2
        source["keymap"]["layers"].append(
            {"index": 1, "keys": [{"key": "K_I000", "code": 0x0104}]}
        )

        result = hub_overlay.overlay_profile(source, target)

        finding = next(
            item
            for item in result.report["items"]
            if item["path"] == "keymap.layers[1].keys[K_I000]"
        )
        self.assertEqual(finding["verdict"], "dropped")
        self.assertIn("conflicts", finding["reason"])
        self.assertEqual(_codes(result.profile, 1)["K_R0_C0"], 30)

    def test_non_keymap_sections_are_explicitly_deferred_not_silently_lost(self) -> None:
        source, target, _expected = _fixture_profiles()
        source["keymap"]["encoders"] = [
            {"key": "K_ENC0", "cw": 0x00E9, "ccw": 0x00EA}
        ]
        source["macros"] = [{"slot": 3, "events": [{"text": "hello"}]}]

        result = hub_overlay.overlay_profile(source, target)

        findings = {item["path"]: item for item in result.report["items"]}
        self.assertEqual(findings["keymap.encoders[0]"]["verdict"], "dropped")
        self.assertEqual(findings["macros[3]"]["verdict"], "dropped")
        self.assertNotIn("macros", result.profile)
        self.assertTrue(
            all(
                "first-pass overlay maps keymaps only" in item["reason"]
                for item in result.worklist[-2:]
            )
        )
        self.assertTrue(all("source" not in item for item in result.worklist[-2:]))

    def test_missing_keymap_is_rejected_in_plain_words(self) -> None:
        source, target, _expected = _fixture_profiles()
        del source["keymap"]

        with self.assertRaises(hub_overlay.OverlayError) as caught:
            hub_overlay.overlay_profile(source, target)

        self.assertIn("source profile has no keymap", str(caught.exception))


class OverlayRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.mkdtemp(prefix="am_hub_overlay_route_test_")
        self._saved_data_dir = os.environ.get("AM_CONFIGURATOR_DATA_DIR")
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = self._temporary
        self._server, url = create_server()
        self._token = parse_qs(urlparse(url).query)["token"][0]
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        if self._saved_data_dir is None:
            os.environ.pop("AM_CONFIGURATOR_DATA_DIR", None)
        else:
            os.environ["AM_CONFIGURATOR_DATA_DIR"] = self._saved_data_dir
        shutil.rmtree(self._temporary, ignore_errors=True)

    def _request(self, body: dict) -> tuple[int, dict]:
        request = Request(
            self._base + "/api/hub/overlay",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-AM-Token": self._token},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_authenticated_route_returns_profile_report_and_worklist(self) -> None:
        source, target, expected = _fixture_profiles()

        status, payload = self._request({"source": source, "target": target})

        self.assertEqual(status, 200)
        self.assertEqual(payload["profile"]["identity"], target["identity"])
        self.assertEqual(len(payload["report"]["items"]), expected["report_items"])
        self.assertEqual(len(payload["worklist"]), expected["dropped"])

    def test_route_rejects_unknown_fields(self) -> None:
        source, target, _expected = _fixture_profiles()

        status, payload = self._request(
            {"source": source, "target": target, "write": True}
        )

        self.assertEqual(status, 400)
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
