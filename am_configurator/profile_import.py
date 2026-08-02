"""Strict, server-side import adapters for supported JSON profile dialects."""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from . import device_mapping


MAX_JSON_BYTES: Final = 10_000_000
AM_CONFIGURATOR_PROFILE: Final = "am_configurator_profile"
AM_MASTER_PROFILE: Final = "am_master_profile"
AM_MASTER_AM80_LIGHTING: Final = "am_master_am80_lighting"
PROFILE_KIND: Final = "profile"
LIGHTING_KIND: Final = "lighting"

_MAX_JSON_DEPTH = 64
_MAX_JSON_VALUES = 1_000_000
_MAX_DESCRIPTION_LENGTH = 500
_ASSIGNMENT_CODE = re.compile(r"^#[0-9A-Fa-f]{8}$")
_RGB_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_AM_MASTER_RGB = re.compile(r"^[0-9A-Fa-f]{6}$")
_PROFILE_MARKERS = frozenset({"product_info", "key_layer", "page_data"})
_LIGHTING_REQUIRED = frozenset({"speed", "brightness", "frames", "frames_axial"})
_LIGHTING_ALLOWED = _LIGHTING_REQUIRED | {"description"}
_TRACK_NAMES = ("frames", "keyframes", "spotlight_frames", "axial", "head")


class _DuplicateKeyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Normalization:
    code: str
    count: int
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "count": self.count, "message": self.message}


@dataclass(frozen=True, slots=True)
class ImportReport:
    """One immutable classified result; public accessors return defensive copies."""

    source_format: str
    kind: str
    normalizations: tuple[Normalization, ...]
    _content: object

    def profile(self) -> dict[str, Any]:
        if self.kind != PROFILE_KIND:
            raise ValueError("The imported JSON is lighting, not a keyboard profile.")
        result = _thaw(self._content)
        if not isinstance(result, dict):  # pragma: no cover - construction invariant
            raise RuntimeError("The imported profile report is invalid.")
        return result

    def lighting(self) -> dict[str, Any]:
        if self.kind != LIGHTING_KIND:
            raise ValueError("The imported JSON is a profile, not lighting-only data.")
        result = _thaw(self._content)
        if not isinstance(result, dict):  # pragma: no cover - construction invariant
            raise RuntimeError("The imported lighting report is invalid.")
        return result

    def to_response(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_format": self.source_format,
            "kind": self.kind,
            "normalizations": [item.to_dict() for item in self.normalizations],
        }
        if self.kind == PROFILE_KIND:
            result["config"] = self.profile()
        else:
            result["lighting"] = self.lighting()
        return result


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return copy.deepcopy(value)


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(
                "The configuration file contains duplicate JSON object fields."
            )
        result[key] = value
    return result


def _reject_nonstandard_constant(_value: str) -> object:
    raise ValueError("The configuration file contains a nonstandard JSON number.")


def _validate_json_tree(
    value: object,
    *,
    depth: int = 0,
    count: list[int] | None = None,
) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("The configuration file is too deeply nested.")
    if count is None:
        count = [0]
    count[0] += 1
    if count[0] > _MAX_JSON_VALUES:
        raise ValueError("The configuration file contains too many values.")
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:
        if abs(value) > 2**53:
            raise ValueError("The configuration file contains an unsupported number.")
        return
    if isinstance(value, float):
        if not math.isfinite(value) or abs(value) > 2**53:
            raise ValueError("The configuration file contains an unsupported number.")
        return
    if isinstance(value, list):
        for child in value:
            _validate_json_tree(child, depth=depth + 1, count=count)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):  # pragma: no cover - JSON invariant
                raise ValueError("The configuration file contains an invalid field.")
            _validate_json_tree(child, depth=depth + 1, count=count)
        return
    raise ValueError("The configuration file contains an unsupported value.")


def _decode_json(payload: bytes) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_JSON_BYTES:
        raise ValueError("The configuration file is missing or too large.")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The configuration file must be UTF-8 JSON.") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonstandard_constant,
        )
    except _DuplicateKeyError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("The configuration"):
            raise
        raise ValueError("The configuration file is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("The selected JSON is not a configuration object.")
    _validate_json_tree(value)
    return value


def _strip_am_master_comments(value: object) -> int:
    count = 0
    if isinstance(value, dict):
        if "//" in value:
            comment = value["//"]
            if (
                not isinstance(comment, str)
                or len(comment) > 10_000
                or any(ord(character) < 32 or ord(character) == 127 for character in comment)
            ):
                raise ValueError("An AM Master comment field is malformed.")
            del value["//"]
            count += 1
        for child in value.values():
            count += _strip_am_master_comments(child)
    elif isinstance(value, list):
        for child in value:
            count += _strip_am_master_comments(child)
    return count


def _is_disabled_placeholder(track: object) -> bool:
    if not isinstance(track, dict) or set(track) != {"valid", "frame_num", "frame_data"}:
        return False
    if track["valid"] is not False or type(track["frame_num"]) is not int or track["frame_num"] != 0:
        return False
    frame_data = track["frame_data"]
    if not isinstance(frame_data, list) or len(frame_data) != 1:
        return False
    frame = frame_data[0]
    if not isinstance(frame, dict) or set(frame) != {"frame_index", "frame_RGB"}:
        return False
    if frame["frame_index"] not in (0, "0") or isinstance(frame["frame_index"], bool):
        return False
    colors = frame["frame_RGB"]
    return (
        isinstance(colors, list)
        and len(colors) == 1
        and isinstance(colors[0], str)
        and len(colors[0]) <= 100
    )


def _normalize_disabled_placeholders(config: dict[str, Any]) -> int:
    pages = config.get("page_data")
    if not isinstance(pages, list):
        return 0
    count = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        for track_name in _TRACK_NAMES:
            track = page.get(track_name)
            if _is_disabled_placeholder(track):
                track["frame_data"] = []
                count += 1
    return count


def _uppercase_assignment(value: object) -> tuple[object, int]:
    if not isinstance(value, str) or not _ASSIGNMENT_CODE.fullmatch(value):
        return value, 0
    normalized = value.upper()
    return normalized, int(normalized != value)


def _normalize_assignments(config: dict[str, Any]) -> int:
    count = 0
    key_layer = config.get("key_layer")
    layer_data = key_layer.get("layer_data") if isinstance(key_layer, dict) else None
    if isinstance(layer_data, list):
        for layer in layer_data:
            codes = layer.get("layer") if isinstance(layer, dict) else None
            if not isinstance(codes, list):
                continue
            for index, code in enumerate(codes):
                codes[index], changed = _uppercase_assignment(code)
                count += changed
    macros = config.get("macro_key")
    if isinstance(macros, list):
        for macro in macros:
            if not isinstance(macro, dict):
                continue
            if "original_key" in macro:
                macro["original_key"], changed = _uppercase_assignment(
                    macro["original_key"]
                )
                count += changed
            events = macro.get("layer_key")
            if isinstance(events, list):
                for index, code in enumerate(events):
                    events[index], changed = _uppercase_assignment(code)
                    count += changed
    return count


def _uppercase_rgb(value: object) -> tuple[object, int]:
    if not isinstance(value, str) or not _RGB_COLOR.fullmatch(value):
        return value, 0
    normalized = value.upper()
    return normalized, int(normalized != value)


def _normalize_profile_rgb(config: dict[str, Any]) -> int:
    pages = config.get("page_data")
    if not isinstance(pages, list):
        return 0
    count = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        color = page.get("color")
        if isinstance(color, dict):
            for field in ("back_rgb", "rgb"):
                if field in color:
                    color[field], changed = _uppercase_rgb(color[field])
                    count += changed
        for track_name in _TRACK_NAMES:
            track = page.get(track_name)
            frames = track.get("frame_data") if isinstance(track, dict) else None
            if not isinstance(frames, list):
                continue
            for frame in frames:
                colors = frame.get("frame_RGB") if isinstance(frame, dict) else None
                if not isinstance(colors, list):
                    continue
                for index, color_value in enumerate(colors):
                    colors[index], changed = _uppercase_rgb(color_value)
                    count += changed
    return count


def _note(code: str, count: int, singular: str, plural: str | None = None) -> Normalization:
    label = singular if count == 1 else (plural or singular + "s")
    return Normalization(code=code, count=count, message=f"{label}: {count}.")


def _profile_report(
    root: dict[str, Any],
    *,
    profile_validator: Callable[[object], dict[str, Any]],
) -> ImportReport:
    comment_count = _strip_am_master_comments(root)
    placeholder_count = _normalize_disabled_placeholders(root)
    am_master = bool(comment_count or placeholder_count)
    assignment_count = _normalize_assignments(root) if am_master else 0
    rgb_count = _normalize_profile_rgb(root) if am_master else 0
    normalized = profile_validator(root)
    if not isinstance(normalized, dict):
        raise TypeError("The profile validator returned an invalid result.")
    notes: list[Normalization] = []
    if comment_count:
        notes.append(
            _note(
                "am_master_comments_removed",
                comment_count,
                "AM Master comment removed",
                "AM Master comments removed",
            )
        )
    if placeholder_count:
        notes.append(
            _note(
                "am_master_disabled_placeholders",
                placeholder_count,
                "Disabled zero-frame placeholder normalized",
                "Disabled zero-frame placeholders normalized",
            )
        )
    if assignment_count:
        notes.append(
            _note(
                "assignment_case",
                assignment_count,
                "Assignment code uppercased",
                "Assignment codes uppercased",
            )
        )
    if rgb_count:
        notes.append(
            _note(
                "rgb_case",
                rgb_count,
                "Lighting color uppercased",
                "Lighting colors uppercased",
            )
        )
    return ImportReport(
        source_format=AM_MASTER_PROFILE if am_master else AM_CONFIGURATOR_PROFILE,
        kind=PROFILE_KIND,
        normalizations=tuple(notes),
        _content=_freeze(normalized),
    )


def _lighting_frames(
    value: object,
    *,
    target: str,
    pixels: int,
) -> list[list[str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"AM Master {target} lighting must contain at least one frame.")
    result: list[list[str]] = []
    for frame in value:
        if not isinstance(frame, list) or len(frame) != pixels:
            raise ValueError(
                f"Each AM Master {target} frame must contain exactly {pixels} colors."
            )
        if any(not isinstance(color, str) or not _AM_MASTER_RGB.fullmatch(color) for color in frame):
            raise ValueError(f"AM Master {target} lighting contains an invalid RGB color.")
        result.append([f"#{color.upper()}" for color in frame])
    return result


def _lighting_report(root: dict[str, Any]) -> ImportReport:
    unknown = set(root) - _LIGHTING_ALLOWED
    missing = _LIGHTING_REQUIRED - set(root)
    if unknown or missing:
        raise ValueError(
            "AM Master AM 80 lighting has unsupported or missing fields."
        )
    speed = root["speed"]
    if type(speed) is not int or speed not in device_mapping.LED_SPEEDS_MS:
        raise ValueError("AM Master AM 80 lighting uses an unsupported frame speed.")
    brightness = root["brightness"]
    if type(brightness) is not int or not (
        0 <= brightness <= 100 or brightness == 255
    ):
        raise ValueError(
            "AM Master AM 80 brightness must be 0 through 100, or 255 for 100%."
        )
    description = root.get("description")
    if description is not None and (
        not isinstance(description, str)
        or len(description) > _MAX_DESCRIPTION_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in description)
    ):
        raise ValueError("The AM Master lighting description is malformed.")

    descriptor = device_mapping.device_descriptor("NEON80")
    frame_limit = descriptor["limits"]["frames"]
    head = _lighting_frames(root["frames"], target="Head", pixels=230)
    axial = _lighting_frames(root["frames_axial"], target="Per-key", pixels=89)
    if len(head) != len(axial):
        raise ValueError("AM Master Head and Per-key lighting must share one timeline.")
    if len(head) > frame_limit:
        raise ValueError(
            f"AM Master AM 80 lighting exceeds the {frame_limit}-frame limit."
        )

    tracks: dict[str, dict[str, Any]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for target, frames in (("head", head), ("axial", axial)):
        target_descriptor = descriptor["lighting"][target]
        tracks[target] = {
            "frames": frames,
            "frame_count": len(frames),
            "width": target_descriptor["width"],
            "height": target_descriptor["height"],
            "pixels": target_descriptor["output_leds"],
            "mapped_pixels": target_descriptor["output_leds"],
        }
        metadata[target] = {
            "signature": target_descriptor["signature"],
            "semantic_target": target_descriptor["semantic_target"],
            "track_role": target_descriptor["track_role"],
            "relationship": "selected" if target == "head" else "authored_companion",
            "frame_count": len(frames),
        }
    lightness = 100 if brightness == 255 else brightness
    mapped_result = {
        "tracks": tracks,
        "source_frames": len(head),
        "decoded_frames": len(head),
        "duration_ms": speed,
        "source_duration_ms": len(head) * speed,
        "timing_resampled": False,
        "model": descriptor["family"],
    }
    destination = {
        "product_id": descriptor["product_id"],
        "family": descriptor["family"],
        "slot": None,
        "target": "head",
        "targets": ["head", "axial"],
        "frame_limit": frame_limit,
        "lightness": lightness,
        "speed_ms": speed,
        "description": description,
    }
    rgb_count = len(head) * (230 + 89)
    notes = [
        _note(
            "am_master_rgb_syntax",
            rgb_count,
            "AM Master RGB value converted to #RRGGBB",
            "AM Master RGB values converted to #RRGGBB",
        )
    ]
    if brightness == 255:
        notes.append(
            Normalization(
                code="am_master_brightness_255",
                count=1,
                message="AM Master brightness 255 converted to 100%.",
            )
        )
    return ImportReport(
        source_format=AM_MASTER_AM80_LIGHTING,
        kind=LIGHTING_KIND,
        normalizations=tuple(notes),
        _content=_freeze(
            {
                "description": description,
                "mapped_result": mapped_result,
                "tracks": metadata,
                "destination": destination,
            }
        ),
    )


def import_json_bytes(
    payload: bytes,
    *,
    profile_validator: Callable[[object], dict[str, Any]],
) -> ImportReport:
    """Parse, classify, normalize, and validate one bounded JSON import."""

    root = _decode_json(payload)
    keys = set(root)
    profile_marked = bool(keys & _PROFILE_MARKERS)
    lighting_marked = bool(keys & _LIGHTING_REQUIRED)
    if profile_marked and lighting_marked:
        raise ValueError("The selected JSON mixes profile and lighting-only fields.")
    if lighting_marked:
        return _lighting_report(root)
    if profile_marked:
        return _profile_report(root, profile_validator=profile_validator)
    raise ValueError(
        "The selected JSON is not a recognized AM Configurator profile or AM Master lighting file."
    )
