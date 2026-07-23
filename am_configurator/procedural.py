"""Backend-neutral procedural animation contract and deterministic renderer.

Model providers may choose only a bounded recipe.  This module validates that
recipe, renders periodic exact-raster frames locally, evaluates deterministic
LED quality metrics, writes GIF artifacts, and maps the same source frames
through the application's existing device conversion core.
"""

from __future__ import annotations

import json
import math
import random
import re
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Sequence

from PIL import GifImagePlugin, Image

from . import device_mapping


SCHEMA_VERSION = 1
DEFAULT_WIDTH = 18
DEFAULT_HEIGHT = 7
DEFAULT_FRAME_COUNT = 200
DEFAULT_DURATION_MS = 34
MAX_WIDTH = 200
MAX_HEIGHT = 200
MAX_FRAME_COUNT = 256
MAX_RENDERED_PIXELS = 10_000_000
DENSITIES = ("balanced", "dense", "sparse")

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ROOT_KEYS = {
    "schema_version",
    "name",
    "density",
    "background",
    "palette",
    "layers",
}
_LAYER_KEYS = {
    "kind",
    "color_index",
    "secondary_color_index",
    "speed",
    "phase",
    "direction_degrees",
    "center_x",
    "center_y",
    "scale",
    "width",
    "trail",
    "count",
    "intensity",
    "seed",
}
_KINDS = {"comet", "wave", "pulse", "sparkle", "orbit", "sweep", "noise"}


class RecipeError(ValueError):
    """A provider or caller supplied an unusable animation recipe."""


class QualityError(RecipeError):
    """Rendered frames failed one or more deterministic quality requirements."""

    def __init__(
        self,
        failures: Sequence[str],
        metrics: QualityMetrics | None = None,
    ) -> None:
        self.failures = tuple(dict.fromkeys(failures))
        self.metrics = metrics
        super().__init__(f"Animation failed quality checks: {', '.join(self.failures)}.")


class WorkCancelled(RuntimeError):
    """The user cancelled bounded local procedural work."""


class WorkDeadlineExceeded(RuntimeError):
    """The shared procedural operation deadline expired."""


@dataclass(frozen=True)
class WorkBudget:
    """Shared monotonic deadline and cancellation predicate for local work."""

    deadline: float
    cancelled: Callable[[], bool]
    monotonic: Callable[[], float] = time.monotonic

    def check(self) -> None:
        if self.cancelled():
            raise WorkCancelled("Procedural generation was cancelled.")
        if self.monotonic() >= self.deadline:
            raise WorkDeadlineExceeded("Procedural generation deadline expired.")


ProgressCallback = Callable[[int, int], None]


def _check_work(work: WorkBudget | None) -> None:
    if work is not None:
        work.check()


def _report_progress(
    progress: ProgressCallback | None,
    completed: int,
    total: int,
) -> None:
    if progress is not None:
        progress(completed, total)


@dataclass(frozen=True)
class QualityMetrics:
    """Deterministic measurements used to accept a rendered recipe."""

    width: int
    height: int
    frame_count: int
    density: str
    minimum_lit_ratio: float
    maximum_lit_ratio: float
    peak_brightness: int
    maximum_adjacent_difference: float
    seam_difference: float

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "minimum_lit_ratio",
            "maximum_lit_ratio",
            "maximum_adjacent_difference",
            "seam_difference",
        ):
            value[key] = round(value[key], 8)
        return value


def recipe_schema() -> dict[str, Any]:
    """Return the exact JSON schema shared by every recipe provider."""

    layer_properties: dict[str, Any] = {
        "kind": {"type": "string", "enum": sorted(_KINDS)},
        "color_index": {"type": "integer", "minimum": 0, "maximum": 4},
        "secondary_color_index": {
            "type": "integer",
            "minimum": 0,
            "maximum": 4,
        },
        "speed": {"type": "integer", "enum": [-3, -2, -1, 1, 2, 3]},
        "phase": {"type": "number", "minimum": 0, "maximum": 1},
        "direction_degrees": {
            "type": "number",
            "minimum": 0,
            "maximum": 360,
        },
        "center_x": {"type": "number", "minimum": 0, "maximum": 1},
        "center_y": {"type": "number", "minimum": 0, "maximum": 1},
        "scale": {"type": "number", "minimum": 0.05, "maximum": 1.5},
        "width": {"type": "number", "minimum": 0.02, "maximum": 1},
        "trail": {"type": "number", "minimum": 0, "maximum": 1},
        "count": {"type": "integer", "minimum": 1, "maximum": 12},
        "intensity": {"type": "number", "minimum": 0.05, "maximum": 1},
        "seed": {"type": "integer", "minimum": 0, "maximum": 9999},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
            "name": {"type": "string", "minLength": 1, "maxLength": 80},
            "density": {"type": "string", "enum": sorted(DENSITIES)},
            "background": {"type": "string", "pattern": _HEX_COLOR.pattern},
            "palette": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {"type": "string", "pattern": _HEX_COLOR.pattern},
            },
            "layers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": layer_properties,
                    "required": sorted(_LAYER_KEYS),
                },
            },
        },
        "required": sorted(_ROOT_KEYS),
    }


def recipe_system_prompt(
    width: int,
    height: int,
    frame_count: int,
    *,
    density_default: str = "balanced",
) -> str:
    """Return common provider guidance for the strict procedural contract."""

    _validate_render_dimensions(width, height, frame_count)
    if density_default not in DENSITIES:
        raise RecipeError("Density default must be sparse, balanced, or dense.")
    return f"""You design abstract keyboard LED loops for an exact {width}x{height} raster and {frame_count} frames.
Return only the required structured recipe with schema_version {SCHEMA_VERSION}. The renderer guarantees looping; choose clear high-contrast parameters that survive very low resolution.
Classify output density as sparse, balanced, or dense. Default to {density_default}. Use sparse only when the prompt explicitly asks for isolated points or darkness. Use dense for whole-board fields, washes, aurora, fire, ocean, or similarly continuous effects.
Use comet for meteors, shooting stars, rain, or chases; wave for aurora and flowing bands; pulse for rings and breathing; sparkle for twinkling points; orbit for rotating dots; sweep for scanning bands; noise for fire or organic shimmer.
Prefer black or very dark backgrounds, 1-3 layers, saturated colors, and counts that remain readable. Avoid cameras, scenery, text, realistic objects, and fine detail. Speed is a nonzero integer cycle count. Every color index must exist in the palette.
Exact numeric bounds for every layer: color indexes 0-4 and inside the chosen palette; speed -3,-2,-1,1,2,3; phase 0-1; direction_degrees 0-360; center_x and center_y 0-1; scale 0.05-1.5; width 0.02-1; trail 0-1; count 1-12; intensity 0.05-1; seed 0-9999. Include every field for every layer."""


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise RecipeError(f"{label} has {'; '.join(details)}.")


def _number(
    value: Any,
    label: str,
    minimum: float,
    maximum: float,
    *,
    integer: bool = False,
) -> int | float:
    valid = isinstance(value, int) if integer else isinstance(value, (int, float))
    if isinstance(value, bool) or not valid or not math.isfinite(float(value)):
        raise RecipeError(f"{label} must be a finite {'integer' if integer else 'number'}.")
    normalized: int | float = int(value) if integer else float(value)
    if normalized < minimum or normalized > maximum:
        raise RecipeError(f"{label} must be between {minimum} and {maximum}.")
    return normalized


def validate_recipe(value: Any) -> dict[str, Any]:
    """Validate and normalize a recipe without accepting unknown fields."""

    if not isinstance(value, dict):
        raise RecipeError("The animation recipe must be an object.")
    _exact_keys(value, _ROOT_KEYS, "The animation recipe")
    if (
        isinstance(value["schema_version"], bool)
        or not isinstance(value["schema_version"], int)
        or value["schema_version"] != SCHEMA_VERSION
    ):
        raise RecipeError("Recipe schema version is unsupported.")
    name = value["name"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise RecipeError("Recipe name must contain 1 to 80 characters.")
    density = value["density"]
    if density not in DENSITIES:
        raise RecipeError("Recipe density must be sparse, balanced, or dense.")
    background = value["background"]
    if not isinstance(background, str) or not _HEX_COLOR.fullmatch(background):
        raise RecipeError("Background must be a six-digit hex color.")
    palette = value["palette"]
    if not isinstance(palette, list) or not 1 <= len(palette) <= 5:
        raise RecipeError("Palette must contain 1 to 5 colors.")
    if any(
        not isinstance(color, str) or not _HEX_COLOR.fullmatch(color)
        for color in palette
    ):
        raise RecipeError("Every palette entry must be a six-digit hex color.")
    layers = value["layers"]
    if not isinstance(layers, list) or not 1 <= len(layers) <= 6:
        raise RecipeError("Recipe must contain 1 to 6 layers.")

    normalized_layers: list[dict[str, Any]] = []
    for index, layer in enumerate(layers):
        label = f"Layer {index + 1}"
        if not isinstance(layer, dict):
            raise RecipeError(f"{label} must be an object.")
        _exact_keys(layer, _LAYER_KEYS, label)
        kind = layer["kind"]
        if not isinstance(kind, str) or kind not in _KINDS:
            raise RecipeError(f"{label} has an unsupported primitive.")
        color_index = _number(
            layer["color_index"], f"{label} color index", 0, 4, integer=True
        )
        secondary_index = _number(
            layer["secondary_color_index"],
            f"{label} secondary color index",
            0,
            4,
            integer=True,
        )
        if color_index >= len(palette) or secondary_index >= len(palette):
            raise RecipeError(f"{label} references a color outside the palette.")
        speed = _number(layer["speed"], f"{label} speed", -3, 3, integer=True)
        if speed == 0:
            raise RecipeError(f"{label} speed cannot be zero.")
        normalized_layers.append(
            {
                "kind": kind,
                "color_index": color_index,
                "secondary_color_index": secondary_index,
                "speed": speed,
                "phase": _number(layer["phase"], f"{label} phase", 0, 1),
                "direction_degrees": _number(
                    layer["direction_degrees"], f"{label} direction", 0, 360
                ),
                "center_x": _number(layer["center_x"], f"{label} center x", 0, 1),
                "center_y": _number(layer["center_y"], f"{label} center y", 0, 1),
                "scale": _number(layer["scale"], f"{label} scale", 0.05, 1.5),
                "width": _number(layer["width"], f"{label} width", 0.02, 1),
                "trail": _number(layer["trail"], f"{label} trail", 0, 1),
                "count": _number(layer["count"], f"{label} count", 1, 12, integer=True),
                "intensity": _number(
                    layer["intensity"], f"{label} intensity", 0.05, 1
                ),
                "seed": _number(layer["seed"], f"{label} seed", 0, 9999, integer=True),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "name": name.strip(),
        "density": density,
        "background": background.upper(),
        "palette": [color.upper() for color in palette],
        "layers": normalized_layers,
    }


def _validate_render_dimensions(width: int, height: int, frame_count: int) -> None:
    for value, label, maximum in (
        (width, "Width", MAX_WIDTH),
        (height, "Height", MAX_HEIGHT),
        (frame_count, "Frame count", MAX_FRAME_COUNT),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise RecipeError(f"{label} must be an integer from 1 to {maximum}.")
    if width * height * frame_count > MAX_RENDERED_PIXELS:
        raise RecipeError("Requested animation exceeds the local pixel budget.")


def _rgb(value: str) -> tuple[float, float, float]:
    return tuple(
        float(int(value[index : index + 2], 16)) for index in (1, 3, 5)
    )  # type: ignore[return-value]


def _torus_delta(left: float, right: float) -> float:
    delta = abs(left - right) % 1.0
    return min(delta, 1.0 - delta)


def _gaussian(distance: float, sigma: float) -> float:
    return math.exp(-(distance * distance) / (2 * sigma * sigma))


def _direction_winding(degrees: float) -> tuple[int, int]:
    directions = (
        (1, 0),
        (1, 1),
        (0, 1),
        (-1, 1),
        (-1, 0),
        (-1, -1),
        (0, -1),
        (1, -1),
    )
    return directions[int((degrees % 360 + 22.5) // 45) % len(directions)]


def _sample_layer(
    layer: dict[str, Any],
    x: float,
    y: float,
    phase: float,
    width: int,
    height: int,
) -> tuple[float, float]:
    kind = layer["kind"]
    speed = layer["speed"]
    local_phase = phase * speed + layer["phase"]
    min_dimension = min(width, height)
    point_sigma = 0.18 + layer["width"] * 0.65

    if kind == "comet":
        winding_x, winding_y = _direction_winding(layer["direction_degrees"])
        samples = 14
        best_amount = 0.0
        best_mix = 0.0
        for comet_index in range(layer["count"]):
            head = local_phase + comet_index / layer["count"]
            for sample_index in range(samples):
                fraction = sample_index / (samples - 1)
                lag = math.copysign(layer["trail"] * 0.48 * fraction, speed)
                cx = (layer["center_x"] + winding_x * (head - lag)) % 1.0
                cy = (layer["center_y"] + winding_y * (head - lag)) % 1.0
                dx = _torus_delta(x, cx) * width
                dy = _torus_delta(y, cy) * height
                falloff = _gaussian(math.hypot(dx, dy), point_sigma)
                tail = math.exp(-3.4 * fraction)
                amount = falloff * tail
                if amount > best_amount:
                    best_amount = amount
                    best_mix = math.exp(-7.0 * fraction)
        return min(1.0, best_amount * 1.15), best_mix

    radians = math.radians(layer["direction_degrees"])
    direction_x, direction_y = math.cos(radians), math.sin(radians)
    spatial = x * direction_x + y * direction_y
    if kind == "wave":
        wave = 0.5 + 0.5 * math.sin(
            2 * math.pi * (spatial / max(0.05, layer["scale"]) - local_phase)
        )
        amount = wave ** (1.0 + 5.0 * (1.0 - layer["width"]))
        return amount, 1.0 - wave

    if kind == "pulse":
        dx = (x - layer["center_x"]) * width
        dy = (y - layer["center_y"]) * height
        distance = math.hypot(dx, dy)
        oscillation = 0.5 - 0.5 * math.cos(2 * math.pi * local_phase)
        radius = layer["scale"] * min_dimension * (0.12 + 0.62 * oscillation)
        band_sigma = 0.18 + layer["width"] * 1.35
        amount = _gaussian(abs(distance - radius), band_sigma)
        return amount, oscillation

    if kind == "sparkle":
        generator = random.Random(layer["seed"])
        amount = 0.0
        mix = 0.0
        for _ in range(layer["count"]):
            sx, sy, offset = generator.random(), generator.random(), generator.random()
            dx = _torus_delta(x, sx) * width
            dy = _torus_delta(y, sy) * height
            twinkle = max(0.0, math.sin(2 * math.pi * (local_phase + offset)))
            twinkle **= 1.0 + 5.0 * (1.0 - layer["width"])
            candidate = (
                _gaussian(math.hypot(dx, dy), max(0.18, point_sigma * 0.65))
                * twinkle
            )
            if candidate > amount:
                amount, mix = candidate, twinkle
        return amount, mix

    if kind == "orbit":
        amount = 0.0
        mix = 0.0
        radius_pixels = layer["scale"] * min_dimension * 0.42
        for dot_index in range(layer["count"]):
            angle = 2 * math.pi * (local_phase + dot_index / layer["count"])
            cx = (layer["center_x"] + math.cos(angle) * radius_pixels / width) % 1.0
            cy = (layer["center_y"] + math.sin(angle) * radius_pixels / height) % 1.0
            dx = _torus_delta(x, cx) * width
            dy = _torus_delta(y, cy) * height
            candidate = _gaussian(math.hypot(dx, dy), point_sigma)
            if candidate > amount:
                amount = candidate
                mix = dot_index / max(1, layer["count"] - 1)
        return amount, mix

    if kind == "sweep":
        wave = 0.5 + 0.5 * math.cos(2 * math.pi * (spatial - local_phase))
        amount = wave ** (1.0 + 10.0 * (1.0 - layer["width"]))
        return amount, 1.0 - wave

    generator = random.Random(layer["seed"])
    value = 0.0
    for harmonic in range(1, 4):
        offset = generator.random()
        value += math.sin(
            2
            * math.pi
            * (local_phase * harmonic + x * (harmonic + 1) + y * harmonic + offset)
        ) / harmonic
    normalized = max(0.0, min(1.0, 0.5 + value / 3.2))
    amount = normalized ** (1.0 + 3.0 * (1.0 - layer["width"]))
    return amount, normalized


def _screen(
    base: tuple[float, float, float],
    color: tuple[float, float, float],
    amount: float,
) -> tuple[float, float, float]:
    strength = max(0.0, min(1.0, amount))
    return tuple(
        255.0 - (255.0 - channel) * (1.0 - (source / 255.0) * strength)
        for channel, source in zip(base, color)
    )  # type: ignore[return-value]


def render_recipe(
    recipe: dict[str, Any],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    frame_count: int = DEFAULT_FRAME_COUNT,
    work: WorkBudget | None = None,
    progress: ProgressCallback | None = None,
) -> list[Image.Image]:
    """Render exact raster frames from a validated periodic recipe."""

    normalized = validate_recipe(recipe)
    _validate_render_dimensions(width, height, frame_count)
    background = _rgb(normalized["background"])
    palette = [_rgb(color) for color in normalized["palette"]]
    frames: list[Image.Image] = []
    offsets = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))
    for frame_index in range(frame_count):
        _check_work(work)
        phase = frame_index / frame_count
        pixels: list[tuple[int, int, int]] = []
        for pixel_y in range(height):
            for pixel_x in range(width):
                _check_work(work)
                samples: list[tuple[float, float, float]] = []
                for offset_x, offset_y in offsets:
                    x = (pixel_x + offset_x) / width
                    y = (pixel_y + offset_y) / height
                    color = background
                    for layer in normalized["layers"]:
                        amount, mix = _sample_layer(layer, x, y, phase, width, height)
                        primary = palette[layer["color_index"]]
                        secondary = palette[layer["secondary_color_index"]]
                        blend = max(0.0, min(1.0, mix))
                        source = tuple(
                            primary[channel] * (1.0 - blend)
                            + secondary[channel] * blend
                            for channel in range(3)
                        )
                        color = _screen(color, source, amount * layer["intensity"])
                    samples.append(color)
                pixels.append(
                    tuple(
                        round(sum(sample[channel] for sample in samples) / len(samples))
                        for channel in range(3)
                    )
                )
        image = Image.new("RGB", (width, height))
        image.putdata(pixels)
        frames.append(image)
        _report_progress(progress, frame_index + 1, frame_count)
    return frames


def _frame_difference(left: Image.Image, right: Image.Image) -> float:
    left_bytes = left.tobytes()
    right_bytes = right.tobytes()
    return sum(abs(a - b) for a, b in zip(left_bytes, right_bytes)) / len(left_bytes)


def assess_quality(
    recipe: dict[str, Any],
    frames: Sequence[Image.Image],
    *,
    work: WorkBudget | None = None,
    progress: ProgressCallback | None = None,
) -> QualityMetrics:
    """Measure an exact frame sequence without applying acceptance thresholds."""

    normalized = validate_recipe(recipe)
    materialized = list(frames)
    if not materialized:
        raise RecipeError("Quality assessment requires at least one frame.")
    width, height = materialized[0].size
    if any(
        frame.mode != "RGB" or frame.size != (width, height)
        for frame in materialized
    ):
        raise RecipeError("Quality assessment requires uniform RGB frames.")
    lit_ratios: list[float] = []
    peak = 0
    total_work = len(materialized) * 2
    for index, frame in enumerate(materialized):
        _check_work(work)
        # Pillow 12 renamed this API; retain the fallback for the declared
        # Pillow 10+ range without emitting the newer deprecation warning.
        getter = getattr(frame, "get_flattened_data", frame.getdata)
        pixels = list(getter())
        lit_ratios.append(sum(max(pixel) > 32 for pixel in pixels) / len(pixels))
        peak = max(peak, max(max(pixel) for pixel in pixels))
        _report_progress(progress, index + 1, total_work)
    ordinary = []
    for index in range(1, len(materialized)):
        _check_work(work)
        ordinary.append(
            _frame_difference(materialized[index - 1], materialized[index])
        )
        _report_progress(progress, len(materialized) + index, total_work)
    maximum_adjacent = max(ordinary, default=0.0)
    _check_work(work)
    seam = _frame_difference(materialized[-1], materialized[0])
    _report_progress(progress, total_work, total_work)
    return QualityMetrics(
        width=width,
        height=height,
        frame_count=len(materialized),
        density=normalized["density"],
        minimum_lit_ratio=min(lit_ratios),
        maximum_lit_ratio=max(lit_ratios),
        peak_brightness=peak,
        maximum_adjacent_difference=maximum_adjacent,
        seam_difference=seam,
    )


def validate_quality(
    recipe: dict[str, Any],
    frames: Sequence[Image.Image],
    *,
    width: int | None = None,
    height: int | None = None,
    frame_count: int | None = None,
    work: WorkBudget | None = None,
    progress: ProgressCallback | None = None,
) -> QualityMetrics:
    """Require exact geometry, motion, brightness, loop, and density quality."""

    normalized = validate_recipe(recipe)
    materialized = list(frames)
    failures: list[str] = []
    if not materialized or any(not isinstance(frame, Image.Image) for frame in materialized):
        raise QualityError(("dimensions",))
    actual_width, actual_height = materialized[0].size
    expected_width = actual_width if width is None else width
    expected_height = actual_height if height is None else height
    expected_count = len(materialized) if frame_count is None else frame_count
    if (
        len(materialized) != expected_count
        or any(
            frame.mode != "RGB" or frame.size != (expected_width, expected_height)
            for frame in materialized
        )
    ):
        failures.append("dimensions")
    try:
        metrics = assess_quality(
            normalized,
            materialized,
            work=work,
            progress=progress,
        )
    except RecipeError:
        raise QualityError(("dimensions",)) from None
    if metrics.maximum_adjacent_difference <= 0:
        failures.append("motion")
    if metrics.peak_brightness <= 180:
        failures.append("brightness")
    if metrics.seam_difference > metrics.maximum_adjacent_difference * 1.25 + 0.01:
        failures.append("seam")
    if normalized["density"] == "sparse":
        if metrics.maximum_lit_ratio > 0.60:
            failures.append("density")
    elif normalized["density"] == "balanced":
        if metrics.minimum_lit_ratio < 0.35 or metrics.maximum_lit_ratio > 0.95:
            failures.append("density")
    elif metrics.minimum_lit_ratio < 0.70:
        failures.append("density")
    if failures:
        raise QualityError(failures, metrics)
    return metrics


def gif_durations(frame_count: int, duration_ms: int) -> list[int]:
    """Convert firmware milliseconds to GIF centiseconds without drift."""

    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count < 1:
        raise RecipeError("GIF frame count must be a positive integer.")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or not 10 <= duration_ms <= 1000
    ):
        raise RecipeError("Frame duration must be an integer from 10 to 1000 ms.")
    base_ticks, remainder = divmod(duration_ms, 10)
    accumulator = 0
    result = []
    for _ in range(frame_count):
        ticks = base_ticks
        accumulator += remainder
        if accumulator >= 10:
            ticks += 1
            accumulator -= 10
        result.append(max(1, ticks) * 10)
    return result


def _exact_gif_frame(frame: Image.Image) -> Image.Image:
    """Build an indexed frame without changing any source RGB value."""

    rgb = frame.convert("RGB")
    colors = rgb.getcolors(maxcolors=256)
    if colors is None:
        raise RecipeError("GIF frames cannot contain more than 256 colors.")
    palette_colors = sorted(color for _count, color in colors)
    palette_indices = {color: index for index, color in enumerate(palette_colors)}
    palette = [channel for color in palette_colors for channel in color]
    palette.extend([0] * (768 - len(palette)))

    indexed = Image.new("P", rgb.size)
    indexed.putpalette(palette)
    getter = getattr(rgb, "get_flattened_data", rgb.getdata)
    indexed.putdata([palette_indices[pixel] for pixel in getter()])
    return indexed


def write_gif(
    frames: Sequence[Image.Image],
    path: Path | BinaryIO,
    durations: Sequence[int],
    *,
    work: WorkBudget | None = None,
    progress: ProgressCallback | None = None,
) -> None:
    """Write a looping GIF from an already validated exact frame sequence."""

    materialized = list(frames)
    frame_durations = list(durations)
    if not materialized or len(materialized) != len(frame_durations):
        raise RecipeError("GIF frames and durations must be non-empty and equal in length.")
    total_work = len(materialized) * 2
    converted = []
    for index, frame in enumerate(materialized):
        _check_work(work)
        converted.append(_exact_gif_frame(frame))
        _report_progress(progress, index + 1, total_work)

    destination = path.open("wb") if isinstance(path, Path) else nullcontext(path)
    with destination as output:
        # Image.save(save_all=True) performs its entire second encoding pass
        # without yielding. Encode one complete frame at a time so the shared
        # work budget remains observable between bounded units.
        header, _palette = GifImagePlugin.getheader(
            converted[0],
            info={"loop": 0},
        )
        for block in header:
            output.write(block)
        for index, (frame, duration) in enumerate(
            zip(converted, frame_durations, strict=True)
        ):
            _check_work(work)
            for block in GifImagePlugin.getdata(
                frame,
                duration=duration,
                disposal=2,
                include_color_table=index > 0,
            ):
                output.write(block)
            _report_progress(progress, len(materialized) + index + 1, total_work)
        output.write(b";")


def write_preview_gif(
    frames: Sequence[Image.Image],
    path: Path | BinaryIO,
    durations: Sequence[int],
    *,
    scale: int = 40,
    work: WorkBudget | None = None,
    progress: ProgressCallback | None = None,
) -> None:
    """Upscale exact frames with nearest-neighbor and write their preview GIF."""

    if isinstance(scale, bool) or not isinstance(scale, int) or scale < 1:
        raise RecipeError("Preview scale must be a positive integer.")
    materialized = list(frames)
    total_work = len(materialized) * 3
    preview_frames = []
    for index, frame in enumerate(materialized):
        _check_work(work)
        preview_frames.append(
            frame.resize(
                (frame.width * scale, frame.height * scale),
                Image.Resampling.NEAREST,
            )
        )
        _report_progress(progress, index + 1, total_work)
    write_gif(
        preview_frames,
        path,
        durations,
        work=work,
        progress=lambda completed, _total: _report_progress(
            progress, len(materialized) + completed, total_work
        ),
    )


def map_frames_to_led_tracks(
    frames: Sequence[Image.Image],
    *,
    duration_ms: int,
    product_id: str,
    targets: Sequence[str],
    work: WorkBudget | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Map exact source frames through the application's canonical LED mapper."""

    materialized = list(frames)
    gif_durations(len(materialized), duration_ms)
    _check_work(work)
    return device_mapping.frames_to_led_tracks(
        materialized,
        [duration_ms] * len(materialized),
        list(targets),
        "nearest",
        product_id,
        work_check=None if work is None else work.check,
        progress=progress,
    )


def write_animation_artifacts(
    recipe: dict[str, Any],
    output_directory: Path,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    frame_count: int = DEFAULT_FRAME_COUNT,
    duration_ms: int = DEFAULT_DURATION_MS,
    product_id: str = "80",
    targets: Sequence[str] = ("keyframes", "spotlight_frames"),
) -> dict[str, Path]:
    """Write quality-checked GIF and mapped LED artifacts from one frame source."""

    normalized = validate_recipe(recipe)
    frames = render_recipe(normalized, width=width, height=height, frame_count=frame_count)
    quality = validate_quality(
        normalized,
        frames,
        width=width,
        height=height,
        frame_count=frame_count,
    )
    durations = gif_durations(frame_count, duration_ms)
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "recipe": output / "recipe.json",
        "raster_gif": output / "raster.gif",
        "preview_gif": output / "preview.gif",
        "led_json": output / "led.json",
        "summary": output / "summary.json",
    }
    paths["recipe"].write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    write_gif(frames, paths["raster_gif"], durations)
    write_preview_gif(frames, paths["preview_gif"], durations)

    mapped = map_frames_to_led_tracks(
        frames,
        duration_ms=duration_ms,
        product_id=product_id,
        targets=targets,
    )
    paths["led_json"].write_text(
        json.dumps(mapped, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    summary = {
        "name": normalized["name"],
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "duration_ms": duration_ms,
        "loop_duration_ms": frame_count * duration_ms,
        "product_id": product_id,
        "targets": list(targets),
        "quality": quality.to_dict(),
        "files": {key: path.name for key, path in paths.items() if key != "summary"},
    }
    paths["summary"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return paths
