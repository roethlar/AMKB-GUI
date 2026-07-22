"""Prepare the verified current-host llama.cpp runtime for native builds.

This command never downloads source or model weights. CI or the release
operator stages the single pinned source archive under ``build/llama/sources``;
an already-attested cache is verified and reused without rebuilding.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

from am_configurator import local_ai_runtime
from build_tools import llama_bundle


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "packaging" / "llama" / "manifest.json"


def _host_target() -> tuple[str, str]:
    if sys.platform == "darwin":
        platform_name = "macos"
    elif sys.platform.startswith("linux"):
        platform_name = "linux"
    elif sys.platform == "win32":
        platform_name = "windows"
    else:
        raise llama_bundle.BundleError("current platform does not support local AI")
    machine = platform.machine().lower()
    architecture = (
        "arm64"
        if machine in {"arm64", "aarch64"}
        else "x86_64"
        if machine in {"amd64", "x86_64"}
        else ""
    )
    if not architecture:
        raise llama_bundle.BundleError("current architecture does not support local AI")
    return platform_name, architecture


def prepare_runtime(root: Path = ROOT) -> local_ai_runtime.RuntimePaths:
    root = root.resolve()
    manifest_path = root / "packaging" / "llama" / "manifest.json"
    manifest = llama_bundle.load_manifest(manifest_path)
    platform_name, architecture = _host_target()
    cache = root / "build" / "llama" / llama_bundle.cache_key(
        manifest, platform_name, architecture
    )
    binary_root = cache / "bin"
    if cache.exists() or cache.is_symlink():
        try:
            return local_ai_runtime.verify_runtime_attestation(
                binary_root,
                manifest,
                platform_name=platform_name,
                architecture=architecture,
            )
        except local_ai_runtime.LocalRuntimeError:
            raise llama_bundle.BundleError(
                "cached llama.cpp runtime failed attestation; remove it only after investigating"
            ) from None

    archive = root / "build" / "llama" / "sources" / f"{manifest['revision']}.tar.gz"
    if not archive.is_file() or archive.is_symlink():
        raise llama_bundle.BundleError(
            "pinned llama.cpp source archive is not staged"
        )
    return llama_bundle.build_runtime(
        archive,
        cache,
        manifest,
        platform_name=platform_name,
        architecture=architecture,
    )


def main() -> int:
    try:
        runtime = prepare_runtime()
    except (llama_bundle.BundleError, local_ai_runtime.LocalRuntimeError) as exc:
        print(f"llama.cpp preparation failed: {exc}", file=sys.stderr)
        return 1
    print(runtime.server.parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
