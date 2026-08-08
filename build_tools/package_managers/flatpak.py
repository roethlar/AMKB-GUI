"""Generate a Flatpak package tree that installs the published Linux AppImage.

App id (D2): io.github.roethlar.AMConfigurator

Uses Flatpak extra-data so the build downloads the exact GitHub Release
AppImage by URL + sha256 + size. finish-args grant device access so HID/serial
keyboards can be opened (same practical need as a host AppImage).
"""

from __future__ import annotations

import hashlib
import json
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

# D2
FLATPAK_APP_ID = "io.github.roethlar.AMConfigurator"
COMMAND_NAME = "am-configurator"
DISPLAY_NAME = "AM Configurator"
RUNTIME = "org.freedesktop.Platform"
RUNTIME_VERSION = "24.08"
SDK = "org.freedesktop.Sdk"

_DESKTOP_RELATIVE = Path("packaging/linux/am-configurator.desktop")
_ICON_RELATIVE = Path("assets/am-configurator-512.png")
_UDEV_RELATIVE = Path("am_configurator/data/60-am-neon-80.rules")

_MANIFEST_NAME = f"{FLATPAK_APP_ID}.yml"
_METAINFO_NAME = f"{FLATPAK_APP_ID}.metainfo.xml"
_DESKTOP_NAME = f"{FLATPAK_APP_ID}.desktop"
_ICON_NAME = f"{FLATPAK_APP_ID}.png"
_WRAPPER_NAME = "am-configurator.sh"
_APPLY_EXTRA_NAME = "apply_extra"
_UDEV_NAME = "60-am-neon-80.rules"
_README_UDEV = "README-udev.txt"


@dataclass(frozen=True)
class FlatpakPackageInputs:
    version: str
    appimage_filename: str
    appimage_sha256: str
    appimage_url: str
    appimage_size: int
    homepage: str = DEFAULT_HOMEPAGE


def build_inputs(
    *,
    version: str,
    digests: dict[str, str],
    appimage_size: int,
    asset_base: str | None = None,
    homepage: str = DEFAULT_HOMEPAGE,
) -> FlatpakPackageInputs:
    version = validate_version(version)
    if not isinstance(appimage_size, int) or isinstance(appimage_size, bool):
        raise PackageManagerError("appimage size must be a positive integer")
    if appimage_size <= 0:
        raise PackageManagerError("appimage size must be a positive integer")

    filename = linux_appimage_filename(version)
    sha256 = require_digest(digests, filename)
    url = release_download_url(version, filename, asset_base=asset_base)
    return FlatpakPackageInputs(
        version=version,
        appimage_filename=filename,
        appimage_sha256=sha256,
        appimage_url=url,
        appimage_size=appimage_size,
        homepage=homepage,
    )


def render_manifest(inputs: FlatpakPackageInputs) -> str:
    """YAML Flatpak manifest (deterministic field order)."""

    # finish-args: network for AI HTTPS; devices for HID/serial keyboards.
    lines = [
        f"app-id: {FLATPAK_APP_ID}",
        f"runtime: {RUNTIME}",
        f"runtime-version: '{RUNTIME_VERSION}'",
        f"sdk: {SDK}",
        f"command: {COMMAND_NAME}",
        "finish-args:",
        "  - --share=network",
        "  - --share=ipc",
        "  - --socket=fallback-x11",
        "  - --socket=wayland",
        "  - --device=all",
        "  - --filesystem=xdg-download",
        "  - --talk-name=org.freedesktop.secrets",
        "modules:",
        "  - name: am-configurator",
        "    buildsystem: simple",
        "    build-commands:",
        f"      - install -Dm755 {_APPLY_EXTRA_NAME} /app/bin/apply_extra",
        f"      - install -Dm755 {_WRAPPER_NAME} /app/bin/{COMMAND_NAME}",
        f"      - install -Dm644 {_DESKTOP_NAME} /app/share/applications/{_DESKTOP_NAME}",
        f"      - install -Dm644 {_METAINFO_NAME} /app/share/metainfo/{_METAINFO_NAME}",
        f"      - install -Dm644 {_ICON_NAME} /app/share/icons/hicolor/512x512/apps/{FLATPAK_APP_ID}.png",
        f"      - install -Dm644 {_UDEV_NAME} /app/share/am-configurator/{_UDEV_NAME}",
        f"      - install -Dm644 {_README_UDEV} /app/share/am-configurator/{_README_UDEV}",
        "    sources:",
        "      - type: extra-data",
        f"        filename: {inputs.appimage_filename}",
        f"        url: {inputs.appimage_url}",
        f"        sha256: {inputs.appimage_sha256}",
        f"        size: {inputs.appimage_size}",
        "      - type: file",
        f"        path: {_APPLY_EXTRA_NAME}",
        "      - type: file",
        f"        path: {_WRAPPER_NAME}",
        "      - type: file",
        f"        path: {_DESKTOP_NAME}",
        "      - type: file",
        f"        path: {_METAINFO_NAME}",
        "      - type: file",
        f"        path: {_ICON_NAME}",
        "      - type: file",
        f"        path: {_UDEV_NAME}",
        "      - type: file",
        f"        path: {_README_UDEV}",
        "",
    ]
    return "\n".join(lines)


def render_apply_extra(inputs: FlatpakPackageInputs) -> str:
    # Flatpak invokes apply_extra with the extra-data directory as cwd.
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f'install -Dm755 "{inputs.appimage_filename}" '
        f'am-configurator.AppImage\n'
    )


def render_wrapper() -> str:
    # Installed AppImage lives under /app/extra after first run apply_extra.
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        "APPIMAGE=/app/extra/am-configurator.AppImage\n"
        'if [ ! -x "$APPIMAGE" ]; then\n'
        '  echo "AM Configurator AppImage is missing under /app/extra." >&2\n'
        "  exit 1\n"
        "fi\n"
        'exec "$APPIMAGE" "$@"\n'
    )


def render_desktop() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={DISPLAY_NAME}\n"
        "Comment=Configure Angry Miao keyboards locally\n"
        f"Exec={COMMAND_NAME}\n"
        f"Icon={FLATPAK_APP_ID}\n"
        "Categories=Settings;HardwareSettings;\n"
        "Terminal=false\n"
        f"X-Flatpak={FLATPAK_APP_ID}\n"
    )


def render_metainfo(inputs: FlatpakPackageInputs) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{FLATPAK_APP_ID}</id>
  <name>{DISPLAY_NAME}</name>
  <summary>Standalone Angry Miao keyboard configurator</summary>
  <metadata_license>MIT</metadata_license>
  <project_license>MIT</project_license>
  <description>
    <p>
      Set up Angry Miao keyboards — keymaps, macros, and lighting — from one
      app on your own computer. This package installs the published Linux
      AppImage from the project GitHub Releases.
    </p>
  </description>
  <launchable type="desktop-id">{FLATPAK_APP_ID}.desktop</launchable>
  <url type="homepage">{inputs.homepage}</url>
  <url type="bugtracker">{inputs.homepage}/issues</url>
  <developer_name>roethlar</developer_name>
  <releases>
    <release version="{inputs.version}" />
  </releases>
  <content_rating type="oars-1.1" />
</component>
"""


def render_udev_readme() -> str:
    return (
        "AM Neon 80 on Linux needs a host udev rule for raw HID access.\n"
        "Flatpak cannot install system udev rules. On the host, run:\n"
        "\n"
        "  flatpak run --command=sh io.github.roethlar.AMConfigurator \\\n"
        "    -c '/app/extra/am-configurator.AppImage --print-udev-rule' \\\n"
        "    | sudo tee /etc/udev/rules.d/60-am-neon-80.rules >/dev/null\n"
        "\n"
        "Or copy /app/share/am-configurator/60-am-neon-80.rules from the\n"
        "installed app (see docs/neon-80-linux.md in the source repository).\n"
        "Then: sudo udevadm control --reload-rules && sudo udevadm trigger\n"
        "Unplug and replug the keyboard.\n"
    )


def generate_flatpak_package(
    *,
    version: str,
    digests: dict[str, str],
    appimage_size: int,
    repo_root: Path | str,
    output_dir: Path | str,
    asset_base: str | None = None,
    homepage: str = DEFAULT_HOMEPAGE,
) -> Path:
    """Write Flatpak sources + manifest into output_dir. Returns that path."""

    root = Path(repo_root)
    destination = Path(output_dir)
    inputs = build_inputs(
        version=version,
        digests=digests,
        appimage_size=appimage_size,
        asset_base=asset_base,
        homepage=homepage,
    )

    icon_src = root / _ICON_RELATIVE
    udev_src = root / _UDEV_RELATIVE
    for path in (icon_src, udev_src):
        if not path.is_file():
            raise PackageManagerError(f"required packaging source is missing: {path}")

    if destination.exists():
        if not destination.is_dir():
            raise PackageManagerError(
                f"output path exists and is not a directory: {destination}"
            )
        existing = [p for p in destination.iterdir() if p.name != ".DS_Store"]
        if existing:
            expected = {
                _MANIFEST_NAME,
                _METAINFO_NAME,
                _DESKTOP_NAME,
                _ICON_NAME,
                _WRAPPER_NAME,
                _APPLY_EXTRA_NAME,
                _UDEV_NAME,
                _README_UDEV,
            }
            if {p.name for p in existing} - expected:
                raise PackageManagerError(
                    f"refusing to write into non-empty directory: {destination}"
                )

    destination.mkdir(parents=True, exist_ok=True)

    apply_extra = render_apply_extra(inputs)
    wrapper = render_wrapper()
    desktop = render_desktop()
    metainfo = render_metainfo(inputs)
    udev_readme = render_udev_readme()
    manifest = render_manifest(inputs)

    (destination / _APPLY_EXTRA_NAME).write_text(
        apply_extra, encoding="utf-8", newline="\n"
    )
    (destination / _APPLY_EXTRA_NAME).chmod(0o755)
    (destination / _WRAPPER_NAME).write_text(wrapper, encoding="utf-8", newline="\n")
    (destination / _WRAPPER_NAME).chmod(0o755)
    (destination / _DESKTOP_NAME).write_text(desktop, encoding="utf-8", newline="\n")
    (destination / _METAINFO_NAME).write_text(
        metainfo, encoding="utf-8", newline="\n"
    )
    (destination / _README_UDEV).write_text(
        udev_readme, encoding="utf-8", newline="\n"
    )
    (destination / _MANIFEST_NAME).write_text(
        manifest, encoding="utf-8", newline="\n"
    )
    shutil.copy2(icon_src, destination / _ICON_NAME)
    shutil.copy2(udev_src, destination / _UDEV_NAME)

    # Sanity: wrapper and apply_extra digests are content we control.
    _ = hashlib.sha256(wrapper.encode("utf-8")).hexdigest()
    _ = file_sha256(destination / _ICON_NAME)

    return destination


def manifest_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / _MANIFEST_NAME
