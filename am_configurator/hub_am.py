"""The AM spoke: build a hub profile from one AM configuration.

This is the first spoke of the hub format (H1 of the hub-configurator plan).
It reads the AM configuration JSON this application already stores — the
``key_layer``/``macro_key``/``page_data`` shape ``validate_config`` enforces —
and expresses it in the hub vocabulary defined by ``hub_profile``.

Spoke decisions, recorded here because the AM data forces them:

- **Key identities are positional** (``K_I000``…): AM boards ship no
  authored definition naming their keys, so the index into the family's
  flat key list is the only identity that exists. Semantic naming
  (K_ENTER) is the overlay engine's job, inferred from what keys do —
  never invented here. No ``matrix`` section is emitted for the same
  reason: the serial families' row/column semantics are not authored
  anywhere we can cite.
- **Keycodes translate through the proven Vial mapping** (`to_qmk`); a
  code QMK cannot express is kept verbatim in ``native`` with
  ``carried: false`` and ``code: 0`` so a round-trip back to AM is
  lossless and a transfer elsewhere reports honestly instead of guessing.
- **Macro events decode the AM wire truth**: ``#11PPUUUU`` is key-down,
  ``#10PPUUUU`` key-up, each with a following pause from ``intvel_ms``.
- **Lighting tracks become hub animations** named ``page<N>.<track>``,
  placement ``geometry_seam`` (the settled placement rule).
"""

from __future__ import annotations

from typing import Any

from . import device_mapping
from .hub_profile import HUB_SCHEMA_VERSION, validate_hub_profile
from .vial_keymap import UnsupportedKeycode, from_qmk, parse_code, to_qmk

_EVENT_DOWN = 0x11
_EVENT_UP = 0x10

_CODE_NO = "#00000000"

# HID modifier bits (low nibble = left hand) and the keyboard-page usage of
# the modifier *key* itself: LCtrl 0xE0, LShift 0xE1, LAlt 0xE2, LGui 0xE3,
# right-hand variants +4.
_MODIFIER_USAGES = ((0x01, 0xE0), (0x02, 0xE1), (0x04, 0xE2), (0x08, 0xE3))


class AmSpokeError(ValueError):
    """An AM configuration this spoke cannot express. Message is UI-safe."""


def _fail(message: str) -> str:
    raise AmSpokeError(message)


def _code_parts(code: object, label: str) -> tuple[int, int, int]:
    if not isinstance(code, str) or len(code) != 9 or not code.startswith("#"):
        _fail(f"{label} is not a #MMPPUUUU keycode.")
    try:
        raw = bytes.fromhex(code[1:])
    except ValueError:
        _fail(f"{label} is not a #MMPPUUUU keycode.")
    return raw[0], raw[1], (raw[2] << 8) | raw[3]


def _key_entry(index: int, code: str, label: str) -> dict[str, Any]:
    identity = f"K_I{index:03d}"
    try:
        return {"key": identity, "code": to_qmk(code)}
    except UnsupportedKeycode:
        return {"key": identity, "code": 0, "carried": False, "native": code.upper()}


def _keymap(config: dict[str, Any], keys_per_layer: int) -> dict[str, Any] | None:
    key_layer = config.get("key_layer") or {}
    layer_data = key_layer.get("layer_data") or []
    if not layer_data:
        return None
    layers = []
    for position, entry in enumerate(layer_data):
        label = f"key_layer.layer_data[{position}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("layer"), list):
            _fail(f"{label} must contain a layer list.")
        codes = entry["layer"]
        if len(codes) != keys_per_layer:
            _fail(f"{label} must contain exactly {keys_per_layer} keycodes.")
        layers.append(
            {
                "index": position,
                "keys": [
                    _key_entry(index, code, f"{label}.layer[{index}]")
                    for index, code in enumerate(codes)
                ],
            }
        )
    return {"layers": layers}


def _macro_events(macro: dict[str, Any], label: str) -> list[dict[str, Any]]:
    codes = macro.get("layer_key") or []
    delays = macro.get("intvel_ms") or []
    events: list[dict[str, Any]] = []
    for index, code in enumerate(codes):
        event_label = f"{label}.layer_key[{index}]"
        marker, page, usage = _code_parts(code, event_label)
        if marker == _EVENT_DOWN:
            kind = "down"
        elif marker == _EVENT_UP:
            kind = "up"
        else:
            _fail(f"{event_label} is neither key-down (11) nor key-up (10).")
        try:
            value = to_qmk(f"#00{page:02X}{usage:04X}")
        except UnsupportedKeycode as exc:
            _fail(f"{event_label} cannot be expressed as a QMK keycode: {exc}")
        events.append({kind: value})
        if index < len(delays):
            pause = delays[index]
            if not isinstance(pause, int) or isinstance(pause, bool) or not 0 <= pause <= 65535:
                _fail(f"{label}.intvel_ms[{index}] must be 0..65535 milliseconds.")
            if pause:
                events.append({"delay_ms": pause})
    return events


def _macros(config: dict[str, Any]) -> list[dict[str, Any]] | None:
    macro_key = config.get("macro_key") or []
    if not macro_key:
        return None
    result = []
    for slot, macro in enumerate(macro_key):
        label = f"macro_key[{slot}]"
        if not isinstance(macro, dict):
            _fail(f"{label} must be an object.")
        result.append({"slot": slot, "events": _macro_events(macro, label)})
    return result


def _animations(config: dict[str, Any]) -> list[dict[str, Any]]:
    animations = []
    for page in config.get("page_data") or []:
        if not isinstance(page, dict):
            continue
        page_index = page.get("page_index", "?")
        for field in ("frames", "keyframes", "spotlight_frames"):
            track = page.get(field)
            if not isinstance(track, dict):
                continue
            frames = track.get("frame_data") or []
            if not frames:
                continue
            animation: dict[str, Any] = {
                "name": f"page{page_index}.{field}",
                "frames": [
                    [str(color).upper() for color in frame.get("frame_RGB") or []]
                    if isinstance(frame, dict)
                    else _fail(f"page {page_index} {field} frame is not an object")
                    for frame in frames
                ],
                "placement": "geometry_seam",
            }
            speed = page.get("speed_ms")
            if isinstance(speed, int) and not isinstance(speed, bool) and 1 <= speed <= 65535:
                animation["frame_ms"] = speed
            lightness = page.get("lightness")
            if isinstance(lightness, int) and not isinstance(lightness, bool) and 0 <= lightness <= 100:
                animation["brightness"] = lightness
            animations.append(animation)
    return animations


def _capabilities(spec: device_mapping.FamilySpec, layer_count: int) -> dict[str, Any]:
    if spec.macro_buffer_bytes:
        budget: dict[str, Any] = {
            "model": "bytes",
            "slots": spec.macro_tracks,
            "buffer_bytes": spec.macro_buffer_bytes,
        }
    else:
        budget = {
            "model": "events",
            "tracks": spec.macro_tracks,
            "events_total": spec.macro_events,
        }
    return {
        "keymap": {
            "layers": max(1, layer_count),
            "keys_per_layer": spec.keys_per_layer,
        },
        "macros": {"budget": budget, "delays": True},
        "lighting": {
            "static_color": "per_key",
            "per_key_direct": False,
            "custom_animation": {"frames_max": spec.frame_cap, "streaming": False},
        },
    }


def build_hub_profile(config: dict[str, Any], *, origin: str = "user") -> dict[str, Any]:
    """Express one AM configuration as a validated hub profile.

    ``origin`` is the provenance of the configuration's content: ``"device"``
    when it was read from a keyboard, ``"user"`` when it was authored or
    edited in this application.
    """

    if origin not in ("device", "user"):
        raise AmSpokeError("The profile origin must be 'device' or 'user'.")
    if not isinstance(config, dict):
        raise AmSpokeError("The AM configuration must be a JSON object.")
    product_id = (config.get("product_info") or {}).get("product_id")
    if not isinstance(product_id, str) or not product_id:
        raise AmSpokeError("The AM configuration names no product_id.")
    try:
        family = device_mapping.led_model(product_id)
    except ValueError as exc:
        raise AmSpokeError(str(exc)) from exc
    spec = device_mapping.spec_for_product(product_id)

    keymap = _keymap(config, spec.keys_per_layer)
    macros = _macros(config)
    animations = _animations(config)

    profile: dict[str, Any] = {
        "schema_version": HUB_SCHEMA_VERSION,
        "identity": {
            "ecosystem": "am",
            "family": family,
            "wire_identity": device_mapping.config_product_id(product_id),
            "endpoint": {"transport": spec.transport},
        },
        "capabilities": _capabilities(
            spec, len(keymap["layers"]) if keymap else 1
        ),
    }
    provenance: dict[str, str] = {}
    if keymap is not None:
        profile["keymap"] = keymap
        provenance["/keymap"] = origin
    if macros is not None:
        profile["macros"] = macros
        provenance["/macros"] = origin
    if animations:
        profile["lighting"] = {"animations": animations}
        provenance["/lighting"] = origin
    if provenance:
        profile["provenance"] = provenance
    try:
        return validate_hub_profile(profile)
    except ValueError as exc:
        raise AmSpokeError(f"The AM configuration does not fit the hub format: {exc}") from exc


# --- hub -> AM (the apply direction) ---------------------------------------


class _Report:
    """Collects carried/adapted/dropped items while a profile is applied."""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def carried(self, path: str) -> None:
        self.items.append({"path": path, "verdict": "carried"})

    def adapted(self, path: str, reason: str) -> None:
        self.items.append({"path": path, "verdict": "adapted", "reason": reason})

    def dropped(self, path: str, reason: str) -> None:
        self.items.append({"path": path, "verdict": "dropped", "reason": reason})


def _positional_index(identity: str) -> int | None:
    if identity.startswith("K_I") and identity[3:].isdigit():
        return int(identity[3:])
    return None


def _apply_keymap(
    profile: dict[str, Any],
    spec: device_mapping.FamilySpec,
    source_is_am: bool,
    report: _Report,
) -> dict[str, Any] | None:
    keymap = profile.get("keymap")
    if keymap is None:
        return None
    width = spec.keys_per_layer
    layer_data = []
    for layer in sorted(keymap["layers"], key=lambda entry: entry["index"]):
        codes = [_CODE_NO] * width
        for entry in layer["keys"]:
            path = f"keymap.layers[{layer['index']}].keys[{entry['key']}]"
            index = _positional_index(entry["key"])
            if index is None:
                report.dropped(
                    path,
                    "AM boards address keys by position; a named key has no "
                    "position here until the overlay engine assigns one.",
                )
                continue
            if index >= width:
                report.dropped(
                    path,
                    f"this keyboard has {width} keys; source key {index + 1} "
                    "has no home.",
                )
                continue
            if entry.get("carried") is False and "native" in entry:
                if source_is_am:
                    codes[index] = entry["native"]
                    report.carried(path)
                else:
                    report.dropped(
                        path,
                        "this key uses a code native to another ecosystem and "
                        "has no QMK meaning to translate.",
                    )
                continue
            codes[index] = from_qmk(entry["code"])
            report.carried(path)
        layer_data.append({"layer": codes})
    if not layer_data:
        return None
    return {"layer_num": len(layer_data), "layer_data": layer_data}


def _macro_wire_events(
    events: list[dict[str, Any]], path: str, report: _Report
) -> tuple[list[str], list[int]] | None:
    codes: list[str] = []
    delays: list[int] = []
    adapted = False

    def emit(marker: int, page: int, usage: int) -> None:
        codes.append(f"#{marker:02X}{page:02X}{usage:04X}")
        delays.append(0)

    def emit_value(value: int, markers: tuple[int, ...], event_path: str) -> bool:
        nonlocal adapted
        spelling = parse_code(from_qmk(value))
        if spelling.modifier:
            modifier_usages = [
                usage + (4 if spelling.modifier & 0xF0 else 0)
                for bit, usage in _MODIFIER_USAGES
                if spelling.modifier & (bit | (bit << 4))
            ]
            for usage in modifier_usages:
                emit(_EVENT_DOWN, 0x07, usage)
            for marker in markers:
                emit(marker, spelling.page, spelling.usage)
            for usage in reversed(modifier_usages):
                emit(_EVENT_UP, 0x07, usage)
            report.adapted(
                event_path,
                "AM macros hold one key per event; the modifier became its own "
                "press and release around the key.",
            )
            adapted = True
            return True
        for marker in markers:
            emit(marker, spelling.page, spelling.usage)
        return True

    for index, event in enumerate(events):
        event_path = f"{path}.events[{index}]"
        kind = next(iter(event))
        value = event[kind]
        if kind == "delay_ms":
            if delays:
                delays[-1] = min(0xFFFF, delays[-1] + value)
            elif value:
                report.adapted(
                    event_path,
                    "AM macros pause after a key, not before the first one; the "
                    "leading pause was dropped.",
                )
                adapted = True
            continue
        if kind == "text":
            report.dropped(
                event_path,
                "typed text needs a keyboard layout to become key events; type "
                "it in the macro editor instead.",
            )
            return None
        markers = {
            "down": (_EVENT_DOWN,),
            "up": (_EVENT_UP,),
            "tap": (_EVENT_DOWN, _EVENT_UP),
        }[kind]
        emit_value(value, markers, event_path)
    if not codes:
        report.dropped(path, "this macro has no key events after translation.")
        return None
    if not adapted:
        report.carried(path)
    return codes, delays


def _apply_macros(
    profile: dict[str, Any],
    spec: device_mapping.FamilySpec,
    report: _Report,
) -> list[dict[str, Any]] | None:
    macros = profile.get("macros")
    if not macros:
        return None
    result = []
    for macro in sorted(macros, key=lambda entry: entry["slot"]):
        slot = macro["slot"]
        path = f"macros[{slot}]"
        if slot >= spec.macro_tracks:
            report.dropped(
                path, f"this keyboard stores {spec.macro_tracks} macros; slot "
                f"{slot + 1} has no home."
            )
            continue
        wire = _macro_wire_events(macro["events"], path, report)
        if wire is None:
            continue
        codes, delays = wire
        if len(codes) > spec.macro_events:
            report.dropped(
                path,
                f"this macro needs {len(codes)} events; the keyboard stores at "
                f"most {spec.macro_events}.",
            )
            continue
        result.append(
            {
                "original_key": f"#009201{slot:02X}",
                "layer_key": codes,
                "intvel_ms": delays,
            }
        )
    return result or None


def _blank_page(page_index: int) -> dict[str, Any]:
    """The canonical AM page scaffold the serial wire encoder expects."""

    return {
        "valid": 1,
        "page_index": page_index,
        "lightness": 100,
        "speed_ms": 90,
        "color": {"default": False, "back_rgb": "#000000", "rgb": "#000000"},
        "word_page": {"valid": 0, "word_len": 0, "unicode": []},
        "frames": {"valid": 0, "frame_num": 0, "frame_data": []},
        "keyframes": {"valid": 0, "frame_num": 0, "frame_data": []},
    }


def _apply_lighting(
    profile: dict[str, Any],
    spec: device_mapping.FamilySpec,
    report: _Report,
) -> list[dict[str, Any]] | None:
    lighting = profile.get("lighting") or {}
    animations = lighting.get("animations") or []
    pages: dict[int, dict[str, Any]] = {}
    for position, animation in enumerate(animations):
        path = f"lighting.animations[{position}]"
        name = animation["name"]
        prefix, _, field = name.partition(".")
        if not (
            prefix.startswith("page")
            and prefix[4:].isdigit()
            and field in ("frames", "keyframes", "spotlight_frames")
        ):
            report.dropped(
                path,
                f"animation {name!r} does not target an AM lighting page; the "
                "editor can place it manually.",
            )
            continue
        page_index = int(prefix[4:])
        if field == "spotlight_frames" and page_index not in (5, 6, 7):
            report.dropped(
                path,
                f"{name} targets the spotlight, which only exists on custom "
                "pages 5, 6, and 7.",
            )
            continue
        expected = spec.track_colors(field)
        frames = animation["frames"]
        if len(frames[0]) != expected:
            report.dropped(
                path,
                f"{name} paints {len(frames[0])} lights; this keyboard's "
                f"{field} track has {expected}.",
            )
            continue
        if len(frames) > spec.frame_cap:
            report.dropped(
                path,
                f"{name} has {len(frames)} frames; this keyboard plays at most "
                f"{spec.frame_cap}.",
            )
            continue
        page = pages.setdefault(page_index, _blank_page(page_index))
        page[field] = {
            "valid": 1,
            "frame_num": len(frames),
            "frame_data": [
                {"frame_index": index, "frame_RGB": list(frame)}
                for index, frame in enumerate(frames)
            ],
        }
        if "frame_ms" in animation:
            page["speed_ms"] = animation["frame_ms"]
        if "brightness" in animation:
            page["lightness"] = animation["brightness"]
        report.carried(path)
    if not pages:
        return None
    return [pages[index] for index in sorted(pages)]


def apply_hub_profile(profile: dict[str, Any], *, product_id: str) -> dict[str, Any]:
    """Express one hub profile as an AM configuration for ``product_id``.

    Returns ``{"config": ..., "report": ...}`` where the report is a validated
    transfer report: every source item is carried, adapted (with the reason),
    or dropped (with the reason). Nothing is written to any device here; the
    result goes through the normal preflight and typed-confirmation write flow.
    """

    validated = validate_hub_profile(profile)
    if not isinstance(product_id, str) or not product_id:
        raise AmSpokeError("The target product_id is missing.")
    try:
        family = device_mapping.led_model(product_id)
    except ValueError as exc:
        raise AmSpokeError(str(exc)) from exc
    spec = device_mapping.spec_for_product(product_id)
    source_is_am = validated["identity"]["ecosystem"] == "am"

    report = _Report()
    key_layer = _apply_keymap(validated, spec, source_is_am, report)
    macros = _apply_macros(validated, spec, report)
    pages = _apply_lighting(validated, spec, report)

    config: dict[str, Any] = {
        "product_info": {"product_id": device_mapping.config_product_id(product_id)},
    }
    if key_layer is not None:
        config["key_layer"] = key_layer
    if macros is not None:
        config["macro_key"] = macros
    if pages is not None:
        config["page_data"] = pages

    from .hub_profile import validate_transfer_report

    transfer_report = validate_transfer_report(
        {
            "source": validated["identity"],
            "target": {
                "ecosystem": "am",
                "family": family,
                "wire_identity": device_mapping.config_product_id(product_id),
                "endpoint": {"transport": spec.transport},
            },
            "items": report.items,
        }
    )
    return {"config": config, "report": transfer_report}
