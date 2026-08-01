"""Collect the exact Soup typelib used by PyWebView's GTK backend."""

from PyInstaller.utils.hooks.gi import get_gi_typelibs


binaries, datas, hiddenimports = get_gi_typelibs("Soup", "3.0")
