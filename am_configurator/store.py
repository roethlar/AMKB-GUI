#!/usr/bin/env python3
"""Device-scoped state store for each keyboard's configuration and history.

The firmware does not support partial writes (`JSON_START` erases the whole
configuration flash), and LED frames cannot be read back from the device. The
last verified full profile is therefore the local source of truth for LED state.
It is persisted here per device and snapshotted after each verified write.

Storage root resolution ladder (first that is set wins):

    $AM_CONFIGURATOR_DATA_DIR > $XDG_DATA_HOME/am-configurator > ~/.local/share/am-configurator

Layout::

    <root>/devices/<product_id>/current.json   # last full IR we wrote (LED source of truth)
    <root>/devices/<product_id>/meta.json       # product_id, version, last_seen
    <root>/devices/<product_id>/layout-evidence.json  # bounded pathless Vial layouts
    <root>/devices/<product_id>/history/...      # ISO8601 snapshots (added in a later issue)

Device identity: the R4 exposes no unique per-unit serial (the USB serial string
is a shared dummy, product_id/version are identical across all R4s), so we key on
`product_id` (e.g. `CB04`) and treat the single-device case as the supported one.

Pure stdlib — no pyserial / Pillow — so it loads in a core-only install.

Usage::

    python -m am_configurator.store path --device CB04
    python -m am_configurator.store --selftest
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .atomic_io import fsync_directory, replace_file

if os.name == "nt":
    import msvcrt
else:
    import fcntl

APP = "am-configurator"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_WINDOWS_LOCK_ATTEMPTS = 100
_WINDOWS_LOCK_RETRY_SECONDS = 0.1


def store_root() -> Path:
    """Resolve the storage root via the ladder (env override > XDG > home default)."""
    env = os.environ.get("AM_CONFIGURATOR_DATA_DIR")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / APP
    return Path.home() / ".local" / "share" / APP


def _safe_key(product_id: str) -> str:
    """Guard the device key so it can't escape the devices/ dir (path traversal)."""
    key = (product_id or "").strip()
    if not _SAFE_KEY.match(key):
        raise ValueError(
            f"invalid product_id key {product_id!r} (expected [A-Za-z0-9_-]+, e.g. 'CB04')"
        )
    return key


def sole_device() -> str | None:
    """The single stored device key, or None when zero or several exist.

    Single-device is the supported case (the R4 has no per-unit identity), so
    offline commands (dump / diff) can unambiguously target the one device dir
    when exactly one exists; we refuse to guess between several.
    """
    devices = store_root() / "devices"
    if not devices.is_dir():
        return None
    keys = [d.name for d in devices.iterdir() if d.is_dir()]
    return keys[0] if len(keys) == 1 else None


def device_dir(product_id: str, *, create: bool = False) -> Path:
    """`<root>/devices/<product_id>/`. Create it (and parents) when `create`."""
    d = store_root() / "devices" / _safe_key(product_id)
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def current_path(product_id: str) -> Path:
    return device_dir(product_id) / "current.json"


def meta_path(product_id: str) -> Path:
    return device_dir(product_id) / "meta.json"


def _lock_windows_byte(
    file,
    *,
    attempts: int = _WINDOWS_LOCK_ATTEMPTS,
    retry_seconds: float = _WINDOWS_LOCK_RETRY_SECONDS,
) -> None:
    """Acquire Windows' byte lock with a bounded, diagnosable retry."""
    if attempts < 1:
        raise ValueError("Windows lock attempts must be at least 1")
    for attempt in range(attempts):
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if attempt == attempts - 1:
                raise TimeoutError(
                    "Device profile is locked by another AM Configurator process."
                ) from exc
            time.sleep(retry_seconds)


@contextlib.contextmanager
def device_lock(product_id: str):
    """Exclusive per-device advisory lock on `<device_dir>/.lock`.

    Holds for a whole compound write so two concurrent app processes can't
    interleave the current.json + meta.json pair (or, later, a snapshot+save
    sequence) and leave them describing different states. Unix uses ``flock``;
    Windows locks the first byte with ``msvcrt.locking``.
    """
    lock_path = device_dir(product_id, create=True) / ".lock"
    with open(lock_path, "a+b") as f:
        if os.name == "nt":
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                f.write(b"\0")
                f.flush()
            _lock_windows_byte(f)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _atomic_write_json(path: Path, obj: object) -> None:
    """Write JSON atomically: temp file in the same dir, then os.replace().

    Same-directory temp keeps the rename atomic (no cross-filesystem copy), so a
    crash mid-write never leaves a half-written current.json.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        replace_file(tmp, path)
        fsync_directory(path.parent)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict | None:
    """Parsed JSON object, or None if the file is absent."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


LAYOUT_EVIDENCE_SCHEMA_VERSION = 1
LAYOUT_EVIDENCE_MAX = 8
LAYOUT_EVIDENCE_MAX_BYTES = 512 * 1024
_LAYOUT_EVIDENCE_FIELDS = {
    "schema_version",
    "product_id",
    "keymap_signature",
    "key_layout",
}


def layout_evidence_path(product_id: str) -> Path:
    """Private app-local dynamic layouts remembered for one product family."""

    return device_dir(product_id) / "layout-evidence.json"


def load_layout_evidence(product_id: str) -> dict | None:
    path = layout_evidence_path(product_id)
    if not path.exists():
        return None
    with path.open("rb") as stream:
        encoded = stream.read(LAYOUT_EVIDENCE_MAX_BYTES + 1)
    if len(encoded) > LAYOUT_EVIDENCE_MAX_BYTES:
        raise ValueError("Remembered layout evidence is oversized.")
    value = json.loads(encoded)
    if not isinstance(value, dict):
        raise ValueError("Remembered layout evidence is invalid.")
    return value


def remember_layout_evidence(
    product_id: str,
    evidence: dict,
    *,
    validate_existing: Callable[[object], dict],
) -> Path:
    """Remember one validated pathless projection with bounded retention."""

    if not isinstance(evidence, dict) or set(evidence) != _LAYOUT_EVIDENCE_FIELDS:
        raise ValueError("Dynamic layout evidence is invalid.")
    signature = evidence.get("keymap_signature")
    if not isinstance(signature, str) or not signature:
        raise ValueError("Dynamic layout evidence has no signature.")
    path = layout_evidence_path(product_id)
    with device_lock(product_id):
        try:
            current = load_layout_evidence(product_id)
        except (OSError, ValueError):
            current = None
        layouts: list[object] = []
        if (
            isinstance(current, dict)
            and set(current) == {"schema_version", "layouts"}
            and current.get("schema_version") == LAYOUT_EVIDENCE_SCHEMA_VERSION
            and isinstance(current.get("layouts"), list)
            and len(current["layouts"]) <= LAYOUT_EVIDENCE_MAX
        ):
            layouts = current["layouts"]
        retained: list[dict] = []
        for item in layouts:
            try:
                validated = validate_existing(item)
            except (TypeError, ValueError):
                continue
            if validated.get("keymap_signature") != signature:
                retained.append(validated)
        payload = {
            "schema_version": LAYOUT_EVIDENCE_SCHEMA_VERSION,
            "layouts": [evidence, *retained][:LAYOUT_EVIDENCE_MAX],
        }
        if current == payload:
            return path
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > LAYOUT_EVIDENCE_MAX_BYTES:
            raise ValueError("Remembered layout evidence is oversized.")
        _atomic_write_json(path, payload)
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_current(product_id: str) -> dict | None:
    """The last full IR we wrote for this device, or None if we've never written it."""
    return _read_json(current_path(product_id))


def load_meta(product_id: str) -> dict | None:
    return _read_json(meta_path(product_id))


def _update_meta(product_id: str, *, version: str | None = None) -> dict:
    """Merge-update meta.json (product_id, version, last_seen). Returns the new meta."""
    meta = load_meta(product_id) or {}
    meta["product_id"] = _safe_key(product_id)
    if version is not None:
        meta["version"] = version
    meta["last_seen"] = _now_iso()
    _atomic_write_json(meta_path(product_id), meta)
    return meta


def record_seen(product_id: str, *, version: str | None = None) -> dict:
    """Note that we observed this device (updates meta only, not current.json).

    Use from read-only commands (`dump` / `get`) so last_seen tracks reality even
    when nothing is written.
    """
    with device_lock(product_id):
        return _update_meta(product_id, version=version)


def save_current(product_id: str, ir: dict, *, version: str | None = None) -> Path:
    """Persist `ir` as this device's current full config and refresh meta.

    Returns the path to current.json. (Snapshotting into history/ is a separate
    concern, added by the auto-snapshot issue, so writers can compose the two.)
    """
    path = current_path(product_id)
    with device_lock(product_id):
        _atomic_write_json(path, ir)
        _update_meta(product_id, version=version)
    return path


HISTORY_MAX_DEFAULT = 50


def _history_max() -> int:
    """Snapshot retention cap (env `AM_CONFIGURATOR_HISTORY_MAX`, else 50)."""
    raw = os.environ.get("AM_CONFIGURATOR_HISTORY_MAX")
    if raw is None:
        return HISTORY_MAX_DEFAULT
    try:
        n = int(raw)
    except ValueError:
        raise ValueError(f"AM_CONFIGURATOR_HISTORY_MAX must be an integer, got {raw!r}")
    if n < 1:
        raise ValueError(f"AM_CONFIGURATOR_HISTORY_MAX must be >= 1, got {n}")
    return n


def history_dir(product_id: str, *, create: bool = False) -> Path:
    """`<device_dir>/history/` — the timestamped snapshot folder."""
    d = device_dir(product_id) / "history"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def list_history(product_id: str) -> list[Path]:
    """Snapshot files, newest first. ISO8601 names sort lexically = chronologically."""
    d = history_dir(product_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"), reverse=True)


def _prune_history(product_id: str) -> None:
    """Drop the oldest snapshots beyond the retention cap."""
    for old in list_history(product_id)[_history_max():]:
        old.unlink(missing_ok=True)


def snapshot(product_id: str, ir: dict) -> Path:
    """Write `ir` as a timestamped snapshot under history/, then prune to the cap.

    Returns the snapshot path. Locks independently (not nested with
    `save_current`): a writer takes a before-snapshot then saves current as two
    sequential locked steps — flock is per-fd, so nesting two `device_lock`s in
    one process would self-deadlock. The brief gap is acceptable for a
    single-user desktop app (history and current are independent files).
    """
    with device_lock(product_id):
        d = history_dir(product_id, create=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        path = d / f"{stamp}.json"
        suffix = 1
        while path.exists():  # same-microsecond collision guard (rare)
            path = d / f"{stamp}-{suffix}.json"
            suffix += 1
        _atomic_write_json(path, ir)
        _prune_history(product_id)
    return path


# --- App-level settings -------------------------------------------------------
#
# App-scoped configuration in one settings.json under the store root. A legacy
# 'llm'/'ai' block from an older build of the app is tolerated on load and
# silently dropped: no AI provider settings, model choices, or credentials
# survive migration to the current schema.

SETTINGS_SCHEMA_VERSION = 7
LOOP_MODES = ("smooth", "none", "ping_pong")


class SettingsUnavailableError(ValueError):
    """Settings could not be read or written without risking existing bytes."""

    code = "settings_unavailable"

    def __init__(self) -> None:
        super().__init__("Settings are temporarily unavailable.")


class SettingsSchemaUnsupportedError(ValueError):
    """Settings were written by a newer, unsupported application version."""

    code = "settings_schema_unsupported"

    def __init__(self) -> None:
        super().__init__("Settings require a newer application version.")


class SettingsMigrationWriteError(ValueError):
    """Legacy settings were readable but their upgraded form could not be saved."""

    code = "settings_migration_write_failed"

    def __init__(self) -> None:
        super().__init__("Legacy settings could not be upgraded because storage is unavailable.")


class SettingsMigrationValidationError(ValueError):
    """Legacy settings cannot be represented safely by the active schema."""

    code = "settings_migration_invalid"

    def __init__(self) -> None:
        super().__init__("Legacy settings contain data that cannot be safely upgraded.")


def _default_settings() -> dict:
    """A fresh copy of the current schema v7 defaults."""

    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "library": {"current_root": None, "roots": []},
        "generation": {"loop_mode": "smooth"},
    }


def _validate_library_and_generation(
    settings: dict, *, extra_generation_fields: frozenset[str] = frozenset()
) -> dict:
    """Validate the surviving `library`/`generation` portion of any settings
    version and return it in the current v7 shape. Any `ai`/`llm` sub-object
    a caller already tolerated as a known top-level key is intentionally not
    inspected here — its contents are discarded, never carried forward."""

    result: dict = {"schema_version": SETTINGS_SCHEMA_VERSION}
    result["library"] = _validate_library(settings.get("library", {}))
    generation = _object(settings.get("generation", {}), "settings 'generation'")
    _reject_unknown(
        generation, {"loop_mode"} | extra_generation_fields, "generation settings"
    )
    loop_mode = generation.get("loop_mode", "smooth")
    if loop_mode not in LOOP_MODES:
        raise ValueError("loop_mode must be smooth, none, or ping_pong")
    result["generation"] = {"loop_mode": loop_mode}
    return result


def settings_path() -> Path:
    """`<root>/settings.json` — app-level (not per-device) configuration."""
    return store_root() / "settings.json"


@contextlib.contextmanager
def _settings_lock():
    """Exclusive advisory lock on `<root>/.settings.lock` for compound writes.

    Modelled on `device_lock` but app-scoped, so two concurrent app processes
    cannot interleave a settings write. Unix uses ``flock``; Windows locks the
    first byte with ``msvcrt.locking``.
    """
    root = store_root()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".settings.lock"
    with open(lock_path, "a+b") as f:
        if os.name == "nt":
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                f.write(b"\0")
                f.flush()
            _lock_windows_byte(f)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _object(values: object, label: str) -> dict:
    if not isinstance(values, dict):
        raise ValueError(f"{label} must be a JSON object")
    return values


def _reject_unknown(values: dict, allowed: set[str], label: str) -> None:
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown {label} field(s): {sorted(unknown)}")


def _canonical_library_root(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("library current_root must be an absolute path or null")
    try:
        path = Path(value).expanduser()
    except (OSError, RuntimeError) as exc:
        raise ValueError("library current_root could not be canonicalized") from exc
    if not path.is_absolute():
        raise ValueError("library current_root must be an absolute path or null")
    try:
        return str(path.resolve(strict=False))
    except (OSError, RuntimeError) as exc:
        raise ValueError("library current_root could not be canonicalized") from exc


def _validate_legacy_settings(values: object) -> dict:
    """Accept the unversioned v1 shape (llm ignored) and return v7-shaped settings."""
    settings = _object(values, "settings")
    unknown_top = set(settings) - {"schema_version", "llm"}
    if unknown_top:
        raise ValueError(f"unknown settings field(s): {sorted(unknown_top)}")
    if "schema_version" in settings:
        version = settings["schema_version"]
        if type(version) is not int or version != 1:
            raise ValueError("unsupported settings schema_version")

    # The legacy 'llm' block (interpreter/renderer/keys) is tolerated but
    # discarded: nothing downstream still consumes AI provider settings.
    _object(settings.get("llm", {}), "settings 'llm'")

    return _default_settings()


def _validate_v2_settings(values: object) -> dict:
    """Accept the former v2 shape (llm ignored) and return v7-shaped settings."""
    settings = _object(values, "settings")
    _reject_unknown(
        settings,
        {"schema_version", "llm", "library", "generation"},
        "settings",
    )
    version = settings.get("schema_version")
    if type(version) is not int or version != 2:
        raise ValueError("unsupported settings schema_version")

    # The legacy 'llm' block (models/keys) is tolerated but discarded.
    _object(settings.get("llm", {}), "settings 'llm'")

    return _validate_library_and_generation(
        settings,
        extra_generation_fields=frozenset(
            {"candidate_count", "privacy_ack_version", "privacy_ack_at"}
        ),
    )


def _validate_library(values: object) -> dict:
    library = _object(values, "settings 'library'")
    _reject_unknown(library, {"current_root", "roots"}, "library settings")
    current_root = _canonical_library_root(library.get("current_root"))
    roots = library.get("roots", [])
    if not isinstance(roots, list):
        raise ValueError("settings 'library.roots' must be a JSON array")
    normalized_roots: list[str] = []
    for root in roots:
        canonical = _canonical_library_root(root)
        if canonical is None:
            raise ValueError("settings 'library.roots' entries must be absolute paths")
        if canonical not in normalized_roots:
            normalized_roots.append(canonical)
    return {"current_root": current_root, "roots": normalized_roots}


def _validate_v3_settings(values: object) -> dict:
    """Accept the former v3 shape (ai ignored) and return v7-shaped settings."""

    settings = _object(values, "settings")
    _reject_unknown(
        settings,
        {"schema_version", "ai", "library", "generation"},
        "settings",
    )
    if settings.get("schema_version") != 3:
        raise ValueError("unsupported settings schema_version")

    # The legacy 'ai' block is tolerated but discarded.
    _object(settings.get("ai", {}), "settings 'ai'")

    return _validate_library_and_generation(settings)


def _validate_v4_settings(values: object) -> dict:
    """Accept the former v4 shape (ai ignored) and return v7-shaped settings."""

    settings = _object(values, "settings")
    _reject_unknown(
        settings,
        {"schema_version", "ai", "library", "generation"},
        "settings",
    )
    if settings.get("schema_version") != 4:
        raise ValueError("unsupported settings schema_version")

    # The legacy 'ai' block is tolerated but discarded.
    _object(settings.get("ai", {}), "settings 'ai'")

    return _validate_library_and_generation(settings)


def _validate_v5_settings(values: object) -> dict:
    """Accept the former v5 shape (ai ignored) and return v7-shaped settings."""

    settings = _object(values, "settings")
    _reject_unknown(
        settings,
        {"schema_version", "ai", "library", "generation"},
        "settings",
    )
    if settings.get("schema_version") != 5:
        raise ValueError("unsupported settings schema_version")

    # The legacy 'ai' block is tolerated but discarded.
    _object(settings.get("ai", {}), "settings 'ai'")

    return _validate_library_and_generation(settings)


def _validate_v6_settings(values: object) -> dict:
    """Accept the former v6 shape (ai ignored) and return v7-shaped settings."""

    settings = _object(values, "settings")
    _reject_unknown(
        settings,
        {"schema_version", "ai", "library", "generation"},
        "settings",
    )
    if settings.get("schema_version") != 6:
        raise ValueError("unsupported settings schema_version")

    # The legacy 'ai' block is tolerated but discarded.
    _object(settings.get("ai", {}), "settings 'ai'")

    return _validate_library_and_generation(settings)


def _validate_settings(values: object) -> dict:
    """Strict-validate and normalize schema v7 settings.

    A persisted `ai` key from a version of the app that still had AI features
    is tolerated on load (not rejected) and silently dropped: it is never
    validated, never carried into the result, and will not be written back
    out on the next save.
    """

    settings = _object(values, "settings")
    _reject_unknown(
        settings,
        {"schema_version", "ai", "library", "generation"},
        "settings",
    )
    if settings.get("schema_version") != SETTINGS_SCHEMA_VERSION:
        raise ValueError("unsupported settings schema_version")

    return _validate_library_and_generation(settings)


def _decode_settings(values: object) -> tuple[dict, bool]:
    """Return ``(normalized_v7, migration_required)``."""

    if isinstance(values, dict):
        version = values.get("schema_version")
        if version == SETTINGS_SCHEMA_VERSION:
            return _validate_settings(values), False
        legacy_validators = {
            6: _validate_v6_settings,
            5: _validate_v5_settings,
            4: _validate_v4_settings,
            3: _validate_v3_settings,
            2: _validate_v2_settings,
        }
        if version in legacy_validators:
            try:
                return legacy_validators[version](values), True
            except ValueError:
                raise SettingsMigrationValidationError() from None
        if type(version) is int and version > SETTINGS_SCHEMA_VERSION:
            raise SettingsSchemaUnsupportedError()
        if "schema_version" in values and version != 1:
            raise ValueError("unsupported settings schema_version")
    try:
        return _validate_legacy_settings(values), True
    except ValueError:
        raise SettingsMigrationValidationError() from None


def _quarantine_settings(path: Path) -> None:
    """Rename an unreadable settings file aside so the app can start fresh."""
    with contextlib.suppress(OSError):
        replace_file(path, path.with_name(path.name + ".bad"))


def _read_settings_file(path: Path) -> tuple[dict, bool] | None:
    raw = _read_json(path)
    if raw is None:
        return None
    return _decode_settings(raw)


def _write_settings_file(path: Path, settings: dict) -> None:
    _atomic_write_json(path, settings)
    if os.name != "nt":
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)


def _migrate_legacy_settings(path: Path, settings: dict) -> tuple[dict, str | None]:
    """Persist the freshly migrated settings under the settings lock."""

    try:
        _write_settings_file(path, settings)
    except OSError:
        return settings, SettingsMigrationWriteError.code
    return settings, None


def load_settings_with_status() -> tuple[dict, str | None]:
    """Return schema v7 settings and a pathless migration-retry reason."""

    path = settings_path()
    try:
        loaded = _read_settings_file(path)
    except SettingsMigrationValidationError:
        return _default_settings(), SettingsMigrationValidationError.code
    except SettingsSchemaUnsupportedError:
        return _default_settings(), SettingsSchemaUnsupportedError.code
    except OSError:
        return _default_settings(), SettingsUnavailableError.code
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        _quarantine_settings(path)
        return _default_settings(), None
    if loaded is None:
        return _default_settings(), None
    normalized, migration_required = loaded
    if not migration_required:
        return normalized, None

    # Re-read under the lock so a concurrent migration or update wins.
    try:
        with _settings_lock():
            try:
                current = _read_settings_file(path)
            except SettingsMigrationValidationError:
                return _default_settings(), SettingsMigrationValidationError.code
            except SettingsSchemaUnsupportedError:
                return _default_settings(), SettingsSchemaUnsupportedError.code
            except OSError:
                return _default_settings(), SettingsUnavailableError.code
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                _quarantine_settings(path)
                return _default_settings(), None
            if current is None:
                return _default_settings(), None
            normalized, migration_required = current
            if not migration_required:
                return normalized, None
            return _migrate_legacy_settings(path, normalized)
    except OSError:
        return normalized, SettingsMigrationWriteError.code


def load_settings() -> dict:
    """Load schema v7 settings, retrying safe migrations."""

    return load_settings_with_status()[0]


def _settings_for_update(path: Path) -> dict:
    try:
        loaded = _read_settings_file(path)
    except SettingsMigrationValidationError:
        raise
    except SettingsSchemaUnsupportedError:
        raise
    except OSError:
        raise SettingsUnavailableError() from None
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        _quarantine_settings(path)
        return _default_settings()
    if loaded is None:
        return _default_settings()
    normalized, migration_required = loaded
    if migration_required:
        normalized, reason = _migrate_legacy_settings(path, normalized)
        if reason == SettingsMigrationWriteError.code:
            raise SettingsMigrationWriteError()
        if reason is not None:
            raise SettingsUnavailableError()
    return normalized


def discard_legacy_api_credential(values: object) -> dict:
    """Force a settings rewrite to repair a stuck legacy-format file after confirmation."""

    body = _object(values, "legacy settings repair")
    _reject_unknown(body, {"confirm"}, "legacy settings repair")
    if set(body) != {"confirm"} or body["confirm"] is not True:
        raise ValueError("Discarding the legacy settings requires confirmation.")

    path = settings_path()
    try:
        with _settings_lock():
            loaded = _read_settings_file(path)
            if loaded is None:
                raise ValueError("There are no legacy settings to repair.")
            normalized, migration_required = loaded
            if not migration_required:
                raise ValueError("Legacy settings do not need repair.")
            normalized = _validate_settings(normalized)
            _write_settings_file(path, normalized)
            return normalized
    except (SettingsSchemaUnsupportedError, ValueError):
        raise
    except OSError:
        raise SettingsMigrationWriteError() from None


def _mutate_settings(mutator) -> dict:
    path = settings_path()
    with _settings_lock():
        settings = _settings_for_update(path)
        mutator(settings)
        normalized = _validate_settings(settings)
        _write_settings_file(path, normalized)
    return normalized


def save_settings(values: dict) -> dict:
    """Persist a strict v7 settings payload."""

    normalized = _validate_settings(values)
    path = settings_path()
    with _settings_lock():
        _settings_for_update(path)
        _write_settings_file(path, normalized)
    return normalized


def update_generation_settings(values: object) -> dict:
    body = _object(values, "generation settings")
    _reject_unknown(body, {"loop_mode"}, "generation settings")
    if set(body) != {"loop_mode"} or body["loop_mode"] not in LOOP_MODES:
        raise ValueError("loop_mode must be smooth, none, or ping_pong")

    def mutate(settings: dict) -> None:
        settings["generation"]["loop_mode"] = body["loop_mode"]

    return _mutate_settings(mutate)


def update_preferences(values: object) -> dict:
    """Temporary loop-mode bridge for the legacy Settings route."""

    body = _object(values, "preference settings")
    _reject_unknown(body, {"loop_mode"}, "preference settings")
    if set(body) != {"loop_mode"} or body["loop_mode"] not in LOOP_MODES:
        raise ValueError("loop_mode must be smooth, none, or ping_pong")

    def mutate(settings: dict) -> None:
        settings["generation"]["loop_mode"] = body["loop_mode"]

    return _mutate_settings(mutate)


def update_library_root(values: object) -> dict:
    """Change the root for future jobs while retaining canonical old roots."""
    body = _object(values, "library settings")
    _reject_unknown(body, {"current_root"}, "library settings")
    if set(body) != {"current_root"}:
        raise ValueError("library settings require current_root")
    new_root = _canonical_library_root(body["current_root"])

    def mutate(settings: dict) -> None:
        library = settings["library"]
        previous = library["current_root"]
        if previous == new_root:
            return
        if previous is not None and previous not in library["roots"]:
            library["roots"].append(previous)
        library["current_root"] = new_root

    return _mutate_settings(mutate)


def _check(cond: bool, msg: str) -> None:
    """Self-test guard. Explicit raise (not `assert`) so `-O` can't strip it."""
    if not cond:
        raise RuntimeError(f"am-configurator store self-test failed: {msg}")


def _selftest() -> int:
    """Round-trip the store in an isolated temp dir; verify the ladder + persistence."""
    import shutil

    saved = {k: os.environ.get(k)
             for k in ("AM_CONFIGURATOR_DATA_DIR", "XDG_DATA_HOME", "AM_CONFIGURATOR_HISTORY_MAX")}
    tmp = Path(tempfile.mkdtemp(prefix="am_configurator_store_"))
    try:
        # --- ladder: env override wins ---
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = str(tmp / "envroot")
        _check(store_root() == tmp / "envroot", "AM_CONFIGURATOR_DATA_DIR should win")

        # --- ladder: XDG when no explicit override ---
        os.environ.pop("AM_CONFIGURATOR_DATA_DIR", None)
        os.environ["XDG_DATA_HOME"] = str(tmp / "xdg")
        _check(store_root() == tmp / "xdg" / APP, "XDG_DATA_HOME/<app> should be used")

        # --- ladder: home default when neither is set ---
        os.environ.pop("XDG_DATA_HOME", None)
        _check(store_root() == Path.home() / ".local" / "share" / APP, "home default")

        # --- round-trip current + meta under an env root ---
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = str(tmp / "root")
        pid = "CB04"
        _check(load_current(pid) is None, "no current before first write")
        ir = {"page_num": 8, "key_layer": {"layer_num": 7}, "marker": "ピカチュウ"}
        path = save_current(pid, ir, version="AM_CB040.N40.R1.01.50")
        _check(path == (tmp / "root" / "devices" / "CB04" / "current.json"), "current path")
        _check(load_current(pid) == ir, "current round-trips byte-for-byte")
        meta = load_meta(pid)
        _check(bool(meta) and meta["product_id"] == "CB04", "meta records product_id")
        _check(meta["version"] == "AM_CB040.N40.R1.01.50", "meta records version")
        _check("last_seen" in meta, "meta records last_seen")

        # --- record_seen updates meta only, leaves current intact ---
        record_seen(pid, version="AM_CB040.N40.R1.01.51")
        _check(load_current(pid) == ir, "record_seen must not touch current.json")
        _check(load_meta(pid)["version"] == "AM_CB040.N40.R1.01.51", "record_seen bumps version")

        # --- snapshots accumulate, newest first, and prune to the cap ---
        _check(list_history(pid) == [], "no history before first snapshot")
        os.environ["AM_CONFIGURATOR_HISTORY_MAX"] = "3"
        snaps = [snapshot(pid, {"n": i}) for i in range(5)]
        _check(len(set(snaps)) == 5, "each snapshot gets a distinct filename")
        kept = list_history(pid)
        _check(len(kept) == 3, f"prune keeps the cap of 3, got {len(kept)}")
        _check([_read_json(p)["n"] for p in kept] == [4, 3, 2], "newest-first, oldest pruned")

        # --- path traversal is rejected ---
        for bad in ("../evil", "a/b", "", "CB 04"):
            try:
                device_dir(bad)
            except ValueError:
                continue
            raise RuntimeError(f"am-configurator store self-test failed: unsafe key {bad!r} accepted")

        print("am-configurator store self-test: OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                    help="run the round-trip self-test in a temp dir and exit")
    sub = ap.add_subparsers(dest="cmd")
    p_path = sub.add_parser("path", help="print the resolved store root / device dir")
    p_path.add_argument("--device", metavar="PRODUCT_ID",
                        help="show this device's dir instead of the root (e.g. CB04)")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if args.cmd == "path":
        if not args.device:
            print(store_root())
            return 0
        try:
            print(device_dir(args.device))
        except ValueError as e:
            print(f"am-configurator store: {e}", file=sys.stderr)
            return 2
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
