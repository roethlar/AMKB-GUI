"""Pure Vial/QMK and VialRGB lighting capability/command codecs.

No function in this module opens HID.  Transport code supplies device-proven
values and may execute the returned closed command records only after the
normal endpoint-bound confirmation preflight.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from . import hub_lighting


CMD_LIGHTING_SET_VALUE = 0x07
CMD_LIGHTING_GET_VALUE = 0x08
CMD_LIGHTING_SAVE = 0x09

QMK_BACKLIGHT_BRIGHTNESS = 0x09
QMK_BACKLIGHT_EFFECT = 0x0A
QMK_RGBLIGHT_BRIGHTNESS = 0x80
QMK_RGBLIGHT_EFFECT = 0x81
QMK_RGBLIGHT_EFFECT_SPEED = 0x82
QMK_RGBLIGHT_COLOR = 0x83

VIALRGB_GET_INFO = 0x40
VIALRGB_GET_MODE = 0x41
VIALRGB_GET_SUPPORTED = 0x42
VIALRGB_GET_NUMBER_LEDS = 0x43
VIALRGB_GET_LED_INFO = 0x44
VIALRGB_SET_MODE = 0x41
VIALRGB_DIRECT_FASTSET = 0x42
VIALRGB_DIRECT_EFFECT = 1
VIALRGB_FEATURE_FLAG = 0x01
VIALRGB_PROTOCOL_VERSION = 1
VIALRGB_MAX_CHUNK_PIXELS = 9
VIALRGB_REPORTS_PER_SECOND = 30


class VialLightingError(ValueError):
    """Definition or device lighting evidence is unsafe or unsupported."""


@dataclass(frozen=True)
class VialRGBInfo:
    protocol_version: int
    maximum_brightness: int
    effect_ids: tuple[int, ...]
    pixel_count: int | None = None


@dataclass(frozen=True)
class VialLightingCommand:
    surface_id: str
    value_id: int
    payload: bytes


@dataclass(frozen=True)
class VialLightingWritePlan:
    lighting: dict[str, Any] | None
    commands: tuple[VialLightingCommand, ...]
    save: bool
    items: tuple[dict[str, Any], ...]


def _fail(message: str) -> None:
    raise VialLightingError(message)


def _byte(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
        _fail(f"{label} must be an integer in 0..255.")
    return value


def _effect(
    effect_id: int,
    *,
    semantic: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"id": effect_id}
    if semantic:
        item["semantic"] = semantic
    return item


def _legacy_surfaces(
    lighting: str,
    current: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    surfaces: list[dict[str, Any]] = []
    if lighting in ("qmk_backlight", "qmk_backlight_rgblight"):
        effects = [_effect(0, semantic="off"), _effect(1, semantic="breathing")]
        current_effect = current.get("backlight", {}).get("effect_id")
        if isinstance(current_effect, int) and not isinstance(current_effect, bool):
            if current_effect not in {entry["id"] for entry in effects}:
                effects.append(_effect(current_effect))
        surfaces.append(
            {
                "id": "backlight",
                "role": "backlight",
                "generation": "qmk_backlight",
                "effects": effects,
                "brightness": {"min": 0, "max": 255},
            }
        )
    if lighting in ("qmk_rgblight", "qmk_backlight_rgblight"):
        effects = [_effect(0, semantic="off"), _effect(1, semantic="solid")]
        current_effect = current.get("underglow", {}).get("effect_id")
        if isinstance(current_effect, int) and not isinstance(current_effect, bool):
            if current_effect not in {entry["id"] for entry in effects}:
                effects.append(_effect(current_effect))
        surfaces.append(
            {
                "id": "underglow",
                "role": "underglow",
                "generation": "qmk_rgblight",
                "effects": effects,
                "brightness": {"min": 0, "max": 255},
                "speed": {"min": 0, "max": 255},
                "color": hub_lighting.standard_hsv_descriptor(channels=2),
            }
        )
    return surfaces


def capabilities_from_definition(
    definition: object,
    *,
    vial_protocol: int,
    feature_flags: int = 0,
    vialrgb_info: VialRGBInfo | None = None,
    current: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Extract only lighting a pinned embedded definition/device proves."""

    if not isinstance(definition, dict):
        _fail("The Vial definition must be an object.")
    if not isinstance(vial_protocol, int) or isinstance(vial_protocol, bool):
        _fail("The Vial protocol version must be an integer.")
    if not isinstance(feature_flags, int) or isinstance(feature_flags, bool):
        _fail("The Vial feature flags must be an integer.")
    lighting = definition.get("lighting")
    current_values = current or {}
    if lighting in ("qmk_backlight", "qmk_rgblight", "qmk_backlight_rgblight"):
        return hub_lighting.validate_capabilities(
            {"surfaces": _legacy_surfaces(lighting, current_values)}
        )
    if lighting != "vialrgb":
        return {"surfaces": []}
    if vial_protocol < 4 or not feature_flags & VIALRGB_FEATURE_FLAG:
        return {"surfaces": []}
    if vialrgb_info is None:
        return {"surfaces": []}
    if vialrgb_info.protocol_version != VIALRGB_PROTOCOL_VERSION:
        _fail(
            f"VialRGB protocol {vialrgb_info.protocol_version} is unsupported; "
            f"OpenKeeb supports exactly {VIALRGB_PROTOCOL_VERSION}."
        )
    maximum = _byte(vialrgb_info.maximum_brightness, "VialRGB maximum brightness")
    if maximum == 0:
        _fail("VialRGB maximum brightness must be at least 1.")
    effect_ids = tuple(vialrgb_info.effect_ids)
    if not effect_ids or len(effect_ids) > hub_lighting.MAX_EFFECTS:
        _fail(
            f"VialRGB supported effects must contain 1..{hub_lighting.MAX_EFFECTS} ids."
        )
    if len(set(effect_ids)) != len(effect_ids):
        _fail("VialRGB supported effects repeat an id.")
    effects = []
    for effect_id in effect_ids:
        if (
            not isinstance(effect_id, int)
            or isinstance(effect_id, bool)
            or not 0 <= effect_id <= 0xFFFF
        ):
            _fail("VialRGB effect ids must be integers in 0..65535.")
        effects.append(_effect(effect_id, semantic="off" if effect_id == 0 else None))
    surface: dict[str, Any] = {
        "id": "vialrgb",
        "role": "keys",
        "generation": "vialrgb",
        "effects": effects,
        "brightness": {"min": 0, "max": maximum},
        "speed": {"min": 0, "max": 255},
        "color": hub_lighting.standard_hsv_descriptor(channels=2),
    }
    if VIALRGB_DIRECT_EFFECT in effect_ids:
        pixel_count = vialrgb_info.pixel_count
        if (
            not isinstance(pixel_count, int)
            or isinstance(pixel_count, bool)
            or not 1 <= pixel_count <= hub_lighting.MAX_PIXELS
        ):
            _fail(
                "VialRGB direct mode requires a device-proven pixel count in "
                f"1..{hub_lighting.MAX_PIXELS}."
            )
        surface["per_key"] = {
            "pixel_count": pixel_count,
            "color": hub_lighting.standard_hsv_descriptor(channels=3),
        }
        surface["stream"] = {
            "protocol": "vialrgb-1",
            "pixel_count": pixel_count,
            "max_chunk_pixels": min(VIALRGB_MAX_CHUNK_PIXELS, pixel_count),
            "volatile": True,
        }
    return hub_lighting.validate_capabilities({"surfaces": [surface]})


def state_from_values(
    capabilities: object,
    values: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Normalize device-returned native values against proved capabilities."""

    validated = hub_lighting.validate_capabilities(capabilities)
    states: list[dict[str, Any]] = []
    for surface in validated["surfaces"]:
        raw = values.get(surface["id"])
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            _fail(f"Vial lighting values for {surface['id']} must be an object.")
        state = {"id": surface["id"], **copy.deepcopy(dict(raw))}
        try:
            states.append(hub_lighting.validate_surface_state(state, surface))
        except hub_lighting.LightingModelError as exc:
            _fail(str(exc))
    return {"surfaces": states}


def _state_map(lighting: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if lighting is None:
        return {}
    return {state["id"]: state for state in lighting.get("surfaces", [])}


def _legacy_commands(
    surface: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[VialLightingCommand]:
    if surface["generation"] == "qmk_backlight":
        ids = {"brightness": QMK_BACKLIGHT_BRIGHTNESS, "effect_id": QMK_BACKLIGHT_EFFECT}
    elif surface["generation"] == "qmk_rgblight":
        ids = {
            "brightness": QMK_RGBLIGHT_BRIGHTNESS,
            "effect_id": QMK_RGBLIGHT_EFFECT,
            "speed": QMK_RGBLIGHT_EFFECT_SPEED,
            "color": QMK_RGBLIGHT_COLOR,
        }
    else:
        return []
    commands: list[VialLightingCommand] = []
    for field in ("effect_id", "brightness", "speed", "color"):
        if field not in after or after.get(field) == before.get(field):
            continue
        value = after[field]
        payload = bytes(value) if field == "color" else bytes([value])
        commands.append(VialLightingCommand(surface["id"], ids[field], payload))
    if "per_key" in after and after.get("per_key") != before.get("per_key"):
        _fail("Persistent Vial per-key writes are not a surveyed legacy command.")
    return commands


def plan_write(
    source_profile: dict[str, Any],
    target_profile: dict[str, Any],
) -> VialLightingWritePlan:
    """Plan closed persistent lighting commands without opening HID."""

    try:
        transfer = hub_lighting.plan_transfer(source_profile, target_profile)
    except hub_lighting.LightingModelError as exc:
        _fail(str(exc))
    target_caps = hub_lighting.validate_capabilities(
        target_profile.get("capabilities", {}).get("lighting", {"surfaces": []})
    )
    before_map = _state_map(target_profile.get("lighting"))
    after_map = _state_map(transfer.lighting)
    commands: list[VialLightingCommand] = []
    for surface in target_caps["surfaces"]:
        before = before_map.get(surface["id"], {"id": surface["id"]})
        after = after_map.get(surface["id"], before)
        if surface["generation"] != "vialrgb":
            commands.extend(_legacy_commands(surface, before, after))
            continue
        if after == before:
            continue
        if after.get("effect_id") == VIALRGB_DIRECT_EFFECT:
            _fail("VialRGB direct mode is volatile and cannot be saved as a persistent effect.")
        if "per_key" in after and after.get("per_key") != before.get("per_key"):
            _fail("VialRGB per-key data belongs to the volatile streaming route.")
        required = ("effect_id", "speed", "color", "brightness")
        merged = {**before, **after}
        missing = [field for field in required if field not in merged]
        if missing:
            _fail(
                "A persistent VialRGB mode update requires a complete current "
                f"mode snapshot; missing {', '.join(missing)}."
            )
        color = merged["color"]
        payload = (
            int(merged["effect_id"]).to_bytes(2, "little")
            + bytes([merged["speed"], color[0], color[1], merged["brightness"]])
        )
        commands.append(VialLightingCommand(surface["id"], VIALRGB_SET_MODE, payload))
    return VialLightingWritePlan(
        lighting=copy.deepcopy(transfer.lighting),
        commands=tuple(commands),
        save=bool(commands),
        items=transfer.items,
    )
