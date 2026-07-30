#!/usr/bin/env python3
"""Build and smoke-test an AM Configurator installer for the current OS."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from build_tools.release_info import artifact_filename, project_version


PROJECT_ROOT = Path(__file__).resolve().parent
RunCommand = Callable[[list[str], Path], None]


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
    sync: bool = True,
    run_command: RunCommand | None = None,
) -> Path:
    """Build the current platform's installer and return its artifact path."""
    root = root.resolve()
    target = _target_for_platform(platform_name)
    runner = run_command or _run
    version = project_version(root)
    artifact = root / "dist" / artifact_filename(target, root=root)
    print(f"Building AM Configurator {version} for {target}...", flush=True)
    if sync:
        runner(
            ["uv", "sync", "--locked", "--extra", "desktop", "--extra", "build"],
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip uv dependency synchronization when the build environment is ready.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        artifact = build_installer(
            sync=not args.skip_sync,
        )
    except (subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(f"\nBuilt installer:\n{artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
