"""Collect the exact WebKitGTK typelib used by PyWebView's GTK backend."""

from PyInstaller.utils.hooks.gi import get_gi_typelibs


binaries, datas, hiddenimports = get_gi_typelibs("WebKit2", "4.1")
