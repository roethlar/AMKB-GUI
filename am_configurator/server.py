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
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Sequence
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__


_PKG = Path(__file__).resolve().parent
_ASSETS = _PKG / "web"
_STATIC = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/lighting_state.js": "lighting_state.js",
    "/icon.png": "icon.png",
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
_MACRO_EVENTS_PER_BLOCK = 8
_CYBERBOARD_MACRO_READBACK_BLOCKS = 15

# xAI models-list endpoint (GET), used only for the no-cost "Test key" check.
# Pinned like the generation endpoints in ``llm.py`` (``XAI_RESPONSES_URL`` /
# ``XAI_IMAGES_URL``); bumping it is a deliberate one-line change. The paid
# generation calls flow through ``llm._xai_request`` (POST); this cheap GET probe
# lives here because that transport is POST-only.
_XAI_MODELS_URL = "https://api.x.ai/v1/language-models"
_SETTINGS_TEST_TIMEOUT = 20.0
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
# ProviderError.code -> local HTTP status (design §Typed errors). Shared by the
# settings key-test endpoint; the generation job endpoints reuse it in Task 9.
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
# CyberBoard profile JSON stores the 40x5 display in raster order:
# index = y * 40 + x.  Angry Miao's editor uses a column-major array while
# painting, then transposes it back to this row-major shape during export.
# GIF pixels from Pillow are already row-major, so preserve their order.
_CB_DISPLAY_MAP = tuple(range(200))
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


def frames_to_led_tracks(
    images: Sequence[Image.Image],
    durations_ms: Sequence[int],
    targets: list[str] | tuple[str, ...],
    resample: str = "box",
    product_id: str = "CB_XX",
) -> dict[str, Any]:
    """Map an ordered list of frames onto one or more LED tracks.

    This is the shared mapping core for both the GIF import path (via
    ``gif_to_led_tracks``) and the LLM generation path. It owns alpha
    flattening, aspect-fit cropping, resampling, hex conversion, the per-target
    firmware-index remap, the ``_MAX_GIF_FRAMES`` limit, and timeline
    normalization. Callers that already know a decode-specific frame count
    (e.g. GIF ``n_frames``) override ``source_frames``/``decoded_frames`` in the
    returned dict.
    """
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
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise ValueError(
            "GIF import needs Pillow. Reinstall AM Configurator."
        ) from exc

    frames = list(images)[:_MAX_GIF_FRAMES]
    if not frames:
        raise ValueError("The GIF contains no frames.")
    raw_durations = list(durations_ms)[:_MAX_GIF_FRAMES]
    filters = {
        "nearest": Image.Resampling.NEAREST,
        "box": Image.Resampling.BOX,
        "lanczos": Image.Resampling.LANCZOS,
    }
    track_frames: dict[str, list[list[str]]] = {target: [] for target in requested}
    durations: list[int] = []
    for index, frame in enumerate(frames):
        source_duration = raw_durations[index] if index < len(raw_durations) else None
        durations.append(max(10, int(source_duration or 90)))
        rgba = frame.convert("RGBA")
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

    timeline, duration, timing_resampled = _gif_timeline_indices(durations)
    tracks = {}
    for target, layout in layouts.items():
        mapped = [track_frames[target][index] for index in timeline]
        width, height = layout["size"]
        tracks[target] = {
            "frames": mapped,
            "frame_count": len(mapped),
            "width": width,
            "height": height,
            "pixels": int(layout["pixels"]),
            "mapped_pixels": len({index for index in layout["map"] if index >= 0}),
        }
    return {
        "tracks": tracks,
        "source_frames": len(frames),
        "decoded_frames": len(frames),
        "duration_ms": duration,
        "source_duration_ms": sum(durations),
        "timing_resampled": timing_resampled,
        "model": model,
    }


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
    for target in requested:
        if _GIF_LAYOUTS[model].get(target) is None:
            supported = ", ".join(_GIF_LAYOUTS[model])
            raise ValueError(
                f"{product_id} does not support GIF target {target}; use {supported}."
            )
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

    result = frames_to_led_tracks(images, durations, requested, resample, product_id)
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


def _xai_get(url: str, payload: Any, api_key: str, deadline: float) -> dict[str, Any]:
    """Validate an xAI API key with one no-cost GET, mapping failures to
    ``llm.ProviderError`` exactly like the paid POST transport.

    Same four-argument transport contract as ``llm._xai_request`` (``payload`` is
    unused for a GET) so ``_State.llm_transport`` can hold this real probe or a
    fake injected by tests. The bounded read guards an oversized body and the API
    key is redacted from every error message via ``llm``'s helpers.
    """
    from . import llm

    if (
        not isinstance(api_key, str)
        or not api_key
        or api_key != api_key.strip()
        or any(ord(character) < 33 or ord(character) == 127 for character in api_key)
    ):
        raise llm.ProviderError(
            "auth", "provider could not use this API key; check the key in Settings"
        )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise llm.ProviderError(
            "timeout", "provider deadline exceeded before the key check"
        )
    request = urllib.request.Request(
        url, method="GET", headers={"Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=min(remaining, _SETTINGS_TEST_TIMEOUT)
        ) as response:
            response.read(llm.MAX_PROVIDER_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        code = exc.code
        retry_after = llm._parse_retry_after(exc.headers.get("Retry-After"))
        if code in (401, 403):
            raise llm.ProviderError(
                "auth", "provider rejected the API key; check the key in Settings"
            ) from exc
        if code == 429:
            raise llm.ProviderError(
                "rate_limited",
                "provider rate limit reached; retry later",
                retry_after=retry_after,
            ) from exc
        if 500 <= code <= 599:
            raise llm.ProviderError(
                "unavailable", f"provider is temporarily unavailable (HTTP {code})"
            ) from exc
        raise llm.ProviderError(
            "bad_response", f"provider returned an unexpected status (HTTP {code})"
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            raise llm.ProviderError(
                "timeout", llm._redact(f"provider request timed out: {exc}", api_key)
            ) from exc
        raise llm.ProviderError(
            "offline", llm._redact(f"could not reach the provider: {exc}", api_key)
        ) from exc
    except OSError as exc:
        raise llm.ProviderError(
            "offline", llm._redact(f"could not reach the provider: {exc}", api_key)
        ) from exc
    return {"ok": True}


def _settings_view() -> dict[str, Any]:
    """Load app settings for the browser with every API key masked.

    The raw key never leaves the server: each known key provider reports only
    ``{"set": bool, "last4": str}``, derived from the effective key (the
    ``XAI_API_KEY`` env override or the stored value) so the UI can show whether
    a usable key is present without ever receiving it.
    """
    from . import llm, store

    settings = store.load_settings()
    keys: dict[str, Any] = {}
    for provider in llm.KEY_PROVIDERS:
        if provider == "xai":
            effective = store.resolve_xai_key()
        else:  # pragma: no cover - single provider today; kept general for follow-ups
            effective = settings["llm"]["keys"].get(provider) or None
        keys[provider] = {
            "set": bool(effective),
            # Never let a short malformed/test key escape in full merely
            # because its entire value fits inside the last-four display.
            "last4": effective[-4:] if effective and len(effective) > 4 else "",
        }
    return {
        "schema_version": settings["schema_version"],
        "llm": {
            "models": dict(settings["llm"]["models"]),
            "keys": keys,
            # Temporary aliases for the unchanged settings dialog. Model IDs
            # are separate v2 preferences; the legacy provider registries still
            # contain only the xAI-backed ``grok`` implementation.
            "interpreter": "grok",
            "renderer": "grok",
        },
        "library": {
            "current_root": settings["library"]["current_root"],
            "roots": list(settings["library"]["roots"]),
        },
        "generation": dict(settings["generation"]),
    }


def _capabilities() -> dict[str, Any]:
    """Provider/model/target capabilities for the UI — the single source of truth.

    Targets are derived from ``_GIF_LAYOUTS``: targets on the same raster size can
    be generated together (each lists the others as ``extra_targets``, e.g. the
    Relic per-key/spotlight pair), while a model whose targets span more than one
    raster is ``single_target`` (the single-CyberBoard-target rule).
    """
    from . import ai_catalog, llm

    targets: dict[str, Any] = {}
    for model, layouts in _GIF_LAYOUTS.items():
        sizes = {tuple(layout["size"]) for layout in layouts.values()}
        entries = []
        for name, layout in layouts.items():
            width, height = layout["size"]
            extra = [
                other
                for other, other_layout in layouts.items()
                if other != name and tuple(other_layout["size"]) == (width, height)
            ]
            entries.append({
                "name": name,
                "width": width,
                "height": height,
                "pixels": int(layout["pixels"]),
                "extra_targets": extra,
            })
        targets[model] = {"single_target": len(sizes) > 1, "targets": entries}
    return {
        "ai_catalog": ai_catalog.catalog_view(),
        "privacy_disclosure_version": ai_catalog.PRIVACY_DISCLOSURE_VERSION,
        "providers": {
            "interpreters": list(llm.INTERPRETER_PROVIDERS),
            "renderers": list(llm.RENDERER_PROVIDERS),
            "keys": list(llm.KEY_PROVIDERS),
        },
        "models": dict(llm.XAI_MODELS),
        "model_frame_caps": dict(llm.MODEL_FRAME_CAPS),
        "max_rendered_keyframes": llm.MAX_RENDERED_KEYFRAMES,
        "targets": targets,
    }


def generation_spec(
    product_id: str,
    targets: list[str] | tuple[str, ...],
    frame_count: int | None,
) -> tuple[Any, list[str]]:
    """Build the per-generation ``llm.RasterSpec`` from ``_GIF_LAYOUTS``.

    Validates the product and every requested target the same way
    ``frames_to_led_tracks`` does, then enforces the single-raster rule: all
    requested targets must share one raster size (the single-CyberBoard-target
    rule falls out of this, since CB's two targets are different rasters). The
    first target is the spec's primary ``target`` and the rest become
    ``extra_targets`` (e.g. the Relic per-key/spotlight pair on one raster).

    ``mapped_positions`` is set only for genuinely sparse targets — where the
    union of visible source positions covers at most half the raster (the Relic
    spotlight edges), so the interpreter prompt can steer content onto them —
    and is ``None`` for dense targets. ``max_frames`` is the per-model firmware
    cap, lowered to a supplied ``frame_count`` (clamped into ``1..cap``) so a
    user-chosen frame count acts as the ceiling the interpreter plans within.
    Raises ``ValueError`` (mapped to HTTP 400 by the caller) on any bad input.
    Returns the spec plus the de-duplicated target list to map through.
    """
    from . import llm

    model = _led_model(product_id)
    requested = list(dict.fromkeys(str(target) for target in targets))
    if not requested:
        raise ValueError("At least one LED generation target is required.")
    layouts: dict[str, dict[str, Any]] = {}
    for target in requested:
        layout = _GIF_LAYOUTS[model].get(target)
        if layout is None:
            supported = ", ".join(_GIF_LAYOUTS[model])
            raise ValueError(
                f"{product_id} does not support LED target {target}; use {supported}."
            )
        layouts[target] = layout
    sizes = {tuple(layout["size"]) for layout in layouts.values()}
    if len(sizes) > 1:
        raise ValueError(
            "These LED targets use different rasters and cannot be generated "
            "together; generate one target at a time."
        )
    width, height = next(iter(sizes))

    cap = llm.MODEL_FRAME_CAPS[model]
    if frame_count is None:
        max_frames = cap
    else:
        max_frames = max(1, min(int(frame_count), cap))

    visible: set[tuple[int, int]] = set()
    for layout in layouts.values():
        layout_width = int(layout["size"][0])
        for source_index, output_index in enumerate(layout["map"]):
            if output_index >= 0:
                visible.add((source_index % layout_width, source_index // layout_width))
    mapped_positions: tuple[tuple[int, int], ...] | None = None
    if visible and len(visible) * 2 <= width * height:
        mapped_positions = tuple(sorted(visible))

    primary = requested[0]
    output_len = len({index for index in layouts[primary]["map"] if index >= 0})
    spec = llm.RasterSpec(
        model=model,
        target=primary,
        extra_targets=tuple(requested[1:]),
        width=width,
        height=height,
        mapped_positions=mapped_positions,
        output_len=output_len,
        max_frames=max_frames,
    )
    return spec, requested


# Compatibility alias for the legacy endpoint/tests until Task 16 removes it.
_generation_spec = generation_spec


def _default_llm_factories() -> dict[str, Any]:
    """Resolve the legacy interpreter/renderer provider implementations.

    Returns the ``{"interpreter", "renderer"}`` factory map ``generate_effect``
    expects. Curated v2 values are model IDs, not registry keys; the superseded
    generator continues using its sole ``grok`` providers until Task 16 removes
    it. Tests inject their own map via ``_State.llm_factories``.
    """
    from . import llm

    interpreter_cls = llm.INTERPRETERS["grok"]
    renderer_cls = llm.RENDERERS["grok"]
    return {
        "interpreter": lambda api_key: interpreter_cls(api_key),
        "renderer": lambda api_key: renderer_cls(api_key),
    }


class _State:
    def __init__(
        self,
        config: dict[str, Any] | None,
        token: str,
        llm_transport: Any = None,
        llm_factories: dict[str, Any] | None = None,
        lighting_library: Any = None,
        lighting_coordinator: Any = None,
        lighting_dependencies: dict[str, Any] | None = None,
    ) -> None:
        if (lighting_library is None) != (lighting_coordinator is None):
            raise ValueError(
                "lighting_library and lighting_coordinator must be injected together"
            )
        self.config = config
        self.token = token
        self.device_lock = threading.Lock()
        self.last_device_scan = 0.0
        # xAI key-check transport (``(url, payload, api_key, deadline) -> dict``,
        # the ``llm._xai_request`` contract). ``None`` uses the real ``_xai_get``
        # GET probe; tests inject a fake so no request ever leaves the machine.
        self.llm_transport = llm_transport
        # Interpreter/renderer factory map for ``llm.generate_effect``. ``None``
        # resolves the real registry classes via ``_default_llm_factories``;
        # tests inject fakes so no request ever leaves the machine.
        self.llm_factories = llm_factories
        # Native desktop builds attach a narrow chooser/reveal bridge after
        # creating the loopback server. Browser-only launches leave it unset.
        self.desktop_bridge: Any = None
        self._lighting_lock = threading.Lock()
        self._lighting_library = lighting_library
        self._lighting_coordinator = lighting_coordinator
        self._lighting_dependencies = dict(lighting_dependencies or {})
        from .generation import _PROCESS_OPERATION_GATE

        self._generation_gate = self._lighting_dependencies.get(
            "operation_gate", _PROCESS_OPERATION_GATE
        )
        self._lighting_root_signature: tuple[Any, ...] | None = None
        self._lighting_reconcile_signature: tuple[int, bytes | None] | None = None
        self._lighting_reconcile_pending = False
        self._lighting_reconcile_worker: threading.Thread | None = None
        # Single-flight generation worker. Only one job runs at a time; the job
        # dict (id/phase/status/cancel/result/error) is held until read or
        # replaced by the next start. Guarded by ``_job_lock``.
        self._job_lock = threading.Lock()
        self._job: dict[str, Any] | None = None
        self._worker: threading.Thread | None = None

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
            if (
                self._lighting_library is not None
                and (self._lighting_root_signature == signature or active is not None)
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
        api_key = store.resolve_xai_key()
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
            return coordinator.reconcile_startup(api_key=api_key)
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

    def start_generation(self, run: Any) -> str | None:
        """Start ``run(job)`` on the worker thread, or ``None`` if one is busy.

        Enforces single-flight: a start is refused (returns ``None`` → HTTP 409)
        while a previous job is still ``running``. The returned job id lets the
        caller poll status. ``run`` is the closure that performs the generation
        and must call :meth:`finish_generation` exactly once when it ends.
        """
        from .generation import GenerationBusyError

        with self._job_lock:
            if self._job is not None and self._job["status"] == "running":
                return None
            job_id = secrets.token_urlsafe(18)
            try:
                operation_token, cancelled = self._generation_gate.begin(job_id)
            except GenerationBusyError:
                return None
            job: dict[str, Any] = {
                "id": job_id,
                "phase": "starting",
                "status": "running",
                "cancel": cancelled,
                "result": None,
                "error": None,
            }

            def guarded_run() -> None:
                try:
                    run(job)
                finally:
                    self._generation_gate.finish(operation_token)

            self._job = job
            self._worker = threading.Thread(
                target=guarded_run, name="am-led-generation", daemon=True
            )
            try:
                self._worker.start()
            except BaseException:
                self._job = None
                self._worker = None
                self._generation_gate.finish(operation_token)
                raise
            return job_id

    def finish_generation(
        self,
        job: dict[str, Any],
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Record a job's terminal outcome (``done`` / ``cancelled`` / ``error``)."""
        with self._job_lock:
            job["status"] = status
            job["phase"] = status
            job["result"] = result
            job["error"] = error

    def generation_status(self, job_id: str | None) -> dict[str, Any] | None:
        """Snapshot the named job, or ``None`` if it is unknown or has been replaced."""
        with self._job_lock:
            job = self._job
            if job is None or not job_id or job["id"] != job_id:
                return None
            return {
                "status": job["status"],
                "phase": job["phase"],
                "result": job["result"],
                "error": job["error"],
            }

    def cancel_generation(self, job_id: str | None = None) -> bool:
        """Flag the current running job for cancellation; ``True`` if one was flagged.

        With no ``job_id`` the current job is targeted (the single-flight case);
        a mismatched id or a job that is not running is a no-op returning ``False``.
        """
        with self._job_lock:
            job = self._job
            if job is None or job["status"] != "running":
                return False
            if job_id is not None and job["id"] != job_id:
                return False
            job["cancel"].set()
            return True

    def join_generation(self, timeout: float = 5.0) -> None:
        """Join the generation worker thread (test synchronization helper)."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout)


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

    def _lighting_error(self, exc: Exception) -> bool:
        from . import llm
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

    def _lighting_internal_error(self, exc: Exception) -> None:
        # Keep unexpected dependency and filesystem details on the local
        # process boundary. In particular, OSError text may contain the user's
        # absolute library path and must never become browser-visible JSON.
        self.log_error("Unhandled Lighting request error: %s", type(exc).__name__)
        self._json(
            {"error": "The Lighting request failed unexpectedly."},
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

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
                elif path == "/api/settings":
                    self._json(_settings_view())
                elif path == "/api/led/capabilities":
                    self._json(_capabilities())
                elif path.startswith("/api/lighting/"):
                    self._lighting_get(path, urlparse(self.path).query)
                elif path == "/api/led/generate/status":
                    self._generation_status(urlparse(self.path).query)
                else:
                    self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001 - API boundary
                if path.startswith("/api/lighting/"):
                    if not self._lighting_error(exc):
                        self._lighting_internal_error(exc)
                else:
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
            elif path == "/api/settings":
                self._save_settings(body)
            elif path == "/api/settings/key":
                self._save_settings_key(body)
            elif path == "/api/settings/preferences":
                self._save_settings_preferences(body)
            elif path == "/api/settings/library":
                self._save_settings_library(body)
            elif path == "/api/settings/privacy":
                self._save_settings_privacy(body)
            elif path == "/api/settings/test":
                self._test_settings_key(body)
            elif path == "/api/native/choose-library":
                self._native_choose_library(body)
            elif path == "/api/native/reveal-library":
                self._native_reveal_library(body)
            elif path == "/api/lighting/concepts" or path.startswith(
                "/api/lighting/jobs/"
            ):
                self._lighting_post(path, body)
            elif path == "/api/led/generate":
                self._start_generation(body)
            elif path == "/api/led/generate/cancel":
                self._cancel_generation(body)
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
            if path.startswith("/api/lighting/"):
                if not self._lighting_error(exc):
                    self._lighting_internal_error(exc)
            else:
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

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

    @staticmethod
    def _lighting_settings(*, require_key: bool) -> tuple[dict, str, bool]:
        from . import ai_catalog, store

        settings = store.load_settings()
        key = store.resolve_xai_key() or ""
        acknowledged = (
            settings["generation"]["privacy_ack_version"]
            == ai_catalog.PRIVACY_DISCLOSURE_VERSION
            and isinstance(settings["generation"]["privacy_ack_at"], str)
        )
        if require_key and not key:
            raise ValueError("Add an xAI API key in Settings before generation.")
        if require_key and not acknowledged:
            raise ValueError(
                "Acknowledge the current xAI privacy disclosure in Settings before generation."
            )
        return settings, key, acknowledged

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
        spec, resolved = generation_spec(product_id, targets, None)
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
            self._strict_body(
                body,
                allowed={
                    "prompt",
                    "product_id",
                    "targets",
                    "candidate_count",
                    "loop_mode",
                },
                required={"prompt", "product_id", "targets"},
            )
            settings, key, acknowledged = self._lighting_settings(require_key=True)
            candidate_count = body.get(
                "candidate_count", settings["generation"]["candidate_count"]
            )
            loop_mode = body.get("loop_mode", settings["generation"]["loop_mode"])
            manifest = coordinator.start_concepts(
                prompt=body["prompt"],
                candidate_count=candidate_count,
                target=self._lighting_target(body["product_id"], body["targets"]),
                models=settings["llm"]["models"],
                loop_mode=loop_mode,
                api_key=key,
                privacy_acknowledged=acknowledged,
            )
            self._json({"job_id": manifest["job_id"]}, HTTPStatus.ACCEPTED)
            return

        parts = path.strip("/").split("/")
        if len(parts) != 5 or parts[:3] != ["api", "lighting", "jobs"]:
            self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        job_id, action = parts[3], parts[4]
        # Resolve through the manifest boundary before any coordinator action;
        # this validates canonical IDs and historical-root ownership uniformly.
        library.load_manifest(job_id)
        if action == "concepts":
            self._strict_body(body, allowed={"candidate_count"})
            settings, key, acknowledged = self._lighting_settings(require_key=True)
            manifest = coordinator.more_like_this(
                job_id,
                candidate_count=body.get(
                    "candidate_count", settings["generation"]["candidate_count"]
                ),
                api_key=key,
                privacy_acknowledged=acknowledged,
            )
            status = HTTPStatus.ACCEPTED
        elif action == "animate":
            self._strict_body(
                body,
                allowed={"candidate_id", "motion", "loop_mode"},
                required={"candidate_id"},
            )
            settings, key, acknowledged = self._lighting_settings(require_key=True)
            manifest = coordinator.start_animation(
                job_id,
                candidate_id=body["candidate_id"],
                motion=body.get("motion"),
                loop_mode=body.get(
                    "loop_mode", settings["generation"]["loop_mode"]
                ),
                api_key=key,
                privacy_acknowledged=acknowledged,
            )
            status = HTTPStatus.ACCEPTED
        elif action == "process":
            self._strict_body(body, allowed=set())
            manifest = coordinator.retry_local(job_id)
            status = HTTPStatus.ACCEPTED
        elif action == "cancel":
            self._strict_body(body, allowed=set())
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

    def _save_settings(self, body: dict[str, Any]) -> None:
        """Temporary whole-object compatibility route for the current UI.

        It accepts only the legacy provider/key shape and changes only the key;
        all v2 preferences survive. The split routes below are canonical.
        """
        from . import store

        if "schema_version" in body:
            raise ValueError(
                "The legacy settings route accepts provider key changes only."
            )
        store.save_settings(body)
        self.state.reconcile_lighting(force=True)
        self._json(_settings_view())

    def _save_settings_key(self, body: dict[str, Any]) -> None:
        from . import store

        store.update_api_key(body)
        self.state.reconcile_lighting(force=True)
        self._json(_settings_view())

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

    def _test_settings_key(self, body: dict[str, Any]) -> None:
        """No-cost xAI key check: one models-list request through the transport.

        Uses the effective key (``store.resolve_xai_key``); no key → 400 with a
        Settings hint before any request. Typed provider failures map to their
        design HTTP status (auth→400, rate_limited→429 with ``retry_after``,
        timeout→504, offline→503, bad_response/unavailable→502).
        """
        from . import llm, store

        key = store.resolve_xai_key()
        if not key:
            raise ValueError(
                "No xAI API key is configured. Add your key in Settings, then test it."
            )
        transport = self.state.llm_transport or _xai_get
        deadline = time.monotonic() + _SETTINGS_TEST_TIMEOUT
        try:
            transport(_XAI_MODELS_URL, None, key, deadline)
        except llm.ProviderError as exc:
            status = _PROVIDER_ERROR_HTTP.get(exc.code, HTTPStatus.BAD_GATEWAY)
            payload: dict[str, Any] = {"ok": False, "code": exc.code, "error": exc.message}
            if exc.retry_after is not None:
                payload["retry_after"] = exc.retry_after
            self._json(payload, status)
            return
        self._json({"ok": True})

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
        except Exception:  # noqa: BLE001 - native UI boundary
            self._json(
                {"error": "The native folder chooser could not be opened."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
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

    def _start_generation(self, body: dict[str, Any]) -> None:
        """Validate a generation request and start the single-flight worker.

        Validation happens synchronously and up front (design §3): the prompt,
        the product/target raster (via :func:`_generation_spec`, which enforces
        the single-CyberBoard-target rule and clamps ``frame_count``), then the
        configured key — each a ``ValueError`` mapped to HTTP 400 by ``do_POST``,
        so no provider is ever contacted for a malformed request or a missing
        key. Only then does a background job start; a second start while one is
        running returns 409. The paid work runs on the worker thread; this
        handler returns ``{"job_id"}`` immediately.
        """
        from . import llm, store

        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("A prompt describing the effect is required.")
        product_id = str(body.get("product_id") or "")
        targets = body.get("targets")
        if (
            not isinstance(targets, list)
            or not targets
            or not all(isinstance(target, str) for target in targets)
        ):
            raise ValueError(
                "Generation targets must be a non-empty list of LED track names."
            )
        frame_count = body.get("frame_count")
        if frame_count is not None and (
            isinstance(frame_count, bool) or not isinstance(frame_count, int)
        ):
            raise ValueError("frame_count must be an integer when supplied.")

        spec, resolved_targets = _generation_spec(product_id, targets, frame_count)

        key = store.resolve_xai_key()
        if not key:
            raise ValueError(
                "No xAI API key is configured. Add your key in Settings, then generate."
            )
        factories = self.state.llm_factories or _default_llm_factories()
        state = self.state

        def run(job: dict[str, Any]) -> None:
            def progress(phase: str) -> None:
                job["phase"] = phase

            def cancelled() -> bool:
                return job["cancel"].is_set()

            try:
                result = llm.generate_effect(
                    prompt, spec, resolved_targets, product_id, key, factories,
                    progress, cancelled,
                )
            except llm.Cancelled:
                state.finish_generation(job, status="cancelled")
            except llm.ProviderError as exc:
                state.finish_generation(job, status="error", error=exc)
            except Exception as exc:  # noqa: BLE001 - surfaced as a job error
                state.finish_generation(job, status="error", error=exc)
            else:
                state.finish_generation(job, status="done", result=result)

        job_id = self.state.start_generation(run)
        if job_id is None:
            self._json(
                {
                    "error": "A generation is already running. Wait for it to "
                    "finish or cancel it."
                },
                HTTPStatus.CONFLICT,
            )
            return
        self._json({"job_id": job_id})

    def _generation_status(self, query: str) -> None:
        """Report a generation job's phase while running, or its outcome once done.

        A running job returns ``{"status": "running", "phase": ...}``; a finished
        job returns the full ``/api/led/gif``-shaped result merged with
        ``{"status": "done"}`` plus ``plan``/``usage``. Cancellation reports
        ``{"status": "cancelled"}``. A typed provider failure is mapped to its
        design HTTP status (auth→400, rate_limited→429 with ``retry_after``,
        timeout→504, offline→503, bad_response/unavailable→502); any other
        failure is a 500. An unknown or replaced job id is a 404.
        """
        from . import llm

        params = parse_qs(query)
        job_id = (params.get("job") or [None])[0]
        snapshot = self.state.generation_status(job_id)
        if snapshot is None:
            self._json({"error": "Unknown or expired generation job."}, HTTPStatus.NOT_FOUND)
            return
        status = snapshot["status"]
        if status == "running":
            self._json({"status": "running", "phase": snapshot["phase"]})
            return
        if status == "cancelled":
            self._json({"status": "cancelled"})
            return
        if status == "error":
            error = snapshot["error"]
            if isinstance(error, llm.ProviderError):
                http_status = _PROVIDER_ERROR_HTTP.get(error.code, HTTPStatus.BAD_GATEWAY)
                payload: dict[str, Any] = {
                    "status": "error", "code": error.code, "error": error.message,
                }
                if error.retry_after is not None:
                    payload["retry_after"] = error.retry_after
                self._json(payload, http_status)
            else:
                self._json(
                    {"status": "error", "error": str(error)},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            return
        payload = {"status": "done"}
        payload.update(snapshot["result"] or {})
        self._json(payload)

    def _cancel_generation(self, body: dict[str, Any]) -> None:
        """Flag the current generation for cancellation (honored between calls)."""
        job_id = body.get("job") if isinstance(body, dict) else None
        cancelled = self.state.cancel_generation(str(job_id) if job_id else None)
        self._json({"cancelled": bool(cancelled)})

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
        self.state.config = copy.deepcopy(clean)
        return {
            "ok": True,
            "device": asdict(after),
            "frames": frame_total,
            "macros": len(expected_macros),
            "macro_verification": macro_verification["status"],
            "macro_warning": macro_verification["warning"],
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
    llm_factories: dict[str, Any] | None = None,
    lighting_library: Any = None,
    lighting_coordinator: Any = None,
    lighting_dependencies: dict[str, Any] | None = None,
) -> tuple[_Server, str]:
    """Create the loopback configurator server without starting its event loop.

    ``llm_factories`` overrides the legacy interpreter/renderer factory map.
    Lighting tests may inject a complete ``lighting_library``/coordinator pair,
    or just ``lighting_dependencies`` for the production coordinator. These
    seams keep endpoint tests offline while production resolves real providers.
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
        llm_factories=llm_factories,
        lighting_library=lighting_library,
        lighting_coordinator=lighting_coordinator,
        lighting_dependencies=lighting_dependencies,
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
