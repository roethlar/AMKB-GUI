"""Generic read-only VIA raw-HID transport for the OpenKeeb hub.

Unlike Vial, VIA firmware does not embed its definition.  A shallow raw-HID
candidate becomes a resolved VIA device only after a bounded user-imported
definition matches USB VID/PID and a mutation-refusing session proves the
protocol and active physical-layout options on that exact endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import hid_transport, hub_via, vial_keymap, vial_macros


class ViaTransportError(ValueError):
    """Live VIA data cannot be represented or read safely."""


@dataclass(frozen=True)
class ResolvedViaDevice:
    """Imported definition and read-only protocol proof pinned to an endpoint."""

    endpoint: hid_transport.ViaEndpointInfo
    definition: hub_via.ViaDefinition
    via_protocol: int
    layout_options: int
    keycode_spec: str | None


_MAX_LAYERS = 32
_MAX_MACROS = 128
_MAX_MACRO_BUFFER = 65_535


def list_devices() -> list[hid_transport.ViaEndpointInfo]:
    """List non-Vial raw-HID candidates without opening or transmitting."""

    return hid_transport.list_via_endpoints()


def device_json(info: hid_transport.ViaEndpointInfo) -> dict[str, Any]:
    """Public candidate metadata without exposing the operating-system path."""

    return {
        "address": info.address,
        "vid": info.usb_vendor_id,
        "pid": info.usb_product_id,
        "manufacturer": info.manufacturer_string,
        "usb_product": info.product_string,
        "interface": info.interface_number,
        "definition_required": True,
    }


def _probe(
    session, definition: hub_via.ViaDefinition
) -> tuple[int, int, str | None]:
    protocol = vial_keymap.read_via_protocol(session)
    if not 7 <= protocol <= 255:
        raise ViaTransportError(
            f"VIA protocol {protocol} is outside the supported range 7..255."
        )
    layout_options = (
        vial_keymap.read_layout_options(session)
        if definition.choice_counts
        else 0
    )
    hub_via.project_layout(definition, layout_options)
    keycode_spec = (
        vial_keymap.read_keycode_spec(session) if protocol >= 13 else None
    )
    return protocol, layout_options, keycode_spec


def resolve_device(address: str, definition: object) -> ResolvedViaDevice:
    """Match one imported definition and prove VIA identity read-only."""

    imported = hub_via.load_definition(definition)
    endpoint = hid_transport.find_via_endpoint(address)
    if (endpoint.usb_vendor_id, endpoint.usb_product_id) != (
        imported.usb_vendor_id,
        imported.usb_product_id,
    ):
        raise hid_transport.HidIdentityError(
            "The imported VIA definition does not match this endpoint's USB VID/PID."
        )
    session = hid_transport.open_via_read(endpoint)
    try:
        protocol, layout_options, keycode_spec = _probe(session, imported)
    finally:
        session.close()
    return ResolvedViaDevice(
        endpoint=endpoint,
        definition=imported,
        via_protocol=protocol,
        layout_options=layout_options,
        keycode_spec=keycode_spec,
    )


def _capacity(session, protocol: int) -> vial_macros.MacroCapacity:
    if protocol < 8:
        return vial_macros.MacroCapacity(count=0, buffer_bytes=0)
    capacity = vial_macros.read_capacity(session)
    if not 0 <= capacity.count <= _MAX_MACROS:
        raise ViaTransportError(
            f"VIA macro count must be in 0..{_MAX_MACROS}."
        )
    if not capacity.count <= capacity.buffer_bytes <= _MAX_MACRO_BUFFER:
        raise ViaTransportError(
            "VIA macro buffer size is inconsistent with its slot count."
        )
    return capacity


def _read_snapshot(resolved: ResolvedViaDevice) -> hub_via.ViaSnapshot:
    definition = resolved.definition
    session = hid_transport.open_via_read(resolved.endpoint)
    try:
        protocol, layout_options, keycode_spec = _probe(session, definition)
        if (
            protocol != resolved.via_protocol
            or layout_options != resolved.layout_options
            or keycode_spec != resolved.keycode_spec
        ):
            raise hid_transport.HidIdentityError(
                "The VIA endpoint changed after its definition was resolved."
            )
        layer_count = (
            vial_keymap.read_layer_count(session) if protocol >= 8 else 4
        )
        if not 1 <= layer_count <= _MAX_LAYERS:
            raise ViaTransportError(
                f"VIA layer count must be in 1..{_MAX_LAYERS}."
            )
        capacity = _capacity(session, protocol)
        keymap = vial_keymap.read_via_keymap_buffer(
            session,
            via_protocol=protocol,
            layers=layer_count,
            rows=definition.matrix_rows,
            cols=definition.matrix_cols,
        )
        macros = (
            vial_macros.read_macro_buffer(session, capacity=capacity)
            if protocol >= 8
            else b""
        )
    finally:
        session.close()
    return hub_via.load_snapshot(
        {
            "definition": definition.definition,
            "via_protocol": protocol,
            "keycode_spec": keycode_spec,
            "usb_vendor_id": resolved.endpoint.usb_vendor_id,
            "usb_product_id": resolved.endpoint.usb_product_id,
            "layout_options": layout_options,
            "layer_count": layer_count,
            "keymap_hex": keymap.hex(),
            "macro_count": capacity.count,
            "macro_buffer_bytes": capacity.buffer_bytes,
            "macro_hex": macros.hex(),
        }
    )


def read_snapshot(address: str, definition: object) -> hub_via.ViaSnapshot:
    """Resolve and read one complete VIA snapshot without a mutating command."""

    return _read_snapshot(resolve_device(address, definition))


def read_hub_profile(
    address: str, definition: object, *, origin: str = "device"
) -> dict[str, Any]:
    """Read one VIA keyboard directly into the common hub profile."""

    return hub_via.build_hub_profile(
        read_snapshot(address, definition), origin=origin
    )
