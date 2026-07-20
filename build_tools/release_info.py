"""Shared release metadata for native installer builders."""
from __future__ import annotations

import argparse
import os
import platform
import re
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VERSION_PATTERN = re.compile(r'^__version__\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def base_version(root: Path = PROJECT_ROOT) -> str:
    with (root / "pyproject.toml").open("rb") as file:
        return str(tomllib.load(file)["project"]["version"])


def project_version(root: Path = PROJECT_ROOT) -> str:
    version_file = root / "am_configurator" / "_version.py"
    if not version_file.is_file():
        return base_version(root)
    match = _VERSION_PATTERN.search(version_file.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"Could not read application version from {version_file}")
    return match.group(1)


def build_version(build_number: int, *, root: Path = PROJECT_ROOT) -> str:
    """Turn a GitHub workflow run number into a three-part app version."""
    if build_number < 1:
        raise ValueError("Build number must be a positive integer.")
    parts = base_version(root).split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Base project version must contain three numeric parts.")
    return f"{parts[0]}.{parts[1]}.{build_number}"


def stamp_build_version(build_number: int, *, root: Path = PROJECT_ROOT) -> str:
    """Write the CI build version into the module bundled by PyInstaller."""
    version = build_version(build_number, root=root)
    version_file = root / "am_configurator" / "_version.py"
    version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    return version


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
    stamp = subparsers.add_parser("stamp")
    stamp.add_argument("--build-number", type=int, required=True)
    stamp.add_argument("--github-output", action="store_true")
    args = parser.parse_args()

    if args.command == "version":
        print(project_version())
    elif args.command == "arch":
        print(normalize_arch())
    elif args.command == "artifact":
        print(artifact_filename(args.target))
    else:
        version = stamp_build_version(args.build_number)
        if args.github_output:
            output_path = os.environ.get("GITHUB_OUTPUT")
            if not output_path:
                raise ValueError("GITHUB_OUTPUT is unavailable outside GitHub Actions.")
            with Path(output_path).open("a", encoding="utf-8") as output:
                output.write(f"version={version}\n")
        print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
