"""CLI for package-manager stubs (AUR parked; Flatpak active).

prepare-flatpak / prepare-aur
  Fetch published release digests and write a package tree.

push-aur
  AUR git push (parked while Arch locks the AUR).

flatpak / aur
  Offline generate from local sums/manifest (tests and debugging).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from build_tools.package_managers.aur import AUR_PACKAGE_NAME, generate_aur_package
from build_tools.package_managers.common import (
    PackageManagerError,
    digests_from_manifest,
    digests_from_sums,
    validate_version,
)
from build_tools.package_managers.flatpak import (
    FLATPAK_APP_ID,
    generate_flatpak_package,
    manifest_path,
)
from build_tools.package_managers.release_aur import (
    DEFAULT_PACKAGE_OUT,
    aur_git_default,
    prepare_aur_package,
    push_aur_package,
)
from build_tools.package_managers.release_flatpak import (
    DEFAULT_FLATPAK_OUT,
    appimage_size_from_manifest_payload,
    build_flatpak_command,
    prepare_flatpak_package,
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
        description="Package-manager release tools for AM Configurator."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_fp = sub.add_parser(
        "prepare-flatpak",
        help="fetch release digests/size and write the Flatpak package tree",
    )
    prepare_fp.add_argument("--version", help="release version")
    prepare_fp.add_argument("--out", type=Path, help="output directory")
    prepare_fp.add_argument("--asset-base", help="asset base URL template")
    _add_repo_root(prepare_fp)

    prepare = sub.add_parser(
        "prepare-aur",
        help="fetch SHA256SUMS and write the AUR package tree (AUR publish parked)",
    )
    prepare.add_argument("--version", help="release version")
    prepare.add_argument("--out", type=Path)
    prepare.add_argument("--sums-url", help="override SHA256SUMS URL")
    prepare.add_argument("--asset-base", help="asset base URL template")
    _add_repo_root(prepare)

    push = sub.add_parser("push-aur", help="AUR git push (blocked while AUR is locked)")
    push.add_argument("--package-dir", type=Path)
    push.add_argument("--aur-git", type=Path)
    push.add_argument("--version")
    push.add_argument("--no-push", action="store_true")
    push.add_argument("--no-commit", action="store_true")
    _add_repo_root(push)

    generate_fp = sub.add_parser(
        "flatpak",
        help="generate Flatpak tree from local manifest/sums (no download)",
    )
    generate_fp.add_argument("--version", help="canonical version")
    generate_fp.add_argument("--out", type=Path, required=True)
    generate_fp.add_argument("--asset-base")
    generate_fp.add_argument(
        "--size",
        type=int,
        help="AppImage byte size (required with --sums; taken from --manifest)",
    )
    src = generate_fp.add_mutually_exclusive_group(required=True)
    src.add_argument("--sums", type=Path)
    src.add_argument("--manifest", type=Path)
    _add_repo_root(generate_fp)

    generate = sub.add_parser("aur", help="generate AUR tree from local sums/manifest")
    generate.add_argument("--version")
    gen_src = generate.add_mutually_exclusive_group(required=True)
    gen_src.add_argument("--sums", type=Path)
    gen_src.add_argument("--manifest", type=Path)
    generate.add_argument("--out", type=Path, required=True)
    generate.add_argument("--asset-base")
    _add_repo_root(generate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare-flatpak":
            destination = prepare_flatpak_package(
                version=args.version,
                repo_root=args.repo_root,
                output_dir=args.out,
                asset_base=args.asset_base,
            )
            print(manifest_path(destination))
            print(f"prepared {FLATPAK_APP_ID} -> {destination}")
            print(
                "next: ./build_tools/release_flatpak.sh build "
                "(needs flatpak-builder)"
            )
            return 0

        if args.command == "prepare-aur":
            destination = prepare_aur_package(
                version=args.version,
                repo_root=args.repo_root,
                output_dir=args.out,
                asset_base=args.asset_base,
                sums_url=args.sums_url,
            )
            print(destination / "PKGBUILD")
            print(f"prepared {AUR_PACKAGE_NAME} -> {destination}")
            print("AUR push is parked until Arch reopens package create/push.")
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

        if args.command == "flatpak":
            if args.manifest is not None:
                manifest_version, digests = digests_from_manifest(args.manifest)
                version = (
                    validate_version(args.version)
                    if args.version
                    else manifest_version
                )
                if version != manifest_version:
                    raise PackageManagerError(
                        f"--version {version} does not match manifest "
                        f"app_version {manifest_version}"
                    )
                payload = json.loads(
                    Path(args.manifest).read_text(encoding="utf-8")
                )
                size = appimage_size_from_manifest_payload(
                    payload, version=version
                )
            else:
                digests = digests_from_sums(args.sums)
                version = (
                    validate_version(args.version)
                    if args.version
                    else project_version(args.repo_root)
                )
                if args.size is None:
                    raise PackageManagerError(
                        "--size is required when generating Flatpak from --sums"
                    )
                size = args.size
            destination = generate_flatpak_package(
                version=version,
                digests=digests,
                appimage_size=size,
                repo_root=args.repo_root,
                output_dir=args.out,
                asset_base=args.asset_base,
            )
            print(manifest_path(destination))
            print(f"generated {FLATPAK_APP_ID} {version} -> {destination}")
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
                        f"--version {version} does not match manifest "
                        f"app_version {manifest_version}"
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
            print(f"generated {AUR_PACKAGE_NAME} {version} -> {destination}")
            return 0

        raise PackageManagerError(f"unsupported command: {args.command}")
    except PackageManagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
