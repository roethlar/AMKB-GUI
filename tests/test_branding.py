from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from build_tools.release_info import artifact_filename


ROOT = Path(__file__).resolve().parents[1]


class OpenKeebBrandingTests(unittest.TestCase):
    def test_current_product_surfaces_use_openkeeb_identity(self) -> None:
        surfaces = (
            "am_configurator/web/index.html",
            "am_configurator/desktop.py",
            "am_configurator/server.py",
            "build.py",
            "packaging/am_configurator.spec",
            "packaging/macos/build_dmg.sh",
            "packaging/windows/AMConfigurator.iss",
            "packaging/windows/build_installer.ps1",
            "packaging/linux/am-configurator.desktop",
            "packaging/linux/build_appimage.sh",
        )
        for relative in surfaces:
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("OpenKeeb", text)
                self.assertNotIn("AM Configurator", text)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('<h1 align="center">OpenKeeb</h1>', readme)
        self.assertIn("OpenKeeb is the next major version", readme)

    def test_reserved_compatibility_identifiers_do_not_move(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual("am-configurator", metadata["project"]["name"])
        self.assertEqual(
            "am_configurator.desktop:main",
            metadata["project"]["gui-scripts"]["am-configurator"],
        )
        self.assertIn(
            'bundle_identifier="dev.amconfigurator.desktop"',
            (ROOT / "packaging/am_configurator.spec").read_text(encoding="utf-8"),
        )
        self.assertIn(
            'APP = "am-configurator"',
            (ROOT / "am_configurator/store.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            'sessionStorage.setItem("am-configurator-token"',
            (ROOT / "am_configurator/web/app.js").read_text(encoding="utf-8"),
        )

    def test_native_artifacts_use_openkeeb_display_name(self) -> None:
        self.assertEqual(
            "OpenKeeb-0.1.68-macOS-arm64.dmg",
            artifact_filename("macos", "aarch64", root=ROOT),
        )
        self.assertEqual(
            "OpenKeeb-0.1.68-Windows-x64-Setup.exe",
            artifact_filename("windows", "x86_64", root=ROOT),
        )
        self.assertEqual(
            "OpenKeeb-0.1.68-Linux-x86_64.AppImage",
            artifact_filename("linux", "x86_64", root=ROOT),
        )

    def test_new_identity_assets_replace_am_mark(self) -> None:
        expected = (
            "assets/openkeeb-mark.svg",
            "assets/openkeeb.png",
            "assets/openkeeb-512.png",
            "assets/openkeeb.ico",
            "assets/openkeeb.icns",
            "am_configurator/web/icon.png",
        )
        for relative in expected:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
        for relative in (
            "assets/am-configurator.png",
            "assets/am-configurator-512.png",
            "assets/am-configurator.ico",
            "assets/am-configurator.icns",
        ):
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists())


if __name__ == "__main__":
    unittest.main()
