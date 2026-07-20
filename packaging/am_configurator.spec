# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller recipe for the native AM Configurator app."""
from pathlib import Path
import sys

from build_tools.release_info import project_version


project = Path(SPECPATH).parent
app_version = project_version(project)
hidden_imports = [
    "am_configurator.device",
    "am_configurator.llm",
    "am_configurator.macros",
    "am_configurator.protocol",
    "am_configurator.reader",
    "am_configurator.server",
    "am_configurator.store",
    "am_configurator.writer",
]
if sys.platform == "darwin":
    hidden_imports.append("webview.platforms.cocoa")
elif sys.platform == "win32":
    hidden_imports.extend(("webview.platforms.winforms", "webview.platforms.edgechromium"))
else:
    hidden_imports.append("webview.platforms.qt")
executable_icon = (
    str(project / "assets" / "am-configurator.ico")
    if sys.platform == "win32"
    else None
)

a = Analysis(
    [str(project / "packaging" / "launcher.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[(str(project / "am_configurator" / "web"), "am_configurator/web")],
    hiddenimports=hidden_imports,
    hookspath=[],
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
    upx=True,
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
    upx=True,
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
