"""The AM spoke: AM configurations expressed as hub profiles, and its route."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from am_configurator import hub_am
from am_configurator.hub_am import AmSpokeError, build_hub_profile
from am_configurator.hub_profile import uncovered_leaves, validate_hub_profile
from am_configurator.server import create_server


def _neon_layer(fill: str = "#00070004") -> list[str]:
    codes = [fill] * 90
    codes[0] = "#00070029"  # Esc
    codes[1] = "#02070004"  # Shift+A
    codes[2] = "#00FF5101"  # raw QMK passthrough, proven on hardware
    codes[3] = "#00951510"  # AM-only code with no QMK spelling
    return codes


def _neon_config() -> dict:
    return {
        "product_info": {"product_id": "NEON80"},
        "key_layer": {"layer_num": 1, "layer_data": [{"layer": _neon_layer()}]},
        "macro_key": [
            {
                "original_key": "#00920100",
                "layer_key": ["#11070004", "#10070004"],
                "intvel_ms": [50, 0],
            }
        ],
        "page_data": [
            {
                "page_index": 1,
                "keyframes": {
                    "frame_num": 2,
                    "frame_data": [
                        {"frame_index": 0, "frame_RGB": ["#ff0000"] * 90},
                        {"frame_index": 1, "frame_RGB": ["#00ff00"] * 90},
                    ],
                },
            }
        ],
    }


class AmSpokeTests(unittest.TestCase):
    def test_profile_validates_and_identifies_the_board(self) -> None:
        profile = build_hub_profile(_neon_config())
        self.assertEqual(profile, validate_hub_profile(profile))
        self.assertEqual(profile["identity"]["ecosystem"], "am")
        self.assertEqual(profile["identity"]["family"], "NEON")
        self.assertEqual(profile["identity"]["wire_identity"], "NEON80")
        self.assertEqual(profile["identity"]["endpoint"]["transport"], "hid")

    def test_keymap_uses_positional_identities_and_translated_codes(self) -> None:
        keys = build_hub_profile(_neon_config())["keymap"]["layers"][0]["keys"]
        by_identity = {key["key"]: key for key in keys}
        self.assertEqual(len(keys), 90)
        self.assertEqual(by_identity["K_I000"]["code"], 0x0029)
        self.assertEqual(by_identity["K_I001"]["code"], 0x0204)
        self.assertEqual(by_identity["K_I002"]["code"], 0x5101)

    def test_untranslatable_code_is_kept_native_not_guessed(self) -> None:
        keys = build_hub_profile(_neon_config())["keymap"]["layers"][0]["keys"]
        entry = {key["key"]: key for key in keys}["K_I003"]
        self.assertEqual(
            entry, {"key": "K_I003", "code": 0, "carried": False, "native": "#00951510"}
        )

    def test_macro_events_decode_down_up_and_delay(self) -> None:
        macros = build_hub_profile(_neon_config())["macros"]
        self.assertEqual(
            macros,
            [
                {
                    "slot": 0,
                    "events": [{"down": 0x0004}, {"delay_ms": 50}, {"up": 0x0004}],
                }
            ],
        )

    def test_lighting_tracks_become_named_animations(self) -> None:
        animations = build_hub_profile(_neon_config())["lighting"]["animations"]
        self.assertEqual(animations[0]["name"], "page1.keyframes")
        self.assertEqual(animations[0]["placement"], "geometry_seam")
        self.assertEqual(animations[0]["frames"][0][0], "#FF0000")
        self.assertEqual(len(animations[0]["frames"][0]), 90)

    def test_neon_budget_is_bytes_serial_budget_is_events(self) -> None:
        neon = build_hub_profile(_neon_config())
        self.assertEqual(
            neon["capabilities"]["macros"]["budget"],
            {"model": "bytes", "slots": 16, "buffer_bytes": 6677},
        )
        serial = {
            "product_info": {"product_id": "CB04"},
            "key_layer": {
                "layer_num": 1,
                "layer_data": [{"layer": ["#00070004"] * 200}],
            },
        }
        cb = build_hub_profile(serial)
        self.assertEqual(
            cb["capabilities"]["macros"]["budget"],
            {"model": "events", "tracks": 32, "events_total": 200},
        )
        self.assertEqual(cb["identity"]["endpoint"]["transport"], "serial")

    def test_provenance_covers_every_exported_section(self) -> None:
        profile = build_hub_profile(_neon_config(), origin="device")
        self.assertEqual(uncovered_leaves(profile), [])
        self.assertEqual(profile["provenance"]["/keymap"], "device")

    def test_unknown_product_fails_plainly(self) -> None:
        with self.assertRaises(AmSpokeError):
            build_hub_profile({"product_info": {"product_id": "MYSTERY"}})

    def test_wrong_layer_width_fails_plainly(self) -> None:
        config = _neon_config()
        config["key_layer"]["layer_data"][0]["layer"] = ["#00070004"] * 89
        with self.assertRaises(AmSpokeError) as caught:
            build_hub_profile(config)
        self.assertIn("exactly 90", str(caught.exception))

    def test_bad_macro_marker_fails_plainly(self) -> None:
        config = _neon_config()
        config["macro_key"][0]["layer_key"][0] = "#00070004"
        with self.assertRaises(AmSpokeError) as caught:
            build_hub_profile(config)
        self.assertIn("key-down", str(caught.exception))

    def test_bad_origin_is_rejected(self) -> None:
        with self.assertRaises(AmSpokeError):
            build_hub_profile(_neon_config(), origin="guessed")


class HubExportRouteTests(unittest.TestCase):
    """POST /api/hub/export drives the AM spoke over the real loopback server."""

    _DEFAULT = object()

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="am_hub_route_test_")
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME")
        }
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = self._tmp
        self._server, url = create_server()
        self._token = parse_qs(urlparse(url).query)["token"][0]
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _request(self, method, path, body=None, token=_DEFAULT):
        headers = {}
        tok = self._token if token is self._DEFAULT else token
        if tok is not None:
            headers["X-AM-Token"] = tok
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._base + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, (json.loads(raw) if raw else None)

    def test_export_returns_a_validated_hub_profile(self) -> None:
        status, response = self._request(
            "POST", "/api/hub/export", {"config": _neon_config(), "origin": "device"}
        )
        self.assertEqual(200, status)
        profile = response["profile"]
        self.assertEqual(profile, validate_hub_profile(profile))
        self.assertEqual(profile["identity"]["family"], "NEON")
        self.assertEqual(profile["provenance"]["/keymap"], "device")

    def test_export_rejects_an_invalid_configuration(self) -> None:
        status, response = self._request(
            "POST", "/api/hub/export", {"config": {"product_info": {}}}
        )
        self.assertEqual(400, status)
        self.assertIn("error", response)

    def test_export_rejects_unknown_body_fields(self) -> None:
        status, _ = self._request(
            "POST",
            "/api/hub/export",
            {"config": _neon_config(), "surprise": 1},
        )
        self.assertEqual(400, status)


if __name__ == "__main__":
    unittest.main()
