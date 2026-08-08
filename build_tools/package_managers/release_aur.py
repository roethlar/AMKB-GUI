"""Repeatable AUR release: fetch digests → generate tree → optional git push.

This is the maintainer path for every public version after the GitHub Release
assets exist. No agent required.

Typical flow (from the application repo root):

  # 1. After vX.Y.Z is published on GitHub:
  uv run --frozen python -m build_tools.package_managers prepare-aur

  # 2. On a machine with AUR SSH (e.g. Arch host) and an AUR git clone:
  uv run --frozen python -m build_tools.package_managers push-aur \\
    --aur-git ~/aur/am-configurator-bin

Optional local Arch proof before push:

  cd dist/package-managers/am-configurator-bin && makepkg -f

Identity and URLs come from this package's constants (D2) and
build_tools.package_managers.common — not from chat.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from build_tools.package_managers.aur import AUR_PACKAGE_NAME, generate_aur_package
from build_tools.package_managers.common import (
    DEFAULT_RELEASE_ASSET_BASE,
    PackageManagerError,
    digests_from_sums,
    validate_version,
)
from build_tools.release_info import PROJECT_ROOT, project_version

# Files the generator writes that must be committed to the AUR git package.
_AUR_PACKAGE_FILES = (
    "PKGBUILD",
    ".SRCINFO",
    "am-configurator.desktop",
    "am-configurator.png",
    "60-am-neon-80.rules",
    "am-configurator.sh",
    f"{AUR_PACKAGE_NAME}.install",
)

DEFAULT_PACKAGE_OUT = Path("dist/package-managers") / AUR_PACKAGE_NAME
DEFAULT_AUR_SSH_URL = f"ssh://aur@aur.archlinux.org/{AUR_PACKAGE_NAME}.git"


def default_sums_url(version: str, *, asset_base: str | None = None) -> str:
    version = validate_version(version)
    base = (asset_base or DEFAULT_RELEASE_ASSET_BASE).format(version=version)
    return f"{base.rstrip('/')}/SHA256SUMS.txt"


def download_text(url: str, *, timeout_seconds: float = 60.0) -> str:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise PackageManagerError(
            f"failed to download {url}: HTTP {exc.code}"
        ) from None
    except urllib.error.URLError as exc:
        raise PackageManagerError(f"failed to download {url}: {exc.reason}") from None
    except TimeoutError as exc:
        raise PackageManagerError(f"timed out downloading {url}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageManagerError(f"checksums file is not UTF-8: {url}") from exc


def prepare_aur_package(
    *,
    version: str | None = None,
    repo_root: Path | str = PROJECT_ROOT,
    output_dir: Path | str | None = None,
    asset_base: str | None = None,
    sums_url: str | None = None,
) -> Path:
    """Download published SHA256SUMS and write the AUR package tree.

    Returns the output directory. Requires network access to GitHub Releases.
    """

    root = Path(repo_root)
    resolved_version = (
        validate_version(version) if version else project_version(root)
    )
    destination = Path(output_dir) if output_dir else root / DEFAULT_PACKAGE_OUT
    url = sums_url or default_sums_url(resolved_version, asset_base=asset_base)

    sums_text = download_text(url)
    sums_path = destination.parent / f"SHA256SUMS-{resolved_version}.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    sums_path.write_text(sums_text, encoding="utf-8", newline="\n")

    digests = digests_from_sums(sums_path)
    return generate_aur_package(
        version=resolved_version,
        digests=digests,
        repo_root=root,
        output_dir=destination,
        asset_base=asset_base,
    )


def _run_git(aur_git: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=aur_git,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise PackageManagerError(
            f"git {' '.join(args)} failed in {aur_git}: {detail}"
        )
    return completed.stdout


def ensure_aur_clone(
    aur_git: Path | str,
    *,
    ssh_url: str = DEFAULT_AUR_SSH_URL,
) -> Path:
    """Clone the AUR package repo if missing; otherwise require a git work tree."""

    path = Path(aur_git)
    if path.is_dir() and (path / ".git").exists():
        return path
    if path.exists() and any(path.iterdir()):
        raise PackageManagerError(
            f"aur-git path exists but is not a git clone: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "clone", ssh_url, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise PackageManagerError(
            f"git clone {ssh_url} failed: {detail}"
        )
    return path


def sync_package_into_aur_git(
    package_dir: Path | str,
    aur_git: Path | str,
) -> None:
    """Copy generated package files into the AUR git working tree."""

    source = Path(package_dir)
    dest = Path(aur_git)
    if not (dest / ".git").exists():
        raise PackageManagerError(f"not an AUR git clone: {dest}")

    missing = [name for name in _AUR_PACKAGE_FILES if not (source / name).is_file()]
    if missing:
        raise PackageManagerError(
            f"package directory is incomplete ({', '.join(missing)}): {source}"
        )

    for name in _AUR_PACKAGE_FILES:
        shutil.copy2(source / name, dest / name)


def push_aur_package(
    *,
    package_dir: Path | str,
    aur_git: Path | str,
    version: str | None = None,
    ssh_url: str = DEFAULT_AUR_SSH_URL,
    commit: bool = True,
    push: bool = True,
    allow_empty: bool = False,
) -> str:
    """Sync generated files into the AUR clone, commit, and push.

    Returns the commit message used (or a no-change note).
    Requires AUR SSH access (ssh -T aur@aur.archlinux.org).
    """

    source = Path(package_dir)
    clone = ensure_aur_clone(aur_git, ssh_url=ssh_url)
    sync_package_into_aur_git(source, clone)

    # pkgver from PKGBUILD if version not supplied
    resolved_version = version
    if resolved_version is None:
        pkgbuild = (clone / "PKGBUILD").read_text(encoding="utf-8")
        for line in pkgbuild.splitlines():
            if line.startswith("pkgver="):
                resolved_version = line.split("=", 1)[1].strip().strip("'\"")
                break
    if not resolved_version:
        raise PackageManagerError("could not determine package version for commit")
    validate_version(resolved_version)

    _run_git(clone, "add", "--", *_AUR_PACKAGE_FILES)
    status = _run_git(clone, "status", "--porcelain", "--", *_AUR_PACKAGE_FILES)
    if not status.strip():
        if allow_empty:
            return f"{AUR_PACKAGE_NAME} {resolved_version}-1 (no changes)"
        raise PackageManagerError(
            f"no changes to commit in {clone}; tree already matches package_dir"
        )

    message = f"{AUR_PACKAGE_NAME} {resolved_version}-1"
    if commit:
        _run_git(clone, "commit", "-m", message)
    if push:
        _run_git(clone, "push", "origin", "HEAD")
    return message


def aur_git_default() -> Path:
    """Default clone path: $AUR_GIT or ~/aur/am-configurator-bin."""

    env = os.environ.get("AUR_GIT")
    if env:
        return Path(env).expanduser()
    return Path.home() / "aur" / AUR_PACKAGE_NAME
