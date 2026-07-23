"""Bind the final macOS FFmpeg signature to its verified prepared runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from build_tools import ffmpeg_bundle


ROOT = Path(__file__).resolve().parents[1]
_PROVENANCE_SCHEMA_VERSION = 1
_MAX_ATTESTATION_BYTES = 64 * 1024
_COMMAND_TIMEOUT_SECONDS = 30
Runner = Callable[..., ffmpeg_bundle.CommandResult]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(args, *, timeout: int = _COMMAND_TIMEOUT_SECONDS) -> ffmpeg_bundle.CommandResult:
    try:
        completed = subprocess.run(
            tuple(str(value) for value in args),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ffmpeg_bundle.BundleError("macOS FFmpeg signing command failed") from None
    return ffmpeg_bundle.CommandResult(
        completed.returncode,
        completed.stdout,
        completed.stderr,
    )


def _read_bounded_json(path: Path, label: str) -> dict:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError
        if path.stat().st_size > _MAX_ATTESTATION_BYTES:
            raise ValueError
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise ffmpeg_bundle.BundleError(f"{label} could not be read") from None


def _atomic_json(path: Path, value: dict) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, raw_temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(raw_temporary)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _codesign_details(binary: Path, *, runner: Runner) -> tuple[str, str, str]:
    verified = runner(
        (
            "/usr/bin/codesign",
            "--verify",
            "--all-architectures",
            "--strict",
            str(binary),
        ),
        timeout=_COMMAND_TIMEOUT_SECONDS,
    )
    if verified.returncode != 0:
        raise ffmpeg_bundle.BundleError("bundled FFmpeg code signature was invalid")
    described = runner(
        ("/usr/bin/codesign", "-d", "--verbose=4", str(binary)),
        timeout=_COMMAND_TIMEOUT_SECONDS,
    )
    if described.returncode != 0:
        raise ffmpeg_bundle.BundleError("bundled FFmpeg code signature was unavailable")
    output = (described.stdout + "\n" + described.stderr)[-_MAX_ATTESTATION_BYTES:]
    identifier_match = re.search(r"(?m)^Identifier=([^\r\n]{1,200})$", output)
    cdhash_match = re.search(r"(?mi)^CDHash=([0-9a-f]{40}|[0-9a-f]{64})$", output)
    signature_match = re.search(r"(?m)^Signature=([^\r\n]{1,200})$", output)
    authorities = re.findall(r"(?m)^Authority=([^\r\n]{1,500})$", output)
    if identifier_match is None or cdhash_match is None or signature_match is None:
        raise ffmpeg_bundle.BundleError("bundled FFmpeg code identity was invalid")
    signature = signature_match.group(1).strip()
    identity = "adhoc" if signature == "adhoc" else authorities[0].strip() if authorities else ""
    if not identity:
        raise ffmpeg_bundle.BundleError("bundled FFmpeg signing identity was invalid")
    return identifier_match.group(1), identity, cdhash_match.group(1).lower()


def finalize_macos_app(
    app_path: Path | str,
    *,
    root: Path = ROOT,
    runner: Runner = _run,
) -> Path:
    app = Path(app_path).resolve(strict=True)
    root = root.resolve(strict=True)
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
    machine = platform.machine().lower()
    architecture = "arm64" if machine in {"arm64", "aarch64"} else "x86_64" if machine in {"x86_64", "amd64"} else ""
    if not architecture:
        raise ffmpeg_bundle.BundleError("current macOS architecture is unsupported")
    manifest = ffmpeg_bundle.load_manifest(manifest_path)
    cache = (
        root
        / "build"
        / "ffmpeg"
        / ffmpeg_bundle.cache_key(manifest, "macos", architecture)
        / "bin"
    )
    prepared_binary = cache / "ffmpeg"
    prepared_attestation_path = cache / "ffmpeg-runtime.json"
    prepared = ffmpeg_bundle.verify_runtime_attestation(
        prepared_binary,
        prepared_attestation_path,
        manifest,
        platform_name="macos",
        architecture=architecture,
    )
    bundled_previous = _read_bounded_json(
        attestation,
        "bundled FFmpeg prepared attestation",
    )
    if bundled_previous != prepared:
        raise ffmpeg_bundle.BundleError(
            "bundled FFmpeg was not paired with its prepared attestation"
        )

    with tempfile.TemporaryDirectory(prefix="am-ffmpeg-signing-") as temporary:
        expected_binary = Path(temporary) / "ffmpeg"
        shutil.copyfile(prepared_binary, expected_binary, follow_symlinks=False)
        signed = runner(
            (
                "/usr/bin/codesign",
                "-s",
                "-",
                "--force",
                "--all-architectures",
                "--timestamp",
                str(expected_binary),
            ),
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
        if signed.returncode != 0:
            raise ffmpeg_bundle.BundleError(
                "prepared FFmpeg signing projection could not be created"
            )
        expected_signed_sha256 = _sha256_file(expected_binary)

    prepared_sha256 = prepared["binary_sha256"]
    signed_sha256 = _sha256_file(binary)
    if signed_sha256 != expected_signed_sha256:
        raise ffmpeg_bundle.BundleError(
            "bundled FFmpeg was not the signed prepared executable"
        )
    code_identifier, signing_identity, cdhash = _codesign_details(
        binary,
        runner=runner,
    )
    signed_attestation = dict(prepared)
    signed_attestation["binary_sha256"] = signed_sha256
    candidate_attestation = attestation.with_name(".ffmpeg-runtime.signed.json")
    try:
        _atomic_json(candidate_attestation, signed_attestation)
        ffmpeg_bundle.verify_runtime_attestation(
            binary,
            candidate_attestation,
            manifest,
            platform_name="macos",
            architecture=architecture,
        )
        os.replace(candidate_attestation, attestation)
    finally:
        candidate_attestation.unlink(missing_ok=True)

    provenance = {
        "schema_version": _PROVENANCE_SCHEMA_VERSION,
        "platform": "macos",
        "architecture": architecture,
        "prepared_binary_sha256": prepared_sha256,
        "prepared_attestation_sha256": _sha256_file(prepared_attestation_path),
        "signed_binary_sha256": signed_sha256,
        "signing_identity": signing_identity,
        "code_identifier": code_identifier,
        "cdhash": cdhash,
        "manifest_sha256": _sha256_file(manifest_path),
        "recipe_sha256": prepared["recipe_sha256"],
        "configure_args": list(prepared["configure_args"]),
        "reported_configure_args": list(prepared["reported_configure_args"]),
        "capabilities": dict(prepared["capabilities"]),
    }
    provenance_path = attestation.with_name("ffmpeg-signing.json")
    _atomic_json(provenance_path, provenance)
    return provenance_path


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
