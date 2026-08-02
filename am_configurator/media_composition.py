"""Strict imported-media validation and transform-aware local rendering."""

from __future__ import annotations

import copy
import hashlib
import math
import re
import secrets
import struct
import threading
import time
import warnings
import zlib
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable


MAX_MEDIA_BYTES = 12_000_000
MAX_MEDIA_DIMENSION = 8_192
MAX_MEDIA_FRAMES = 512
MAX_MEDIA_DURATION_MS = 10 * 60 * 1_000
MAX_MEDIA_FRAME_DURATION_MS = 60_000
MAX_DECODED_PIXELS = 32_000_000
MAX_RENDER_PIXELS = 32_000_000
MAX_PREVIEW_SESSIONS = 2
MAX_PREVIEW_DECODED_PIXELS = MAX_DECODED_PIXELS * MAX_PREVIEW_SESSIONS
MAX_SOURCE_PREVIEW_PIXELS = 1_000_000
MAX_SOURCE_PREVIEW_CACHE_ENTRIES = 4
MAX_SOURCE_PREVIEW_CACHE_BYTES = 16_000_000
PREVIEW_SESSION_TTL_SECONDS = 5 * 60
MAX_TRANSFORM_OFFSET = 8.0
MIN_TRANSFORM_SCALE = 0.01
MAX_TRANSFORM_SCALE = 32.0

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_TRANSFORM_FIELDS = {
    "version",
    "offset_x",
    "offset_y",
    "scale_x",
    "scale_y",
    "aspect_locked",
    "sampling",
    "background",
}
_EFFECT_FIELDS = {
    "version",
    "type",
    "frame_count",
    "duration_ms",
    "parameters",
}
_EFFECT_DIRECTIONS = {
    "left_to_right",
    "right_to_left",
    "top_to_bottom",
    "bottom_to_top",
    "diagonal",
}
_SAMPLING = {"nearest", "box", "lanczos"}
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_SUPPORTED_MODES = {"1", "L", "LA", "P", "PA", "RGB", "RGBA"}


@dataclass(frozen=True)
class DecodedMedia:
    """One fully verified immutable source decoded to bounded RGBA frames."""

    mime_type: str
    width: int
    height: int
    frame_count: int
    duration_ms: int
    sha256: str
    frames: tuple[Any, ...]
    durations_ms: tuple[int, ...]


@dataclass(frozen=True)
class SourceTransform:
    """Versioned normalized transform used only for imported media."""

    version: int
    offset_x: float
    offset_y: float
    scale_x: float
    scale_y: float
    aspect_locked: bool
    sampling: str
    background: str

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "aspect_locked": self.aspect_locked,
            "sampling": self.sampling,
            "background": self.background,
        }


@dataclass(frozen=True)
class SourceRasterBox:
    """Exact rendered source box for one destination raster."""

    rendered_width: int
    rendered_height: int
    left: int
    top: int

    def to_dict(self) -> dict[str, int]:
        return {
            "rendered_width": self.rendered_width,
            "rendered_height": self.rendered_height,
            "left": self.left,
            "top": self.top,
        }


@dataclass(frozen=True)
class ResolvedSourceGeometry:
    """One canonical transform and its immutable per-destination boxes."""

    transform: SourceTransform
    max_offset_x: float
    max_offset_y: float
    boxes: tuple[SourceRasterBox, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "transform": self.transform.to_dict(),
            "limits": {
                "max_x": self.max_offset_x,
                "max_y": self.max_offset_y,
            },
            "boxes": [box.to_dict() for box in self.boxes],
        }


class MediaRenderSuperseded(RuntimeError):
    """A newer editor epoch replaced this transient render."""


@dataclass(frozen=True)
class PreparedMediaSession:
    """One pathless verified decoded source held by the bounded preview LRU."""

    session_id: str
    catalog_id: str
    asset_id: str
    asset_sha256: str
    decoded: DecodedMedia

    @property
    def decoded_pixels(self) -> int:
        return self.decoded.width * self.decoded.height * self.decoded.frame_count


@dataclass(frozen=True)
class PreviewTimelineEntry:
    """One exact firmware output frame and its synchronized source projection."""

    index: int
    source_frame_index: int
    duration_ms: int
    resolved_transform: SourceTransform
    effect_phase: tuple[tuple[str, int, int], ...]
    base_frame_index: int
    color_effect_indices: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "source_frame_index": self.source_frame_index,
            "duration_ms": self.duration_ms,
            "resolved_transform": self.resolved_transform.to_dict(),
            "effect_phase": [
                {
                    "type": effect_type,
                    "frame_index": frame_index,
                    "frame_count": frame_count,
                }
                for effect_type, frame_index, frame_count in self.effect_phase
            ],
        }


@dataclass(frozen=True)
class PreparedMediaRender:
    """Validated destination/effect projection shared by frame and full renders."""

    session: PreparedMediaSession
    product_id: str
    model: str
    targets: tuple[str, ...]
    destination_sizes: tuple[tuple[int, int], ...]
    frame_limit: int
    transform: SourceTransform
    effects: tuple[dict[str, object], ...]
    resolved_transforms: tuple[SourceTransform, ...]
    color_effects: tuple[dict[str, object], ...]
    timeline: tuple[PreviewTimelineEntry, ...]


@dataclass
class _PreviewSessionCacheEntry:
    prepared: PreparedMediaSession
    last_access: float
    source_previews: OrderedDict[int, bytes]
    source_preview_bytes: int = 0


def _sniff_media(payload: bytes) -> str:
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if payload.startswith(_PNG_SIGNATURE):
        return "image/png"
    if payload.startswith(b"BM"):
        return "image/bmp"
    raise ValueError("The file is not a supported GIF, PNG, or BMP image.")


def _validate_png_container(payload: bytes) -> tuple[int, int]:
    position = len(_PNG_SIGNATURE)
    chunk_index = 0
    dimensions: tuple[int, int] | None = None
    saw_iend = False
    while position < len(payload):
        if len(payload) - position < 12:
            raise ValueError("The PNG is truncated or contains trailing bytes.")
        length = struct.unpack(">I", payload[position : position + 4])[0]
        chunk_type = payload[position + 4 : position + 8]
        data_start = position + 8
        data_end = data_start + length
        chunk_end = data_end + 4
        if data_end < data_start or chunk_end > len(payload):
            raise ValueError("The PNG is truncated or contains trailing bytes.")
        data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(data, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("The PNG failed its container integrity check.")
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("The PNG header is invalid.")
            dimensions = struct.unpack(">II", data[:8])
        if chunk_type in {b"acTL", b"fcTL", b"fdAT"}:
            raise ValueError("Animated PNG is not supported.")
        position = chunk_end
        chunk_index += 1
        if chunk_type == b"IEND":
            if length != 0 or position != len(payload):
                raise ValueError("The PNG is truncated or contains trailing bytes.")
            saw_iend = True
            break
    if not saw_iend or dimensions is None:
        raise ValueError("The PNG is truncated or contains trailing bytes.")
    return dimensions


def _consume_gif_sub_blocks(payload: bytes, position: int) -> int:
    while True:
        if position >= len(payload):
            raise ValueError("The GIF is truncated or contains trailing bytes.")
        length = payload[position]
        position += 1
        if length == 0:
            return position
        position += length
        if position > len(payload):
            raise ValueError("The GIF is truncated or contains trailing bytes.")


def _validate_gif_container(payload: bytes) -> tuple[int, int]:
    if len(payload) < 14:
        raise ValueError("The GIF is truncated or contains trailing bytes.")
    dimensions = struct.unpack("<HH", payload[6:10])
    packed = payload[10]
    position = 13
    if packed & 0x80:
        position += 3 * (2 ** ((packed & 0x07) + 1))
    saw_image = False
    while position < len(payload):
        marker = payload[position]
        position += 1
        if marker == 0x3B:
            if position != len(payload) or not saw_image:
                raise ValueError("The GIF is truncated or contains trailing bytes.")
            return dimensions
        if marker == 0x21:
            if position >= len(payload):
                raise ValueError("The GIF is truncated or contains trailing bytes.")
            position += 1
            position = _consume_gif_sub_blocks(payload, position)
            continue
        if marker != 0x2C or position + 9 > len(payload):
            raise ValueError("The GIF is truncated or contains trailing bytes.")
        descriptor = payload[position : position + 9]
        position += 9
        if descriptor[8] & 0x80:
            position += 3 * (2 ** ((descriptor[8] & 0x07) + 1))
        if position >= len(payload):
            raise ValueError("The GIF is truncated or contains trailing bytes.")
        position += 1
        position = _consume_gif_sub_blocks(payload, position)
        saw_image = True
    raise ValueError("The GIF is truncated or contains trailing bytes.")


def _validate_container(payload: bytes, mime_type: str) -> tuple[int, int] | None:
    if mime_type == "image/gif":
        return _validate_gif_container(payload)
    if mime_type == "image/png":
        return _validate_png_container(payload)
    if len(payload) < 26:
        raise ValueError("The BMP is truncated.")
    declared_size = struct.unpack("<I", payload[2:6])[0]
    pixel_offset = struct.unpack("<I", payload[10:14])[0]
    dib_size = struct.unpack("<I", payload[14:18])[0]
    if (
        declared_size != len(payload)
        or 14 + dib_size > len(payload)
        or pixel_offset < 14 + dib_size
        or pixel_offset >= len(payload)
        or dib_size < 12
    ):
        raise ValueError("The BMP is truncated or contains trailing bytes.")
    if dib_size == 12:
        return struct.unpack("<HH", payload[18:22])
    if dib_size < 40:
        raise ValueError("The BMP header is unsupported.")
    width, height = struct.unpack("<ii", payload[18:26])
    return width, abs(height)


def _positive_dimensions(width: object, height: object) -> tuple[int, int]:
    if (
        type(width) is not int
        or type(height) is not int
        or width <= 0
        or height <= 0
        or width > MAX_MEDIA_DIMENSION
        or height > MAX_MEDIA_DIMENSION
    ):
        raise ValueError("The media dimensions exceed the supported limit.")
    return width, height


def decode_media(
    payload: bytes,
    *,
    work_check: Callable[[], None] | None = None,
) -> DecodedMedia:
    """Sniff, fully decode, and normalize one bounded GIF, PNG, or BMP."""

    if work_check is not None:
        work_check()
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("Media bytes are required.")
    if len(payload) > MAX_MEDIA_BYTES:
        raise ValueError("The media file exceeds the size limit.")
    mime_type = _sniff_media(payload)
    container_dimensions = _validate_container(payload, mime_type)
    if container_dimensions is not None:
        _positive_dimensions(*container_dimensions)

    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise ValueError(
            "Media import needs Pillow. Reinstall AM Configurator."
        ) from exc

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(BytesIO(payload)) as verifier:
                verifier.verify()
            if work_check is not None:
                work_check()
            with Image.open(BytesIO(payload)) as image:
                width, height = _positive_dimensions(*image.size)
                if (
                    container_dimensions is not None
                    and container_dimensions != (width, height)
                ):
                    raise ValueError(
                        "The media header dimensions disagree with its decoded image."
                    )
                frame_count = getattr(image, "n_frames", 1)
                if (
                    type(frame_count) is not int
                    or frame_count <= 0
                    or frame_count > MAX_MEDIA_FRAMES
                ):
                    raise ValueError("The media frame limit was exceeded.")
                if mime_type != "image/gif" and frame_count != 1:
                    if mime_type == "image/png":
                        raise ValueError("Animated PNG is not supported.")
                    raise ValueError("Still media must contain exactly one frame.")
                decoded_pixels = width * height * frame_count
                if decoded_pixels > MAX_DECODED_PIXELS:
                    raise ValueError("The media decoded-pixel limit was exceeded.")

                frames: list[Any] = []
                durations: list[int] = []
                for index in range(frame_count):
                    if work_check is not None:
                        work_check()
                    image.seek(index)
                    if image.size != (width, height):
                        raise ValueError(
                            "Media frame dimensions disagree with the source metadata."
                        )
                    if image.mode not in _SUPPORTED_MODES:
                        raise ValueError("The media frame mode is unsupported.")
                    frame = image.convert("RGBA")
                    frame.load()
                    frames.append(frame.copy())
                    if mime_type == "image/gif":
                        raw_duration = image.info.get("duration", 0)
                        if (
                            isinstance(raw_duration, bool)
                            or not isinstance(raw_duration, (int, float))
                            or not math.isfinite(float(raw_duration))
                        ):
                            raise ValueError("The GIF frame timing is invalid.")
                        duration = max(10, int(raw_duration or 90))
                        if duration > MAX_MEDIA_FRAME_DURATION_MS:
                            raise ValueError("The GIF frame duration limit was exceeded.")
                        durations.append(duration)
                    else:
                        durations.append(0)
                if work_check is not None:
                    work_check()
                try:
                    image.seek(frame_count)
                except EOFError:
                    pass
                else:
                    raise ValueError(
                        "The media frame count disagrees with its decoded content."
                    )
    except Warning as exc:
        raise ValueError("The media decoder emitted an unsafe warning.") from exc
    except ValueError:
        raise
    except (EOFError, OSError, SyntaxError) as exc:
        raise ValueError("The media file could not be completely decoded.") from exc

    duration_ms = sum(durations) if mime_type == "image/gif" else 0
    if mime_type == "image/gif" and (
        duration_ms <= 0 or duration_ms > MAX_MEDIA_DURATION_MS
    ):
        raise ValueError("The media duration limit was exceeded.")
    return DecodedMedia(
        mime_type=mime_type,
        width=width,
        height=height,
        frame_count=frame_count,
        duration_ms=duration_ms,
        sha256=hashlib.sha256(payload).hexdigest(),
        frames=tuple(frames),
        durations_ms=tuple(durations),
    )


def _finite_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number.")
    return float(value)


def validate_source_transform(value: object) -> SourceTransform:
    """Validate the exact version-1 normalized transform schema."""

    if not isinstance(value, Mapping) or set(value) != _TRANSFORM_FIELDS:
        raise ValueError("The source transform schema is unsupported.")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("The source transform version is unsupported.")
    offset_x = _finite_number(value["offset_x"], "offset_x")
    offset_y = _finite_number(value["offset_y"], "offset_y")
    if offset_x == 0.0:
        offset_x = 0.0
    if offset_y == 0.0:
        offset_y = 0.0
    scale_x = _finite_number(value["scale_x"], "scale_x")
    scale_y = _finite_number(value["scale_y"], "scale_y")
    if (
        abs(offset_x) > MAX_TRANSFORM_OFFSET
        or abs(offset_y) > MAX_TRANSFORM_OFFSET
    ):
        raise ValueError("The source transform offset is outside its supported range.")
    if (
        not MIN_TRANSFORM_SCALE <= scale_x <= MAX_TRANSFORM_SCALE
        or not MIN_TRANSFORM_SCALE <= scale_y <= MAX_TRANSFORM_SCALE
    ):
        raise ValueError("The source transform scale is outside its supported range.")
    aspect_locked = value["aspect_locked"]
    if type(aspect_locked) is not bool:
        raise ValueError("aspect_locked must be a boolean.")
    if aspect_locked and not math.isclose(
        scale_x,
        scale_y,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("Locked source transforms require equal scales.")
    sampling = value["sampling"]
    if not isinstance(sampling, str) or sampling not in _SAMPLING:
        raise ValueError("The source transform sampling mode is unsupported.")
    background = value["background"]
    if (
        not isinstance(background, str)
        or not _HEX_COLOR.fullmatch(background)
        or background.upper() != "#000000"
    ):
        raise ValueError("The source transform background is invalid.")
    return SourceTransform(
        version=1,
        offset_x=offset_x,
        offset_y=offset_y,
        scale_x=scale_x,
        scale_y=scale_y,
        aspect_locked=aspect_locked,
        sampling=sampling,
        background=background.upper(),
    )


def _validated_geometry_size(
    value: object,
    label: str,
) -> tuple[int, int]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(type(dimension) is not int or dimension <= 0 for dimension in value)
    ):
        raise ValueError(f"{label} size is invalid.")
    return int(value[0]), int(value[1])


def _round_geometry(value: float) -> int:
    """Apply the framing contract's explicit floor(value + 0.5) rule."""

    return math.floor(value + 0.5)


def resolve_source_geometry(
    source_size: tuple[int, int] | list[int],
    destination_sizes: Sequence[tuple[int, int] | list[int]],
    transform: SourceTransform | Mapping[str, object],
) -> ResolvedSourceGeometry:
    """Resolve one maximum-overlap transform across every destination."""

    source_width, source_height = _validated_geometry_size(
        source_size,
        "Source",
    )
    if (
        not isinstance(destination_sizes, Sequence)
        or isinstance(destination_sizes, (str, bytes))
        or not destination_sizes
    ):
        raise ValueError("At least one destination size is required.")
    destinations = tuple(
        _validated_geometry_size(size, f"Destination {index}")
        for index, size in enumerate(destination_sizes, 1)
    )
    checked = (
        transform
        if isinstance(transform, SourceTransform)
        else validate_source_transform(transform)
    )

    dimensions: list[tuple[int, int]] = []
    limits: list[tuple[float, float]] = []
    for destination_width, destination_height in destinations:
        base_scale = max(
            destination_width / source_width,
            destination_height / source_height,
        )
        rendered_width = max(
            1,
            _round_geometry(source_width * base_scale * checked.scale_x),
        )
        rendered_height = max(
            1,
            _round_geometry(source_height * base_scale * checked.scale_y),
        )
        dimensions.append((rendered_width, rendered_height))
        limits.append(
            (
                min(
                    MAX_TRANSFORM_OFFSET,
                    abs(rendered_width - destination_width)
                    / (2 * destination_width),
                ),
                min(
                    MAX_TRANSFORM_OFFSET,
                    abs(rendered_height - destination_height)
                    / (2 * destination_height),
                ),
            )
        )

    max_offset_x = min(limit[0] for limit in limits)
    max_offset_y = min(limit[1] for limit in limits)
    offset_x = min(max_offset_x, max(-max_offset_x, checked.offset_x))
    offset_y = min(max_offset_y, max(-max_offset_y, checked.offset_y))
    canonical = SourceTransform(
        version=checked.version,
        offset_x=0.0 if offset_x == 0.0 else offset_x,
        offset_y=0.0 if offset_y == 0.0 else offset_y,
        scale_x=checked.scale_x,
        scale_y=checked.scale_y,
        aspect_locked=checked.aspect_locked,
        sampling=checked.sampling,
        background=checked.background,
    )
    boxes = tuple(
        SourceRasterBox(
            rendered_width=rendered_width,
            rendered_height=rendered_height,
            left=_round_geometry(
                (destination_width - rendered_width) / 2
                + canonical.offset_x * destination_width
            ),
            top=_round_geometry(
                (destination_height - rendered_height) / 2
                + canonical.offset_y * destination_height
            ),
        )
        for (
            (destination_width, destination_height),
            (rendered_width, rendered_height),
        ) in zip(destinations, dimensions, strict=True)
    )
    return ResolvedSourceGeometry(
        transform=canonical,
        max_offset_x=max_offset_x,
        max_offset_y=max_offset_y,
        boxes=boxes,
    )


def canonicalize_source_transform(
    transform: SourceTransform | Mapping[str, object],
    source_size: tuple[int, int] | list[int],
    destination_sizes: Sequence[tuple[int, int] | list[int]],
) -> SourceTransform:
    """Return the geometry-safe copy of a valid version-1 transform."""

    return resolve_source_geometry(
        source_size,
        destination_sizes,
        transform,
    ).transform


def _bounded_number(
    value: object,
    minimum: float,
    maximum: float,
    label: str,
) -> float:
    number = _finite_number(value, label)
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} is outside its supported range.")
    return number


def _bounded_integer(
    value: object,
    minimum: int,
    maximum: int,
    label: str,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} is outside its supported range.")
    return value


def _exact_parameters(
    value: object,
    fields: set[str],
    label: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{label} parameters are invalid.")
    return value


def validate_effect_spec(
    value: object,
    *,
    frame_limit: int = 256,
    still_source: bool = False,
) -> dict[str, object]:
    """Validate the shared deterministic version-1 local-effect schema."""

    limit = _bounded_integer(frame_limit, 2, 256, "Effect frame limit")
    if not isinstance(value, Mapping) or set(value) != _EFFECT_FIELDS:
        raise ValueError("The local effect schema is unsupported.")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("The local effect version is unsupported.")
    effect_type = value["type"]
    if not isinstance(effect_type, str):
        raise ValueError("The local effect type is invalid.")
    frame_count = _bounded_integer(
        value["frame_count"],
        2,
        limit,
        "Effect frame count",
    )
    duration_ms = _bounded_integer(
        value["duration_ms"],
        10,
        60_000,
        "Effect frame duration",
    )

    parameters: dict[str, object]
    if effect_type == "pulse":
        raw = _exact_parameters(
            value["parameters"],
            {"minimum_brightness"},
            "Pulse",
        )
        parameters = {
            "minimum_brightness": _bounded_number(
                raw["minimum_brightness"],
                0.0,
                1.0,
                "Pulse minimum brightness",
            )
        }
    elif effect_type == "hue_cycle":
        raw = _exact_parameters(value["parameters"], {"turns"}, "Hue cycle")
        parameters = {
            "turns": _bounded_number(
                raw["turns"],
                0.125,
                4.0,
                "Hue cycle turns",
            )
        }
    elif effect_type == "sweep":
        raw = _exact_parameters(
            value["parameters"],
            {"direction", "width", "minimum_brightness"},
            "Sweep",
        )
        direction = raw["direction"]
        if not isinstance(direction, str) or direction not in _EFFECT_DIRECTIONS:
            raise ValueError("The Sweep direction is unsupported.")
        parameters = {
            "direction": direction,
            "width": _bounded_number(
                raw["width"],
                0.05,
                2.0,
                "Sweep width",
            ),
            "minimum_brightness": _bounded_number(
                raw["minimum_brightness"],
                0.0,
                1.0,
                "Sweep minimum brightness",
            ),
        }
    elif effect_type == "shimmer":
        raw = _exact_parameters(
            value["parameters"],
            {"depth", "seed"},
            "Shimmer",
        )
        parameters = {
            "depth": _bounded_number(
                raw["depth"],
                0.0,
                1.0,
                "Shimmer depth",
            ),
            "seed": _bounded_integer(
                raw["seed"],
                0,
                0xFFFFFFFF,
                "Shimmer seed",
            ),
        }
    elif effect_type == "move_zoom":
        if still_source is not True:
            raise ValueError("Move & zoom requires one imported still source.")
        raw = _exact_parameters(
            value["parameters"],
            {"start_transform", "end_transform"},
            "Move & zoom",
        )
        start = validate_source_transform(raw["start_transform"])
        end = validate_source_transform(raw["end_transform"])
        if (
            start.aspect_locked != end.aspect_locked
            or start.sampling != end.sampling
            or start.background != end.background
        ):
            raise ValueError(
                "Move & zoom endpoints use incompatible transforms."
            )
        parameters = {
            "start_transform": start.to_dict(),
            "end_transform": end.to_dict(),
        }
    else:
        raise ValueError("The local effect type is unsupported.")

    return {
        "version": 1,
        "type": effect_type,
        "frame_count": frame_count,
        "duration_ms": duration_ms,
        "parameters": parameters,
    }


def _parse_color(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str) or not _HEX_COLOR.fullmatch(value):
        raise ValueError("A local effect source color is invalid.")
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))


def _hex_color(red: float, green: float, blue: float) -> str:
    channels = (
        max(0, min(255, math.floor(channel + 0.5)))
        for channel in (red, green, blue)
    )
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def _scale_color(color: str, multiplier: float) -> str:
    red, green, blue = _parse_color(color)
    return _hex_color(
        red * multiplier,
        green * multiplier,
        blue * multiplier,
    )


def _rgb_to_hsv(color: tuple[int, int, int]) -> list[float]:
    red, green, blue = (channel / 255 for channel in color)
    maximum = max(red, green, blue)
    minimum = min(red, green, blue)
    delta = maximum - minimum
    hue = 0.0
    if delta > 0:
        if maximum == red:
            hue = ((green - blue) / delta) % 6
        elif maximum == green:
            hue = (blue - red) / delta + 2
        else:
            hue = (red - green) / delta + 4
        hue /= 6
        if hue < 0:
            hue += 1
    return [hue, 0.0 if maximum == 0 else delta / maximum, maximum]


def _hsv_to_rgb(color: Sequence[float]) -> tuple[float, float, float]:
    hue_value, saturation, value = color
    hue = ((hue_value % 1) + 1) % 1
    section = hue * 6
    index = math.floor(section)
    fraction = section - index
    low = value * (1 - saturation)
    falling = value * (1 - fraction * saturation)
    rising = value * (1 - (1 - fraction) * saturation)
    channels = (
        (value, rising, low),
        (falling, value, low),
        (low, value, rising),
        (low, falling, value),
        (rising, low, value),
        (value, low, falling),
    )[index % 6]
    return tuple(channel * 255 for channel in channels)


def _hue_color(color: str, turns: float) -> str:
    hsv = _rgb_to_hsv(_parse_color(color))
    hsv[0] += turns
    return _hex_color(*_hsv_to_rgb(hsv))


def _noise_phase(seed: int, pixel_index: int) -> float:
    mask = 0xFFFFFFFF
    value = (
        (seed & mask)
        ^ (((pixel_index + 1) & mask) * 0x9E3779B1 & mask)
    ) & mask
    value ^= value >> 16
    value = value * 0x7FEB352D & mask
    value ^= value >> 15
    value = value * 0x846CA68B & mask
    value ^= value >> 16
    return (value / 0x100000000) * math.pi * 2


def _validated_coordinates(
    value: object,
    length: int,
) -> list[dict[str, float]]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != length
    ):
        raise ValueError("Sweep coordinates do not match the source frame.")
    coordinates: list[dict[str, float]] = []
    for index, coordinate in enumerate(value):
        if not isinstance(coordinate, Mapping):
            raise ValueError(f"Sweep coordinate {index + 1} is invalid.")
        coordinates.append(
            {
                "x": _bounded_number(
                    coordinate.get("x"),
                    0.0,
                    1.0,
                    f"Sweep coordinate {index + 1} x",
                ),
                "y": _bounded_number(
                    coordinate.get("y"),
                    0.0,
                    1.0,
                    f"Sweep coordinate {index + 1} y",
                ),
            }
        )
    return coordinates


def _sweep_position(coordinate: Mapping[str, float], direction: str) -> float:
    if direction == "left_to_right":
        return coordinate["x"]
    if direction == "right_to_left":
        return 1 - coordinate["x"]
    if direction == "top_to_bottom":
        return coordinate["y"]
    if direction == "bottom_to_top":
        return 1 - coordinate["y"]
    return (coordinate["x"] + coordinate["y"]) / 2


def _checked_color_effect(effect: object) -> dict[str, object]:
    raw_frame_count = (
        effect.get("frame_count")
        if isinstance(effect, Mapping)
        else None
    )
    checked = validate_effect_spec(
        effect,
        frame_limit=raw_frame_count
        if type(raw_frame_count) is int
        else 256,
        still_source=False,
    )
    if checked["type"] == "move_zoom":
        raise ValueError("Move & zoom renders source transforms, not LED colors.")
    return checked


def _normalized_effect_frames(source_frames: object) -> list[list[str]]:
    if not isinstance(source_frames, (list, tuple)) or not source_frames:
        raise ValueError("A local effect requires source frames.")
    first = source_frames[0]
    pixel_count = len(first) if isinstance(first, (list, tuple)) else -1
    if pixel_count <= 0:
        raise ValueError("A local effect source frame is empty.")
    frames: list[list[str]] = []
    for frame_index, frame in enumerate(source_frames):
        if not isinstance(frame, (list, tuple)) or len(frame) != pixel_count:
            raise ValueError(
                f"Local effect source frame {frame_index + 1} is invalid."
            )
        normalized: list[str] = []
        for color in frame:
            _parse_color(color)
            normalized.append(color.upper())
        frames.append(normalized)
    return frames


def _render_color_effect_frame_checked(
    source: Sequence[str],
    checked: Mapping[str, object],
    frame_index: int,
    *,
    positions: Sequence[Mapping[str, float]] | None,
) -> list[str]:
    frame_count = int(checked["frame_count"])
    if type(frame_index) is not int or not 0 <= frame_index < frame_count:
        raise ValueError("The local effect frame index is invalid.")

    effect_type = str(checked["type"])
    parameters = checked["parameters"]
    assert isinstance(parameters, dict)
    if effect_type == "pulse":
        phase = frame_index / (frame_count - 1)
        wave = math.sin(math.pi * phase) ** 2
        minimum = float(parameters["minimum_brightness"])
        return [
            _scale_color(
                color,
                1 - (1 - minimum) * wave,
            )
            for color in source
        ]
    if effect_type == "hue_cycle":
        turns = float(parameters["turns"]) * frame_index / frame_count
        return [_hue_color(color, turns) for color in source]
    if effect_type == "sweep":
        assert positions is not None
        width = float(parameters["width"])
        progress = frame_index / (frame_count - 1)
        center = -width + progress * (1 + width * 2)
        minimum = float(parameters["minimum_brightness"])
        colors: list[str] = []
        for pixel_index, color in enumerate(source):
            distance = abs(
                _sweep_position(
                    positions[pixel_index],
                    str(parameters["direction"]),
                )
                - center
            )
            mask = max(0.0, min(1.0, 1 - distance / width))
            colors.append(
                _scale_color(
                    color,
                    minimum + (1 - minimum) * mask,
                )
            )
        return colors
    depth = float(parameters["depth"])
    loop_phase = math.pi * 2 * frame_index / frame_count
    return [
        _scale_color(
            color,
            1
            - depth
            + depth
            * (
                0.5
                + 0.5
                * math.sin(
                    loop_phase
                    + _noise_phase(
                        int(parameters["seed"]),
                        pixel_index,
                    )
                )
            ),
        )
        for pixel_index, color in enumerate(source)
    ]


def render_color_effect_frame(
    source_frame: object,
    effect: object,
    frame_index: int,
    *,
    coordinates: object = None,
) -> list[str]:
    """Render one exact color-effect output frame through the shared primitive."""

    checked = _checked_color_effect(effect)
    frames = _normalized_effect_frames([source_frame])
    positions = (
        _validated_coordinates(coordinates, len(frames[0]))
        if checked["type"] == "sweep"
        else None
    )
    return _render_color_effect_frame_checked(
        frames[0],
        checked,
        frame_index,
        positions=positions,
    )


def render_color_effect(
    source_frames: object,
    effect: object,
    *,
    coordinates: object = None,
) -> list[list[str]]:
    """Render color/intensity effects identically to the browser reducer."""

    checked = _checked_color_effect(effect)
    frames = _normalized_effect_frames(source_frames)
    frame_count = int(checked["frame_count"])
    positions = (
        _validated_coordinates(coordinates, len(frames[0]))
        if checked["type"] == "sweep"
        else None
    )
    output: list[list[str]] = []
    for frame_index in range(frame_count):
        source_index = min(
            len(frames) - 1,
            math.floor(frame_index * len(frames) / frame_count),
        )
        output.append(
            _render_color_effect_frame_checked(
                frames[source_index],
                checked,
                frame_index,
                positions=positions,
            )
        )
    return output


def interpolate_move_zoom(
    effect: object,
    *,
    source_size: tuple[int, int] | list[int] | None = None,
    destination_sizes: Sequence[tuple[int, int] | list[int]] | None = None,
) -> list[dict[str, object]]:
    """Expand a validated Move & zoom effect into exact transform keyframes."""

    raw_frame_count = (
        effect.get("frame_count")
        if isinstance(effect, Mapping)
        else None
    )
    checked = validate_effect_spec(
        effect,
        frame_limit=raw_frame_count
        if type(raw_frame_count) is int
        else 256,
        still_source=True,
    )
    if checked["type"] != "move_zoom":
        raise ValueError("Only Move & zoom produces transform keyframes.")
    parameters = checked["parameters"]
    assert isinstance(parameters, dict)
    start = parameters["start_transform"]
    end = parameters["end_transform"]
    assert isinstance(start, dict) and isinstance(end, dict)
    frame_count = int(checked["frame_count"])
    result: list[dict[str, object]] = []
    for index in range(frame_count):
        progress = index / (frame_count - 1)
        interpolated = validate_source_transform(
            {
                **start,
                "offset_x": float(start["offset_x"])
                + (float(end["offset_x"]) - float(start["offset_x"]))
                * progress,
                "offset_y": float(start["offset_y"])
                + (float(end["offset_y"]) - float(start["offset_y"]))
                * progress,
                "scale_x": float(start["scale_x"])
                + (float(end["scale_x"]) - float(start["scale_x"]))
                * progress,
                "scale_y": float(start["scale_y"])
                + (float(end["scale_y"]) - float(start["scale_y"]))
                * progress,
            }
        )
        if (source_size is None) != (destination_sizes is None):
            raise ValueError(
                "Move & zoom geometry requires source and destination sizes."
            )
        if source_size is not None and destination_sizes is not None:
            interpolated = canonicalize_source_transform(
                interpolated,
                source_size,
                destination_sizes,
            )
        result.append(interpolated.to_dict())
    return result


def _resampling_filter(image_module: Any, sampling: str) -> Any:
    return {
        "nearest": image_module.Resampling.NEAREST,
        "box": image_module.Resampling.BOX,
        "lanczos": image_module.Resampling.LANCZOS,
    }[sampling]


def _composite_background(frame: Any, background: str) -> Any:
    from PIL import Image

    rgba = frame.convert("RGBA")
    color = tuple(int(background[index : index + 2], 16) for index in (1, 3, 5))
    canvas = Image.new("RGBA", rgba.size, (*color, 255))
    return Image.alpha_composite(canvas, rgba).convert("RGB")


def _legacy_center_crop(frame: Any, size: tuple[int, int], sampling: str) -> Any:
    from PIL import Image

    width, height = size
    fitted = frame
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
        fitted = fitted.resize(size, _resampling_filter(Image, sampling))
    return fitted


def render_source_frame(
    frame: Any,
    destination_size: tuple[int, int],
    transform: SourceTransform | Mapping[str, object],
) -> Any:
    """Render one source frame into a destination raster without orientation drift."""

    from PIL import Image

    checked = (
        transform
        if isinstance(transform, SourceTransform)
        else validate_source_transform(transform)
    )
    if (
        not isinstance(destination_size, tuple)
        or len(destination_size) != 2
        or any(type(value) is not int or value <= 0 for value in destination_size)
    ):
        raise ValueError("The selected lighting area has an invalid size.")
    width, height = destination_size
    if width * height > MAX_RENDER_PIXELS:
        raise ValueError("The selected lighting area is too large to render.")
    source = _composite_background(frame, checked.background)
    geometry = resolve_source_geometry(
        (source.width, source.height),
        [destination_size],
        checked,
    )
    checked = geometry.transform
    if (
        checked.offset_x == 0.0
        and checked.offset_y == 0.0
        and checked.scale_x == 1.0
        and checked.scale_y == 1.0
    ):
        return _legacy_center_crop(source, destination_size, checked.sampling)

    box = geometry.boxes[0]
    rendered_width = box.rendered_width
    rendered_height = box.rendered_height
    if rendered_width * rendered_height > MAX_RENDER_PIXELS:
        raise ValueError("Zoom out: this framing is too large to render.")
    rendered = source
    if rendered.size != (rendered_width, rendered_height):
        rendered = rendered.resize(
            (rendered_width, rendered_height),
            _resampling_filter(Image, checked.sampling),
        )
    background = tuple(
        int(checked.background[index : index + 2], 16) for index in (1, 3, 5)
    )
    output = Image.new("RGB", destination_size, background)
    output.paste(rendered, (box.left, box.top))
    return output


def _source_preview_size(width: int, height: int) -> tuple[int, int]:
    """Fit a complete source frame inside the display-only preview ceiling."""

    if width * height <= MAX_SOURCE_PREVIEW_PIXELS:
        return width, height
    scale = math.sqrt(MAX_SOURCE_PREVIEW_PIXELS / (width * height))
    preview_width = max(1, math.floor(width * scale))
    preview_height = max(1, math.floor(height * scale))
    while preview_width * preview_height > MAX_SOURCE_PREVIEW_PIXELS:
        if preview_width / width >= preview_height / height:
            preview_width -= 1
        else:
            preview_height -= 1
    return preview_width, preview_height


def _encode_source_preview(frame: Any, size: tuple[int, int]) -> bytes:
    """Encode one untransformed complete decoded frame as a static PNG."""

    from PIL import Image

    projected = frame
    if tuple(frame.size) != size:
        projected = frame.resize(size, Image.Resampling.LANCZOS)
    output = BytesIO()
    projected.save(output, format="PNG")
    return output.getvalue()


class MediaRenderCoordinator:
    """Coordinate bounded pathless media sessions and exact transient renders."""

    def __init__(
        self,
        catalog: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        from .library import LibraryCatalog

        if not isinstance(catalog, LibraryCatalog):
            raise TypeError("catalog must be a LibraryCatalog")
        self.catalog = catalog
        self._clock = clock
        self._lock = threading.Lock()
        self._latest_epochs: dict[
            tuple[str, str | None, str, tuple[str, ...]], int
        ] = {}
        self._active_counts: dict[str, int] = {}
        self._sessions: OrderedDict[str, _PreviewSessionCacheEntry] = OrderedDict()
        self._closed = False

    def active_catalog_ids(self) -> set[str]:
        with self._lock:
            return {
                catalog_id
                for catalog_id, count in self._active_counts.items()
                if count > 0
            }

    def close(self) -> None:
        """Invalidate every transient session owned by this catalog identity."""

        with self._lock:
            self._closed = True
            self._sessions.clear()
            self._latest_epochs.clear()

    def invalidate_catalog_id(self, catalog_id: str) -> None:
        """Discard cached state after one Library item is removed or deleted."""

        with self._lock:
            for session_id in [
                session_id
                for session_id, entry in self._sessions.items()
                if entry.prepared.catalog_id == catalog_id
            ]:
                self._drop_session_locked(session_id)
            for key in [key for key in self._latest_epochs if key[0] == catalog_id]:
                self._latest_epochs.pop(key, None)

    def _drop_session_locked(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        for key in [key for key in self._latest_epochs if key[1] == session_id]:
            self._latest_epochs.pop(key, None)

    def _purge_expired_locked(self, now: float) -> None:
        for session_id in [
            session_id
            for session_id, entry in self._sessions.items()
            if now - entry.last_access >= PREVIEW_SESSION_TTL_SECONDS
        ]:
            self._drop_session_locked(session_id)

    def _start_active(self, catalog_id: str) -> None:
        with self._lock:
            if self._closed:
                raise ValueError("This media preview session is no longer available.")
            self._active_counts[catalog_id] = (
                self._active_counts.get(catalog_id, 0) + 1
            )

    def _finish_active(self, catalog_id: str) -> None:
        with self._lock:
            remaining = self._active_counts.get(catalog_id, 0) - 1
            if remaining > 0:
                self._active_counts[catalog_id] = remaining
            else:
                self._active_counts.pop(catalog_id, None)

    @staticmethod
    def _checked_session_id(session_id: object) -> str:
        if (
            not isinstance(session_id, str)
            or not 32 <= len(session_id) <= 200
            or any(
                character
                not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
                for character in session_id
            )
        ):
            raise ValueError("The media preview session is invalid.")
        return session_id

    def _source_asset(
        self,
        catalog_id: str,
        *,
        verify_content: bool,
    ) -> tuple[dict[str, object], Any]:
        detail = self.catalog.get(catalog_id)
        item = detail.get("item")
        source = item.get("source") if isinstance(item, dict) else None
        if (
            detail.get("namespace") != "item"
            or detail.get("kind") != "media_source"
            or detail.get("removed") is not False
            or not isinstance(source, dict)
        ):
            raise ValueError("This Library item is not an available media source.")
        asset_id = source.get("asset_id")
        if not isinstance(asset_id, str):
            raise ValueError("This Library media source has an invalid asset.")
        owned = self.catalog.resolve_asset(
            catalog_id,
            asset_id,
            verify_content=verify_content,
        )
        record = owned.record
        byte_size = record.get("byte_size")
        if (
            record.get("kind") != "source"
            or type(byte_size) is not int
            or not 0 < byte_size <= MAX_MEDIA_BYTES
            or record.get("mime_type") != source.get("mime_type")
            or record.get("sha256") != source.get("sha256")
        ):
            raise ValueError("The saved media source metadata no longer matches its asset.")
        return source, owned

    @staticmethod
    def _source_matches(
        source: Mapping[str, object],
        owned: Any,
        decoded: DecodedMedia,
    ) -> bool:
        return (
            source.get("asset_id") == owned.record.get("asset_id")
            and source.get("mime_type") == decoded.mime_type
            and source.get("sha256") == decoded.sha256
            and source.get("width") == decoded.width
            and source.get("height") == decoded.height
            and source.get("frame_count") == decoded.frame_count
            and source.get("duration_ms") == decoded.duration_ms
        )

    def _create_session(self, catalog_id: str) -> PreparedMediaSession:
        source, owned = self._source_asset(catalog_id, verify_content=False)
        byte_size = int(owned.record["byte_size"])
        with owned.open_verified() as stream:
            payload = stream.read(byte_size + 1)
        if len(payload) != byte_size:
            raise ValueError("The saved media source changed while it was read.")
        decoded = decode_media(payload)
        if not self._source_matches(source, owned, decoded):
            raise ValueError("The saved media source metadata no longer matches its asset.")

        with self._lock:
            if self._closed:
                raise ValueError("This media preview session is no longer available.")
            self._purge_expired_locked(self._clock())
            session_id = secrets.token_urlsafe(32)
            while session_id in self._sessions:
                session_id = secrets.token_urlsafe(32)
            prepared = PreparedMediaSession(
                session_id=session_id,
                catalog_id=catalog_id,
                asset_id=str(source["asset_id"]),
                asset_sha256=decoded.sha256,
                decoded=decoded,
            )
            while self._sessions and (
                len(self._sessions) >= MAX_PREVIEW_SESSIONS
                or sum(
                    entry.prepared.decoded_pixels
                    for entry in self._sessions.values()
                )
                + prepared.decoded_pixels
                > MAX_PREVIEW_DECODED_PIXELS
            ):
                oldest_session_id = next(iter(self._sessions))
                self._drop_session_locked(oldest_session_id)
            if prepared.decoded_pixels > MAX_PREVIEW_DECODED_PIXELS:
                raise ValueError("The media preview decoded-pixel limit was exceeded.")
            self._sessions[session_id] = _PreviewSessionCacheEntry(
                prepared=prepared,
                last_access=self._clock(),
                source_previews=OrderedDict(),
            )
            return prepared

    def _get_session(
        self,
        catalog_id: str,
        session_id: object,
    ) -> PreparedMediaSession:
        checked_id = self._checked_session_id(session_id)
        with self._lock:
            if self._closed:
                raise ValueError("This media preview session is no longer available.")
            self._purge_expired_locked(self._clock())
            entry = self._sessions.get(checked_id)
            if entry is None or entry.prepared.catalog_id != catalog_id:
                raise ValueError("This media preview session is no longer available.")
            prepared = entry.prepared

        try:
            # Session creation already verified and decoded the exact asset bytes.
            # Reuse rechecks ownership, safe path/descriptor state, size, and the
            # current manifest digest without rereading up to 12 MB per live frame.
            source, owned = self._source_asset(catalog_id, verify_content=False)
            if (
                prepared.asset_id != source.get("asset_id")
                or prepared.asset_sha256 != source.get("sha256")
                or not self._source_matches(source, owned, prepared.decoded)
            ):
                raise ValueError(
                    "The saved media source metadata no longer matches its asset."
                )
        except Exception:
            with self._lock:
                current = self._sessions.get(checked_id)
                if current is not None and current.prepared is prepared:
                    self._drop_session_locked(checked_id)
            raise

        with self._lock:
            current = self._sessions.get(checked_id)
            if (
                self._closed
                or current is None
                or current.prepared is not prepared
            ):
                raise ValueError("This media preview session is no longer available.")
            current.last_access = self._clock()
            self._sessions.move_to_end(checked_id)
        return prepared

    @staticmethod
    def _source_preview_descriptor(
        prepared: PreparedMediaSession,
    ) -> dict[str, object]:
        width, height = _source_preview_size(
            prepared.decoded.width,
            prepared.decoded.height,
        )
        return {
            "mime_type": "image/png",
            "width": width,
            "height": height,
            "frame_count": prepared.decoded.frame_count,
            "display_only": True,
        }

    def _session_response(
        self,
        prepared: PreparedMediaSession,
    ) -> dict[str, object]:
        decoded = prepared.decoded
        return {
            "catalog_id": prepared.catalog_id,
            "preview_session_id": prepared.session_id,
            "source": {
                "mime_type": decoded.mime_type,
                "width": decoded.width,
                "height": decoded.height,
                "frame_count": decoded.frame_count,
                "duration_ms": decoded.duration_ms,
                "sha256": decoded.sha256,
            },
            "source_preview": self._source_preview_descriptor(prepared),
        }

    def prepare_preview_session(self, catalog_id: str) -> dict[str, object]:
        """Decode and retain one verified Library media source within the LRU."""

        self._start_active(catalog_id)
        try:
            return self._session_response(self._create_session(catalog_id))
        finally:
            self._finish_active(catalog_id)

    @staticmethod
    def _validate_render_request(
        *,
        product_id: object,
        targets: object,
        transform: object,
        epoch: object,
        effects: object,
    ) -> SourceTransform:
        if type(epoch) is not int or not 0 <= epoch <= 2**53:
            raise ValueError("The media render epoch is invalid.")
        if not isinstance(product_id, str) or not product_id:
            raise ValueError("A destination product_id is required.")
        if (
            not isinstance(targets, (list, tuple))
            or not targets
            or any(not isinstance(target, str) or not target for target in targets)
        ):
            raise ValueError("Media render targets must be a non-empty list.")
        if (
            not isinstance(effects, (list, tuple))
            or len(effects) > 8
            or any(not isinstance(effect, Mapping) for effect in effects)
        ):
            raise ValueError("Media render effects must be a bounded list.")
        return validate_source_transform(transform)

    def _prepare_render(
        self,
        session: PreparedMediaSession,
        *,
        product_id: str,
        targets: Sequence[str],
        checked_transform: SourceTransform,
        effects: Sequence[Mapping[str, object]],
    ) -> PreparedMediaRender:
        from . import device_mapping

        model, resolved_targets, destination_sizes = (
            device_mapping.media_target_sizes(product_id, targets)
        )
        frame_limit = device_mapping.family_spec(model).frame_cap
        source_size = (session.decoded.width, session.decoded.height)
        canonical_transform = canonicalize_source_transform(
            checked_transform,
            source_size,
            destination_sizes,
        )
        checked_effects = tuple(
            validate_effect_spec(
                effect,
                frame_limit=frame_limit,
                still_source=session.decoded.frame_count == 1,
            )
            for effect in effects
        )
        move_effects = tuple(
            effect for effect in checked_effects if effect["type"] == "move_zoom"
        )
        if len(move_effects) > 1:
            raise ValueError(
                "A media composition can contain only one Move & zoom effect."
            )
        if move_effects and checked_effects[0]["type"] != "move_zoom":
            raise ValueError("Move & zoom must be the first media composition effect.")

        if move_effects:
            raw_transforms = interpolate_move_zoom(
                move_effects[0],
                source_size=source_size,
                destination_sizes=destination_sizes,
            )
            resolved_transforms = tuple(
                validate_source_transform(value) for value in raw_transforms
            )
            base_indices, base_duration, _resampled = (
                device_mapping.media_timeline_indices(
                    [int(move_effects[0]["duration_ms"])]
                    * len(resolved_transforms),
                    frame_limit=frame_limit,
                )
            )
            base_entries = [
                PreviewTimelineEntry(
                    index=output_index,
                    source_frame_index=0,
                    duration_ms=base_duration,
                    resolved_transform=resolved_transforms[transform_index],
                    effect_phase=(
                        (
                            "move_zoom",
                            transform_index,
                            len(resolved_transforms),
                        ),
                    ),
                    base_frame_index=output_index,
                    color_effect_indices=(),
                )
                for output_index, transform_index in enumerate(base_indices)
            ]
        else:
            resolved_transforms = ()
            base_indices, base_duration, _resampled = (
                device_mapping.media_timeline_indices(
                    session.decoded.durations_ms,
                    frame_limit=frame_limit,
                )
            )
            base_entries = [
                PreviewTimelineEntry(
                    index=output_index,
                    source_frame_index=source_frame_index,
                    duration_ms=base_duration,
                    resolved_transform=canonical_transform,
                    effect_phase=(),
                    base_frame_index=output_index,
                    color_effect_indices=(),
                )
                for output_index, source_frame_index in enumerate(base_indices)
            ]

        color_effects = tuple(
            effect for effect in checked_effects if effect["type"] != "move_zoom"
        )
        timeline = base_entries
        for effect in color_effects:
            previous = timeline
            frame_count = int(effect["frame_count"])
            duration_ms = int(effect["duration_ms"])
            timeline = []
            for frame_index in range(frame_count):
                source_index = min(
                    len(previous) - 1,
                    math.floor(frame_index * len(previous) / frame_count),
                )
                source_entry = previous[source_index]
                timeline.append(
                    PreviewTimelineEntry(
                        index=frame_index,
                        source_frame_index=source_entry.source_frame_index,
                        duration_ms=duration_ms,
                        resolved_transform=source_entry.resolved_transform,
                        effect_phase=(
                            *source_entry.effect_phase,
                            (str(effect["type"]), frame_index, frame_count),
                        ),
                        base_frame_index=source_entry.base_frame_index,
                        color_effect_indices=(
                            *source_entry.color_effect_indices,
                            frame_index,
                        ),
                    )
                )

        return PreparedMediaRender(
            session=session,
            product_id=product_id,
            model=model,
            targets=tuple(resolved_targets),
            destination_sizes=destination_sizes,
            frame_limit=frame_limit,
            transform=canonical_transform,
            effects=checked_effects,
            resolved_transforms=resolved_transforms,
            color_effects=color_effects,
            timeline=tuple(timeline),
        )

    @staticmethod
    def _target_effect_coordinates(
        model: str,
        target: str,
        pixel_count: int,
    ) -> list[dict[str, float]]:
        from . import device_mapping

        target_capability = next(
            entry
            for entry in device_mapping.target_capabilities()[model]["targets"]
            if entry["name"] == target
        )
        coordinates = [
            {"x": 0.5, "y": 0.5} for _index in range(pixel_count)
        ]
        width = target_capability["width"]
        height = target_capability["height"]
        for source_index, output_index in enumerate(target_capability["map"]):
            if output_index < 0:
                continue
            coordinates[output_index] = {
                "x": ((source_index % width) + 0.5) / width,
                "y": ((source_index // width) + 0.5) / height,
            }
        for copy_rule in target_capability["copies"]:
            coordinates[copy_rule["output_index"]] = copy.deepcopy(
                coordinates[copy_rule["source_index"]]
            )
        return coordinates

    def _apply_full_color_effects(
        self,
        mapped: dict[str, Any],
        effects: Sequence[Mapping[str, object]],
        check: Callable[[], None],
    ) -> None:
        coordinate_cache: dict[str, list[dict[str, float]]] = {}
        for effect in effects:
            for target, track in mapped["tracks"].items():
                check()
                coordinates = coordinate_cache.get(target)
                if coordinates is None:
                    coordinates = self._target_effect_coordinates(
                        str(mapped["model"]),
                        target,
                        int(track["pixels"]),
                    )
                    coordinate_cache[target] = coordinates
                frames = render_color_effect(
                    track["frames"],
                    effect,
                    coordinates=coordinates,
                )
                track["frames"] = frames
                track["frame_count"] = len(frames)
            mapped["source_frames"] = int(effect["frame_count"])
            mapped["decoded_frames"] = int(effect["frame_count"])
            mapped["duration_ms"] = int(effect["duration_ms"])
            mapped["source_duration_ms"] = (
                int(effect["frame_count"]) * int(effect["duration_ms"])
            )
            mapped["timing_resampled"] = False

    def _begin_epoch(
        self,
        prepared: PreparedMediaRender,
        epoch: int,
        *,
        session_scoped: bool,
    ) -> Callable[[], None]:
        session = prepared.session
        key = (
            session.catalog_id,
            session.session_id if session_scoped else None,
            prepared.product_id,
            prepared.targets,
        )
        with self._lock:
            current = self._sessions.get(session.session_id)
            if (
                self._closed
                or current is None
                or current.prepared is not session
            ):
                raise ValueError("This media preview session is no longer available.")
            latest = self._latest_epochs.get(key)
            if latest is not None and epoch <= latest:
                raise MediaRenderSuperseded(
                    "A newer media preview superseded this render."
                )
            self._latest_epochs[key] = epoch

        def check() -> None:
            with self._lock:
                current_entry = self._sessions.get(session.session_id)
                if (
                    self._closed
                    or current_entry is None
                    or current_entry.prepared is not session
                    or self._latest_epochs.get(key) != epoch
                ):
                    raise MediaRenderSuperseded(
                        "A newer media preview superseded this render."
                    )

        return check

    def _render_full_mapping(
        self,
        prepared: PreparedMediaRender,
        *,
        check: Callable[[], None],
        progress: Callable[[int, int], None] | None,
    ) -> dict[str, Any]:
        from . import device_mapping

        move_effect = next(
            (effect for effect in prepared.effects if effect["type"] == "move_zoom"),
            None,
        )
        if move_effect is not None:
            mapped = device_mapping.compose_media_transform_sequence_to_led_tracks(
                prepared.session.decoded.frames[0],
                [int(move_effect["duration_ms"])]
                * len(prepared.resolved_transforms),
                prepared.targets,
                [transform.to_dict() for transform in prepared.resolved_transforms],
                prepared.product_id,
                work_check=check,
                progress=progress,
            )
        else:
            mapped = device_mapping.compose_media_frames_to_led_tracks(
                prepared.session.decoded.frames,
                prepared.session.decoded.durations_ms,
                prepared.targets,
                prepared.transform.to_dict(),
                prepared.product_id,
                work_check=check,
                progress=progress,
            )
        self._apply_full_color_effects(mapped, prepared.color_effects, check)
        expected_frames = len(prepared.timeline)
        if any(
            track.get("frame_count") != expected_frames
            for track in mapped["tracks"].values()
        ):
            raise ValueError("The media preview timeline does not match its LED frames.")
        return mapped

    def render(
        self,
        catalog_id: str,
        *,
        product_id: str,
        targets: Sequence[str],
        transform: Mapping[str, object],
        epoch: int,
        effects: Sequence[Mapping[str, object]] = (),
        preview_session_id: str | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, object]:
        checked_transform = self._validate_render_request(
            product_id=product_id,
            targets=targets,
            transform=transform,
            epoch=epoch,
            effects=effects,
        )
        if preview_session_id is not None:
            self._checked_session_id(preview_session_id)
        self._start_active(catalog_id)
        try:
            session = (
                self._create_session(catalog_id)
                if preview_session_id is None
                else self._get_session(catalog_id, preview_session_id)
            )
            prepared = self._prepare_render(
                session,
                product_id=product_id,
                targets=targets,
                checked_transform=checked_transform,
                effects=effects,
            )
            check = self._begin_epoch(
                prepared,
                epoch,
                session_scoped=preview_session_id is not None,
            )
            check()
            mapped = self._render_full_mapping(
                prepared,
                check=check,
                progress=progress,
            )
            check()
            return {
                "catalog_id": catalog_id,
                "epoch": epoch,
                "preview_session_id": session.session_id,
                "transform": prepared.transform.to_dict(),
                "effects": [copy.deepcopy(effect) for effect in prepared.effects],
                "resolved_transforms": [
                    value.to_dict() for value in prepared.resolved_transforms
                ],
                "preview_timeline": [
                    entry.to_dict() for entry in prepared.timeline
                ],
                "source_preview": self._source_preview_descriptor(session),
                "mapped_result": mapped,
            }
        finally:
            self._finish_active(catalog_id)

    def render_frame(
        self,
        catalog_id: str,
        *,
        preview_session_id: str,
        product_id: str,
        targets: Sequence[str],
        transform: Mapping[str, object],
        effects: Sequence[Mapping[str, object]],
        frame_index: int,
        epoch: int,
    ) -> dict[str, object]:
        checked_transform = self._validate_render_request(
            product_id=product_id,
            targets=targets,
            transform=transform,
            epoch=epoch,
            effects=effects,
        )
        checked_session_id = self._checked_session_id(preview_session_id)
        if type(frame_index) is not int or not 0 <= frame_index < MAX_MEDIA_FRAMES:
            raise ValueError("The media preview frame index is invalid.")
        self._start_active(catalog_id)
        try:
            session = self._get_session(catalog_id, checked_session_id)
            prepared = self._prepare_render(
                session,
                product_id=product_id,
                targets=targets,
                checked_transform=checked_transform,
                effects=effects,
            )
            if frame_index >= len(prepared.timeline):
                raise ValueError("The media preview frame index is invalid.")
            check = self._begin_epoch(prepared, epoch, session_scoped=True)
            check()
            entry = prepared.timeline[frame_index]
            from . import device_mapping

            mapped = device_mapping.map_media_frame_to_led_tracks(
                session.decoded.frames[entry.source_frame_index],
                prepared.targets,
                entry.resolved_transform.to_dict(),
                prepared.product_id,
                work_check=check,
            )
            coordinate_cache: dict[str, list[dict[str, float]]] = {}
            for effect, effect_index in zip(
                prepared.color_effects,
                entry.color_effect_indices,
                strict=True,
            ):
                for target, track in mapped["tracks"].items():
                    check()
                    coordinates = coordinate_cache.get(target)
                    if coordinates is None:
                        coordinates = self._target_effect_coordinates(
                            prepared.model,
                            target,
                            int(track["pixels"]),
                        )
                        coordinate_cache[target] = coordinates
                    track["colors"] = render_color_effect_frame(
                        track["colors"],
                        effect,
                        effect_index,
                        coordinates=coordinates,
                    )
            check()
            return {
                "catalog_id": catalog_id,
                "epoch": epoch,
                "preview_session_id": session.session_id,
                "transform": prepared.transform.to_dict(),
                "effects": [copy.deepcopy(effect) for effect in prepared.effects],
                "resolved_transforms": [
                    value.to_dict() for value in prepared.resolved_transforms
                ],
                "timeline_entry": entry.to_dict(),
                "source_preview": self._source_preview_descriptor(session),
                "mapped_frame": mapped,
            }
        finally:
            self._finish_active(catalog_id)

    def source_frame_png(
        self,
        catalog_id: str,
        *,
        preview_session_id: str,
        source_frame_index: int,
    ) -> bytes:
        checked_session_id = self._checked_session_id(preview_session_id)
        if (
            type(source_frame_index) is not int
            or not 0 <= source_frame_index < MAX_MEDIA_FRAMES
        ):
            raise ValueError("The source preview frame index is invalid.")
        self._start_active(catalog_id)
        try:
            session = self._get_session(catalog_id, checked_session_id)
            if source_frame_index >= session.decoded.frame_count:
                raise ValueError("The source preview frame index is invalid.")
            with self._lock:
                entry = self._sessions.get(checked_session_id)
                cached = (
                    entry.source_previews.get(source_frame_index)
                    if entry is not None and entry.prepared is session
                    else None
                )
                if cached is not None:
                    entry.source_previews.move_to_end(source_frame_index)
                    return cached

            descriptor = self._source_preview_descriptor(session)
            payload = _encode_source_preview(
                session.decoded.frames[source_frame_index],
                (int(descriptor["width"]), int(descriptor["height"])),
            )
            with self._lock:
                entry = self._sessions.get(checked_session_id)
                if (
                    not self._closed
                    and entry is not None
                    and entry.prepared is session
                    and len(payload) <= MAX_SOURCE_PREVIEW_CACHE_BYTES
                ):
                    old = entry.source_previews.pop(source_frame_index, None)
                    if old is not None:
                        entry.source_preview_bytes -= len(old)
                    while entry.source_previews and (
                        len(entry.source_previews) >= MAX_SOURCE_PREVIEW_CACHE_ENTRIES
                        or entry.source_preview_bytes + len(payload)
                        > MAX_SOURCE_PREVIEW_CACHE_BYTES
                    ):
                        _old_index, old_payload = entry.source_previews.popitem(
                            last=False
                        )
                        entry.source_preview_bytes -= len(old_payload)
                    entry.source_previews[source_frame_index] = payload
                    entry.source_preview_bytes += len(payload)
            return payload
        finally:
            self._finish_active(catalog_id)


__all__ = [
    "DecodedMedia",
    "MAX_DECODED_PIXELS",
    "MAX_MEDIA_BYTES",
    "MAX_MEDIA_DIMENSION",
    "MAX_MEDIA_DURATION_MS",
    "MAX_MEDIA_FRAMES",
    "MediaRenderCoordinator",
    "MediaRenderSuperseded",
    "PreparedMediaRender",
    "PreparedMediaSession",
    "PreviewTimelineEntry",
    "ResolvedSourceGeometry",
    "SourceRasterBox",
    "SourceTransform",
    "canonicalize_source_transform",
    "decode_media",
    "interpolate_move_zoom",
    "render_color_effect",
    "render_color_effect_frame",
    "render_source_frame",
    "resolve_source_geometry",
    "validate_effect_spec",
    "validate_source_transform",
]
