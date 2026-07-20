#!/usr/bin/env python3
"""Read and write modern Angry Miao macro tracks.

Relic 80 (AM21) and AFA use the lowercase ``macro_key`` JSON field.  This is
different from the older uppercase ``MACRO_key`` table.  Each macro contains
press/release key events (``#11......`` / ``#10......``) and a 16-bit delay.

The protocol was checked against AM21 hardware: [6,10] returns the same
chunked payload that AM Master's ``cmd_send_macro_key`` emits as [6,5].
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Final

import serial

from .device import BAUD
from .protocol import build_frame, crc_ok, exclusive_serial_kwargs

CMD_GET_KEY_MACRO: Final = (6, 10)
EVENTS_PER_FRAME: Final = 8
EVENT_SIZE: Final = 6  # 4-byte key event + 2-byte big-endian delay
WRITE_DELAY: Final = 0.005


def _code_bytes(code: str) -> bytes:
    if not isinstance(code, str) or len(code) != 9 or not code.startswith("#"):
        raise ValueError(f"invalid macro keycode: {code!r}")
    try:
        raw = bytes.fromhex(code[1:])
    except ValueError as exc:
        raise ValueError(f"invalid macro keycode: {code!r}") from exc
    if len(raw) != 4:
        raise ValueError(f"invalid macro keycode: {code!r}")
    return raw


def macro_frames(macros: list[dict]) -> tuple[bytes, ...]:
    """Encode lowercase ``macro_key`` entries as [6,5] frames."""
    chunks: list[tuple[int, bytes, int, list[str], list[int]]] = []
    for macro_index, macro in enumerate(macros):
        original = _code_bytes(macro.get("original_key", ""))
        events = list(macro.get("layer_key") or [])
        delays = list(macro.get("intvel_ms") or [])
        if len(events) > 200:
            raise ValueError(f"macro {macro_index} has {len(events)} events; maximum is 200")
        for event in events:
            _code_bytes(event)
        for package_index, start in enumerate(range(0, len(events), EVENTS_PER_FRAME)):
            sub_events = events[start : start + EVENTS_PER_FRAME]
            sub_delays = [int(v) for v in delays[start : start + len(sub_events)]]
            sub_delays.extend(0 for _ in range(len(sub_events) - len(sub_delays)))
            if any(not 0 <= delay <= 65535 for delay in sub_delays):
                raise ValueError(f"macro {macro_index} has a delay outside 0..65535ms")
            chunks.append((macro_index, original, package_index, sub_events, sub_delays))

    if len(chunks) > 255:
        raise ValueError(f"macro transfer needs {len(chunks)} frames; maximum is 255")

    total = len(chunks)
    result: list[bytes] = []
    for usb_index, (macro_index, original, package_index, events, delays) in enumerate(chunks):
        payload = bytearray([total, usb_index, macro_index])
        payload += original
        payload += bytes([package_index])
        for event, delay in zip(events, delays):
            payload += _code_bytes(event)
            payload += int(delay).to_bytes(2, "big")
        result.append(build_frame(6, 5, bytes(payload)))
    return tuple(result)


def _drain(port: str, *, timeout: float = 0.7) -> list[bytes]:
    ser = serial.Serial(
        port, baudrate=BAUD, timeout=timeout, write_timeout=2,
        **exclusive_serial_kwargs(),
    )
    try:
        time.sleep(0.1)
        ser.reset_input_buffer()
        ser.write(build_frame(*CMD_GET_KEY_MACRO))
        ser.flush()
        frames: list[bytes] = []
        while True:
            frame = ser.read(64)
            if not frame:
                break
            frames.append(frame)
        return frames
    finally:
        ser.close()


def parse_macro_frames(frames: list[bytes]) -> list[dict]:
    """Decode [6,10] response frames into official lowercase macro JSON."""
    if not frames:
        raise ValueError("macro read returned no frames")
    if any(not crc_ok(frame) for frame in frames):
        raise ValueError("macro read returned a frame with a bad CRC")
    if len(frames) == 1 and frames[0][2] == 0:
        return []
    frames = sorted(frames, key=lambda frame: frame[3])
    total = frames[0][2]
    if total != len(frames) or any(frame[2] != total for frame in frames):
        raise ValueError(f"macro read expected {total} frames, received {len(frames)}")

    grouped: dict[int, list[bytes]] = defaultdict(list)
    for frame in frames:
        if frame[0:2] != bytes(CMD_GET_KEY_MACRO):
            raise ValueError(f"unexpected macro response command {frame[0:2].hex()}")
        grouped[frame[4]].append(frame)

    macros: list[dict] = []
    for macro_index in sorted(grouped):
        group = sorted(grouped[macro_index], key=lambda frame: frame[9])
        original = f"#{group[0][5:9].hex().upper()}"
        events: list[str] = []
        delays: list[int] = []
        for frame in group:
            if frame[5:9] != group[0][5:9]:
                raise ValueError(f"macro {macro_index} changed original_key mid-stream")
            for offset in range(10, 10 + EVENTS_PER_FRAME * EVENT_SIZE, EVENT_SIZE):
                raw = frame[offset : offset + 4]
                if raw == b"\0\0\0\0":
                    break
                events.append(f"#{raw.hex().upper()}")
                delays.append(int.from_bytes(frame[offset + 4 : offset + 6], "big"))
        macros.append({"original_key": original, "layer_key": events, "intvel_ms": delays})
    return macros


def read_macros(port: str) -> list[dict]:
    return parse_macro_frames(_drain(port))


def write_macros(port: str, macros: list[dict], *, timeout: float = 2.0) -> tuple[bytes, ...]:
    """Write modern macro frames.

    The caller should read [6,10] afterward and compare; the command does not
    provide a reliable per-frame acknowledgement.
    """
    frames = macro_frames(macros)
    # A zero-frame control clears the table.  Non-empty transfers carry their
    # total in every frame, matching AM Master's builder.
    outgoing = frames or (build_frame(6, 5, bytes([0, 0, 0]) + b"\0" * 5),)
    ser = serial.Serial(
        port, baudrate=BAUD, timeout=timeout, write_timeout=timeout,
        **exclusive_serial_kwargs(),
    )
    try:
        time.sleep(0.1)
        ser.reset_input_buffer()
        for frame in outgoing:
            time.sleep(WRITE_DELAY)
            ser.write(frame)
        ser.flush()
    finally:
        ser.close()
    return frames
