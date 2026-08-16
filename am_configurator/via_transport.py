"""Definition-bound VIA raw-HID transport for the OpenKeeb hub.

Unlike Vial, VIA firmware does not embed its definition.  A shallow raw-HID
candidate becomes a resolved VIA device only after a bounded user-imported
definition matches USB VID/PID. Reads use a mutation-refusing session. Writes
require a pure plan, exact typed phrase, connection-scoped endpoint reproof,
same-handle protocol/capacity checks, a narrow command allowlist, and read-back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import hid_transport, hub_via, vial_keymap, vial_macros


class ViaTransportError(ValueError):
    """Live VIA data cannot be represented, read, or written safely."""


class ViaAcceptedWriteError(RuntimeError):
    """A VIA keyboard accepted bytes before later write/read-back failure."""

    def __init__(
        self, message: str, *, keymap_bytes: int, macro_bytes: int
    ) -> None:
        super().__init__(message)
        self.keymap_bytes = keymap_bytes
        self.macro_bytes = macro_bytes


@dataclass(frozen=True)
class ResolvedViaDevice:
    """Imported definition and read-only protocol proof pinned to an endpoint."""

    endpoint: hid_transport.ViaEndpointInfo
    definition: hub_via.ViaDefinition
    via_protocol: int
    layout_options: int
    keycode_spec: str | None


@dataclass(frozen=True)
class PreparedViaWrite:
    """Read-only target snapshot and pure plan pinned to one VIA endpoint."""

    endpoint: hid_transport.ViaEndpointInfo
    definition: hub_via.ViaDefinition
    target: hub_via.ViaSnapshot
    plan: hub_via.ViaWritePlan

    @property
    def confirmation(self) -> str:
        return hid_transport.via_write_confirmation(
            self.endpoint, self.definition.name
        )


@dataclass(frozen=True)
class ViaWriteReceipt:
    """Exact accepted byte counts and planner transfer report."""

    keymap_bytes: int
    macro_bytes: int
    report: dict[str, Any]


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


def prepare_write(
    address: str, definition: object, profile: object
) -> PreparedViaWrite:
    """Read the exact target and build a pure plan without sending a setter."""

    resolved = resolve_device(address, definition)
    target = _read_snapshot(resolved)
    plan = hub_via.plan_via_write(profile, target=target)
    if plan.keymap_buffer is None and plan.macro_buffer is None:
        raise ViaTransportError(
            "The hub profile has no VIA keymap or macro data to write."
        )
    return PreparedViaWrite(
        endpoint=resolved.endpoint,
        definition=resolved.definition,
        target=target,
        plan=plan,
    )


def _matches_endpoint(
    info: hid_transport.ViaEndpointInfo, prepared: PreparedViaWrite
) -> bool:
    return (
        info == prepared.endpoint
        and info.usb_vendor_id == prepared.target.usb_vendor_id
        and info.usb_product_id == prepared.target.usb_product_id
        and prepared.definition.definition_hash == prepared.target.definition_hash
        and prepared.definition.name == prepared.target.name
        and prepared.definition.matrix_rows == prepared.target.matrix_rows
        and prepared.definition.matrix_cols == prepared.target.matrix_cols
    )


def _revalidate_write(
    session, prepared: PreparedViaWrite
) -> vial_macros.MacroCapacity:
    target = prepared.target
    protocol, layout_options, keycode_spec = _probe(
        session, prepared.definition
    )
    layer_count = vial_keymap.read_layer_count(session) if protocol >= 8 else 4
    capacity = _capacity(session, protocol)
    if (
        protocol != target.via_protocol
        or layout_options != target.layout_options
        or keycode_spec != target.keycode_spec
        or layer_count != target.layer_count
        or capacity.count != target.macro_count
        or capacity.buffer_bytes != target.macro_buffer_bytes
    ):
        raise hid_transport.HidIdentityError(
            "The VIA endpoint protocol, layout, or buffer limits changed "
            "after preflight."
        )
    keymap = prepared.plan.keymap_buffer
    if keymap is not None and len(keymap) != len(target.keymap_buffer):
        raise ViaTransportError("The planned VIA keymap no longer fits target.")
    macros = prepared.plan.macro_buffer
    if macros is not None and len(macros) != capacity.buffer_bytes:
        raise ViaTransportError("The planned VIA macro buffer no longer fits target.")
    return capacity


def execute_write(
    prepared: PreparedViaWrite, *, confirmation: str
) -> ViaWriteReceipt:
    """Execute one endpoint-bound plan and require exact complete read-back."""

    if confirmation != prepared.confirmation:
        raise hid_transport.HidIdentityError(
            f"Type {prepared.confirmation} exactly to confirm writing this keyboard."
        )
    current = hid_transport.find_via_endpoint(prepared.endpoint.address)
    if not _matches_endpoint(current, prepared):
        raise hid_transport.HidIdentityError(
            "The connected VIA endpoint no longer matches the preflight snapshot."
        )
    approval = hid_transport.approve_via_write(
        current,
        definition_name=prepared.definition.name,
        definition_hash=prepared.definition.definition_hash,
        confirmation=confirmation,
    )
    session = hid_transport.open_via_approved(approval)
    keymap_written = 0
    macros_written = 0
    try:
        capacity = _revalidate_write(session, prepared)
        try:
            if prepared.plan.keymap_buffer is not None:
                keymap_written = vial_keymap.write_via_keymap_buffer(
                    session,
                    prepared.plan.keymap_buffer,
                    via_protocol=prepared.target.via_protocol,
                    layers=prepared.target.layer_count,
                    rows=prepared.target.matrix_rows,
                    cols=prepared.target.matrix_cols,
                )
            if prepared.plan.macro_buffer is not None:
                macros_written = vial_macros.write_macro_buffer(
                    session,
                    prepared.plan.macro_buffer,
                    capacity=capacity,
                )
        except vial_keymap.ViaKeymapAcceptedWriteError as error:
            raise ViaAcceptedWriteError(
                str(error),
                keymap_bytes=error.keymap_bytes,
                macro_bytes=macros_written,
            ) from error
        except vial_macros.MacroAcceptedWriteError as error:
            raise ViaAcceptedWriteError(
                str(error),
                keymap_bytes=keymap_written,
                macro_bytes=error.macro_bytes,
            ) from error

        if prepared.plan.keymap_buffer is not None:
            readback = vial_keymap.read_via_keymap_buffer(
                session,
                via_protocol=prepared.target.via_protocol,
                layers=prepared.target.layer_count,
                rows=prepared.target.matrix_rows,
                cols=prepared.target.matrix_cols,
            )
            if readback != prepared.plan.keymap_buffer:
                raise ViaAcceptedWriteError(
                    "The VIA keyboard accepted keymap bytes but read-back differed.",
                    keymap_bytes=keymap_written,
                    macro_bytes=macros_written,
                )
        if prepared.plan.macro_buffer is not None:
            readback = vial_macros.read_macro_buffer(session, capacity=capacity)
            if readback != prepared.plan.macro_buffer:
                raise ViaAcceptedWriteError(
                    "The VIA keyboard accepted macro bytes but read-back differed.",
                    keymap_bytes=keymap_written,
                    macro_bytes=macros_written,
                )
    except ViaAcceptedWriteError:
        raise
    except Exception as error:
        if keymap_written or macros_written:
            raise ViaAcceptedWriteError(
                "The VIA keyboard accepted part of the write before it failed.",
                keymap_bytes=keymap_written,
                macro_bytes=macros_written,
            ) from error
        raise
    finally:
        session.close()
    return ViaWriteReceipt(
        keymap_bytes=keymap_written,
        macro_bytes=macros_written,
        report=prepared.plan.report,
    )


def write_hub_profile(
    address: str,
    definition: object,
    profile: object,
    *,
    confirmation: str,
) -> ViaWriteReceipt:
    """Prepare again inside this request, then execute the endpoint-bound plan."""

    return execute_write(
        prepare_write(address, definition, profile),
        confirmation=confirmation,
    )
