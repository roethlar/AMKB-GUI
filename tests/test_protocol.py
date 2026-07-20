from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from am_configurator import device, reader, store
from am_configurator.macros import macro_frames, parse_macro_frames
from am_configurator.protocol import build_frame, crc_ok, exclusive_serial_kwargs
from am_configurator.writer import car_light_data_frames, car_light_info_frames


class ProtocolTests(unittest.TestCase):
    def test_frame_crc_and_platform_serial_options(self) -> None:
        frame = build_frame(1, 2, b"hello")
        self.assertEqual(64, len(frame))
        self.assertTrue(crc_ok(frame))
        with patch("am_configurator.protocol.sys.platform", "win32"):
            self.assertEqual({}, exclusive_serial_kwargs())

    def test_cross_platform_usb_serial_discovery(self) -> None:
        def port(path: str, *, vid: int | None = None, hwid: str = "") -> SimpleNamespace:
            return SimpleNamespace(
                device=path,
                vid=vid,
                hwid=hwid,
                description="Angry Miao" if vid else "",
                manufacturer="",
                product="",
            )

        cases = (
            ("Darwin", [port("/dev/tty.usbmodem1", vid=1), port("/dev/cu.usbmodem1", vid=1)], ["/dev/cu.usbmodem1"]),
            ("Windows", [port("COM4", vid=1), port("COM1")], ["COM4"]),
            ("Linux", [port("/dev/ttyACM0"), port("/dev/ttyS0")], ["/dev/ttyACM0"]),
        )
        for system, ports, expected in cases:
            with self.subTest(system=system), patch(
                "am_configurator.device.platform.system", return_value=system
            ), patch("am_configurator.device.list_ports.comports", return_value=ports):
                self.assertEqual(expected, device.candidate_ports())

    def test_partial_spotlight_manifest_keeps_custom_slot_positions(self) -> None:
        pages = [{"page_index": index} for index in range(8)]
        pages[7]["spotlight_frames"] = {
            "valid": 1,
            "frame_num": 3,
            "frame_data": [],
        }
        manifest = car_light_info_frames(pages)[0]
        self.assertEqual(bytes([0, 0, 1, 0, 0, 0, 0, 0, 3]), manifest[2:11])

    def test_spotlight_data_rejects_non_custom_pages(self) -> None:
        pages = [{"page_index": 3, "spotlight_frames": {
            "valid": 1,
            "frame_num": 1,
            "frame_data": [{"frame_index": 0, "frame_RGB": ["#010203"] * 24}],
        }}]
        with self.assertRaisesRegex(ValueError, "pages 5, 6, and 7"):
            car_light_data_frames(pages)

    def test_partial_keymap_frame_is_reported_as_protocol_error(self) -> None:
        with patch("am_configurator.reader._drain", return_value=[b"\x06"]):
            with self.assertRaisesRegex(ValueError, "bad CRC"):
                reader.read_keymap("unused")

    def test_macro_frames_round_trip(self) -> None:
        macros = [{
            "original_key": "#00951500",
            "layer_key": ["#11070004", "#10070004"],
            "intvel_ms": [25, 0],
        }]
        sent = macro_frames(macros)
        replies = [build_frame(6, 10, frame[2:63]) for frame in sent]
        self.assertEqual(macros, parse_macro_frames(replies))

    def test_store_uses_app_owned_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"AM_CONFIGURATOR_DATA_DIR": directory},
            clear=False,
        ):
            self.assertEqual(Path(directory), store.store_root())


if __name__ == "__main__":
    unittest.main()
