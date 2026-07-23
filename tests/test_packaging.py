from __future__ import annotations

import tomllib
import unittest
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory

from PIL import Image

from build import build_installer, reserve_local_build_number
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
    def test_local_build_number_advances_past_artifacts_and_counter(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "dist").mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nversion = "0.1.0"\n', encoding="utf-8"
            )
            (root / "dist" / "AM-Configurator-0.1.8-macOS-arm64.dmg").touch()
            (root / ".am-configurator-build-number").write_text(
                "10\n", encoding="utf-8"
            )

            self.assertEqual(11, reserve_local_build_number(root))
            self.assertEqual(
                "11\n",
                (root / ".am-configurator-build-number").read_text(encoding="utf-8"),
            )

    def test_build_script_dispatches_and_restores_the_tracked_version(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "am_configurator"
            package.mkdir()
            (root / "dist").mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nversion = "0.1.0"\n', encoding="utf-8"
            )
            version_file = package / "_version.py"
            original = '__version__ = "0.1.0"\n'
            version_file.write_text(original, encoding="utf-8")
            expected_name = artifact_filename("macos", root=root).replace(
                "-0.1.0-", "-0.1.12-"
            )
            commands: list[list[str]] = []

            def run_command(command: list[str], cwd: Path) -> None:
                self.assertEqual(root, cwd)
                commands.append(command)
                self.assertEqual("0.1.12", project_version(root))
                if command[-1].endswith("build_dmg.sh"):
                    (root / "dist" / artifact_filename("macos", root=root)).touch()

            artifact = build_installer(
                root=root,
                platform_name="darwin",
                build_number=12,
                run_command=run_command,
            )

            self.assertEqual(
                root / "dist" / expected_name,
                artifact,
            )
            self.assertEqual(original, version_file.read_text(encoding="utf-8"))
            self.assertEqual("uv", commands[0][0])
            self.assertIn("sync", commands[0])
            self.assertIn("build_tools.prepare_ffmpeg", commands[1])
            self.assertIn("build_tools.prepare_llama", commands[2])
            self.assertIn("pyinstaller", commands[3])
            self.assertTrue(commands[4][-1].endswith("build_dmg.sh"))

    def test_build_script_restores_the_version_after_a_failed_build(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "am_configurator"
            package.mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nversion = "0.1.0"\n', encoding="utf-8"
            )
            version_file = package / "_version.py"
            original = '__version__ = "0.1.0"\n'
            version_file.write_text(original, encoding="utf-8")

            def fail(_command: list[str], _cwd: Path) -> None:
                raise CalledProcessError(1, "uv")

            with self.assertRaises(CalledProcessError):
                build_installer(
                    root=root,
                    platform_name="linux",
                    build_number=13,
                    run_command=fail,
                )
            self.assertEqual(original, version_file.read_text(encoding="utf-8"))

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
        upload = workflow.split("- name: Upload native installer", 1)[1]
        self.assertNotIn(".zip", upload)
        self.assertNotIn(".tar.gz", upload)

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

    def test_spec_bundles_the_llm_module(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")

        # The LLM provider layer is imported lazily inside server.py, so
        # PyInstaller's static analysis misses it; it must be a hidden import or
        # the frozen app cannot generate effects.
        self.assertIn("hidden_imports", spec)
        self.assertIn('"am_configurator.llm"', spec)

    def test_secure_credential_dependency_and_os_backends_are_frozen(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text("utf-8")

        self.assertIn("keyring==25.7.0", metadata["project"]["dependencies"])
        self.assertIn('"am_configurator.credentials"', spec)
        for backend in ("macOS", "SecretService", "Windows"):
            self.assertIn(f'"keyring.backends.{backend}"', spec)

    def test_native_bundle_contains_verified_ffmpeg_and_real_media_smoke(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        smoke = (ROOT / "am_configurator" / "desktop.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
        macos = (ROOT / "packaging" / "macos" / "build_dmg.sh").read_text(encoding="utf-8")

        self.assertIn("build_tools.prepare_ffmpeg", build_script)
        self.assertIn("build_tools.prepare_ffmpeg", workflow)
        self.assertIn("get_ffmpeg_runtime", spec)
        self.assertIn('(str(ffmpeg_binary), "ffmpeg")', spec)
        for name in ("manifest.json", "ffmpeg-runtime.json", "LGPL-2.1.txt", "README.md"):
            self.assertIn(name, spec)
        self.assertIn("tiny-motion.mp4", spec)
        self.assertIn("process_video_frames", smoke)
        self.assertIn("MODEL_FRAME_CAPS", smoke)
        self.assertIn("get_ffmpeg_runtime", smoke)
        self.assertIn("build_tools.finalize_ffmpeg_bundle", macos)
        self.assertIn("codesign --force --sign -", macos)

    def test_transitional_llama_bundle_is_not_an_active_product_smoke(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text("utf-8")
        build_script = (ROOT / "build.py").read_text("utf-8")
        smoke = (ROOT / "am_configurator" / "desktop.py").read_text("utf-8")
        providers = (ROOT / "am_configurator" / "recipe_provider.py").read_text("utf-8")
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text("utf-8")
        macos = (ROOT / "packaging" / "macos" / "build_dmg.sh").read_text("utf-8")

        self.assertIn("build_tools.prepare_llama", build_script)
        self.assertIn("build_tools.prepare_llama", workflow)
        self.assertIn("get_local_ai_runtime", spec)
        self.assertIn("llama-runtime.json", spec)
        self.assertIn('project / "packaging" / "llama"', spec)
        self.assertIn("MIT.txt", spec)
        self.assertNotIn(".gguf", spec.lower())
        self.assertIn("rglob(\"*.gguf\")", smoke)
        self.assertIn("_run_api_recipe_smoke", smoke)
        self.assertIn("_run_ollama_recipe_smoke", smoke)
        self.assertNotIn("_run_local_recipe_smoke", smoke)
        self.assertNotIn("ManagedLlamaServer", providers)
        self.assertNotIn("ManagedLocalRecipeProvider", providers)
        self.assertIn("_run_disabled_ai_smoke", smoke)
        run_smoke = smoke[smoke.index("def run_smoke_test") :]
        self.assertNotIn("_run_local_recipe_smoke()", run_smoke)
        disabled_smoke = smoke[
            smoke.index("def _run_disabled_ai_smoke") : smoke.index("def _run_api_recipe_smoke")
        ]
        self.assertNotIn("get_local_ai_runtime", disabled_smoke)
        self.assertIn("build_tools.finalize_llama_bundle", macos)

    def test_frozen_smoke_test_runs_fake_recipe_backends_offline(self) -> None:
        smoke = (ROOT / "am_configurator" / "desktop.py").read_text(encoding="utf-8")

        # Both shipped recipe adapters must reach deterministic render and
        # mapping through injected fake transports, never provider hosts.
        self.assertIn("XaiRecipeProvider", smoke)
        self.assertIn("OllamaRecipeProvider", smoke)
        self.assertIn("render_recipe", smoke)
        self.assertIn("map_frames_to_led_tracks", smoke)
        # ssl context creation is verified without a socket; the real-TLS reach
        # test is opt-in only, so a CI/offline smoke run never touches network.
        self.assertIn("create_default_context", smoke)
        self.assertIn("AM_SMOKE_NET", smoke)

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
