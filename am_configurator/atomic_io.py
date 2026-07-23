"""Small cross-process-safe filesystem publication primitives."""

from __future__ import annotations

import os
import time
from collections.abc import Callable


WINDOWS_REPLACE_ATTEMPTS = 100
WINDOWS_REPLACE_RETRY_SECONDS = 0.1
_WINDOWS_SHARING_ERRORS = {5, 32}


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
