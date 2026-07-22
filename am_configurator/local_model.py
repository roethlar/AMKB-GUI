"""Private attestation for a user-selected local GGUF model.

The model file remains user-owned.  This module records and validates a
selection but never copies, modifies, downloads, moves, or deletes weights.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MIN_MODEL_BYTES = 1024 * 1024
MAX_MODEL_BYTES = 64 * 1024 * 1024 * 1024
MAX_ATTESTATION_BYTES = 64 * 1024
ATTESTATION_SCHEMA_VERSION = 1
_ATTESTATION_KEYS = {
    "schema_version",
    "path",
    "filename",
    "size_bytes",
    "sha256",
    "device",
    "inode",
    "mtime_ns",
}


class LocalModelError(RuntimeError):
    """A selected model is absent, unsafe, unsupported, or has changed."""


@dataclass(frozen=True)
class SelectedModel:
    path: Path
    filename: str
    size_bytes: int
    sha256: str
    device: int
    inode: int
    mtime_ns: int


def _default_root() -> Path:
    from .store import store_root

    return store_root() / "ai"


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
    )


def _validate_filename(value: str) -> str:
    if (
        not value
        or len(value) > 255
        or any(ord(character) < 32 for character in value)
        or Path(value).name != value
    ):
        raise LocalModelError("Selected local model filename is invalid.")
    return value


def _open_model(path: Path, *, hash_file: bool) -> tuple[os.stat_result, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise LocalModelError("Selected local model must be a regular file.")
        descriptor = os.open(path, flags)
    except LocalModelError:
        raise
    except OSError:
        raise LocalModelError("Selected local model could not be opened.") from None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_identity(before, opened):
            raise LocalModelError("Selected local model changed during verification.")
        if not MIN_MODEL_BYTES <= opened.st_size <= MAX_MODEL_BYTES:
            raise LocalModelError("Selected local model size is unsupported.")
        if os.read(descriptor, 4) != b"GGUF":
            raise LocalModelError("Selected local model is not a GGUF file.")
        digest = hashlib.sha256() if hash_file else None
        if digest is not None:
            os.lseek(descriptor, 0, os.SEEK_SET)
            while True:
                block = os.read(descriptor, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
        after = os.fstat(descriptor)
        if not _same_identity(opened, after):
            raise LocalModelError("Selected local model changed during verification.")
        return after, None if digest is None else digest.hexdigest()
    except OSError:
        raise LocalModelError("Selected local model could not be read.") from None
    finally:
        os.close(descriptor)


def _selected(path: Path, filename: str, details: os.stat_result, sha256: str) -> SelectedModel:
    return SelectedModel(
        path=path,
        filename=filename,
        size_bytes=details.st_size,
        sha256=sha256,
        device=details.st_dev,
        inode=details.st_ino,
        mtime_ns=details.st_mtime_ns,
    )


class LocalModelManager:
    """Own a private selection record while leaving model weights untouched."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = (_default_root() if root is None else Path(root)).expanduser().resolve()
        self.attestation_path = self.root / "local-model.json"

    def _prepare_root(self) -> None:
        if self.root.is_symlink():
            raise LocalModelError("Local model metadata directory is unsafe.")
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not self.root.is_dir() or self.root.is_symlink():
                raise OSError
            if os.name != "nt":
                os.chmod(self.root, 0o700)
        except OSError:
            raise LocalModelError("Local model metadata could not be prepared.") from None

    def _write(self, selected: SelectedModel) -> None:
        self._prepare_root()
        value = {
            "schema_version": ATTESTATION_SCHEMA_VERSION,
            "path": str(selected.path),
            "filename": selected.filename,
            "size_bytes": selected.size_bytes,
            "sha256": selected.sha256,
            "device": selected.device,
            "inode": selected.inode,
            "mtime_ns": selected.mtime_ns,
        }
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(
            dir=self.root,
            prefix=".local-model.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary)
        try:
            if os.name != "nt":
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self.attestation_path)
            if os.name != "nt":
                os.chmod(self.attestation_path, 0o600)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise LocalModelError("Local model selection could not be saved.") from None

    def select(self, value: Path | str) -> SelectedModel:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise LocalModelError("Selected local model path must be absolute.")
        if candidate.is_symlink():
            raise LocalModelError("Selected local model must not be a symlink.")
        if candidate.suffix.lower() != ".gguf":
            raise LocalModelError("Selected local model must use the .gguf extension.")
        try:
            path = candidate.resolve(strict=True)
        except OSError:
            raise LocalModelError("Selected local model is unavailable.") from None
        filename = _validate_filename(path.name)
        details, sha256 = _open_model(path, hash_file=True)
        if sha256 is None:
            raise AssertionError("model hash was not computed")
        selected = _selected(path, filename, details, sha256)
        self._write(selected)
        return selected

    def _read_attestation(self) -> dict[str, Any] | None:
        if not self.attestation_path.exists():
            return None
        if self.attestation_path.is_symlink():
            raise LocalModelError("Local model selection metadata is invalid.")
        try:
            raw = self.attestation_path.read_bytes()
            if len(raw) > MAX_ATTESTATION_BYTES:
                raise ValueError
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            raise LocalModelError("Local model selection metadata is invalid.") from None
        if not isinstance(value, dict) or set(value) != _ATTESTATION_KEYS:
            raise LocalModelError("Local model selection metadata is invalid.")
        if (
            value["schema_version"] != ATTESTATION_SCHEMA_VERSION
            or not isinstance(value["path"], str)
            or not isinstance(value["filename"], str)
            or any(
                isinstance(value[name], bool) or not isinstance(value[name], int)
                for name in ("size_bytes", "device", "inode", "mtime_ns")
            )
            or not isinstance(value["sha256"], str)
            or len(value["sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in value["sha256"])
        ):
            raise LocalModelError("Local model selection metadata is invalid.")
        _validate_filename(value["filename"])
        return value

    def resolve_selected(self) -> SelectedModel:
        value = self._read_attestation()
        if value is None:
            raise LocalModelError("No local model is selected.")
        candidate = Path(value["path"])
        if (
            not candidate.is_absolute()
            or candidate.name != value["filename"]
            or candidate.suffix.lower() != ".gguf"
            or candidate.is_symlink()
        ):
            raise LocalModelError("Local model selection metadata is invalid.")
        try:
            path = candidate.resolve(strict=True)
        except OSError:
            raise LocalModelError("Selected local model is unavailable.") from None
        details, _ = _open_model(path, hash_file=False)
        recorded_identity = (
            value["device"],
            value["inode"],
            value["size_bytes"],
            value["mtime_ns"],
        )
        current_identity = (
            details.st_dev,
            details.st_ino,
            details.st_size,
            details.st_mtime_ns,
        )
        if current_identity == recorded_identity:
            return _selected(path, value["filename"], details, value["sha256"])
        details, sha256 = _open_model(path, hash_file=True)
        if sha256 != value["sha256"]:
            raise LocalModelError("Selected local model changed after verification.")
        selected = _selected(path, value["filename"], details, sha256)
        self._write(selected)
        return selected

    def status(self) -> dict[str, Any]:
        if not self.attestation_path.exists():
            return {
                "selected": False,
                "filename": None,
                "size_bytes": None,
                "verified": False,
                "reason": "model_missing",
            }
        try:
            selected = self.resolve_selected()
        except LocalModelError:
            return {
                "selected": True,
                "filename": None,
                "size_bytes": None,
                "verified": False,
                "reason": "model_invalid",
            }
        return {
            "selected": True,
            "filename": selected.filename,
            "size_bytes": selected.size_bytes,
            "verified": True,
            "reason": None,
        }

    def clear(self) -> None:
        if not self.root.exists():
            return
        if self.root.is_symlink() or not self.root.is_dir():
            raise LocalModelError("Local model metadata directory is unsafe.")
        try:
            self.attestation_path.unlink(missing_ok=True)
        except OSError:
            raise LocalModelError("Local model selection could not be cleared.") from None


__all__ = [
    "ATTESTATION_SCHEMA_VERSION",
    "LocalModelError",
    "LocalModelManager",
    "MAX_MODEL_BYTES",
    "MIN_MODEL_BYTES",
    "SelectedModel",
]
