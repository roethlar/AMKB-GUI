"""Re-attest macOS llama.cpp binaries after PyInstaller code signing."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from am_configurator import local_ai_runtime
from build_tools import llama_bundle


def finalize_macos_app(app_path: Path | str) -> Path:
    app = Path(app_path).resolve(strict=True)
    if not app.is_dir() or app.suffix != ".app":
        raise llama_bundle.BundleError("macOS application bundle is invalid")
    contents = app / "Contents"
    binary_root = contents / "Frameworks" / "llama"
    metadata_root = contents / "Resources" / "llama"
    manifest_path = metadata_root / "manifest.json"
    attestation = metadata_root / "llama-runtime.json"
    machine = platform.machine().lower()
    architecture = (
        "arm64"
        if machine in {"arm64", "aarch64"}
        else "x86_64"
        if machine in {"x86_64", "amd64"}
        else ""
    )
    if not architecture:
        raise llama_bundle.BundleError("current macOS architecture is unsupported")
    manifest = llama_bundle.load_manifest(manifest_path)
    names = manifest["binaries"]
    runtime = local_ai_runtime.RuntimePaths(
        cli=binary_root / names["cli"],
        server=binary_root / names["server"],
    )
    if any(path.is_symlink() or not path.is_file() for path in (runtime.cli, runtime.server)):
        raise llama_bundle.BundleError("bundled llama.cpp executables are invalid")
    try:
        previous = json.loads(attestation.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise llama_bundle.BundleError("bundled llama.cpp attestation could not be read") from None
    compiler_identity = previous.get("compiler_identity") if isinstance(previous, dict) else None
    if not isinstance(compiler_identity, str) or not compiler_identity:
        raise llama_bundle.BundleError("bundled llama.cpp compiler identity is invalid")
    inspection = llama_bundle.inspect_runtime(runtime, manifest)
    llama_bundle.emit_runtime_attestation(
        runtime,
        attestation,
        manifest,
        inspection,
        compiler_identity=compiler_identity,
        platform_name="macos",
        architecture=architecture,
    )
    local_ai_runtime.verify_runtime_attestation(
        binary_root,
        manifest,
        platform_name="macos",
        architecture=architecture,
        metadata_symlink_root=contents,
    )
    return attestation


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    args = parser.parse_args(argv)
    try:
        attestation = finalize_macos_app(args.app)
    except (llama_bundle.BundleError, local_ai_runtime.LocalRuntimeError, OSError) as exc:
        print(f"llama.cpp bundle finalization failed: {exc}", file=sys.stderr)
        return 1
    print(attestation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
