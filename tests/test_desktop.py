from __future__ import annotations

import sys
import json
import tempfile
import types
import unittest
from pathlib import Path
from urllib.parse import quote, urlsplit
from unittest import mock

from am_configurator import desktop


class _FakeWindow:
    def __init__(self, selection=None) -> None:
        self.selection = selection
        self.dialog_calls: list[dict] = []

    def create_file_dialog(self, **kwargs):
        self.dialog_calls.append(kwargs)
        return self.selection


def _fake_webview_module() -> types.ModuleType:
    """Stand in for the optional pywebview dependency.

    `desktop._folder_dialog_type` imports `webview` lazily so the base install
    never needs it. CI installs with `uv sync --locked` and no extras, so a test
    that reaches the real import fails there while passing on a developer
    machine built with `--extra desktop`.
    """
    module = types.ModuleType("webview")
    module.FileDialog = types.SimpleNamespace(
        FOLDER="folder-dialog",
        OPEN="open-dialog",
    )
    return module


class DesktopBridgeTests(unittest.TestCase):
    def test_folder_chooser_returns_none_when_cancelled(self) -> None:
        window = _FakeWindow(None)
        bridge = desktop.DesktopBridge(window)

        with mock.patch.dict(sys.modules, {"webview": _fake_webview_module()}):
            self.assertIsNone(bridge.choose_library_folder())
            self.assertEqual(
                window.dialog_calls,
                [{"dialog_type": desktop._folder_dialog_type(), "allow_multiple": False}],
            )

    def test_folder_chooser_returns_only_a_canonical_absolute_directory(self) -> None:
        with (
            tempfile.TemporaryDirectory() as raw_tmp,
            mock.patch.dict(sys.modules, {"webview": _fake_webview_module()}),
        ):
            tmp = Path(raw_tmp)
            chosen = tmp / "library"
            chosen.mkdir()
            window = _FakeWindow([str(chosen / ".." / "library")])
            bridge = desktop.DesktopBridge(window)

            self.assertEqual(bridge.choose_library_folder(), str(chosen.resolve()))

            window.selection = ["relative/library"]
            self.assertIsNone(bridge.choose_library_folder())

    def test_media_chooser_filters_supported_formats_and_returns_no_path(self) -> None:
        with (
            tempfile.TemporaryDirectory() as raw_tmp,
            mock.patch.dict(sys.modules, {"webview": _fake_webview_module()}),
        ):
            root = Path(raw_tmp)
            for suffix in ("gif", "png", "bmp"):
                selected = root / f"selected.{suffix}"
                payload = f"fixture-{suffix}".encode("ascii")
                selected.write_bytes(payload)
                window = _FakeWindow([str(selected)])
                bridge = desktop.DesktopBridge(window)

                result = bridge.choose_media_file()

                self.assertEqual(
                    result,
                    {"name": selected.name, "payload": payload},
                )
                self.assertNotIn(str(root), repr(result))
                self.assertEqual(
                    window.dialog_calls,
                    [{
                        "dialog_type": desktop._media_dialog_type(),
                        "allow_multiple": False,
                        "file_types": desktop._MEDIA_FILE_TYPES,
                    }],
                )

            filters = " ".join(desktop._MEDIA_FILE_TYPES)
            for extension in ("*.gif", "*.GIF", "*.png", "*.PNG", "*.bmp", "*.BMP", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG"):
                self.assertIn(extension, filters)
            self.assertNotIn("*.*", filters)

            for selection in (None, []):
                with self.subTest(selection=selection):
                    cancelled = desktop.DesktopBridge(_FakeWindow(selection))
                    self.assertIsNone(cancelled.choose_media_file())

    def test_bridge_has_no_local_model_file_picker(self) -> None:
        bridge = desktop.DesktopBridge(_FakeWindow(None))

        self.assertFalse(hasattr(bridge, "choose_local_model"))
        self.assertFalse(hasattr(bridge, "_choose_local_model"))
        self.assertFalse(hasattr(desktop, "_model_dialog_type"))

    def test_reveal_accepts_only_existing_targets_under_recorded_roots(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            current = tmp / "current"
            historical = tmp / "historical"
            outside = tmp / "outside"
            for directory in (current, historical, outside):
                directory.mkdir()
            current_asset = current / "concept.png"
            old_asset = historical / "video.mp4"
            outside_asset = outside / "secret.txt"
            for asset in (current_asset, old_asset, outside_asset):
                asset.write_bytes(b"fixture")

            opened: list[Path] = []
            bridge = desktop.DesktopBridge(
                settings_loader=lambda: {
                    "library": {
                        "current_root": str(current),
                        "roots": [str(historical)],
                    }
                },
                opener=opened.append,
            )

            self.assertTrue(bridge.reveal_library_path(str(current_asset)))
            self.assertTrue(bridge.reveal_library_path(str(old_asset)))
            self.assertFalse(bridge.reveal_library_path(str(outside_asset)))
            self.assertFalse(bridge.reveal_library_path(str(current / "missing.png")))
            self.assertFalse(bridge.reveal_library_path("relative.png"))
            self.assertEqual(opened, [current_asset.resolve(), old_asset.resolve()])

    def test_reveal_rejects_a_symlink_escape_from_a_recorded_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            root = tmp / "library"
            outside = tmp / "outside"
            root.mkdir()
            outside.mkdir()
            secret = outside / "secret.txt"
            secret.write_text("fixture", encoding="utf-8")
            try:
                (root / "escape").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks are unavailable")

            opened: list[Path] = []
            bridge = desktop.DesktopBridge(
                settings_loader=lambda: {
                    "library": {"current_root": str(root), "roots": []}
                },
                opener=opened.append,
            )

            self.assertFalse(
                bridge.reveal_library_path(str(root / "escape" / "secret.txt"))
            )
            self.assertEqual(opened, [])


class DesktopSmokeTests(unittest.TestCase):
    def test_full_smoke_loads_the_bundled_ui_without_ai_wiring(self) -> None:
        captured: dict = {}
        opened_assets: list[str] = []
        payloads = {
            "/": (
                b'OpenKeeb data-library-filter="sources" '
                b'data-library-filter="removed"'
            ),
            "/lighting_workspace.js": b"createLightingWorkspace",
            "/lighting_composer.js": b"renderColorEffect",
            "/library_state.js": b"libraryCatalogQuery",
            "/app.js": b"async function applyLibraryProfile",
            "/style.css": b".library-pagination",
        }

        class _Response:
            status = 200

            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self) -> bytes:
                return self.payload

        class _Server:
            @staticmethod
            def serve_forever(**_kwargs):
                return None

            @staticmethod
            def shutdown():
                return None

            @staticmethod
            def server_close():
                return None

        def create_server(**kwargs):
            captured.update(kwargs)
            return _Server(), "http://127.0.0.1:43111/?token=smoke"

        def open_loopback(url: str, *, timeout: int):
            self.assertEqual(5, timeout)
            path = urlsplit(url).path
            opened_assets.append(path)
            return _Response(payloads[path])

        with (
            mock.patch.dict(sys.modules, {"webview": types.ModuleType("webview")}),
            mock.patch.object(
                desktop,
                "_native_webview_policy",
                return_value=("webview.platforms.cocoa", None, "wkwebview"),
            ),
            mock.patch.object(desktop.importlib.util, "find_spec", return_value=object()),
            mock.patch.object(desktop, "_assert_ollama_api_only_bundle"),
            mock.patch.object(desktop, "create_server", side_effect=create_server),
            mock.patch.object(desktop, "urlopen", side_effect=open_loopback),
        ):
            self.assertEqual(desktop.run_smoke_test(), 0)

        self.assertEqual({}, captured)
        self.assertEqual(
            [
                "/",
                "/lighting_workspace.js",
                "/lighting_composer.js",
                "/library_state.js",
                "/app.js",
                "/style.css",
            ],
            opened_assets,
        )

class DesktopWindowTests(unittest.TestCase):
    def test_macos_automatic_window_tabbing_is_disabled(self) -> None:
        class _FakeNSWindow:
            automatic_window_tabbing = True

            @classmethod
            def setAllowsAutomaticWindowTabbing_(cls, value: bool) -> None:
                cls.automatic_window_tabbing = value

        fake_appkit = types.SimpleNamespace(NSWindow=_FakeNSWindow)

        with (
            mock.patch.object(desktop.sys, "platform", "darwin"),
            mock.patch.dict(sys.modules, {"AppKit": fake_appkit}),
        ):
            desktop._disable_macos_automatic_window_tabbing()

        self.assertFalse(_FakeNSWindow.automatic_window_tabbing)

    def test_run_desktop_binds_native_actions_only_to_loopback_server(self) -> None:
        created: dict = {}

        class _ClosedEvent:
            def __iadd__(self, callback):
                created["closed_callback"] = callback
                return self

        window = types.SimpleNamespace(events=types.SimpleNamespace(closed=_ClosedEvent()))

        def create_window(*args, **kwargs):
            created["args"] = args
            created["kwargs"] = kwargs
            return window

        def start(**kwargs):
            created["start_kwargs"] = kwargs
            created["storage_existed"] = Path(kwargs["storage_path"]).is_dir()

        fake_webview = types.SimpleNamespace(
            FileDialog=types.SimpleNamespace(FOLDER=20),
            settings={},
            create_window=create_window,
            start=start,
        )

        class _Server:
            def __init__(self):
                self.state = types.SimpleNamespace()

            def serve_forever(self, **kwargs):
                return None

            def shutdown(self):
                created["shutdown"] = True

            def server_close(self):
                created["server_close"] = True

        fake_server = _Server()
        with (
            mock.patch.dict(sys.modules, {"webview": fake_webview}),
            mock.patch.object(desktop, "create_server", return_value=(fake_server, "http://local")),
            mock.patch.object(desktop, "_disable_macos_automatic_window_tabbing") as disable_tabbing,
            mock.patch.object(desktop.platform, "system", return_value="Linux"),
        ):
            self.assertEqual(desktop.run_desktop(debug=True), 0)

        disable_tabbing.assert_called_once_with()
        self.assertNotIn("js_api", created["kwargs"])
        self.assertFalse(created["kwargs"]["text_select"])
        bridge = fake_server.state.desktop_bridge
        self.assertIsInstance(bridge, desktop.DesktopBridge)
        self.assertIs(bridge._window, window)
        self.assertIs(fake_server.state.desktop_bridge, bridge)
        self.assertTrue(created["shutdown"])
        self.assertTrue(created["server_close"])
        self.assertFalse(created["start_kwargs"]["private_mode"])
        self.assertTrue(created["storage_existed"])
        self.assertFalse(Path(created["start_kwargs"]["storage_path"]).exists())


class DesktopNativePolicyTests(unittest.TestCase):
    def test_linux_policy_requires_gtk_webkit(self) -> None:
        with mock.patch.object(desktop.platform, "system", return_value="Linux"):
            self.assertEqual(
                ("webview.platforms.gtk", "gtk", "gtkwebkit2"),
                desktop._native_webview_policy(),
            )

    def test_probe_script_checks_the_real_browser_policy_surface(self) -> None:
        script = desktop._native_policy_probe_script("verify")

        for required in (
            "localStorage",
            "sessionStorage",
            "location.search",
            "window.pywebview",
            "choose_library_folder",
            "_bind_window",
            "ALLOW_DOWNLOADS",
            "Content-Security-Policy",
            "script-src",
        ):
            with self.subTest(required=required):
                self.assertIn(required, script)

    def test_native_probe_reports_only_the_missing_backend_module(self) -> None:
        fake_webview = types.SimpleNamespace(settings={})
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            (root / "probe.json").write_text(
                json.dumps({"url": "http://127.0.0.1:43111/?token=test-token"}),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(sys.modules, {"webview": fake_webview}),
                mock.patch.object(desktop.platform, "system", return_value="Linux"),
                mock.patch.object(
                    desktop.importlib.util,
                    "find_spec",
                    return_value=object(),
                ),
                mock.patch.object(
                    desktop.importlib,
                    "import_module",
                    side_effect=ImportError(
                        "secret /private/path",
                        name="PyQt6.QtWebEngineWidgets",
                    ),
                ),
                self.assertRaises(SystemExit) as raised,
            ):
                desktop._run_native_policy_probe("seed", root)

            result = json.loads((root / "seed.json").read_text(encoding="utf-8"))

        message = str(raised.exception)
        self.assertEqual(
            "Native webview policy smoke failed: platform backend import failed "
            "(PyQt6.QtWebEngineWidgets).",
            message,
        )
        self.assertNotIn("secret", message)
        self.assertNotIn("/private/path", message)
        self.assertEqual(
            {"ok": False, "reason": "backend_import_PyQt6.QtWebEngineWidgets"},
            result,
        )

    def test_native_probe_reports_only_the_renderer_exception_type(self) -> None:
        class SecretRendererFailure(Exception):
            pass

        fake_webview = types.SimpleNamespace(
            settings={},
            create_window=lambda *args, **kwargs: object(),
            start=mock.Mock(side_effect=SecretRendererFailure("/private/path")),
        )
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            (root / "probe.json").write_text(
                json.dumps({"url": "http://127.0.0.1:43111/?token=test-token"}),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(sys.modules, {"webview": fake_webview}),
                mock.patch.object(desktop.platform, "system", return_value="Linux"),
                mock.patch.object(desktop.importlib.util, "find_spec", return_value=object()),
                mock.patch.object(desktop.importlib, "import_module", return_value=object()),
                self.assertRaises(SystemExit) as raised,
            ):
                desktop._run_native_policy_probe("seed", root)

            result = json.loads((root / "seed.json").read_text(encoding="utf-8"))

        self.assertEqual(
            "Native webview policy smoke failed: renderer_start_SecretRendererFailure.",
            str(raised.exception),
        )
        self.assertEqual(
            {"ok": False, "reason": "renderer_start_SecretRendererFailure"},
            result,
        )
        self.assertNotIn("/private/path", json.dumps(result))

    def test_native_probe_reports_only_a_missing_shared_library_name(self) -> None:
        fake_webview = types.SimpleNamespace(settings={})
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            (root / "probe.json").write_text(
                json.dumps({"url": "http://127.0.0.1:43111/?token=test-token"}),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(sys.modules, {"webview": fake_webview}),
                mock.patch.object(desktop.platform, "system", return_value="Linux"),
                mock.patch.object(desktop.importlib.util, "find_spec", return_value=object()),
                mock.patch.object(
                    desktop.importlib,
                    "import_module",
                    side_effect=ImportError(
                        "/private/path/libQt6Gui.so.6: cannot open shared object file",
                        name="QtGui",
                    ),
                ),
                self.assertRaises(SystemExit) as raised,
            ):
                desktop._run_native_policy_probe("seed", root)

            result = json.loads((root / "seed.json").read_text(encoding="utf-8"))

        self.assertEqual(
            "Native webview policy smoke failed: platform backend import failed "
            "(shared_library_libQt6Gui.so.6).",
            str(raised.exception),
        )
        self.assertEqual(
            {"ok": False, "reason": "backend_import_shared_library_libQt6Gui.so.6"},
            result,
        )
        self.assertNotIn("/private/path", json.dumps(result))

    def test_linux_native_probe_uses_isolated_storage_and_selected_renderer(self) -> None:
        payload = {name: True for name in desktop._NATIVE_POLICY_VERIFY_KEYS}
        payload["csp"] = "default-src 'self'; script-src 'self'"
        created: dict = {}
        original_cwd = Path.cwd()

        class _Window:
            events = types.SimpleNamespace(
                loaded=types.SimpleNamespace(wait=lambda timeout: bool(timeout))
            )

            def run_js(self, script):
                created["script"] = script
                created["current_url"] = (
                    "http://127.0.0.1:43111/#/__native_policy__/"
                    + quote(json.dumps(payload), safe="")
                )

            def get_current_url(self):
                return created.get("current_url", "http://127.0.0.1:43111/")

            def destroy(self):
                created["destroyed"] = True

        window = _Window()

        def start(func, args, **kwargs):
            created["start"] = kwargs
            created["storage_existed"] = Path(kwargs["storage_path"]).is_dir()
            created["cwd"] = Path.cwd()
            func(*args)

        def create_window(*args, **kwargs):
            created["window_kwargs"] = kwargs
            return window

        fake_webview = types.SimpleNamespace(
            renderer="gtkwebkit2",
            settings={},
            create_window=create_window,
            start=start,
        )
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            bundle_root = root / "bundle"
            bundle_root.mkdir()
            canonical_bundle_root = bundle_root.resolve()
            (root / "probe.json").write_text(
                json.dumps({"url": "http://127.0.0.1:43111/?token=test-token"}),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(sys.modules, {"webview": fake_webview}),
                mock.patch.object(desktop.platform, "system", return_value="Linux"),
                mock.patch.object(desktop.importlib.util, "find_spec", return_value=object()),
                mock.patch.object(desktop.importlib, "import_module", return_value=object()),
                mock.patch.object(
                    desktop.sys,
                    "_MEIPASS",
                    str(bundle_root),
                    create=True,
                ),
            ):
                self.assertEqual(desktop._run_native_policy_probe("verify", root), 0)

            result = json.loads((root / "verify.json").read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual("gtk", created["start"]["gui"])
        self.assertFalse(created["start"]["private_mode"])
        self.assertTrue(created["storage_existed"])
        self.assertFalse(Path(created["start"]["storage_path"]).exists())
        self.assertEqual(canonical_bundle_root, created["cwd"])
        self.assertEqual(original_cwd, Path.cwd())
        self.assertTrue(fake_webview.settings["ALLOW_DOWNLOADS"])
        self.assertNotIn("js_api", created["window_kwargs"])
        self.assertTrue(created["destroyed"])

    def test_smoke_runs_seed_and_verify_children_against_one_origin(self) -> None:
        observed: list[tuple[str, str]] = []
        lifecycle: list[str] = []

        class _Server:
            def serve_forever(self, **kwargs):
                lifecycle.append(f"serve:{kwargs['poll_interval']}")

            def shutdown(self):
                lifecycle.append("shutdown")

            def server_close(self):
                lifecycle.append("close")

        def run_child(command, **kwargs):
            del kwargs
            phase = command[command.index("--native-policy-probe") + 1]
            root = Path(command[command.index("--native-policy-dir") + 1])
            descriptor = json.loads(
                (root / "probe.json").read_text(encoding="utf-8")
            )
            observed.append((phase, descriptor["url"]))
            desktop._write_native_policy_result(
                root,
                phase,
                {"ok": True, "renderer": "wkwebview"},
            )
            return types.SimpleNamespace(returncode=0)

        with (
            mock.patch.object(
                desktop,
                "create_server",
                return_value=(
                    _Server(),
                    "http://127.0.0.1:43111/?token=private-token",
                ),
            ) as create_server_mock,
            mock.patch.object(desktop, "_assert_ollama_api_only_bundle"),
            mock.patch.object(desktop.subprocess, "run", side_effect=run_child),
            mock.patch.object(desktop.platform, "system", return_value="Darwin"),
        ):
            self.assertEqual(desktop.run_native_policy_smoke(), 0)

        discovery_kwargs = create_server_mock.call_args.kwargs
        self.assertEqual([], discovery_kwargs["device_discovery"]())
        self.assertEqual([], discovery_kwargs["vial_device_discovery"]())
        self.assertEqual([], discovery_kwargs["via_device_discovery"]())
        self.assertEqual(["seed", "verify"], [phase for phase, _url in observed])
        self.assertEqual(1, len({url for _phase, url in observed}))
        self.assertIn("shutdown", lifecycle)
        self.assertIn("close", lifecycle)


if __name__ == "__main__":
    unittest.main()
