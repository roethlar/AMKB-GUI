from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from am_configurator import desktop


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


class DesktopWindowTests(unittest.TestCase):
    def test_run_desktop_injects_and_binds_the_native_bridge(self) -> None:
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
            def serve_forever(self, **kwargs):
                return None

            def shutdown(self):
                created["shutdown"] = True

            def server_close(self):
                created["server_close"] = True

        with (
            mock.patch.dict(sys.modules, {"webview": fake_webview}),
            mock.patch.object(desktop, "create_server", return_value=(_Server(), "http://local")),
        ):
            self.assertEqual(desktop.run_desktop(debug=True), 0)

        bridge = created["kwargs"]["js_api"]
        self.assertIsInstance(bridge, desktop.DesktopBridge)
        self.assertIs(bridge._window, window)
        self.assertTrue(created["shutdown"])
        self.assertTrue(created["server_close"])


if __name__ == "__main__":
    unittest.main()
