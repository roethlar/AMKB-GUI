"""Strict app-native profile metadata for portable dynamic layouts."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from . import device_mapping, store


APP_METADATA_KEY = "_am_configurator"
APP_METADATA_SCHEMA_VERSION = 1
DYNAMIC_LAYOUT_SCHEMA_VERSION = 1
MAX_METADATA_BYTES = 64 * 1024
_APP_FIELDS = {"schema_version", "dynamic_layout"}
_LAYOUT_FIELDS = {
    "schema_version",
    "product_id",
    "keymap_signature",
    "key_layout",
}
_SIGNATURE = re.compile(r"^keymap:v1:[0-9a-f]{64}$")
_IGNORED_WARNING = (
    "Saved AM Configurator layout metadata was ignored because it is invalid. "
    "Per-key editing stays unavailable until exact layout evidence is available."
)


def _profile_product_id(config: object) -> str:
    if not isinstance(config, dict):
        raise ValueError("The profile is not a configuration object.")
    product_info = config.get("product_info")
    if not isinstance(product_info, dict):
        raise ValueError("The profile has no product ID.")
    product = product_info.get("product_id")
    if not isinstance(product, str) or not product.strip():
        raise ValueError("The profile has no product ID.")
    return product


def _canonical_product_id(product_id: str) -> str:
    return str(device_mapping.device_descriptor(product_id)["product_id"])


def _is_dynamic_product(product_id: str) -> bool:
    try:
        return device_mapping.led_model(product_id) == "NEON"
    except ValueError:
        return False


def _bounded_metadata(value: object) -> None:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Dynamic layout metadata is not JSON-safe.") from exc
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError("Dynamic layout metadata is oversized.")


def _validate_dynamic_layout(value: object, product_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _LAYOUT_FIELDS:
        raise ValueError("Dynamic layout metadata has unsupported fields.")
    if type(value.get("schema_version")) is not int or value["schema_version"] != DYNAMIC_LAYOUT_SCHEMA_VERSION:
        raise ValueError("Dynamic layout metadata has an unsupported version.")
    metadata_product = value.get("product_id")
    if not isinstance(metadata_product, str):
        raise ValueError("Dynamic layout metadata has no product ID.")
    canonical_product = _canonical_product_id(product_id)
    if metadata_product != canonical_product or not _is_dynamic_product(product_id):
        raise ValueError("Dynamic layout metadata belongs to another product.")
    layout = value.get("key_layout")
    if not isinstance(layout, list):
        raise ValueError("Dynamic layout metadata has no key projection.")
    canonical = device_mapping.canonical_dynamic_key_layout(product_id, layout)
    if canonical is None:
        raise ValueError("Dynamic layout metadata has an invalid key projection.")
    canonical_layout = [dict(item) for item in canonical]
    if layout != canonical_layout:
        raise ValueError("Dynamic layout metadata is not canonical.")
    signature = value.get("keymap_signature")
    descriptor = device_mapping.device_descriptor(
        product_id,
        key_layout=canonical_layout,
    )
    expected = descriptor["keymap"]["signature"]
    if (
        not isinstance(signature, str)
        or _SIGNATURE.fullmatch(signature) is None
        or signature != expected
    ):
        raise ValueError("Dynamic layout metadata signature does not match.")
    return {
        "schema_version": DYNAMIC_LAYOUT_SCHEMA_VERSION,
        "product_id": canonical_product,
        "keymap_signature": signature,
        "key_layout": canonical_layout,
    }


def build_dynamic_layout(product_id: str, key_layout: object) -> dict[str, Any]:
    canonical = device_mapping.canonical_dynamic_key_layout(product_id, key_layout)
    if canonical is None:
        raise ValueError("Exact dynamic keyboard layout evidence is unavailable.")
    canonical_layout = [dict(item) for item in canonical]
    descriptor = device_mapping.device_descriptor(
        product_id,
        key_layout=canonical_layout,
    )
    signature = descriptor["keymap"]["signature"]
    if not isinstance(signature, str):
        raise ValueError("Exact dynamic keyboard layout evidence is unavailable.")
    evidence = {
        "schema_version": DYNAMIC_LAYOUT_SCHEMA_VERSION,
        "product_id": descriptor["product_id"],
        "keymap_signature": signature,
        "key_layout": canonical_layout,
    }
    _bounded_metadata(
        {
            "schema_version": APP_METADATA_SCHEMA_VERSION,
            "dynamic_layout": evidence,
        }
    )
    return evidence


def remember_dynamic_layout(product_id: str, key_layout: object) -> dict[str, Any]:
    evidence = build_dynamic_layout(product_id, key_layout)
    return remember_dynamic_evidence(evidence)


def remember_dynamic_evidence(evidence: object) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise ValueError("Dynamic layout evidence is invalid.")
    product_id = evidence.get("product_id")
    if not isinstance(product_id, str):
        raise ValueError("Dynamic layout evidence has no product ID.")
    canonical = _validate_dynamic_layout(evidence, product_id)

    def validate_existing(value: object) -> dict[str, Any]:
        return _validate_dynamic_layout(value, canonical["product_id"])

    store.remember_layout_evidence(
        canonical["product_id"],
        canonical,
        validate_existing=validate_existing,
    )
    return canonical


def _embedded_layout(config: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    if APP_METADATA_KEY not in config:
        return None, False
    metadata = config[APP_METADATA_KEY]
    _bounded_metadata(metadata)
    if not isinstance(metadata, dict) or set(metadata) != _APP_FIELDS:
        raise ValueError("AM Configurator metadata has unsupported fields.")
    if type(metadata.get("schema_version")) is not int or metadata["schema_version"] != APP_METADATA_SCHEMA_VERSION:
        raise ValueError("AM Configurator metadata has an unsupported version.")
    return _validate_dynamic_layout(
        metadata.get("dynamic_layout"),
        _profile_product_id(config),
    ), True


def embedded_layout_evidence(config: object) -> dict[str, Any] | None:
    if not isinstance(config, dict):
        return None
    try:
        evidence, _present = _embedded_layout(config)
    except ValueError:
        return None
    return copy.deepcopy(evidence)


def _remembered_layouts(product_id: str) -> list[dict[str, Any]]:
    payload = store.load_layout_evidence(_canonical_product_id(product_id))
    if payload is None:
        return []
    if (
        set(payload) != {"schema_version", "layouts"}
        or payload.get("schema_version") != store.LAYOUT_EVIDENCE_SCHEMA_VERSION
        or not isinstance(payload.get("layouts"), list)
        or len(payload["layouts"]) > store.LAYOUT_EVIDENCE_MAX
    ):
        raise ValueError("Remembered layout evidence is invalid.")
    layouts: list[dict[str, Any]] = []
    signatures: set[str] = set()
    for value in payload["layouts"]:
        evidence = _validate_dynamic_layout(value, product_id)
        signature = evidence["keymap_signature"]
        if signature in signatures:
            raise ValueError("Remembered layout evidence contains duplicates.")
        signatures.add(signature)
        layouts.append(evidence)
    return layouts


def _public_evidence(evidence: dict[str, Any], source: str) -> dict[str, Any]:
    return {**copy.deepcopy(evidence), "source": source}


def resolve_layout_evidence(
    config: object,
    *,
    preferred_signature: object = None,
) -> dict[str, Any]:
    try:
        product_id = _profile_product_id(config)
    except ValueError:
        return {"evidence": None, "warning": None}
    if not _is_dynamic_product(product_id):
        return {"evidence": None, "warning": None}
    assert isinstance(config, dict)
    try:
        embedded, present = _embedded_layout(config)
    except ValueError:
        return {"evidence": None, "warning": _IGNORED_WARNING}
    if embedded is not None:
        warning = None
        try:
            remember_dynamic_evidence(embedded)
        except (OSError, ValueError):
            warning = (
                "This profile contains exact per-key layout evidence, but the app "
                "could not remember it locally."
            )
        return {
            "evidence": _public_evidence(embedded, "embedded"),
            "warning": warning,
        }
    if present:
        return {"evidence": None, "warning": _IGNORED_WARNING}
    try:
        remembered = _remembered_layouts(product_id)
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "evidence": None,
            "warning": (
                "Remembered per-key layout evidence could not be loaded. Connect "
                "and read the keyboard to restore it."
            ),
        }
    if preferred_signature is not None:
        if not isinstance(preferred_signature, str) or _SIGNATURE.fullmatch(preferred_signature) is None:
            return {"evidence": None, "warning": _IGNORED_WARNING}
        selected = next(
            (
                item
                for item in remembered
                if item["keymap_signature"] == preferred_signature
            ),
            None,
        )
        if selected is None:
            return {
                "evidence": None,
                "warning": (
                    "The selected keyboard layout has not been validated locally. "
                    "Read the keyboard before using its per-key surface."
                ),
            }
        return {
            "evidence": _public_evidence(selected, "remembered"),
            "warning": None,
        }
    if len(remembered) == 1:
        return {
            "evidence": _public_evidence(remembered[0], "remembered"),
            "warning": None,
        }
    if len(remembered) > 1:
        return {
            "evidence": None,
            "warning": (
                "More than one exact per-key layout is remembered for this keyboard. "
                "Connect and read the matching keyboard to choose safely."
            ),
        }
    return {
        "evidence": None,
        "warning": (
            "This profile has no exact per-key layout evidence. Head lighting, "
            "macros, keymap data, Library, and Save remain available."
        ),
    }


def attach_dynamic_layout(
    config: dict[str, Any],
    evidence: object,
) -> dict[str, Any]:
    product_id = _profile_product_id(config)
    canonical = _validate_dynamic_layout(evidence, product_id)
    result = copy.deepcopy(config)
    result.pop(APP_METADATA_KEY, None)
    result[APP_METADATA_KEY] = {
        "schema_version": APP_METADATA_SCHEMA_VERSION,
        "dynamic_layout": canonical,
    }
    _bounded_metadata(result[APP_METADATA_KEY])
    return result


def portable_profile(
    config: dict[str, Any],
    *,
    preferred_signature: object = None,
    key_layout: object = None,
) -> dict[str, Any]:
    product_id = _profile_product_id(config)
    result = copy.deepcopy(config)
    result.pop(APP_METADATA_KEY, None)
    if not _is_dynamic_product(product_id):
        return {"config": result, "evidence": None, "warning": None}

    warning = None
    evidence: dict[str, Any] | None = None
    source = "remembered"
    if key_layout is not None:
        connected = build_dynamic_layout(product_id, key_layout)
        try:
            embedded, _present = _embedded_layout(config)
        except ValueError:
            embedded = None
        if embedded is not None:
            if embedded["keymap_signature"] != connected["keymap_signature"]:
                raise ValueError(
                    "The connected keyboard layout does not match the exact "
                    "layout embedded in this profile."
                )
            evidence = embedded
            source = "embedded"
        else:
            evidence = connected
            source = "connected"
        try:
            remember_dynamic_evidence(evidence)
        except (OSError, ValueError):
            warning = "The exact layout could not be remembered locally."
    else:
        resolved = resolve_layout_evidence(
            config,
            preferred_signature=preferred_signature,
        )
        public = resolved["evidence"]
        warning = resolved["warning"]
        if public is not None:
            source = str(public["source"])
            evidence = {field: copy.deepcopy(public[field]) for field in _LAYOUT_FIELDS}
    if evidence is None:
        return {"config": result, "evidence": None, "warning": warning}
    portable = attach_dynamic_layout(result, evidence)
    return {
        "config": portable,
        "evidence": _public_evidence(evidence, source),
        "warning": warning,
    }
