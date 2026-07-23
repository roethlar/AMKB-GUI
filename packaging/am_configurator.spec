# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller recipe for the native AM Configurator app."""
from pathlib import Path
import sys

from am_configurator.ffmpeg_runtime import get_ffmpeg_runtime
from build_tools.release_info import project_version


project = Path(SPECPATH).parent
app_version = project_version(project)
ffmpeg_binary = get_ffmpeg_runtime()
ffmpeg_metadata = project / "packaging" / "ffmpeg"
binaries = [
    (str(ffmpeg_binary), "ffmpeg"),
]
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
else:
    hidden_imports.extend(("webview.platforms.qt", "keyring.backends.SecretService"))
executable_icon = (
    str(project / "assets" / "am-configurator.ico")
    if sys.platform == "win32"
    else None
)

a = Analysis(
    [str(project / "packaging" / "launcher.py")],
    pathex=[str(project)],
    binaries=binaries,
    datas=[
        (str(project / "am_configurator" / "web"), "am_configurator/web"),
        (str(ffmpeg_binary.with_name("ffmpeg-runtime.json")), "ffmpeg"),
        (str(ffmpeg_metadata / "manifest.json"), "ffmpeg"),
        (str(ffmpeg_metadata / "LGPL-2.1.txt"), "ffmpeg"),
        (str(ffmpeg_metadata / "README.md"), "ffmpeg"),
        (str(ffmpeg_metadata / "ffmpeg-devel.asc"), "ffmpeg"),
        (str(project / "tests" / "fixtures" / "tiny-motion.mp4"), "smoke"),
    ],
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
