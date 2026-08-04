"""Translate US-layout text into the shared macro event model.

VIA/Vial stores literal text bytes alongside explicit key actions. The browser
editor, serial protocol, and portable JSON instead represent key-down and
key-up events. Keeping the character map here gives both the editor's
Text-to-keystrokes helper and Vial readback one canonical translation.
"""

from __future__ import annotations

import random
from typing import Any


US_TEXT_KEYSTROKES: dict[str, tuple[int, bool]] = {
    "\b": (0x2A, False),
    "\t": (0x2B, False),
    "\n": (0x28, False),
    "\x1b": (0x29, False),
    " ": (0x2C, False),
    "-": (0x2D, False),
    "_": (0x2D, True),
    "=": (0x2E, False),
    "+": (0x2E, True),
    "[": (0x2F, False),
    "{": (0x2F, True),
    "]": (0x30, False),
    "}": (0x30, True),
    "\\": (0x31, False),
    "|": (0x31, True),
    ";": (0x33, False),
    ":": (0x33, True),
    "'": (0x34, False),
    '"': (0x34, True),
    "`": (0x35, False),
    "~": (0x35, True),
    ",": (0x36, False),
    "<": (0x36, True),
    ".": (0x37, False),
    ">": (0x37, True),
    "/": (0x38, False),
    "?": (0x38, True),
    "\x7f": (0x4C, False),
}
for _offset, _character in enumerate("abcdefghijklmnopqrstuvwxyz"):
    US_TEXT_KEYSTROKES[_character] = (0x04 + _offset, False)
    US_TEXT_KEYSTROKES[_character.upper()] = (0x04 + _offset, True)
for _offset, (_plain, _shifted) in enumerate(zip("1234567890", "!@#$%^&*()")):
    US_TEXT_KEYSTROKES[_plain] = (0x1E + _offset, False)
    US_TEXT_KEYSTROKES[_shifted] = (0x1E + _offset, True)


def natural_delays(
    count: int,
    *,
    wpm: int | None = None,
    cadence: list[int] | None = None,
    seed: int = 0,
) -> list[int]:
    """Build per-key pauses that read as natural typing.

    With ``cadence`` the pauses are drawn from the user's own recorded sample;
    otherwise they jitter seeded-randomly around the WPM target's interval
    (60000 / (5 * WPM) ms) or a 90 ms default. The seed makes every result
    deterministic: the same inputs regenerate the same macro.
    """

    if count < 0:
        raise ValueError("The key count cannot be negative.")
    rng = random.Random(seed)
    if cadence is not None:
        return [rng.choice(cadence) for _ in range(count)]
    mean = round(60000 / (5 * wpm)) if wpm else 90
    return [max(1, min(1000, round(mean * rng.uniform(0.6, 1.4)))) for _ in range(count)]


def compile_us_text(
    text: str,
    *,
    inter_key_delay_ms: int,
    transition_delay_ms: int,
    release_shift_each_character: bool = False,
    max_events: int | None = None,
    inter_key_delays: list[int] | None = None,
) -> dict[str, Any]:
    """Compile text to deterministic key-down/up events.

    ``release_shift_each_character`` mirrors QMK ``send_char`` exactly: a
    shifted literal registers and releases Shift around that one character.
    The interactive editor leaves it false so adjacent shifted characters use
    one readable Shift run. ``inter_key_delays`` overrides the uniform
    ``inter_key_delay_ms`` with one pause per character (natural timing).
    """

    if not isinstance(text, str) or not text:
        raise ValueError("Enter some text to convert.")
    if inter_key_delay_ms < 0 or transition_delay_ms < 0:
        raise ValueError("Macro event delays cannot be negative.")
    if inter_key_delays is not None:
        if len(inter_key_delays) != len(text):
            raise ValueError("Natural timing needs exactly one pause per character.")
        if any(pause < 0 for pause in inter_key_delays):
            raise ValueError("Macro event delays cannot be negative.")

    events: list[str] = []
    delays: list[int] = []
    shift_down = False

    def emit(usage: int, down: bool, pause: int) -> None:
        events.append(f"#{0x11 if down else 0x10:02X}07{usage:04X}")
        delays.append(pause)

    for index, character in enumerate(text):
        mapping = US_TEXT_KEYSTROKES.get(character)
        if mapping is None:
            raise ValueError(
                f"Character {character!r} at position {index + 1} is not available "
                "on the US keyboard layout."
            )
        usage, needs_shift = mapping
        if needs_shift != shift_down:
            emit(0xE1, needs_shift, transition_delay_ms)
            shift_down = needs_shift
        emit(usage, True, transition_delay_ms)
        pause = inter_key_delays[index] if inter_key_delays is not None else inter_key_delay_ms
        emit(usage, False, pause)
        if release_shift_each_character and shift_down:
            emit(0xE1, False, transition_delay_ms)
            shift_down = False

    if shift_down:
        emit(0xE1, False, transition_delay_ms)
    if delays:
        delays[-1] = 0
    if max_events is not None and len(events) > max_events:
        raise ValueError(
            f"This text needs {len(events)} macro events; the complete profile "
            f"limit is {max_events}."
        )
    return {"layer_key": events, "intvel_ms": delays}
