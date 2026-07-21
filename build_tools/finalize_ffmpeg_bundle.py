"""Re-attest the final macOS FFmpeg binary after PyInstaller code signing."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from build_tools import ffmpeg_bundle


ROOT = Path(__file__).resolve().parents[1]


def finalize_macos_app(app_path: Path | str) -> Path:
    app = Path(app_path).resolve(strict=True)
    if not app.is_dir() or app.suffix != ".app":
        raise ffmpeg_bundle.BundleError("macOS application bundle is invalid")
    contents = app / "Contents"
    binary = contents / "Frameworks" / "ffmpeg" / "ffmpeg"
    attestation = contents / "Resources" / "ffmpeg" / "ffmpeg-runtime.json"
    manifest_path = contents / "Resources" / "ffmpeg" / "manifest.json"
    if binary.is_symlink() or not binary.is_file():
        raise ffmpeg_bundle.BundleError("bundled FFmpeg executable is invalid")
    if attestation.is_symlink() or not attestation.is_file():
        raise ffmpeg_bundle.BundleError("bundled FFmpeg attestation is invalid")
    try:
        previous = json.loads(attestation.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ffmpeg_bundle.BundleError("bundled FFmpeg attestation could not be read") from None
    compiler_identity = previous.get("compiler_identity") if isinstance(previous, dict) else None
    if not isinstance(compiler_identity, str) or not compiler_identity:
        raise ffmpeg_bundle.BundleError("bundled FFmpeg compiler identity is invalid")
    machine = platform.machine().lower()
    architecture = "arm64" if machine in {"arm64", "aarch64"} else "x86_64" if machine in {"x86_64", "amd64"} else ""
    if not architecture:
        raise ffmpeg_bundle.BundleError("current macOS architecture is unsupported")
    manifest = ffmpeg_bundle.load_manifest(manifest_path)
    inspection = ffmpeg_bundle.inspect_runtime(binary, manifest)
    ffmpeg_bundle.emit_runtime_attestation(
        binary,
        attestation,
        manifest,
        inspection,
        compiler_identity=compiler_identity,
        platform_name="macos",
        architecture=architecture,
    )
    ffmpeg_bundle.verify_runtime_attestation(
        binary,
        attestation,
        manifest,
        platform_name="macos",
        architecture=architecture,
    )
    return attestation


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    args = parser.parse_args(argv)
    try:
        attestation = finalize_macos_app(args.app)
    except (ffmpeg_bundle.BundleError, OSError) as exc:
        print(f"FFmpeg bundle finalization failed: {exc}", file=sys.stderr)
        return 1
    print(attestation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
