"""CLI for package-manager stubs and the AUR release process.

Subcommands
-----------
prepare-aur
  Download SHA256SUMS for a published GitHub Release version and write the
  AUR package tree. Run from this application repo (any OS with network).

push-aur
  Copy that tree into an AUR git clone, commit, and push. Run on a machine
  that can `ssh -T aur@aur.archlinux.org` (typically Arch).

aur
  Low-level generate from a local --sums or --manifest file (used by tests).

Repeatable maintainer process (no agent)::

  # After vX.Y.Z exists on GitHub Releases:
  uv run --frozen python -m build_tools.package_managers prepare-aur --version X.Y.Z

  # Optional proof on Arch:
  #   cd dist/package-managers/am-configurator-bin && makepkg -f

  # Publish (AUR SSH required):
  uv run --frozen python -m build_tools.package_managers push-aur
"""

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
from build_tools.package_managers.release_aur import (
    DEFAULT_PACKAGE_OUT,
    aur_git_default,
    prepare_aur_package,
    push_aur_package,
)
from build_tools.release_info import PROJECT_ROOT, project_version


def _add_repo_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=PROJECT_ROOT,
        help="application repository root (default: this checkout)",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Package-manager stubs and AUR release process for AM Configurator."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser(
        "prepare-aur",
        help="fetch published SHA256SUMS and write the AUR package tree",
    )
    prepare.add_argument(
        "--version",
        help="release version (default: am_configurator/_version.py)",
    )
    prepare.add_argument(
        "--out",
        type=Path,
        help=f"output directory (default: <repo>/{DEFAULT_PACKAGE_OUT})",
    )
    prepare.add_argument(
        "--sums-url",
        help="override SHA256SUMS URL (default: GitHub Release for this version)",
    )
    prepare.add_argument(
        "--asset-base",
        help="release asset base URL template; may include {version}",
    )
    _add_repo_root(prepare)

    push = sub.add_parser(
        "push-aur",
        help="sync package tree into AUR git clone, commit, and push",
    )
    push.add_argument(
        "--package-dir",
        type=Path,
        help=(
            "generated package directory "
            f"(default: <repo>/{DEFAULT_PACKAGE_OUT})"
        ),
    )
    push.add_argument(
        "--aur-git",
        type=Path,
        help=(
            "AUR package git clone path "
            f"(default: $AUR_GIT or ~/aur/{AUR_PACKAGE_NAME})"
        ),
    )
    push.add_argument(
        "--version",
        help="version for the commit message (default: read pkgver from PKGBUILD)",
    )
    push.add_argument(
        "--no-push",
        action="store_true",
        help="commit only; do not git push",
    )
    push.add_argument(
        "--no-commit",
        action="store_true",
        help="copy files only; do not commit or push",
    )
    _add_repo_root(push)

    generate = sub.add_parser(
        "aur",
        help="generate AUR tree from a local sums/manifest file (no download)",
    )
    generate.add_argument("--version", help="canonical three-part version")
    source = generate.add_mutually_exclusive_group(required=True)
    source.add_argument("--sums", type=Path, help="path to SHA256SUMS.txt")
    source.add_argument("--manifest", type=Path, help="path to release-manifest.json")
    generate.add_argument(
        "--out",
        type=Path,
        required=True,
        help="directory to write the package tree into",
    )
    generate.add_argument("--asset-base", help="asset base URL template")
    _add_repo_root(generate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare-aur":
            destination = prepare_aur_package(
                version=args.version,
                repo_root=args.repo_root,
                output_dir=args.out,
                asset_base=args.asset_base,
                sums_url=args.sums_url,
            )
            print(destination / "PKGBUILD")
            print(destination / ".SRCINFO")
            print(f"prepared {AUR_PACKAGE_NAME} -> {destination}")
            print(
                "next: on a host with AUR SSH, "
                "uv run --frozen python -m build_tools.package_managers push-aur"
            )
            return 0

        if args.command == "push-aur":
            package_dir = (
                Path(args.package_dir)
                if args.package_dir
                else Path(args.repo_root) / DEFAULT_PACKAGE_OUT
            )
            aur_git = Path(args.aur_git) if args.aur_git else aur_git_default()
            message = push_aur_package(
                package_dir=package_dir,
                aur_git=aur_git,
                version=args.version,
                commit=not args.no_commit,
                push=not args.no_push and not args.no_commit,
            )
            print(message)
            print(f"aur-git: {aur_git}")
            return 0

        if args.command == "aur":
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
            return 0

        raise PackageManagerError(f"unsupported command: {args.command}")
    except PackageManagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
