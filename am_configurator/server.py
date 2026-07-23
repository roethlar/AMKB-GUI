"""Local, dependency-free browser GUI for Angry Miao keyboard configuration."""
from __future__ import annotations

import copy
import base64
import binascii
import hashlib
import io
import json
import math
import mimetypes
import secrets
import threading
import time
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__, device_mapping


_PKG = Path(__file__).resolve().parent
_ASSETS = _PKG / "web"
_STATIC = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/lighting_review.js": "lighting_review.js",
    "/lighting_state.js": "lighting_state.js",
    "/lighting_targets.js": "lighting_targets.js",
    "/icon.png": "icon.png",
    "/style.css": "style.css",
}
_KEY_FIELDS = (
    "key_layer", "tab_key", "tab_key_num", "macro_key", "MACRO_key",
    "MACRO_key_num", "Fn_key", "Fn_key_num", "swap_key", "swap_key_num",
    "exchange_key", "exchange_num",
)
_MAX_GIF_BYTES = 12_000_000
_KEYMAP_VERIFY_ATTEMPTS = 4
_KEYMAP_VERIFY_RETRY_SECONDS = 1.0
_MACRO_EVENTS_PER_BLOCK = 8
_CYBERBOARD_MACRO_READBACK_BLOCKS = 15

_MAX_ASSET_RANGE_BYTES = 8 * 1024 * 1024
_LIGHTING_ASSET_MIMES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "video/mp4",
        "application/json",
    }
)
# ProviderError.code -> local HTTP status (design §Typed errors).
_PROVIDER_ERROR_HTTP: dict[str, HTTPStatus] = {
    "config": HTTPStatus.BAD_REQUEST,
    "auth": HTTPStatus.BAD_REQUEST,
    "rate_limited": HTTPStatus.TOO_MANY_REQUESTS,
    "timeout": HTTPStatus.GATEWAY_TIMEOUT,
    "offline": HTTPStatus.SERVICE_UNAVAILABLE,
    "moderation": HTTPStatus.BAD_REQUEST,
    "bad_response": HTTPStatus.BAD_GATEWAY,
    "unavailable": HTTPStatus.BAD_GATEWAY,
}

_TEXT_KEY_USAGES: dict[str, tuple[int, bool]] = {
    "\n": (0x28, False), "\t": (0x2B, False), " ": (0x2C, False),
    "-": (0x2D, False), "_": (0x2D, True), "=": (0x2E, False), "+": (0x2E, True),
    "[": (0x2F, False), "{": (0x2F, True), "]": (0x30, False), "}": (0x30, True),
    "\\": (0x31, False), "|": (0x31, True), ";": (0x33, False), ":": (0x33, True),
    "'": (0x34, False), '"': (0x34, True), "`": (0x35, False), "~": (0x35, True),
    ",": (0x36, False), "<": (0x36, True), ".": (0x37, False), ">": (0x37, True),
    "/": (0x38, False), "?": (0x38, True),
}
for _offset, _character in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _TEXT_KEY_USAGES[_character] = (0x04 + _offset, False)
    _TEXT_KEY_USAGES[_character.upper()] = (0x04 + _offset, True)
for _offset, (_plain, _shifted) in enumerate(zip("1234567890", "!@#$%^&*()")):
    _TEXT_KEY_USAGES[_plain] = (0x1E + _offset, False)
    _TEXT_KEY_USAGES[_shifted] = (0x1E + _offset, True)


class AcceptedWriteError(RuntimeError):
    """The device ACKed the full write, but a later verification step failed."""

def merge_configs(configs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Merge official LED and ``*-KEY.json`` exports without losing either half."""
    if not configs:
        return None
    led_sources = [c for c in configs if c.get("page_data")]
    key_only = [
        c for c in configs
        if c.get("key_layer") and not c.get("page_data")
    ]
    key_sources = key_only or [c for c in configs if c.get("key_layer")]
    base = copy.deepcopy((led_sources or key_sources or configs)[-1])

    # Preserve arbitrary product-specific fields from every file.  Known LED
    # and key sections are overlaid authoritatively below.
    for config in configs:
        for key, value in config.items():
            if key not in base:
                base[key] = copy.deepcopy(value)
    if led_sources:
        led = led_sources[-1]
        base["page_data"] = copy.deepcopy(led.get("page_data", []))
        base["page_num"] = int(led.get("page_num", len(base["page_data"])))
    if key_sources:
        key_config = key_sources[-1]
        for key in _KEY_FIELDS:
            if key in key_config:
                base[key] = copy.deepcopy(key_config[key])
        if "product_info" in key_config:
            base["product_info"] = copy.deepcopy(key_config["product_info"])
    return base


def blank_config(
    device_id: str,
    layers: list[list[str]],
    macros: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a writable, all-local profile when no AM JSON was opened first."""
    upper = device_id.upper()
    product_id = "80" if upper == "AM21" else upper
    relic = product_id == "80"

    pages: list[dict[str, Any]] = []
    for index in range(8):
        custom = index >= 5
        page: dict[str, Any] = {
            "valid": 1 if index < 3 or custom else 0,
            "page_index": index,
            "lightness": 100,
            "speed_ms": 90 if custom else 50,
            "color": {
                "default": False,
                "back_rgb": "#000000",
                "rgb": "#FFFFFF" if index == 2 else "#000000",
            },
            "word_page": {"valid": 0, "word_len": 0, "unicode": []},
            "frames": {"valid": 1 if custom else 0, "frame_num": 0, "frame_data": []},
            "keyframes": {
                "valid": 1 if custom else 0,
                "frame_num": 1 if custom else 0,
                "frame_data": (
                    [{"frame_index": 0, "frame_RGB": ["#000000"] * 90}]
                    if custom else []
                ),
            },
        }
        if relic and custom:
            page["spotlight_frames"] = {
                "valid": 1,
                "frame_num": 1,
                "frame_data": [
                    {"frame_index": 0, "frame_RGB": ["#000000"] * 24}
                ],
            }
        pages.append(page)

    return {
        "product_info": {
            "product_info_addr": "product_info_addr",
            "product_id": product_id,
        },
        "page_num": len(pages),
        "page_data": pages,
        "tab_key": [],
        "tab_key_num": 0,
        "macro_key": copy.deepcopy(macros),
        "MACRO_key": [],
        "MACRO_key_num": 0,
        "exchange_key": [],
        "exchange_num": 0,
        "swap_key": [],
        "swap_key_num": 0,
        "Fn_key": [],
        "Fn_key_num": 0,
        "key_layer": {
            "valid": 1,
            "layer_num": len(layers),
            "layer_data": [{"layer": list(layer)} for layer in layers],
        },
    }


def gif_to_led_tracks(
    payload: bytes,
    targets: list[str] | tuple[str, ...],
    resample: str = "box",
    product_id: str = "CB_XX",
) -> dict[str, Any]:
    """Decode a GIF once and map each frame onto one or more LED tracks."""
    _model, requested = device_mapping.validate_gif_targets(product_id, targets)
    if resample not in {"nearest", "box", "lanczos"}:
        raise ValueError("GIF resampling must be nearest, box, or lanczos.")
    if not payload or len(payload) > _MAX_GIF_BYTES:
        raise ValueError("GIF must be between 1 byte and 12 MB.")
    try:
        from PIL import Image, UnidentifiedImageError
    except ModuleNotFoundError as exc:
        raise ValueError(
            "GIF import needs Pillow. Reinstall AM Configurator."
        ) from exc

    try:
        with Image.open(io.BytesIO(payload)) as image:
            if image.format != "GIF":
                raise ValueError("The selected file is not a GIF.")
            source_frames = int(getattr(image, "n_frames", 1))
            frame_count = min(source_frames, device_mapping.MAX_FRAMES)
            images: list[Image.Image] = []
            durations: list[int] = []
            for index in range(frame_count):
                image.seek(index)
                durations.append(int(image.info.get("duration") or 90))
                images.append(image.convert("RGBA"))
    except UnidentifiedImageError as exc:
        raise ValueError("The selected file is not a readable GIF.") from exc
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"Could not decode GIF: {exc}") from exc

    result = device_mapping.frames_to_led_tracks(
        images,
        durations,
        requested,
        resample,
        product_id,
    )
    result["source_frames"] = source_frames
    result["decoded_frames"] = frame_count
    return result


def gif_to_led_frames(
    payload: bytes,
    target: str,
    resample: str = "box",
    product_id: str = "CB_XX",
) -> dict[str, Any]:
    """Decode and resize a GIF into one firmware-ready RGB track."""
    result = gif_to_led_tracks(payload, [target], resample, product_id)
    return {
        **result["tracks"][target],
        "source_frames": result["source_frames"],
        "decoded_frames": result["decoded_frames"],
        "duration_ms": result["duration_ms"],
        "source_duration_ms": result["source_duration_ms"],
        "timing_resampled": result["timing_resampled"],
        "model": result["model"],
    }


def _hex_color(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def _key_code(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 9 or not value.startswith("#"):
        return False
    try:
        return len(bytes.fromhex(value[1:])) == 4
    except ValueError:
        return False


def extract_importable_macros(config: Any) -> list[dict[str, Any]]:
    """Copy only modern macro definitions from another AM configuration."""
    if not isinstance(config, dict):
        raise ValueError("The selected JSON is not a configuration object.")
    source = config.get("macro_key")
    if not isinstance(source, list) or not source:
        if config.get("MACRO_key"):
            raise ValueError(
                "This file contains only legacy MACRO_key entries. Choose the board's "
                "*-KEY.json export containing lowercase macro_key definitions."
            )
        raise ValueError("The selected JSON contains no importable macros.")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_events = 0
    for position, macro in enumerate(source, 1):
        if not isinstance(macro, dict):
            raise ValueError(f"Macro {position} is not an object.")
        token = str(macro.get("original_key") or "").upper()
        if not _key_code(token):
            raise ValueError(f"Macro {position} has an invalid token keycode.")
        raw_token = bytes.fromhex(token[1:])
        usage = int.from_bytes(raw_token[2:4], "big")
        if raw_token[:2] != b"\x00\x95" or not 0x1500 <= usage <= 0x151F:
            raise ValueError(f"Macro {position} does not use an M1–M32 token.")
        if token in seen:
            raise ValueError(f"The source defines {token} more than once.")
        seen.add(token)

        events = [str(code).upper() for code in (macro.get("layer_key") or [])]
        delays = list(macro.get("intvel_ms") or [])
        if not events:
            raise ValueError(f"Macro {position} has no key events.")
        if len(events) > 200 or total_events + len(events) > 200:
            raise ValueError("The imported macros exceed the 200-event device limit.")
        if any(not _key_code(code) for code in events):
            raise ValueError(f"Macro {position} contains an invalid event keycode.")
        # Angry Miao's recorder normally stores N-1 pauses for N events; the
        # final event has no following pause. The wire format still has a delay
        # field, so canonicalize that omitted tail to zero.
        if len(delays) < max(0, len(events) - 1):
            raise ValueError(f"Macro {position} is missing delays between key events.")
        normalized_delays = [int(value) for value in delays[:len(events)]]
        normalized_delays.extend(0 for _ in range(len(events) - len(normalized_delays)))
        if any(not 0 <= delay <= 65535 for delay in normalized_delays):
            raise ValueError(f"Macro {position} has a delay outside 0..65535ms.")
        total_events += len(events)
        result.append({
            "original_key": token,
            "layer_key": events,
            "intvel_ms": normalized_delays,
        })
    return result


def _product_family(value: Any) -> str:
    product = str(value or "").upper()
    if product in {"80", "AM21"}:
        return "80"
    if product == "ALICE":
        return "ALICE"
    if product.startswith("CB"):
        return "CB"
    return product


def config_transfer_options(config: Any, target_product_id: Any) -> dict[str, Any]:
    """Describe which parts of a profile can safely move to another board."""
    if not isinstance(config, dict):
        raise ValueError("The selected JSON is not a configuration object.")
    source_product_id = str(
        ((config.get("product_info") or {}).get("product_id") or "")
    )
    if not source_product_id:
        raise ValueError("The selected JSON has no product_info.product_id.")
    target = str(target_product_id or "")
    if not target:
        raise ValueError("The target keyboard has no product ID.")

    try:
        imported_macros = extract_importable_macros(config)
        macro_error = None
    except ValueError as exc:
        imported_macros = []
        macro_error = str(exc)

    compatible = _product_family(source_product_id) == _product_family(target)
    key_layers = ((config.get("key_layer") or {}).get("layer_data") or [])
    led_pages = config.get("page_data") or []
    return {
        "compatible": compatible,
        "source_product_id": source_product_id,
        "target_product_id": target,
        "can_import_macros": bool(imported_macros),
        "macro_count": len(imported_macros),
        "macro_error": macro_error,
        "can_merge_keymap": compatible and bool(key_layers),
        "can_merge_leds": compatible and bool(led_pages),
    }


def text_to_macro_events(text: Any, delay_ms: Any = 10) -> dict[str, Any]:
    """Compile US-layout text into deterministic macro key-down/up events."""
    if not isinstance(text, str) or not text:
        raise ValueError("Enter some text to convert.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    try:
        delay = int(delay_ms)
    except (TypeError, ValueError) as exc:
        raise ValueError("The inter-key delay must be a whole number.") from exc
    if not 1 <= delay <= 1000:
        raise ValueError("The inter-key delay must be between 1 and 1000ms.")

    events: list[str] = []
    delays: list[int] = []
    shift_down = False

    def emit(usage: int, down: bool, pause: int) -> None:
        events.append(f"#{0x11 if down else 0x10:02X}07{usage:04X}")
        delays.append(pause)

    for index, character in enumerate(text):
        mapping = _TEXT_KEY_USAGES.get(character)
        if mapping is None:
            raise ValueError(
                f"Character {character!r} at position {index + 1} is not available "
                "on the US keyboard layout."
            )
        usage, needs_shift = mapping
        if needs_shift != shift_down:
            emit(0xE1, needs_shift, 1)
            shift_down = needs_shift
        emit(usage, True, 1)
        emit(usage, False, delay)
    if shift_down:
        emit(0xE1, False, 1)
    if delays:
        delays[-1] = 0
    if len(events) > 200:
        raise ValueError(
            f"This text needs {len(events)} macro events; the complete profile limit is 200."
        )
    return {"layer_key": events, "intvel_ms": delays, "characters": len(text)}


def validate_config(config: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(config, dict):
        return {"ok": False, "errors": ["Configuration must be a JSON object."], "warnings": []}

    product = ((config.get("product_info") or {}).get("product_id"))
    if not isinstance(product, str) or not product:
        errors.append("product_info.product_id is missing.")

    key_layer = config.get("key_layer") or {}
    layers = key_layer.get("layer_data") or []
    if not layers:
        errors.append("key_layer.layer_data is missing.")
    for index, layer_data in enumerate(layers, 1):
        layer = layer_data.get("layer") if isinstance(layer_data, dict) else None
        if not isinstance(layer, list) or len(layer) != 200:
            errors.append(f"Layer {index} must contain exactly 200 keycodes.")
        elif any(not isinstance(code, str) or len(code) != 9 for code in layer):
            errors.append(f"Layer {index} contains a malformed keycode.")
    if key_layer.get("layer_num", len(layers)) != len(layers):
        errors.append("key_layer.layer_num does not match layer_data.")

    macros = config.get("macro_key") or []
    if len(macros) > 32:
        errors.append("macro_key contains more than 32 macros.")
    event_total = 0
    for index, macro in enumerate(macros, 1):
        events = macro.get("layer_key") or []
        delays = macro.get("intvel_ms") or []
        event_total += len(events)
        if not events:
            errors.append(f"Macro {index} has no events.")
        if len(events) > 200:
            errors.append(f"Macro {index} contains more than 200 events.")
        if len(delays) < max(0, len(events) - 1):
            errors.append(f"Macro {index} is missing delays between events.")
        if any(not isinstance(delay, int) or not 0 <= delay <= 65535 for delay in delays[:len(events)]):
            errors.append(f"Macro {index} has a delay outside 0..65535ms.")
    if event_total > 200:
        errors.append(f"Macros contain {event_total} events in total; the device limit is 200.")
    readable_layers = [
        item.get("layer", [])
        for item in layers
        if isinstance(item, dict) and isinstance(item.get("layer"), list)
    ]
    referenced_macros = _macro_references(readable_layers)
    defined_macros = {
        str(macro.get("original_key") or "").upper()
        for macro in macros
        if isinstance(macro, dict)
    }
    missing_macros = [code for code in referenced_macros if code not in defined_macros]
    if missing_macros:
        labels = ", ".join(f"M{int(code[-2:], 16) + 1}" for code in missing_macros)
        warnings.append(
            f"The keymap assigns {labels}, but their macro actions are missing; "
            "a device write cannot reconstruct them."
        )

    pages = config.get("page_data") or []
    led_frames = {"display": 0, "per_key": 0, "edge": 0}
    for page in pages:
        page_index = page.get("page_index", "?")
        for field, expected in (("frames", 200), ("keyframes", 90), ("spotlight_frames", 24)):
            track = page.get(field)
            if (
                field == "spotlight_frames"
                and track is not None
                and page_index not in (5, 6, 7)
            ):
                errors.append(
                    f"Page {page_index} spotlight_frames is only valid on "
                    "custom pages 5, 6, and 7."
                )
            if not track:
                continue
            data = track.get("frame_data") or []
            declared = int(track.get("frame_num", 0))
            led_frames[{"frames": "display", "keyframes": "per_key", "spotlight_frames": "edge"}[field]] += declared
            if declared != len(data):
                errors.append(f"Page {page_index} {field}.frame_num does not match frame_data.")
            for frame in data:
                colors = frame.get("frame_RGB")
                if not isinstance(colors, list) or len(colors) != expected:
                    errors.append(
                        f"Page {page_index} {field} frame {frame.get('frame_index', '?')} "
                        f"must contain {expected} colors."
                    )
                    break
                if any(not _hex_color(color) for color in colors):
                    errors.append(f"Page {page_index} {field} contains an invalid color.")
                    break
    if not pages:
        warnings.append("This is a key-only export; writing it will clear LED pages on the device.")

    frame_plan: dict[str, Any] | None = None
    if not errors:
        try:
            from . import writer

            plan = writer.plan(config)
            frame_plan = {"total": plan.total, "sections": dict(plan.sections)}
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"Wire encoder rejected the configuration: {exc}")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "product_id": product,
        "layers": len(layers),
        "macros": len(macros),
        "macro_events": event_total,
        "pages": len(pages),
        "led_frames": led_frames,
        "frame_plan": frame_plan,
    }


def _device_matches_config(device_id: str, config_id: str) -> bool:
    return _product_family(device_id) == _product_family(config_id)


def _stored_device_config(device_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return the last verified full config for a device, if it is still valid."""
    from . import store

    try:
        candidate = store.load_current(device_id)
        if candidate is None:
            return None, None
        checked = validate_config(candidate)
        config_id = str(checked.get("product_id") or "")
        if not checked["ok"] or not _device_matches_config(device_id, config_id):
            return None, "The saved last-known configuration was invalid and was ignored."
        return copy.deepcopy(candidate), None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, f"The saved last-known configuration could not be loaded: {exc}"


def _macro_references(key_layers: list[list[str]]) -> list[str]:
    """Return the modern macro tokens assigned anywhere in a keymap."""
    references: set[str] = set()
    for layer in key_layers:
        for code in layer:
            upper = code.upper() if isinstance(code, str) else ""
            if (
                len(upper) == 9
                and upper.startswith("#009515")
                and all(ch in "0123456789ABCDEF" for ch in upper[-2:])
                and int(upper[-2:], 16) <= 0x1F
            ):
                references.add(upper)
    return sorted(references)


def _padded_macro_delays(macro: dict[str, Any]) -> list[int]:
    """Canonical wire/read-back delays, including the optional zero tail."""
    event_count = len(macro.get("layer_key") or [])
    delays = [int(value) for value in (macro.get("intvel_ms") or [])[:event_count]]
    delays.extend(0 for _ in range(event_count - len(delays)))
    return delays


def _canonical_macros(values: Any) -> list[dict[str, Any]]:
    """Normalize macro JSON to the exact shape returned by the device."""
    result: list[dict[str, Any]] = []
    for macro in values or []:
        events = [str(code).upper() for code in (macro.get("layer_key") or [])]
        result.append({
            "original_key": str(macro.get("original_key") or "").upper(),
            "layer_key": events,
            "intvel_ms": _padded_macro_delays({**macro, "layer_key": events}),
        })
    return result


def _macro_block_count(values: list[dict[str, Any]]) -> int:
    return sum(
        math.ceil(len(macro.get("layer_key") or []) / _MACRO_EVENTS_PER_BLOCK)
        for macro in values
        if macro.get("layer_key")
    )


def _macro_prefix_for_blocks(
    values: list[dict[str, Any]], block_limit: int
) -> list[dict[str, Any]]:
    """Return the semantic macro prefix represented by the first N wire blocks."""
    remaining = max(0, block_limit)
    result: list[dict[str, Any]] = []
    for macro in _canonical_macros(values):
        events = macro["layer_key"]
        required = math.ceil(len(events) / _MACRO_EVENTS_PER_BLOCK) if events else 0
        used = min(required, remaining)
        event_count = min(len(events), used * _MACRO_EVENTS_PER_BLOCK)
        if event_count:
            result.append({
                "original_key": macro["original_key"],
                "layer_key": events[:event_count],
                "intvel_ms": macro["intvel_ms"][:event_count],
            })
        remaining -= used
        if used < required or remaining == 0:
            break
    return result


def _macro_mismatch_detail(
    expected: list[dict[str, Any]], actual: list[dict[str, Any]]
) -> str:
    expected_events = sum(len(macro["layer_key"]) for macro in expected)
    actual_events = sum(len(macro["layer_key"]) for macro in actual)
    summary = (
        f"expected {len(expected)} macros/{expected_events} events/"
        f"{_macro_block_count(expected)} blocks, read {len(actual)} macros/"
        f"{actual_events} events/{_macro_block_count(actual)} blocks"
    )
    for macro_index in range(max(len(expected), len(actual))):
        if macro_index >= len(expected):
            return f"{summary}; unexpected macro {macro_index + 1}"
        if macro_index >= len(actual):
            return f"{summary}; macro {macro_index + 1} was missing"
        want = expected[macro_index]
        got = actual[macro_index]
        if want["original_key"] != got["original_key"]:
            return f"{summary}; macro {macro_index + 1} token differed"
        for event_index in range(max(len(want["layer_key"]), len(got["layer_key"]))):
            if event_index >= len(want["layer_key"]):
                return f"{summary}; macro {macro_index + 1} had an extra event"
            if event_index >= len(got["layer_key"]):
                return f"{summary}; macro {macro_index + 1} event {event_index + 1} was missing"
            if want["layer_key"][event_index] != got["layer_key"][event_index]:
                return f"{summary}; macro {macro_index + 1} event {event_index + 1} differed"
            if want["intvel_ms"][event_index] != got["intvel_ms"][event_index]:
                return f"{summary}; macro {macro_index + 1} delay {event_index + 1} differed"
    return summary


def _classify_macro_readback(
    product_id: Any,
    expected_values: Any,
    actual_values: Any,
) -> dict[str, Any]:
    """Accept CyberBoard's observed 15-block ceiling only for an exact prefix."""
    expected = _canonical_macros(expected_values)
    actual = _canonical_macros(actual_values)
    expected_events = sum(len(macro["layer_key"]) for macro in expected)
    actual_events = sum(len(macro["layer_key"]) for macro in actual)
    if actual == expected:
        return {
            "status": "verified",
            "verified_events": actual_events,
            "expected_events": expected_events,
            "warning": None,
            "detail": None,
        }
    expected_blocks = _macro_block_count(expected)
    if (
        _product_family(product_id) == "CB"
        and expected_blocks > _CYBERBOARD_MACRO_READBACK_BLOCKS
        and actual
        == _macro_prefix_for_blocks(expected, _CYBERBOARD_MACRO_READBACK_BLOCKS)
    ):
        warning = (
            "CyberBoard returned its first 15 macro blocks: "
            f"{actual_events} of {expected_events} events matched exactly. "
            f"The remaining {expected_events - actual_events} events are not exposed "
            "by this firmware's macro read-back command."
        )
        return {
            "status": "partial",
            "verified_events": actual_events,
            "expected_events": expected_events,
            "warning": warning,
            "detail": None,
        }
    return {
        "status": "mismatch",
        "verified_events": actual_events,
        "expected_events": expected_events,
        "warning": None,
        "detail": _macro_mismatch_detail(expected, actual),
    }


def _reconcile_read_macros(
    product_id: Any,
    device_macros: Any,
    stored_config: Any,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Keep a complete local CyberBoard snapshot when its readable prefix matches."""
    read = _canonical_macros(device_macros)
    stored = (
        stored_config.get("macro_key")
        if isinstance(stored_config, dict)
        and isinstance(stored_config.get("macro_key"), list)
        else None
    )
    if stored is not None:
        verdict = _classify_macro_readback(product_id, stored, read)
        if verdict["status"] == "partial":
            warning = (
                f"{verdict['warning']} Restored the complete local snapshot instead "
                "of replacing it with truncated device data."
            )
            return copy.deepcopy(stored), warning, True
    if (
        _product_family(product_id) == "CB"
        and _macro_block_count(read) == _CYBERBOARD_MACRO_READBACK_BLOCKS
    ):
        return read, (
            "CyberBoard returned 15 macro blocks, its observed read-back ceiling. "
            "Without a matching complete local snapshot, later macro events may be "
            "unreadable; open a saved JSON to restore them."
        ), False
    return read, None, False


def _keymap_differences(
    expected: list[list[str]],
    actual: list[list[str]],
    *,
    example_limit: int = 6,
) -> tuple[int, list[str]]:
    """Count keymap differences and format a bounded set of useful coordinates."""
    count = 0
    examples: list[str] = []
    for layer_index in range(max(len(expected), len(actual))):
        want = expected[layer_index] if layer_index < len(expected) else []
        got = actual[layer_index] if layer_index < len(actual) else []
        for key_index in range(max(len(want), len(got))):
            expected_code = want[key_index] if key_index < len(want) else "<missing>"
            actual_code = got[key_index] if key_index < len(got) else "<missing>"
            if expected_code.upper() == actual_code.upper():
                continue
            count += 1
            if len(examples) < example_limit:
                examples.append(
                    f"layer {layer_index + 1} key {key_index}: "
                    f"expected {expected_code}, got {actual_code}"
                )
    return count, examples


def _verify_keymap_readback(
    port: str,
    expected: list[list[str]],
    *,
    attempts: int = _KEYMAP_VERIFY_ATTEMPTS,
    retry_seconds: float = _KEYMAP_VERIFY_RETRY_SECONDS,
) -> list[list[str]]:
    """Retry read-back while the keyboard finishes committing its flash."""
    from . import reader

    last_actual: list[list[str]] = []
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            last_actual = reader.read_keymap(port, layers=len(expected))
            last_error = None
            if not _keymap_differences(expected, last_actual)[0]:
                return last_actual
        except (ValueError, OSError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(retry_seconds)

    if last_error is not None:
        detail = f"the last read failed: {last_error}"
    else:
        count, examples = _keymap_differences(expected, last_actual)
        detail = f"{count} keycodes differed"
        if examples:
            detail += "; first differences: " + "; ".join(examples)
    raise AcceptedWriteError(
        "Device accepted the configuration, but keymap verification did not settle "
        f"after {max(1, attempts)} reads ({detail}). The LED write may already be "
        "active; retry verification instead of sending the configuration again."
    )


def _probe_keyboard(port: str, attempts: int = 3) -> Any:
    """Probe with a short settle retry; macOS can hold a just-scanned CDC port."""
    from . import device as device_module

    result = None
    for attempt in range(attempts):
        try:
            result = device_module.probe(port, full=True)
        except OSError:
            result = None
        if result and result.is_keyboard:
            return result
        if attempt + 1 < attempts:
            time.sleep(0.2)
    return result


def _settings_view(*, credential_store=None) -> dict[str, Any]:
    """Return the active credential-free settings schema used by the UI."""
    from . import store

    settings, reason = store.load_settings_with_status(
        credential_store=credential_store
    )
    migration_required = reason in {
        store.InvalidAPICredentialError.code,
        store.SettingsMigrationCredentialError.code,
        store.SettingsMigrationValidationError.code,
        store.SettingsMigrationWriteError.code,
    }
    return {
        "schema_version": settings["schema_version"],
        "migration": {
            "required": migration_required,
            "reason": reason if migration_required else None,
        },
        "library": {
            "current_root": settings["library"]["current_root"],
            "roots": list(settings["library"]["roots"]),
        },
        "generation": {
            "loop_mode": settings["generation"]["loop_mode"],
            "privacy_ack_version": settings["ai"]["api"]["disclosure_version"],
            "privacy_ack_at": settings["ai"]["api"]["disclosure_at"],
        },
    }


def _capabilities() -> dict[str, Any]:
    """Provider/model/target capabilities for the UI — the single source of truth.

    Target geometry is projected by the lower-level device mapping core.
    """
    from . import ai_catalog

    return {
        "ai_catalog": ai_catalog.catalog_view(),
        "privacy_disclosure_version": ai_catalog.PRIVACY_DISCLOSURE_VERSION,
        "model_frame_caps": dict(device_mapping.MODEL_FRAME_CAPS),
        "targets": device_mapping.target_capabilities(),
    }


class DocumentRevisionError(RuntimeError):
    """The browser's document revision is absent or no longer current."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _State:
    def __init__(
        self,
        config: dict[str, Any] | None,
        token: str,
        lighting_library: Any = None,
        lighting_coordinator: Any = None,
        lighting_dependencies: dict[str, Any] | None = None,
        ai_capability: Any = None,
        credential_store: Any = None,
        procedural_coordinator: Any = None,
        ollama_client: Any = None,
    ) -> None:
        if (lighting_library is None) != (lighting_coordinator is None):
            raise ValueError(
                "lighting_library and lighting_coordinator must be injected together"
            )
        self.config = copy.deepcopy(config)
        self.token = token
        self._document_lock = threading.Lock()
        self._document_snapshot: bytes | None = None
        self._document_revision: str | None = None
        self.device_lock = threading.Lock()
        self.last_device_scan = 0.0
        # Native desktop builds attach a narrow Library chooser/reveal bridge after
        # creating the loopback server. Browser-only launches leave it unset.
        self.desktop_bridge: Any = None
        self._lighting_lock = threading.Lock()
        self._lighting_library = lighting_library
        self._lighting_coordinator = lighting_coordinator
        self._lighting_dependencies = dict(lighting_dependencies or {})
        self._ai_lock = threading.Lock()
        self._ai_capability = ai_capability
        self._credential_store = credential_store
        self._procedural_coordinator = procedural_coordinator
        self._ollama_client = ollama_client
        self._procedural_library_identity: int | None = (
            id(lighting_library) if procedural_coordinator is not None else None
        )
        from .generation import _PROCESS_OPERATION_GATE

        self._generation_gate = self._lighting_dependencies.get(
            "operation_gate", _PROCESS_OPERATION_GATE
        )
        self._lighting_root_signature: tuple[Any, ...] | None = None
        self._lighting_reconcile_signature: tuple[int, bytes | None] | None = None
        self._lighting_reconcile_pending = False
        self._lighting_reconcile_worker: threading.Thread | None = None
        if config is not None:
            try:
                self.synchronize_document(config)
            except ValueError:
                # Keep an invalid launch document available for manual repair, but
                # never let it establish a generation target.
                pass

    @property
    def document_revision(self) -> str | None:
        with self._document_lock:
            return self._document_revision

    def synchronize_document(self, config: object) -> str:
        """Validate and atomically replace the immutable open-document snapshot."""
        try:
            encoded = json.dumps(
                config,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            candidate = json.loads(encoded)
            checked = validate_config(candidate)
            product_id = checked.get("product_id")
            if not checked.get("ok") or not isinstance(product_id, str):
                raise ValueError
            device_mapping.led_model(product_id)
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ValueError(
                "The open document must be a complete valid keyboard configuration."
            ) from None
        revision = secrets.token_urlsafe(24)
        with self._document_lock:
            self._document_snapshot = encoded
            self._document_revision = revision
            self.config = copy.deepcopy(candidate)
        return revision

    def clear_document(self) -> None:
        with self._document_lock:
            self._document_snapshot = None
            self._document_revision = None
            self.config = None

    def procedural_target(self, revision: str) -> dict:
        with self._document_lock:
            snapshot = self._document_snapshot
            current = self._document_revision
            if snapshot is None or current is None:
                raise DocumentRevisionError(
                    "document_required",
                    "Open or read a compatible device profile before generation.",
                )
            if not secrets.compare_digest(revision, current):
                raise DocumentRevisionError(
                    "document_stale",
                    "The open document changed before generation. Try again.",
                )
        document = json.loads(snapshot)
        product_id = document["product_info"]["product_id"]
        model = device_mapping.led_model(product_id)
        if model == "CB":
            targets = ["frames"]
        elif model == "80":
            targets = ["keyframes", "spotlight_frames"]
        else:
            targets = ["keyframes"]
        return _Handler._lighting_target(product_id, targets)

    def ai_services(self) -> Any:
        """Return the Ollama/API-only capability service."""
        with self._ai_lock:
            if self._ai_capability is None:
                from . import store
                from .ai_capability import AICapabilityService

                credential_store = self._credential_store
                self._ai_capability = AICapabilityService(
                    settings_loader=lambda: store.load_settings(
                        credential_store=credential_store
                    ),
                    credential_status_loader=lambda: store.credential_status(
                        credential_store=credential_store
                    ),
                    credential_resolver=lambda: store.resolve_xai_key(
                        credential_store=credential_store
                    ),
                    fingerprint_writer=lambda backend, fingerprint: (
                        store.set_ai_setup_fingerprint(
                            backend,
                            fingerprint,
                            credential_store=credential_store,
                        )
                    ),
                    ai_settings_writer=lambda values, **kwargs: store.update_ai_settings(
                        values,
                        credential_store=credential_store,
                        **kwargs,
                    ),
                    ollama_client=self._ollama_client,
                )
            return self._ai_capability

    def procedural_services(self) -> tuple[Any, Any]:
        """Return the current Library and its local-first procedural coordinator."""
        from .library import GeneratedAssetLibrary

        library, _legacy = self.lighting_services()
        if (
            self._procedural_coordinator is not None
            and self._procedural_library_identity == id(library)
        ):
            return library, self._procedural_coordinator
        if not isinstance(library, GeneratedAssetLibrary):
            raise RuntimeError("Procedural generation services are unavailable.")
        from .procedural_generation import ProceduralGenerationCoordinator

        capability = self.ai_services()
        self._procedural_coordinator = ProceduralGenerationCoordinator(
            library,
            capability,
            operation_gate=self._generation_gate,
        )
        self._procedural_library_identity = id(library)
        return library, self._procedural_coordinator

    def close(self) -> None:
        capability = self._ai_capability
        close = getattr(capability, "close", None)
        if callable(close):
            close()

    def lighting_services(self) -> tuple[Any, Any]:
        """Return durable services, refreshing idle production roots from Settings."""
        if self._lighting_root_signature is None and self._lighting_library is not None:
            return self._lighting_library, self._lighting_coordinator
        from . import store
        from .generation import GenerationCoordinator
        from .library import GeneratedAssetLibrary

        settings = store.load_settings()
        current_root = settings["library"]["current_root"]
        roots = tuple(settings["library"]["roots"])
        signature = (current_root, *roots)
        with self._lighting_lock:
            active = getattr(self._lighting_coordinator, "active_job_id", None)
            procedural_active = getattr(
                self._procedural_coordinator, "active_job_id", None
            )
            if (
                self._lighting_library is not None
                and (
                    self._lighting_root_signature == signature
                    or active is not None
                    or procedural_active is not None
                )
            ):
                return self._lighting_library, self._lighting_coordinator
            library = GeneratedAssetLibrary(current_root, roots)
            coordinator = GenerationCoordinator(
                library, **self._lighting_dependencies
            )
            self._lighting_library = library
            self._lighting_coordinator = coordinator
            self._lighting_root_signature = signature
            return library, coordinator

    def reconcile_lighting(self, *, force: bool = False) -> list[dict]:
        """Reconcile durable work now and again whenever the effective key changes."""
        from . import store
        from .generation import GenerationBusyError

        if self._generation_gate.is_active:
            self._defer_lighting_reconciliation()
            return []

        _library, coordinator = self.lighting_services()
        api_key = store.resolve_xai_key(
            credential_store=self._credential_store
        )
        key_fingerprint = (
            hashlib.sha256(api_key.encode("utf-8")).digest() if api_key else None
        )
        signature = (id(coordinator), key_fingerprint)
        with self._lighting_lock:
            if not force and signature == self._lighting_reconcile_signature:
                return []
            # Claim this signature before reconciliation so concurrent requests
            # cannot launch the same accepted video twice. A failure clears the
            # claim, allowing the next safe trigger to retry.
            self._lighting_reconcile_signature = signature
        try:
            token, _cancelled = self._generation_gate.begin()
            try:
                actions = coordinator.reconcile_startup(
                    api_key=api_key,
                    _admission_token=token,
                )
                try:
                    _procedural_library, procedural = self.procedural_services()
                except RuntimeError:
                    return actions
                return [
                    *actions,
                    *procedural.reconcile_startup(_admission_token=token),
                ]
            finally:
                self._generation_gate.finish(token)
        except GenerationBusyError:
            with self._lighting_lock:
                if self._lighting_reconcile_signature == signature:
                    self._lighting_reconcile_signature = None
            self._defer_lighting_reconciliation()
            return []
        except BaseException:
            with self._lighting_lock:
                if self._lighting_reconcile_signature == signature:
                    self._lighting_reconcile_signature = None
            raise

    def _defer_lighting_reconciliation(self) -> None:
        """Coalesce settings/startup recovery until shared admission is idle."""
        with self._lighting_lock:
            self._lighting_reconcile_pending = True
            if (
                self._lighting_reconcile_worker is not None
                and self._lighting_reconcile_worker.is_alive()
            ):
                return

            def resume_when_idle() -> None:
                while True:
                    self._generation_gate.wait_until_idle()
                    with self._lighting_lock:
                        if not self._lighting_reconcile_pending:
                            self._lighting_reconcile_worker = None
                            return
                        self._lighting_reconcile_pending = False
                    try:
                        self.reconcile_lighting(force=True)
                    except Exception:
                        with self._lighting_lock:
                            self._lighting_reconcile_worker = None
                        return
                    with self._lighting_lock:
                        if not self._lighting_reconcile_pending:
                            self._lighting_reconcile_worker = None
                            return

            worker = threading.Thread(
                target=resume_when_idle,
                name="am-lighting-reconcile",
                daemon=True,
            )
            self._lighting_reconcile_worker = worker
            worker.start()

    def settle_after_scan(self, seconds: float = 1.5) -> None:
        remaining = seconds - (time.monotonic() - self.last_device_scan)
        if remaining > 0:
            time.sleep(remaining)

class _Handler(BaseHTTPRequestHandler):
    server_version = f"AMConfigurator/{__version__}"

    @property
    def state(self) -> _State:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep launch output useful; successful static requests are noise.
        if len(args) < 2 or str(args[1]) not in {"200", "304"}:
            super().log_message(fmt, *args)

    def _headers(
        self,
        status: int,
        content_type: str,
        length: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; "
            "media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'",
        )
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def _json(self, value: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(payload))
        self.wfile.write(payload)

    def _authorized(self) -> bool:
        candidate = self.headers.get("X-AM-Token", "")
        expected = self.state.token
        if not isinstance(candidate, str) or not isinstance(expected, str):
            return False
        try:
            candidate_bytes = candidate.encode("ascii")
            expected_bytes = expected.encode("ascii")
        except UnicodeEncodeError:
            return False
        return secrets.compare_digest(candidate_bytes, expected_bytes)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 25_000_000:
                raise ValueError("invalid request size")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("request body must be an object")
            return value
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid request: {exc}") from exc

    def _lighting_error(self, exc: Exception) -> bool:
        from . import llm
        from .ai_capability import AICapabilityError
        from .generation import (
            GenerationBusyError,
            GenerationNotActiveError,
            GenerationValidationError,
        )
        from .library import (
            AssetNotFoundError,
            InvalidIdentifierError,
            LibraryRootError,
            ManifestError,
        )

        if isinstance(exc, AICapabilityError):
            self._json(
                {"code": exc.reason, "error": "Optional AI is not ready."},
                HTTPStatus.CONFLICT,
            )
            return True
        if isinstance(exc, llm.ProviderError):
            payload: dict[str, Any] = {
                "code": exc.code,
                "error": exc.message,
            }
            if exc.retry_after is not None:
                payload["retry_after"] = exc.retry_after
            self._json(
                payload,
                _PROVIDER_ERROR_HTTP.get(exc.code, HTTPStatus.BAD_GATEWAY),
            )
            return True
        if isinstance(exc, (GenerationBusyError, GenerationNotActiveError)):
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return True
        if isinstance(exc, AssetNotFoundError):
            self._json({"error": "Asset not found."}, HTTPStatus.NOT_FOUND)
            return True
        if isinstance(exc, InvalidIdentifierError):
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if isinstance(exc, ManifestError):
            self._json({"error": "Generated job or asset not found."}, HTTPStatus.NOT_FOUND)
            return True
        if isinstance(exc, (GenerationValidationError, LibraryRootError, ValueError)):
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        return False

    def _internal_error(self, exc: Exception) -> None:
        # Keep unexpected dependency, filesystem, device, provider, and
        # subprocess details on the local process boundary. Exception text may
        # contain user paths, raw replies, signed URLs, or credentials.
        self.log_error("Unhandled local API request error: %s", type(exc).__name__)
        self._json(
            {"error": "The local request failed unexpectedly."},
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    def _accepted_write_error(self, exc: AcceptedWriteError) -> None:
        self.log_error(
            "Accepted device write did not verify: %s",
            type(exc).__name__,
        )
        self._json(
            {
                "error": (
                    "Device accepted the configuration, but verification did not "
                    "complete. Retry verification instead of sending the "
                    "configuration again."
                ),
                "accepted": True,
                "retryable": True,
            },
            HTTPStatus.CONFLICT,
        )

    @staticmethod
    def _is_ai_path(path: str) -> bool:
        return path.startswith("/api/ai/") or path in {
            "/api/settings/ai",
            "/api/settings/credential",
            "/api/settings/migration/discard-credential",
        }

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            if not self._authorized():
                self._json({"error": "Unauthorized local request."}, HTTPStatus.FORBIDDEN)
                return
            try:
                if path == "/api/config":
                    self._json(
                        {
                            "config": self.state.config,
                            "document_revision": self.state.document_revision,
                        }
                    )
                elif path == "/api/devices":
                    from . import device

                    with self.state.device_lock:
                        devices = device.list_devices(full=True)
                        self.state.last_device_scan = time.monotonic()
                    self._json({"devices": [asdict(d) for d in devices]})
                elif path == "/api/settings":
                    self._json(
                        _settings_view(
                            credential_store=self.state._credential_store
                        )
                    )
                elif path == "/api/led/capabilities":
                    self._json(_capabilities())
                elif path == "/api/ai/status":
                    if parsed.query:
                        raise ValueError(
                            "The optional AI status route does not accept query fields."
                        )
                    capability = self.state.ai_services()
                    self._json(capability.status())
                elif path == "/api/ai/local/models":
                    if parsed.query:
                        raise ValueError(
                            "The local model route does not accept query fields."
                        )
                    capability = self.state.ai_services()
                    self._json(capability.discover_local_models())
                elif path.startswith("/api/lighting/"):
                    self._lighting_get(path, parsed.query)
                elif path == "/api/led/generate/status":
                    self._retired_ai_mutation()
                else:
                    self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001 - API boundary
                handled = (
                    path.startswith("/api/lighting/") or self._is_ai_path(path)
                ) and self._lighting_error(exc)
                if not handled:
                    self._internal_error(exc)
            return

        filename = _STATIC.get(path)
        if filename is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        asset = _ASSETS / filename
        try:
            payload = asset.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if filename == "index.html":
            payload = payload.replace(
                b"__AM_VERSION__",
                __version__.encode("utf-8"),
            )
        content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self._headers(HTTPStatus.OK, content_type, len(payload))
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if not self._authorized():
            self._json({"error": "Unauthorized local request."}, HTTPStatus.FORBIDDEN)
            return
        try:
            body = self._body()
            if path == "/api/config/validate":
                self._json(validate_config(body.get("config")))
            elif path == "/api/document/sync":
                self._synchronize_document(body)
            elif path == "/api/config/compatibility":
                self._json(config_transfer_options(
                    body.get("config"),
                    body.get("target_product_id"),
                ))
            elif path == "/api/macros/import":
                source = body.get("config")
                self._json({
                    "macros": extract_importable_macros(source),
                    "product_id": str(((source or {}).get("product_info") or {}).get("product_id") or "?"),
                })
            elif path == "/api/macros/text":
                self._json(text_to_macro_events(body.get("text"), body.get("delay_ms", 10)))
            elif path == "/api/led/gif":
                self._convert_gif(body)
            elif path == "/api/settings/preferences":
                self._save_settings_preferences(body)
            elif path == "/api/settings/library":
                self._save_settings_library(body)
            elif path == "/api/settings/privacy":
                self._save_settings_privacy(body)
            elif path == "/api/settings/ai":
                self._save_ai_settings(body)
            elif path == "/api/settings/credential":
                self._save_ai_credential(body)
            elif path == "/api/settings/migration/discard-credential":
                self._discard_legacy_ai_credential(body)
            elif path == "/api/ai/test":
                self._test_ai_backend(body)
            elif path == "/api/ai/local/select":
                self._select_local_model(body)
            elif path == "/api/ai/local/clear":
                self._clear_local_model(body)
            elif path == "/api/native/choose-library":
                self._native_choose_library(body)
            elif path == "/api/native/reveal-library":
                self._native_reveal_library(body)
            elif path == "/api/lighting/effects":
                self._start_procedural_effect(body)
            elif path == "/api/lighting/concepts" or path.startswith(
                "/api/lighting/jobs/"
            ):
                self._lighting_post(path, body)
            elif path == "/api/led/generate":
                self._retired_ai_mutation()
            elif path == "/api/led/generate/cancel":
                self._retired_ai_mutation()
            elif path == "/api/device/read":
                self._read_device(body)
            elif path == "/api/device/write":
                self._write_device(body)
            elif path == "/api/device/verify":
                self._verify_device_write(body)
            else:
                self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
        except AcceptedWriteError as exc:
            self._accepted_write_error(exc)
        except ValueError as exc:
            payload = {"error": str(exc)}
            code = getattr(exc, "code", None)
            if isinstance(code, str):
                payload["code"] = code
            self._json(payload, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - API boundary
            handled = (
                path.startswith("/api/lighting/") or self._is_ai_path(path)
            ) and self._lighting_error(exc)
            if not handled:
                self._internal_error(exc)

    @staticmethod
    def _strict_body(
        body: dict[str, Any],
        *,
        allowed: set[str],
        required: set[str] = frozenset(),
    ) -> None:
        unknown = set(body) - allowed
        missing = required - set(body)
        if unknown or missing:
            raise ValueError("The lighting request body has unsupported fields.")

    def _require_ai_idle(self) -> None:
        if self.state._generation_gate.is_active:
            from .generation import GenerationBusyError

            raise GenerationBusyError("another generation operation is already active")

    def _save_ai_settings(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(
            body,
            allowed={"enabled", "backend", "provider", "model_id"},
        )
        if not body:
            raise ValueError("The optional AI settings request is empty.")
        self._require_ai_idle()
        capability = self.state.ai_services()
        current = capability.status()
        selected_backend = body.get("backend", current["backend"])
        selected_provider = body.get("provider", current["api"]["provider"])
        selected_model = body.get("model_id", current["api"]["model_id"])
        will_enable = body.get("enabled", current["enabled"])
        ready = False
        if will_enable:
            ready = capability.backend_setup_valid(selected_backend)
            if selected_backend == "api":
                ready = (
                    ready
                    and selected_provider == current["api"]["provider"]
                    and selected_model == current["api"]["model_id"]
                )
        store.update_ai_settings(
            body,
            ready=ready,
            credential_store=self.state._credential_store,
        )
        self._json(capability.status())

    def _save_ai_credential(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(
            body,
            allowed={"provider", "key"},
            required={"provider", "key"},
        )
        self._require_ai_idle()
        store.update_api_key(
            body,
            credential_store=self.state._credential_store,
        )
        self.state.reconcile_lighting(force=True)
        capability = self.state.ai_services()
        self._json(capability.status())

    def _discard_legacy_ai_credential(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(body, allowed={"confirm"}, required={"confirm"})
        self._require_ai_idle()
        store.discard_legacy_api_credential(body)
        self._json(
            _settings_view(credential_store=self.state._credential_store)
        )

    def _test_ai_backend(self, body: dict[str, Any]) -> None:
        self._strict_body(
            body,
            allowed={"backend"},
            required={"backend"},
        )
        capability = self.state.ai_services()
        token, cancelled = self.state._generation_gate.begin("ai-setup-test")
        try:
            status = capability.test_and_enable(
                body["backend"],
                deadline=time.monotonic() + 180.0,
                cancelled=cancelled.is_set,
            )
        finally:
            self.state._generation_gate.finish(token)
        self._json(status)

    def _select_local_model(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(body, allowed={"model_id"}, required={"model_id"})
        self._require_ai_idle()
        model_id = body["model_id"]
        if not isinstance(model_id, str):
            raise ValueError("The Ollama model name is invalid.")
        capability = self.state.ai_services()
        discovered = capability.discover_local_models()
        if discovered.get("available") is not True:
            self._json(
                {"error": "The local Ollama service is unavailable."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        match = next(
            (
                model
                for model in discovered.get("models", [])
                if isinstance(model, dict) and model.get("model_id") == model_id
            ),
            None,
        )
        if match is None:
            raise ValueError("The selected Ollama model is not installed locally.")
        store.update_local_ai_settings(
            {
                "model_id": match["model_id"],
                "model_digest": match["digest"],
            },
            credential_store=self.state._credential_store,
        )
        capability.close()
        self._json(capability.status())

    def _clear_local_model(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(body, allowed=set())
        self._require_ai_idle()
        capability = self.state.ai_services()
        store.update_local_ai_settings(
            {"model_id": None, "model_digest": None},
            credential_store=self.state._credential_store,
        )
        self._json(capability.status())

    def _synchronize_document(self, body: dict[str, Any]) -> None:
        self._strict_body(body, allowed={"config"}, required={"config"})
        revision = self.state.synchronize_document(body["config"])
        self._json({"revision": revision})

    def _start_procedural_effect(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(
            body,
            allowed={"prompt", "backend", "loop_mode", "document_revision"},
            required={"prompt", "backend", "document_revision"},
        )
        revision = body["document_revision"]
        if not isinstance(revision, str) or not 24 <= len(revision) <= 200:
            raise ValueError("document_revision must be an opaque revision string.")
        try:
            target = self.state.procedural_target(revision)
        except DocumentRevisionError as exc:
            self._json({"code": exc.code, "error": str(exc)}, HTTPStatus.CONFLICT)
            return
        capability = self.state.ai_services()
        status = capability.require_ready()
        if body["backend"] != status["backend"]:
            self._json(
                {
                    "code": "backend_mismatch",
                    "error": "The selected AI backend changed before generation.",
                },
                HTTPStatus.CONFLICT,
            )
            return
        settings = store.load_settings(
            credential_store=self.state._credential_store
        )
        _library, coordinator = self.state.procedural_services()
        manifest = coordinator.start_effect(
            prompt=body["prompt"],
            target=target,
            loop_mode=body.get(
                "loop_mode", settings["generation"]["loop_mode"]
            ),
        )
        self._json(
            {"job_id": manifest["job_id"], "target": manifest["target"]},
            HTTPStatus.ACCEPTED,
        )

    def _retired_ai_mutation(self) -> None:
        self._json(
            {
                "code": "retired",
                "error": "This legacy AI generation route is retired.",
            },
            HTTPStatus.GONE,
        )

    @staticmethod
    def _lighting_target(product_id: object, targets: object) -> dict:
        if not isinstance(product_id, str) or not product_id:
            raise ValueError("product_id must be a non-empty string.")
        if (
            not isinstance(targets, list)
            or not targets
            or not all(isinstance(target, str) and target for target in targets)
        ):
            raise ValueError("targets must be a non-empty list of LED track names.")
        spec, resolved = device_mapping.generation_spec(product_id, targets, None)
        return {
            "family": spec.model,
            "product_id": product_id,
            "raster": {"width": spec.width, "height": spec.height},
            "targets": resolved,
            "frame_cap": spec.max_frames,
        }

    def _lighting_post(self, path: str, body: dict[str, Any]) -> None:
        library, coordinator = self.state.lighting_services()
        if path == "/api/lighting/concepts":
            self._retired_ai_mutation()
            return

        parts = path.strip("/").split("/")
        if len(parts) != 5 or parts[:3] != ["api", "lighting", "jobs"]:
            self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        job_id, action = parts[3], parts[4]
        if action in {"concepts", "animate", "process"}:
            self._retired_ai_mutation()
            return
        # Resolve through the manifest boundary before any coordinator action;
        # this validates canonical IDs and historical-root ownership uniformly.
        manifest = library.load_manifest(job_id)
        if action == "cancel":
            self._strict_body(body, allowed=set())
            if manifest.get("pipeline") == "procedural":
                _procedural_library, procedural = self.state.procedural_services()
                manifest = procedural.cancel(job_id)
            else:
                manifest = coordinator.cancel(job_id)
            status = HTTPStatus.OK
        else:
            self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        self._json({"job_id": manifest["job_id"]}, status)

    def _lighting_get(self, path: str, query: str) -> None:
        library, _coordinator = self.state.lighting_services()
        if path == "/api/lighting/library":
            self._lighting_library_page(library, query)
            return
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:3] == ["api", "lighting", "jobs"]:
            if query:
                raise ValueError("The job status route does not accept query fields.")
            self._json(library.get_job(parts[3]))
            return
        if len(parts) == 4 and parts[:3] == ["api", "lighting", "library"]:
            if query:
                raise ValueError("The library detail route does not accept query fields.")
            self._json(library.get_job(parts[3]))
            return
        if len(parts) == 5 and parts[:3] == ["api", "lighting", "assets"]:
            if query:
                raise ValueError("Asset routes do not accept query fields.")
            self._lighting_asset(library, parts[3], parts[4])
            return
        self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def _lighting_library_page(self, library: Any, query: str) -> None:
        values = parse_qs(query, keep_blank_values=True)
        if set(values) - {"page", "limit", "status", "kind", "query"}:
            raise ValueError("The library query has unsupported fields.")
        if any(len(items) != 1 for items in values.values()):
            raise ValueError("The library query cannot repeat fields.")

        def positive_integer(name: str, default: int, maximum: int) -> int:
            raw = values.get(name, [str(default)])[0]
            if not raw.isdigit():
                raise ValueError(f"{name} must be a positive integer.")
            number = int(raw)
            if not 1 <= number <= maximum:
                raise ValueError(f"{name} is outside its supported range.")
            return number

        page = positive_integer("page", 1, 1_000_000)
        limit = positive_integer("limit", 24, 100)
        statuses = {
            value
            for value in values.get("status", [""])[0].split(",")
            if value
        }
        if any(
            len(status) > 80 or not status.replace("_", "").isalnum()
            for status in statuses
        ):
            raise ValueError("status filter is invalid.")
        kind = values.get("kind", [""])[0]
        if len(kind) > 80 or (kind and not kind.replace("_", "").isalnum()):
            raise ValueError("kind filter is invalid.")
        search = values.get("query", [""])[0].casefold()
        if len(search) > 200:
            raise ValueError("query filter is too long.")

        scanned = library.scan()
        jobs = []
        for manifest in scanned["jobs"]:
            if statuses and manifest["status"] not in statuses:
                continue
            if kind and not any(asset["kind"] == kind for asset in manifest["assets"]):
                continue
            if search and search not in manifest["prompt"].casefold():
                continue
            jobs.append(
                {
                    "job_id": manifest["job_id"],
                    "created_at": manifest["created_at"],
                    "updated_at": manifest["updated_at"],
                    "prompt": manifest["prompt"],
                    "target": manifest["target"],
                    "selected_candidate_id": manifest["selected_candidate_id"],
                    "status": manifest["status"],
                    "phase": manifest["phase"],
                    "progress": manifest["progress"],
                    "costs": manifest["costs"],
                    "candidate_count": len(manifest["candidates"]),
                    "asset_count": len(manifest["assets"]),
                }
            )
        total = len(jobs)
        start = (page - 1) * limit
        selected = jobs[start : start + limit]
        self._json(
            {
                "jobs": selected,
                "page": page,
                "limit": limit,
                "total": total,
                "has_more": start + len(selected) < total,
                "errors": scanned["errors"],
            }
        )

    def _range_not_satisfiable(self, total: int) -> None:
        payload = json.dumps({"error": "The requested media range is invalid."}).encode()
        self._headers(
            HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
            "application/json; charset=utf-8",
            len(payload),
            {"Content-Range": f"bytes */{total}"},
        )
        self.wfile.write(payload)

    def _lighting_asset(self, library: Any, job_id: str, asset_id: str) -> None:
        owned = library.resolve_asset(job_id, asset_id)
        mime_type = owned.record["mime_type"]
        if mime_type not in _LIGHTING_ASSET_MIMES:
            raise ValueError("This generated asset type cannot be served.")
        total = owned.record["byte_size"]
        range_header = self.headers.get("Range")
        if range_header is None:
            with owned.open_verified() as stream:
                payload = stream.read(total + 1)
            if len(payload) != total:
                raise ValueError("The generated asset changed while it was read.")
            extra = {"Accept-Ranges": "bytes"} if mime_type == "video/mp4" else None
            self._headers(HTTPStatus.OK, mime_type, len(payload), extra)
            self.wfile.write(payload)
            return
        if mime_type != "video/mp4" or not range_header.startswith("bytes="):
            self._range_not_satisfiable(total)
            return
        requested = range_header[6:]
        if "," in requested or requested.count("-") != 1:
            self._range_not_satisfiable(total)
            return
        first, last = requested.split("-", 1)
        try:
            if first:
                start = int(first)
                end = int(last) if last else total - 1
            else:
                suffix = int(last)
                if suffix <= 0:
                    raise ValueError
                start = max(0, total - suffix)
                end = total - 1
        except ValueError:
            self._range_not_satisfiable(total)
            return
        if (
            start < 0
            or end < start
            or start >= total
            or end >= total
            or end - start + 1 > _MAX_ASSET_RANGE_BYTES
        ):
            self._range_not_satisfiable(total)
            return
        with owned.open_verified() as stream:
            stream.seek(start)
            payload = stream.read(end - start + 1)
        self._headers(
            HTTPStatus.PARTIAL_CONTENT,
            mime_type,
            len(payload),
            {
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{total}",
            },
        )
        self.wfile.write(payload)

    def _convert_gif(self, body: dict[str, Any]) -> None:
        encoded = body.get("data")
        if not isinstance(encoded, str):
            raise ValueError("GIF data is missing.")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("GIF data is not valid base64.") from exc
        targets = body.get("targets")
        if targets is not None:
            if not isinstance(targets, list) or not all(
                isinstance(target, str) for target in targets
            ):
                raise ValueError("GIF targets must be a list of LED track names.")
            result = gif_to_led_tracks(
                payload,
                targets,
                str(body.get("resample") or "box"),
                str(body.get("product_id") or ""),
            )
        else:
            result = gif_to_led_frames(
                payload,
                str(body.get("target") or ""),
                str(body.get("resample") or "box"),
                str(body.get("product_id") or ""),
            )
        self._json(result)

    def _save_settings_preferences(self, body: dict[str, Any]) -> None:
        from . import store

        store.update_preferences(body)
        self._json(_settings_view())

    def _save_settings_library(self, body: dict[str, Any]) -> None:
        from . import store

        store.update_library_root(body)
        self.state.reconcile_lighting(force=True)
        self._json(_settings_view())

    def _save_settings_privacy(self, body: dict[str, Any]) -> None:
        from . import store

        store.acknowledge_privacy(body)
        self._json(_settings_view())

    def _native_choose_library(self, body: dict[str, Any]) -> None:
        if body:
            raise ValueError("The folder chooser does not accept options.")
        bridge = self.state.desktop_bridge
        if bridge is None:
            self._json(
                {"error": "The native folder chooser is unavailable in this launch."},
                HTTPStatus.NOT_FOUND,
            )
            return
        try:
            selected = bridge.choose_library_folder()
        except Exception as exc:  # noqa: BLE001 - native UI boundary
            self._internal_error(exc)
            return
        self._json({"path": selected})

    def _native_reveal_library(self, body: dict[str, Any]) -> None:
        if set(body) != {"path"} or not isinstance(body["path"], str):
            raise ValueError("Reveal requires one library path.")
        bridge = self.state.desktop_bridge
        if bridge is None:
            self._json(
                {"error": "Native Reveal is unavailable in this launch."},
                HTTPStatus.NOT_FOUND,
            )
            return
        try:
            revealed = bool(bridge.reveal_library_path(body["path"]))
        except Exception:  # noqa: BLE001 - native UI boundary
            revealed = False
        self._json({"revealed": revealed})

    def _read_device(self, body: dict[str, Any]) -> None:
        from . import macros as macro_protocol
        from . import reader

        port = str(body.get("port") or "")
        layers = int(body.get("layers") or 7)
        if not port:
            raise ValueError("A serial port is required.")
        with self.state.device_lock:
            self.state.settle_after_scan()
            device = _probe_keyboard(port)
            if not device or not device.is_keyboard:
                raise ValueError("The selected port is not a supported Angry Miao keyboard.")
            time.sleep(0.1)
            key_layers = reader.read_keymap(port, layers=layers)
            time.sleep(0.1)
            device_macros = macro_protocol.read_macros(port)
        stored_config, stored_warning = _stored_device_config(device.product_id or "")
        resolved_macros, macro_read_warning, restored_macro_snapshot = (
            _reconcile_read_macros(
                device.product_id or "", device_macros, stored_config
            )
        )
        self._json({
            "device": asdict(device),
            "layers": key_layers,
            "macros": resolved_macros,
            "macro_references": _macro_references(key_layers),
            "macro_read_warning": macro_read_warning,
            "macro_restored_from_snapshot": restored_macro_snapshot,
            "blank_config": blank_config(
                device.product_id or "", key_layers, resolved_macros
            ),
            "stored_config": stored_config,
            "stored_warning": stored_warning,
        })

    def _write_device(self, body: dict[str, Any]) -> None:
        from . import writer

        port, config, checked = self._write_request(body)
        with self.state.device_lock:
            self.state.settle_after_scan()
            before = self._validated_write_target(port, checked, body)
            frame_plan = writer.plan(config)
            ok, reply = writer.write_config(port, frame_plan.frames)
            if not ok:
                raise RuntimeError(f"Device rejected JSON_END: {reply.hex() or 'no response'}")
            time.sleep(writer.SETTLE_SECONDS)
            result = self._finish_accepted_write(
                port, config, before, frame_plan.total, install_macros=True
            )
        self._json(result)

    def _verify_device_write(self, body: dict[str, Any]) -> None:
        """Finish an ACKed write without transmitting the full configuration again."""
        from . import writer

        port, config, checked = self._write_request(body)
        with self.state.device_lock:
            before = self._validated_write_target(port, checked, body)
            frame_plan = writer.plan(config)
            result = self._finish_accepted_write(
                port, config, before, frame_plan.total, install_macros=False
            )
        self._json(result)

    @staticmethod
    def _write_request(body: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        port = str(body.get("port") or "")
        config = body.get("config")
        checked = validate_config(config)
        if not checked["ok"]:
            raise ValueError("Configuration is invalid: " + "; ".join(checked["errors"]))
        if not port:
            raise ValueError("A serial port is required.")
        return port, config, checked

    @staticmethod
    def _validated_write_target(port: str, checked: dict[str, Any], body: dict[str, Any]) -> Any:
        before = _probe_keyboard(port)
        if not before or not before.is_keyboard or not before.product_id:
            raise ValueError("The selected port is not a supported Angry Miao keyboard.")
        config_id = str(checked["product_id"])
        if not _device_matches_config(before.product_id, config_id):
            raise ValueError(
                f"Configuration {config_id} does not match connected device {before.product_id}."
            )
        confirmation = str(body.get("confirmation") or "")
        if confirmation != before.product_id:
            raise ValueError(f"Confirmation must exactly match {before.product_id}.")
        return before

    def _finish_accepted_write(
        self,
        port: str,
        config: dict[str, Any],
        before: Any,
        frame_total: int,
        *,
        install_macros: bool,
    ) -> dict[str, Any]:
        from . import macros
        from . import store

        expected_layers = [
            [code.upper() for code in item["layer"]]
            for item in config["key_layer"]["layer_data"]
        ]
        expected_macros = _canonical_macros(config.get("macro_key", []))
        # JSON_START replaces the device config. Restore the separately-addressed
        # macro table immediately after its ACK, before a potentially transient
        # keymap read-back can abort verification. The verify-only endpoint never
        # writes; it only checks what the accepted write left on the device.
        if install_macros:
            macros.write_macros(port, expected_macros)
            time.sleep(0.25)

        _verify_keymap_readback(port, expected_layers)
        read_macros = macros.read_macros(port)
        macro_verification = _classify_macro_readback(
            before.product_id, expected_macros, read_macros
        )
        if macro_verification["status"] == "mismatch":
            raise AcceptedWriteError(
                "Device accepted the configuration and its keymap verified, but macro "
                "read-back did not match "
                f"({macro_verification['detail']}). Retry verification instead of "
                "sending the full configuration again."
            )

        after = _probe_keyboard(port)
        if not after or after.product_id != before.product_id:
            raise AcceptedWriteError(
                "Device accepted the configuration but disappeared before verification "
                "completed. Reconnect it and retry verification instead of resending."
            )
        clean = {key: value for key, value in config.items() if key != "_provenance"}
        store.save_current(after.product_id, clean, version=after.version)
        snapshot = store.snapshot(after.product_id, clean)
        document_revision = self.state.synchronize_document(clean)
        return {
            "ok": True,
            "device": asdict(after),
            "frames": frame_total,
            "macros": len(expected_macros),
            "macro_verification": macro_verification["status"],
            "macro_warning": macro_verification["warning"],
            "snapshot": snapshot.stem,
            "document_revision": document_revision,
        }


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: _State) -> None:
        super().__init__(address, _Handler)
        self.state = state

    def server_bind(self) -> None:
        # HTTPServer's default calls getfqdn(host), which is unnecessary for a
        # loopback-only app and can stall frozen desktop binaries during DNS
        # resolution. Bind directly and keep the fields HTTPServer expects.
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = int(self.server_address[1])

    def server_close(self) -> None:
        try:
            self.state.close()
        finally:
            super().server_close()


def create_server(
    config_paths: list[str] | None = None,
    *,
    port: int = 0,
    lighting_library: Any = None,
    lighting_coordinator: Any = None,
    lighting_dependencies: dict[str, Any] | None = None,
    ai_capability: Any = None,
    credential_store: Any = None,
    procedural_coordinator: Any = None,
    ollama_client: Any = None,
) -> tuple[_Server, str]:
    """Create the loopback configurator server without starting its event loop.

    Tests may inject complete durable/procedural coordinators, the capability
    service and credential store, or just dependency maps for
    production construction. These seams keep endpoint tests offline.
    """
    configs: list[dict[str, Any]] = []
    for raw_path in config_paths or []:
        path = Path(raw_path).expanduser()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"am-configurator: cannot read {path}: {exc}") from None
        if not isinstance(value, dict):
            raise SystemExit(f"am-configurator: {path} is not a JSON object")
        configs.append(value)

    token = secrets.token_urlsafe(24)
    state = _State(
        merge_configs(configs),
        token,
        lighting_library=lighting_library,
        lighting_coordinator=lighting_coordinator,
        lighting_dependencies=lighting_dependencies,
        ai_capability=ai_capability,
        credential_store=credential_store,
        procedural_coordinator=procedural_coordinator,
        ollama_client=ollama_client,
    )
    state.reconcile_lighting(force=True)
    server = _Server(("127.0.0.1", port), state)
    url = f"http://127.0.0.1:{server.server_port}/?token={token}"
    return server, url


def run(
    config_paths: list[str] | None = None,
    *,
    port: int = 0,
    open_browser: bool = True,
) -> int:
    server, url = create_server(config_paths, port=port)
    print("AM Configurator is running locally.")
    print(url)
    print("Press Ctrl-C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping AM Configurator.")
    finally:
        server.server_close()
    return 0
