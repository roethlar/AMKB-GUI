"""Canonical Angry Miao device raster and LED-track conversion."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable


MAX_FRAMES = 256
MODEL_FRAME_CAPS = {"CB": 80, "80": 200, "ALICE": 186, "NEON": 256}
LED_SPEEDS_MS = (
    255,
    240,
    224,
    208,
    192,
    176,
    160,
    146,
    132,
    118,
    100,
    90,
    76,
    62,
    48,
    34,
)


@dataclass(frozen=True)
class RasterSpec:
    """One device-owned raster and its firmware frame ceiling."""

    model: str
    target: str
    extra_targets: tuple[str, ...]
    width: int
    height: int
    mapped_positions: tuple[tuple[int, int], ...] | None
    output_len: int
    max_frames: int


# Source-pixel -> firmware-index maps used by Angry Miao's image converters.
_CB_KEY_MAP = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
    15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
    30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
    45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, -1, 58, 59,
    60, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, -1, 72, 73, -1,
    75, 76, 77, 79, -1, 80, -1, -1, 81, 85, 86, -1, 87, 88, 89,
)
# CyberBoard profile JSON stores the 40x5 display in row-major order.
_CB_DISPLAY_MAP = tuple(range(200))
_AFA_KEY_MAP = (
    0, 1, 2, 3, 4, 5, 6, 20, 7, 8, 9, 10, 11, 12, -1, 13,
    14, 15, -1, 16, 17, 18, 19, 34, 35, 21, 22, 23, 24, 25, 26, 27,
    28, 29, -1, 30, 31, 32, 33, 48, 49, 36, 37, 38, 39, 40, -1, 41,
    42, 43, -1, 44, 45, 46, 47, 62, 63, 64, 50, 51, 52, 53, 54, 55,
    56, 57, 58, -1, 59, 60, 61, 73, 70, 65, -1, 66, -1, 67, 68, 69,
)
_RELIC_KEY_MAP = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 59, 58,
    15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 74, 73,
    30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 89, 72,
    45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, -1, 57, -1, -1, -1,
    60, -1, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, -1, 71, -1, 87, -1,
    75, 76, 77, 78, -1, -1, 79, -1, -1, 80, -1, 85, 86, 88, 83, 82, 81,
)


def _placed_map(
    width: int,
    height: int,
    placements: list[tuple[int, int, int]],
) -> tuple[int, ...]:
    result = [-1] * (width * height)
    for x, y, output_index in placements:
        result[y * width + x] = output_index
    return tuple(result)


_RELIC_KEY_SOURCE_MAP = _placed_map(
    18,
    7,
    [
        (position % 17 + 1, position // 17 + 1, output_index)
        for position, output_index in enumerate(_RELIC_KEY_MAP)
        if output_index >= 0
    ],
)
_RELIC_EDGE_MAP = _placed_map(
    18,
    7,
    [
        (0, 6, 0),
        (0, 5, 1),
        (13, 0, 2),
        (14, 0, 3),
        (15, 0, 4),
        (16, 0, 5),
        (17, 0, 6),
    ],
)
# Axial LED payload order for the Neon 80, derived from the Apache-2.0
# neon80_driver file `src/804/axialDefinitionsData.ts`, whose ARRAY INDEX is the
# payload index. Its CSS pixel coordinates quantize onto a 19x6 grid at a 53px
# column pitch, which places all 89 LEDs with no collisions.
#
# This is emphatically NOT the firmware's `real_map`: that table is AW20216
# driver-chip routing the firmware applies after receiving a frame, and
# transcribing it here would map every LED twice. See the plan's "Do not
# transcribe the firmware LED maps".
_NEON_AXIAL_PLACEMENTS = (
        (0, 0, 0), (1, 0, 1), (2, 0, 2), (3, 0, 3),
        (4, 0, 4), (6, 0, 5), (7, 0, 6), (8, 0, 7),
        (9, 0, 8), (10, 0, 9), (11, 0, 10), (12, 0, 11),
        (13, 0, 12), (14, 0, 13), (16, 0, 14), (17, 0, 15),
        (18, 0, 16), (0, 1, 17), (1, 1, 18), (2, 1, 19),
        (3, 1, 20), (4, 1, 21), (5, 1, 22), (6, 1, 23),
        (7, 1, 24), (8, 1, 25), (9, 1, 26), (10, 1, 27),
        (11, 1, 28), (12, 1, 29), (14, 1, 30), (16, 1, 31),
        (17, 1, 32), (18, 1, 33), (0, 2, 34), (2, 2, 35),
        (3, 2, 36), (4, 2, 37), (5, 2, 38), (6, 2, 39),
        (7, 2, 40), (8, 2, 41), (9, 2, 42), (10, 2, 43),
        (11, 2, 44), (12, 2, 45), (13, 2, 46), (14, 2, 47),
        (16, 2, 48), (17, 2, 49), (18, 2, 50), (0, 3, 51),
        (2, 3, 52), (3, 3, 53), (4, 3, 54), (5, 3, 55),
        (6, 3, 56), (7, 3, 57), (8, 3, 58), (9, 3, 59),
        (10, 3, 60), (11, 3, 61), (12, 3, 62), (14, 3, 63),
        (1, 4, 64), (2, 4, 65), (3, 4, 66), (4, 4, 67),
        (5, 4, 68), (6, 4, 69), (7, 4, 70), (8, 4, 71),
        (9, 4, 72), (10, 4, 73), (11, 4, 74), (13, 4, 75),
        (17, 4, 76), (0, 5, 77), (2, 5, 78), (3, 5, 79),
        (4, 5, 80), (7, 5, 81), (10, 5, 82), (11, 5, 83),
        (13, 5, 84), (14, 5, 85), (16, 5, 86), (17, 5, 87),
        (18, 5, 88),
)

_NEON_AXIAL_MAP = _placed_map(19, 6, [list(p) for p in _NEON_AXIAL_PLACEMENTS])

# The head matrix needs no map: the host transmits it row-major, so payload
# index is simply y * 46 + x.
_NEON_HEAD_MAP = tuple(range(230))

_LAYOUTS: dict[str, dict[str, dict[str, Any]]] = {
    "CB": {
        "keyframes": {"size": (15, 6), "map": _CB_KEY_MAP, "pixels": 90},
        "frames": {"size": (40, 5), "map": _CB_DISPLAY_MAP, "pixels": 200},
    },
    "ALICE": {
        "keyframes": {
            "size": (16, 5),
            "map": _AFA_KEY_MAP,
            "pixels": 90,
            "copies": ((71, 7), (72, 20)),
        },
    },
    "NEON": {
        "axial": {
            "size": (19, 6),
            "map": _NEON_AXIAL_MAP,
            "pixels": 89,
        },
        "head": {
            "size": (46, 5),
            "map": _NEON_HEAD_MAP,
            "pixels": 230,
        },
    },
    "80": {
        "keyframes": {
            "size": (18, 7),
            "map": _RELIC_KEY_SOURCE_MAP,
            "pixels": 90,
        },
        "spotlight_frames": {
            "size": (18, 7),
            "map": _RELIC_EDGE_MAP,
            "pixels": 24,
        },
    },
}


def led_model(product_id: str) -> str:
    """Return the canonical LED family for a product identifier."""

    upper = product_id.upper()
    if upper in {"NEON", "NEON80", "AM NEON 80"}:
        return "NEON"
    if upper in {"AM21", "80"}:
        return "80"
    if upper == "ALICE":
        return "ALICE"
    if upper.startswith("CB"):
        return "CB"
    raise ValueError(f"No GIF LED map is available for product {product_id or '?'}.")


def config_product_id(device_id: str) -> str:
    """The `product_id` a freshly created configuration should carry.

    A keyboard reports its own identifier, which is not always what the AM JSON
    format stores: the Relic 80 probes as `AM21`, but its configurations name
    `80`. Every other identifier is stored as reported. This is a wire-format
    rule, distinct from `led_model`'s family lookup — `CB04` stays `CB04` here
    while resolving to family `CB` there.
    """

    upper = str(device_id).upper()
    return "80" if upper == "AM21" else upper


# --- Per-family device specification -------------------------------------
#
# One authority for the per-family numbers that consumers used to hardcode:
# LED track colour counts, macro limits, and transport kind. `_LAYOUTS` above
# remains the authority for which targets a family *authors* and how their
# pixels map; this answers "how large is this track, and what are this family's
# limits", which validation and the editor both need.
#
# Track colour counts come from `_LAYOUTS` wherever a family authors the track,
# so there is no second copy of those numbers. `_SHARED_TRACK_COLORS` covers
# tracks a family does not author: `validate_config` has always checked any
# present track against these counts regardless of family, and preserving that
# keeps this refactor behaviour-neutral.

SERIAL_TRANSPORT = "serial"
HID_TRANSPORT = "hid"

_SHARED_TRACK_COLORS = {"frames": 200, "keyframes": 90, "spotlight_frames": 24}

# The AM serial firmwares share these ceilings, expressed as counts: how many
# macro tracks, and how many events across all of them.
#
# A Vial device does not have a comparable number. It reports `GET_BUFFER_SIZE`,
# a total macro buffer in *bytes*, and how many events fit depends on how each
# one encodes. There is no correct conversion: assume too many bytes per event
# and valid macro sets are rejected, assume too few and an oversized buffer is
# accepted and overruns the device. So a byte budget is a separate field to be
# added alongside these, not a different value for them — and never `None`,
# which would silently disable the checks in `validate_config` and render an
# empty limit in the editor. See plan task N7.
_SERIAL_MACRO_TRACKS = 32
_SERIAL_MACRO_EVENTS = 200


@dataclass(frozen=True)
class FamilySpec:
    """Canonical per-family limits. See the module comment above."""

    model: str
    transport: str
    frame_cap: int
    macro_tracks: int
    macro_events: int
    # Vial devices report a macro *buffer* in bytes and have no event-count
    # limit; the serial families have the opposite. Both are recorded, and 0
    # means "this family does not express capacity that way" - never None,
    # which would silently disable enforcement (see finding or-3).
    macro_buffer_bytes: int = 0
    # How many keycodes one layer holds. The serial families share a 25x8
    # matrix; the Neon reports 6x15 in its own Vial definition. Validation used
    # to demand 200 for every family, which rejected every keymap the Neon can
    # produce.
    keys_per_layer: int = 200

    def track_colors(self, field: str) -> int:
        """Exact colour count for one LED track on this family."""

        layout = _LAYOUTS.get(self.model, {}).get(field)
        if layout is not None:
            return int(layout["pixels"])
        return _SHARED_TRACK_COLORS[field]

    @property
    def authored_tracks(self) -> tuple[str, ...]:
        """Track names this family actually authors, in layout order."""

        return tuple(_LAYOUTS.get(self.model, {}))


# Measured on the owner's board by read-only VIA reads, 2026-07-25: 16 macros
# and a 6677-byte buffer. `macro_events` here is a *proven upper bound* rather
# than a device limit - no macro event encodes in fewer than one byte, so the
# count can never exceed the byte budget. Exact byte sizing before a write is
# the real check and belongs to plan task N7.
_NEON_MACRO_TRACKS = 16
_NEON_MACRO_BUFFER_BYTES = 6677
# 6 rows x 15 columns, from the definition the board serves.
_NEON_KEYS_PER_LAYER = 90

_FAMILY_SPECS = {
    model: FamilySpec(
        model=model,
        transport=SERIAL_TRANSPORT,
        frame_cap=cap,
        macro_tracks=_SERIAL_MACRO_TRACKS,
        macro_events=_SERIAL_MACRO_EVENTS,
    )
    for model, cap in MODEL_FRAME_CAPS.items()
    if model != "NEON"
}

_FAMILY_SPECS["NEON"] = FamilySpec(
    model="NEON",
    transport=HID_TRANSPORT,
    frame_cap=MODEL_FRAME_CAPS["NEON"],
    macro_tracks=_NEON_MACRO_TRACKS,
    macro_events=_NEON_MACRO_BUFFER_BYTES,
    macro_buffer_bytes=_NEON_MACRO_BUFFER_BYTES,
    keys_per_layer=_NEON_KEYS_PER_LAYER,
)

# Used when a configuration names a product this build does not recognise.
# `validate_config` has always accepted such a config and checked it against the
# shared counts, so the fallback preserves that rather than rejecting the file.
_UNKNOWN_FAMILY_SPEC = FamilySpec(
    model="",
    transport=SERIAL_TRANSPORT,
    frame_cap=MAX_FRAMES,
    macro_tracks=_SERIAL_MACRO_TRACKS,
    macro_events=_SERIAL_MACRO_EVENTS,
)

_KEYMAP_ENCODINGS = {
    "CB": "am-usage32-v1",
    "80": "am-usage32-v1",
    "ALICE": "am-usage32-v1",
    "NEON": "qmk-vial16-v1",
}
_KEYMAP_MATRICES = {
    "CB": (25, 8),
    "80": (25, 8),
    "ALICE": (25, 8),
    "NEON": (6, 15),
}
_KEYMAP_LAYOUT_IDS = {
    "CB": "cyberboard-fixed-v1",
    "80": "relic-80-fixed-v1",
    "ALICE": "afa-fixed-v1",
}
_LAYER_LIMITS = {"CB": 7, "80": 7, "ALICE": 7, "NEON": 4}
_PRODUCT_LABELS = {
    "CB": "CyberBoard",
    "80": "Relic 80",
    "ALICE": "AM AFA",
    "NEON": "AM Neon 80",
}
_TARGET_SEMANTICS = {
    "frames": "display",
    "keyframes": "per_key",
    "spotlight_frames": "edge",
    "axial": "per_key",
    "head": "display",
}
def family_spec(model: str) -> FamilySpec:
    """Return the specification for an LED family.

    Raises `KeyError` for an unknown family. Callers that hold a real device or
    family must never silently substitute another device's geometry.
    """

    return _FAMILY_SPECS[model]


def spec_for_product(product_id: object) -> FamilySpec:
    """Resolve a configuration's `product_id` to a specification.

    Never raises: an absent or unrecognised product yields the shared fallback,
    preserving the historical behaviour of validating unknown files rather than
    rejecting them outright.
    """

    if not isinstance(product_id, str) or not product_id:
        return _UNKNOWN_FAMILY_SPEC
    try:
        model = led_model(product_id)
    except ValueError:
        return _UNKNOWN_FAMILY_SPEC
    return _FAMILY_SPECS.get(model, _UNKNOWN_FAMILY_SPEC)


def _signature(namespace: str, value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return f"{namespace}:v1:{hashlib.sha256(encoded).hexdigest()}"


def _canonical_product_id(product_id: str, model: str) -> str:
    if model == "NEON":
        return "NEON80"
    return config_product_id(product_id)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    rounded = round(result, 4)
    return 0.0 if rounded == 0 else rounded


def _canonical_dynamic_key_layout(
    key_layout: object,
    *,
    rows: int,
    columns: int,
) -> list[dict[str, int | float]] | None:
    if (
        isinstance(key_layout, (str, bytes, bytearray))
        or not isinstance(key_layout, Sequence)
        or not key_layout
    ):
        return None
    canonical: list[dict[str, int | float]] = []
    seen_indexes: set[int] = set()
    seen_positions: set[tuple[int, int]] = set()
    required = {
        "index",
        "matrix_row",
        "matrix_col",
        "x",
        "y",
        "width",
        "height",
        "rotation",
    }
    for item in key_layout:
        if not isinstance(item, Mapping) or set(item) != required:
            return None
        index = item["index"]
        matrix_row = item["matrix_row"]
        matrix_col = item["matrix_col"]
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or isinstance(matrix_row, bool)
            or not isinstance(matrix_row, int)
            or isinstance(matrix_col, bool)
            or not isinstance(matrix_col, int)
            or not 0 <= matrix_row < rows
            or not 0 <= matrix_col < columns
            or index != matrix_row * columns + matrix_col
            or index in seen_indexes
            or (matrix_row, matrix_col) in seen_positions
        ):
            return None
        x = _finite_number(item["x"])
        y = _finite_number(item["y"])
        width = _finite_number(item["width"])
        height = _finite_number(item["height"])
        rotation = _finite_number(item["rotation"])
        if (
            x is None
            or y is None
            or width is None
            or height is None
            or rotation is None
            or x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or rotation != 0
            or x + width > 100.0001
            or y + height > 100.0001
        ):
            return None
        seen_indexes.add(index)
        seen_positions.add((matrix_row, matrix_col))
        canonical.append(
            {
                "index": index,
                "matrix_row": matrix_row,
                "matrix_col": matrix_col,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "rotation": rotation,
            }
        )
    canonical.sort(key=lambda item: (item["matrix_row"], item["matrix_col"]))
    return canonical


def canonical_dynamic_key_layout(
    product_id: str,
    key_layout: object,
) -> tuple[dict[str, int | float], ...] | None:
    """Return the exact bounded portable projection for a dynamic layout.

    Fixed families deliberately return no projection: their geometry is owned
    by the built-in family descriptor and does not belong in saved profile
    metadata.
    """

    model = led_model(product_id)
    if model != "NEON":
        return None
    rows, columns = _KEYMAP_MATRICES[model]
    canonical = _canonical_dynamic_key_layout(
        key_layout,
        rows=rows,
        columns=columns,
    )
    if canonical is None:
        return None
    return tuple(dict(item) for item in canonical)


def _keymap_descriptor(
    model: str,
    key_layout: object,
) -> dict[str, Any]:
    rows, columns = _KEYMAP_MATRICES[model]
    encoding = _KEYMAP_ENCODINGS[model]
    if model == "NEON":
        physical_layout = _canonical_dynamic_key_layout(
            key_layout,
            rows=rows,
            columns=columns,
        )
        if physical_layout is None:
            return {
                "signature": None,
                "layout_known": False,
                "encoding": encoding,
                "matrix_rows": rows,
                "matrix_columns": columns,
            }
        layout_identity: dict[str, Any] = {
            "kind": "device_definition",
            "keys": physical_layout,
        }
    else:
        layout_identity = {
            "kind": "fixed_family",
            "layout_id": _KEYMAP_LAYOUT_IDS[model],
            "matrix_positions": [
                {
                    "index": index,
                    "matrix_row": index // columns,
                    "matrix_col": index % columns,
                }
                for index in range(rows * columns)
            ],
        }
    signature = _signature(
        "keymap",
        {
            "schema_version": 1,
            "family": model,
            "matrix": {"rows": rows, "columns": columns},
            "keys_per_layer": _FAMILY_SPECS[model].keys_per_layer,
            "assignment_encoding": encoding,
            "physical_layout": layout_identity,
        },
    )
    return {
        "signature": signature,
        "layout_known": True,
        "encoding": encoding,
        "matrix_rows": rows,
        "matrix_columns": columns,
    }


def _lighting_target_descriptor(model: str, target: str) -> dict[str, Any]:
    layout = _LAYOUTS[model][target]
    width, height = layout["size"]
    copies = [
        {"output_index": int(output), "source_index": int(source)}
        for output, source in layout.get("copies", ())
    ]
    derivations: list[dict[str, Any]] = []
    if (model, target) == ("NEON", "head"):
        from . import neon_lighting

        # Derive the exact source-index order through the production reducer so
        # the signature changes with that reducer. Repeating its dimensions or
        # skip table here would create a second authority.
        source_indexes = list(range(neon_lighting.HEAD_LED_COUNT))
        derived_indexes = neon_lighting.derive_side_frame(source_indexes)
        derivations.append(
            {
                "semantic_target": "side_screen_lights",
                "method": "derive_side_frame",
                "width": neon_lighting.SIDE_COLUMNS,
                "height": neon_lighting.SIDE_ROWS,
                "output_leds": neon_lighting.SIDE_LED_COUNT,
                "source_indexes": derived_indexes,
                "track_role": "dependent",
            }
        )
    public = {
        "semantic_target": _TARGET_SEMANTICS[target],
        "track_role": "authored",
        "width": int(width),
        "height": int(height),
        "output_leds": int(layout["pixels"]),
        "copies": copies,
        "derivations": derivations,
    }
    signature = _signature(
        "lighting",
        {
            "schema_version": 1,
            "target": target,
            **public,
            "output_order": [int(index) for index in layout["map"]],
        },
    )
    return {"signature": signature, **public}


def device_descriptor(
    product_id: str,
    *,
    key_layout: object = None,
    product_label: object = None,
    layer_count: int | None = None,
    macro_count: int | None = None,
    macro_buffer_bytes: int | None = None,
) -> dict[str, Any]:
    """Return canonical signatures and limits for one supported destination.

    The fixed serial families have a built-in layout identity. A Vial layout is
    deliberately different: its signature exists only when the validated
    device-definition projection is present, so an imported Neon JSON can never
    acquire a guessed keymap identity from its product name.
    """

    model = led_model(product_id)
    spec = _FAMILY_SPECS[model]
    layers = _LAYER_LIMITS[model] if layer_count is None else layer_count
    macros = spec.macro_tracks if macro_count is None else macro_count
    macro_bytes = (
        spec.macro_buffer_bytes
        if macro_buffer_bytes is None
        else macro_buffer_bytes
    )
    for value, label, minimum in (
        (layers, "layer count", 1),
        (macros, "macro count", 0),
        (macro_bytes, "macro buffer size", 0),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
            or value > 1_000_000
        ):
            raise ValueError(f"The device {label} is invalid.")
    label = str(product_label or _PRODUCT_LABELS[model]).strip()
    if not label or len(label) > 200 or any(ord(character) < 32 for character in label):
        raise ValueError("The device product label is invalid.")
    return {
        "schema_version": 1,
        "product_id": _canonical_product_id(product_id, model),
        "family": model,
        "product_label": label,
        "keymap": _keymap_descriptor(model, key_layout),
        "lighting": {
            target: _lighting_target_descriptor(model, target)
            for target in _LAYOUTS[model]
        },
        "limits": {
            "frames": spec.frame_cap,
            "layers": layers,
            "keys_per_layer": spec.keys_per_layer,
            "macros": macros,
            "macro_events": spec.macro_events,
            "macro_buffer_bytes": macro_bytes,
            "assignment_encoding": _KEYMAP_ENCODINGS[model],
        },
    }


def lighting_section_compatibility(
    content_kind: str,
    *,
    destination_signature: str | None,
    source_signature: str | None = None,
    has_recipe: bool = False,
    has_media_source: bool = False,
) -> dict[str, str]:
    """Classify one lighting section without trusting a product-name match."""

    def result(status: str, reason_code: str, detail: str) -> dict[str, str]:
        return {
            "status": status,
            "reason_code": reason_code,
            "detail": detail,
        }

    if not destination_signature:
        return result(
            "blocked",
            "target_unavailable",
            "The destination does not expose this lighting target.",
        )
    if content_kind == "media_source":
        return result(
            "convertible",
            "media_rerender",
            "The original media can be rendered for this destination.",
        )
    if content_kind == "generation_job" and has_recipe:
        return result(
            "convertible",
            "recipe_rerender",
            "The validated recipe can be rendered directly for this destination.",
        )
    if content_kind == "lighting_composition" and has_media_source:
        return result(
            "convertible",
            "media_rerender",
            "The original media composition can be rendered for this destination.",
        )
    if source_signature and source_signature == destination_signature:
        return result(
            "exact",
            "lighting_signature_match",
            "The rendered lighting target matches exactly.",
        )
    if content_kind not in {"generation_job", "lighting_composition"}:
        raise ValueError("The lighting content kind is unsupported.")
    return result(
        "blocked",
        "lighting_signature_mismatch",
        "Rendered frames require an exact lighting target match.",
    )


def validate_gif_targets(
    product_id: str,
    targets: Sequence[str],
) -> tuple[str, list[str]]:
    """Return a device family and de-duplicated, supported GIF targets."""

    model = led_model(product_id)
    requested = list(dict.fromkeys(str(target) for target in targets))
    if not requested:
        raise ValueError("At least one GIF LED target is required.")
    for target in requested:
        if _LAYOUTS[model].get(target) is None:
            supported = ", ".join(_LAYOUTS[model])
            raise ValueError(
                f"{product_id} does not support GIF target {target}; use {supported}."
            )
    return model, requested


def media_target_sizes(
    product_id: str,
    targets: Sequence[str],
) -> tuple[str, list[str], tuple[tuple[int, int], ...]]:
    """Resolve every requested imported-media destination raster."""

    model, requested = validate_gif_targets(product_id, targets)
    return (
        model,
        requested,
        tuple(tuple(_LAYOUTS[model][target]["size"]) for target in requested),
    )


def firmware_led_speed(duration_ms: int) -> int:
    """Return the nearest timing step exposed by the firmware."""

    duration = max(1, int(duration_ms))
    return min(LED_SPEEDS_MS, key=lambda speed: (abs(speed - duration), speed))


def media_timeline_indices(
    durations: Sequence[int],
    *,
    frame_limit: int = MAX_FRAMES,
) -> tuple[list[int], int, bool]:
    """Select canonical firmware output frames for source-frame durations."""

    if type(frame_limit) is not int or not 1 <= frame_limit <= MAX_FRAMES:
        raise ValueError("The LED frame limit is invalid.")
    clean = [max(10, int(duration or 90)) for duration in durations]
    if not clean:
        return [0], 90, False
    variable = len(set(clean)) > 1
    if not variable and len(clean) <= frame_limit:
        return list(range(len(clean))), firmware_led_speed(clean[0]), False

    common = clean[0]
    for duration in clean[1:]:
        common = math.gcd(common, duration)
    speed = firmware_led_speed(common)
    total = sum(clean)
    if math.ceil(total / speed) > frame_limit:
        fitting = [
            candidate
            for candidate in sorted(LED_SPEEDS_MS)
            if math.ceil(total / candidate) <= frame_limit
        ]
        speed = fitting[0] if fitting else max(LED_SPEEDS_MS)

    output_count = min(frame_limit, max(1, math.ceil(total / speed)))
    indices: list[int] = []
    source_index = 0
    boundary = clean[0]
    for output_index in range(output_count):
        timestamp = min(total - 1, output_index * speed)
        while source_index < len(clean) - 1 and timestamp >= boundary:
            source_index += 1
            boundary += clean[source_index]
        indices.append(source_index)
    return indices, speed, True


def _map_prepared_media_frame(
    image: Any,
    *,
    model: str,
    requested: Sequence[str],
    layouts: Mapping[str, Mapping[str, Any]],
    destination_sizes: Sequence[tuple[int, int]],
    transform: Any,
    work_check: Callable[[], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Map one source frame through canonical geometry onto exact LED arrays."""

    from .media_composition import render_source_frame

    raster_colors: dict[tuple[int, int], list[str]] = {}
    for size in destination_sizes:
        if work_check is not None:
            work_check()
        if size in raster_colors:
            continue
        raster = render_source_frame(image, size, transform)
        pixels = (
            raster.get_flattened_data()
            if hasattr(raster, "get_flattened_data")
            else raster.getdata()
        )
        raster_colors[size] = [
            f"#{red:02X}{green:02X}{blue:02X}"
            for red, green, blue in pixels
        ]

    tracks: dict[str, dict[str, Any]] = {}
    for target in requested:
        if work_check is not None:
            work_check()
        layout = layouts[target]
        size = tuple(layout["size"])
        source_colors = raster_colors[size]
        colors = ["#000000"] * int(layout["pixels"])
        for source_index, output_index in enumerate(layout["map"]):
            if output_index >= 0:
                colors[output_index] = source_colors[source_index]
        for output_index, source_index in layout.get("copies", ()):
            colors[output_index] = colors[source_index]
        width, height = size
        tracks[target] = {
            "colors": colors,
            "width": width,
            "height": height,
            "pixels": int(layout["pixels"]),
            "mapped_pixels": len(
                {index for index in layout["map"] if index >= 0}
            ),
        }
    return tracks


def map_media_frame_to_led_tracks(
    image: Any,
    targets: list[str] | tuple[str, ...],
    transform: Mapping[str, object],
    product_id: str = "CB_XX",
    *,
    work_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Render and map one exact output frame for live media preview."""

    from .media_composition import (
        canonicalize_source_transform,
        validate_source_transform,
    )

    if work_check is not None:
        work_check()
    model, requested, destination_sizes = media_target_sizes(product_id, targets)
    checked = canonicalize_source_transform(
        validate_source_transform(transform),
        tuple(image.size),
        destination_sizes,
    )
    layouts = {target: _LAYOUTS[model][target] for target in requested}
    return {
        "model": model,
        "tracks": _map_prepared_media_frame(
            image,
            model=model,
            requested=requested,
            layouts=layouts,
            destination_sizes=destination_sizes,
            transform=checked,
            work_check=work_check,
        ),
    }


def frames_to_led_tracks(
    images: Sequence[Any],
    durations_ms: Sequence[int],
    targets: list[str] | tuple[str, ...],
    resample: str = "box",
    product_id: str = "CB_XX",
    *,
    work_check: Callable[[], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    frame_limit: int = MAX_FRAMES,
    source_frame_limit: int | None = None,
) -> dict[str, Any]:
    """Map ordered raster frames onto one or more firmware LED tracks."""

    if type(frame_limit) is not int or not 1 <= frame_limit <= MAX_FRAMES:
        raise ValueError("The LED frame limit is invalid.")
    if source_frame_limit is None:
        source_frame_limit = frame_limit
    if type(source_frame_limit) is not int or source_frame_limit < frame_limit:
        raise ValueError("The source frame limit is invalid.")
    if work_check is not None:
        work_check()
    model, requested = validate_gif_targets(product_id, targets)
    layouts: dict[str, dict[str, Any]] = {}
    for target in requested:
        if work_check is not None:
            work_check()
        layouts[target] = _LAYOUTS[model][target]
    if resample not in {"nearest", "box", "lanczos"}:
        raise ValueError("GIF resampling must be nearest, box, or lanczos.")
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise ValueError("GIF import needs Pillow. Reinstall AM Configurator.") from exc

    frames = list(images)[:source_frame_limit]
    if not frames:
        raise ValueError("The GIF contains no frames.")
    raw_durations = list(durations_ms)[:source_frame_limit]
    filters = {
        "nearest": Image.Resampling.NEAREST,
        "box": Image.Resampling.BOX,
        "lanczos": Image.Resampling.LANCZOS,
    }
    track_frames: dict[str, list[list[str]]] = {target: [] for target in requested}
    durations: list[int] = []
    for index, frame in enumerate(frames):
        if work_check is not None:
            work_check()
        source_duration = raw_durations[index] if index < len(raw_durations) else None
        durations.append(max(10, int(source_duration or 90)))
        rgba = frame.convert("RGBA")
        black = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        rgb = Image.alpha_composite(black, rgba).convert("RGB")
        raster_colors: dict[tuple[int, int], list[str]] = {}
        for layout in layouts.values():
            width, height = layout["size"]
            size = (width, height)
            if size not in raster_colors:
                fitted = rgb
                source_ratio = fitted.width / fitted.height
                target_ratio = width / height
                if source_ratio > target_ratio:
                    crop_width = max(1, round(fitted.height * target_ratio))
                    left = (fitted.width - crop_width) // 2
                    fitted = fitted.crop((left, 0, left + crop_width, fitted.height))
                elif source_ratio < target_ratio:
                    crop_height = max(1, round(fitted.width / target_ratio))
                    top = (fitted.height - crop_height) // 2
                    fitted = fitted.crop((0, top, fitted.width, top + crop_height))
                if fitted.size != size:
                    fitted = fitted.resize(size, filters[resample])
                pixels = (
                    fitted.get_flattened_data()
                    if hasattr(fitted, "get_flattened_data")
                    else fitted.getdata()
                )
                raster_colors[size] = [
                    f"#{red:02X}{green:02X}{blue:02X}"
                    for red, green, blue in pixels
                ]

        for target, layout in layouts.items():
            if work_check is not None:
                work_check()
            source_colors = raster_colors[layout["size"]]
            colors = ["#000000"] * int(layout["pixels"])
            for source_index, output_index in enumerate(layout["map"]):
                if output_index >= 0:
                    colors[output_index] = source_colors[source_index]
            for output_index, source_index in layout.get("copies", ()):
                colors[output_index] = colors[source_index]
            track_frames[target].append(colors)
        if progress is not None:
            progress(index + 1, len(frames))

    if work_check is not None:
        work_check()
    timeline, duration, timing_resampled = media_timeline_indices(
        durations,
        frame_limit=frame_limit,
    )
    tracks = {}
    for target, layout in layouts.items():
        if work_check is not None:
            work_check()
        mapped = [track_frames[target][index] for index in timeline]
        width, height = layout["size"]
        tracks[target] = {
            "frames": mapped,
            "frame_count": len(mapped),
            "width": width,
            "height": height,
            "pixels": int(layout["pixels"]),
            "mapped_pixels": len(
                {index for index in layout["map"] if index >= 0}
            ),
        }
    return {
        "tracks": tracks,
        "source_frames": len(frames),
        "decoded_frames": len(frames),
        "duration_ms": duration,
        "source_duration_ms": sum(durations),
        "timing_resampled": timing_resampled,
        "model": model,
    }


def compose_media_frames_to_led_tracks(
    images: Sequence[Any],
    durations_ms: Sequence[int],
    targets: list[str] | tuple[str, ...],
    transform: Mapping[str, object],
    product_id: str = "CB_XX",
    *,
    work_check: Callable[[], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Transform imported media and map it within the destination frame ceiling."""

    from .media_composition import (
        MAX_MEDIA_FRAMES,
        canonicalize_source_transform,
        render_source_frame,
        validate_source_transform,
    )

    if work_check is not None:
        work_check()
    checked = validate_source_transform(transform)
    model, requested, destination_sizes = media_target_sizes(product_id, targets)
    frame_limit = family_spec(model).frame_cap
    frames = list(images)
    if not frames:
        raise ValueError("The imported media contains no frames.")
    if len(frames) > MAX_MEDIA_FRAMES:
        raise ValueError("The imported media frame limit was exceeded.")
    raw_durations = list(durations_ms)[:MAX_MEDIA_FRAMES]
    source_sizes = {tuple(frame.size) for frame in frames}
    if len(source_sizes) != 1:
        raise ValueError("Imported media frames must share one source size.")
    checked = canonicalize_source_transform(
        checked,
        next(iter(source_sizes)),
        destination_sizes,
    )

    layouts = {target: _LAYOUTS[model][target] for target in requested}
    track_frames: dict[str, list[list[str]]] = {
        target: [] for target in requested
    }
    durations: list[int] = []
    for index, frame in enumerate(frames):
        if work_check is not None:
            work_check()
        source_duration = (
            raw_durations[index] if index < len(raw_durations) else None
        )
        durations.append(max(10, int(source_duration or 90)))
        mapped = _map_prepared_media_frame(
            frame,
            model=model,
            requested=requested,
            layouts=layouts,
            destination_sizes=destination_sizes,
            transform=checked,
            work_check=work_check,
        )
        for target in requested:
            track_frames[target].append(mapped[target]["colors"])
        if progress is not None:
            progress(index + 1, len(frames))

    if work_check is not None:
        work_check()
    timeline, duration, timing_resampled = media_timeline_indices(
        durations,
        frame_limit=frame_limit,
    )
    tracks: dict[str, dict[str, Any]] = {}
    for target, layout in layouts.items():
        if work_check is not None:
            work_check()
        mapped = [track_frames[target][index] for index in timeline]
        width, height = layout["size"]
        tracks[target] = {
            "frames": mapped,
            "frame_count": len(mapped),
            "width": width,
            "height": height,
            "pixels": int(layout["pixels"]),
            "mapped_pixels": len(
                {index for index in layout["map"] if index >= 0}
            ),
        }
    return {
        "tracks": tracks,
        "source_frames": len(frames),
        "decoded_frames": len(frames),
        "duration_ms": duration,
        "source_duration_ms": sum(durations),
        "timing_resampled": timing_resampled,
        "model": model,
    }


def compose_media_transform_sequence_to_led_tracks(
    image: Any,
    durations_ms: Sequence[int],
    targets: list[str] | tuple[str, ...],
    transforms: Sequence[Mapping[str, object]],
    product_id: str = "CB_XX",
    *,
    work_check: Callable[[], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Render one still through canonical transforms and map every target."""

    from .media_composition import (
        canonicalize_source_transform,
        render_source_frame,
        validate_source_transform,
    )

    if work_check is not None:
        work_check()
    model, requested, destination_sizes = media_target_sizes(product_id, targets)
    frame_limit = family_spec(model).frame_cap
    raw_transforms = list(transforms)
    if not raw_transforms or len(raw_transforms) > frame_limit:
        raise ValueError("The imported media transform frame limit was exceeded.")
    source_size = tuple(image.size)
    checked = [
        canonicalize_source_transform(
            validate_source_transform(transform),
            source_size,
            destination_sizes,
        )
        for transform in raw_transforms
    ]
    sampling = checked[0].sampling
    if any(transform.sampling != sampling for transform in checked[1:]):
        raise ValueError("Move & zoom transforms must share one sampling mode.")
    durations = list(durations_ms)
    if len(durations) != len(checked):
        raise ValueError("Move & zoom timing must match its transform frames.")

    layouts = {target: _LAYOUTS[model][target] for target in requested}
    track_frames: dict[str, list[list[str]]] = {
        target: [] for target in requested
    }
    for index, transform in enumerate(checked):
        if work_check is not None:
            work_check()
        mapped = _map_prepared_media_frame(
            image,
            model=model,
            requested=requested,
            layouts=layouts,
            destination_sizes=destination_sizes,
            transform=transform,
            work_check=work_check,
        )
        for target in requested:
            track_frames[target].append(mapped[target]["colors"])
        if progress is not None:
            progress(index + 1, len(checked))

    timeline, duration, timing_resampled = media_timeline_indices(
        durations,
        frame_limit=frame_limit,
    )
    tracks: dict[str, dict[str, Any]] = {}
    for target, layout in layouts.items():
        selected = [track_frames[target][index] for index in timeline]
        width, height = layout["size"]
        tracks[target] = {
            "frames": selected,
            "frame_count": len(selected),
            "width": width,
            "height": height,
            "pixels": int(layout["pixels"]),
            "mapped_pixels": len(
                {index for index in layout["map"] if index >= 0}
            ),
        }
    return {
        "tracks": tracks,
        "source_frames": len(checked),
        "decoded_frames": len(checked),
        "duration_ms": duration,
        "source_duration_ms": sum(durations),
        "timing_resampled": timing_resampled,
        "model": model,
    }


def validate_mapped_result(
    mapped: object,
    *,
    frame_count: int,
    duration_ms: int,
    targets: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Validate an exact generated timeline before publication or recovery."""

    if not isinstance(mapped, dict):
        raise ValueError("animation mapping returned an invalid result")
    expected_targets = set(targets)
    tracks = mapped.get("tracks")
    if (
        type(frame_count) is not int
        or frame_count <= 0
        or type(duration_ms) is not int
        or duration_ms <= 0
        or not isinstance(tracks, dict)
        or mapped.get("source_frames") != frame_count
        or mapped.get("decoded_frames") != frame_count
        or mapped.get("duration_ms") != duration_ms
        or mapped.get("source_duration_ms") != frame_count * duration_ms
        or mapped.get("timing_resampled") is not False
        or set(tracks) != expected_targets
    ):
        raise ValueError("animation mapping changed the exact frame timeline")
    for track in tracks.values():
        if (
            not isinstance(track, dict)
            or track.get("frame_count") != frame_count
            or not isinstance(track.get("frames"), list)
            or len(track["frames"]) != frame_count
        ):
            raise ValueError("animation mapping changed the exact frame count")
    return mapped


def generation_spec(
    product_id: str,
    targets: list[str] | tuple[str, ...],
    frame_count: int | None,
) -> tuple[RasterSpec, list[str]]:
    """Build a validated same-raster generation specification."""

    model = led_model(product_id)
    requested = list(dict.fromkeys(str(target) for target in targets))
    if not requested:
        raise ValueError("At least one LED generation target is required.")
    layouts: dict[str, dict[str, Any]] = {}
    for target in requested:
        layout = _LAYOUTS[model].get(target)
        if layout is None:
            supported = ", ".join(_LAYOUTS[model])
            raise ValueError(
                f"{product_id} does not support LED target {target}; use {supported}."
            )
        layouts[target] = layout
    sizes = {tuple(layout["size"]) for layout in layouts.values()}
    if len(sizes) > 1:
        raise ValueError(
            "These LED targets use different rasters and cannot be generated "
            "together; generate one target at a time."
        )
    width, height = next(iter(sizes))

    cap = MODEL_FRAME_CAPS[model]
    max_frames = cap if frame_count is None else max(1, min(int(frame_count), cap))

    visible: set[tuple[int, int]] = set()
    for layout in layouts.values():
        layout_width = int(layout["size"][0])
        for source_index, output_index in enumerate(layout["map"]):
            if output_index >= 0:
                visible.add(
                    (source_index % layout_width, source_index // layout_width)
                )
    mapped_positions: tuple[tuple[int, int], ...] | None = None
    if visible and len(visible) * 2 <= width * height:
        mapped_positions = tuple(sorted(visible))

    primary = requested[0]
    output_len = len(
        {index for index in layouts[primary]["map"] if index >= 0}
    )
    return (
        RasterSpec(
            model=model,
            target=primary,
            extra_targets=tuple(requested[1:]),
            width=width,
            height=height,
            mapped_positions=mapped_positions,
            output_len=output_len,
            max_frames=max_frames,
        ),
        requested,
    )


def target_capabilities() -> dict[str, Any]:
    """Return public target geometry derived from the canonical layouts."""

    targets: dict[str, Any] = {}
    for model, layouts in _LAYOUTS.items():
        descriptor = device_descriptor(model)
        sizes = {tuple(layout["size"]) for layout in layouts.values()}
        entries = []
        for name, layout in layouts.items():
            width, height = layout["size"]
            signature = descriptor["lighting"][name]
            extra = [
                other
                for other, other_layout in layouts.items()
                if other != name
                and tuple(other_layout["size"]) == (width, height)
            ]
            entries.append(
                {
                    "name": name,
                    "width": width,
                    "height": height,
                    "pixels": int(layout["pixels"]),
                    "extra_targets": extra,
                    "signature": signature["signature"],
                    "semantic_target": signature["semantic_target"],
                    "track_role": signature["track_role"],
                    "copies": signature["copies"],
                    "derivations": signature["derivations"],
                    # The source-pixel -> payload-index map, so the editor can
                    # lay out any family's track without carrying its own copy
                    # of these tables. Python stays the single authority; a
                    # second copy in JavaScript is exactly the drift the
                    # cross-language guard exists to prevent.
                    "map": list(layout["map"]),
                }
            )
        targets[model] = {
            "single_target": len(sizes) > 1,
            "targets": entries,
            "keymap": descriptor["keymap"],
            "limits": descriptor["limits"],
        }
    return targets
