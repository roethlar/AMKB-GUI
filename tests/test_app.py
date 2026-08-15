from __future__ import annotations

import base64
import copy
import errno
import inspect
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
import traceback
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
from am_configurator import __version__, profile_metadata, transport
from am_configurator.device_mapping import (
    MAX_FRAMES,
    device_descriptor,
    firmware_led_speed,
    frames_to_led_tracks,
    target_capabilities,
)
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
    config_section_compatibility,
    config_transfer_options,
    create_server,
    extract_importable_macros,
    gif_to_led_frames,
    gif_to_led_tracks,
    merge_configs,
    project_config_sections,
    text_to_macro_events,
    validate_config,
)
from am_configurator.protocol import build_frame
from am_configurator.device import candidate_ports
from am_configurator.protocol import exclusive_serial_kwargs
from am_configurator.macros import macro_frames, parse_macro_frames
from am_configurator.writer import car_light_data_frames, car_light_info_frames
from am_configurator import device_mapping, server, store
from am_configurator import media_composition
from build_tools.release_info import project_version
from am_configurator.library import (
    GeneratedAssetLibrary,
    SavedItemLibrary,
)


_DEFAULT_SETTINGS = {
    "schema_version": 7,
    "library": {"current_root": None, "roots": []},
    "generation": {"loop_mode": "smooth"},
}


class SettingsStoreTests(unittest.TestCase):
    """Strict v5 settings, safe legacy migration, and curated AI catalog."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="am_settings_test_")
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME")
        }
        os.environ.pop("XDG_DATA_HOME", None)
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

    def test_v1_file_migrates_to_v7_defaults_and_discards_legacy_llm_block(self) -> None:
        legacy = {
            "llm": {
                "interpreter": "grok",
                "renderer": "grok",
                "keys": {"xai": "sk-existing"},
            }
        }
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(legacy), encoding="utf-8")

        self.assertEqual(store.load_settings(), _DEFAULT_SETTINGS)
        self.assertFalse(path.with_name(path.name + ".bad").exists())
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], 7)
        self.assertNotIn("llm", saved)
        self.assertNotIn("sk-existing", path.read_text(encoding="utf-8"))

    def test_v7_round_trip(self) -> None:
        payload = copy.deepcopy(_DEFAULT_SETTINGS)
        payload["generation"]["loop_mode"] = "ping_pong"
        store.save_settings(payload)
        self.assertEqual(store.load_settings(), payload)

    def test_v6_migrates_to_v7_discarding_the_legacy_ai_block(self) -> None:
        library_root = str((Path(self._tmp) / "library").resolve())
        legacy = {
            "schema_version": 6,
            "ai": {
                "enabled": True,
                "backend": "local",
                "local": {
                    "model_id": "ornith:latest",
                    "model_digest": "b" * 64,
                    "setup_fingerprint": "c" * 64,
                },
            },
            "library": {
                "current_root": library_root,
                "roots": [library_root],
            },
            "generation": {"loop_mode": "ping_pong"},
        }
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(legacy), encoding="utf-8")

        migrated = store.load_settings()
        expected = copy.deepcopy(_DEFAULT_SETTINGS)
        expected["library"] = {
            "current_root": library_root,
            "roots": [library_root],
        }
        expected["generation"]["loop_mode"] = "ping_pong"
        self.assertEqual(expected, migrated)
        self.assertEqual(expected, json.loads(path.read_text(encoding="utf-8")))
        self.assertNotIn("ai", migrated)

    def test_unknown_fields_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store.save_settings({**copy.deepcopy(_DEFAULT_SETTINGS), "bogus": 1})
        with self.assertRaises(ValueError):
            store.update_preferences({"models": {}, "bogus": 1})
        with self.assertRaises(ValueError):
            store.update_library_root({"current_root": None, "bogus": 1})
        # A rejected save must persist nothing.
        self.assertFalse(store.settings_path().exists())

    def test_retired_model_and_candidate_preferences_are_rejected(self) -> None:
        invalid_preferences = (
            {"models": {"interpreter": "grok-future"}},
            {"models": {"concept": "grok-future"}},
            {"models": {"video": "grok-future"}},
            {"models": {"unknown": "grok-4.5"}},
            {"loop_mode": "crossfade"},
            {"candidate_count": 0},
            {"candidate_count": 9},
            {"candidate_count": True},
            {"candidate_count": "4"},
        )
        for payload in invalid_preferences:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                store.update_preferences(payload)
        self.assertFalse(store.settings_path().exists())

    def test_independent_updates_preserve_loop_mode_and_library(self) -> None:
        root = Path(self._tmp) / "library"
        store.update_preferences({"loop_mode": "none"})
        store.update_library_root({"current_root": str(root)})
        settings = store.load_settings()
        self.assertNotIn("llm", settings)
        self.assertNotIn("candidate_count", settings["generation"])
        self.assertEqual(settings["generation"]["loop_mode"], "none")
        self.assertEqual(settings["library"]["current_root"], str(root.resolve()))

    def test_v2_model_preferences_are_discarded_during_migration(self) -> None:
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": 2,
            "llm": {
                "models": {
                    "interpreter": "grok-4.3",
                    "concept": "grok-imagine-image-quality",
                    "video": "grok-imagine-video",
                },
                "keys": {},
            },
            "library": {"current_root": None, "roots": []},
            "generation": {
                "candidate_count": 8,
                "loop_mode": "smooth",
                "privacy_ack_version": None,
                "privacy_ack_at": None,
            },
        }), encoding="utf-8")
        self.assertNotIn("llm", store.load_settings())

    def test_library_root_history_is_canonical_and_deduplicated(self) -> None:
        first = Path(self._tmp) / "first"
        second = Path(self._tmp) / "second"
        first.mkdir()
        second.mkdir()
        first_spelling = first / "child" / ".."

        store.update_library_root({"current_root": str(first_spelling)})
        store.update_library_root({"current_root": str(first)})
        self.assertEqual(store.load_settings()["library"]["roots"], [])
        store.update_library_root({"current_root": str(second)})
        store.update_library_root({"current_root": str(first)})
        store.update_library_root({"current_root": None})

        library = store.load_settings()["library"]
        self.assertIsNone(library["current_root"])
        self.assertEqual(library["roots"], [str(first.resolve()), str(second.resolve())])

    def test_corrupt_file_recovers(self) -> None:
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not valid json", encoding="utf-8")
        self.assertEqual(store.load_settings(), _DEFAULT_SETTINGS)
        self.assertFalse(path.exists())
        self.assertTrue(path.with_name(path.name + ".bad").exists())

    def test_file_permissions(self) -> None:
        store.update_preferences({"loop_mode": "none"})
        if sys.platform.startswith("win"):
            self.skipTest("POSIX file permissions are not enforced on Windows")
        mode = stat.S_IMODE(os.stat(store.settings_path()).st_mode)
        self.assertEqual(mode, 0o600)

    def test_transient_read_errors_preserve_exact_settings_bytes(self) -> None:
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        original = (json.dumps(_DEFAULT_SETTINGS, indent=2) + "\n").encode("utf-8")
        path.write_bytes(original)
        real_read_text = Path.read_text

        for error_number in (errno.EMFILE, errno.EACCES, errno.EIO):
            with self.subTest(errno=error_number):

                def fail_settings_read(candidate, *args, **kwargs):
                    if candidate == path:
                        raise OSError(error_number, "transient settings read failure")
                    return real_read_text(candidate, *args, **kwargs)

                with patch.object(Path, "read_text", fail_settings_read):
                    settings, reason = store.load_settings_with_status()

                self.assertEqual(_DEFAULT_SETTINGS, settings)
                self.assertEqual("settings_unavailable", reason)
                self.assertEqual(original, path.read_bytes())
                self.assertFalse(path.with_name(path.name + ".bad").exists())

    def test_future_schema_is_reported_without_rename_or_overwrite(self) -> None:
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        original = (
            json.dumps(
                {
                    "schema_version": store.SETTINGS_SCHEMA_VERSION + 1,
                    "future": {"kept": True},
                },
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
        path.write_bytes(original)

        settings, reason = store.load_settings_with_status()

        self.assertEqual(_DEFAULT_SETTINGS, settings)
        self.assertEqual("settings_schema_unsupported", reason)
        self.assertEqual(original, path.read_bytes())
        self.assertFalse(path.with_name(path.name + ".bad").exists())
        with self.assertRaises(store.SettingsSchemaUnsupportedError):
            store.update_generation_settings({"loop_mode": "ping_pong"})
        self.assertEqual(original, path.read_bytes())


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


def _am_master_neon_lighting(
    *,
    frame_count: int = 1,
    speed: int = 90,
    brightness: int = 255,
    description: str | None = None,
) -> dict:
    result = {
        "speed": speed,
        "brightness": brightness,
        "frames": [
            [f"{(frame * 4099 + pixel * 17 + 0x123456) & 0xFFFFFF:06x}" for pixel in range(230)]
            for frame in range(frame_count)
        ],
        "frames_axial": [
            [f"{(frame * 4099 + pixel * 17 + 0x654321) & 0xFFFFFF:06x}" for pixel in range(89)]
            for frame in range(frame_count)
        ],
    }
    if description is not None:
        result["description"] = description
    return result


def _synthetic_neon_key_layout() -> list[dict[str, int | float]]:
    axial = next(
        target
        for target in target_capabilities()["NEON"]["targets"]
        if target["name"] == "axial"
    )
    width = axial["width"]
    height = axial["height"]
    pixel_map = axial["map"]
    matrix_columns = device_descriptor("NEON80")["keymap"]["matrix_columns"]
    result: list[dict[str, int | float]] = []
    for row in range(height):
        row_pixels = [
            pixel
            for pixel in pixel_map[row * width : (row + 1) * width]
            if pixel >= 0
        ]
        key_count = min(len(row_pixels), matrix_columns)
        key_width = 96.0 / key_count
        for column in range(key_count):
            result.append(
                {
                    "index": row * matrix_columns + column,
                    "matrix_row": row,
                    "matrix_col": column,
                    "x": column * key_width,
                    "y": row * (88.0 / height),
                    "width": key_width,
                    "height": 12.0,
                    "rotation": 0.0,
                }
            )
    return result


class DesktopServerTests(unittest.TestCase):
    def test_keyboard_probe_does_not_shadow_device_module(self) -> None:
        keyboard = SimpleNamespace(is_keyboard=True)
        with patch("am_configurator.device.probe", return_value=keyboard) as probe:
            result = _probe_keyboard(
                transport.DeviceHandle(transport.SERIAL, "/dev/example"), attempts=1
            )

        self.assertIs(keyboard, result)
        probe.assert_called_once_with("/dev/example", full=True)

    def test_package_declares_native_desktop_entry_point(self) -> None:
        metadata = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertNotIn("version", metadata["project"])
        self.assertEqual(["version"], metadata["project"]["dynamic"])
        self.assertEqual(
            "am_configurator/_version.py",
            metadata["tool"]["hatch"]["version"]["path"],
        )
        self.assertEqual(project_version(ROOT), __version__)
        self.assertEqual(
            "am_configurator.desktop:main",
            metadata["project"]["gui-scripts"]["am-configurator"],
        )

    def test_empty_state_connect_task_reaches_the_device_read_action(self) -> None:
        source = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("Connect a keyboard", source)
        self.assertIn('id="read-device"', source)
        self.assertIn("Read keymap &amp; macros", source)
        self.assertIn(
            '$("#empty-connect").addEventListener("click",showDeviceDialog)',
            script,
        )
        self.assertNotIn("Device → Read", source)

    def test_layout_audit_uses_the_platform_webview_policy(self) -> None:
        # cx-4: a hardcoded gui="edgechromium" breaks the audit tool on the
        # macOS/Linux platforms the app itself supports.
        source = (ROOT / "build_tools" / "layout_audit.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('gui="edgechromium"', source)
        self.assertIn("_native_webview_policy", source)

    def test_version_lives_only_in_about(self) -> None:
        html = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )
        style = (ROOT / "am_configurator" / "web" / "style.css").read_text(
            encoding="utf-8"
        )
        topbar = re.search(
            r'<header class="topbar">(?P<body>.*?)</header>', html, re.DOTALL
        )
        about = re.search(
            r'<dialog id="about-dialog".*?</dialog>', html, re.DOTALL
        )

        self.assertIsNotNone(topbar)
        self.assertIsNotNone(about)
        self.assertNotIn("AM Configurator", topbar.group("body"))
        self.assertNotIn("Version", topbar.group("body"))
        self.assertNotIn('class="brand"', html)
        self.assertNotIn('id="app-version"', html)
        self.assertIn(
            '<button id="about-button" type="button" class="about-link">About</button>',
            html,
        )
        self.assertIn("AM Configurator", about.group(0))
        self.assertIn("Version __AM_VERSION__", about.group(0))
        self.assertEqual(1, html.count("__AM_VERSION__"))
        self.assertIn('$("#about-button").addEventListener("click"', script)
        self.assertIn(".about-link", style)
        self.assertNotIn("button primary", about.group(0))

    def test_text_selection_is_limited_to_editable_controls(self) -> None:
        style = (ROOT / "am_configurator" / "web" / "style.css").read_text(
            encoding="utf-8"
        )
        noneditable = re.search(
            r"body,\s*body \* \{(?P<body>.*?)\}",
            style,
            re.DOTALL,
        )
        editable = re.search(
            r'input:not\(\[type\]\),.*?\[contenteditable="plaintext-only"\] '
            r"\{(?P<body>.*?)\}",
            style,
            re.DOTALL,
        )

        self.assertIsNotNone(noneditable)
        self.assertIsNotNone(editable)
        self.assertIn("-webkit-user-select: none", noneditable.group("body"))
        self.assertIn("user-select: none", noneditable.group("body"))
        self.assertIn("-webkit-user-select: text", editable.group("body"))
        self.assertIn("user-select: text", editable.group("body"))
        self.assertNotIn("user-select: all", style)

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
        # The edge track is gated on the family actually authoring it, and only
        # for the custom slots. Comparing the raw product id instead would miss
        # AM21, which is the Relic's reported identifier.
        self.assertIn('edgeColorCount!==null&&index>=5', compact)
        self.assertIn(
            'spec.authoredTracks.includes("spotlight_frames")',
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

    def test_neon_write_dialog_explains_the_physical_unlock_combo(self) -> None:
        html = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "am_configurator" / "web" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="write-unlock-note"', html)
        self.assertIn("Esc and F2", script)
        self.assertIn('productFamily(verifiedDevice.product_id)==="NEON"', script)
        self.assertIn("Unlocking, then writing", script)
        self.assertIn(
            '$("#write-dialog").addEventListener("cancel",event=>',
            script,
        )
        self.assertIn("event.preventDefault()", script)

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
                transport.DeviceHandle(transport.SERIAL, "/dev/example"),
                expected,
                attempts=2,
                retry_seconds=0.01,
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
                transport.DeviceHandle(transport.SERIAL, "/dev/example"),
                expected,
                attempts=2,
                retry_seconds=0.01,
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
                self.assertNotIn(b'class="brand"', page)
                self.assertNotIn(b'id="app-version"', page)
                self.assertEqual(1, page.count(f"Version {__version__}".encode()))
                about = re.search(
                    rb'<dialog id="about-dialog".*?</dialog>', page, re.DOTALL
                )
                self.assertIsNotNone(about)
                self.assertIn(f"Version {__version__}".encode(), about.group(0))
                self.assertNotIn(b"__AM_VERSION__", page)
            request = Request(
                f"http://127.0.0.1:{server.server_port}/api/config",
                headers={"X-AM-Token": token},
            )
            with urlopen(request, timeout=2) as response:
                self.assertEqual(
                    b'{"config": null, "document_revision": null, '
                    b'"layout_evidence": null, "layout_warning": null}',
                    response.read(),
                )
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
        self.assertEqual("blocked", cross_board["sections"]["keymap"]["status"])
        self.assertEqual("portable", cross_board["sections"]["macros"]["status"])

        same_board = config_transfer_options(source, "AM21")
        self.assertTrue(same_board["compatible"])
        self.assertTrue(same_board["can_merge_keymap"])
        self.assertTrue(same_board["can_merge_leds"])
        self.assertEqual("exact", same_board["sections"]["keymap"]["status"])

    def test_neon_keymap_compatibility_requires_layout_and_supported_codes(self) -> None:
        layers = [["#00070004"] * 90 for _ in range(4)]
        source = blank_config("NEON80", layers, [])
        destination = blank_config("NEON80", layers, [])

        unknown = config_section_compatibility(source, destination)
        self.assertEqual("blocked", unknown["sections"]["keymap"]["status"])
        self.assertEqual(
            "source_layout_unknown",
            unknown["sections"]["keymap"]["reason_code"],
        )

        layout = [
            {
                "index": 0,
                "matrix_row": 0,
                "matrix_col": 0,
                "x": 0.0,
                "y": 0.0,
                "width": 6.0,
                "height": 12.0,
                "rotation": 0.0,
            }
        ]
        exact = config_section_compatibility(
            source,
            destination,
            source_key_layout=layout,
            target_key_layout=layout,
        )
        self.assertEqual("exact", exact["sections"]["keymap"]["status"])

        source["key_layer"]["layer_data"][0]["layer"][0] = "#000C00E9"
        unsupported = config_section_compatibility(
            source,
            destination,
            source_key_layout=layout,
            target_key_layout=layout,
        )
        self.assertEqual("blocked", unsupported["sections"]["keymap"]["status"])
        self.assertEqual(
            "unsupported_assignment",
            unsupported["sections"]["keymap"]["reason_code"],
        )

    def test_profile_compatibility_rejects_layer_and_macro_capacity_overflow(self) -> None:
        destination = _base_config("80")
        too_many_layers = _base_config("80")
        too_many_layers["key_layer"] = {
            "valid": 1,
            "layer_num": 8,
            "layer_data": [_layer() for _ in range(8)],
        }
        layers = config_section_compatibility(too_many_layers, destination)
        self.assertEqual(
            "layer_capacity_exceeded",
            layers["sections"]["keymap"]["reason_code"],
        )

        macro_source = _base_config("80")
        macro_source["macro_key"] = [
            {
                "original_key": f"#009515{index:02X}",
                "layer_key": ["#00070004"],
                "intvel_ms": [0],
            }
            for index in range(17)
        ]
        neon = blank_config(
            "NEON80",
            [["#00070004"] * 90 for _ in range(4)],
            [],
        )
        macros = config_section_compatibility(macro_source, neon)
        self.assertEqual("blocked", macros["sections"]["macros"]["status"])
        self.assertEqual(
            "macro_capacity_exceeded",
            macros["sections"]["macros"]["reason_code"],
        )

    def test_section_projection_preserves_destination_identity_and_unselected_data(self) -> None:
        source = _base_config("80")
        source["product_info"]["source_only"] = "must not cross"
        source["key_layer"]["layer_data"][0]["layer"][0] = "#00070004"
        source["key_layer"]["layer_data"][1]["layer"][0] = "#00070005"
        source["macro_key"] = [
            {
                "original_key": "#00951500",
                "layer_key": ["#11070004", "#10070004"],
                "intvel_ms": [25, 0],
            }
        ]

        destination = _base_config("AM21")
        destination["product_info"]["destination_identity"] = "keep"
        destination["key_layer"]["layer_num"] = 3
        destination["key_layer"]["layer_data"].append(_layer("#00070006"))
        destination["page_data"] = [_page(5)]
        destination["page_num"] = 1
        original_identity = copy.deepcopy(destination["product_info"])
        original_lighting = copy.deepcopy(destination["page_data"])

        result = project_config_sections(
            source,
            destination,
            ["keymap", "macros"],
        )
        candidate = result["config"]
        self.assertEqual(original_identity, candidate["product_info"])
        self.assertNotIn("source_only", candidate["product_info"])
        self.assertEqual(original_lighting, candidate["page_data"])
        self.assertEqual(
            "#00070004",
            candidate["key_layer"]["layer_data"][0]["layer"][0],
        )
        self.assertEqual(
            "#00070005",
            candidate["key_layer"]["layer_data"][1]["layer"][0],
        )
        self.assertEqual(
            "#00070006",
            candidate["key_layer"]["layer_data"][2]["layer"][0],
        )
        self.assertEqual(source["macro_key"], candidate["macro_key"])
        self.assertTrue(result["validation"]["ok"])

    def test_section_projection_accepts_a_saved_dynamic_keymap_signature(self) -> None:
        layers = [["#00070004"] * 90 for _ in range(4)]
        source = blank_config("NEON80", layers, [])
        destination = blank_config("NEON80", layers, [])
        source["key_layer"]["layer_data"][0]["layer"][0] = "#00070005"
        layout = [
            {
                "index": 0,
                "matrix_row": 0,
                "matrix_col": 0,
                "x": 0.0,
                "y": 0.0,
                "width": 6.0,
                "height": 12.0,
                "rotation": 0.0,
            }
        ]
        saved_signature = device_mapping.device_descriptor(
            "NEON80",
            key_layout=layout,
        )["keymap"]["signature"]

        result = project_config_sections(
            source,
            destination,
            ["keymap"],
            source_keymap_signature=saved_signature,
            target_key_layout=layout,
        )

        self.assertEqual(
            "#00070005",
            result["config"]["key_layer"]["layer_data"][0]["layer"][0],
        )
        self.assertEqual(
            "exact",
            result["compatibility"]["sections"]["keymap"]["status"],
        )

    def test_embedded_dynamic_layout_drives_offline_profile_compatibility(self) -> None:
        layers = [["#00070004"] * 90 for _ in range(4)]
        source = blank_config("NEON80", layers, [])
        destination = blank_config("NEON80", layers, [])
        layout = [
            {
                "index": 0,
                "matrix_row": 0,
                "matrix_col": 0,
                "x": 0.0,
                "y": 0.0,
                "width": 6.0,
                "height": 12.0,
                "rotation": 0.0,
            }
        ]
        evidence = profile_metadata.build_dynamic_layout("NEON80", layout)
        source = profile_metadata.attach_dynamic_layout(source, evidence)
        destination = profile_metadata.attach_dynamic_layout(destination, evidence)

        compatibility = config_section_compatibility(source, destination)

        self.assertEqual(
            "exact",
            compatibility["sections"]["keymap"]["status"],
        )
        self.assertEqual(
            evidence["keymap_signature"],
            compatibility["source"]["keymap"]["signature"],
        )

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
            count = min(int(getattr(image, "n_frames", 1)), MAX_FRAMES)
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
            result["tracks"]["frames"]["frame_count"], MAX_FRAMES
        )
        self.assertEqual(MAX_FRAMES, result["source_frames"])
        self.assertEqual(MAX_FRAMES, result["decoded_frames"])

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


class DeviceMappingConstantsTests(unittest.TestCase):
    """Shared firmware-speed constants used by the device protocol layer."""

    def test_device_mapping_owns_firmware_speed_steps(self) -> None:
        self.assertEqual(34, min(device_mapping.LED_SPEEDS_MS))


class LedGenerateEndpointTests(unittest.TestCase):
    """Task 8: settings + capabilities HTTP endpoints on the loopback server.

    Each test starts a real ``create_server`` instance on a background thread and
    drives it over localhost with ``X-AM-Token``. Settings persistence is isolated
    to a temp ``AM_CONFIGURATOR_DATA_DIR``, so nothing here reads a real environment.
    """

    _DEFAULT = object()  # sentinel: use the server's own token

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="am_endpoint_test_")
        self._saved_env = {
            k: os.environ.get(k)
            for k in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME")
        }
        os.environ.pop("XDG_DATA_HOME", None)
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

    def test_key_assignments_use_the_target_familys_wire_vocabulary(self) -> None:
        for code in ("#00000000", "#00070004", "#0095150F", "#00FF5101"):
            with self.subTest(code=code):
                status, response = self._request(
                    "POST",
                    "/api/keymap/assignment",
                    {"product_id": "NEON80", "code": code.lower()},
                )
                self.assertEqual(200, status)
                self.assertEqual({"ok": True, "code": code}, response)

        for code in ("#000C00E9", "#00920100", "#00951510", "#00FF0004"):
            with self.subTest(code=code):
                status, response = self._request(
                    "POST",
                    "/api/keymap/assignment",
                    {"product_id": "NEON80", "code": code},
                )
                self.assertEqual(400, status)
                self.assertFalse(response["ok"])
                self.assertIn(code, response["error"])
                self.assertIn("cannot be written", response["error"])

        status, response = self._request(
            "POST",
            "/api/keymap/assignment",
            {"product_id": "AM21", "code": "#00920100"},
        )
        self.assertEqual(200, status)
        self.assertEqual({"ok": True, "code": "#00920100"}, response)

    @staticmethod
    def _dynamic_layout(*, first_width: float = 6.0) -> list[dict[str, int | float]]:
        return [
            {
                "index": 0,
                "matrix_row": 0,
                "matrix_col": 0,
                "x": 0.0,
                "y": 0.0,
                "width": first_width,
                "height": 12.0,
                "rotation": 0.0,
            },
            {
                "index": 1,
                "matrix_row": 0,
                "matrix_col": 1,
                "x": 12.0,
                "y": 0.0,
                "width": 8.0,
                "height": 12.0,
                "rotation": 0.0,
            },
        ]

    def test_document_sync_and_export_use_server_validated_layout_evidence(self) -> None:
        config = blank_config(
            "NEON80",
            [["#00000000"] * 90 for _ in range(4)],
            [],
        )
        evidence = profile_metadata.remember_dynamic_layout(
            "NEON80",
            self._dynamic_layout(),
        )

        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {
                "config": config,
                "layout_signature": evidence["keymap_signature"],
            },
        )
        self.assertEqual(200, status)
        self.assertEqual(
            evidence["keymap_signature"],
            synchronized["layout_evidence"]["keymap_signature"],
        )
        self.assertEqual("remembered", synchronized["layout_evidence"]["source"])

        status, exported = self._request(
            "POST",
            "/api/config/export",
            {
                "config": config,
                "layout_signature": evidence["keymap_signature"],
            },
        )
        self.assertEqual(200, status)
        self.assertEqual(
            evidence["keymap_signature"],
            exported["config"]["_am_configurator"]["dynamic_layout"][
                "keymap_signature"
            ],
        )
        self.assertEqual(evidence["key_layout"], exported["layout_evidence"]["key_layout"])

        fixed = _base_config("AM21")
        status, fixed_export = self._request(
            "POST",
            "/api/config/export",
            {"config": fixed},
        )
        self.assertEqual(200, status)
        self.assertEqual(fixed, fixed_export["config"])
        self.assertIsNone(fixed_export["layout_evidence"])

    def test_profile_export_rejects_connected_layout_conflicting_with_embedded(self) -> None:
        layout = self._dynamic_layout()
        evidence = profile_metadata.build_dynamic_layout("NEON80", layout)
        config = profile_metadata.attach_dynamic_layout(
            blank_config(
                "NEON80",
                [["#00000000"] * 90 for _ in range(4)],
                [],
            ),
            evidence,
        )

        status, rejected = self._request(
            "POST",
            "/api/config/export",
            {
                "config": config,
                "key_layout": self._dynamic_layout(first_width=7.0),
            },
        )
        self.assertEqual(400, status)
        self.assertEqual(
            "The connected keyboard layout does not match the exact layout "
            "embedded in this profile.",
            rejected["error"],
        )
        self.assertIsNone(store.load_layout_evidence("NEON80"))

        status, exported = self._request(
            "POST",
            "/api/config/export",
            {"config": config, "key_layout": layout},
        )
        self.assertEqual(200, status)
        self.assertEqual("embedded", exported["layout_evidence"]["source"])
        self.assertEqual(
            config["_am_configurator"],
            exported["config"]["_am_configurator"],
        )

    def test_dynamic_layout_mismatch_blocks_before_confirmation_or_transport(self) -> None:
        config = blank_config(
            "NEON80",
            [["#00000000"] * 90 for _ in range(4)],
            [],
        )
        evidence = profile_metadata.build_dynamic_layout(
            "NEON80",
            self._dynamic_layout(),
        )
        config = profile_metadata.attach_dynamic_layout(config, evidence)
        connected = SimpleNamespace(
            is_keyboard=True,
            product_id="NEON80",
            key_layout=self._dynamic_layout(first_width=7.0),
        )
        transmissions: list[dict] = []
        link = SimpleNamespace(
            write_config=lambda address, candidate: transmissions.append(candidate),
        )
        body = {
            "transport": transport.SERIAL,
            "address": "safe-test-device",
            "config": config,
            "layout_signature": evidence["keymap_signature"],
        }

        with (
            patch("am_configurator.server._probe_keyboard", return_value=connected),
            patch.object(transport, "transport_for_handle", return_value=link),
        ):
            status, preflight = self._request(
                "POST",
                "/api/device/preflight",
                body,
            )
            self.assertEqual(400, status)
            self.assertEqual("layout_mismatch", preflight["code"])

            status, direct = self._request(
                "POST",
                "/api/device/write",
                {**body, "confirmation": "NEON80"},
            )

        self.assertEqual(400, status)
        self.assertEqual("layout_mismatch", direct["code"])
        self.assertEqual([], transmissions)

    def test_protocol_boundary_strips_app_metadata_before_any_driver_sees_it(self) -> None:
        config = _base_config("AM21")
        config["_am_configurator"] = {
            "schema_version": 1,
            "dynamic_layout": {
                "address": "COM-private",
                "serial": "shared-dummy",
            },
        }
        config["_provenance"] = {"path": "C:/private/profile.json"}
        connected = SimpleNamespace(is_keyboard=True, product_id="AM21")
        received: list[dict] = []

        def capture(_address: str, candidate: dict) -> None:
            received.append(candidate)
            raise ValueError("captured before transport")

        link = SimpleNamespace(write_config=capture)
        with (
            patch("am_configurator.server._probe_keyboard", return_value=connected),
            patch.object(transport, "transport_for_handle", return_value=link),
        ):
            status, _response = self._request(
                "POST",
                "/api/device/write",
                {
                    "transport": transport.SERIAL,
                    "address": "safe-test-device",
                    "config": config,
                    "confirmation": "AM21",
                },
            )

        self.assertEqual(400, status)
        self.assertEqual(1, len(received))
        self.assertNotIn("_am_configurator", received[0])
        self.assertNotIn("_provenance", received[0])
        self.assertEqual(
            {
                "exchange_key",
                "exchange_num",
                "key_layer",
                "macro_key",
                "page_data",
                "swap_key",
                "swap_key_num",
            }
            & set(config),
            set(received[0]),
        )

    def test_verified_neon_snapshot_retains_portable_layout_metadata(self) -> None:
        config = blank_config(
            "NEON80",
            [["#00000000"] * 90 for _ in range(4)],
            [],
        )
        connected = SimpleNamespace(
            is_keyboard=True,
            product_id="NEON80",
            key_layout=self._dynamic_layout(),
            version="test",
        )
        protocol_inputs: list[dict] = []
        stored: list[dict] = []
        snapshotted: list[dict] = []

        link = SimpleNamespace(
            write_config=lambda _address, candidate: (
                protocol_inputs.append(copy.deepcopy(candidate))
                or transport.WriteReceipt(1, "test report")
            ),
            write_macros=lambda _address, _macros: None,
            read_macros=lambda _address: [],
        )

        with (
            patch("am_configurator.server._probe_keyboard", return_value=connected),
            patch("am_configurator.server._verify_keymap_readback"),
            patch.object(transport, "transport_for_handle", return_value=link),
            patch.object(
                transport,
                "device_json",
                return_value={
                    "transport": transport.SERIAL,
                    "address": "safe-test-device",
                    "product_id": "NEON80",
                    "key_layout": self._dynamic_layout(),
                },
            ),
            patch.object(
                store,
                "save_current",
                side_effect=lambda _product, candidate, **_kwargs: (
                    stored.append(copy.deepcopy(candidate))
                    or Path(self._tmp) / "current.json"
                ),
            ),
            patch.object(
                store,
                "snapshot",
                side_effect=lambda _product, candidate: (
                    snapshotted.append(copy.deepcopy(candidate))
                    or Path(self._tmp) / "snapshot.json"
                ),
            ),
            patch("am_configurator.server.time.sleep"),
        ):
            status, response = self._request(
                "POST",
                "/api/device/write",
                {
                    "transport": transport.SERIAL,
                    "address": "safe-test-device",
                    "config": config,
                    "confirmation": "NEON80",
                },
            )

        self.assertEqual(200, status, response)
        self.assertEqual(1, len(protocol_inputs))
        self.assertNotIn("_am_configurator", protocol_inputs[0])
        self.assertEqual(1, len(stored))
        self.assertEqual(stored, snapshotted)
        metadata = stored[0]["_am_configurator"]["dynamic_layout"]
        self.assertEqual("NEON80", metadata["product_id"])
        self.assertRegex(metadata["keymap_signature"], r"^keymap:v1:[0-9a-f]{64}$")
        self.assertEqual(self._dynamic_layout(), metadata["key_layout"])

    def test_device_read_publishes_the_reported_macro_limits(self) -> None:
        device_layers = [["#00000000"] * 90 for _ in range(4)]
        device = SimpleNamespace(is_keyboard=True, product_id="NEON80")
        link = SimpleNamespace(
            read_keymap=lambda address, *, layers: device_layers,
            read_macro_state=lambda address: transport.MacroReadResult(
                [],
                device_reported=True,
                device_macro_count=9,
                device_macro_buffer_bytes=321,
            ),
        )

        with (
            patch.object(transport, "transport_for_handle", return_value=link),
            patch("am_configurator.server._probe_keyboard", return_value=device),
            patch.object(
                transport,
                "device_json",
                return_value={"product_id": "NEON80"},
            ),
            patch("am_configurator.server._stored_device_config", return_value=(None, None)),
            patch("am_configurator.server.time.sleep"),
        ):
            status, response = self._request(
                "POST",
                "/api/device/read",
                {"port": "/dev/example", "layers": 4},
            )

        self.assertEqual(200, status)
        self.assertEqual(9, response["device"]["macro_count"])
        self.assertEqual(321, response["device"]["macro_buffer_bytes"])
        descriptor = response["device"]["descriptor"]
        self.assertIsNone(descriptor["keymap"]["signature"])
        self.assertEqual(4, descriptor["limits"]["layers"])
        self.assertEqual(9, descriptor["limits"]["macros"])
        self.assertEqual(321, descriptor["limits"]["macro_buffer_bytes"])
        self.assertEqual({"axial", "head"}, set(descriptor["lighting"]))

    def test_device_io_stays_on_one_worker_across_http_requests(self) -> None:
        device_layers = [["#00000000"] * 90 for _ in range(4)]
        device = SimpleNamespace(is_keyboard=True, product_id="NEON80")
        workers = []

        def record(value):
            workers.append(threading.current_thread())
            return value

        link = SimpleNamespace(
            read_keymap=lambda address, *, layers: record(device_layers),
            read_macro_state=lambda address: record(
                transport.MacroReadResult([], device_reported=False)
            ),
        )

        with (
            patch.object(transport, "discover", side_effect=lambda: record([])),
            patch.object(transport, "transport_for_handle", return_value=link),
            patch(
                "am_configurator.server._probe_keyboard",
                side_effect=lambda handle: record(device),
            ),
            patch.object(
                transport,
                "device_json",
                return_value={"product_id": "NEON80"},
            ),
            patch(
                "am_configurator.server._stored_device_config",
                return_value=(None, None),
            ),
            patch("am_configurator.server.time.sleep"),
        ):
            scan_status, _ = self._request("GET", "/api/devices")
            read_status, _ = self._request(
                "POST",
                "/api/device/read",
                {"port": "/dev/example", "layers": 4},
            )

        self.assertEqual(200, scan_status)
        self.assertEqual(200, read_status)
        self.assertGreaterEqual(len(workers), 4)
        self.assertEqual(1, len({id(worker) for worker in workers}))
        self.assertTrue(workers[0].name.startswith("am-device-io"))

    def test_injected_device_discovery_keeps_native_smoke_off_hardware(self) -> None:
        workers: list[str] = []

        def offline_discovery():
            workers.append(threading.current_thread().name)
            return []

        isolated_server, url = create_server(device_discovery=offline_discovery)
        isolated_thread = threading.Thread(
            target=isolated_server.serve_forever,
            daemon=True,
        )
        isolated_thread.start()
        try:
            token = parse_qs(urlparse(url).query)["token"][0]
            request = Request(
                f"http://127.0.0.1:{isolated_server.server_port}/api/devices",
                headers={"X-AM-Token": token},
            )
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read())
                self.assertEqual(200, response.status)
        finally:
            isolated_server.shutdown()
            isolated_server.server_close()
            isolated_thread.join(timeout=2)

        self.assertEqual({"devices": []}, payload)
        self.assertEqual(1, len(workers))
        self.assertTrue(workers[0].startswith("am-device-io"))

    def test_support_report_route_is_read_only_and_sanitized(self) -> None:
        from am_configurator.transport import DeviceHandle

        def fake_discovery():
            return [
                (
                    DeviceHandle("serial", "/Users/secret/ttyUSB0"),
                    {
                        "product_id": "FUTURE80",
                        "is_keyboard": True,
                        "version": "9.9.9",
                        "pages": 4,
                        "path": "/Users/secret/ttyUSB0",
                        "serial_number": "do-not-leak",
                    },
                )
            ]

        # Minimal stand-in: device_json is used by _device_payload path.
        # Use create_server with discovery that returns handle+info pairs.
        isolated_server, url = create_server(device_discovery=fake_discovery)
        isolated_thread = threading.Thread(
            target=isolated_server.serve_forever,
            daemon=True,
        )
        isolated_thread.start()
        try:
            token = parse_qs(urlparse(url).query)["token"][0]
            request = Request(
                f"http://127.0.0.1:{isolated_server.server_port}/api/devices/support-report",
                headers={"X-AM-Token": token},
            )
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read())
                self.assertEqual(200, response.status)
        finally:
            isolated_server.shutdown()
            isolated_server.server_close()
            isolated_thread.join(timeout=2)

        self.assertEqual("New keyboard model detected", payload["headline"])
        self.assertEqual(1, payload["counts"]["unsupported_keyboards"])
        blob = json.dumps(payload)
        self.assertNotIn("/Users/secret", blob)
        self.assertNotIn("do-not-leak", blob)
        self.assertNotIn("ttyUSB0", blob)
        device = payload["devices"]["unsupported_keyboards"][0]
        self.assertEqual("FUTURE80", device["product_id"])
        self.assertNotIn("address", device)
        self.assertNotIn("path", device)

    def test_non_ascii_auth_header_is_cleanly_rejected(self) -> None:
        for method, body in ((b"GET", b""), (b"POST", b"{}")):
            with self.subTest(method=method.decode("ascii")):
                with socket.create_connection(
                    ("127.0.0.1", self._server.server_port),
                    timeout=5,
                ) as connection:
                    request = (
                        method
                        + b" /api/settings HTTP/1.1\r\n"
                        + b"Host: 127.0.0.1\r\n"
                        + b"X-AM-Token: \xff\r\n"
                        + b"Content-Length: "
                        + str(len(body)).encode("ascii")
                        + b"\r\nConnection: close\r\n\r\n"
                        + body
                    )
                    connection.sendall(request)
                    response = bytearray()
                    while True:
                        chunk = connection.recv(4096)
                        if not chunk:
                            break
                        response.extend(chunk)

                headers, payload = bytes(response).split(b"\r\n\r\n", 1)
                self.assertIn(b" 403 ", headers.splitlines()[0])
                self.assertEqual(
                    {"error": "Unauthorized local request."},
                    json.loads(payload),
                )

    def test_internal_get_post_and_accepted_write_errors_are_redacted(self) -> None:
        private_detail = f"device output at {Path(self._tmp) / 'private.json'}"
        expected = {"error": "The local request failed unexpectedly."}

        with patch(
            "am_configurator.device.list_devices",
            side_effect=OSError(private_detail),
        ):
            status, response = self._request("GET", "/api/devices")
        self.assertEqual(500, status)
        self.assertEqual(expected, response)
        self.assertNotIn(private_detail, json.dumps(response))

        self._server.state.desktop_bridge = SimpleNamespace(
            choose_library_folder=lambda: (_ for _ in ()).throw(
                OSError(private_detail)
            )
        )
        status, response = self._request(
            "POST",
            "/api/native/choose-library",
            {},
        )
        self.assertEqual(500, status)
        self.assertEqual(expected, response)
        self.assertNotIn(private_detail, json.dumps(response))

        with patch(
            "am_configurator.server._Handler._save_settings_preferences",
            side_effect=RuntimeError(private_detail),
        ):
            status, response = self._request(
                "POST",
                "/api/settings/preferences",
                {"loop_mode": "smooth"},
            )
        self.assertEqual(500, status)
        self.assertEqual(expected, response)
        self.assertNotIn(private_detail, json.dumps(response))

        with patch(
            "am_configurator.server._Handler._write_device",
            side_effect=AcceptedWriteError(private_detail),
        ):
            status, response = self._request("POST", "/api/device/write", {})
        self.assertEqual(409, status)
        self.assertEqual(True, response["accepted"])
        self.assertEqual(True, response["retryable"])
        self.assertNotIn(private_detail, json.dumps(response))

    def test_split_settings_routes_update_sections_independently(self) -> None:
        status, data = self._request(
            "POST", "/api/settings/preferences", {"loop_mode": "ping_pong"}
        )
        self.assertEqual(status, 200)
        self.assertNotIn("candidate_count", data["generation"])
        self.assertEqual(data["generation"]["loop_mode"], "ping_pong")

        library = Path(self._tmp) / "generated-library"
        status, data = self._request(
            "POST", "/api/settings/library", {"current_root": str(library)}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["library"]["current_root"], str(library.resolve()))

        status, data = self._request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(data["library"]["current_root"], str(library.resolve()))

    def test_split_settings_routes_are_strict_and_never_echo_secrets(self) -> None:
        secret = "sk-must-not-appear-anywhere"
        invalid_cases = (
            ("/api/settings/preferences", {"models": {"interpreter": "future"}}),
            ("/api/settings/preferences", {"candidate_count": 9}),
            ("/api/settings/preferences", {"loop_mode": "crossfade"}),
            ("/api/settings/preferences", {"unknown": True}),
            ("/api/settings/library", {"current_root": None, "unknown": True}),
        )
        for path, body in invalid_cases:
            with self.subTest(path=path, body=body):
                status, data = self._request("POST", path, body)
                self.assertEqual(status, 400)
                self.assertNotIn(secret, json.dumps(data))
        self.assertFalse(store.settings_path().exists())

    def test_capabilities(self) -> None:
        status, data = self._request("GET", "/api/led/capabilities")
        self.assertEqual(status, 200)

        self.assertEqual(
            data["model_frame_caps"],
            dict(device_mapping.MODEL_FRAME_CAPS),
        )
        self.assertNotIn("models", data)
        self.assertNotIn("providers", data)
        self.assertNotIn("max_rendered_keyframes", data)
        self.assertNotIn("ai_catalog", data)
        self.assertNotIn("privacy_disclosure_version", data)

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

    def test_obsolete_ai_settings_routes_and_raw_key_helper_are_gone(self) -> None:
        for path, body in (
            ("/api/settings/key", {"provider": "xai", "key": "must-not-land"}),
            ("/api/settings/test", {}),
        ):
            with self.subTest(path=path):
                status, response = self._request("POST", path, body)
                self.assertEqual(404, status)
                self.assertNotIn("must-not-land", json.dumps(response))

        self.assertFalse(hasattr(server, "_xai_get"))

    def test_native_folder_actions_dispatch_through_the_desktop_bridge(self) -> None:
        revealed: list[str] = []
        bridge = SimpleNamespace(
            choose_library_folder=lambda: "/tmp/chosen-library",
            reveal_library_path=lambda path: revealed.append(path) is None,
        )
        self._server.state.desktop_bridge = bridge

        status, data = self._request("POST", "/api/native/choose-library", {})
        self.assertEqual(status, 200)
        self.assertEqual(data, {"path": "/tmp/chosen-library"})

        status, data = self._request(
            "POST", "/api/native/reveal-library", {"path": "/tmp/chosen-library"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data, {"revealed": True})
        self.assertEqual(revealed, ["/tmp/chosen-library"])

    def test_native_media_picker_banks_selected_bytes_and_rejects_bad_media(self) -> None:
        from PIL import Image

        image = Image.new("RGBA", (3, 2), (131, 88, 255, 255))
        output = io.BytesIO()
        image.save(output, format="PNG")
        png = output.getvalue()

        self._server.state.desktop_bridge = None
        status, data = self._request("POST", "/api/native/choose-media", {})
        self.assertEqual(404, status)
        self.assertNotIn(str(self._tmp), json.dumps(data))

        self._server.state.desktop_bridge = SimpleNamespace(
            choose_media_file=lambda: None,
        )
        status, data = self._request("POST", "/api/native/choose-media", {})
        self.assertEqual(200, status)
        self.assertEqual({"cancelled": True}, data)

        library_root = Path(self._tmp) / "library"
        store.update_library_root({"current_root": str(library_root)})
        selections = iter((
            {"name": "native.png", "payload": png},
            {"name": "pretends-to-be.gif", "payload": b"not supported media"},
        ))
        self._server.state.desktop_bridge = SimpleNamespace(
            choose_media_file=lambda: next(selections),
        )
        status, imported = self._request("POST", "/api/native/choose-media", {})
        self.assertEqual(201, status)
        self.assertFalse(imported["cancelled"])
        self.assertFalse(imported["deduplicated"])
        self.assertEqual("media_source", imported["item"]["kind"])
        self.assertEqual("image/png", imported["item"]["item"]["source"]["mime_type"])
        self.assertNotIn(str(self._tmp), json.dumps(imported))

        before = self._server.state.library_catalog().saved_items.scan()
        status, _ = self._request("POST", "/api/native/choose-media", {})
        self.assertEqual(400, status)
        after = self._server.state.library_catalog().saved_items.scan()
        self.assertEqual(before["items"], after["items"])

        self._server.state.desktop_bridge = SimpleNamespace(
            choose_media_file=lambda: {"path": "C:/private/file.png"},
        )
        status, data = self._request("POST", "/api/native/choose-media", {})
        self.assertEqual(400, status)
        self.assertNotIn("C:/private", json.dumps(data))

    def test_requires_auth(self) -> None:
        cases = [
            ("GET", "/api/settings", None),
            ("GET", "/api/led/capabilities", None),
            ("GET", "/api/led/generate/status?job=x", None),
            ("POST", "/api/settings/key", {"provider": "xai", "key": "x"}),
            ("POST", "/api/settings/preferences", {"candidate_count": 4}),
            ("POST", "/api/settings/library", {"current_root": None}),
            ("POST", "/api/settings/privacy", {"version": "anything"}),
            ("POST", "/api/native/choose-media", {}),
            ("POST", "/api/settings/test", {}),
            (
                "POST",
                "/api/keymap/assignment",
                {"product_id": "NEON80", "code": "#00070004"},
            ),
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

    def test_legacy_generation_routes_are_retired(self) -> None:
        cases = (
            ("GET", "/api/led/generate/status?job=old", None),
            (
                "POST",
                "/api/led/generate",
                {"prompt": "old", "product_id": "CB04", "targets": ["frames"]},
            ),
            ("POST", "/api/led/generate/cancel", {}),
        )
        for method, path, body in cases:
            with self.subTest(method=method, path=path):
                status, data = self._request(method, path, body)
                self.assertEqual(404, status)

    def test_migration_discard_route_requires_confirmation_and_scrubs_plaintext(
        self,
    ) -> None:
        """`/api/settings/migration/discard-credential` is a confirmed, manual
        retry of a stuck legacy-schema migration. No AI/credential vault
        exists any more, so "no vault modification" is exercised here as:
        the settings directory gains no file besides settings.json and its
        advisory lock, and no plaintext secret from the legacy 'llm' block
        survives the repair."""

        secret = "sk-only-legacy-route-copy"
        library_root = Path(self._tmp) / "legacy-library"
        legacy = {
            "schema_version": 2,
            "llm": {
                "models": {
                    "interpreter": "grok-4.3",
                    "concept": "grok-imagine-image-quality",
                    "video": "grok-imagine-video",
                },
                "keys": {"xai": secret},
            },
            "library": {"current_root": str(library_root), "roots": []},
            "generation": {
                "candidate_count": 4,
                "loop_mode": "ping_pong",
                "privacy_ack_version": "2026-07-20-xai-v1",
                "privacy_ack_at": "2026-07-20T12:00:00+00:00",
            },
        }
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        original = (json.dumps(legacy, indent=2) + "\n").encode("utf-8")
        path.write_bytes(original)

        # Make the automatic migrate-on-read write fail exactly once, so the
        # GET leaves the file stuck at schema v2 with a retryable reason
        # instead of silently upgrading it in place.
        real_write = store._write_settings_file
        calls = {"n": 0}

        def flaky_write(target_path, settings):
            if calls["n"] == 0:
                calls["n"] += 1
                raise OSError(errno.EACCES, "simulated migration write failure")
            return real_write(target_path, settings)

        with patch.object(store, "_write_settings_file", flaky_write):
            status, settings = self._request("GET", "/api/settings")
        self.assertEqual(200, status)
        self.assertEqual(
            {"required": True, "reason": "settings_migration_write_failed"},
            settings["migration"],
        )
        self.assertNotIn(secret, json.dumps(settings))
        self.assertEqual(original, path.read_bytes())

        # Confirmation gate: missing/false confirm, and unknown fields, are
        # both refused without touching the file.
        for body in ({"confirm": False}, {"confirm": True, "extra": True}):
            with self.subTest(body=body):
                status, _response = self._request(
                    "POST", "/api/settings/migration/discard-credential", body
                )
                self.assertEqual(400, status)
                self.assertEqual(original, path.read_bytes())

        status, repaired = self._request(
            "POST",
            "/api/settings/migration/discard-credential",
            {"confirm": True},
        )

        self.assertEqual(200, status)
        self.assertEqual({"required": False, "reason": None}, repaired["migration"])
        self.assertEqual("ping_pong", repaired["generation"]["loop_mode"])
        self.assertEqual(
            str(library_root.resolve()), repaired["library"]["current_root"]
        )
        self.assertNotIn(secret, path.read_text("utf-8"))
        self.assertNotIn(secret, json.dumps(repaired))
        # No vault/credential file exists any more; confirm nothing besides
        # settings.json and its advisory lock was created alongside it.
        self.assertEqual(
            {"settings.json", ".settings.lock"},
            {p.name for p in path.parent.iterdir() if p.is_file()},
        )


class MediaRendererLifecycleTests(unittest.TestCase):
    def test_library_root_change_and_state_close_invalidate_renderer_sessions(
        self,
    ) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            first_root = Path(temporary) / "first"
            second_root = Path(temporary) / "second"
            selected_root = [first_root]

            def settings():
                return {
                    "library": {
                        "current_root": str(selected_root[0]),
                        "roots": [],
                    }
                }

            state = server._State(
                None,
                "test-token",
            )
            second_renderer = None
            try:
                with patch.object(store, "load_settings", side_effect=settings):
                    first_library = state.lighting_library()
                    first_renderer = state.media_renderer()
                    self.assertFalse(first_renderer._closed)
                    source_image = Image.new("RGBA", (2, 1), (40, 80, 120, 255))
                    source_output = io.BytesIO()
                    source_image.save(source_output, format="PNG")
                    source_payload = source_output.getvalue()
                    decoded = media_composition.decode_media(source_payload)
                    source_manifest, _created = SavedItemLibrary(
                        first_root,
                        minimum_free_bytes=1,
                    ).bank_media_source(
                        name="root-bound.png",
                        payload=source_payload,
                        metadata={
                            "mime_type": decoded.mime_type,
                            "width": decoded.width,
                            "height": decoded.height,
                            "frame_count": decoded.frame_count,
                            "duration_ms": decoded.duration_ms,
                        },
                    )
                    source_catalog_id = f"item:{source_manifest['item_id']}"
                    source_session_id = first_renderer.prepare_preview_session(
                        source_catalog_id
                    )["preview_session_id"]

                    selected_root[0] = second_root
                    second_library = state.lighting_library()
                    self.assertIsNot(first_library, second_library)
                    self.assertTrue(first_renderer._closed)
                    self.assertIsNone(state._media_renderer)
                    self.assertIsNone(state._library_catalog)
                    with self.assertRaisesRegex(ValueError, "no longer available"):
                        first_renderer.source_frame_png(
                            source_catalog_id,
                            preview_session_id=source_session_id,
                            source_frame_index=0,
                        )

                    second_renderer = state.media_renderer()
                    self.assertIsNot(first_renderer, second_renderer)
                    self.assertFalse(second_renderer._closed)
            finally:
                state.close()
            self.assertIsNotNone(second_renderer)
            self.assertTrue(second_renderer._closed)


class LightingStudioEndpointTests(unittest.TestCase):
    _DEFAULT = object()

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="am_lighting_endpoint_")
        self._saved_env = {
            key: os.environ.get(key)
            for key in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME")
        }
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = self._tmp
        self.root = Path(self._tmp) / "generated"
        store.update_library_root({"current_root": str(self.root)})
        self.library = GeneratedAssetLibrary(self.root, minimum_free_bytes=1)
        self._server, url = create_server(
            lighting_library=self.library,
        )
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

    def _request(self, method, path, body=None, token=_DEFAULT, timeout=5):
        headers = {}
        selected = self._token if token is self._DEFAULT else token
        if selected is not None:
            headers["X-AM-Token"] = selected
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._base + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, (json.loads(raw) if raw else None)

    def _raw_request(self, path: str, *, headers: dict | None = None, token=_DEFAULT):
        request_headers = dict(headers or {})
        selected = self._token if token is self._DEFAULT else token
        if selected is not None:
            request_headers["X-AM-Token"] = selected
        request = Request(self._base + path, method="GET", headers=request_headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def _media_request(
        self,
        name: str,
        payload: bytes,
        *,
        content_type: str = "application/octet-stream",
        token=_DEFAULT,
        query_suffix: str = "",
    ):
        headers = {"Content-Type": content_type}
        selected = self._token if token is self._DEFAULT else token
        if selected is not None:
            headers["X-AM-Token"] = selected
        path = f"/api/library/import/media?name={quote(name, safe='')}{query_suffix}"
        request = Request(
            self._base + path,
            data=payload,
            method="POST",
            headers=headers,
        )
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                return response.status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw)

    def _socket_status(self, request: bytes) -> int:
        with socket.create_connection(
            ("127.0.0.1", self._server.server_port),
            timeout=5,
        ) as connection:
            connection.sendall(request)
            connection.shutdown(socket.SHUT_WR)
            response = b""
            while True:
                chunk = connection.recv(8192)
                if not chunk:
                    break
                response += chunk
        return int(response.split(b" ", 2)[1])

    def _job(self, *, prompt="library ember", status="awaiting_selection") -> dict:
        manifest = self.library.create_job(
            prompt=prompt,
            target={
                "family": "CB",
                "product_id": "CB_TEST",
                "raster": {"width": 40, "height": 5},
                "targets": ["frames"],
                "frame_cap": 80,
            },
            models={
                "backend": "ollama",
                "provider": "ollama",
                "model_id": "ornith:latest",
            },
        )
        return self.library.update_manifest(
            manifest["job_id"], {"status": status, "phase": status}
        )

    def test_routes_require_authentication(self) -> None:
        paths = (
            ("GET", "/api/lighting/library", None),
            ("GET", "/api/library/items", None),
            ("GET", "/api/library/items/item:00000000-0000-4000-8000-000000000000", None),
            (
                "GET",
                "/api/library/assets/"
                "item:00000000-0000-4000-8000-000000000000/"
                "00000000-0000-4000-8000-000000000000",
                None,
            ),
            (
                "POST",
                "/api/library/items/"
                "item:00000000-0000-4000-8000-000000000000/remove",
                {},
            ),
            (
                "POST",
                "/api/library/items/"
                "item:00000000-0000-4000-8000-000000000000/restore",
                {},
            ),
            (
                "DELETE",
                "/api/library/items/"
                "item:00000000-0000-4000-8000-000000000000",
                None,
            ),
            ("GET", "/api/lighting/assets/00000000-0000-4000-8000-000000000000/00000000-0000-4000-8000-000000000000", None),
            ("POST", "/api/lighting/render", {}),
        )
        for method, path, body in paths:
            with self.subTest(path=path):
                if method == "GET":
                    status, _headers, _raw = self._raw_request(path, token=None)
                else:
                    status, _data = self._request(method, path, body, token=None)
                self.assertEqual(403, status)

    def test_unexpected_lighting_errors_never_expose_local_paths(self) -> None:
        secret_path = self.root / "jobs" / "private-asset.png"
        job_id = "00000000-0000-4000-8000-000000000000"
        asset_id = "00000000-0000-4000-8000-000000000001"
        with patch.object(
            self.library,
            "resolve_asset",
            side_effect=OSError(f"asset changed at {secret_path}"),
        ):
            status, _headers, payload = self._raw_request(
                f"/api/lighting/assets/{job_id}/{asset_id}"
            )
        self.assertEqual(500, status)
        self.assertNotIn(str(self.root).encode(), payload)
        self.assertEqual(
            "The local request failed unexpectedly.",
            json.loads(payload)["error"],
        )

    def test_durable_job_snapshots_and_filterable_pagination_are_pathless(self) -> None:
        first = self._job(prompt="violet ember", status="ready")
        self.library.bank_asset(
            first["job_id"],
            kind="concept",
            data=b"concept",
            mime_type="image/png",
            origin="test",
        )
        self._job(prompt="blue ocean", status="failed")
        self._job(prompt="violet pulse", status="ready")
        status, library_detail = self._request(
            "GET", f"/api/lighting/library/{first['job_id']}"
        )
        self.assertEqual(200, status)
        self.assertEqual(first["job_id"], library_detail["job_id"])
        self.assertNotIn(str(self.root), json.dumps(library_detail))

        status, page = self._request(
            "GET", "/api/lighting/library?page=1&limit=1&status=ready&query=violet"
        )
        self.assertEqual(200, status)
        self.assertEqual(2, page["total"])
        self.assertEqual(1, len(page["jobs"]))
        self.assertTrue(page["has_more"])
        self.assertEqual(1, page["page"])
        status, second_page = self._request(
            "GET", "/api/lighting/library?page=2&limit=1&status=ready&query=violet"
        )
        self.assertEqual(200, status)
        self.assertEqual(1, len(second_page["jobs"]))
        for summary in page["jobs"] + second_page["jobs"]:
            self.assertEqual("ready", summary["status"])
            self.assertIn("violet", summary["prompt"])
            self.assertNotIn("assets", summary)
        status, kind_page = self._request(
            "GET", "/api/lighting/library?kind=concept"
        )
        self.assertEqual(200, status)
        self.assertEqual(1, kind_page["total"])
        self.assertEqual(first["job_id"], kind_page["jobs"][0]["job_id"])
        for query in ("unknown=x", "limit=101", "status=ready&status=failed"):
            with self.subTest(query=query):
                status, _ = self._request("GET", f"/api/lighting/library?{query}")
                self.assertEqual(400, status)

    def test_mixed_library_catalog_lists_details_and_serves_saved_assets(self) -> None:
        saved_library = SavedItemLibrary(self.root, minimum_free_bytes=1)
        saved = saved_library.create_item(
            kind="media_source",
            origin="media_import",
            name="Imported ocean.png",
            tags=("blue", "favorite"),
            source={
                "asset_id": "original",
                "width": 3,
                "height": 2,
                "frame_count": 1,
                "duration_ms": 0,
            },
            assets={
                "original": {
                    "kind": "source",
                    "mime_type": "image/png",
                    "data": b"saved-ocean",
                }
            },
        )
        job = self._job(prompt="violet generated", status="ready")

        status, page = self._request(
            "GET",
            "/api/library/items?kind=media_source&status=ready"
            "&compatibility=unknown&query=favorite",
        )
        self.assertEqual(200, status)
        self.assertEqual(1, page["total"])
        self.assertEqual(
            f"item:{saved['item_id']}",
            page["items"][0]["catalog_id"],
        )
        self.assertNotIn(str(self.root), json.dumps(page))

        status, detail = self._request(
            "GET",
            f"/api/library/items/item:{saved['item_id']}",
        )
        self.assertEqual(200, status)
        self.assertEqual(saved["item_id"], detail["item"]["item_id"])
        self.assertNotIn("relative_path", json.dumps(detail))

        asset = saved["assets"][0]
        status, headers, payload = self._raw_request(
            f"/api/library/assets/item:{saved['item_id']}/{asset['asset_id']}"
        )
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["Content-Type"])
        self.assertEqual(b"saved-ocean", payload)

        status, jobs = self._request(
            "GET",
            "/api/library/items?kind=generation_job&query=violet",
        )
        self.assertEqual(200, status)
        self.assertEqual(
            [f"job:{job['job_id']}"],
            [item["catalog_id"] for item in jobs["items"]],
        )
        status, job_detail = self._request(
            "GET",
            f"/api/library/items/job:{job['job_id']}",
        )
        self.assertEqual(200, status)
        self.assertEqual(job["job_id"], job_detail["job"]["job_id"])
        status, _ = self._request(
            "GET",
            f"/api/library/items/{saved['item_id']}",
        )
        self.assertEqual(400, status)
        for query in (
            "unknown=x",
            "limit=101",
            "status=ready&status=failed",
            "kind=not-a-kind",
            "compatibility=imaginary",
            "removed=maybe",
        ):
            with self.subTest(query=query):
                status, _ = self._request("GET", f"/api/library/items?{query}")
                self.assertEqual(400, status)

    def test_raw_media_import_banks_all_formats_deduplicates_and_renders(self) -> None:
        from PIL import Image

        def still(format_name: str) -> bytes:
            image = Image.new("RGBA", (4, 2))
            image.putdata(
                (
                    (255, 0, 0, 255),
                    (0, 255, 0, 255),
                    (0, 0, 255, 255),
                    (255, 255, 0, 255),
                    (0, 255, 255, 255),
                    (255, 0, 255, 255),
                    (255, 255, 255, 255),
                    (0, 0, 0, 255),
                )
            )
            if format_name == "BMP":
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format=format_name)
            return output.getvalue()

        gif_frames = [
            Image.new("RGB", (4, 2), (255, 0, 0)),
            Image.new("RGB", (4, 2), (0, 0, 255)),
        ]
        gif_output = io.BytesIO()
        gif_frames[0].save(
            gif_output,
            format="GIF",
            save_all=True,
            append_images=gif_frames[1:],
            duration=[30, 70],
            loop=0,
            optimize=False,
        )
        cases = (
            ("still.png", still("PNG"), "image/png", 1, 0),
            ("still.bmp", still("BMP"), "image/bmp", 1, 0),
            ("motion.gif", gif_output.getvalue(), "image/gif", 2, 100),
        )
        imported = {}
        for name, payload, mime_type, frame_count, duration_ms in cases:
            with self.subTest(name=name):
                status, result = self._media_request(
                    name,
                    payload,
                    content_type="text/plain",
                )
                self.assertEqual(201, status)
                self.assertFalse(result["deduplicated"])
                detail = result["item"]
                imported[name] = (payload, detail)
                self.assertEqual("media_source", detail["kind"])
                self.assertEqual(mime_type, detail["item"]["source"]["mime_type"])
                self.assertEqual(frame_count, detail["item"]["source"]["frame_count"])
                self.assertEqual(duration_ms, detail["item"]["source"]["duration_ms"])
                self.assertNotIn(str(self.root), json.dumps(result))

                asset = detail["item"]["assets"][0]
                asset_status, headers, served = self._raw_request(
                    f"/api/library/assets/{detail['catalog_id']}/{asset['asset_id']}"
                )
                self.assertEqual(200, asset_status)
                self.assertEqual(mime_type, headers["Content-Type"])
                self.assertEqual(payload, served)

        png_payload, png_detail = imported["still.png"]
        status, duplicate = self._media_request("renamed.png", png_payload)
        self.assertEqual(200, status)
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(png_detail["catalog_id"], duplicate["item"]["catalog_id"])
        self.assertEqual("still.png", duplicate["item"]["name"])

        transform = {
            "version": 1,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "aspect_locked": True,
            "sampling": "nearest",
            "background": "#000000",
        }
        status, rendered = self._request(
            "POST",
            f"/api/library/items/{png_detail['catalog_id']}/render",
            {
                "product_id": "CB04",
                "targets": ["frames"],
                "transform": transform,
                "epoch": 7,
            },
        )
        self.assertEqual(200, status)
        self.assertEqual(7, rendered["epoch"])
        self.assertEqual(transform, rendered["transform"])
        self.assertEqual([], rendered["resolved_transforms"])
        self.assertEqual(
            1,
            rendered["mapped_result"]["tracks"]["frames"]["frame_count"],
        )

        rejected_pan = {
            **transform,
            "offset_x": 8.0,
            "offset_y": -8.0,
        }
        status, constrained = self._request(
            "POST",
            f"/api/library/items/{png_detail['catalog_id']}/render",
            {
                "product_id": "CB04",
                "targets": ["frames"],
                "transform": rejected_pan,
                "epoch": 8,
            },
        )
        self.assertEqual(200, status)
        self.assertEqual(
            {**rejected_pan, "offset_x": 0.0, "offset_y": -1.5},
            constrained["transform"],
        )
        self.assertEqual([], constrained["resolved_transforms"])

        move_zoom = {
            "version": 1,
            "type": "move_zoom",
            "frame_count": 3,
            "duration_ms": 90,
            "parameters": {
                "start_transform": transform,
                "end_transform": {
                    **transform,
                    "offset_x": 8.0,
                    "offset_y": -8.0,
                    "scale_x": 2.0,
                    "scale_y": 2.0,
                },
            },
        }
        status, animated = self._request(
            "POST",
            f"/api/library/items/{png_detail['catalog_id']}/render",
            {
                "product_id": "CB04",
                "targets": ["frames", "keyframes"],
                "transform": transform,
                "effects": [move_zoom],
                "epoch": 9,
            },
        )
        self.assertEqual(200, status)
        self.assertEqual(
            [
                transform,
                {
                    **transform,
                    "offset_x": 0.25,
                    "offset_y": -5 / 12,
                    "scale_x": 1.5,
                    "scale_y": 1.5,
                },
                {
                    **transform,
                    "offset_x": 0.5,
                    "offset_y": -0.75,
                    "scale_x": 2.0,
                    "scale_y": 2.0,
                },
            ],
            animated["resolved_transforms"],
        )
        self.assertEqual(
            {"frames", "keyframes"},
            set(animated["mapped_result"]["tracks"]),
        )
        item_id = png_detail["item"]["item_id"]
        item_dir = self.root / "items" / item_id
        self.assertEqual([], list((item_dir / ".work").iterdir()))
        stored = SavedItemLibrary(self.root, minimum_free_bytes=1).load_manifest(item_id)
        self.assertEqual(1, len(stored["assets"]))
        self.assertEqual(png_payload, (item_dir / stored["assets"][0]["relative_path"]).read_bytes())

    def test_media_preview_routes_are_strict_authenticated_pathless_and_invalidated(
        self,
    ) -> None:
        from PIL import Image

        image = Image.new("RGBA", (4, 2))
        image.putdata(
            (
                (255, 0, 0, 255),
                (0, 255, 0, 255),
                (0, 0, 255, 255),
                (255, 255, 0, 255),
                (0, 255, 255, 255),
                (255, 0, 255, 255),
                (255, 255, 255, 255),
                (0, 0, 0, 255),
            )
        )
        output = io.BytesIO()
        image.save(output, format="PNG")
        status, imported = self._media_request("preview-source.png", output.getvalue())
        self.assertEqual(201, status)
        catalog_id = imported["item"]["catalog_id"]
        route = f"/api/library/items/{catalog_id}"

        status, _ = self._request(
            "POST",
            f"{route}/preview-session",
            {},
            token=None,
        )
        self.assertEqual(403, status)
        with patch("am_configurator.media_composition.decode_media") as decode:
            status, _ = self._request(
                "POST",
                f"{route}/preview-session",
                {"unexpected": True},
            )
        self.assertEqual(400, status)
        decode.assert_not_called()

        status, session = self._request(
            "POST",
            f"{route}/preview-session",
            {},
        )
        self.assertEqual(201, status)
        session_id = session["preview_session_id"]
        self.assertGreaterEqual(len(session_id), 32)
        self.assertEqual(
            {
                "mime_type": "image/png",
                "width": 4,
                "height": 2,
                "frame_count": 1,
                "display_only": True,
            },
            session["source_preview"],
        )
        self.assertNotIn(str(self.root), json.dumps(session))

        source_path = (
            f"{route}/source-frame?preview_session_id={session_id}"
            "&source_frame_index=0"
        )
        status, _headers, _payload = self._raw_request(source_path, token=None)
        self.assertEqual(403, status)
        status, headers, projection = self._raw_request(source_path)
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["Content-Type"])
        self.assertNotIn(str(self.root).encode(), projection)
        with Image.open(io.BytesIO(projection)) as projected:
            projected.load()
            self.assertEqual((4, 2), projected.size)
            source_pixels = (
                image.get_flattened_data()
                if hasattr(image, "get_flattened_data")
                else image.getdata()
            )
            projected_rgba = projected.convert("RGBA")
            projected_pixels = (
                projected_rgba.get_flattened_data()
                if hasattr(projected_rgba, "get_flattened_data")
                else projected_rgba.getdata()
            )
            self.assertEqual(
                list(source_pixels),
                list(projected_pixels),
            )
        status, _headers, _payload = self._raw_request(
            source_path,
            headers={"Range": "bytes=0-1"},
        )
        self.assertEqual(416, status)
        for query in (
            "",
            f"preview_session_id={session_id}",
            f"preview_session_id={session_id}&source_frame_index=0&extra=x",
            f"preview_session_id={session_id}&preview_session_id={session_id}&source_frame_index=0",
            f"preview_session_id={session_id}&source_frame_index=-1",
            "preview_session_id=short&source_frame_index=0",
        ):
            with self.subTest(query=query):
                status, _headers, _payload = self._raw_request(
                    f"{route}/source-frame?{query}"
                )
                self.assertEqual(400, status)

        transform = {
            "version": 1,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "aspect_locked": True,
            "sampling": "nearest",
            "background": "#000000",
        }
        render_body = {
            "preview_session_id": session_id,
            "product_id": "CB04",
            "targets": ["frames", "keyframes"],
            "transform": transform,
            "effects": [],
            "epoch": 1,
        }
        status, full = self._request("POST", f"{route}/render", render_body)
        self.assertEqual(200, status)
        status, selected = self._request(
            "POST",
            f"{route}/render-frame",
            {**render_body, "frame_index": 0, "epoch": 2},
        )
        self.assertEqual(200, status)
        for target in render_body["targets"]:
            self.assertEqual(
                full["mapped_result"]["tracks"][target]["frames"][0],
                selected["mapped_frame"]["tracks"][target]["colors"],
            )
        self.assertNotIn(str(self.root), json.dumps(selected))

        malformed = (
            {**render_body, "frame_index": 0, "epoch": 3, "unexpected": True},
            {
                key: value
                for key, value in {**render_body, "frame_index": 0, "epoch": 3}.items()
                if key != "effects"
            },
            {**render_body, "frame_index": True, "epoch": 3},
            {**render_body, "frame_index": 1, "epoch": 3},
            {**render_body, "frame_index": 512, "epoch": 3},
            {**render_body, "frame_index": 0, "epoch": 3, "preview_session_id": "short"},
            {**render_body, "frame_index": 0, "epoch": 3, "product_id": ""},
            {**render_body, "frame_index": 0, "epoch": 3, "targets": []},
            {
                **render_body,
                "frame_index": 0,
                "epoch": 3,
                "transform": {**transform, "unknown": True},
            },
            {
                **render_body,
                "frame_index": 0,
                "epoch": 3,
                "effects": [{}] * 9,
            },
        )
        for body in malformed:
            with self.subTest(body_keys=sorted(body)):
                status, _ = self._request("POST", f"{route}/render-frame", body)
                self.assertEqual(400, status)

        status, _ = self._request("POST", f"{route}/remove", {})
        self.assertEqual(200, status)
        status, _ = self._request("POST", f"{route}/restore", {})
        self.assertEqual(200, status)
        status, _headers, _payload = self._raw_request(source_path)
        self.assertEqual(400, status)

    def test_save_lighting_banks_validated_slot_result_and_source_provenance(
        self,
    ) -> None:
        from PIL import Image

        profile = _base_config("80")
        profile["page_data"] = [_page(index) for index in range(8)]
        profile["page_num"] = 8
        profile["page_data"][5]["keyframes"] = {
            "valid": 1,
            "frame_num": 2,
            "frame_data": [
                {
                    "frame_index": 0,
                    "frame_RGB": ["#112233"] * 90,
                },
                {
                    "frame_index": 1,
                    "frame_RGB": ["#445566"] * 90,
                },
            ],
        }
        profile["page_data"][5]["spotlight_frames"] = {
            "valid": 1,
            "frame_num": 2,
            "frame_data": [
                {
                    "frame_index": 0,
                    "frame_RGB": ["#778899"] * 24,
                },
                {
                    "frame_index": 1,
                    "frame_RGB": ["#AABBCC"] * 24,
                },
            ],
        }
        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": profile},
        )
        self.assertEqual(200, status)
        revision = synchronized["revision"]
        before = copy.deepcopy(self._server.state.config)

        output = io.BytesIO()
        Image.new("RGB", (4, 2), (20, 40, 80)).save(output, format="PNG")
        status, imported = self._media_request("banked-source.png", output.getvalue())
        self.assertEqual(201, status)
        source_catalog_id = imported["item"]["catalog_id"]
        transform = {
            "version": 1,
            "offset_x": 0.25,
            "offset_y": -0.1,
            "scale_x": 1.5,
            "scale_y": 1.5,
            "aspect_locked": True,
            "sampling": "box",
            "background": "#000000",
        }
        effect = {
            "version": 1,
            "type": "pulse",
            "frame_count": 2,
            "duration_ms": 90,
            "parameters": {"minimum_brightness": 0.2},
        }
        status, saved = self._request(
            "POST",
            "/api/library/save/lighting",
            {
                "name": "Current Relic lighting",
                "document_revision": revision,
                "slot": 5,
                "target": "keyframes",
                "source_catalog_id": source_catalog_id,
                "transform": transform,
                "effects": [effect],
            },
        )
        self.assertEqual(201, status)
        self.assertEqual("lighting_composition", saved["kind"])
        composition = saved["item"]["composition"]
        self.assertEqual(source_catalog_id, composition["source_catalog_id"])
        self.assertEqual(transform, composition["transform"])
        self.assertEqual([effect], composition["effects"])
        self.assertEqual(5, composition["destination"]["slot"])
        self.assertEqual("keyframes", composition["destination"]["target"])
        self.assertEqual(
            {"keyframes", "spotlight_frames"},
            set(composition["tracks"]),
        )
        result_id = composition["rendered_asset_id"]
        status, headers, payload = self._raw_request(
            f"/api/library/assets/{saved['catalog_id']}/{result_id}"
        )
        self.assertEqual(200, status)
        self.assertEqual("application/json", headers["Content-Type"])
        mapped = json.loads(payload)
        self.assertEqual(2, mapped["tracks"]["keyframes"]["frame_count"])
        self.assertEqual(
            ["#112233"] * 90,
            mapped["tracks"]["keyframes"]["frames"][0],
        )
        preview_id = composition["preview_asset_id"]
        status, headers, preview = self._raw_request(
            f"/api/library/assets/{saved['catalog_id']}/{preview_id}"
        )
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["Content-Type"])
        self.assertTrue(preview.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(before, self._server.state.config)
        self.assertEqual(revision, self._server.state.document_revision)

        status, stale = self._request(
            "POST",
            "/api/library/save/lighting",
            {
                "name": "Stale",
                "document_revision": "x" * 32,
                "slot": 5,
                "target": "keyframes",
                "source_catalog_id": None,
                "transform": None,
                "effects": [],
            },
        )
        self.assertEqual(409, status)
        self.assertEqual("document_stale", stale["code"])

    def test_save_lighting_excludes_independent_tracks_on_another_timeline(
        self,
    ) -> None:
        profile = _base_config("CB04")
        profile["page_data"] = [_page(index) for index in range(8)]
        profile["page_num"] = 8
        profile["page_data"][5]["keyframes"] = {
            "valid": 1,
            "frame_num": 2,
            "frame_data": [
                {
                    "frame_index": index,
                    "frame_RGB": [f"#{index + 1:06X}"] * 90,
                }
                for index in range(2)
            ],
        }
        profile["page_data"][5]["frames"] = {
            "valid": 1,
            "frame_num": 6,
            "frame_data": [
                {
                    "frame_index": index,
                    "frame_RGB": [f"#{index + 3:06X}"] * 200,
                }
                for index in range(6)
            ],
        }
        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": profile},
        )
        self.assertEqual(200, status)

        status, saved = self._request(
            "POST",
            "/api/library/save/lighting",
            {
                "name": "Current CyberBoard display",
                "document_revision": synchronized["revision"],
                "slot": 5,
                "target": "frames",
                "source_catalog_id": None,
                "transform": None,
                "effects": [],
            },
        )

        self.assertEqual(201, status)
        composition = saved["item"]["composition"]
        self.assertEqual({"frames"}, set(composition["tracks"]))
        result_id = composition["rendered_asset_id"]
        status, headers, payload = self._raw_request(
            f"/api/library/assets/{saved['catalog_id']}/{result_id}"
        )
        self.assertEqual(200, status)
        self.assertEqual("application/json", headers["Content-Type"])
        mapped = json.loads(payload)
        self.assertEqual({"frames"}, set(mapped["tracks"]))
        self.assertEqual(6, mapped["tracks"]["frames"]["frame_count"])

    def test_media_upload_envelope_and_decode_failures_publish_nothing(self) -> None:
        from PIL import Image

        image = Image.new("RGBA", (2, 1), (255, 0, 0, 255))
        png_output = io.BytesIO()
        image.save(png_output, format="PNG")
        png = png_output.getvalue()

        status, _ = self._media_request("unauthorized.png", png, token=None)
        self.assertEqual(403, status)
        for name, suffix in (
            ("bad.png", "&unknown=x"),
            ("bad.png", "&name=again.png"),
            ("../escape.png", ""),
        ):
            with self.subTest(name=name, suffix=suffix):
                status, _ = self._media_request(name, png, query_suffix=suffix)
                self.assertEqual(400, status)

        token = self._token.encode("ascii")
        prefix = (
            b"POST /api/library/import/media?name=raw.png HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            + b"X-AM-Token: "
            + token
            + b"\r\nConnection: close\r\n"
        )
        self.assertEqual(400, self._socket_status(prefix + b"\r\n"))
        self.assertEqual(
            400,
            self._socket_status(
                prefix
                + b"Transfer-Encoding: chunked\r\n"
                + b"Content-Length: 0\r\n\r\n0\r\n\r\n"
            ),
        )
        self.assertEqual(
            400,
            self._socket_status(
                prefix
                + f"Content-Length: {media_composition.MAX_MEDIA_BYTES + 1}\r\n\r\n".encode(
                    "ascii"
                )
            ),
        )

        second = Image.new("RGBA", (2, 1), (0, 0, 255, 255))
        apng_output = io.BytesIO()
        image.save(
            apng_output,
            format="PNG",
            save_all=True,
            append_images=[second],
            duration=[40, 60],
            loop=0,
        )
        for name, payload in (
            ("animated.png", apng_output.getvalue()),
            ("truncated.png", png[:-1]),
            ("trailing.png", png + b"trailing"),
        ):
            with self.subTest(name=name):
                status, _ = self._media_request(name, payload)
                self.assertEqual(400, status)

        saved = SavedItemLibrary(self.root, minimum_free_bytes=1).scan()
        self.assertEqual([], saved["items"])

    def test_json_import_endpoint_is_read_only_and_classifies_without_the_filename(
        self,
    ) -> None:
        lighting = _am_master_neon_lighting(frame_count=2)
        encoded = base64.b64encode(
            json.dumps(lighting, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        responses = []
        for name in ("looks-like-a-profile.json", "renamed-without-a-json-suffix"):
            status, response = self._request(
                "POST",
                "/api/config/import",
                {"name": name, "data": encoded},
            )
            self.assertEqual(200, status)
            self.assertEqual("am_master_am80_lighting", response["source_format"])
            self.assertEqual("lighting", response["kind"])
            self.assertEqual("NEON80", response["lighting"]["destination"]["product_id"])
            self.assertEqual(2, response["lighting"]["mapped_result"]["source_frames"])
            responses.append(response)
        first = copy.deepcopy(responses[0])
        second = copy.deepcopy(responses[1])
        first.pop("name")
        second.pop("name")
        self.assertEqual(first, second)
        self.assertIsNone(self._server.state.config)

        status, catalog = self._request("GET", "/api/library/items")
        self.assertEqual(200, status)
        self.assertEqual(0, catalog["total"])
        for path, body, token in (
            (
                "/api/config/import?unexpected=true",
                {"name": "lighting.json", "data": encoded},
                self._DEFAULT,
            ),
            (
                "/api/config/import",
                {"name": "lighting.json", "data": encoded, "extra": True},
                self._DEFAULT,
            ),
            (
                "/api/config/import",
                {"name": "lighting.json", "data": encoded},
                None,
            ),
        ):
            with self.subTest(path=path, fields=sorted(body), authorized=token is not None):
                status, _response = self._request("POST", path, body, token=token)
                self.assertEqual(403 if token is None else 400, status)

    def test_lighting_import_exposes_only_validated_remembered_layout_evidence(
        self,
    ) -> None:
        layout = _synthetic_neon_key_layout()
        evidence = profile_metadata.build_dynamic_layout("NEON80", layout)
        profile_metadata.remember_dynamic_evidence(evidence)
        lighting = _am_master_neon_lighting(frame_count=1)
        status, response = self._request(
            "POST",
            "/api/config/import",
            {
                "name": "Offline lighting.json",
                "data": base64.b64encode(json.dumps(lighting).encode("utf-8")).decode(
                    "ascii"
                ),
            },
        )
        self.assertEqual(200, status)
        self.assertEqual("remembered", response["layout_evidence"]["source"])
        self.assertEqual(
            evidence["key_layout"],
            response["layout_evidence"]["key_layout"],
        )
        self.assertEqual(
            evidence["keymap_signature"],
            response["layout_evidence"]["keymap_signature"],
        )
        self.assertIsNone(response["layout_warning"])
        self.assertIsNone(self._server.state.config)

    def test_library_import_banks_am_master_lighting_as_an_offline_composition(
        self,
    ) -> None:
        lighting = _am_master_neon_lighting(
            frame_count=2,
            brightness=255,
            description="Synthetic offline lighting",
        )
        encoded = base64.b64encode(json.dumps(lighting).encode("utf-8")).decode("ascii")
        status, imported = self._request(
            "POST",
            "/api/library/import/profile",
            {"name": "Offline Neon lighting.json", "data": encoded},
        )
        self.assertEqual(201, status)
        self.assertEqual("lighting_composition", imported["kind"])
        self.assertEqual("json_import", imported["item"]["origin"])
        self.assertEqual("am_master_am80_lighting", imported["source_format"])
        self.assertEqual("NEON", imported["item"]["device"]["family"])
        composition = imported["item"]["composition"]
        self.assertIsNone(composition["destination"]["slot"])
        self.assertEqual(100, composition["destination"]["lightness"])
        self.assertEqual(
            "Synthetic offline lighting",
            composition["destination"]["description"],
        )
        self.assertEqual({"head", "axial"}, set(composition["tracks"]))
        rendered_id = composition["rendered_asset_id"]
        status, headers, payload = self._raw_request(
            f"/api/library/assets/{imported['catalog_id']}/{rendered_id}"
        )
        self.assertEqual(200, status)
        self.assertEqual("application/json", headers["Content-Type"])
        mapped = json.loads(payload)
        self.assertEqual(2, mapped["tracks"]["head"]["frame_count"])
        self.assertEqual(2, mapped["tracks"]["axial"]["frame_count"])
        self.assertIsNone(self._server.state.config)

    def test_am_master_profile_is_normalized_before_library_banking(self) -> None:
        profile = _base_config("ALICE")
        page = _page(0)
        page["//"] = "synthetic built-in page"
        page["frames"] = {
            "valid": False,
            "frame_num": 0,
            "frame_data": [{"frame_index": "0", "frame_RGB": ["bad"]}],
        }
        profile["page_data"] = [page]
        profile["page_num"] = 1
        encoded = base64.b64encode(json.dumps(profile).encode("utf-8")).decode("ascii")
        status, imported = self._request(
            "POST",
            "/api/library/import/profile",
            {"name": "Synthetic AFA export.json", "data": encoded},
        )
        self.assertEqual(201, status)
        self.assertEqual("keyboard_profile", imported["kind"])
        self.assertEqual("am_master_profile", imported["source_format"])
        asset_id = imported["item"]["profile"]["asset_id"]
        status, _headers, payload = self._raw_request(
            f"/api/library/assets/{imported['catalog_id']}/{asset_id}"
        )
        self.assertEqual(200, status)
        normalized = json.loads(payload)
        self.assertNotIn("//", normalized["page_data"][0])
        self.assertEqual([], normalized["page_data"][0]["frames"]["frame_data"])
        self.assertTrue(validate_config(normalized)["ok"])
        self.assertIsNone(self._server.state.config)

    def test_profile_import_and_mapping_save_bank_exact_data_without_side_effects(
        self,
    ) -> None:
        profile = _base_config("80")
        profile["macro_key"] = [
            {
                "original_key": "#00951500",
                "layer_key": ["#11070004", "#10070004"],
                "intvel_ms": [25, 0],
            }
        ]
        profile["page_data"] = [_page(index) for index in range(8)]
        profile["page_num"] = len(profile["page_data"])
        profile["page_data"][5]["keyframes"] = {
            "valid": 1,
            "frame_num": 1,
            "frame_data": [
                {"frame_index": 0, "frame_RGB": ["#112233"] * 90}
            ],
        }
        original = (
            json.dumps(profile, ensure_ascii=False, indent=3).encode("utf-8")
            + b"\n"
        )
        device_dir = store.device_dir("80", create=True)
        current_sentinel = device_dir / "current.json"
        history_sentinel = device_dir / "history" / "keep.json"
        history_sentinel.parent.mkdir(parents=True)
        current_sentinel.write_bytes(b"current stays")
        history_sentinel.write_bytes(b"history stays")

        self.assertIsNone(self._server.state.config)
        invalid_data = base64.b64encode(b"{}").decode("ascii")
        for path, body in (
            (
                "/api/library/import/profile",
                {"name": "Invalid.json", "data": invalid_data},
            ),
            (
                "/api/library/import/profile?unexpected=true",
                {"name": "Invalid.json", "data": invalid_data},
            ),
            (
                "/api/library/import/profile",
                {
                    "name": "Invalid.json",
                    "data": invalid_data,
                    "extra": True,
                },
            ),
        ):
            with self.subTest(path=path, fields=sorted(body)):
                status, _ = self._request("POST", path, body)
                self.assertEqual(400, status)
        status, empty = self._request(
            "GET",
            "/api/library/items?kind=keyboard_profile",
        )
        self.assertEqual(200, status)
        self.assertEqual(0, empty["total"])

        status, imported = self._request(
            "POST",
            "/api/library/import/profile",
            {
                "name": "Original Relic mapping.json",
                "data": base64.b64encode(original).decode("ascii"),
            },
        )
        self.assertEqual(201, status)
        self.assertEqual("keyboard_profile", imported["kind"])
        self.assertEqual("json_import", imported["item"]["origin"])
        self.assertEqual(
            ["identity", "keymap", "macros", "lighting"],
            imported["item"]["profile"]["sections"],
        )
        self.assertRegex(
            imported["item"]["device"]["keymap_signature"],
            r"^keymap:v1:[0-9a-f]{64}$",
        )
        imported_asset = imported["item"]["profile"]["asset_id"]
        status, headers, payload = self._raw_request(
            f"/api/library/assets/{imported['catalog_id']}/{imported_asset}"
        )
        self.assertEqual(200, status)
        self.assertEqual("application/json", headers["Content-Type"])
        self.assertEqual(original, payload)
        self.assertIsNone(self._server.state.config)

        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": profile},
        )
        self.assertEqual(200, status)
        revision = synchronized["revision"]
        before_document = copy.deepcopy(self._server.state.config)
        status, saved = self._request(
            "POST",
            "/api/library/save/profile",
            {
                "name": "Current Relic mapping",
                "document_revision": revision,
            },
        )
        self.assertEqual(201, status)
        self.assertEqual("verified_export", saved["item"]["origin"])
        self.assertEqual(revision, self._server.state.document_revision)
        self.assertEqual(before_document, self._server.state.config)
        saved_asset = saved["item"]["profile"]["asset_id"]
        status, _headers, saved_payload = self._raw_request(
            f"/api/library/assets/{saved['catalog_id']}/{saved_asset}"
        )
        self.assertEqual(200, status)
        self.assertEqual(profile, json.loads(saved_payload))
        self.assertEqual(b"current stays", current_sentinel.read_bytes())
        self.assertEqual(b"history stays", history_sentinel.read_bytes())

    def test_saved_neon_library_profile_keeps_its_exact_layout_portable(self) -> None:
        profile = blank_config(
            "NEON80",
            [["#00000000"] * 90 for _ in range(4)],
            [],
        )
        layout = LedGenerateEndpointTests._dynamic_layout()
        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": profile},
        )
        self.assertEqual(200, status)

        status, saved = self._request(
            "POST",
            "/api/library/save/profile",
            {
                "name": "Portable Neon profile",
                "document_revision": synchronized["revision"],
                "key_layout": layout,
            },
        )
        self.assertEqual(201, status)
        asset_id = saved["item"]["profile"]["asset_id"]
        status, _headers, payload = self._raw_request(
            f"/api/library/assets/{saved['catalog_id']}/{asset_id}"
        )
        self.assertEqual(200, status)
        banked = json.loads(payload)
        metadata = banked["_am_configurator"]["dynamic_layout"]
        self.assertEqual(layout, metadata["key_layout"])
        self.assertEqual(
            saved["item"]["device"]["keymap_signature"],
            metadata["keymap_signature"],
        )
        self.assertNotIn("_am_configurator", self._server.state.config)

    def test_library_save_rejects_connected_layout_conflicting_with_embedded(self) -> None:
        layout = LedGenerateEndpointTests._dynamic_layout()
        evidence = profile_metadata.build_dynamic_layout("NEON80", layout)
        profile = profile_metadata.attach_dynamic_layout(
            blank_config(
                "NEON80",
                [["#00000000"] * 90 for _ in range(4)],
                [],
            ),
            evidence,
        )
        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": profile},
        )
        self.assertEqual(200, status)
        before_items = self._server.state.library_catalog().saved_items.scan()
        before_evidence = store.load_layout_evidence("NEON80")
        before_document = copy.deepcopy(self._server.state.config)

        status, rejected = self._request(
            "POST",
            "/api/library/save/profile",
            {
                "name": "Conflicting portable Neon profile",
                "document_revision": synchronized["revision"],
                "key_layout": LedGenerateEndpointTests._dynamic_layout(
                    first_width=7.0,
                ),
            },
        )

        self.assertEqual(400, status)
        self.assertEqual(
            "The connected keyboard layout does not match the exact layout "
            "embedded in this profile.",
            rejected["error"],
        )
        after_items = self._server.state.library_catalog().saved_items.scan()
        self.assertEqual(before_items["items"], after_items["items"])
        self.assertEqual(before_evidence, store.load_layout_evidence("NEON80"))
        self.assertEqual(before_document, self._server.state.config)

    def test_profile_compatibility_preview_is_sectioned_and_read_only(self) -> None:
        source = _base_config("80")
        source["macro_key"] = [
            {
                "original_key": "#00951500",
                "layer_key": ["#11070004", "#10070004"],
                "intvel_ms": [25, 0],
            }
        ]
        source["page_data"] = [_page(index) for index in range(8)]
        source["page_num"] = len(source["page_data"])
        source["page_data"][5]["keyframes"] = {
            "valid": 1,
            "frame_num": 1,
            "frame_data": [
                {"frame_index": 0, "frame_RGB": ["#112233"] * 90}
            ],
        }
        source_bytes = json.dumps(source, separators=(",", ":")).encode("utf-8")
        status, imported = self._request(
            "POST",
            "/api/library/import/profile",
            {
                "name": "Portable Relic.json",
                "data": base64.b64encode(source_bytes).decode("ascii"),
            },
        )
        self.assertEqual(201, status)

        destination = _base_config("AM21")
        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": destination},
        )
        self.assertEqual(200, status)
        revision = synchronized["revision"]
        before = copy.deepcopy(self._server.state.config)
        status, exact = self._request(
            "POST",
            f"/api/library/items/{imported['catalog_id']}/compatibility",
            {"document_revision": revision},
        )
        self.assertEqual(200, status)
        self.assertEqual("exact", exact["sections"]["keymap"]["status"])
        self.assertEqual("portable", exact["sections"]["macros"]["status"])
        self.assertEqual("exact", exact["sections"]["lighting"]["status"])
        self.assertEqual("portable", exact["summary"])
        self.assertEqual(before, self._server.state.config)
        self.assertEqual(revision, self._server.state.document_revision)

        incompatible = _base_config("ALICE")
        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": incompatible},
        )
        self.assertEqual(200, status)
        incompatible_revision = synchronized["revision"]
        status, partial = self._request(
            "POST",
            f"/api/library/items/{imported['catalog_id']}/compatibility",
            {"document_revision": incompatible_revision},
        )
        self.assertEqual(200, status)
        self.assertEqual("blocked", partial["sections"]["keymap"]["status"])
        self.assertEqual("portable", partial["sections"]["macros"]["status"])
        self.assertEqual("blocked", partial["sections"]["lighting"]["status"])
        self.assertEqual("partial", partial["summary"])
        self.assertEqual(incompatible, self._server.state.config)

    def test_profile_apply_projects_selected_sections_without_mutating_server_document(
        self,
    ) -> None:
        source = _base_config("80")
        source["key_layer"]["layer_data"][0]["layer"][0] = "#00070005"
        source["macro_key"] = [
            {
                "original_key": "#00951500",
                "layer_key": ["#11070004", "#10070004"],
                "intvel_ms": [25, 0],
            }
        ]
        source["page_data"] = [_page(index) for index in range(8)]
        source["page_num"] = len(source["page_data"])
        source_bytes = json.dumps(source, separators=(",", ":")).encode("utf-8")
        status, imported = self._request(
            "POST",
            "/api/library/import/profile",
            {
                "name": "Selective profile.json",
                "data": base64.b64encode(source_bytes).decode("ascii"),
            },
        )
        self.assertEqual(201, status)

        destination = _base_config("AM21")
        destination["product_info"]["destination_identity"] = "keep"
        destination["page_data"] = [_page(5)]
        destination["page_num"] = 1
        original_destination = copy.deepcopy(destination)
        status, synchronized = self._request(
            "POST",
            "/api/document/sync",
            {"config": destination},
        )
        self.assertEqual(200, status)
        revision = synchronized["revision"]

        status, applied = self._request(
            "POST",
            f"/api/library/items/{imported['catalog_id']}/apply",
            {
                "document_revision": revision,
                "sections": ["keymap", "macros"],
            },
        )

        self.assertEqual(200, status)
        self.assertEqual(["keymap", "macros"], applied["applied_sections"])
        self.assertTrue(applied["identity_preserved"])
        self.assertEqual(
            original_destination["product_info"],
            applied["config"]["product_info"],
        )
        self.assertEqual(
            original_destination["page_data"],
            applied["config"]["page_data"],
        )
        self.assertEqual(
            "#00070005",
            applied["config"]["key_layer"]["layer_data"][0]["layer"][0],
        )
        self.assertEqual(source["macro_key"], applied["config"]["macro_key"])
        self.assertEqual(original_destination, self._server.state.config)
        self.assertEqual(revision, self._server.state.document_revision)

        status, _ = self._request(
            "POST",
            f"/api/library/items/{imported['catalog_id']}/apply",
            {
                "document_revision": revision,
                "sections": ["keymap"],
                "unexpected": True,
            },
        )
        self.assertEqual(400, status)

        newer = copy.deepcopy(destination)
        newer["key_layer"]["layer_data"][0]["layer"][1] = "#00070006"
        status, _ = self._request(
            "POST",
            "/api/document/sync",
            {"config": newer},
        )
        self.assertEqual(200, status)
        status, stale = self._request(
            "POST",
            f"/api/library/items/{imported['catalog_id']}/apply",
            {
                "document_revision": revision,
                "sections": ["keymap"],
            },
        )
        self.assertEqual(409, status)
        self.assertEqual("document_stale", stale["code"])

    def test_library_remove_restore_and_delete_routes_are_exact_and_active_safe(
        self,
    ) -> None:
        saved_library = SavedItemLibrary(self.root, minimum_free_bytes=1)
        saved = saved_library.create_item(
            kind="media_source",
            origin="media_import",
            name="Disposable.png",
            source={
                "asset_id": "original",
                "width": 1,
                "height": 1,
                "frame_count": 1,
                "duration_ms": 0,
            },
            assets={
                "original": {
                    "kind": "source",
                    "mime_type": "image/png",
                    "data": b"disposable",
                }
            },
        )
        catalog_id = f"item:{saved['item_id']}"
        route = f"/api/library/items/{catalog_id}"
        device_history_sentinel = Path(self._tmp) / "device-history.json"
        device_history_sentinel.write_bytes(b"unchanged")

        status, _ = self._request("POST", f"{route}/remove", {"extra": True})
        self.assertEqual(400, status)
        status, removed = self._request("POST", f"{route}/remove", {})
        self.assertEqual(200, status)
        self.assertTrue(removed["removed"])
        self.assertNotIn(str(self.root), json.dumps(removed))
        status, removed_page = self._request(
            "GET",
            "/api/library/items?removed=true",
        )
        self.assertEqual(200, status)
        self.assertEqual([catalog_id], [item["catalog_id"] for item in removed_page["items"]])
        status, live_page = self._request(
            "GET",
            "/api/library/items?removed=false",
        )
        self.assertEqual(200, status)
        self.assertNotIn(
            catalog_id,
            [item["catalog_id"] for item in live_page["items"]],
        )

        status, restored = self._request("POST", f"{route}/restore", {})
        self.assertEqual(200, status)
        self.assertFalse(restored["removed"])
        self.assertNotIn(str(self.root), json.dumps(restored))
        status, _ = self._request("DELETE", route)
        self.assertEqual(409, status)

        status, _ = self._request("POST", f"{route}/remove", {})
        self.assertEqual(200, status)
        status, _ = self._request("DELETE", f"{route}?force=true")
        self.assertEqual(400, status)
        status, _ = self._request("DELETE", route, {"force": True})
        self.assertEqual(400, status)
        status, deleted = self._request("DELETE", route)
        self.assertEqual(200, status)
        self.assertEqual({"catalog_id": catalog_id, "deleted": True}, deleted)
        self.assertEqual(b"unchanged", device_history_sentinel.read_bytes())
        status, _ = self._request("GET", route)
        self.assertEqual(404, status)

    def test_asset_streaming_enforces_ownership_mime_and_rejects_ranges(self) -> None:
        job = self._job()
        other = self._job(prompt="other")
        image = self.library.bank_asset(
            job["job_id"],
            kind="concept",
            data=b"fake-png-bytes",
            mime_type="image/png",
            origin="test",
        )
        status, headers, payload = self._raw_request(
            f"/api/lighting/assets/{job['job_id']}/{image['asset_id']}"
        )
        self.assertEqual(200, status)
        self.assertEqual("image/png", headers["Content-Type"])
        self.assertEqual(b"fake-png-bytes", payload)
        status, _headers, _payload = self._raw_request(
            f"/api/lighting/assets/{job['job_id']}/{image['asset_id']}",
            headers={"Range": "bytes=0-1"},
        )
        self.assertEqual(416, status)
        status, _headers, _payload = self._raw_request(
            f"/api/lighting/assets/{other['job_id']}/{image['asset_id']}"
        )
        self.assertEqual(404, status)
        status, _headers, _payload = self._raw_request(
            "/api/lighting/assets/not-a-job/not-an-asset"
        )
        self.assertEqual(400, status)

        owned_image = self.library.resolve_asset(job["job_id"], image["asset_id"])
        external = Path(self._tmp) / "external.png"
        external.write_bytes(b"outside")
        owned_image.path.unlink()
        owned_image.path.symlink_to(external)
        status, _headers, _payload = self._raw_request(
            f"/api/lighting/assets/{job['job_id']}/{image['asset_id']}"
        )
        self.assertEqual(404, status)

    _EFFECT_LAYER = {
        "kind": "comet",
        "color_index": 0,
        "secondary_color_index": 1,
        "speed": 1,
        "phase": 0.12,
        "direction_degrees": 25.0,
        "center_x": 0.1,
        "center_y": 0.32,
        "scale": 0.55,
        "width": 0.8,
        "trail": 0.48,
        "count": 3,
        "intensity": 1.0,
        "seed": 17,
    }

    def _effect_recipe(self, density: str = "sparse", **changes) -> dict:
        layer = dict(self._EFFECT_LAYER)
        layer.update(changes)
        # Untidy on purpose: the route must bank the validator's normalized
        # recipe, not whatever the caller sent.
        return {
            "schema_version": 1,
            "name": "  Endpoint ember  ",
            "density": density,
            "background": "#000000",
            "palette": ["#ffffff", "#3a8dff"],
            "layers": [layer],
        }

    def _render_effect(self, recipe=None, *, product_id="CB04", targets=("keyframes",)):
        return self._request(
            "POST",
            "/api/lighting/render",
            {
                "recipe": self._effect_recipe() if recipe is None else recipe,
                "product_id": product_id,
                "targets": list(targets),
            },
            timeout=60,
        )

    def _banked_asset(self, catalog_id: str, asset_id: str) -> bytes:
        status, _headers, payload = self._raw_request(
            f"/api/library/assets/{catalog_id}/{asset_id}"
        )
        self.assertEqual(200, status)
        return payload

    def test_effect_render_banks_one_openable_procedural_result(self) -> None:
        status, detail = self._render_effect()
        self.assertEqual(201, status)
        self.assertEqual("job", detail["namespace"])
        self.assertEqual("generation_job", detail["kind"])
        self.assertEqual("Endpoint ember", detail["name"])
        self.assertEqual("ready", detail["status"])

        job = detail["job"]
        # app.js opens a Library entry on the board through
        # applyLibraryPreview -> acceptedBoardFrameSetForApply({provenance:
        # "procedural_result"}), which needs exactly this shape: a procedural
        # pipeline, a completed attempt owning a mapped result, and a target
        # whose family and first track match the open keyboard.
        self.assertEqual("procedural", job["pipeline"])
        self.assertEqual(
            {
                "family": "CB",
                "product_id": device_descriptor("CB04")["product_id"],
                "product_label": device_descriptor("CB04")["product_label"],
                "raster": {"width": 15, "height": 6},
                "targets": ["keyframes"],
                "frame_cap": 80,
            },
            job["target"],
        )
        self.assertEqual(1, len(job["procedural_attempts"]))
        attempt = job["procedural_attempts"][0]
        self.assertEqual("complete", attempt["status"])
        self.assertEqual("ready_for_review", attempt["phase"])
        self.assertIsNone(attempt["error_code"])
        self.assertEqual(
            {"width": 15, "height": 6, "frame_count": 80, "density": "sparse"},
            {key: attempt["quality"][key] for key in ("width", "height", "frame_count", "density")},
        )
        self.assertEqual(
            {"recipe", "raster_animation", "preview_animation", "mapped_result"},
            {asset["kind"] for asset in job["assets"]},
        )
        assets = {asset["kind"]: asset for asset in job["assets"]}
        self.assertEqual(
            attempt["mapped_result_asset_id"],
            assets["mapped_result"]["asset_id"],
        )
        self.assertEqual("image/gif", assets["preview_animation"]["mime_type"])
        self.assertEqual("image/gif", assets["raster_animation"]["mime_type"])

        catalog_id = detail["catalog_id"]
        mapped = json.loads(
            self._banked_asset(catalog_id, attempt["mapped_result_asset_id"])
        )
        self.assertEqual(["keyframes"], list(mapped["tracks"]))
        self.assertEqual(80, mapped["tracks"]["keyframes"]["frame_count"])
        self.assertEqual(80, mapped["source_frames"])
        self.assertEqual(34, mapped["duration_ms"])
        self.assertFalse(mapped["timing_resampled"])
        banked_recipe = json.loads(
            self._banked_asset(catalog_id, attempt["recipe_asset_id"])
        )
        self.assertEqual("Endpoint ember", banked_recipe["name"])
        self.assertEqual(["#FFFFFF", "#3A8DFF"], banked_recipe["palette"])
        self.assertEqual(
            b"GIF8",
            self._banked_asset(catalog_id, attempt["preview_asset_id"])[:4],
        )
        self.assertNotIn(str(self.root), json.dumps(detail))

    def test_effect_render_rejects_unusable_requests_without_banking(self) -> None:
        rejections = (
            ("unsupported primitive", {"recipe": self._effect_recipe(kind="spiral")}),
            ("palette", {"recipe": self._effect_recipe(color_index=4)}),
            ("LED target", {"targets": ["frames", "keyframes"]}),
            ("LED map", {"product_id": "NOT_A_KEYBOARD"}),
            ("LED area", {"targets": []}),
        )
        for expected, changes in rejections:
            with self.subTest(expected=expected):
                status, payload = self._render_effect(
                    recipe=changes.get("recipe"),
                    product_id=changes.get("product_id", "CB04"),
                    targets=changes.get("targets", ("keyframes",)),
                )
                self.assertEqual(400, status)
                self.assertIn(expected, payload["error"])
        status, payload = self._request(
            "POST",
            "/api/lighting/render",
            {
                "recipe": self._effect_recipe(),
                "product_id": "CB04",
                "targets": ["keyframes"],
                "duration_ms": 34,
            },
            timeout=60,
        )
        self.assertEqual(400, status)
        self.assertIn("one recipe, one keyboard", payload["error"])
        self.assertEqual([], self.library.scan()["jobs"])

    def test_effect_render_rejects_failed_quality_without_banking(self) -> None:
        # The layer lights a fifth of the raster, so the dense floor rejects it
        # only after a complete render — the gate itself stays untouched.
        status, payload = self._render_effect(recipe=self._effect_recipe("dense"))
        self.assertEqual(400, status)
        self.assertEqual("quality_failed", payload["code"])
        self.assertIn("density", payload["error"])
        self.assertIn("Nothing was saved", payload["error"])
        self.assertEqual([], self.library.scan()["jobs"])

    def test_effect_render_deadline_leaves_no_partial_library_entry(self) -> None:
        with patch.object(server, "_EFFECT_RENDER_DEADLINE_SECONDS", 0.0):
            status, payload = self._render_effect()
        self.assertEqual(409, status)
        self.assertIn("took too long", payload["error"])
        self.assertIn("Nothing was saved", payload["error"])
        self.assertEqual([], self.library.scan()["jobs"])
        self.assertFalse(list((self.root / "jobs").glob("*")))

    def test_effect_render_checks_the_budget_before_it_writes_anything(self) -> None:
        # Expire the shared deadline at the exact moment the last rendering
        # stage finishes: every byte exists, nothing has been written yet.
        from am_configurator import procedural

        clock = {"now": 0.0}
        real_mapper = procedural.map_frames_to_led_tracks

        def expire_once_mapped(*args, **kwargs):
            mapped = real_mapper(*args, **kwargs)
            clock["now"] = 10.0
            return mapped

        def budget():
            return procedural.WorkBudget(
                deadline=1.0,
                cancelled=lambda: False,
                monotonic=lambda: clock["now"],
            )

        with patch.object(server, "_effect_work_budget", budget), patch.object(
            procedural, "map_frames_to_led_tracks", expire_once_mapped
        ):
            status, payload = self._render_effect()
        self.assertEqual(409, status)
        self.assertIn("took too long", payload["error"])
        self.assertEqual([], self.library.scan()["jobs"])
        self.assertFalse(list((self.root / "jobs").glob("*")))

    def test_retired_creation_has_no_injectable_legacy_stack(self) -> None:
        for name in ("lighting_coordinator", "lighting_dependencies"):
            self.assertNotIn(name, inspect.signature(server._State).parameters)
            self.assertNotIn(name, inspect.signature(create_server).parameters)

    def test_static_csp_allows_only_local_media(self) -> None:
        request = Request(self._base + "/", method="GET")
        with urlopen(request, timeout=5) as response:
            csp = response.headers["Content-Security-Policy"]
        self.assertIn("media-src 'self' blob:", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertIn("img-src 'self' blob: data:", csp)
        self.assertIn("connect-src 'self'", csp)


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

    def test_text_macro_timing_fast_and_slow(self) -> None:
        fast = text_to_macro_events("abc", timing={"mode": "fast"})
        self.assertEqual([1, 10, 1, 10, 1, 0], fast["intvel_ms"])
        slow = text_to_macro_events("abc", timing={"mode": "slow"})
        self.assertEqual([1, 100, 1, 100, 1, 0], slow["intvel_ms"])

    def test_text_macro_natural_timing_is_deterministic_and_bounded(self) -> None:
        first = text_to_macro_events("hello world", timing={"mode": "natural", "wpm": 90})
        second = text_to_macro_events("hello world", timing={"mode": "natural", "wpm": 90})
        self.assertEqual(first, second, "natural timing must regenerate identically")
        pauses = first["intvel_ms"]
        # 90 WPM targets a 133ms interval; seeded jitter keeps 0.6x to 1.4x of it.
        # The compiler zeroes the final event's pause, so it is excluded here.
        for release_pause in pauses[1:-1:2]:
            self.assertTrue(79 <= release_pause <= 187, release_pause)
        for transition_pause in pauses[0::2]:
            self.assertEqual(1, transition_pause)
        self.assertEqual(0, pauses[-1])
        other_text = text_to_macro_events("hello worle", timing={"mode": "natural", "wpm": 90})
        self.assertNotEqual(first["intvel_ms"], other_text["intvel_ms"])

    def test_text_macro_natural_draws_from_a_captured_cadence(self) -> None:
        cadence = [50, 90, 130]
        first = text_to_macro_events("typing sample", timing={"mode": "natural", "cadence": cadence})
        second = text_to_macro_events("typing sample", timing={"mode": "natural", "cadence": cadence})
        self.assertEqual(first, second)
        for release_pause in first["intvel_ms"][1::2]:
            self.assertIn(release_pause, cadence + [0])

    def test_text_macro_timing_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "fast, slow, or natural"):
            text_to_macro_events("ab", timing={"mode": "ludicrous"})
        with self.assertRaisesRegex(ValueError, "timing choice is malformed"):
            text_to_macro_events("ab", timing="fast")
        with self.assertRaisesRegex(ValueError, "whole number"):
            text_to_macro_events("ab", timing={"mode": "natural", "wpm": "fast"})
        with self.assertRaisesRegex(ValueError, "between 20 and 140"):
            text_to_macro_events("ab", timing={"mode": "natural", "wpm": 400})
        with self.assertRaisesRegex(ValueError, "cadence sample"):
            text_to_macro_events("ab", timing={"mode": "natural", "cadence": []})
        with self.assertRaisesRegex(ValueError, "cadence sample"):
            text_to_macro_events("ab", timing={"mode": "natural", "cadence": [0]})
        with self.assertRaisesRegex(ValueError, "cadence sample"):
            text_to_macro_events("ab", timing={"mode": "natural", "cadence": [50] * 513})

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


class NeonEditorGeometryGuardTests(unittest.TestCase):
    """The editor must never invent a layout it does not have.

    An identity map renders a plausible grid at the wrong positions. A user
    painting on it authors LED positions that do not exist on the device, and
    the result is saved and written as if it were correct.
    """

    def _app_source(self) -> str:
        return (ROOT / "am_configurator" / "web" / "app.js").read_text(encoding="utf-8")

    def test_a_family_without_embedded_maps_refuses_to_render_without_geometry(self) -> None:
        source = self._app_source()
        compact = re.sub(r"\s+", "", source)

        self.assertIn(
            "if(!model.keyMap&&!model.displayMap&&!model.physicalLayout&&!servedTarget){",
            compact,
        )
        self.assertIn("geometryUnavailableNotice()", source)

    def test_geometry_loads_before_the_first_render_and_without_ai(self) -> None:
        """Bundling it with the AI calls let a slow AI status delay the layout."""
        source = self._app_source()
        compact = re.sub(r"\s+", "", source)

        self.assertIn("awaitloadDeviceGeometry();render();", compact)
        # The capabilities call must not sit in the deferred settings bundle.
        settings_bundle = re.search(r"asyncfunctionloadSettings\(\)\{(.*?)\}", compact)
        self.assertIsNotNone(settings_bundle)
        self.assertNotIn("led/capabilities", settings_bundle.group(1))
