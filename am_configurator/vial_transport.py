"""Generic Vial HID transport for the OpenKeeb hub spoke.

Discovery and reads are constrained to a read-only raw-HID session.  A write
is a separate, explicit path: plan against a pinned snapshot, type the board's
embedded definition name, re-enumerate the same connection-scoped endpoint,
re-prove its firmware UID and definition hash on the open handle, validate all
buffer limits, complete Vial's physical unlock, then transmit and read back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import hid_transport, hub_vial, vial_keymap, vial_macros


_MAX_MATRIX_AXIS = 32
_MAX_KEYS_PER_LAYER = 512
_MAX_LAYERS = 32
_MAX_MACROS = 128
_MAX_MACRO_BUFFER = 65535


class VialTransportError(ValueError):
    """Live Vial data cannot be represented or safely transferred."""


class VialAcceptedWriteError(RuntimeError):
    """A device accepted bytes before a later write/read-back failure."""

    def __init__(self, message: str, *, keymap_bytes: int, macro_bytes: int) -> None:
        super().__init__(message)
        self.keymap_bytes = keymap_bytes
        self.macro_bytes = macro_bytes


@dataclass(frozen=True)
class PreparedVialWrite:
    """Pure plan pinned to the endpoint and snapshot used to build it."""

    endpoint: hid_transport.VialDeviceInfo
    target: hub_vial.VialSnapshot
    plan: hub_vial.VialWritePlan

    @property
    def confirmation(self) -> str:
        return self.target.name


@dataclass(frozen=True)
class VialWriteReceipt:
    """Exact accepted byte counts plus the planner's transfer report."""

    keymap_bytes: int
    macro_bytes: int
    report: dict[str, Any]


def list_devices(*, deep: bool = False) -> list[hid_transport.VialDeviceInfo]:
    """List generic Vial raw-HID endpoints; shallow mode opens nothing."""
    return hid_transport.list_vial_devices(deep=deep)


def device_json(info: hid_transport.VialDeviceInfo) -> dict[str, Any]:
    """Public endpoint metadata without exposing the operating-system path."""
    return {
        "address": info.address,
        "vid": info.usb_vendor_id,
        "pid": info.usb_product_id,
        "manufacturer": info.manufacturer_string,
        "usb_product": info.product_string,
        "name": info.name,
        "vial_protocol": info.protocol_version or None,
        "definition_hash": info.definition_hash or None,
        "identity_error": info.identity_error,
    }


def _integer(value: object, label: str, *, low: int, high: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not low <= value <= high
    ):
        raise VialTransportError(f"{label} must be an integer in {low}..{high}.")
    return value


def _bounded_shape(
    info: hid_transport.VialDeviceInfo,
    *,
    via_protocol: int,
    layer_count: int,
    capacity: vial_macros.MacroCapacity,
) -> tuple[int, int]:
    """Bound untrusted sizes before allocating/reading device buffers.

    ``hub_vial.load_snapshot`` remains the canonical validation.  These are
    pre-read ceilings so a hostile device cannot force an allocation before
    the canonical validator sees the completed record.
    """
    definition = info.definition
    if not isinstance(definition, dict):
        raise VialTransportError("The Vial definition is unavailable.")
    try:
        matrix = definition["matrix"]
        rows_value = matrix["rows"]
        cols_value = matrix["cols"]
    except (KeyError, TypeError) as error:
        raise VialTransportError(
            "The Vial definition must declare its matrix before buffers are read."
        ) from error
    rows = _integer(rows_value, "Vial matrix rows", low=1, high=_MAX_MATRIX_AXIS)
    cols = _integer(cols_value, "Vial matrix columns", low=1, high=_MAX_MATRIX_AXIS)
    if rows * cols > _MAX_KEYS_PER_LAYER:
        raise VialTransportError(
            f"The Vial matrix has {rows * cols} cells; "
            f"the hub supports at most {_MAX_KEYS_PER_LAYER}."
        )
    _integer(via_protocol, "VIA protocol", low=1, high=255)
    _integer(info.protocol_version, "Vial protocol", low=0, high=6)
    _integer(layer_count, "Vial layer count", low=1, high=_MAX_LAYERS)
    _integer(capacity.count, "Vial macro count", low=0, high=_MAX_MACROS)
    _integer(
        capacity.buffer_bytes,
        "Vial macro buffer size",
        low=capacity.count,
        high=_MAX_MACRO_BUFFER,
    )
    return rows, cols


def _read_snapshot(
    info: hid_transport.VialDeviceInfo,
) -> hub_vial.VialSnapshot:
    if not info.writable or info.definition is None:
        raise hid_transport.HidIdentityError(
            info.identity_error or "The Vial keyboard identity is incomplete."
        )
    session = hid_transport.open_vial_read(info)
    try:
        via_protocol = vial_keymap.read_via_protocol(session)
        layer_count = vial_keymap.read_layer_count(session)
        capacity = vial_macros.read_capacity(session)
        rows, cols = _bounded_shape(
            info,
            via_protocol=via_protocol,
            layer_count=layer_count,
            capacity=capacity,
        )
        keymap = vial_keymap.read_keymap_buffer(
            session, size=layer_count * rows * cols * 2
        )
        macro_buffer = vial_macros.read_macro_buffer(session, capacity=capacity)
    finally:
        session.close()
    return hub_vial.load_snapshot(
        {
            "definition": info.definition,
            "via_protocol": via_protocol,
            "vial_protocol": info.protocol_version,
            "firmware_uid": info.firmware_uid,
            "usb_vendor_id": info.usb_vendor_id,
            "usb_product_id": info.usb_product_id,
            "layer_count": layer_count,
            "keymap_hex": keymap.hex(),
            "macro_count": capacity.count,
            "macro_buffer_bytes": capacity.buffer_bytes,
            "macro_hex": macro_buffer.hex(),
        }
    )


def read_snapshot(address: str) -> hub_vial.VialSnapshot:
    """Read and validate one complete generic Vial snapshot."""
    return _read_snapshot(hid_transport.find_vial(address))


def read_hub_profile(address: str, *, origin: str = "device") -> dict[str, Any]:
    """Read one Vial keyboard directly into the common hub profile."""
    return hub_vial.build_hub_profile(read_snapshot(address), origin=origin)


def prepare_write(address: str, profile: object) -> PreparedVialWrite:
    """Read the target and produce a pure write plan; never unlock or mutate."""
    endpoint = hid_transport.find_vial(address)
    target = _read_snapshot(endpoint)
    plan = hub_vial.plan_vial_write(profile, target=target)
    return PreparedVialWrite(endpoint=endpoint, target=target, plan=plan)


def _matches_target(
    info: hid_transport.VialDeviceInfo, prepared: PreparedVialWrite
) -> bool:
    target = prepared.target
    original = prepared.endpoint
    return (
        info.writable
        and info.address == original.address
        and info.path == original.path
        and info.usb_vendor_id == target.usb_vendor_id
        and info.usb_product_id == target.usb_product_id
        and info.name == target.name
        and info.firmware_uid == target.firmware_uid
        and info.protocol_version == target.vial_protocol
        and info.definition_hash == target.definition_hash
    )


def _revalidate_limits(
    session,
    prepared: PreparedVialWrite,
) -> vial_macros.MacroCapacity:
    target = prepared.target
    via_protocol = vial_keymap.read_via_protocol(session)
    layer_count = vial_keymap.read_layer_count(session)
    capacity = vial_macros.read_capacity(session)
    _bounded_shape(
        prepared.endpoint,
        via_protocol=via_protocol,
        layer_count=layer_count,
        capacity=capacity,
    )
    if (
        via_protocol != target.via_protocol
        or layer_count != target.layer_count
        or capacity.count != target.macro_count
        or capacity.buffer_bytes != target.macro_buffer_bytes
    ):
        raise hid_transport.HidIdentityError(
            "The Vial keyboard's protocol or buffer limits changed after preflight."
        )
    keymap = prepared.plan.keymap_buffer
    if keymap is not None and len(keymap) != len(target.keymap_buffer):
        raise VialTransportError("The planned keymap buffer no longer fits the target.")
    macros = prepared.plan.macro_buffer
    if macros is not None and len(macros) != capacity.buffer_bytes:
        raise VialTransportError("The planned macro buffer no longer fits the target.")
    if keymap is None and macros is None:
        raise VialTransportError("The hub profile has no Vial keymap or macro data to write.")
    return capacity


def execute_write(
    prepared: PreparedVialWrite, *, confirmation: str
) -> VialWriteReceipt:
    """Execute one prepared write after identity, typed, and physical gates."""
    if confirmation != prepared.confirmation:
        raise hid_transport.HidIdentityError(
            f"Type {prepared.confirmation} exactly to confirm writing this keyboard."
        )
    current = hid_transport.find_vial(prepared.endpoint.address)
    if not _matches_target(current, prepared):
        raise hid_transport.HidIdentityError(
            "The connected Vial endpoint no longer matches the preflight snapshot."
        )
    approval = hid_transport.approve_vial_write(current, confirmation)
    session = hid_transport.open_vial_approved(approval)
    keymap_written = 0
    macros_written = 0
    try:
        capacity = _revalidate_limits(session, prepared)
        vial_keymap.ensure_unlocked(session)
        try:
            if prepared.plan.keymap_buffer is not None:
                keymap_written = vial_keymap.write_keymap_buffer(
                    session,
                    prepared.plan.keymap_buffer,
                    require_unlocked=False,
                )
            if prepared.plan.macro_buffer is not None:
                macros_written = vial_macros.write_macro_buffer(
                    session,
                    prepared.plan.macro_buffer,
                    capacity=capacity,
                )
            if prepared.plan.keymap_buffer is not None:
                readback = vial_keymap.read_keymap_buffer(
                    session, size=len(prepared.plan.keymap_buffer)
                )
                if readback != prepared.plan.keymap_buffer:
                    raise VialAcceptedWriteError(
                        "The keyboard accepted keymap bytes but read-back differed.",
                        keymap_bytes=keymap_written,
                        macro_bytes=macros_written,
                    )
            if prepared.plan.macro_buffer is not None:
                readback = vial_macros.read_macro_buffer(session, capacity=capacity)
                if readback != prepared.plan.macro_buffer:
                    raise VialAcceptedWriteError(
                        "The keyboard accepted macro bytes but read-back differed.",
                        keymap_bytes=keymap_written,
                        macro_bytes=macros_written,
                    )
        except VialAcceptedWriteError:
            raise
        except Exception as error:
            if keymap_written or macros_written:
                raise VialAcceptedWriteError(
                    "The keyboard accepted part of the Vial write before it failed.",
                    keymap_bytes=keymap_written,
                    macro_bytes=macros_written,
                ) from error
            raise
    finally:
        session.close()
    return VialWriteReceipt(
        keymap_bytes=keymap_written,
        macro_bytes=macros_written,
        report=prepared.plan.report,
    )


def write_hub_profile(
    address: str, profile: object, *, confirmation: str
) -> VialWriteReceipt:
    """Convenience wrapper for one preflight-and-execute API request."""
    return execute_write(
        prepare_write(address, profile), confirmation=confirmation
    )
