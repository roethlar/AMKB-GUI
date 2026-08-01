"""Collect the exact WebKitGTK typelib used by PyWebView's GTK backend."""

from PyInstaller.config import CONF
from PyInstaller.utils.hooks.gi import get_gi_typelibs

from build_tools.webkitgtk_bundle import prepare_webkitgtk_bundle


binaries, datas, hiddenimports = get_gi_typelibs("WebKit2", "4.1")
jsc_binaries, jsc_datas, jsc_hiddenimports = get_gi_typelibs("JavaScriptCore", "4.1")
binaries += jsc_binaries
datas += jsc_datas
hiddenimports += jsc_hiddenimports
binaries = prepare_webkitgtk_bundle(binaries, workpath=CONF["workpath"])
