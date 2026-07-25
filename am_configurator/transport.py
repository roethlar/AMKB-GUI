"""Transport-neutral device addressing and dispatch.

The AM serial families are reached over a USB CDC port, so the device routes
historically passed a bare port string end to end. That works only while every
supported keyboard speaks the same protocol over the same kind of link. A
`DeviceHandle` replaces the bare string with "which transport, and where on it",
and a transport object owns the operations the device routes need.

This module is deliberately a seam, not a protocol: the serial transport
delegates to `device`, `reader`, `writer`, and `macros` exactly as the routes
used to call them, so introducing it changes no behaviour. Imports stay lazy
inside the methods because those modules pull in `pyserial`, and discovery must
not cost an import on an install that never touches a keyboard.

Registration is explicit and closed: an unrecognised transport kind raises
rather than being treated as serial. Guessing the link type would mean writing
one keyboard's protocol to another keyboard's endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from . import device_mapping


SERIAL = device_mapping.SERIAL_TRANSPORT


class UnsupportedTransportError(ValueError):
    """A handle names a transport this build cannot drive.

    Subclasses `ValueError` so the device routes report it as a bad request,
    which is what it is: the caller asked for a link this build does not have.
    """


@dataclass(frozen=True)
class DeviceHandle:
    """Where a device is, and how to talk to it."""

    transport: str
    address: str

    def as_json(self) -> dict[str, str]:
        return {"transport": self.transport, "address": self.address}


@runtime_checkable
class DeviceTransport(Protocol):
    """The device operations a route needs, for one kind of link."""

    kind: str

    def list_devices(self, *, full: bool = False) -> list[Any]: ...

    def handle_for(self, info: Any) -> DeviceHandle: ...

    def probe(self, address: str, *, full: bool = False) -> Any: ...

    def read_keymap(self, address: str, *, layers: int) -> list[list[str]]: ...

    def read_macros(self, address: str) -> list[dict[str, Any]]: ...

    def write_macros(self, address: str, entries: list[dict[str, Any]]) -> Any: ...

    def write_config(self, address: str, frames: tuple[bytes, ...]) -> tuple[bool, bytes]: ...


class SerialTransport:
    """The USB CDC link the AM serial families speak.

    Every method is a straight delegation to the module that already owned the
    call, so routing through the handle is behaviour-neutral for these devices.
    """

    kind = SERIAL

    def list_devices(self, *, full: bool = False) -> list[Any]:
        from . import device

        return device.list_devices(full=full)

    def handle_for(self, info: Any) -> DeviceHandle:
        return DeviceHandle(SERIAL, info.port)

    def probe(self, address: str, *, full: bool = False) -> Any:
        from . import device

        return device.probe(address, full=full)

    def read_keymap(self, address: str, *, layers: int) -> list[list[str]]:
        from . import reader

        return reader.read_keymap(address, layers=layers)

    def read_macros(self, address: str) -> list[dict[str, Any]]:
        from . import macros

        return macros.read_macros(address)

    def write_macros(self, address: str, entries: list[dict[str, Any]]) -> Any:
        from . import macros

        return macros.write_macros(address, entries)

    def write_config(self, address: str, frames: tuple[bytes, ...]) -> tuple[bool, bytes]:
        from . import writer

        return writer.write_config(address, frames)


_TRANSPORTS: dict[str, DeviceTransport] = {}


def register_transport(transport: DeviceTransport) -> None:
    _TRANSPORTS[transport.kind] = transport


def transport_kinds() -> tuple[str, ...]:
    """Registered transport kinds, in registration order."""

    return tuple(_TRANSPORTS)


def transport_for(kind: str) -> DeviceTransport:
    """Resolve a transport kind, or raise `UnsupportedTransportError`."""

    try:
        return _TRANSPORTS[kind]
    except KeyError:
        known = ", ".join(_TRANSPORTS) or "none"
        raise UnsupportedTransportError(
            f"Unsupported device transport {kind or '?'}; this build drives: {known}."
        ) from None


def transport_for_handle(handle: DeviceHandle) -> DeviceTransport:
    return transport_for(handle.transport)


def handle_from_payload(body: dict[str, Any]) -> DeviceHandle:
    """Build a handle from a device request body.

    A missing `transport` means serial, and `port` is accepted as the serial
    address: every payload written before handles existed carries exactly that
    shape, and a browser tab left open across an upgrade should keep working.
    A payload that *names* a transport gets no such leniency — an unregistered
    kind raises here, before any I/O is attempted.
    """

    kind = str(body.get("transport") or SERIAL).strip() or SERIAL
    address = str(body.get("address") or body.get("port") or "").strip()
    if not address:
        raise ValueError("A device is required.")
    transport_for(kind)
    return DeviceHandle(kind, address)


def discover() -> list[tuple[DeviceHandle, Any]]:
    """Every device on every registered transport, paired with its handle."""

    found: list[tuple[DeviceHandle, Any]] = []
    for transport in _TRANSPORTS.values():
        for info in transport.list_devices(full=True):
            found.append((transport.handle_for(info), info))
    return found


register_transport(SerialTransport())
