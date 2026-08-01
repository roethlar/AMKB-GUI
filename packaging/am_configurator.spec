# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller recipe for the native AM Configurator app."""
from pathlib import Path
import sys

from build_tools.release_info import project_version


project = Path(SPECPATH).parent
app_version = project_version(project)
bundle_datas = [
    (str(project / "am_configurator" / "web"), "am_configurator/web"),
    # The Linux udev rule must reach the user, not only the source archive:
    # the permission error tells them to install it, and an AppImage user
    # has no source tree to install it from.
    (str(project / "am_configurator" / "data"), "am_configurator/data"),
    # The protocol layer derives from MIT-licensed cyberboard-cli, whose
    # notice must accompany every copy. The Windows installer's LicenseFile
    # only displays it during setup, so it has to ship as bundle data too.
    (str(project / "LICENSE"), "."),
    (str(project / "THIRD_PARTY_NOTICES"), "."),
    (str(project / "licenses" / "cyberboard-cli-LICENSE.txt"), "licenses"),
]


def required_linux_license(component, candidates):
    for candidate in map(Path, candidates):
        if candidate.is_file():
            return str(candidate), f"licenses/linux-native/{component}"
    raise FileNotFoundError(f"Required Linux {component} license was not found.")


hidden_imports = [
    "am_configurator.ai_capability",
    "am_configurator.credentials",
    "am_configurator.device",
    "am_configurator.llm",
    "am_configurator.macros",
    "am_configurator.protocol",
    "am_configurator.procedural",
    "am_configurator.procedural_generation",
    "am_configurator.reader",
    "am_configurator.recipe_provider",
    "am_configurator.server",
    "am_configurator.store",
    "am_configurator.writer",
]
if sys.platform == "darwin":
    hidden_imports.extend(("webview.platforms.cocoa", "keyring.backends.macOS"))
elif sys.platform == "win32":
    hidden_imports.extend(
        (
            "webview.platforms.winforms",
            "webview.platforms.edgechromium",
            "keyring.backends.Windows",
        )
    )
elif sys.platform.startswith("linux"):
    hidden_imports.extend(
        (
            "webview.platforms.gtk",
            "gi.repository.Gtk",
            "gi.repository.Gdk",
            "gi.repository.Gio",
            "gi.repository.GLib",
            "gi.repository.WebKit2",
            "gi.repository.Soup",
            "keyring.backends.SecretService",
        )
    )
    bundle_datas.extend(
        (
            required_linux_license(
                "gtk",
                (
                    "/usr/share/common-licenses/LGPL-2.1",
                    "/usr/share/licenses/spdx/LGPL-2.1-or-later.txt",
                ),
            ),
            required_linux_license(
                "libsoup",
                (
                    "/usr/share/common-licenses/LGPL-2",
                    "/usr/share/licenses/spdx/LGPL-2.0-or-later.txt",
                ),
            ),
            required_linux_license(
                "webkitgtk",
                (
                    "/usr/share/doc/libwebkit2gtk-4.1-0/copyright",
                    "/usr/share/licenses/webkit2gtk-4.1/LICENSE",
                ),
            ),
        )
    )
else:
    raise SystemExit(f"Unsupported native build platform: {sys.platform}")
executable_icon = (
    str(project / "assets" / "am-configurator.ico")
    if sys.platform == "win32"
    else None
)

a = Analysis(
    [str(project / "packaging" / "launcher.py")],
    pathex=[str(project)],
    binaries=[],
    datas=bundle_datas,
    hiddenimports=hidden_imports,
    hookspath=[str(project / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AM Configurator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=executable_icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AM Configurator",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AM Configurator.app",
        bundle_identifier="dev.amconfigurator.desktop",
        version=app_version,
        icon=str(project / "assets" / "am-configurator.icns"),
        info_plist={
            "CFBundleDisplayName": "AM Configurator",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "MIT License",
        },
    )
