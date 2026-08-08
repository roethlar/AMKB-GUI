"""Read-only support reports for devices this build does not fully drive.

Used when something is plugged in but is not a supported Angry Miao family, so
the user can open a GitHub issue with a sanitized snapshot. Never opens a
write path on the keyboard.
"""

from __future__ import annotations

import platform
import re
from typing import Any, Mapping

from am_configurator import __version__
from am_configurator import device_mapping

# Host-local or identity-bearing keys must not leave the machine in a report.
_REDACT_KEYS = frozenset(
    {
        "path",
        "address",
        "port",
        "serial_number",
        "serial",
        "hwid",
        "location",
        "manufacturer",
        "interface_number",
        "usage",
        "usage_page",
        "release_number",
        "bus_type",
    }
)

# Values that look like absolute paths or user home directories.
_PATH_PATTERN = re.compile(
    r"(/(?:Users|home|var|tmp|private|dev)/[^\s\"']+)"
    r"|([A-Za-z]:\\[^\s\"']+)",
    re.IGNORECASE,
)

_REPORT_SCHEMA = 1


def is_supported_product(product_id: object) -> bool:
    """True when this build has a real family mapping for the product id."""

    if not isinstance(product_id, str) or not product_id.strip():
        return False
    try:
        model = device_mapping.led_model(product_id.strip())
    except ValueError:
        return False
    try:
        device_mapping.family_spec(model)
    except KeyError:
        return False
    return True


def _redact_string(value: str) -> str:
    if not value:
        return value
    return _PATH_PATTERN.sub("[redacted-path]", value)


def _sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, (bytes, bytearray)):
        return "[redacted-bytes]"
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_value(item)
            for key, item in value.items()
            if str(key) not in _REDACT_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:200]


def sanitize_device(device: Mapping[str, Any]) -> dict[str, Any]:
    """Project one `/api/devices` entry into a report-safe object."""

    product_id = device.get("product_id")
    product = product_id.strip() if isinstance(product_id, str) else ""
    supported = is_supported_product(product) if product else False

    safe: dict[str, Any] = {
        "supported": supported,
        "is_keyboard": bool(device.get("is_keyboard")),
        "transport": str(device.get("transport") or "") or None,
        "product_id": product or None,
        "version": device.get("version"),
        "pages": device.get("pages"),
        "writable": device.get("writable"),
    }

    for key in (
        "usb_vendor_id",
        "usb_product_id",
        "vendor_id",
        "product_name",
        "interface",
        "macro_count",
        "macro_buffer_bytes",
        "layer_count",
    ):
        if key in device and device[key] is not None:
            safe[key] = _sanitize_value(device[key])

    # Drop Nones for a compact report.
    return {key: value for key, value in safe.items() if value is not None}


def classify_devices(
    devices: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, list[dict[str, Any]]]:
    """Split sanitized devices into supported / unsupported / other."""

    supported: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for device in devices:
        sanitized = sanitize_device(device)
        if sanitized.get("is_keyboard") and sanitized.get("supported"):
            supported.append(sanitized)
        elif sanitized.get("is_keyboard"):
            unsupported.append(sanitized)
        else:
            other.append(sanitized)
    return {
        "supported_keyboards": supported,
        "unsupported_keyboards": unsupported,
        "other_devices": other,
    }


def build_support_report(
    devices: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    app_version: str | None = None,
    platform_name: str | None = None,
    platform_release: str | None = None,
    platform_machine: str | None = None,
) -> dict[str, Any]:
    """Build a GitHub-ready support report from a device scan payload."""

    groups = classify_devices(devices)
    unsupported = groups["unsupported_keyboards"]
    supported = groups["supported_keyboards"]

    if unsupported:
        headline = "New keyboard model detected"
        summary = (
            "A keyboard is connected that this build does not fully support. "
            "The report below is read-only and has host paths removed."
        )
    elif supported:
        headline = "Supported keyboard connected"
        summary = "All detected keyboards are families this build already drives."
    elif devices:
        headline = "USB devices present, no keyboard recognized"
        summary = (
            "Something is connected, but nothing reported itself as a keyboard "
            "this app can drive."
        )
    else:
        headline = "No devices detected"
        summary = "Nothing was found on a full device scan."

    return {
        "schema_version": _REPORT_SCHEMA,
        "headline": headline,
        "summary": summary,
        "app_version": app_version or __version__,
        "platform": {
            "system": platform_name or platform.system(),
            "release": platform_release or platform.release(),
            "machine": platform_machine or platform.machine(),
        },
        "counts": {
            "supported_keyboards": len(supported),
            "unsupported_keyboards": len(unsupported),
            "other_devices": len(groups["other_devices"]),
        },
        "devices": groups,
        "known_limit": (
            "Serial-protocol LED geometry cannot be probed; lighting for a new "
            "serial family still needs a physical board or vendor source."
        ),
    }


__all__ = [
    "build_support_report",
    "classify_devices",
    "is_supported_product",
    "sanitize_device",
]
