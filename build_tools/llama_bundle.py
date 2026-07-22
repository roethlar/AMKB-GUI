"""Verify, build, inspect, and attest the pinned llama.cpp runtime.

This helper accepts only the committed source archive hash and never downloads
source or model weights.  Builds are native and offline after the caller has
acquired the pinned archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from am_configurator import local_ai_runtime


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = ROOT / "packaging" / "llama" / "manifest.json"
COMMAND_TIMEOUT_SECONDS = 30
BUILD_TIMEOUT_SECONDS = 75 * 60
MAX_DIAGNOSTIC_CHARS = 4096
MAX_ARCHIVE_MEMBERS = 200_000
MAX_EXPANDED_BYTES = 2_000_000_000


class BundleError(RuntimeError):
    """A pinned runtime source, build, or attestation check failed."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class BuildPlan:
    configure: tuple[str, ...]
    build: tuple[str, ...]
    environment: dict[str, str]
    build_directory: Path


Runner = Callable[..., CommandResult]


def load_manifest(path: Path | str = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    try:
        return local_ai_runtime.load_manifest(path)
    except local_ai_runtime.LocalRuntimeError as exc:
        raise BundleError(str(exc)) from None


def recipe_sha256(manifest: Mapping[str, Any]) -> str:
    try:
        return local_ai_runtime.recipe_sha256(manifest)
    except local_ai_runtime.LocalRuntimeError as exc:
        raise BundleError(str(exc)) from None


def cache_key(manifest: Mapping[str, Any], platform_name: str, architecture: str) -> str:
    try:
        return local_ai_runtime.cache_key(manifest, platform_name, architecture)
    except local_ai_runtime.LocalRuntimeError as exc:
        raise BundleError(str(exc)) from None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        raise BundleError("llama.cpp source archive could not be read") from None
    return digest.hexdigest()


def verify_source_archive(path: Path | str, manifest: Mapping[str, Any]) -> None:
    try:
        validated = local_ai_runtime.validate_manifest(dict(manifest))
    except local_ai_runtime.LocalRuntimeError as exc:
        raise BundleError(str(exc)) from None
    if _sha256_file(Path(path)) != validated["source"]["sha256"]:
        raise BundleError("llama.cpp source archive hash did not match")


def _validated_members(
    members: Sequence[tarfile.TarInfo],
    manifest: Mapping[str, Any],
) -> tuple[tarfile.TarInfo, ...]:
    if not members or len(members) > MAX_ARCHIVE_MEMBERS:
        raise BundleError("llama.cpp source archive layout was invalid")
    root_name = manifest["source"]["root"]
    total_size = 0
    root_found = False
    cmake_found = False
    license_found = False
    validated = []
    for member in members:
        if not member.name or "\\" in member.name or "\x00" in member.name:
            raise BundleError("llama.cpp source archive contained an unsafe path")
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.parts[0] != root_name
        ):
            raise BundleError("llama.cpp source archive contained an unsafe path")
        if not (member.isdir() or member.isreg()) or member.size < 0:
            raise BundleError("llama.cpp source archive contained an unsafe entry")
        total_size += member.size
        if total_size > MAX_EXPANDED_BYTES:
            raise BundleError("llama.cpp source archive exceeded its expansion limit")
        root_found |= len(path.parts) == 1 and member.isdir()
        cmake_found |= path.parts == (root_name, "CMakeLists.txt") and member.isreg()
        license_found |= path.parts == (root_name, "LICENSE") and member.isreg()
        validated.append(member)
    if not root_found or not cmake_found or not license_found:
        raise BundleError("llama.cpp source archive layout was invalid")
    return tuple(validated)


def extract_source_archive(
    archive_path: Path | str,
    destination: Path | str,
    manifest: Mapping[str, Any],
) -> Path:
    """Extract one rooted archive without links, devices, or path traversal."""

    try:
        validated_manifest = local_ai_runtime.validate_manifest(dict(manifest))
    except local_ai_runtime.LocalRuntimeError as exc:
        raise BundleError(str(exc)) from None
    destination_path = Path(destination).expanduser().resolve()
    if os.path.lexists(destination_path):
        raise BundleError("llama.cpp extraction destination must be fresh")
    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.mkdir(mode=0o700)
        if os.name != "nt":
            os.chmod(destination_path, 0o700)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = _validated_members(archive.getmembers(), validated_manifest)
            for member in members:
                relative = PurePosixPath(member.name)
                target = destination_path.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(
                        parents=True,
                        exist_ok=True,
                        mode=(member.mode & 0o777) | 0o700,
                    )
                    continue
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                source = archive.extractfile(member)
                if source is None:
                    raise BundleError("llama.cpp source member could not be read")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                flags |= getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                with source, os.fdopen(
                    os.open(target, flags, member.mode & 0o777), "wb"
                ) as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if target.stat().st_size != member.size:
                    raise BundleError("llama.cpp source member size was invalid")
    except BundleError:
        shutil.rmtree(destination_path, ignore_errors=True)
        raise
    except (OSError, EOFError, tarfile.TarError):
        shutil.rmtree(destination_path, ignore_errors=True)
        raise BundleError("llama.cpp source archive could not be extracted safely") from None
    return destination_path / validated_manifest["source"]["root"]


def _default_runner(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    try:
        completed = subprocess.run(
            tuple(str(item) for item in args),
            cwd=cwd,
            env=None if env is None else dict(env),
            timeout=timeout,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        raise BundleError("llama.cpp command exceeded its timeout") from None
    except OSError:
        raise BundleError("llama.cpp command could not start") from None
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _run_checked(
    runner: Runner,
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    try:
        result = runner(tuple(str(item) for item in args), cwd=cwd, env=env, timeout=timeout)
    except BundleError:
        raise
    except Exception:
        raise BundleError("llama.cpp command failed") from None
    if not isinstance(result, CommandResult):
        raise BundleError("llama.cpp runner returned invalid output")
    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout)[-MAX_DIAGNOSTIC_CHARS:].strip()
        message = "llama.cpp command failed"
        if diagnostic:
            message += ": " + diagnostic
        raise BundleError(message)
    return result


def build_plan(
    source: Path | str,
    build_directory: Path | str,
    manifest: Mapping[str, Any],
    *,
    platform_name: str,
    architecture: str,
) -> BuildPlan:
    source_path = Path(source).resolve()
    build_path = Path(build_directory).resolve()
    target = f"{platform_name}-{architecture}"
    try:
        platform_args = manifest["platforms"][target]
        local_ai_runtime.validate_manifest(dict(manifest))
    except (KeyError, local_ai_runtime.LocalRuntimeError):
        raise BundleError("llama.cpp build target is unsupported") from None
    prefix_map = f"-ffile-prefix-map={source_path}=/usr/src/llama.cpp"
    debug_map = f"-fdebug-prefix-map={source_path}=/usr/src/llama.cpp"
    configure = (
        "cmake",
        "-S",
        str(source_path),
        "-B",
        str(build_path),
        *manifest["common_cmake_args"],
        *platform_args,
        f"-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG {prefix_map} {debug_map}",
        f"-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG {prefix_map} {debug_map}",
    )
    build = (
        "cmake",
        "--build",
        str(build_path),
        "--config",
        "Release",
        "--target",
        *manifest["build_targets"],
        "--parallel",
    )
    environment = dict(os.environ)
    environment["SOURCE_DATE_EPOCH"] = str(manifest["source_date_epoch"])
    return BuildPlan(configure, build, environment, build_path)


def inspect_runtime(
    runtime: local_ai_runtime.RuntimePaths,
    manifest: Mapping[str, Any],
    *,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    try:
        validated = local_ai_runtime.validate_manifest(dict(manifest))
    except local_ai_runtime.LocalRuntimeError as exc:
        raise BundleError(str(exc)) from None
    capabilities: dict[str, bool] = {}
    for label, binary, flags in (
        ("cli", runtime.cli, validated["required_cli_flags"]),
        ("server", runtime.server, validated["required_server_flags"]),
    ):
        version_result = _run_checked(runner, (str(binary), "--version"))
        version = version_result.stdout + "\n" + version_result.stderr
        expected_build = validated["runtime_version"].removeprefix("b")
        expected_commit = validated["revision"][:7]
        if re.search(
            rf"(?m)^version:\s+{expected_build}\s+\({expected_commit}\)\s*$",
            version,
        ) is None:
            raise BundleError("llama.cpp runtime version did not match")
        help_result = _run_checked(runner, (str(binary), "--help"))
        help_text = help_result.stdout + "\n" + help_result.stderr
        for flag in flags:
            key = f"{label}:{flag}"
            capabilities[key] = flag in help_text
            if not capabilities[key]:
                raise BundleError(f"llama.cpp runtime is missing required {label} flag")
    return {
        "runtime_version": validated["runtime_version"],
        "revision": validated["revision"],
        "capabilities": capabilities,
    }


def _atomic_json(path: Path, value: object) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def emit_runtime_attestation(
    runtime: local_ai_runtime.RuntimePaths,
    destination: Path | str,
    manifest: Mapping[str, Any],
    inspection: Mapping[str, Any],
    *,
    compiler_identity: str,
    platform_name: str,
    architecture: str,
) -> dict[str, Any]:
    try:
        validated = local_ai_runtime.validate_manifest(dict(manifest))
        local_ai_runtime.cache_key(validated, platform_name, architecture)
    except local_ai_runtime.LocalRuntimeError as exc:
        raise BundleError(str(exc)) from None
    expected_capabilities = {
        *(f"cli:{flag}" for flag in validated["required_cli_flags"]),
        *(f"server:{flag}" for flag in validated["required_server_flags"]),
    }
    capabilities = inspection.get("capabilities")
    if (
        not isinstance(compiler_identity, str)
        or not compiler_identity.strip()
        or len(compiler_identity) > 1000
        or inspection.get("runtime_version") != validated["runtime_version"]
        or inspection.get("revision") != validated["revision"]
        or not isinstance(capabilities, Mapping)
        or set(capabilities) != expected_capabilities
        or any(value is not True for value in capabilities.values())
    ):
        raise BundleError("llama.cpp inspection cannot produce an attestation")
    attestation = {
        "schema_version": validated["runtime_attestation_schema_version"],
        "runtime_version": validated["runtime_version"],
        "revision": validated["revision"],
        "platform": platform_name,
        "architecture": architecture,
        "compiler_identity": compiler_identity.strip(),
        "recipe_sha256": recipe_sha256(validated),
        "capabilities": dict(capabilities),
        "files": {
            "cli": _sha256_file(runtime.cli),
            "server": _sha256_file(runtime.server),
        },
    }
    try:
        _atomic_json(Path(destination), attestation)
    except OSError:
        raise BundleError("llama.cpp attestation could not be written") from None
    return attestation


def _built_binary(
    build_directory: Path,
    name: str,
    platform_name: str,
) -> Path:
    filename = name + (".exe" if platform_name == "windows" else "")
    candidates = (
        build_directory / "bin" / filename,
        build_directory / "bin" / "Release" / filename,
    )
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise BundleError("llama.cpp build did not produce the required binaries")


def _compiler_identity(build_directory: Path) -> str:
    for path in sorted(
        (build_directory / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake")
    ):
        try:
            text = path.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        identity = None
        version = None
        for line in text.splitlines():
            if line.startswith("set(CMAKE_CXX_COMPILER_ID "):
                identity = line.split('"', 2)[1]
            elif line.startswith("set(CMAKE_CXX_COMPILER_VERSION "):
                version = line.split('"', 2)[1]
        if identity and version:
            return f"{identity} {version}"
    raise BundleError("llama.cpp compiler identity was unavailable")


def build_runtime(
    source_archive: Path | str,
    destination: Path | str,
    manifest: Mapping[str, Any],
    *,
    platform_name: str,
    architecture: str,
    runner: Runner = _default_runner,
) -> local_ai_runtime.RuntimePaths:
    """Build and atomically publish a fresh attested native runtime."""

    validated = load_manifest(DEFAULT_MANIFEST_PATH)
    if dict(manifest) != validated:
        raise BundleError("llama.cpp build requires the committed manifest")
    verify_source_archive(source_archive, validated)
    destination_path = Path(destination).expanduser().resolve()
    if os.path.lexists(destination_path):
        raise BundleError("llama.cpp runtime destination must be fresh")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    working = Path(
        tempfile.mkdtemp(prefix=".llama-build-", dir=destination_path.parent)
    )
    try:
        source = extract_source_archive(
            source_archive,
            working / "source",
            validated,
        )
        plan = build_plan(
            source,
            working / "build",
            validated,
            platform_name=platform_name,
            architecture=architecture,
        )
        _run_checked(
            runner,
            plan.configure,
            cwd=working,
            env=plan.environment,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        _run_checked(
            runner,
            plan.build,
            cwd=working,
            env=plan.environment,
            timeout=BUILD_TIMEOUT_SECONDS,
        )
        publish = working / "publish"
        binary_root = publish / "bin"
        binary_root.mkdir(parents=True, mode=0o700)
        names = validated["binaries"]
        cli_source = _built_binary(plan.build_directory, names["cli"], platform_name)
        server_source = _built_binary(
            plan.build_directory, names["server"], platform_name
        )
        suffix = ".exe" if platform_name == "windows" else ""
        runtime = local_ai_runtime.RuntimePaths(
            cli=binary_root / (names["cli"] + suffix),
            server=binary_root / (names["server"] + suffix),
        )
        shutil.copy2(cli_source, runtime.cli)
        shutil.copy2(server_source, runtime.server)
        if os.name != "nt":
            runtime.cli.chmod(0o755)
            runtime.server.chmod(0o755)
        inspection = inspect_runtime(runtime, validated, runner=runner)
        emit_runtime_attestation(
            runtime,
            binary_root / "llama-runtime.json",
            validated,
            inspection,
            compiler_identity=_compiler_identity(plan.build_directory),
            platform_name=platform_name,
            architecture=architecture,
        )
        local_ai_runtime.verify_runtime_attestation(
            binary_root,
            validated,
            platform_name=platform_name,
            architecture=architecture,
        )
        os.replace(publish, destination_path)
        return local_ai_runtime.verify_runtime_attestation(
            destination_path / "bin",
            validated,
            platform_name=platform_name,
            architecture=architecture,
        )
    except BundleError:
        raise
    except (OSError, local_ai_runtime.LocalRuntimeError):
        raise BundleError("llama.cpp runtime could not be published") from None
    finally:
        shutil.rmtree(working, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify-source")
    verify.add_argument("source_archive", type=Path)
    build = subparsers.add_parser("build")
    build.add_argument("source_archive", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument(
        "--platform", choices=("macos", "linux", "windows"), required=True
    )
    build.add_argument("--architecture", choices=("arm64", "x86_64"), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = load_manifest()
    verify_source_archive(args.source_archive, manifest)
    if args.command == "verify-source":
        print(json.dumps({"source_verified": True}, indent=2))
        return 0
    runtime = build_runtime(
        args.source_archive,
        args.output,
        manifest,
        platform_name=args.platform,
        architecture=args.architecture,
    )
    print(
        json.dumps(
            {"cli": str(runtime.cli), "server": str(runtime.server)}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BuildPlan",
    "BundleError",
    "CommandResult",
    "build_plan",
    "build_runtime",
    "cache_key",
    "emit_runtime_attestation",
    "extract_source_archive",
    "inspect_runtime",
    "load_manifest",
    "recipe_sha256",
    "verify_source_archive",
]
