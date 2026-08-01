"""Collect and relocate WebKitGTK's out-of-process runtime for PyInstaller."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import re
import shutil


_RELOCATED_RUNTIME = b"/proc/self/cwd/wk"
_REQUIRED_PROCESSES = (
    "WebKitWebProcess",
    "WebKitNetworkProcess",
    "WebKitGPUProcess",
)
_LIBRARY_NAME = re.compile(r"^libwebkit2gtk-(\d+\.\d+)\.so(?:\..*)?$")


def _replace_c_string(payload: bytes, old: bytes, new: bytes) -> bytes:
    if len(new) > len(old):
        raise ValueError("relocated WebKitGTK runtime path is too long")
    needle = old + b"\0"
    if needle not in payload:
        raise ValueError("WebKitGTK runtime path was not found in the library")
    replacement = new + (b"\0" * (len(old) - len(new) + 1))
    return payload.replace(needle, replacement)


def prepare_webkitgtk_bundle(
    binaries: Sequence[tuple[str, str]],
    *,
    workpath: str | Path,
) -> list[tuple[str, str]]:
    """Return binaries with a relocated WebKitGTK library and its helpers."""
    collected = [(str(source), destination) for source, destination in binaries]
    matches: list[tuple[int, Path, str]] = []
    for index, (source, destination) in enumerate(collected):
        path = Path(source)
        match = _LIBRARY_NAME.fullmatch(path.name)
        if match is not None:
            matches.append((index, path, match.group(1)))
    if len(matches) != 1:
        raise ValueError("expected exactly one WebKitGTK shared library")

    index, library, api_version = matches[0]
    helper_dir = library.parent / f"webkit2gtk-{api_version}"
    runtime_files = [helper_dir / name for name in _REQUIRED_PROCESSES]
    injected = helper_dir / "injected-bundle" / "libwebkit2gtkinjectedbundle.so"
    for required in (*runtime_files, injected):
        if not required.is_file():
            raise FileNotFoundError(f"Required WebKitGTK runtime file is missing: {required}")

    old_runtime = str(helper_dir).encode()
    old_injected = old_runtime + b"/injected-bundle/"
    new_injected = _RELOCATED_RUNTIME + b"/injected-bundle/"
    payload = library.read_bytes()
    payload = _replace_c_string(payload, old_injected, new_injected)
    payload = _replace_c_string(payload, old_runtime, _RELOCATED_RUNTIME)

    relocated_dir = Path(workpath) / "webkitgtk-relocated"
    relocated_dir.mkdir(parents=True, exist_ok=True)
    relocated = relocated_dir / library.name
    shutil.copy2(library, relocated)
    relocated.write_bytes(payload)
    collected[index] = (str(relocated), collected[index][1])
    collected.extend((str(process), "wk") for process in runtime_files)
    collected.append((str(injected), "wk/injected-bundle"))
    return collected
