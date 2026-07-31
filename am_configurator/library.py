"""Durable, private storage and catalog projection for Lighting Studio assets.

The library is intentionally independent of provider and device code. It owns
procedural-job recovery plus immutable saved items. Catalog reads never invoke
paid work, local processing, or device operations. Retired video manifests are
recognized only so scans can leave their files untouched and report them as
unsupported.

Manifest schema version 2 adds a pipeline discriminator and procedural attempt
records. Future stages mutate those existing containers
(``concept_batches``, ``animation_attempts``, ``provider_requests``, ``costs``,
and ``recovery``) instead of adding ad-hoc top-level keys.  Assets are internal
relative paths in the manifest, but public views expose only opaque job and
asset UUIDs.

Saved-item schema version 1 uses an exact kind discriminator, publishes a whole
private ``items/<uuid>`` directory through one rename, and exposes jobs/items
through namespaced catalog IDs. Corrupt entries are isolated per directory.
Removal moves one exact owned UUID directory to the same root's private trash;
restore reverses that rename, while permanent deletion accepts only a
link-free trashed directory.

On POSIX, created job directories/files are explicitly owner-only.  On Windows,
CPython 3.11.10+, 3.12.4+, and 3.13+ honor ``mkdir(mode=0o700)`` with a private
DACL; preflight rejects older patch runtimes and replaces inheritance on the
``jobs`` directory with a current-user/SYSTEM/Administrators-only DACL.
Junctions and symlinks still fail closed.
"""
from __future__ import annotations

import contextlib
import copy
import errno
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Mapping

from .atomic_io import replace_file

if os.name == "nt":
    import msvcrt
else:
    import fcntl


MANIFEST_SCHEMA_VERSION = 2
SAVED_ITEM_SCHEMA_VERSION = 1
DEFAULT_MINIMUM_FREE_BYTES = 256 * 1024 * 1024
_DIRECTORIES = ("concepts", "frames", "preview", "result", ".work")
_ASSET_LAYOUT = {
    "concept": ("concepts", {"image/png": ".png", "image/jpeg": ".jpg"}),
    "selected_still": ("concepts", {"image/png": ".png", "image/jpeg": ".jpg"}),
    "frame": ("frames", {"image/png": ".png"}),
    "preview_poster": ("preview", {"image/png": ".png", "image/jpeg": ".jpg"}),
    "preview_animation": ("preview", {"image/gif": ".gif"}),
    "mapped_result": ("result", {"application/json": ".json"}),
    "recipe": ("result", {"application/json": ".json"}),
    "raster_animation": ("frames", {"image/gif": ".gif"}),
}
_ASSET_STATUSES = {"complete", "partial", "cancelled_saved"}
_SAVED_ITEM_DIRECTORIES = ("source", "preview", "result", ".work")
_SAVED_ASSET_LAYOUT = {
    "source": (
        "source",
        {"image/gif": ".gif", "image/png": ".png", "image/bmp": ".bmp"},
    ),
    "preview": (
        "preview",
        {"image/gif": ".gif", "image/png": ".png"},
    ),
    "result": (
        "result",
        {
            "application/json": ".json",
            "image/gif": ".gif",
            "image/png": ".png",
        },
    ),
    "profile": ("source", {"application/json": ".json"}),
}
_SAVED_ITEM_FIELDS = {
    "schema_version",
    "item_id",
    "kind",
    "origin",
    "name",
    "created_at",
    "updated_at",
    "status",
    "tags",
    "device",
    "source",
    "composition",
    "profile",
    "assets",
}
_SAVED_ASSET_FIELDS = {
    "asset_id",
    "kind",
    "relative_path",
    "mime_type",
    "byte_size",
    "sha256",
    "created_at",
}
_SAVED_SOURCE_FIELDS = {
    "asset_id",
    "mime_type",
    "sha256",
    "width",
    "height",
    "frame_count",
    "duration_ms",
}
_SAVED_SOURCE_INPUT_FIELDS = {
    "asset_id",
    "width",
    "height",
    "frame_count",
    "duration_ms",
}
_SAVED_DEVICE_FIELDS = {
    "product_id",
    "family",
    "product_label",
    "keymap_signature",
    "lighting_signature",
}
_SAVED_COMPOSITION_FIELDS = {
    "schema_version",
    "source_catalog_id",
    "transform",
    "effects",
    "manual_overrides",
    "destination",
    "tracks",
    "rendered_asset_id",
    "preview_asset_id",
}
_SAVED_PROFILE_FIELDS = {
    "asset_id",
    "mime_type",
    "sha256",
    "sections",
}
_SAVED_PROFILE_INPUT_FIELDS = {"asset_id", "sections"}
_SAVED_ITEM_KINDS = {
    "media_source",
    "lighting_composition",
    "keyboard_profile",
}
_CATALOG_KINDS = {*_SAVED_ITEM_KINDS, "generation_job"}
_CATALOG_KIND_GROUPS = {
    "lighting": frozenset({"generation_job", "lighting_composition"}),
}
_SAVED_ITEM_ORIGINS = {
    "media_source": {"media_import"},
    "lighting_composition": {"manual"},
    "keyboard_profile": {"json_import", "verified_export"},
}
_SAVED_ITEM_STATUSES = {"ready"}
_MAX_SAVED_ASSETS = 8
_MAX_SAVED_TAGS = 32
_MAX_SAVED_TEXT = 200
_MAX_SAVED_JSON_DEPTH = 16
_MAX_SAVED_JSON_ITEMS = 4096
_LOOP_MODES = {"smooth", "none", "ping_pong"}
_SAFE_TEXT_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
_SAFE_ERROR_CODE = re.compile(r"^[a-z0-9_]{1,80}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "auth_header",
    "client_secret",
    "credential",
    "credentials",
    "headers",
    "password",
    "refresh_token",
    "secret",
    "signed_url",
    "token",
    "media_url",
    "download_url",
    "image_url",
    "video_url",
}
_TERMINAL_OR_IDLE_STATUSES = {
    "awaiting_selection",
    "partial",
    "cancelled",
    "cancelled_saved",
    "failed",
    "expired",
    "interrupted",
    "ready",
    "ready_to_process",
    "submission_unknown",
}
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_MAX_MANIFEST_BYTES = 10 * 1024 * 1024
_MAX_ASSET_INTENT_BYTES = 64 * 1024
_UUID_ATTEMPTS = 32
_ASSET_INTENT_PREFIX = ".asset-intent-"
_PROVIDER_REQUEST_FIELDS = {
    "request_id",
    "status",
    "submitted_at",
    "last_polled_at",
    "next_poll_at",
    "foreground_deadline_at",
    "completed_at",
    "downloaded_at",
    "poll_failures",
    "download_failures",
    "retry_after_seconds",
    "error_code",
}
_PROVIDER_REQUEST_TIMESTAMPS = {
    "submitted_at",
    "last_polled_at",
    "next_poll_at",
    "foreground_deadline_at",
    "completed_at",
    "downloaded_at",
}
_PROVIDER_REQUEST_COUNTS = {
    "poll_failures",
    "download_failures",
    "retry_after_seconds",
}
_MANIFEST_V1_FIELDS = {
    "schema_version",
    "job_id",
    "created_at",
    "updated_at",
    "prompt",
    "target",
    "concept_batches",
    "candidates",
    "selected_candidate_id",
    "animation_attempts",
    "loop_mode",
    "models",
    "provider_requests",
    "status",
    "phase",
    "progress",
    "assets",
    "costs",
    "cancel_requested_at",
    "cancelled_at",
    "errors",
    "recovery",
}
_MANIFEST_V2_FIELDS = _MANIFEST_V1_FIELDS | {"pipeline", "procedural_attempts"}
_PIPELINES = {"legacy_video", "procedural"}
_PROCEDURAL_ATTEMPT_FIELDS = {
    "attempt_id",
    "index",
    "status",
    "phase",
    "started_at",
    "completed_at",
    "recipe_asset_id",
    "raster_asset_id",
    "preview_asset_id",
    "mapped_result_asset_id",
    "quality",
    "usage",
    "error_code",
}
_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}
_JOB_LOCK_TIMEOUT_SECONDS = 10.0
_JOB_LOCK_RETRY_SECONDS = 0.1
_JOB_LOCKED_MESSAGE = "The generated job is locked by another process."


class LibraryError(RuntimeError):
    """Base class for safe, user-reportable library failures."""


class LibraryRootError(LibraryError):
    """The configured library root is absent or fails preflight."""


class LibraryItemStateError(LibraryError):
    """A Library mutation conflicts with the item's current owned state."""


class LibraryItemActiveError(LibraryItemStateError):
    """A Library item cannot move while its operation is active."""


class ManifestError(LibraryError):
    """A manifest is corrupt, unsafe, or violates its schema."""


class InvalidIdentifierError(LibraryError):
    """A job or asset identifier is not a canonical opaque UUID."""


class AssetNotFoundError(LibraryError):
    """The requested asset is not owned by the requested job."""


def _file_stat_identity(details: os.stat_result) -> tuple[int, ...]:
    """Identify file content only, so a path stat and a handle stat can agree.

    Windows reports ``st_ctime_ns`` (creation time) at different resolutions
    through a path query and through an open handle, so a freshly written asset
    disagrees with itself and every banked asset is rejected.  ``st_mode`` and
    reparse status are asserted directly against both the path and the
    descriptor by the callers, so excluding them here removes no check.
    """
    return (
        details.st_dev,
        details.st_ino,
        details.st_size,
        details.st_mtime_ns,
    )


def _stat_is_reparse_point(details: os.stat_result) -> bool:
    attributes = getattr(details, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


@dataclass(frozen=True)
class OwnedAsset:
    """A manifest-owned asset.

    ``path`` is advisory metadata for local management only.  Authenticated
    serving code must use :meth:`open_verified` and stream from the returned
    descriptor rather than reopening ``path`` after lookup.
    """

    path: Path
    record: dict

    @property
    def mime_type(self) -> str:
        return self.record["mime_type"]

    def open_verified(self, *, verify_content: bool = True):
        """Open and integrity-check one stable descriptor for authenticated serving.

        ``verify_content=False`` keeps every path and descriptor check and the
        recorded size, but skips reading the file to confirm its digest.  It
        exists for Range requests, where re-reading the whole file on every seek
        dominates the cost of serving a slice of it.  A non-Range read still
        verifies the bytes, so altered content is caught the first time an asset
        is viewed.
        """
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            before = self.path.lstat()
            if not stat.S_ISREG(before.st_mode) or _stat_is_reparse_point(before):
                raise ManifestError("The owned asset path is unsafe or missing.")
            fd = os.open(self.path, flags)
            file = os.fdopen(fd, "rb")
            info = os.fstat(file.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or _stat_is_reparse_point(info)
                or _file_stat_identity(before) != _file_stat_identity(info)
            ):
                raise ManifestError("The owned asset path is unsafe or missing.")
            content_matches = True
            if verify_content:
                digest = hashlib.sha256()
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
                content_matches = hmac.compare_digest(
                    digest.hexdigest(), self.record["sha256"]
                )
            after = os.fstat(file.fileno())
            after_path = self.path.lstat()
            if (
                _file_stat_identity(info) != _file_stat_identity(after)
                or _file_stat_identity(info) != _file_stat_identity(after_path)
                or info.st_size != self.record["byte_size"]
                or not content_matches
            ):
                raise ManifestError("The owned asset failed its integrity check.")
            file.seek(0)
            return file
        except OSError:
            if "file" in locals():
                file.close()
            raise ManifestError("The owned asset path is unsafe or missing.") from None
        except BaseException:
            if "file" in locals():
                file.close()
            raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidIdentifierError(f"{label} must be an opaque UUID")
    try:
        canonical = str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise InvalidIdentifierError(f"{label} must be an opaque UUID") from exc
    if canonical != value:
        raise InvalidIdentifierError(f"{label} must be a canonical opaque UUID")
    return canonical


def _windows_private_mode_supported(version_info: object) -> bool:
    """Whether this CPython version honors private Windows ``mkdir`` mode."""
    try:
        major, minor, micro = tuple(version_info)[:3]
    except (TypeError, ValueError):
        return False
    if not all(isinstance(part, int) for part in (major, minor, micro)):
        return False
    if major > 3:
        return True
    if major != 3:
        return False
    if minor >= 13:
        return True
    if minor == 12:
        return micro >= 4
    if minor == 11:
        return micro >= 10
    return False


def _canonical_root(value: str | os.PathLike[str] | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise LibraryRootError("The library folder must be an absolute path.")
    if os.name == "nt" and _windows_path_has_reparse_component(path):
        raise LibraryRootError(
            "The Windows library path contains a junction or reparse point."
        )
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise LibraryRootError("The library folder could not be canonicalized.") from exc


def _is_linklike(path: Path) -> bool:
    """Treat symlinks and Windows junction/reparse directories as unsafe."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        if os.name != "nt":
            return False
        attributes = getattr(path.lstat(), "st_file_attributes", None)
        if not isinstance(attributes, int):
            return True
        return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _windows_path_has_reparse_component(path: Path) -> bool:
    """Inspect each existing raw path component before Windows resolution."""
    for candidate in (path, *path.parents):
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return True
        if _is_linklike(candidate):
            return True
    return False


def _make_private_directory(path: Path, *, parents: bool = False) -> None:
    existed = path.exists()
    path.mkdir(mode=0o700, parents=parents, exist_ok=True)
    if os.name != "nt" and not existed:
        os.chmod(path, 0o700)


def _set_windows_private_directory_dacl(path: Path) -> None:
    """Replace a directory DACL with the CPython ``mkdir(0o700)`` policy."""
    if os.name != "nt":
        raise OSError("Windows directory privacy is unavailable.")

    import ctypes
    from ctypes import wintypes

    token_query = 0x0008
    token_user_class = 1
    error_insufficient_buffer = 122
    sddl_revision_1 = 1
    se_file_object = 1
    dacl_security_information = 0x00000004
    protected_dacl_security_information = 0x80000000

    class SidAndAttributes(ctypes.Structure):
        _fields_ = [
            ("sid", ctypes.c_void_p),
            ("attributes", wintypes.DWORD),
        ]

    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = (
        wintypes.BOOL
    )
    advapi32.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), token_query, ctypes.byref(token)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(
            token, token_user_class, None, 0, ctypes.byref(required)
        )
        if (
            ctypes.get_last_error() != error_insufficient_buffer
            or required.value == 0
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        token_buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(
            token,
            token_user_class,
            token_buffer,
            required,
            ctypes.byref(required),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        token_user = ctypes.cast(
            token_buffer, ctypes.POINTER(SidAndAttributes)
        ).contents
        sid_text_buffer = ctypes.c_void_p()
        if not advapi32.ConvertSidToStringSidW(
            token_user.sid, ctypes.byref(sid_text_buffer)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            user_sid = ctypes.wstring_at(sid_text_buffer.value)
        finally:
            kernel32.LocalFree(sid_text_buffer)
    finally:
        kernel32.CloseHandle(token)

    descriptor_text = (
        f"D:P(A;OICI;FA;;;{user_sid})"
        "(A;OICI;FA;;;SY)"
        "(A;OICI;FA;;;BA)"
    )
    descriptor = ctypes.c_void_p()
    descriptor_size = wintypes.DWORD()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        descriptor_text,
        sddl_revision_1,
        ctypes.byref(descriptor),
        ctypes.byref(descriptor_size),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        dacl_present = wintypes.BOOL()
        dacl_defaulted = wintypes.BOOL()
        dacl = ctypes.c_void_p()
        if not advapi32.GetSecurityDescriptorDacl(
            descriptor,
            ctypes.byref(dacl_present),
            ctypes.byref(dacl),
            ctypes.byref(dacl_defaulted),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not dacl_present.value or not dacl.value:
            raise OSError("Private Windows directory DACL was unavailable.")
        result = advapi32.SetNamedSecurityInfoW(
            str(path),
            se_file_object,
            dacl_security_information | protected_dacl_security_information,
            None,
            None,
            dacl,
            None,
        )
        if result:
            raise ctypes.WinError(result)
    finally:
        kernel32.LocalFree(descriptor)


def _fsync_directory(path: Path) -> None:
    """Best-effort metadata sync where directory fsync is supported.

    Asset and manifest file contents are always fsynced before replacement.
    Windows has no directory-fsync primitive exposed here; Unix filesystems
    that reject opening/syncing directories are treated as unsupported rather
    than turning a completed atomic replace into an ambiguous failure.
    """
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            return
        raise
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            raise
    finally:
        os.close(fd)


def _run_write_probe(root: Path) -> None:
    """Create, sync, and remove an owner-only probe in the selected root."""
    probe = root / f".am-write-probe-{uuid.uuid4()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(probe, flags, 0o600)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        os.write(fd, b"am-configurator-library-probe\n")
        os.fsync(fd)
    finally:
        os.close(fd)
        probe.unlink(missing_ok=True)
    _fsync_directory(root)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    _make_private_directory(path.parent, parents=True)
    fd, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        replace_file(temporary_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, value: object) -> None:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write_bytes(path, payload)


def _windows_path_too_long(error: OSError) -> bool:
    return error.errno == errno.ENAMETOOLONG or getattr(error, "winerror", None) == 206


def _run_windows_path_depth_probe(
    root: Path,
    owned_directory_name: str = "jobs",
) -> None:
    """Exercise the deepest owned temporary path and remove it."""
    if owned_directory_name == "jobs":
        # Asset-intent atomic publication is the deepest generated path shape:
        # jobs/<job>/.work/.asset-intent-<asset>.json.<8-char>.tmp
        probe_owner = root / "jobs" / f".am-depth-{uuid.uuid4().hex[:26]}"
        probe_work = probe_owner / ".work"
    elif owned_directory_name == "items":
        # Saved items publish a complete hidden directory before one rename:
        # items/.item-<item>-<uuid>.tmp/result/<asset>.json.<8-char>.tmp
        probe_owner = (
            root
            / "items"
            / f".item-{uuid.uuid4()}-{uuid.uuid4()}.tmp"
        )
        probe_work = probe_owner / "result"
    else:
        raise ValueError("owned_directory_name is unsupported")
    intent = probe_work / f"{_ASSET_INTENT_PREFIX}{uuid.uuid4()}.json"
    failure: BaseException | None = None
    cleanup_failure: OSError | None = None
    try:
        _make_private_directory(probe_work, parents=True)
        _atomic_write_bytes(intent, b"{}\n")
    except BaseException as exc:
        failure = exc
    try:
        if probe_owner.exists() or probe_owner.is_symlink():
            if _is_linklike(probe_owner):
                raise OSError("Windows path-depth probe directory is unsafe")
            shutil.rmtree(probe_owner)
    except OSError as exc:
        cleanup_failure = exc
    if isinstance(failure, OSError) and _windows_path_too_long(failure):
        raise LibraryRootError(
            "The configured Windows library path is too long for generated files; "
            "choose a shorter library folder or enable Windows long-path support."
        ) from failure
    if failure is not None:
        raise failure
    if cleanup_failure is not None:
        raise cleanup_failure


def _preflight_private_root(
    current_root: str | os.PathLike[str] | None,
    owned_directory_name: str,
    *,
    minimum_free_bytes: int,
    disk_usage: Callable[[str | os.PathLike[str]], object],
    missing_message: str,
    unavailable_message: str,
    free_space_message: str,
) -> Path:
    if os.name == "nt" and (
        sys.implementation.name != "cpython"
        or not _windows_private_mode_supported(sys.version_info)
    ):
        raise LibraryRootError(
            "Private Windows library folders require CPython 3.11.10+, "
            "3.12.4+, or 3.13+."
        )
    if current_root is None:
        raise LibraryRootError(missing_message)
    root = _canonical_root(current_root)
    assert root is not None
    try:
        _make_private_directory(root, parents=True)
        if not root.is_dir() or _is_linklike(root):
            raise OSError("root is not a real directory")
        owned_directory = root / owned_directory_name
        _make_private_directory(owned_directory)
        if _is_linklike(owned_directory) or not owned_directory.is_dir():
            raise OSError(
                f"{owned_directory_name} directory is not a real directory"
            )
        if os.name != "nt":
            os.chmod(owned_directory, 0o700)
        else:
            _set_windows_private_directory_dacl(owned_directory)
            if owned_directory_name == "jobs":
                _run_windows_path_depth_probe(root)
            else:
                _run_windows_path_depth_probe(root, owned_directory_name)
        _run_write_probe(root)
        free = disk_usage(root).free
    except LibraryRootError:
        raise
    except (OSError, PermissionError, AttributeError) as exc:
        raise LibraryRootError(unavailable_message) from exc
    if not isinstance(free, int) or free < minimum_free_bytes:
        raise LibraryRootError(free_space_message)
    return root


def _file_integrity(path: Path) -> tuple[int, str, tuple[int, ...]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or _stat_is_reparse_point(before):
            raise OSError
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as file:
            info = os.fstat(file.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or _stat_is_reparse_point(info)
                or _file_stat_identity(before) != _file_stat_identity(info)
            ):
                raise ManifestError("The owned asset path is unsafe or missing.")
            digest = hashlib.sha256()
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(file.fileno())
            after_path = path.lstat()
            identity = _file_stat_identity(info)
            if (
                identity != _file_stat_identity(after)
                or identity != _file_stat_identity(after_path)
            ):
                raise ManifestError("The owned asset changed during verification.")
            return info.st_size, digest.hexdigest(), identity
    except OSError as exc:
        raise ManifestError("The owned asset integrity could not be verified.") from exc


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _acquire_job_file_lock(
    file,
    *,
    windows: bool,
    timeout_seconds: float = _JOB_LOCK_TIMEOUT_SECONDS,
    retry_seconds: float = _JOB_LOCK_RETRY_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
    wait: Callable[[float], object] = time.sleep,
) -> None:
    """Acquire the platform file lock within one monotonic bounded budget."""
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            if windows:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if not windows and exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError(_JOB_LOCKED_MESSAGE) from exc
            wait(min(retry_seconds, remaining))


@contextlib.contextmanager
def _job_lock(job_dir: Path):
    lock_path = job_dir / ".lock"
    if _is_linklike(lock_path):
        raise ManifestError("The job lock is unsafe.")
    process_lock = _thread_lock(lock_path)
    with process_lock:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise ManifestError("The job lock is unsafe.") from exc
        with os.fdopen(fd, "r+b") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ManifestError("The job lock is unsafe.")
            if os.name != "nt":
                os.fchmod(file.fileno(), 0o600)
            else:
                file.seek(0, os.SEEK_END)
                if file.tell() == 0:
                    file.write(b"\0")
                    file.flush()
            _acquire_job_file_lock(file, windows=os.name == "nt")
            try:
                yield
            finally:
                if os.name == "nt":
                    file.seek(0)
                    msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _tree_contains_linklike(path: Path) -> bool:
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                details = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or _stat_is_reparse_point(details):
                    return True
                if stat.S_ISDIR(details.st_mode) and _tree_contains_linklike(
                    Path(entry.path)
                ):
                    return True
    except OSError as exc:
        raise ManifestError("The trashed Library item is unsafe.") from exc
    return False


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized == "url" or normalized in _SENSITIVE_KEYS or normalized.endswith(
        (
            "_api_key",
            "_credential",
            "_credentials",
            "_password",
            "_private_key",
            "_secret",
            "_signed_url",
            "_token",
            "_url",
        )
    )


def _validate_no_sensitive_values(value: object, *, key: str | None = None) -> None:
    if key is not None and _is_sensitive_key(key):
        raise ManifestError("The manifest cannot contain sensitive provider data.")
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise ManifestError("Manifest object keys must be strings.")
            _validate_no_sensitive_values(child, key=child_key)
        return
    if isinstance(value, list):
        for child in value:
            _validate_no_sensitive_values(child)
        return
    if isinstance(value, str):
        lowered = value.casefold()
        if "data:" in lowered and ";base64," in lowered:
            raise ManifestError("The manifest cannot contain sensitive provider data.")
        if re.search(r"\bbearer\s+\S+", value, re.IGNORECASE):
            raise ManifestError("The manifest cannot contain sensitive provider data.")
        if re.search(
            r"https?://\S*[?&](?:x-amz-signature|x-goog-signature|signature|sig|token)=",
            value,
            re.IGNORECASE,
        ):
            raise ManifestError("The manifest cannot contain sensitive provider data.")


def _validate_relative_asset_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError("An asset path is invalid.")
    if "\\" in value:
        raise ManifestError("An asset path is unsafe.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or len(path.parts) != 2:
        raise ManifestError("An asset path is unsafe.")
    return value


def _validate_request_ids(value: object) -> None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            if child_key == "request_id" and child is not None:
                if not isinstance(child, str) or not _SAFE_REQUEST_ID.fullmatch(child):
                    raise ManifestError("A provider request ID is unsafe.")
            _validate_request_ids(child)
    elif isinstance(value, list):
        for child in value:
            _validate_request_ids(child)


def _validate_manifest(value: object, *, expected_job_id: str | None = None) -> dict:
    if not isinstance(value, dict):
        raise ManifestError("The job manifest is invalid.")
    value = copy.deepcopy(value)
    version = value.get("schema_version")
    if version == 1:
        if set(value) != _MANIFEST_V1_FIELDS:
            raise ManifestError("The job manifest has an unsupported schema.")
        value["schema_version"] = MANIFEST_SCHEMA_VERSION
        value["pipeline"] = "legacy_video"
        value["procedural_attempts"] = []
    elif version != MANIFEST_SCHEMA_VERSION:
        raise ManifestError("The job manifest schema is unsupported.")
    pipeline = value.get("pipeline")
    if pipeline not in _PIPELINES:
        raise ManifestError("The job manifest pipeline is unsupported.")
    _validate_request_ids(value)
    _validate_no_sensitive_values(value)
    fields = set(value)
    supported_fields = (fields == _MANIFEST_V2_FIELDS) or (
        pipeline == "procedural"
        and fields == _MANIFEST_V2_FIELDS - {"loop_mode"}
    )
    if not supported_fields:
        raise ManifestError("The job manifest has an unsupported schema.")
    job_id = _canonical_uuid(value["job_id"], "job ID")
    if expected_job_id is not None and job_id != expected_job_id:
        raise ManifestError("The job manifest does not own this directory.")
    if not isinstance(value["created_at"], str) or not isinstance(value["updated_at"], str):
        raise ManifestError("The job manifest timestamps are invalid.")
    if not isinstance(value["prompt"], str):
        raise ManifestError("The job prompt is invalid.")
    if "loop_mode" in value and (
        not isinstance(value["loop_mode"], str)
        or value["loop_mode"] not in _LOOP_MODES
    ):
        raise ManifestError("The job loop mode is invalid.")
    for name in ("target", "models", "provider_requests", "progress", "costs", "recovery"):
        if not isinstance(value[name], dict):
            raise ManifestError(f"The job manifest {name} field is invalid.")
    for name in (
        "concept_batches",
        "candidates",
        "animation_attempts",
        "procedural_attempts",
        "assets",
        "errors",
    ):
        if not isinstance(value[name], list):
            raise ManifestError(f"The job manifest {name} field is invalid.")
    if value["pipeline"] == "legacy_video" and value["procedural_attempts"]:
        raise ManifestError("A legacy job cannot contain procedural attempts.")
    for name in ("status", "phase"):
        if not isinstance(value[name], str) or not _SAFE_TEXT_ID.fullmatch(value[name]):
            raise ManifestError(f"The job manifest {name} is invalid.")
    if value["selected_candidate_id"] is not None:
        _canonical_uuid(value["selected_candidate_id"], "selected candidate ID")
    for name in ("cancel_requested_at", "cancelled_at"):
        if value[name] is not None and not isinstance(value[name], str):
            raise ManifestError(f"The job manifest {name} is invalid.")

    seen_attempt_ids: set[str] = set()
    seen_attempt_indexes: set[int] = set()
    quality_fields = {
        "width",
        "height",
        "frame_count",
        "density",
        "minimum_lit_ratio",
        "maximum_lit_ratio",
        "peak_brightness",
        "maximum_adjacent_difference",
        "seam_difference",
    }
    for attempt in value["procedural_attempts"]:
        if not isinstance(attempt, dict) or set(attempt) != _PROCEDURAL_ATTEMPT_FIELDS:
            raise ManifestError("A procedural attempt has an unsupported schema.")
        attempt_id = _canonical_uuid(attempt["attempt_id"], "procedural attempt ID")
        index = attempt["index"]
        if (
            attempt_id in seen_attempt_ids
            or type(index) is not int
            or not 0 <= index <= 2
            or index in seen_attempt_indexes
        ):
            raise ManifestError("A procedural attempt identity is invalid.")
        seen_attempt_ids.add(attempt_id)
        seen_attempt_indexes.add(index)
        for name in ("status", "phase"):
            if not isinstance(attempt[name], str) or not _SAFE_TEXT_ID.fullmatch(
                attempt[name]
            ):
                raise ManifestError("A procedural attempt state is invalid.")
        if not isinstance(attempt["started_at"], str) or (
            attempt["completed_at"] is not None
            and not isinstance(attempt["completed_at"], str)
        ):
            raise ManifestError("A procedural attempt timestamp is invalid.")
        for name in (
            "recipe_asset_id",
            "raster_asset_id",
            "preview_asset_id",
            "mapped_result_asset_id",
        ):
            if attempt[name] is not None:
                _canonical_uuid(attempt[name], "procedural asset ID")
        error_code = attempt["error_code"]
        if error_code is not None and (
            not isinstance(error_code, str) or not _SAFE_ERROR_CODE.fullmatch(error_code)
        ):
            raise ManifestError("A procedural attempt error code is invalid.")
        usage = attempt["usage"]
        if usage is not None and (
            not isinstance(usage, dict)
            or set(usage) != {"cost_in_usd_ticks"}
            or type(usage["cost_in_usd_ticks"]) is not int
            or usage["cost_in_usd_ticks"] < 0
        ):
            raise ManifestError("A procedural attempt usage record is invalid.")
        quality = attempt["quality"]
        if quality is not None:
            if not isinstance(quality, dict) or set(quality) != quality_fields:
                raise ManifestError("A procedural quality record is invalid.")
            if (
                any(type(quality[name]) is not int or quality[name] < 1 for name in ("width", "height", "frame_count"))
                or type(quality["peak_brightness"]) is not int
                or not 0 <= quality["peak_brightness"] <= 255
                or quality["density"] not in {"sparse", "balanced", "dense"}
            ):
                raise ManifestError("A procedural quality record is invalid.")
            for name in (
                "minimum_lit_ratio",
                "maximum_lit_ratio",
                "maximum_adjacent_difference",
                "seam_difference",
            ):
                metric = quality[name]
                if (
                    isinstance(metric, bool)
                    or not isinstance(metric, (int, float))
                    or not math.isfinite(float(metric))
                    or metric < 0
                ):
                    raise ManifestError("A procedural quality record is invalid.")

    for operation, request in value["provider_requests"].items():
        if not isinstance(operation, str) or not _SAFE_TEXT_ID.fullmatch(operation):
            raise ManifestError("A provider request operation key is invalid.")
        if not isinstance(request, dict) or not set(request).issubset(
            _PROVIDER_REQUEST_FIELDS
        ):
            raise ManifestError("A provider request record has an unsupported schema.")
        if "status" not in request:
            raise ManifestError("A provider request record requires status.")
        status_value = request["status"]
        if not isinstance(status_value, str) or not _SAFE_TEXT_ID.fullmatch(status_value):
            raise ManifestError("A provider request status is invalid.")
        request_id_value = request.get("request_id")
        if request_id_value is not None and (
            not isinstance(request_id_value, str)
            or not _SAFE_REQUEST_ID.fullmatch(request_id_value)
        ):
            raise ManifestError("A provider request ID is unsafe.")
        for field in _PROVIDER_REQUEST_TIMESTAMPS:
            field_value = request.get(field)
            if field_value is not None and not isinstance(field_value, str):
                raise ManifestError("A provider request timestamp is invalid.")
        for field in _PROVIDER_REQUEST_COUNTS:
            field_value = request.get(field)
            if field_value is not None and (
                not isinstance(field_value, int)
                or isinstance(field_value, bool)
                or field_value < 0
            ):
                raise ManifestError("A provider request retry value is invalid.")
        error_code = request.get("error_code")
        if error_code is not None and (
            not isinstance(error_code, str) or not _SAFE_ERROR_CODE.fullmatch(error_code)
        ):
            raise ManifestError("A provider request error code is invalid.")

    progress = value["progress"]
    if set(progress) != {"completed", "total"}:
        raise ManifestError("The job progress has an unsupported schema.")
    completed = progress["completed"]
    total = progress["total"]
    if not isinstance(completed, int) or isinstance(completed, bool) or completed < 0:
        raise ManifestError("The job progress is invalid.")
    if total is not None and (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < completed
    ):
        raise ManifestError("The job progress is invalid.")

    costs = value["costs"]
    if set(costs) != {"estimated_ticks", "actual_by_operation", "actual_incomplete"}:
        raise ManifestError("The job cost record has an unsupported schema.")
    estimated_ticks = costs["estimated_ticks"]
    if (
        estimated_ticks is not None
        and (
            not isinstance(estimated_ticks, int)
            or isinstance(estimated_ticks, bool)
            or estimated_ticks < 0
        )
    ):
        raise ManifestError(
            "The job cost estimate must be a non-negative integer or null."
        )
    actual_by_operation = costs["actual_by_operation"]
    if not isinstance(actual_by_operation, dict):
        raise ManifestError("The job cost record is invalid.")
    for operation, ticks in actual_by_operation.items():
        if not isinstance(operation, str) or not _SAFE_TEXT_ID.fullmatch(operation):
            raise ManifestError("A charged-operation key is invalid.")
        if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 0:
            raise ManifestError("The job cost ticks must be non-negative integers.")
    if not isinstance(costs["actual_incomplete"], bool):
        raise ManifestError("The job cost completeness flag is invalid.")

    for error in value["errors"]:
        if not isinstance(error, dict) or set(error) != {"code", "message", "created_at"}:
            raise ManifestError("An error record has an unsupported schema.")
        if not isinstance(error["code"], str) or not _SAFE_ERROR_CODE.fullmatch(error["code"]):
            raise ManifestError("An error record code is invalid.")
        if (
            not isinstance(error["message"], str)
            or len(error["message"]) > 1000
            or _safe_error_message(error["message"]) != error["message"]
        ):
            raise ManifestError("An error record message is not sanitized.")
        if not isinstance(error["created_at"], str):
            raise ManifestError("An error record timestamp is invalid.")

    seen_assets: set[str] = set()
    for record in value["assets"]:
        if not isinstance(record, dict) or set(record) != {
            "asset_id",
            "kind",
            "relative_path",
            "mime_type",
            "byte_size",
            "sha256",
            "origin",
            "created_at",
            "status",
        }:
            raise ManifestError("An asset record has an unsupported schema.")
        asset_id = _canonical_uuid(record["asset_id"], "asset ID")
        if asset_id in seen_assets:
            raise ManifestError("An asset ID is duplicated.")
        seen_assets.add(asset_id)
        kind = record["kind"]
        if kind not in _ASSET_LAYOUT:
            raise ManifestError("An asset kind is unsupported.")
        relative = _validate_relative_asset_path(record["relative_path"])
        expected_directory, allowed_mimes = _ASSET_LAYOUT[kind]
        if PurePosixPath(relative).parts[0] != expected_directory:
            raise ManifestError("An asset path does not match its kind.")
        mime_type = record["mime_type"]
        if mime_type not in allowed_mimes:
            raise ManifestError("An asset MIME type is unsupported.")
        if PurePosixPath(relative).suffix != allowed_mimes[mime_type]:
            raise ManifestError("An asset extension does not match its MIME type.")
        if not isinstance(record["byte_size"], int) or isinstance(record["byte_size"], bool) or record["byte_size"] < 0:
            raise ManifestError("An asset byte size is invalid.")
        if not isinstance(record["sha256"], str) or not _SHA256.fullmatch(record["sha256"]):
            raise ManifestError("An asset hash is invalid.")
        if not isinstance(record["origin"], str) or not _SAFE_TEXT_ID.fullmatch(record["origin"]):
            raise ManifestError("An asset origin is invalid.")
        if not isinstance(record["created_at"], str):
            raise ManifestError("An asset timestamp is invalid.")
        if record["status"] not in _ASSET_STATUSES:
            raise ManifestError("An asset status is invalid.")
    for attempt in value["procedural_attempts"]:
        for name in (
            "recipe_asset_id",
            "raster_asset_id",
            "preview_asset_id",
            "mapped_result_asset_id",
        ):
            if attempt[name] is not None and attempt[name] not in seen_assets:
                raise ManifestError("A procedural attempt references a missing asset.")
    return copy.deepcopy(value)


def _read_manifest_value(path: Path) -> object:
    if _is_linklike(path) or not path.is_file():
        raise ManifestError("This job manifest could not be read.")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ManifestError("This job manifest could not be read.")
            payload = file.read(_MAX_MANIFEST_BYTES + 1)
        if len(payload) > _MAX_MANIFEST_BYTES:
            raise ManifestError("This job manifest could not be read.")
        return json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ManifestError("This job manifest could not be read.") from exc


def _read_manifest(path: Path, job_id: str) -> dict:
    try:
        return _validate_manifest(
            _read_manifest_value(path),
            expected_job_id=job_id,
        )
    except RecursionError as exc:
        raise ManifestError("This job manifest could not be read.") from exc


def _read_asset_intent(path: Path) -> dict:
    if _is_linklike(path) or not path.is_file():
        raise ManifestError("An asset publication intent is invalid.")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ManifestError("An asset publication intent is invalid.")
            payload = file.read(_MAX_ASSET_INTENT_BYTES + 1)
        if len(payload) > _MAX_ASSET_INTENT_BYTES:
            raise ManifestError("An asset publication intent is invalid.")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ManifestError("An asset publication intent is invalid.") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "record"}:
        raise ManifestError("An asset publication intent is invalid.")
    if value["schema_version"] != 1 or not isinstance(value["record"], dict):
        raise ManifestError("An asset publication intent is invalid.")
    return value


def _redact_local_paths(value: str) -> str:
    redacted = re.sub(
        r"(?<![A-Za-z0-9:])/(?:[^\s,;]+)",
        "[local path]",
        value,
    )
    return re.sub(
        r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:\\|\\\\)[^\s,;]+",
        "[local path]",
        redacted,
    )


def _safe_error_message(message: object) -> str:
    if not isinstance(message, str):
        return "The operation failed."
    sanitized = re.sub(
        r"\bauthorization\s*:\s*bearer\s+\S+",
        "Authorization: [redacted]",
        message,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"\bbearer\s+\S+", "Bearer [redacted]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(
        r"\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
        r"private[_-]?key|password|credentials?|token)\s*[:=]\s*"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
        lambda match: f"{match.group(1)}=[redacted]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"\b(?:xai|sk)-[A-Za-z0-9_-]{6,}\b",
        "[credential]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"data:[^\s]+;base64,[^\s]+", "[data-url]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"https?://\S+", "[url]", sanitized, flags=re.IGNORECASE)
    return _redact_local_paths(sanitized)[:1000]


class GeneratedAssetLibrary:
    """Manifest-backed generated media across one current and older roots."""

    def __init__(
        self,
        current_root: str | os.PathLike[str] | None,
        historical_roots: list[str | os.PathLike[str]] | tuple[str | os.PathLike[str], ...] = (),
        *,
        minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES,
        disk_usage: Callable[[str | os.PathLike[str]], object] = shutil.disk_usage,
    ) -> None:
        if not isinstance(minimum_free_bytes, int) or isinstance(minimum_free_bytes, bool) or minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes must be a non-negative integer")
        self._current_root_value = current_root
        self._historical_root_values = tuple(historical_roots)
        self._minimum_free_bytes = minimum_free_bytes
        self._disk_usage = disk_usage

    def _resolved_roots(self) -> tuple[list[Path], list[dict]]:
        roots: list[Path] = []
        errors: list[dict] = []
        seen: set[str] = set()
        for value in (self._current_root_value, *self._historical_root_values):
            if value is None:
                continue
            try:
                root = _canonical_root(value)
            except LibraryRootError:
                errors.append(
                    {
                        "job_id": None,
                        "code": "root_unavailable",
                        "message": "A recorded library root could not be read.",
                    }
                )
                continue
            assert root is not None
            key = os.path.normcase(str(root))
            if key not in seen:
                seen.add(key)
                roots.append(root)
        return roots, errors

    def _roots(self) -> list[Path]:
        return self._resolved_roots()[0]

    def preflight(self) -> Path:
        """Validate the current root before paid work; no fallback is possible."""
        return _preflight_private_root(
            self._current_root_value,
            "jobs",
            minimum_free_bytes=self._minimum_free_bytes,
            disk_usage=self._disk_usage,
            missing_message="A library folder must be configured before generation.",
            unavailable_message=(
                "The configured library folder is not privately writable."
            ),
            free_space_message=(
                "The configured library folder does not have enough free space."
            ),
        )

    def create_job(
        self,
        *,
        prompt: str = "",
        target: Mapping[str, object] | None = None,
        models: Mapping[str, object] | None = None,
    ) -> dict:
        """Create an owner-private procedural job and its initial manifest."""
        root = self.preflight()
        jobs_dir = root / "jobs"
        job_dir: Path | None = None
        job_id: str | None = None
        for _attempt in range(_UUID_ATTEMPTS):
            candidate_id = str(uuid.uuid4())
            candidate_dir = jobs_dir / candidate_id
            try:
                candidate_dir.mkdir(mode=0o700, exist_ok=False)
            except FileExistsError:
                continue
            job_id = candidate_id
            job_dir = candidate_dir
            break
        if job_dir is None or job_id is None:
            raise LibraryError("A unique generated job ID could not be allocated.")
        try:
            if os.name != "nt":
                os.chmod(job_dir, 0o700)
            for name in _DIRECTORIES:
                directory = job_dir / name
                _make_private_directory(directory)
                if os.name != "nt":
                    os.chmod(directory, 0o700)
            timestamp = _now_iso()
            manifest = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "pipeline": "procedural",
                "job_id": job_id,
                "created_at": timestamp,
                "updated_at": timestamp,
                "prompt": prompt,
                "target": copy.deepcopy(dict(target or {})),
                "concept_batches": [],
                "candidates": [],
                "selected_candidate_id": None,
                "animation_attempts": [],
                "procedural_attempts": [],
                "models": copy.deepcopy(dict(models or {})),
                "provider_requests": {},
                "status": "created",
                "phase": "preflight",
                "progress": {"completed": 0, "total": None},
                "assets": [],
                "costs": {
                    "estimated_ticks": None,
                    "actual_by_operation": {},
                    "actual_incomplete": False,
                },
                "cancel_requested_at": None,
                "cancelled_at": None,
                "errors": [],
                "recovery": {},
            }
            normalized = _validate_manifest(manifest, expected_job_id=job_id)
            with _job_lock(job_dir):
                _atomic_write_json(job_dir / "manifest.json", normalized)
            return normalized
        except BaseException:
            if job_dir.exists() and not _is_linklike(job_dir):
                shutil.rmtree(job_dir)
            raise

    def preflight_job(self, job_id: str) -> Path:
        """Recheck an existing job's owning root before another paid operation."""
        if os.name == "nt" and (
            sys.implementation.name != "cpython"
            or not _windows_private_mode_supported(sys.version_info)
        ):
            raise LibraryRootError(
                "Private Windows library folders require CPython 3.11.10+, "
                "3.12.4+, or 3.13+."
            )
        job_dir = self._find_job_dir(job_id)
        root = job_dir.parent.parent
        try:
            concept_directory = self._owned_child_directory(job_dir, "concepts")
            if os.name == "nt":
                _run_windows_path_depth_probe(root)
            _run_write_probe(job_dir)
            _run_write_probe(concept_directory)
            free = self._disk_usage(root).free
        except (OSError, PermissionError, AttributeError, ManifestError) as exc:
            raise LibraryRootError(
                "The job's library folder is not privately writable."
            ) from exc
        if not isinstance(free, int) or free < self._minimum_free_bytes:
            raise LibraryRootError(
                "The job's library folder does not have enough free space."
            )
        return job_dir

    def _find_job_dir(self, job_id: str) -> Path:
        canonical_id = _canonical_uuid(job_id, "job ID")
        for root in self._roots():
            jobs = root / "jobs"
            if _is_linklike(jobs):
                continue
            if jobs.exists():
                try:
                    canonical_root = root.resolve(strict=True)
                    canonical_jobs = jobs.resolve(strict=True)
                    relative_jobs = canonical_jobs.relative_to(canonical_root)
                except (OSError, RuntimeError, ValueError):
                    continue
                if relative_jobs.parts != ("jobs",):
                    continue
            candidate = jobs / canonical_id
            if not candidate.exists():
                continue
            if _is_linklike(candidate) or not candidate.is_dir():
                continue
            try:
                canonical_jobs = jobs.resolve(strict=True)
                canonical_candidate = candidate.resolve(strict=True)
                canonical_candidate.relative_to(canonical_jobs)
                _read_manifest(candidate / "manifest.json", canonical_id)
            except (OSError, RuntimeError, ValueError, ManifestError):
                continue
            return candidate
        raise ManifestError("The generated job was not found.")

    def load_manifest(self, job_id: str) -> dict:
        canonical_id = _canonical_uuid(job_id, "job ID")
        job_dir = self._find_job_dir(canonical_id)
        with _job_lock(job_dir):
            return _read_manifest(job_dir / "manifest.json", canonical_id)

    def update_manifest(
        self,
        job_id: str,
        change: Mapping[str, object] | Callable[[dict], object],
    ) -> dict:
        """Atomically mutate one manifest while holding its process/job lock."""
        canonical_id = _canonical_uuid(job_id, "job ID")
        job_dir = self._find_job_dir(canonical_id)
        with _job_lock(job_dir):
            current = _read_manifest(job_dir / "manifest.json", canonical_id)
            candidate = copy.deepcopy(current)
            if callable(change):
                replacement = change(candidate)
                if replacement is not None:
                    candidate = replacement
            elif isinstance(change, Mapping):
                candidate.update(copy.deepcopy(dict(change)))
            else:
                raise TypeError("manifest change must be a mapping or callable")
            if not isinstance(candidate, dict):
                raise ManifestError("A manifest mutator must return an object or None.")
            candidate["updated_at"] = _now_iso()
            if candidate.get("job_id") != current["job_id"] or candidate.get("created_at") != current["created_at"]:
                raise ManifestError("Manifest identity fields are immutable.")
            normalized = _validate_manifest(candidate, expected_job_id=canonical_id)
            _atomic_write_json(job_dir / "manifest.json", normalized)
            return normalized

    @staticmethod
    def _owned_child_directory(job_dir: Path, name: str) -> Path:
        directory = job_dir / name
        if _is_linklike(directory) or not directory.is_dir():
            raise ManifestError("An asset directory is unsafe.")
        try:
            canonical_job = job_dir.resolve(strict=True)
            canonical_directory = directory.resolve(strict=True)
            relative = canonical_directory.relative_to(canonical_job)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ManifestError("An asset directory is unsafe.") from exc
        if relative.parts != (name,):
            raise ManifestError("An asset directory is unsafe.")
        return directory

    def bank_asset(
        self,
        job_id: str,
        *,
        kind: str,
        data: bytes,
        mime_type: str,
        origin: str,
        status: str = "complete",
    ) -> dict:
        """Atomically commit bytes and their manifest record before returning."""
        canonical_id = _canonical_uuid(job_id, "job ID")
        if kind not in _ASSET_LAYOUT:
            raise ManifestError("The asset kind is unsupported.")
        directory_name, mime_extensions = _ASSET_LAYOUT[kind]
        if mime_type not in mime_extensions:
            raise ManifestError("The asset MIME type is unsupported for this kind.")
        if not isinstance(data, bytes) or not data:
            raise ManifestError("Asset bytes must be non-empty.")
        if not isinstance(origin, str) or not _SAFE_TEXT_ID.fullmatch(origin):
            raise ManifestError("The asset origin is invalid.")
        if status not in _ASSET_STATUSES:
            raise ManifestError("The asset status is invalid.")
        job_dir = self._find_job_dir(canonical_id)
        with _job_lock(job_dir):
            manifest = _read_manifest(job_dir / "manifest.json", canonical_id)
            asset_directory = self._owned_child_directory(job_dir, directory_name)
            work_directory = self._owned_child_directory(job_dir, ".work")
            known_ids = {asset["asset_id"] for asset in manifest["assets"]}
            asset_id: str | None = None
            filename: str | None = None
            for _attempt in range(_UUID_ATTEMPTS):
                candidate_id = str(uuid.uuid4())
                candidate_filename = candidate_id + mime_extensions[mime_type]
                if candidate_id in known_ids or (asset_directory / candidate_filename).exists():
                    continue
                asset_id = candidate_id
                filename = candidate_filename
                break
            if asset_id is None or filename is None:
                raise LibraryError("A unique generated asset ID could not be allocated.")
            relative_path = f"{directory_name}/{filename}"
            destination = asset_directory / filename
            record = {
                "asset_id": asset_id,
                "kind": kind,
                "relative_path": relative_path,
                "mime_type": mime_type,
                "byte_size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "origin": origin,
                "created_at": _now_iso(),
                "status": status,
            }
            _validate_manifest({**manifest, "assets": [*manifest["assets"], record]}, expected_job_id=canonical_id)
            intent_path = work_directory / f"{_ASSET_INTENT_PREFIX}{asset_id}.json"
            _atomic_write_json(
                intent_path,
                {"schema_version": 1, "record": record},
            )
            try:
                _atomic_write_bytes(destination, data)
                manifest["assets"].append(record)
                manifest["updated_at"] = _now_iso()
                normalized = _validate_manifest(manifest, expected_job_id=canonical_id)
                _atomic_write_json(job_dir / "manifest.json", normalized)
            except BaseException:
                # The bytes have already crossed the atomic publication
                # boundary.  Keep them: startup reconciliation adopts this
                # opaque, hashable orphan instead of discarding paid media.
                raise
            try:
                intent_path.unlink(missing_ok=True)
                _fsync_directory(work_directory)
            except OSError:
                # A stale intent is harmless and is removed on reconciliation.
                pass
            return copy.deepcopy(record)

    def _owned_record(self, job_dir: Path, manifest: dict, asset_id: str) -> OwnedAsset:
        matching = [record for record in manifest["assets"] if record["asset_id"] == asset_id]
        if len(matching) != 1:
            raise AssetNotFoundError("The asset is not owned by this job.")
        record = matching[0]
        relative = _validate_relative_asset_path(record["relative_path"])
        path = job_dir.joinpath(*PurePosixPath(relative).parts)
        try:
            canonical_job = job_dir.resolve(strict=True)
            canonical_path = path.resolve(strict=True)
            canonical_path.relative_to(canonical_job)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ManifestError("The owned asset path is unsafe or missing.") from exc
        if _is_linklike(path) or not canonical_path.is_file():
            raise ManifestError("The owned asset path is unsafe or missing.")
        return OwnedAsset(canonical_path, copy.deepcopy(record))

    @staticmethod
    def _verify_owned_asset(owned: OwnedAsset) -> tuple[int, ...]:
        actual_size, actual_sha256, identity = _file_integrity(owned.path)
        record = owned.record
        if actual_size != record["byte_size"] or not hmac.compare_digest(
            actual_sha256, record["sha256"]
        ):
            raise ManifestError("The owned asset failed its integrity check.")
        return identity

    def _resolve_record(self, job_dir: Path, manifest: dict, asset_id: str) -> OwnedAsset:
        owned = self._owned_record(job_dir, manifest, asset_id)
        self._verify_owned_asset(owned)
        return owned

    def resolve_asset(
        self, job_id: str, asset_id: str, *, verify_content: bool = True
    ) -> OwnedAsset:
        """Resolve one owned asset, confirming it is unchanged across two locks.

        ``verify_content=False`` skips the digest comparison and takes the
        identity for the under-lock recheck from ``lstat`` instead.  Only the
        authenticated serving route passes it, because that route immediately
        calls :meth:`OwnedAsset.open_verified`, which re-checks the descriptor it
        actually serves from. Callers that use ``owned.path`` directly must keep
        the default.
        """
        canonical_job_id = _canonical_uuid(job_id, "job ID")
        canonical_asset_id = _canonical_uuid(asset_id, "asset ID")
        job_dir = self._find_job_dir(canonical_job_id)
        with _job_lock(job_dir):
            manifest = _read_manifest(job_dir / "manifest.json", canonical_job_id)
            owned = self._owned_record(job_dir, manifest, canonical_asset_id)

        if verify_content:
            identity = self._verify_owned_asset(owned)
        else:
            try:
                identity = _file_stat_identity(owned.path.lstat())
            except OSError as exc:
                raise ManifestError(
                    "The owned asset path is unsafe or missing."
                ) from exc

        with _job_lock(job_dir):
            current_manifest = _read_manifest(job_dir / "manifest.json", canonical_job_id)
            current = self._owned_record(job_dir, current_manifest, canonical_asset_id)
            if current.path != owned.path or current.record != owned.record:
                raise ManifestError("The owned asset changed during verification.")
            try:
                current_identity = _file_stat_identity(current.path.lstat())
            except OSError as exc:
                raise ManifestError("The owned asset path is unsafe or missing.") from exc
            if current_identity != identity:
                raise ManifestError("The owned asset changed during verification.")
            return current

    @staticmethod
    def _public_manifest(manifest: dict) -> dict:
        def sanitize(value: object, *, parent_key: str | None = None) -> object:
            if isinstance(value, dict):
                result: dict[str, object] = {}
                for key, child in value.items():
                    normalized = key.casefold().replace("-", "_")
                    if (
                        normalized.startswith("_")
                        or normalized == "relative_path"
                        or normalized == "root"
                        or normalized.endswith("_path")
                        or normalized.endswith("_root")
                    ):
                        continue
                    result[key] = sanitize(child, parent_key=key)
                return result
            if isinstance(value, list):
                return [sanitize(child, parent_key=parent_key) for child in value]
            if isinstance(value, str) and parent_key != "prompt":
                if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
                    return "[local path omitted]"
                return _redact_local_paths(value)
            return copy.deepcopy(value)

        public = sanitize(manifest)
        assert isinstance(public, dict)
        return public

    def get_job(self, job_id: str) -> dict:
        return self._public_manifest(self.load_manifest(job_id))

    def _scan_internal(self) -> tuple[list[tuple[dict, Path]], list[dict]]:
        jobs: list[tuple[dict, Path]] = []
        roots, errors = self._resolved_roots()
        seen: set[str] = set()
        for root in roots:
            jobs_dir = root / "jobs"
            if not jobs_dir.exists():
                continue
            if _is_linklike(jobs_dir) or not jobs_dir.is_dir():
                errors.append(
                    {"job_id": None, "code": "root_unavailable", "message": "A recorded library root could not be read."}
                )
                continue
            try:
                entries = sorted(jobs_dir.iterdir(), key=lambda path: path.name)
            except OSError:
                errors.append(
                    {"job_id": None, "code": "root_unavailable", "message": "A recorded library root could not be read."}
                )
                continue
            for entry in entries:
                try:
                    job_id = _canonical_uuid(entry.name, "job ID")
                except InvalidIdentifierError:
                    continue
                try:
                    if _is_linklike(entry) or not entry.is_dir():
                        raise ManifestError("This job manifest could not be read.")
                    manifest_path = entry / "manifest.json"
                    value = _read_manifest_value(manifest_path)
                    if (
                        isinstance(value, dict)
                        and (
                            value.get("schema_version") == 1
                            or value.get("pipeline") == "legacy_video"
                        )
                    ):
                        if _canonical_uuid(value.get("job_id"), "job ID") != job_id:
                            raise ManifestError(
                                "The job manifest does not own this directory."
                            )
                        errors.append(
                            {
                                "job_id": job_id,
                                "code": "unsupported_video_job",
                                "message": "This retired video job is unsupported and was left unchanged.",
                            }
                        )
                        continue
                    try:
                        manifest = _validate_manifest(value, expected_job_id=job_id)
                    except RecursionError as exc:
                        raise ManifestError(
                            "This job manifest could not be read."
                        ) from exc
                except (ManifestError, InvalidIdentifierError):
                    errors.append(
                        {"job_id": job_id, "code": "corrupt_manifest", "message": "This job manifest could not be read."}
                    )
                    continue
                if job_id in seen:
                    errors.append(
                        {"job_id": job_id, "code": "duplicate_job", "message": "A duplicate job ID was ignored."}
                    )
                    continue
                seen.add(job_id)
                jobs.append((manifest, entry))
        jobs.sort(key=lambda item: (item[0]["created_at"], item[0]["job_id"]), reverse=True)
        return jobs, errors

    def scan(self) -> dict:
        """Return pathless sanitized jobs while isolating corrupt manifests."""
        jobs, errors = self._scan_internal()
        return {
            "jobs": [self._public_manifest(manifest) for manifest, _directory in jobs],
            "errors": errors,
        }

    @staticmethod
    def _purge_work(job_dir: Path) -> None:
        work = job_dir / ".work"
        if _is_linklike(work):
            try:
                work.unlink()
            except (IsADirectoryError, PermissionError):
                os.rmdir(work)
        elif work.exists():
            for child in work.iterdir():
                if _is_linklike(child):
                    try:
                        child.unlink()
                    except (IsADirectoryError, PermissionError):
                        os.rmdir(child)
                elif child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
        _make_private_directory(work)
        if os.name != "nt":
            os.chmod(work, 0o700)

    def _recover_orphan_assets(self, job_dir: Path, job_id: str) -> dict:
        """Finish exact durable asset intents left around an atomic rename."""
        with _job_lock(job_dir):
            manifest = _read_manifest(job_dir / "manifest.json", job_id)
            if _is_linklike(job_dir / ".work"):
                self._purge_work(job_dir)
            known_ids = {asset["asset_id"] for asset in manifest["assets"]}
            recovered: list[dict] = []
            cleanup: list[Path] = []
            work = self._owned_child_directory(job_dir, ".work")
            try:
                intents = list(work.glob(f"{_ASSET_INTENT_PREFIX}*.json"))
            except OSError:
                intents = []
            for intent_path in intents:
                try:
                    intent = _read_asset_intent(intent_path)
                    record = copy.deepcopy(intent["record"])
                    asset_id = _canonical_uuid(record.get("asset_id"), "asset ID")
                    if intent_path.name != f"{_ASSET_INTENT_PREFIX}{asset_id}.json":
                        raise ManifestError("An asset publication intent is invalid.")
                    if asset_id in known_ids:
                        cleanup.append(intent_path)
                        continue
                    candidate = _validate_manifest(
                        {**manifest, "assets": [*manifest["assets"], record]},
                        expected_job_id=job_id,
                    )
                    self._resolve_record(job_dir, candidate, asset_id)
                except (AssetNotFoundError, InvalidIdentifierError, ManifestError):
                    cleanup.append(intent_path)
                    continue
                recovered.append(record)
                known_ids.add(asset_id)
                cleanup.append(intent_path)
            if recovered:
                manifest["assets"].extend(recovered)
                manifest["updated_at"] = _now_iso()
                manifest = _validate_manifest(manifest, expected_job_id=job_id)
                _atomic_write_json(job_dir / "manifest.json", manifest)
            for intent_path in cleanup:
                try:
                    intent_path.unlink(missing_ok=True)
                except OSError:
                    pass
            if cleanup:
                _fsync_directory(work)
            return manifest

    def _asset_record_is_valid(self, job_dir: Path, manifest: dict, record: dict) -> bool:
        try:
            self._resolve_record(job_dir, manifest, record["asset_id"])
        except (AssetNotFoundError, ManifestError):
            return False
        return True

    def _reconcile_scanned_job(self, original: dict, job_dir: Path) -> dict | None:
        job_id = original["job_id"]
        original = self._recover_orphan_assets(job_dir, job_id)
        status = original["status"]
        phase = original["phase"]
        changes: dict[str, object] = {}
        if status == "in_progress" and phase in {
            "concept_generation",
            "concepts_generating",
        }:
            committed_asset_ids = {
                candidate.get("asset_id")
                for candidate in original["candidates"]
                if isinstance(candidate, dict)
                and candidate.get("status") == "complete"
                and isinstance(candidate.get("asset_id"), str)
            }
            has_candidates = any(
                asset["kind"] == "concept"
                and asset["status"] == "complete"
                and asset["asset_id"] in committed_asset_ids
                and self._asset_record_is_valid(job_dir, original, asset)
                for asset in original["assets"]
            )
            changes = {
                "status": "partial" if has_candidates else "interrupted",
                "phase": "interrupted",
            }
        elif status == "in_progress" and phase in {"local_processing", "processing"}:
            changes = {"status": "interrupted", "phase": "interrupted"}
        if changes:
            original = self.update_manifest(job_id, changes)
            status = original["status"]
        if status in _TERMINAL_OR_IDLE_STATUSES:
            with _job_lock(job_dir):
                latest = _read_manifest(job_dir / "manifest.json", job_id)
                if latest["status"] in _TERMINAL_OR_IDLE_STATUSES:
                    self._purge_work(job_dir)
        return None

    def reconcile(self) -> dict[str, list[dict]]:
        """Persist safe states while isolating and reporting damaged jobs."""
        scanned, errors = self._scan_internal()
        actions: list[dict] = []
        for original, job_dir in scanned:
            try:
                action = self._reconcile_scanned_job(original, job_dir)
            except Exception:
                errors.append(
                    {
                        "job_id": original["job_id"],
                        "code": "reconciliation_failed",
                        "message": "This job could not be reconciled.",
                    }
                )
                continue
            if action is not None:
                actions.append(action)
        return {"actions": actions, "errors": errors}

    def record_error(
        self,
        job_id: str,
        *,
        code: str,
        message: object,
        sensitive_values: tuple[str, ...] = (),
    ) -> dict:
        """Append a bounded, URL/credential-redacted error record."""
        if not isinstance(code, str) or not _SAFE_ERROR_CODE.fullmatch(code):
            raise ManifestError("The error code is invalid.")
        if not isinstance(sensitive_values, tuple) or not all(
            isinstance(secret, str) for secret in sensitive_values
        ):
            raise TypeError("sensitive_values must be a tuple of strings")
        sanitized_message = _safe_error_message(message)
        for root in self._roots():
            sanitized_message = sanitized_message.replace(str(root), "[local path]")
        for secret in sensitive_values:
            if secret:
                sanitized_message = sanitized_message.replace(secret, "[credential]")

        def append_error(manifest: dict) -> None:
            manifest["errors"].append(
                {"code": code, "message": sanitized_message, "created_at": _now_iso()}
            )

        return self.update_manifest(job_id, append_error)


def _validate_saved_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"The saved item {label} is invalid.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ManifestError(f"The saved item {label} is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ManifestError(f"The saved item {label} is invalid.")
    return value


def _validate_saved_text(
    value: object,
    label: str,
    *,
    maximum: int = _MAX_SAVED_TEXT,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ManifestError(f"The saved item {label} is invalid.")
    return value


def _validate_saved_json(
    value: object,
    label: str,
    *,
    depth: int = 0,
    count: list[int] | None = None,
) -> None:
    if depth > _MAX_SAVED_JSON_DEPTH:
        raise ManifestError(f"The saved item {label} is too deeply nested.")
    if count is None:
        count = [0]
    count[0] += 1
    if count[0] > _MAX_SAVED_JSON_ITEMS:
        raise ManifestError(f"The saved item {label} is too large.")
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str):
            if len(value) > 10_000:
                raise ManifestError(f"The saved item {label} contains oversized text.")
            if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
                raise ManifestError(f"The saved item {label} contains a local path.")
        return
    if type(value) is int:
        if abs(value) > 2**53:
            raise ManifestError(f"The saved item {label} contains an invalid number.")
        return
    if isinstance(value, float):
        if not math.isfinite(value) or abs(value) > 1_000_000:
            raise ManifestError(f"The saved item {label} contains an invalid number.")
        return
    if isinstance(value, list):
        for child in value:
            _validate_saved_json(
                child,
                label,
                depth=depth + 1,
                count=count,
            )
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key or len(key) > 100:
                raise ManifestError(f"The saved item {label} contains an invalid field.")
            _validate_saved_json(
                child,
                label,
                depth=depth + 1,
                count=count,
            )
        return
    raise ManifestError(f"The saved item {label} contains an unsupported value.")


def _validate_saved_device(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _SAVED_DEVICE_FIELDS:
        raise ManifestError("The saved item device schema is unsupported.")
    result = copy.deepcopy(value)
    _validate_saved_json(result, "device")
    for name in ("product_id", "family", "product_label"):
        _validate_saved_text(result[name], f"device {name}")
    for name in ("keymap_signature", "lighting_signature"):
        signature = result[name]
        if signature is not None and (
            not isinstance(signature, str)
            or not _SAFE_TEXT_ID.fullmatch(signature)
        ):
            raise ManifestError(f"The saved item device {name} is invalid.")
    return result


def _validate_saved_asset_record(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _SAVED_ASSET_FIELDS:
        raise ManifestError("A saved item asset has an unsupported schema.")
    record = copy.deepcopy(value)
    asset_id = _canonical_uuid(record["asset_id"], "asset ID")
    kind = record["kind"]
    if not isinstance(kind, str) or kind not in _SAVED_ASSET_LAYOUT:
        raise ManifestError("A saved item asset kind is unsupported.")
    directory, mime_extensions = _SAVED_ASSET_LAYOUT[kind]
    mime_type = record["mime_type"]
    if not isinstance(mime_type, str) or mime_type not in mime_extensions:
        raise ManifestError("A saved item asset MIME type is unsupported.")
    relative_path = _validate_relative_asset_path(record["relative_path"])
    relative = PurePosixPath(relative_path)
    if relative.parts[0] != directory:
        raise ManifestError("A saved item asset path does not match its kind.")
    expected_name = asset_id + mime_extensions[mime_type]
    if relative.parts[1] != expected_name:
        raise ManifestError("A saved item asset filename is invalid.")
    if type(record["byte_size"]) is not int or record["byte_size"] <= 0:
        raise ManifestError("A saved item asset byte size is invalid.")
    if (
        not isinstance(record["sha256"], str)
        or not _SHA256.fullmatch(record["sha256"])
    ):
        raise ManifestError("A saved item asset hash is invalid.")
    _validate_saved_timestamp(record["created_at"], "asset timestamp")
    return record


def _validate_saved_manifest(
    value: object,
    *,
    expected_item_id: str | None = None,
) -> dict:
    if not isinstance(value, dict):
        raise ManifestError("The saved item manifest is invalid.")
    manifest = copy.deepcopy(value)
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != SAVED_ITEM_SCHEMA_VERSION
        or set(manifest) != _SAVED_ITEM_FIELDS
    ):
        raise ManifestError("The saved item manifest has an unsupported schema.")
    _validate_no_sensitive_values(manifest)
    try:
        encoded = json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ManifestError("The saved item manifest is invalid.") from exc
    if len(encoded) > _MAX_MANIFEST_BYTES:
        raise ManifestError("The saved item manifest is too large.")

    item_id = _canonical_uuid(manifest["item_id"], "item ID")
    if expected_item_id is not None and item_id != expected_item_id:
        raise ManifestError("The saved item manifest does not own this directory.")
    kind = manifest["kind"]
    if not isinstance(kind, str) or kind not in _SAVED_ITEM_KINDS:
        raise ManifestError("The saved item kind is unsupported.")
    origin = manifest["origin"]
    if not isinstance(origin, str) or origin not in _SAVED_ITEM_ORIGINS[kind]:
        raise ManifestError("The saved item origin is invalid for its kind.")
    item_name = _validate_saved_text(manifest["name"], "name")
    if Path(item_name).is_absolute() or PureWindowsPath(item_name).is_absolute():
        raise ManifestError("The saved item name cannot contain a local path.")
    created_at = _validate_saved_timestamp(manifest["created_at"], "creation time")
    updated_at = _validate_saved_timestamp(manifest["updated_at"], "update time")
    if datetime.fromisoformat(updated_at) < datetime.fromisoformat(created_at):
        raise ManifestError("The saved item timestamps are inconsistent.")
    if (
        not isinstance(manifest["status"], str)
        or manifest["status"] not in _SAVED_ITEM_STATUSES
    ):
        raise ManifestError("The saved item status is unsupported.")

    tags = manifest["tags"]
    if (
        not isinstance(tags, list)
        or len(tags) > _MAX_SAVED_TAGS
        or any(
            not isinstance(tag, str)
            or not tag.strip()
            or len(tag) > 80
            or any(ord(character) < 32 or ord(character) == 127 for character in tag)
            or Path(tag).is_absolute()
            or PureWindowsPath(tag).is_absolute()
            for tag in tags
        )
        or len({tag.casefold() for tag in tags}) != len(tags)
    ):
        raise ManifestError("The saved item tags are invalid.")

    assets = manifest["assets"]
    if (
        not isinstance(assets, list)
        or not 1 <= len(assets) <= _MAX_SAVED_ASSETS
    ):
        raise ManifestError("The saved item assets are invalid.")
    normalized_assets = [_validate_saved_asset_record(record) for record in assets]
    asset_ids = [record["asset_id"] for record in normalized_assets]
    asset_paths = [record["relative_path"] for record in normalized_assets]
    if len(set(asset_ids)) != len(asset_ids) or len(set(asset_paths)) != len(asset_paths):
        raise ManifestError("The saved item assets contain duplicate ownership.")
    assets_by_id = {record["asset_id"]: record for record in normalized_assets}

    source = manifest["source"]
    composition = manifest["composition"]
    profile = manifest["profile"]
    device = manifest["device"]
    if kind == "media_source":
        if (
            device is not None
            or composition is not None
            or profile is not None
            or not isinstance(source, dict)
            or set(source) != _SAVED_SOURCE_FIELDS
        ):
            raise ManifestError("The media source manifest discriminator is invalid.")
        source_asset_id = _canonical_uuid(source["asset_id"], "source asset ID")
        source_asset = assets_by_id.get(source_asset_id)
        if (
            source_asset is None
            or source_asset["kind"] != "source"
            or set(assets_by_id) != {source_asset_id}
            or source["mime_type"] != source_asset["mime_type"]
            or source["sha256"] != source_asset["sha256"]
        ):
            raise ManifestError("The media source asset ownership is invalid.")
        mime_type = source["mime_type"]
        if (
            not isinstance(mime_type, str)
            or mime_type not in {"image/gif", "image/png", "image/bmp"}
        ):
            raise ManifestError("The media source MIME type is unsupported.")
        for field in ("width", "height"):
            if type(source[field]) is not int or not 1 <= source[field] <= 65_535:
                raise ManifestError("The media source dimensions are invalid.")
        if (
            type(source["frame_count"]) is not int
            or not 1 <= source["frame_count"] <= 10_000
            or type(source["duration_ms"]) is not int
            or not 0 <= source["duration_ms"] <= 86_400_000
        ):
            raise ManifestError("The media source timing is invalid.")
        if mime_type == "image/gif":
            if source["duration_ms"] <= 0:
                raise ManifestError("The GIF source duration is invalid.")
        elif source["frame_count"] != 1 or source["duration_ms"] != 0:
            raise ManifestError("A still source must contain exactly one frame.")
    elif kind == "lighting_composition":
        if (
            source is not None
            or profile is not None
            or not isinstance(composition, dict)
            or set(composition) != _SAVED_COMPOSITION_FIELDS
        ):
            raise ManifestError("The lighting composition discriminator is invalid.")
        _validate_saved_device(device)
        if (
            type(composition["schema_version"]) is not int
            or composition["schema_version"] != 1
        ):
            raise ManifestError("The lighting composition schema is unsupported.")
        source_catalog_id = composition["source_catalog_id"]
        if source_catalog_id is not None:
            namespace, _identifier = _parse_catalog_id(source_catalog_id)
            if namespace != "item":
                raise ManifestError("The composition source must be a saved item.")
        for name in (
            "transform",
            "effects",
            "manual_overrides",
            "destination",
            "tracks",
        ):
            _validate_saved_json(composition[name], f"composition {name}")
        if composition["transform"] is not None and not isinstance(
            composition["transform"],
            dict,
        ):
            raise ManifestError("The lighting composition transform is invalid.")
        if not isinstance(composition["effects"], list) or not isinstance(
            composition["manual_overrides"],
            list,
        ):
            raise ManifestError("The lighting composition effects are invalid.")
        if not isinstance(composition["destination"], dict) or not isinstance(
            composition["tracks"],
            dict,
        ):
            raise ManifestError("The lighting composition result is invalid.")
        rendered_id = _canonical_uuid(
            composition["rendered_asset_id"],
            "rendered asset ID",
        )
        rendered = assets_by_id.get(rendered_id)
        if rendered is None or rendered["kind"] != "result":
            raise ManifestError("The lighting composition result ownership is invalid.")
        referenced = {rendered_id}
        preview_id = composition["preview_asset_id"]
        if preview_id is not None:
            preview_id = _canonical_uuid(preview_id, "preview asset ID")
            preview = assets_by_id.get(preview_id)
            if preview is None or preview["kind"] != "preview":
                raise ManifestError("The lighting composition preview ownership is invalid.")
            referenced.add(preview_id)
        if set(assets_by_id) != referenced:
            raise ManifestError("The lighting composition has unreferenced assets.")
    else:
        if (
            source is not None
            or composition is not None
            or not isinstance(profile, dict)
            or set(profile) != _SAVED_PROFILE_FIELDS
        ):
            raise ManifestError("The keyboard profile discriminator is invalid.")
        _validate_saved_device(device)
        profile_asset_id = _canonical_uuid(profile["asset_id"], "profile asset ID")
        profile_asset = assets_by_id.get(profile_asset_id)
        if (
            profile_asset is None
            or profile_asset["kind"] != "profile"
            or profile_asset["mime_type"] != "application/json"
            or profile["mime_type"] != profile_asset["mime_type"]
            or profile["sha256"] != profile_asset["sha256"]
            or set(assets_by_id) != {profile_asset_id}
        ):
            raise ManifestError("The keyboard profile asset ownership is invalid.")
        sections = profile["sections"]
        allowed_sections = {"identity", "keymap", "macros", "lighting"}
        if (
            not isinstance(sections, list)
            or not sections
            or any(
                not isinstance(section, str) or section not in allowed_sections
                for section in sections
            )
            or len(set(sections)) != len(sections)
        ):
            raise ManifestError("The keyboard profile sections are invalid.")

    manifest["assets"] = normalized_assets
    return manifest


def _read_saved_manifest(path: Path, item_id: str) -> dict:
    if _is_linklike(path) or not path.is_file():
        raise ManifestError("This saved item manifest could not be read.")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ManifestError("This saved item manifest could not be read.")
            payload = file.read(_MAX_MANIFEST_BYTES + 1)
        if len(payload) > _MAX_MANIFEST_BYTES:
            raise ManifestError("This saved item manifest could not be read.")
        value = json.loads(payload.decode("utf-8"))
        return _validate_saved_manifest(value, expected_item_id=item_id)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ManifestError("This saved item manifest could not be read.") from exc


def _catalog_id(namespace: str, identifier: str) -> str:
    if namespace not in {"job", "item"}:
        raise InvalidIdentifierError("catalog namespace is invalid")
    return f"{namespace}:{_canonical_uuid(identifier, f'{namespace} ID')}"


def _parse_catalog_id(value: object) -> tuple[str, str]:
    if not isinstance(value, str) or value.count(":") != 1:
        raise InvalidIdentifierError(
            "catalog ID must include an opaque server namespace"
        )
    namespace, identifier = value.split(":", 1)
    if namespace not in {"job", "item"}:
        raise InvalidIdentifierError(
            "catalog ID must include an opaque server namespace"
        )
    canonical = _canonical_uuid(identifier, f"{namespace} ID")
    if value != f"{namespace}:{canonical}":
        raise InvalidIdentifierError("catalog ID must be canonical")
    return namespace, canonical


class SavedItemLibrary:
    """Immutable saved Library items across one current and older roots."""

    def __init__(
        self,
        current_root: str | os.PathLike[str] | None,
        historical_roots: list[str | os.PathLike[str]]
        | tuple[str | os.PathLike[str], ...] = (),
        *,
        minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES,
        disk_usage: Callable[[str | os.PathLike[str]], object] = shutil.disk_usage,
    ) -> None:
        if (
            not isinstance(minimum_free_bytes, int)
            or isinstance(minimum_free_bytes, bool)
            or minimum_free_bytes < 0
        ):
            raise ValueError("minimum_free_bytes must be a non-negative integer")
        self._current_root_value = current_root
        self._historical_root_values = tuple(historical_roots)
        self._minimum_free_bytes = minimum_free_bytes
        self._disk_usage = disk_usage

    def _generated_root_probe(self) -> GeneratedAssetLibrary:
        return GeneratedAssetLibrary(
            self._current_root_value,
            self._historical_root_values,
            minimum_free_bytes=self._minimum_free_bytes,
            disk_usage=self._disk_usage,
        )

    def _resolved_roots(self) -> tuple[list[Path], list[dict]]:
        roots, root_errors = self._generated_root_probe()._resolved_roots()
        return roots, [
            {
                "item_id": None,
                "code": error["code"],
                "message": error["message"],
            }
            for error in root_errors
        ]

    def _roots(self) -> list[Path]:
        return self._resolved_roots()[0]

    def preflight(self) -> Path:
        """Validate the configured private root and create its items directory."""
        return _preflight_private_root(
            self._current_root_value,
            "items",
            minimum_free_bytes=self._minimum_free_bytes,
            disk_usage=self._disk_usage,
            missing_message=(
                "A library folder must be configured before saving Library items."
            ),
            unavailable_message=(
                "The configured library folder cannot store private saved items."
            ),
            free_space_message=(
                "The configured library folder does not have enough free space."
            ),
        )

    @staticmethod
    def _owned_child_directory(item_dir: Path, name: str) -> Path:
        return GeneratedAssetLibrary._owned_child_directory(item_dir, name)

    @staticmethod
    def _resolve_creation_reference(
        value: object,
        records: Mapping[str, dict],
        *,
        label: str,
    ) -> dict:
        if not isinstance(value, Mapping):
            raise ManifestError(f"The saved item {label} is invalid.")
        result = copy.deepcopy(dict(value))
        reference = result.get("asset_id")
        if not isinstance(reference, str) or reference not in records:
            raise ManifestError(f"The saved item {label} asset reference is invalid.")
        record = records[reference]
        result["asset_id"] = record["asset_id"]
        result["mime_type"] = record["mime_type"]
        result["sha256"] = record["sha256"]
        return result

    def create_item(
        self,
        *,
        kind: str,
        origin: str,
        name: str,
        assets: Mapping[str, Mapping[str, object]],
        tags: list[str] | tuple[str, ...] = (),
        device: Mapping[str, object] | None = None,
        source: Mapping[str, object] | None = None,
        composition: Mapping[str, object] | None = None,
        profile: Mapping[str, object] | None = None,
    ) -> dict:
        """Atomically publish one strict manifest and all of its owned assets.

        Asset mapping keys are short-lived local labels. Section ``asset_id``
        values refer to those labels and are replaced with server-generated UUIDs
        before the manifest crosses the publication boundary.
        """
        if (
            not isinstance(assets, Mapping)
            or not 1 <= len(assets) <= _MAX_SAVED_ASSETS
        ):
            raise ManifestError("Saved item assets must be a non-empty mapping.")
        root = self.preflight()
        items_dir = root / "items"
        item_id: str | None = None
        item_dir: Path | None = None
        temporary: Path | None = None
        for _attempt in range(_UUID_ATTEMPTS):
            candidate = str(uuid.uuid4())
            candidate_dir = items_dir / candidate
            candidate_temporary = items_dir / f".item-{candidate}-{uuid.uuid4()}.tmp"
            if candidate_dir.exists() or candidate_temporary.exists():
                continue
            item_id = candidate
            item_dir = candidate_dir
            temporary = candidate_temporary
            break
        if item_id is None or item_dir is None or temporary is None:
            raise LibraryError("A unique saved item ID could not be allocated.")

        published = False
        try:
            _make_private_directory(temporary)
            for directory_name in _SAVED_ITEM_DIRECTORIES:
                _make_private_directory(temporary / directory_name)
            created_at = _now_iso()
            records_by_label: dict[str, dict] = {}
            known_asset_ids: set[str] = set()
            asset_intents: list[Path] = []
            for asset_label, raw_specification in assets.items():
                if (
                    not isinstance(asset_label, str)
                    or not _SAFE_TEXT_ID.fullmatch(asset_label)
                    or asset_label in records_by_label
                    or not isinstance(raw_specification, Mapping)
                ):
                    raise ManifestError("A saved item asset label is invalid.")
                specification = dict(raw_specification)
                if set(specification) != {"kind", "mime_type", "data"}:
                    raise ManifestError(
                        "A saved item asset input has an unsupported schema."
                )
                asset_kind = specification["kind"]
                if (
                    not isinstance(asset_kind, str)
                    or asset_kind not in _SAVED_ASSET_LAYOUT
                ):
                    raise ManifestError("A saved item asset kind is unsupported.")
                directory_name, mime_extensions = _SAVED_ASSET_LAYOUT[asset_kind]
                mime_type = specification["mime_type"]
                if (
                    not isinstance(mime_type, str)
                    or mime_type not in mime_extensions
                ):
                    raise ManifestError(
                        "A saved item asset MIME type is unsupported for its kind."
                    )
                data = specification["data"]
                if not isinstance(data, bytes) or not data:
                    raise ManifestError("Saved item asset bytes must be non-empty.")
                asset_id: str | None = None
                for _asset_attempt in range(_UUID_ATTEMPTS):
                    candidate_asset_id = str(uuid.uuid4())
                    if candidate_asset_id not in known_asset_ids:
                        asset_id = candidate_asset_id
                        break
                if asset_id is None:
                    raise LibraryError(
                        "A unique saved item asset ID could not be allocated."
                    )
                known_asset_ids.add(asset_id)
                filename = asset_id + mime_extensions[mime_type]
                relative_path = f"{directory_name}/{filename}"
                destination = temporary / directory_name / filename
                record = {
                    "asset_id": asset_id,
                    "kind": asset_kind,
                    "relative_path": relative_path,
                    "mime_type": mime_type,
                    "byte_size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "created_at": created_at,
                }
                intent_path = (
                    temporary / f"{_ASSET_INTENT_PREFIX}{asset_id}.json"
                )
                _atomic_write_json(
                    intent_path,
                    {
                        "schema_version": 1,
                        "item_id": item_id,
                        "record": record,
                    },
                )
                asset_intents.append(intent_path)
                _atomic_write_bytes(destination, data)
                records_by_label[asset_label] = record

            normalized_source: dict | None = None
            normalized_composition: dict | None = None
            normalized_profile: dict | None = None
            if source is not None:
                if not isinstance(source, Mapping) or set(source) != _SAVED_SOURCE_INPUT_FIELDS:
                    raise ManifestError(
                        "The saved media source input has an unsupported schema."
                    )
                normalized_source = self._resolve_creation_reference(
                    source,
                    records_by_label,
                    label="source",
                )
            if profile is not None:
                if not isinstance(profile, Mapping) or set(profile) != _SAVED_PROFILE_INPUT_FIELDS:
                    raise ManifestError(
                        "The saved keyboard profile input has an unsupported schema."
                    )
                normalized_profile = self._resolve_creation_reference(
                    profile,
                    records_by_label,
                    label="profile",
                )
            if composition is not None:
                if (
                    not isinstance(composition, Mapping)
                    or set(composition) != _SAVED_COMPOSITION_FIELDS
                ):
                    raise ManifestError(
                        "The saved lighting composition input has an unsupported schema."
                    )
                normalized_composition = copy.deepcopy(dict(composition))
                for field in ("rendered_asset_id", "preview_asset_id"):
                    reference = normalized_composition[field]
                    if reference is None and field == "preview_asset_id":
                        continue
                    if not isinstance(reference, str) or reference not in records_by_label:
                        raise ManifestError(
                            "The saved lighting composition asset reference is invalid."
                        )
                    normalized_composition[field] = records_by_label[reference][
                        "asset_id"
                    ]

            manifest = {
                "schema_version": SAVED_ITEM_SCHEMA_VERSION,
                "item_id": item_id,
                "kind": kind,
                "origin": origin,
                "name": name,
                "created_at": created_at,
                "updated_at": created_at,
                "status": "ready",
                "tags": list(tags) if isinstance(tags, (list, tuple)) else tags,
                "device": copy.deepcopy(dict(device)) if isinstance(device, Mapping) else device,
                "source": normalized_source,
                "composition": normalized_composition,
                "profile": normalized_profile,
                "assets": list(records_by_label.values()),
            }
            normalized = _validate_saved_manifest(
                manifest,
                expected_item_id=item_id,
            )
            _atomic_write_json(temporary / "manifest.json", normalized)
            for intent_path in asset_intents:
                intent_path.unlink()
            _fsync_directory(temporary)
            if item_dir.exists() or _is_linklike(item_dir):
                raise LibraryError("The saved item destination is already occupied.")
            os.rename(temporary, item_dir)
            published = True
            _fsync_directory(items_dir)
            return copy.deepcopy(normalized)
        finally:
            if not published and temporary.exists():
                try:
                    if _is_linklike(temporary):
                        temporary.unlink()
                    else:
                        shutil.rmtree(temporary)
                    _fsync_directory(items_dir)
                except OSError:
                    pass

    def create_keyboard_profile(
        self,
        *,
        origin: str,
        name: str,
        configuration: bytes,
        device: Mapping[str, object],
        sections: list[str] | tuple[str, ...],
        tags: list[str] | tuple[str, ...] = (),
    ) -> dict:
        """Publish one exact configuration asset plus its profile projection."""

        if not isinstance(configuration, bytes) or not configuration:
            raise ManifestError(
                "The keyboard profile configuration bytes must be non-empty."
            )
        if not isinstance(sections, (list, tuple)):
            raise ManifestError(
                "The keyboard profile sections must be a list or tuple."
            )
        return self.create_item(
            kind="keyboard_profile",
            origin=origin,
            name=name,
            tags=tags,
            device=device,
            profile={
                "asset_id": "configuration",
                "sections": list(sections),
            },
            assets={
                "configuration": {
                    "kind": "profile",
                    "mime_type": "application/json",
                    "data": configuration,
                }
            },
        )

    def bank_media_source(
        self,
        *,
        name: str,
        payload: bytes,
        metadata: Mapping[str, object],
        tags: list[str] | tuple[str, ...] = (),
    ) -> tuple[dict, bool]:
        """Publish one immutable media source or return its verified duplicate."""

        if not isinstance(payload, bytes) or not payload:
            raise ManifestError("Media source bytes must be non-empty.")
        if (
            not isinstance(metadata, Mapping)
            or set(metadata)
            != {
                "mime_type",
                "width",
                "height",
                "frame_count",
                "duration_ms",
            }
        ):
            raise ManifestError("Media source metadata has an unsupported schema.")
        item_name = _validate_saved_text(name, "name")
        if Path(item_name).is_absolute() or PureWindowsPath(item_name).is_absolute():
            raise ManifestError("The saved item name cannot contain a local path.")
        mime_type = metadata["mime_type"]
        if (
            not isinstance(mime_type, str)
            or mime_type not in {"image/gif", "image/png", "image/bmp"}
        ):
            raise ManifestError("The media source MIME type is unsupported.")

        digest = hashlib.sha256(payload).hexdigest()
        root = self.preflight()
        with _job_lock(root):
            items, _errors = self._scan_internal()
            for manifest, item_dir in items:
                source = manifest.get("source")
                if (
                    manifest.get("kind") != "media_source"
                    or not isinstance(source, dict)
                    or source.get("sha256") != digest
                    or source.get("mime_type") != mime_type
                    or source.get("width") != metadata["width"]
                    or source.get("height") != metadata["height"]
                    or source.get("frame_count") != metadata["frame_count"]
                    or source.get("duration_ms") != metadata["duration_ms"]
                ):
                    continue
                try:
                    owned = self._owned_record(
                        item_dir,
                        manifest,
                        source["asset_id"],
                    )
                    with owned.open_verified() as stream:
                        if stream.read(len(payload) + 1) != payload:
                            continue
                except (LibraryError, OSError):
                    continue
                return copy.deepcopy(manifest), False

            manifest = self.create_item(
                kind="media_source",
                origin="media_import",
                name=item_name,
                tags=tags,
                source={
                    "asset_id": "source",
                    "width": metadata["width"],
                    "height": metadata["height"],
                    "frame_count": metadata["frame_count"],
                    "duration_ms": metadata["duration_ms"],
                },
                assets={
                    "source": {
                        "kind": "source",
                        "mime_type": mime_type,
                        "data": payload,
                    }
                },
            )
            return manifest, True

    def _find_item_dir(self, item_id: str) -> Path:
        canonical_id = _canonical_uuid(item_id, "item ID")
        for root in self._roots():
            items = root / "items"
            if _is_linklike(items):
                continue
            if items.exists():
                try:
                    canonical_root = root.resolve(strict=True)
                    canonical_items = items.resolve(strict=True)
                    relative_items = canonical_items.relative_to(canonical_root)
                except (OSError, RuntimeError, ValueError):
                    continue
                if relative_items.parts != ("items",):
                    continue
            candidate = items / canonical_id
            if not candidate.exists():
                continue
            if _is_linklike(candidate) or not candidate.is_dir():
                continue
            try:
                canonical_items = items.resolve(strict=True)
                canonical_candidate = candidate.resolve(strict=True)
                relative = canonical_candidate.relative_to(canonical_items)
                if relative.parts != (canonical_id,):
                    continue
                _read_saved_manifest(candidate / "manifest.json", canonical_id)
            except (OSError, RuntimeError, ValueError, ManifestError):
                continue
            return candidate
        raise ManifestError("The saved item was not found.")

    def load_manifest(self, item_id: str) -> dict:
        canonical_id = _canonical_uuid(item_id, "item ID")
        item_dir = self._find_item_dir(canonical_id)
        with _job_lock(item_dir):
            return _read_saved_manifest(item_dir / "manifest.json", canonical_id)

    def _owned_record(
        self,
        item_dir: Path,
        manifest: dict,
        asset_id: str,
    ) -> OwnedAsset:
        matching = [
            record
            for record in manifest["assets"]
            if record["asset_id"] == asset_id
        ]
        if len(matching) != 1:
            raise AssetNotFoundError("The asset is not owned by this saved item.")
        record = matching[0]
        relative = _validate_relative_asset_path(record["relative_path"])
        directory_name = PurePosixPath(relative).parts[0]
        asset_directory = self._owned_child_directory(item_dir, directory_name)
        path = asset_directory / PurePosixPath(relative).parts[1]
        try:
            canonical_item = item_dir.resolve(strict=True)
            canonical_path = path.resolve(strict=True)
            canonical_path.relative_to(canonical_item)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ManifestError("The owned asset path is unsafe or missing.") from exc
        return OwnedAsset(path=path, record=copy.deepcopy(record))

    def resolve_asset(
        self,
        item_id: str,
        asset_id: str,
        *,
        verify_content: bool = True,
    ) -> OwnedAsset:
        canonical_item_id = _canonical_uuid(item_id, "item ID")
        canonical_asset_id = _canonical_uuid(asset_id, "asset ID")
        item_dir = self._find_item_dir(canonical_item_id)
        with _job_lock(item_dir):
            manifest = _read_saved_manifest(
                item_dir / "manifest.json",
                canonical_item_id,
            )
            owned = self._owned_record(
                item_dir,
                manifest,
                canonical_asset_id,
            )
            with owned.open_verified(verify_content=verify_content):
                pass
            return owned

    @staticmethod
    def _public_manifest(manifest: dict) -> dict:
        return GeneratedAssetLibrary._public_manifest(manifest)

    def get_item(self, item_id: str) -> dict:
        return self._public_manifest(self.load_manifest(item_id))

    def _scan_internal(self) -> tuple[list[tuple[dict, Path]], list[dict]]:
        items: list[tuple[dict, Path]] = []
        roots, errors = self._resolved_roots()
        seen: set[str] = set()
        for root in roots:
            items_dir = root / "items"
            if not items_dir.exists():
                continue
            if _is_linklike(items_dir) or not items_dir.is_dir():
                errors.append(
                    {
                        "item_id": None,
                        "code": "root_unavailable",
                        "message": "A recorded library root could not be read.",
                    }
                )
                continue
            try:
                entries = sorted(items_dir.iterdir(), key=lambda path: path.name)
            except OSError:
                errors.append(
                    {
                        "item_id": None,
                        "code": "root_unavailable",
                        "message": "A recorded library root could not be read.",
                    }
                )
                continue
            for entry in entries:
                try:
                    item_id = _canonical_uuid(entry.name, "item ID")
                except InvalidIdentifierError:
                    continue
                try:
                    if _is_linklike(entry) or not entry.is_dir():
                        raise ManifestError(
                            "This saved item manifest could not be read."
                        )
                    manifest = _read_saved_manifest(
                        entry / "manifest.json",
                        item_id,
                    )
                except ManifestError:
                    errors.append(
                        {
                            "item_id": item_id,
                            "code": "corrupt_manifest",
                            "message": "This saved item manifest could not be read.",
                        }
                    )
                    continue
                if item_id in seen:
                    errors.append(
                        {
                            "item_id": item_id,
                            "code": "duplicate_item",
                            "message": "A duplicate saved item ID was ignored.",
                        }
                    )
                    continue
                seen.add(item_id)
                items.append((manifest, entry))
        items.sort(
            key=lambda item: (
                item[0]["updated_at"],
                item[0]["created_at"],
                item[0]["item_id"],
            ),
            reverse=True,
        )
        return items, errors

    def scan(self) -> dict:
        """Return pathless saved items while isolating corrupt manifests."""
        items, errors = self._scan_internal()
        return {
            "items": [
                self._public_manifest(manifest)
                for manifest, _directory in items
            ],
            "errors": errors,
        }


class LibraryCatalog:
    """Mixed projection plus reversible owned-state mutations for Library data."""

    def __init__(
        self,
        jobs: GeneratedAssetLibrary,
        saved_items: SavedItemLibrary | None = None,
    ) -> None:
        if not isinstance(jobs, GeneratedAssetLibrary):
            raise TypeError("jobs must be a GeneratedAssetLibrary")
        self.jobs = jobs
        self.saved_items = saved_items or SavedItemLibrary(
            jobs._current_root_value,
            jobs._historical_root_values,
            minimum_free_bytes=jobs._minimum_free_bytes,
            disk_usage=jobs._disk_usage,
        )

    @staticmethod
    def _job_summary(manifest: dict, *, removed: bool = False) -> dict:
        target = copy.deepcopy(manifest["target"])
        prompt = manifest["prompt"]
        name = prompt.strip() or "Untitled generation"
        return {
            "catalog_id": _catalog_id("job", manifest["job_id"]),
            "namespace": "job",
            "kind": "generation_job",
            "origin": "ai_generation",
            "name": name,
            "created_at": manifest["created_at"],
            "updated_at": manifest["updated_at"],
            "status": manifest["status"],
            "tags": [],
            "device": {
                "product_id": target.get("product_id"),
                "family": target.get("family"),
                "product_label": target.get("product_label"),
            },
            "target": target,
            "prompt": prompt,
            "frame_count": None,
            "asset_count": len(manifest["assets"]),
            "compatibility": None,
            "removed": removed,
        }

    @staticmethod
    def _saved_summary(manifest: dict, *, removed: bool = False) -> dict:
        source = manifest["source"]
        return {
            "catalog_id": _catalog_id("item", manifest["item_id"]),
            "namespace": "item",
            "kind": manifest["kind"],
            "origin": manifest["origin"],
            "name": manifest["name"],
            "created_at": manifest["created_at"],
            "updated_at": manifest["updated_at"],
            "status": manifest["status"],
            "tags": copy.deepcopy(manifest["tags"]),
            "device": copy.deepcopy(manifest["device"]),
            "target": None,
            "prompt": None,
            "frame_count": source["frame_count"] if source is not None else None,
            "asset_count": len(manifest["assets"]),
            "compatibility": None,
            "removed": removed,
        }

    @staticmethod
    def _catalog_error(namespace: str, error: Mapping[str, object]) -> dict:
        identifier = error.get(f"{namespace}_id")
        catalog_id = (
            _catalog_id(namespace, identifier)
            if isinstance(identifier, str)
            else None
        )
        return {
            "catalog_id": catalog_id,
            "namespace": namespace,
            "code": error["code"],
            "message": error["message"],
        }

    def _roots_for_namespace(self, namespace: str) -> list[Path]:
        if namespace == "job":
            return self.jobs._roots()
        if namespace == "item":
            return self.saved_items._roots()
        raise InvalidIdentifierError("catalog namespace is invalid")

    @staticmethod
    def _namespace_directory(namespace: str) -> str:
        if namespace == "job":
            return "jobs"
        if namespace == "item":
            return "items"
        raise InvalidIdentifierError("catalog namespace is invalid")

    @classmethod
    def _owned_container(
        cls,
        root: Path,
        namespace: str,
        *,
        removed: bool,
        create: bool = False,
    ) -> Path | None:
        directory_name = cls._namespace_directory(namespace)
        parts = (".trash", directory_name) if removed else (directory_name,)
        current = root
        for part in parts:
            candidate = current / part
            if create:
                if candidate.exists() or candidate.is_symlink():
                    if _is_linklike(candidate) or not candidate.is_dir():
                        raise ManifestError(
                            "A Library ownership directory is unsafe."
                        )
                else:
                    _make_private_directory(candidate)
                if _is_linklike(candidate) or not candidate.is_dir():
                    raise ManifestError(
                        "A Library ownership directory is unsafe."
                    )
                if os.name != "nt":
                    os.chmod(candidate, 0o700)
                else:
                    _set_windows_private_directory_dacl(candidate)
            if not candidate.exists():
                return None
            if _is_linklike(candidate) or not candidate.is_dir():
                raise ManifestError("A Library ownership directory is unsafe.")
            current = candidate
        try:
            canonical_root = root.resolve(strict=True)
            canonical_container = current.resolve(strict=True)
            relative = canonical_container.relative_to(canonical_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ManifestError("A Library ownership directory is unsafe.") from exc
        if relative.parts != parts:
            raise ManifestError("A Library ownership directory is unsafe.")
        return current

    @staticmethod
    def _read_owned_manifest(
        namespace: str,
        directory: Path,
        identifier: str,
    ) -> dict:
        if namespace == "job":
            return _read_manifest(directory / "manifest.json", identifier)
        return _read_saved_manifest(directory / "manifest.json", identifier)

    @staticmethod
    def _public_owned_manifest(namespace: str, manifest: dict) -> dict:
        if namespace == "job":
            return GeneratedAssetLibrary._public_manifest(manifest)
        return SavedItemLibrary._public_manifest(manifest)

    def _summary(
        self,
        namespace: str,
        manifest: dict,
        *,
        removed: bool,
    ) -> dict:
        if namespace == "job":
            return self._job_summary(manifest, removed=removed)
        return self._saved_summary(manifest, removed=removed)

    def _scan_removed_namespace(
        self,
        namespace: str,
    ) -> tuple[list[dict], list[dict]]:
        manifests: list[dict] = []
        errors: list[dict] = []
        seen: set[str] = set()
        for root in self._roots_for_namespace(namespace):
            try:
                container = self._owned_container(
                    root,
                    namespace,
                    removed=True,
                )
            except ManifestError:
                errors.append(
                    {
                        "catalog_id": None,
                        "namespace": namespace,
                        "code": "root_unavailable",
                        "message": "A recorded Library trash root could not be read.",
                    }
                )
                continue
            if container is None:
                continue
            try:
                entries = sorted(container.iterdir(), key=lambda path: path.name)
            except OSError:
                errors.append(
                    {
                        "catalog_id": None,
                        "namespace": namespace,
                        "code": "root_unavailable",
                        "message": "A recorded Library trash root could not be read.",
                    }
                )
                continue
            for entry in entries:
                try:
                    identifier = _canonical_uuid(
                        entry.name,
                        f"{namespace} ID",
                    )
                except InvalidIdentifierError:
                    continue
                catalog_id = _catalog_id(namespace, identifier)
                try:
                    if _is_linklike(entry) or not entry.is_dir():
                        raise ManifestError(
                            "This removed Library manifest could not be read."
                        )
                    try:
                        canonical_container = container.resolve(strict=True)
                        canonical_entry = entry.resolve(strict=True)
                        relative = canonical_entry.relative_to(
                            canonical_container
                        )
                    except (OSError, RuntimeError, ValueError) as exc:
                        raise ManifestError(
                            "This removed Library manifest could not be read."
                        ) from exc
                    if relative.parts != (identifier,):
                        raise ManifestError(
                            "This removed Library manifest could not be read."
                        )
                    manifest = self._read_owned_manifest(
                        namespace,
                        entry,
                        identifier,
                    )
                except ManifestError:
                    errors.append(
                        {
                            "catalog_id": catalog_id,
                            "namespace": namespace,
                            "code": "corrupt_manifest",
                            "message": (
                                "This removed Library manifest could not be read."
                            ),
                        }
                    )
                    continue
                if identifier in seen:
                    errors.append(
                        {
                            "catalog_id": catalog_id,
                            "namespace": namespace,
                            "code": "duplicate_removed_item",
                            "message": (
                                "A duplicate removed Library ID was ignored."
                            ),
                        }
                    )
                    continue
                seen.add(identifier)
                manifests.append(manifest)
        return manifests, errors

    def scan(self) -> dict:
        job_scan = self.jobs.scan()
        item_scan = self.saved_items.scan()
        items = [
            self._job_summary(manifest)
            for manifest in job_scan["jobs"]
        ]
        items.extend(
            self._saved_summary(manifest)
            for manifest in item_scan["items"]
        )
        errors = [
            self._catalog_error("job", error)
            for error in job_scan["errors"]
        ]
        errors.extend(
            self._catalog_error("item", error)
            for error in item_scan["errors"]
        )
        seen_catalog_ids = {item["catalog_id"] for item in items}
        for namespace in ("job", "item"):
            removed_manifests, removed_errors = self._scan_removed_namespace(
                namespace
            )
            errors.extend(removed_errors)
            for manifest in removed_manifests:
                summary = self._summary(
                    namespace,
                    self._public_owned_manifest(namespace, manifest),
                    removed=True,
                )
                if summary["catalog_id"] in seen_catalog_ids:
                    errors.append(
                        {
                            "catalog_id": summary["catalog_id"],
                            "namespace": namespace,
                            "code": "duplicate_catalog_item",
                            "message": (
                                "A duplicate live and removed Library ID was ignored."
                            ),
                        }
                    )
                    continue
                seen_catalog_ids.add(summary["catalog_id"])
                items.append(summary)
        items.sort(
            key=lambda item: (
                item["updated_at"],
                item["created_at"],
                item["catalog_id"],
            ),
            reverse=True,
        )
        return {"items": items, "errors": errors}

    @staticmethod
    def _search_blob(item: Mapping[str, object]) -> str:
        searchable = {
            "name": item["name"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "origin": item["origin"],
            "tags": item["tags"],
            "device": item["device"],
            "target": item["target"],
            "prompt": item["prompt"],
        }
        return json.dumps(
            searchable,
            ensure_ascii=False,
            sort_keys=True,
        ).casefold()

    def page(
        self,
        *,
        page: int,
        limit: int,
        statuses: set[str] | frozenset[str] = frozenset(),
        kind: str = "",
        compatibility: str = "",
        removed: bool = False,
        query: str = "",
    ) -> dict:
        if type(page) is not int or page < 1:
            raise ValueError("page must be a positive integer.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit is outside its supported range.")
        if not isinstance(kind, str) or (
            kind
            and kind not in _CATALOG_KINDS
            and kind not in _CATALOG_KIND_GROUPS
        ):
            raise ValueError("kind filter is invalid.")
        if not isinstance(compatibility, str) or compatibility not in {
            "",
            "unknown",
            "exact",
            "convertible",
            "partial",
            "incompatible",
        }:
            raise ValueError("compatibility filter is invalid.")
        if type(removed) is not bool:
            raise ValueError("removed filter is invalid.")
        if (
            not isinstance(statuses, (set, frozenset))
            or any(
                not isinstance(status, str)
                or not status
                or len(status) > 80
                or not _SAFE_TEXT_ID.fullmatch(status)
                for status in statuses
            )
        ):
            raise ValueError("status filter is invalid.")
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("query filter is invalid.")
        search = query.casefold().strip()
        scanned = self.scan()
        matches = []
        for item in scanned["items"]:
            if item["removed"] is not removed:
                continue
            if statuses and item["status"] not in statuses:
                continue
            if kind and item["kind"] not in _CATALOG_KIND_GROUPS.get(
                kind,
                frozenset({kind}),
            ):
                continue
            item_compatibility = item["compatibility"] or "unknown"
            if compatibility and item_compatibility != compatibility:
                continue
            if search and search not in self._search_blob(item):
                continue
            matches.append(item)
        total = len(matches)
        start = (page - 1) * limit
        selected = matches[start : start + limit]
        return {
            "items": selected,
            "page": page,
            "limit": limit,
            "total": total,
            "has_more": start + len(selected) < total,
            "errors": scanned["errors"],
        }

    def _find_locations(
        self,
        namespace: str,
        identifier: str,
        *,
        removed: bool,
    ) -> list[tuple[Path, Path, dict]]:
        locations: list[tuple[Path, Path, dict]] = []
        for root in self._roots_for_namespace(namespace):
            container = self._owned_container(
                root,
                namespace,
                removed=removed,
            )
            if container is None:
                continue
            candidate = container / identifier
            if not candidate.exists() and not candidate.is_symlink():
                continue
            if _is_linklike(candidate) or not candidate.is_dir():
                raise ManifestError("A Library item directory is unsafe.")
            try:
                canonical_container = container.resolve(strict=True)
                canonical_candidate = candidate.resolve(strict=True)
                relative = canonical_candidate.relative_to(canonical_container)
            except (OSError, RuntimeError, ValueError) as exc:
                raise ManifestError("A Library item directory is unsafe.") from exc
            if relative.parts != (identifier,):
                raise ManifestError("A Library item directory is unsafe.")
            manifest = self._read_owned_manifest(
                namespace,
                candidate,
                identifier,
            )
            locations.append((root, candidate, manifest))
        return locations

    def _single_location(
        self,
        catalog_id: str,
        *,
        removed: bool | None,
    ) -> tuple[str, str, Path, Path, dict, bool]:
        namespace, identifier = _parse_catalog_id(catalog_id)
        states = (False, True) if removed is None else (removed,)
        locations = [
            (root, directory, manifest, state)
            for state in states
            for root, directory, manifest in self._find_locations(
                namespace,
                identifier,
                removed=state,
            )
        ]
        if not locations:
            raise ManifestError("The Library item was not found.")
        if len(locations) != 1:
            raise LibraryItemStateError(
                "The Library item ownership is ambiguous."
            )
        root, directory, manifest, state = locations[0]
        return namespace, identifier, root, directory, manifest, state

    def _detail(
        self,
        namespace: str,
        manifest: dict,
        *,
        removed: bool,
    ) -> dict:
        public = self._public_owned_manifest(namespace, manifest)
        summary = self._summary(namespace, public, removed=removed)
        return {
            **summary,
            "job" if namespace == "job" else "item": public,
        }

    @staticmethod
    def _validated_active_ids(
        active_catalog_ids: set[str] | frozenset[str],
    ) -> set[str]:
        if not isinstance(active_catalog_ids, (set, frozenset)):
            raise TypeError("active_catalog_ids must be a set")
        result: set[str] = set()
        for catalog_id in active_catalog_ids:
            namespace, identifier = _parse_catalog_id(catalog_id)
            result.add(_catalog_id(namespace, identifier))
        return result

    def get(self, catalog_id: str) -> dict:
        (
            namespace,
            _identifier,
            _root,
            _directory,
            manifest,
            removed,
        ) = self._single_location(catalog_id, removed=None)
        return self._detail(namespace, manifest, removed=removed)

    def resolve_asset(
        self,
        catalog_id: str,
        asset_id: str,
        *,
        verify_content: bool = True,
    ) -> OwnedAsset:
        (
            namespace,
            _identifier,
            _root,
            directory,
            manifest,
            _removed,
        ) = self._single_location(catalog_id, removed=None)
        canonical_asset_id = _canonical_uuid(asset_id, "asset ID")
        if namespace == "job":
            owned = self.jobs._owned_record(
                directory,
                manifest,
                canonical_asset_id,
            )
        else:
            owned = self.saved_items._owned_record(
                directory,
                manifest,
                canonical_asset_id,
            )
        with owned.open_verified(verify_content=verify_content):
            pass
        return owned

    def _move(
        self,
        catalog_id: str,
        *,
        source_removed: bool,
        active_catalog_ids: set[str] | frozenset[str],
    ) -> dict:
        namespace, identifier = _parse_catalog_id(catalog_id)
        canonical_catalog_id = _catalog_id(namespace, identifier)
        active = self._validated_active_ids(active_catalog_ids)
        if canonical_catalog_id in active:
            raise LibraryItemActiveError(
                "The Library item has an active operation."
            )
        try:
            (
                _namespace,
                _identifier,
                root,
                source,
                manifest,
                _state,
            ) = self._single_location(
                canonical_catalog_id,
                removed=source_removed,
            )
        except ManifestError:
            opposite = self._find_locations(
                namespace,
                identifier,
                removed=not source_removed,
            )
            if opposite:
                raise LibraryItemStateError(
                    "The Library item is already in the requested state."
                ) from None
            raise
        if (
            not source_removed
            and namespace == "job"
            and manifest["status"] not in _TERMINAL_OR_IDLE_STATUSES
        ):
            raise LibraryItemActiveError(
                "The generated Library job is still active."
            )
        if self._find_locations(
            namespace,
            identifier,
            removed=not source_removed,
        ):
            raise LibraryItemStateError(
                "The Library item exists in both live and removed storage."
            )
        with _job_lock(root):
            (
                _namespace,
                _identifier,
                locked_root,
                locked_source,
                locked_manifest,
                _state,
            ) = self._single_location(
                canonical_catalog_id,
                removed=source_removed,
            )
            if locked_root != root or locked_source != source:
                raise LibraryItemStateError(
                    "The Library item changed while the operation was starting."
                )
            if (
                not source_removed
                and namespace == "job"
                and locked_manifest["status"] not in _TERMINAL_OR_IDLE_STATUSES
            ):
                raise LibraryItemActiveError(
                    "The generated Library job is still active."
                )
            if self._find_locations(
                namespace,
                identifier,
                removed=not source_removed,
            ):
                raise LibraryItemStateError(
                    "The Library item destination is already occupied."
                )
            destination_container = self._owned_container(
                root,
                namespace,
                removed=not source_removed,
                create=True,
            )
            assert destination_container is not None
            destination = destination_container / identifier
            if destination.exists() or _is_linklike(destination):
                raise LibraryItemStateError(
                    "The Library item destination is already occupied."
                )
            try:
                os.rename(source, destination)
                _fsync_directory(source.parent)
                _fsync_directory(destination.parent)
                _fsync_directory(root)
            except OSError as exc:
                raise LibraryItemStateError(
                    "The Library item could not be moved."
                ) from exc
            moved_manifest = self._read_owned_manifest(
                namespace,
                destination,
                identifier,
            )
        return self._detail(
            namespace,
            moved_manifest,
            removed=not source_removed,
        )

    def remove(
        self,
        catalog_id: str,
        *,
        active_catalog_ids: set[str] | frozenset[str] = frozenset(),
    ) -> dict:
        return self._move(
            catalog_id,
            source_removed=False,
            active_catalog_ids=active_catalog_ids,
        )

    def restore(
        self,
        catalog_id: str,
        *,
        active_catalog_ids: set[str] | frozenset[str] = frozenset(),
    ) -> dict:
        return self._move(
            catalog_id,
            source_removed=True,
            active_catalog_ids=active_catalog_ids,
        )

    def delete_forever(
        self,
        catalog_id: str,
        *,
        active_catalog_ids: set[str] | frozenset[str] = frozenset(),
    ) -> dict:
        namespace, identifier = _parse_catalog_id(catalog_id)
        canonical_catalog_id = _catalog_id(namespace, identifier)
        active = self._validated_active_ids(active_catalog_ids)
        if canonical_catalog_id in active:
            raise LibraryItemActiveError(
                "The Library item has an active operation."
            )
        try:
            (
                _namespace,
                _identifier,
                root,
                directory,
                _manifest,
                _state,
            ) = self._single_location(
                canonical_catalog_id,
                removed=True,
            )
        except ManifestError:
            if self._find_locations(
                namespace,
                identifier,
                removed=False,
            ):
                raise LibraryItemStateError(
                    "Only a removed Library item can be deleted forever."
                ) from None
            raise
        if self._find_locations(namespace, identifier, removed=False):
            raise LibraryItemStateError(
                "The Library item exists in both live and removed storage."
            )
        with _job_lock(root):
            (
                _namespace,
                _identifier,
                locked_root,
                locked_directory,
                _manifest,
                _state,
            ) = self._single_location(
                canonical_catalog_id,
                removed=True,
            )
            if locked_root != root or locked_directory != directory:
                raise LibraryItemStateError(
                    "The Library item changed while deletion was starting."
                )
            if _tree_contains_linklike(directory):
                raise ManifestError("The trashed Library item contains an unsafe link.")
            try:
                shutil.rmtree(directory)
                _fsync_directory(directory.parent)
                _fsync_directory(root)
            except OSError as exc:
                raise LibraryItemStateError(
                    "The removed Library item could not be deleted."
                ) from exc
        return {"catalog_id": canonical_catalog_id, "deleted": True}


__all__ = [
    "AssetNotFoundError",
    "DEFAULT_MINIMUM_FREE_BYTES",
    "GeneratedAssetLibrary",
    "InvalidIdentifierError",
    "LibraryCatalog",
    "LibraryError",
    "LibraryItemActiveError",
    "LibraryItemStateError",
    "LibraryRootError",
    "MANIFEST_SCHEMA_VERSION",
    "ManifestError",
    "OwnedAsset",
    "SAVED_ITEM_SCHEMA_VERSION",
    "SavedItemLibrary",
]
