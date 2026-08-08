"""CLI: generate package-manager stubs from release digests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from build_tools.package_managers.aur import AUR_PACKAGE_NAME, generate_aur_package
from build_tools.package_managers.common import (
    PackageManagerError,
    digests_from_manifest,
    digests_from_sums,
    validate_version,
)
from build_tools.release_info import PROJECT_ROOT, project_version


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate package-manager package trees from published release digests."
        )
    )
    parser.add_argument(
        "channel",
        choices=("aur",),
        help="package-manager channel to generate",
    )
    parser.add_argument(
        "--version",
        help="canonical three-part version (default: am_configurator/_version.py)",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--sums",
        type=Path,
        help="path to SHA256SUMS.txt from the GitHub Release",
    )
    source.add_argument(
        "--manifest",
        type=Path,
        help="path to release-manifest.json from the GitHub Release",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="directory to write the package tree into",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=PROJECT_ROOT,
        help="repository root for desktop/icon/udev sources (default: this repo)",
    )
    parser.add_argument(
        "--asset-base",
        help=(
            "release asset base URL template; may include {version}. "
            "Default: GitHub Releases download URL for roethlar/AMKB-GUI"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
        if args.manifest is not None:
            manifest_version, digests = digests_from_manifest(args.manifest)
            version = (
                validate_version(args.version)
                if args.version
                else manifest_version
            )
            if version != manifest_version:
                raise PackageManagerError(
                    f"--version {version} does not match manifest app_version "
                    f"{manifest_version}"
                )
        else:
            digests = digests_from_sums(args.sums)
            version = (
                validate_version(args.version)
                if args.version
                else project_version(args.repo_root)
            )

        if args.channel == "aur":
            destination = generate_aur_package(
                version=version,
                digests=digests,
                repo_root=args.repo_root,
                output_dir=args.out,
                asset_base=args.asset_base,
            )
            print(destination / "PKGBUILD")
            print(destination / ".SRCINFO")
            print(f"generated {AUR_PACKAGE_NAME} {version} -> {destination}")
        else:
            raise PackageManagerError(f"unsupported channel: {args.channel}")
    except PackageManagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
