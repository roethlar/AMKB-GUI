"""Resolve and verify the bundled FFmpeg runtime without searching ``PATH``."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import sys
from pathlib import Path
from typing import Mapping


PINNED_MANIFEST_SHA256 = (
    "c28ae7f1078a398669620303c8174cb6531097033c2b49d0c1142ce7a162a619"
)
MAX_FFMPEG_JSON_BYTES = 64 * 1024
MAX_FFMPEG_FILE_BYTES = 1024 * 1024 * 1024
SOURCE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST_PATH = SOURCE_ROOT / "packaging" / "ffmpeg" / "manifest.json"
_MANIFEST_KEYS = {
    "schema_version",
    "ffmpeg_version",
    "source",
    "source_date_epoch",
    "runtime_attestation_schema_version",
    "build_recipe",
    "configure_args",
    "required_capabilities",
}
_ATTESTATION_KEYS = {
    "schema_version",
    "ffmpeg_version",
    "platform",
    "architecture",
    "compiler_identity",
    "recipe_sha256",
    "configure_args",
    "reported_configure_args",
    "capabilities",
    "binary_sha256",
}
_CAPABILITY_CATEGORIES = (
    "decoders",
    "parsers",
    "encoders",
    "demuxers",
    "muxers",
    "protocols",
    "filters",
)
_DANGEROUS_REPORTED_FLAGS = {
    "--enable-gpl",
    "--enable-nonfree",
    "--enable-version3",
    "--enable-network",
    "--enable-shared",
    "--enable-everything",
    "--enable-autodetect",
    "--enable-ffplay",
    "--enable-ffprobe",
    "--enable-avdevice",
    "--enable-swresample",
    "--disable-static",
}
_BUILD_RECIPE_KEYS = {
    "build_prefix",
    "source_prefix",
    "prefix_arg",
    "architecture_arg",
    "target_os_args",
    "architecture_extra_args",
    "tool_args",
    "cflags",
    "ldflags",
    "make_target",
    "tool_roles",
}


class FfmpegRuntimeError(RuntimeError):
    """The prepared runtime is absent or does not match its attestation."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


def _regular_file_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
        getattr(details, "st_file_attributes", 0),
    )


def _is_reparse_point(details: os.stat_result) -> bool:
    attributes = getattr(details, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _read_verified_regular_file(
    path: Path | str,
    *,
    max_bytes: int,
    hash_only: bool,
) -> bytes | str:
    """Read one stable regular file without following a link or exceeding a cap."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("FFmpeg verification size limit must be a positive integer")
    candidate = Path(path)
    descriptor: int | None = None
    stage = "metadata"
    try:
        before = candidate.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or _is_reparse_point(before)
            or before.st_size < 0
            or before.st_size > max_bytes
        ):
            raise OSError
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        flags |= getattr(os, "O_NOFOLLOW", 0)
        stage = "open"
        descriptor = os.open(candidate, flags)
        stage = "opened_identity"
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse_point(opened)
            or opened.st_size < 0
            or opened.st_size > max_bytes
            or _regular_file_identity(before) != _regular_file_identity(opened)
        ):
            raise OSError
        digest = hashlib.sha256() if hash_only else None
        payload = bytearray() if not hash_only else None
        total = 0
        stage = "read"
        while block := os.read(descriptor, min(1024 * 1024, max_bytes - total + 1)):
            total += len(block)
            if total > max_bytes:
                raise OSError
            if digest is not None:
                digest.update(block)
            else:
                assert payload is not None
                payload.extend(block)
        stage = "final_identity"
        after_opened = os.fstat(descriptor)
        after_path = candidate.lstat()
        if (
            total != opened.st_size
            or not stat.S_ISREG(after_path.st_mode)
            or _is_reparse_point(after_path)
            or _regular_file_identity(opened) != _regular_file_identity(after_opened)
            or _regular_file_identity(opened) != _regular_file_identity(after_path)
        ):
            raise OSError
        if digest is not None:
            return digest.hexdigest()
        assert payload is not None
        return bytes(payload)
    except OSError:
        raise FfmpegRuntimeError(
            "FFmpeg verification file could not be read",
            reason=stage,
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_bounded_json(
    path: Path | str,
    *,
    max_bytes: int = MAX_FFMPEG_JSON_BYTES,
) -> object:
    raw = _read_verified_regular_file(path, max_bytes=max_bytes, hash_only=False)
    assert isinstance(raw, bytes)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise FfmpegRuntimeError("FFmpeg JSON file could not be read") from None


def sha256_file(
    path: Path | str,
    *,
    max_bytes: int = MAX_FFMPEG_FILE_BYTES,
) -> str:
    digest = _read_verified_regular_file(path, max_bytes=max_bytes, hash_only=True)
    assert isinstance(digest, str)
    return digest


def load_manifest(path: Path | str) -> dict:
    """Load only the byte-for-byte pinned runtime manifest."""
    try:
        raw = _read_verified_regular_file(
            path,
            max_bytes=MAX_FFMPEG_JSON_BYTES,
            hash_only=False,
        )
    except FfmpegRuntimeError:
        raise FfmpegRuntimeError("FFmpeg runtime manifest is unavailable") from None
    assert isinstance(raw, bytes)
    if hashlib.sha256(raw).hexdigest() != PINNED_MANIFEST_SHA256:
        raise FfmpegRuntimeError("FFmpeg runtime manifest was not the pinned recipe")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise FfmpegRuntimeError("FFmpeg runtime manifest was invalid") from None
    _validate_manifest_shape(manifest)
    return manifest


def _validate_manifest_shape(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _MANIFEST_KEYS:
        raise FfmpegRuntimeError("FFmpeg runtime manifest schema was invalid")
    if (
        value.get("schema_version") != 2
        or not isinstance(value.get("ffmpeg_version"), str)
        or value.get("runtime_attestation_schema_version") != 1
        or not isinstance(value.get("source_date_epoch"), int)
        or not isinstance(value.get("configure_args"), list)
        or not all(isinstance(item, str) for item in value["configure_args"])
    ):
        raise FfmpegRuntimeError("FFmpeg runtime manifest schema was invalid")
    source = value.get("source")
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is None
    ):
        raise FfmpegRuntimeError("FFmpeg runtime manifest source was invalid")
    capabilities = value.get("required_capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != set(_CAPABILITY_CATEGORIES):
        raise FfmpegRuntimeError("FFmpeg runtime manifest capabilities were invalid")
    if any(
        not isinstance(capabilities[category], list)
        or not capabilities[category]
        or not all(isinstance(name, str) and name for name in capabilities[category])
        for category in _CAPABILITY_CATEGORIES
    ):
        raise FfmpegRuntimeError("FFmpeg runtime manifest capabilities were invalid")
    recipe = value.get("build_recipe")
    if not isinstance(recipe, dict) or set(recipe) != _BUILD_RECIPE_KEYS:
        raise FfmpegRuntimeError("FFmpeg runtime build recipe was invalid")
    if any(
        not isinstance(recipe.get(name), str) or not recipe[name]
        for name in (
            "build_prefix",
            "source_prefix",
            "prefix_arg",
            "architecture_arg",
            "make_target",
        )
    ):
        raise FfmpegRuntimeError("FFmpeg runtime build recipe was invalid")
    string_maps = ("target_os_args", "tool_args")
    list_maps = ("architecture_extra_args", "ldflags")
    if any(
        not isinstance(recipe.get(name), dict)
        or not recipe[name]
        or any(not isinstance(key, str) or not isinstance(item, str) or not item for key, item in recipe[name].items())
        for name in string_maps
    ):
        raise FfmpegRuntimeError("FFmpeg runtime build recipe was invalid")
    if any(
        not isinstance(recipe.get(name), dict)
        or not recipe[name]
        or any(
            not isinstance(key, str)
            or not isinstance(items, list)
            or any(not isinstance(item, str) or not item for item in items)
            for key, items in recipe[name].items()
        )
        for name in list_maps
    ):
        raise FfmpegRuntimeError("FFmpeg runtime build recipe was invalid")
    for name in ("cflags", "tool_roles"):
        items = recipe.get(name)
        if not isinstance(items, list) or not items or any(
            not isinstance(item, str) or not item for item in items
        ):
            raise FfmpegRuntimeError("FFmpeg runtime build recipe was invalid")
    return value


def recipe_sha256(manifest: Mapping[str, object]) -> str:
    manifest = _validate_manifest_shape(manifest)
    recipe = {
        "ffmpeg_version": manifest["ffmpeg_version"],
        "source_date_epoch": manifest["source_date_epoch"],
        "build_recipe": manifest["build_recipe"],
        "configure_args": manifest["configure_args"],
        "required_capabilities": manifest["required_capabilities"],
        "runtime_attestation_schema_version": manifest[
            "runtime_attestation_schema_version"
        ],
    }
    encoded = json.dumps(
        recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def cache_key(manifest: Mapping[str, object], platform_name: str, architecture: str) -> str:
    manifest = _validate_manifest_shape(manifest)
    _validate_target(platform_name, architecture)
    return "-".join(
        (
            "ffmpeg",
            manifest["ffmpeg_version"],
            platform_name,
            architecture,
            manifest["source"]["sha256"],
            recipe_sha256(manifest),
        )
    )


def _capability_keys(manifest: Mapping[str, object]) -> set[str]:
    capabilities = manifest["required_capabilities"]
    return {
        f"{category}:{name}"
        for category in _CAPABILITY_CATEGORIES
        for name in capabilities[category]
    }


def verify_runtime_attestation(
    binary: Path | str,
    attestation_path: Path | str,
    manifest: Mapping[str, object],
    *,
    platform_name: str,
    architecture: str,
) -> dict:
    manifest = _validate_manifest_shape(manifest)
    _validate_target(platform_name, architecture)
    try:
        attestation = read_bounded_json(attestation_path)
    except FfmpegRuntimeError:
        raise FfmpegRuntimeError("FFmpeg runtime attestation could not be read") from None
    capabilities = attestation.get("capabilities") if isinstance(attestation, dict) else None
    reported_args = (
        attestation.get("reported_configure_args") if isinstance(attestation, dict) else None
    )
    expected_target = {
        name: value for name, value in manifest["build_recipe"]["target_os_args"].items()
    }[platform_name]
    recipe = manifest["build_recipe"]
    required_reported = {
        recipe["prefix_arg"].format(build_prefix=recipe["build_prefix"]),
        recipe["architecture_arg"].format(architecture=architecture),
        expected_target,
        *recipe["architecture_extra_args"][architecture],
    }
    tool_prefixes = tuple(
        recipe["tool_args"][role].split("{path}", 1)[0]
        for role in recipe["tool_roles"]
    )
    valid = (
        isinstance(attestation, dict)
        and set(attestation) == _ATTESTATION_KEYS
        and attestation["schema_version"] == manifest["runtime_attestation_schema_version"]
        and attestation["ffmpeg_version"] == manifest["ffmpeg_version"]
        and attestation["platform"] == platform_name
        and attestation["architecture"] == architecture
        and isinstance(attestation["compiler_identity"], str)
        and bool(attestation["compiler_identity"].strip())
        and len(attestation["compiler_identity"]) <= 1000
        and attestation["recipe_sha256"] == recipe_sha256(manifest)
        and attestation["configure_args"] == manifest["configure_args"]
        and isinstance(reported_args, list)
        and all(isinstance(arg, str) and arg.startswith("--") for arg in reported_args)
        and len(reported_args) == len(set(reported_args))
        and set(manifest["configure_args"]).issubset(set(reported_args))
        and required_reported.issubset(set(reported_args))
        and not set(reported_args).intersection(_DANGEROUS_REPORTED_FLAGS)
        and all(
            any(arg.startswith(prefix + "/") for arg in reported_args)
            for prefix in tool_prefixes
        )
        and isinstance(capabilities, dict)
        and set(capabilities) == _capability_keys(manifest)
        and all(value is True for value in capabilities.values())
        and isinstance(attestation["binary_sha256"], str)
        and re.fullmatch(r"[0-9a-f]{64}", attestation["binary_sha256"]) is not None
    )
    if not valid or sha256_file(binary) != attestation["binary_sha256"]:
        raise FfmpegRuntimeError("FFmpeg runtime attestation did not match the binary")
    return attestation


def _validate_target(platform_name: str, architecture: str) -> None:
    if platform_name not in {"macos", "linux", "windows"}:
        raise FfmpegRuntimeError("FFmpeg runtime platform is unsupported")
    if architecture not in {"x86_64", "arm64"}:
        raise FfmpegRuntimeError("FFmpeg runtime architecture is unsupported")
    if platform_name in {"linux", "windows"} and architecture != "x86_64":
        raise FfmpegRuntimeError("FFmpeg runtime target is unsupported")


def _host_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    raise FfmpegRuntimeError("current platform does not support bundled FFmpeg")


def _host_architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise FfmpegRuntimeError("current architecture does not support bundled FFmpeg")


def _verify_candidate(
    value: Path | str,
    manifest: Mapping[str, object],
    *,
    platform_name: str,
    architecture: str,
) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise FfmpegRuntimeError("FFmpeg runtime path must be absolute")
    if candidate.is_symlink():
        raise FfmpegRuntimeError("FFmpeg runtime path must not be a symlink")
    try:
        candidate = candidate.resolve(strict=True)
    except OSError:
        raise FfmpegRuntimeError("FFmpeg runtime path is missing") from None
    if not candidate.is_file():
        raise FfmpegRuntimeError("FFmpeg runtime path is not a file")
    if os.name != "nt" and not os.access(candidate, os.X_OK):
        raise FfmpegRuntimeError("FFmpeg runtime path is not executable")
    attestation = candidate.with_name("ffmpeg-runtime.json")
    if attestation.is_symlink():
        frozen_value = getattr(sys, "_MEIPASS", None)
        if frozen_value is None:
            raise FfmpegRuntimeError("FFmpeg runtime attestation must not be a symlink")
        try:
            frozen_root = Path(frozen_value).resolve(strict=True)
            candidate.relative_to(frozen_root)
            resolved_attestation = attestation.resolve(strict=True)
            allowed_roots = [frozen_root]
            if frozen_root.name == "Frameworks":
                allowed_roots.append(frozen_root.parent / "Resources")
            if not any(
                resolved_attestation.is_relative_to(root.resolve(strict=True))
                for root in allowed_roots
                if root.is_dir()
            ):
                raise ValueError
            if not resolved_attestation.is_file():
                raise ValueError
        except (OSError, ValueError):
            raise FfmpegRuntimeError(
                "FFmpeg runtime attestation symlink leaves the frozen bundle"
            ) from None
        attestation = resolved_attestation
    verify_runtime_attestation(
        candidate,
        attestation,
        manifest,
        platform_name=platform_name,
        architecture=architecture,
    )
    return candidate


def resolve_ffmpeg(
    *,
    manifest: Mapping[str, object],
    injected: Path | str | None = None,
    environment: Mapping[str, str] | None = None,
    development_root: Path | str | None = None,
    bundle_root: Path | str | None = None,
    platform_name: str | None = None,
    architecture: str | None = None,
) -> Path:
    """Resolve injected, override, prepared cache, or PyInstaller paths in order."""
    manifest = _validate_manifest_shape(manifest)
    platform_name = _host_platform() if platform_name is None else platform_name
    architecture = _host_architecture() if architecture is None else architecture
    _validate_target(platform_name, architecture)
    environment = os.environ if environment is None else environment
    binary_name = "ffmpeg.exe" if platform_name == "windows" else "ffmpeg"
    if injected is not None:
        return _verify_candidate(
            injected, manifest, platform_name=platform_name, architecture=architecture
        )
    override = environment.get("AM_CONFIGURATOR_FFMPEG")
    if override:
        return _verify_candidate(
            override, manifest, platform_name=platform_name, architecture=architecture
        )
    if development_root is not None:
        cached = (
            Path(development_root)
            / cache_key(manifest, platform_name, architecture)
            / "bin"
            / binary_name
        )
        if cached.exists() or cached.is_symlink():
            return _verify_candidate(
                cached, manifest, platform_name=platform_name, architecture=architecture
            )
    if bundle_root is None:
        frozen_root = getattr(sys, "_MEIPASS", None)
        bundle_root = None if frozen_root is None else Path(frozen_root)
    if bundle_root is not None:
        bundled = Path(bundle_root) / "ffmpeg" / binary_name
        if bundled.exists() or bundled.is_symlink():
            return _verify_candidate(
                bundled, manifest, platform_name=platform_name, architecture=architecture
            )
    raise FfmpegRuntimeError("verified bundled FFmpeg runtime is unavailable")


def _frozen_manifest_path(frozen_root: Path) -> Path:
    candidate = frozen_root / "ffmpeg" / "manifest.json"
    if not candidate.is_symlink():
        return candidate
    try:
        resolved_root = frozen_root.resolve(strict=True)
        if resolved_root.name != "Frameworks":
            raise ValueError
        resources = (resolved_root.parent / "Resources").resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        if not resolved_candidate.is_relative_to(resources):
            raise ValueError
        if not resolved_candidate.is_file():
            raise ValueError
    except (OSError, ValueError):
        raise FfmpegRuntimeError(
            "FFmpeg runtime manifest symlink leaves the frozen bundle"
        ) from None
    return resolved_candidate


def get_ffmpeg_runtime(
    *,
    injected: Path | str | None = None,
    environment: Mapping[str, str] | None = None,
    development_root: Path | str | None = None,
    bundle_root: Path | str | None = None,
    platform_name: str | None = None,
    architecture: str | None = None,
) -> Path:
    """Locate the pinned manifest, then resolve a verified executable.

    Source checkouts own ``packaging/ffmpeg/manifest.json`` and default to their
    prepared ``build/ffmpeg`` cache. Frozen builds own both the manifest and
    executable under PyInstaller's bundle roots. A macOS metadata symlink is
    accepted only when it resolves from ``Frameworks`` into the sibling
    ``Resources`` directory. No build-tool package or system ``PATH`` lookup is
    involved.
    """
    frozen_value = getattr(sys, "_MEIPASS", None)
    frozen_root = None if frozen_value is None else Path(frozen_value)
    manifest_path = (
        SOURCE_MANIFEST_PATH
        if frozen_root is None
        else _frozen_manifest_path(frozen_root)
    )
    manifest = load_manifest(manifest_path)
    if development_root is None and frozen_root is None:
        development_root = SOURCE_ROOT / "build" / "ffmpeg"
    if bundle_root is None and frozen_root is not None:
        bundle_root = frozen_root
    return resolve_ffmpeg(
        manifest=manifest,
        injected=injected,
        environment=environment,
        development_root=development_root,
        bundle_root=bundle_root,
        platform_name=platform_name,
        architecture=architecture,
    )


__all__ = [
    "FfmpegRuntimeError",
    "PINNED_MANIFEST_SHA256",
    "cache_key",
    "get_ffmpeg_runtime",
    "load_manifest",
    "recipe_sha256",
    "resolve_ffmpeg",
    "verify_runtime_attestation",
]
