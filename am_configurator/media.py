"""Hardened local media boundary for provider video downloads and animation."""

from __future__ import annotations

import errno
import hashlib
import math
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
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
    """A stable media failure with optional in-memory process diagnostics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        process_diagnostics: object = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.process_diagnostics = _bounded_ffmpeg_diagnostics(process_diagnostics)


class MediaCancelled(Exception):
    """Raised only between bounded downloader I/O operations."""


@dataclass(frozen=True)
class DownloadedVideo:
    """Durable local result; deliberately carries no provider URL."""

    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ProcessedAnimation:
    """An exact, validated compact-raster frame sequence."""

    directory: Path
    frame_paths: tuple[Path, ...]
    frame_count: int
    width: int
    height: int
    loop_mode: str


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _default_opener():
    context = ssl.create_default_context()
    director = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
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


def _response_is_closed(response: object) -> bool:
    isclosed = getattr(response, "isclosed", None)
    if callable(isclosed):
        try:
            if isclosed():
                return True
        except (OSError, ValueError):
            pass
    return hasattr(response, "fp") and getattr(response, "fp", None) is None


def _looks_like_mp4(prefix: bytes, total_size: int) -> bool:
    if total_size < 16 or len(prefix) < 16 or prefix[4:8] != b"ftyp":
        return False
    box_size = int.from_bytes(prefix[:4], "big")
    if box_size == 1:
        if total_size < 24 or len(prefix) < 24:
            return False
        box_size = int.from_bytes(prefix[8:16], "big")
        return 24 <= box_size <= total_size
    return 16 <= box_size <= total_size


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


def _copy_video_backup(
    source: Path,
    backup: Path,
    deadline: float,
    cancelled,
) -> None:
    """Create a private durable backup when the filesystem cannot hard-link."""

    read_flags = os.O_RDONLY
    read_flags |= getattr(os, "O_CLOEXEC", 0)
    read_flags |= getattr(os, "O_NOFOLLOW", 0)
    read_flags |= getattr(os, "O_BINARY", 0)
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    write_flags |= getattr(os, "O_CLOEXEC", 0)
    write_flags |= getattr(os, "O_NOFOLLOW", 0)
    write_flags |= getattr(os, "O_BINARY", 0)
    source_fd: int | None = None
    backup_fd: int | None = None
    complete = False
    try:
        source_fd = os.open(source, read_flags)
        backup_fd = os.open(backup, write_flags, 0o600)
        with os.fdopen(source_fd, "rb") as source_stream:
            source_fd = None
            with os.fdopen(backup_fd, "wb") as backup_stream:
                backup_fd = None
                while True:
                    _check_cancel(cancelled)
                    _remaining_timeout(deadline)
                    chunk = source_stream.read(_READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    backup_stream.write(chunk)
                backup_stream.flush()
                os.fsync(backup_stream.fileno())
        os.chmod(backup, 0o600)
        _fsync_directory(backup.parent)
        complete = True
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if backup_fd is not None:
            os.close(backup_fd)
        if not complete:
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass


def _create_video_backup(
    source: Path,
    backup: Path,
    deadline: float,
    cancelled,
) -> None:
    try:
        os.link(source, backup, follow_symlinks=False)
    except (NotImplementedError, OSError):
        _copy_video_backup(source, backup, deadline, cancelled)


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
    preserve_backup = False
    try:
        expected_size = _content_length(response)
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
                if len(prefix) < 24:
                    prefix.extend(chunk[: 24 - len(prefix)])
                digest.update(chunk)
                try:
                    stream.write(chunk)
                except OSError:
                    raise MediaError("io", "video temporary file write failed") from None
                if expected_size is not None and total == expected_size:
                    break
                if _response_is_closed(response):
                    break

            _check_cancel(cancelled)
            _remaining_timeout(deadline)
            if expected_size is not None and total != expected_size:
                raise MediaError(
                    "bad_response", "video response length did not match its header"
                )
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
                _create_video_backup(
                    destination_path,
                    backup_path,
                    deadline,
                    cancelled,
                )
                backup_created = True
            os.replace(part_path, destination_path)
            published = True
            try:
                _fsync_directory(destination_path.parent)
            except OSError:
                if backup_created:
                    rollback_failure: MediaError | None = None
                    try:
                        os.replace(backup_path, destination_path)
                    except OSError:
                        preserve_backup = True
                        rollback_failure = MediaError(
                            "io",
                            "video publication rollback failed; previous file was preserved",
                        )
                    if rollback_failure is not None:
                        raise rollback_failure from None
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
        if backup_created and not preserve_backup:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass


def content_frame_count(frame_count: int, loop_mode: str) -> int:
    """Return the full-source frames FFmpeg must produce for a loop mode."""
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count <= 0:
        raise MediaError("config", "animation frame count is invalid")
    if loop_mode == "smooth":
        return frame_count - math.ceil(frame_count / 8)
    if loop_mode == "none":
        return frame_count
    if loop_mode == "ping_pong":
        if frame_count % 2:
            raise MediaError("config", "ping-pong animation requires an even frame count")
        return frame_count // 2 + 1
    raise MediaError("config", "animation loop mode is invalid")


def _validated_dimensions(width: object, height: object) -> tuple[int, int]:
    values = (width, height)
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= 4096
        for value in values
    ):
        raise MediaError("config", "animation dimensions are invalid")
    return width, height


def _absolute_regular_file(value: object, label: str, *, executable: bool = False) -> Path:
    try:
        path = Path(os.fspath(value))
    except (TypeError, ValueError):
        raise MediaError("config", f"{label} path is invalid") from None
    if not path.is_absolute() or path.is_symlink():
        raise MediaError("config", f"{label} must be an absolute regular file")
    try:
        path = path.resolve(strict=True)
    except OSError:
        raise MediaError("config", f"{label} is unavailable") from None
    if not path.is_file():
        raise MediaError("config", f"{label} must be an absolute regular file")
    if executable and not os.access(path, os.X_OK):
        raise MediaError("config", f"{label} is not executable")
    return path


def _absolute_output_pattern(value: object) -> Path:
    try:
        pattern = Path(os.fspath(value))
    except (TypeError, ValueError):
        raise MediaError("config", "animation output pattern is invalid") from None
    if (
        not pattern.is_absolute()
        or pattern.name.count("%04d") != 1
        or pattern.name.replace("%04d", "").find("%") != -1
        or pattern.suffix.casefold() != ".png"
        or not pattern.parent.is_dir()
        or pattern.parent.is_symlink()
    ):
        raise MediaError("config", "animation output pattern is invalid")
    return pattern


def _ffmpeg_image2_pattern(pattern: Path) -> str:
    """Escape literal parent-path percents while retaining the frame token."""

    escaped_parent = os.fspath(pattern.parent).replace("%", "%%")
    return os.path.join(escaped_parent, pattern.name)


def build_ffmpeg_frame_command(
    ffmpeg_path: object,
    source_path: object,
    output_pattern: object,
    *,
    width: object,
    height: object,
    content_frame_count: object,
) -> tuple[str, ...]:
    """Build the fixed local-only argv used to decode compact content frames."""
    binary = _absolute_regular_file(ffmpeg_path, "FFmpeg runtime", executable=True)
    source = _absolute_regular_file(source_path, "source video")
    pattern = _absolute_output_pattern(output_pattern)
    width, height = _validated_dimensions(width, height)
    if (
        isinstance(content_frame_count, bool)
        or not isinstance(content_frame_count, int)
        or not 1 <= content_frame_count <= 200
    ):
        raise MediaError("config", "animation content frame count is invalid")
    filter_graph = ",".join(
        (
            "trim=duration=1",
            "setpts=PTS-STARTPTS",
            (
                f"minterpolate=fps={content_frame_count}:mi_mode=mci:"
                "mc_mode=aobmc:me_mode=bidir:vsbmc=1"
            ),
            (
                f"scale=w={width}:h={height}:"
                "force_original_aspect_ratio=increase:flags=lanczos"
            ),
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2",
            "format=rgb24",
            f"fps=fps={content_frame_count}:round=up:eof_action=pass",
        )
    )
    return (
        str(binary),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-protocol_whitelist",
        "file",
        "-i",
        str(source),
        "-an",
        "-sn",
        "-dn",
        "-vf",
        filter_graph,
        "-frames:v",
        str(content_frame_count),
        "-start_number",
        "1",
        "-threads",
        "1",
        "-c:v",
        "png",
        "-f",
        "image2",
        _ffmpeg_image2_pattern(pattern),
    )


def subprocess_creation_flags(os_name: str | None = None) -> int:
    """Return the platform flag that keeps FFmpeg from opening a console."""
    if os_name is None:
        os_name = os.name
    if os_name == "nt":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def _bounded_ffmpeg_diagnostics(stderr: object) -> str:
    if isinstance(stderr, bytes):
        value = stderr[-8192:].decode("utf-8", errors="replace")
    elif isinstance(stderr, str):
        value = stderr[-8192:]
    else:
        return ""
    return "".join(character if character >= " " or character in "\n\t" else "?" for character in value)


def _stop_process(process) -> None:
    try:
        process.terminate()
    except (OSError, ProcessLookupError):
        return
    try:
        process.wait(timeout=1.0)
        return
    except subprocess.TimeoutExpired:
        pass
    except (OSError, ValueError):
        return
    try:
        process.kill()
    except (OSError, ProcessLookupError):
        return
    try:
        process.wait(timeout=1.0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def _start_diagnostic_reader(process) -> tuple[bytearray, threading.Thread | None]:
    stream = getattr(process, "stderr", None)
    buffer = bytearray()
    if stream is None or not callable(getattr(stream, "read", None)):
        return buffer, None

    def drain() -> None:
        try:
            while True:
                chunk = stream.read(4096)
                if not isinstance(chunk, bytes) or not chunk:
                    return
                buffer.extend(chunk)
                if len(buffer) > 8192:
                    del buffer[:-8192]
        except (OSError, ValueError):
            return

    thread = threading.Thread(target=drain, name="ffmpeg-diagnostics", daemon=True)
    thread.start()
    return buffer, thread


def _finish_diagnostic_reader(process, thread: threading.Thread | None) -> None:
    if thread is None:
        return
    thread.join(timeout=1.0)
    stream = getattr(process, "stderr", None)
    if thread.is_alive():
        try:
            stream.close()
        except (AttributeError, OSError, ValueError):
            pass
        thread.join(timeout=0.1)
    else:
        try:
            stream.close()
        except (AttributeError, OSError, ValueError):
            pass


def _check_processing_cancel(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise MediaCancelled("animation processing cancelled")


def run_ffmpeg_command(
    command: object,
    *,
    deadline: float,
    cancelled=None,
    popen_factory=None,
) -> None:
    """Run one fixed FFmpeg argv with bounded waits and graceful cancellation."""
    if (
        not isinstance(command, (tuple, list))
        or not command
        or any(not isinstance(value, str) or not value for value in command)
        or not Path(command[0]).is_absolute()
        or any(
            "http://" in value.casefold() or "https://" in value.casefold()
            for value in command
        )
    ):
        raise MediaError("config", "FFmpeg command is invalid")
    _check_processing_cancel(cancelled)
    if deadline - time.monotonic() <= 0:
        raise MediaError("timeout", "animation processing deadline expired")
    if popen_factory is None:
        popen_factory = subprocess.Popen
    try:
        process = popen_factory(
            tuple(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess_creation_flags(),
            shell=False,
        )
    except (OSError, ValueError):
        raise MediaError("runtime", "FFmpeg could not be started") from None

    diagnostics, diagnostic_thread = _start_diagnostic_reader(process)
    try:
        while True:
            _check_processing_cancel(cancelled)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MediaError("timeout", "animation processing deadline expired")
            try:
                process.wait(timeout=min(remaining, 0.1))
                break
            except subprocess.TimeoutExpired:
                continue
            except (OSError, ValueError):
                raise MediaError("processing", "FFmpeg process communication failed") from None
    except (MediaCancelled, MediaError):
        _stop_process(process)
        _finish_diagnostic_reader(process, diagnostic_thread)
        raise
    _finish_diagnostic_reader(process, diagnostic_thread)
    if process.returncode != 0:
        raise MediaError(
            "processing",
            "FFmpeg could not process the video",
            process_diagnostics=bytes(diagnostics),
        )


def _validate_png_sequence(
    directory: Path,
    prefix: str,
    count: int,
    width: int,
    height: int,
) -> tuple[Path, ...]:
    from PIL import Image, UnidentifiedImageError

    expected = tuple(directory / f"{prefix}-{index:04d}.png" for index in range(1, count + 1))
    try:
        actual = tuple(sorted(directory.iterdir()))
    except OSError:
        raise MediaError("bad_output", "animation frame output could not be inspected") from None
    if actual != expected or any(path.is_symlink() for path in expected):
        raise MediaError("bad_output", "animation frame names or count were invalid")
    for path in expected:
        try:
            with Image.open(path) as image:
                if (
                    image.format != "PNG"
                    or image.mode != "RGB"
                    or image.size != (width, height)
                ):
                    raise MediaError("bad_output", "animation frame format or dimensions were invalid")
                image.verify()
            with Image.open(path) as image:
                image.load()
        except MediaError:
            raise
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            raise MediaError("bad_output", "animation frame image data was invalid") from None
    return expected


def _write_frame_copy(source: Path, destination: Path) -> None:
    try:
        with source.open("rb") as input_stream, destination.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.chmod(destination, 0o600)
    except OSError:
        raise MediaError("io", "animation frame could not be staged") from None


def _write_smooth_blend(source_last: Path, source_first: Path, destination: Path, alpha: float) -> None:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(source_last) as last_image, Image.open(source_first) as first_image:
            last_rgb = last_image.convert("RGB")
            first_rgb = first_image.convert("RGB")
            blended = Image.blend(last_rgb, first_rgb, alpha)
            with destination.open("xb") as output_stream:
                blended.save(output_stream, format="PNG")
                output_stream.flush()
                os.fsync(output_stream.fileno())
        os.chmod(destination, 0o600)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise MediaError("io", "animation loop blend could not be staged") from None


def _assemble_loop_frames(
    content_paths: tuple[Path, ...],
    destination: Path,
    frame_count: int,
    loop_mode: str,
) -> None:
    if loop_mode == "smooth":
        for index, source in enumerate(content_paths, 1):
            _write_frame_copy(source, destination / f"frame-{index:04d}.png")
        blend_count = frame_count - len(content_paths)
        for offset in range(1, blend_count + 1):
            _write_smooth_blend(
                content_paths[-1],
                content_paths[0],
                destination / f"frame-{len(content_paths) + offset:04d}.png",
                offset / (blend_count + 1),
            )
        return
    if loop_mode == "none":
        order = range(len(content_paths))
    else:
        order = tuple(range(len(content_paths))) + tuple(
            range(len(content_paths) - 2, 0, -1)
        )
    for output_index, content_index in enumerate(order, 1):
        _write_frame_copy(
            content_paths[content_index],
            destination / f"frame-{output_index:04d}.png",
        )


def _validate_processing_paths(
    source_path: object,
    destination_directory: object,
    work_directory: object,
) -> tuple[Path, Path, Path]:
    source = _absolute_regular_file(source_path, "source video")
    try:
        destination = Path(os.fspath(destination_directory))
        work = Path(os.fspath(work_directory))
    except (TypeError, ValueError):
        raise MediaError("config", "animation processing path is invalid") from None
    if (
        not destination.is_absolute()
        or not destination.name
        or not destination.parent.is_dir()
        or destination.parent.is_symlink()
        or destination.is_symlink()
        or (destination.exists() and not destination.is_dir())
        or not work.is_absolute()
        or not work.is_dir()
        or work.is_symlink()
    ):
        raise MediaError("config", "animation processing path is invalid")
    try:
        if destination.parent.stat().st_dev != work.stat().st_dev:
            raise MediaError("config", "animation work directory must share the destination filesystem")
    except OSError:
        raise MediaError("config", "animation processing path is unavailable") from None
    return source, destination, work


def _publish_frame_directory(staged: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}.previous")
    if backup.exists() or backup.is_symlink():
        raise MediaError("io", "animation publication backup is unavailable")
    backup_created = False
    published = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            backup_created = True
        os.replace(staged, destination)
        published = True
        _fsync_directory(destination.parent)
    except (OSError, MediaError):
        if published:
            try:
                os.replace(destination, staged)
            except OSError:
                pass
        if backup_created:
            try:
                os.replace(backup, destination)
                backup_created = False
                _fsync_directory(destination.parent)
            except OSError:
                raise MediaError(
                    "io", "animation publication rollback failed; previous frames were preserved"
                ) from None
        raise MediaError("io", "animation frames could not be published durably") from None
    if backup_created:
        try:
            shutil.rmtree(backup)
            _fsync_directory(destination.parent)
        except OSError:
            pass


def _reconcile_frame_publication(destination: Path) -> None:
    """Restore an interrupted prior publication or remove its stale backup."""
    backup = destination.with_name(f".{destination.name}.previous")
    if not backup.exists() and not backup.is_symlink():
        return
    if backup.is_symlink() or not backup.is_dir():
        raise MediaError("io", "animation publication backup is invalid")
    try:
        if destination.exists():
            shutil.rmtree(backup)
        else:
            os.replace(backup, destination)
        _fsync_directory(destination.parent)
    except OSError:
        raise MediaError("io", "animation publication backup could not be reconciled") from None


def process_video_frames(
    source_path: object,
    destination_directory: object,
    work_directory: object,
    *,
    ffmpeg_path: object,
    width: object,
    height: object,
    frame_count: object,
    loop_mode: str,
    deadline: float,
    cancelled=None,
    runner=None,
) -> ProcessedAnimation:
    """Convert one banked local MP4 into an exact atomic firmware-cap sequence."""
    from .device_mapping import MODEL_FRAME_CAPS

    source, destination, work = _validate_processing_paths(
        source_path, destination_directory, work_directory
    )
    width, height = _validated_dimensions(width, height)
    if (
        isinstance(frame_count, bool)
        or not isinstance(frame_count, int)
        or frame_count not in frozenset(MODEL_FRAME_CAPS.values())
    ):
        raise MediaError("config", "animation frame count is not a device maximum")
    content_count = content_frame_count(frame_count, loop_mode)
    _check_processing_cancel(cancelled)
    if deadline - time.monotonic() <= 0:
        raise MediaError("timeout", "animation processing deadline expired")
    binary = _absolute_regular_file(ffmpeg_path, "FFmpeg runtime", executable=True)
    _reconcile_frame_publication(destination)
    if runner is None:
        runner = run_ffmpeg_command

    stage_root: Path | None = None
    try:
        stage_root = Path(tempfile.mkdtemp(prefix="animation-", dir=work))
        os.chmod(stage_root, 0o700)
        content_directory = stage_root / "content"
        final_directory = stage_root / "final"
        content_directory.mkdir(mode=0o700)
        final_directory.mkdir(mode=0o700)
    except OSError:
        if stage_root is not None:
            try:
                shutil.rmtree(stage_root)
            except OSError:
                pass
        raise MediaError("io", "animation work directory could not be prepared") from None

    try:
        command = build_ffmpeg_frame_command(
            binary,
            source,
            content_directory / "content-%04d.png",
            width=width,
            height=height,
            content_frame_count=content_count,
        )
        runner(command, deadline=deadline, cancelled=cancelled)
        _check_processing_cancel(cancelled)
        content_paths = _validate_png_sequence(
            content_directory, "content", content_count, width, height
        )
        _assemble_loop_frames(
            content_paths, final_directory, frame_count, loop_mode
        )
        final_paths = _validate_png_sequence(
            final_directory, "frame", frame_count, width, height
        )
        _fsync_directory(final_directory)
        _publish_frame_directory(final_directory, destination)
        published_paths = tuple(destination / path.name for path in final_paths)
        return ProcessedAnimation(
            directory=destination,
            frame_paths=published_paths,
            frame_count=frame_count,
            width=width,
            height=height,
            loop_mode=loop_mode,
        )
    finally:
        try:
            shutil.rmtree(stage_root)
        except OSError:
            pass
