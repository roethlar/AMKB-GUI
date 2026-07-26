"""The Neon 80 device driver: raw HID transport plus its own protocols.

This is the `transport.DeviceTransport` implementation for the Neon, so the
device routes reach it through a `DeviceHandle` exactly as they reach the serial
families. It owns its protocol end to end — lighting packets come from
`neon_lighting`, discovery and identity from `hid_transport` — which is the
whole point of the seam sitting below the encoding.

**A Neon write is refused, deliberately and completely, until the keymap and
macro protocols exist.** The route's write path pushes a configuration, then
installs macros, then reads the keymap back. Two of those three are not
implemented yet (plan tasks N6 and N7). A driver that pushed lighting and then
failed on macros would leave the keyboard holding half a write while the user
was told it failed — the worst outcome available. So `write_config` refuses
before transmitting a single packet, and `supports_full_write` is the one flag
to flip when N6 and N7 land.
"""

from __future__ import annotations

from typing import Any

from . import device_mapping, hid_transport, neon_lighting, transport


NEON_TRANSPORT = device_mapping.HID_TRANSPORT

# Flip to True only when read_keymap, read_macros, and write_macros are real.
# `write_config` refuses while this is False, which is what makes a partial
# write impossible rather than merely unlikely.
supports_full_write = False


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

    def read_keymap(self, address: str, *, layers: int) -> list[list[str]]:
        raise NeonUnsupportedOperation(
            "Reading the keymap from a Neon 80 is not implemented yet."
        )

    def read_macros(self, address: str) -> list[dict[str, Any]]:
        raise NeonUnsupportedOperation(
            "Reading macros from a Neon 80 is not implemented yet."
        )

    def write_macros(self, address: str, entries: list[dict[str, Any]]) -> Any:
        raise NeonUnsupportedOperation(
            "Writing macros to a Neon 80 is not implemented yet."
        )

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

    def _refuse_partial_write(self) -> None:
        if not supports_full_write:
            raise NeonUnsupportedOperation(
                "Writing to an AM Neon 80 is not enabled yet: its keymap and "
                "macro protocols are still to come. Nothing was sent to the "
                "keyboard. Lighting alone would leave the device holding an "
                "incomplete write."
            )

    def describe_write(self, config: dict[str, Any]) -> transport.WriteReceipt:
        self._refuse_partial_write()
        return transport.WriteReceipt(self._plan(config).packet_count, self.write_unit_label)

    def write_config(self, address: str, config: dict[str, Any]) -> transport.WriteReceipt:
        # Refuse first. Planning would be harmless, but refusing before doing
        # any work at all is the property worth having.
        self._refuse_partial_write()

        info = hid_transport.find(address)
        approval = hid_transport.approve_write(info, info.model or "")
        plan = self._plan(config)
        session = hid_transport.open_approved(approval)
        try:
            sent = neon_lighting.push(session, plan)
        finally:
            session.close()
        return transport.WriteReceipt(sent, self.write_unit_label)


transport.register_transport(NeonTransport())
