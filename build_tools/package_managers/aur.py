"""Generate an AUR am-configurator-bin package tree from release digests."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from build_tools.package_managers.common import (
    DEFAULT_HOMEPAGE,
    PackageManagerError,
    file_sha256,
    linux_appimage_filename,
    release_download_url,
    require_digest,
    validate_version,
)

# D2 identifiers (decision 2026-08-08).
AUR_PACKAGE_NAME = "am-configurator-bin"
COMMAND_NAME = "am-configurator"
DISPLAY_NAME = "AM Configurator"
PKGREL = 1
LICENSE_ID = "MIT"

_DESKTOP_RELATIVE = Path("packaging/linux/am-configurator.desktop")
_ICON_RELATIVE = Path("assets/am-configurator-512.png")
_UDEV_RELATIVE = Path("am_configurator/data/60-am-neon-80.rules")

_LOCAL_DESKTOP = "am-configurator.desktop"
_LOCAL_ICON = "am-configurator.png"
_LOCAL_UDEV = "60-am-neon-80.rules"
_LOCAL_INSTALL = f"{AUR_PACKAGE_NAME}.install"
_LOCAL_WRAPPER = "am-configurator.sh"


@dataclass(frozen=True)
class AurPackageInputs:
    version: str
    appimage_filename: str
    appimage_sha256: str
    appimage_url: str
    desktop_sha256: str
    icon_sha256: str
    udev_sha256: str
    wrapper_sha256: str
    homepage: str = DEFAULT_HOMEPAGE


def _read_required(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PackageManagerError(f"cannot read {path}: {exc}") from None
    if not data:
        raise PackageManagerError(f"required source file is empty: {path}")
    return data


def build_inputs(
    *,
    version: str,
    digests: dict[str, str],
    repo_root: Path | str,
    asset_base: str | None = None,
    homepage: str = DEFAULT_HOMEPAGE,
) -> AurPackageInputs:
    version = validate_version(version)
    root = Path(repo_root)
    appimage_filename = linux_appimage_filename(version)
    appimage_sha256 = require_digest(digests, appimage_filename)
    appimage_url = release_download_url(
        version,
        appimage_filename,
        asset_base=asset_base,
    )

    desktop_path = root / _DESKTOP_RELATIVE
    icon_path = root / _ICON_RELATIVE
    udev_path = root / _UDEV_RELATIVE
    for path in (desktop_path, icon_path, udev_path):
        if not path.is_file():
            raise PackageManagerError(f"required packaging source is missing: {path}")

    provisional = AurPackageInputs(
        version=version,
        appimage_filename=appimage_filename,
        appimage_sha256=appimage_sha256,
        appimage_url=appimage_url,
        desktop_sha256=file_sha256(desktop_path),
        icon_sha256=file_sha256(icon_path),
        udev_sha256=file_sha256(udev_path),
        wrapper_sha256="",
        homepage=homepage,
    )
    wrapper_text = render_wrapper(provisional)
    wrapper_sha256 = hashlib.sha256(wrapper_text.encode("utf-8")).hexdigest()
    return AurPackageInputs(
        version=provisional.version,
        appimage_filename=provisional.appimage_filename,
        appimage_sha256=provisional.appimage_sha256,
        appimage_url=provisional.appimage_url,
        desktop_sha256=provisional.desktop_sha256,
        icon_sha256=provisional.icon_sha256,
        udev_sha256=provisional.udev_sha256,
        wrapper_sha256=wrapper_sha256,
        homepage=provisional.homepage,
    )


def render_pkgbuild(inputs: AurPackageInputs) -> str:
    """Return a deterministic PKGBUILD for am-configurator-bin."""

    # Source order is fixed so sha256sums lines stay aligned with source=().
    source_appimage = f"{inputs.appimage_filename}::{inputs.appimage_url}"
    lines = [
        f"# Maintainer: roethlar <https://github.com/roethlar>",
        f"pkgname={AUR_PACKAGE_NAME}",
        f"pkgver={inputs.version}",
        f"pkgrel={PKGREL}",
        f"pkgdesc='Standalone Angry Miao keyboard configurator'",
        "arch=('x86_64')",
        f"url='{inputs.homepage}'",
        f"license=('{LICENSE_ID}')",
        "# fuse2: AppImage runtime on typical Arch desktops",
        "depends=('fuse2')",
        "options=('!strip' '!debug')",
        f"install={_LOCAL_INSTALL}",
        "source=(",
        f"  '{source_appimage}'",
        f"  '{_LOCAL_DESKTOP}'",
        f"  '{_LOCAL_ICON}'",
        f"  '{_LOCAL_UDEV}'",
        f"  '{_LOCAL_WRAPPER}'",
        ")",
        "sha256sums=(",
        f"  '{inputs.appimage_sha256}'",
        f"  '{inputs.desktop_sha256}'",
        f"  '{inputs.icon_sha256}'",
        f"  '{inputs.udev_sha256}'",
        f"  '{inputs.wrapper_sha256}'",
        ")",
        "",
        "package() {",
        f'  install -Dm755 "${{srcdir}}/{inputs.appimage_filename}" \\',
        f'    "${{pkgdir}}/opt/{COMMAND_NAME}/{inputs.appimage_filename}"',
        f'  install -Dm755 "${{srcdir}}/{_LOCAL_WRAPPER}" \\',
        f'    "${{pkgdir}}/usr/bin/{COMMAND_NAME}"',
        f'  install -Dm644 "${{srcdir}}/{_LOCAL_DESKTOP}" \\',
        f'    "${{pkgdir}}/usr/share/applications/{_LOCAL_DESKTOP}"',
        f'  install -Dm644 "${{srcdir}}/{_LOCAL_ICON}" \\',
        f'    "${{pkgdir}}/usr/share/icons/hicolor/512x512/apps/{COMMAND_NAME}.png"',
        f'  install -Dm644 "${{srcdir}}/{_LOCAL_UDEV}" \\',
        f'    "${{pkgdir}}/usr/lib/udev/rules.d/{_LOCAL_UDEV}"',
        "}",
        "",
    ]
    return "\n".join(lines)


def render_srcinfo(inputs: AurPackageInputs) -> str:
    """Return a deterministic .SRCINFO matching render_pkgbuild."""

    source_appimage = f"{inputs.appimage_filename}::{inputs.appimage_url}"
    rows = [
        f"pkgbase = {AUR_PACKAGE_NAME}",
        f"\tpkgdesc = Standalone Angry Miao keyboard configurator",
        f"\tpkgver = {inputs.version}",
        f"\tpkgrel = {PKGREL}",
        f"\turl = {inputs.homepage}",
        f"\tinstall = {_LOCAL_INSTALL}",
        f"\tarch = x86_64",
        f"\tlicense = {LICENSE_ID}",
        f"\tdepends = fuse2",
        f"\toptions = !strip",
        f"\toptions = !debug",
        f"\tsource = {source_appimage}",
        f"\tsource = {_LOCAL_DESKTOP}",
        f"\tsource = {_LOCAL_ICON}",
        f"\tsource = {_LOCAL_UDEV}",
        f"\tsource = {_LOCAL_WRAPPER}",
        f"\tsha256sums = {inputs.appimage_sha256}",
        f"\tsha256sums = {inputs.desktop_sha256}",
        f"\tsha256sums = {inputs.icon_sha256}",
        f"\tsha256sums = {inputs.udev_sha256}",
        f"\tsha256sums = {inputs.wrapper_sha256}",
        f"pkgname = {AUR_PACKAGE_NAME}",
        "",
    ]
    return "\n".join(rows)


def render_wrapper(inputs: AurPackageInputs) -> str:
    return (
        "#!/bin/sh\n"
        f'exec /opt/{COMMAND_NAME}/{inputs.appimage_filename} "$@"\n'
    )


def render_install_script() -> str:
    return """post_install() {
  echo "AM Neon 80: unplug and replug the keyboard so the installed udev rule applies."
}

post_upgrade() {
  post_install
}
"""


def generate_aur_package(
    *,
    version: str,
    digests: dict[str, str],
    repo_root: Path | str,
    output_dir: Path | str,
    asset_base: str | None = None,
    homepage: str = DEFAULT_HOMEPAGE,
) -> Path:
    """Write PKGBUILD, .SRCINFO, and local sources into output_dir.

    Returns the output directory path.
    """

    root = Path(repo_root)
    destination = Path(output_dir)
    inputs = build_inputs(
        version=version,
        digests=digests,
        repo_root=root,
        asset_base=asset_base,
        homepage=homepage,
    )

    if destination.exists():
        if not destination.is_dir():
            raise PackageManagerError(
                f"output path exists and is not a directory: {destination}"
            )
        # Refuse non-empty destinations that are not an earlier generation of
        # this package, so a mistaken path does not get clobbered.
        existing = [path for path in destination.iterdir() if path.name != ".DS_Store"]
        if existing:
            expected_names = {
                "PKGBUILD",
                ".SRCINFO",
                _LOCAL_DESKTOP,
                _LOCAL_ICON,
                _LOCAL_UDEV,
                _LOCAL_WRAPPER,
                _LOCAL_INSTALL,
            }
            names = {path.name for path in existing}
            if not names.issubset(expected_names):
                raise PackageManagerError(
                    f"refusing to write into non-empty directory: {destination}"
                )

    destination.mkdir(parents=True, exist_ok=True)

    shutil.copy2(root / _DESKTOP_RELATIVE, destination / _LOCAL_DESKTOP)
    shutil.copy2(root / _ICON_RELATIVE, destination / _LOCAL_ICON)
    shutil.copy2(root / _UDEV_RELATIVE, destination / _LOCAL_UDEV)

    wrapper_path = destination / _LOCAL_WRAPPER
    wrapper_path.write_text(render_wrapper(inputs), encoding="utf-8", newline="\n")
    wrapper_path.chmod(0o755)

    install_path = destination / _LOCAL_INSTALL
    install_path.write_text(render_install_script(), encoding="utf-8", newline="\n")

    pkgbuild = render_pkgbuild(inputs)
    srcinfo = render_srcinfo(inputs)
    (destination / "PKGBUILD").write_text(pkgbuild, encoding="utf-8", newline="\n")
    (destination / ".SRCINFO").write_text(srcinfo, encoding="utf-8", newline="\n")

    # Recompute local digests after copy so the written PKGBUILD matches bytes
    # on disk even if the source tree used different line endings (it must not).
    written_desktop = file_sha256(destination / _LOCAL_DESKTOP)
    written_icon = file_sha256(destination / _LOCAL_ICON)
    written_udev = file_sha256(destination / _LOCAL_UDEV)
    written_wrapper = file_sha256(destination / _LOCAL_WRAPPER)
    if (
        written_desktop != inputs.desktop_sha256
        or written_icon != inputs.icon_sha256
        or written_udev != inputs.udev_sha256
        or written_wrapper != inputs.wrapper_sha256
    ):
        raise PackageManagerError(
            "written local sources do not match the digests embedded in PKGBUILD"
        )

    return destination
