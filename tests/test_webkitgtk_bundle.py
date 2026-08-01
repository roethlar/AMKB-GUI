from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class WebKitGtkBundleTests(unittest.TestCase):
    def test_runtime_helpers_are_collected_and_bundled_library_is_relocated(self) -> None:
        from build_tools.webkitgtk_bundle import prepare_webkitgtk_bundle

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_dir = root / "usr" / "lib"
            helper_dir = library_dir / "webkit2gtk-4.1"
            injected_dir = helper_dir / "injected-bundle"
            injected_dir.mkdir(parents=True)
            library = library_dir / "libwebkit2gtk-4.1.so.0"
            old_base = str(helper_dir).encode()
            old_injected = old_base + b"/injected-bundle/"
            library.write_bytes(
                b"prefix\0" + old_base + b"\0" + old_injected + b"\0suffix"
            )
            for name in (
                "WebKitWebProcess",
                "WebKitNetworkProcess",
                "WebKitGPUProcess",
            ):
                (helper_dir / name).write_bytes(name.encode())
            injected = injected_dir / "libwebkit2gtkinjectedbundle.so"
            injected.write_bytes(b"injected")
            workpath = root / "build"

            bundled = prepare_webkitgtk_bundle(
                [(str(library), ".")],
                workpath=workpath,
            )

            patched = workpath / "webkitgtk-relocated" / library.name
            patched_bytes = patched.read_bytes()
            self.assertIn(b"/proc/self/cwd/wk\0", patched_bytes)
            self.assertIn(b"/proc/self/cwd/wk/injected-bundle/\0", patched_bytes)
            self.assertNotIn(old_base, patched_bytes)
            self.assertIn((str(patched), "."), bundled)
            self.assertNotIn((str(library), "."), bundled)
            for name in (
                "WebKitWebProcess",
                "WebKitNetworkProcess",
                "WebKitGPUProcess",
            ):
                self.assertIn((str(helper_dir / name), "wk"), bundled)
            self.assertIn((str(injected), "wk/injected-bundle"), bundled)
            self.assertIn(old_base, library.read_bytes())

    def test_missing_required_helper_fails_the_build(self) -> None:
        from build_tools.webkitgtk_bundle import prepare_webkitgtk_bundle

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            library_dir = root / "usr" / "lib"
            helper_dir = library_dir / "webkit2gtk-4.1"
            helper_dir.mkdir(parents=True)
            library = library_dir / "libwebkit2gtk-4.1.so.0"
            old_base = str(helper_dir).encode()
            library.write_bytes(
                old_base + b"\0" + old_base + b"/injected-bundle/\0"
            )

            with self.assertRaises(FileNotFoundError):
                prepare_webkitgtk_bundle(
                    [(str(library), ".")],
                    workpath=root / "build",
                )


if __name__ == "__main__":
    unittest.main()
