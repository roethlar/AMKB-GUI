"""Keymap translation between the application's codes and QMK's, for Vial.

The application's keymap surface is 32-bit: `#MMPPUUUU` is a modifier mask, a
HID usage page, and a 16-bit usage. QMK keycodes are 16-bit. A lossless
round-trip of every code the UI can emit is therefore **impossible** on a Vial
device, and pretending otherwise would mean silently coercing codes into
something the user did not ask for.

So this module defines the subset where translation is *provably injective*, and
rejects everything else by name:

- Usage page `0x07` — HID keyboard/keypad — with a usage of `0xFF` or less.
  QMK's basic keycodes are exactly those usages, so the mapping is the identity
  and round-trips byte for byte.
- Modifiers that live on one side only. QMK packs modifiers as five bits: four
  for Ctrl/Shift/Alt/GUI and one meaning "right-hand". The application uses the
  HID mask, which names left and right independently, so a code holding both a
  left and a right modifier has no QMK spelling. Those are rejected rather than
  flattened onto one side.

Everything outside that — vendor usage pages, consumer-control codes, usages
above `0xFF`, mixed-side modifiers — is refused with a typed error naming the
code and the reason. The caller is expected to surface that at assignment time,
so it never reaches a device.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


HID_KEYBOARD_PAGE = 0x07
MAX_BASIC_USAGE = 0xFF

# Reserved page carrying a raw QMK keycode in the usage field.
#
# The translation is not symmetric, and hardware proved it: the application's
# 32-bit surface can express codes QMK cannot, *and* QMK has feature keycodes
# (layer switches, tap-dance, macros) the application's HID vocabulary cannot
# name. The owner's board reports 0x5101 in its shipped keymap.
#
# Reading must never fail, so an untranslatable QMK code is carried verbatim on
# this page instead. That is lossless in both directions: the 16-bit keycode
# fits the 16-bit usage field exactly. A code that *does* have a natural
# spelling is rejected on this page, so every keycode has exactly one
# representation and read-back is stable.
QMK_PASSTHROUGH_PAGE = 0xFF

# QMK modifier bits, in QMK's order, and the HID mask bit each corresponds to.
_QMK_CTRL, _QMK_SHIFT, _QMK_ALT, _QMK_GUI = 0x01, 0x02, 0x04, 0x08
_QMK_RIGHT = 0x10

_HID_LEFT_MASK = 0x0F
_HID_RIGHT_MASK = 0xF0

_CODE_PATTERN = re.compile(r"^#[0-9A-Fa-f]{8}$")

KC_NO = 0x0000
CODE_NO = "#00070000"


class UnsupportedKeycode(ValueError):
    """A code the application can express and QMK cannot.

    Carries the offending code so a caller can tell the user exactly which key
    is the problem, rather than reporting that "the keymap" failed.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code} cannot be written to this keyboard: {reason}")
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class CodeParts:
    modifier: int
    page: int
    usage: int


def parse_code(code: str) -> CodeParts:
    text = str(code).strip()
    if not _CODE_PATTERN.match(text):
        raise UnsupportedKeycode(text, "it is not a #MMPPUUUU keycode")
    raw = bytes.fromhex(text[1:])
    return CodeParts(modifier=raw[0], page=raw[1], usage=(raw[2] << 8) | raw[3])


def format_code(parts: CodeParts) -> str:
    return f"#{parts.modifier:02X}{parts.page:02X}{parts.usage:04X}"


def _qmk_mods(modifier: int, code: str) -> int:
    """Translate a HID modifier mask into QMK's five-bit form."""

    if modifier == 0:
        return 0

    left = modifier & _HID_LEFT_MASK
    right = (modifier & _HID_RIGHT_MASK) >> 4
    if left and right:
        raise UnsupportedKeycode(
            code,
            "it holds left and right modifiers at once, which QMK cannot "
            "express: QMK stores one right-hand flag for all four modifiers",
        )

    nibble = left or right
    mods = 0
    for hid_bit, qmk_bit in (
        (0x01, _QMK_CTRL),
        (0x02, _QMK_SHIFT),
        (0x04, _QMK_ALT),
        (0x08, _QMK_GUI),
    ):
        if nibble & hid_bit:
            mods |= qmk_bit
    if right:
        mods |= _QMK_RIGHT
    return mods


def to_qmk(code: str) -> int:
    """Translate one application keycode to a 16-bit QMK keycode."""

    parts = parse_code(code)

    if parts.page == QMK_PASSTHROUGH_PAGE:
        if parts.modifier:
            raise UnsupportedKeycode(
                code, "a raw QMK keycode carries its own modifiers already"
            )
        natural = from_qmk(parts.usage)
        if not natural.startswith(f"#{0:02X}{QMK_PASSTHROUGH_PAGE:02X}"):
            raise UnsupportedKeycode(
                code,
                f"0x{parts.usage:04X} has a normal spelling, {natural}; keeping "
                "two spellings for one keycode would make read-back unstable",
            )
        return parts.usage

    if parts.page != HID_KEYBOARD_PAGE:
        raise UnsupportedKeycode(
            code,
            f"usage page 0x{parts.page:02X} has no QMK equivalent; only the HID "
            f"keyboard page 0x{HID_KEYBOARD_PAGE:02X} translates",
        )
    if parts.usage > MAX_BASIC_USAGE:
        raise UnsupportedKeycode(
            code,
            f"usage 0x{parts.usage:04X} is above 0x{MAX_BASIC_USAGE:02X}, beyond "
            "QMK's basic keycode range",
        )

    mods = _qmk_mods(parts.modifier, code)
    return (mods << 8) | parts.usage


def from_qmk(value: int) -> str:
    """Translate a 16-bit QMK keycode back to an application keycode.

    Total: every 16-bit value has a representation, because a keyboard's own
    keymap is full of QMK feature codes and refusing to read them would make the
    device unreadable. Codes with a HID spelling get it; the rest travel on the
    passthrough page. Either way `to_qmk(from_qmk(v)) == v`, which is what makes
    read-back stable.
    """

    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{value!r} is not a 16-bit keycode.")

    usage = value & 0xFF
    mods = (value >> 8) & 0x1F
    if (value >> 8) & ~0x1F:
        # A QMK feature keycode. It has no HID spelling, so it travels verbatim
        # rather than failing the read.
        return format_code(
            CodeParts(modifier=0, page=QMK_PASSTHROUGH_PAGE, usage=value)
        )

    modifier = 0
    if mods:
        nibble = 0
        for qmk_bit, hid_bit in (
            (_QMK_CTRL, 0x01),
            (_QMK_SHIFT, 0x02),
            (_QMK_ALT, 0x04),
            (_QMK_GUI, 0x08),
        ):
            if mods & qmk_bit:
                nibble |= hid_bit
        if not nibble:
            # QMK's right-hand flag set with no modifier selected. The HID mask
            # has no bit for "right" on its own, so this has no spelling and
            # travels verbatim rather than collapsing to an unmodified key.
            return format_code(
                CodeParts(modifier=0, page=QMK_PASSTHROUGH_PAGE, usage=value)
            )
        modifier = (nibble << 4) if (mods & _QMK_RIGHT) else nibble

    return format_code(CodeParts(modifier=modifier, page=HID_KEYBOARD_PAGE, usage=usage))


def is_representable(code: str) -> bool:
    """Whether a code survives translation. Never raises."""

    try:
        to_qmk(code)
    except (UnsupportedKeycode, ValueError):
        return False
    return True


def unsupported_codes(layers: list[list[str]]) -> list[tuple[int, int, str, str]]:
    """Every code in a keymap that cannot be written, with where it sits.

    Returns `(layer, index, code, reason)`. A stored profile is allowed to hold
    unsupported codes — it loads and displays fine — so the check runs when the
    profile is applied to a Neon, and names the keys rather than the file.
    """

    problems: list[tuple[int, int, str, str]] = []
    for layer_index, layer in enumerate(layers):
        for key_index, code in enumerate(layer):
            try:
                to_qmk(code)
            except UnsupportedKeycode as error:
                problems.append((layer_index, key_index, error.code, error.reason))
            except ValueError:
                problems.append((layer_index, key_index, str(code), "it is malformed"))
    return problems


def encode_layers(layers: list[list[str]]) -> bytes:
    """Encode a full keymap into QMK's big-endian 16-bit buffer.

    Refuses the whole keymap if any code is unsupported: a partially translated
    keymap written to a device is worse than one that was never written, and the
    caller gets every offending key at once rather than one per attempt.
    """

    problems = unsupported_codes(layers)
    if problems:
        listing = ", ".join(
            f"layer {layer} key {index} ({code})" for layer, index, code, _ in problems[:5]
        )
        more = "" if len(problems) <= 5 else f", and {len(problems) - 5} more"
        raise UnsupportedKeycode(
            problems[0][2],
            f"{len(problems)} key(s) cannot be written to this keyboard: "
            f"{listing}{more}",
        )

    buffer = bytearray()
    for layer in layers:
        for code in layer:
            buffer += to_qmk(code).to_bytes(2, "big")
    return bytes(buffer)


def decode_layers(buffer: bytes, *, layers: int, keys_per_layer: int) -> list[list[str]]:
    """Decode QMK's keymap buffer back into application keycodes."""

    expected = layers * keys_per_layer * 2
    if len(buffer) < expected:
        raise ValueError(
            f"The keymap buffer holds {len(buffer)} bytes; {expected} were expected."
        )

    codes = [
        from_qmk(int.from_bytes(buffer[offset : offset + 2], "big"))
        for offset in range(0, expected, 2)
    ]
    return [
        codes[layer * keys_per_layer : (layer + 1) * keys_per_layer]
        for layer in range(layers)
    ]


# --- Device transport -----------------------------------------------------
#
# VIA carries the keymap as one flat big-endian 16-bit buffer, read and written
# in chunks that fit a 32-byte report. These are VIA commands, not Vial's
# `0xFE`-prefixed ones, so they do not go through `hid_transport._vial_request`
# and its read-only allowlist; the write commands here are genuinely mutating
# and are gated on an unlocked device instead.

VIA_GET_LAYER_COUNT = 0x11
VIA_GET_BUFFER = 0x12
VIA_SET_BUFFER = 0x13

# A report is 32 bytes: one command, two offset, one length, leaving 28.
BUFFER_CHUNK = 28

_UNLOCK_STATUS_UNLOCKED = 1


class KeyboardLocked(RuntimeError):
    """Vial refuses keymap writes until the board is physically unlocked.

    This is a distinct, actionable state and not a generic write failure: the
    user has to hold specific keys on the keyboard itself, which no amount of
    retrying from software will accomplish.
    """


def _via_request(session, command: int, *args: int) -> bytes:
    session.send(bytes([command, *args]))
    return session.receive()


def read_layer_count(session) -> int:
    """How many layers this keyboard actually has.

    Asked rather than assumed. The AM serial families have seven; the Neon
    reports four, and defaulting to seven would read past the end of its keymap.
    """

    return _via_request(session, VIA_GET_LAYER_COUNT)[1]


def read_keymap_buffer(session, *, size: int) -> bytes:
    """Read `size` bytes of the keymap buffer, chunked to fit a report."""

    buffer = bytearray()
    while len(buffer) < size:
        offset = len(buffer)
        chunk = min(BUFFER_CHUNK, size - offset)
        reply = _via_request(
            session, VIA_GET_BUFFER, (offset >> 8) & 0xFF, offset & 0xFF, chunk
        )
        buffer += reply[4 : 4 + chunk]
    return bytes(buffer)


def read_keymap(session, *, layers: int | None = None, keys_per_layer: int) -> list[list[str]]:
    """Read and translate the whole keymap."""

    if layers is None:
        layers = read_layer_count(session)
    buffer = read_keymap_buffer(session, size=layers * keys_per_layer * 2)
    return decode_layers(buffer, layers=layers, keys_per_layer=keys_per_layer)


def unlock_status(session) -> tuple[bool, int]:
    """Whether the board is unlocked, and how many keys it wants held.

    Read-only, and the reason a write can report something the user can act on
    instead of a bare failure.
    """

    from . import hid_transport

    reply = _via_request(session, 0xFE, hid_transport.VIAL_GET_UNLOCK_STATUS)
    return reply[0] == _UNLOCK_STATUS_UNLOCKED, reply[1]


def write_keymap(session, layers: list[list[str]], *, require_unlocked: bool = True) -> int:
    """Translate and write a whole keymap. Returns the bytes written.

    The translation runs first and refuses everything if any code is
    unsupported, so an unsupported keycode is reported before a single byte
    reaches the device rather than partway through the buffer.
    """

    payload = encode_layers(layers)

    if require_unlocked:
        unlocked, held_keys = unlock_status(session)
        if not unlocked:
            raise KeyboardLocked(
                "This keyboard is locked. Vial requires it to be unlocked from "
                f"the keyboard itself: hold the {held_keys} designated key(s) "
                "until it reports unlocked, then write again. Nothing was "
                "written."
            )

    written = 0
    while written < len(payload):
        chunk = payload[written : written + BUFFER_CHUNK]
        session.send(
            bytes([VIA_SET_BUFFER, (written >> 8) & 0xFF, written & 0xFF, len(chunk)])
            + chunk
        )
        session.receive()
        written += len(chunk)
    return written
