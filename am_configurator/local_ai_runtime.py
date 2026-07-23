"""Resolve and attest the transitional packaged llama.cpp artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


PINNED_MANIFEST_SHA256 = (
    "3f4f2c0f5c7d71ace34cddcfb6030a696a30dbaf029d9a17868bd50299fa3319"
)
SOURCE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST_PATH = SOURCE_ROOT / "packaging" / "llama" / "manifest.json"
MAX_RUNTIME_ATTESTATION_BYTES = 64 * 1024
_MANIFEST_KEYS = {
    "schema_version",
    "runtime_version",
    "revision",
    "source",
    "source_date_epoch",
    "license",
    "runtime_attestation_schema_version",
    "binaries",
    "common_cmake_args",
    "platforms",
    "build_targets",
    "required_cli_flags",
    "required_server_flags",
}
_SOURCE_KEYS = {"url", "sha256", "root"}
_LICENSE_KEYS = {"spdx", "file", "source_url"}
_BINARY_KEYS = {"cli", "server"}
_ATTESTATION_KEYS = {
    "schema_version",
    "runtime_version",
    "revision",
    "platform",
    "architecture",
    "compiler_identity",
    "recipe_sha256",
    "capabilities",
    "files",
}
_SUPPORTED_TARGETS = {
    ("macos", "arm64"): "macos-arm64",
    ("linux", "x86_64"): "linux-x86_64",
    ("windows", "x86_64"): "windows-x86_64",
}


class LocalRuntimeError(RuntimeError):
    """The transitional packaged runtime artifacts are unavailable or invalid."""


@dataclass(frozen=True)
class RuntimePaths:
    cli: Path
    server: Path


def _exact_dict(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise LocalRuntimeError("Local runtime manifest schema is invalid.")
    return value


def _string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = _exact_dict(value, _MANIFEST_KEYS)
    source = _exact_dict(manifest["source"], _SOURCE_KEYS)
    license_value = _exact_dict(manifest["license"], _LICENSE_KEYS)
    binaries = _exact_dict(manifest["binaries"], _BINARY_KEYS)
    valid = (
        manifest["schema_version"] == 1
        and manifest["runtime_version"] == "b9637"
        and manifest["revision"]
        == "aedb2a5e9ca3d4064148bbb919e0ddc0c1b70ab3"
        and source
        == {
            "url": "https://github.com/ggml-org/llama.cpp/archive/"
            "aedb2a5e9ca3d4064148bbb919e0ddc0c1b70ab3.tar.gz",
            "sha256": "3857876e4a2461f7041166bd74b5d39e3db51b8639353d55f87d6f904b3b75bd",
            "root": "llama.cpp-aedb2a5e9ca3d4064148bbb919e0ddc0c1b70ab3",
        }
        and manifest["source_date_epoch"] == 1781461060
        and license_value["spdx"] == "MIT"
        and license_value["file"] == "MIT.txt"
        and isinstance(license_value["source_url"], str)
        and license_value["source_url"].startswith("https://github.com/")
        and manifest["runtime_attestation_schema_version"] == 1
        and binaries == {"cli": "llama-cli", "server": "llama-server"}
        and _string_list(manifest["common_cmake_args"])
        and isinstance(manifest["platforms"], dict)
        and set(manifest["platforms"]) == set(_SUPPORTED_TARGETS.values())
        and all(_string_list(arguments) for arguments in manifest["platforms"].values())
        and manifest["build_targets"] == ["llama-cli", "llama-server"]
        and _string_list(manifest["required_cli_flags"])
        and _string_list(manifest["required_server_flags"])
    )
    if not valid:
        raise LocalRuntimeError("Local runtime manifest schema is invalid.")
    required_common = {
        "-DBUILD_SHARED_LIBS=OFF",
        "-DGGML_BACKEND_DL=OFF",
        "-DGGML_NATIVE=OFF",
        "-DGGML_RPC=OFF",
        "-DLLAMA_BUILD_UI=OFF",
        "-DLLAMA_USE_PREBUILT_UI=OFF",
    }
    if not required_common.issubset(set(manifest["common_cmake_args"])):
        raise LocalRuntimeError("Local runtime build recipe is invalid.")
    if "-DGGML_METAL=ON" not in manifest["platforms"]["macos-arm64"]:
        raise LocalRuntimeError("Local runtime build recipe is invalid.")
    for target in ("linux-x86_64", "windows-x86_64"):
        if "-DGGML_VULKAN=ON" not in manifest["platforms"][target]:
            raise LocalRuntimeError("Local runtime build recipe is invalid.")
    return manifest


def load_manifest(path: Path | str = SOURCE_MANIFEST_PATH) -> dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
    except OSError:
        raise LocalRuntimeError("Local runtime manifest is unavailable.") from None
    if hashlib.sha256(raw).hexdigest() != PINNED_MANIFEST_SHA256:
        raise LocalRuntimeError("Local runtime manifest is not the pinned recipe.")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise LocalRuntimeError("Local runtime manifest is invalid.") from None
    return validate_manifest(value)


def recipe_sha256(manifest: Mapping[str, Any]) -> str:
    validated = validate_manifest(dict(manifest))
    encoded = json.dumps(
        validated,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _target_key(platform_name: str, architecture: str) -> str:
    try:
        return _SUPPORTED_TARGETS[(platform_name, architecture)]
    except KeyError:
        raise LocalRuntimeError("Local runtime target is unsupported.") from None


def cache_key(manifest: Mapping[str, Any], platform_name: str, architecture: str) -> str:
    target = _target_key(platform_name, architecture)
    validated = validate_manifest(dict(manifest))
    return "-".join(
        (
            "llama",
            validated["runtime_version"],
            target,
            recipe_sha256(validated),
        )
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise OSError
        descriptor = os.open(path, flags)
    except OSError:
        raise LocalRuntimeError("Local runtime file could not be read.") from None
    try:
        opened = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
        )
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
            raise LocalRuntimeError("Local runtime file changed during verification.")
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        if identity(opened) != identity(os.fstat(descriptor)):
            raise LocalRuntimeError("Local runtime file changed during verification.")
        return digest.hexdigest()
    except OSError:
        raise LocalRuntimeError("Local runtime file could not be read.") from None
    finally:
        os.close(descriptor)


def _read_runtime_attestation(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_size > MAX_RUNTIME_ATTESTATION_BYTES
            ):
                raise ValueError
            raw = source.read(MAX_RUNTIME_ATTESTATION_BYTES + 1)
            if len(raw) > MAX_RUNTIME_ATTESTATION_BYTES:
                raise ValueError
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise LocalRuntimeError("Local runtime attestation is invalid.") from None
    if not isinstance(value, dict):
        raise LocalRuntimeError("Local runtime attestation is invalid.")
    return value


def _binary_names(manifest: Mapping[str, Any], platform_name: str) -> dict[str, str]:
    suffix = ".exe" if platform_name == "windows" else ""
    return {name: value + suffix for name, value in manifest["binaries"].items()}


def _runtime_paths(root: Path, manifest: Mapping[str, Any], platform_name: str) -> RuntimePaths:
    names = _binary_names(manifest, platform_name)
    return RuntimePaths(cli=root / names["cli"], server=root / names["server"])


def _capability_keys(manifest: Mapping[str, Any]) -> set[str]:
    return {
        *(f"cli:{flag}" for flag in manifest["required_cli_flags"]),
        *(f"server:{flag}" for flag in manifest["required_server_flags"]),
    }


def verify_runtime_attestation(
    root: Path | str,
    manifest: Mapping[str, Any],
    *,
    platform_name: str,
    architecture: str,
    metadata_symlink_root: Path | str | None = None,
) -> RuntimePaths:
    validated = validate_manifest(dict(manifest))
    _target_key(platform_name, architecture)
    root_path = Path(root).expanduser()
    if not root_path.is_absolute() or root_path.is_symlink():
        raise LocalRuntimeError("Local runtime directory is unsafe.")
    try:
        root_path = root_path.resolve(strict=True)
    except OSError:
        raise LocalRuntimeError("Local runtime directory is unavailable.") from None
    if not root_path.is_dir():
        raise LocalRuntimeError("Local runtime directory is unavailable.")
    paths = _runtime_paths(root_path, validated, platform_name)
    for binary in (paths.cli, paths.server):
        if binary.is_symlink() or not binary.is_file():
            raise LocalRuntimeError("Local runtime binary is unavailable.")
        if os.name != "nt" and not os.access(binary, os.X_OK):
            raise LocalRuntimeError("Local runtime binary is not executable.")
    attestation_path = root_path / "llama-runtime.json"
    if attestation_path.is_symlink():
        if metadata_symlink_root is None:
            raise LocalRuntimeError("Local runtime attestation is invalid.")
        try:
            allowed_root = Path(metadata_symlink_root).resolve(strict=True)
            resolved_attestation = attestation_path.resolve(strict=True)
        except OSError:
            raise LocalRuntimeError("Local runtime attestation is invalid.") from None
        if allowed_root != resolved_attestation and allowed_root not in resolved_attestation.parents:
            raise LocalRuntimeError("Local runtime attestation is invalid.")
        attestation_path = resolved_attestation
    attestation = _read_runtime_attestation(attestation_path)
    capabilities = attestation.get("capabilities")
    files = attestation.get("files")
    expected_files = {
        "cli": _sha256_file(paths.cli),
        "server": _sha256_file(paths.server),
    }
    valid = (
        isinstance(attestation, dict)
        and set(attestation) == _ATTESTATION_KEYS
        and attestation["schema_version"]
        == validated["runtime_attestation_schema_version"]
        and attestation["runtime_version"] == validated["runtime_version"]
        and attestation["revision"] == validated["revision"]
        and attestation["platform"] == platform_name
        and attestation["architecture"] == architecture
        and isinstance(attestation["compiler_identity"], str)
        and bool(attestation["compiler_identity"].strip())
        and len(attestation["compiler_identity"]) <= 1000
        and attestation["recipe_sha256"] == recipe_sha256(validated)
        and isinstance(capabilities, dict)
        and set(capabilities) == _capability_keys(validated)
        and all(value is True for value in capabilities.values())
        and files == expected_files
    )
    if not valid:
        raise LocalRuntimeError("Local runtime attestation does not match its files.")
    return paths


def _host_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    raise LocalRuntimeError("Current platform does not support the local runtime.")


def _host_architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"amd64", "x86_64"}:
        return "x86_64"
    raise LocalRuntimeError("Current architecture does not support the local runtime.")


def resolve_runtime(
    *,
    manifest: Mapping[str, Any],
    injected: Path | str | None = None,
    environment: Mapping[str, str] | None = None,
    development_root: Path | str | None = None,
    bundle_root: Path | str | None = None,
    platform_name: str | None = None,
    architecture: str | None = None,
) -> RuntimePaths:
    validated = validate_manifest(dict(manifest))
    platform_name = _host_platform() if platform_name is None else platform_name
    architecture = _host_architecture() if architecture is None else architecture
    _target_key(platform_name, architecture)
    environment = os.environ if environment is None else environment
    candidates: list[tuple[Path, Path | None]] = []
    if injected is not None:
        candidates.append((Path(injected), None))
    else:
        override = environment.get("AM_CONFIGURATOR_LLAMA_RUNTIME")
        if override:
            candidates.append((Path(override), None))
        if development_root is not None:
            candidates.append((
                Path(development_root)
                / cache_key(validated, platform_name, architecture)
                / "bin",
                None,
            ))
        if bundle_root is not None:
            bundle = Path(bundle_root)
            candidates.append((bundle / "llama", bundle.parent))
    for candidate, metadata_root in candidates:
        if candidate.exists() or candidate.is_symlink():
            return verify_runtime_attestation(
                candidate,
                validated,
                platform_name=platform_name,
                architecture=architecture,
                metadata_symlink_root=metadata_root,
            )
    raise LocalRuntimeError("Verified local runtime is unavailable.")


def get_local_ai_runtime(
    *,
    injected: Path | str | None = None,
    environment: Mapping[str, str] | None = None,
    development_root: Path | str | None = None,
    bundle_root: Path | str | None = None,
    platform_name: str | None = None,
    architecture: str | None = None,
) -> RuntimePaths:
    frozen_value = getattr(sys, "_MEIPASS", None)
    frozen_root = None if frozen_value is None else Path(frozen_value)
    manifest_path = (
        SOURCE_MANIFEST_PATH
        if frozen_root is None
        else frozen_root / "llama" / "manifest.json"
    )
    manifest = load_manifest(manifest_path)
    if development_root is None and frozen_root is None:
        development_root = SOURCE_ROOT / "build" / "llama"
    if bundle_root is None and frozen_root is not None:
        bundle_root = frozen_root
    return resolve_runtime(
        manifest=manifest,
        injected=injected,
        environment=environment,
        development_root=development_root,
        bundle_root=bundle_root,
        platform_name=platform_name,
        architecture=architecture,
    )


__all__ = [
    "LocalRuntimeError",
    "PINNED_MANIFEST_SHA256",
    "RuntimePaths",
    "cache_key",
    "get_local_ai_runtime",
    "load_manifest",
    "recipe_sha256",
    "resolve_runtime",
    "validate_manifest",
    "verify_runtime_attestation",
]
