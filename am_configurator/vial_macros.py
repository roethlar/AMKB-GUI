"""Macros for Vial devices: the VIA macro buffer, sized before it is sent.

Kept separate from `macros.py` rather than folded into it, which the plan
originally suggested. That wording predates the decision recorded in
`.agents/decisions.md` as "The device seam sits below the protocol encoding":
`macros.py` is the AM serial protocol, and putting a raw-HID protocol beside it
would put two wire formats in one module. The macro *data model* is shared,
which is what actually matters.

Two facts drive the whole design.

A Vial macro write rewrites the entire buffer. There is no per-macro update, so
a write that runs out of room partway through does not fail cleanly — it leaves
the keyboard holding a truncated set, destroying macros the user already had.
Everything is therefore compiled and measured before the first byte is sent.

Capacity is bytes, not events. `GET_BUFFER_SIZE` reports a total buffer; how
many events fit depends on what each one encodes to. There is no correct
conversion in either direction, so the check is done on the compiled buffer
itself.

Note the keycode field means something different here than in a keymap. In
`macro_key` the leading byte of `#MMPPUUUU` is an event type — `0x11` press,
`0x10` release — not the modifier mask it is in `key_layer`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import vial_keymap


VIA_MACRO_GET_COUNT = 0x0C
VIA_MACRO_GET_BUFFER_SIZE = 0x0D
VIA_MACRO_GET_BUFFER = 0x0E
VIA_MACRO_SET_BUFFER = 0x0F

BUFFER_CHUNK = 28

# VIA's macro encoding. `0x01` introduces a sequence; `0x00` ends a macro.
SS_PREFIX = 0x01
SS_TAP = 0x01
SS_DOWN = 0x02
SS_UP = 0x03
SS_DELAY = 0x04
MACRO_TERMINATOR = 0x00

EVENT_PRESS = 0x11
EVENT_RELEASE = 0x10

# A delay is two bytes, each offset by one so neither can be a null that would
# terminate the macro early. That caps a single delay at 255 * 254 + 254.
_DELAY_BASE = 255
MAX_DELAY_MS = (_DELAY_BASE - 1) * _DELAY_BASE + (_DELAY_BASE - 1)


class MacroCapacityError(ValueError):
    """A macro set does not fit the device, measured before anything is sent."""


class MacroEncodingError(ValueError):
    """A macro event cannot be expressed in the VIA macro encoding."""


@dataclass(frozen=True)
class MacroCapacity:
    """What one device actually reports. Never guessed, never defaulted."""

    count: int
    buffer_bytes: int


def _encode_delay(milliseconds: int) -> bytes:
    if not 0 <= milliseconds <= MAX_DELAY_MS:
        raise MacroEncodingError(
            f"A macro delay of {milliseconds} ms is outside the range this "
            f"keyboard can store (0 to {MAX_DELAY_MS} ms)."
        )
    high, low = divmod(int(milliseconds), _DELAY_BASE)
    return bytes([SS_PREFIX, SS_DELAY, low + 1, high + 1])


def _decode_delay(low: int, high: int) -> int:
    return (low - 1) + (high - 1) * _DELAY_BASE


def _event_bytes(code: str) -> bytes:
    parts = vial_keymap.parse_code(code)

    if parts.page != vial_keymap.HID_KEYBOARD_PAGE:
        raise MacroEncodingError(
            f"{code} uses usage page 0x{parts.page:02X}, which a Vial macro "
            "cannot express; only the HID keyboard page translates."
        )
    if parts.usage > vial_keymap.MAX_BASIC_USAGE:
        raise MacroEncodingError(
            f"{code} uses usage 0x{parts.usage:04X}, beyond the single-byte "
            "keycodes a Vial macro stores."
        )

    if parts.modifier == EVENT_PRESS:
        action = SS_DOWN
    elif parts.modifier == EVENT_RELEASE:
        action = SS_UP
    elif parts.modifier == 0x00:
        action = SS_TAP
    else:
        raise MacroEncodingError(
            f"{code} has event type 0x{parts.modifier:02X}; a macro event must "
            "be a press (0x11), a release (0x10), or a tap (0x00)."
        )
    return bytes([SS_PREFIX, action, parts.usage])


def encode_macro(macro: dict[str, Any]) -> bytes:
    """Encode one macro, terminator included."""

    events = list(macro.get("layer_key") or [])
    delays = list(macro.get("intvel_ms") or [])

    payload = bytearray()
    for index, code in enumerate(events):
        payload += _event_bytes(code)
        if index < len(delays) and delays[index]:
            payload += _encode_delay(int(delays[index]))
    payload.append(MACRO_TERMINATOR)
    return bytes(payload)


def encode_macros(macros: list[dict[str, Any]], *, capacity: MacroCapacity) -> bytes:
    """Compile every macro and prove the result fits, before any transmission.

    Both limits are checked here rather than at the wire, because a Vial macro
    write replaces the whole buffer: discovering the overflow partway through
    would leave the keyboard holding a truncated macro set.
    """

    if len(macros) > capacity.count:
        raise MacroCapacityError(
            f"This keyboard stores {capacity.count} macros; the profile has "
            f"{len(macros)}. Nothing was sent."
        )

    buffer = bytearray()
    for macro in macros:
        buffer += encode_macro(macro)
    # Unused slots still need their terminator, or the device reads the next
    # macro's bytes as part of this one.
    buffer += bytes([MACRO_TERMINATOR]) * (capacity.count - len(macros))

    if len(buffer) > capacity.buffer_bytes:
        raise MacroCapacityError(
            f"These macros compile to {len(buffer)} bytes and this keyboard has "
            f"{capacity.buffer_bytes}. Shorten or remove some macros. Nothing "
            "was sent."
        )
    return bytes(buffer)


def decode_macros(buffer: bytes, *, count: int) -> list[dict[str, Any]]:
    """Decode the device buffer back into the shared macro data model."""

    macros: list[dict[str, Any]] = []
    position = 0
    for _ in range(count):
        events: list[str] = []
        delays: list[int] = []
        while position < len(buffer) and buffer[position] != MACRO_TERMINATOR:
            if buffer[position] != SS_PREFIX:
                # A literal byte: VIA also allows plain text in a macro. Treat
                # it as a tap so the macro survives a read rather than being
                # dropped.
                events.append(f"#0007{buffer[position]:04X}")
                delays.append(0)
                position += 1
                continue

            action = buffer[position + 1]
            if action == SS_DELAY:
                milliseconds = _decode_delay(buffer[position + 2], buffer[position + 3])
                if delays:
                    delays[-1] = milliseconds
                position += 4
                continue

            modifier = {SS_DOWN: EVENT_PRESS, SS_UP: EVENT_RELEASE, SS_TAP: 0x00}.get(action)
            if modifier is None:
                raise MacroEncodingError(
                    f"The keyboard returned an unknown macro action 0x{action:02X}."
                )
            events.append(f"#{modifier:02X}07{buffer[position + 2]:04X}")
            delays.append(0)
            position += 3

        position += 1  # step over the terminator
        macros.append(
            {
                "original_key": events[0] if events else vial_keymap.CODE_NO,
                "layer_key": events,
                "intvel_ms": delays,
            }
        )
    return macros


def _via_request(session, command: int, *args: int) -> bytes:
    session.send(bytes([command, *args]))
    return session.receive()


def read_capacity(session) -> MacroCapacity:
    """Ask the device what it can hold. Both numbers come from the device."""

    count = _via_request(session, VIA_MACRO_GET_COUNT)[1]
    size = int.from_bytes(_via_request(session, VIA_MACRO_GET_BUFFER_SIZE)[1:3], "big")
    return MacroCapacity(count=count, buffer_bytes=size)


def read_macros(session, *, capacity: MacroCapacity | None = None) -> list[dict[str, Any]]:
    if capacity is None:
        capacity = read_capacity(session)

    buffer = bytearray()
    while len(buffer) < capacity.buffer_bytes:
        offset = len(buffer)
        chunk = min(BUFFER_CHUNK, capacity.buffer_bytes - offset)
        reply = _via_request(
            session, VIA_MACRO_GET_BUFFER, (offset >> 8) & 0xFF, offset & 0xFF, chunk
        )
        buffer += reply[4 : 4 + chunk]
    return decode_macros(bytes(buffer), count=capacity.count)


def write_macros(
    session, macros: list[dict[str, Any]], *, capacity: MacroCapacity | None = None
) -> int:
    """Write the whole macro buffer. Returns the bytes written.

    Compiles and size-checks first: on overflow this raises having sent nothing,
    which is the only safe behaviour when the write replaces everything.
    """

    if capacity is None:
        capacity = read_capacity(session)

    payload = encode_macros(macros, capacity=capacity)

    written = 0
    while written < len(payload):
        chunk = payload[written : written + BUFFER_CHUNK]
        session.send(
            bytes(
                [VIA_MACRO_SET_BUFFER, (written >> 8) & 0xFF, written & 0xFF, len(chunk)]
            )
            + chunk
        )
        session.receive()
        written += len(chunk)
    return written
