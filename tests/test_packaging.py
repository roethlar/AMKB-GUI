from __future__ import annotations

import importlib.util
import sys
import tomllib
import unittest
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from build import build_installer, reserve_local_build_number
from am_configurator import __version__, desktop
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
            self.assertIn("pyinstaller", commands[2])
            self.assertTrue(commands[3][-1].endswith("build_dmg.sh"))

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

    def test_desktop_workflow_runs_frozen_native_policy_on_every_platform(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(3, workflow.count("--native-policy-smoke"))
        for platform_name in ("macos", "windows", "linux"):
            with self.subTest(platform=platform_name):
                self.assertIn(
                    f"Verify native webview policy ({platform_name})",
                    workflow,
                )
        self.assertIn("xvfb-run", workflow)

    def test_linux_native_webview_prerequisites_are_installed(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        for package in (
            "libegl1",
            "libxcb-cursor0",
            "libxcb-icccm4",
            "libxcb-keysyms1",
            "libxcb-shape0",
            "libxcb-xkb1",
            "libxkbcommon-x11-0",
        ):
            with self.subTest(package=package):
                self.assertIn(package, workflow)

    def test_windows_ffmpeg_uses_the_setup_msys2_installation(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("id: msys2", workflow)
        self.assertIn(
            "MSYS2_LOCATION: ${{ steps.msys2.outputs.msys2-location }}",
            workflow,
        )
        self.assertNotIn("C:/msys64", workflow)
        self.assertIn('Join-Path $env:MSYS2_LOCATION "usr/bin"', workflow)
        self.assertIn('Join-Path $env:MSYS2_LOCATION "mingw64/bin"', workflow)
        self.assertIn('$env:PATH = "$usrBin;$mingwBin;$env:PATH"', workflow)
        for variable in ("$gpg", "$bash", "$cc", "$ar", "$ranlib", "$strip"):
            self.assertIn(variable, workflow)

    def test_desktop_workflow_has_no_obsolete_vulkan_setup(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("vulkan", workflow.casefold())

    def test_ci_runs_each_node_gate_as_a_failure_sensitive_step(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for command in (
            "node --test tests/web/*.test.js",
            "node --check am_configurator/web/lighting_state.js",
            "node --check am_configurator/web/lighting_review.js",
            "node --check am_configurator/web/lighting_targets.js",
            "node --check am_configurator/web/app.js",
        ):
            self.assertIn(f"run: {command}", workflow)

    def test_release_pipeline_has_no_llama_build_commands(self) -> None:
        paths = (
            ROOT / "build.py",
            ROOT / ".github" / "workflows" / "desktop.yml",
            ROOT / "packaging" / "am_configurator.spec",
            ROOT / "packaging" / "macos" / "build_dmg.sh",
            ROOT / "packaging" / "linux" / "build_appimage.sh",
            ROOT / "packaging" / "windows" / "build_installer.ps1",
            ROOT / "build_tools" / "prepare_ffmpeg.py",
            ROOT / "build_tools" / "ffmpeg_bundle.py",
        )
        release_surface = "\n".join(path.read_text("utf-8") for path in paths)
        release_surface = release_surface.casefold().replace("ollama", "")

        for forbidden in ("llama", "gguf", "ggml"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, release_surface)

    def test_linux_appimagetool_uses_immutable_release_assets(self) -> None:
        script = (ROOT / "packaging" / "linux" / "build_appimage.sh").read_text(
            encoding="utf-8"
        )
        checksums = {
            "x86_64": "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
            "aarch64": "f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158",
            "i686": "7ad9ff47c203aae0149b18f6df9e3018b2e2f470ea644a0413e3ded39e9e3bdb",
            "armhf": "42b61cba5495d8aaf418a5c9a015a49b85ad92efabcbd3c341f1540440e4e23d",
        }

        self.assertIn('appimagetool_version="1.9.1"', script)
        self.assertNotIn("/continuous/", script)
        self.assertIn(
            "releases/download/$appimagetool_version/appimagetool-$arch.AppImage",
            script,
        )
        for arch, checksum in checksums.items():
            with self.subTest(arch=arch):
                self.assertIn(f'{arch}) checksum="{checksum}" ;;', script)
        self.assertIn(
            '  *)\n'
            '    echo "Unsupported appimagetool architecture: $arch" >&2\n'
            "    exit 1\n"
            "    ;;",
            script,
        )
        self.assertIn(
            'tool_dir="$project_root/build/appimage-tools/$appimagetool_version"',
            script,
        )
        self.assertIn(
            'tool_path="$tool_dir/appimagetool-$arch-$checksum.AppImage"',
            script,
        )

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
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        finalizer = (ROOT / "build_tools" / "finalize_ffmpeg_bundle.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("build_tools.prepare_ffmpeg", build_script)
        self.assertIn("build_tools.prepare_ffmpeg", workflow)
        self.assertIn("packaging/ffmpeg/manifest.json text eol=lf", attributes)
        self.assertIn("get_ffmpeg_runtime", spec)
        self.assertIn('(str(ffmpeg_binary), "ffmpeg")', spec)
        self.assertNotIn("upx=True", spec)
        self.assertEqual(spec.count("upx=False"), 2)
        for name in ("manifest.json", "ffmpeg-runtime.json", "LGPL-2.1.txt", "README.md"):
            self.assertIn(name, spec)
        self.assertIn("tiny-motion.mp4", spec)
        self.assertIn("process_video_frames", smoke)
        self.assertIn("MODEL_FRAME_CAPS", smoke)
        self.assertIn("get_ffmpeg_runtime", smoke)
        self.assertIn("build_tools.finalize_ffmpeg_bundle", macos)
        self.assertIn("codesign --force --sign -", macos)
        for field in (
            "ffmpeg-signing.json",
            "prepared_binary_sha256",
            "signed_binary_sha256",
            "signing_identity",
            "cdhash",
            "capabilities",
        ):
            with self.subTest(provenance_field=field):
                self.assertIn(field, finalizer)
        self.assertIn("verify_runtime_attestation", finalizer)
        self.assertNotIn("inspect_runtime(", finalizer)

    def test_native_packages_are_ollama_api_only(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text("utf-8")
        build_script = (ROOT / "build.py").read_text("utf-8")
        smoke = (ROOT / "am_configurator" / "desktop.py").read_text("utf-8")
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text("utf-8")
        macos = (ROOT / "packaging" / "macos" / "build_dmg.sh").read_text("utf-8")
        packaged_surface = "\n".join((spec, build_script, workflow, macos)).lower()
        self.assertNotIn("llama", packaged_surface.replace("ollama", ""))

        removed_paths = (
            ROOT / "am_configurator" / "local_ai_runtime.py",
            ROOT / "am_configurator" / "local_model.py",
            ROOT / "build_tools" / "finalize_llama_bundle.py",
            ROOT / "build_tools" / "llama_bundle.py",
            ROOT / "build_tools" / "prepare_llama.py",
            ROOT / "packaging" / "llama",
            ROOT / "tests" / "test_local_ai_runtime.py",
        )
        for path in removed_paths:
            self.assertFalse(path.exists(), str(path.relative_to(ROOT)))
        for forbidden in (
            "llama.cpp",
            "llama-cli",
            "llama-server",
            "llama-runtime",
            "prepare_llama",
            "finalize_llama",
            "local_ai_runtime",
            "local_model",
            "packaging/llama",
            ".gguf",
        ):
            self.assertNotIn(forbidden, packaged_surface)

        product_surface = "\n".join(
            (ROOT / "am_configurator" / name).read_text("utf-8")
            for name in ("procedural_generation.py", "server.py", "web/app.js")
        ).lower()
        self.assertNotIn("llama.cpp", product_surface)
        self.assertNotIn("/api/ai/local/gguf", product_surface)
        self.assertIn("_assert_ollama_api_only_bundle", smoke)
        for forbidden_artifact in ('".gguf"', '"llama-cli"', '"llama-server"'):
            self.assertIn(forbidden_artifact, smoke)

    def test_application_forbids_managed_llama_processes_and_credentials(self) -> None:
        executable_modules = (
            "ai_capability.py",
            "desktop.py",
            "recipe_provider.py",
            "server.py",
        )
        sources = {
            name: (ROOT / "am_configurator" / name).read_text("utf-8")
            for name in executable_modules
        }
        combined = "\n".join(sources.values())

        for forbidden in (
            "ManagedLlamaServer",
            "ManagedLocalRecipeProvider",
            "probe_full_gpu_offload",
            "_run_local_recipe_smoke",
            '"--api-key"',
            "Bearer {token}",
        ):
            self.assertNotIn(forbidden, combined)
        for name in ("ai_capability.py", "recipe_provider.py"):
            self.assertNotIn("subprocess", sources[name])
            self.assertNotIn("Popen", sources[name])

    def test_local_model_and_runtime_attestations_cannot_return(self) -> None:
        removed_paths = (
            ROOT / "am_configurator" / "local_model.py",
            ROOT / "am_configurator" / "local_ai_runtime.py",
            ROOT / "build_tools" / "llama_bundle.py",
            ROOT / "build_tools" / "prepare_llama.py",
            ROOT / "build_tools" / "finalize_llama_bundle.py",
            ROOT / "packaging" / "llama",
        )
        for path in removed_paths:
            self.assertFalse(path.exists(), str(path.relative_to(ROOT)))
        for module in (
            "am_configurator.local_model",
            "am_configurator.local_ai_runtime",
            "build_tools.llama_bundle",
        ):
            self.assertIsNone(importlib.util.find_spec(module), module)

        allowed_ffmpeg_modules = {
            ROOT / "am_configurator" / "ffmpeg_runtime.py",
            ROOT / "build_tools" / "ffmpeg_bundle.py",
            ROOT / "build_tools" / "prepare_ffmpeg.py",
            ROOT / "build_tools" / "finalize_ffmpeg_bundle.py",
        }
        source_paths = [
            path
            for root in (ROOT / "am_configurator", ROOT / "build_tools")
            for path in root.glob("*.py")
            if path not in allowed_ffmpeg_modules
        ]
        source_paths.extend((ROOT / "build.py", ROOT / "packaging" / "am_configurator.spec"))
        source_paths.extend((ROOT / ".github" / "workflows").glob("*"))
        shipping_source = "\n".join(
            path.read_text("utf-8") for path in source_paths if path.is_file()
        )
        shipping_source = shipping_source.replace('"llama-runtime.json"', "").replace(
            '"local-model.json"', ""
        )
        for forbidden in (
            "LocalModelManager",
            "SelectedModel",
            "LocalRuntimeError",
            "RuntimePaths",
            "ATTESTATION_SCHEMA_VERSION",
            "MAX_RUNTIME_ATTESTATION_BYTES",
            "_read_runtime_attestation",
            "runtime_attestation_schema_version",
            "verify_runtime_attestation",
            "packaging/llama",
        ):
            self.assertNotIn(forbidden, shipping_source)

        for path in (ROOT / "packaging").rglob("*"):
            relative = path.relative_to(ROOT / "packaging")
            if relative.parts and relative.parts[0] == "ffmpeg":
                continue
            lowered = relative.as_posix().lower()
            self.assertNotIn("llama", lowered)
            self.assertNotIn(".gguf", lowered)
            self.assertNotIn("local-model.json", lowered)

        capability = (ROOT / "am_configurator" / "ai_capability.py").read_text("utf-8")
        for forbidden in (
            "attestation",
            "from .local_model",
            "import local_model",
            "localmodelmanager",
            "local_ai_runtime",
            "model_path",
            "verify_runtime_attestation",
        ):
            self.assertNotIn(forbidden, capability.lower())

        with TemporaryDirectory(prefix="am-attestation-artifact-") as temporary:
            root = Path(temporary)
            with patch.object(sys, "_MEIPASS", str(root), create=True):
                for name in ("local-model.json", "llama-runtime.json"):
                    artifact = root / name
                    artifact.write_text("{}", encoding="utf-8")
                    with self.subTest(artifact=name), self.assertRaises(SystemExit):
                        desktop._assert_ollama_api_only_bundle()
                    artifact.unlink()

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
