"""Isolated local-model proof for deterministic low-resolution LED loops.

This module is intentionally not wired into the desktop application.  A local
language model chooses bounded procedural parameters; every output frame is
then rendered locally from periodic functions and mapped through the existing
device conversion core.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image


DEFAULT_MODEL = "gemma4:12b-mlx"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_WIDTH = 18
DEFAULT_HEIGHT = 7
DEFAULT_FRAME_COUNT = 200
DEFAULT_DURATION_MS = 34
MAX_RESPONSE_BYTES = 1_000_000

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_ROOT_KEYS = {"name", "background", "palette", "layers"}
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
    """The local model or caller supplied an unusable animation recipe."""


def recipe_schema() -> dict[str, Any]:
    """Return the exact JSON schema supplied to Ollama structured output."""

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
            "name": {"type": "string", "minLength": 1, "maxLength": 80},
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
    """Validate and normalize a model recipe without accepting extra fields."""

    if not isinstance(value, dict):
        raise RecipeError("The animation recipe must be an object.")
    _exact_keys(value, _ROOT_KEYS, "The animation recipe")
    name = value["name"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise RecipeError("Recipe name must contain 1 to 80 characters.")
    background = value["background"]
    if not isinstance(background, str) or not _HEX_COLOR.fullmatch(background):
        raise RecipeError("Background must be a six-digit hex color.")
    palette = value["palette"]
    if not isinstance(palette, list) or not 1 <= len(palette) <= 5:
        raise RecipeError("Palette must contain 1 to 5 colors.")
    if any(not isinstance(color, str) or not _HEX_COLOR.fullmatch(color) for color in palette):
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
        if kind not in _KINDS:
            raise RecipeError(f"{label} has an unsupported primitive.")
        color_index = _number(layer["color_index"], f"{label} color index", 0, 4, integer=True)
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
                    layer["direction_degrees"],
                    f"{label} direction",
                    0,
                    360,
                ),
                "center_x": _number(layer["center_x"], f"{label} center x", 0, 1),
                "center_y": _number(layer["center_y"], f"{label} center y", 0, 1),
                "scale": _number(layer["scale"], f"{label} scale", 0.05, 1.5),
                "width": _number(layer["width"], f"{label} width", 0.02, 1),
                "trail": _number(layer["trail"], f"{label} trail", 0, 1),
                "count": _number(layer["count"], f"{label} count", 1, 12, integer=True),
                "intensity": _number(
                    layer["intensity"],
                    f"{label} intensity",
                    0.05,
                    1,
                ),
                "seed": _number(layer["seed"], f"{label} seed", 0, 9999, integer=True),
            }
        )
    return {
        "name": name.strip(),
        "background": background.upper(),
        "palette": [color.upper() for color in palette],
        "layers": normalized_layers,
    }


def _system_prompt(width: int, height: int, frame_count: int) -> str:
    return f"""You design abstract keyboard LED loops for an exact {width}x{height} raster and {frame_count} frames.
Return only the required structured recipe. The renderer guarantees looping; choose clear high-contrast parameters that survive very low resolution.
Use comet for meteors, shooting stars, rain, or chases; wave for aurora and flowing bands; pulse for rings and breathing; sparkle for twinkling points; orbit for rotating dots; sweep for scanning bands; noise for fire or organic shimmer.
Prefer black or very dark backgrounds, 1-3 layers, saturated colors, and counts that remain readable. Avoid cameras, scenery, text, realistic objects, and fine detail. Speed is a nonzero integer cycle count. Every color index must exist in the palette.
Exact numeric bounds for every layer: color indexes 0-4 and inside the chosen palette; speed -3,-2,-1,1,2,3; phase 0-1; direction_degrees 0-360; center_x and center_y 0-1; scale 0.05-1.5; width 0.02-1; trail 0-1; count 1-12; intensity 0.05-1; seed 0-9999. Include every field for every layer."""


class OllamaRecipeClient:
    """Small loopback-only Ollama structured-output client."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = 180,
    ) -> None:
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Ollama endpoint must be an unauthenticated loopback HTTP URL.")
        if timeout_seconds <= 0 or timeout_seconds > 600:
            raise ValueError("Ollama timeout must be between 0 and 600 seconds.")
        self.endpoint = endpoint.rstrip("/")
        self.opener = opener
        self.timeout_seconds = float(timeout_seconds)

    def _request(self, body: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.endpoint}/api/chat",
            data=json.dumps(body, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise RecipeError(f"Ollama returned HTTP {exc.code}.") from None
        except (OSError, TimeoutError, URLError) as exc:
            raise RecipeError("Could not reach the local Ollama service.") from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise RecipeError("Ollama response exceeded the local size limit.")
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RecipeError("Ollama returned malformed JSON.") from None
        if not isinstance(parsed, dict):
            raise RecipeError("Ollama returned an invalid response object.")
        return parsed

    def generate(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MODEL,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        frame_count: int = DEFAULT_FRAME_COUNT,
    ) -> dict[str, Any]:
        clean_prompt = str(prompt).strip()
        if not 1 <= len(clean_prompt) <= 4000:
            raise RecipeError("Prompt must contain 1 to 4000 characters.")
        if not _MODEL_NAME.fullmatch(model):
            raise RecipeError("Ollama model name is invalid.")
        _validate_render_dimensions(width, height, frame_count)
        messages = [
            {"role": "system", "content": _system_prompt(width, height, frame_count)},
            {"role": "user", "content": clean_prompt},
        ]
        last_error: RecipeError | None = None
        for attempt in range(3):
            response = self._request(
                {
                    "model": model,
                    "stream": False,
                    "format": recipe_schema(),
                    "options": {"temperature": 0.35, "seed": 7319 + attempt},
                    "messages": messages,
                }
            )
            content = response.get("message", {}).get("content")
            try:
                if not isinstance(content, str) or len(content.encode()) > MAX_RESPONSE_BYTES:
                    raise RecipeError("Ollama did not return a bounded recipe string.")
                recipe = json.loads(content)
                return validate_recipe(recipe)
            except (json.JSONDecodeError, RecipeError) as exc:
                last_error = exc if isinstance(exc, RecipeError) else RecipeError("Ollama recipe was not JSON.")
                if attempt < 2:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"The recipe failed validation: {last_error}. Return a corrected complete recipe.",
                        }
                    )
        raise last_error or RecipeError("Ollama did not return a usable recipe.")


def _validate_render_dimensions(width: int, height: int, frame_count: int) -> None:
    for value, label, maximum in (
        (width, "Width", 200),
        (height, "Height", 200),
        (frame_count, "Frame count", 256),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise RecipeError(f"{label} must be an integer from 1 to {maximum}.")
    if width * height * frame_count > 10_000_000:
        raise RecipeError("Requested animation exceeds the local pixel budget.")


def _rgb(value: str) -> tuple[float, float, float]:
    return tuple(float(int(value[index : index + 2], 16)) for index in (1, 3, 5))  # type: ignore[return-value]


def _torus_delta(left: float, right: float) -> float:
    delta = abs(left - right) % 1.0
    return min(delta, 1.0 - delta)


def _gaussian(distance: float, sigma: float) -> float:
    return math.exp(-(distance * distance) / (2 * sigma * sigma))


def _direction_winding(degrees: float) -> tuple[int, int]:
    directions = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
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
    # Models reason poorly about a normalized width on a raster this small.
    # Keep point primitives inside a safe subpixel-to-one-pixel envelope; the
    # model may vary softness, but cannot turn a comet into a full-board wash.
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
        # Preserve a crisp LED-scale head after subpixel averaging without
        # broadening the point envelope into a board-wide glow.
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
            candidate = _gaussian(math.hypot(dx, dy), max(0.18, point_sigma * 0.65)) * twinkle
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
) -> list[Image.Image]:
    """Render exact raster frames from a validated periodic recipe."""

    normalized = validate_recipe(recipe)
    _validate_render_dimensions(width, height, frame_count)
    background = _rgb(normalized["background"])
    palette = [_rgb(color) for color in normalized["palette"]]
    frames: list[Image.Image] = []
    offsets = ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75))
    for frame_index in range(frame_count):
        phase = frame_index / frame_count
        pixels: list[tuple[int, int, int]] = []
        for pixel_y in range(height):
            for pixel_x in range(width):
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
                            primary[channel] * (1.0 - blend) + secondary[channel] * blend
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
    return frames


def _gif_durations(frame_count: int, duration_ms: int) -> list[int]:
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or not 10 <= duration_ms <= 1000:
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


def _save_gif(frames: Sequence[Image.Image], path: Path, durations: Sequence[int]) -> None:
    converted = [frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for frame in frames]
    converted[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=converted[1:],
        duration=list(durations),
        loop=0,
        disposal=2,
        optimize=False,
    )


def write_proof_artifacts(
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
    """Write inspectable GIFs and exact mapped LED JSON from one frame source."""

    normalized = validate_recipe(recipe)
    frames = render_recipe(normalized, width=width, height=height, frame_count=frame_count)
    durations = _gif_durations(frame_count, duration_ms)
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
    _save_gif(frames, paths["raster_gif"], durations)
    preview_frames = [
        frame.resize((width * 40, height * 40), Image.Resampling.NEAREST)
        for frame in frames
    ]
    _save_gif(preview_frames, paths["preview_gif"], durations)

    from .server import frames_to_led_tracks

    mapped = frames_to_led_tracks(frames, [duration_ms] * frame_count, list(targets), "nearest", product_id)
    paths["led_json"].write_text(json.dumps(mapped, separators=(",", ":")) + "\n", encoding="utf-8")
    summary = {
        "name": normalized["name"],
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "duration_ms": duration_ms,
        "loop_duration_ms": frame_count * duration_ms,
        "product_id": product_id,
        "targets": list(targets),
        "files": {key: path.name for key, path in paths.items() if key != "summary"},
    }
    paths["summary"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a local procedural LED animation proof.")
    parser.add_argument("prompt", help="Natural-language lighting effect description")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Installed Ollama model name")
    parser.add_argument("--output", type=Path, required=True, help="Directory for GIF and LED artifacts")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Loopback Ollama base URL")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAME_COUNT)
    args = parser.parse_args(argv)
    client = OllamaRecipeClient(endpoint=args.endpoint)
    recipe = client.generate(
        args.prompt,
        model=args.model,
        width=args.width,
        height=args.height,
        frame_count=args.frames,
    )
    paths = write_proof_artifacts(
        recipe,
        args.output,
        width=args.width,
        height=args.height,
        frame_count=args.frames,
    )
    print(json.dumps({key: str(path) for key, path in paths.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
