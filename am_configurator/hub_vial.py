"""Pure Vial spoke for OpenKeeb's hub profile.

H2 begins at the protocol boundary rather than at a physical keyboard.  A
``VialSnapshot`` is the complete result of read-only discovery: the embedded
definition, protocol/USB identity, and already-read keymap and macro buffers.
The fixture loader validates that untrusted shape before any codec sees it.

The inverse path produces a ``VialWritePlan`` containing complete replacement
buffers plus the carried/adapted/dropped report.  It deliberately owns no HID
session and exposes no write function; a later H2 transport slice must put the
plan behind the existing device/model confirmation and Vial unlock gates.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import re
from typing import Any

from . import hid_transport, vial_keymap, vial_macros
from .hub_profile import (
    HUB_SCHEMA_VERSION,
    validate_hub_profile,
    validate_transfer_report,
)


_SNAPSHOT_FIELDS = {
    "definition",
    "via_protocol",
    "vial_protocol",
    "firmware_uid",
    "usb_vendor_id",
    "usb_product_id",
    "layer_count",
    "keymap_hex",
    "macro_count",
    "macro_buffer_bytes",
    "macro_hex",
}
_UID_RE = re.compile(r"^[0-9a-fA-F]{16}$")
_MATRIX_KEY_RE = re.compile(r"^K_R([0-9]+)_C([0-9]+)$")
_MAX_KEYS_PER_LAYER = 512
_MAX_LAYERS = 32
_MAX_MACROS = 128
_MAX_MACRO_BUFFER = 65535


class VialSpokeError(ValueError):
    """A Vial snapshot or transfer cannot be represented safely."""


@dataclass(frozen=True)
class VialSnapshot:
    """One read-only Vial discovery result, independent of a HID session."""

    definition: dict[str, Any]
    definition_hash: str
    name: str
    matrix_rows: int
    matrix_cols: int
    key_layout: tuple[dict[str, int | float], ...]
    via_protocol: int
    vial_protocol: int
    firmware_uid: str
    usb_vendor_id: int
    usb_product_id: int
    layer_count: int
    keymap_buffer: bytes
    macro_count: int
    macro_buffer_bytes: int
    macro_buffer: bytes

    @property
    def keys_per_layer(self) -> int:
        return self.matrix_rows * self.matrix_cols


@dataclass(frozen=True)
class VialWritePlan:
    """Buffers a confirmed transport may write, but never writes itself."""

    keymap_buffer: bytes | None
    macro_buffer: bytes | None
    report: dict[str, Any]


def _fail(message: str) -> None:
    raise VialSpokeError(message)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object.")
    return value


def _integer(value: object, label: str, *, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        _fail(f"{label} must be an integer in {low}..{high}.")
    return value


def _hex_bytes(value: object, label: str) -> bytes:
    if not isinstance(value, str):
        _fail(f"{label} must be a hexadecimal string.")
    try:
        return bytes.fromhex(value)
    except ValueError:
        _fail(f"{label} must be a hexadecimal string.")


def _canonical_definition(value: object) -> dict[str, Any]:
    definition = _object(value, "Vial definition")
    try:
        encoded = json.dumps(
            definition,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        canonical = json.loads(encoded)
    except (TypeError, ValueError, UnicodeError) as error:
        raise VialSpokeError("The Vial definition is not canonical JSON.") from error
    return canonical


def load_snapshot(value: object) -> VialSnapshot:
    """Validate a fixture/read-only discovery record into an immutable seam."""

    record = _object(value, "Vial snapshot")
    unknown = sorted(set(record) - _SNAPSHOT_FIELDS)
    missing = sorted(_SNAPSHOT_FIELDS - set(record))
    if unknown:
        _fail(f"Vial snapshot has unknown fields: {', '.join(unknown)}.")
    if missing:
        _fail(f"Vial snapshot is missing fields: {', '.join(missing)}.")

    definition = _canonical_definition(record["definition"])
    try:
        name = definition["name"]
        matrix = definition["matrix"]
        rows_value = matrix["rows"]
        cols_value = matrix["cols"]
    except (KeyError, TypeError):
        _fail("The Vial definition must name the board and declare its matrix.")
    if not isinstance(name, str) or not name.strip():
        _fail("The Vial definition name must be non-empty text.")
    rows = _integer(rows_value, "Vial definition matrix rows", low=1, high=32)
    cols = _integer(cols_value, "Vial definition matrix columns", low=1, high=32)
    if rows * cols > _MAX_KEYS_PER_LAYER:
        _fail(
            f"The Vial definition matrix has {rows * cols} cells; "
            f"the hub supports at most {_MAX_KEYS_PER_LAYER}."
        )
    key_layout = hid_transport.project_key_layout(definition)
    if not key_layout:
        _fail("The Vial definition layout is missing or cannot be interpreted safely.")

    via_protocol = _integer(record["via_protocol"], "VIA protocol", low=1, high=255)
    if via_protocol != 9:
        _fail(
            f"VIA protocol {via_protocol} is not supported by the Vial spoke; "
            "the surveyed Vial protocol uses VIA protocol 9."
        )
    vial_protocol = _integer(record["vial_protocol"], "Vial protocol", low=0, high=6)
    firmware_uid = record["firmware_uid"]
    if not isinstance(firmware_uid, str) or not _UID_RE.fullmatch(firmware_uid):
        _fail("The Vial firmware UID must be exactly 16 hexadecimal characters.")

    layer_count = _integer(
        record["layer_count"], "Vial layer count", low=1, high=_MAX_LAYERS
    )
    keymap_buffer = _hex_bytes(record["keymap_hex"], "Vial keymap buffer")
    expected_keymap = layer_count * rows * cols * 2
    if len(keymap_buffer) != expected_keymap:
        _fail(
            f"The Vial keymap buffer is {len(keymap_buffer)} bytes; "
            f"{layer_count} layers of a {rows}x{cols} matrix require {expected_keymap}."
        )

    macro_count = _integer(
        record["macro_count"], "Vial macro count", low=0, high=_MAX_MACROS
    )
    macro_buffer_bytes = _integer(
        record["macro_buffer_bytes"],
        "Vial macro buffer size",
        low=macro_count,
        high=_MAX_MACRO_BUFFER,
    )
    macro_buffer = _hex_bytes(record["macro_hex"], "Vial macro buffer")
    if len(macro_buffer) != macro_buffer_bytes:
        _fail(
            f"The Vial macro buffer is {len(macro_buffer)} bytes; "
            f"the device reported {macro_buffer_bytes}."
        )

    return VialSnapshot(
        definition=definition,
        definition_hash=hid_transport.definition_fingerprint(definition),
        name=name.strip(),
        matrix_rows=rows,
        matrix_cols=cols,
        key_layout=tuple(copy.deepcopy(key_layout)),
        via_protocol=via_protocol,
        vial_protocol=vial_protocol,
        firmware_uid=firmware_uid.lower(),
        usb_vendor_id=_integer(
            record["usb_vendor_id"], "USB vendor ID", low=0, high=0xFFFF
        ),
        usb_product_id=_integer(
            record["usb_product_id"], "USB product ID", low=0, high=0xFFFF
        ),
        layer_count=layer_count,
        keymap_buffer=keymap_buffer,
        macro_count=macro_count,
        macro_buffer_bytes=macro_buffer_bytes,
        macro_buffer=macro_buffer,
    )


def _matrix_key(row: int, col: int) -> str:
    return f"K_R{row}_C{col}"


def _matrix_position(identity: str, snapshot: VialSnapshot) -> tuple[int, int] | None:
    matched = _MATRIX_KEY_RE.fullmatch(identity)
    if matched is None:
        return None
    row, col = (int(part) for part in matched.groups())
    if row >= snapshot.matrix_rows or col >= snapshot.matrix_cols:
        return None
    return row, col


def _definition_identity(snapshot: VialSnapshot) -> dict[str, Any]:
    return {
        "ecosystem": "vial",
        "family": snapshot.name,
        "wire_identity": snapshot.firmware_uid,
        "endpoint": {
            "vid": snapshot.usb_vendor_id,
            "pid": snapshot.usb_product_id,
            "transport": "hid",
        },
        "protocol": {
            "via_protocol": snapshot.via_protocol,
            "vial_protocol": snapshot.vial_protocol,
        },
        "definition": {"source": "device", "hash": snapshot.definition_hash},
    }


def _decode_keymap(snapshot: VialSnapshot) -> list[list[int]]:
    layers = vial_keymap.decode_layers(
        snapshot.keymap_buffer,
        layers=snapshot.layer_count,
        keys_per_layer=snapshot.keys_per_layer,
        vial_protocol=snapshot.vial_protocol,
    )
    return [
        [
            vial_keymap.to_qmk(code, vial_protocol=snapshot.vial_protocol)
            for code in layer
        ]
        for layer in layers
    ]


_BASIC_ACTIONS = {
    "tap": vial_macros.SS_TAP,
    "down": vial_macros.SS_DOWN,
    "up": vial_macros.SS_UP,
}
_EXTENDED_ACTIONS = {"tap": 0x05, "down": 0x06, "up": 0x07}
_ACTION_EVENTS = {value: key for key, value in _BASIC_ACTIONS.items()} | {
    value: key for key, value in _EXTENDED_ACTIONS.items()
}


def _encode_delay(milliseconds: int) -> bytes:
    if not 0 <= milliseconds <= vial_macros.MAX_DELAY_MS:
        _fail(
            f"A Vial macro delay must be 0..{vial_macros.MAX_DELAY_MS} milliseconds."
        )
    high, low = divmod(milliseconds, 255)
    return bytes([vial_macros.SS_PREFIX, vial_macros.SS_DELAY, low + 1, high + 1])


def _decode_delay(low: int, high: int, *, slot: int) -> int:
    if low == 0 or high == 0:
        _fail(f"Vial macro slot {slot} contains a truncated delay.")
    return (low - 1) + (high - 1) * 255


def _encode_macro_key(kind: str, code: object, *, vial_protocol: int) -> bytes:
    value = _integer(code, f"Vial macro {kind} keycode", low=1, high=0xFFFF)
    if value <= 0xFF:
        if vial_protocol < 2:
            return bytes([_BASIC_ACTIONS[kind], value])
        return bytes([vial_macros.SS_PREFIX, _BASIC_ACTIONS[kind], value])
    if vial_protocol < 5:
        _fail(
            f"Vial protocol {vial_protocol} cannot store 16-bit macro keycode "
            f"0x{value:04X}; protocol 5 or newer is required."
        )
    if value & 0xFF00 == 0xFF00 and value & 0xFF:
        _fail(
            f"Vial's 0xFF macro escape makes keycode 0x{value:04X} ambiguous; "
            "it cannot be written losslessly."
        )
    stored = value
    if value & 0xFF == 0:
        stored = 0xFF00 | (value >> 8)
    return bytes(
        [vial_macros.SS_PREFIX, _EXTENDED_ACTIONS[kind]]
    ) + stored.to_bytes(2, "little")


def encode_macro_events(events: list[dict[str, Any]], *, vial_protocol: int) -> bytes:
    """Encode normalized hub macro events without a slot terminator."""

    _integer(vial_protocol, "Vial protocol", low=0, high=6)
    if not isinstance(events, list):
        _fail("Vial macro events must be a list.")
    payload = bytearray()
    for index, event in enumerate(events):
        if not isinstance(event, dict) or len(event) != 1:
            _fail(f"Vial macro event {index} must contain exactly one action.")
        kind, value = next(iter(event.items()))
        if kind in _BASIC_ACTIONS:
            payload += _encode_macro_key(kind, value, vial_protocol=vial_protocol)
        elif kind == "delay_ms":
            if not isinstance(value, int) or isinstance(value, bool):
                _fail(f"Vial macro event {index} delay must be an integer.")
            if vial_protocol < 2:
                _fail(
                    f"Vial protocol {vial_protocol} cannot store macro delays; "
                    "protocol 2 or newer is required."
                )
            payload += _encode_delay(value)
        elif kind == "text":
            if not isinstance(value, str) or not value:
                _fail(f"Vial macro event {index} text must be non-empty.")
            encoded = value.encode("utf-8")
            reserved = {0}
            if vial_protocol < 2:
                reserved.update(_BASIC_ACTIONS.values())
            else:
                reserved.add(vial_macros.SS_PREFIX)
            if any(byte in reserved for byte in encoded):
                _fail(
                    f"Vial macro event {index} text contains a reserved control byte."
                )
            payload += encoded
        else:
            _fail(f"Vial macro event {index} has unknown action {kind!r}.")
    return bytes(payload)


def decode_macro_events(
    payload: bytes, *, vial_protocol: int, slot: int
) -> list[dict[str, Any]]:
    """Decode one Vial macro payload (without its NUL terminator)."""

    _integer(vial_protocol, "Vial protocol", low=0, high=6)
    events: list[dict[str, Any]] = []
    position = 0
    literal = bytearray()

    def flush_literal() -> None:
        if not literal:
            return
        try:
            text = literal.decode("utf-8")
        except UnicodeDecodeError as error:
            raise VialSpokeError(
                f"Vial macro slot {slot} contains text that is not UTF-8."
            ) from error
        events.append({"text": text})
        literal.clear()

    if vial_protocol < 2:
        while position < len(payload):
            action = payload[position]
            kind = _ACTION_EVENTS.get(action)
            if action in _BASIC_ACTIONS.values() and kind is not None:
                flush_literal()
                if position + 1 >= len(payload) or payload[position + 1] == 0:
                    _fail(f"Vial macro slot {slot} ends inside a key action.")
                events.append({kind: payload[position + 1]})
                position += 2
                continue
            literal.append(action)
            position += 1
        flush_literal()
        return events

    while position < len(payload):
        if payload[position] != vial_macros.SS_PREFIX:
            literal.append(payload[position])
            position += 1
            continue
        flush_literal()
        if position + 1 >= len(payload):
            _fail(f"Vial macro slot {slot} ends inside an action prefix.")
        action = payload[position + 1]
        if action == vial_macros.SS_DELAY:
            if position + 3 >= len(payload):
                _fail(f"Vial macro slot {slot} ends inside a delay.")
            events.append(
                {
                    "delay_ms": _decode_delay(
                        payload[position + 2], payload[position + 3], slot=slot
                    )
                }
            )
            position += 4
            continue
        kind = _ACTION_EVENTS.get(action)
        if kind is None:
            _fail(f"Vial macro slot {slot} contains unknown action 0x{action:02X}.")
        if action in _BASIC_ACTIONS.values():
            if position + 2 >= len(payload) or payload[position + 2] == 0:
                _fail(f"Vial macro slot {slot} ends inside a key action.")
            code = payload[position + 2]
            position += 3
        else:
            if vial_protocol < 5:
                _fail(
                    f"Vial macro slot {slot} uses a 16-bit action unavailable before "
                    "Vial protocol 5."
                )
            if position + 3 >= len(payload):
                _fail(f"Vial macro slot {slot} ends inside a 16-bit key action.")
            stored = int.from_bytes(payload[position + 2 : position + 4], "little")
            if stored & 0xFF00 == 0xFF00:
                code = (stored & 0xFF) << 8
            else:
                code = stored
            if code == 0:
                _fail(f"Vial macro slot {slot} contains an empty key action.")
            position += 4
        events.append({kind: code})
    flush_literal()
    return events


def decode_macro_buffer(
    buffer: bytes, *, count: int, vial_protocol: int
) -> list[dict[str, Any]]:
    """Decode all non-empty slots from a NUL-separated Vial macro buffer."""

    position = 0
    macros: list[dict[str, Any]] = []
    for slot in range(count):
        terminator = buffer.find(b"\x00", position)
        if terminator < 0:
            _fail(f"The Vial macro buffer ends before slot {slot}'s terminator.")
        payload = buffer[position:terminator]
        events = decode_macro_events(payload, vial_protocol=vial_protocol, slot=slot)
        if events:
            macros.append({"slot": slot, "events": events})
        position = terminator + 1
    return macros


def encode_macro_buffer(
    macros: list[dict[str, Any]],
    *,
    count: int,
    buffer_bytes: int,
    vial_protocol: int,
) -> bytes:
    """Compile and size-check a complete replacement buffer before any write."""

    table: list[list[dict[str, Any]] | None] = [None] * count
    for position, macro in enumerate(macros):
        if not isinstance(macro, dict):
            _fail(f"Hub macro {position} must be an object.")
        slot = _integer(macro.get("slot"), f"Hub macro {position} slot", low=0, high=count - 1)
        if table[slot] is not None:
            _fail(f"Hub macros assign Vial slot {slot} more than once.")
        events = macro.get("events")
        if not isinstance(events, list):
            _fail(f"Hub macro slot {slot} events must be a list.")
        table[slot] = events

    payload = bytearray()
    for events in table:
        if events is not None:
            payload += encode_macro_events(events, vial_protocol=vial_protocol)
        payload.append(vial_macros.MACRO_TERMINATOR)
    if len(payload) > buffer_bytes:
        _fail(
            f"These macros compile to {len(payload)} bytes but the Vial keyboard "
            f"stores {buffer_bytes}. Nothing was written."
        )
    return bytes(payload).ljust(buffer_bytes, b"\x00")


def build_hub_profile(
    snapshot: VialSnapshot, *, origin: str = "device"
) -> dict[str, Any]:
    """Express one validated Vial snapshot as a hub profile."""

    if origin not in ("device", "user"):
        _fail("The Vial profile origin must be 'device' or 'user'.")
    layers = _decode_keymap(snapshot)
    matrix_map = {
        _matrix_key(row, col): [row, col]
        for row in range(snapshot.matrix_rows)
        for col in range(snapshot.matrix_cols)
    }
    profile = {
        "schema_version": HUB_SCHEMA_VERSION,
        "identity": _definition_identity(snapshot),
        "capabilities": {
            "keymap": {
                "layers": snapshot.layer_count,
                "keys_per_layer": snapshot.keys_per_layer,
            },
            "macros": {
                "budget": {
                    "model": "bytes",
                    "slots": snapshot.macro_count,
                    "buffer_bytes": snapshot.macro_buffer_bytes,
                },
                "delays": snapshot.vial_protocol >= 2,
            },
        },
        "keymap": {
            "layers": [
                {
                    "index": index,
                    "keys": [
                        {
                            "key": _matrix_key(flat // snapshot.matrix_cols, flat % snapshot.matrix_cols),
                            "code": code,
                        }
                        for flat, code in enumerate(layer)
                    ],
                }
                for index, layer in enumerate(layers)
            ],
            "matrix": {
                "rows": snapshot.matrix_rows,
                "cols": snapshot.matrix_cols,
                "map": matrix_map,
            },
        },
        "macros": decode_macro_buffer(
            snapshot.macro_buffer,
            count=snapshot.macro_count,
            vial_protocol=snapshot.vial_protocol,
        ),
        "provenance": {
            "/identity": "device",
            "/capabilities": "device",
            "/keymap": origin,
            "/macros": origin,
        },
    }
    return validate_hub_profile(profile)


class _Report:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def carried(self, path: str) -> None:
        self.items.append({"path": path, "verdict": "carried"})

    def adapted(self, path: str, reason: str) -> None:
        self.items.append({"path": path, "verdict": "adapted", "reason": reason})

    def dropped(self, path: str, reason: str) -> None:
        self.items.append({"path": path, "verdict": "dropped", "reason": reason})


def _source_vial_protocol(profile: dict[str, Any]) -> int:
    identity = profile["identity"]
    if identity["ecosystem"] != "vial":
        return vial_keymap.DEFAULT_VIAL_PROTOCOL
    return int((identity.get("protocol") or {}).get("vial_protocol", 6))


def _adapt_keycode(code: int, *, source_protocol: int, target_protocol: int) -> int:
    portable = vial_keymap.from_qmk(code, vial_protocol=source_protocol)
    return vial_keymap.to_qmk(portable, vial_protocol=target_protocol)


def _plan_keymap(
    profile: dict[str, Any], target: VialSnapshot, report: _Report
) -> bytes | None:
    keymap = profile.get("keymap")
    if keymap is None:
        return None
    target_layers = _decode_keymap(target)
    source_protocol = _source_vial_protocol(profile)
    for layer in keymap["layers"]:
        layer_index = layer["index"]
        for entry in layer["keys"]:
            identity = entry["key"]
            path = f"keymap.layers[{layer_index}].keys[{identity}]"
            if layer_index >= target.layer_count:
                report.dropped(path, f"this Vial keyboard has only {target.layer_count} layers.")
                continue
            matrix = _matrix_position(identity, target)
            if matrix is None:
                report.dropped(
                    path,
                    "this key has no Vial matrix address; the H4 overlay must assign one.",
                )
                continue
            row, col = matrix
            flat = row * target.matrix_cols + col
            try:
                code = _adapt_keycode(
                    entry["code"],
                    source_protocol=source_protocol,
                    target_protocol=target.vial_protocol,
                )
            except (ValueError, vial_keymap.UnsupportedVialProtocol) as error:
                report.dropped(path, f"the target Vial keycode map cannot express it: {error}")
                continue
            target_layers[layer_index][flat] = code
            if code == entry["code"]:
                report.carried(path)
            else:
                report.adapted(
                    path,
                    f"Vial protocol {target.vial_protocol} uses a different macro trigger value.",
                )
    return b"".join(code.to_bytes(2, "big") for layer in target_layers for code in layer)


def _plan_macros(
    profile: dict[str, Any], target: VialSnapshot, report: _Report
) -> bytes | None:
    macros = profile.get("macros")
    if macros is None:
        return None
    carried: list[dict[str, Any]] = []
    for macro in macros:
        slot = macro["slot"]
        path = f"macros[{slot}]"
        if slot >= target.macro_count:
            report.dropped(
                path,
                f"this Vial keyboard stores {target.macro_count} macro slots.",
            )
            continue
        try:
            encode_macro_events(macro["events"], vial_protocol=target.vial_protocol)
        except VialSpokeError as error:
            report.dropped(path, str(error))
            continue
        carried.append(macro)
        report.carried(path)
    return encode_macro_buffer(
        carried,
        count=target.macro_count,
        buffer_bytes=target.macro_buffer_bytes,
        vial_protocol=target.vial_protocol,
    )


def plan_vial_write(
    profile: dict[str, Any], *, target: VialSnapshot
) -> VialWritePlan:
    """Build complete Vial replacement buffers; never open or write a device."""

    validated = validate_hub_profile(profile)
    report = _Report()
    keymap_buffer = _plan_keymap(validated, target, report)
    macro_buffer = _plan_macros(validated, target, report)
    transfer_report = validate_transfer_report(
        {
            "source": validated["identity"],
            "target": _definition_identity(target),
            "items": report.items,
        }
    )
    return VialWritePlan(
        keymap_buffer=keymap_buffer,
        macro_buffer=macro_buffer,
        report=transfer_report,
    )
