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
from .vial_keymap import UnsupportedKeycode, to_qmk

_EVENT_DOWN = 0x11
_EVENT_UP = 0x10


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
            animations.append(
                {
                    "name": f"page{page_index}.{field}",
                    "frames": [
                        [str(color).upper() for color in frame.get("frame_RGB") or []]
                        if isinstance(frame, dict)
                        else _fail(f"page {page_index} {field} frame is not an object")
                        for frame in frames
                    ],
                    "placement": "geometry_seam",
                }
            )
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
