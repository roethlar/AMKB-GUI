"""Verify, build, attest, and resolve the pinned LGPL FFmpeg runtime.

This helper never downloads source or discovers a system ``ffmpeg`` through
``PATH``. Network acquisition is deliberately outside the helper: callers hand
it the pinned archive and detached signature, and it performs a fresh safe
extraction before building.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator, Mapping, Sequence

from am_configurator import ffmpeg_runtime


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = ROOT / "packaging" / "ffmpeg" / "manifest.json"
DEFAULT_RELEASE_KEY_PATH = ROOT / "packaging" / "ffmpeg" / "ffmpeg-devel.asc"
COMMAND_TIMEOUT_SECONDS = 30
BUILD_TIMEOUT_SECONDS = 75 * 60
MAX_DIAGNOSTIC_CHARS = 4096

_PINNED_VERSION = "8.1.2"
_PINNED_SOURCE_URL = "https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz"
_PINNED_SOURCE_SHA256 = (
    "464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c"
)
_PINNED_RELEASE_FINGERPRINT = "FCF986EA15E6E293A5644F10B4322F04D67658D8"
_PINNED_SOURCE_DATE_EPOCH = 1781664417
_SOURCE_ROOT_NAME = "ffmpeg-8.1.2"

_CONFIGURE_ARGS = (
    "--disable-everything",
    "--disable-autodetect",
    "--disable-gpl",
    "--disable-nonfree",
    "--disable-version3",
    "--enable-ffmpeg",
    "--disable-ffplay",
    "--disable-ffprobe",
    "--disable-doc",
    "--disable-debug",
    "--disable-network",
    "--enable-static",
    "--disable-shared",
    "--enable-pic",
    "--disable-avdevice",
    "--disable-swresample",
    "--enable-zlib",
    "--enable-demuxer=mov",
    "--enable-decoder=h264,mpeg4,hevc",
    "--enable-parser=h264,mpeg4video,hevc",
    "--enable-encoder=png",
    "--enable-muxer=image2",
    "--enable-protocol=file",
    "--enable-filter=trim,setpts,minterpolate,scale,crop,format,fps",
)

_REQUIRED_CAPABILITIES = {
    "decoders": ("h264", "mpeg4", "hevc"),
    "parsers": ("h264", "mpeg4video", "hevc"),
    "encoders": ("png",),
    "demuxers": ("mov",),
    "muxers": ("image2",),
    "protocols": ("file",),
    "filters": ("trim", "setpts", "minterpolate", "scale", "crop", "format", "fps"),
}
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

_BUILD_RECIPE = {
    "build_prefix": "/usr/local/am-configurator-ffmpeg",
    "source_prefix": "/usr/src/ffmpeg-8.1.2",
    "prefix_arg": "--prefix={build_prefix}",
    "architecture_arg": "--arch={architecture}",
    "target_os_args": {
        "macos": "--target-os=darwin",
        "linux": "--target-os=linux",
        "windows": "--target-os=mingw32",
    },
    "architecture_extra_args": {
        "x86_64": ["--disable-x86asm"],
        "arm64": [],
    },
    "tool_args": {
        "cc": "--cc={path}",
        "ar": "--ar={path}",
        "ranlib": "--ranlib={path}",
        "strip": "--strip={path}",
    },
    "cflags": [
        "-O2",
        "-ffile-prefix-map={source_dir}={source_prefix}",
        "-fdebug-prefix-map={source_dir}={source_prefix}",
    ],
    "ldflags": {
        "macos": ["-Wl,-dead_strip"],
        "linux": ["-Wl,--gc-sections"],
        "windows": ["-Wl,--gc-sections"],
    },
    "make_target": "ffmpeg",
    "tool_roles": ["cc", "ar", "ranlib", "strip"],
}

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
_SOURCE_KEYS = {"url", "signature_url", "sha256", "release_key_fingerprint"}
_PLATFORMS = {"macos", "linux", "windows"}
_ARCHITECTURES = {"x86_64", "arm64"}


class BundleError(RuntimeError):
    """A deterministic, path-safe bundle validation or build failure."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CommandSpec:
    args: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    timeout: int


Runner = Callable[..., CommandResult]


def _require_exact_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise BundleError(f"{label} does not match the supported schema")
    return value


def validate_manifest(value: object) -> dict:
    """Validate the committed recipe without accepting silent extensions."""
    manifest = _require_exact_keys(value, _MANIFEST_KEYS, "FFmpeg manifest")
    if manifest["schema_version"] != 2:
        raise BundleError("FFmpeg manifest schema version is unsupported")
    if manifest["ffmpeg_version"] != _PINNED_VERSION:
        raise BundleError("FFmpeg version does not match the pinned release")
    source = _require_exact_keys(manifest["source"], _SOURCE_KEYS, "FFmpeg source")
    if source != {
        "url": _PINNED_SOURCE_URL,
        "signature_url": _PINNED_SOURCE_URL + ".asc",
        "sha256": _PINNED_SOURCE_SHA256,
        "release_key_fingerprint": _PINNED_RELEASE_FINGERPRINT,
    }:
        raise BundleError("FFmpeg source metadata does not match the pinned release")
    if manifest["source_date_epoch"] != _PINNED_SOURCE_DATE_EPOCH:
        raise BundleError("FFmpeg SOURCE_DATE_EPOCH does not match the pinned release")
    if manifest["runtime_attestation_schema_version"] != 1:
        raise BundleError("FFmpeg runtime attestation schema is unsupported")
    if manifest["build_recipe"] != _BUILD_RECIPE:
        raise BundleError("FFmpeg native build recipe does not match the pinned recipe")
    if manifest["configure_args"] != list(_CONFIGURE_ARGS):
        raise BundleError("FFmpeg configure recipe does not match the LGPL-only recipe")
    capabilities = _require_exact_keys(
        manifest["required_capabilities"],
        set(_REQUIRED_CAPABILITIES),
        "FFmpeg capabilities",
    )
    for category, expected in _REQUIRED_CAPABILITIES.items():
        if capabilities[category] != list(expected):
            raise BundleError(f"FFmpeg {category} do not match the minimal recipe")
    return manifest


def load_manifest(path: Path | str = DEFAULT_MANIFEST_PATH) -> dict:
    parsed = read_bounded_json(path, "FFmpeg manifest")
    return validate_manifest(parsed)


def read_bounded_json(path: Path | str, label: str) -> object:
    try:
        return ffmpeg_runtime.read_bounded_json(path)
    except ffmpeg_runtime.FfmpegRuntimeError:
        raise BundleError(f"{label} could not be read") from None


def recipe_sha256(manifest: Mapping[str, object]) -> str:
    validate_manifest(manifest)
    try:
        return ffmpeg_runtime.recipe_sha256(manifest)
    except ffmpeg_runtime.FfmpegRuntimeError:
        raise BundleError("FFmpeg recipe could not be hashed") from None


def cache_key(manifest: Mapping[str, object], platform_name: str, architecture: str) -> str:
    validate_manifest(manifest)
    try:
        return ffmpeg_runtime.cache_key(manifest, platform_name, architecture)
    except ffmpeg_runtime.FfmpegRuntimeError:
        raise BundleError("FFmpeg cache target is unsupported") from None


def sha256_file(path: Path | str) -> str:
    try:
        return ffmpeg_runtime.sha256_file(path)
    except ffmpeg_runtime.FfmpegRuntimeError:
        raise BundleError("FFmpeg file could not be read") from None


def verify_source_archive(path: Path | str, manifest: Mapping[str, object]) -> None:
    source = manifest.get("source") if isinstance(manifest, Mapping) else None
    if not isinstance(source, Mapping) or not isinstance(source.get("sha256"), str):
        raise BundleError("FFmpeg source hash metadata is invalid")
    expected = source["sha256"]
    if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise BundleError("FFmpeg source hash metadata is invalid")
    if sha256_file(path) != expected:
        raise BundleError("FFmpeg source archive hash did not match")


def _validated_tar_members(members: Sequence[tarfile.TarInfo]) -> tuple[tarfile.TarInfo, ...]:
    if not members or len(members) > 100_000:
        raise BundleError("FFmpeg source archive layout was invalid")
    total_size = 0
    root_found = False
    configure_found = False
    validated: list[tarfile.TarInfo] = []
    for member in members:
        name = member.name
        if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
            raise BundleError("FFmpeg source archive contained an unsafe path")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or not path.parts
            or any(
                part in {"", ".", ".."} or ":" in part
                for part in path.parts
            )
        ):
            raise BundleError("FFmpeg source archive contained an unsafe path")
        if path.parts[0] != _SOURCE_ROOT_NAME:
            raise BundleError("FFmpeg source archive contained an unexpected root")
        if not (member.isdir() or member.isreg()):
            raise BundleError("FFmpeg source archive contained an unsafe entry type")
        if member.size < 0:
            raise BundleError("FFmpeg source archive contained an invalid size")
        total_size += member.size
        if total_size > 1_000_000_000:
            raise BundleError("FFmpeg source archive expanded beyond its safety limit")
        if len(path.parts) == 1 and member.isdir():
            root_found = True
        if path.parts == (_SOURCE_ROOT_NAME, "configure") and member.isreg():
            configure_found = True
        validated.append(member)
    if not root_found or not configure_found:
        raise BundleError("FFmpeg source archive layout was invalid")
    return tuple(validated)


def extract_source_archive(archive_path: Path | str, destination: Path | str) -> Path:
    """Privately extract the single pinned FFmpeg source root without links."""
    archive_path = Path(archive_path)
    destination = Path(destination).expanduser().resolve()
    if os.path.lexists(destination):
        raise BundleError("FFmpeg source extraction destination must be fresh")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(mode=0o700)
        if os.name != "nt":
            os.chmod(destination, 0o700)
        with tarfile.open(archive_path, mode="r:xz") as archive:
            members = _validated_tar_members(archive.getmembers())
            for member in members:
                relative = PurePosixPath(member.name)
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(mode=member.mode & 0o777, parents=True, exist_ok=True)
                    if os.name != "nt":
                        os.chmod(target, member.mode & 0o777)
                    continue
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise BundleError("FFmpeg source archive file could not be read")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                flags |= getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                with source, os.fdopen(os.open(target, flags, member.mode & 0o777), "wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                if target.stat().st_size != member.size:
                    raise BundleError("FFmpeg source archive file size was invalid")
                if os.name != "nt":
                    os.chmod(target, member.mode & 0o777)
    except BundleError:
        try:
            shutil.rmtree(destination)
        except OSError:
            pass
        raise
    except (OSError, EOFError, tarfile.TarError):
        try:
            shutil.rmtree(destination)
        except OSError:
            pass
        raise BundleError("FFmpeg source archive could not be extracted safely") from None
    return destination / _SOURCE_ROOT_NAME


def _default_runner(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> CommandResult:
    try:
        completed = subprocess.run(
            tuple(str(value) for value in args),
            cwd=cwd,
            env=None if env is None else dict(env),
            timeout=timeout,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        raise BundleError("FFmpeg command exceeded its bounded timeout") from None
    except OSError:
        raise BundleError("FFmpeg command could not be started") from None
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
        result = runner(tuple(str(value) for value in args), cwd=cwd, env=env, timeout=timeout)
    except BundleError:
        raise
    except Exception:
        raise BundleError("FFmpeg command failed") from None
    if not isinstance(result, CommandResult):
        raise BundleError("FFmpeg runner returned an invalid result")
    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout)[-MAX_DIAGNOSTIC_CHARS:].strip()
        message = "FFmpeg command failed"
        if diagnostic:
            message += ": " + diagnostic
        raise BundleError(message)
    return result


@contextmanager
def _isolated_gpg_runner(
    public_key: Path | str,
    gpg: Path | str,
) -> Iterator[tuple[Runner, str]]:
    """Import the pinned release key into one private, ephemeral keyring."""
    candidate = Path(public_key).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise BundleError("FFmpeg release public key is unavailable")
    key = candidate.resolve()
    gpg_text = str(gpg)
    gpg_path = gpg_text if Path(gpg_text).is_absolute() else shutil.which(gpg_text)
    if not gpg_path:
        raise BundleError("GnuPG is required to verify the FFmpeg release signature")

    with tempfile.TemporaryDirectory(prefix="am-ffmpeg-gpg-") as temporary:
        keyring = Path(temporary) / "gnupg"
        keyring.mkdir(mode=0o700)
        if os.name != "nt":
            keyring.chmod(0o700)

        def isolated_runner(
            args: Sequence[str],
            *,
            cwd: Path | None = None,
            env: Mapping[str, str] | None = None,
            timeout: int = COMMAND_TIMEOUT_SECONDS,
        ) -> CommandResult:
            environment = dict(os.environ)
            if env is not None:
                environment.update(env)
            environment["GNUPGHOME"] = str(keyring)
            return _default_runner(args, cwd=cwd, env=environment, timeout=timeout)

        _run_checked(
            isolated_runner,
            (str(gpg_path), "--batch", "--import", str(key)),
        )
        yield isolated_runner, str(gpg_path)


def verify_source_signature(
    archive: Path | str,
    signature: Path | str,
    manifest: Mapping[str, object],
    *,
    runner: Runner = _default_runner,
    gpg: Path | str = "gpg",
) -> None:
    source = manifest.get("source") if isinstance(manifest, Mapping) else None
    if not isinstance(source, Mapping):
        raise BundleError("FFmpeg signature metadata is invalid")
    fingerprint = source.get("release_key_fingerprint")
    if not isinstance(fingerprint, str) or re.fullmatch(r"[A-F0-9]{40}", fingerprint) is None:
        raise BundleError("FFmpeg signature fingerprint is invalid")
    result = _run_checked(
        runner,
        (
            str(gpg),
            "--batch",
            "--no-auto-key-retrieve",
            "--status-fd",
            "1",
            "--verify",
            str(signature),
            str(archive),
        ),
    )
    fingerprints = re.findall(r"(?m)^\[GNUPG:\] VALIDSIG ([A-F0-9]{40})(?:\s|$)", result.stdout)
    if fingerprints != [fingerprint]:
        raise BundleError("FFmpeg detached signature did not match the release key")


def _capability_keys(manifest: Mapping[str, object]) -> tuple[str, ...]:
    capabilities = manifest["required_capabilities"]
    return tuple(
        f"{category}:{name}"
        for category in _REQUIRED_CAPABILITIES
        for name in capabilities[category]  # type: ignore[index]
    )


def inspect_runtime(
    binary: Path | str,
    manifest: Mapping[str, object],
    *,
    runner: Runner = _default_runner,
) -> dict:
    validate_manifest(manifest)
    binary_text = str(binary)
    version = _run_checked(runner, (binary_text, "-version")).stdout
    if re.search(
        rf"(?m)^ffmpeg version {re.escape(str(manifest['ffmpeg_version']))}(?:\s|$)",
        version,
    ) is None:
        raise BundleError("FFmpeg runtime version did not match the manifest")
    buildconf = _run_checked(runner, (binary_text, "-buildconf")).stdout
    reported_args: list[str] = []
    for line in buildconf.splitlines():
        stripped = line.strip()
        if not stripped.startswith("--"):
            continue
        try:
            parsed = shlex.split(stripped)
        except ValueError:
            raise BundleError("FFmpeg runtime configure output was invalid") from None
        if len(parsed) != 1:
            raise BundleError("FFmpeg runtime configure output was invalid")
        reported_args.append(parsed[0])
    reported_set = set(reported_args)
    if not set(manifest["configure_args"]).issubset(reported_set):
        raise BundleError("FFmpeg runtime configure flags did not match the manifest")
    if reported_set.intersection(_DANGEROUS_REPORTED_FLAGS):
        raise BundleError("FFmpeg runtime reported a forbidden configure flag")

    switches = {
        "decoders": "-decoders",
        "encoders": "-encoders",
        "demuxers": "-demuxers",
        "muxers": "-muxers",
        "protocols": "-protocols",
        "filters": "-filters",
    }
    results: dict[str, bool] = {}
    configured_parsers: set[str] = set()
    for argument in reported_args:
        if argument.startswith("--enable-parser="):
            configured_parsers.update(argument.split("=", 1)[1].split(","))
    for name in manifest["required_capabilities"]["parsers"]:
        key = f"parsers:{name}"
        results[key] = name in configured_parsers
        if not results[key]:
            raise BundleError(f"FFmpeg runtime is missing required parser {name}")
    for category, switch in switches.items():
        output = _run_checked(runner, (binary_text, switch)).stdout
        tokens = {
            alias
            for line in output.splitlines()
            for token in line.split()
            for alias in token.split(",")
        }
        for name in manifest["required_capabilities"][category]:
            key = f"{category}:{name}"
            results[key] = name in tokens
            if not results[key]:
                raise BundleError(f"FFmpeg runtime is missing required {category[:-1]} {name}")
    return {
        "ffmpeg_version": manifest["ffmpeg_version"],
        "configure_args": list(manifest["configure_args"]),
        "reported_configure_args": reported_args,
        "capabilities": results,
    }


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary_path = Path(temporary)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _validate_target(platform_name: str, architecture: str) -> None:
    if platform_name not in _PLATFORMS or architecture not in _ARCHITECTURES:
        raise BundleError("FFmpeg platform or architecture is unsupported")
    if platform_name in {"linux", "windows"} and architecture != "x86_64":
        raise BundleError("FFmpeg target is not one of the supported build environments")


def emit_runtime_attestation(
    binary: Path | str,
    destination: Path | str,
    manifest: Mapping[str, object],
    inspection: Mapping[str, object],
    *,
    compiler_identity: str,
    platform_name: str,
    architecture: str,
) -> dict:
    validate_manifest(manifest)
    _validate_target(platform_name, architecture)
    if not isinstance(compiler_identity, str) or not compiler_identity.strip() or len(compiler_identity) > 1000:
        raise BundleError("FFmpeg compiler identity is invalid")
    expected_keys = set(_capability_keys(manifest))
    capabilities = inspection.get("capabilities")
    reported_args = inspection.get("reported_configure_args")
    if (
        inspection.get("ffmpeg_version") != manifest["ffmpeg_version"]
        or inspection.get("configure_args") != manifest["configure_args"]
        or not isinstance(reported_args, list)
        or not all(isinstance(arg, str) and arg.startswith("--") for arg in reported_args)
        or len(reported_args) != len(set(reported_args))
        or not set(manifest["configure_args"]).issubset(set(reported_args))
        or bool(set(reported_args).intersection(_DANGEROUS_REPORTED_FLAGS))
        or not isinstance(capabilities, Mapping)
        or set(capabilities) != expected_keys
        or any(value is not True for value in capabilities.values())
    ):
        raise BundleError("FFmpeg inspection cannot produce a trusted attestation")
    attestation = {
        "schema_version": manifest["runtime_attestation_schema_version"],
        "ffmpeg_version": manifest["ffmpeg_version"],
        "platform": platform_name,
        "architecture": architecture,
        "compiler_identity": compiler_identity.strip(),
        "recipe_sha256": recipe_sha256(manifest),
        "configure_args": list(manifest["configure_args"]),
        "reported_configure_args": list(reported_args),
        "capabilities": dict(capabilities),
        "binary_sha256": sha256_file(binary),
    }
    _atomic_json(Path(destination), attestation)
    return attestation


def verify_runtime_attestation(
    binary: Path | str,
    attestation_path: Path | str,
    manifest: Mapping[str, object],
    *,
    platform_name: str,
    architecture: str,
) -> dict:
    validate_manifest(manifest)
    try:
        return ffmpeg_runtime.verify_runtime_attestation(
            binary,
            attestation_path,
            manifest,
            platform_name=platform_name,
            architecture=architecture,
        )
    except ffmpeg_runtime.FfmpegRuntimeError:
        raise BundleError("FFmpeg runtime attestation did not match the binary") from None


def _host_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    raise BundleError("current platform does not support the bundled FFmpeg runtime")


def _host_architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise BundleError("current architecture does not support the bundled FFmpeg runtime")


def _runtime_name(platform_name: str) -> str:
    return "ffmpeg.exe" if platform_name == "windows" else "ffmpeg"


def _msys_path(path: Path) -> str:
    text = str(path.resolve())
    match = re.fullmatch(r"([A-Za-z]):[\\/](.*)", text)
    if match is None:
        return text.replace("\\", "/")
    return f"/{match.group(1).lower()}/{match.group(2).replace(chr(92), '/')}"


def build_command_plan(
    source_dir: Path | str,
    output_dir: Path | str,
    manifest: Mapping[str, object],
    *,
    platform_name: str,
    architecture: str,
    jobs: int,
    msys2_bash: Path | str | None = None,
    tool_paths: Mapping[str, Path | str] | None = None,
) -> tuple[CommandSpec, ...]:
    validate_manifest(manifest)
    _validate_target(platform_name, architecture)
    if isinstance(jobs, bool) or not isinstance(jobs, int) or not 1 <= jobs <= 64:
        raise BundleError("FFmpeg build job count is invalid")
    source = Path(source_dir).resolve()
    Path(output_dir).resolve()
    try:
        source.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise BundleError(
            "FFmpeg source tree must be outside the workspace so build paths cannot leak"
        )
    tools = _resolve_build_tools(platform_name, tool_paths)
    recipe = manifest["build_recipe"]
    tool_arguments = {
        role: _msys_path(path) if platform_name == "windows" else str(path)
        for role, path in tools.items()
    }
    args = list(manifest["configure_args"])
    args.append(
        recipe["prefix_arg"].format(build_prefix=recipe["build_prefix"])
    )
    args.append(recipe["architecture_arg"].format(architecture=architecture))
    args.extend(
        recipe["tool_args"][role].format(path=tool_arguments[role])
        for role in recipe["tool_roles"]
    )
    args.extend(recipe["architecture_extra_args"][architecture])
    args.append(recipe["target_os_args"][platform_name])
    prefix_source = _msys_path(source) if platform_name == "windows" else str(source)
    if any(character.isspace() for character in prefix_source):
        raise BundleError("FFmpeg source path must not contain whitespace")
    replacements = {
        "source_dir": prefix_source,
        "source_prefix": recipe["source_prefix"],
    }
    cflags = [flag.format(**replacements) for flag in recipe["cflags"]]
    environment = {
        "SOURCE_DATE_EPOCH": str(manifest["source_date_epoch"]),
        "CFLAGS": shlex.join(cflags),
        "LDFLAGS": shlex.join(recipe["ldflags"][platform_name]),
    }
    make_command = ("make", f"-j{jobs}", recipe["make_target"])
    if platform_name != "windows":
        return (
            CommandSpec((str(source / "configure"), *args), source, environment, 10 * 60),
            CommandSpec(make_command, source, environment, BUILD_TIMEOUT_SECONDS),
        )
    if msys2_bash is None or not Path(msys2_bash).is_absolute():
        raise BundleError("Windows FFmpeg builds require an absolute MSYS2 bash path")
    msys_source = _msys_path(source)
    commands = (
        "./configure " + " ".join(shlex.quote(arg) for arg in args),
        " ".join(shlex.quote(arg) for arg in make_command),
    )
    timeouts = (10 * 60, BUILD_TIMEOUT_SECONDS)
    return tuple(
        CommandSpec(
            (
                str(msys2_bash),
                "--noprofile",
                "--norc",
                "-lc",
                (
                    "export PATH=/usr/bin:/mingw64/bin:$PATH && "
                    f"cd {shlex.quote(msys_source)} && {command}"
                ),
            ),
            source,
            environment,
            timeout,
        )
        for command, timeout in zip(commands, timeouts)
    )


def _resolve_build_tools(
    platform_name: str,
    tool_paths: Mapping[str, Path | str] | None,
) -> dict[str, Path]:
    names = {
        "cc": "gcc" if platform_name == "windows" else "cc",
        "ar": "ar",
        "ranlib": "ranlib",
        "strip": "strip",
    }
    if tool_paths is not None and set(tool_paths) != set(names):
        raise BundleError("FFmpeg build tool mapping is incomplete")
    resolved: dict[str, Path] = {}
    for role, name in names.items():
        value = tool_paths[role] if tool_paths is not None else shutil.which(name)
        if value is None:
            raise BundleError(f"required FFmpeg build tool {role} is unavailable")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise BundleError(f"FFmpeg build tool {role} must have an absolute path")
        if tool_paths is None:
            try:
                path = path.resolve(strict=True)
            except OSError:
                raise BundleError(f"required FFmpeg build tool {role} is unavailable") from None
        resolved[role] = path
    return resolved


def _compiler_identity(compiler: Path, runner: Runner) -> str:
    result = _run_checked(runner, (str(compiler), "--version"))
    output = result.stdout or result.stderr
    identity = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if not identity or len(identity) > 1000:
        raise BundleError("FFmpeg compiler identity could not be determined")
    return identity


def build_current_host(
    source_dir: Path | str,
    output_dir: Path | str,
    manifest: Mapping[str, object],
    *,
    runner: Runner = _default_runner,
    jobs: int = 2,
    platform_name: str | None = None,
    architecture: str | None = None,
    msys2_bash: Path | str | None = None,
    tool_paths: Mapping[str, Path | str] | None = None,
) -> Path:
    """Build an already verified/extracted source tree and emit its attestation."""
    platform_name = _host_platform() if platform_name is None else platform_name
    architecture = _host_architecture() if architecture is None else architecture
    output = Path(output_dir).resolve()
    tools = _resolve_build_tools(platform_name, tool_paths)
    plan = build_command_plan(
        source_dir,
        output,
        manifest,
        platform_name=platform_name,
        architecture=architecture,
        jobs=jobs,
        msys2_bash=msys2_bash,
        tool_paths=tools,
    )
    for command in plan:
        environment = dict(os.environ)
        environment.update(command.environment)
        _run_checked(
            runner,
            command.args,
            cwd=command.cwd,
            env=environment,
            timeout=command.timeout,
        )
    built_binary = Path(source_dir).resolve() / _runtime_name(platform_name)
    if not built_binary.is_file():
        raise BundleError("FFmpeg build did not produce the expected executable")
    binary = output / "bin" / _runtime_name(platform_name)
    binary.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(built_binary, binary)
    except OSError:
        raise BundleError("FFmpeg executable could not be copied into the cache") from None
    inspection = inspect_runtime(binary, manifest, runner=runner)
    compiler_identity = _compiler_identity(tools["cc"], runner)
    emit_runtime_attestation(
        binary,
        binary.with_name("ffmpeg-runtime.json"),
        manifest,
        inspection,
        compiler_identity=compiler_identity,
        platform_name=platform_name,
        architecture=architecture,
    )
    return binary


def build_verified_archive(
    archive_path: Path | str,
    signature_path: Path | str,
    extraction_directory: Path | str,
    output_directory: Path | str,
    manifest: Mapping[str, object],
    *,
    runner: Runner = _default_runner,
    jobs: int = 2,
    platform_name: str | None = None,
    architecture: str | None = None,
    msys2_bash: Path | str | None = None,
    tool_paths: Mapping[str, Path | str] | None = None,
    gpg: Path | str = "gpg",
) -> Path:
    """Verify, freshly extract, build, attest, and clean one official archive."""
    archive = Path(archive_path)
    signature = Path(signature_path)
    extraction = Path(extraction_directory).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    try:
        output.relative_to(extraction)
    except ValueError:
        pass
    else:
        raise BundleError("FFmpeg output directory must be outside its temporary source")
    verify_source_archive(archive, manifest)
    verify_source_signature(archive, signature, manifest, runner=runner, gpg=gpg)
    source: Path | None = None
    try:
        source = extract_source_archive(archive, extraction)
        return build_current_host(
            source,
            output,
            manifest,
            runner=runner,
            jobs=jobs,
            platform_name=platform_name,
            architecture=architecture,
            msys2_bash=msys2_bash,
            tool_paths=tool_paths,
        )
    finally:
        if source is not None:
            try:
                shutil.rmtree(extraction)
            except OSError:
                pass


def main(argv: Sequence[str] | None = None) -> int:
    """Offline CLI for verifying pinned source and building the current host."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify-source")
    verify_parser.add_argument("--archive", type=Path, required=True)
    verify_parser.add_argument("--signature", type=Path, required=True)
    verify_parser.add_argument("--public-key", type=Path, default=DEFAULT_RELEASE_KEY_PATH)
    verify_parser.add_argument("--gpg", default="gpg")

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--archive", type=Path, required=True)
    build_parser.add_argument("--signature", type=Path, required=True)
    build_parser.add_argument("--public-key", type=Path, default=DEFAULT_RELEASE_KEY_PATH)
    build_parser.add_argument("--extract-dir", type=Path, required=True)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--jobs", type=int, default=2)
    build_parser.add_argument("--gpg", default="gpg")
    build_parser.add_argument("--msys2-bash", type=Path)
    build_parser.add_argument("--platform", choices=sorted(_PLATFORMS))
    build_parser.add_argument("--architecture", choices=sorted(_ARCHITECTURES))
    for role in ("cc", "ar", "ranlib", "strip"):
        build_parser.add_argument(f"--{role}", type=Path)

    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)
    if args.command == "verify-source":
        with _isolated_gpg_runner(args.public_key, args.gpg) as (runner, gpg):
            verify_source_archive(args.archive, manifest)
            verify_source_signature(
                args.archive,
                args.signature,
                manifest,
                runner=runner,
                gpg=gpg,
            )
        return 0
    supplied_tools = {role: getattr(args, role) for role in ("cc", "ar", "ranlib", "strip")}
    tool_paths = None
    if any(value is not None for value in supplied_tools.values()):
        if any(value is None for value in supplied_tools.values()):
            raise BundleError("all absolute FFmpeg build tool paths must be supplied together")
        tool_paths = supplied_tools
    with _isolated_gpg_runner(args.public_key, args.gpg) as (runner, gpg):
        binary = build_verified_archive(
            args.archive,
            args.signature,
            args.extract_dir,
            args.output_dir,
            manifest,
            runner=runner,
            jobs=args.jobs,
            platform_name=args.platform,
            architecture=args.architecture,
            msys2_bash=args.msys2_bash,
            tool_paths=tool_paths,
            gpg=gpg,
        )
    print(binary)
    return 0


__all__ = [
    "BUILD_TIMEOUT_SECONDS",
    "COMMAND_TIMEOUT_SECONDS",
    "BundleError",
    "CommandResult",
    "CommandSpec",
    "build_command_plan",
    "build_current_host",
    "build_verified_archive",
    "cache_key",
    "emit_runtime_attestation",
    "extract_source_archive",
    "inspect_runtime",
    "load_manifest",
    "main",
    "recipe_sha256",
    "validate_manifest",
    "verify_runtime_attestation",
    "verify_source_archive",
    "verify_source_signature",
]


if __name__ == "__main__":
    raise SystemExit(main())
