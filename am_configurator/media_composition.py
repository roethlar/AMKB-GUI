"""Strict imported-media validation and transform-aware local rendering."""

from __future__ import annotations

import copy
import hashlib
import math
import re
import struct
import threading
import warnings
import zlib
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


class MediaRenderSuperseded(RuntimeError):
    """A newer editor epoch replaced this transient render."""


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


def render_color_effect(
    source_frames: object,
    effect: object,
    *,
    coordinates: object = None,
) -> list[list[str]]:
    """Render color/intensity effects identically to the browser reducer."""

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

    effect_type = str(checked["type"])
    positions = (
        _validated_coordinates(coordinates, pixel_count)
        if effect_type == "sweep"
        else None
    )
    frame_count = int(checked["frame_count"])
    parameters = checked["parameters"]
    assert isinstance(parameters, dict)
    output: list[list[str]] = []
    for frame_index in range(frame_count):
        source_index = min(
            len(frames) - 1,
            math.floor(frame_index * len(frames) / frame_count),
        )
        source = frames[source_index]
        if effect_type == "pulse":
            phase = frame_index / (frame_count - 1)
            wave = math.sin(math.pi * phase) ** 2
            minimum = float(parameters["minimum_brightness"])
            output.append(
                [
                    _scale_color(
                        color,
                        1 - (1 - minimum) * wave,
                    )
                    for color in source
                ]
            )
        elif effect_type == "hue_cycle":
            turns = (
                float(parameters["turns"])
                * frame_index
                / frame_count
            )
            output.append([_hue_color(color, turns) for color in source])
        elif effect_type == "sweep":
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
            output.append(colors)
        else:
            depth = float(parameters["depth"])
            loop_phase = math.pi * 2 * frame_index / frame_count
            output.append(
                [
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
            )
    return output


def interpolate_move_zoom(effect: object) -> list[dict[str, object]]:
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
        result.append(
            validate_source_transform(
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
            ).to_dict()
        )
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
        raise ValueError("The destination raster size is invalid.")
    width, height = destination_size
    if width * height > MAX_RENDER_PIXELS:
        raise ValueError("The destination raster is too large.")
    source = _composite_background(frame, checked.background)
    if (
        checked.offset_x == 0.0
        and checked.offset_y == 0.0
        and checked.scale_x == 1.0
        and checked.scale_y == 1.0
    ):
        return _legacy_center_crop(source, destination_size, checked.sampling)

    base_scale = max(width / source.width, height / source.height)
    rendered_width = max(1, round(source.width * base_scale * checked.scale_x))
    rendered_height = max(1, round(source.height * base_scale * checked.scale_y))
    if rendered_width * rendered_height > MAX_RENDER_PIXELS:
        raise ValueError("The transformed source raster is too large.")
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
    left = round((width - rendered_width) / 2 + checked.offset_x * width)
    top = round((height - rendered_height) / 2 + checked.offset_y * height)
    output.paste(rendered, (left, top))
    return output


class MediaRenderCoordinator:
    """Coordinate pathless transient renders with monotonic editor epochs."""

    def __init__(self, catalog: Any) -> None:
        from .library import LibraryCatalog

        if not isinstance(catalog, LibraryCatalog):
            raise TypeError("catalog must be a LibraryCatalog")
        self.catalog = catalog
        self._lock = threading.Lock()
        self._latest_epochs: dict[str, int] = {}
        self._active_counts: dict[str, int] = {}

    def active_catalog_ids(self) -> set[str]:
        with self._lock:
            return {
                catalog_id
                for catalog_id, count in self._active_counts.items()
                if count > 0
            }

    def _begin(self, catalog_id: str, epoch: int) -> Callable[[], None]:
        with self._lock:
            latest = self._latest_epochs.get(catalog_id)
            if latest is not None and epoch <= latest:
                raise MediaRenderSuperseded(
                    "A newer media preview superseded this render."
                )
            self._latest_epochs[catalog_id] = epoch
            self._active_counts[catalog_id] = (
                self._active_counts.get(catalog_id, 0) + 1
            )

        def check() -> None:
            with self._lock:
                if self._latest_epochs.get(catalog_id) != epoch:
                    raise MediaRenderSuperseded(
                        "A newer media preview superseded this render."
                    )

        return check

    def _finish(self, catalog_id: str) -> None:
        with self._lock:
            remaining = self._active_counts.get(catalog_id, 0) - 1
            if remaining > 0:
                self._active_counts[catalog_id] = remaining
            else:
                self._active_counts.pop(catalog_id, None)

    def render(
        self,
        catalog_id: str,
        *,
        product_id: str,
        targets: Sequence[str],
        transform: Mapping[str, object],
        epoch: int,
        effects: Sequence[Mapping[str, object]] = (),
        progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, object]:
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
        checked_transform = validate_source_transform(transform)
        detail = self.catalog.get(catalog_id)
        item = detail.get("item")
        if (
            detail.get("namespace") != "item"
            or detail.get("kind") != "media_source"
            or detail.get("removed") is not False
            or not isinstance(item, dict)
            or not isinstance(item.get("source"), dict)
        ):
            raise ValueError("This Library item is not an available media source.")

        check = self._begin(catalog_id, epoch)
        try:
            check()
            source = item["source"]
            owned = self.catalog.resolve_asset(
                catalog_id,
                source["asset_id"],
                verify_content=False,
            )
            byte_size = owned.record["byte_size"]
            if (
                type(byte_size) is not int
                or byte_size <= 0
                or byte_size > MAX_MEDIA_BYTES
            ):
                raise ValueError("The saved media source exceeds the size limit.")
            with owned.open_verified() as stream:
                payload = stream.read(byte_size + 1)
            if len(payload) != byte_size:
                raise ValueError("The saved media source changed while it was read.")
            decoded = decode_media(payload, work_check=check)
            if (
                decoded.mime_type != source["mime_type"]
                or decoded.sha256 != source["sha256"]
                or decoded.width != source["width"]
                or decoded.height != source["height"]
                or decoded.frame_count != source["frame_count"]
                or decoded.duration_ms != source["duration_ms"]
            ):
                raise ValueError(
                    "The saved media source metadata no longer matches its asset."
                )
            check()
            from . import device_mapping

            frame_limit = device_mapping.family_spec(
                device_mapping.led_model(product_id)
            ).frame_cap
            checked_effects = [
                validate_effect_spec(
                    effect,
                    frame_limit=frame_limit,
                    still_source=decoded.frame_count == 1,
                )
                for effect in effects
            ]
            move_effects = [
                effect
                for effect in checked_effects
                if effect["type"] == "move_zoom"
            ]
            if len(move_effects) > 1:
                raise ValueError(
                    "A media composition can contain only one Move & zoom effect."
                )
            if move_effects:
                if checked_effects[0]["type"] != "move_zoom":
                    raise ValueError(
                        "Move & zoom must be the first media composition effect."
                    )
                transforms = interpolate_move_zoom(move_effects[0])
                raster, resolved_targets = device_mapping.generation_spec(
                    product_id,
                    list(targets),
                    len(transforms),
                )
                rendered_frames = [
                    render_source_frame(
                        decoded.frames[0],
                        (raster.width, raster.height),
                        frame_transform,
                    )
                    for frame_transform in transforms
                ]
                mapped = device_mapping.frames_to_led_tracks(
                    rendered_frames,
                    [int(move_effects[0]["duration_ms"])] * len(rendered_frames),
                    resolved_targets,
                    "nearest",
                    product_id,
                    work_check=check,
                    progress=progress,
                    frame_limit=frame_limit,
                    source_frame_limit=frame_limit,
                )
            else:
                mapped = device_mapping.compose_media_frames_to_led_tracks(
                    decoded.frames,
                    decoded.durations_ms,
                    list(targets),
                    checked_transform.to_dict(),
                    product_id,
                    work_check=check,
                    progress=progress,
                )
            color_effects = [
                effect
                for effect in checked_effects
                if effect["type"] != "move_zoom"
            ]
            for effect in color_effects:
                for target, track in mapped["tracks"].items():
                    capabilities = device_mapping.target_capabilities()[
                        mapped["model"]
                    ]["targets"]
                    target_capability = next(
                        entry
                        for entry in capabilities
                        if entry["name"] == target
                    )
                    coordinates = [
                        {"x": 0.5, "y": 0.5}
                        for _index in range(track["pixels"])
                    ]
                    width = target_capability["width"]
                    height = target_capability["height"]
                    for source_index, output_index in enumerate(
                        target_capability["map"]
                    ):
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
            check()
            return {
                "catalog_id": catalog_id,
                "epoch": epoch,
                "transform": checked_transform.to_dict(),
                "effects": checked_effects,
                "mapped_result": mapped,
            }
        finally:
            self._finish(catalog_id)


__all__ = [
    "DecodedMedia",
    "MAX_DECODED_PIXELS",
    "MAX_MEDIA_BYTES",
    "MAX_MEDIA_DIMENSION",
    "MAX_MEDIA_DURATION_MS",
    "MAX_MEDIA_FRAMES",
    "MediaRenderCoordinator",
    "MediaRenderSuperseded",
    "SourceTransform",
    "decode_media",
    "interpolate_move_zoom",
    "render_color_effect",
    "render_source_frame",
    "validate_effect_spec",
    "validate_source_transform",
]
