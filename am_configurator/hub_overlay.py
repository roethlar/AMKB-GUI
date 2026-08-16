"""Pure semantic first-pass overlay between two validated hub profiles.

H4 deliberately owns no transport.  It starts with the target's complete hub
profile, maps source keymap entries onto target key identities, and returns an
honest transfer report plus the unresolved worklist used by H5.

Semantic ``K_*`` identities match directly.  Existing AM, Vial, and VIA spoke
profiles may expose only positional ``K_I###`` or ``K_R#_C#`` identities; for
those, the source and target base keycodes are the only device-proven semantic
anchors available.  Matrix coordinates never match across keyboards.
"""

from __future__ import annotations

import copy
from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Any

from .hub_profile import validate_hub_profile, validate_transfer_report


_INDEX_KEY_RE = re.compile(r"^K_I[0-9]+$")
_MATRIX_KEY_RE = re.compile(r"^K_R[0-9]+_C[0-9]+$")
_ALPHANUMERIC_CODES = frozenset(range(0x0004, 0x0028))
_CUSTOM_CODE_LOW = 0x7E00
_CUSTOM_CODE_HIGH = 0x7FFF


class OverlayError(ValueError):
    """Two valid hub profiles cannot be overlaid without guessing."""


@dataclass(frozen=True)
class OverlayResult:
    """Target-shaped profile, validated report, and unresolved UI worklist."""

    profile: dict[str, Any]
    report: dict[str, Any]
    worklist: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _Placement:
    target_key: str | None
    target_layer: int | None
    adapted: bool
    reason: str | None
    suggestions: tuple[tuple[int, str], ...]


def _layers(profile: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {layer["index"]: layer for layer in profile["keymap"]["layers"]}


def _layer_entries(profile: dict[str, Any]) -> dict[int, dict[str, dict[str, Any]]]:
    return {
        layer["index"]: {entry["key"]: entry for entry in layer["keys"]}
        for layer in profile["keymap"]["layers"]
    }


def _is_positional(identity: str) -> bool:
    return bool(_INDEX_KEY_RE.fullmatch(identity) or _MATRIX_KEY_RE.fullmatch(identity))


def _is_custom_keycode(code: int) -> bool:
    # QMK 0.0.1 used separate 0x7E/0x7F pages; 0.0.2+ repartitioned the
    # same union.  The whole union is therefore conservatively per-board.
    return _CUSTOM_CODE_LOW <= code <= _CUSTOM_CODE_HIGH


def _path(layer: int, identity: str) -> str:
    return f"keymap.layers[{layer}].keys[{identity}]"


def _suggestion_dicts(
    suggestions: tuple[tuple[int, str], ...],
) -> list[dict[str, Any]]:
    return [
        {"target_key": target_key, "target_layer": target_layer}
        for target_layer, target_key in suggestions
    ]


def _target_occurrences(
    target_layers: dict[int, dict[str, dict[str, Any]]],
) -> dict[int, tuple[tuple[int, str], ...]]:
    occurrences: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for layer_index in sorted(target_layers):
        for identity, entry in target_layers[layer_index].items():
            occurrences[entry["code"]].append((layer_index, identity))
    return {
        code: tuple(sorted(positions))
        for code, positions in occurrences.items()
    }


def _infer_placements(
    source_base: dict[str, dict[str, Any]],
    target_layers: dict[int, dict[str, dict[str, Any]]],
) -> dict[str, _Placement]:
    target_base = target_layers[0]
    occurrences = _target_occurrences(target_layers)
    source_counts = Counter(entry["code"] for entry in source_base.values())
    target_base_codes: dict[int, list[str]] = defaultdict(list)
    for identity, entry in target_base.items():
        target_base_codes[entry["code"]].append(identity)

    placements: dict[str, _Placement] = {}
    for identity, entry in source_base.items():
        code = entry["code"]
        suggestions = occurrences.get(code, ())

        if not _is_positional(identity) and identity in target_base:
            placements[identity] = _Placement(identity, 0, False, None, ())
            continue

        if source_counts[code] > 1:
            placements[identity] = _Placement(
                None,
                None,
                False,
                (
                    "more than one source key has this base-layer function; "
                    "its physical home is ambiguous"
                ),
                suggestions,
            )
            continue

        base_matches = tuple(sorted(target_base_codes.get(code, ())))
        if len(base_matches) == 1:
            placements[identity] = _Placement(base_matches[0], 0, False, None, ())
            continue
        if len(base_matches) > 1:
            placements[identity] = _Placement(
                None,
                None,
                False,
                (
                    "the target has more than one base-layer key with this "
                    "function; no physical home was guessed"
                ),
                tuple((0, target_key) for target_key in base_matches),
            )
            continue

        non_base = tuple(position for position in suggestions if position[0] != 0)
        if code in _ALPHANUMERIC_CODES and len(non_base) == 1:
            target_layer, target_key = non_base[0]
            placements[identity] = _Placement(
                target_key,
                target_layer,
                True,
                (
                    "the target's existing layer convention places this "
                    f"alphanumeric key on layer {target_layer}"
                ),
                (),
            )
            continue

        placements[identity] = _Placement(
            None,
            None,
            False,
            "this source key has no unambiguous physical home on the target",
            suggestions,
        )
    return placements


def _set_keycode(entry: dict[str, Any], code: int) -> None:
    entry["code"] = code
    entry.pop("carried", None)
    entry.pop("native", None)


def _deferred_source_sections(
    source: dict[str, Any],
    report_items: list[dict[str, Any]],
    worklist: list[dict[str, Any]],
) -> None:
    reason = "H4's first-pass overlay maps keymaps only; this item remains in the worklist"
    for encoder_index, _encoder in enumerate(source.get("keymap", {}).get("encoders", [])):
        path = f"keymap.encoders[{encoder_index}]"
        report_items.append({"path": path, "verdict": "dropped", "reason": reason})
        worklist.append({"path": path, "reason": reason, "suggestions": []})
    for macro in source.get("macros", []):
        path = f"macros[{macro['slot']}]"
        report_items.append({"path": path, "verdict": "dropped", "reason": reason})
        worklist.append({"path": path, "reason": reason, "suggestions": []})
    if "lighting" in source:
        path = "lighting"
        report_items.append({"path": path, "verdict": "dropped", "reason": reason})
        worklist.append({"path": path, "reason": reason, "suggestions": []})


def overlay_profile(source_profile: object, target_profile: object) -> OverlayResult:
    """Overlay source keymap onto target without coordinates or silent loss.

    Layer zero is the semantic anchor.  Alphanumeric keys found on exactly one
    established non-base target layer are adapted there (the common 40% digit
    convention).  Other homeless keys remain target-preserving worklist items
    with any same-keycode target positions offered as structured suggestions.
    """

    if isinstance(source_profile, dict) and "keymap" not in source_profile:
        raise OverlayError("The source profile has no keymap to overlay.")
    if isinstance(target_profile, dict) and "keymap" not in target_profile:
        raise OverlayError("The target profile has no keymap to receive the overlay.")
    source = validate_hub_profile(source_profile)
    target = validate_hub_profile(target_profile)

    source_layers = _layers(source)
    target_layer_objects = _layers(target)
    if 0 not in source_layers:
        raise OverlayError("The source keymap has no base layer 0 for semantic matching.")
    if 0 not in target_layer_objects:
        raise OverlayError("The target keymap has no base layer 0 for semantic matching.")

    output = copy.deepcopy(target)
    source_entries = _layer_entries(source)
    target_entries = _layer_entries(output)
    placements = _infer_placements(source_entries[0], target_entries)
    report_items: list[dict[str, Any]] = []
    worklist: list[dict[str, Any]] = []
    assigned: dict[tuple[int, str], str] = {}

    def drop(
        path: str,
        reason: str,
        suggestions: tuple[tuple[int, str], ...] = (),
    ) -> None:
        report_items.append({"path": path, "verdict": "dropped", "reason": reason})
        worklist.append(
            {
                "path": path,
                "reason": reason,
                "suggestions": _suggestion_dicts(suggestions),
            }
        )

    for layer_index in sorted(source_entries):
        for identity, source_entry in source_entries[layer_index].items():
            path = _path(layer_index, identity)
            code = source_entry["code"]
            if source_entry.get("carried") is False:
                drop(path, "the source marks this spoke-native keycode as not portable")
                continue
            if _is_custom_keycode(code):
                drop(
                    path,
                    "QMK keyboard/user keycodes are per-board custom and cannot be carried safely",
                )
                continue

            if not _is_positional(identity) and identity in target_entries.get(layer_index, {}):
                placement = _Placement(identity, layer_index, False, None, ())
            else:
                placement = placements.get(identity)
                if placement is None:
                    drop(
                        path,
                        (
                            "this key has no source base-layer semantic anchor; "
                            "no target position was guessed"
                        ),
                    )
                    continue

            if placement.target_key is None or placement.target_layer is None:
                drop(path, placement.reason or "this key has no target home", placement.suggestions)
                continue

            if placement.adapted:
                if layer_index != 0:
                    drop(
                        path,
                        (
                            "only the source base assignment can use a target "
                            "non-base alphanumeric convention"
                        ),
                        ((placement.target_layer, placement.target_key),),
                    )
                    continue
                destination_layer = placement.target_layer
            else:
                destination_layer = layer_index

            destination = target_entries.get(destination_layer, {}).get(placement.target_key)
            if destination is None:
                drop(
                    path,
                    f"the target has no layer {destination_layer} home for this mapped key",
                    ((placement.target_layer, placement.target_key),),
                )
                continue

            destination_id = (destination_layer, placement.target_key)
            if destination_id in assigned:
                drop(
                    path,
                    (
                        "this placement conflicts with an earlier first-pass "
                        "assignment; the earlier base-layer assignment was kept"
                    ),
                    (destination_id,),
                )
                continue

            _set_keycode(destination, code)
            assigned[destination_id] = path
            if placement.adapted:
                report_items.append(
                    {
                        "path": path,
                        "verdict": "adapted",
                        "reason": placement.reason,
                    }
                )
            else:
                report_items.append({"path": path, "verdict": "carried"})

    _deferred_source_sections(source, report_items, worklist)
    report = validate_transfer_report(
        {
            "source": source["identity"],
            "target": target["identity"],
            "items": report_items,
        }
    )
    output["transfer_report"] = report
    provenance = output.setdefault("provenance", {})
    for pointer in tuple(provenance):
        if pointer == "/keymap" or pointer.startswith("/keymap/"):
            del provenance[pointer]
    provenance["/keymap"] = "user"
    validated_output = validate_hub_profile(output)
    return OverlayResult(
        profile=validated_output,
        report=validated_output["transfer_report"],
        worklist=tuple(copy.deepcopy(worklist)),
    )
