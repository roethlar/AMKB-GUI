"""Strict imported-media validation and transform-aware local rendering."""

from __future__ import annotations

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
            if latest is not None and epoch < latest:
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

            mapped = device_mapping.compose_media_frames_to_led_tracks(
                decoded.frames,
                decoded.durations_ms,
                list(targets),
                checked_transform.to_dict(),
                product_id,
                work_check=check,
                progress=progress,
            )
            check()
            return {
                "catalog_id": catalog_id,
                "epoch": epoch,
                "transform": checked_transform.to_dict(),
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
    "render_source_frame",
    "validate_source_transform",
]
