"""The Neon 80 device driver: raw HID transport plus its own protocols.

This is the `transport.DeviceTransport` implementation for the Neon, so the
device routes reach it through a `DeviceHandle` exactly as they reach the serial
families. It owns its protocol end to end — lighting packets come from
`neon_lighting`, discovery and identity from `hid_transport` — which is the
whole point of the seam sitting below the encoding.

All three protocols are implemented now — lighting (N5), keymap (N6), macros
(N7) — so a write is no longer refused outright. What replaces the refusal is a
**preflight**: everything that can be validated is validated before the first
byte, because these three writes are not one transaction. Lighting packets, a
keymap buffer, and a macro buffer are separate transmissions, and a failure
between them leaves the keyboard in a mixed state. Nothing can make that atomic,
so the next best thing is to make failure-after-the-first-byte as unlikely as
possible: translate the keymap, compile and size the macros, plan every lighting
packet, and confirm the device is unlocked — all before transmitting.

The keyboard's own lock is the one thing that cannot be preflighted away and is
reported as its own actionable state, because only the user can clear it.
"""

from __future__ import annotations

from typing import Any

from . import (
    device_mapping,
    hid_transport,
    neon_lighting,
    transport,
    vial_keymap,
    vial_macros,
)


NEON_TRANSPORT = device_mapping.HID_TRANSPORT

# The Neon's key matrix, from the Vial definition its firmware serves.
NEON_KEYS_PER_LAYER = 90


class NeonUnsupportedOperation(hid_transport.HidError):
    """An operation the Neon driver cannot perform yet.

    Raised *before* any I/O, so refusing costs the device nothing.
    """


class NeonTransport:
    """Drives an AM Neon 80 over raw HID."""

    kind = NEON_TRANSPORT
    write_unit_label = "lighting packets"

    def list_devices(self, *, full: bool = False) -> list[Any]:
        return hid_transport.list_devices()

    def handle_for(self, info: Any) -> transport.DeviceHandle:
        return transport.DeviceHandle(self.kind, info.address)

    def probe(self, address: str, *, full: bool = False) -> Any:
        return hid_transport.find(address)

    def _session(self, address: str):
        info = hid_transport.find(address)
        return hid_transport.open_approved(
            hid_transport.approve_write(info, info.model or "")
        )

    def read_keymap(self, address: str, *, layers: int) -> list[list[str]]:
        """Read the keymap. `layers` is ignored in favour of what the device says.

        The route defaults to seven layers, which is the serial families' count.
        This keyboard has four, and reading seven would run off the end of its
        buffer.
        """

        session = self._session(address)
        try:
            return vial_keymap.read_keymap(
                session, keys_per_layer=NEON_KEYS_PER_LAYER
            )
        finally:
            session.close()

    def read_macros(self, address: str) -> list[dict[str, Any]]:
        session = self._session(address)
        try:
            return vial_macros.read_macros(session)
        finally:
            session.close()

    def write_macros(self, address: str, entries: list[dict[str, Any]]) -> Any:
        session = self._session(address)
        try:
            return vial_macros.write_macros(session, entries)
        finally:
            session.close()

    def _plan(self, config: dict[str, Any], *, slot: int = 1) -> neon_lighting.LightingPlan:
        pages = config.get("page_data") or []
        page = next(
            (p for p in pages if int(p.get("page_index", -1)) == slot + 4),
            None,
        )
        if page is None:
            raise neon_lighting.NeonLightingError(
                f"The configuration has no custom slot {slot} to write."
            )
        axial = [
            frame.get("frame_RGB", [])
            for frame in (page.get("axial", {}).get("frame_data") or [])
        ]
        head = [
            frame.get("frame_RGB", [])
            for frame in (page.get("head", {}).get("frame_data") or [])
        ]
        return neon_lighting.plan_push(
            axial,
            head,
            slot=slot,
            lightness=int(page.get("lightness", 100)),
            interval=int(page.get("speed_ms", 90)),
        )

    @staticmethod
    def _keymap_layers(config: dict[str, Any]) -> list[list[str]]:
        layer_data = (config.get("key_layer") or {}).get("layer_data") or []
        return [entry.get("layer", []) for entry in layer_data]

    def preflight(self, session, config: dict[str, Any]) -> neon_lighting.LightingPlan:
        """Validate everything that can be validated before any byte is sent.

        The three writes are not one transaction and cannot be made one, so this
        is what stands in for atomicity: every failure that can be found without
        touching the device is found here.
        """

        plan = self._plan(config)

        layers = self._keymap_layers(config)
        if layers:
            # Raises naming every unsupported key at once.
            vial_keymap.encode_layers(layers)

        macros = config.get("macro_key") or []
        capacity = vial_macros.read_capacity(session)
        vial_macros.encode_macros(macros, capacity=capacity)

        unlocked, held_keys = vial_keymap.unlock_status(session)
        if not unlocked:
            raise vial_keymap.KeyboardLocked(
                "This keyboard is locked. Vial requires it to be unlocked from "
                f"the keyboard itself: hold the {held_keys} designated key(s) "
                "until it reports unlocked, then write again. Nothing was "
                "written."
            )
        return plan

    def describe_write(self, config: dict[str, Any]) -> transport.WriteReceipt:
        return transport.WriteReceipt(self._plan(config).packet_count, self.write_unit_label)

    def write_config(self, address: str, config: dict[str, Any]) -> transport.WriteReceipt:
        session = self._session(address)
        try:
            plan = self.preflight(session, config)
            sent = neon_lighting.push(session, plan)
        finally:
            session.close()
        return transport.WriteReceipt(sent, self.write_unit_label)


transport.register_transport(NeonTransport())
