"""Definition-bound VIA raw-HID transport for the OpenKeeb hub.

Unlike Vial, VIA firmware does not embed its definition.  A shallow raw-HID
candidate becomes a resolved VIA device only after a bounded user-imported
definition matches USB VID/PID. Reads use a mutation-refusing session. Writes
require a pure plan, exact typed phrase, connection-scoped endpoint reproof,
same-handle protocol/capacity checks, a narrow command allowlist, and read-back.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
import hashlib
from typing import Any

from . import (
    hid_transport,
    hub_profile,
    hub_via,
    via_lighting,
    vial_keymap,
    vial_macros,
)


class ViaTransportError(ValueError):
    """Live VIA data cannot be represented, read, or written safely."""


class ViaAcceptedWriteError(RuntimeError):
    """A VIA keyboard accepted bytes before later write/read-back failure."""

    def __init__(
        self,
        message: str,
        *,
        keymap_bytes: int,
        macro_bytes: int,
        lighting_changes: int = 0,
        lighting_saves: int = 0,
    ) -> None:
        super().__init__(message)
        self.keymap_bytes = keymap_bytes
        self.macro_bytes = macro_bytes
        self.lighting_changes = lighting_changes
        self.lighting_saves = lighting_saves


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
    lighting_plan: via_lighting.ViaLightingWritePlan
    lighting_backup: dict[str, Any] | None
    target_fingerprint: str
    report: dict[str, Any]

    @property
    def confirmation(self) -> str:
        return hid_transport.via_write_confirmation(
            self.endpoint, self.definition.name
        )


@dataclass(frozen=True)
class HubDocument:
    """One browser editor document derived from one live snapshot."""

    device: dict[str, Any]
    profile: dict[str, Any]
    layout: tuple[dict[str, int | float | str], ...]
    lighting_geometry: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ViaWriteReceipt:
    """Exact accepted byte counts and planner transfer report."""

    keymap_bytes: int
    macro_bytes: int
    lighting_changes: int
    lighting_saves: int
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


_CHANNEL_LIGHTING_CONTROLS = {
    "qmk_backlight": (1, {"brightness": 1, "effect_id": 2}),
    "qmk_rgblight": (
        2,
        {"brightness": 1, "effect_id": 2, "speed": 3, "color": 4},
    ),
    "qmk_rgb_matrix": (
        3,
        {"brightness": 1, "effect_id": 2, "speed": 3, "color": 4},
    ),
}
_LEGACY_LIGHTING_CONTROLS = {
    "qmk_backlight": {
        "brightness": via_lighting.QMK_BACKLIGHT_BRIGHTNESS,
        "effect_id": via_lighting.QMK_BACKLIGHT_EFFECT,
    },
    "qmk_rgblight": {
        "brightness": via_lighting.QMK_RGBLIGHT_BRIGHTNESS,
        "effect_id": via_lighting.QMK_RGBLIGHT_EFFECT,
        "speed": via_lighting.QMK_RGBLIGHT_EFFECT_SPEED,
        "color": via_lighting.QMK_RGBLIGHT_COLOR,
    },
}


def _lighting_context(
    resolved: ResolvedViaDevice,
) -> tuple[
    dict[str, Any],
    tuple[dict[str, int | float], ...],
    dict[str, int],
    tuple[tuple[int, ...], ...],
]:
    layout = hub_via.project_layout(
        resolved.definition,
        resolved.layout_options,
    )
    led_mapping = {
        f"K_R{item['matrix_row']}_C{item['matrix_col']}": int(item["led_index"])
        for item in layout
        if "led_index" in item
    }
    capabilities = via_lighting.capabilities_from_definition(
        resolved.definition.definition,
        via_protocol=resolved.via_protocol,
        led_mapping=led_mapping or None,
    )
    gets: list[tuple[int, ...]] = []
    for surface in capabilities["surfaces"]:
        if resolved.via_protocol >= 11:
            channel, commands = _CHANNEL_LIGHTING_CONTROLS[surface["generation"]]
            gets.extend(
                (channel, command)
                for field, command in commands.items()
                if ("effects" if field == "effect_id" else field) in surface
            )
        else:
            gets.extend(
                (value_id,)
                for field, value_id in _LEGACY_LIGHTING_CONTROLS.get(
                    surface["generation"], {}
                ).items()
                if ("effects" if field == "effect_id" else field) in surface
            )
        if "per_key" in surface:
            gets.append((0, 1))
    return capabilities, layout, led_mapping, tuple(dict.fromkeys(gets))


def _read_lighting(
    session,
    resolved: ResolvedViaDevice,
    capabilities: dict[str, Any],
    layout: tuple[dict[str, int | float], ...],
    led_mapping: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any] | None, tuple[dict[str, Any], ...]]:
    if not capabilities["surfaces"]:
        return capabilities, None, ()
    values: dict[str, dict[str, Any]] = {}
    for surface in capabilities["surfaces"]:
        state: dict[str, Any] = {}
        if resolved.via_protocol >= 11:
            channel, commands = _CHANNEL_LIGHTING_CONTROLS[surface["generation"]]
            for field, command in commands.items():
                capability_field = "effects" if field == "effect_id" else field
                if capability_field not in surface:
                    continue
                payload = vial_keymap.read_lighting_channel(
                    session,
                    channel,
                    command,
                )
                size = 2 if field == "color" else 1
                if len(payload) < size:
                    raise ViaTransportError("The VIA keyboard returned short lighting state.")
                state[field] = list(payload[:2]) if field == "color" else payload[0]
        else:
            for field, value_id in _LEGACY_LIGHTING_CONTROLS.get(
                surface["generation"], {}
            ).items():
                capability_field = "effects" if field == "effect_id" else field
                if capability_field not in surface:
                    continue
                payload = vial_keymap.read_lighting_value(session, value_id)
                size = 2 if field == "color" else 1
                if len(payload) < size:
                    raise ViaTransportError("The VIA keyboard returned short lighting state.")
                state[field] = list(payload[:2]) if field == "color" else payload[0]
        if "per_key" in surface:
            colors: dict[str, list[int]] = {}
            for key, led_index in led_mapping.items():
                payload = vial_keymap.read_lighting_channel(
                    session,
                    0,
                    1,
                    led_index,
                    1,
                )
                if len(payload) < 4 or payload[:2] != bytes([led_index, 1]):
                    raise ViaTransportError(
                        "The VIA keyboard returned mismatched per-key lighting state."
                    )
                colors[key] = list(payload[2:4])
            state["per_key"] = colors
        values[surface["id"]] = state

    capabilities = via_lighting.capabilities_from_definition(
        resolved.definition.definition,
        via_protocol=resolved.via_protocol,
        current=values,
        led_mapping=led_mapping or None,
    )
    lighting = via_lighting.state_from_values(capabilities, values)
    layout_by_key = {
        f"K_R{item['matrix_row']}_C{item['matrix_col']}": item for item in layout
    }
    geometry = tuple(
        {
            "surface_id": "rgb_matrix",
            "pixel_id": key,
            "led_index": led_index,
            "x": round(
                float(layout_by_key[key]["x"])
                + float(layout_by_key[key]["width"]) / 2,
                4,
            ),
            "y": round(
                float(layout_by_key[key]["y"])
                + float(layout_by_key[key]["height"]) / 2,
                4,
            ),
            "key": key,
        }
        for key, led_index in led_mapping.items()
    )
    return capabilities, lighting, geometry


def _read_snapshot(resolved: ResolvedViaDevice) -> hub_via.ViaSnapshot:
    definition = resolved.definition
    capabilities, layout, led_mapping, lighting_gets = _lighting_context(resolved)
    session = hid_transport.open_via_read(
        resolved.endpoint,
        lighting_gets=lighting_gets,
    )
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
        lighting_capabilities, lighting_state, lighting_geometry = _read_lighting(
            session,
            resolved,
            capabilities,
            layout,
            led_mapping,
        )
    finally:
        session.close()
    snapshot = hub_via.load_snapshot(
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
    return replace(
        snapshot,
        lighting_capabilities=lighting_capabilities,
        lighting_state=lighting_state,
        lighting_geometry=lighting_geometry,
    )


def read_snapshot(address: str, definition: object) -> hub_via.ViaSnapshot:
    """Resolve and read one complete VIA snapshot without a mutating command."""

    return _read_snapshot(resolve_device(address, definition))


def _editor_layout(
    snapshot: hub_via.ViaSnapshot,
) -> tuple[dict[str, int | float | str], ...]:
    return tuple(
        {
            **item,
            "key": f"K_R{item['matrix_row']}_C{item['matrix_col']}",
        }
        for item in snapshot.key_layout
    )


def read_hub_document(
    address: str, definition: object, *, origin: str = "device"
) -> HubDocument:
    """Resolve one endpoint and derive its profile and active geometry."""

    resolved = resolve_device(address, definition)
    snapshot = _read_snapshot(resolved)
    return HubDocument(
        device=device_json(resolved.endpoint),
        profile=hub_via.build_hub_profile(snapshot, origin=origin),
        layout=_editor_layout(snapshot),
        lighting_geometry=snapshot.lighting_geometry,
    )


def read_hub_profile(
    address: str, definition: object, *, origin: str = "device"
) -> dict[str, Any]:
    """Read one VIA keyboard directly into the common hub profile."""

    return read_hub_document(address, definition, origin=origin).profile


def prepare_write(
    address: str, definition: object, profile: object
) -> PreparedViaWrite:
    """Read the exact target and build a pure plan without sending a setter."""

    resolved = resolve_device(address, definition)
    target = _read_snapshot(resolved)
    validated = hub_profile.validate_hub_profile(profile)
    target_profile = hub_via.build_hub_profile(target)
    led_mapping = {
        f"K_R{item['matrix_row']}_C{item['matrix_col']}": int(item["led_index"])
        for item in target.key_layout
        if "led_index" in item
    }
    plan = hub_via.plan_via_write(validated, target=target)
    lighting_plan = via_lighting.plan_write(
        validated,
        target_profile,
        via_protocol=target.via_protocol,
        led_mapping=led_mapping or None,
    )
    if (
        plan.keymap_buffer is None
        and plan.macro_buffer is None
        and not lighting_plan.commands
    ):
        raise ViaTransportError(
            "The hub profile has no VIA data to write."
        )
    fingerprint = "sha256-" + hashlib.sha256(
        hub_profile.dumps_hub_profile(target_profile).encode("utf-8")
    ).hexdigest()
    report = copy.deepcopy(plan.report)
    report["items"].extend(copy.deepcopy(lighting_plan.items))
    return PreparedViaWrite(
        endpoint=resolved.endpoint,
        definition=resolved.definition,
        target=target,
        plan=plan,
        lighting_plan=lighting_plan,
        lighting_backup=copy.deepcopy(target_profile.get("lighting")),
        target_fingerprint=fingerprint,
        report=report,
    )


def write_matches_target(prepared: PreparedViaWrite) -> bool:
    """Whether a fresh read already equals every planned writable buffer."""

    keymap = prepared.plan.keymap_buffer
    macros = prepared.plan.macro_buffer
    return (
        (keymap is None or keymap == prepared.target.keymap_buffer)
        and (macros is None or macros == prepared.target.macro_buffer)
        and not prepared.lighting_plan.commands
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
    resolved = ResolvedViaDevice(
        endpoint=current,
        definition=prepared.definition,
        via_protocol=prepared.target.via_protocol,
        layout_options=prepared.target.layout_options,
        keycode_spec=prepared.target.keycode_spec,
    )
    capabilities, layout, led_mapping, lighting_gets = _lighting_context(resolved)
    lighting_sets = tuple(
        (
            (command.command,)
            if command.channel is None
            else (command.channel, command.command)
        )
        for command in prepared.lighting_plan.commands
    )
    lighting_saves_allowed = tuple(
        () if channel is None else (channel,)
        for channel in prepared.lighting_plan.save_channels
    )
    session = hid_transport.open_via_approved(
        approval,
        allow_keymap=prepared.plan.keymap_buffer is not None,
        allow_macros=prepared.plan.macro_buffer is not None,
        lighting_gets=lighting_gets,
        lighting_sets=lighting_sets,
        lighting_saves=lighting_saves_allowed,
    )
    keymap_written = 0
    macros_written = 0
    lighting_changes = 0
    lighting_saves = 0
    try:
        capacity = _revalidate_write(session, prepared)
        current_caps, current_state, current_geometry = _read_lighting(
            session,
            resolved,
            capabilities,
            layout,
            led_mapping,
        )
        if (
            current_caps != prepared.target.lighting_capabilities
            or current_state != prepared.target.lighting_state
            or current_geometry != prepared.target.lighting_geometry
        ):
            raise hid_transport.HidIdentityError(
                "The VIA lighting target changed after preflight."
            )
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

        for command in prepared.lighting_plan.commands:
            prefix = (
                [command.command]
                if command.channel is None
                else [command.channel, command.command]
            )
            try:
                vial_keymap.set_lighting_value(
                    session,
                    *prefix,
                    *command.payload,
                )
            except Exception as error:
                raise ViaAcceptedWriteError(
                    "The VIA keyboard may have accepted a lighting change before failure.",
                    keymap_bytes=keymap_written,
                    macro_bytes=macros_written,
                    lighting_changes=lighting_changes + 1,
                    lighting_saves=lighting_saves,
                ) from error
            lighting_changes += 1
        if prepared.lighting_plan.commands:
            _caps, lighting_readback, _geometry = _read_lighting(
                session,
                resolved,
                capabilities,
                layout,
                led_mapping,
            )
            if lighting_readback != prepared.lighting_plan.lighting:
                raise ViaAcceptedWriteError(
                    "The VIA keyboard accepted lighting changes but read-back differed.",
                    keymap_bytes=keymap_written,
                    macro_bytes=macros_written,
                    lighting_changes=lighting_changes,
                    lighting_saves=lighting_saves,
                )
        for channel in prepared.lighting_plan.save_channels:
            try:
                if channel is None:
                    vial_keymap.save_lighting(session)
                else:
                    vial_keymap.save_lighting(session, channel)
            except Exception as error:
                raise ViaAcceptedWriteError(
                    "The VIA keyboard may have accepted a lighting save before failure.",
                    keymap_bytes=keymap_written,
                    macro_bytes=macros_written,
                    lighting_changes=lighting_changes,
                    lighting_saves=lighting_saves + 1,
                ) from error
            lighting_saves += 1
    except ViaAcceptedWriteError:
        raise
    except Exception as error:
        if keymap_written or macros_written or lighting_changes or lighting_saves:
            raise ViaAcceptedWriteError(
                "The VIA keyboard accepted part of the write before it failed.",
                keymap_bytes=keymap_written,
                macro_bytes=macros_written,
                lighting_changes=lighting_changes,
                lighting_saves=lighting_saves,
            ) from error
        raise
    finally:
        session.close()
    return ViaWriteReceipt(
        keymap_bytes=keymap_written,
        macro_bytes=macros_written,
        lighting_changes=lighting_changes,
        lighting_saves=lighting_saves,
        report=prepared.report,
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
