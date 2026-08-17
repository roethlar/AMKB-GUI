"""Generic Vial HID transport for the OpenKeeb hub spoke.

Discovery and reads are constrained to a read-only raw-HID session.  A write
is a separate, explicit path: plan against a pinned snapshot, type the board's
embedded definition name, re-enumerate the same connection-scoped endpoint,
re-prove its firmware UID and definition hash on the open handle, validate all
buffer limits, complete Vial's physical unlock, then transmit and read back.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
import hashlib
import threading
from typing import Any

from . import (
    hid_transport,
    hub_lighting,
    hub_profile,
    hub_vial,
    vial_keymap,
    vial_lighting,
    vial_macros,
    vial_rgb_stream,
)


_MAX_MATRIX_AXIS = 32
_MAX_KEYS_PER_LAYER = 512
_MAX_LAYERS = 32
_MAX_MACROS = 128
_MAX_MACRO_BUFFER = 65535


class VialTransportError(ValueError):
    """Live Vial data cannot be represented or safely transferred."""


class VialAcceptedWriteError(RuntimeError):
    """A device accepted bytes before a later write/read-back failure."""

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
class PreparedVialWrite:
    """Pure plan pinned to the endpoint and snapshot used to build it."""

    endpoint: hid_transport.VialDeviceInfo
    target: hub_vial.VialSnapshot
    plan: hub_vial.VialWritePlan
    lighting_plan: vial_lighting.VialLightingWritePlan
    lighting_backup: dict[str, Any] | None
    target_fingerprint: str
    report: dict[str, Any]
    unlock_status: vial_keymap.UnlockStatus

    @property
    def confirmation(self) -> str:
        return self.target.name


@dataclass(frozen=True)
class PreparedVialRGBStream:
    """One animation bound to a read target and its captured volatile mode."""

    endpoint: hid_transport.VialDeviceInfo
    target: hub_vial.VialSnapshot
    animation_index: int
    animation_name: str
    surface_id: str
    pixel_ids: tuple[str, ...]
    original_state: dict[str, Any]
    plan: vial_rgb_stream.StreamPlan
    target_fingerprint: str

    @property
    def confirmation(self) -> str:
        return f"PREVIEW {self.target.name}"

    @property
    def subject(self) -> str:
        return self.animation_name


@dataclass(frozen=True)
class HubDocument:
    """One browser editor document derived from one live snapshot."""

    device: dict[str, Any]
    profile: dict[str, Any]
    layout: tuple[dict[str, int | float | str], ...]
    lighting_geometry: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class VialWriteReceipt:
    """Exact accepted byte counts plus the planner's transfer report."""

    keymap_bytes: int
    macro_bytes: int
    lighting_changes: int
    lighting_saves: int
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
        "vial_feature_flags": info.feature_flags,
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


def _lighting_gets(info: hid_transport.VialDeviceInfo) -> tuple[tuple[int, ...], ...]:
    definition = info.definition or {}
    lighting = definition.get("lighting")
    value_ids: tuple[int, ...] = ()
    if lighting in ("qmk_backlight", "qmk_backlight_rgblight"):
        value_ids += (
            vial_lighting.QMK_BACKLIGHT_BRIGHTNESS,
            vial_lighting.QMK_BACKLIGHT_EFFECT,
        )
    if lighting in ("qmk_rgblight", "qmk_backlight_rgblight"):
        value_ids += (
            vial_lighting.QMK_RGBLIGHT_BRIGHTNESS,
            vial_lighting.QMK_RGBLIGHT_EFFECT,
            vial_lighting.QMK_RGBLIGHT_EFFECT_SPEED,
            vial_lighting.QMK_RGBLIGHT_COLOR,
        )
    if (
        lighting == "vialrgb"
        and info.protocol_version >= 4
        and info.feature_flags & vial_lighting.VIALRGB_FEATURE_FLAG
    ):
        value_ids = (
            vial_lighting.VIALRGB_GET_INFO,
            vial_lighting.VIALRGB_GET_SUPPORTED,
            vial_lighting.VIALRGB_GET_MODE,
            vial_lighting.VIALRGB_GET_NUMBER_LEDS,
            vial_lighting.VIALRGB_GET_LED_INFO,
        )
    return tuple((value_id,) for value_id in value_ids)


def _legacy_lighting_values(session, capabilities: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contracts = {
        "qmk_backlight": {
            "brightness": (vial_lighting.QMK_BACKLIGHT_BRIGHTNESS, 1),
            "effect_id": (vial_lighting.QMK_BACKLIGHT_EFFECT, 1),
        },
        "qmk_rgblight": {
            "brightness": (vial_lighting.QMK_RGBLIGHT_BRIGHTNESS, 1),
            "effect_id": (vial_lighting.QMK_RGBLIGHT_EFFECT, 1),
            "speed": (vial_lighting.QMK_RGBLIGHT_EFFECT_SPEED, 1),
            "color": (vial_lighting.QMK_RGBLIGHT_COLOR, 2),
        },
    }
    values: dict[str, dict[str, Any]] = {}
    for surface in capabilities["surfaces"]:
        state: dict[str, Any] = {}
        for field, (value_id, size) in contracts.get(surface["generation"], {}).items():
            capability_field = "effects" if field == "effect_id" else field
            if capability_field not in surface:
                continue
            payload = vial_keymap.read_lighting_value(session, value_id)
            if len(payload) < size:
                raise VialTransportError("The keyboard returned a short lighting value.")
            state[field] = list(payload[:size]) if field == "color" else payload[0]
        values[surface["id"]] = state
    return values


def _vialrgb_effects(session) -> tuple[int, ...]:
    effects = {0}
    lower = 0
    for _page in range((hub_lighting.MAX_EFFECTS + 14) // 15 + 1):
        payload = vial_keymap.read_lighting_value(
            session,
            vial_lighting.VIALRGB_GET_SUPPORTED,
            lower & 0xFF,
            (lower >> 8) & 0xFF,
        )
        ended = False
        page: list[int] = []
        for offset in range(0, len(payload) - 1, 2):
            effect = int.from_bytes(payload[offset : offset + 2], "little")
            if effect == 0xFFFF:
                ended = True
                break
            if effect > lower:
                page.append(effect)
        effects.update(page)
        if len(effects) > hub_lighting.MAX_EFFECTS:
            raise VialTransportError("The VialRGB effect list exceeds the hub bound.")
        if ended:
            return tuple(sorted(effects))
        if not page or max(page) <= lower:
            raise VialTransportError("The VialRGB effect pages did not advance.")
        lower = max(page)
    raise VialTransportError("The VialRGB effect list did not terminate.")


def _vialrgb_lighting(
    session,
    info: hid_transport.VialDeviceInfo,
    *,
    rows: int,
    cols: int,
) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    info_payload = vial_keymap.read_lighting_value(
        session, vial_lighting.VIALRGB_GET_INFO
    )
    if len(info_payload) < 3:
        raise VialTransportError("The keyboard returned short VialRGB info.")
    protocol = int.from_bytes(info_payload[:2], "little")
    maximum_brightness = info_payload[2]
    effect_ids = _vialrgb_effects(session)

    mode = vial_keymap.read_lighting_value(session, vial_lighting.VIALRGB_GET_MODE)
    if len(mode) < 6:
        raise VialTransportError("The keyboard returned short VialRGB mode state.")
    values = {
        "vialrgb": {
            "effect_id": int.from_bytes(mode[:2], "little"),
            "speed": mode[2],
            "color": [mode[3], mode[4]],
            "brightness": mode[5],
        }
    }

    pixel_count: int | None = None
    geometry: list[dict[str, Any]] = []
    if vial_lighting.VIALRGB_DIRECT_EFFECT in effect_ids:
        count_payload = vial_keymap.read_lighting_value(
            session, vial_lighting.VIALRGB_GET_NUMBER_LEDS
        )
        if len(count_payload) < 2:
            raise VialTransportError("The keyboard returned short VialRGB LED count.")
        pixel_count = int.from_bytes(count_payload[:2], "little")
        if not 1 <= pixel_count <= hub_lighting.MAX_PIXELS:
            raise VialTransportError(
                f"VialRGB LED count must be in 1..{hub_lighting.MAX_PIXELS}."
            )
        seen_pixels: set[str] = set()
        for index in range(pixel_count):
            payload = vial_keymap.read_lighting_value(
                session,
                vial_lighting.VIALRGB_GET_LED_INFO,
                index & 0xFF,
                (index >> 8) & 0xFF,
            )
            if len(payload) < 5:
                raise VialTransportError("The keyboard returned short VialRGB LED info.")
            x, y, flags, row, column = payload[:5]
            key = None
            if row < rows and column < cols:
                key = f"K_R{row}_C{column}"
            pixel_id = key or f"LED_I{index}"
            if pixel_id in seen_pixels:
                raise VialTransportError(
                    f"VialRGB LED metadata repeats pixel identity {pixel_id}."
                )
            seen_pixels.add(pixel_id)
            item: dict[str, Any] = {
                "surface_id": "vialrgb",
                "pixel_id": pixel_id,
                "led_index": index,
                "x": round(x / 255 * 100, 4),
                "y": round(y / 255 * 100, 4),
                "flags": flags,
            }
            if key is not None:
                item["key"] = key
            geometry.append(item)

    rgb_info = vial_lighting.VialRGBInfo(
        protocol_version=protocol,
        maximum_brightness=maximum_brightness,
        effect_ids=effect_ids,
        pixel_count=pixel_count,
    )
    capabilities = vial_lighting.capabilities_from_definition(
        info.definition,
        vial_protocol=info.protocol_version,
        feature_flags=info.feature_flags,
        vialrgb_info=rgb_info,
        current=values,
    )
    return (
        capabilities,
        vial_lighting.state_from_values(capabilities, values),
        tuple(geometry),
    )


def _read_lighting(
    session,
    info: hid_transport.VialDeviceInfo,
    *,
    rows: int,
    cols: int,
) -> tuple[dict[str, Any], dict[str, Any] | None, tuple[dict[str, Any], ...]]:
    lighting = (info.definition or {}).get("lighting")
    if (
        lighting == "vialrgb"
        and info.protocol_version >= 4
        and info.feature_flags & vial_lighting.VIALRGB_FEATURE_FLAG
    ):
        return _vialrgb_lighting(session, info, rows=rows, cols=cols)
    capabilities = vial_lighting.capabilities_from_definition(
        info.definition,
        vial_protocol=info.protocol_version,
        feature_flags=info.feature_flags,
    )
    if not capabilities["surfaces"]:
        return capabilities, None, ()
    values = _legacy_lighting_values(session, capabilities)
    capabilities = vial_lighting.capabilities_from_definition(
        info.definition,
        vial_protocol=info.protocol_version,
        feature_flags=info.feature_flags,
        current=values,
    )
    return capabilities, vial_lighting.state_from_values(capabilities, values), ()


def _read_snapshot(
    info: hid_transport.VialDeviceInfo,
) -> hub_vial.VialSnapshot:
    if not info.writable or info.definition is None:
        raise hid_transport.HidIdentityError(
            info.identity_error or "The Vial keyboard identity is incomplete."
        )
    session = hid_transport.open_vial_read(info, lighting_gets=_lighting_gets(info))
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
        lighting_capabilities, lighting_state, lighting_geometry = _read_lighting(
            session,
            info,
            rows=rows,
            cols=cols,
        )
    finally:
        session.close()
    snapshot = hub_vial.load_snapshot(
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
    return replace(
        snapshot,
        feature_flags=info.feature_flags,
        lighting_capabilities=lighting_capabilities,
        lighting_state=lighting_state,
        lighting_geometry=lighting_geometry,
    )


def read_snapshot(address: str) -> hub_vial.VialSnapshot:
    """Read and validate one complete generic Vial snapshot."""
    return _read_snapshot(hid_transport.find_vial(address))


def _read_unlock_status(
    info: hid_transport.VialDeviceInfo,
) -> vial_keymap.UnlockStatus:
    """Read Vial's volatile lock hint without starting its handshake."""

    session = hid_transport.open_vial_read(info)
    try:
        return vial_keymap.unlock_status(session)
    finally:
        session.close()


def _editor_layout(
    snapshot: hub_vial.VialSnapshot,
) -> tuple[dict[str, int | float | str], ...]:
    return tuple(
        {
            **item,
            "key": f"K_R{item['matrix_row']}_C{item['matrix_col']}",
        }
        for item in snapshot.key_layout
    )


def read_hub_document(address: str, *, origin: str = "device") -> HubDocument:
    """Read one endpoint once and derive its profile and active geometry."""

    endpoint = hid_transport.find_vial(address)
    snapshot = _read_snapshot(endpoint)
    return HubDocument(
        device=device_json(endpoint),
        profile=hub_vial.build_hub_profile(snapshot, origin=origin),
        layout=_editor_layout(snapshot),
        lighting_geometry=snapshot.lighting_geometry,
    )


def read_hub_profile(address: str, *, origin: str = "device") -> dict[str, Any]:
    """Read one Vial keyboard directly into the common hub profile."""
    return read_hub_document(address, origin=origin).profile


def prepare_stream(
    address: str,
    profile: object,
    *,
    animation_index: int,
    maximum_duration_ms: int = vial_rgb_stream.MAX_DURATION_MS,
) -> PreparedVialRGBStream:
    """Bind one validated VialRGB animation to a fresh read-only target."""

    if (
        isinstance(animation_index, bool)
        or not isinstance(animation_index, int)
        or animation_index < 0
    ):
        raise VialTransportError("The VialRGB animation index is invalid.")
    endpoint = hid_transport.find_vial(address)
    target = _read_snapshot(endpoint)
    validated = hub_profile.validate_hub_profile(profile)
    animations = validated.get("lighting", {}).get("animations", [])
    if animation_index >= len(animations):
        raise VialTransportError("The selected VialRGB animation is unavailable.")
    animation = animations[animation_index]
    capabilities = (target.lighting_capabilities or {}).get("surfaces", [])
    capability = next(
        (
            surface
            for surface in capabilities
            if surface.get("id") == animation.get("surface_id")
        ),
        None,
    )
    if (
        capability is None
        or capability.get("generation") != "vialrgb"
        or not isinstance(capability.get("stream"), dict)
        or capability["stream"].get("volatile") is not True
    ):
        raise VialTransportError(
            "The selected target does not prove volatile VialRGB streaming."
        )
    geometry = tuple(
        item
        for item in target.lighting_geometry
        if item.get("surface_id") == capability["id"]
    )
    pixel_ids = tuple(str(item.get("pixel_id") or "") for item in geometry)
    if (
        len(pixel_ids) != capability["stream"]["pixel_count"]
        or tuple(animation.get("pixel_ids", ())) != pixel_ids
    ):
        raise VialTransportError(
            "The animation pixel identities do not match the current target geometry."
        )
    original = next(
        (
            surface
            for surface in (target.lighting_state or {}).get("surfaces", [])
            if surface.get("id") == capability["id"]
        ),
        None,
    )
    if original is None:
        raise VialTransportError("The current VialRGB mode was not read.")
    if original.get("effect_id") == vial_lighting.VIALRGB_DIRECT_EFFECT:
        raise VialTransportError(
            "The keyboard is already in VialRGB direct mode; choose a hardware effect first."
        )
    plan = vial_rgb_stream.build_plan(
        animation["frames"],
        frame_ms=animation.get("frame_ms", 90),
        brightness=animation.get("brightness", 100),
        maximum_duration_ms=maximum_duration_ms,
        max_chunk_pixels=capability["stream"]["max_chunk_pixels"],
        reports_per_second=vial_lighting.VIALRGB_REPORTS_PER_SECOND,
    )
    target_profile = hub_vial.build_hub_profile(target)
    target_fingerprint = "sha256-" + hashlib.sha256(
        hub_profile.dumps_hub_profile(target_profile).encode("utf-8")
    ).hexdigest()
    return PreparedVialRGBStream(
        endpoint=endpoint,
        target=target,
        animation_index=animation_index,
        animation_name=animation["name"],
        surface_id=capability["id"],
        pixel_ids=pixel_ids,
        original_state=copy.deepcopy(original),
        plan=plan,
        target_fingerprint=target_fingerprint,
    )


def _vialrgb_mode_payload(state: dict[str, Any]) -> tuple[int, ...]:
    color = state.get("color")
    if not isinstance(color, list) or len(color) != 2:
        raise VialTransportError("The captured VialRGB HSV mode is invalid.")
    return (
        *int(state["effect_id"]).to_bytes(2, "little"),
        int(state["speed"]),
        int(color[0]),
        int(color[1]),
        int(state["brightness"]),
    )


def execute_stream(
    prepared: PreparedVialRGBStream,
    *,
    confirmation: str,
    stop_event: threading.Event,
    progress=None,
    clock: vial_rgb_stream.Clock | None = None,
) -> vial_rgb_stream.StreamOutcome:
    """Run one no-SAVE preview on a single re-proved endpoint-bound handle."""

    if confirmation != prepared.confirmation:
        raise hid_transport.HidIdentityError(
            f"Type {prepared.confirmation} exactly to start volatile preview."
        )
    current = hid_transport.find_vial(prepared.endpoint.address)
    if not _matches_target(current, prepared):
        raise hid_transport.HidIdentityError(
            "The connected Vial endpoint no longer matches preview preflight."
        )
    approval = hid_transport.approve_vial_stream(current, confirmation)
    stream_surface = next(
        surface
        for surface in prepared.target.lighting_capabilities["surfaces"]
        if surface["id"] == prepared.surface_id
    )
    stream = stream_surface["stream"]
    offsets = range(0, prepared.plan.pixel_count, stream["max_chunk_pixels"])
    lighting_sets = (
        (vial_lighting.VIALRGB_SET_MODE,),
        *(
            (
                vial_lighting.VIALRGB_DIRECT_FASTSET,
                offset & 0xFF,
                (offset >> 8) & 0xFF,
            )
            for offset in offsets
        ),
    )
    session = hid_transport.open_vial_stream_approved(
        approval,
        lighting_gets=_lighting_gets(current),
        lighting_sets=lighting_sets,
    )
    try:
        capabilities, lighting_state, geometry = _read_lighting(
            session,
            current,
            rows=prepared.target.matrix_rows,
            cols=prepared.target.matrix_cols,
        )
        if (
            capabilities != prepared.target.lighting_capabilities
            or lighting_state != prepared.target.lighting_state
            or geometry != prepared.target.lighting_geometry
        ):
            raise hid_transport.HidIdentityError(
                "VialRGB capability, mode, or geometry changed after preview preflight."
            )
        direct_state = {
            **prepared.original_state,
            "effect_id": vial_lighting.VIALRGB_DIRECT_EFFECT,
        }

        def set_mode(state: dict[str, Any]) -> None:
            vial_keymap.set_lighting_value(
                session,
                vial_lighting.VIALRGB_SET_MODE,
                *_vialrgb_mode_payload(state),
            )

        def send_chunk(
            offset: int, pixels: tuple[tuple[int, int, int], ...]
        ) -> None:
            payload = [offset & 0xFF, (offset >> 8) & 0xFF]
            payload.extend(channel for pixel in pixels for channel in pixel)
            vial_keymap.set_lighting_value(
                session,
                vial_lighting.VIALRGB_DIRECT_FASTSET,
                *payload,
            )

        return vial_rgb_stream.run_stream(
            prepared.plan,
            stop_event=stop_event,
            enter_direct=lambda: set_mode(direct_state),
            send_chunk=send_chunk,
            restore=lambda: set_mode(prepared.original_state),
            clock=clock,
            progress=progress,
        )
    finally:
        session.close()


def prepare_write(address: str, profile: object) -> PreparedVialWrite:
    """Read the target and produce a pure write plan; never unlock or mutate."""
    endpoint = hid_transport.find_vial(address)
    target = _read_snapshot(endpoint)
    unlock_status = _read_unlock_status(endpoint)
    validated = hub_profile.validate_hub_profile(profile)
    target_profile = hub_vial.build_hub_profile(target)
    plan = hub_vial.plan_vial_write(validated, target=target)
    lighting_plan = vial_lighting.plan_write(validated, target_profile)
    fingerprint = "sha256-" + hashlib.sha256(
        hub_profile.dumps_hub_profile(target_profile).encode("utf-8")
    ).hexdigest()
    report = copy.deepcopy(plan.report)
    report["items"].extend(copy.deepcopy(lighting_plan.items))
    return PreparedVialWrite(
        endpoint=endpoint,
        target=target,
        plan=plan,
        lighting_plan=lighting_plan,
        lighting_backup=copy.deepcopy(target_profile.get("lighting")),
        target_fingerprint=fingerprint,
        report=report,
        unlock_status=unlock_status,
    )


def write_matches_target(prepared: PreparedVialWrite) -> bool:
    """Whether a fresh read already equals every planned writable buffer."""

    keymap = prepared.plan.keymap_buffer
    macros = prepared.plan.macro_buffer
    return (
        (keymap is None or keymap == prepared.target.keymap_buffer)
        and (macros is None or macros == prepared.target.macro_buffer)
        and not prepared.lighting_plan.commands
    )


def unlock_key_layout(prepared: PreparedVialWrite) -> tuple[dict[str, Any], ...]:
    """Resolve reported unlock matrix positions through the active layout."""

    layout = {
        (item["matrix_row"], item["matrix_col"]): item
        for item in _editor_layout(prepared.target)
    }
    resolved: list[dict[str, Any]] = []
    for row, column in prepared.unlock_status.keys:
        if (row, column) not in layout:
            raise VialTransportError(
                "A Vial unlock key is absent from the active physical layout."
            )
        resolved.append(
            {
                "key": layout[(row, column)]["key"],
                "matrix_row": row,
                "matrix_col": column,
            }
        )
    return tuple(resolved)


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
        and info.feature_flags == target.feature_flags
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
    if keymap is None and macros is None and not prepared.lighting_plan.commands:
        raise VialTransportError("The hub profile has no Vial data to write.")
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
    lighting_sets = tuple(
        (command.value_id,) for command in prepared.lighting_plan.commands
    )
    session = hid_transport.open_vial_approved(
        approval,
        allow_keymap=prepared.plan.keymap_buffer is not None,
        allow_macros=prepared.plan.macro_buffer is not None,
        lighting_gets=_lighting_gets(current),
        lighting_sets=lighting_sets,
        lighting_saves=((),) if prepared.lighting_plan.save else (),
    )
    keymap_written = 0
    macros_written = 0
    lighting_changes = 0
    lighting_saves = 0
    try:
        capacity = _revalidate_limits(session, prepared)
        capabilities, state, geometry = _read_lighting(
            session,
            current,
            rows=prepared.target.matrix_rows,
            cols=prepared.target.matrix_cols,
        )
        if (
            capabilities != prepared.target.lighting_capabilities
            or state != prepared.target.lighting_state
            or geometry != prepared.target.lighting_geometry
        ):
            raise hid_transport.HidIdentityError(
                "The Vial lighting target changed after preflight."
            )
        if (
            prepared.plan.keymap_buffer is not None
            or prepared.plan.macro_buffer is not None
        ):
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
            for command in prepared.lighting_plan.commands:
                try:
                    vial_keymap.set_lighting_value(
                        session,
                        command.value_id,
                        *command.payload,
                    )
                except Exception as error:
                    raise VialAcceptedWriteError(
                        "The keyboard may have accepted a lighting change before failure.",
                        keymap_bytes=keymap_written,
                        macro_bytes=macros_written,
                        lighting_changes=lighting_changes + 1,
                        lighting_saves=lighting_saves,
                    ) from error
                lighting_changes += 1
            if prepared.lighting_plan.commands:
                _caps, lighting_readback, _geometry = _read_lighting(
                    session,
                    current,
                    rows=prepared.target.matrix_rows,
                    cols=prepared.target.matrix_cols,
                )
                if lighting_readback != prepared.lighting_plan.lighting:
                    raise VialAcceptedWriteError(
                        "The keyboard accepted lighting changes but read-back differed.",
                        keymap_bytes=keymap_written,
                        macro_bytes=macros_written,
                        lighting_changes=lighting_changes,
                        lighting_saves=lighting_saves,
                    )
            if prepared.lighting_plan.save:
                try:
                    vial_keymap.save_lighting(session)
                except Exception as error:
                    raise VialAcceptedWriteError(
                        "The keyboard may have accepted the lighting save before failure.",
                        keymap_bytes=keymap_written,
                        macro_bytes=macros_written,
                        lighting_changes=lighting_changes,
                        lighting_saves=lighting_saves + 1,
                    ) from error
                lighting_saves += 1
        except vial_macros.MacroAcceptedWriteError as error:
            raise VialAcceptedWriteError(
                str(error),
                keymap_bytes=keymap_written,
                macro_bytes=error.macro_bytes,
            ) from error
        except VialAcceptedWriteError:
            raise
        except Exception as error:
            if keymap_written or macros_written or lighting_changes or lighting_saves:
                raise VialAcceptedWriteError(
                    "The keyboard accepted part of the Vial write before it failed.",
                    keymap_bytes=keymap_written,
                    macro_bytes=macros_written,
                    lighting_changes=lighting_changes,
                    lighting_saves=lighting_saves,
                ) from error
            raise
    finally:
        session.close()
    return VialWriteReceipt(
        keymap_bytes=keymap_written,
        macro_bytes=macros_written,
        lighting_changes=lighting_changes,
        lighting_saves=lighting_saves,
        report=prepared.report,
    )


def write_hub_profile(
    address: str, profile: object, *, confirmation: str
) -> VialWriteReceipt:
    """Convenience wrapper for one preflight-and-execute API request."""
    return execute_write(
        prepare_write(address, profile), confirmation=confirmation
    )
