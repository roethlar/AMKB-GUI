"""Pure capability-honest VIA lighting definition and write codecs."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

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

_COMMON_MENUS = {
    "qmk_backlight",
    "qmk_rgblight",
    "qmk_rgb_matrix",
    "qmk_backlight_rgblight",
}
_CONTROL_CONTRACTS = {
    "id_qmk_backlight_brightness": ("backlight", 1, 1, "range", "brightness"),
    "id_qmk_backlight_effect": ("backlight", 1, 2, "dropdown", "effect_id"),
    "id_qmk_rgblight_brightness": ("underglow", 2, 1, "range", "brightness"),
    "id_qmk_rgblight_effect": ("underglow", 2, 2, "dropdown", "effect_id"),
    "id_qmk_rgblight_effect_speed": ("underglow", 2, 3, "range", "speed"),
    "id_qmk_rgblight_color": ("underglow", 2, 4, "color", "color"),
    "id_qmk_rgb_matrix_brightness": ("rgb_matrix", 3, 1, "range", "brightness"),
    "id_qmk_rgb_matrix_effect": ("rgb_matrix", 3, 2, "dropdown", "effect_id"),
    "id_qmk_rgb_matrix_effect_speed": ("rgb_matrix", 3, 3, "range", "speed"),
    "id_qmk_rgb_matrix_color": ("rgb_matrix", 3, 4, "color", "color"),
}
_SURFACE_BASES = {
    "backlight": {
        "id": "backlight",
        "role": "backlight",
        "generation": "qmk_backlight",
    },
    "underglow": {
        "id": "underglow",
        "role": "underglow",
        "generation": "qmk_rgblight",
    },
    "rgb_matrix": {
        "id": "rgb_matrix",
        "role": "keys",
        "generation": "qmk_rgb_matrix",
    },
}


class ViaLightingError(ValueError):
    """A VIA definition or lighting transfer cannot be executed safely."""


@dataclass(frozen=True)
class ViaLightingCommand:
    surface_id: str
    channel: int | None
    command: int
    payload: bytes


@dataclass(frozen=True)
class ViaLightingWritePlan:
    lighting: dict[str, Any] | None
    commands: tuple[ViaLightingCommand, ...]
    save_channels: tuple[int | None, ...]
    items: tuple[dict[str, Any], ...]


def _fail(message: str) -> None:
    raise ViaLightingError(message)


def validate_led_mapping(value: object) -> dict[str, int]:
    """Validate ephemeral canonical-key to VIA LED-index evidence."""

    if not isinstance(value, Mapping):
        _fail("The VIA LED mapping must be an object.")
    if len(value) > hub_lighting.MAX_PIXELS:
        _fail(f"The VIA LED mapping exceeds {hub_lighting.MAX_PIXELS} pixels.")
    result: dict[str, int] = {}
    seen_indexes: set[int] = set()
    for key, index in value.items():
        try:
            checked_key = hub_lighting.validate_pixel_id(key, "VIA LED mapping key")
        except hub_lighting.LightingModelError as exc:
            _fail(str(exc))
        if not checked_key.startswith("K_"):
            _fail(f"VIA LED mapping key {key!r} is not a canonical K_* identity.")
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index <= 255
        ):
            _fail(f"VIA LED index for {key} must be an integer in 0..255.")
        if index in seen_indexes:
            _fail(f"VIA LED mapping repeats index {index}.")
        seen_indexes.add(index)
        result[key] = index
    return result


def _surface(surfaces: dict[str, dict[str, Any]], surface_id: str) -> dict[str, Any]:
    if surface_id not in surfaces:
        surfaces[surface_id] = copy.deepcopy(_SURFACE_BASES[surface_id])
    return surfaces[surface_id]


def _semantic(label: object) -> str | None:
    if not isinstance(label, str):
        return None
    normalized = " ".join(label.strip().lower().split())
    if normalized in ("off", "all off"):
        return "off"
    if normalized in ("solid", "solid color"):
        return "solid"
    if normalized == "breathing":
        return "breathing"
    return None


def _effect_options(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > hub_lighting.MAX_EFFECTS:
        _fail(f"{label} must be a bounded effect option list.")
    effects: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_semantics: set[str] = set()
    for index, option in enumerate(value):
        if isinstance(option, str):
            effect_label = option
            effect_id = index
        elif (
            isinstance(option, list)
            and len(option) == 2
            and isinstance(option[0], str)
            and isinstance(option[1], int)
            and not isinstance(option[1], bool)
        ):
            effect_label = option[0]
            effect_id = option[1]
        else:
            _fail(f"{label}[{index}] must be a label or [label, integer id].")
        if not 0 <= effect_id <= 0xFFFF or effect_id in seen_ids:
            _fail(f"{label} has an invalid or duplicate effect id {effect_id!r}.")
        seen_ids.add(effect_id)
        effect: dict[str, Any] = {"id": effect_id}
        semantic = _semantic(effect_label)
        if semantic and semantic not in seen_semantics:
            effect["semantic"] = semantic
            seen_semantics.add(semantic)
        effects.append(effect)
    return effects


def _known_common_menu(
    name: str,
    surfaces: dict[str, dict[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
) -> None:
    if name in ("qmk_backlight", "qmk_backlight_rgblight"):
        surface = _surface(surfaces, "backlight")
        surface["brightness"] = {"min": 0, "max": 255}
        surface["effects"] = [
            {"id": 0, "semantic": "off"},
            {"id": 1, "semantic": "breathing"},
        ]
    if name in ("qmk_rgblight", "qmk_backlight_rgblight"):
        surface = _surface(surfaces, "underglow")
        surface.update(
            {
                "effects": [
                    {"id": 0, "semantic": "off"},
                    {"id": 1, "semantic": "solid"},
                ],
                "brightness": {"min": 0, "max": 255},
                "speed": {"min": 0, "max": 255},
                "color": hub_lighting.standard_hsv_descriptor(channels=2),
            }
        )
    if name == "qmk_rgb_matrix":
        surface = _surface(surfaces, "rgb_matrix")
        surface.update(
            {
                "effects": [
                    {"id": 0, "semantic": "off"},
                    {"id": 1, "semantic": "solid"},
                ],
                "brightness": {"min": 0, "max": 255},
                "speed": {"min": 0, "max": 255},
                "color": hub_lighting.standard_hsv_descriptor(channels=2),
            }
        )
    for surface_id, surface in surfaces.items():
        current_effect = current.get(surface_id, {}).get("effect_id")
        if (
            isinstance(current_effect, int)
            and not isinstance(current_effect, bool)
            and "effects" in surface
            and current_effect not in {entry["id"] for entry in surface["effects"]}
        ):
            surface["effects"].append({"id": current_effect})


def _walk_controls(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk_controls(item)
    elif isinstance(value, dict):
        content = value.get("content")
        if (
            isinstance(content, list)
            and len(content) == 3
            and isinstance(content[0], str)
        ):
            yield value
        else:
            for item in value.values():
                yield from _walk_controls(item)


def _inline_controls(
    menus: list[Any],
    surfaces: dict[str, dict[str, Any]],
) -> None:
    seen_controls: set[str] = set()
    for control in _walk_controls(menus):
        content = control["content"]
        control_id = content[0]
        if control_id not in _CONTROL_CONTRACTS:
            if control_id.startswith("id_qmk_"):
                _fail(f"VIA lighting control {control_id!r} is not on the allowlist.")
            continue
        if control_id in seen_controls:
            _fail(f"VIA lighting control {control_id!r} appears more than once.")
        seen_controls.add(control_id)
        surface_id, channel, command, control_type, field = _CONTROL_CONTRACTS[
            control_id
        ]
        if content[1:] != [channel, command] or control.get("type") != control_type:
            _fail(f"VIA lighting control {control_id!r} does not match its closed contract.")
        surface = _surface(surfaces, surface_id)
        if field in ("brightness", "speed"):
            options = control.get("options")
            if (
                not isinstance(options, list)
                or len(options) != 2
                or any(not isinstance(item, int) or isinstance(item, bool) for item in options)
            ):
                _fail(f"VIA lighting control {control_id!r} has no integer range.")
            surface[field] = {"min": options[0], "max": options[1]}
        elif field == "color":
            surface["color"] = hub_lighting.standard_hsv_descriptor(channels=2)
        else:
            surface["effects"] = _effect_options(
                control.get("options"), f"VIA lighting control {control_id!r} options"
            )


def capabilities_from_definition(
    definition: object,
    *,
    via_protocol: int,
    current: Mapping[str, Mapping[str, Any]] | None = None,
    led_mapping: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Extract recognized built-in VIA lighting only; custom menus stay inert."""

    if not isinstance(definition, dict):
        _fail("The VIA definition must be an object.")
    if not isinstance(via_protocol, int) or isinstance(via_protocol, bool):
        _fail("The VIA protocol version must be an integer.")
    current_values = current or {}
    surfaces: dict[str, dict[str, Any]] = {}
    lighting = definition.get("lighting")
    if isinstance(lighting, str) and lighting in _COMMON_MENUS:
        _known_common_menu(lighting, surfaces, current_values)
    elif isinstance(lighting, dict):
        # VIA v2 custom lighting objects are definition-provided data.  Only
        # their surveyed built-in value ids are recognized.
        supported = lighting.get("supportedLightingValues")
        if not isinstance(supported, list):
            return {"surfaces": []}
        values = set(supported)
        if values & {QMK_BACKLIGHT_BRIGHTNESS, QMK_BACKLIGHT_EFFECT}:
            surface = _surface(surfaces, "backlight")
            if QMK_BACKLIGHT_BRIGHTNESS in values:
                surface["brightness"] = {"min": 0, "max": 255}
            if QMK_BACKLIGHT_EFFECT in values:
                surface["effects"] = _effect_options(
                    lighting.get("effects", []), "VIA v2 backlight effects"
                )
        if values & {
            QMK_RGBLIGHT_BRIGHTNESS,
            QMK_RGBLIGHT_EFFECT,
            QMK_RGBLIGHT_EFFECT_SPEED,
            QMK_RGBLIGHT_COLOR,
        }:
            surface = _surface(surfaces, "underglow")
            if QMK_RGBLIGHT_BRIGHTNESS in values:
                surface["brightness"] = {"min": 0, "max": 255}
            if QMK_RGBLIGHT_EFFECT in values:
                surface["effects"] = _effect_options(
                    lighting.get("underglowEffects", []),
                    "VIA v2 underglow effects",
                )
            if QMK_RGBLIGHT_EFFECT_SPEED in values:
                surface["speed"] = {"min": 0, "max": 255}
            if QMK_RGBLIGHT_COLOR in values:
                surface["color"] = hub_lighting.standard_hsv_descriptor(channels=2)
    menus = definition.get("menus")
    if menus is not None and via_protocol >= 11:
        if not isinstance(menus, list):
            _fail("VIA menus must be a list.")
        inline: list[Any] = []
        for menu in menus:
            if isinstance(menu, str):
                if menu in _COMMON_MENUS:
                    _known_common_menu(menu, surfaces, current_values)
            else:
                inline.append(menu)
        _inline_controls(inline, surfaces)
    mapped_leds = validate_led_mapping(led_mapping or {})
    if mapped_leds and "rgb_matrix" in surfaces:
        surfaces["rgb_matrix"]["per_key"] = {
            "pixel_count": len(mapped_leds),
            "color": hub_lighting.standard_hsv_descriptor(channels=2),
        }
    try:
        return hub_lighting.validate_capabilities(
            {"surfaces": [surfaces[key] for key in sorted(surfaces)]}
        )
    except hub_lighting.LightingModelError as exc:
        _fail(str(exc))


def state_from_values(
    capabilities: object,
    values: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    validated = hub_lighting.validate_capabilities(capabilities)
    states: list[dict[str, Any]] = []
    for surface in validated["surfaces"]:
        raw = values.get(surface["id"])
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            _fail(f"VIA lighting values for {surface['id']} must be an object.")
        try:
            states.append(
                hub_lighting.validate_surface_state(
                    {"id": surface["id"], **copy.deepcopy(dict(raw))}, surface
                )
            )
        except hub_lighting.LightingModelError as exc:
            _fail(str(exc))
    return {"surfaces": states}


def _state_map(lighting: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        state["id"]: state
        for state in (lighting or {}).get("surfaces", [])
    }


def _command_contract(
    generation: str,
    field: str,
    *,
    channel_mode: bool,
) -> tuple[int | None, int]:
    if channel_mode:
        channels = {
            "qmk_backlight": (1, {"brightness": 1, "effect_id": 2}),
            "qmk_rgblight": (
                2,
                {"brightness": 1, "effect_id": 2, "speed": 3, "color": 4},
            ),
            "qmk_rgb_matrix": (
                3,
                {"brightness": 1, "effect_id": 2, "speed": 3, "color": 4},
            ),
        }
        if generation not in channels or field not in channels[generation][1]:
            _fail(f"VIA has no recognized {generation} {field} command.")
        channel, commands = channels[generation]
        return channel, commands[field]
    values = {
        "qmk_backlight": {
            "brightness": QMK_BACKLIGHT_BRIGHTNESS,
            "effect_id": QMK_BACKLIGHT_EFFECT,
        },
        "qmk_rgblight": {
            "brightness": QMK_RGBLIGHT_BRIGHTNESS,
            "effect_id": QMK_RGBLIGHT_EFFECT,
            "speed": QMK_RGBLIGHT_EFFECT_SPEED,
            "color": QMK_RGBLIGHT_COLOR,
        },
    }
    if generation not in values or field not in values[generation]:
        _fail(f"VIA v2 has no recognized {generation} {field} value id.")
    return None, values[generation][field]


def plan_write(
    source_profile: dict[str, Any],
    target_profile: dict[str, Any],
    *,
    via_protocol: int,
    led_mapping: Mapping[str, int] | None = None,
) -> ViaLightingWritePlan:
    try:
        transfer = hub_lighting.plan_transfer(source_profile, target_profile)
    except hub_lighting.LightingModelError as exc:
        _fail(str(exc))
    capabilities = hub_lighting.validate_capabilities(
        target_profile.get("capabilities", {}).get("lighting", {"surfaces": []})
    )
    before = _state_map(target_profile.get("lighting"))
    after = _state_map(transfer.lighting)
    commands: list[ViaLightingCommand] = []
    save_channels: set[int | None] = set()
    # Hub files intentionally do not persist raw definitions.  Protocol 11+
    # uses channel contracts; older definitions use top-level value ids.
    channel_mode = via_protocol >= 11
    mapped_leds = validate_led_mapping(led_mapping or {})
    for surface in capabilities["surfaces"]:
        old = before.get(surface["id"], {"id": surface["id"]})
        new = after.get(surface["id"], old)
        old_per_key = old.get("per_key", {})
        new_per_key = new.get("per_key", old_per_key)
        if new_per_key != old_per_key:
            if via_protocol < 11 or "per_key" not in surface:
                _fail("VIA per-key colors have no recognized persistent command contract.")
            for key in sorted(set(old_per_key) | set(new_per_key)):
                if key not in new_per_key or new_per_key.get(key) == old_per_key.get(key):
                    continue
                if key not in mapped_leds:
                    _fail(f"VIA per-key color for {key} has no definition-proven LED index.")
                color = new_per_key[key]
                commands.append(
                    ViaLightingCommand(
                        surface["id"],
                        0,
                        1,
                        bytes([mapped_leds[key], 1, *color]),
                    )
                )
                save_channels.add(0)
        for field in ("effect_id", "brightness", "speed", "color"):
            if field not in new or new.get(field) == old.get(field):
                continue
            channel, command = _command_contract(
                surface["generation"], field, channel_mode=channel_mode
            )
            value = new[field]
            payload = bytes(value) if field == "color" else bytes([value])
            commands.append(
                ViaLightingCommand(surface["id"], channel, command, payload)
            )
            save_channels.add(channel)
    return ViaLightingWritePlan(
        lighting=copy.deepcopy(transfer.lighting),
        commands=tuple(commands),
        save_channels=tuple(
            sorted(save_channels, key=lambda item: -1 if item is None else item)
        ),
        items=transfer.items,
    )
