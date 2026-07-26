from __future__ import annotations

import unittest
from unittest.mock import patch

from am_configurator import neon_driver, neon_lighting, transport


def _neon_config(frames: int = 2) -> dict:
    return {
        "product_info": {"product_id": "NEON80"},
        "page_data": [
            {
                "page_index": 5,
                "lightness": 100,
                "speed_ms": 90,
                "axial": {
                    "frame_data": [
                        {"frame_RGB": ["#010203"] * neon_lighting.AXIAL_LED_COUNT}
                        for _ in range(frames)
                    ]
                },
                "head": {
                    "frame_data": [
                        {"frame_RGB": ["#040506"] * neon_lighting.HEAD_LED_COUNT}
                        for _ in range(frames)
                    ]
                },
            }
        ],
    }


class RegistrationTests(unittest.TestCase):
    def test_the_neon_driver_is_registered_under_the_hid_transport(self) -> None:
        self.assertIn(neon_driver.NEON_TRANSPORT, transport.transport_kinds())
        driver = transport.transport_for(neon_driver.NEON_TRANSPORT)
        self.assertIsInstance(driver, neon_driver.NeonTransport)

    def test_it_satisfies_the_driver_interface(self) -> None:
        driver = transport.transport_for(neon_driver.NEON_TRANSPORT)
        for operation in (
            "list_devices",
            "handle_for",
            "probe",
            "read_keymap",
            "read_macros",
            "write_macros",
            "describe_write",
            "write_config",
        ):
            with self.subTest(operation=operation):
                self.assertTrue(callable(getattr(driver, operation, None)))


class PartialWriteRefusalTests(unittest.TestCase):
    """A write must be refused entirely, not attempted and abandoned.

    The route's write path pushes a configuration, installs macros, then reads
    the keymap back. Two of those three do not exist yet. Pushing lighting and
    then failing on macros would leave the keyboard holding half a write while
    the user is told it failed, which is the worst available outcome.
    """

    def setUp(self) -> None:
        self.driver = neon_driver.NeonTransport()

    def test_a_write_is_refused_before_any_device_is_touched(self) -> None:
        with (
            patch.object(neon_driver.hid_transport, "find") as find,
            patch.object(neon_driver.hid_transport, "open_approved") as opened,
            patch.object(neon_driver.neon_lighting, "push") as pushed,
        ):
            with self.assertRaises(neon_driver.NeonUnsupportedOperation) as raised:
                self.driver.write_config("hid:00", _neon_config())

        self.assertIn("Nothing was sent", str(raised.exception))
        find.assert_not_called()
        opened.assert_not_called()
        pushed.assert_not_called()

    def test_describing_a_write_is_refused_too(self) -> None:
        with self.assertRaises(neon_driver.NeonUnsupportedOperation):
            self.driver.describe_write(_neon_config())

    def test_the_unimplemented_operations_name_themselves(self) -> None:
        for call in (
            lambda: self.driver.read_keymap("hid:00", layers=4),
            lambda: self.driver.read_macros("hid:00"),
            lambda: self.driver.write_macros("hid:00", []),
        ):
            with self.subTest():
                with self.assertRaises(neon_driver.NeonUnsupportedOperation):
                    call()

    def test_the_refusal_is_one_flag_and_the_lighting_path_is_real(self) -> None:
        """Once N6 and N7 land, flipping the flag must reach a working push."""

        sent: list[bytes] = []

        class Session:
            def send(self, packet: bytes) -> None:
                sent.append(packet)

            def receive(self, timeout_ms: int = 0) -> bytes:
                reply = bytearray(32)
                reply[7] = neon_lighting.REPLY_OK
                return bytes(reply)

            def close(self) -> None:
                pass

        info = type(
            "Info", (), {"model": "NEON80", "writable": True, "address": "hid:00"}
        )()

        with (
            patch.object(neon_driver, "supports_full_write", True),
            patch.object(neon_driver.hid_transport, "find", return_value=info),
            patch.object(neon_driver.hid_transport, "approve_write", return_value=object()),
            patch.object(neon_driver.hid_transport, "open_approved", return_value=Session()),
        ):
            receipt = self.driver.write_config("hid:00", _neon_config())

        self.assertGreater(receipt.units, 0)
        self.assertEqual("lighting packets", receipt.unit_label)
        self.assertEqual(receipt.units, len(sent))
        # Three channels were transmitted, not just the two authored tracks.
        self.assertEqual({0x01, 0x04, 0x07}, {packet[1] for packet in sent})


class PlanExtractionTests(unittest.TestCase):
    def test_a_slot_with_no_page_is_refused(self) -> None:
        driver = neon_driver.NeonTransport()
        with self.assertRaises(neon_lighting.NeonLightingError):
            driver._plan({"page_data": []})

    def test_the_plan_uses_the_pages_brightness_and_interval(self) -> None:
        driver = neon_driver.NeonTransport()
        config = _neon_config()
        config["page_data"][0]["lightness"] = 42
        config["page_data"][0]["speed_ms"] = 7

        plan = driver._plan(config)
        first = plan.uploads[0].frames[0][0]
        self.assertEqual(42, first[4])
        self.assertEqual(7, first[5])


if __name__ == "__main__":
    unittest.main()
