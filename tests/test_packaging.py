from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from am_configurator import __version__
from build_tools.release_info import (
    artifact_filename,
    build_version,
    normalize_arch,
    project_version,
    stamp_build_version,
)


ROOT = Path(__file__).resolve().parents[1]


class ReleaseInfoTests(unittest.TestCase):
    def test_ci_build_number_is_stamped_into_runtime_version(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "am_configurator"
            package.mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nversion = "0.1.0"\n', encoding="utf-8"
            )
            (package / "_version.py").write_text(
                '__version__ = "0.1.0"\n', encoding="utf-8"
            )

            self.assertEqual("0.1.42", build_version(42, root=root))
            self.assertEqual("0.1.42", stamp_build_version(42, root=root))
            self.assertEqual("0.1.42", project_version(root))
            self.assertEqual(
                '__version__ = "0.1.42"\n',
                (package / "_version.py").read_text(encoding="utf-8"),
            )

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
        self.assertIn(
            "stamp --build-number ${{ github.run_number }} --github-output",
            workflow,
        )
        self.assertIn(
            "AM-Configurator-${{ steps.build_version.outputs.version }}-"
            "${{ matrix.artifact }}",
            workflow,
        )
        self.assertNotIn(".zip", workflow)
        self.assertNotIn(".tar.gz", workflow)

        for path in (
            "assets/am-configurator.png",
            "packaging/macos/build_dmg.sh",
            "packaging/linux/build_appimage.sh",
            "packaging/windows/AMConfigurator.iss",
            "packaging/windows/build_installer.ps1",
        ):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())

    def test_brand_icon_is_wired_into_every_distribution(self) -> None:
        icon_paths = {
            "assets/am-configurator.png": (1024, 1024),
            "assets/am-configurator-512.png": (512, 512),
            "am_configurator/web/icon.png": (128, 128),
        }
        for relative_path, expected_size in icon_paths.items():
            with self.subTest(path=relative_path):
                with Image.open(ROOT / relative_path) as icon:
                    self.assertEqual(expected_size, icon.size)

        self.assertTrue((ROOT / "assets" / "am-configurator.icns").is_file())
        self.assertTrue((ROOT / "assets" / "am-configurator.ico").is_file())

        spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")
        windows = (ROOT / "packaging" / "windows" / "AMConfigurator.iss").read_text(
            encoding="utf-8"
        )
        linux = (ROOT / "packaging" / "linux" / "build_appimage.sh").read_text(
            encoding="utf-8"
        )
        server = (ROOT / "am_configurator" / "server.py").read_text(encoding="utf-8")
        html = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("am-configurator.icns", spec)
        self.assertIn("am-configurator.ico", spec)
        self.assertIn("SetupIconFile=..\\..\\assets\\am-configurator.ico", windows)
        self.assertIn("assets/am-configurator-512.png", linux)
        self.assertIn('"/icon.png": "icon.png"', server)
        self.assertIn('<link rel="icon" href="/icon.png"', html)
        self.assertIn('<img class="brand-mark" src="/icon.png"', html)

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
