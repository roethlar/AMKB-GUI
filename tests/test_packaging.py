from __future__ import annotations

import unittest
from pathlib import Path

from am_configurator import __version__
from build_tools.release_info import artifact_filename, normalize_arch, project_version


ROOT = Path(__file__).resolve().parents[1]


class ReleaseInfoTests(unittest.TestCase):
    def test_release_names_use_project_version_and_normalized_architecture(self) -> None:
        self.assertEqual(__version__, project_version(ROOT))
        self.assertEqual("x86_64", normalize_arch("AMD64"))
        self.assertEqual("aarch64", normalize_arch("arm64"))
        self.assertEqual(
            "AM-Configurator-0.1.0-macOS-arm64.dmg",
            artifact_filename("macos", "arm64", root=ROOT),
        )
        self.assertEqual(
            "AM-Configurator-0.1.0-Windows-x64-Setup.exe",
            artifact_filename("windows", "AMD64", root=ROOT),
        )
        self.assertEqual(
            "AM-Configurator-0.1.0-Linux-x86_64.AppImage",
            artifact_filename("linux", "x86_64", root=ROOT),
        )

    def test_desktop_workflow_publishes_native_installers(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("*.dmg", workflow)
        self.assertIn("*-Setup.exe", workflow)
        self.assertIn("*.AppImage", workflow)
        self.assertNotIn(".zip", workflow)
        self.assertNotIn(".tar.gz", workflow)

        for path in (
            "assets/am-configurator.svg",
            "packaging/macos/build_dmg.sh",
            "packaging/linux/build_appimage.sh",
            "packaging/windows/AMConfigurator.iss",
            "packaging/windows/build_installer.ps1",
        ):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())

    def test_windows_installer_smoke_test_waits_for_gui_processes(self) -> None:
        script = (ROOT / "packaging" / "windows" / "build_installer.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "Start-Process -FilePath $installer -ArgumentList $installerArgs -Wait -PassThru",
            script,
        )
        self.assertIn(
            "Start-Process -FilePath $installedApp -ArgumentList \"--smoke-test\" -Wait -PassThru",
            script,
        )


if __name__ == "__main__":
    unittest.main()
