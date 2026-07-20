"""Local, dependency-free browser GUI for Angry Miao keyboard configuration."""
from __future__ import annotations

import copy
import base64
import binascii
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
from urllib.parse import urlparse


_PKG = Path(__file__).resolve().parent
_ASSETS = _PKG / "web"
_STATIC = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/style.css": "style.css",
}
_KEY_FIELDS = (
    "key_layer", "tab_key", "tab_key_num", "macro_key", "MACRO_key",
    "MACRO_key_num", "Fn_key", "Fn_key_num", "swap_key", "swap_key_num",
    "exchange_key", "exchange_num",
)
_MAX_GIF_BYTES = 12_000_000
_MAX_GIF_FRAMES = 256
# The current official configurator exposes these exact firmware timing steps.
_LED_SPEEDS_MS = (255, 240, 224, 208, 192, 176, 160, 146, 132, 118, 100, 90, 76, 62, 48, 34)
_KEYMAP_VERIFY_ATTEMPTS = 4
_KEYMAP_VERIFY_RETRY_SECONDS = 1.0

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

# Source-pixel -> firmware-index maps used by Angry Miao's own image converters.
# The firmware always stores 90 per-key colors, but the physical/raster geometry
# differs per model and leaves some indexes unused.
_CB_KEY_MAP = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
    15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
    30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
    45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, -1, 58, 59,
    60, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, -1, 72, 73, -1,
    75, 76, 77, 79, -1, 80, -1, -1, 81, 85, 86, -1, 87, 88, 89,
)
# The CyberBoard display is drawn as 40 columns by 5 rows, but both Angry
# Miao's converter and the firmware serialize each column before moving right.
# PIL gives us row-major source pixels, so map (x, y) to x * 5 + y.
_CB_DISPLAY_MAP = tuple(
    (source_index % 40) * 5 + source_index // 40
    for source_index in range(200)
)
_AFA_KEY_MAP = (
    0, 1, 2, 3, 4, 5, 6, 20, 7, 8, 9, 10, 11, 12, -1, 13,
    14, 15, -1, 16, 17, 18, 19, 34, 35, 21, 22, 23, 24, 25, 26, 27,
    28, 29, -1, 30, 31, 32, 33, 48, 49, 36, 37, 38, 39, 40, -1, 41,
    42, 43, -1, 44, 45, 46, 47, 62, 63, 64, 50, 51, 52, 53, 54, 55,
    56, 57, 58, -1, 59, 60, 61, 73, 70, 65, -1, 66, -1, 67, 68, 69,
)
_RELIC_KEY_MAP = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 59, 58,
    15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 74, 73,
    30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 89, 72,
    45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, -1, 57, -1, -1, -1,
    60, -1, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, -1, 71, -1, 87, -1,
    75, 76, 77, 78, -1, -1, 79, -1, -1, 80, -1, 85, 86, 88, 83, 82, 81,
)


def _placed_map(width: int, height: int, placements: list[tuple[int, int, int]]) -> tuple[int, ...]:
    result = [-1] * (width * height)
    for x, y, output_index in placements:
        result[y * width + x] = output_index
    return tuple(result)


_RELIC_KEY_SOURCE_MAP = _placed_map(
    18, 7,
    [
        (position % 17 + 1, position // 17 + 1, output_index)
        for position, output_index in enumerate(_RELIC_KEY_MAP)
        if output_index >= 0
    ],
)
_RELIC_EDGE_MAP = _placed_map(
    18, 7,
    [(0, 6, 0), (0, 5, 1), (13, 0, 2), (14, 0, 3),
     (15, 0, 4), (16, 0, 5), (17, 0, 6)],
)
_GIF_LAYOUTS: dict[str, dict[str, dict[str, Any]]] = {
    "CB": {
        "keyframes": {"size": (15, 6), "map": _CB_KEY_MAP, "pixels": 90},
        "frames": {"size": (40, 5), "map": _CB_DISPLAY_MAP, "pixels": 200},
    },
    "ALICE": {
        "keyframes": {
            "size": (16, 5), "map": _AFA_KEY_MAP, "pixels": 90,
            "copies": ((71, 7), (72, 20)),
        },
    },
    "80": {
        "keyframes": {"size": (18, 7), "map": _RELIC_KEY_SOURCE_MAP, "pixels": 90},
        "spotlight_frames": {"size": (18, 7), "map": _RELIC_EDGE_MAP, "pixels": 24},
    },
}


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


def _led_model(product_id: str) -> str:
    upper = product_id.upper()
    if upper in {"AM21", "80"}:
        return "80"
    if upper == "ALICE":
        return "ALICE"
    if upper.startswith("CB"):
        return "CB"
    raise ValueError(f"No GIF LED map is available for product {product_id or '?'}.")


def firmware_led_speed(duration_ms: int) -> int:
    """Nearest timing step the Angry Miao firmware/configurator exposes."""
    duration = max(1, int(duration_ms))
    return min(_LED_SPEEDS_MS, key=lambda speed: (abs(speed - duration), speed))


def _gif_timeline_indices(durations: list[int]) -> tuple[list[int], int, bool]:
    """Map variable GIF delays onto one supported device-wide frame duration."""
    clean = [max(10, int(duration or 90)) for duration in durations]
    if not clean:
        return [0], 90, False
    variable = len(set(clean)) > 1
    if not variable:
        return list(range(len(clean))), firmware_led_speed(clean[0]), False

    common = clean[0]
    for duration in clean[1:]:
        common = math.gcd(common, duration)
    speed = firmware_led_speed(common)
    total = sum(clean)
    if math.ceil(total / speed) > _MAX_GIF_FRAMES:
        fitting = [
            candidate
            for candidate in sorted(_LED_SPEEDS_MS)
            if math.ceil(total / candidate) <= _MAX_GIF_FRAMES
        ]
        speed = fitting[0] if fitting else max(_LED_SPEEDS_MS)

    output_count = min(_MAX_GIF_FRAMES, max(1, math.ceil(total / speed)))
    indices: list[int] = []
    source_index = 0
    boundary = clean[0]
    for output_index in range(output_count):
        timestamp = min(total - 1, output_index * speed)
        while source_index < len(clean) - 1 and timestamp >= boundary:
            source_index += 1
            boundary += clean[source_index]
        indices.append(source_index)
    return indices, speed, True


def gif_to_led_tracks(
    payload: bytes,
    targets: list[str] | tuple[str, ...],
    resample: str = "box",
    product_id: str = "CB_XX",
) -> dict[str, Any]:
    """Decode a GIF once and map each frame onto one or more LED tracks."""
    model = _led_model(product_id)
    requested = list(dict.fromkeys(str(target) for target in targets))
    if not requested:
        raise ValueError("At least one GIF LED target is required.")
    layouts: dict[str, dict[str, Any]] = {}
    for target in requested:
        layout = _GIF_LAYOUTS[model].get(target)
        if layout is None:
            supported = ", ".join(_GIF_LAYOUTS[model])
            raise ValueError(
                f"{product_id} does not support GIF target {target}; use {supported}."
            )
        layouts[target] = layout
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
            frame_count = min(source_frames, _MAX_GIF_FRAMES)
            filters = {
                "nearest": Image.Resampling.NEAREST,
                "box": Image.Resampling.BOX,
                "lanczos": Image.Resampling.LANCZOS,
            }
            track_frames: dict[str, list[list[str]]] = {
                target: [] for target in requested
            }
            durations: list[int] = []
            for index in range(frame_count):
                image.seek(index)
                durations.append(max(10, int(image.info.get("duration") or 90)))
                rgba = image.convert("RGBA")
                black = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
                rgb = Image.alpha_composite(black, rgba).convert("RGB")
                raster_colors: dict[tuple[int, int], list[str]] = {}
                for layout in layouts.values():
                    width, height = layout["size"]
                    size = (width, height)
                    if size not in raster_colors:
                        fitted = rgb
                        source_ratio = fitted.width / fitted.height
                        target_ratio = width / height
                        if source_ratio > target_ratio:
                            crop_width = max(1, round(fitted.height * target_ratio))
                            left = (fitted.width - crop_width) // 2
                            fitted = fitted.crop((left, 0, left + crop_width, fitted.height))
                        elif source_ratio < target_ratio:
                            crop_height = max(1, round(fitted.width / target_ratio))
                            top = (fitted.height - crop_height) // 2
                            fitted = fitted.crop((0, top, fitted.width, top + crop_height))
                        if fitted.size != size:
                            fitted = fitted.resize(size, filters[resample])
                        pixels = (
                            fitted.get_flattened_data()
                            if hasattr(fitted, "get_flattened_data") else fitted.getdata()
                        )
                        raster_colors[size] = [
                            f"#{red:02X}{green:02X}{blue:02X}"
                            for red, green, blue in pixels
                        ]

                for target, layout in layouts.items():
                    source_colors = raster_colors[layout["size"]]
                    colors = ["#000000"] * int(layout["pixels"])
                    for source_index, output_index in enumerate(layout["map"]):
                        if output_index >= 0:
                            colors[output_index] = source_colors[source_index]
                    for output_index, source_index in layout.get("copies", ()):
                        colors[output_index] = colors[source_index]
                    track_frames[target].append(colors)
    except UnidentifiedImageError as exc:
        raise ValueError("The selected file is not a readable GIF.") from exc
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"Could not decode GIF: {exc}") from exc

    if not track_frames or not next(iter(track_frames.values())):
        raise ValueError("The GIF contains no frames.")
    timeline, duration, timing_resampled = _gif_timeline_indices(durations)
    tracks = {}
    for target, layout in layouts.items():
        frames = [track_frames[target][index] for index in timeline]
        width, height = layout["size"]
        tracks[target] = {
            "frames": frames,
            "frame_count": len(frames),
            "width": width,
            "height": height,
            "pixels": int(layout["pixels"]),
            "mapped_pixels": len({index for index in layout["map"] if index >= 0}),
        }
    return {
        "tracks": tracks,
        "source_frames": source_frames,
        "decoded_frames": frame_count,
        "duration_ms": duration,
        "source_duration_ms": sum(durations),
        "timing_resampled": timing_resampled,
        "model": model,
    }


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
    device = device_id.upper()
    config = config_id.upper()
    if config == "80":
        return device == "AM21"
    if config == "ALICE":
        return device == "ALICE"
    if config.startswith("CB"):
        return device.startswith("CB")
    return device == config


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
    from . import device

    device = None
    for attempt in range(attempts):
        try:
            device = device.probe(port, full=True)
        except OSError:
            device = None
        if device and device.is_keyboard:
            return device
        if attempt + 1 < attempts:
            time.sleep(0.2)
    return device


class _State:
    def __init__(self, config: dict[str, Any] | None, token: str) -> None:
        self.config = config
        self.token = token
        self.device_lock = threading.Lock()
        self.last_device_scan = 0.0

    def settle_after_scan(self, seconds: float = 1.5) -> None:
        remaining = seconds - (time.monotonic() - self.last_device_scan)
        if remaining > 0:
            time.sleep(remaining)


class _Handler(BaseHTTPRequestHandler):
    server_version = "AMConfigurator/0.1"

    @property
    def state(self) -> _State:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep launch output useful; successful static requests are noise.
        if args and str(args[1]) not in {"200", "304"}:
            super().log_message(fmt, *args)

    def _headers(self, status: int, content_type: str, length: int) -> None:
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
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _json(self, value: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(payload))
        self.wfile.write(payload)

    def _authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-AM-Token", ""), self.state.token)

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

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            if not self._authorized():
                self._json({"error": "Unauthorized local request."}, HTTPStatus.FORBIDDEN)
                return
            try:
                if path == "/api/config":
                    self._json({"config": self.state.config})
                elif path == "/api/devices":
                    from . import device

                    with self.state.device_lock:
                        devices = device.list_devices(full=True)
                        self.state.last_device_scan = time.monotonic()
                    self._json({"devices": [asdict(d) for d in devices]})
                else:
                    self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001 - API boundary
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
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
            elif path == "/api/device/read":
                self._read_device(body)
            elif path == "/api/device/write":
                self._write_device(body)
            elif path == "/api/device/verify":
                self._verify_device_write(body)
            else:
                self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
        except AcceptedWriteError as exc:
            self._json(
                {"error": str(exc), "accepted": True, "retryable": True},
                HTTPStatus.CONFLICT,
            )
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - API boundary
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

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

    def _read_device(self, body: dict[str, Any]) -> None:
        from . import macros
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
            macros = macros.read_macros(port)
        stored_config, stored_warning = _stored_device_config(device.product_id or "")
        self._json({
            "device": asdict(device),
            "layers": key_layers,
            "macros": macros,
            "macro_references": _macro_references(key_layers),
            "blank_config": blank_config(device.product_id or "", key_layers, macros),
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
        expected_macros = [
            {
                "original_key": macro["original_key"].upper(),
                "layer_key": [code.upper() for code in macro.get("layer_key", [])],
                "intvel_ms": _padded_macro_delays(macro),
            }
            for macro in config.get("macro_key", [])
        ]
        # JSON_START replaces the device config. Restore the separately-addressed
        # macro table immediately after its ACK, before a potentially transient
        # keymap read-back can abort verification. The verify-only endpoint never
        # writes; it only checks what the accepted write left on the device.
        if install_macros:
            macros.write_macros(port, expected_macros)
            time.sleep(0.25)

        _verify_keymap_readback(port, expected_layers)
        read_macros = macros.read_macros(port)
        if read_macros != expected_macros:
            raise AcceptedWriteError(
                "Device accepted the configuration and its keymap verified, but macro "
                "read-back did not match. Retry verification instead of sending the "
                "full configuration again."
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
        self.state.config = copy.deepcopy(clean)
        return {
            "ok": True,
            "device": asdict(after),
            "frames": frame_total,
            "macros": len(expected_macros),
            "snapshot": snapshot.stem,
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


def create_server(
    config_paths: list[str] | None = None,
    *,
    port: int = 0,
) -> tuple[_Server, str]:
    """Create the loopback configurator server without starting its event loop."""
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
    state = _State(merge_configs(configs), token)
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
