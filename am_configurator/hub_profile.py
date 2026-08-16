"""The OpenKeeb hub profile format: one file that captures everything a
keyboard can be told, with per-field provenance.

This is the H1 landing of the schema drafted in
``docs/design/2026-08-15-hub-schema-draft.md``, written against the surveyed
tables in ``docs/design/2026-08-15-h0-keycode-capability-survey.md``. Every
ecosystem (AM, Vial, VIA) gets a reader and a writer against this one shape;
cross-board transfer always passes through it.

Settled here (delegated decisions, recorded 2026-08-16):

- On-disk encoding is JSON (matches every existing store file and the
  atomic-write helpers in ``store.py``).
- Provenance is a pointer map: a separate ``provenance`` object keyed by JSON
  pointer, where one pointer may cover a whole subtree.
- ``spoke_addressing`` is never stored; it is re-derived from the pinned
  definition at write time. The validator rejects it on sight.

Keycodes are the QMK 16-bit composed values carried verbatim (survey rule:
composition is preserved, never flattened). Canonical key identity is the
``K_*`` name (position-independent); the matrix map is a separate section so
cross-board matching never rides on wiring coordinates.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Callable

HUB_SCHEMA_VERSION = 1

ECOSYSTEMS = ("am", "vial", "via")
TRANSPORTS = ("hid", "serial")
ORIGINS = ("device", "user", "default")
VERDICTS = ("carried", "adapted", "dropped")
STATIC_COLOR_MODES = ("none", "global", "zone", "per_key")
LIGHTING_GENERATIONS = ("rgblight", "led_matrix", "rgb_matrix", "am_frames")
DEFINITION_SOURCES = ("device", "user_import")

MAX_BYTES = 4 * 1024 * 1024
MAX_LAYERS = 32
MAX_KEYS_PER_LAYER = 512
MAX_ENCODERS = 64
MAX_MACROS = 256
MAX_MACRO_EVENTS = 4096
MAX_TEXT_CHARS = 4096
MAX_DELAY_MS = 65535
MAX_ANIMATIONS = 64
MAX_FRAMES = 1024
MAX_PIXELS = 1024
MAX_REPORT_ITEMS = 4096

_TOP_FIELDS = {
    "schema_version",
    "identity",
    "capabilities",
    "keymap",
    "macros",
    "lighting",
    "provenance",
    "transfer_report",
}
_PAYLOAD_SECTIONS = ("keymap", "macros", "lighting")


class HubProfileError(ValueError):
    """A hub profile that does not follow the schema. The message is the
    plain-words reason, safe to show in the UI."""


def _fail(message: str) -> None:
    raise HubProfileError(message)


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object.")
    return value


def _reject_unknown(values: dict, allowed: set[str], label: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        _fail(f"{label} has unsupported fields: {', '.join(unknown)}.")


def _require(values: dict, fields: set[str], label: str) -> None:
    missing = sorted(fields - set(values))
    if missing:
        _fail(f"{label} is missing required fields: {', '.join(missing)}.")


def _int(value: object, label: str, *, low: int = 0, high: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _fail(f"{label} must be an integer.")
    if value < low or (high is not None and value > high):
        bound = f"{low}..{high}" if high is not None else f">= {low}"
        _fail(f"{label} must be in {bound}.")
    return value


def _str(value: object, label: str, *, max_len: int = 256) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty string.")
    if len(value) > max_len:
        _fail(f"{label} is longer than {max_len} characters.")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"{label} must be true or false.")
    return value


def _choice(value: object, choices: tuple[str, ...], label: str) -> str:
    if value not in choices:
        _fail(f"{label} must be one of: {', '.join(choices)}.")
    return value


def _key_identity(value: object, label: str) -> str:
    text = _str(value, label, max_len=64)
    body = text[2:]
    if not text.startswith("K_") or not body or not all(
        ch.isascii() and (ch.isupper() or ch.isdigit() or ch == "_") for ch in body
    ):
        _fail(f"{label} must be a canonical key identity like K_ENTER.")
    return text


def _keycode(value: object, label: str) -> int:
    return _int(value, label, low=0, high=0xFFFF)


def _hsv(value: object, label: str, *, channels: int = 3) -> list[int]:
    if not isinstance(value, list) or len(value) != channels:
        _fail(f"{label} must be a list of {channels} channel values.")
    return [_int(v, f"{label} channel", low=0, high=255) for v in value]


def _sha256(value: object, label: str) -> str:
    text = _str(value, label, max_len=80)
    if not text.startswith("sha256-") or len(text) != 71:
        _fail(f"{label} must be a sha256-<64 hex digits> digest.")
    digest = text[len("sha256-") :]
    if not all(ch in "0123456789abcdef" for ch in digest):
        _fail(f"{label} must use lowercase hex digits.")
    return text


# --- identity ---------------------------------------------------------------


def _validate_identity(value: object) -> dict:
    identity = _object(value, "identity")
    allowed = {"ecosystem", "family", "wire_identity", "endpoint", "protocol", "definition"}
    _reject_unknown(identity, allowed, "identity")
    _require(identity, {"ecosystem", "family", "wire_identity"}, "identity")
    result: dict[str, Any] = {
        "ecosystem": _choice(identity["ecosystem"], ECOSYSTEMS, "identity.ecosystem"),
        "family": _str(identity["family"], "identity.family"),
        "wire_identity": _str(identity["wire_identity"], "identity.wire_identity"),
    }
    if "endpoint" in identity:
        endpoint = _object(identity["endpoint"], "identity.endpoint")
        _reject_unknown(endpoint, {"vid", "pid", "transport"}, "identity.endpoint")
        _require(endpoint, {"transport"}, "identity.endpoint")
        out: dict[str, Any] = {
            "transport": _choice(endpoint["transport"], TRANSPORTS, "identity.endpoint.transport"),
        }
        for field in ("vid", "pid"):
            if field in endpoint:
                out[field] = _int(endpoint[field], f"identity.endpoint.{field}", low=0, high=0xFFFF)
        result["endpoint"] = out
    if "protocol" in identity:
        protocol = _object(identity["protocol"], "identity.protocol")
        _reject_unknown(
            protocol,
            {"via_protocol", "vial_protocol", "keycode_spec"},
            "identity.protocol",
        )
        out = {}
        for field in ("via_protocol", "vial_protocol"):
            if field in protocol:
                out[field] = _int(protocol[field], f"identity.protocol.{field}", low=0, high=255)
        if "keycode_spec" in protocol:
            out["keycode_spec"] = _str(protocol["keycode_spec"], "identity.protocol.keycode_spec", max_len=16)
        result["protocol"] = out
    if "definition" in identity:
        definition = _object(identity["definition"], "identity.definition")
        _reject_unknown(definition, {"source", "hash"}, "identity.definition")
        _require(definition, {"source", "hash"}, "identity.definition")
        result["definition"] = {
            "source": _choice(definition["source"], DEFINITION_SOURCES, "identity.definition.source"),
            "hash": _sha256(definition["hash"], "identity.definition.hash"),
        }
    return result


# --- capabilities -----------------------------------------------------------


def _validate_macro_budget(value: object) -> dict:
    budget = _object(value, "capabilities.macros.budget")
    _require(budget, {"model"}, "capabilities.macros.budget")
    model = _choice(budget["model"], ("events", "bytes"), "capabilities.macros.budget.model")
    if model == "events":
        fields = {"model", "tracks", "events_total"}
    else:
        fields = {"model", "slots", "buffer_bytes"}
    _reject_unknown(budget, fields, "capabilities.macros.budget")
    _require(budget, fields, "capabilities.macros.budget")
    result = {"model": model}
    for field in sorted(fields - {"model"}):
        result[field] = _int(budget[field], f"capabilities.macros.budget.{field}", low=0)
    return result


def _validate_capabilities(value: object) -> dict:
    capabilities = _object(value, "capabilities")
    _reject_unknown(capabilities, {"keymap", "macros", "lighting"}, "capabilities")
    result: dict[str, Any] = {}
    if "keymap" in capabilities:
        keymap = _object(capabilities["keymap"], "capabilities.keymap")
        _reject_unknown(keymap, {"layers", "keys_per_layer", "encoders"}, "capabilities.keymap")
        _require(keymap, {"layers", "keys_per_layer"}, "capabilities.keymap")
        out: dict[str, Any] = {
            "layers": _int(keymap["layers"], "capabilities.keymap.layers", low=1, high=MAX_LAYERS),
            "keys_per_layer": _int(
                keymap["keys_per_layer"], "capabilities.keymap.keys_per_layer", low=1, high=MAX_KEYS_PER_LAYER
            ),
        }
        if "encoders" in keymap:
            out["encoders"] = _int(keymap["encoders"], "capabilities.keymap.encoders", low=0, high=MAX_ENCODERS)
        result["keymap"] = out
    if "macros" in capabilities:
        macros = _object(capabilities["macros"], "capabilities.macros")
        _reject_unknown(macros, {"budget", "delays"}, "capabilities.macros")
        _require(macros, {"budget", "delays"}, "capabilities.macros")
        result["macros"] = {
            "budget": _validate_macro_budget(macros["budget"]),
            "delays": _bool(macros["delays"], "capabilities.macros.delays"),
        }
    if "lighting" in capabilities:
        lighting = _object(capabilities["lighting"], "capabilities.lighting")
        allowed = {"static_color", "hardware_effects", "per_key_direct", "custom_animation"}
        _reject_unknown(lighting, allowed, "capabilities.lighting")
        _require(lighting, {"static_color"}, "capabilities.lighting")
        out = {
            "static_color": _choice(
                lighting["static_color"], STATIC_COLOR_MODES, "capabilities.lighting.static_color"
            ),
        }
        if "hardware_effects" in lighting:
            groups = lighting["hardware_effects"]
            if not isinstance(groups, list):
                _fail("capabilities.lighting.hardware_effects must be a list.")
            validated = []
            for index, entry in enumerate(groups):
                label = f"capabilities.lighting.hardware_effects[{index}]"
                group = _object(entry, label)
                _reject_unknown(group, {"generation", "ids"}, label)
                _require(group, {"generation", "ids"}, label)
                ids = group["ids"]
                if not isinstance(ids, list) or len(ids) > 1024:
                    _fail(f"{label}.ids must be a list of at most 1024 effect ids.")
                validated.append(
                    {
                        "generation": _choice(group["generation"], LIGHTING_GENERATIONS, f"{label}.generation"),
                        "ids": [_int(v, f"{label}.ids entry", low=0, high=0xFFFF) for v in ids],
                    }
                )
            out["hardware_effects"] = validated
        if "per_key_direct" in lighting:
            out["per_key_direct"] = _bool(lighting["per_key_direct"], "capabilities.lighting.per_key_direct")
        if "custom_animation" in lighting:
            custom = lighting["custom_animation"]
            if custom is False:
                out["custom_animation"] = False
            else:
                label = "capabilities.lighting.custom_animation"
                animation = _object(custom, label)
                _reject_unknown(animation, {"frames_max", "streaming"}, label)
                _require(animation, {"frames_max", "streaming"}, label)
                out["custom_animation"] = {
                    "frames_max": _int(animation["frames_max"], f"{label}.frames_max", low=0, high=MAX_FRAMES),
                    "streaming": _bool(animation["streaming"], f"{label}.streaming"),
                }
        result["lighting"] = out
    return result


# --- keymap -----------------------------------------------------------------


def _validate_keymap(value: object) -> dict:
    keymap = _object(value, "keymap")
    if "spoke_addressing" in keymap:
        _fail(
            "keymap.spoke_addressing is never stored; it is re-derived from the "
            "pinned definition at write time."
        )
    _reject_unknown(keymap, {"layers", "matrix", "encoders"}, "keymap")
    _require(keymap, {"layers"}, "keymap")
    layers = keymap["layers"]
    if not isinstance(layers, list) or not layers or len(layers) > MAX_LAYERS:
        _fail(f"keymap.layers must be a list of 1..{MAX_LAYERS} layers.")
    seen_indexes: set[int] = set()
    validated_layers = []
    for position, entry in enumerate(layers):
        label = f"keymap.layers[{position}]"
        layer = _object(entry, label)
        _reject_unknown(layer, {"index", "keys"}, label)
        _require(layer, {"index", "keys"}, label)
        index = _int(layer["index"], f"{label}.index", low=0, high=MAX_LAYERS - 1)
        if index in seen_indexes:
            _fail(f"keymap.layers lists layer index {index} more than once.")
        seen_indexes.add(index)
        keys = layer["keys"]
        if not isinstance(keys, list) or len(keys) > MAX_KEYS_PER_LAYER:
            _fail(f"{label}.keys must be a list of at most {MAX_KEYS_PER_LAYER} keys.")
        seen_keys: set[str] = set()
        validated_keys = []
        for key_position, key_entry in enumerate(keys):
            key_label = f"{label}.keys[{key_position}]"
            key = _object(key_entry, key_label)
            _reject_unknown(key, {"key", "code", "carried", "native"}, key_label)
            _require(key, {"key", "code"}, key_label)
            identity = _key_identity(key["key"], f"{key_label}.key")
            if identity in seen_keys:
                _fail(f"{label} assigns {identity} more than once.")
            seen_keys.add(identity)
            out = {"key": identity, "code": _keycode(key["code"], f"{key_label}.code")}
            if "carried" in key:
                out["carried"] = _bool(key["carried"], f"{key_label}.carried")
            if "native" in key:
                # The spoke-native spelling of a code QMK cannot express,
                # kept so a round-trip back to the same ecosystem is
                # lossless. Only meaningful alongside carried: false.
                if out.get("carried") is not False:
                    _fail(f"{key_label}.native is only allowed when carried is false.")
                out["native"] = _str(key["native"], f"{key_label}.native", max_len=64)
            validated_keys.append(out)
        validated_layers.append({"index": index, "keys": validated_keys})
    result: dict[str, Any] = {"layers": validated_layers}
    if "matrix" in keymap:
        matrix = _object(keymap["matrix"], "keymap.matrix")
        _reject_unknown(matrix, {"rows", "cols", "map"}, "keymap.matrix")
        _require(matrix, {"rows", "cols", "map"}, "keymap.matrix")
        rows = _int(matrix["rows"], "keymap.matrix.rows", low=1, high=255)
        cols = _int(matrix["cols"], "keymap.matrix.cols", low=1, high=255)
        mapping = _object(matrix["map"], "keymap.matrix.map")
        validated_map = {}
        for name, position in mapping.items():
            identity = _key_identity(name, "keymap.matrix.map key")
            if not isinstance(position, list) or len(position) != 2:
                _fail(f"keymap.matrix.map[{identity}] must be a [row, col] pair.")
            row = _int(position[0], f"keymap.matrix.map[{identity}] row", low=0, high=rows - 1)
            col = _int(position[1], f"keymap.matrix.map[{identity}] col", low=0, high=cols - 1)
            validated_map[identity] = [row, col]
        result["matrix"] = {"rows": rows, "cols": cols, "map": validated_map}
    if "encoders" in keymap:
        encoders = keymap["encoders"]
        if not isinstance(encoders, list) or len(encoders) > MAX_ENCODERS:
            _fail(f"keymap.encoders must be a list of at most {MAX_ENCODERS} encoders.")
        validated_encoders = []
        for index, entry in enumerate(encoders):
            label = f"keymap.encoders[{index}]"
            encoder = _object(entry, label)
            _reject_unknown(encoder, {"key", "cw", "ccw"}, label)
            _require(encoder, {"key", "cw", "ccw"}, label)
            validated_encoders.append(
                {
                    "key": _key_identity(encoder["key"], f"{label}.key"),
                    "cw": _keycode(encoder["cw"], f"{label}.cw"),
                    "ccw": _keycode(encoder["ccw"], f"{label}.ccw"),
                }
            )
        result["encoders"] = validated_encoders
    return result


# --- macros -----------------------------------------------------------------

_EVENT_KINDS = ("tap", "down", "up", "text", "delay_ms")


def _validate_macro_event(value: object, label: str) -> dict:
    event = _object(value, label)
    if len(event) != 1:
        _fail(f"{label} must contain exactly one of: {', '.join(_EVENT_KINDS)}.")
    kind = next(iter(event))
    if kind not in _EVENT_KINDS:
        _fail(f"{label} must contain exactly one of: {', '.join(_EVENT_KINDS)}.")
    payload = event[kind]
    if kind in ("tap", "down", "up"):
        return {kind: _keycode(payload, f"{label}.{kind}")}
    if kind == "text":
        if not isinstance(payload, str) or len(payload) > MAX_TEXT_CHARS:
            _fail(f"{label}.text must be a string of at most {MAX_TEXT_CHARS} characters.")
        return {"text": payload}
    return {"delay_ms": _int(payload, f"{label}.delay_ms", low=0, high=MAX_DELAY_MS)}


def _validate_macros(value: object) -> list:
    if not isinstance(value, list) or len(value) > MAX_MACROS:
        _fail(f"macros must be a list of at most {MAX_MACROS} macros.")
    seen_slots: set[int] = set()
    result = []
    for position, entry in enumerate(value):
        label = f"macros[{position}]"
        macro = _object(entry, label)
        _reject_unknown(macro, {"slot", "events"}, label)
        _require(macro, {"slot", "events"}, label)
        slot = _int(macro["slot"], f"{label}.slot", low=0, high=MAX_MACROS - 1)
        if slot in seen_slots:
            _fail(f"macros lists slot {slot} more than once.")
        seen_slots.add(slot)
        events = macro["events"]
        if not isinstance(events, list) or len(events) > MAX_MACRO_EVENTS:
            _fail(f"{label}.events must be a list of at most {MAX_MACRO_EVENTS} events.")
        result.append(
            {
                "slot": slot,
                "events": [
                    _validate_macro_event(event, f"{label}.events[{index}]")
                    for index, event in enumerate(events)
                ],
            }
        )
    return result


# --- lighting ---------------------------------------------------------------

_RGB_CHARS = set("0123456789ABCDEF")


def _rgb(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 7
        or not value.startswith("#")
        or not set(value[1:]) <= _RGB_CHARS
    ):
        _fail(f"{label} must be an uppercase #RRGGBB color.")
    return value


def _validate_lighting(value: object) -> dict:
    lighting = _object(value, "lighting")
    _reject_unknown(lighting, {"static", "hardware_effect", "animations"}, "lighting")
    result: dict[str, Any] = {}
    if "static" in lighting:
        static = _object(lighting["static"], "lighting.static")
        _reject_unknown(static, {"mode", "color", "per_key"}, "lighting.static")
        _require(static, {"mode"}, "lighting.static")
        mode = _choice(static["mode"], ("global", "per_key"), "lighting.static.mode")
        out: dict[str, Any] = {"mode": mode}
        if mode == "global":
            _require(static, {"mode", "color"}, "lighting.static")
            out["color"] = _hsv(static["color"], "lighting.static.color")
        else:
            _require(static, {"mode", "per_key"}, "lighting.static")
            per_key = _object(static["per_key"], "lighting.static.per_key")
            if len(per_key) > MAX_KEYS_PER_LAYER:
                _fail(f"lighting.static.per_key must map at most {MAX_KEYS_PER_LAYER} keys.")
            out["per_key"] = {
                _key_identity(name, "lighting.static.per_key key"): _hsv(
                    color, f"lighting.static.per_key[{name}]"
                )
                for name, color in per_key.items()
            }
        result["static"] = out
    if "hardware_effect" in lighting:
        effect = _object(lighting["hardware_effect"], "lighting.hardware_effect")
        _reject_unknown(effect, {"generation", "id", "speed", "color"}, "lighting.hardware_effect")
        _require(effect, {"generation", "id"}, "lighting.hardware_effect")
        out = {
            "generation": _choice(
                effect["generation"], LIGHTING_GENERATIONS, "lighting.hardware_effect.generation"
            ),
            "id": _int(effect["id"], "lighting.hardware_effect.id", low=0, high=0xFFFF),
        }
        if "speed" in effect:
            out["speed"] = _int(effect["speed"], "lighting.hardware_effect.speed", low=0, high=255)
        if "color" in effect:
            out["color"] = _hsv(effect["color"], "lighting.hardware_effect.color", channels=2)
        result["hardware_effect"] = out
    if "animations" in lighting:
        animations = lighting["animations"]
        if not isinstance(animations, list) or len(animations) > MAX_ANIMATIONS:
            _fail(f"lighting.animations must be a list of at most {MAX_ANIMATIONS} animations.")
        validated = []
        for index, entry in enumerate(animations):
            label = f"lighting.animations[{index}]"
            animation = _object(entry, label)
            _reject_unknown(
                animation,
                {"name", "frames", "placement", "frame_ms", "brightness"},
                label,
            )
            _require(animation, {"name", "frames", "placement"}, label)
            frames = animation["frames"]
            if not isinstance(frames, list) or not frames or len(frames) > MAX_FRAMES:
                _fail(f"{label}.frames must be a list of 1..{MAX_FRAMES} frames.")
            pixels = None
            validated_frames = []
            for frame_index, frame in enumerate(frames):
                frame_label = f"{label}.frames[{frame_index}]"
                if not isinstance(frame, list) or not frame or len(frame) > MAX_PIXELS:
                    _fail(f"{frame_label} must be a list of 1..{MAX_PIXELS} colors.")
                if pixels is None:
                    pixels = len(frame)
                elif len(frame) != pixels:
                    _fail(f"{label} frames must all contain the same number of colors.")
                validated_frames.append([_rgb(color, f"{frame_label} color") for color in frame])
            out = {
                "name": _str(animation["name"], f"{label}.name", max_len=128),
                "frames": validated_frames,
                "placement": _choice(animation["placement"], ("geometry_seam",), f"{label}.placement"),
            }
            if "frame_ms" in animation:
                out["frame_ms"] = _int(animation["frame_ms"], f"{label}.frame_ms", low=1, high=65535)
            if "brightness" in animation:
                out["brightness"] = _int(animation["brightness"], f"{label}.brightness", low=0, high=100)
            validated.append(out)
        result["animations"] = validated
    return result


# --- provenance (pointer map) ----------------------------------------------


def _pointer_tokens(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        _fail(f"provenance pointer {pointer!r} must start with '/'.")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]


def _resolve_pointer(profile: dict, pointer: str) -> object:
    node: object = profile
    for token in _pointer_tokens(pointer):
        if isinstance(node, dict):
            if token not in node:
                _fail(f"provenance pointer {pointer!r} does not resolve in this profile.")
            node = node[token]
        elif isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                _fail(f"provenance pointer {pointer!r} does not resolve in this profile.")
            node = node[int(token)]
        else:
            _fail(f"provenance pointer {pointer!r} does not resolve in this profile.")
    return node


def _validate_provenance(value: object, profile: dict) -> dict:
    provenance = _object(value, "provenance")
    result = {}
    for pointer, origin in provenance.items():
        root = _pointer_tokens(pointer)[0]
        if root not in _PAYLOAD_SECTIONS and root not in ("identity", "capabilities"):
            _fail(f"provenance pointer {pointer!r} must point inside the profile payload.")
        _resolve_pointer(profile, pointer)
        result[pointer] = _choice(origin, ORIGINS, f"provenance[{pointer}]")
    return result


def _leaf_pointers(node: object, prefix: str) -> list[str]:
    if isinstance(node, dict):
        if not node:
            return [prefix]
        return [
            pointer
            for token, child in node.items()
            for pointer in _leaf_pointers(
                child, f"{prefix}/{token.replace('~', '~0').replace('/', '~1')}"
            )
        ]
    if isinstance(node, list):
        if not node:
            return [prefix]
        return [
            pointer
            for index, child in enumerate(node)
            for pointer in _leaf_pointers(child, f"{prefix}/{index}")
        ]
    return [prefix]


def uncovered_leaves(profile: dict) -> list[str]:
    """Leaf pointers under keymap/macros/lighting with no provenance.

    A pointer covers itself and everything beneath it, so ``"/keymap":
    "device"`` covers the whole keymap. Writers must leave this empty; the
    validator does not force it so hand-edited files fail with the better
    message ("no provenance for X") at write time, not load time.
    """

    validated = validate_hub_profile(profile)
    covered = list(validated.get("provenance", {}))
    uncovered = []
    for section in _PAYLOAD_SECTIONS:
        if section not in validated:
            continue
        for pointer in _leaf_pointers(validated[section], f"/{section}"):
            if not any(pointer == entry or pointer.startswith(entry + "/") for entry in covered):
                uncovered.append(pointer)
    return uncovered


# --- transfer report --------------------------------------------------------


def _validate_report_identity(value: object, label: str) -> dict:
    return _validate_identity(_object(value, label))


def validate_transfer_report(value: object) -> dict:
    """Validate a transfer report: source, target, and per-item verdicts.

    Three verdicts only — carried / adapted / dropped. Anything not carried
    verbatim must say why in plain words; this is UI input, not a log.
    """

    report = _object(value, "transfer_report")
    _reject_unknown(report, {"source", "target", "items"}, "transfer_report")
    _require(report, {"source", "target", "items"}, "transfer_report")
    items = report["items"]
    if not isinstance(items, list) or len(items) > MAX_REPORT_ITEMS:
        _fail(f"transfer_report.items must be a list of at most {MAX_REPORT_ITEMS} items.")
    validated_items = []
    for index, entry in enumerate(items):
        label = f"transfer_report.items[{index}]"
        item = _object(entry, label)
        _reject_unknown(item, {"path", "verdict", "reason"}, label)
        _require(item, {"path", "verdict"}, label)
        verdict = _choice(item["verdict"], VERDICTS, f"{label}.verdict")
        out = {
            "path": _str(item["path"], f"{label}.path", max_len=512),
            "verdict": verdict,
        }
        if verdict in ("adapted", "dropped"):
            _require(item, {"path", "verdict", "reason"}, label)
        if "reason" in item:
            out["reason"] = _str(item["reason"], f"{label}.reason", max_len=1024)
        validated_items.append(out)
    return {
        "source": _validate_report_identity(report["source"], "transfer_report.source"),
        "target": _validate_report_identity(report["target"], "transfer_report.target"),
        "items": validated_items,
    }


# --- whole profile ----------------------------------------------------------


def validate_hub_profile(value: object) -> dict:
    """Validate and normalize one hub profile. Returns a deep, independent copy."""

    profile = _object(value, "The hub profile")
    _reject_unknown(profile, _TOP_FIELDS, "The hub profile")
    _require(profile, {"schema_version", "identity"}, "The hub profile")
    if profile["schema_version"] != HUB_SCHEMA_VERSION:
        _fail(
            f"This app reads hub profiles with schema_version {HUB_SCHEMA_VERSION}; "
            f"this file says {profile['schema_version']!r}."
        )
    sections: dict[str, Callable[[object], object]] = {
        "capabilities": _validate_capabilities,
        "keymap": _validate_keymap,
        "macros": _validate_macros,
        "lighting": _validate_lighting,
        "transfer_report": validate_transfer_report,
    }
    result: dict[str, Any] = {
        "schema_version": HUB_SCHEMA_VERSION,
        "identity": _validate_identity(profile["identity"]),
    }
    for section, validator in sections.items():
        if section in profile:
            result[section] = validator(profile[section])
    if "provenance" in profile:
        result["provenance"] = _validate_provenance(profile["provenance"], result)
    return copy.deepcopy(result)


def dumps_hub_profile(profile: dict) -> str:
    """Canonical on-disk text: validated, sorted keys, 2-space indent, JSON."""

    validated = validate_hub_profile(profile)
    return json.dumps(validated, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


class _DuplicateKeyError(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, entry in pairs:
        if name in result:
            raise _DuplicateKeyError(f"The profile repeats the field {name!r}.")
        result[name] = entry
    return result


def loads_hub_profile(payload: bytes | str) -> dict:
    """Parse and validate hub profile text (or bytes) from an untrusted source."""

    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if not isinstance(payload, (bytes, bytearray)):
        _fail("The hub profile payload must be text or bytes.")
    if len(payload) > MAX_BYTES:
        _fail(f"The hub profile is larger than {MAX_BYTES // (1024 * 1024)} MiB.")
    try:
        parsed = json.loads(
            bytes(payload).decode("utf-8"),
            object_pairs_hook=_object_without_duplicates,
        )
    except _DuplicateKeyError as exc:
        raise HubProfileError(str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise HubProfileError("The hub profile is not valid UTF-8 text.") from exc
    except json.JSONDecodeError as exc:
        raise HubProfileError(f"The hub profile is not valid JSON: {exc.msg} (line {exc.lineno}).") from exc
    return validate_hub_profile(parsed)
