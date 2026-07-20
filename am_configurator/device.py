"""Discover supported Angry Miao keyboards over USB CDC serial.

READ-ONLY: sends only identity/status queries ([1,1] product_id, [1,2]
product_info, [2,6] check_pages) and never modifies keyboard config. This is
the robust answer to AM Master's flaky detection: instead of trusting a
device-node name or a hardcoded VID/PID, open each candidate serial port and
ask it who it is — only a device that returns a CRC-valid keyboard reply
counts (a co-resident LG monitor exposes its own cu.usbmodem* port, hence the
need to verify by reply, not by name).

"""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass

import serial  # pyserial
from serial.tools import list_ports

from .protocol import build_frame, crc_ok, exclusive_serial_kwargs, parse_string_reply

BAUD = 9600
CMD_PRODUCT_ID = (1, 1)
CMD_PRODUCT_INFO = (1, 2)
CMD_CHECK_PAGES = (2, 6)


@dataclass(frozen=True)
class DeviceInfo:
    port: str
    product_id: str | None
    version: str | None
    pages: int | None
    is_cyberboard: bool
    is_dongle: bool
    is_keyboard: bool


def candidate_ports() -> list[str]:
    """USB serial ports that could be an Angry Miao keyboard on this OS."""
    system = platform.system()
    candidates: set[str] = set()
    for info in list_ports.comports():
        device = str(info.device)
        hwid = str(info.hwid or "").upper()
        description = " ".join(
            str(value or "")
            for value in (info.description, info.manufacturer, info.product)
        ).upper()
        usb = info.vid is not None or "USB" in hwid or "ANGRY" in description
        if system == "Darwin":
            if device.startswith("/dev/cu.usbmodem"):
                candidates.add(device)
        elif system == "Windows":
            if usb and device.upper().startswith("COM"):
                candidates.add(device)
        elif usb or device.startswith(("/dev/ttyACM", "/dev/ttyUSB")):
            candidates.add(device)
    return sorted(candidates)


def _query(ser: serial.Serial, command: tuple[int, int]) -> bytes:
    ser.reset_input_buffer()
    time.sleep(0.005)  # mirror AM Master's inter-frame delay
    ser.write(build_frame(*command))
    ser.flush()
    return ser.read(64)


def probe(port: str, *, full: bool = False, timeout: float = 1.5) -> DeviceInfo | None:
    """Identify the device on `port`. Return ``None`` when it is unsupported.

    `full=True` additionally fetches firmware version and page count.
    """
    try:
        ser = serial.Serial(
            port, baudrate=BAUD, timeout=timeout, write_timeout=timeout,
            **exclusive_serial_kwargs(),
        )
    except (serial.SerialException, OSError):
        return None
    try:
        time.sleep(0.1)
        reply = _query(ser, CMD_PRODUCT_ID)
        if not crc_ok(reply):
            return None
        product_id = parse_string_reply(reply)
        if product_id is None:
            return None
        upper = product_id.upper()
        is_dongle = "DONGLE" in upper
        is_cyberboard = upper.startswith("CB") and not is_dongle
        # Newer boards keep the same serial framing but use model IDs instead
        # of the CBxx family name.  AM21 = Relic 80; ALICE = AFA.
        is_keyboard = is_cyberboard or upper in {"AM21", "ALICE"}
        version: str | None = None
        pages: int | None = None
        if full and is_keyboard:
            info = _query(ser, CMD_PRODUCT_INFO)
            version = parse_string_reply(info) if crc_ok(info) else None
            checked = _query(ser, CMD_CHECK_PAGES)
            pages = checked[2] if crc_ok(checked) else None
        return DeviceInfo(
            port, product_id, version, pages, is_cyberboard, is_dongle, is_keyboard
        )
    finally:
        ser.close()


def list_devices(*, full: bool = False) -> list[DeviceInfo]:
    return [info for port in candidate_ports() if (info := probe(port, full=full)) is not None]
