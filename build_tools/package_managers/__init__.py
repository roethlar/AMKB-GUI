"""Deterministic package-manager stubs from published release digests."""

from __future__ import annotations

from build_tools.package_managers.aur import (
    AUR_PACKAGE_NAME,
    generate_aur_package,
    render_pkgbuild,
    render_srcinfo,
)
from build_tools.package_managers.common import (
    DEFAULT_RELEASE_ASSET_BASE,
    PackageManagerError,
    digests_from_manifest,
    digests_from_sums,
    linux_appimage_filename,
    release_download_url,
    require_digest,
    validate_version,
)

__all__ = [
    "AUR_PACKAGE_NAME",
    "DEFAULT_RELEASE_ASSET_BASE",
    "PackageManagerError",
    "digests_from_manifest",
    "digests_from_sums",
    "generate_aur_package",
    "linux_appimage_filename",
    "release_download_url",
    "render_pkgbuild",
    "render_srcinfo",
    "require_digest",
    "validate_version",
]
