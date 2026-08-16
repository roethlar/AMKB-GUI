"""Pure definition-backed VIA spoke for OpenKeeb's hub profile.

VIA firmware does not embed its physical definition.  H3 therefore accepts a
user-imported definition, validates and fingerprints it, reads the active
layout-option bitfield from the keyboard, and only then projects one physical
layout.  The snapshot and pure write-plan seams own no HID session and cannot
write hardware.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import math
import re
from typing import Any

from . import hid_transport, vial_macros
from .hub_profile import (
    HUB_SCHEMA_VERSION,
    validate_hub_profile,
    validate_transfer_report,
)


class ViaSpokeError(ValueError):
    """A VIA definition or snapshot cannot be represented safely."""


@dataclass(frozen=True)
class _PhysicalKey:
    row: int
    col: int
    group: int
    option: int
    x: float
    y: float
    width: float
    height: float
    rotation: float
    rotation_x: float
    rotation_y: float


@dataclass(frozen=True)
class ViaDefinition:
    """Bounded user-imported VIA definition plus parsed layout alternatives."""

    definition: dict[str, Any]
    definition_hash: str
    name: str
    usb_vendor_id: int
    usb_product_id: int
    matrix_rows: int
    matrix_cols: int
    choice_counts: tuple[int, ...]
    physical_keys: tuple[_PhysicalKey, ...]

    @property
    def keys_per_layer(self) -> int:
        return self.matrix_rows * self.matrix_cols


@dataclass(frozen=True)
class ViaSnapshot:
    """One complete read-only VIA result, independent of a HID session."""

    definition: dict[str, Any]
    definition_hash: str
    name: str
    matrix_rows: int
    matrix_cols: int
    key_layout: tuple[dict[str, int | float], ...]
    via_protocol: int
    keycode_spec: str | None
    usb_vendor_id: int
    usb_product_id: int
    layout_options: int
    layer_count: int
    keymap_buffer: bytes
    macro_count: int
    macro_buffer_bytes: int
    macro_buffer: bytes

    @property
    def keys_per_layer(self) -> int:
        return self.matrix_rows * self.matrix_cols


@dataclass(frozen=True)
class ViaWritePlan:
    """Complete replacement buffers and report; never writes hardware."""

    keymap_buffer: bytes | None
    macro_buffer: bytes | None
    report: dict[str, Any]


_MAX_DEFINITION_BYTES = 1_048_576
_MAX_MATRIX_AXIS = 32
_MAX_KEYS_PER_LAYER = 512
_MAX_LAYOUT_ENTRIES = 2_048
_MAX_LAYOUT_GROUPS = 32
_MAX_LAYOUT_CHOICES = 32
_MAX_LAYERS = 32
_MAX_MACROS = 128
_MAX_MACRO_BUFFER = 65_535
_PAIR_RE = re.compile(r"^([0-9]+)[,，]([0-9]+)$")
_MATRIX_KEY_RE = re.compile(r"^K_R([0-9]+)_C([0-9]+)$")

# KLE's raw newline labels move when the alignment property changes.  Matrix
# row/column lives in normalized legend 0 and VIA's layout group/option lives
# in normalized legend 8.  This is the table used by @the-via/reader.
_KLE_ALIGNMENT = (
    (0, 6, 2, 8, 9, 11, 3, 5, 1, 4, 7, 10),
    (1, 7, -1, -1, 9, 11, 4, -1, -1, -1, -1, 10),
    (3, -1, 5, -1, 9, 11, -1, -1, 4, -1, -1, 10),
    (4, -1, -1, -1, 9, 11, -1, -1, -1, -1, -1, 10),
    (0, 6, 2, 8, 10, -1, 3, 5, 1, 4, 7, -1),
    (1, 7, -1, -1, 10, -1, 4, -1, -1, -1, -1, -1),
    (3, -1, 5, -1, 9, 11, -1, -1, 4, -1, -1, -1),
    (4, -1, -1, -1, 9, 11, -1, -1, -1, -1, -1, -1),
)


def _fail(message: str) -> None:
    raise ViaSpokeError(message)


def _integer(value: object, label: str, *, low: int, high: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not low <= value <= high
    ):
        _fail(f"{label} must be an integer in {low}..{high}.")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be a finite number.")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        _fail(f"{label} must be a finite{' positive' if positive else ''} number.")
    return result


def _usb_id(value: object, label: str) -> int:
    if isinstance(value, str) and re.fullmatch(r"0[xX][0-9a-fA-F]{1,4}", value):
        return int(value, 16)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFFFF:
        return value
    _fail(f"VIA {label} must be a 16-bit integer or hexadecimal string.")


def _canonical_definition(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("The VIA definition must be a JSON object.")
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        canonical = json.loads(encoded)
    except (TypeError, ValueError, UnicodeError) as error:
        raise ViaSpokeError("The VIA definition is not canonical JSON.") from error
    if len(encoded) > _MAX_DEFINITION_BYTES:
        _fail(
            f"The VIA definition is larger than {_MAX_DEFINITION_BYTES} bytes."
        )
    return canonical


def _pair(value: str, label: str) -> tuple[int, int]:
    matched = _PAIR_RE.fullmatch(value.strip())
    if matched is None:
        _fail(f"{label} must be a row,column pair.")
    return int(matched.group(1)), int(matched.group(2))


def _normalized_labels(value: str, alignment: int) -> list[str]:
    normalized = [""] * 12
    for index, label in enumerate(value.split("\n")[:12]):
        destination = _KLE_ALIGNMENT[alignment][index]
        if destination >= 0:
            normalized[destination] = label.strip()
    return normalized


def _choice_counts(labels: object) -> tuple[int, ...]:
    if labels is None:
        return ()
    if not isinstance(labels, list) or len(labels) > _MAX_LAYOUT_GROUPS:
        _fail(
            f"VIA layouts.labels must be a list with at most {_MAX_LAYOUT_GROUPS} groups."
        )
    counts: list[int] = []
    for index, label in enumerate(labels):
        if isinstance(label, str) and label:
            counts.append(2)
        elif (
            isinstance(label, list)
            and 2 <= len(label) <= _MAX_LAYOUT_CHOICES + 1
            and all(isinstance(item, str) and item for item in label)
        ):
            counts.append(len(label) - 1)
        else:
            _fail(
                f"VIA layout label {index} must be text or a label plus choices."
            )
    return tuple(counts)


def _parse_layout(
    keymap: object,
    *,
    rows: int,
    cols: int,
    choice_counts: tuple[int, ...],
) -> tuple[_PhysicalKey, ...]:
    if not isinstance(keymap, list) or not keymap:
        _fail("VIA layouts.keymap must be a non-empty KLE row list.")
    if len(keymap) > _MAX_LAYOUT_ENTRIES:
        _fail("The VIA layout has too many rows.")

    result: list[_PhysicalKey] = []
    total_entries = 0
    cursor_y = -1.0
    previous = {
        "rotation": 0.0,
        "rotation_x": 0.0,
        "rotation_y": 0.0,
        "alignment": 0,
    }
    for row_index, physical_row in enumerate(keymap):
        if not isinstance(physical_row, list):
            _fail(f"VIA layout row {row_index} must be a list.")
        total_entries += len(physical_row)
        if total_entries > _MAX_LAYOUT_ENTRIES:
            _fail(f"The VIA layout exceeds {_MAX_LAYOUT_ENTRIES} entries.")
        cursor_x = 0.0
        cursor_y += 1.0
        width = 1.0
        height = 1.0
        rotation = previous["rotation"]
        rotation_x = previous["rotation_x"]
        rotation_y = previous["rotation_y"]
        alignment = int(previous["alignment"])
        decal = False

        for entry_index, entry in enumerate(physical_row):
            label = f"VIA layout row {row_index} entry {entry_index}"
            if isinstance(entry, dict):
                if "rx" in entry:
                    rotation_x = _number(entry["rx"], f"{label}.rx")
                if "ry" in entry:
                    rotation_y = _number(entry["ry"], f"{label}.ry")
                if "rx" in entry or "ry" in entry:
                    cursor_y = rotation_y
                    cursor_x = 0.0
                if "x" in entry:
                    cursor_x += _number(entry["x"], f"{label}.x")
                if "y" in entry:
                    cursor_y += _number(entry["y"], f"{label}.y")
                if "w" in entry:
                    width = _number(entry["w"], f"{label}.w", positive=True)
                if "h" in entry:
                    height = _number(entry["h"], f"{label}.h", positive=True)
                if "r" in entry:
                    rotation = _number(entry["r"], f"{label}.r")
                if "a" in entry:
                    alignment = _integer(entry["a"], f"{label}.a", low=0, high=7)
                if "d" in entry:
                    if not isinstance(entry["d"], bool):
                        _fail(f"{label}.d must be true or false.")
                    decal = entry["d"]
                continue
            if not isinstance(entry, str):
                _fail(f"{label} must be a KLE property object or key label.")

            labels = _normalized_labels(entry, alignment)
            if not decal and labels[0]:
                matrix_row, matrix_col = _pair(labels[0], f"{label} matrix")
                if matrix_row >= rows or matrix_col >= cols:
                    _fail(
                        f"{label} matrix position {matrix_row},{matrix_col} "
                        "falls outside the declared matrix."
                    )
                group = -1
                option = 0
                if labels[8]:
                    group, option = _pair(labels[8], f"{label} layout option")
                    if group >= len(choice_counts):
                        _fail(f"{label} references undeclared layout group {group}.")
                    if option >= choice_counts[group]:
                        _fail(
                            f"{label} references unavailable option {option} "
                            f"for layout group {group}."
                        )
                result.append(
                    _PhysicalKey(
                        row=matrix_row,
                        col=matrix_col,
                        group=group,
                        option=option,
                        x=cursor_x + rotation_x,
                        y=cursor_y,
                        width=width,
                        height=height,
                        rotation=rotation,
                        rotation_x=rotation_x,
                        rotation_y=rotation_y,
                    )
                )
            cursor_x += width
            width = 1.0
            height = 1.0
            decal = False

        previous = {
            "rotation": rotation,
            "rotation_x": rotation_x,
            "rotation_y": rotation_y,
            "alignment": alignment,
        }

    if not result:
        _fail("The VIA definition has no matrix-backed physical keys.")
    return tuple(result)


def load_definition(value: object) -> ViaDefinition:
    """Validate a user-supplied VIA definition into a bounded immutable seam."""

    definition = _canonical_definition(value)
    name = definition.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
        _fail("VIA definition name must be 1..128 characters of text.")

    if "vendorId" in definition or "productId" in definition:
        if "vendorId" not in definition or "productId" not in definition:
            _fail("VIA definition must contain both vendorId and productId.")
        vendor_id = _usb_id(definition["vendorId"], "vendorId")
        product_id = _usb_id(definition["productId"], "productId")
    else:
        combined = definition.get("vendorProductId")
        combined = _integer(
            combined, "VIA vendorProductId", low=0, high=0xFFFFFFFF
        )
        vendor_id = (combined >> 16) & 0xFFFF
        product_id = combined & 0xFFFF

    try:
        matrix = definition["matrix"]
        layouts = definition["layouts"]
        rows_value = matrix["rows"]
        cols_value = matrix["cols"]
        keymap = layouts["keymap"]
    except (KeyError, TypeError) as error:
        raise ViaSpokeError(
            "VIA definition must contain matrix rows/columns and layouts.keymap."
        ) from error
    rows = _integer(rows_value, "VIA matrix rows", low=1, high=_MAX_MATRIX_AXIS)
    cols = _integer(cols_value, "VIA matrix columns", low=1, high=_MAX_MATRIX_AXIS)
    if rows * cols > _MAX_KEYS_PER_LAYER:
        _fail(
            f"The VIA matrix has {rows * cols} cells; "
            f"the hub supports at most {_MAX_KEYS_PER_LAYER}."
        )
    if not isinstance(layouts, dict):
        _fail("VIA layouts must be a JSON object.")
    choices = _choice_counts(layouts.get("labels"))
    keys = _parse_layout(
        keymap, rows=rows, cols=cols, choice_counts=choices
    )
    return ViaDefinition(
        definition=definition,
        definition_hash=hid_transport.definition_fingerprint(definition),
        name=name.strip(),
        usb_vendor_id=vendor_id,
        usb_product_id=product_id,
        matrix_rows=rows,
        matrix_cols=cols,
        choice_counts=choices,
        physical_keys=keys,
    )


def _bit_width(choice_count: int) -> int:
    return max(1, (choice_count - 1).bit_length())


def unpack_layout_options(packed: int, choices: tuple[int, ...]) -> tuple[int, ...]:
    """Decode VIA's packed 32-bit layout choices without inventing defaults."""

    _integer(packed, "VIA layout options", low=0, high=0xFFFFFFFF)
    remaining = packed
    selected: list[int] = []
    for count in reversed(choices):
        width = _bit_width(count)
        selected.insert(0, remaining & ((1 << width) - 1))
        remaining >>= width
    if remaining:
        _fail("VIA layout options contain bits absent from the imported definition.")
    for index, (choice, count) in enumerate(zip(selected, choices)):
        if choice >= count:
            _fail(
                f"VIA layout group {index} reports option {choice}, "
                f"but the definition has {count} choices."
            )
    return tuple(selected)


def _rotated_bounds(key: _PhysicalKey) -> tuple[float, float, float, float]:
    radians = math.radians(key.rotation)
    sine = math.sin(radians)
    cosine = math.cos(radians)
    points = []
    for x, y in (
        (key.x, key.y),
        (key.x + key.width, key.y),
        (key.x, key.y + key.height),
        (key.x + key.width, key.y + key.height),
    ):
        relative_x = x - key.rotation_x
        relative_y = y - key.rotation_y
        points.append(
            (
                key.rotation_x + relative_x * cosine - relative_y * sine,
                key.rotation_y + relative_x * sine + relative_y * cosine,
            )
        )
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def project_layout(
    definition: ViaDefinition, packed_options: int
) -> tuple[dict[str, int | float], ...]:
    """Select and normalize the physical layout reported by the keyboard."""

    selected = unpack_layout_options(packed_options, definition.choice_counts)
    keys = [
        key
        for key in definition.physical_keys
        if key.group < 0 or selected[key.group] == key.option
    ]
    seen: set[tuple[int, int]] = set()
    for key in keys:
        position = (key.row, key.col)
        if position in seen:
            _fail(
                f"The selected VIA layout maps matrix position {key.row},{key.col} twice."
            )
        seen.add(position)
    if not keys or len(keys) > _MAX_KEYS_PER_LAYER:
        _fail("The selected VIA layout has an unsupported physical-key count.")

    bounds = [_rotated_bounds(key) for key in keys]
    min_x = min(bound[0] for bound in bounds)
    min_y = min(bound[1] for bound in bounds)
    max_x = max(bound[2] for bound in bounds)
    max_y = max(bound[3] for bound in bounds)
    extent_x = max_x - min_x
    extent_y = max_y - min_y
    if extent_x <= 0 or extent_y <= 0:
        _fail("The selected VIA layout has no finite physical extent.")
    return tuple(
        {
            "matrix_row": key.row,
            "matrix_col": key.col,
            "x": round((key.x - min_x) / extent_x * 95.0, 4),
            "y": round((key.y - min_y) / extent_y * 86.0, 4),
            "width": round(key.width / extent_x * 95.0, 4),
            "height": round(key.height / extent_y * 86.0, 4),
            "rotation": round(key.rotation, 4),
        }
        for key in keys
    )


_SNAPSHOT_FIELDS = {
    "definition",
    "via_protocol",
    "keycode_spec",
    "usb_vendor_id",
    "usb_product_id",
    "layout_options",
    "layer_count",
    "keymap_hex",
    "macro_count",
    "macro_buffer_bytes",
    "macro_hex",
}


def _hex_bytes(value: object, label: str) -> bytes:
    if not isinstance(value, str):
        _fail(f"{label} must be a hexadecimal string.")
    try:
        return bytes.fromhex(value)
    except ValueError as error:
        raise ViaSpokeError(f"{label} must be a hexadecimal string.") from error


def load_snapshot(value: object) -> ViaSnapshot:
    """Validate one complete read-only VIA discovery record."""

    if not isinstance(value, dict):
        _fail("VIA snapshot must be a JSON object.")
    unknown = sorted(set(value) - _SNAPSHOT_FIELDS)
    missing = sorted(_SNAPSHOT_FIELDS - set(value))
    if unknown:
        _fail(f"VIA snapshot has unknown fields: {', '.join(unknown)}.")
    if missing:
        _fail(f"VIA snapshot is missing fields: {', '.join(missing)}.")

    definition = load_definition(value["definition"])
    via_protocol = _integer(
        value["via_protocol"], "VIA protocol", low=7, high=255
    )
    vendor_id = _integer(
        value["usb_vendor_id"], "VIA USB vendor id", low=0, high=0xFFFF
    )
    product_id = _integer(
        value["usb_product_id"], "VIA USB product id", low=0, high=0xFFFF
    )
    if (vendor_id, product_id) != (
        definition.usb_vendor_id,
        definition.usb_product_id,
    ):
        _fail("The VIA definition does not match the snapshot USB VID/PID.")
    keycode_spec = value["keycode_spec"]
    if keycode_spec is not None and (
        not isinstance(keycode_spec, str) or not 1 <= len(keycode_spec) <= 16
    ):
        _fail("VIA keycode spec must be null or 1..16 characters of text.")
    if via_protocol >= 13 and keycode_spec is None:
        _fail("VIA protocol 13 or newer must report its QMK keycode spec.")
    if via_protocol < 13 and keycode_spec is not None:
        _fail("VIA protocols before 13 imply their keycode map and report no spec.")

    layout_options = _integer(
        value["layout_options"], "VIA layout options", low=0, high=0xFFFFFFFF
    )
    key_layout = project_layout(definition, layout_options)
    layer_count = _integer(
        value["layer_count"], "VIA layer count", low=1, high=_MAX_LAYERS
    )
    keymap_buffer = _hex_bytes(value["keymap_hex"], "VIA keymap buffer")
    expected_keymap = layer_count * definition.keys_per_layer * 2
    if len(keymap_buffer) != expected_keymap:
        _fail(
            f"The VIA keymap buffer has {len(keymap_buffer)} bytes; "
            f"{expected_keymap} expected."
        )

    macro_count = _integer(
        value["macro_count"], "VIA macro count", low=0, high=_MAX_MACROS
    )
    macro_buffer_bytes = _integer(
        value["macro_buffer_bytes"],
        "VIA macro buffer size",
        low=0,
        high=_MAX_MACRO_BUFFER,
    )
    macro_buffer = _hex_bytes(value["macro_hex"], "VIA macro buffer")
    if len(macro_buffer) != macro_buffer_bytes:
        _fail(
            f"The VIA macro buffer has {len(macro_buffer)} bytes; "
            f"{macro_buffer_bytes} expected."
        )
    if via_protocol < 8 and (macro_count or macro_buffer_bytes):
        _fail("VIA protocol 7 does not expose dynamic macros.")
    if macro_count > macro_buffer_bytes:
        _fail("The VIA macro buffer cannot hold one terminator per macro slot.")
    decode_macro_buffer(
        macro_buffer, count=macro_count, via_protocol=via_protocol
    )
    return ViaSnapshot(
        definition=copy.deepcopy(definition.definition),
        definition_hash=definition.definition_hash,
        name=definition.name,
        matrix_rows=definition.matrix_rows,
        matrix_cols=definition.matrix_cols,
        key_layout=key_layout,
        via_protocol=via_protocol,
        keycode_spec=keycode_spec,
        usb_vendor_id=vendor_id,
        usb_product_id=product_id,
        layout_options=layout_options,
        layer_count=layer_count,
        keymap_buffer=keymap_buffer,
        macro_count=macro_count,
        macro_buffer_bytes=macro_buffer_bytes,
        macro_buffer=macro_buffer,
    )


def decode_macro_events(
    payload: bytes, *, via_protocol: int, slot: int
) -> list[dict[str, Any]]:
    """Decode one VIA macro slot, including the protocol-11 delay dialect."""

    events: list[dict[str, Any]] = []
    literal = bytearray()

    def flush_literal() -> None:
        if not literal:
            return
        try:
            text = literal.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ViaSpokeError(
                f"VIA macro slot {slot} contains literal text that is not UTF-8."
            ) from error
        events.append({"text": text})
        literal.clear()

    position = 0
    actions = {1: "tap", 2: "down", 3: "up"}
    if via_protocol < 11:
        while position < len(payload):
            action = payload[position]
            if action not in actions:
                literal.append(action)
                position += 1
                continue
            flush_literal()
            if position + 1 >= len(payload) or payload[position + 1] == 0:
                _fail(f"VIA macro slot {slot} ends inside a key action.")
            events.append({actions[action]: payload[position + 1]})
            position += 2
        flush_literal()
        return events

    while position < len(payload):
        if payload[position] != vial_macros.SS_PREFIX:
            literal.append(payload[position])
            position += 1
            continue
        flush_literal()
        if position + 1 >= len(payload):
            _fail(f"VIA macro slot {slot} ends inside an action prefix.")
        action = payload[position + 1]
        if action in actions:
            if position + 2 >= len(payload) or payload[position + 2] == 0:
                _fail(f"VIA macro slot {slot} ends inside a key action.")
            events.append({actions[action]: payload[position + 2]})
            position += 3
            continue
        if action == vial_macros.SS_DELAY:
            terminator = payload.find(b"|", position + 2)
            if terminator < 0:
                _fail(f"VIA macro slot {slot} has an unterminated delay.")
            digits = payload[position + 2 : terminator]
            if not digits or not all(0x30 <= byte <= 0x39 for byte in digits):
                _fail(f"VIA macro slot {slot} contains a non-decimal delay.")
            delay = int(digits.decode("ascii"))
            if delay > 65_535:
                _fail(f"VIA macro slot {slot} delay exceeds 65,535 ms.")
            events.append({"delay_ms": delay})
            position = terminator + 1
            continue
        _fail(f"VIA macro slot {slot} contains unknown action 0x{action:02X}.")
    flush_literal()
    return events


def decode_macro_buffer(
    buffer: bytes, *, count: int, via_protocol: int
) -> list[dict[str, Any]]:
    """Decode all non-empty slots from a complete VIA macro buffer."""

    _integer(count, "VIA macro count", low=0, high=_MAX_MACROS)
    _integer(via_protocol, "VIA protocol", low=7, high=255)
    position = 0
    macros: list[dict[str, Any]] = []
    for slot in range(count):
        terminator = buffer.find(b"\x00", position)
        if terminator < 0:
            _fail(f"The VIA macro buffer ends before slot {slot}'s terminator.")
        events = decode_macro_events(
            buffer[position:terminator], via_protocol=via_protocol, slot=slot
        )
        if events:
            macros.append({"slot": slot, "events": events})
        position = terminator + 1
    return macros


def _matrix_key(row: int, col: int) -> str:
    return f"K_R{row}_C{col}"


def _decode_keymap(snapshot: ViaSnapshot) -> list[list[int]]:
    values = [
        int.from_bytes(snapshot.keymap_buffer[offset : offset + 2], "big")
        for offset in range(0, len(snapshot.keymap_buffer), 2)
    ]
    return [
        values[
            layer * snapshot.keys_per_layer : (layer + 1) * snapshot.keys_per_layer
        ]
        for layer in range(snapshot.layer_count)
    ]


def _identity(snapshot: ViaSnapshot) -> dict[str, Any]:
    protocol: dict[str, Any] = {"via_protocol": snapshot.via_protocol}
    if snapshot.keycode_spec is not None:
        protocol["keycode_spec"] = snapshot.keycode_spec
    return {
        "ecosystem": "via",
        "family": snapshot.name,
        "wire_identity": (
            f"{snapshot.usb_vendor_id:04X}:{snapshot.usb_product_id:04X}"
        ),
        "endpoint": {
            "vid": snapshot.usb_vendor_id,
            "pid": snapshot.usb_product_id,
            "transport": "hid",
        },
        "protocol": protocol,
        "definition": {
            "source": "user_import",
            "hash": snapshot.definition_hash,
        },
    }


def build_hub_profile(
    snapshot: ViaSnapshot, *, origin: str = "device"
) -> dict[str, Any]:
    """Express one validated VIA snapshot as the common hub profile."""

    if origin not in ("device", "user"):
        _fail("The VIA profile origin must be 'device' or 'user'.")
    layers = _decode_keymap(snapshot)
    matrix_map = {
        _matrix_key(row, col): [row, col]
        for row in range(snapshot.matrix_rows)
        for col in range(snapshot.matrix_cols)
    }
    profile = {
        "schema_version": HUB_SCHEMA_VERSION,
        "identity": _identity(snapshot),
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
                "delays": snapshot.via_protocol >= 11,
            },
        },
        "keymap": {
            "layers": [
                {
                    "index": index,
                    "keys": [
                        {
                            "key": _matrix_key(
                                flat // snapshot.matrix_cols,
                                flat % snapshot.matrix_cols,
                            ),
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
            via_protocol=snapshot.via_protocol,
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

    def dropped(self, path: str, reason: str) -> None:
        self.items.append(
            {"path": path, "verdict": "dropped", "reason": reason}
        )


def _matrix_position(identity: str, target: ViaSnapshot) -> tuple[int, int] | None:
    matched = _MATRIX_KEY_RE.fullmatch(identity)
    if matched is None:
        return None
    row, col = (int(value) for value in matched.groups())
    if row >= target.matrix_rows or col >= target.matrix_cols:
        return None
    return row, col


def _plan_keymap(
    profile: dict[str, Any], target: ViaSnapshot, report: _Report
) -> bytes | None:
    keymap = profile.get("keymap")
    if keymap is None:
        return None

    target_layers = _decode_keymap(target)
    source_spec = (profile["identity"].get("protocol") or {}).get(
        "keycode_spec"
    )
    target_spec = target.keycode_spec
    for layer in keymap["layers"]:
        layer_index = layer["index"]
        for entry in layer["keys"]:
            identity = entry["key"]
            path = f"keymap.layers[{layer_index}].keys[{identity}]"
            if layer_index >= target.layer_count:
                report.dropped(
                    path,
                    f"this VIA keyboard only stores {target.layer_count} layers.",
                )
                continue
            matrix = _matrix_position(identity, target)
            if matrix is None:
                report.dropped(
                    path,
                    "this VIA keyboard has no matrix address for that key; "
                    "H4 overlay must assign one.",
                )
                continue
            if (
                source_spec is not None
                and target_spec is not None
                and source_spec != target_spec
            ):
                report.dropped(
                    path,
                    f"source keycode spec {source_spec} differs from target "
                    f"{target_spec}; no conversion table is available.",
                )
                continue
            row, col = matrix
            target_layers[layer_index][row * target.matrix_cols + col] = entry[
                "code"
            ]
            report.carried(path)

    return b"".join(
        code.to_bytes(2, "big") for layer in target_layers for code in layer
    )


def encode_macro_events(
    events: list[dict[str, Any]], *, via_protocol: int
) -> bytes:
    """Encode normalized hub events into one unterminated VIA macro slot."""

    _integer(via_protocol, "VIA protocol", low=8, high=255)
    if not isinstance(events, list):
        _fail("VIA macro events must be a list.")
    payload = bytearray()
    actions = {"tap": 1, "down": 2, "up": 3}
    for index, event in enumerate(events):
        if not isinstance(event, dict) or len(event) != 1:
            _fail(f"VIA macro event {index} must contain exactly one action.")
        kind, value = next(iter(event.items()))
        if kind in actions:
            code = _integer(
                value,
                f"VIA macro event {index} {kind} keycode",
                low=1,
                high=0xFF,
            )
            if via_protocol < 11:
                payload += bytes([actions[kind], code])
            else:
                payload += bytes([vial_macros.SS_PREFIX, actions[kind], code])
            continue
        if kind == "delay_ms":
            if via_protocol < 11:
                _fail(
                    f"VIA protocol {via_protocol} cannot store macro delays; "
                    "protocol 11 or newer is required."
                )
            delay = _integer(
                value,
                f"VIA macro event {index} delay",
                low=0,
                high=65_535,
            )
            payload += bytes([vial_macros.SS_PREFIX, vial_macros.SS_DELAY])
            payload += str(delay).encode("ascii") + b"|"
            continue
        if kind == "text":
            if not isinstance(value, str) or not value:
                _fail(f"VIA macro event {index} text must be non-empty text.")
            try:
                encoded = value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ViaSpokeError(
                    f"VIA macro event {index} text must be valid UTF-8."
                ) from error
            reserved = {0, 1} if via_protocol >= 11 else {0, 1, 2, 3}
            if any(byte in reserved for byte in encoded):
                _fail(
                    f"VIA macro event {index} text contains a byte reserved "
                    f"by protocol {via_protocol}."
                )
            payload += encoded
            continue
        _fail(f"VIA macro event {index} has unsupported action {kind!r}.")
    return bytes(payload)


def encode_macro_buffer(
    macros: list[dict[str, Any]],
    *,
    count: int,
    buffer_bytes: int,
    via_protocol: int,
) -> bytes:
    """Compile and size-check a complete VIA macro replacement buffer."""

    _integer(via_protocol, "VIA protocol", low=7, high=255)
    count = _integer(count, "VIA macro count", low=0, high=_MAX_MACROS)
    buffer_bytes = _integer(
        buffer_bytes,
        "VIA macro buffer size",
        low=0,
        high=_MAX_MACRO_BUFFER,
    )
    if not isinstance(macros, list):
        _fail("VIA macros must be a list.")
    if via_protocol < 8:
        if macros or count or buffer_bytes:
            _fail("VIA protocol 7 does not expose dynamic macros.")
        return b""
    if count > buffer_bytes:
        _fail("The VIA macro buffer cannot hold one terminator per macro slot.")
    if count == 0 and macros:
        _fail("This VIA keyboard stores no macros.")

    table: list[list[dict[str, Any]] | None] = [None] * count
    for position, macro in enumerate(macros):
        if not isinstance(macro, dict):
            _fail(f"Hub macro {position} must be an object.")
        slot = _integer(
            macro.get("slot"),
            f"Hub macro {position} slot",
            low=0,
            high=count - 1,
        )
        if table[slot] is not None:
            _fail(f"Hub macros assign VIA slot {slot} more than once.")
        events = macro.get("events")
        if not isinstance(events, list):
            _fail(f"Hub macro slot {slot} events must be a list.")
        table[slot] = events

    payload = bytearray()
    for events in table:
        if events is not None:
            payload += encode_macro_events(events, via_protocol=via_protocol)
        payload.append(vial_macros.MACRO_TERMINATOR)
    if len(payload) > buffer_bytes:
        _fail(
            f"These VIA macros compile to {len(payload)} bytes but the keyboard "
            f"stores {buffer_bytes}. Nothing was written."
        )
    return bytes(payload).ljust(buffer_bytes, b"\x00")


def _plan_macros(
    profile: dict[str, Any], target: ViaSnapshot, report: _Report
) -> bytes | None:
    macros = profile.get("macros")
    if macros is None:
        return None
    if target.via_protocol < 8 or target.macro_count == 0:
        for macro in macros:
            report.dropped(
                f"macros[{macro['slot']}]",
                f"VIA protocol {target.via_protocol} exposes no dynamic macros.",
            )
        return None

    carried: list[dict[str, Any]] = []
    for macro in macros:
        slot = macro["slot"]
        path = f"macros[{slot}]"
        if slot >= target.macro_count:
            report.dropped(
                path,
                f"this VIA keyboard stores {target.macro_count} macro slots.",
            )
            continue
        try:
            encode_macro_events(
                macro["events"], via_protocol=target.via_protocol
            )
        except ViaSpokeError as error:
            report.dropped(path, str(error))
            continue
        carried.append(macro)
        report.carried(path)
    return encode_macro_buffer(
        carried,
        count=target.macro_count,
        buffer_bytes=target.macro_buffer_bytes,
        via_protocol=target.via_protocol,
    )


def plan_via_write(
    profile: dict[str, Any], *, target: ViaSnapshot
) -> ViaWritePlan:
    """Build complete VIA replacement buffers without opening a device."""

    validated = validate_hub_profile(profile)
    report = _Report()
    keymap_buffer = _plan_keymap(validated, target, report)
    macro_buffer = _plan_macros(validated, target, report)
    transfer_report = validate_transfer_report(
        {
            "source": validated["identity"],
            "target": _identity(target),
            "items": report.items,
        }
    )
    return ViaWritePlan(
        keymap_buffer=keymap_buffer,
        macro_buffer=macro_buffer,
        report=transfer_report,
    )
