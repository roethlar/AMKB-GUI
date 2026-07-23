"""Small cross-process-safe filesystem publication primitives."""

from __future__ import annotations

import errno
import os
import time
from collections.abc import Callable


WINDOWS_REPLACE_ATTEMPTS = 100
WINDOWS_REPLACE_RETRY_SECONDS = 0.1
_WINDOWS_SHARING_ERRORS = {5, 32}
_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


def fsync_directory(
    path: str | os.PathLike[str],
    *,
    windows: bool | None = None,
) -> None:
    """Durably publish directory entries where the platform supports it."""
    windows = os.name == "nt" if windows is None else windows
    if windows:
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            return
        raise
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            raise
    finally:
        os.close(descriptor)


def replace_file(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    windows: bool | None = None,
    attempts: int = WINDOWS_REPLACE_ATTEMPTS,
    retry_seconds: float = WINDOWS_REPLACE_RETRY_SECONDS,
    sleep: Callable[[float], object] = time.sleep,
) -> None:
    """Atomically replace a file, retrying bounded Windows reader contention."""
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
        raise ValueError("replace attempts must be a positive integer")
    if retry_seconds < 0:
        raise ValueError("replace retry delay must not be negative")
    windows = os.name == "nt" if windows is None else windows
    allowed_attempts = attempts if windows else 1
    for attempt in range(allowed_attempts):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            retryable = isinstance(exc, PermissionError) or getattr(
                exc, "winerror", None
            ) in _WINDOWS_SHARING_ERRORS
            if not retryable or attempt == allowed_attempts - 1:
                raise
            sleep(retry_seconds)
