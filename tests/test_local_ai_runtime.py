from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path

from am_configurator import local_ai_runtime
from build_tools import llama_bundle, prepare_llama


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "packaging" / "llama" / "manifest.json"


def _runtime_files(root: Path) -> local_ai_runtime.RuntimePaths:
    cli = root / ("llama-cli.exe" if os.name == "nt" else "llama-cli")
    server = root / ("llama-server.exe" if os.name == "nt" else "llama-server")
    cli.write_bytes(b"cli")
    server.write_bytes(b"server")
    if os.name != "nt":
        cli.chmod(0o755)
        server.chmod(0o755)
    return local_ai_runtime.RuntimePaths(cli=cli, server=server)


class LlamaBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = llama_bundle.load_manifest(MANIFEST_PATH)

    def test_manifest_pins_runtime_source_license_and_gpu_builds_without_models(self) -> None:
        self.assertEqual("b9637", self.manifest["runtime_version"])
        self.assertEqual(
            "aedb2a5e9ca3d4064148bbb919e0ddc0c1b70ab3",
            self.manifest["revision"],
        )
        self.assertEqual("MIT", self.manifest["license"]["spdx"])
        self.assertEqual(
            {"macos-arm64", "linux-x86_64", "windows-x86_64"},
            set(self.manifest["platforms"]),
        )
        self.assertIn("-DGGML_METAL=ON", self.manifest["platforms"]["macos-arm64"])
        self.assertIn("-DGGML_VULKAN=ON", self.manifest["platforms"]["linux-x86_64"])
        self.assertIn("-DGGML_VULKAN=ON", self.manifest["platforms"]["windows-x86_64"])
        encoded = json.dumps(self.manifest).lower()
        self.assertNotIn("model_url", encoded)
        self.assertNotIn("huggingface", encoded)

    def test_source_extraction_rejects_links_and_traversal(self) -> None:
        root_name = self.manifest["source"]["root"]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive = base / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                root = tarfile.TarInfo(root_name)
                root.type = tarfile.DIRTYPE
                bundle.addfile(root)
                cmake = tarfile.TarInfo(f"{root_name}/CMakeLists.txt")
                cmake.size = 5
                bundle.addfile(cmake, io.BytesIO(b"cmake"))
                license_file = tarfile.TarInfo(f"{root_name}/LICENSE")
                license_file.size = 3
                bundle.addfile(license_file, io.BytesIO(b"MIT"))
            extracted = llama_bundle.extract_source_archive(
                archive, base / "good", self.manifest
            )
            self.assertEqual(b"cmake", (extracted / "CMakeLists.txt").read_bytes())

            malicious = base / "malicious.tar.gz"
            with tarfile.open(malicious, "w:gz") as bundle:
                escape = tarfile.TarInfo(f"{root_name}/../escape")
                escape.size = 1
                bundle.addfile(escape, io.BytesIO(b"x"))
            with self.assertRaises(llama_bundle.BundleError):
                llama_bundle.extract_source_archive(
                    malicious, base / "bad", self.manifest
                )
            self.assertFalse((base / "bad").exists())

            linked = base / "linked.tar.gz"
            with tarfile.open(linked, "w:gz") as bundle:
                link = tarfile.TarInfo(f"{root_name}/linked-source")
                link.type = tarfile.SYMTYPE
                link.linkname = "../outside"
                bundle.addfile(link)
            with self.assertRaises(llama_bundle.BundleError):
                llama_bundle.extract_source_archive(
                    linked, base / "linked", self.manifest
                )
            self.assertFalse((base / "linked").exists())

    def test_build_plan_is_offline_static_and_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = llama_bundle.build_plan(
                root / "source",
                root / "build",
                self.manifest,
                platform_name="macos",
                architecture="arm64",
            )
            configure = " ".join(plan.configure)
            self.assertEqual("cmake", plan.configure[0])
            self.assertIn("-DBUILD_SHARED_LIBS=OFF", plan.configure)
            self.assertIn("-DGGML_RPC=OFF", plan.configure)
            self.assertIn("-DGGML_NATIVE=OFF", plan.configure)
            self.assertIn("-DGGML_METAL=ON", plan.configure)
            self.assertIn("-ffile-prefix-map=", configure)
            self.assertEqual(
                str(self.manifest["source_date_epoch"]),
                plan.environment["SOURCE_DATE_EPOCH"],
            )
            self.assertEqual(
                ("llama-cli", "llama-server"),
                tuple(
                    plan.build[
                        plan.build.index("--target") + 1 : plan.build.index("--parallel")
                    ]
                ),
            )

    def test_prepare_reuses_attested_cache_and_refuses_invalid_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "packaging" / "llama"
            metadata.mkdir(parents=True)
            shutil.copy2(MANIFEST_PATH, metadata / "manifest.json")
            cache = root / "build" / "llama" / llama_bundle.cache_key(
                self.manifest, "macos", "arm64"
            )
            binary_root = cache / "bin"
            binary_root.mkdir(parents=True)
            runtime = _runtime_files(binary_root)
            inspection = {
                "runtime_version": self.manifest["runtime_version"],
                "revision": self.manifest["revision"],
                "capabilities": {
                    **{f"cli:{flag}": True for flag in self.manifest["required_cli_flags"]},
                    **{f"server:{flag}": True for flag in self.manifest["required_server_flags"]},
                },
            }
            llama_bundle.emit_runtime_attestation(
                runtime,
                binary_root / "llama-runtime.json",
                self.manifest,
                inspection,
                compiler_identity="test compiler",
                platform_name="macos",
                architecture="arm64",
            )
            original_target = prepare_llama._host_target
            prepare_llama._host_target = lambda: ("macos", "arm64")
            try:
                self.assertEqual(
                    local_ai_runtime.RuntimePaths(
                        cli=runtime.cli.resolve(), server=runtime.server.resolve()
                    ),
                    prepare_llama.prepare_runtime(root),
                )
                runtime.cli.write_bytes(b"tampered")
                with self.assertRaisesRegex(
                    llama_bundle.BundleError, "remove it only after investigating"
                ):
                    prepare_llama.prepare_runtime(root)
            finally:
                prepare_llama._host_target = original_target

    def test_runtime_attestation_binds_both_binaries_and_never_searches_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = _runtime_files(root)

            def runner(args, **_kwargs):
                if "--version" in args:
                    return llama_bundle.CommandResult(
                        0, "", "version: 9637 (aedb2a5)\n"
                    )
                return llama_bundle.CommandResult(
                    0,
                    " ".join(
                        self.manifest["required_cli_flags"]
                        if Path(args[0]).name.startswith("llama-cli")
                        else self.manifest["required_server_flags"]
                    ),
                    "",
                )

            inspection = llama_bundle.inspect_runtime(
                runtime, self.manifest, runner=runner
            )
            llama_bundle.emit_runtime_attestation(
                runtime,
                root / "llama-runtime.json",
                self.manifest,
                inspection,
                compiler_identity="test compiler",
                platform_name="macos",
                architecture="arm64",
            )
            resolved = local_ai_runtime.resolve_runtime(
                manifest=self.manifest,
                injected=root,
                platform_name="macos",
                architecture="arm64",
            )
            self.assertEqual(
                local_ai_runtime.RuntimePaths(
                    cli=runtime.cli.resolve(), server=runtime.server.resolve()
                ),
                resolved,
            )

            runtime.cli.write_bytes(b"tampered")
            with self.assertRaises(local_ai_runtime.LocalRuntimeError):
                local_ai_runtime.resolve_runtime(
                    manifest=self.manifest,
                    injected=root,
                    platform_name="macos",
                    architecture="arm64",
                )
            with self.assertRaises(local_ai_runtime.LocalRuntimeError):
                local_ai_runtime.resolve_runtime(
                    manifest=self.manifest,
                    environment={"PATH": str(root)},
                    development_root=root / "unused",
                    platform_name="macos",
                    architecture="arm64",
                )

    @unittest.skipIf(os.name == "nt", "macOS bundle symlink layout is POSIX-only")
    def test_frozen_bundle_accepts_only_confined_metadata_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            contents = Path(directory) / "Contents"
            binary_root = contents / "Frameworks" / "llama"
            metadata_root = contents / "Resources" / "llama"
            binary_root.mkdir(parents=True)
            metadata_root.mkdir(parents=True)
            runtime = _runtime_files(binary_root)
            inspection = {
                "runtime_version": self.manifest["runtime_version"],
                "revision": self.manifest["revision"],
                "capabilities": {
                    **{f"cli:{flag}": True for flag in self.manifest["required_cli_flags"]},
                    **{f"server:{flag}": True for flag in self.manifest["required_server_flags"]},
                },
            }
            llama_bundle.emit_runtime_attestation(
                runtime,
                metadata_root / "llama-runtime.json",
                self.manifest,
                inspection,
                compiler_identity="test compiler",
                platform_name="macos",
                architecture="arm64",
            )
            (binary_root / "llama-runtime.json").symlink_to(
                metadata_root / "llama-runtime.json"
            )

            resolved = local_ai_runtime.resolve_runtime(
                manifest=self.manifest,
                bundle_root=contents / "Frameworks",
                platform_name="macos",
                architecture="arm64",
            )
            self.assertEqual(
                local_ai_runtime.RuntimePaths(
                    cli=runtime.cli.resolve(), server=runtime.server.resolve()
                ),
                resolved,
            )

            outside = Path(directory) / "outside.json"
            outside.write_bytes((metadata_root / "llama-runtime.json").read_bytes())
            (binary_root / "llama-runtime.json").unlink()
            (binary_root / "llama-runtime.json").symlink_to(outside)
            with self.assertRaises(local_ai_runtime.LocalRuntimeError):
                local_ai_runtime.resolve_runtime(
                    manifest=self.manifest,
                    bundle_root=contents / "Frameworks",
                    platform_name="macos",
                    architecture="arm64",
                )


if __name__ == "__main__":
    unittest.main()
