"""Read keymaps from supported Angry Miao keyboards.

The official app never uses the device's read commands (the `cmd_get_*`
builders in TransJsonCmd are dead code), but the R4 firmware honors them. In
particular [6,9] (get_key_msg) streams the entire key_layer matrix back as
4-byte keycodes, chunked 60 bytes per frame exactly like the [6,7] write.

Verified on hardware 2026-06-22: dumping after a full write round-trips
1400/1400 keycodes (7 layers x 200 keys) with zero mismatches — so this gives
automated write -> read -> diff verification for the keymap. (No LED-frame
read-back path is known; [6,15] get_flash returns only flash status metadata,
not frame data, so LED still needs a visual check.)

"""
from __future__ import annotations

import time
from typing import Final

import serial  # pyserial

from .device import BAUD
from .protocol import build_frame, crc_ok, exclusive_serial_kwargs

CMD_GET_KEY_MSG: Final = (6, 9)
KEYS_PER_LAYER: Final = 200  # 25 x 8 physical matrix
DEFAULT_LAYERS: Final = 7    # R4
CHUNK: Final = 60            # payload bytes per [6,9] frame


def _drain(port: str, command: tuple[int, int], *, timeout: float = 1.0) -> list[bytes]:
    ser = serial.Serial(
        port, baudrate=BAUD, timeout=timeout, write_timeout=2,
        **exclusive_serial_kwargs(),
    )
    try:
        time.sleep(0.1)
        ser.reset_input_buffer()
        ser.write(build_frame(*command))
        ser.flush()
        frames: list[bytes] = []
        while True:
            chunk = ser.read(64)
            if not chunk:
                break
            frames.append(chunk)
        return frames
    finally:
        ser.close()


def read_keymap(port: str, *, layers: int = DEFAULT_LAYERS) -> list[list[str]]:
    """Return `layers` lists of KEYS_PER_LAYER `#MMPPUUUU` keycodes."""
    frames = _drain(port, CMD_GET_KEY_MSG)
    if any(not crc_ok(f) for f in frames):
        raise ValueError("keymap read returned a frame with a bad CRC")
    frames = sorted(frames, key=lambda f: f[2])
    blob = b"".join(f[3:63] for f in frames)
    codes = ["#%02X%02X%02X%02X" % tuple(blob[i : i + 4]) for i in range(0, len(blob), 4)]
    return [codes[i * KEYS_PER_LAYER : (i + 1) * KEYS_PER_LAYER] for i in range(layers)]
