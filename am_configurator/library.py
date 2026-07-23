"""Durable, private storage for generated Lighting Studio assets.

The library is intentionally independent of provider and device code.  It owns
only local durability and recovery metadata; callers decide whether a returned
``resume_video_poll`` action is scheduled.  Reconciliation never invokes paid
or local processing work itself.

Manifest schema version 2 adds a pipeline discriminator and procedural attempt
records while normalizing version 1 video manifests in memory without rewriting
them. Future stages mutate those existing containers
(``concept_batches``, ``animation_attempts``, ``provider_requests``, ``costs``,
and ``recovery``) instead of adding ad-hoc top-level keys.  Assets are internal
relative paths in the manifest, but public views expose only opaque job and
asset UUIDs.

On POSIX, created job directories/files are explicitly owner-only.  On Windows,
CPython 3.11.10+, 3.12.4+, and 3.13+ honor ``mkdir(mode=0o700)`` with a private
DACL; preflight rejects older patch runtimes.  Native ACL verification for
pre-existing Windows ``jobs`` directories remains pending.  Junctions and
symlinks still fail closed.
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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Mapping

if os.name == "nt":
    import msvcrt
else:
    import fcntl


MANIFEST_SCHEMA_VERSION = 2
DEFAULT_MINIMUM_FREE_BYTES = 256 * 1024 * 1024
_DIRECTORIES = ("concepts", "video", "frames", "preview", "result", ".work")
_ASSET_LAYOUT = {
    "concept": ("concepts", {"image/png": ".png", "image/jpeg": ".jpg"}),
    "selected_still": ("concepts", {"image/png": ".png", "image/jpeg": ".jpg"}),
    "source_video": ("video", {"video/mp4": ".mp4"}),
    "frame": ("frames", {"image/png": ".png"}),
    "preview_poster": ("preview", {"image/png": ".png", "image/jpeg": ".jpg"}),
    "preview_animation": ("preview", {"image/gif": ".gif", "video/mp4": ".mp4"}),
    "mapped_result": ("result", {"application/json": ".json"}),
    "recipe": ("result", {"application/json": ".json"}),
    "raster_animation": ("frames", {"image/gif": ".gif"}),
}
_ASSET_STATUSES = {"complete", "partial", "cancelled_saved"}
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


class LibraryError(RuntimeError):
    """Base class for safe, user-reportable library failures."""


class LibraryRootError(LibraryError):
    """The configured library root is absent or fails preflight."""


class ManifestError(LibraryError):
    """A manifest is corrupt, unsafe, or violates its schema."""


class InvalidIdentifierError(LibraryError):
    """A job or asset identifier is not a canonical opaque UUID."""


class AssetNotFoundError(LibraryError):
    """The requested asset is not owned by the requested job."""


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

    def open_verified(self):
        """Open and integrity-check one stable descriptor for authenticated serving."""
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self.path, flags)
            file = os.fdopen(fd, "rb")
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ManifestError("The owned asset path is unsafe or missing.")
            digest = hashlib.sha256()
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
            if info.st_size != self.record["byte_size"] or not hmac.compare_digest(
                digest.hexdigest(), self.record["sha256"]
            ):
                raise ManifestError("The owned asset failed its integrity check.")
            file.seek(0)
            return file
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
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, value: object) -> None:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write_bytes(path, payload)


def _windows_path_too_long(error: OSError) -> bool:
    return error.errno == errno.ENAMETOOLONG or getattr(error, "winerror", None) == 206


def _run_windows_path_depth_probe(root: Path) -> None:
    """Exercise the longest generated-library temporary path and remove it."""
    # Asset-intent atomic publication is the deepest current path shape:
    # jobs/<36-char job>/.work/.asset-intent-<36-char asset>.json.<8-char>.tmp
    # Keep the synthetic job component exactly UUID length without making it a
    # valid job that a concurrent Library scan could mistake for user data.
    probe_job = root / "jobs" / f".am-depth-{uuid.uuid4().hex[:26]}"
    probe_work = probe_job / ".work"
    intent = probe_work / f"{_ASSET_INTENT_PREFIX}{uuid.uuid4()}.json"
    failure: BaseException | None = None
    cleanup_failure: OSError | None = None
    try:
        _make_private_directory(probe_work, parents=True)
        _atomic_write_bytes(intent, b"{}\n")
    except BaseException as exc:
        failure = exc
    try:
        if probe_job.exists() or probe_job.is_symlink():
            if _is_linklike(probe_job):
                raise OSError("Windows path-depth probe directory is unsafe")
            shutil.rmtree(probe_job)
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


def _file_integrity(path: Path) -> tuple[int, str]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ManifestError("The owned asset path is unsafe or missing.")
            digest = hashlib.sha256()
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
            return info.st_size, digest.hexdigest()
    except OSError as exc:
        raise ManifestError("The owned asset integrity could not be verified.") from exc


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


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
                fcntl.flock(file.fileno(), fcntl.LOCK_EX)
            else:
                file.seek(0, os.SEEK_END)
                if file.tell() == 0:
                    file.write(b"\0")
                    file.flush()
                file.seek(0)
                attempts = 100
                for attempt in range(attempts):
                    try:
                        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if attempt == attempts - 1:
                            raise TimeoutError("The generated job is locked by another process.")
                        threading.Event().wait(0.1)
            try:
                yield
            finally:
                if os.name == "nt":
                    file.seek(0)
                    msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(file.fileno(), fcntl.LOCK_UN)


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
    _validate_request_ids(value)
    _validate_no_sensitive_values(value)
    if set(value) != _MANIFEST_V2_FIELDS:
        raise ManifestError("The job manifest has an unsupported schema.")
    if value["pipeline"] not in _PIPELINES:
        raise ManifestError("The job manifest pipeline is unsupported.")
    job_id = _canonical_uuid(value["job_id"], "job ID")
    if expected_job_id is not None and job_id != expected_job_id:
        raise ManifestError("The job manifest does not own this directory.")
    if not isinstance(value["created_at"], str) or not isinstance(value["updated_at"], str):
        raise ManifestError("The job manifest timestamps are invalid.")
    if not isinstance(value["prompt"], str):
        raise ManifestError("The job prompt is invalid.")
    if value["loop_mode"] not in _LOOP_MODES:
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
        not isinstance(estimated_ticks, int)
        or isinstance(estimated_ticks, bool)
        or estimated_ticks < 0
    ):
        raise ManifestError("The job cost ticks must be non-negative integers.")
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


def _read_manifest(path: Path, job_id: str) -> dict:
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
        value = json.loads(payload.decode("utf-8"))
        return _validate_manifest(value, expected_job_id=job_id)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
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
        if os.name == "nt" and (
            sys.implementation.name != "cpython"
            or not _windows_private_mode_supported(sys.version_info)
        ):
            raise LibraryRootError(
                "Private Windows library folders require CPython 3.11.10+, "
                "3.12.4+, or 3.13+."
            )
        if self._current_root_value is None:
            raise LibraryRootError("A library folder must be configured before generation.")
        root = _canonical_root(self._current_root_value)
        assert root is not None
        try:
            _make_private_directory(root, parents=True)
            if not root.is_dir() or _is_linklike(root):
                raise OSError("root is not a real directory")
            jobs = root / "jobs"
            _make_private_directory(jobs)
            if _is_linklike(jobs):
                raise OSError("jobs directory is a symlink")
            if os.name != "nt":
                os.chmod(jobs, 0o700)
            else:
                _run_windows_path_depth_probe(root)
            _run_write_probe(root)
            free = self._disk_usage(root).free
        except LibraryRootError:
            raise
        except (OSError, PermissionError, AttributeError) as exc:
            raise LibraryRootError("The configured library folder is not privately writable.") from exc
        if not isinstance(free, int) or free < self._minimum_free_bytes:
            raise LibraryRootError("The configured library folder does not have enough free space.")
        return root

    def create_job(
        self,
        *,
        prompt: str = "",
        target: Mapping[str, object] | None = None,
        models: Mapping[str, object] | None = None,
        loop_mode: str = "smooth",
        pipeline: str = "legacy_video",
    ) -> dict:
        """Create an owner-private UUID job and its initial manifest."""
        if pipeline not in _PIPELINES:
            raise ManifestError("The job pipeline is unsupported.")
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
                "pipeline": pipeline,
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
                "loop_mode": loop_mode,
                "models": copy.deepcopy(dict(models or {})),
                "provider_requests": {},
                "status": "created",
                "phase": "preflight",
                "progress": {"completed": 0, "total": None},
                "assets": [],
                "costs": {
                    "estimated_ticks": 0,
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

    def _resolve_record(self, job_dir: Path, manifest: dict, asset_id: str) -> OwnedAsset:
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
        actual_size, actual_sha256 = _file_integrity(canonical_path)
        if actual_size != record["byte_size"] or not hmac.compare_digest(
            actual_sha256, record["sha256"]
        ):
            raise ManifestError("The owned asset failed its integrity check.")
        return OwnedAsset(canonical_path, copy.deepcopy(record))

    def resolve_asset(self, job_id: str, asset_id: str) -> OwnedAsset:
        canonical_job_id = _canonical_uuid(job_id, "job ID")
        canonical_asset_id = _canonical_uuid(asset_id, "asset ID")
        job_dir = self._find_job_dir(canonical_job_id)
        with _job_lock(job_dir):
            manifest = _read_manifest(job_dir / "manifest.json", canonical_job_id)
            return self._resolve_record(job_dir, manifest, canonical_asset_id)

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
                    manifest = _read_manifest(entry / "manifest.json", job_id)
                except ManifestError:
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

    @staticmethod
    def _video_request_id(manifest: dict) -> str | None:
        video = manifest["provider_requests"].get("video")
        if not isinstance(video, dict):
            return None
        request_id = video.get("request_id")
        if isinstance(request_id, str) and _SAFE_REQUEST_ID.fullmatch(request_id):
            return request_id
        return None

    @staticmethod
    def _video_request_status(manifest: dict) -> str | None:
        video = manifest["provider_requests"].get("video")
        if not isinstance(video, dict):
            return None
        status = video.get("status")
        return status if isinstance(status, str) else None

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

    def _source_video_asset(self, job_dir: Path, manifest: dict) -> dict | None:
        for asset in reversed(manifest["assets"]):
            if (
                asset["kind"] == "source_video"
                and asset["status"] in {"complete", "cancelled_saved"}
                and self._asset_record_is_valid(job_dir, manifest, asset)
            ):
                return asset
        return None

    def _reconcile_scanned_job(self, original: dict, job_dir: Path) -> dict | None:
        job_id = original["job_id"]
        original = self._recover_orphan_assets(job_dir, job_id)
        status = original["status"]
        phase = original["phase"]
        request_id = self._video_request_id(original)
        request_status = self._video_request_status(original)
        source_video = self._source_video_asset(job_dir, original)
        has_mapped_result = any(
            asset["kind"] == "mapped_result"
            and asset["status"] == "complete"
            and self._asset_record_is_valid(job_dir, original, asset)
            for asset in original["assets"]
        )
        changes: dict[str, object] = {}
        action = None

        if source_video is not None and not has_mapped_result and status not in {
            "ready_to_process",
            "cancelled_saved",
        }:
            recovery = copy.deepcopy(original["recovery"])
            recovery["source_video_asset_id"] = source_video["asset_id"]
            if status == "cancelled" or original["cancel_requested_at"] is not None:
                changes = {
                    "status": "cancelled_saved",
                    "phase": "cancelled_saved",
                    "recovery": recovery,
                }
            else:
                changes = {
                    "status": "ready_to_process",
                    "phase": "ready_to_process",
                    "recovery": recovery,
                }
        elif (
            request_id is not None
            and source_video is None
            and phase
            in {
                "video_submitting",
                "video_submitted",
                "video_polling",
                "video_downloading",
                "background_retrieval",
            }
            and request_status not in {"failed", "expired"}
        ):
            action = {
                "job_id": job_id,
                "action": "resume_video_poll",
                "request_id": request_id,
            }
        elif request_id is not None and request_status in {"failed", "expired"}:
            changes = {"status": request_status, "phase": "video_terminal"}
        elif (
            status == "in_progress"
            and phase in {"video_submitting", "video_submitted"}
            and request_id is None
        ):
            changes = {"status": "submission_unknown", "phase": "interrupted"}
        elif status == "in_progress" and phase in {
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
        elif (
            status == "in_progress"
            and phase in {"local_processing", "processing"}
            and source_video is None
        ):
            changes = {"status": "interrupted", "phase": "interrupted"}
        if changes:
            original = self.update_manifest(job_id, changes)
            status = original["status"]
        if status in _TERMINAL_OR_IDLE_STATUSES:
            with _job_lock(job_dir):
                latest = _read_manifest(job_dir / "manifest.json", job_id)
                if latest["status"] in _TERMINAL_OR_IDLE_STATUSES:
                    self._purge_work(job_dir)
        return action

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


__all__ = [
    "AssetNotFoundError",
    "DEFAULT_MINIMUM_FREE_BYTES",
    "GeneratedAssetLibrary",
    "InvalidIdentifierError",
    "LibraryError",
    "LibraryRootError",
    "MANIFEST_SCHEMA_VERSION",
    "ManifestError",
    "OwnedAsset",
]
