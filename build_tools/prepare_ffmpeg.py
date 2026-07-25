"""Prepare the verified, current-host FFmpeg runtime used by native builds.

This command never downloads source. A caller must stage the pinned release
archive and detached signature under ``build/ffmpeg/sources`` (or pass explicit
paths). Existing attested cache entries are verified and reused.
"""
from __future__ import annotations

import argparse
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from build_tools import ffmpeg_bundle


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "packaging" / "ffmpeg" / "manifest.json"
PUBLIC_KEY_PATH = ROOT / "packaging" / "ffmpeg" / "ffmpeg-devel.asc"


def _host_target() -> tuple[str, str]:
    platform_name = (
        "macos" if sys.platform == "darwin"
        else "windows" if sys.platform == "win32"
        else "linux" if sys.platform.startswith("linux")
        else ""
    )
    machine = platform.machine().lower()
    architecture = "x86_64" if machine in {"amd64", "x86_64"} else "arm64" if machine in {"aarch64", "arm64"} else ""
    if not platform_name or not architecture:
        raise ffmpeg_bundle.BundleError("current platform does not support the bundled FFmpeg runtime")
    return platform_name, architecture


def _runner_with_environment(
    extra_environment: Mapping[str, str],
    *,
    msys2_bash: Path | None = None,
    msys2_gpg: Path | None = None,
):
    def run(args, *, cwd=None, env=None, timeout=ffmpeg_bundle.COMMAND_TIMEOUT_SECONDS):
        environment = dict(os.environ)
        environment.update(extra_environment)
        if env is not None:
            environment.update(env)
        command = tuple(str(value) for value in args)
        if (
            msys2_bash is not None
            and msys2_gpg is not None
            and command
            and Path(command[0]) == msys2_gpg
        ):
            gpg_arguments = tuple(
                ffmpeg_bundle._msys_path(Path(value))
                if Path(value).is_absolute()
                else value
                for value in command[1:]
            )
            gnupg_home = ffmpeg_bundle._msys_path(
                Path(environment["GNUPGHOME"])
            )
            command = (
                str(msys2_bash),
                "--noprofile",
                "--norc",
                "-lc",
                (
                    "export PATH=/usr/bin:/mingw64/bin:$PATH && "
                    f"export GNUPGHOME={shlex.quote(gnupg_home)} && "
                    "exec "
                    + " ".join(
                        shlex.quote(value)
                        for value in (
                            ffmpeg_bundle._msys_path(msys2_gpg),
                            *gpg_arguments,
                        )
                    )
                ),
            )
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                timeout=timeout,
                check=False,
                capture_output=True,
                text=True,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ffmpeg_bundle.BundleError("FFmpeg preparation command failed") from None
        return ffmpeg_bundle.CommandResult(completed.returncode, completed.stdout, completed.stderr)

    return run


def prepare_current_host(
    *,
    root: Path = ROOT,
    archive: Path | None = None,
    signature: Path | None = None,
    public_key: Path | None = None,
    gpg: Path | str = "gpg",
    jobs: int | None = None,
    msys2_bash: Path | None = None,
    tool_paths: Mapping[str, Path] | None = None,
) -> Path:
    root = root.resolve()
    manifest_path = root / "packaging" / "ffmpeg" / "manifest.json"
    manifest = ffmpeg_bundle.load_manifest(manifest_path)
    platform_name, architecture = _host_target()
    cache = root / "build" / "ffmpeg" / ffmpeg_bundle.cache_key(manifest, platform_name, architecture)
    binary_name = "ffmpeg.exe" if platform_name == "windows" else "ffmpeg"
    binary = cache / "bin" / binary_name
    attestation = binary.with_name("ffmpeg-runtime.json")
    if binary.exists() or attestation.exists():
        ffmpeg_bundle.verify_runtime_attestation(
            binary,
            attestation,
            manifest,
            platform_name=platform_name,
            architecture=architecture,
        )
        print(binary)
        return binary

    source_dir = root / "build" / "ffmpeg" / "sources"
    archive = (archive or source_dir / Path(manifest["source"]["url"]).name).resolve()
    signature = (signature or source_dir / Path(manifest["source"]["signature_url"]).name).resolve()
    public_key = (public_key or root / "packaging" / "ffmpeg" / "ffmpeg-devel.asc").resolve()
    for path, label in ((archive, "source archive"), (signature, "detached signature"), (public_key, "release public key")):
        if not path.is_file():
            raise ffmpeg_bundle.BundleError(f"FFmpeg {label} is not staged: {path}")
    gpg_path = shutil.which(str(gpg)) if not Path(gpg).is_absolute() else str(gpg)
    if not gpg_path:
        raise ffmpeg_bundle.BundleError("GnuPG is required to verify the FFmpeg release signature")

    with tempfile.TemporaryDirectory(prefix="am-ffmpeg-prepare-") as temporary:
        temporary_root = Path(temporary)
        gnupg_home = temporary_root / "gnupg"
        gnupg_home.mkdir(mode=0o700)
        runner = _runner_with_environment(
            {"GNUPGHOME": str(gnupg_home)},
            msys2_bash=msys2_bash if platform_name == "windows" else None,
            msys2_gpg=Path(gpg_path) if platform_name == "windows" else None,
        )
        imported = runner((str(gpg_path), "--batch", "--import", str(public_key)))
        if imported.returncode != 0:
            raise ffmpeg_bundle.BundleError("FFmpeg release public key could not be imported")
        built = ffmpeg_bundle.build_verified_archive(
            archive,
            signature,
            temporary_root / "source",
            cache,
            manifest,
            runner=runner,
            jobs=jobs or min(8, max(1, os.cpu_count() or 2)),
            platform_name=platform_name,
            architecture=architecture,
            msys2_bash=msys2_bash,
            tool_paths=tool_paths,
            gpg=gpg_path,
        )
    print(built)
    return built


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--gpg", default="gpg")
    parser.add_argument("--jobs", type=int)
    parser.add_argument("--msys2-bash", type=Path)
    for role in ("cc", "ar", "ranlib", "strip"):
        parser.add_argument(f"--{role}", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    supplied_tools = {role: getattr(args, role) for role in ("cc", "ar", "ranlib", "strip")}
    tool_paths = None
    if any(path is not None for path in supplied_tools.values()):
        if any(path is None for path in supplied_tools.values()):
            _parser().error("--cc, --ar, --ranlib, and --strip must be supplied together")
        tool_paths = supplied_tools
    try:
        prepare_current_host(
            archive=args.archive,
            signature=args.signature,
            public_key=args.public_key,
            gpg=args.gpg,
            jobs=args.jobs,
            msys2_bash=args.msys2_bash,
            tool_paths=tool_paths,
        )
    except ffmpeg_bundle.BundleError as exc:
        print(f"FFmpeg preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
