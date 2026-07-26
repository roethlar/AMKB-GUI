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

    The inverse of `to_qmk` over its whole range, which is what makes read-back
    stable: writing then reading a representable keymap returns the codes that
    were written, character for character.
    """

    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{value!r} is not a 16-bit keycode.")

    usage = value & 0xFF
    mods = (value >> 8) & 0x1F
    if (value >> 8) & ~0x1F:
        raise UnsupportedKeycode(
            f"0x{value:04X}",
            "it is a QMK feature keycode with no application representation",
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
