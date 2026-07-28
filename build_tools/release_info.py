"""Shared release metadata for native installer builders."""
from __future__ import annotations

import argparse
import os
import platform
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_NUMERIC_PART = r"(?:0|[1-9]\d*)"
_VERSION_PATTERN = re.compile(
    rf'__version__\s*=\s*"({_NUMERIC_PART}\.{_NUMERIC_PART}\.{_NUMERIC_PART})"\s*'
)


def project_version(root: Path = PROJECT_ROOT) -> str:
    version_file = root / "am_configurator" / "_version.py"
    if not version_file.is_file():
        raise ValueError(f"Canonical application version is missing: {version_file}")
    match = _VERSION_PATTERN.fullmatch(version_file.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"Canonical application version is invalid: {version_file}")
    return match.group(1)


def _write_github_output(version: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise ValueError("GITHUB_OUTPUT is unavailable outside GitHub Actions.")
    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")


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
    version_command = subparsers.add_parser("version")
    version_command.add_argument("--github-output", action="store_true")
    subparsers.add_parser("arch")
    artifact = subparsers.add_parser("artifact")
    artifact.add_argument("target", choices=("macos", "windows", "linux"))
    args = parser.parse_args()

    if args.command == "version":
        version = project_version()
        if args.github_output:
            _write_github_output(version)
        print(version)
    elif args.command == "arch":
        print(normalize_arch())
    else:
        print(artifact_filename(args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
