"""Collect the JavaScriptCore typelib used by WebKitGTK."""

from PyInstaller.utils.hooks.gi import get_gi_typelibs


binaries, datas, hiddenimports = get_gi_typelibs("JavaScriptCore", "4.1")
