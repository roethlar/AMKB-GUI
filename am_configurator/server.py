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
import re
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__, device_mapping, macro_text, transport


_PKG = Path(__file__).resolve().parent
_ASSETS = _PKG / "web"
_STATIC = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/lighting_review.js": "lighting_review.js",
    "/lighting_state.js": "lighting_state.js",
    "/lighting_targets.js": "lighting_targets.js",
    "/lighting_composer.js": "lighting_composer.js",
    "/library_state.js": "library_state.js",
    "/icon.png": "icon.png",
    "/style.css": "style.css",
}
_KEY_FIELDS = (
    "key_layer", "tab_key", "tab_key_num", "macro_key", "MACRO_key",
    "MACRO_key_num", "Fn_key", "Fn_key_num", "swap_key", "swap_key_num",
    "exchange_key", "exchange_num",
)
_MAX_GIF_BYTES = 12_000_000
_MAX_PROFILE_BYTES = 10_000_000
_KEYMAP_VERIFY_ATTEMPTS = 4
_KEYMAP_VERIFY_RETRY_SECONDS = 1.0
_MACRO_EVENTS_PER_BLOCK = 8
_CYBERBOARD_MACRO_READBACK_BLOCKS = 15

_MAX_ASSET_RANGE_BYTES = 8 * 1024 * 1024
_LIGHTING_ASSET_MIMES = frozenset(
    {
        "image/bmp",
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
    product_id = device_mapping.config_product_id(device_id)
    spec = device_mapping.spec_for_product(device_id)
    key_colors = spec.track_colors("keyframes")
    # `frames` and `keyframes` are emitted for every family regardless of what it
    # authors, which is how these profiles have always been shaped. Every *other*
    # authored track comes from the specification by name, so a family is not
    # limited to the track names this function happens to mention: a device
    # authoring, say, an axial and a head track gets both, correctly sized.
    extra_tracks = tuple(
        (track, spec.track_colors(track))
        for track in spec.authored_tracks
        if track not in ("frames", "keyframes")
    )

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
                    [{"frame_index": 0, "frame_RGB": ["#000000"] * key_colors}]
                    if custom else []
                ),
            },
        }
        if custom:
            for track, colors in extra_tracks:
                page[track] = {
                    "valid": 1,
                    "frame_num": 1,
                    "frame_data": [
                        {"frame_index": 0, "frame_RGB": ["#000000"] * colors}
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


def extract_importable_macros(
    config: Any,
    *,
    max_tracks: int = 32,
    max_events: int = 200,
) -> list[dict[str, Any]]:
    """Copy only modern macro definitions from another AM configuration."""
    if (
        isinstance(max_tracks, bool)
        or not isinstance(max_tracks, int)
        or max_tracks <= 0
        or isinstance(max_events, bool)
        or not isinstance(max_events, int)
        or max_events <= 0
    ):
        raise ValueError("The destination macro limits are invalid.")
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

    if len(source) > max_tracks:
        raise ValueError(
            f"The imported profile has {len(source)} macros; the destination "
            f"stores {max_tracks}."
        )

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
        if (
            raw_token[:2] != b"\x00\x95"
            or not 0x1500 <= usage < 0x1500 + max_tracks
        ):
            raise ValueError(
                f"Macro {position} names a slot outside the destination's "
                f"{max_tracks}-macro capacity."
            )
        if token in seen:
            raise ValueError(f"The source defines {token} more than once.")
        seen.add(token)

        events = [str(code).upper() for code in (macro.get("layer_key") or [])]
        delays = list(macro.get("intvel_ms") or [])
        if not events:
            raise ValueError(f"Macro {position} has no key events.")
        if len(events) > max_events or total_events + len(events) > max_events:
            raise ValueError(
                f"The imported macros exceed the {max_events}-event device limit."
            )
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


def _compatibility_section(
    status: str,
    reason_code: str,
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "status": status,
        "reason_code": reason_code,
        "detail": detail,
        "selected": status != "blocked",
        **extra,
    }


def _profile_layers(config: dict[str, Any]) -> list[list[str]] | None:
    key_layer = config.get("key_layer")
    if not isinstance(key_layer, dict):
        return []
    layer_data = key_layer.get("layer_data")
    if not isinstance(layer_data, list):
        return []
    layers: list[list[str]] = []
    for entry in layer_data:
        if not isinstance(entry, dict) or not isinstance(entry.get("layer"), list):
            return None
        layers.append(list(entry["layer"]))
    return layers


def _keymap_compatibility(
    source: dict[str, Any],
    source_descriptor: dict[str, Any],
    target_descriptor: dict[str, Any],
    *,
    source_keymap_signature: str | None = None,
) -> dict[str, Any]:
    layers = _profile_layers(source)
    if layers is None:
        return _compatibility_section(
            "blocked",
            "keymap_invalid",
            "The saved keymap section is malformed.",
        )
    if not layers:
        return _compatibility_section(
            "blocked",
            "section_absent",
            "The saved profile has no keymap layers.",
        )
    source_keymap = source_descriptor["keymap"]
    target_keymap = target_descriptor["keymap"]
    if source_keymap_signature is not None:
        if (
            not isinstance(source_keymap_signature, str)
            or not re.fullmatch(r"keymap:v1:[0-9a-f]{64}", source_keymap_signature)
        ):
            return _compatibility_section(
                "blocked",
                "source_layout_unknown",
                "The saved profile has no verified physical-layout evidence.",
            )
        source_signature = source_keymap_signature
    elif not source_keymap["layout_known"]:
        return _compatibility_section(
            "blocked",
            "source_layout_unknown",
            "The saved profile has no verified physical-layout evidence.",
        )
    else:
        source_signature = source_keymap["signature"]
    if not target_keymap["layout_known"]:
        return _compatibility_section(
            "blocked",
            "target_layout_unknown",
            "The destination has no verified physical-layout evidence.",
        )
    if source_signature != target_keymap["signature"]:
        return _compatibility_section(
            "blocked",
            "keymap_signature_mismatch",
            "The physical key layout or assignment encoding does not match.",
        )
    limits = target_descriptor["limits"]
    if len(layers) > limits["layers"]:
        return _compatibility_section(
            "blocked",
            "layer_capacity_exceeded",
            f"The profile has {len(layers)} layers; the destination stores "
            f"{limits['layers']}.",
            source_layers=len(layers),
            target_layers=limits["layers"],
        )
    for index, layer in enumerate(layers, 1):
        if len(layer) != limits["keys_per_layer"]:
            return _compatibility_section(
                "blocked",
                "keymap_invalid",
                f"Layer {index} does not contain exactly "
                f"{limits['keys_per_layer']} assignments.",
            )
        if any(not _key_code(code) for code in layer):
            return _compatibility_section(
                "blocked",
                "keymap_invalid",
                f"Layer {index} contains a malformed assignment.",
            )
    if limits["assignment_encoding"] == "qmk-vial16-v1":
        from . import vial_keymap

        unsupported = vial_keymap.unsupported_codes(layers)
        if unsupported:
            layer_index, key_index, code, reason = unsupported[0]
            return _compatibility_section(
                "blocked",
                "unsupported_assignment",
                f"{code} at layer {layer_index + 1}, matrix index {key_index} "
                f"cannot be written to this destination because {reason}.",
                unsupported_count=len(unsupported),
            )
    return _compatibility_section(
        "exact",
        "keymap_signature_match",
        "The physical layout and assignment encoding match exactly.",
        source_layers=len(layers),
        target_layers=limits["layers"],
    )


def _macro_compatibility(
    source: dict[str, Any],
    target_descriptor: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = source.get("macro_key")
    if not isinstance(raw, list) or not raw:
        return (
            _compatibility_section(
                "blocked",
                "section_absent",
                "The saved profile has no portable macro definitions.",
                macro_count=0,
                event_count=0,
            ),
            [],
        )
    limits = target_descriptor["limits"]
    event_count = sum(
        len(macro.get("layer_key") or [])
        for macro in raw
        if isinstance(macro, dict)
    )
    if len(raw) > limits["macros"] or event_count > limits["macro_events"]:
        return (
            _compatibility_section(
                "blocked",
                "macro_capacity_exceeded",
                f"The profile has {len(raw)} macros and {event_count} events; "
                f"the destination allows {limits['macros']} macros and "
                f"{limits['macro_events']} events.",
                macro_count=len(raw),
                event_count=event_count,
            ),
            [],
        )
    try:
        normalized = extract_importable_macros(
            source,
            max_tracks=limits["macros"],
            max_events=limits["macro_events"],
        )
    except ValueError as error:
        return (
            _compatibility_section(
                "blocked",
                "macro_invalid",
                str(error),
                macro_count=len(raw),
                event_count=event_count,
            ),
            [],
        )
    if limits["assignment_encoding"] == "qmk-vial16-v1":
        from . import vial_macros

        try:
            vial_macros.encode_macros(
                normalized,
                capacity=vial_macros.MacroCapacity(
                    count=limits["macros"],
                    buffer_bytes=limits["macro_buffer_bytes"],
                ),
            )
        except vial_macros.MacroCapacityError as error:
            return (
                _compatibility_section(
                    "blocked",
                    "macro_capacity_exceeded",
                    str(error),
                    macro_count=len(normalized),
                    event_count=event_count,
                ),
                [],
            )
        except (vial_macros.MacroEncodingError, ValueError) as error:
            return (
                _compatibility_section(
                    "blocked",
                    "macro_encoding_unsupported",
                    str(error),
                    macro_count=len(normalized),
                    event_count=event_count,
                ),
                [],
            )
    return (
        _compatibility_section(
            "portable",
            "macros_validate",
            "Every macro fits the destination without truncation or renumbering.",
            macro_count=len(normalized),
            event_count=event_count,
        ),
        normalized,
    )


def _active_lighting_targets(config: dict[str, Any]) -> list[str]:
    known = {
        "frames",
        "keyframes",
        "spotlight_frames",
        "axial",
        "head",
    }
    active: set[str] = set()
    pages = config.get("page_data")
    if not isinstance(pages, list):
        return []
    for page in pages:
        if not isinstance(page, dict):
            continue
        for target in known:
            track = page.get(target)
            if not isinstance(track, dict):
                continue
            data = track.get("frame_data")
            if (
                isinstance(data, list)
                and data
                or isinstance(track.get("frame_num"), int)
                and track.get("frame_num", 0) > 0
            ):
                active.add(target)
    return sorted(active)


def _profile_sections(config: dict[str, Any]) -> list[str]:
    sections = ["identity"]
    layers = _profile_layers(config)
    if layers:
        sections.append("keymap")
    if (
        isinstance(config.get("macro_key"), list)
        and config["macro_key"]
        or isinstance(config.get("MACRO_key"), list)
        and config["MACRO_key"]
    ):
        sections.append("macros")
    if _active_lighting_targets(config):
        sections.append("lighting")
    return sections


def _validated_profile_config(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("The selected JSON is not a configuration object.")
    validation = validate_config(value)
    if not validation["ok"]:
        detail = "; ".join(validation["errors"][:3])
        raise ValueError(f"The selected JSON is not a valid configuration: {detail}")
    product_id = ((value.get("product_info") or {}).get("product_id"))
    if not isinstance(product_id, str) or not product_id.strip():
        raise ValueError("The selected JSON has no product_info.product_id.")
    return copy.deepcopy(value)


def _profile_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("The Library profile name is missing.")
    name = value.strip()
    if (
        not name
        or len(name) > 200
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ValueError("The Library profile name is invalid.")
    return name


def _decode_profile_data(value: object) -> tuple[bytes, dict[str, Any]]:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > ((_MAX_PROFILE_BYTES + 2) // 3) * 4 + 8
    ):
        raise ValueError("The configuration file is missing or too large.")
    try:
        payload = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The configuration file encoding is invalid.") from exc
    if not payload or len(payload) > _MAX_PROFILE_BYTES:
        raise ValueError("The configuration file is missing or too large.")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The configuration file is not valid JSON.") from exc
    return payload, _validated_profile_config(decoded)


def _profile_device_metadata(
    config: dict[str, Any],
    *,
    key_layout: object = None,
) -> dict[str, Any]:
    product_id = str(config["product_info"]["product_id"])
    try:
        descriptor = device_mapping.device_descriptor(
            product_id,
            key_layout=key_layout,
        )
    except ValueError:
        return {
            "product_id": product_id,
            "family": "unknown",
            "product_label": product_id,
            "keymap_signature": None,
            "lighting_signature": None,
        }

    target_signatures = {
        target: descriptor["lighting"][target]["signature"]
        for target in _active_lighting_targets(config)
        if target in descriptor["lighting"]
    }
    lighting_signature: str | None = None
    if target_signatures:
        encoded = json.dumps(
            target_signatures,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        lighting_signature = (
            "lighting-set:v1:" + hashlib.sha256(encoded).hexdigest()
        )
    return {
        "product_id": descriptor["product_id"],
        "family": descriptor["family"],
        "product_label": descriptor["product_label"],
        "keymap_signature": descriptor["keymap"]["signature"],
        "lighting_signature": lighting_signature,
    }


def _profile_snapshot_bytes(config: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            config,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )


def _lighting_composition_tracks(
    config: Mapping[str, Any],
    *,
    slot: int,
    target: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Project one validated custom slot into the saved mapped-result shape."""

    product_info = config.get("product_info")
    product_id = (
        product_info.get("product_id")
        if isinstance(product_info, Mapping)
        else None
    )
    if not isinstance(product_id, str) or not product_id:
        raise ValueError("The open document has no supported product identity.")
    descriptor = device_mapping.device_descriptor(product_id)
    lighting = descriptor["lighting"]
    if target not in lighting:
        raise ValueError("The selected lighting target is unavailable.")
    pages = config.get("page_data")
    if not isinstance(pages, list):
        raise ValueError("The open document has no lighting pages.")
    page = next(
        (
            candidate
            for candidate in pages
            if isinstance(candidate, Mapping)
            and candidate.get("page_index") == slot
        ),
        pages[slot] if 0 <= slot < len(pages) else None,
    )
    if not isinstance(page, Mapping):
        raise ValueError("The selected custom lighting slot is unavailable.")

    tracks: dict[str, dict[str, Any]] = {}
    track_metadata: dict[str, dict[str, Any]] = {}
    for track_name, target_descriptor in lighting.items():
        raw_track = page.get(track_name)
        if not isinstance(raw_track, Mapping) or raw_track.get("valid") != 1:
            continue
        raw_frames = raw_track.get("frame_data")
        if not isinstance(raw_frames, list) or not raw_frames:
            continue
        if len(raw_frames) > descriptor["limits"]["frames"]:
            raise ValueError(
                f"The {track_name} lighting track exceeds the frame limit."
            )
        expected_pixels = target_descriptor["output_leds"]
        frames: list[list[str]] = []
        for frame_index, raw_frame in enumerate(raw_frames):
            colors = (
                raw_frame.get("frame_RGB")
                if isinstance(raw_frame, Mapping)
                else None
            )
            if (
                not isinstance(colors, list)
                or len(colors) != expected_pixels
                or any(not _hex_color(color) for color in colors)
            ):
                raise ValueError(
                    f"The {track_name} lighting track contains an invalid frame."
                )
            frames.append([color.upper() for color in colors])
        tracks[track_name] = {
            "frames": frames,
            "frame_count": len(frames),
            "width": target_descriptor["width"],
            "height": target_descriptor["height"],
            "pixels": expected_pixels,
            "mapped_pixels": expected_pixels,
        }
        track_metadata[track_name] = {
            "signature": target_descriptor["signature"],
            "semantic_target": target_descriptor["semantic_target"],
            "track_role": target_descriptor["track_role"],
            "relationship": (
                "selected" if track_name == target else "authored_companion"
            ),
            "frame_count": len(frames),
        }
    if target not in tracks:
        raise ValueError("The selected lighting target has no authored frames.")

    speed_ms = page.get("speed_ms")
    if type(speed_ms) is not int or not 1 <= speed_ms <= 60_000:
        raise ValueError("The selected lighting slot has invalid timing.")
    lightness = page.get("lightness")
    if type(lightness) is not int or not 0 <= lightness <= 100:
        raise ValueError("The selected lighting slot has invalid brightness.")
    primary_count = tracks[target]["frame_count"]
    mapped_result = {
        "tracks": tracks,
        "source_frames": primary_count,
        "decoded_frames": primary_count,
        "duration_ms": speed_ms,
        "source_duration_ms": primary_count * speed_ms,
        "timing_resampled": False,
        "model": descriptor["family"],
    }
    destination = {
        "product_id": descriptor["product_id"],
        "family": descriptor["family"],
        "slot": slot,
        "target": target,
        "targets": list(tracks),
        "frame_limit": descriptor["limits"]["frames"],
        "lightness": lightness,
        "speed_ms": speed_ms,
    }
    return mapped_result, track_metadata, destination


def _lighting_composition_device(
    descriptor: Mapping[str, Any],
    track_metadata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    signatures = {
        name: metadata["signature"]
        for name, metadata in track_metadata.items()
    }
    encoded = json.dumps(
        signatures,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return {
        "product_id": descriptor["product_id"],
        "family": descriptor["family"],
        "product_label": descriptor["product_label"],
        "keymap_signature": None,
        "lighting_signature": (
            "lighting-set:v1:" + hashlib.sha256(encoded).hexdigest()
        ),
    }


def _lighting_composition_preview(mapped_result: Mapping[str, Any]) -> bytes:
    """Create one bounded first-frame PNG without exposing profile data."""

    try:
        from PIL import Image, ImageDraw
    except ModuleNotFoundError as exc:
        raise ValueError(
            "Saving a lighting preview needs Pillow. Reinstall AM Configurator."
        ) from exc

    tracks = mapped_result.get("tracks")
    if not isinstance(tracks, Mapping) or not tracks:
        raise ValueError("The lighting composition has no previewable tracks.")
    rows: list[tuple[str, list[str]]] = []
    for name, track in tracks.items():
        frames = track.get("frames") if isinstance(track, Mapping) else None
        colors = frames[0] if isinstance(frames, list) and frames else None
        if (
            not isinstance(name, str)
            or not isinstance(colors, list)
            or not colors
            or any(not _hex_color(color) for color in colors)
        ):
            raise ValueError("The lighting composition preview is invalid.")
        rows.append((name, colors))

    cell = 8
    gap = 6
    columns = min(32, max(1, max(len(colors) for _name, colors in rows)))
    row_heights = [
        math.ceil(len(colors) / columns) * cell
        for _name, colors in rows
    ]
    width = columns * cell
    height = sum(row_heights) + gap * (len(rows) - 1)
    if width * height > 4_000_000:
        raise ValueError("The lighting composition preview is too large.")
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    top = 0
    for (_name, colors), row_height in zip(rows, row_heights, strict=True):
        for index, color in enumerate(colors):
            left = (index % columns) * cell
            y = top + (index // columns) * cell
            draw.rectangle(
                (left, y, left + cell - 1, y + cell - 1),
                fill=color,
            )
        top += row_height + gap
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _lighting_compatibility(
    source: dict[str, Any],
    source_descriptor: dict[str, Any],
    target_descriptor: dict[str, Any],
) -> dict[str, Any]:
    targets = _active_lighting_targets(source)
    if not targets:
        return _compatibility_section(
            "blocked",
            "section_absent",
            "The saved profile has no populated lighting tracks.",
            targets=[],
        )
    for target in targets:
        source_target = source_descriptor["lighting"].get(target)
        destination_target = target_descriptor["lighting"].get(target)
        if source_target is None or destination_target is None:
            return _compatibility_section(
                "blocked",
                "lighting_target_unavailable",
                f"The {target} lighting track is not available on both devices.",
                targets=targets,
            )
        classification = device_mapping.lighting_section_compatibility(
            "lighting_composition",
            source_signature=source_target["signature"],
            destination_signature=destination_target["signature"],
        )
        if classification["status"] != "exact":
            return _compatibility_section(
                "blocked",
                classification["reason_code"],
                classification["detail"],
                targets=targets,
            )
    frame_limit = target_descriptor["limits"]["frames"]
    for page in source.get("page_data") or []:
        if not isinstance(page, dict):
            continue
        for target in targets:
            track = page.get(target)
            if not isinstance(track, dict):
                continue
            data = track.get("frame_data") or []
            if isinstance(data, list) and len(data) > frame_limit:
                return _compatibility_section(
                    "blocked",
                    "frame_capacity_exceeded",
                    f"The {target} track has {len(data)} frames; the destination "
                    f"allows {frame_limit}.",
                    targets=targets,
                )
    return _compatibility_section(
        "exact",
        "lighting_signature_match",
        "Every populated lighting track matches exactly.",
        targets=targets,
    )


def config_section_compatibility(
    source_config: Any,
    destination_config: Any | None = None,
    *,
    target_product_id: Any = None,
    source_key_layout: object = None,
    source_keymap_signature: str | None = None,
    target_key_layout: object = None,
    target_layer_count: int | None = None,
    target_macro_count: int | None = None,
    target_macro_buffer_bytes: int | None = None,
) -> dict[str, Any]:
    """Build a server-authoritative, section-by-section profile import plan."""

    if not isinstance(source_config, dict):
        raise ValueError("The selected JSON is not a configuration object.")
    source_product_id = str(
        ((source_config.get("product_info") or {}).get("product_id") or "")
    )
    if not source_product_id:
        raise ValueError("The selected JSON has no product_info.product_id.")
    if destination_config is not None:
        if not isinstance(destination_config, dict):
            raise ValueError("The destination document is not a configuration object.")
        target_product = str(
            ((destination_config.get("product_info") or {}).get("product_id") or "")
        )
    else:
        target_product = str(target_product_id or "")
    if not target_product:
        raise ValueError("The target keyboard has no product ID.")

    try:
        source_descriptor = device_mapping.device_descriptor(
            source_product_id,
            key_layout=source_key_layout,
        )
    except ValueError:
        source_descriptor = {
            "schema_version": 1,
            "product_id": source_product_id,
            "family": None,
            "product_label": source_product_id,
            "keymap": {
                "signature": None,
                "layout_known": False,
                "encoding": None,
                "matrix_rows": None,
                "matrix_columns": None,
            },
            "lighting": {},
            "limits": {},
        }
    target_descriptor = device_mapping.device_descriptor(
        target_product,
        key_layout=target_key_layout,
        layer_count=target_layer_count,
        macro_count=target_macro_count,
        macro_buffer_bytes=target_macro_buffer_bytes,
    )
    keymap = _keymap_compatibility(
        source_config,
        source_descriptor,
        target_descriptor,
        source_keymap_signature=source_keymap_signature,
    )
    macros, _normalized_macros = _macro_compatibility(
        source_config,
        target_descriptor,
    )
    lighting = _lighting_compatibility(
        source_config,
        source_descriptor,
        target_descriptor,
    )
    sections = {
        "keymap": keymap,
        "macros": macros,
        "lighting": lighting,
    }
    allowed = [
        name for name, section in sections.items() if section["status"] != "blocked"
    ]
    if not allowed:
        summary = "blocked"
    elif len(allowed) != len(sections):
        summary = "partial"
    elif any(section["status"] == "convertible" for section in sections.values()):
        summary = "convertible"
    elif any(section["status"] == "portable" for section in sections.values()):
        summary = "portable"
    else:
        summary = "exact"
    return {
        "summary": summary,
        "source": source_descriptor,
        "target": target_descriptor,
        "sections": sections,
        "compatible_sections": allowed,
    }


def config_transfer_options(config: Any, target_product_id: Any) -> dict[str, Any]:
    """Describe which parts of a profile can safely move to another board."""
    result = config_section_compatibility(
        config,
        target_product_id=target_product_id,
    )
    source_product_id = str(
        ((config.get("product_info") or {}).get("product_id") or "")
    )
    target = str(target_product_id or "")
    macro_section = result["sections"]["macros"]
    compatible = _product_family(source_product_id) == _product_family(target)
    key_layers = ((config.get("key_layer") or {}).get("layer_data") or [])
    led_pages = config.get("page_data") or []
    return {
        **result,
        "compatible": compatible,
        "source_product_id": source_product_id,
        "target_product_id": target,
        "can_import_macros": macro_section["status"] == "portable",
        "macro_count": int(macro_section.get("macro_count") or 0),
        "macro_error": (
            None if macro_section["status"] == "portable" else macro_section["detail"]
        ),
        "can_merge_keymap": result["sections"]["keymap"]["status"] == "exact",
        # Retain the old page-level seam until the catalog UI consumes the
        # section matrix. The new `sections.lighting` result is authoritative.
        "can_merge_leds": compatible and bool(led_pages),
    }


def project_config_sections(
    source_config: Any,
    destination_config: Any,
    sections: Sequence[str],
    *,
    source_key_layout: object = None,
    source_keymap_signature: str | None = None,
    target_key_layout: object = None,
    target_layer_count: int | None = None,
    target_macro_count: int | None = None,
    target_macro_buffer_bytes: int | None = None,
) -> dict[str, Any]:
    """Project selected compatible sections into one complete candidate config."""

    if not isinstance(source_config, dict) or not isinstance(destination_config, dict):
        raise ValueError("Both source and destination must be configuration objects.")
    if isinstance(sections, (str, bytes, bytearray)) or not isinstance(
        sections, Sequence
    ):
        raise ValueError("Sections must be a list of section names.")
    selected = list(dict.fromkeys(str(section) for section in sections))
    allowed_names = {"keymap", "macros", "lighting"}
    if not selected or any(section not in allowed_names for section in selected):
        raise ValueError("Select one or more supported profile sections.")
    plan = config_section_compatibility(
        source_config,
        destination_config,
        source_key_layout=source_key_layout,
        source_keymap_signature=source_keymap_signature,
        target_key_layout=target_key_layout,
        target_layer_count=target_layer_count,
        target_macro_count=target_macro_count,
        target_macro_buffer_bytes=target_macro_buffer_bytes,
    )
    for section in selected:
        verdict = plan["sections"][section]
        required = "portable" if section == "macros" else "exact"
        if verdict["status"] != required:
            raise ValueError(
                f"The {section} section cannot be applied: {verdict['detail']}"
            )

    candidate = copy.deepcopy(destination_config)
    destination_identity = copy.deepcopy(destination_config.get("product_info"))
    if not isinstance(destination_identity, dict):
        raise ValueError("The destination identity is missing.")
    changes: list[dict[str, Any]] = []
    if "keymap" in selected:
        source_key_layer = source_config["key_layer"]
        source_layer_data = copy.deepcopy(source_key_layer["layer_data"])
        destination_key_layer = copy.deepcopy(destination_config.get("key_layer") or {})
        destination_layer_data = copy.deepcopy(
            destination_key_layer.get("layer_data") or []
        )
        merged_layers = source_layer_data + destination_layer_data[len(source_layer_data) :]
        destination_key_layer["valid"] = 1
        destination_key_layer["layer_data"] = merged_layers
        destination_key_layer["layer_num"] = len(merged_layers)
        candidate["key_layer"] = destination_key_layer
        changes.append(
            {
                "section": "keymap",
                "layers_imported": len(source_layer_data),
                "layers_preserved": max(
                    0, len(destination_layer_data) - len(source_layer_data)
                ),
            }
        )
    if "macros" in selected:
        _verdict, normalized = _macro_compatibility(
            source_config,
            plan["target"],
        )
        candidate["macro_key"] = copy.deepcopy(normalized)
        changes.append({"section": "macros", "macros_imported": len(normalized)})
    if "lighting" in selected:
        candidate["page_data"] = copy.deepcopy(source_config.get("page_data") or [])
        candidate["page_num"] = int(
            source_config.get("page_num", len(candidate["page_data"]))
        )
        changes.append(
            {"section": "lighting", "pages_imported": len(candidate["page_data"])}
        )
    candidate["product_info"] = destination_identity
    validation = validate_config(candidate)
    if not validation["ok"]:
        detail = "; ".join(validation["errors"][:3])
        raise ValueError(
            f"The selected sections do not form a valid destination profile: {detail}"
        )
    return {
        "config": candidate,
        "applied_sections": selected,
        "changes": changes,
        "validation": validation,
        "identity_preserved": True,
        "compatibility": plan,
    }


def key_assignment_status(product_id: Any, code: Any) -> dict[str, Any]:
    """Validate one editor assignment against the target family's wire format."""

    product = str(product_id or "").strip()
    normalized = str(code or "").strip().upper()
    if (
        len(normalized) != 9
        or not normalized.startswith("#")
        or any(character not in "0123456789ABCDEF" for character in normalized[1:])
    ):
        return {
            "ok": False,
            "error": "Use # followed by exactly eight hexadecimal digits.",
        }
    try:
        family = device_mapping.led_model(product)
    except ValueError:
        return {
            "ok": False,
            "error": f"{product or 'This product'} has no supported keymap format.",
        }
    if family != "NEON":
        return {"ok": True, "code": normalized}

    from . import vial_keymap

    try:
        vial_keymap.to_qmk(normalized)
    except vial_keymap.UnsupportedKeycode as error:
        return {"ok": False, "error": str(error)}
    return {"ok": True, "code": normalized}


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
    compiled = macro_text.compile_us_text(
        text,
        inter_key_delay_ms=delay,
        transition_delay_ms=1,
        max_events=200,
    )
    return {**compiled, "characters": len(text)}


def validate_config(config: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(config, dict):
        return {"ok": False, "errors": ["Configuration must be a JSON object."], "warnings": []}

    product = ((config.get("product_info") or {}).get("product_id"))
    if not isinstance(product, str) or not product:
        errors.append("product_info.product_id is missing.")
    # One authority for this family's track sizes and macro ceilings; an
    # unrecognised product falls back to the shared counts rather than being
    # rejected outright, as it always has been.
    spec = device_mapping.spec_for_product(product)

    key_layer = config.get("key_layer") or {}
    layers = key_layer.get("layer_data") or []
    if not layers:
        errors.append("key_layer.layer_data is missing.")
    keys_per_layer = spec.keys_per_layer
    for index, layer_data in enumerate(layers, 1):
        layer = layer_data.get("layer") if isinstance(layer_data, dict) else None
        if not isinstance(layer, list) or len(layer) != keys_per_layer:
            errors.append(
                f"Layer {index} must contain exactly {keys_per_layer} keycodes."
            )
        elif any(not isinstance(code, str) or len(code) != 9 for code in layer):
            errors.append(f"Layer {index} contains a malformed keycode.")
    if key_layer.get("layer_num", len(layers)) != len(layers):
        errors.append("key_layer.layer_num does not match layer_data.")

    macros = config.get("macro_key") or []
    if len(macros) > spec.macro_tracks:
        errors.append(f"macro_key contains more than {spec.macro_tracks} macros.")
    event_total = 0
    for index, macro in enumerate(macros, 1):
        events = macro.get("layer_key") or []
        delays = macro.get("intvel_ms") or []
        event_total += len(events)
        if not events:
            errors.append(f"Macro {index} has no events.")
        if len(events) > spec.macro_events:
            errors.append(
                f"Macro {index} contains more than {spec.macro_events} events."
            )
        if len(delays) < max(0, len(events) - 1):
            errors.append(f"Macro {index} is missing delays between events.")
        if any(not isinstance(delay, int) or not 0 <= delay <= 65535 for delay in delays[:len(events)]):
            errors.append(f"Macro {index} has a delay outside 0..65535ms.")
    if event_total > spec.macro_events:
        errors.append(
            f"Macros contain {event_total} events in total; the device limit is "
            f"{spec.macro_events}."
        )
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
        for field in ("frames", "keyframes", "spotlight_frames"):
            expected = spec.track_colors(field)
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
    # The serial wire encoder is one family's encoder, not a general validator.
    # Running it against a Neon configuration rejected every valid one, because
    # it looks for AM serial page structure the Neon does not have. A device on
    # another transport is validated by its own driver at write time, where the
    # preflight already refuses before transmitting.
    if not errors and spec.transport == device_mapping.SERIAL_TRANSPORT:
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


def _decorate_device_descriptor(
    payload: dict[str, Any],
    *,
    layer_count: int | None = None,
    macro_count: int | None = None,
    macro_buffer_bytes: int | None = None,
) -> dict[str, Any]:
    """Attach server-derived signatures without inventing absent layout evidence."""

    result = copy.deepcopy(payload)
    product_id = result.get("product_id")
    if not isinstance(product_id, str) or not product_id:
        return result
    product_label = (
        result.get("definition_name")
        or result.get("product_string")
        or None
    )
    try:
        result["descriptor"] = device_mapping.device_descriptor(
            product_id,
            key_layout=result.get("key_layout"),
            product_label=product_label,
            layer_count=layer_count,
            macro_count=macro_count,
            macro_buffer_bytes=macro_buffer_bytes,
        )
    except ValueError:
        # Unsupported or malformed discovery results stay visible, but they do
        # not gain a compatibility identity.
        result.pop("descriptor", None)
    return result


def _device_payload(
    handle: transport.DeviceHandle,
    info: Any,
    *,
    layer_count: int | None = None,
    macro_count: int | None = None,
    macro_buffer_bytes: int | None = None,
) -> dict[str, Any]:
    return _decorate_device_descriptor(
        transport.device_json(handle, info),
        layer_count=layer_count,
        macro_count=macro_count,
        macro_buffer_bytes=macro_buffer_bytes,
    )


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
    handle: transport.DeviceHandle,
    expected: list[list[str]],
    *,
    attempts: int = _KEYMAP_VERIFY_ATTEMPTS,
    retry_seconds: float = _KEYMAP_VERIFY_RETRY_SECONDS,
) -> list[list[str]]:
    """Retry read-back while the keyboard finishes committing its flash."""
    link = transport.transport_for_handle(handle)

    last_actual: list[list[str]] = []
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            last_actual = link.read_keymap(handle.address, layers=len(expected))
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


def _probe_keyboard(handle: transport.DeviceHandle, attempts: int = 3) -> Any:
    """Probe with a short settle retry; macOS can hold a just-scanned CDC port."""
    link = transport.transport_for_handle(handle)

    result = None
    for attempt in range(attempts):
        try:
            result = link.probe(handle.address, full=True)
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
    api_settings = settings["ai"]["api"]
    selected_api = api_settings["providers"][api_settings["selected_provider"]]
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
        "ai": {
            "enabled": settings["ai"]["enabled"],
            "backend": settings["ai"]["backend"],
            "ollama": {
                field: settings["ai"]["ollama"][field]
                for field in (
                    "base_url",
                    "model_id",
                    "model_digest",
                    "model_location",
                    "disclosure_version",
                    "disclosure_at",
                )
            },
            "api": {
                "selected_provider": api_settings["selected_provider"],
                "providers": {
                    provider: {
                        "model_id": provider_settings["model_id"],
                        "disclosure_version": provider_settings[
                            "disclosure_version"
                        ],
                        "disclosure_at": provider_settings["disclosure_at"],
                    }
                    for provider, provider_settings in api_settings[
                        "providers"
                    ].items()
                },
            },
        },
        "library": {
            "current_root": settings["library"]["current_root"],
            "roots": list(settings["library"]["roots"]),
        },
        "generation": {
            "loop_mode": settings["generation"]["loop_mode"],
            "privacy_ack_version": selected_api["disclosure_version"],
            "privacy_ack_at": selected_api["disclosure_at"],
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
        device_discovery: (
            Callable[[], list[tuple[transport.DeviceHandle, Any]]] | None
        ) = None,
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
        # macOS hidapi owns CoreFoundation/IOKit state that is thread-affine.
        # ThreadingHTTPServer creates a fresh request thread for each call, and
        # moving a later enumeration to a different thread can trap inside
        # IOHIDManager. Keep every device operation on one long-lived worker;
        # the lock still documents and enforces the transport-wide exclusion.
        self._device_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="am-device-io",
        )
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
        self._device_discovery = device_discovery
        self._procedural_library_identity: int | None = (
            id(lighting_library) if procedural_coordinator is not None else None
        )
        self._library_catalog: Any = None
        self._library_catalog_identity: int | None = None
        self._media_renderer: Any = None
        self._media_renderer_catalog_identity: int | None = None
        from .generation_admission import PROCESS_OPERATION_GATE

        self._generation_gate = self._lighting_dependencies.get(
            "operation_gate", PROCESS_OPERATION_GATE
        )
        self._lighting_root_signature: tuple[Any, ...] | None = None
        self._lighting_reconcile_signature: (
            tuple[int, bool, bytes | None] | None
        ) = None
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

    def document_snapshot(self, revision: str) -> dict[str, Any]:
        """Return one immutable revision without changing the open document."""

        with self._document_lock:
            snapshot = self._document_snapshot
            current = self._document_revision
            if snapshot is None or current is None:
                raise DocumentRevisionError(
                    "document_required",
                    "Open or read a keyboard configuration first.",
                )
            if not secrets.compare_digest(revision, current):
                raise DocumentRevisionError(
                    "document_stale",
                    "The open document changed. Try again.",
                )
        return json.loads(snapshot)

    def procedural_target(self, revision: str, target: str) -> dict:
        if not isinstance(target, str) or not target:
            raise ValueError("target must name one selected LED destination.")
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
        return _Handler._lighting_target(product_id, [target])

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
                    credential_status_loader=lambda provider: store.credential_status(
                        provider,
                        credential_store=credential_store
                    ),
                    credential_resolver=lambda provider: store.resolve_api_key(
                        provider,
                        credential_store=credential_store
                    ),
                    fingerprint_writer=lambda backend, fingerprint, **kwargs: (
                        store.set_ai_setup_fingerprint(
                            backend,
                            fingerprint,
                            provider=kwargs.get("provider"),
                            credential_store=credential_store,
                        )
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

    def library_catalog(self) -> Any:
        """Return the mixed catalog for the current generated-asset root set."""
        from .library import GeneratedAssetLibrary, LibraryCatalog

        library, _coordinator = self.lighting_services()
        if not isinstance(library, GeneratedAssetLibrary):
            raise RuntimeError("Library catalog services are unavailable.")
        with self._lighting_lock:
            if (
                self._library_catalog is None
                or self._library_catalog_identity != id(library)
            ):
                self._library_catalog = LibraryCatalog(library)
                self._library_catalog_identity = id(library)
            return self._library_catalog

    def media_renderer(self) -> Any:
        """Return the transform renderer bound to the current mixed catalog."""

        from .media_composition import MediaRenderCoordinator

        catalog = self.library_catalog()
        with self._lighting_lock:
            if (
                self._media_renderer is None
                or self._media_renderer_catalog_identity != id(catalog)
            ):
                self._media_renderer = MediaRenderCoordinator(catalog)
                self._media_renderer_catalog_identity = id(catalog)
            return self._media_renderer

    def close(self) -> None:
        try:
            capability = self._ai_capability
            close = getattr(capability, "close", None)
            if callable(close):
                close()
        finally:
            self._device_executor.shutdown(wait=True)

    def device_io(self, operation):
        """Run one complete device operation on the stable HID worker thread."""

        def serialized():
            with self.device_lock:
                return operation()

        return self._device_executor.submit(serialized).result()

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
            media_active = (
                bool(self._media_renderer.active_catalog_ids())
                if self._media_renderer is not None
                else False
            )
            if (
                self._lighting_library is not None
                and (
                    self._lighting_root_signature == signature
                    or active is not None
                    or procedural_active is not None
                    or media_active
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
        from .generation_admission import GenerationBusyError

        if self._generation_gate.is_active:
            self._defer_lighting_reconciliation()
            return []

        _library, coordinator = self.lighting_services()
        settings = store.load_settings(credential_store=self._credential_store)
        ai_settings = settings["ai"]
        api_selected = (
            ai_settings["enabled"] is True
            and ai_settings["backend"] == "api"
            and ai_settings["api"]["selected_provider"] == "xai"
        )
        credential_checked = api_selected
        api_key = (
            store.resolve_xai_key(credential_store=self._credential_store)
            if credential_checked
            else None
        )
        key_fingerprint = (
            hashlib.sha256(api_key.encode("utf-8")).digest() if api_key else None
        )
        signature = (id(coordinator), api_selected, key_fingerprint)
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
                if actions and not credential_checked:
                    recovery_key = store.resolve_xai_key(
                        credential_store=self._credential_store
                    )
                    if recovery_key:
                        actions = coordinator.reconcile_startup(
                            api_key=recovery_key,
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
        from .generation_admission import (
            GenerationBusyError,
            GenerationNotActiveError,
            GenerationValidationError,
        )
        from .library import (
            AssetNotFoundError,
            InvalidIdentifierError,
            LibraryItemStateError,
            LibraryRootError,
            ManifestError,
        )
        from .media_composition import MediaRenderSuperseded

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
        if isinstance(exc, MediaRenderSuperseded):
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return True
        if isinstance(exc, AssetNotFoundError):
            self._json({"error": "Asset not found."}, HTTPStatus.NOT_FOUND)
            return True
        if isinstance(exc, InvalidIdentifierError):
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return True
        if isinstance(exc, LibraryItemStateError):
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return True
        if isinstance(exc, ManifestError):
            self._json(
                {"error": "Library item, job, or asset not found."},
                HTTPStatus.NOT_FOUND,
            )
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
            "/api/settings/ollama",
            "/api/settings/ollama/disclosure",
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
                    def scan_devices():
                        discover = self.state._device_discovery or transport.discover
                        found = discover()
                        self.state.last_device_scan = time.monotonic()
                        return found

                    found = self.state.device_io(scan_devices)
                    self._json({
                        "devices": [
                            _device_payload(handle, info)
                            for handle, info in found
                        ]
                    })
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
                elif path == "/api/ai/ollama/models":
                    if parsed.query:
                        raise ValueError(
                            "The Ollama model route does not accept query fields."
                        )
                    capability = self.state.ai_services()
                    self._json(capability.discover_ollama_models())
                elif path.startswith("/api/library/"):
                    self._library_get(path, parsed.query)
                elif path.startswith("/api/lighting/"):
                    self._lighting_get(path, parsed.query)
                elif path == "/api/led/generate/status":
                    self._retired_ai_mutation()
                else:
                    self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001 - API boundary
                handled = (
                    path.startswith("/api/library/")
                    or path.startswith("/api/lighting/")
                    or self._is_ai_path(path)
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
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._authorized():
            self._json({"error": "Unauthorized local request."}, HTTPStatus.FORBIDDEN)
            return
        try:
            if path == "/api/library/import/media":
                self._library_import_media(parsed.query)
                return
            body = self._body()
            if path == "/api/config/validate":
                self._json(validate_config(body.get("config")))
            elif path == "/api/keymap/assignment":
                if set(body) != {"product_id", "code"}:
                    raise ValueError(
                        "Key assignment validation requires product_id and code."
                    )
                result = key_assignment_status(body["product_id"], body["code"])
                self._json(
                    result,
                    HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST,
                )
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
            elif path == "/api/settings/ollama":
                self._save_ollama_settings(body)
            elif path == "/api/settings/ollama/disclosure":
                self._save_ollama_disclosure(body)
            elif path == "/api/settings/credential":
                self._save_ai_credential(body)
            elif path == "/api/settings/migration/discard-credential":
                self._discard_legacy_ai_credential(body)
            elif path == "/api/ai/test":
                self._test_ai_backend(body)
            elif path == "/api/ai/ollama/select":
                self._select_ollama_model(body)
            elif path == "/api/ai/ollama/clear":
                self._clear_ollama_model(body)
            elif path == "/api/native/choose-library":
                self._native_choose_library(body)
            elif path == "/api/native/reveal-library":
                self._native_reveal_library(body)
            elif path == "/api/library/import/profile":
                self._library_import_profile(body)
            elif path == "/api/library/save/lighting":
                self._library_save_lighting(body)
            elif path == "/api/library/save/profile":
                self._library_save_profile(body)
            elif path.startswith("/api/library/items/"):
                self._library_post(path, body)
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
                path.startswith("/api/library/")
                or path.startswith("/api/lighting/")
                or self._is_ai_path(path)
            ) and self._lighting_error(exc)
            if not handled:
                self._internal_error(exc)

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._authorized():
            self._json(
                {"error": "Unauthorized local request."},
                HTTPStatus.FORBIDDEN,
            )
            return
        try:
            if parsed.query:
                raise ValueError(
                    "Library deletion does not accept query fields."
                )
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError(
                    "Library deletion does not accept a request body."
                ) from exc
            if (
                content_length != 0
                or self.headers.get("Transfer-Encoding")
            ):
                raise ValueError(
                    "Library deletion does not accept a request body."
                )
            parts = path.strip("/").split("/")
            if len(parts) != 4 or parts[:3] != ["api", "library", "items"]:
                self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
                return
            catalog = self.state.library_catalog()
            self._json(
                catalog.delete_forever(
                    parts[3],
                    active_catalog_ids=self._active_library_catalog_ids(),
                )
            )
        except ValueError as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - API boundary
            if not self._lighting_error(exc):
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
            from .generation_admission import GenerationBusyError

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
        store.update_ai_settings(
            body,
            credential_store=self.state._credential_store,
        )
        self._json(capability.status(probe=False))

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
        self._json(capability.status(probe=False))

    def _save_ollama_settings(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(
            body,
            allowed={"base_url"},
            required={"base_url"},
        )
        self._require_ai_idle()
        settings = store.update_ollama_ai_settings(
            body,
            credential_store=self.state._credential_store,
        )
        self.state.ai_services().close()
        ollama = settings["ai"]["ollama"]
        self._json(
            {
                "ollama": {
                    field: ollama[field]
                    for field in (
                        "base_url",
                        "model_id",
                        "model_digest",
                        "model_location",
                        "disclosure_version",
                        "disclosure_at",
                    )
                }
            }
        )

    def _save_ollama_disclosure(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(
            body,
            allowed={"version"},
            required={"version"},
        )
        self._require_ai_idle()
        store.acknowledge_ollama_disclosure(
            body,
            credential_store=self.state._credential_store,
        )
        self._json(self.state.ai_services().status(probe=False))

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
            status = capability.test_backend(
                body["backend"],
                deadline=time.monotonic() + 180.0,
                cancelled=cancelled.is_set,
            )
        finally:
            self.state._generation_gate.finish(token)
        self._json(status)

    def _select_ollama_model(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(
            body,
            allowed={"model_id", "model_digest", "model_location"},
            required={"model_id", "model_digest", "model_location"},
        )
        self._require_ai_idle()
        capability = self.state.ai_services()
        store.update_ollama_ai_settings(
            {
                "model_id": body["model_id"],
                "model_digest": body["model_digest"],
                "model_location": body["model_location"],
            },
            credential_store=self.state._credential_store,
        )
        capability.close()
        self._json(capability.status(probe=False))

    def _clear_ollama_model(self, body: dict[str, Any]) -> None:
        from . import store

        self._strict_body(body, allowed=set())
        self._require_ai_idle()
        capability = self.state.ai_services()
        store.update_ollama_ai_settings(
            {
                "model_id": None,
                "model_digest": None,
                "model_location": None,
            },
            credential_store=self.state._credential_store,
        )
        self._json(capability.status(probe=False))

    def _synchronize_document(self, body: dict[str, Any]) -> None:
        self._strict_body(body, allowed={"config"}, required={"config"})
        revision = self.state.synchronize_document(body["config"])
        self._json({"revision": revision})

    def _start_procedural_effect(self, body: dict[str, Any]) -> None:
        self._strict_body(
            body,
            allowed={"prompt", "backend", "target", "document_revision"},
            required={"prompt", "backend", "target", "document_revision"},
        )
        revision = body["document_revision"]
        if not isinstance(revision, str) or not 24 <= len(revision) <= 200:
            raise ValueError("document_revision must be an opaque revision string.")
        try:
            target = self.state.procedural_target(revision, body["target"])
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
        _library, coordinator = self.state.procedural_services()
        manifest = coordinator.start_effect(
            prompt=body["prompt"],
            target=target,
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

    @staticmethod
    def _media_import_name(query: str) -> str:
        if len(query) > 4_096:
            raise ValueError("The media import query is too long.")
        if any(
            character == "%"
            and (
                index + 2 >= len(query)
                or any(
                    digit not in "0123456789abcdefABCDEF"
                    for digit in query[index + 1 : index + 3]
                )
            )
            for index, character in enumerate(query)
        ):
            raise ValueError("The media import query encoding is invalid.")
        try:
            values = parse_qs(
                query,
                keep_blank_values=True,
                strict_parsing=True,
                errors="strict",
            )
        except (UnicodeError, ValueError) as exc:
            raise ValueError("The media import query is invalid.") from exc
        if set(values) != {"name"} or len(values["name"]) != 1:
            raise ValueError(
                "Media import requires exactly one encoded name query field."
            )
        name = values["name"][0]
        if (
            not name
            or len(name) > 200
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
        ):
            raise ValueError("The media import file name is invalid.")
        return name

    def _library_import_media(self, query: str) -> None:
        from . import media_composition

        name = self._media_import_name(query)
        if self.headers.get_all("Transfer-Encoding"):
            raise ValueError("Media import does not accept transfer encoding.")
        if self.headers.get("Content-Encoding") is not None:
            raise ValueError("Media import does not accept content encoding.")
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) != 1:
            raise ValueError("Media import requires one valid content length.")
        raw_length = lengths[0].strip()
        if not raw_length.isascii() or not raw_length.isdigit():
            raise ValueError("Media import requires one valid content length.")
        length = int(raw_length)
        if not 0 < length <= media_composition.MAX_MEDIA_BYTES:
            raise ValueError("The media upload exceeds the size limit.")
        payload = self.rfile.read(length)
        if len(payload) != length:
            raise ValueError("The media upload ended before its declared length.")

        decoded = media_composition.decode_media(payload)
        catalog = self.state.library_catalog()
        manifest, created = catalog.saved_items.bank_media_source(
            name=name,
            payload=payload,
            metadata={
                "mime_type": decoded.mime_type,
                "width": decoded.width,
                "height": decoded.height,
                "frame_count": decoded.frame_count,
                "duration_ms": decoded.duration_ms,
            },
        )
        detail = catalog.get(f"item:{manifest['item_id']}")
        self._json(
            {
                "item": detail,
                "deduplicated": not created,
            },
            HTTPStatus.CREATED if created else HTTPStatus.OK,
        )

    def _bank_keyboard_profile(
        self,
        *,
        config: dict[str, Any],
        configuration: bytes,
        origin: str,
        name: str,
        key_layout: object = None,
    ) -> dict[str, Any]:
        catalog = self.state.library_catalog()
        item = catalog.saved_items.create_keyboard_profile(
            origin=origin,
            name=_profile_name(name),
            configuration=configuration,
            device=_profile_device_metadata(config, key_layout=key_layout),
            sections=_profile_sections(config),
        )
        return catalog.get(f"item:{item['item_id']}")

    def _library_import_profile(self, body: dict[str, Any]) -> None:
        if urlparse(self.path).query:
            raise ValueError("Profile import does not accept query fields.")
        if set(body) != {"name", "data"}:
            raise ValueError(
                "Profile import requires exactly one file name and encoded file."
            )
        configuration, config = _decode_profile_data(body["data"])
        detail = self._bank_keyboard_profile(
            config=config,
            configuration=configuration,
            origin="json_import",
            name=body["name"],
        )
        self._json(detail, HTTPStatus.CREATED)

    def _library_save_profile(self, body: dict[str, Any]) -> None:
        if urlparse(self.path).query:
            raise ValueError("Saving a mapping does not accept query fields.")
        if set(body) not in (
            {"name", "document_revision"},
            {"name", "document_revision", "key_layout"},
        ):
            raise ValueError(
                "Saving a mapping requires a name and current document revision."
            )
        revision = body["document_revision"]
        if not isinstance(revision, str) or not 24 <= len(revision) <= 200:
            raise ValueError("document_revision must be an opaque revision string.")
        try:
            config = self.state.document_snapshot(revision)
        except DocumentRevisionError as exc:
            self._json(
                {"code": exc.code, "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        detail = self._bank_keyboard_profile(
            config=config,
            configuration=_profile_snapshot_bytes(config),
            origin="verified_export",
            name=body["name"],
            key_layout=body.get("key_layout"),
        )
        self._json(detail, HTTPStatus.CREATED)

    def _library_save_lighting(self, body: dict[str, Any]) -> None:
        from . import media_composition

        if urlparse(self.path).query:
            raise ValueError("Saving lighting does not accept query fields.")
        expected = {
            "name",
            "document_revision",
            "slot",
            "target",
            "source_catalog_id",
            "transform",
            "effects",
        }
        if set(body) != expected:
            raise ValueError(
                "Saving lighting requires one current slot and its provenance."
            )
        revision = body["document_revision"]
        if not isinstance(revision, str) or not 24 <= len(revision) <= 200:
            raise ValueError("document_revision must be an opaque revision string.")
        try:
            config = self.state.document_snapshot(revision)
        except DocumentRevisionError as exc:
            self._json(
                {"code": exc.code, "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return

        slot = body["slot"]
        if type(slot) is not int or slot not in {5, 6, 7}:
            raise ValueError("Lighting can be saved only from custom slots 5–7.")
        target = body["target"]
        if not isinstance(target, str) or not target:
            raise ValueError("A selected lighting target is required.")
        mapped_result, tracks, destination = _lighting_composition_tracks(
            config,
            slot=slot,
            target=target,
        )
        product_id = str(config["product_info"]["product_id"])
        descriptor = device_mapping.device_descriptor(product_id)

        catalog = self.state.library_catalog()
        source_catalog_id = body["source_catalog_id"]
        checked_transform: dict[str, object] | None
        still_source = False
        if source_catalog_id is None:
            if body["transform"] is not None:
                raise ValueError(
                    "Framing requires one imported media item saved in Library."
                )
            checked_transform = None
        else:
            if not isinstance(source_catalog_id, str):
                raise ValueError("The composition media source is invalid.")
            source_detail = catalog.get(source_catalog_id)
            source_item = source_detail.get("item")
            source = (
                source_item.get("source")
                if isinstance(source_item, dict)
                else None
            )
            if (
                source_detail.get("namespace") != "item"
                or source_detail.get("kind") != "media_source"
                or source_detail.get("removed") is not False
                or not isinstance(source, dict)
            ):
                raise ValueError(
                    "The composition media source is unavailable."
                )
            checked_transform = media_composition.validate_source_transform(
                body["transform"]
            ).to_dict()
            still_source = source["frame_count"] == 1

        raw_effects = body["effects"]
        if not isinstance(raw_effects, list) or len(raw_effects) > 8:
            raise ValueError("The lighting composition effects are invalid.")
        effects = [
            media_composition.validate_effect_spec(
                effect,
                frame_limit=descriptor["limits"]["frames"],
                still_source=still_source,
            )
            for effect in raw_effects
        ]
        rendered = json.dumps(
            mapped_result,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        preview = _lighting_composition_preview(mapped_result)
        item = catalog.saved_items.create_item(
            kind="lighting_composition",
            origin="manual",
            name=body["name"],
            device=_lighting_composition_device(descriptor, tracks),
            composition={
                "schema_version": 1,
                "source_catalog_id": source_catalog_id,
                "transform": checked_transform,
                "effects": effects,
                "manual_overrides": [],
                "destination": destination,
                "tracks": tracks,
                "rendered_asset_id": "rendered",
                "preview_asset_id": "preview",
            },
            assets={
                "rendered": {
                    "kind": "result",
                    "mime_type": "application/json",
                    "data": rendered,
                },
                "preview": {
                    "kind": "preview",
                    "mime_type": "image/png",
                    "data": preview,
                },
            },
        )
        detail = catalog.get(f"item:{item['item_id']}")
        self._json(detail, HTTPStatus.CREATED)

    @staticmethod
    def _catalog_profile_config(
        catalog: Any,
        catalog_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        detail = catalog.get(catalog_id)
        item = detail.get("item")
        if (
            detail.get("namespace") != "item"
            or detail.get("kind") != "keyboard_profile"
            or not isinstance(item, dict)
        ):
            raise ValueError("This Library item is not a keyboard profile.")
        profile = item.get("profile")
        if not isinstance(profile, dict):
            raise ValueError("This Library keyboard profile is invalid.")
        owned = catalog.resolve_asset(
            catalog_id,
            profile.get("asset_id"),
        )
        byte_size = owned.record.get("byte_size")
        if type(byte_size) is not int or not 0 < byte_size <= _MAX_PROFILE_BYTES:
            raise ValueError("This Library keyboard profile is too large.")
        with owned.open_verified() as stream:
            configuration = stream.read(byte_size + 1)
        if len(configuration) != byte_size:
            raise ValueError("This Library keyboard profile changed while it was read.")
        try:
            value = json.loads(configuration)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("This Library keyboard profile is not valid JSON.") from exc
        config = _validated_profile_config(value)
        device = item.get("device")
        source_product_id = str(config["product_info"]["product_id"])
        try:
            expected_product_id = device_mapping.device_descriptor(
                source_product_id
            )["product_id"]
        except ValueError:
            expected_product_id = source_product_id
        if (
            not isinstance(device, dict)
            or device.get("product_id")
            != expected_product_id
        ):
            raise ValueError("This Library keyboard profile identity is inconsistent.")
        return detail, config

    def _library_profile_compatibility(
        self,
        catalog_id: str,
        body: dict[str, Any],
    ) -> None:
        if set(body) not in (
            {"document_revision"},
            {"document_revision", "target_key_layout"},
        ):
            raise ValueError(
                "Profile compatibility requires the current document revision."
            )
        revision = body["document_revision"]
        if not isinstance(revision, str) or not 24 <= len(revision) <= 200:
            raise ValueError("document_revision must be an opaque revision string.")
        try:
            destination = self.state.document_snapshot(revision)
        except DocumentRevisionError as exc:
            self._json(
                {"code": exc.code, "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        catalog = self.state.library_catalog()
        detail, source = self._catalog_profile_config(catalog, catalog_id)
        source_device = detail["item"]["device"]
        compatibility = config_section_compatibility(
            source,
            destination,
            source_keymap_signature=source_device.get("keymap_signature"),
            target_key_layout=body.get("target_key_layout"),
        )
        self._json(
            {
                **compatibility,
                "catalog_id": detail["catalog_id"],
                "name": detail["name"],
                "source_sections": detail["item"]["profile"]["sections"],
            }
        )

    def _library_profile_apply(
        self,
        catalog_id: str,
        body: dict[str, Any],
    ) -> None:
        if set(body) not in (
            {"document_revision", "sections"},
            {"document_revision", "sections", "target_key_layout"},
        ):
            raise ValueError(
                "Profile Apply requires the current document revision and selected sections."
            )
        revision = body["document_revision"]
        if not isinstance(revision, str) or not 24 <= len(revision) <= 200:
            raise ValueError("document_revision must be an opaque revision string.")
        try:
            destination = self.state.document_snapshot(revision)
        except DocumentRevisionError as exc:
            self._json(
                {"code": exc.code, "error": str(exc)},
                HTTPStatus.CONFLICT,
            )
            return
        catalog = self.state.library_catalog()
        detail, source = self._catalog_profile_config(catalog, catalog_id)
        source_device = detail["item"]["device"]
        projected = project_config_sections(
            source,
            destination,
            body["sections"],
            source_keymap_signature=source_device.get("keymap_signature"),
            target_key_layout=body.get("target_key_layout"),
        )
        self._json(
            {
                **projected,
                "catalog_id": detail["catalog_id"],
                "name": detail["name"],
                "source_sections": detail["item"]["profile"]["sections"],
            }
        )

    def _active_library_catalog_ids(self) -> set[str]:
        active_ids = {
            getattr(self.state._generation_gate, "active_job_id", None),
            getattr(self.state._lighting_coordinator, "active_job_id", None),
            getattr(self.state._procedural_coordinator, "active_job_id", None),
        }
        catalog_ids = {
            f"job:{job_id}"
            for job_id in active_ids
            if isinstance(job_id, str) and job_id
        }
        renderer = self.state._media_renderer
        if renderer is not None:
            catalog_ids.update(renderer.active_catalog_ids())
        return catalog_ids

    def _library_post(self, path: str, body: dict[str, Any]) -> None:
        if urlparse(self.path).query:
            raise ValueError(
                "Library mutations do not accept query fields."
            )
        parts = path.strip("/").split("/")
        if (
            len(parts) == 5
            and parts[:3] == ["api", "library", "items"]
            and parts[4] == "render"
        ):
            if set(body) not in (
                {"product_id", "targets", "transform", "epoch"},
                {"product_id", "targets", "transform", "effects", "epoch"},
            ):
                raise ValueError(
                    "Media rendering requires product_id, targets, transform, and epoch."
                )
            self._json(
                self.state.media_renderer().render(
                    parts[3],
                    product_id=body["product_id"],
                    targets=body["targets"],
                    transform=body["transform"],
                    epoch=body["epoch"],
                    effects=body.get("effects", ()),
                )
            )
            return
        if (
            len(parts) == 5
            and parts[:3] == ["api", "library", "items"]
            and parts[4] == "compatibility"
        ):
            self._library_profile_compatibility(parts[3], body)
            return
        if (
            len(parts) == 5
            and parts[:3] == ["api", "library", "items"]
            and parts[4] == "apply"
        ):
            self._library_profile_apply(parts[3], body)
            return
        if body:
            raise ValueError(
                "The Library mutation body has unsupported fields."
            )
        if (
            len(parts) != 5
            or parts[:3] != ["api", "library", "items"]
            or parts[4] not in {"remove", "restore"}
        ):
            self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        catalog = self.state.library_catalog()
        operation = (
            catalog.remove if parts[4] == "remove" else catalog.restore
        )
        self._json(
            operation(
                parts[3],
                active_catalog_ids=self._active_library_catalog_ids(),
            )
        )

    def _library_get(self, path: str, query: str) -> None:
        catalog = self.state.library_catalog()
        if path == "/api/library/items":
            self._library_catalog_page(catalog, query)
            return
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:3] == ["api", "library", "items"]:
            if query:
                raise ValueError(
                    "The Library detail route does not accept query fields."
                )
            self._json(catalog.get(parts[3]))
            return
        if len(parts) == 5 and parts[:3] == ["api", "library", "assets"]:
            if query:
                raise ValueError("Library asset routes do not accept query fields.")
            self._library_asset(catalog, parts[3], parts[4])
            return
        self._json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def _library_catalog_page(self, catalog: Any, query: str) -> None:
        values = parse_qs(query, keep_blank_values=True)
        if set(values) - {
            "page",
            "limit",
            "status",
            "kind",
            "compatibility",
            "removed",
            "query",
        }:
            raise ValueError("The Library query has unsupported fields.")
        if any(len(items) != 1 for items in values.values()):
            raise ValueError("The Library query cannot repeat fields.")

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
        compatibility = values.get("compatibility", [""])[0]
        if (
            len(compatibility) > 80
            or (
                compatibility
                and not compatibility.replace("_", "").isalnum()
            )
        ):
            raise ValueError("compatibility filter is invalid.")
        removed_value = values.get("removed", ["false"])[0]
        if removed_value not in {"true", "false"}:
            raise ValueError("removed filter is invalid.")
        removed = removed_value == "true"
        search = values.get("query", [""])[0]
        if len(search) > 200:
            raise ValueError("query filter is too long.")
        self._json(
            catalog.page(
                page=page,
                limit=limit,
                statuses=statuses,
                kind=kind,
                compatibility=compatibility,
                removed=removed,
                query=search,
            )
        )

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
        # open_verified re-checks the descriptor this route actually serves
        # from, so hashing again at resolve time protects nothing extra.
        owned = library.resolve_asset(job_id, asset_id, verify_content=False)
        self._serve_library_asset(owned)

    def _library_asset(
        self,
        catalog: Any,
        catalog_id: str,
        asset_id: str,
    ) -> None:
        owned = catalog.resolve_asset(
            catalog_id,
            asset_id,
            verify_content=False,
        )
        self._serve_library_asset(owned)

    def _serve_library_asset(self, owned: Any) -> None:
        mime_type = owned.record["mime_type"]
        if mime_type not in _LIGHTING_ASSET_MIMES:
            raise ValueError("This Library asset type cannot be served.")
        total = owned.record["byte_size"]
        range_header = self.headers.get("Range")
        if range_header is None:
            with owned.open_verified() as stream:
                payload = stream.read(total + 1)
            if len(payload) != total:
                raise ValueError("The Library asset changed while it was read.")
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
        # A media player issues many Range requests per playback; verifying the
        # whole file on each seek reads far more than the slice being served.
        # The initial non-Range request verifies content end to end.
        with owned.open_verified(verify_content=False) as stream:
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
        handle = transport.handle_from_payload(body)
        link = transport.transport_for_handle(handle)
        layers = int(body.get("layers") or 7)

        def read_device():
            self.state.settle_after_scan()
            device = _probe_keyboard(handle)
            if not device or not device.is_keyboard:
                raise ValueError("The selected device is not a supported Angry Miao keyboard.")
            time.sleep(0.1)
            key_layers = link.read_keymap(handle.address, layers=layers)
            time.sleep(0.1)
            macro_state = link.read_macro_state(handle.address)
            return device, key_layers, macro_state

        device, key_layers, macro_state = self.state.device_io(read_device)
        device_macros = macro_state.macros
        stored_config, stored_warning = _stored_device_config(device.product_id or "")
        resolved_macros, macro_read_warning, restored_macro_snapshot = (
            _reconcile_read_macros(
                device.product_id or "", device_macros, stored_config
            )
        )
        device_payload = transport.device_json(handle, device)
        if macro_state.device_reported:
            device_payload.update(
                {
                    "macro_count": macro_state.device_macro_count,
                    "macro_buffer_bytes": macro_state.device_macro_buffer_bytes,
                }
            )
        device_payload = _decorate_device_descriptor(
            device_payload,
            layer_count=len(key_layers),
            macro_count=(
                macro_state.device_macro_count
                if macro_state.device_reported
                else None
            ),
            macro_buffer_bytes=(
                macro_state.device_macro_buffer_bytes
                if macro_state.device_reported
                else None
            ),
        )
        self._json({
            # Not `asdict`: a raw-HID device carries its OS path as bytes, which
            # no JSON encoder accepts, and its canonical product id is a derived
            # property rather than a field. `asdict` here returned HTTP 500 for
            # every Neon read after the reads had already succeeded.
            "device": device_payload,
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
        handle, config, checked = self._write_request(body)
        link = transport.transport_for_handle(handle)

        def write_device():
            self.state.settle_after_scan()
            before = self._validated_write_target(handle, checked, body)
            receipt = link.write_config(handle.address, config)
            return self._finish_accepted_write(
                handle, config, before, receipt, install_macros=True
            )

        result = self.state.device_io(write_device)
        self._json(result)

    def _verify_device_write(self, body: dict[str, Any]) -> None:
        """Finish an ACKed write without transmitting the full configuration again."""
        handle, config, checked = self._write_request(body)
        link = transport.transport_for_handle(handle)

        def verify_device_write():
            before = self._validated_write_target(handle, checked, body)
            return self._finish_accepted_write(
                handle, config, before, link.describe_write(config), install_macros=False
            )

        result = self.state.device_io(verify_device_write)
        self._json(result)

    @staticmethod
    def _write_request(
        body: dict[str, Any],
    ) -> tuple[transport.DeviceHandle, dict[str, Any], dict[str, Any]]:
        config = body.get("config")
        checked = validate_config(config)
        if not checked["ok"]:
            raise ValueError("Configuration is invalid: " + "; ".join(checked["errors"]))
        return transport.handle_from_payload(body), config, checked

    @staticmethod
    def _validated_write_target(
        handle: transport.DeviceHandle, checked: dict[str, Any], body: dict[str, Any]
    ) -> Any:
        before = _probe_keyboard(handle)
        if not before or not before.is_keyboard or not before.product_id:
            raise ValueError("The selected device is not a supported Angry Miao keyboard.")
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
        handle: transport.DeviceHandle,
        config: dict[str, Any],
        before: Any,
        receipt: transport.WriteReceipt,
        *,
        install_macros: bool,
    ) -> dict[str, Any]:
        from . import store

        link = transport.transport_for_handle(handle)

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
            link.write_macros(handle.address, expected_macros)
            time.sleep(0.25)

        _verify_keymap_readback(handle, expected_layers)
        read_macros = link.read_macros(handle.address)
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

        after = _probe_keyboard(handle)
        if not after or after.product_id != before.product_id:
            raise AcceptedWriteError(
                "Device accepted the configuration but disappeared before verification "
                "completed. Reconnect it and retry verification instead of resending."
            )
        clean = {key: value for key, value in config.items() if key != "_provenance"}
        store.save_current(
            after.product_id, clean, version=getattr(after, "version", None)
        )
        snapshot = store.snapshot(after.product_id, clean)
        document_revision = self.state.synchronize_document(clean)
        return {
            "ok": True,
            "device": _device_payload(handle, after),
            "write_units": receipt.units,
            "write_unit_label": receipt.unit_label,
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
    device_discovery: (
        Callable[[], list[tuple[transport.DeviceHandle, Any]]] | None
    ) = None,
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
        device_discovery=device_discovery,
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
