#!/usr/bin/env python3
"""Build and smoke-test an AM Configurator installer for the current OS."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from build_tools.release_info import (
    artifact_filename,
    base_version,
    stamp_build_version,
)


PROJECT_ROOT = Path(__file__).resolve().parent
_COUNTER_FILE = ".am-configurator-build-number"
_ARTIFACT_VERSION = re.compile(
    r"^AM-Configurator-(?P<major>\d+)\.(?P<minor>\d+)\.(?P<build>\d+)-"
)
RunCommand = Callable[[list[str], Path], None]


def _version_parts(root: Path) -> tuple[int, int, int]:
    parts = base_version(root).split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Base project version must contain three numeric parts.")
    return int(parts[0]), int(parts[1]), int(parts[2])


def reserve_local_build_number(root: Path = PROJECT_ROOT) -> int:
    """Reserve the next per-clone build number without dirtying tracked files."""
    major, minor, base_build = _version_parts(root)
    candidates = [base_build]
    counter_path = root / _COUNTER_FILE
    if counter_path.is_file():
        raw_counter = counter_path.read_text(encoding="utf-8").strip()
        if not raw_counter.isdigit():
            raise ValueError(f"Local build counter is invalid: {counter_path}")
        candidates.append(int(raw_counter))

    dist = root / "dist"
    if dist.is_dir():
        for path in dist.iterdir():
            match = _ARTIFACT_VERSION.match(path.name)
            if match and (int(match["major"]), int(match["minor"])) == (major, minor):
                candidates.append(int(match["build"]))

    build_number = max(candidates) + 1
    temporary = counter_path.with_name(f"{counter_path.name}.tmp")
    temporary.write_text(f"{build_number}\n", encoding="utf-8")
    temporary.replace(counter_path)
    return build_number


def _target_for_platform(platform_name: str) -> str:
    if platform_name == "darwin":
        return "macos"
    if platform_name == "win32":
        return "windows"
    if platform_name.startswith("linux"):
        return "linux"
    raise ValueError(f"Unsupported build platform: {platform_name}")


def _packager_command(target: str, root: Path) -> list[str]:
    if target == "macos":
        return ["bash", str(root / "packaging" / "macos" / "build_dmg.sh")]
    if target == "linux":
        return ["bash", str(root / "packaging" / "linux" / "build_appimage.sh")]
    powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if powershell is None:
        raise RuntimeError("PowerShell is required to build the Windows installer.")
    return [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(root / "packaging" / "windows" / "build_installer.ps1"),
    ]


def _run(command: list[str], cwd: Path) -> None:
    print("+", subprocess.list2cmdline(command), flush=True)
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required build command was not found: {command[0]}") from exc


def build_installer(
    *,
    root: Path = PROJECT_ROOT,
    platform_name: str = sys.platform,
    build_number: int | None = None,
    sync: bool = True,
    run_command: RunCommand | None = None,
) -> Path:
    """Build the current platform's installer and return its artifact path."""
    root = root.resolve()
    target = _target_for_platform(platform_name)
    number = build_number if build_number is not None else reserve_local_build_number(root)
    runner = run_command or _run
    version_file = root / "am_configurator" / "_version.py"
    original_version = version_file.read_bytes() if version_file.is_file() else None

    try:
        version = stamp_build_version(number, root=root)
        artifact = root / "dist" / artifact_filename(target, root=root)
        print(f"Building AM Configurator {version} for {target}...", flush=True)
        if sync:
            runner(
                ["uv", "sync", "--locked", "--extra", "desktop", "--extra", "build"],
                root,
            )
        runner(
            ["uv", "run", "--frozen", "python", "-m", "build_tools.prepare_ffmpeg"],
            root,
        )
        runner(
            [
                "uv",
                "run",
                "--frozen",
                "--extra",
                "desktop",
                "--extra",
                "build",
                "pyinstaller",
                "--noconfirm",
                "--clean",
                "packaging/am_configurator.spec",
            ],
            root,
        )
        runner(_packager_command(target, root), root)
        if not artifact.is_file():
            raise RuntimeError(f"Installer was not created: {artifact}")
        return artifact
    finally:
        if original_version is None:
            version_file.unlink(missing_ok=True)
        else:
            version_file.write_bytes(original_version)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-number",
        type=int,
        help="Use a specific positive build number instead of the local counter.",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip uv dependency synchronization when the build environment is ready.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.build_number is not None and args.build_number < 1:
        _parser().error("--build-number must be a positive integer")
    try:
        artifact = build_installer(
            build_number=args.build_number,
            sync=not args.skip_sync,
        )
    except (subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(f"\nBuilt installer:\n{artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
