"""Lighting push for the AM Neon 80 over the vendor `0xF0` HID command.

One authored effect becomes three transmitted channels. The user paints two
tracks — axial (89 per-switch LEDs) and head (230 LEDs, 46x5 row-major) — and
the side zone is *derived* from the head frames at transmit time. Side is
therefore never independently authored and is not a selectable track; see the
plan's "Zones, slots, and capacity".

Slot *N* transmits as channels *N*, *N+3*, and *N+6*: axial, head, side.

Packets are 32 bytes. Byte `[0]` is the command selector and `[1..31]` are the
payload the driver actually sends, so the checksum covers `[0..30]`. `packIndex`
is the packet's index within its frame, except on the very last packet of the
very last frame, where it is `255` — that terminator is what tells the firmware
the upload is complete, so a stream that omits it leaves the device waiting.

Nothing here opens a device. Transmission takes an already-approved session from
`hid_transport.open_approved`, which is the only thing that may write to a
keyboard.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


LIGHTING_COMMAND = 0xF0
PACKET_LENGTH = 32
MAX_RGB_BYTES = 24
LEDS_PER_PACKET = 8

AXIAL_LED_COUNT = 89
HEAD_LED_COUNT = 230
SIDE_LED_COUNT = 70

HEAD_ROWS = 5
HEAD_COLUMNS = 46
SIDE_ROWS = 4
SIDE_COLUMNS = 21

MAX_FRAMES = 256
SLOTS = (1, 2, 3)

# Channel bases from the firmware's command enum: axial 0x01-0x03,
# head 0x04-0x06, side 0x07-0x09, one per user slot.
_AXIAL_BASE = 0x01
_HEAD_BASE = 0x04
_SIDE_BASE = 0x07

_FINAL_PACKET_MARKER = 255


class NeonLightingError(RuntimeError):
    """A lighting push could not be built or completed."""


class NeonLightingRejected(NeonLightingError):
    """The keyboard did not return the expected packet echo.

    Names the zone and frame, because an unexpected reply partway through an upload
    leaves the device holding an incomplete effect and the user needs to know
    which one.
    """


def _rgb_bytes(color: str) -> bytes:
    text = str(color).strip()
    if not text.startswith("#") or len(text) != 7:
        raise NeonLightingError(f"Colour {color!r} is not a #RRGGBB value.")
    try:
        return bytes.fromhex(text[1:])
    except ValueError:
        raise NeonLightingError(f"Colour {color!r} is not a #RRGGBB value.") from None


def derive_side_frame(head: Sequence[str]) -> list[str]:
    """Derive the 70 side colours from one 230-value head frame.

    Nearest-neighbour downsample of the 46x5 head matrix to 21x4, walked row by
    row, with fourteen positions skipped where the case has no side LED. The
    skips are not decorative: 84 candidates minus 14 is exactly `SIDE_LED_NUM`,
    and any variation produces a frame the firmware will not accept.
    """

    if len(head) != HEAD_LED_COUNT:
        raise NeonLightingError(
            f"A head frame must hold {HEAD_LED_COUNT} colours, got {len(head)}."
        )

    side: list[str] = []
    for y in range(SIDE_ROWS):
        for x in range(SIDE_COLUMNS):
            if y == 0 and 4 < x < 16:
                continue
            if y == 1 and x in (6, 7):
                continue
            if y == 3 and x == 6:
                continue
            source_x = (x * HEAD_COLUMNS) // SIDE_COLUMNS
            source_y = (y * HEAD_ROWS) // SIDE_ROWS
            side.append(head[source_y * HEAD_COLUMNS + source_x])

    if len(side) != SIDE_LED_COUNT:  # pragma: no cover - guarded by the tests
        raise NeonLightingError(
            f"Side derivation produced {len(side)} colours, expected {SIDE_LED_COUNT}."
        )
    return side


def _checksum(packet: Sequence[int]) -> int:
    return sum(packet[0:31]) & 0xFF


def build_frame_packets(
    channel: int,
    frame_index: int,
    colors: Sequence[str],
    *,
    lightness: int,
    interval: int,
    is_final_frame: bool,
) -> list[bytes]:
    """Build every 32-byte packet for one frame on one channel."""

    payload = b"".join(_rgb_bytes(color) for color in colors)
    chunks = [
        payload[offset : offset + MAX_RGB_BYTES]
        for offset in range(0, len(payload), MAX_RGB_BYTES)
    ] or [b""]

    packets: list[bytes] = []
    for index, chunk in enumerate(chunks):
        last_of_frame = index == len(chunks) - 1
        packet = bytearray(PACKET_LENGTH)
        packet[0] = LIGHTING_COMMAND
        packet[1] = channel
        packet[2] = frame_index & 0xFF
        # The terminator marks the end of the whole upload, not the end of a
        # frame: only the last packet of the last frame carries it.
        packet[3] = (
            _FINAL_PACKET_MARKER if (is_final_frame and last_of_frame) else index & 0xFF
        )
        packet[4] = lightness & 0xFF
        packet[5] = interval & 0xFF
        packet[6] = len(chunk)
        packet[7 : 7 + len(chunk)] = chunk
        packet[31] = _checksum(packet)
        packets.append(bytes(packet))
    return packets


def _expected_reply(packet: bytes, packet_index: int) -> bytes:
    """Return the echo produced by the Neon's vendor-lighting firmware.

    The reply has no status byte: byte 7 is the first echoed RGB byte. On the
    final packet, firmware replaces the 0xFF terminator with that packet's real
    index before recomputing the checksum and returning the report.
    """

    expected = bytearray(packet)
    if expected[3] == _FINAL_PACKET_MARKER:
        expected[3] = packet_index & 0xFF
        expected[31] = _checksum(expected)
    return bytes(expected)


@dataclass(frozen=True)
class ChannelUpload:
    """Every packet for one zone of one slot, with the zone named for errors."""

    zone: str
    channel: int
    frames: tuple[tuple[bytes, ...], ...]

    @property
    def packet_count(self) -> int:
        return sum(len(frame) for frame in self.frames)


@dataclass(frozen=True)
class LightingPlan:
    """A complete, validated upload. Building one sends nothing."""

    slot: int
    uploads: tuple[ChannelUpload, ...]

    @property
    def packet_count(self) -> int:
        return sum(upload.packet_count for upload in self.uploads)


def plan_push(
    axial_frames: Sequence[Sequence[str]],
    head_frames: Sequence[Sequence[str]],
    *,
    slot: int,
    lightness: int = 100,
    interval: int = 90,
) -> LightingPlan:
    """Validate an effect and build every packet, before anything is sent.

    Everything that can be checked is checked here: a rejection partway through
    an upload leaves the keyboard holding half an effect, so the frame counts
    and track lengths are proven correct while that still costs nothing.
    """

    if slot not in SLOTS:
        raise NeonLightingError(f"Slot must be one of {SLOTS}, got {slot}.")
    if len(axial_frames) != len(head_frames):
        raise NeonLightingError(
            "The axial and head tracks must have the same frame count "
            f"({len(axial_frames)} and {len(head_frames)})."
        )
    if not axial_frames:
        raise NeonLightingError("An effect must contain at least one frame.")
    if len(axial_frames) > MAX_FRAMES:
        raise NeonLightingError(
            f"An effect may hold at most {MAX_FRAMES} frames, got {len(axial_frames)}."
        )
    for index, frame in enumerate(axial_frames):
        if len(frame) != AXIAL_LED_COUNT:
            raise NeonLightingError(
                f"Axial frame {index} must hold {AXIAL_LED_COUNT} colours, "
                f"got {len(frame)}."
            )
    for index, frame in enumerate(head_frames):
        if len(frame) != HEAD_LED_COUNT:
            raise NeonLightingError(
                f"Head frame {index} must hold {HEAD_LED_COUNT} colours, "
                f"got {len(frame)}."
            )

    side_frames = [derive_side_frame(frame) for frame in head_frames]
    last = len(axial_frames) - 1

    def _channel_upload(zone: str, base: int, frames: Sequence[Sequence[str]]):
        channel = base + slot - 1
        built = tuple(
            tuple(
                build_frame_packets(
                    channel,
                    index,
                    frame,
                    lightness=lightness,
                    interval=interval,
                    is_final_frame=index == last,
                )
            )
            for index, frame in enumerate(frames)
        )
        return ChannelUpload(zone=zone, channel=channel, frames=built)

    return LightingPlan(
        slot=slot,
        uploads=(
            _channel_upload("axial", _AXIAL_BASE, axial_frames),
            _channel_upload("head", _HEAD_BASE, head_frames),
            _channel_upload("side", _SIDE_BASE, side_frames),
        ),
    )


def push(
    session: Any,
    plan: LightingPlan,
    *,
    deadline: float | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    progress_interval: float = 0.25,
) -> int:
    """Transmit a planned upload over an already-approved session.

    `session` must come from `hid_transport.open_approved`; this module never
    opens a device, so it cannot write to a keyboard that has not cleared the
    identity gate and a typed confirmation.

    The firmware echoes accepted vendor-lighting reports; it does not return a
    separate status byte. An unexpected echo raises immediately so the caller
    never reports a partial effect as complete.
    """

    total = plan.packet_count
    sent = 0
    last_report = 0.0

    for upload in plan.uploads:
        for frame_index, frame in enumerate(upload.frames):
            for packet_index, packet in enumerate(frame):
                if is_cancelled is not None and is_cancelled():
                    raise NeonLightingError("The lighting push was cancelled.")
                if deadline is not None and time.monotonic() > deadline:
                    raise NeonLightingError("The lighting push exceeded its deadline.")

                session.send(packet)
                reply = session.receive()
                if reply != _expected_reply(packet, packet_index):
                    raise NeonLightingRejected(
                        f"The keyboard returned an unexpected reply for the "
                        f"{upload.zone} zone at frame {frame_index}. The effect "
                        "on the device is incomplete."
                    )

                sent += 1
                now = time.monotonic()
                if on_progress is not None and now - last_report >= progress_interval:
                    last_report = now
                    on_progress(sent, total)

    if on_progress is not None:
        on_progress(sent, total)
    return sent
