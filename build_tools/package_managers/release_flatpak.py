"""Repeatable Flatpak release: fetch digests/size → write manifest tree.

Typical flow (after a public GitHub Release exists):

  ./build_tools/release_flatpak.sh prepare
  # on a machine with flatpak-builder:
  ./build_tools/release_flatpak.sh build
  # Flathub submission is separate (see packaging/flatpak/PROCESS.md)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from build_tools.package_managers.common import (
    DEFAULT_RELEASE_ASSET_BASE,
    PackageManagerError,
    digests_from_manifest,
    digests_from_sums,
    linux_appimage_filename,
    validate_version,
)
from build_tools.package_managers.flatpak import (
    FLATPAK_APP_ID,
    generate_flatpak_package,
)
from build_tools.package_managers.release_aur import download_text
from build_tools.release_info import PROJECT_ROOT, project_version

DEFAULT_FLATPAK_OUT = Path("dist/package-managers") / "flatpak"


def default_manifest_url(version: str, *, asset_base: str | None = None) -> str:
    version = validate_version(version)
    base = (asset_base or DEFAULT_RELEASE_ASSET_BASE).format(version=version)
    return f"{base.rstrip('/')}/release-manifest.json"


def default_sums_url(version: str, *, asset_base: str | None = None) -> str:
    version = validate_version(version)
    base = (asset_base or DEFAULT_RELEASE_ASSET_BASE).format(version=version)
    return f"{base.rstrip('/')}/SHA256SUMS.txt"


def appimage_size_from_manifest_payload(
    payload: dict,
    *,
    version: str,
) -> int:
    filename = linux_appimage_filename(version)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise PackageManagerError("release manifest lists no artifacts")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("filename") != filename:
            continue
        size = artifact.get("byte_size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise PackageManagerError(
                f"release manifest has no positive byte_size for {filename}"
            )
        return size
    raise PackageManagerError(
        f"release manifest is missing Linux AppImage artifact {filename}"
    )


def content_length(url: str, *, timeout_seconds: float = 60.0) -> int:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            length = response.headers.get("Content-Length")
    except urllib.error.HTTPError as exc:
        raise PackageManagerError(
            f"failed HEAD {url}: HTTP {exc.code}"
        ) from None
    except urllib.error.URLError as exc:
        raise PackageManagerError(f"failed HEAD {url}: {exc.reason}") from None
    if not length:
        raise PackageManagerError(f"no Content-Length for {url}")
    try:
        size = int(length)
    except ValueError as exc:
        raise PackageManagerError(f"invalid Content-Length for {url}") from exc
    if size <= 0:
        raise PackageManagerError(f"non-positive Content-Length for {url}")
    return size


def prepare_flatpak_package(
    *,
    version: str | None = None,
    repo_root: Path | str = PROJECT_ROOT,
    output_dir: Path | str | None = None,
    asset_base: str | None = None,
) -> Path:
    """Download release metadata and write the Flatpak package tree."""

    root = Path(repo_root)
    resolved = validate_version(version) if version else project_version(root)
    destination = Path(output_dir) if output_dir else root / DEFAULT_FLATPAK_OUT

    manifest_url = default_manifest_url(resolved, asset_base=asset_base)
    sums_url = default_sums_url(resolved, asset_base=asset_base)

    digests: dict[str, str]
    size: int
    try:
        manifest_text = download_text(manifest_url)
        payload = json.loads(manifest_text)
        if not isinstance(payload, dict):
            raise PackageManagerError("release manifest must be a JSON object")
        manifest_version, digests = digests_from_manifest(
            _write_temp_json(destination.parent, resolved, payload)
        )
        if manifest_version != resolved:
            raise PackageManagerError(
                f"manifest app_version {manifest_version} != requested {resolved}"
            )
        size = appimage_size_from_manifest_payload(payload, version=resolved)
    except PackageManagerError:
        # Fallback: sums + Content-Length
        sums_text = download_text(sums_url)
        sums_path = destination.parent / f"SHA256SUMS-{resolved}.txt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        sums_path.write_text(sums_text, encoding="utf-8", newline="\n")
        digests = digests_from_sums(sums_path)
        filename = linux_appimage_filename(resolved)
        from build_tools.package_managers.common import release_download_url

        size = content_length(
            release_download_url(resolved, filename, asset_base=asset_base)
        )

    return generate_flatpak_package(
        version=resolved,
        digests=digests,
        appimage_size=size,
        repo_root=root,
        output_dir=destination,
        asset_base=asset_base,
    )


def _write_temp_json(parent: Path, version: str, payload: dict) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / f"release-manifest-{version}.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def build_flatpak_command(package_dir: Path | str) -> list[str]:
    """Return a flatpak-builder command line for local proof builds."""

    directory = Path(package_dir)
    manifest = directory / f"{FLATPAK_APP_ID}.yml"
    return [
        "flatpak-builder",
        "--user",
        "--install",
        "--force-clean",
        str(directory / "build"),
        str(manifest),
    ]
