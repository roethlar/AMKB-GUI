from __future__ import annotations

import base64
import copy
import io
import json
import os
import re
import shutil
import socket
import ssl
import stat
import sys
import tempfile
import threading
import time
import tomllib
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
from am_configurator import __version__
from am_configurator.server import (
    AcceptedWriteError,
    _classify_macro_readback,
    _device_matches_config,
    _keymap_differences,
    _macro_references,
    _probe_keyboard,
    _reconcile_read_macros,
    _stored_device_config,
    _verify_keymap_readback,
    blank_config,
    config_transfer_options,
    create_server,
    extract_importable_macros,
    frames_to_led_tracks,
    gif_to_led_frames,
    gif_to_led_tracks,
    firmware_led_speed,
    _MAX_GIF_FRAMES,
    merge_configs,
    text_to_macro_events,
    validate_config,
)
from am_configurator.protocol import build_frame
from am_configurator.device import candidate_ports
from am_configurator.protocol import exclusive_serial_kwargs
from am_configurator.macros import macro_frames, parse_macro_frames
from am_configurator.writer import car_light_data_frames, car_light_info_frames
from am_configurator import llm, server, store


_DEFAULT_SETTINGS = {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {}}}


class SettingsStoreTests(unittest.TestCase):
    """Strict app-level settings store: defaults, round-trip, recovery, env override."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="am_settings_test_")
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME", "XAI_API_KEY")
        }
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ.pop("XAI_API_KEY", None)
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_defaults_when_missing(self) -> None:
        self.assertEqual(store.load_settings(), _DEFAULT_SETTINGS)
        # A missing file must not be created as a side effect of reading it.
        self.assertFalse(store.settings_path().exists())

    def test_round_trip(self) -> None:
        payload = {
            "llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": "sk-test"}}
        }
        store.save_settings(payload)
        self.assertEqual(store.load_settings(), payload)

    def test_unknown_fields_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store.save_settings(
                {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {}}, "bogus": 1}
            )
        with self.assertRaises(ValueError):
            store.save_settings(
                {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {}, "bogus": 1}}
            )
        with self.assertRaises(ValueError):
            store.save_settings(
                {"llm": {"interpreter": "nope", "renderer": "grok", "keys": {}}}
            )
        with self.assertRaises(ValueError):
            store.save_settings(
                {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"bogus": "x"}}}
            )
        # A rejected save must persist nothing.
        self.assertFalse(store.settings_path().exists())

    def test_mask_sentinel_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store.save_settings(
                {
                    "llm": {
                        "interpreter": "grok",
                        "renderer": "grok",
                        "keys": {"xai": store.KEY_MASK},
                    }
                }
            )
        self.assertFalse(store.settings_path().exists())

    def test_empty_key_clears(self) -> None:
        store.save_settings(
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": "sk-test"}}}
        )
        store.save_settings(
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": ""}}}
        )
        self.assertEqual(store.load_settings()["llm"]["keys"], {})
        self.assertIsNone(store.resolve_xai_key())

    def test_corrupt_file_recovers(self) -> None:
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not valid json", encoding="utf-8")
        self.assertEqual(store.load_settings(), _DEFAULT_SETTINGS)
        self.assertFalse(path.exists())
        self.assertTrue(path.with_name(path.name + ".bad").exists())

    def test_env_override(self) -> None:
        store.save_settings(
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": "sk-disk"}}}
        )
        before = store.settings_path().read_text(encoding="utf-8")
        os.environ["XAI_API_KEY"] = "sk-env"
        self.assertEqual(store.resolve_xai_key(), "sk-env")
        # The env override is never persisted; disk content is untouched.
        self.assertEqual(store.settings_path().read_text(encoding="utf-8"), before)
        self.assertEqual(store.load_settings()["llm"]["keys"]["xai"], "sk-disk")

    def test_error_message_omits_secret(self) -> None:
        secret = "sk-super-secret-should-never-be-logged"
        with self.assertRaises(ValueError) as ctx:
            store.save_settings(
                {
                    "llm": {
                        "interpreter": "nope",
                        "renderer": "grok",
                        "keys": {"xai": secret},
                    }
                }
            )
        self.assertNotIn(secret, str(ctx.exception))

    def test_file_permissions(self) -> None:
        store.save_settings(
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": "sk-test"}}}
        )
        if sys.platform.startswith("win"):
            self.skipTest("POSIX file permissions are not enforced on Windows")
        mode = stat.S_IMODE(os.stat(store.settings_path()).st_mode)
        self.assertEqual(mode, 0o600)


def _layer(fill: str = "#00000000") -> dict:
    return {"layer": [fill] * 200}


def _base_config(product: str = "80") -> dict:
    return {
        "product_info": {"product_info_addr": "product_info_addr", "product_id": product},
        "page_num": 0,
        "page_data": [],
        "tab_key": [],
        "tab_key_num": 0,
        "macro_key": [],
        "MACRO_key": [],
        "MACRO_key_num": 0,
        "exchange_key": [],
        "exchange_num": 0,
        "swap_key": [],
        "swap_key_num": 0,
        "Fn_key": [],
        "Fn_key_num": 0,
        "key_layer": {"valid": 1, "layer_num": 2, "layer_data": [_layer(), _layer()]},
    }


class DesktopServerTests(unittest.TestCase):
    def test_keyboard_probe_does_not_shadow_device_module(self) -> None:
        keyboard = SimpleNamespace(is_keyboard=True)
        with patch("am_configurator.device.probe", return_value=keyboard) as probe:
            result = _probe_keyboard("/dev/example", attempts=1)

        self.assertIs(keyboard, result)
        probe.assert_called_once_with("/dev/example", full=True)

    def test_package_declares_native_desktop_entry_point(self) -> None:
        metadata = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(metadata["project"]["version"], __version__)
        self.assertEqual(
            "am_configurator.desktop:main",
            metadata["project"]["gui-scripts"]["am-configurator"],
        )

    def test_empty_state_copy_names_the_current_device_read_action(self) -> None:
        source = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("Devices → Read keymap &amp; macros", source)
        self.assertNotIn("Device → Read", source)

    def test_am21_creates_relic_edge_tracks_only_for_custom_slots(self) -> None:
        source = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )
        create_pages = re.search(
            r"function createLedPages\(\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(create_pages)
        compact = re.sub(r"\s+", "", create_pages.group("body"))
        self.assertIn(
            'productFamily(productId())==="80"&&index>=5',
            compact,
        )
        self.assertNotIn('productId().toUpperCase()==="80"', compact)

    def test_write_action_is_in_main_toolbar_not_device_picker(self) -> None:
        source = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        toolbar = re.search(r'<div class="top-actions">(?P<body>.*?)</div>', source, re.DOTALL)
        picker = re.search(r'<div id="device-actions".*?>(?P<body>.*?)</div>', source, re.DOTALL)
        self.assertIsNotNone(toolbar)
        self.assertIsNotNone(picker)
        self.assertIn('id="write-button"', toolbar.group("body"))
        self.assertNotIn('id="write-button"', picker.group("body"))
        self.assertNotIn('id="write-device"', source)

    def test_incompatible_profile_ui_explains_and_recovers_from_mismatch(self) -> None:
        html = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )

        for element_id in (
            "compatibility-banner",
            "incompatible-dialog",
            "import-incompatible-macros",
            "open-incompatible",
            "return-connected-workspace",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', html)

        self.assertIn("/api/config/compatibility", script)
        self.assertIn("Open as detached file", html)
        self.assertIn("Import macros only", html)
        self.assertIn("Keymaps and LED tracks use model-specific indexes", html)
        self.assertIn('$("#save-button").disabled = !state.config;', script)

    def test_relic_layer_7_am_controls_are_available_in_key_palette(self) -> None:
        source = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )
        table = re.search(r"const VENDOR = \{(?P<body>.*?)\n\};", source, re.DOTALL)
        self.assertIsNotNone(table)
        controls = {
            int(usage, 16): label
            for usage, label in re.findall(
                r'0x([0-9a-f]+):"([^"]+)"', table.group("body")
            )
        }
        captured = {
            0x0106: "Bluetooth 1",
            0x0107: "Bluetooth 2",
            0x0108: "Bluetooth 3",
            0x0130: "2.4G",
            0x0900: "Next PCB",
            0x0901: "PCB Bright +",
            0x0902: "PCB Bright −",
            0x0903: "PCB On / Off",
            0x0904: "PCB Speed +",
            0x0905: "PCB Speed −",
            0x090B: "Nameplate Bright +",
            0x090C: "Nameplate Bright −",
            0x090D: "Nameplate On / Off",
            0x090E: "Nameplate Color",
            0x090F: "Next Nameplate",
            0x0910: "Battery",
            0x0A02: "Reset",
            0x0C0B: "Fn 2",
            0x0C0F: "Layer 1",
            0x0C10: "Layer 2",
            0x0C11: "Layer 3",
            0x0C12: "Layer 4",
            0x0C13: "Layer 5",
            0x0C14: "Layer 6",
            0x0C15: "Layer 7",
            0x0C20: "Fn 1",
            0x0C22: "Fn 3",
            0x0C23: "Fn 4",
            0x0C24: "Fn 5",
            0x0C25: "Fn 6",
            0x0C26: "Fn 7",
        }
        self.assertEqual(captured, {usage: controls[usage] for usage in captured})

    def test_last_verified_config_can_supply_unreadable_led_data(self) -> None:
        stored = _base_config("80")
        with patch("am_configurator.store.load_current", return_value=stored):
            restored, warning = _stored_device_config("AM21")
        self.assertEqual(stored, restored)
        self.assertIsNot(stored, restored)
        self.assertIsNone(warning)

    def test_invalid_last_verified_config_is_not_used(self) -> None:
        with patch(
            "am_configurator.store.load_current",
            return_value={"product_info": {"product_id": "ALICE"}},
        ):
            restored, warning = _stored_device_config("AM21")
        self.assertIsNone(restored)
        self.assertIn("invalid", warning.lower())

    def test_keymap_readback_retries_a_transient_commit_mismatch(self) -> None:
        expected = [["#00070004", "#00070005"]]
        stale = [["#00000000", "#00000000"]]
        with (
            patch("am_configurator.reader.read_keymap", side_effect=[stale, expected]) as read,
            patch("am_configurator.server.time.sleep") as sleep,
        ):
            actual = _verify_keymap_readback(
                "/dev/example", expected, attempts=2, retry_seconds=0.01
            )
        self.assertEqual(expected, actual)
        self.assertEqual(2, read.call_count)
        sleep.assert_called_once_with(0.01)

    def test_keymap_readback_reports_exact_persistent_differences(self) -> None:
        expected = [["#00070004", "#00070005"]]
        actual = [["#00070004", "#00070006"]]
        self.assertEqual(
            (1, ["layer 1 key 1: expected #00070005, got #00070006"]),
            _keymap_differences(expected, actual),
        )
        with (
            patch("am_configurator.reader.read_keymap", return_value=actual),
            patch("am_configurator.server.time.sleep"),
            self.assertRaisesRegex(AcceptedWriteError, "layer 1 key 1"),
        ):
            _verify_keymap_readback(
                "/dev/example", expected, attempts=2, retry_seconds=0.01
            )

    def test_loopback_server_can_be_owned_by_a_native_window(self) -> None:
        server, url = create_server()
        self.assertEqual("127.0.0.1", server.server_address[0])
        token = parse_qs(urlparse(url).query)["token"][0]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(url, timeout=2) as response:
                page = response.read()
                self.assertIn(b"AM Configurator", page)
                version_badge = (
                    f'id="app-version" title="Application version">'
                    f"v{__version__}</span>"
                ).encode()
                self.assertIn(
                    version_badge,
                    page,
                )
                self.assertNotIn(b"__AM_VERSION__", page)
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/config",
                headers={"X-AM-Token": token},
            )
            with urlopen(request, timeout=2) as response:
                self.assertEqual(b'{"config": null}', response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_cross_platform_usb_serial_discovery(self) -> None:
        def port(device: str, *, vid: int | None = None, hwid: str = "") -> SimpleNamespace:
            return SimpleNamespace(
                device=device,
                vid=vid,
                hwid=hwid,
                description="Angry Miao" if vid else "",
                manufacturer="",
                product="",
            )

        cases = (
            ("Darwin", [port("/dev/tty.usbmodem1", vid=1), port("/dev/cu.usbmodem1", vid=1)], ["/dev/cu.usbmodem1"]),
            ("Windows", [port("COM4", vid=1), port("COM1")], ["COM4"]),
            ("Linux", [port("/dev/ttyACM0"), port("/dev/ttyS0")], ["/dev/ttyACM0"]),
        )
        for system, ports, expected in cases:
            with self.subTest(system=system), patch("am_configurator.device.platform.system", return_value=system), patch("am_configurator.device.list_ports.comports", return_value=ports):
                self.assertEqual(expected, candidate_ports())

    def test_windows_omits_posix_exclusive_serial_flag(self) -> None:
        with patch("am_configurator.protocol.sys.platform", "win32"):
            self.assertEqual({}, exclusive_serial_kwargs())
        with patch("am_configurator.protocol.sys.platform", "darwin"):
            self.assertEqual({"exclusive": True}, exclusive_serial_kwargs())


def _page(index: int) -> dict:
    return {
        "valid": 1,
        "page_index": index,
        "lightness": 100,
        "speed_ms": 90,
        "color": {"default": False, "back_rgb": "#000000", "rgb": "#000000"},
        "word_page": {"valid": 0, "word_len": 0, "unicode": []},
        "frames": {"valid": 0, "frame_num": 0, "frame_data": []},
        "keyframes": {"valid": 0, "frame_num": 0, "frame_data": []},
    }


class MergeTests(unittest.TestCase):
    def test_led_and_key_exports_merge_in_either_order(self) -> None:
        lighting = _base_config()
        lighting["page_data"] = [_page(i) for i in range(8)]
        lighting["page_num"] = 8
        key = _base_config()
        key["key_layer"]["layer_data"][0]["layer"][4] = "#00070004"
        key["macro_key"] = [{
            "original_key": "#00951500",
            "layer_key": ["#11070004", "#10070004"],
            "intvel_ms": [25, 25],
        }]

        for pair in ([lighting, key], [key, lighting]):
            merged = merge_configs(pair)
            self.assertEqual(8, len(merged["page_data"]))
            self.assertEqual("#00070004", merged["key_layer"]["layer_data"][0]["layer"][4])
            self.assertEqual(1, len(merged["macro_key"]))

    def test_validation_reports_key_only_warning(self) -> None:
        result = validate_config(_base_config())
        self.assertTrue(result["ok"])
        self.assertTrue(any("key-only" in warning for warning in result["warnings"]))

    def test_product_matching(self) -> None:
        self.assertTrue(_device_matches_config("AM21", "80"))
        self.assertTrue(_device_matches_config("ALICE", "ALICE"))
        self.assertTrue(_device_matches_config("CB04", "CB_XX"))
        self.assertFalse(_device_matches_config("AM21", "ALICE"))

    def test_cross_board_transfer_allows_only_portable_macros(self) -> None:
        source = _base_config("80")
        source["page_data"] = [_page(index) for index in range(8)]
        source["macro_key"] = [{
            "original_key": "#00951500",
            "layer_key": ["#11070004", "#10070004"],
            "intvel_ms": [25, 0],
        }]

        cross_board = config_transfer_options(source, "CB04")
        self.assertFalse(cross_board["compatible"])
        self.assertTrue(cross_board["can_import_macros"])
        self.assertEqual(1, cross_board["macro_count"])
        self.assertFalse(cross_board["can_merge_keymap"])
        self.assertFalse(cross_board["can_merge_leds"])

        same_board = config_transfer_options(source, "AM21")
        self.assertTrue(same_board["compatible"])
        self.assertTrue(same_board["can_merge_keymap"])
        self.assertTrue(same_board["can_merge_leds"])

    def test_blank_config_from_device_is_writable(self) -> None:
        config = blank_config("AM21", [["#00000000"] * 200] * 7, [])
        self.assertEqual("80", config["product_info"]["product_id"])
        self.assertEqual(8, len(config["page_data"]))
        self.assertEqual(24, len(config["page_data"][5]["spotlight_frames"]["frame_data"][0]["frame_RGB"]))
        self.assertTrue(validate_config(config)["ok"])


class GifImportTests(unittest.TestCase):
    def test_gif_uses_each_models_led_map(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        first = Image.new("RGB", (4, 4), "#FF0000")
        second = Image.new("RGB", (4, 4), "#0000FF")
        source = io.BytesIO()
        first.save(
            source,
            format="GIF",
            save_all=True,
            append_images=[second],
            duration=80,
            loop=0,
        )
        payload = source.getvalue()
        cases = (
            ("CB04", "frames", 200, 200),
            ("CB04", "keyframes", 90, 83),
            ("ALICE", "keyframes", 90, 72),
            ("80", "keyframes", 90, 89),
            ("80", "spotlight_frames", 24, 7),
        )
        for product, target, pixels, mapped in cases:
            result = gif_to_led_frames(payload, target, "nearest", product)
            self.assertEqual(2, result["frame_count"])
            self.assertEqual(76, result["duration_ms"])
            self.assertTrue(all(len(frame) == pixels for frame in result["frames"]))
            self.assertEqual(mapped, result["mapped_pixels"])
            self.assertEqual("#FF0000", result["frames"][0][0])
            self.assertEqual("#0000FF", result["frames"][1][0])

        afa = gif_to_led_frames(payload, "keyframes", "nearest", "ALICE")["frames"][0]
        self.assertEqual(afa[7], afa[71])
        self.assertEqual(afa[20], afa[72])
        relic_edge = gif_to_led_frames(payload, "spotlight_frames", "nearest", "80")["frames"][0]
        self.assertEqual(["#000000"] * 17, relic_edge[7:])

    def test_variable_gif_delays_are_resampled_to_firmware_timing(self) -> None:
        from PIL import Image

        first = Image.new("RGB", (2, 2), "#FF0000")
        second = Image.new("RGB", (2, 2), "#0000FF")
        source = io.BytesIO()
        first.save(
            source,
            format="GIF",
            save_all=True,
            append_images=[second],
            duration=[100, 500],
            loop=0,
        )
        result = gif_to_led_frames(source.getvalue(), "frames", "nearest", "CB04")
        self.assertEqual(100, result["duration_ms"])
        self.assertTrue(result["timing_resampled"])
        self.assertEqual(6, result["frame_count"])
        self.assertEqual("#FF0000", result["frames"][0][0])
        self.assertTrue(all(frame[0] == "#0000FF" for frame in result["frames"][1:]))
        self.assertEqual(76, firmware_led_speed(80))

    def test_model_rejects_an_led_target_it_does_not_have(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not support"):
            gif_to_led_frames(b"GIF89a", "frames", product_id="ALICE")

    def test_cyberboard_display_preserves_row_major_motion(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        source = Image.new("RGB", (40, 5), "#000000")
        source.putpixel((0, 0), (255, 0, 0))
        source.putpixel((1, 0), (0, 255, 0))
        source.putpixel((0, 1), (0, 0, 255))
        payload = io.BytesIO()
        source.save(payload, format="GIF")

        frame = gif_to_led_frames(
            payload.getvalue(), "frames", "nearest", "CB04"
        )["frames"][0]
        self.assertEqual("#FF0000", frame[0])   # x=0, y=0 -> 0*40+0
        self.assertEqual("#00FF00", frame[1])   # x=1, y=0 -> 0*40+1
        self.assertEqual("#0000FF", frame[40])  # x=0, y=1 -> 1*40+0
        self.assertEqual("#000000", frame[5])

    def test_relic_gif_maps_keys_and_edges_from_the_same_raster(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        source = Image.new("RGB", (18, 7), "#000000")
        source.putpixel((1, 1), (0, 0, 255))   # Firmware key LED 0.
        source.putpixel((0, 6), (255, 0, 0))   # Firmware edge LED 0.
        source.putpixel((17, 0), (0, 255, 0))  # Firmware edge LED 6.
        payload = io.BytesIO()
        source.save(payload, format="GIF")

        result = gif_to_led_tracks(
            payload.getvalue(),
            ["keyframes", "spotlight_frames"],
            "nearest",
            "AM21",
        )
        keys = result["tracks"]["keyframes"]
        edges = result["tracks"]["spotlight_frames"]
        self.assertEqual(1, keys["frame_count"])
        self.assertEqual(keys["frame_count"], edges["frame_count"])
        self.assertEqual("#0000FF", keys["frames"][0][0])
        self.assertEqual("#FF0000", edges["frames"][0][0])
        self.assertEqual("#00FF00", edges["frames"][0][6])
        self.assertEqual(["#000000"] * 17, edges["frames"][0][7:])


class FramesToLedTracksTests(unittest.TestCase):
    def _build_gif(self) -> bytes:
        from PIL import Image

        colors = ("#FF0000", "#00FF00", "#0000FF", "#FFFF00")
        frames = [Image.new("RGB", (18, 7), color) for color in colors]
        source = io.BytesIO()
        frames[0].save(
            source,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=[80, 100, 120, 80],
            loop=0,
        )
        return source.getvalue()

    def _decode(self, payload: bytes):
        from PIL import Image

        images = []
        durations = []
        with Image.open(io.BytesIO(payload)) as image:
            count = min(int(getattr(image, "n_frames", 1)), _MAX_GIF_FRAMES)
            for index in range(count):
                image.seek(index)
                durations.append(int(image.info.get("duration") or 90))
                images.append(image.convert("RGBA"))
        return images, durations

    def test_parity_with_gif_import(self) -> None:
        try:
            from PIL import Image  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        payload = self._build_gif()
        images, durations = self._decode(payload)
        cases = (
            ("CB04", ["frames", "keyframes"]),
            ("AM21", ["keyframes", "spotlight_frames"]),
            ("ALICE", ["keyframes"]),
        )
        for product, targets in cases:
            with self.subTest(product=product, targets=targets):
                expected = gif_to_led_tracks(payload, targets, "nearest", product)
                actual = frames_to_led_tracks(
                    images, durations, targets, "nearest", product
                )
                self.assertEqual(expected, actual)

    def test_frame_limit_and_timing(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        images = [Image.new("RGB", (4, 4), "#123456") for _ in range(300)]
        durations = [50 if index % 2 == 0 else 100 for index in range(300)]
        result = frames_to_led_tracks(images, durations, ["frames"], "nearest", "CB04")
        self.assertTrue(result["timing_resampled"])
        self.assertLessEqual(
            result["tracks"]["frames"]["frame_count"], _MAX_GIF_FRAMES
        )
        self.assertEqual(_MAX_GIF_FRAMES, result["source_frames"])
        self.assertEqual(_MAX_GIF_FRAMES, result["decoded_frames"])

    def test_rejects_empty_and_bad_target(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        with self.assertRaisesRegex(ValueError, "contains no frames"):
            frames_to_led_tracks([], [], ["frames"], "nearest", "CB04")
        with self.assertRaisesRegex(ValueError, "does not support"):
            frames_to_led_tracks(
                [Image.new("RGB", (4, 4))], [90], ["frames"], "nearest", "ALICE"
            )


_DROP = object()  # sentinel: mutate() removes the field entirely

# A sentinel API key used only in transport tests. It is deliberately
# distinctive so redaction assertions can prove it never reaches an error
# string or log line. It is not a real credential.
_FAKE_KEY = "sk-fake-SENTINEL-do-not-log-0123456789"


class _FakeResponse:
    """Minimal stand-in for a urllib response: bounded ``read`` plus ``close``."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.read_amounts: list[int | None] = []
        self.closed = False

    def read(self, amt: int | None = None) -> bytes:
        self.read_amounts.append(amt)
        if amt is None:
            data, self._body = self._body, b""
        else:
            data, self._body = self._body[:amt], self._body[amt:]
        return data

    def close(self) -> None:
        self.closed = True


class _RecordingOpener:
    """Fake urllib opener callable: records each call, then returns or raises.

    Mirrors the real opener contract used by ``llm._xai_request``
    (``opener(request, timeout=...)``) so the transport's parsing and error
    mapping are exercised with zero network I/O.
    """

    def __init__(self, *, response=None, error: BaseException | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[Request, object]] = []

    def __call__(self, request, timeout=None):
        self.calls.append((request, timeout))
        if self._error is not None:
            raise self._error
        return self._response


def _request_header(request, name: str) -> str | None:
    """Case-insensitive lookup of a header on a urllib ``Request``."""
    for key, value in request.header_items():
        if key.lower() == name.lower():
            return value
    return None


class _FakeTransport:
    """Fake xAI transport: records each call, then returns a canned dict or raises.

    The signature mirrors ``llm._xai_request`` minus the opener
    (``(url, payload, api_key, deadline) -> dict``) — the contract the concrete
    Grok providers use to invoke their injected transport, so their request
    building, extraction, and error paths run with zero network I/O.
    """

    def __init__(self, *, response=None, error: BaseException | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def __call__(self, url, payload, api_key, deadline):
        self.calls.append(
            {"url": url, "payload": payload, "api_key": api_key, "deadline": deadline}
        )
        if self._error is not None:
            raise self._error
        return self._response


def _responses_envelope(plan_dict: dict) -> dict:
    """A minimal xAI ``/v1/responses`` structured-output envelope carrying
    ``plan_dict`` as the assistant message's ``output_text`` JSON."""
    return {
        "output": [
            {"type": "reasoning", "content": []},
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": json.dumps(plan_dict)}
                ],
            },
        ],
        "usage": {"input_tokens": 128, "output_tokens": 64},
    }


def _image_envelope(b64: str) -> dict:
    """A minimal xAI ``/v1/images/generations`` envelope carrying one inline
    base64 image — the ``response_format: "b64_json"`` shape the renderer reads."""
    return {"data": [{"b64_json": b64}]}


def _encode_image(image, fmt: str = "PNG") -> str:
    """Serialize a Pillow image to ``fmt`` and base64-encode the bytes for a fake
    image-generation response body (no network, no temp files)."""
    buf = io.BytesIO()
    image.save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


class GrokTransportTests(unittest.TestCase):
    """Task 3 subset: shared constants, drift guards, and EffectPlan validation.

    Later tasks extend this class with the xAI transport and the concrete
    interpreter/renderer paths (all with injected fakes, never the network).
    """

    def _spec(self, **overrides) -> "llm.RasterSpec":
        base = dict(
            model="CB",
            target="display",
            extra_targets=(),
            width=40,
            height=5,
            mapped_positions=None,
            output_len=200,
            max_frames=80,
        )
        base.update(overrides)
        return llm.RasterSpec(**base)

    def _good_plan(self) -> dict:
        return {
            "subject": "pac-man",
            "palette": "yellow dot on black",
            "motion": "chomps left to right",
            "frame_count": 6,
            "frame_ms": 100,
            "keyframe_prompts": ["open mouth", "closed mouth", "open again"],
            "tween": "crossfade",
            "notes": "loops seamlessly",
        }

    def test_speed_steps_match_server(self) -> None:
        # Single source of truth: llm duplicates the tuple so it need not import
        # server; this guard fails loudly if the two ever drift apart.
        self.assertEqual(llm.LED_SPEEDS_MS, server._LED_SPEEDS_MS)

    def test_provider_names_match_store_allowlists(self) -> None:
        # store.py must stay stdlib-core-only and cannot import llm, so it keeps
        # its own allowlists. This guard keeps the canonical names in sync.
        self.assertEqual(
            set(llm.INTERPRETER_PROVIDERS), set(store._KNOWN_INTERPRETERS)
        )
        self.assertEqual(set(llm.RENDERER_PROVIDERS), set(store._KNOWN_RENDERERS))
        self.assertEqual(set(llm.KEY_PROVIDERS), set(store._KNOWN_KEY_PROVIDERS))

    def test_plan_validation_accepts_good_plan(self) -> None:
        plan = llm.plan_from_json(self._good_plan(), self._spec())
        self.assertIsInstance(plan, llm.EffectPlan)
        self.assertEqual(plan.subject, "pac-man")
        self.assertEqual(plan.frame_count, 6)
        self.assertEqual(plan.frame_ms, 100)
        self.assertEqual(plan.tween, "crossfade")
        self.assertEqual(
            plan.keyframe_prompts, ("open mouth", "closed mouth", "open again")
        )
        self.assertIsInstance(plan.keyframe_prompts, tuple)

    def test_plan_validation_rejects_bad_plans(self) -> None:
        spec = self._spec()

        def mutate(**changes) -> dict:
            data = self._good_plan()
            for key, value in changes.items():
                if value is _DROP:
                    data.pop(key, None)
                else:
                    data[key] = value
            return data

        cases = {
            "missing_field": mutate(subject=_DROP),
            "wrong_type_int": mutate(frame_count="6"),
            "wrong_type_str": mutate(subject=123),
            "wrong_type_prompts": mutate(keyframe_prompts="not a list"),
            "prompt_entry_not_str": mutate(keyframe_prompts=["ok", 7]),
            "bool_not_int": mutate(frame_count=True),
            "frame_ms_not_a_speed_step": mutate(frame_ms=101),
            "frame_count_too_low": mutate(frame_count=0),
            "frame_count_over_cap": mutate(frame_count=spec.max_frames + 1),
            "no_prompts": mutate(keyframe_prompts=[]),
            "too_many_prompts": mutate(
                frame_count=4, keyframe_prompts=["a", "b", "c", "d", "e"]
            ),
            "over_keyframe_ceiling": mutate(
                frame_count=80,
                keyframe_prompts=[
                    f"f{i}" for i in range(llm.MAX_RENDERED_KEYFRAMES + 1)
                ],
            ),
            "bad_tween": mutate(tween="fade"),
            "empty_prompt": mutate(keyframe_prompts=["ok", ""]),
            "oversized_prompt": mutate(keyframe_prompts=["x" * 2001]),
            "oversized_subject": mutate(subject="x" * 2001),
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(llm.ProviderError) as ctx:
                    llm.plan_from_json(data, spec)
                self.assertEqual(ctx.exception.code, "bad_response")

    def test_plan_from_json_rejects_non_object(self) -> None:
        with self.assertRaises(llm.ProviderError) as ctx:
            llm.plan_from_json(["not", "a", "dict"], self._spec())
        self.assertEqual(ctx.exception.code, "bad_response")

    # --- xAI transport (llm._xai_request) ---------------------------------
    #
    # All transport tests inject a fake opener; the real urllib opener
    # (``opener=None``) is never exercised here.

    _URL = "https://api.x.ai/v1/responses"

    def _future_deadline(self) -> float:
        return time.monotonic() + 30.0

    def _http_error(self, code: int, *, retry_after=None) -> urllib.error.HTTPError:
        hdrs = Message()
        if retry_after is not None:
            hdrs["Retry-After"] = str(retry_after)
        return urllib.error.HTTPError(
            self._URL, code, f"HTTP {code}", hdrs, io.BytesIO(b"{}")
        )

    def test_xai_request_success_sets_headers_and_returns_dict(self) -> None:
        payload = {"model": "grok-4.5", "input": "hi"}
        expected = {"ok": True, "value": 42}
        opener = _RecordingOpener(
            response=_FakeResponse(json.dumps(expected).encode("utf-8"))
        )

        result = llm._xai_request(
            self._URL, payload, _FAKE_KEY, self._future_deadline(), opener=opener
        )

        self.assertEqual(result, expected)
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            _request_header(request, "Authorization"), f"Bearer {_FAKE_KEY}"
        )
        self.assertEqual(
            _request_header(request, "Content-Type"), "application/json"
        )
        self.assertEqual(json.loads(request.data.decode("utf-8")), payload)
        # Per-call timeout is capped at 30s and never exceeds the deadline.
        self.assertLessEqual(timeout, 30.0)
        self.assertGreater(timeout, 0.0)

    def test_xai_request_auth_error(self) -> None:
        for code in (401, 403):
            with self.subTest(code=code):
                opener = _RecordingOpener(error=self._http_error(code))
                with self.assertRaises(llm.ProviderError) as ctx:
                    llm._xai_request(
                        self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                    )
                self.assertEqual(ctx.exception.code, "auth")

    def test_xai_request_rate_limited_passes_retry_after(self) -> None:
        opener = _RecordingOpener(error=self._http_error(429, retry_after=7))
        with self.assertRaises(llm.ProviderError) as ctx:
            llm._xai_request(
                self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
            )
        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertEqual(ctx.exception.retry_after, 7)

    def test_xai_request_rate_limited_without_retry_after(self) -> None:
        opener = _RecordingOpener(error=self._http_error(429))
        with self.assertRaises(llm.ProviderError) as ctx:
            llm._xai_request(
                self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
            )
        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertIsNone(ctx.exception.retry_after)

    def test_xai_request_server_errors_unavailable(self) -> None:
        for code in (500, 502, 503):
            with self.subTest(code=code):
                opener = _RecordingOpener(error=self._http_error(code))
                with self.assertRaises(llm.ProviderError) as ctx:
                    llm._xai_request(
                        self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                    )
                self.assertEqual(ctx.exception.code, "unavailable")

    def test_xai_request_other_4xx_bad_response(self) -> None:
        for code in (400, 404, 422):
            with self.subTest(code=code):
                opener = _RecordingOpener(error=self._http_error(code))
                with self.assertRaises(llm.ProviderError) as ctx:
                    llm._xai_request(
                        self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                    )
                self.assertEqual(ctx.exception.code, "bad_response")

    def test_xai_request_offline_on_network_failure(self) -> None:
        errors = {
            "urlerror": urllib.error.URLError(socket.gaierror("name resolution")),
            "connection_reset": ConnectionResetError("peer reset"),
            "ssl": ssl.SSLError("handshake failed"),
        }
        for name, error in errors.items():
            with self.subTest(case=name):
                opener = _RecordingOpener(error=error)
                with self.assertRaises(llm.ProviderError) as ctx:
                    llm._xai_request(
                        self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                    )
                self.assertEqual(ctx.exception.code, "offline")

    def test_xai_request_timeout_on_expired_deadline_skips_opener(self) -> None:
        opener = _RecordingOpener(response=_FakeResponse(b"{}"))
        past_deadline = time.monotonic() - 1.0
        with self.assertRaises(llm.ProviderError) as ctx:
            llm._xai_request(self._URL, {}, _FAKE_KEY, past_deadline, opener=opener)
        self.assertEqual(ctx.exception.code, "timeout")
        # The deadline is enforced before any network contact.
        self.assertEqual(opener.calls, [])

    def test_xai_request_timeout_on_socket_timeout(self) -> None:
        # A per-call timeout firing is a deadline overrun, not an offline
        # condition (design: timeout == "deadline exceeded (any phase)").
        for name, error in {
            "raw": TimeoutError("slow"),
            "wrapped": urllib.error.URLError(TimeoutError("slow")),
        }.items():
            with self.subTest(case=name):
                opener = _RecordingOpener(error=error)
                with self.assertRaises(llm.ProviderError) as ctx:
                    llm._xai_request(
                        self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                    )
                self.assertEqual(ctx.exception.code, "timeout")

    def test_xai_request_oversized_body_bad_response(self) -> None:
        # Shrink the cap so the test proves the bounded read without allocating
        # 25 MB. The read must be bounded to cap+1 bytes, not trust in length.
        with patch.object(llm, "MAX_PROVIDER_RESPONSE", 8):
            body = b"x" * 20
            response = _FakeResponse(body)
            opener = _RecordingOpener(response=response)
            with self.assertRaises(llm.ProviderError) as ctx:
                llm._xai_request(
                    self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                )
            self.assertEqual(ctx.exception.code, "bad_response")
            # Bounded read: exactly cap+1 bytes requested, never the whole stream.
            self.assertEqual(response.read_amounts, [9])

    def test_xai_request_non_json_bad_response(self) -> None:
        opener = _RecordingOpener(response=_FakeResponse(b"not json {["))
        with self.assertRaises(llm.ProviderError) as ctx:
            llm._xai_request(
                self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
            )
        self.assertEqual(ctx.exception.code, "bad_response")

    def test_xai_request_non_object_json_bad_response(self) -> None:
        opener = _RecordingOpener(response=_FakeResponse(b"[1, 2, 3]"))
        with self.assertRaises(llm.ProviderError) as ctx:
            llm._xai_request(
                self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
            )
        self.assertEqual(ctx.exception.code, "bad_response")

    def test_xai_request_no_auto_retry(self) -> None:
        # Exactly one opener call per invocation on every path — no paid call is
        # ever retried, including on 5xx/429 which look retryable.
        scenarios = {
            "success": _RecordingOpener(response=_FakeResponse(b"{}")),
            "server_error": _RecordingOpener(error=self._http_error(503)),
            "rate_limited": _RecordingOpener(error=self._http_error(429, retry_after=3)),
        }
        for name, opener in scenarios.items():
            with self.subTest(case=name):
                try:
                    llm._xai_request(
                        self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                    )
                except llm.ProviderError:
                    pass
                self.assertEqual(len(opener.calls), 1)

    def test_xai_request_redacts_secret_in_error(self) -> None:
        # Force the key into a raised exception's own text; the transport must
        # scrub it before it reaches ProviderError.message / str().
        leaky = urllib.error.URLError(f"connection failed with key {_FAKE_KEY}")
        opener = _RecordingOpener(error=leaky)
        with self.assertRaises(llm.ProviderError) as ctx:
            llm._xai_request(
                self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
            )
        self.assertEqual(ctx.exception.code, "offline")
        self.assertNotIn(_FAKE_KEY, str(ctx.exception))
        self.assertNotIn(_FAKE_KEY, ctx.exception.message)

    def test_xai_request_secret_absent_across_all_error_paths(self) -> None:
        # Sweep every error mapping and assert the key never surfaces.
        openers = [
            _RecordingOpener(error=self._http_error(401)),
            _RecordingOpener(error=self._http_error(429, retry_after=7)),
            _RecordingOpener(error=self._http_error(500)),
            _RecordingOpener(error=self._http_error(404)),
            _RecordingOpener(error=urllib.error.URLError("boom")),
            _RecordingOpener(error=TimeoutError("slow")),
            _RecordingOpener(response=_FakeResponse(b"not json")),
        ]
        for opener in openers:
            with self.assertRaises(llm.ProviderError) as ctx:
                llm._xai_request(
                    self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
                )
            self.assertNotIn(_FAKE_KEY, str(ctx.exception))
            self.assertNotIn(_FAKE_KEY, ctx.exception.message)


class GrokInterpreterTests(unittest.TestCase):
    """Task 5: ``GrokInterpreter`` request building, output extraction, refusal
    handling, and the Refine flow — all through an injected fake transport."""

    _RESPONSES_URL = "https://api.x.ai/v1/responses"

    def _future_deadline(self) -> float:
        return time.monotonic() + 30.0

    def _spec(self, **overrides) -> "llm.RasterSpec":
        base = dict(
            model="CB",
            target="display",
            extra_targets=(),
            width=40,
            height=5,
            mapped_positions=None,
            output_len=200,
            max_frames=80,
        )
        base.update(overrides)
        return llm.RasterSpec(**base)

    def _good_plan(self) -> dict:
        return {
            "subject": "pac-man",
            "palette": "yellow dot on black",
            "motion": "chomps left to right",
            "frame_count": 6,
            "frame_ms": 100,
            "keyframe_prompts": ["open mouth", "closed mouth", "open again"],
            "tween": "crossfade",
            "notes": "loops seamlessly",
        }

    @staticmethod
    def _system(payload: dict) -> str:
        for message in payload["input"]:
            if message.get("role") == "system":
                return message["content"]
        raise AssertionError("payload has no system message")

    @staticmethod
    def _user(payload: dict) -> str:
        for message in payload["input"]:
            if message.get("role") == "user":
                return message["content"]
        raise AssertionError("payload has no user message")

    def test_interpret_happy_path(self) -> None:
        spec = self._spec()
        transport = _FakeTransport(response=_responses_envelope(self._good_plan()))
        interpreter = llm.GrokInterpreter(_FAKE_KEY, transport=transport)

        plan = interpreter.interpret(
            "pac-man chased by a blue ghost", spec, self._future_deadline()
        )

        self.assertIsInstance(plan, llm.EffectPlan)
        self.assertEqual(plan.subject, "pac-man")
        self.assertEqual(
            plan.keyframe_prompts, ("open mouth", "closed mouth", "open again")
        )

        # Exactly one upstream call, carrying the sentinel key and the endpoint.
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["url"], self._RESPONSES_URL)
        self.assertEqual(call["api_key"], _FAKE_KEY)

        payload = call["payload"]
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["model"], llm.XAI_MODELS["interpreter"])
        fmt = payload["text"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertIs(fmt["strict"], True)
        self.assertIs(fmt["schema"]["additionalProperties"], False)

        system = self._system(payload)
        self.assertIn(f"{spec.width}x{spec.height}", system)  # raster size
        self.assertIn(str(spec.max_frames), system)  # frame cap
        self.assertIn("limit, not a goal", system)  # cap is a ceiling, not a target
        self.assertIn(", ".join(str(s) for s in llm.LED_SPEEDS_MS), system)  # speed steps
        # No sparse mask language when the spec carries no mask.
        self.assertNotIn("Only the following", system)

        # The sparse-position mask appears only when the spec provides one.
        masked = self._spec(
            model="80",
            target="spotlight_frames",
            max_frames=200,
            mapped_positions=((0, 0), (3, 2), (6, 4)),
        )
        masked_transport = _FakeTransport(
            response=_responses_envelope(self._good_plan())
        )
        llm.GrokInterpreter(_FAKE_KEY, transport=masked_transport).interpret(
            "edge glow", masked, self._future_deadline()
        )
        masked_system = self._system(masked_transport.calls[0]["payload"])
        self.assertIn("(0, 0)", masked_system)
        self.assertIn("(6, 4)", masked_system)

    def test_schema_valid_but_inconsistent_fails(self) -> None:
        # A plan that satisfies the JSON schema shape but violates the
        # independent plan_from_json rules (more prompts than frame_count) must
        # fail as bad_response — never leaking through to a paid render call.
        spec = self._spec()
        bad = self._good_plan()
        bad["frame_count"] = 4
        bad["keyframe_prompts"] = ["a", "b", "c", "d", "e"]
        transport = _FakeTransport(response=_responses_envelope(bad))
        interpreter = llm.GrokInterpreter(_FAKE_KEY, transport=transport)

        with self.assertRaises(llm.ProviderError) as ctx:
            interpreter.interpret("x", spec, self._future_deadline())
        self.assertEqual(ctx.exception.code, "bad_response")

    def test_moderation_refusal(self) -> None:
        spec = self._spec()
        refusal = {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "refusal", "refusal": "I can't help with that."}
                    ],
                }
            ]
        }
        transport = _FakeTransport(response=refusal)
        interpreter = llm.GrokInterpreter(_FAKE_KEY, transport=transport)

        with self.assertRaises(llm.ProviderError) as ctx:
            interpreter.interpret("something disallowed", spec, self._future_deadline())
        self.assertEqual(ctx.exception.code, "moderation")

    def test_previous_plan_included(self) -> None:
        spec = self._spec()
        previous = llm.plan_from_json(self._good_plan(), spec)
        transport = _FakeTransport(response=_responses_envelope(self._good_plan()))
        interpreter = llm.GrokInterpreter(_FAKE_KEY, transport=transport)

        interpreter.interpret(
            "make the ghost redder",
            spec,
            self._future_deadline(),
            previous_plan=previous,
        )

        user = self._user(transport.calls[0]["payload"])
        # The prior plan summary and the new instruction both reach the model.
        self.assertIn(previous.subject, user)
        self.assertIn(previous.motion, user)
        self.assertIn("make the ghost redder", user)


class GrokImagineRendererTests(unittest.TestCase):
    """Task 6: ``GrokImagineRenderer`` sequential per-keyframe rendering, the full
    response validation chain (shape → base64 → byte cap → format whitelist →
    pixel cap → load), partial-failure discard, and cancellation — all through an
    injected fake transport with tiny in-memory images and zero network I/O."""

    _IMAGES_URL = "https://api.x.ai/v1/images/generations"

    def _future_deadline(self) -> float:
        return time.monotonic() + 30.0

    def _spec(self, **overrides) -> "llm.RasterSpec":
        base = dict(
            model="CB",
            target="display",
            extra_targets=(),
            width=40,
            height=5,
            mapped_positions=None,
            output_len=200,
            max_frames=80,
        )
        base.update(overrides)
        return llm.RasterSpec(**base)

    def _plan(self, prompts) -> "llm.EffectPlan":
        prompts = tuple(prompts)
        return llm.EffectPlan(
            subject="pac-man",
            palette="yellow dot on black",
            motion="chomps left to right",
            frame_count=max(6, len(prompts)),
            frame_ms=100,
            keyframe_prompts=prompts,
            tween="crossfade",
            notes="",
        )

    def test_render_happy_path(self) -> None:
        from PIL import Image

        b64 = _encode_image(Image.new("RGB", (8, 4), (10, 20, 30)))
        prompts = ["open mouth", "closed mouth", "open again"]
        transport = _FakeTransport(response=_image_envelope(b64))
        renderer = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport)

        result = renderer.render(
            self._plan(prompts), self._spec(), self._future_deadline()
        )

        self.assertIsInstance(result, llm.RenderedFrames)
        self.assertEqual(len(result.images), len(prompts))
        for image in result.images:
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (8, 4))

        # One sequential upstream call per keyframe prompt, in order, each
        # carrying the pinned renderer model, n=1, and the b64_json mode.
        self.assertEqual(len(transport.calls), len(prompts))
        for prompt, call in zip(prompts, transport.calls):
            self.assertEqual(call["url"], self._IMAGES_URL)
            self.assertEqual(call["api_key"], _FAKE_KEY)
            payload = call["payload"]
            self.assertEqual(payload["model"], llm.XAI_MODELS["renderer"])
            self.assertEqual(payload["n"], 1)
            self.assertEqual(payload["response_format"], "b64_json")
            self.assertIn(prompt, payload["prompt"])  # per-keyframe, in order

    def test_url_fields_ignored(self) -> None:
        # A response carrying only a URL (never the requested b64_json) is a
        # malformed response, not something to fetch: URL mode is never fetched.
        transport = _FakeTransport(
            response={"data": [{"url": "https://x.example/frame.png"}]}
        )
        renderer = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport)

        with self.assertRaises(llm.ProviderError) as ctx:
            renderer.render(self._plan(["a"]), self._spec(), self._future_deadline())
        self.assertEqual(ctx.exception.code, "bad_response")
        self.assertEqual(len(transport.calls), 1)

    def test_invalid_base64(self) -> None:
        transport = _FakeTransport(response=_image_envelope("@not@base64@"))
        renderer = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport)

        with self.assertRaises(llm.ProviderError) as ctx:
            renderer.render(self._plan(["a"]), self._spec(), self._future_deadline())
        self.assertEqual(ctx.exception.code, "bad_response")
        # The base64 stage rejects it — not a downstream Pillow failure. This
        # pins the guard: strict base64 validation, so bad input never reaches
        # the decoder.
        self.assertIn("base64", ctx.exception.message)

    def test_oversized_decoded_image(self) -> None:
        # Byte-size cap fires before Pillow ever opens the payload, so oversized
        # bytes are rejected without a decode attempt.
        big = base64.b64encode(b"\x00" * (llm.MAX_IMAGE_BYTES + 1)).decode("ascii")
        transport = _FakeTransport(response=_image_envelope(big))
        renderer = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport)

        with self.assertRaises(llm.ProviderError) as ctx:
            renderer.render(self._plan(["a"]), self._spec(), self._future_deadline())
        self.assertEqual(ctx.exception.code, "bad_response")
        # Pin the guard to the byte cap specifically: without it, these bytes
        # would instead fail later at Pillow open with a different message.
        self.assertIn("byte cap", ctx.exception.message)

    def test_pixel_cap(self) -> None:
        from PIL import Image

        # 2100x2100 = 4,410,000 px > 4 MP cap, but a solid PNG stays far under
        # the byte cap — so this exercises the pixel cap specifically.
        side = 2100
        b64 = _encode_image(Image.new("RGB", (side, side), (1, 2, 3)))
        self.assertLess(len(base64.b64decode(b64)), llm.MAX_IMAGE_BYTES)
        transport = _FakeTransport(response=_image_envelope(b64))
        renderer = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport)

        with self.assertRaises(llm.ProviderError) as ctx:
            renderer.render(self._plan(["a"]), self._spec(), self._future_deadline())
        self.assertEqual(ctx.exception.code, "bad_response")

    def test_format_whitelist(self) -> None:
        from PIL import Image

        # A GIF payload is rejected by the format whitelist...
        gif_b64 = _encode_image(Image.new("RGB", (8, 4), (5, 5, 5)), "GIF")
        gif_transport = _FakeTransport(response=_image_envelope(gif_b64))
        with self.assertRaises(llm.ProviderError) as ctx:
            llm.GrokImagineRenderer(_FAKE_KEY, transport=gif_transport).render(
                self._plan(["a"]), self._spec(), self._future_deadline()
            )
        self.assertEqual(ctx.exception.code, "bad_response")

        # ...while PNG and JPEG both decode to RGB images.
        for fmt in ("PNG", "JPEG"):
            b64 = _encode_image(Image.new("RGB", (8, 4), (9, 9, 9)), fmt)
            transport = _FakeTransport(response=_image_envelope(b64))
            result = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport).render(
                self._plan(["a"]), self._spec(), self._future_deadline()
            )
            self.assertEqual(len(result.images), 1)
            self.assertEqual(result.images[0].mode, "RGB")

    def test_partial_failure_discards(self) -> None:
        from PIL import Image

        good = _image_envelope(_encode_image(Image.new("RGB", (8, 4), (7, 8, 9))))
        # Keyframe 1 succeeds; keyframe 2 fails; keyframe 3 must never be called.
        outcomes = [good, llm.ProviderError("unavailable", "boom"), good]
        calls: list[dict] = []

        def transport(url, payload, api_key, deadline):
            calls.append({"url": url, "payload": payload})
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        renderer = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport)
        with self.assertRaises(llm.ProviderError) as ctx:
            renderer.render(
                self._plan(["a", "b", "c"]), self._spec(), self._future_deadline()
            )
        self.assertEqual(ctx.exception.code, "unavailable")
        # Failed at keyframe 2 of 3: exactly two calls, no partial result leaks.
        self.assertEqual(len(calls), 2)

    def test_cancel_between_calls(self) -> None:
        from PIL import Image

        good = _image_envelope(_encode_image(Image.new("RGB", (8, 4), (2, 4, 6))))
        transport = _FakeTransport(response=good)
        renderer = llm.GrokImagineRenderer(_FAKE_KEY, transport=transport)

        # Cancel becomes true once the first keyframe has been requested, so the
        # predicate is consulted between calls and stops the second render.
        cancelled = lambda: len(transport.calls) >= 1  # noqa: E731

        with self.assertRaises(llm.Cancelled):
            renderer.render(
                self._plan(["a", "b", "c"]),
                self._spec(),
                self._future_deadline(),
                cancelled=cancelled,
            )
        self.assertEqual(len(transport.calls), 1)


class _FakeGenInterpreter:
    """Fake Interpreter matching the ``interpret`` protocol; records its calls.

    Returns a pre-built :class:`llm.EffectPlan` (constructed directly, so a test
    can deliberately hand ``generate_effect`` a plan that violates the budget the
    real interpreter's ``plan_from_json`` would have rejected) or raises a
    supplied error.
    """

    def __init__(self, plan=None, error: BaseException | None = None) -> None:
        self._plan = plan
        self._error = error
        self.calls: list[dict] = []

    def interpret(self, prompt, spec, deadline, previous_plan=None):
        self.calls.append(
            {"prompt": prompt, "spec": spec, "deadline": deadline,
             "previous_plan": previous_plan}
        )
        if self._error is not None:
            raise self._error
        return self._plan


class _FakeGenRenderer:
    """Fake Renderer matching the ``render`` protocol and the Task 6 renderer's
    between-keyframe cancel contract: it polls ``cancelled()`` once *before* each
    keyframe, so ``generate_effect``'s progress/cancel gate is exercised exactly
    as the real ``GrokImagineRenderer`` drives it. Records one entry per
    ``render`` call so a test can prove render was (or was never) started."""

    def __init__(self, image_for=None, error: BaseException | None = None,
                 error_at: int | None = None) -> None:
        self._image_for = image_for
        self._error = error
        self._error_at = error_at
        self.calls: list[float] = []

    def render(self, plan, spec, deadline, cancelled=None):
        self.calls.append(deadline)
        images = []
        for index in range(len(plan.keyframe_prompts)):
            if cancelled is not None and cancelled():
                raise llm.Cancelled("cancelled between keyframes")
            if self._error is not None and (
                self._error_at is None or self._error_at == index
            ):
                raise self._error
            images.append(self._image_for(index))
        return llm.RenderedFrames(images=tuple(images))


def _gen_factories(interpreter, renderer) -> dict:
    """Resolved interpreter/renderer factory pair for ``generate_effect``:
    each value is a ``callable(api_key) -> provider`` as the registry classes
    are in production."""
    return {
        "interpreter": lambda api_key: interpreter,
        "renderer": lambda api_key: renderer,
    }


class _BlockingGenInterpreter:
    """Fake Interpreter that blocks inside ``interpret`` until released.

    Lets the generation-endpoint tests observe a job while it is genuinely
    running — for the single-flight 409 and the cancel path — with no timing
    races: ``started`` is set on entry and the call then waits on ``release``
    before returning the pre-built plan. ``calls`` records each invocation so a
    test can prove the (single) provider call happened."""

    def __init__(self, plan, started, release) -> None:
        self._plan = plan
        self._started = started
        self._release = release
        self.calls: list[dict] = []

    def interpret(self, prompt, spec, deadline, previous_plan=None):
        self.calls.append({"prompt": prompt, "spec": spec, "deadline": deadline,
                           "previous_plan": previous_plan})
        self._started.set()
        if not self._release.wait(timeout=5):
            raise AssertionError("blocking interpreter was never released")
        return self._plan


class GenerateEffectTests(unittest.TestCase):
    """Task 7: keyframe tweening and the ``generate_effect`` orchestrator that
    wires interpreter -> renderer -> tween -> frame mapping under one monotonic
    deadline, with budget enforcement, cancellation, progress phases, and typed
    error propagation — all with injected fakes and zero network I/O."""

    def _spec(self, **overrides) -> "llm.RasterSpec":
        base = dict(
            model="CB",
            target="frames",
            extra_targets=(),
            width=40,
            height=5,
            mapped_positions=None,
            output_len=200,
            max_frames=80,
        )
        base.update(overrides)
        return llm.RasterSpec(**base)

    def _plan(self, **overrides) -> "llm.EffectPlan":
        base = dict(
            subject="pac-man",
            palette="yellow dot on black",
            motion="chomps left to right",
            frame_count=6,
            frame_ms=100,
            keyframe_prompts=("open", "closed", "open again"),
            tween="crossfade",
            notes="",
        )
        base.update(overrides)
        return llm.EffectPlan(**base)

    # -- tween expansion ---------------------------------------------------

    def test_expand_step_and_crossfade(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        dark = Image.new("RGB", (1, 1), (0, 0, 0))
        bright = Image.new("RGB", (1, 1), (30, 60, 90))

        # K == frame_count is the identity: the exact input objects come back.
        identity = llm.expand_keyframes([dark, bright], 2, "crossfade")
        self.assertEqual(len(identity), 2)
        self.assertIs(identity[0], dark)
        self.assertIs(identity[1], bright)

        # K == 1 repeats the single keyframe for every output frame.
        repeated = llm.expand_keyframes([bright], 4, "crossfade")
        self.assertEqual(len(repeated), 4)
        for frame in repeated:
            self.assertEqual(frame.getpixel((0, 0)), (30, 60, 90))

        # crossfade: two keyframes -> four frames blend at 0, 1/3, 2/3, 1 with
        # Image.blend, giving exact intermediate pixels.
        cross = llm.expand_keyframes([dark, bright], 4, "crossfade")
        self.assertEqual(
            [frame.getpixel((0, 0)) for frame in cross],
            [(0, 0, 0), (10, 20, 30), (20, 40, 60), (30, 60, 90)],
        )

        # step: hold the nearest keyframe at or to the left of each position.
        stepped = llm.expand_keyframes([dark, bright], 4, "step")
        self.assertEqual(
            [frame.getpixel((0, 0)) for frame in stepped],
            [(0, 0, 0), (0, 0, 0), (0, 0, 0), (30, 60, 90)],
        )

    # -- full pipeline -----------------------------------------------------

    def test_generate_effect_pipeline(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        plan = self._plan(frame_count=6, frame_ms=100,
                          keyframe_prompts=("open", "closed", "open again"))
        # Rendered keyframes deliberately differ in size: the orchestrator must
        # normalize each to the generation raster before the crossfade blend and
        # the mapping, or Image.blend would refuse mismatched sizes.
        sizes = [(120, 30), (80, 80), (64, 40)]
        colors = [(90, 0, 0), (0, 90, 0), (0, 0, 90)]
        renderer = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", sizes[i], colors[i])
        )
        interpreter = _FakeGenInterpreter(plan=plan)

        result = llm.generate_effect(
            "pac-man chased by a blue ghost",
            self._spec(),
            ["frames"],
            "CB04",
            _FAKE_KEY,
            _gen_factories(interpreter, renderer),
        )

        # /api/led/gif-shaped result, mapped through frames_to_led_tracks.
        self.assertIn("tracks", result)
        self.assertEqual(result["tracks"]["frames"]["frame_count"], 6)
        self.assertEqual(result["model"], "CB")
        # Generated-path GIF-shape fields (design §3): defined by the generation
        # parameters, not decode leftovers.
        self.assertEqual(result["source_frames"], 6)
        self.assertEqual(result["decoded_frames"], 6)
        self.assertEqual(result["source_duration_ms"], 6 * 100)
        self.assertIs(result["timing_resampled"], False)
        # duration_ms is the per-frame firmware speed (consumed as speed_ms by
        # the UI), so it is frame_ms — not the total loop duration.
        self.assertEqual(result["duration_ms"], 100)

        # Plan + usage summaries for the UI.
        self.assertEqual(result["plan"]["subject"], "pac-man")
        self.assertEqual(result["plan"]["frame_count"], 6)
        self.assertEqual(result["plan"]["rendered_keyframes"], 3)
        self.assertEqual(result["plan"]["tween"], "crossfade")
        self.assertEqual(result["plan"]["frame_ms"], 100)
        self.assertEqual(result["usage"]["provider_calls"], 1 + 3)
        self.assertEqual(result["usage"]["rendered_keyframes"], 3)
        self.assertEqual(result["usage"]["output_frames"], 6)

        # One interpret call, one render call over the three keyframes.
        self.assertEqual(len(interpreter.calls), 1)
        self.assertEqual(len(renderer.calls), 1)

    def test_progress_phases(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        plan = self._plan(frame_count=6, keyframe_prompts=("a", "b", "c"))
        renderer = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", (40, 5), (i, i, i))
        )
        interpreter = _FakeGenInterpreter(plan=plan)
        phases: list[str] = []

        llm.generate_effect(
            "p", self._spec(), ["frames"], "CB04", _FAKE_KEY,
            _gen_factories(interpreter, renderer), progress=phases.append,
        )

        self.assertEqual(
            phases,
            ["interpreting", "rendering 1/3", "rendering 2/3", "rendering 3/3",
             "tweening", "mapping"],
        )

    def test_deadline_spans_phases(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        plan = self._plan(keyframe_prompts=("a", "b"))
        renderer = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", (40, 5), (1, 2, 3))
        )
        interpreter = _FakeGenInterpreter(plan=plan)

        before = time.monotonic()
        llm.generate_effect(
            "p", self._spec(), ["frames"], "CB04", _FAKE_KEY,
            _gen_factories(interpreter, renderer),
        )
        after = time.monotonic()

        interp_deadline = interpreter.calls[0]["deadline"]
        render_deadline = renderer.calls[0]
        # One monotonic deadline created from LLM_TOTAL_BUDGET, shared verbatim
        # across both provider phases.
        self.assertEqual(interp_deadline, render_deadline)
        self.assertGreaterEqual(interp_deadline, before + llm.LLM_TOTAL_BUDGET)
        self.assertLessEqual(interp_deadline, after + llm.LLM_TOTAL_BUDGET)

    # -- cancellation ------------------------------------------------------

    def test_cancel_between_phases(self) -> None:
        # Cancel becomes true once interpret has run: the orchestrator must honor
        # it before the paid render phase ever starts.
        plan = self._plan(keyframe_prompts=("a", "b"))
        renderer = _FakeGenRenderer(image_for=lambda i: None)
        interpreter = _FakeGenInterpreter(plan=plan)
        cancelled = lambda: len(interpreter.calls) >= 1  # noqa: E731

        with self.assertRaises(llm.Cancelled):
            llm.generate_effect(
                "p", self._spec(), ["frames"], "CB04", _FAKE_KEY,
                _gen_factories(interpreter, renderer), cancelled=cancelled,
            )
        # render() was never entered, so no paid image call was made.
        self.assertEqual(len(renderer.calls), 0)

    def test_cancel_during_render(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        plan = self._plan(keyframe_prompts=("a", "b", "c"))
        rendered: list[int] = []

        def image_for(index):
            rendered.append(index)
            return Image.new("RGB", (40, 5), (index, index, index))

        renderer = _FakeGenRenderer(image_for=image_for)
        interpreter = _FakeGenInterpreter(plan=plan)
        cancelled = lambda: len(rendered) >= 1  # noqa: E731

        with self.assertRaises(llm.Cancelled):
            llm.generate_effect(
                "p", self._spec(), ["frames"], "CB04", _FAKE_KEY,
                _gen_factories(interpreter, renderer), cancelled=cancelled,
            )
        # First keyframe rendered; the second was gated off between keyframes.
        self.assertEqual(rendered, [0])

    # -- budget enforcement (mutation-proofed) -----------------------------

    def test_budget_rejects_excess_keyframes(self) -> None:
        # A rogue/faked interpreter returns more keyframes than
        # MAX_RENDERED_KEYFRAMES; the orchestrator must reject before any paid
        # render, capping spend regardless of provider behavior.
        over = llm.MAX_RENDERED_KEYFRAMES + 1
        plan = self._plan(
            frame_count=over, keyframe_prompts=tuple(f"k{i}" for i in range(over))
        )
        renderer = _FakeGenRenderer(image_for=lambda i: None)
        interpreter = _FakeGenInterpreter(plan=plan)

        with self.assertRaises(llm.ProviderError) as ctx:
            llm.generate_effect(
                "p", self._spec(max_frames=200), ["frames"], "CB04", _FAKE_KEY,
                _gen_factories(interpreter, renderer),
            )
        self.assertEqual(ctx.exception.code, "bad_response")
        self.assertEqual(len(renderer.calls), 0)

    def test_budget_rejects_excess_frame_count(self) -> None:
        # frame_count over the per-model MODEL_FRAME_CAPS ceiling is rejected
        # before any paid render.
        plan = self._plan(frame_count=81, keyframe_prompts=("a", "b"))
        renderer = _FakeGenRenderer(image_for=lambda i: None)
        interpreter = _FakeGenInterpreter(plan=plan)

        with self.assertRaises(llm.ProviderError) as ctx:
            llm.generate_effect(
                "p", self._spec(max_frames=80), ["frames"], "CB04", _FAKE_KEY,
                _gen_factories(interpreter, renderer),
            )
        self.assertEqual(ctx.exception.code, "bad_response")
        self.assertEqual(len(renderer.calls), 0)

    def test_budget_rejects_global_frame_ceiling(self) -> None:
        try:
            from PIL import Image  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        # Even with an implausibly large per-model cap, MAX_LLM_FRAMES is the
        # hard global ceiling on output frames; frame_count above it is rejected
        # before any paid render (real images so the guard's removal would
        # silently succeed instead of erroring elsewhere).
        over = llm.MAX_LLM_FRAMES + 1
        plan = self._plan(frame_count=over, keyframe_prompts=("a", "b"))
        renderer = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", (40, 5), (0, 0, 0))
        )
        interpreter = _FakeGenInterpreter(plan=plan)

        with self.assertRaises(llm.ProviderError) as ctx:
            llm.generate_effect(
                "p", self._spec(max_frames=10_000), ["frames"], "CB04", _FAKE_KEY,
                _gen_factories(interpreter, renderer),
            )
        self.assertEqual(ctx.exception.code, "bad_response")
        self.assertEqual(len(renderer.calls), 0)

    # -- typed error propagation -------------------------------------------

    def test_interpreter_error_propagates(self) -> None:
        interpreter = _FakeGenInterpreter(
            error=llm.ProviderError("rate_limited", "slow down", retry_after=7)
        )
        renderer = _FakeGenRenderer(image_for=lambda i: None)

        with self.assertRaises(llm.ProviderError) as ctx:
            llm.generate_effect(
                "p", self._spec(), ["frames"], "CB04", _FAKE_KEY,
                _gen_factories(interpreter, renderer),
            )
        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertEqual(ctx.exception.retry_after, 7)
        self.assertEqual(len(renderer.calls), 0)

    def test_renderer_error_propagates(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")

        plan = self._plan(keyframe_prompts=("a", "b", "c"))
        renderer = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", (40, 5), (0, 0, 0)),
            error=llm.ProviderError("unavailable", "boom"),
            error_at=1,
        )
        interpreter = _FakeGenInterpreter(plan=plan)

        with self.assertRaises(llm.ProviderError) as ctx:
            llm.generate_effect(
                "p", self._spec(), ["frames"], "CB04", _FAKE_KEY,
                _gen_factories(interpreter, renderer),
            )
        self.assertEqual(ctx.exception.code, "unavailable")


class LedGenerateEndpointTests(unittest.TestCase):
    """Task 8: settings + capabilities HTTP endpoints on the loopback server.

    Each test starts a real ``create_server`` instance on a background thread and
    drives it over localhost with ``X-AM-Token``. Settings persistence is isolated
    to a temp ``AM_CONFIGURATOR_DATA_DIR`` and the ``XAI_API_KEY`` override is
    cleared, so nothing here reads a real environment. The ``/api/settings/test``
    key check runs entirely through an injected fake transport — no real network,
    no real API key.
    """

    _DEFAULT = object()  # sentinel: use the server's own token

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="am_endpoint_test_")
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME", "XAI_API_KEY")
        }
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ.pop("XAI_API_KEY", None)
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = self._tmp
        self._server, url = create_server()
        self._token = parse_qs(urlparse(url).query)["token"][0]
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
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

    def _save_key(self, value: str) -> None:
        status, _ = self._request(
            "POST",
            "/api/settings",
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": value}}},
        )
        self.assertEqual(status, 200)

    def test_settings_round_trip_masks_key(self) -> None:
        key = "sk-secret-9WXYZ7788"
        status, saved = self._request(
            "POST",
            "/api/settings",
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": key}}},
        )
        self.assertEqual(status, 200)
        # Even the POST response must never echo the raw key back to the browser.
        self.assertNotIn(key, json.dumps(saved))

        status, data = self._request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(data["llm"]["keys"]["xai"], {"set": True, "last4": "7788"})
        self.assertEqual(data["llm"]["interpreter"], "grok")
        # The raw key never returns to the browser, anywhere in the payload.
        self.assertNotIn(key, json.dumps(data))

        # Posting the display mask sentinel can never round-trip into storage.
        status, _ = self._request(
            "POST",
            "/api/settings",
            {
                "llm": {
                    "interpreter": "grok",
                    "renderer": "grok",
                    "keys": {"xai": store.KEY_MASK},
                }
            },
        )
        self.assertEqual(status, 400)

    def test_settings_strict_validation(self) -> None:
        # Unknown top-level field.
        status, _ = self._request(
            "POST",
            "/api/settings",
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {}}, "bogus": 1},
        )
        self.assertEqual(status, 400)
        # Unknown provider name.
        status, _ = self._request(
            "POST",
            "/api/settings",
            {"llm": {"interpreter": "nope", "renderer": "grok", "keys": {}}},
        )
        self.assertEqual(status, 400)
        # Unknown API-key provider.
        status, _ = self._request(
            "POST",
            "/api/settings",
            {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {"bogus": "x"}}},
        )
        self.assertEqual(status, 400)
        # Nothing was persisted by any rejected save.
        self.assertFalse(store.settings_path().exists())

    def test_capabilities(self) -> None:
        status, data = self._request("GET", "/api/led/capabilities")
        self.assertEqual(status, 200)

        self.assertEqual(data["models"], dict(llm.XAI_MODELS))
        self.assertEqual(data["model_frame_caps"], dict(llm.MODEL_FRAME_CAPS))
        self.assertEqual(data["max_rendered_keyframes"], llm.MAX_RENDERED_KEYFRAMES)
        self.assertEqual(
            data["providers"]["interpreters"], list(llm.INTERPRETER_PROVIDERS)
        )
        self.assertEqual(data["providers"]["renderers"], list(llm.RENDERER_PROVIDERS))
        self.assertEqual(data["providers"]["keys"], list(llm.KEY_PROVIDERS))

        # Single-CB-target rule: CB's two targets are different rasters, so exactly
        # one may be generated at a time and neither pairs with the other.
        cb = data["targets"]["CB"]
        self.assertTrue(cb["single_target"])
        for target in cb["targets"]:
            self.assertEqual(target["extra_targets"], [])

        # Relic pair: keyframes and spotlight_frames share one raster, so each is
        # the other's extra_target and the model is not single-target.
        relic = data["targets"]["80"]
        self.assertFalse(relic["single_target"])
        by_name = {target["name"]: target for target in relic["targets"]}
        self.assertIn("spotlight_frames", by_name["keyframes"]["extra_targets"])
        self.assertIn("keyframes", by_name["spotlight_frames"]["extra_targets"])

    def test_settings_test_endpoint(self) -> None:
        self._save_key("sk-test-ABCD1234")

        # A successful models-list probe through the injected transport → ok.
        probe = _FakeTransport(response={"models": []})
        self._server.state.llm_transport = probe
        status, data = self._request("POST", "/api/settings/test", {})
        self.assertEqual(status, 200)
        self.assertEqual(data, {"ok": True})
        # The probe carried the stored key and the pinned models-list endpoint.
        self.assertEqual(len(probe.calls), 1)
        self.assertEqual(probe.calls[0]["api_key"], "sk-test-ABCD1234")
        self.assertEqual(probe.calls[0]["url"], server._XAI_MODELS_URL)

        # A typed auth failure maps to 400 and carries the stable code.
        self._server.state.llm_transport = _FakeTransport(
            error=llm.ProviderError("auth", "provider rejected the API key")
        )
        status, data = self._request("POST", "/api/settings/test", {})
        self.assertEqual(status, 400)
        self.assertEqual(data["code"], "auth")

        # A rate-limit maps to 429 and passes retry_after through.
        self._server.state.llm_transport = _FakeTransport(
            error=llm.ProviderError("rate_limited", "slow down", retry_after=7)
        )
        status, data = self._request("POST", "/api/settings/test", {})
        self.assertEqual(status, 429)
        self.assertEqual(data["code"], "rate_limited")
        self.assertEqual(data["retry_after"], 7)

        # No key configured → 400 with a Settings hint, and the transport is never
        # consulted (the guard fires before any network path).
        self._save_key("")
        self.assertIsNone(store.resolve_xai_key())
        unused = _FakeTransport(response={"models": []})
        self._server.state.llm_transport = unused
        status, data = self._request("POST", "/api/settings/test", {})
        self.assertEqual(status, 400)
        self.assertIn("Settings", data["error"])
        self.assertEqual(unused.calls, [])

    def test_requires_auth(self) -> None:
        cases = [
            ("GET", "/api/settings", None),
            ("GET", "/api/led/capabilities", None),
            ("GET", "/api/led/generate/status?job=x", None),
            (
                "POST",
                "/api/settings",
                {"llm": {"interpreter": "grok", "renderer": "grok", "keys": {}}},
            ),
            ("POST", "/api/settings/test", {}),
            (
                "POST",
                "/api/led/generate",
                {"prompt": "p", "product_id": "CB04", "targets": ["frames"]},
            ),
            ("POST", "/api/led/generate/cancel", {}),
        ]
        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                status, _ = self._request(method, path, body, token=None)
                self.assertEqual(status, 403)

    # -- Task 9: background generation job endpoints ----------------------

    def _plan(self) -> "llm.EffectPlan":
        return llm.EffectPlan(
            subject="pac-man", palette="yellow on black", motion="chomps",
            frame_count=6, frame_ms=100,
            keyframe_prompts=("open", "closed", "open again"),
            tween="crossfade", notes="",
        )

    def _install_fakes(self, interpreter, renderer) -> None:
        """Inject fake interpreter/renderer factories exactly as the registry
        classes are wired in production (``callable(api_key) -> provider``)."""
        self._server.state.llm_factories = _gen_factories(interpreter, renderer)

    def _generate(self, **overrides):
        body = {"prompt": "pac-man chased by a blue ghost",
                "product_id": "CB04", "targets": ["frames"]}
        body.update(overrides)
        return self._request("POST", "/api/led/generate", body)

    def test_generate_lifecycle(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")
        self._save_key("sk-gen-ABCD1234")
        interp = _FakeGenInterpreter(plan=self._plan())
        rend = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", (40, 5), (i * 20, 0, 0))
        )
        self._install_fakes(interp, rend)

        status, data = self._generate()
        self.assertEqual(status, 200)
        job_id = data["job_id"]
        self.assertTrue(job_id)

        # Deterministic: join the worker, then read the final status once.
        self._server.state.join_generation(5)
        status, data = self._request(
            "GET", f"/api/led/generate/status?job={job_id}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "done")
        # Result-shape parity with /api/led/gif plus plan + usage (design §3).
        self.assertEqual(data["tracks"]["frames"]["frame_count"], 6)
        self.assertEqual(data["model"], "CB")
        self.assertEqual(data["source_frames"], 6)
        self.assertEqual(data["decoded_frames"], 6)
        self.assertEqual(data["duration_ms"], 100)
        self.assertEqual(data["source_duration_ms"], 6 * 100)
        self.assertIs(data["timing_resampled"], False)
        self.assertEqual(data["plan"]["subject"], "pac-man")
        self.assertEqual(data["plan"]["rendered_keyframes"], 3)
        self.assertEqual(data["usage"]["provider_calls"], 1 + 3)
        # Exactly one interpret call and one render call for this generation.
        self.assertEqual(len(interp.calls), 1)
        self.assertEqual(len(rend.calls), 1)

    def test_single_flight(self) -> None:
        self._save_key("sk-gen-ABCD1234")
        started, release = threading.Event(), threading.Event()
        interp = _BlockingGenInterpreter(self._plan(), started, release)
        rend = _FakeGenRenderer(image_for=lambda i: None)
        self._install_fakes(interp, rend)
        try:
            status, _ = self._generate()
            self.assertEqual(status, 200)
            self.assertTrue(started.wait(2))
            # A second start while the first job is still running → 409.
            status, _ = self._generate(prompt="second")
            self.assertEqual(status, 409)
        finally:
            release.set()
        self._server.state.join_generation(5)
        # Only the first job's provider call ever happened.
        self.assertEqual(len(interp.calls), 1)

    def test_cancel(self) -> None:
        self._save_key("sk-gen-ABCD1234")
        started, release = threading.Event(), threading.Event()
        interp = _BlockingGenInterpreter(self._plan(), started, release)
        rend = _FakeGenRenderer(image_for=lambda i: None)
        self._install_fakes(interp, rend)

        status, data = self._generate()
        self.assertEqual(status, 200)
        job_id = data["job_id"]
        self.assertTrue(started.wait(2))

        status, _ = self._request("POST", "/api/led/generate/cancel", {})
        self.assertEqual(status, 200)
        release.set()  # interpret returns; generate_effect then sees the cancel flag
        self._server.state.join_generation(5)

        status, data = self._request(
            "GET", f"/api/led/generate/status?job={job_id}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "cancelled")
        # Cancel fired before any keyframe render, and nothing page-affecting moved.
        self.assertEqual(rend.calls, [])
        self.assertIsNone(self._server.state.config)

    def test_validation_first(self) -> None:
        self._save_key("sk-gen-ABCD1234")
        interp = _FakeGenInterpreter(plan=self._plan())
        rend = _FakeGenRenderer(image_for=lambda i: None)
        self._install_fakes(interp, rend)

        # Mixed CyberBoard targets span two rasters → 400 before any provider call.
        status, _ = self._generate(targets=["frames", "keyframes"])
        self.assertEqual(status, 400)
        # Unknown target → 400.
        status, _ = self._generate(targets=["bogus"])
        self.assertEqual(status, 400)
        # A rejected request never reaches the interpreter.
        self.assertEqual(interp.calls, [])

        # frame_count above the model cap is clamped to MODEL_FRAME_CAPS[model].
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")
        interp = _FakeGenInterpreter(plan=self._plan())
        rend = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", (40, 5), (0, 0, 0))
        )
        self._install_fakes(interp, rend)
        status, _ = self._generate(frame_count=9999)
        self.assertEqual(status, 200)
        self._server.state.join_generation(5)
        self.assertEqual(len(interp.calls), 1)
        self.assertEqual(
            interp.calls[0]["spec"].max_frames, llm.MODEL_FRAME_CAPS["CB"]
        )

    def test_missing_key_hint(self) -> None:
        # setUp cleared XAI_API_KEY and points at a temp data dir: no key exists.
        self.assertIsNone(store.resolve_xai_key())
        interp = _FakeGenInterpreter(plan=self._plan())
        rend = _FakeGenRenderer(image_for=lambda i: None)
        self._install_fakes(interp, rend)
        status, data = self._generate()
        self.assertEqual(status, 400)
        self.assertIn("Settings", data["error"])
        # The guard fires before any provider work.
        self.assertEqual(interp.calls, [])

    def test_provider_error_mapping(self) -> None:
        self._save_key("sk-gen-ABCD1234")
        cases = [
            (llm.ProviderError("rate_limited", "slow down", retry_after=7), 429, 7),
            (llm.ProviderError("timeout", "too slow"), 504, None),
            (llm.ProviderError("offline", "no network"), 503, None),
            (llm.ProviderError("bad_response", "garbage"), 502, None),
        ]
        for error, http_status, retry in cases:
            with self.subTest(code=error.code):
                interp = _FakeGenInterpreter(error=error)
                rend = _FakeGenRenderer(image_for=lambda i: None)
                self._install_fakes(interp, rend)
                status, data = self._generate()
                self.assertEqual(status, 200)
                job_id = data["job_id"]
                self._server.state.join_generation(5)
                status, data = self._request(
                    "GET", f"/api/led/generate/status?job={job_id}"
                )
                self.assertEqual(status, http_status)
                self.assertEqual(data["status"], "error")
                self.assertEqual(data["code"], error.code)
                if retry is not None:
                    self.assertEqual(data["retry_after"], retry)

    def test_no_device_writes(self) -> None:
        try:
            from PIL import Image
        except ModuleNotFoundError:
            self.skipTest("Pillow is provided by the led extra")
        self._save_key("sk-gen-ABCD1234")
        interp = _FakeGenInterpreter(plan=self._plan())
        rend = _FakeGenRenderer(
            image_for=lambda i: Image.new("RGB", (40, 5), (0, 0, 0))
        )
        self._install_fakes(interp, rend)
        with patch("am_configurator.writer.write_config") as write_config, \
                patch("am_configurator.macros.write_macros") as write_macros, \
                patch("am_configurator.reader.read_keymap") as read_keymap, \
                patch.object(server, "_probe_keyboard") as probe:
            status, data = self._generate()
            self.assertEqual(status, 200)
            job_id = data["job_id"]
            self._server.state.join_generation(5)
            self._request("GET", f"/api/led/generate/status?job={job_id}")
            self._request("POST", "/api/led/generate/cancel", {})
            write_config.assert_not_called()
            write_macros.assert_not_called()
            read_keymap.assert_not_called()
            probe.assert_not_called()


class MacroProtocolTests(unittest.TestCase):
    def test_cyberboard_accepts_only_an_exact_fifteen_block_macro_prefix(self) -> None:
        counts = (22, 32, 36, 38)
        expected = [
            {
                "original_key": f"#009515{index:02X}",
                "layer_key": ["#11070004"] * count,
                "intvel_ms": [25] * (count - 1) + [0],
            }
            for index, count in enumerate(counts)
        ]
        readable_prefix = copy.deepcopy(expected)
        readable_prefix[-1]["layer_key"] = readable_prefix[-1]["layer_key"][:24]
        readable_prefix[-1]["intvel_ms"] = readable_prefix[-1]["intvel_ms"][:24]

        partial = _classify_macro_readback("CB04", expected, readable_prefix)
        self.assertEqual("partial", partial["status"])
        self.assertEqual(114, partial["verified_events"])
        self.assertEqual(128, partial["expected_events"])
        self.assertIn("15 macro blocks", partial["warning"])
        self.assertEqual(
            "verified",
            _classify_macro_readback("CB04", expected, expected)["status"],
        )

        self.assertEqual(
            "mismatch",
            _classify_macro_readback("AM21", expected, readable_prefix)["status"],
        )
        changed_prefix = copy.deepcopy(readable_prefix)
        changed_prefix[0]["layer_key"][0] = "#11070005"
        self.assertEqual(
            "mismatch",
            _classify_macro_readback("CB04", expected, changed_prefix)["status"],
        )

        restored, warning, used_snapshot = _reconcile_read_macros(
            "CB04", readable_prefix, {"macro_key": expected}
        )
        self.assertEqual(expected, restored)
        self.assertTrue(used_snapshot)
        self.assertIn("complete local snapshot", warning)

        truncated, warning, used_snapshot = _reconcile_read_macros(
            "CB04", readable_prefix, None
        )
        self.assertEqual(readable_prefix, truncated)
        self.assertFalse(used_snapshot)
        self.assertIn("open a saved JSON", warning)

    def test_cyberboard_macro_readback_ui_reports_the_unreadable_tail(self) -> None:
        app = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("macro_read_warning", app)
        self.assertIn("Write accepted; macro tail unreadable", app)

    def test_text_macro_uses_fixed_delays_and_shift_runs(self) -> None:
        plain = text_to_macro_events("ab", 10)
        self.assertEqual(
            ["#11070004", "#10070004", "#11070005", "#10070005"],
            plain["layer_key"],
        )
        self.assertEqual([1, 10, 1, 0], plain["intvel_ms"])

        shifted = text_to_macro_events("A!b", 7)
        self.assertEqual("#110700E1", shifted["layer_key"][0])
        self.assertEqual("#11070004", shifted["layer_key"][1])
        self.assertEqual("#1107001E", shifted["layer_key"][3])
        self.assertEqual("#100700E1", shifted["layer_key"][5])
        self.assertEqual("#11070005", shifted["layer_key"][6])
        self.assertEqual(8, len(shifted["layer_key"]))
        self.assertEqual(0, shifted["intvel_ms"][-1])

    def test_text_macro_supports_enter_and_rejects_untypable_or_long_text(self) -> None:
        self.assertEqual(
            ["#11070028", "#10070028"],
            text_to_macro_events("\n", 10)["layer_key"],
        )
        with self.assertRaisesRegex(ValueError, "US keyboard layout"):
            text_to_macro_events("café", 10)
        with self.assertRaisesRegex(ValueError, "202 macro events"):
            text_to_macro_events("a" * 101, 10)

    def test_macro_import_copies_only_modern_cross_board_definitions(self) -> None:
        source = _base_config("80")
        source["macro_key"] = [{
            "original_key": "#00951502",
            "layer_key": ["#11070004", "#10070004"],
            "intvel_ms": [25, 31, 999, 999],
        }]
        imported = extract_importable_macros(source)
        self.assertEqual([{
            "original_key": "#00951502",
            "layer_key": ["#11070004", "#10070004"],
            "intvel_ms": [25, 31],
        }], imported)
        self.assertEqual("80", source["product_info"]["product_id"])

    def test_official_macro_with_no_final_delay_is_normalized(self) -> None:
        source = _base_config("80")
        source["macro_key"] = [{
            "original_key": "#00951500",
            "layer_key": ["#11070004", "#10070004"],
            "intvel_ms": [25],
        }]
        imported = extract_importable_macros(source)
        self.assertEqual([25, 0], imported[0]["intvel_ms"])
        self.assertTrue(validate_config(source)["ok"])

    def test_validation_rejects_empty_macro(self) -> None:
        source = _base_config("80")
        source["macro_key"] = [{
            "original_key": "#00951500",
            "layer_key": [],
            "intvel_ms": [],
        }]

        result = validate_config(source)

        self.assertFalse(result["ok"])
        self.assertIn("Macro 1 has no events.", result["errors"])

    def test_macro_import_rejects_legacy_only_lighting_export(self) -> None:
        source = _base_config("80")
        source["MACRO_key"] = [{
            "MACRO_key_index": 0,
            "input_key": "#00070013",
            "out_key": ["#00070014"],
            "intvel_ms": [25],
        }]
        with self.assertRaisesRegex(ValueError, r"\*-KEY\.json"):
            extract_importable_macros(source)

    def test_macro_references_are_recovered_from_all_keymap_layers(self) -> None:
        layers = [["#00000000"] * 200 for _ in range(2)]
        layers[0][4] = "#00951502"
        layers[1][8] = "#00951500"
        layers[1][9] = "#00951502"
        self.assertEqual(["#00951500", "#00951502"], _macro_references(layers))

    def test_validation_warns_about_macro_assignments_without_actions(self) -> None:
        config = _base_config("CB04")
        config["key_layer"]["layer_data"][1]["layer"][39] = "#00951500"
        result = validate_config(config)
        self.assertTrue(result["ok"])
        self.assertTrue(any("assigns M1" in warning for warning in result["warnings"]))

    def test_modern_macro_frames_round_trip(self) -> None:
        macros = [
            {
                "original_key": "#00951500",
                "layer_key": ["#11070004", "#10070004"] * 5,
                "intvel_ms": [25, 31] * 5,
            },
            {
                "original_key": "#00951501",
                "layer_key": ["#11070028", "#10070028"],
                "intvel_ms": [120, 0],
            },
        ]
        sent = macro_frames(macros)
        self.assertEqual(3, len(sent))
        self.assertTrue(all(frame[:2] == b"\x06\x05" for frame in sent))
        replies = [build_frame(6, 10, frame[2:63]) for frame in sent]
        self.assertEqual(macros, parse_macro_frames(replies))


class SpotlightProtocolTests(unittest.TestCase):
    def test_validation_rejects_edge_lights_outside_custom_slots(self) -> None:
        page = _page(3)
        page["spotlight_frames"] = {
            "valid": 1,
            "frame_num": 1,
            "frame_data": [
                {"frame_index": 0, "frame_RGB": ["#112233"] * 24}
            ],
        }
        config = _base_config("80")
        config["page_data"] = [page]
        config["page_num"] = 1

        result = validate_config(config)

        self.assertFalse(result["ok"])
        self.assertIn(
            "Page 3 spotlight_frames is only valid on custom pages 5, 6, and 7.",
            result["errors"],
        )

    def test_display_and_per_key_tracks_share_manifest_and_timing(self) -> None:
        page = _page(5)
        page["frames"] = {
            "valid": 1,
            "frame_num": 1,
            "frame_data": [{"frame_index": 0, "frame_RGB": ["#112233"] * 200}],
        }
        page["keyframes"] = {
            "valid": 1,
            "frame_num": 1,
            "frame_data": [{"frame_index": 0, "frame_RGB": ["#445566"] * 90}],
        }
        config = _base_config("CB04")
        config["page_data"] = [page]
        config["page_num"] = 1

        from am_configurator.writer import plan

        encoded = plan(config)
        sections = dict(encoded.sections)
        self.assertEqual(11, sections["rgb_frame"])
        self.assertEqual(5, sections["key_frame"])
        manifest = encoded.frames[0]
        self.assertEqual(bytes([2, 1, 1, 5, 0, 1, 0, 1, 0]), manifest[:9])
        page_control = encoded.frames[1]
        self.assertEqual(bytes([2, 2, 1, 0, 1, 1, 5, 100, 90, 0]), page_control[:10])
        self.assertTrue(any(frame[:4] == bytes([5, 5, 0, 0]) for frame in encoded.frames))

    def test_spotlight_manifest_and_chunks(self) -> None:
        pages = [_page(i) for i in range(8)]
        for index, count in zip((5, 6, 7), (1, 100, 256)):
            page = pages[index]
            page["spotlight_frames"] = {
                "valid": 1,
                "frame_num": count,
                "frame_data": [],
            }
        manifest = car_light_info_frames(pages)
        self.assertEqual(1, len(manifest))
        # Three valid flags, then decimal (hundreds, remainder) count pairs.
        self.assertEqual(bytes([1, 1, 1, 0, 1, 1, 0, 2, 56]), manifest[0][2:11])

        pages[5]["spotlight_frames"] = {
            "valid": 1,
            "frame_num": 1,
            "frame_data": [{"frame_index": 3, "frame_RGB": ["#010203"] * 24}],
        }
        for index in (6, 7):
            pages[index]["spotlight_frames"]["frame_num"] = 0
        frames = car_light_data_frames(pages)
        self.assertEqual(2, len(frames))
        self.assertEqual(bytes([12, 2, 5, 0, 3, 0]), frames[0][:6])
        self.assertEqual(bytes([12, 2, 5, 0, 3, 1]), frames[1][:6])


if __name__ == "__main__":
    unittest.main()
