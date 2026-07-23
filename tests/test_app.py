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
import traceback
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
from am_configurator.device_mapping import (
    MAX_FRAMES,
    firmware_led_speed,
    frames_to_led_tracks,
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
    config_transfer_options,
    create_server,
    extract_importable_macros,
    gif_to_led_frames,
    gif_to_led_tracks,
    merge_configs,
    text_to_macro_events,
    validate_config,
)
from am_configurator.protocol import build_frame
from am_configurator.device import candidate_ports
from am_configurator.protocol import exclusive_serial_kwargs
from am_configurator.macros import macro_frames, parse_macro_frames
from am_configurator.writer import car_light_data_frames, car_light_info_frames
from am_configurator import credentials, device_mapping, llm, server, store
from am_configurator import generation
from am_configurator.library import (
    GeneratedAssetLibrary,
    LibraryRootError,
)


_DEFAULT_SETTINGS = {
    "schema_version": 5,
    "ai": {
        "enabled": False,
        "backend": None,
        "local": {
            "model_id": None,
            "model_digest": None,
            "setup_fingerprint": None,
        },
        "api": {
            "provider": "xai",
            "model_id": "grok-4.5",
            "setup_fingerprint": None,
            "disclosure_version": None,
            "disclosure_at": None,
        },
    },
    "library": {"current_root": None, "roots": []},
    "generation": {"loop_mode": "smooth"},
}
class _ScopedTestCredentialStore:
    """Keep test credentials isolated by each test's temporary data root."""

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    @staticmethod
    def _key(provider: str) -> tuple[str, str]:
        return (str(store.store_root()), provider)

    def available(self) -> bool:
        return True

    def get(self, provider: str) -> str | None:
        return self.values.get(self._key(provider))

    def set(self, provider: str, value: str) -> None:
        self.values[self._key(provider)] = value

    def delete(self, provider: str) -> None:
        self.values.pop(self._key(provider), None)


_TEST_CREDENTIALS = _ScopedTestCredentialStore()
_CREDENTIAL_PATCHER = None


def setUpModule() -> None:
    global _CREDENTIAL_PATCHER
    _CREDENTIAL_PATCHER = patch.object(
        credentials,
        "default_credential_store",
        return_value=_TEST_CREDENTIALS,
    )
    _CREDENTIAL_PATCHER.start()


def tearDownModule() -> None:
    if _CREDENTIAL_PATCHER is not None:
        _CREDENTIAL_PATCHER.stop()


class SettingsStoreTests(unittest.TestCase):
    """Strict v5 settings, safe legacy migration, and curated AI catalog."""

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

    def test_catalog_has_only_curated_recipe_models_and_integer_prices(self) -> None:
        from am_configurator import ai_catalog

        catalog = ai_catalog.catalog_view()
        self.assertEqual(catalog["schema_version"], 1)
        self.assertEqual(catalog["pricing_as_of"], "2026-07-20")
        expected = {
            "interpreter": {
                "default": "grok-4.5",
                "choices": {
                    "grok-4.5": {
                        "input_per_million_tokens_usd_ticks": 20_000_000_000,
                        "output_per_million_tokens_usd_ticks": 60_000_000_000,
                    },
                    "grok-4.3": {
                        "input_per_million_tokens_usd_ticks": 12_500_000_000,
                        "output_per_million_tokens_usd_ticks": 25_000_000_000,
                    },
                },
            },
        }
        observed = {}
        for role, role_data in catalog["roles"].items():
            observed[role] = {
                "default": role_data["default"],
                "choices": {
                    choice["id"]: choice["pricing"] for choice in role_data["choices"]
                },
            }
            for choice in role_data["choices"]:
                self.assertTrue(choice["pricing"])
                self.assertTrue(all(type(value) is int for value in choice["pricing"].values()))
        self.assertEqual(observed, expected)
        self.assertEqual(ai_catalog.DEFAULT_MODELS, {"interpreter": "grok-4.5"})

    def test_v1_file_migrates_in_place_without_losing_key(self) -> None:
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
        self.assertEqual("sk-existing", store.resolve_xai_key())
        self.assertFalse(path.with_name(path.name + ".bad").exists())
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], 5)
        self.assertNotIn("llm", saved)
        self.assertNotIn("sk-existing", path.read_text(encoding="utf-8"))

    def test_v5_round_trip(self) -> None:
        payload = copy.deepcopy(_DEFAULT_SETTINGS)
        payload["ai"]["backend"] = "local"
        payload["ai"]["local"]["setup_fingerprint"] = "a" * 64
        payload["generation"]["loop_mode"] = "ping_pong"
        store.save_settings(payload)
        self.assertEqual(store.load_settings(), payload)

    def test_unknown_fields_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store.save_settings({**copy.deepcopy(_DEFAULT_SETTINGS), "bogus": 1})
        with self.assertRaises(ValueError):
            store.update_preferences({"models": {}, "bogus": 1})
        with self.assertRaises(ValueError):
            store.update_api_key({"provider": "bogus", "key": "x"})
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

    def test_mask_sentinel_rejected(self) -> None:
        with self.assertRaises(ValueError):
            store.update_api_key({"provider": "xai", "key": store.KEY_MASK})
        self.assertFalse(store.settings_path().exists())

    def test_empty_key_clears(self) -> None:
        store.update_api_key({"provider": "xai", "key": "sk-test"})
        store.update_api_key({"provider": "xai", "key": ""})
        self.assertNotIn("sk-test", store.settings_path().read_text("utf-8"))
        self.assertIsNone(store.resolve_xai_key())

    def test_independent_updates_preserve_key_loop_mode_and_library(self) -> None:
        root = Path(self._tmp) / "library"
        store.update_api_key({"provider": "xai", "key": "sk-stays-put"})
        store.update_preferences({"loop_mode": "none"})
        store.update_library_root({"current_root": str(root)})
        settings = store.load_settings()
        self.assertEqual(store.resolve_xai_key(), "sk-stays-put")
        self.assertNotIn("llm", settings)
        self.assertNotIn("candidate_count", settings["generation"])
        self.assertEqual(settings["generation"]["loop_mode"], "none")
        self.assertEqual(settings["library"]["current_root"], str(root.resolve()))

        # The legacy whole-object POST remains a key-only compatibility seam
        # and must not reset the active Library or loop preference.
        store.save_settings({
            "llm": {"interpreter": "grok", "renderer": "grok", "keys": {"xai": ""}}
        })
        settings = store.load_settings()
        self.assertIsNone(store.resolve_xai_key())
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

    def test_privacy_acknowledges_only_current_version(self) -> None:
        from am_configurator import ai_catalog

        store.update_api_key({"provider": "xai", "key": "sk-private"})
        with self.assertRaises(ValueError):
            store.acknowledge_privacy({"version": "older-disclosure"})
        with self.assertRaises(ValueError):
            store.acknowledge_privacy({
                "version": ai_catalog.PRIVACY_DISCLOSURE_VERSION,
                "extra": True,
            })
        saved = store.acknowledge_privacy({
            "version": ai_catalog.PRIVACY_DISCLOSURE_VERSION,
        })
        self.assertEqual(
            saved["ai"]["api"]["disclosure_version"],
            ai_catalog.PRIVACY_DISCLOSURE_VERSION,
        )
        self.assertRegex(
            saved["ai"]["api"]["disclosure_at"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$",
        )
        self.assertEqual(store.resolve_xai_key(), "sk-private")

    def test_corrupt_file_recovers(self) -> None:
        path = store.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not valid json", encoding="utf-8")
        self.assertEqual(store.load_settings(), _DEFAULT_SETTINGS)
        self.assertFalse(path.exists())
        self.assertTrue(path.with_name(path.name + ".bad").exists())

    def test_env_override(self) -> None:
        store.update_api_key({"provider": "xai", "key": "sk-disk"})
        before = store.settings_path().read_text(encoding="utf-8")
        os.environ["XAI_API_KEY"] = "sk-env"
        self.assertEqual(store.resolve_xai_key(), "sk-env")
        # The env override is never persisted; disk content is untouched.
        self.assertEqual(store.settings_path().read_text(encoding="utf-8"), before)
        os.environ.pop("XAI_API_KEY")
        self.assertEqual(store.resolve_xai_key(), "sk-disk")

    def test_error_message_omits_secret(self) -> None:
        secret = "sk-super-secret-should-never-be-logged"
        with self.assertRaises(ValueError) as ctx:
            store.update_api_key({"provider": "xai", "key": [secret]})
        self.assertNotIn(secret, str(ctx.exception))

    def test_file_permissions(self) -> None:
        store.update_api_key({"provider": "xai", "key": "sk-test"})
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
        server, url = create_server(
            lighting_library=object(),
            lighting_coordinator=SimpleNamespace(
                active_job_id=None,
                reconcile_startup=lambda **_kwargs: [],
            ),
        )
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
                self.assertEqual(
                    b'{"config": null, "document_revision": null}', response.read()
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


class _FakeGetTransport:
    """Fake xAI GET transport with no payload argument."""

    def __init__(self, *, response=None, error: BaseException | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def __call__(self, url, api_key, deadline):
        self.calls.append({"url": url, "api_key": api_key, "deadline": deadline})
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
    """Shared speed constants and bounded xAI transport behavior."""

    def test_device_mapping_owns_firmware_speed_steps(self) -> None:
        # Single source of truth: llm duplicates the tuple so it need not import
        # server; this guard fails loudly if the two ever drift apart.
        self.assertEqual(34, min(device_mapping.LED_SPEEDS_MS))

    _URL = "https://api.x.ai/v1/responses"

    def _future_deadline(self) -> float:
        return time.monotonic() + 30.0

    def _http_error(
        self, code: int, *, retry_after=None, body: bytes = b"{}"
    ) -> urllib.error.HTTPError:
        hdrs = Message()
        if retry_after is not None:
            hdrs["Retry-After"] = str(retry_after)
        return urllib.error.HTTPError(
            self._URL, code, f"HTTP {code}", hdrs, io.BytesIO(body)
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

    def test_xai_transport_pins_origin_and_never_contacts_invalid_urls(self) -> None:
        invalid_urls = (
            "http://api.x.ai/v1/responses",
            "https://api.x.ai:443/v1/responses",
            "https://api.x.ai.evil.example/v1/responses",
            "https://api.x.ai@evil.example/v1/responses",
            "https://api.x.ai/v1/responses?next=https://evil.example",
            "https://api.x.ai/v1/responses#fragment",
        )
        for url in invalid_urls:
            for method in ("post", "get"):
                with self.subTest(url=url, method=method):
                    opener = _RecordingOpener(response=_FakeResponse(b"{}"))
                    with self.assertRaises(llm.ProviderError) as ctx:
                        if method == "post":
                            llm._xai_request(
                                url,
                                {},
                                _FAKE_KEY,
                                self._future_deadline(),
                                opener=opener,
                            )
                        else:
                            llm._xai_get_request(
                                url,
                                _FAKE_KEY,
                                self._future_deadline(),
                                opener=opener,
                            )
                    self.assertEqual(ctx.exception.code, "config")
                    self.assertEqual(opener.calls, [])
                    self.assertNotIn(_FAKE_KEY, str(ctx.exception))

    def test_default_xai_opener_ignores_proxies_and_refuses_redirects(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://proxy.invalid:8000",
                "HTTPS_PROXY": "http://proxy.invalid:8443",
                "ALL_PROXY": "socks5://proxy.invalid:1080",
            },
        ):
            open_call = llm._default_opener()
        handlers = open_call.__self__.handlers
        self.assertFalse(
            any(isinstance(handler, urllib.request.ProxyHandler) for handler in handlers)
        )
        redirect_handler = next(
            handler
            for handler in handlers
            if isinstance(handler, llm._NoXaiRedirects)
        )
        request = urllib.request.Request(
            self._URL,
            headers={"Authorization": f"Bearer {_FAKE_KEY}"},
        )
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                self.assertIsNone(
                    redirect_handler.redirect_request(
                        request,
                        None,
                        code,
                        "redirect",
                        Message(),
                        "https://evil.example/collect",
                    )
                )

    def test_actual_xai_request_ignores_environment_proxy(self) -> None:
        sentinel_proxy = ("127.0.0.1", 54322)
        attempted_connections = []

        def block_network(address, *_args, **_kwargs):
            attempted_connections.append(address)
            raise OSError("test socket blocked")

        with patch.dict(
            os.environ,
            {"HTTPS_PROXY": f"http://{sentinel_proxy[0]}:{sentinel_proxy[1]}"},
            clear=True,
        ):
            opener = llm._default_opener()
        with patch.object(socket, "create_connection", side_effect=block_network):
            with self.assertRaises(llm.ProviderError) as captured:
                llm._xai_request(
                    self._URL,
                    {},
                    _FAKE_KEY,
                    self._future_deadline(),
                    opener=opener,
                )

        self.assertEqual("offline", captured.exception.code)
        self.assertEqual([("api.x.ai", 443)], attempted_connections)
        self.assertNotIn(sentinel_proxy, attempted_connections)
        self.assertNotIn(_FAKE_KEY, str(captured.exception))

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

    def test_xai_request_http_error_retains_exact_usage_without_retry(self) -> None:
        body = json.dumps(
            {"error": {"message": _FAKE_KEY}, "usage": {"cost_in_usd_ticks": 91}}
        ).encode("utf-8")
        error = self._http_error(429, retry_after=7, body=body)
        opener = _RecordingOpener(error=error)

        with self.assertRaises(llm.ProviderError) as ctx:
            llm._xai_request(
                self._URL, {}, _FAKE_KEY, self._future_deadline(), opener=opener
            )

        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertEqual(ctx.exception.retry_after, 7)
        self.assertEqual(
            ctx.exception.usage,
            llm.ProviderUsage(cost_in_usd_ticks=91, reported=True),
        )
        self.assertNotIn(_FAKE_KEY, str(ctx.exception))
        self.assertEqual(len(opener.calls), 1)
        self.assertTrue(error.fp.closed)

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




class HistoricalVideoPollProviderTests(unittest.TestCase):
    """Status-only recovery for historical accepted xAI video requests."""

    def _future_deadline(self) -> float:
        return time.monotonic() + 30.0

    def test_poll_validates_request_id_before_get_and_accepts_every_status(self) -> None:
        invalid_ids = (
            "",
            "-starts-wrong",
            "has/slash",
            "has?query",
            "has#fragment",
            "has%2Fescape",
            "has\ncontrol",
            "a" * 201,
        )
        for request_id in invalid_ids:
            transport = _FakeGetTransport(response={})
            provider = llm.XaiVideoProvider(
                _FAKE_KEY,
                poll_transport=transport,
            )
            with self.subTest(request_id=request_id):
                with self.assertRaises(llm.ProviderError) as ctx:
                    provider.poll(request_id, self._future_deadline())
                self.assertEqual(ctx.exception.code, "config")
                self.assertEqual(transport.calls, [])

        longest = "a" + "~" * 199
        transport = _FakeGetTransport(response={"status": "pending"})
        result = llm.XaiVideoProvider(
            _FAKE_KEY,
            poll_transport=transport,
        ).poll(longest, self._future_deadline())
        self.assertEqual(result.request_id, longest)
        self.assertEqual(len(transport.calls), 1)

        for status in ("pending", "failed", "expired"):
            response = {
                "status": status,
                "usage": {"cost_in_usd_ticks": 17},
            }
            transport = _FakeGetTransport(response=response)
            result = llm.XaiVideoProvider(
                _FAKE_KEY,
                poll_transport=transport,
            ).poll("req_123", self._future_deadline())
            self.assertEqual(result.status, status)
            self.assertIsNone(result.video_url)
            self.assertIsNone(result.duration)
            self.assertEqual(result.usage.cost_in_usd_ticks, 17)
            self.assertEqual(
                transport.calls[0]["url"],
                llm.XAI_VIDEO_STATUS_URL.format(request_id="req_123"),
            )

    def test_poll_rejects_malformed_or_mismatched_echoed_request_ids(self) -> None:
        signed_url = "https://cdn.example/video.mp4?signature=temporary-secret"
        for echoed_request_id in ("different_request", "has/slash", None):
            response = {
                "request_id": echoed_request_id,
                "status": "done",
                "video": {"url": signed_url, "duration": 1},
                "usage": {"cost_in_usd_ticks": 29},
            }
            provider = llm.XaiVideoProvider(
                _FAKE_KEY,
                poll_transport=_FakeGetTransport(response=response),
            )
            with self.subTest(echoed_request_id=echoed_request_id):
                with self.assertRaises(llm.ProviderError) as ctx:
                    provider.poll("req_123", self._future_deadline())
                self.assertEqual(ctx.exception.code, "bad_response")
                self.assertEqual(ctx.exception.usage.cost_in_usd_ticks, 29)

    def test_done_requires_one_second_video_url_and_usage_is_exact_or_missing(self) -> None:
        signed_url = "https://cdn.example/video.mp4?signature=temporary-secret"
        done = {
            "request_id": "req.done-1",
            "status": "done",
            "video": {"url": signed_url, "duration": 1},
        }
        result = llm.XaiVideoProvider(
            _FAKE_KEY,
            poll_transport=_FakeGetTransport(response=done),
        ).poll("req.done-1", self._future_deadline())
        self.assertEqual(result.video_url, signed_url)
        self.assertEqual(result.duration, 1)
        self.assertIsNone(result.usage.cost_in_usd_ticks)
        self.assertFalse(result.usage.reported)
        self.assertNotIn(signed_url, repr(result))
        self.assertNotIn(signed_url, str(result))

        bad_responses = (
            {**done, "status": "queued"},
            {**done, "video": {}},
            {**done, "video": {"url": "", "duration": 1}},
            {**done, "video": {"url": signed_url, "duration": 2}},
            {**done, "usage": {"cost_in_usd_ticks": True}},
        )
        for response in bad_responses:
            with self.subTest(response=response):
                with self.assertRaises(llm.ProviderError) as ctx:
                    llm.XaiVideoProvider(
                        _FAKE_KEY,
                        poll_transport=_FakeGetTransport(response=response),
                    ).poll("req.done-1", self._future_deadline())
                self.assertEqual(ctx.exception.code, "bad_response")

    def test_poll_preserves_typed_usage_and_redacts_errors(self) -> None:
        usage = llm.ProviderUsage(cost_in_usd_ticks=77, reported=True)
        transport = _FakeGetTransport(error=llm.ProviderError(
            "rate_limited",
            f"poll failed using {_FAKE_KEY}",
            retry_after=9,
            usage=usage,
        ))
        provider = llm.XaiVideoProvider(
            _FAKE_KEY,
            poll_transport=transport,
        )
        with self.assertRaises(llm.ProviderError) as ctx:
            provider.poll("req_1", self._future_deadline())
        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertEqual(ctx.exception.retry_after, 9)
        self.assertEqual(ctx.exception.usage, usage)
        self.assertNotIn(_FAKE_KEY, str(ctx.exception))
        self.assertEqual(len(transport.calls), 1)

    def test_get_transport_uses_validated_url_deadline_timeout_and_no_body(self) -> None:
        response = _FakeResponse(json.dumps({
            "request_id": "req_1", "status": "pending"
        }).encode("utf-8"))
        opener = _RecordingOpener(response=response)
        with patch.object(llm.time, "monotonic", return_value=100.0):
            parsed = llm._xai_get_request(
                llm.XAI_VIDEO_STATUS_URL.format(request_id="req_1"),
                _FAKE_KEY,
                112.5,
                opener=opener,
            )
        self.assertEqual(parsed["status"], "pending")
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(timeout, 12.5)

        expired = _RecordingOpener(response=response)
        with patch.object(llm.time, "monotonic", return_value=200.0):
            with self.assertRaises(llm.ProviderError) as ctx:
                llm._xai_get_request(
                    llm.XAI_VIDEO_STATUS_URL.format(request_id="req_1"),
                    _FAKE_KEY,
                    200.0,
                    opener=expired,
                )
        self.assertEqual(ctx.exception.code, "timeout")
        self.assertEqual(expired.calls, [])


class LedGenerateEndpointTests(unittest.TestCase):
    """Task 8: settings + capabilities HTTP endpoints on the loopback server.

    Each test starts a real ``create_server`` instance on a background thread and
    drives it over localhost with ``X-AM-Token``. Settings persistence is isolated
    to a temp ``AM_CONFIGURATOR_DATA_DIR`` and the ``XAI_API_KEY`` override is
    cleared, so nothing here reads a real environment or credential.
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
            "/api/settings/credential",
            {"provider": "xai", "key": value},
        )
        self.assertEqual(status, 200)

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

    def test_current_credential_route_masks_key(self) -> None:
        key = "sk-secret-9WXYZ7788"
        status, saved = self._request(
            "POST",
            "/api/settings/credential",
            {"provider": "xai", "key": key},
        )
        self.assertEqual(status, 200)
        # Even the POST response must never echo the raw key back to the browser.
        self.assertNotIn(key, json.dumps(saved))
        self.assertNotIn("llm", saved)
        self.assertEqual(store.resolve_xai_key(), key)

        status, data = self._request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(data["schema_version"], 5)
        self.assertNotIn("llm", data)
        self.assertNotIn("candidate_count", data["generation"])
        # The raw key never returns to the browser, anywhere in the payload.
        self.assertNotIn(key, json.dumps(data))

        # Posting the display mask sentinel can never round-trip into storage.
        status, _ = self._request(
            "POST",
            "/api/settings/credential",
            {"provider": "xai", "key": store.KEY_MASK},
        )
        self.assertEqual(status, 400)

    def test_settings_masks_even_a_short_key_in_full(self) -> None:
        key = "tiny"
        status, saved = self._request(
            "POST", "/api/settings/credential", {"provider": "xai", "key": key}
        )
        self.assertEqual(status, 200)
        self.assertNotIn(key, json.dumps(saved))
        self.assertNotIn("llm", saved)
        self.assertEqual(store.resolve_xai_key(), key)

    def test_split_settings_routes_update_sections_independently(self) -> None:
        from am_configurator import ai_catalog

        key = "sk-split-route-12345678"
        status, data = self._request(
            "POST", "/api/settings/credential", {"provider": "xai", "key": key}
        )
        self.assertEqual(status, 200)
        self.assertNotIn(key, json.dumps(data))
        self.assertNotIn("llm", data)
        self.assertEqual(store.resolve_xai_key(), key)

        status, data = self._request(
            "POST", "/api/settings/preferences", {"loop_mode": "ping_pong"}
        )
        self.assertEqual(status, 200)
        self.assertNotIn("candidate_count", data["generation"])
        self.assertEqual(data["generation"]["loop_mode"], "ping_pong")
        self.assertEqual(store.resolve_xai_key(), key)

        library = Path(self._tmp) / "generated-library"
        status, data = self._request(
            "POST", "/api/settings/library", {"current_root": str(library)}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["library"]["current_root"], str(library.resolve()))
        self.assertEqual(store.resolve_xai_key(), key)

        status, data = self._request("POST", "/api/settings/privacy", {
            "version": ai_catalog.PRIVACY_DISCLOSURE_VERSION,
        })
        self.assertEqual(status, 200)
        self.assertEqual(
            data["generation"]["privacy_ack_version"],
            ai_catalog.PRIVACY_DISCLOSURE_VERSION,
        )
        self.assertTrue(data["generation"]["privacy_ack_at"])
        self.assertEqual(store.resolve_xai_key(), key)

        status, data = self._request(
            "POST", "/api/settings/credential", {"provider": "xai", "key": ""}
        )
        self.assertEqual(status, 200)
        self.assertIsNone(store.resolve_xai_key())
        status, data = self._request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(data["library"]["current_root"], str(library.resolve()))

    def test_split_settings_routes_are_strict_and_never_echo_secrets(self) -> None:
        from am_configurator import ai_catalog

        secret = "sk-must-not-appear-anywhere"
        invalid_cases = (
            ("/api/settings/credential", {"provider": "xai", "key": [secret]}),
            ("/api/settings/credential", {"provider": "xai", "key": "x", "extra": 1}),
            ("/api/settings/preferences", {"models": {"interpreter": "future"}}),
            ("/api/settings/preferences", {"candidate_count": 9}),
            ("/api/settings/preferences", {"loop_mode": "crossfade"}),
            ("/api/settings/preferences", {"unknown": True}),
            ("/api/settings/library", {"current_root": None, "unknown": True}),
            ("/api/settings/privacy", {"version": "old"}),
            (
                "/api/settings/privacy",
                {"version": ai_catalog.PRIVACY_DISCLOSURE_VERSION, "unknown": True},
            ),
        )
        for path, body in invalid_cases:
            with self.subTest(path=path, body=body):
                status, data = self._request("POST", path, body)
                self.assertEqual(status, 400)
                self.assertNotIn(secret, json.dumps(data))
        self.assertFalse(store.settings_path().exists())

    def test_capabilities(self) -> None:
        from am_configurator import ai_catalog

        status, data = self._request("GET", "/api/led/capabilities")
        self.assertEqual(status, 200)

        self.assertEqual(data["ai_catalog"], ai_catalog.catalog_view())
        self.assertEqual(
            data["privacy_disclosure_version"],
            ai_catalog.PRIVACY_DISCLOSURE_VERSION,
        )
        self.assertEqual(
            data["model_frame_caps"],
            dict(device_mapping.MODEL_FRAME_CAPS),
        )
        self.assertNotIn("models", data)
        self.assertNotIn("providers", data)
        self.assertNotIn("max_rendered_keyframes", data)

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
        class TrackingCredentialStore:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            def get(self, provider):
                self.calls.append(("get", provider))
                return "existing-key"

            def set(self, provider, value):
                self.calls.append(("set", provider, value))

            def delete(self, provider):
                self.calls.append(("delete", provider))

        vault = TrackingCredentialStore()
        self._server.state._credential_store = vault
        with patch.object(
            llm,
            "_xai_get_request",
            return_value={"models": []},
        ) as provider:
            for path, body in (
                ("/api/settings/key", {"provider": "xai", "key": "must-not-land"}),
                ("/api/settings/test", {}),
            ):
                with self.subTest(path=path):
                    status, response = self._request("POST", path, body)
                    self.assertIn(status, {404, 410})
                    self.assertNotIn("must-not-land", json.dumps(response))

        self.assertEqual([], vault.calls)
        provider.assert_not_called()
        self.assertFalse(hasattr(server._Handler, "_lighting_settings"))
        self.assertFalse(hasattr(server, "_xai_get"))
        self.assertFalse(hasattr(self._server.state, "llm_transport"))

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

    def test_requires_auth(self) -> None:
        cases = [
            ("GET", "/api/settings", None),
            ("GET", "/api/led/capabilities", None),
            ("GET", "/api/led/generate/status?job=x", None),
            ("POST", "/api/settings/key", {"provider": "xai", "key": "x"}),
            ("POST", "/api/settings/preferences", {"candidate_count": 4}),
            ("POST", "/api/settings/library", {"current_root": None}),
            ("POST", "/api/settings/privacy", {"version": "anything"}),
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
                self.assertEqual(410, status)
                self.assertEqual("retired", data["code"])


class _LightingEndpointCoordinator:
    def __init__(self, library: GeneratedAssetLibrary) -> None:
        self.library = library
        self.calls: list[tuple[str, tuple, dict]] = []
        self.reconcile_calls: list[str | None] = []
        self.failure: Exception | None = None
        self.active_job_id: str | None = None

    def reconcile_startup(
        self,
        *,
        api_key: str | None = None,
        _admission_token: object | None = None,
    ):
        del _admission_token
        self.reconcile_calls.append(api_key)
        return []

    def _raise_or_record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.calls.append((name, args, kwargs))
        if self.failure is not None:
            raise self.failure

    def cancel(self, job_id: str):
        self._raise_or_record("cancel", (job_id,), {})
        return self.library.load_manifest(job_id)


class CombinedReconciliationAdmissionTests(unittest.TestCase):
    def test_legacy_and_procedural_reconciliation_share_one_state_lease(self) -> None:
        gate = generation.OperationGate()
        procedural_entered = threading.Event()
        release_procedural = threading.Event()

        class LegacyCoordinator:
            active_job_id = None

            def __init__(self) -> None:
                self.tokens: list[object | None] = []

            def reconcile_startup(
                self,
                *,
                api_key=None,
                _admission_token=None,
            ) -> list[dict]:
                del api_key
                self.tokens.append(_admission_token)
                if _admission_token is None:
                    token, _cancelled = gate.begin()
                    gate.finish(token)
                return []

        class ProceduralCoordinator:
            active_job_id = None

            def __init__(self) -> None:
                self.tokens: list[object | None] = []

            def reconcile_startup(self, *, _admission_token=None) -> list[dict]:
                self.tokens.append(_admission_token)
                procedural_entered.set()
                if not release_procedural.wait(2):
                    raise TimeoutError("test did not release procedural reconciliation")
                if _admission_token is None:
                    token, _cancelled = gate.begin()
                    gate.finish(token)
                return []

        library = object()
        legacy = LegacyCoordinator()
        procedural = ProceduralCoordinator()
        state = server._State(
            None,
            "test-token",
            lighting_library=library,
            lighting_coordinator=legacy,
            lighting_dependencies={"operation_gate": gate},
            credential_store=credentials.MemoryCredentialStore(),
            procedural_coordinator=procedural,
        )
        failures: list[BaseException] = []

        def run_reconciliation() -> None:
            try:
                with patch.object(store, "resolve_xai_key", return_value=None):
                    state.reconcile_lighting(force=True)
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run_reconciliation)
        worker.start()
        admitted = None
        try:
            self.assertTrue(procedural_entered.wait(1))
            with self.assertRaises(generation.GenerationBusyError):
                admitted = gate.begin("concurrent-generation")
        finally:
            if admitted is not None:
                gate.finish(admitted[0])
            release_procedural.set()
            worker.join(2)

        self.assertFalse(worker.is_alive())
        self.assertEqual([], failures)
        self.assertEqual(1, len(legacy.tokens))
        self.assertIsNotNone(legacy.tokens[0])
        self.assertEqual(legacy.tokens, procedural.tokens)
        replacement_token, _replacement_cancelled = gate.begin("after-reconcile")
        gate.finish(replacement_token)


class AIServiceConstructionTests(unittest.TestCase):
    def test_concurrent_requests_publish_one_capability_service(self) -> None:
        state = server._State(
            None,
            "test-token",
            credential_store=credentials.MemoryCredentialStore(),
        )
        created: list[object] = []
        first_factory_entered = threading.Event()
        second_factory_entered = threading.Event()
        release_factory = threading.Event()
        results: list[object] = []

        def build_service(**_kwargs):
            service = object()
            created.append(service)
            first_factory_entered.set()
            if len(created) > 1:
                second_factory_entered.set()
            if not release_factory.wait(2):
                raise TimeoutError("test did not release service construction")
            return service

        def resolve_service() -> None:
            results.append(state.ai_services())

        with patch(
            "am_configurator.ai_capability.AICapabilityService",
            side_effect=build_service,
        ):
            first = threading.Thread(target=resolve_service)
            second = threading.Thread(target=resolve_service)
            first.start()
            self.assertTrue(first_factory_entered.wait(1))
            second.start()
            second_factory_entered.wait(0.2)
            release_factory.set()
            first.join(2)
            second.join(2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(1, len(created))
        self.assertEqual(2, len(results))
        self.assertIs(results[0], results[1])


class LightingStudioEndpointTests(unittest.TestCase):
    _DEFAULT = object()

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="am_lighting_endpoint_")
        self._saved_env = {
            key: os.environ.get(key)
            for key in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME", "XAI_API_KEY")
        }
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ.pop("XAI_API_KEY", None)
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = self._tmp
        self.root = Path(self._tmp) / "generated"
        store.update_library_root({"current_root": str(self.root)})
        store.update_api_key({"provider": "xai", "key": "sk-lighting-secret"})
        store.acknowledge_privacy({"version": "2026-07-20-xai-v1"})
        self.library = GeneratedAssetLibrary(self.root, minimum_free_bytes=1)
        self.coordinator = _LightingEndpointCoordinator(self.library)
        self._server, url = create_server(
            lighting_library=self.library,
            lighting_coordinator=self.coordinator,
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

    def _request(self, method, path, body=None, token=_DEFAULT):
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
            with urlopen(request, timeout=5) as response:
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
                "interpreter": "grok-4.5",
                "concept": "grok-imagine-image",
                "video": "grok-imagine-video-1.5",
            },
            loop_mode="smooth",
        )
        return self.library.update_manifest(
            manifest["job_id"], {"status": status, "phase": status}
        )

    def test_routes_are_authenticated_and_legacy_creation_is_retired(self) -> None:
        paths = (
            ("POST", "/api/lighting/concepts", {"prompt": "p", "product_id": "CB04", "targets": ["frames"]}),
            ("GET", "/api/lighting/library", None),
            ("GET", "/api/lighting/jobs/00000000-0000-4000-8000-000000000000", None),
            ("POST", "/api/lighting/jobs/00000000-0000-4000-8000-000000000000/cancel", {}),
            ("GET", "/api/lighting/assets/00000000-0000-4000-8000-000000000000/00000000-0000-4000-8000-000000000000", None),
        )
        for method, path, body in paths:
            with self.subTest(path=path):
                if method == "GET":
                    status, _headers, _raw = self._raw_request(path, token=None)
                else:
                    status, _data = self._request(method, path, body, token=None)
                self.assertEqual(403, status)

        with patch("am_configurator.writer.write_config") as write_config:
            status, data = self._request(
                "POST",
                "/api/lighting/concepts",
                {
                    "prompt": "A violet comet",
                    "product_id": "CB04",
                    "targets": ["frames"],
                    "candidate_count": 3,
                    "loop_mode": "smooth",
                },
            )
        self.assertEqual(410, status)
        self.assertEqual("retired", data["code"])
        self.assertNotIn("sk-lighting-secret", json.dumps(data))
        self.assertEqual([], self.coordinator.calls)
        write_config.assert_not_called()

    def test_startup_reconciliation_retries_when_a_key_becomes_available(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        store.update_api_key({"provider": "xai", "key": ""})
        coordinator = _LightingEndpointCoordinator(self.library)
        self._server, url = create_server(
            lighting_library=self.library,
            lighting_coordinator=coordinator,
        )
        self._token = parse_qs(urlparse(url).query)["token"][0]
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        self.assertEqual([None], coordinator.reconcile_calls)
        status, response = self._request(
            "POST",
            "/api/settings/credential",
            {"provider": "xai", "key": "sk-restored-secret"},
        )
        self.assertEqual(200, status)
        self.assertEqual([None, "sk-restored-secret"], coordinator.reconcile_calls)
        self.assertNotIn("sk-restored-secret", json.dumps(response))

    def test_reconciliation_waits_for_active_generation_to_finish(self) -> None:
        gate = generation.OperationGate()
        coordinator = _LightingEndpointCoordinator(self.library)
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        self._server, url = create_server(
            lighting_library=self.library,
            lighting_coordinator=coordinator,
            lighting_dependencies={"operation_gate": gate},
        )
        self._token = parse_qs(urlparse(url).query)["token"][0]
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        coordinator.reconcile_calls.clear()

        token, _cancelled = gate.begin("active-generation")
        try:
            self.assertEqual([], self._server.state.reconcile_lighting(force=True))
            self.assertEqual([], coordinator.reconcile_calls)
        finally:
            gate.finish(token)

        deadline = time.monotonic() + 2
        while not coordinator.reconcile_calls and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(["sk-lighting-secret"], coordinator.reconcile_calls)

    def test_retired_generation_stays_gone_while_admission_is_busy(self) -> None:
        gate = generation.OperationGate()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        self._server, url = create_server(
            lighting_dependencies={"operation_gate": gate},
        )
        self._token = parse_qs(urlparse(url).query)["token"][0]
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        legacy_body = {
            "prompt": "violet pulse",
            "product_id": "CB04",
            "targets": ["frames"],
            "frame_count": 1,
        }

        durable_token, _cancelled = gate.begin("durable-test-job")
        try:
            status, data = self._request("POST", "/api/led/generate", legacy_body)
        finally:
            gate.finish(durable_token)
        self.assertEqual(410, status)
        self.assertEqual("retired", data["code"])

    def test_retired_mutations_and_legacy_cancel_dispatch_without_device_writes(self) -> None:
        job = self._job()
        job_id = job["job_id"]
        retired = (
            ("/api/lighting/concepts", {"prompt": "old"}),
            (f"/api/lighting/jobs/{job_id}/concepts", {"candidate_count": 2}),
            (
                f"/api/lighting/jobs/{job_id}/animate",
                {"candidate_id": "00000000-0000-4000-8000-000000000001", "motion": "pulse", "loop_mode": "none"},
            ),
            (f"/api/lighting/jobs/{job_id}/process", {}),
        )
        with patch("am_configurator.writer.write_config") as write_config:
            for path, body in retired:
                with self.subTest(path=path):
                    status, data = self._request("POST", path, body)
                    self.assertEqual(410, status)
                    self.assertEqual("retired", data["code"])
            status, data = self._request(
                "POST", f"/api/lighting/jobs/{job_id}/cancel", {}
            )
            self.assertEqual(200, status)
            self.assertEqual(job_id, data["job_id"])
            self.assertEqual("cancel", self.coordinator.calls[-1][0])
            write_config.assert_not_called()

        before = len(self.coordinator.calls)
        status, _ = self._request(
            "POST", f"/api/lighting/jobs/{job_id}/cancel", {"extra": True}
        )
        self.assertEqual(400, status)
        status, _ = self._request(
            "POST", "/api/lighting/jobs/not-a-job/cancel", {}
        )
        self.assertEqual(400, status)
        self.assertEqual(before, len(self.coordinator.calls))

    def test_retired_creation_never_dispatches_provider_errors(self) -> None:
        cases = (
            LibraryRootError("library unavailable"),
            generation.GenerationBusyError("busy"),
            generation.GenerationNotActiveError("not active"),
            llm.ProviderError("rate_limited", "slow", retry_after=9),
            llm.ProviderError("unavailable", "provider unavailable"),
        )
        for error in cases:
            with self.subTest(error=type(error).__name__):
                self.coordinator.failure = error
                status, data = self._request(
                    "POST",
                    "/api/lighting/concepts",
                    {"prompt": "p", "product_id": "CB04", "targets": ["frames"]},
                )
                self.assertEqual(410, status)
                self.assertEqual("retired", data["code"])
                self.assertNotIn("sk-lighting-secret", json.dumps(data))
                self.assertEqual([], self.coordinator.calls)
        self.coordinator.failure = None

    def test_unexpected_lighting_errors_never_expose_local_paths(self) -> None:
        secret_path = self.root / "jobs" / "private-video.mp4"
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
        status, snapshot = self._request(
            "GET", f"/api/lighting/jobs/{first['job_id']}"
        )
        self.assertEqual(200, status)
        self.assertEqual(first["job_id"], snapshot["job_id"])
        self.assertNotIn(str(self.root), json.dumps(snapshot))
        status, library_detail = self._request(
            "GET", f"/api/lighting/library/{first['job_id']}"
        )
        self.assertEqual(200, status)
        self.assertEqual(snapshot, library_detail)

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

    def test_asset_streaming_enforces_ownership_mime_and_bounded_single_ranges(self) -> None:
        job = self._job()
        other = self._job(prompt="other")
        image = self.library.bank_asset(
            job["job_id"],
            kind="concept",
            data=b"fake-png-bytes",
            mime_type="image/png",
            origin="test",
        )
        video_payload = b"0123456789abcdefghijklmnopqrstuvwxyz"
        video = self.library.bank_asset(
            job["job_id"],
            kind="source_video",
            data=video_payload,
            mime_type="video/mp4",
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
        status, headers, payload = self._raw_request(
            f"/api/lighting/assets/{job['job_id']}/{video['asset_id']}",
            headers={"Range": "bytes=10-19"},
        )
        self.assertEqual(206, status)
        self.assertEqual("bytes 10-19/36", headers["Content-Range"])
        self.assertEqual(video_payload[10:20], payload)
        self.assertEqual("bytes", headers["Accept-Ranges"])

        status, _headers, _payload = self._raw_request(
            f"/api/lighting/assets/{other['job_id']}/{image['asset_id']}"
        )
        self.assertEqual(404, status)
        status, _headers, _payload = self._raw_request(
            f"/api/lighting/assets/{job['job_id']}/{video['asset_id']}",
            headers={"Range": "bytes=0-1,3-4"},
        )
        self.assertEqual(416, status)
        status, _headers, _payload = self._raw_request(
            "/api/lighting/assets/not-a-job/not-an-asset"
        )
        self.assertEqual(400, status)

        oversized = self.library.bank_asset(
            job["job_id"],
            kind="source_video",
            data=b"v" * (server._MAX_ASSET_RANGE_BYTES + 1),
            mime_type="video/mp4",
            origin="test",
        )
        status, _headers, _payload = self._raw_request(
            f"/api/lighting/assets/{job['job_id']}/{oversized['asset_id']}",
            headers={
                "Range": f"bytes=0-{server._MAX_ASSET_RANGE_BYTES}"
            },
        )
        self.assertEqual(416, status)

        owned_image = self.library.resolve_asset(job["job_id"], image["asset_id"])
        external = Path(self._tmp) / "external.png"
        external.write_bytes(b"outside")
        owned_image.path.unlink()
        owned_image.path.symlink_to(external)
        status, _headers, _payload = self._raw_request(
            f"/api/lighting/assets/{job['job_id']}/{image['asset_id']}"
        )
        self.assertEqual(404, status)

    def test_retired_creation_has_no_injectable_legacy_stack(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        self._server, url = create_server(
            lighting_dependencies={
                "operation_gate": generation.OperationGate(),
            }
        )
        self._token = parse_qs(urlparse(url).query)["token"][0]
        self._base = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        status, response = self._request(
            "POST", "/api/lighting/concepts", {"prompt": "offline violet"}
        )
        self.assertEqual(410, status)
        self.assertEqual("retired", response["code"])

    def test_static_csp_allows_only_local_media(self) -> None:
        request = Request(self._base + "/", method="GET")
        with urlopen(request, timeout=5) as response:
            csp = response.headers["Content-Security-Policy"]
        self.assertIn("media-src 'self' blob:", csp)


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
