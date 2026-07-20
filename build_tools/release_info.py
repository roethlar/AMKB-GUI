"""Shared release metadata for native installer builders."""
from __future__ import annotations

import argparse
import platform
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def project_version(root: Path = PROJECT_ROOT) -> str:
    with (root / "pyproject.toml").open("rb") as file:
        return str(tomllib.load(file)["project"]["version"])


def normalize_arch(machine: str | None = None) -> str:
    value = (machine or platform.machine()).strip().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
    }
    normalized = aliases.get(value, value)
    if normalized not in {"x86_64", "aarch64", "i686", "armhf"}:
        raise ValueError(f"Unsupported release architecture: {machine or value}")
    return normalized


def artifact_filename(
    target: str,
    machine: str | None = None,
    *,
    root: Path = PROJECT_ROOT,
) -> str:
    version = project_version(root)
    arch = normalize_arch(machine)
    if target == "macos":
        label = {"x86_64": "x64", "aarch64": "arm64"}.get(arch)
        if label is None:
            raise ValueError(f"Unsupported macOS release architecture: {arch}")
        return f"AM-Configurator-{version}-macOS-{label}.dmg"
    if target == "windows":
        label = {"x86_64": "x64", "aarch64": "arm64"}.get(arch)
        if label is None:
            raise ValueError(f"Unsupported Windows release architecture: {arch}")
        return f"AM-Configurator-{version}-Windows-{label}-Setup.exe"
    if target == "linux":
        return f"AM-Configurator-{version}-Linux-{arch}.AppImage"
    raise ValueError(f"Unsupported release target: {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version")
    subparsers.add_parser("arch")
    artifact = subparsers.add_parser("artifact")
    artifact.add_argument("target", choices=("macos", "windows", "linux"))
    args = parser.parse_args()

    if args.command == "version":
        print(project_version())
    elif args.command == "arch":
        print(normalize_arch())
    else:
        print(artifact_filename(args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
