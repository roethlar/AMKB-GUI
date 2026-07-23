from __future__ import annotations

import sys
import json
import socket
import tempfile
import types
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest import mock

from am_configurator import desktop
from am_configurator import credentials, device, llm, ollama_client, procedural, recipe_provider, store
from am_configurator.ai_capability import AICapabilityService


class _FakeWindow:
    def __init__(self, selection=None) -> None:
        self.selection = selection
        self.dialog_calls: list[dict] = []

    def create_file_dialog(self, **kwargs):
        self.dialog_calls.append(kwargs)
        return self.selection


class DesktopBridgeTests(unittest.TestCase):
    def test_folder_chooser_returns_none_when_cancelled(self) -> None:
        window = _FakeWindow(None)
        bridge = desktop.DesktopBridge(window)

        self.assertIsNone(bridge.choose_library_folder())
        self.assertEqual(
            window.dialog_calls,
            [{"dialog_type": desktop._folder_dialog_type(), "allow_multiple": False}],
        )

    def test_folder_chooser_returns_only_a_canonical_absolute_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            chosen = tmp / "library"
            chosen.mkdir()
            window = _FakeWindow([str(chosen / ".." / "library")])
            bridge = desktop.DesktopBridge(window)

            self.assertEqual(bridge.choose_library_folder(), str(chosen.resolve()))

            window.selection = ["relative/library"]
            self.assertIsNone(bridge.choose_library_folder())

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
    def test_full_smoke_uses_only_in_memory_credentials_and_offline_ollama(self) -> None:
        captured: dict = {}

        class _Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            @staticmethod
            def read() -> bytes:
                return b"AM Configurator"

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

        with (
            mock.patch.dict(sys.modules, {"webview": types.ModuleType("webview")}),
            mock.patch.object(
                desktop,
                "_native_webview_policy",
                return_value=("webview.platforms.cocoa", None, "wkwebview"),
            ),
            mock.patch.object(desktop.importlib.util, "find_spec", return_value=object()),
            mock.patch.object(desktop, "_assert_ollama_api_only_bundle"),
            mock.patch.object(desktop, "_run_disabled_ai_smoke"),
            mock.patch.object(desktop, "_run_api_recipe_smoke"),
            mock.patch.object(desktop, "_run_ollama_recipe_smoke"),
            mock.patch.object(desktop, "_run_ffmpeg_media_smoke"),
            mock.patch.object(desktop, "create_server", side_effect=create_server),
            mock.patch.object(desktop, "urlopen", return_value=_Response()),
        ):
            self.assertEqual(desktop.run_smoke_test(), 0)

        self.assertIsInstance(
            captured.get("credential_store"), credentials.MemoryCredentialStore
        )
        self.assertIsInstance(
            captured.get("ollama_client"), desktop._OfflineOllamaInventory
        )

    def test_every_offline_ai_smoke_executes_without_external_side_effects(self) -> None:
        calls = {
            "disabled_status": 0,
            "api_generate": 0,
            "ollama_generate": 0,
            "render": 0,
            "map": 0,
        }

        original_status = AICapabilityService.status
        original_api_generate = recipe_provider.XaiRecipeProvider.generate
        original_ollama_generate = recipe_provider.OllamaRecipeProvider.generate
        original_render = procedural.render_recipe
        original_map = procedural.map_frames_to_led_tracks

        def disabled_status(service):
            calls["disabled_status"] += 1
            return original_status(service)

        def api_generate(provider, *args, **kwargs):
            calls["api_generate"] += 1
            return original_api_generate(provider, *args, **kwargs)

        def ollama_generate(provider, *args, **kwargs):
            calls["ollama_generate"] += 1
            return original_ollama_generate(provider, *args, **kwargs)

        def render(*args, **kwargs):
            calls["render"] += 1
            return original_render(*args, **kwargs)

        def map_frames(*args, **kwargs):
            calls["map"] += 1
            return original_map(*args, **kwargs)

        def external_side_effect(*_args, **_kwargs):
            raise AssertionError("offline desktop smoke crossed an external boundary")

        with (
            mock.patch.object(AICapabilityService, "status", new=disabled_status),
            mock.patch.object(recipe_provider.XaiRecipeProvider, "generate", new=api_generate),
            mock.patch.object(recipe_provider.OllamaRecipeProvider, "generate", new=ollama_generate),
            mock.patch.object(procedural, "render_recipe", new=render),
            mock.patch.object(procedural, "map_frames_to_led_tracks", new=map_frames),
            mock.patch.object(socket, "create_connection", side_effect=external_side_effect),
            mock.patch.object(desktop, "urlopen", side_effect=external_side_effect),
            mock.patch.object(llm, "_default_opener", side_effect=external_side_effect),
            mock.patch.object(ollama_client.OllamaClient, "list_models", side_effect=external_side_effect),
            mock.patch.object(ollama_client.OllamaClient, "chat", side_effect=external_side_effect),
            mock.patch.object(credentials, "default_credential_store", side_effect=external_side_effect),
            mock.patch.object(credentials.KeyringCredentialStore, "get", side_effect=external_side_effect),
            mock.patch.object(credentials.KeyringCredentialStore, "set", side_effect=external_side_effect),
            mock.patch.object(credentials.KeyringCredentialStore, "delete", side_effect=external_side_effect),
            mock.patch.object(store, "update_local_ai_settings", side_effect=external_side_effect),
            mock.patch.object(desktop.subprocess, "Popen", side_effect=external_side_effect),
            mock.patch.object(device.serial, "Serial", side_effect=external_side_effect),
        ):
            desktop._run_disabled_ai_smoke()
            desktop._run_api_recipe_smoke()
            desktop._run_ollama_recipe_smoke()

        self.assertEqual(
            {
                "disabled_status": 1,
                "api_generate": 1,
                "ollama_generate": 1,
                "render": 2,
                "map": 2,
            },
            calls,
        )
        self.assertFalse(hasattr(desktop, "_run_local_recipe_smoke"))

    def test_recipe_smokes_construct_real_adapters_and_propagate_stage_failures(self) -> None:
        constructors = {"api": 0, "ollama": 0}
        real_api_provider = recipe_provider.XaiRecipeProvider
        real_ollama_provider = recipe_provider.OllamaRecipeProvider

        def api_provider(*args, **kwargs):
            constructors["api"] += 1
            return real_api_provider(*args, **kwargs)

        def ollama_provider(*args, **kwargs):
            constructors["ollama"] += 1
            return real_ollama_provider(*args, **kwargs)

        with (
            mock.patch.object(recipe_provider, "XaiRecipeProvider", side_effect=api_provider),
            mock.patch.object(recipe_provider, "OllamaRecipeProvider", side_effect=ollama_provider),
            mock.patch.object(procedural, "render_recipe", wraps=procedural.render_recipe) as render,
            mock.patch.object(
                procedural,
                "map_frames_to_led_tracks",
                wraps=procedural.map_frames_to_led_tracks,
            ) as map_frames,
        ):
            desktop._run_api_recipe_smoke()
            desktop._run_ollama_recipe_smoke()

        self.assertEqual({"api": 1, "ollama": 1}, constructors)
        self.assertEqual(2, render.call_count)
        self.assertEqual(2, map_frames.call_count)

        class SmokeStageFailure(RuntimeError):
            pass

        cases = (
            (
                "disabled status",
                desktop._run_disabled_ai_smoke,
                mock.patch.object(
                    AICapabilityService,
                    "status",
                    side_effect=SmokeStageFailure("disabled status failed"),
                ),
            ),
            (
                "api provider construction",
                desktop._run_api_recipe_smoke,
                mock.patch.object(
                    recipe_provider,
                    "XaiRecipeProvider",
                    side_effect=SmokeStageFailure("api construction failed"),
                ),
            ),
            (
                "api rendering",
                desktop._run_api_recipe_smoke,
                mock.patch.object(
                    procedural,
                    "render_recipe",
                    side_effect=SmokeStageFailure("api rendering failed"),
                ),
            ),
            (
                "ollama provider construction",
                desktop._run_ollama_recipe_smoke,
                mock.patch.object(
                    recipe_provider,
                    "OllamaRecipeProvider",
                    side_effect=SmokeStageFailure("ollama construction failed"),
                ),
            ),
            (
                "ollama mapping",
                desktop._run_ollama_recipe_smoke,
                mock.patch.object(
                    procedural,
                    "map_frames_to_led_tracks",
                    side_effect=SmokeStageFailure("ollama mapping failed"),
                ),
            ),
        )
        for name, smoke, failure_patch in cases:
            with self.subTest(stage=name), failure_patch:
                with self.assertRaises(SmokeStageFailure):
                    smoke()


class DesktopWindowTests(unittest.TestCase):
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

        fake_webview = types.SimpleNamespace(
            FileDialog=types.SimpleNamespace(FOLDER=20),
            settings={},
            create_window=create_window,
            start=lambda **kwargs: None,
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
        ):
            self.assertEqual(desktop.run_desktop(debug=True), 0)

        self.assertNotIn("js_api", created["kwargs"])
        bridge = fake_server.state.desktop_bridge
        self.assertIsInstance(bridge, desktop.DesktopBridge)
        self.assertIs(bridge._window, window)
        self.assertIs(fake_server.state.desktop_bridge, bridge)
        self.assertTrue(created["shutdown"])
        self.assertTrue(created["server_close"])


class DesktopNativePolicyTests(unittest.TestCase):
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
            "settings-local-panel",
            "settings-api-panel",
            "GGUF",
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

    def test_native_probe_uses_private_mode_and_the_selected_renderer(self) -> None:
        payload = {name: True for name in desktop._NATIVE_POLICY_VERIFY_KEYS}
        payload["csp"] = "default-src 'self'; script-src 'self'"
        created: dict = {}

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
            func(*args)

        def create_window(*args, **kwargs):
            created["window_kwargs"] = kwargs
            return window

        fake_webview = types.SimpleNamespace(
            renderer="qtwebengine",
            settings={},
            create_window=create_window,
            start=start,
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
            ):
                self.assertEqual(desktop._run_native_policy_probe("verify", root), 0)

            result = json.loads((root / "verify.json").read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertEqual("qt", created["start"]["gui"])
        self.assertTrue(created["start"]["private_mode"])
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
            ),
            mock.patch.object(desktop, "_assert_ollama_api_only_bundle"),
            mock.patch.object(desktop.subprocess, "run", side_effect=run_child),
            mock.patch.object(desktop.platform, "system", return_value="Darwin"),
        ):
            self.assertEqual(desktop.run_native_policy_smoke(), 0)

        self.assertEqual(["seed", "verify"], [phase for phase, _url in observed])
        self.assertEqual(1, len({url for _phase, url in observed}))
        self.assertIn("shutdown", lifecycle)
        self.assertIn("close", lifecycle)


if __name__ == "__main__":
    unittest.main()
