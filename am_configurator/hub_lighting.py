"""Pure OpenKeeb schema-v2 lighting validation and transfer planning.

This module deliberately has no HID dependency.  It owns the bounded hub
vocabulary shared by AM, Vial, and VIA and produces target-shaped transfer
results that transports may later encode behind their existing write gates.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
from typing import Any, Iterable


MAX_SURFACES = 16
MAX_EFFECTS = 1024
MAX_PIXELS = 1024
MAX_ANIMATIONS = 64
MAX_FRAMES = 1024
MAX_IDENTIFIER = 64

SURFACE_ROLES = ("keys", "underglow", "backlight", "panel", "accent")
LIGHTING_GENERATIONS = (
    "am_frames",
    "qmk_backlight",
    "qmk_rgblight",
    "qmk_rgb_matrix",
    "vialrgb",
)
EFFECT_SEMANTICS = ("off", "solid", "breathing")
STREAM_PROTOCOLS = ("vialrgb-1",)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_KEY_ID_RE = re.compile(r"^K_[A-Z0-9_]+$")
_OPAQUE_PIXEL_ID_RE = re.compile(r"^LED_I(?:0|[1-9][0-9]*)$")
_RGB_RE = re.compile(r"^#[0-9A-F]{6}$")


class LightingModelError(ValueError):
    """Lighting data is unsafe, ambiguous, or outside the bounded schema."""


@dataclass(frozen=True)
class LightingTransferPlan:
    """Target-shaped persistent state plus explicit transfer findings."""

    lighting: dict[str, Any] | None
    items: tuple[dict[str, Any], ...]


def _fail(message: str) -> None:
    raise LightingModelError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object.")
    return value


def _list(value: object, label: str, *, maximum: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        _fail(f"{label} must be a list of at most {maximum} items.")
    return value


def _integer(
    value: object,
    label: str,
    *,
    low: int = 0,
    high: int = 0xFFFF,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not low <= value <= high
    ):
        _fail(f"{label} must be an integer in {low}..{high}.")
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        _fail(
            f"{label} must be 1..{MAX_IDENTIFIER} ASCII letters, numbers, "
            "underscores, or hyphens and start with a letter or number."
        )
    return value


def _known(value: object, choices: Iterable[str], label: str) -> str:
    values = tuple(choices)
    if value not in values:
        _fail(f"{label} must be one of: {', '.join(values)}.")
    return str(value)


def _only(value: dict[str, Any], fields: set[str], label: str) -> None:
    unknown = sorted(set(value) - fields)
    if unknown:
        _fail(f"{label} has unsupported fields: {', '.join(unknown)}.")


def _needs(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - set(value))
    if missing:
        _fail(f"{label} is missing required fields: {', '.join(missing)}.")


def _range(value: object, label: str) -> dict[str, int]:
    item = _object(value, label)
    _only(item, {"min", "max"}, label)
    _needs(item, {"min", "max"}, label)
    low = _integer(item["min"], f"{label}.min")
    high = _integer(item["max"], f"{label}.max")
    if low >= high:
        _fail(f"{label}.min must be lower than {label}.max.")
    return {"min": low, "max": high}


def _hsv_descriptor(value: object, label: str) -> dict[str, Any]:
    descriptor = _object(value, label)
    _only(descriptor, {"space", "channels"}, label)
    _needs(descriptor, {"space", "channels"}, label)
    if descriptor["space"] != "hsv":
        _fail(f"{label}.space must be hsv.")
    channels = _list(descriptor["channels"], f"{label}.channels", maximum=3)
    if len(channels) not in (2, 3):
        _fail(f"{label}.channels must contain two or three native ranges.")
    return {
        "space": "hsv",
        "channels": [
            _range(channel, f"{label}.channels[{index}]")
            for index, channel in enumerate(channels)
        ],
    }


def validate_pixel_id(value: object, label: str = "pixel id") -> str:
    if not isinstance(value, str) or not (
        _KEY_ID_RE.fullmatch(value) or _OPAQUE_PIXEL_ID_RE.fullmatch(value)
    ):
        _fail(f"{label} must be a canonical K_* identity or LED_I<n>.")
    if len(value) > MAX_IDENTIFIER:
        _fail(f"{label} is longer than {MAX_IDENTIFIER} characters.")
    return value


def validate_surface_capability(value: object, *, label: str = "lighting surface") -> dict[str, Any]:
    surface = _object(value, label)
    fields = {
        "id",
        "role",
        "generation",
        "effects",
        "brightness",
        "speed",
        "color",
        "per_key",
        "stream",
    }
    _only(surface, fields, label)
    _needs(surface, {"id", "role", "generation"}, label)
    result: dict[str, Any] = {
        "id": _identifier(surface["id"], f"{label}.id"),
        "role": _known(surface["role"], SURFACE_ROLES, f"{label}.role"),
        "generation": _known(
            surface["generation"], LIGHTING_GENERATIONS, f"{label}.generation"
        ),
    }
    if "effects" in surface:
        effects = _list(surface["effects"], f"{label}.effects", maximum=MAX_EFFECTS)
        seen_ids: set[int] = set()
        seen_semantics: set[str] = set()
        validated_effects: list[dict[str, Any]] = []
        for index, value_effect in enumerate(effects):
            effect_label = f"{label}.effects[{index}]"
            effect = _object(value_effect, effect_label)
            _only(effect, {"id", "semantic"}, effect_label)
            _needs(effect, {"id"}, effect_label)
            effect_id = _integer(effect["id"], f"{effect_label}.id")
            if effect_id in seen_ids:
                _fail(f"{label}.effects repeats effect id {effect_id}.")
            seen_ids.add(effect_id)
            entry: dict[str, Any] = {"id": effect_id}
            if "semantic" in effect:
                semantic = _known(
                    effect["semantic"], EFFECT_SEMANTICS, f"{effect_label}.semantic"
                )
                if semantic in seen_semantics:
                    _fail(f"{label}.effects repeats semantic {semantic!r}.")
                seen_semantics.add(semantic)
                entry["semantic"] = semantic
            validated_effects.append(entry)
        result["effects"] = validated_effects
    for control in ("brightness", "speed"):
        if control in surface:
            result[control] = _range(surface[control], f"{label}.{control}")
    if "color" in surface:
        result["color"] = _hsv_descriptor(surface["color"], f"{label}.color")
    if "per_key" in surface:
        per_key = _object(surface["per_key"], f"{label}.per_key")
        _only(per_key, {"pixel_count", "color"}, f"{label}.per_key")
        _needs(per_key, {"pixel_count"}, f"{label}.per_key")
        per_key_result: dict[str, Any] = {
            "pixel_count": _integer(
                per_key["pixel_count"],
                f"{label}.per_key.pixel_count",
                low=1,
                high=MAX_PIXELS,
            )
        }
        if "color" in per_key:
            per_key_result["color"] = _hsv_descriptor(
                per_key["color"], f"{label}.per_key.color"
            )
        result["per_key"] = per_key_result
    if "stream" in surface:
        if result["generation"] != "vialrgb":
            _fail(f"{label}.stream is allowed only on a vialrgb surface.")
        stream = _object(surface["stream"], f"{label}.stream")
        _only(
            stream,
            {"protocol", "pixel_count", "max_chunk_pixels", "volatile"},
            f"{label}.stream",
        )
        _needs(
            stream,
            {"protocol", "pixel_count", "max_chunk_pixels", "volatile"},
            f"{label}.stream",
        )
        if stream["volatile"] is not True:
            _fail(f"{label}.stream.volatile must be true.")
        pixel_count = _integer(
            stream["pixel_count"],
            f"{label}.stream.pixel_count",
            low=1,
            high=MAX_PIXELS,
        )
        chunk = _integer(
            stream["max_chunk_pixels"],
            f"{label}.stream.max_chunk_pixels",
            low=1,
            high=MAX_PIXELS,
        )
        if chunk > pixel_count:
            _fail(f"{label}.stream.max_chunk_pixels cannot exceed pixel_count.")
        result["stream"] = {
            "protocol": _known(
                stream["protocol"], STREAM_PROTOCOLS, f"{label}.stream.protocol"
            ),
            "pixel_count": pixel_count,
            "max_chunk_pixels": chunk,
            "volatile": True,
        }
    return result


def validate_capabilities(value: object) -> dict[str, Any]:
    lighting = _object(value, "capabilities.lighting")
    _only(lighting, {"surfaces"}, "capabilities.lighting")
    _needs(lighting, {"surfaces"}, "capabilities.lighting")
    surfaces = _list(
        lighting["surfaces"], "capabilities.lighting.surfaces", maximum=MAX_SURFACES
    )
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, value_surface in enumerate(surfaces):
        surface = validate_surface_capability(
            value_surface, label=f"capabilities.lighting.surfaces[{index}]"
        )
        if surface["id"] in seen:
            _fail(f"capabilities.lighting.surfaces repeats id {surface['id']!r}.")
        seen.add(surface["id"])
        validated.append(surface)
    return {"surfaces": validated}


def _channel_values(
    value: object,
    descriptor: dict[str, Any],
    label: str,
) -> list[int]:
    channels = descriptor["channels"]
    if not isinstance(value, list) or len(value) != len(channels):
        _fail(f"{label} must contain {len(channels)} native channel values.")
    return [
        _integer(
            entry,
            f"{label}[{index}]",
            low=channel["min"],
            high=channel["max"],
        )
        for index, (entry, channel) in enumerate(zip(value, channels, strict=True))
    ]


def _per_key_values(
    value: object,
    *,
    maximum: int,
    descriptor: dict[str, Any] | None,
    label: str,
) -> dict[str, list[int]]:
    mapping = _object(value, label)
    if len(mapping) > maximum:
        _fail(f"{label} maps more than the declared {maximum} pixels.")
    result: dict[str, list[int]] = {}
    for key, color in mapping.items():
        if not isinstance(key, str) or not _KEY_ID_RE.fullmatch(key) or len(key) > 64:
            _fail(f"{label} key {key!r} must be a canonical K_* identity.")
        if descriptor is None:
            if not isinstance(color, list) or len(color) != 3:
                _fail(f"{label}[{key}] must contain three HSV values.")
            result[key] = [
                _integer(channel, f"{label}[{key}][{index}]", low=0, high=255)
                for index, channel in enumerate(color)
            ]
        else:
            result[key] = _channel_values(color, descriptor, f"{label}[{key}]")
    return result


def validate_surface_state(
    value: object,
    capability: dict[str, Any],
    *,
    label: str = "lighting surface state",
) -> dict[str, Any]:
    surface = _object(value, label)
    _only(
        surface,
        {"id", "effect_id", "brightness", "speed", "color", "per_key"},
        label,
    )
    _needs(surface, {"id"}, label)
    surface_id = _identifier(surface["id"], f"{label}.id")
    if surface_id != capability["id"]:
        _fail(
            f"{label}.id {surface_id!r} does not match capability "
            f"{capability['id']!r}."
        )
    result: dict[str, Any] = {"id": surface_id}
    if "effect_id" in surface:
        supported = {effect["id"] for effect in capability.get("effects", [])}
        effect_id = _integer(surface["effect_id"], f"{label}.effect_id")
        if effect_id not in supported:
            _fail(f"{label}.effect_id {effect_id} is not declared by the surface.")
        result["effect_id"] = effect_id
    for control in ("brightness", "speed"):
        if control not in surface:
            continue
        if control not in capability:
            _fail(f"{label}.{control} is not exposed by the surface.")
        bounds = capability[control]
        result[control] = _integer(
            surface[control],
            f"{label}.{control}",
            low=bounds["min"],
            high=bounds["max"],
        )
    if "color" in surface:
        if "color" not in capability:
            _fail(f"{label}.color is not exposed by the surface.")
        result["color"] = _channel_values(
            surface["color"], capability["color"], f"{label}.color"
        )
    if "per_key" in surface:
        if "per_key" not in capability:
            _fail(f"{label}.per_key is not exposed by the surface.")
        result["per_key"] = _per_key_values(
            surface["per_key"],
            maximum=capability["per_key"]["pixel_count"],
            descriptor=capability["per_key"].get("color"),
            label=f"{label}.per_key",
        )
    return result


def _validate_animation(
    value: object,
    capabilities: dict[str, dict[str, Any]],
    *,
    label: str,
) -> dict[str, Any]:
    animation = _object(value, label)
    fields = {
        "name",
        "surface_id",
        "pixel_ids",
        "frames",
        "placement",
        "frame_ms",
        "brightness",
    }
    _only(animation, fields, label)
    _needs(
        animation,
        {"name", "surface_id", "pixel_ids", "frames", "placement"},
        label,
    )
    name = animation["name"]
    if not isinstance(name, str) or not name or len(name) > 128:
        _fail(f"{label}.name must be a non-empty string of at most 128 characters.")
    surface_id = _identifier(animation["surface_id"], f"{label}.surface_id")
    if surface_id not in capabilities:
        _fail(f"{label}.surface_id {surface_id!r} has no capability surface.")
    pixels = _list(animation["pixel_ids"], f"{label}.pixel_ids", maximum=MAX_PIXELS)
    if not pixels:
        _fail(f"{label}.pixel_ids must contain at least one pixel.")
    pixel_ids = [
        validate_pixel_id(pixel, f"{label}.pixel_ids[{index}]")
        for index, pixel in enumerate(pixels)
    ]
    if len(set(pixel_ids)) != len(pixel_ids):
        _fail(f"{label}.pixel_ids must not repeat a pixel identity.")
    frames = _list(animation["frames"], f"{label}.frames", maximum=MAX_FRAMES)
    if not frames:
        _fail(f"{label}.frames must contain at least one frame.")
    validated_frames: list[list[str]] = []
    for frame_index, frame in enumerate(frames):
        if not isinstance(frame, list) or len(frame) != len(pixel_ids):
            _fail(
                f"{label}.frames[{frame_index}] must contain exactly "
                f"{len(pixel_ids)} pixels."
            )
        colors: list[str] = []
        for pixel_index, color in enumerate(frame):
            if not isinstance(color, str) or not _RGB_RE.fullmatch(color):
                _fail(
                    f"{label}.frames[{frame_index}][{pixel_index}] must be an "
                    "uppercase #RRGGBB color."
                )
            colors.append(color)
        validated_frames.append(colors)
    if animation["placement"] != "geometry_seam":
        _fail(f"{label}.placement must be geometry_seam.")
    result: dict[str, Any] = {
        "name": name,
        "surface_id": surface_id,
        "pixel_ids": pixel_ids,
        "frames": validated_frames,
        "placement": "geometry_seam",
    }
    if "frame_ms" in animation:
        result["frame_ms"] = _integer(
            animation["frame_ms"], f"{label}.frame_ms", low=1, high=65535
        )
    if "brightness" in animation:
        result["brightness"] = _integer(
            animation["brightness"], f"{label}.brightness", low=0, high=100
        )
    return result


def validate_lighting(
    value: object,
    capability_value: object,
) -> dict[str, Any]:
    capabilities = validate_capabilities(capability_value)
    capability_map = {surface["id"]: surface for surface in capabilities["surfaces"]}
    lighting = _object(value, "lighting")
    _only(lighting, {"surfaces", "animations"}, "lighting")
    result: dict[str, Any] = {}
    if "surfaces" in lighting:
        surfaces = _list(lighting["surfaces"], "lighting.surfaces", maximum=MAX_SURFACES)
        seen: set[str] = set()
        states: list[dict[str, Any]] = []
        for index, value_surface in enumerate(surfaces):
            candidate = _object(value_surface, f"lighting.surfaces[{index}]")
            surface_id = _identifier(
                candidate.get("id"), f"lighting.surfaces[{index}].id"
            )
            if surface_id in seen:
                _fail(f"lighting.surfaces repeats id {surface_id!r}.")
            if surface_id not in capability_map:
                _fail(f"lighting.surfaces id {surface_id!r} has no capability surface.")
            seen.add(surface_id)
            states.append(
                validate_surface_state(
                    candidate,
                    capability_map[surface_id],
                    label=f"lighting.surfaces[{index}]",
                )
            )
        result["surfaces"] = states
    if "animations" in lighting:
        animations = _list(
            lighting["animations"], "lighting.animations", maximum=MAX_ANIMATIONS
        )
        result["animations"] = [
            _validate_animation(
                animation,
                capability_map,
                label=f"lighting.animations[{index}]",
            )
            for index, animation in enumerate(animations)
        ]
    return result


def _effect_maps(surface: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    by_id = {effect["id"]: effect for effect in surface.get("effects", [])}
    by_semantic = {
        effect["semantic"]: effect["id"]
        for effect in surface.get("effects", [])
        if "semantic" in effect
    }
    return by_id, by_semantic


def _scaled_value(
    value: int,
    source_range: dict[str, int],
    target_range: dict[str, int],
) -> int:
    source_span = source_range["max"] - source_range["min"]
    target_span = target_range["max"] - target_range["min"]
    numerator = (value - source_range["min"]) * target_span
    # Round halves up deterministically without binary floating point.
    return target_range["min"] + (numerator * 2 + source_span) // (2 * source_span)


def _finding(path: str, verdict: str, reason: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"path": path, "verdict": verdict}
    if reason:
        item["reason"] = reason
    return item


def _matching_target_surface(
    source: dict[str, Any],
    targets: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    exact = [
        target
        for target in targets
        if target["role"] == source["role"]
        and target["generation"] == source["generation"]
    ]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, "more than one target surface has the same role and generation"
    same_role = [target for target in targets if target["role"] == source["role"]]
    if len(same_role) == 1:
        return same_role[0], None
    if len(same_role) > 1:
        return None, "more than one target surface has the same role"
    return None, "the target exposes no surface with the same role"


def plan_transfer(
    source_profile: dict[str, Any],
    target_profile: dict[str, Any],
) -> LightingTransferPlan:
    """Map source lighting onto target capability/state without guessing.

    Both profiles must already be schema-v2 normalized.  The output begins
    with the target's current lighting so an omitted or incompatible source
    field cannot silently erase target state.
    """

    source_caps = validate_capabilities(
        source_profile.get("capabilities", {}).get("lighting", {"surfaces": []})
    )
    target_caps = validate_capabilities(
        target_profile.get("capabilities", {}).get("lighting", {"surfaces": []})
    )
    source_lighting_value = source_profile.get("lighting")
    if source_lighting_value is None:
        return LightingTransferPlan(
            copy.deepcopy(target_profile.get("lighting")),
            (),
        )
    source_lighting = validate_lighting(source_lighting_value, source_caps)
    target_lighting = validate_lighting(
        target_profile.get("lighting", {}), target_caps
    )
    target_cap_list = target_caps["surfaces"]
    source_cap_map = {surface["id"]: surface for surface in source_caps["surfaces"]}
    target_state_map = {
        state["id"]: state for state in target_lighting.get("surfaces", [])
    }
    output_states = copy.deepcopy(target_state_map)
    items: list[dict[str, Any]] = []

    for state_index, source_state in enumerate(source_lighting.get("surfaces", [])):
        source_surface = source_cap_map[source_state["id"]]
        target_surface, reason = _matching_target_surface(source_surface, target_cap_list)
        base_path = f"lighting.surfaces[{source_state['id']}]"
        if target_surface is None:
            items.append(_finding(base_path, "dropped", reason))
            continue
        output = copy.deepcopy(output_states.get(target_surface["id"], {"id": target_surface["id"]}))
        source_effects, _ = _effect_maps(source_surface)
        target_effects, target_semantics = _effect_maps(target_surface)

        if "effect_id" in source_state:
            path = f"{base_path}.effect_id"
            source_effect = source_effects[source_state["effect_id"]]
            if (
                source_surface["generation"] == target_surface["generation"]
                and source_state["effect_id"] in target_effects
            ):
                output["effect_id"] = source_state["effect_id"]
                items.append(_finding(path, "carried"))
            elif (
                source_effect.get("semantic") in ("off", "solid", "breathing")
                and source_effect.get("semantic") in target_semantics
            ):
                output["effect_id"] = target_semantics[source_effect["semantic"]]
                items.append(
                    _finding(
                        path,
                        "adapted",
                        f"mapped {source_effect['semantic']} to target effect id "
                        f"{output['effect_id']}",
                    )
                )
            else:
                items.append(
                    _finding(path, "dropped", "no unambiguous target effect mapping")
                )

        for control in ("brightness", "speed"):
            if control not in source_state:
                continue
            path = f"{base_path}.{control}"
            if control not in source_surface or control not in target_surface:
                items.append(
                    _finding(path, "dropped", f"the target does not expose {control}")
                )
                continue
            mapped = _scaled_value(
                source_state[control], source_surface[control], target_surface[control]
            )
            output[control] = mapped
            if mapped == source_state[control] and source_surface[control] == target_surface[control]:
                items.append(_finding(path, "carried"))
            else:
                items.append(
                    _finding(
                        path,
                        "adapted",
                        f"scaled native {source_surface[control]['min']}.."
                        f"{source_surface[control]['max']} to "
                        f"{target_surface[control]['min']}..{target_surface[control]['max']}",
                    )
                )

        if "color" in source_state:
            path = f"{base_path}.color"
            if "color" not in target_surface:
                items.append(_finding(path, "dropped", "the target exposes no HSV color"))
            elif len(source_surface["color"]["channels"]) != len(
                target_surface["color"]["channels"]
            ):
                items.append(
                    _finding(path, "dropped", "source and target HSV channel counts differ")
                )
            else:
                mapped_channels = [
                    _scaled_value(value, source_bounds, target_bounds)
                    for value, source_bounds, target_bounds in zip(
                        source_state["color"],
                        source_surface["color"]["channels"],
                        target_surface["color"]["channels"],
                        strict=True,
                    )
                ]
                output["color"] = mapped_channels
                if (
                    mapped_channels == source_state["color"]
                    and source_surface["color"] == target_surface["color"]
                ):
                    items.append(_finding(path, "carried"))
                else:
                    items.append(_finding(path, "adapted", "scaled native HSV ranges"))

        if "per_key" in source_state:
            if "per_key" not in target_surface:
                for key in source_state["per_key"]:
                    items.append(
                        _finding(
                            f"{base_path}.per_key[{key}]",
                            "dropped",
                            "the target exposes no per-key lighting",
                        )
                    )
            else:
                target_keys = {
                    key["key"]
                    for layer in target_profile.get("keymap", {}).get("layers", [])
                    for key in layer.get("keys", [])
                }
                mapped: dict[str, list[int]] = {}
                source_descriptor = source_surface["per_key"].get("color")
                target_descriptor = target_surface["per_key"].get("color")
                for key, color in source_state["per_key"].items():
                    path = f"{base_path}.per_key[{key}]"
                    if key not in target_keys:
                        items.append(
                            _finding(path, "dropped", "the target has no matching key identity")
                        )
                    elif key in mapped:
                        items.append(
                            _finding(path, "dropped", "the target pixel would be assigned twice")
                        )
                    elif (source_descriptor is None) != (target_descriptor is None):
                        items.append(
                            _finding(
                                path,
                                "dropped",
                                "source and target per-key color channels differ",
                            )
                        )
                    elif source_descriptor is not None and len(
                        source_descriptor["channels"]
                    ) != len(target_descriptor["channels"]):
                        items.append(
                            _finding(
                                path,
                                "dropped",
                                "source and target per-key color channels differ",
                            )
                        )
                    else:
                        if source_descriptor is None:
                            mapped_color = copy.deepcopy(color)
                            adapted = False
                        else:
                            mapped_color = [
                                _scaled_value(value, source_bounds, target_bounds)
                                for value, source_bounds, target_bounds in zip(
                                    color,
                                    source_descriptor["channels"],
                                    target_descriptor["channels"],
                                    strict=True,
                                )
                            ]
                            adapted = (
                                mapped_color != color
                                or source_descriptor != target_descriptor
                            )
                        mapped[key] = mapped_color
                        items.append(
                            _finding(
                                path,
                                "adapted" if adapted else "carried",
                                "scaled native per-key HSV ranges" if adapted else None,
                            )
                        )
                output["per_key"] = mapped

        output_states[target_surface["id"]] = validate_surface_state(
            output, target_surface, label=f"target lighting surface {target_surface['id']}"
        )

    output_animations = copy.deepcopy(target_lighting.get("animations", []))
    target_cap_map = {surface["id"]: surface for surface in target_cap_list}
    for animation_index, animation in enumerate(source_lighting.get("animations", [])):
        source_surface = source_cap_map[animation["surface_id"]]
        target_surface, reason = _matching_target_surface(source_surface, target_cap_list)
        path = f"lighting.animations[{animation_index}]"
        if target_surface is None:
            items.append(_finding(path, "dropped", reason))
            continue
        target_stream = target_surface.get("stream")
        source_stream = source_surface.get("stream")
        if not source_stream or not target_stream:
            items.append(
                _finding(path, "dropped", "both surfaces must prove compatible streaming")
            )
            continue
        if source_stream["protocol"] != target_stream["protocol"]:
            items.append(_finding(path, "dropped", "stream protocols differ"))
            continue
        if len(animation["pixel_ids"]) != target_stream["pixel_count"]:
            items.append(_finding(path, "dropped", "animation pixel identities do not match target count"))
            continue
        candidate = copy.deepcopy(animation)
        candidate["surface_id"] = target_surface["id"]
        checked = _validate_animation(
            candidate,
            target_cap_map,
            label=f"transferred {path}",
        )
        output_animations.append(checked)
        verdict = "carried" if source_surface["id"] == target_surface["id"] else "adapted"
        items.append(
            _finding(
                path,
                verdict,
                None if verdict == "carried" else "retargeted compatible stream surface",
            )
        )

    result: dict[str, Any] = {}
    if output_states or "surfaces" in target_lighting or "surfaces" in source_lighting:
        result["surfaces"] = [output_states[key] for key in sorted(output_states)]
    if output_animations or "animations" in target_lighting or "animations" in source_lighting:
        result["animations"] = output_animations
    return LightingTransferPlan(validate_lighting(result, target_caps), tuple(items))


def standard_hsv_descriptor(*, channels: int = 2) -> dict[str, Any]:
    """Return a fresh bounded 0..255 HSV descriptor for surveyed protocols."""

    if channels not in (2, 3):
        _fail("HSV descriptors use two or three channels.")
    return {
        "space": "hsv",
        "channels": [{"min": 0, "max": 255} for _ in range(channels)],
    }


def opaque_pixel_ids(count: int) -> list[str]:
    count = _integer(count, "pixel count", low=1, high=MAX_PIXELS)
    return [f"LED_I{index}" for index in range(count)]


_V1_GENERATIONS = {
    "rgblight": ("qmk_rgblight", "underglow"),
    "led_matrix": ("qmk_backlight", "backlight"),
    "rgb_matrix": ("qmk_rgb_matrix", "keys"),
    "am_frames": ("am_frames", "panel"),
}


def _v1_surface(
    surfaces: dict[str, dict[str, Any]],
    generation: str,
) -> dict[str, Any]:
    if generation not in _V1_GENERATIONS:
        _fail(f"The schema-version-1 lighting generation {generation!r} is unknown.")
    new_generation, role = _V1_GENERATIONS[generation]
    surface = surfaces.get(new_generation)
    if surface is None:
        surface = {
            "id": new_generation,
            "role": role,
            "generation": new_generation,
        }
        surfaces[new_generation] = surface
    return surface


def _v1_static_surface(
    surfaces: dict[str, dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    if mode == "per_key":
        compatible = [
            surface
            for surface in surfaces.values()
            if surface["generation"] in ("qmk_rgb_matrix", "vialrgb")
        ]
        fallback = "rgb_matrix"
    else:
        compatible = [
            surface
            for surface in surfaces.values()
            if surface["generation"]
            in ("qmk_rgblight", "qmk_rgb_matrix", "vialrgb")
        ]
        fallback = "rgblight"
    if len(compatible) == 1:
        return compatible[0]
    if len(compatible) > 1:
        _fail(
            "The schema-version-1 static lighting state could belong to more "
            "than one surface; migration would guess."
        )
    frame_surfaces = [
        surface
        for surface in surfaces.values()
        if surface["generation"] == "am_frames"
    ]
    if len(frame_surfaces) == 1:
        return frame_surfaces[0]
    return _v1_surface(surfaces, fallback)


def _merge_effects(surface: dict[str, Any], ids: list[int]) -> None:
    existing = {effect["id"] for effect in surface.get("effects", [])}
    if len(ids) != len(set(ids)):
        _fail("A schema-version-1 lighting capability repeats an effect id.")
    surface["effects"] = [
        *surface.get("effects", []),
        *({"id": effect_id} for effect_id in ids if effect_id not in existing),
    ]


def _set_state_field(
    state: dict[str, Any],
    field: str,
    value: object,
    *,
    explanation: str,
) -> None:
    if field in state and state[field] != value:
        _fail(
            f"The schema-version-1 {explanation} conflicts with another value "
            "on the same migrated surface."
        )
    state[field] = copy.deepcopy(value)


def migrate_v1_profile(value: object) -> dict[str, Any]:
    """Convert an already validated exact schema-v1 profile to schema v2.

    The old validator remains the authority for the accepted v1 shape.  This
    function handles only deterministic representational changes and refuses
    combinations for which v1 did not identify an owning surface.
    """

    profile = copy.deepcopy(_object(value, "The schema-version-1 hub profile"))
    if profile.get("schema_version") != 1:
        _fail("Only a validated schema-version-1 profile can be migrated.")

    capabilities = profile.setdefault("capabilities", {})
    old_capability = capabilities.pop("lighting", None)
    old_lighting = profile.pop("lighting", None)
    surfaces: dict[str, dict[str, Any]] = {}

    if old_capability is not None:
        for group in old_capability.get("hardware_effects", []):
            surface = _v1_surface(surfaces, group["generation"])
            _merge_effects(surface, group["ids"])
        custom = old_capability.get("custom_animation")
        if custom:
            _v1_surface(surfaces, "am_frames")

    hardware = (old_lighting or {}).get("hardware_effect")
    if hardware is not None:
        surface = _v1_surface(surfaces, hardware["generation"])
        _merge_effects(surface, [hardware["id"]])
        if "speed" in hardware:
            surface["speed"] = {"min": 0, "max": 255}
        if "color" in hardware:
            surface["color"] = standard_hsv_descriptor(channels=2)

    animations = (old_lighting or {}).get("animations", [])
    if animations:
        _v1_surface(surfaces, "am_frames")

    static = (old_lighting or {}).get("static")
    static_surface: dict[str, Any] | None = None
    if static is not None:
        static_surface = _v1_static_surface(surfaces, static["mode"])
        if static["mode"] == "global":
            static_surface["color"] = standard_hsv_descriptor(channels=2)
            static_surface["brightness"] = {"min": 0, "max": 255}
        else:
            static_surface["per_key"] = {
                "pixel_count": max(1, len(static["per_key"])),
                "color": standard_hsv_descriptor(channels=3),
            }

    if old_capability is not None:
        static_mode = old_capability.get("static_color", "none")
        if static_mode != "none" and static is None:
            capability_mode = "per_key" if static_mode == "per_key" else "global"
            capability_surface = _v1_static_surface(surfaces, capability_mode)
            if capability_mode == "per_key":
                declared_keys = capabilities.get("keymap", {}).get(
                    "keys_per_layer", 1
                )
                capability_surface["per_key"] = {
                    "pixel_count": max(1, min(declared_keys, MAX_PIXELS)),
                    "color": standard_hsv_descriptor(channels=3),
                }
            else:
                capability_surface["color"] = standard_hsv_descriptor(channels=2)
                capability_surface["brightness"] = {"min": 0, "max": 255}
        if old_capability.get("per_key_direct") and static_surface is not None:
            static_surface.setdefault(
                "per_key",
                {
                    "pixel_count": max(1, len(static.get("per_key", {}))),
                    "color": standard_hsv_descriptor(channels=3),
                },
            )

    states: dict[str, dict[str, Any]] = {}
    if hardware is not None:
        surface_id = _V1_GENERATIONS[hardware["generation"]][0]
        state = states.setdefault(surface_id, {"id": surface_id})
        _set_state_field(
            state,
            "effect_id",
            hardware["id"],
            explanation="hardware effect id",
        )
        if "speed" in hardware:
            _set_state_field(
                state,
                "speed",
                hardware["speed"],
                explanation="hardware effect speed",
            )
        if "color" in hardware:
            _set_state_field(
                state,
                "color",
                hardware["color"],
                explanation="hardware effect color",
            )
    if static is not None and static_surface is not None:
        state = states.setdefault(static_surface["id"], {"id": static_surface["id"]})
        if static["mode"] == "global":
            color = static["color"]
            _set_state_field(
                state,
                "color",
                color[:2],
                explanation="static HSV color",
            )
            _set_state_field(
                state,
                "brightness",
                color[2],
                explanation="static brightness",
            )
        else:
            _set_state_field(
                state,
                "per_key",
                static["per_key"],
                explanation="per-key static colors",
            )

    new_animations: list[dict[str, Any]] = []
    for animation in animations:
        pixel_count = len(animation["frames"][0])
        new_animations.append(
            {
                **copy.deepcopy(animation),
                "surface_id": "am_frames",
                "pixel_ids": opaque_pixel_ids(pixel_count),
            }
        )

    if surfaces or old_capability is not None:
        capabilities["lighting"] = {
            "surfaces": [
                validate_surface_capability(surface)
                for surface in sorted(surfaces.values(), key=lambda item: item["id"])
            ]
        }
    if old_lighting is not None:
        migrated_lighting: dict[str, Any] = {}
        if states:
            migrated_lighting["surfaces"] = [states[key] for key in sorted(states)]
        if "animations" in old_lighting:
            migrated_lighting["animations"] = new_animations
        profile["lighting"] = migrated_lighting

    provenance = profile.get("provenance")
    if provenance:
        rewritten: dict[str, str] = {}
        for pointer, origin in provenance.items():
            if pointer == "/lighting/static" and static_surface is not None:
                state_index = sorted(states).index(static_surface["id"])
                if static["mode"] == "global":
                    rewritten[f"/lighting/surfaces/{state_index}/color"] = origin
                    rewritten[f"/lighting/surfaces/{state_index}/brightness"] = origin
                else:
                    rewritten[f"/lighting/surfaces/{state_index}/per_key"] = origin
            elif pointer == "/lighting/hardware_effect" and hardware is not None:
                state_id = _V1_GENERATIONS[hardware["generation"]][0]
                state_index = sorted(states).index(state_id)
                for field in ("effect_id", "speed", "color"):
                    if field in states[state_id]:
                        new_pointer = f"/lighting/surfaces/{state_index}/{field}"
                        if new_pointer in rewritten and rewritten[new_pointer] != origin:
                            _fail(
                                "Schema-version-1 lighting provenance assigns "
                                "conflicting origins to one migrated field."
                            )
                        rewritten[new_pointer] = origin
            elif pointer == "/lighting/animations":
                rewritten[pointer] = origin
            elif pointer.startswith("/lighting/"):
                _fail(
                    f"Schema-version-1 provenance pointer {pointer!r} cannot be "
                    "mapped without guessing."
                )
            else:
                rewritten[pointer] = origin
        if "/lighting" not in rewritten:
            for state_index, _state_id in enumerate(sorted(states)):
                rewritten.setdefault(
                    f"/lighting/surfaces/{state_index}/id", "default"
                )
        profile["provenance"] = rewritten

    profile["schema_version"] = 2
    return profile
