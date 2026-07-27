"""Transport-neutral device addressing and dispatch.

The AM serial families are reached over a USB CDC port, so the device routes
historically passed a bare port string end to end. That works only while every
supported keyboard speaks the same protocol over the same kind of link. A
`DeviceHandle` replaces the bare string with "which transport, and where on it",
and a transport object owns the operations the device routes need.

The seam sits *below* the protocol encoding, which is the point: a driver
receives the logical configuration and plans its own protocol. Handing it
already-encoded bytes would make the abstraction serial-shaped — a raw-HID
keyboard cannot build its own packets out of another protocol's frames. So AM
frame planning lives inside `SerialTransport`, and protocol-specific failure
text belongs to the driver that speaks that protocol, never to the routes.

Imports stay lazy inside the methods because those modules pull in `pyserial`,
and discovery must not cost an import on an install that never touches a
keyboard.

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


class DeviceWriteError(RuntimeError):
    """A device refused a write.

    The driver raises this with its own protocol's rejection detail, so the
    routes never have to know what a rejection looks like on the wire.
    """


@dataclass(frozen=True)
class WriteReceipt:
    """What a driver transmitted, in terms the routes can report.

    Devices do not share a write unit: the AM serial families take 64-byte
    configuration frames, and raw HID takes reports. The count travels with its
    own label so the response payload never assumes one protocol's noun.
    """

    units: int
    unit_label: str


@dataclass(frozen=True)
class MacroReadResult:
    """Macros plus limits that this particular device reported while reading.

    The serial families do not report macro capacity, so their limits remain
    family-owned and both device fields stay zero. Vial reports both values;
    carrying them beside the macros prevents the read route from discarding
    information the driver already queried.
    """

    macros: list[dict[str, Any]]
    device_reported: bool = False
    device_macro_count: int = 0
    device_macro_buffer_bytes: int = 0


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

    def read_macro_state(self, address: str) -> MacroReadResult: ...

    def write_macros(self, address: str, entries: list[dict[str, Any]]) -> Any: ...

    def describe_write(self, config: dict[str, Any]) -> WriteReceipt: ...

    def write_config(self, address: str, config: dict[str, Any]) -> WriteReceipt: ...


class SerialTransport:
    """The USB CDC link the AM serial families speak.

    Read operations are straight delegations to the module that already owned
    the call. The write path additionally owns AM frame planning, its settle
    delay, and its own rejection message: those are properties of this protocol,
    not of writing to a keyboard in general.
    """

    kind = SERIAL
    write_unit_label = "configuration frames"

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

    def read_macro_state(self, address: str) -> MacroReadResult:
        return MacroReadResult(self.read_macros(address))

    def write_macros(self, address: str, entries: list[dict[str, Any]]) -> Any:
        from . import macros

        return macros.write_macros(address, entries)

    def describe_write(self, config: dict[str, Any]) -> WriteReceipt:
        """Plan a write without performing any I/O.

        The verify route reports how much a write transmitted without resending
        it, so the unit count has to be obtainable from the configuration alone.
        """
        from . import writer

        return WriteReceipt(writer.plan(config).total, self.write_unit_label)

    def write_config(self, address: str, config: dict[str, Any]) -> WriteReceipt:
        import time

        from . import writer

        plan = writer.plan(config)
        ok, reply = writer.write_config(address, plan.frames)
        if not ok:
            raise DeviceWriteError(
                f"Device rejected JSON_END: {reply.hex() or 'no response'}"
            )
        time.sleep(writer.SETTLE_SECONDS)
        return WriteReceipt(plan.total, self.write_unit_label)


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
    """Every device on every registered transport, paired with its handle.

    A scan failure propagates. Swallowing it would report "no devices" to a
    user whose device layer is broken, which is the silent-fallback failure
    this module exists to avoid; the route already redacts the detail. A
    transport whose *dependencies* are missing never registers in the first
    place, which is the case worth tolerating and is handled at registration.
    """

    found: list[tuple[DeviceHandle, Any]] = []
    for transport in _TRANSPORTS.values():
        for info in transport.list_devices(full=True):
            found.append((transport.handle_for(info), info))
    return found


def device_json(handle: DeviceHandle, info: Any) -> dict[str, Any]:
    """Project one discovered device into the JSON the browser consumes.

    `asdict` alone is not enough. A raw-HID device carries its OS path as
    `bytes`, which no JSON encoder accepts, and `is_keyboard` is a property
    rather than a field — the browser filters the device list on exactly that
    key, so omitting it makes a real keyboard invisible.
    """

    from dataclasses import asdict, is_dataclass

    payload = asdict(info) if is_dataclass(info) else dict(info)
    payload = {
        key: value.hex() if isinstance(value, (bytes, bytearray)) else value
        for key, value in payload.items()
    }
    for derived in ("is_keyboard", "writable"):
        if hasattr(info, derived):
            payload[derived] = bool(getattr(info, derived))
    # Not boolean: `product_id` is the AM product identifier the browser keys
    # families off, and coercing it to a bool silently made every device report
    # `product_id: true`.
    if hasattr(info, "product_id"):
        payload["product_id"] = getattr(info, "product_id")
    payload.update(handle.as_json())
    return payload


register_transport(SerialTransport())


def register_optional_transports() -> None:
    """Register transports whose dependencies may be absent.

    The Neon driver needs `hidapi`, which is a runtime dependency but can fail
    to load on a machine with no HID backend. Discovery for the serial families
    must not break because of that, so the failure is swallowed here and the
    Neon simply does not enumerate — the same outcome as the keyboard not being
    plugged in.
    """

    try:
        from . import neon_driver  # noqa: F401  (registers on import)
    except Exception:
        pass


register_optional_transports()
