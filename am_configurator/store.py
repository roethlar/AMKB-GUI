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
from datetime import datetime, timezone
from pathlib import Path

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
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict | None:
    """Parsed JSON object, or None if the file is absent."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
# App-scoped configuration in one settings.json under the store root. Keys are
# stored in plaintext (0600 where the OS supports it), disclosed as such in the
# UI; an XAI_API_KEY environment override is honoured without ever being written
# to disk. The v2 write contract is strict and each UI section mutates only its
# own fields, so a model or library change can never erase a key.

KEY_MASK = "•" * 8  # UI display mask; never a legal stored key value
SETTINGS_SCHEMA_VERSION = 2
LOOP_MODES = ("smooth", "none", "ping_pong")
MIN_CANDIDATE_COUNT = 1
MAX_CANDIDATE_COUNT = 8
_LEGACY_INTERPRETERS = ("grok",)
_LEGACY_RENDERERS = ("grok",)
# Kept until the superseded provider-registry generator is removed in Task 16.
_KNOWN_INTERPRETERS = _LEGACY_INTERPRETERS
_KNOWN_RENDERERS = _LEGACY_RENDERERS
_KNOWN_KEY_PROVIDERS = ("xai",)


def _default_settings() -> dict:
    """A fresh copy of the default app settings (no key configured)."""
    from . import ai_catalog

    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "llm": {"models": dict(ai_catalog.DEFAULT_MODELS), "keys": {}},
        "library": {"current_root": None, "roots": []},
        "generation": {
            "candidate_count": 4,
            "loop_mode": "smooth",
            "privacy_ack_version": None,
            "privacy_ack_at": None,
        },
    }


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


def _validate_keys(values: object) -> dict[str, str]:
    keys = _object(values, "settings 'llm.keys'")
    normalized: dict[str, str] = {}
    for name, value in keys.items():
        if name not in _KNOWN_KEY_PROVIDERS:
            raise ValueError(f"unknown API key provider {name!r}")
        if not isinstance(value, str):
            # Deliberately omit the value from the message (it may be a secret).
            raise ValueError(f"API key for {name!r} must be a string")
        if value == KEY_MASK:
            raise ValueError(f"API key for {name!r} is the display mask, not a real key")
        if value:
            normalized[name] = value
    return normalized


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
    """Validate the unversioned v1 shape and return normalized v2 settings."""
    settings = _object(values, "settings")
    unknown_top = set(settings) - {"schema_version", "llm"}
    if unknown_top:
        raise ValueError(f"unknown settings field(s): {sorted(unknown_top)}")
    if "schema_version" in settings:
        version = settings["schema_version"]
        if type(version) is not int or version != 1:
            raise ValueError("unsupported settings schema_version")

    llm = _object(settings.get("llm", {}), "settings 'llm'")
    unknown_llm = set(llm) - {"interpreter", "renderer", "keys"}
    if unknown_llm:
        raise ValueError(f"unknown llm settings field(s): {sorted(unknown_llm)}")

    result = _default_settings()
    if "interpreter" in llm:
        interpreter = llm["interpreter"]
        if interpreter not in _LEGACY_INTERPRETERS:
            raise ValueError("unknown interpreter provider")
    if "renderer" in llm:
        renderer = llm["renderer"]
        if renderer not in _LEGACY_RENDERERS:
            raise ValueError("unknown renderer provider")
    result["llm"]["keys"] = _validate_keys(llm.get("keys", {}))
    return result


def _validate_settings(values: object) -> dict:
    """Strict-validate and normalize a v2 settings object."""
    from . import ai_catalog

    settings = _object(values, "settings")
    _reject_unknown(
        settings,
        {"schema_version", "llm", "library", "generation"},
        "settings",
    )
    version = settings.get("schema_version")
    if type(version) is not int or version != SETTINGS_SCHEMA_VERSION:
        raise ValueError("unsupported settings schema_version")
    result = _default_settings()

    llm = _object(settings.get("llm", {}), "settings 'llm'")
    _reject_unknown(llm, {"models", "keys"}, "llm settings")
    models = _object(llm.get("models", {}), "settings 'llm.models'")
    _reject_unknown(models, set(ai_catalog.MODEL_IDS), "llm model")
    for role, model_id in models.items():
        result["llm"]["models"][role] = ai_catalog.validate_model(role, model_id)
    result["llm"]["keys"] = _validate_keys(llm.get("keys", {}))

    library = _object(settings.get("library", {}), "settings 'library'")
    _reject_unknown(library, {"current_root", "roots"}, "library settings")
    result["library"]["current_root"] = _canonical_library_root(
        library.get("current_root")
    )
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
    result["library"]["roots"] = normalized_roots

    generation = _object(settings.get("generation", {}), "settings 'generation'")
    _reject_unknown(
        generation,
        {"candidate_count", "loop_mode", "privacy_ack_version", "privacy_ack_at"},
        "generation settings",
    )
    candidate_count = generation.get("candidate_count", 4)
    if (
        type(candidate_count) is not int
        or not MIN_CANDIDATE_COUNT <= candidate_count <= MAX_CANDIDATE_COUNT
    ):
        raise ValueError("candidate_count must be an integer from 1 through 8")
    loop_mode = generation.get("loop_mode", "smooth")
    if loop_mode not in LOOP_MODES:
        raise ValueError("loop_mode must be smooth, none, or ping_pong")
    ack_version = generation.get("privacy_ack_version")
    ack_at = generation.get("privacy_ack_at")
    if ack_version is not None and (not isinstance(ack_version, str) or not ack_version):
        raise ValueError("privacy_ack_version must be a non-empty string or null")
    if ack_at is not None and (not isinstance(ack_at, str) or not ack_at):
        raise ValueError("privacy_ack_at must be a non-empty string or null")
    if (ack_version is None) != (ack_at is None):
        raise ValueError("privacy acknowledgment version and timestamp must be set together")
    result["generation"].update({
        "candidate_count": candidate_count,
        "loop_mode": loop_mode,
        "privacy_ack_version": ack_version,
        "privacy_ack_at": ack_at,
    })
    return result


def _decode_settings(values: object) -> tuple[dict, bool]:
    """Return ``(normalized_v2, migrated_from_v1)``."""
    if isinstance(values, dict) and values.get("schema_version") == SETTINGS_SCHEMA_VERSION:
        return _validate_settings(values), False
    if isinstance(values, dict) and "schema_version" in values:
        version = values.get("schema_version")
        if type(version) is not int or version != 1:
            raise ValueError("unsupported settings schema_version")
    return _validate_legacy_settings(values), True


def _quarantine_settings(path: Path) -> None:
    """Rename an unreadable settings file aside so the app can start fresh."""
    with contextlib.suppress(OSError):
        os.replace(path, path.with_name(path.name + ".bad"))


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


def load_settings() -> dict:
    """App settings, recovering to defaults on a missing/corrupt/invalid file.

    A missing file yields the defaults without writing anything. A file that is
    invalid JSON or structurally invalid is quarantined to ``settings.json.bad``
    and the defaults are returned — a bad settings file is never a hard error.
    """
    path = settings_path()
    try:
        loaded = _read_settings_file(path)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        _quarantine_settings(path)
        return _default_settings()
    except ValueError:
        _quarantine_settings(path)
        return _default_settings()
    if loaded is None:
        return _default_settings()
    normalized, migrated = loaded
    if not migrated:
        return normalized

    # Re-read under the lock before migrating so a concurrent valid write is
    # never overwritten by a stale v1 snapshot.
    with _settings_lock():
        try:
            current = _read_settings_file(path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
            _quarantine_settings(path)
            return _default_settings()
        if current is None:
            return _default_settings()
        normalized, migrated = current
        if migrated:
            _write_settings_file(path, normalized)
        return normalized


def _settings_for_update(path: Path) -> dict:
    try:
        loaded = _read_settings_file(path)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
        _quarantine_settings(path)
        return _default_settings()
    return _default_settings() if loaded is None else loaded[0]


def _mutate_settings(mutator) -> dict:
    path = settings_path()
    with _settings_lock():
        settings = _settings_for_update(path)
        mutator(settings)
        normalized = _validate_settings(settings)
        _write_settings_file(path, normalized)
    return normalized


def save_settings(values: dict) -> dict:
    """Persist v2 settings, or merge the legacy UI's v1 key-only payload.

    The temporary v1 compatibility form validates ``grok`` provider aliases and
    updates only stored keys, preserving all v2 preferences. Task 11 removes
    the unchanged UI's reliance on this form.
    """
    path = settings_path()
    if isinstance(values, dict) and values.get("schema_version") == SETTINGS_SCHEMA_VERSION:
        normalized = _validate_settings(values)
        with _settings_lock():
            _write_settings_file(path, normalized)
        return normalized

    legacy = _validate_legacy_settings(values)
    with _settings_lock():
        normalized = _settings_for_update(path)
        normalized["llm"]["keys"] = legacy["llm"]["keys"]
        normalized = _validate_settings(normalized)
        _write_settings_file(path, normalized)
    return normalized


def update_api_key(values: object) -> dict:
    """Set or clear one provider key without changing any preferences."""
    body = _object(values, "API key settings")
    _reject_unknown(body, {"provider", "key"}, "API key settings")
    if set(body) != {"provider", "key"}:
        raise ValueError("API key settings require provider and key")
    provider = body["provider"]
    if provider not in _KNOWN_KEY_PROVIDERS:
        raise ValueError("unknown API key provider")
    normalized = _validate_keys({provider: body["key"]})

    def mutate(settings: dict) -> None:
        if provider in normalized:
            settings["llm"]["keys"][provider] = normalized[provider]
        else:
            settings["llm"]["keys"].pop(provider, None)

    return _mutate_settings(mutate)


def update_preferences(values: object) -> dict:
    """Update curated models and generation defaults without touching keys."""
    from . import ai_catalog

    body = _object(values, "preference settings")
    _reject_unknown(body, {"models", "candidate_count", "loop_mode"}, "preference settings")
    if not body:
        raise ValueError("preference settings must include a value")
    updates: dict[str, object] = {}
    if "models" in body:
        models = _object(body["models"], "preference models")
        _reject_unknown(models, set(ai_catalog.MODEL_IDS), "model preference")
        if not models:
            raise ValueError("preference models must include a model")
        updates["models"] = {
            role: ai_catalog.validate_model(role, model_id)
            for role, model_id in models.items()
        }
    if "candidate_count" in body:
        count = body["candidate_count"]
        if type(count) is not int or not MIN_CANDIDATE_COUNT <= count <= MAX_CANDIDATE_COUNT:
            raise ValueError("candidate_count must be an integer from 1 through 8")
        updates["candidate_count"] = count
    if "loop_mode" in body:
        loop_mode = body["loop_mode"]
        if loop_mode not in LOOP_MODES:
            raise ValueError("loop_mode must be smooth, none, or ping_pong")
        updates["loop_mode"] = loop_mode

    def mutate(settings: dict) -> None:
        settings["llm"]["models"].update(updates.get("models", {}))
        if "candidate_count" in updates:
            settings["generation"]["candidate_count"] = updates["candidate_count"]
        if "loop_mode" in updates:
            settings["generation"]["loop_mode"] = updates["loop_mode"]

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


def acknowledge_privacy(values: object) -> dict:
    """Record explicit acknowledgment of only the current data-flow disclosure."""
    from . import ai_catalog

    body = _object(values, "privacy settings")
    _reject_unknown(body, {"version"}, "privacy settings")
    if set(body) != {"version"}:
        raise ValueError("privacy settings require version")
    if body["version"] != ai_catalog.PRIVACY_DISCLOSURE_VERSION:
        raise ValueError("only the current privacy disclosure can be acknowledged")

    def mutate(settings: dict) -> None:
        settings["generation"]["privacy_ack_version"] = ai_catalog.PRIVACY_DISCLOSURE_VERSION
        settings["generation"]["privacy_ack_at"] = _now_iso()

    return _mutate_settings(mutate)


def resolve_xai_key() -> str | None:
    """The xAI API key: the ``XAI_API_KEY`` env override wins, else the stored key.

    The environment override is never written to disk.
    """
    env = os.environ.get("XAI_API_KEY")
    if env:
        return env
    key = load_settings()["llm"]["keys"].get("xai")
    return key or None


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
