"""Hardened download boundary for ephemeral xAI-generated videos."""

from __future__ import annotations

import errno
import hashlib
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


VIDEO_MEDIA_HOST = "vidgen.x.ai"
MAX_VIDEO_BYTES = 100_000_000
MAX_MEDIA_REDIRECTS = 5
MEDIA_CALL_TIMEOUT_SECONDS = 30.0
_READ_CHUNK_BYTES = 64 * 1024
_REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))
_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


class MediaError(Exception):
    """A redacted media-boundary failure with a stable local code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MediaCancelled(Exception):
    """Raised only between bounded downloader I/O operations."""


@dataclass(frozen=True)
class DownloadedVideo:
    """Durable local result; deliberately carries no provider URL."""

    path: Path
    size_bytes: int
    sha256: str


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _default_opener():
    context = ssl.create_default_context()
    director = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        _NoRedirectHandler(),
    )
    return director.open


def _validate_media_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise MediaError("config", "video media URL is missing or invalid")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise MediaError("config", "video media URL contains invalid characters")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        raise MediaError("config", "video media URL is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.netloc != VIDEO_MEDIA_HOST
        or parsed.hostname != VIDEO_MEDIA_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise MediaError("config", "video media URL is not an allowed HTTPS URL")
    try:
        if parsed.port is not None:
            raise MediaError("config", "video media URL must not specify a port")
    except ValueError as exc:
        raise MediaError("config", "video media URL has an invalid port") from None
    return value


def _header(response: object, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is not None:
            return str(value)
    try:
        items = headers.items()
    except (AttributeError, TypeError):
        return None
    for key, value in items:
        if str(key).casefold() == name.casefold():
            return str(value)
    return None


def _status(response: object) -> int:
    value = getattr(response, "status", None)
    if value is None:
        getcode = getattr(response, "getcode", None)
        if callable(getcode):
            value = getcode()
    if isinstance(value, bool) or not isinstance(value, int):
        raise MediaError("bad_response", "video host returned an invalid HTTP status")
    return value


def _close_quietly(response: object) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except OSError:
            pass


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise MediaError("timeout", "video download deadline expired")
    return min(remaining, MEDIA_CALL_TIMEOUT_SECONDS)


def _check_cancel(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise MediaCancelled("video download cancelled")


def _open_media_response(
    source_url: str,
    deadline: float,
    opener,
    cancelled,
):
    current_url = _validate_media_url(source_url)
    redirects = 0
    while True:
        _check_cancel(cancelled)
        timeout = _remaining_timeout(deadline)
        request = urllib.request.Request(
            current_url,
            method="GET",
            headers={"Accept": "video/mp4"},
        )
        failure: MediaError | None = None
        try:
            response = opener(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                failure = MediaError("timeout", "video host request timed out")
            else:
                failure = MediaError("unavailable", "video host could not be reached")
        except (TimeoutError, socket.timeout):
            failure = MediaError("timeout", "video host request timed out")
        except (ssl.SSLError, OSError):
            failure = MediaError("unavailable", "video host could not be reached")
        if failure is not None:
            raise failure from None

        keep_open = False
        try:
            status = _status(response)
            if status in _REDIRECT_STATUSES:
                location = _header(response, "Location")
                if not location:
                    raise MediaError(
                        "bad_response", "video host redirect omitted its destination"
                    )
                if redirects >= MAX_MEDIA_REDIRECTS:
                    raise MediaError("bad_response", "video host redirected too many times")
                next_url = urllib.parse.urljoin(current_url, location)
                current_url = _validate_media_url(next_url)
                redirects += 1
                continue
            if not 200 <= status <= 299:
                raise MediaError(
                    "unavailable", "video host returned an unsuccessful response"
                )
            keep_open = True
            return response
        finally:
            if not keep_open:
                _close_quietly(response)


def _content_length(response: object) -> int | None:
    raw = _header(response, "Content-Length")
    if raw is None:
        return None
    try:
        value = int(raw, 10)
    except (TypeError, ValueError):
        raise MediaError("bad_response", "video host sent an invalid content length")
    if value < 0:
        raise MediaError("bad_response", "video host sent an invalid content length")
    if value > MAX_VIDEO_BYTES:
        raise MediaError("too_large", "video exceeded the download size limit")
    return value


def _set_response_timeout(response: object, timeout: float) -> None:
    paths = (
        (),
        ("fp",),
        ("fp", "raw"),
        ("fp", "raw", "_sock"),
        ("fp", "_sock"),
        ("raw", "_sock"),
        ("_sock",),
    )
    for path in paths:
        candidate = response
        try:
            for attribute in path:
                candidate = getattr(candidate, attribute)
        except (AttributeError, ValueError):
            continue
        setter = getattr(candidate, "settimeout", None)
        if not callable(setter):
            continue
        failure: MediaError | None = None
        try:
            setter(timeout)
        except (OSError, ValueError):
            failure = MediaError("unavailable", "video response timeout could not be set")
        if failure is not None:
            raise failure from None
        return
    raise MediaError("bad_response", "video response did not expose timeout control")


def _looks_like_mp4(prefix: bytes, total_size: int) -> bool:
    if total_size < 12 or len(prefix) < 12 or prefix[4:8] != b"ftyp":
        return False
    box_size = int.from_bytes(prefix[:4], "big")
    if box_size == 1:
        if len(prefix) < 16:
            return False
        box_size = int.from_bytes(prefix[8:16], "big")
        return 16 <= box_size <= total_size
    return 8 <= box_size <= total_size


def _fsync_directory(path: Path) -> None:
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


def _destination_paths(destination: object) -> tuple[Path, Path]:
    try:
        path = Path(os.fspath(destination))
    except (TypeError, ValueError):
        raise MediaError("config", "video destination is invalid") from None
    if not path.name or not path.parent.is_dir():
        raise MediaError("config", "video destination parent is unavailable")
    if path.is_symlink() or path.is_dir():
        raise MediaError("config", "video destination is not a regular file path")
    if path.exists() and not path.is_file():
        raise MediaError("config", "video destination is not a regular file path")
    part = path.with_name(path.name + ".part")
    try:
        if part.is_dir():
            raise MediaError("config", "video temporary destination is invalid")
        part.unlink(missing_ok=True)
    except MediaError:
        raise
    except OSError:
        raise MediaError("io", "video temporary destination could not be prepared") from None
    return path, part


def download_video(
    source_url: object,
    destination: object,
    deadline: float,
    *,
    opener=None,
    cancelled=None,
) -> DownloadedVideo:
    """Download, validate, hash, and atomically publish one temporary xAI MP4."""
    source_url = _validate_media_url(source_url)
    _check_cancel(cancelled)
    _remaining_timeout(deadline)
    destination_path, part_path = _destination_paths(destination)
    if opener is None:
        opener = _default_opener()

    response = _open_media_response(source_url, deadline, opener, cancelled)
    published = False
    backup_path = destination_path.with_name(destination_path.name + ".previous")
    backup_created = False
    try:
        _content_length(response)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(part_path, flags, 0o600)
        except OSError:
            raise MediaError("io", "video temporary file could not be created") from None

        digest = hashlib.sha256()
        total = 0
        prefix = bytearray()
        with os.fdopen(fd, "wb") as stream:
            while True:
                _check_cancel(cancelled)
                read_timeout = _remaining_timeout(deadline)
                _set_response_timeout(response, read_timeout)
                amount = min(_READ_CHUNK_BYTES, MAX_VIDEO_BYTES - total + 1)
                read_failure: MediaError | None = None
                try:
                    chunk = response.read(amount)
                except (TimeoutError, socket.timeout):
                    read_failure = MediaError("timeout", "video response read timed out")
                except (ssl.SSLError, OSError):
                    read_failure = MediaError("unavailable", "video response read failed")
                if read_failure is not None:
                    raise read_failure from None
                if not isinstance(chunk, bytes):
                    raise MediaError(
                        "bad_response", "video host returned non-byte content"
                    )
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise MediaError("too_large", "video exceeded the download size limit")
                if len(prefix) < 16:
                    prefix.extend(chunk[: 16 - len(prefix)])
                digest.update(chunk)
                try:
                    stream.write(chunk)
                except OSError:
                    raise MediaError("io", "video temporary file write failed") from None

            _check_cancel(cancelled)
            _remaining_timeout(deadline)
            if not _looks_like_mp4(bytes(prefix), total):
                raise MediaError("bad_response", "video response was not an MP4 file")
            try:
                stream.flush()
                os.fsync(stream.fileno())
            except OSError:
                raise MediaError("io", "video temporary file could not be synced") from None
        try:
            os.chmod(part_path, 0o600)
            if backup_path.is_dir():
                raise MediaError("io", "video publication backup is invalid")
            backup_path.unlink(missing_ok=True)
            if destination_path.exists():
                os.link(destination_path, backup_path, follow_symlinks=False)
                backup_created = True
            os.replace(part_path, destination_path)
            published = True
            try:
                _fsync_directory(destination_path.parent)
            except OSError:
                if backup_created:
                    os.replace(backup_path, destination_path)
                    backup_created = False
                else:
                    destination_path.unlink(missing_ok=True)
                published = False
                try:
                    _fsync_directory(destination_path.parent)
                except OSError:
                    pass
                raise MediaError(
                    "io", "video file could not be published durably"
                ) from None
            if backup_created:
                try:
                    backup_path.unlink()
                    backup_created = False
                except OSError:
                    pass
                if not backup_created:
                    try:
                        _fsync_directory(destination_path.parent)
                    except OSError:
                        pass
        except MediaError:
            raise
        except OSError:
            raise MediaError("io", "video file could not be published durably") from None

        return DownloadedVideo(
            path=destination_path,
            size_bytes=total,
            sha256=digest.hexdigest(),
        )
    finally:
        _close_quietly(response)
        if not published:
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass
        if backup_created:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass
