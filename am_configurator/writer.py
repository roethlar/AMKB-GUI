"""Encode and write full Angry Miao configuration documents.

This is the M1 milestone: take a known-good config — e.g. a merger
`outputs/*.json` the official app was able to write — encode it into the exact
ordered stream of 64-byte frames AM Master sends, and push it over USB CDC
serial with a JSON_START / … / JSON_END handshake.

Faithfully ported from the decompiled originals:
  - TransJsonCmd.py   — every frame's byte layout (the builders)
  - JsonToCmd.py      — chunking (rgb=11, key=5, layer=60) and ordering
  - KBSerialOption.send_r_series_all / json_down — the send sequence + the
    frame-count semantics (START is reset to 0, so JSON_END's total counts the
    DATA frames only — everything between START and END, exclusive).

Two decompiler artifacts were repaired against the clean HATSU analogs and the
clean builders: JsonToCmd's page_control / word_page inner loops (lost) and its
`keyframes is not None` guard (inverted). See .claude/rules/30-write-protocol.md.

A full write replaces keymaps, macros, and LEDs. Callers must perform model
matching and explicit user confirmation before invoking :func:`write_config`.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Final

import serial  # pyserial

from .device import BAUD
from .protocol import build_frame, crc_ok, exclusive_serial_kwargs

# --- send order constants (KBSerialOption.send_r_series_all) ---------------
CMD_JSON_START: Final = (1, 5)
CMD_JSON_END: Final = (1, 6)
RGB_CHUNKS: Final = 11      # 600B display frame / 56 -> 10x56 + 40
KEY_CHUNKS: Final = 5       # 270B per-key frame / 56 -> 4x56 + 46
SPOTLIGHT_CHUNKS: Final = 2 # 72B Relic/AFA edge-light frame / 56 -> 56 + 16
LAYER_CHUNK: Final = 60     # key_layer bytes per [6,7] frame
WORD_PER_FRAME: Final = 28  # unicode chars per [3,1] frame (28*2 = 56B)
PAGES_PER_CONTROL: Final = 4  # page_control entries per [2,2] frame
WRITE_DELAY: Final = 0.005  # GlobalInfo.com_write_delay
SETTLE_SECONDS: Final = 2.0  # flash-commit settle before the post-write probe (matches cb_set/cb_restore)
_PAYLOAD_MAX: Final = 61  # bytes [2:63]


# --- encoding helpers (TransJsonCmd top-of-file) --------------------------
def key_bytes(s: str) -> bytes:
    """`#MMPPUUUU` -> 4 bytes (key_to_bytes / rgba_to_bytes)."""
    return bytes.fromhex(s[1:9])


def rgb_bytes(s: str) -> bytes:
    """`#RRGGBB` -> 3 bytes (rgb_to_bytes)."""
    return bytes.fromhex(s[1:7])


def uni_bytes(s: str) -> bytes:
    """`#XXXX` -> 2 bytes (unicode_to_bytes)."""
    return bytes.fromhex(s[1:5])


def le16(n: int) -> bytes:
    """int_to_bytes(BE, signed) written low-byte-first on the wire."""
    be = int(n).to_bytes(2, "big", signed=True)
    return bytes([be[1], be[0]])


# --- per-section frame builders -------------------------------------------
def uncertainty_frames(pages: list[dict]) -> list[bytes]:
    """[2,1] one manifest frame: page count + per-page frame totals."""
    payload = bytearray([len(pages)])
    for pg in pages:
        payload += bytes([pg["page_index"], pg["word_page"].get("word_len", 0)])
        payload += le16(pg["frames"].get("frame_num", 0))
        payload += le16(pg["keyframes"].get("frame_num", 0))
    return [build_frame(2, 1, bytes(payload))]


def page_control_frames(pages: list[dict]) -> list[bytes]:
    """[2,2] page display settings, PAGES_PER_CONTROL pages per frame."""
    usb_count = math.ceil(len(pages) / PAGES_PER_CONTROL)

    def frame(idx: int) -> bytes:
        chunk = pages[idx * PAGES_PER_CONTROL : (idx + 1) * PAGES_PER_CONTROL]
        payload = bytearray([usb_count, idx, len(chunk)])
        for pg in chunk:
            color = pg["color"]
            payload += bytes([int(bool(pg["valid"])), pg["page_index"], pg["lightness"]])
            payload += le16(pg["speed_ms"])
            payload += bytes([int(bool(color["default"]))])
            payload += rgb_bytes(color["back_rgb"]) + rgb_bytes(color["rgb"])
        return build_frame(2, 2, bytes(payload))

    return [frame(i) for i in range(usb_count)]


def word_page_frames(pages: list[dict]) -> list[bytes]:
    """[3,1] text pages — only pages whose word_page has chars."""
    frames: list[bytes] = []
    for pg in pages:
        wp = pg["word_page"]
        chars = wp.get("unicode", [])
        if wp.get("word_len", 0) == 0:
            continue
        count = math.ceil(len(chars) / WORD_PER_FRAME)
        for i in range(count):
            sub = chars[i * WORD_PER_FRAME : (i + 1) * WORD_PER_FRAME]
            payload = bytes([i, pg["page_index"], int(bool(wp["valid"])), len(sub)])
            payload += b"".join(uni_bytes(c) for c in sub)
            frames.append(build_frame(3, 1, payload))
    return frames


def _rgb_all(frame_data: dict) -> bytes:
    return b"".join(rgb_bytes(c) for c in frame_data["frame_RGB"])


def rgb_frame_frames(pages: list[dict]) -> list[bytes]:
    """[4,page_index] 200px display frames: 600B -> 11 chunks of <=56B."""
    frames: list[bytes] = []
    for pg in pages:
        if pg["frames"].get("frame_num", 0) == 0:
            continue
        for fd in pg["frames"]["frame_data"]:
            blob = _rgb_all(fd)
            for i in range(RGB_CHUNKS):
                chunk = blob[i * 56 : (i + 1) * 56] if i < 10 else blob[10 * 56 : 600]
                payload = le16(fd["frame_index"]) + bytes([i]) + chunk
                frames.append(build_frame(4, pg["page_index"], payload))
    return frames


def key_frame_frames(pages: list[dict]) -> list[bytes]:
    """[5,page_index] 90 per-key frames: 270B -> 5 chunks of <=56B."""
    frames: list[bytes] = []
    for pg in pages:
        kf = pg["keyframes"]
        if kf is None or kf.get("frame_num", 0) == 0:
            continue
        for fd in kf["frame_data"]:
            blob = _rgb_all(fd)
            for i in range(KEY_CHUNKS):
                chunk = blob[i * 56 : (i + 1) * 56] if i < 4 else blob[4 * 56 : 270]
                payload = bytes([fd["frame_index"], i]) + chunk
                frames.append(build_frame(5, pg["page_index"], payload))
    return frames


def car_light_info_frames(pages: list[dict]) -> list[bytes]:
    """[12,1] manifest for the three custom-page spotlight/edge-light tracks.

    Relic 80 and AFA exports attach ``spotlight_frames`` to pages 5..7.  AM
    Master's wire format stores each frame count as two *decimal* bytes
    (hundreds, remainder), rather than a normal base-256 integer.  CyberBoard
    R4 configs simply omit the section, so this remains backwards compatible.
    """
    by_index = {pg.get("page_index"): pg for pg in pages}
    tracks = [
        by_index.get(page_index, {}).get("spotlight_frames")
        for page_index in (5, 6, 7)
    ]
    if all(track is None for track in tracks):
        return []
    # The manifest has no page IDs: its three positions always mean pages 5–7.
    tracks = [
        track if track is not None else {"valid": 0, "frame_num": 0}
        for track in tracks
    ]
    payload = bytearray(int(bool(track.get("valid"))) for track in tracks)
    for track in tracks:
        count = int(track.get("frame_num", 0))
        if not 0 <= count <= 999:
            raise ValueError(f"spotlight frame count out of range: {count}")
        payload += bytes(divmod(count, 100))
    return [build_frame(12, 1, bytes(payload))]


def car_light_data_frames(pages: list[dict]) -> list[bytes]:
    """[12,2] Relic/AFA spotlight frames (24 RGB pixels = 72B, two chunks)."""
    frames: list[bytes] = []
    for pg in pages:
        track = pg.get("spotlight_frames")
        if track is not None and pg.get("page_index") not in (5, 6, 7):
            raise ValueError("spotlight_frames are supported only on pages 5, 6, and 7")
        if not track or int(track.get("frame_num", 0)) == 0:
            continue
        for fd in track.get("frame_data", []):
            blob = _rgb_all(fd)
            if len(blob) != 72:
                raise ValueError(
                    f"spotlight page {pg.get('page_index')} frame "
                    f"{fd.get('frame_index')} has {len(blob) // 3} pixels; expected 24"
                )
            frame_index = int(fd["frame_index"]).to_bytes(2, "big", signed=False)
            for chunk_index in range(SPOTLIGHT_CHUNKS):
                chunk = blob[chunk_index * 56 : (chunk_index + 1) * 56]
                payload = bytes([pg["page_index"]]) + frame_index + bytes([chunk_index]) + chunk
                frames.append(build_frame(12, 2, payload))
    return frames


def exchange_frames(config: dict) -> list[bytes]:
    """[6,1] one frame per exchange_key entry (input @4, output @24)."""
    num = config.get("exchange_num", 0)

    def frame(ek: dict) -> bytes:
        payload = bytearray(_PAYLOAD_MAX)
        payload[0] = num
        payload[1] = ek["exchange_index"]
        for i, k in enumerate(ek["input_key"]):
            payload[2 + i * 4 : 6 + i * 4] = key_bytes(k)
        for i, k in enumerate(ek["out_key"]):
            payload[22 + i * 4 : 26 + i * 4] = key_bytes(k)
        return build_frame(6, 1, bytes(payload))

    return [frame(ek) for ek in config.get("exchange_key", [])]


def swap_frames(config: dict) -> list[bytes]:
    """[6,6] swap keys, up to 11 per frame (9B each: index + in + out)."""
    swaps = config.get("swap_key", [])
    num = config.get("swap_key_num", len(swaps))
    usb_count = math.ceil(len(swaps) / 11) if swaps else 0

    def frame(idx: int) -> bytes:
        chunk = swaps[idx * 11 : (idx + 1) * 11]
        payload = bytearray([num, len(chunk)])
        for s in chunk:
            payload += bytes([s["swap_key_index"]]) + key_bytes(s["input_key"]) + key_bytes(s["out_key"])
        return build_frame(6, 6, bytes(payload))

    return [frame(i) for i in range(usb_count)]


def key_layer_frames(config: dict) -> list[bytes]:
    """[6,8] layer count, then [6,7] layer matrix in 60B chunks."""
    kl = config.get("key_layer")
    if kl is None or not kl.get("valid"):
        return []
    layer_num = kl["layer_num"]
    blob = b"".join(
        key_bytes(k) for layer in kl["layer_data"] for k in layer["layer"]
    )
    count = math.ceil(len(blob) / LAYER_CHUNK)
    control = build_frame(6, 8, bytes([layer_num]))
    chunks = [
        build_frame(6, 7, bytes([i]) + blob[i * LAYER_CHUNK : (i + 1) * LAYER_CHUNK])
        for i in range(count)
    ]
    return [control, *chunks]


@dataclass(frozen=True)
class FramePlan:
    sections: tuple[tuple[str, int], ...]
    frames: tuple[bytes, ...]

    @property
    def total(self) -> int:
        return len(self.frames)


def plan(config: dict) -> FramePlan:
    """Build the ordered data-frame stream (excludes START/END)."""
    pages = config["page_data"]
    sections = (
        ("uncertainty", uncertainty_frames(pages)),
        ("page_control", page_control_frames(pages)),
        ("word_page", word_page_frames(pages)),
        ("rgb_frame", rgb_frame_frames(pages)),
        ("key_frame", key_frame_frames(pages)),
        ("exchange", exchange_frames(config)),
        ("swap", swap_frames(config)),
        ("key_layer", key_layer_frames(config)),
        ("car_light_info", car_light_info_frames(pages)),
        ("car_light_data", car_light_data_frames(pages)),
    )
    frames = tuple(f for _, fs in sections for f in fs)
    return FramePlan(tuple((name, len(fs)) for name, fs in sections), frames)


def write_config(port: str, frames: tuple[bytes, ...], *, timeout: float = 10.0) -> tuple[bool, bytes]:
    """JSON_START -> all data frames (5ms apart) -> JSON_END(total). Returns (ack, end_reply)."""
    ser = serial.Serial(
        port, baudrate=BAUD, timeout=timeout, write_timeout=timeout,
        **exclusive_serial_kwargs(),
    )
    try:
        time.sleep(0.1)
        ser.reset_input_buffer()

        ser.write(build_frame(*CMD_JSON_START))
        ser.flush()
        start_reply = ser.read(64)
        if not (len(start_reply) >= 3 and start_reply[2] == 1):
            return False, start_reply

        for frame in frames:
            time.sleep(WRITE_DELAY)
            ser.write(frame)
        ser.flush()

        end = build_frame(*CMD_JSON_END, len(frames).to_bytes(4, "big", signed=True))
        time.sleep(WRITE_DELAY)
        ser.write(end)
        ser.flush()

        reply = ser.read(64)
        # rev[2]==2 means "wait, flashing" — poll a bounded number of times.
        for _ in range(15):
            if len(reply) >= 3 and reply[2] == 1:
                return True, reply
            if not (len(reply) >= 3 and reply[2] == 2):
                break
            time.sleep(1.0)
            reply = ser.read(64)
        return (len(reply) >= 3 and reply[2] == 1), reply
    finally:
        ser.close()
