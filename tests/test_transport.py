from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from am_configurator import transport
from am_configurator.server import _probe_keyboard


class HandleParsingTests(unittest.TestCase):
    def test_an_unknown_transport_is_rejected_rather_than_driven_as_serial(self) -> None:
        """The one thing dispatch must never do is guess the link type.

        Treating an unrecognised kind as serial would open a CDC port and speak
        the AM frame protocol at a device that does not answer it.
        """

        with self.assertRaises(transport.UnsupportedTransportError) as raised:
            transport.handle_from_payload({"transport": "rawhid", "address": "0001"})
        self.assertIn("rawhid", str(raised.exception))
        self.assertIn(transport.SERIAL, str(raised.exception))

        with self.assertRaises(transport.UnsupportedTransportError):
            transport.transport_for("rawhid")
        with self.assertRaises(transport.UnsupportedTransportError):
            transport.transport_for_handle(transport.DeviceHandle("rawhid", "0001"))

    def test_a_payload_without_a_transport_stays_serial(self) -> None:
        """Every request body written before handles existed carries just a port."""

        legacy = transport.handle_from_payload({"port": "/dev/example"})
        self.assertEqual(transport.DeviceHandle(transport.SERIAL, "/dev/example"), legacy)

        explicit = transport.handle_from_payload(
            {"transport": transport.SERIAL, "address": "/dev/example"}
        )
        self.assertEqual(legacy, explicit)
        self.assertEqual(
            {"transport": "serial", "address": "/dev/example"}, explicit.as_json()
        )

    def test_a_handle_without_an_address_is_refused(self) -> None:
        for body in ({}, {"port": ""}, {"transport": transport.SERIAL}, {"address": "  "}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                transport.handle_from_payload(body)

    def test_unsupported_transport_reads_as_a_bad_request(self) -> None:
        """The device routes map ValueError to 400; the caller named a bad link."""

        self.assertTrue(issubclass(transport.UnsupportedTransportError, ValueError))


class SerialDispatchTests(unittest.TestCase):
    """Serial dispatch must land on exactly the calls the routes used to make."""

    def setUp(self) -> None:
        self.handle = transport.DeviceHandle(transport.SERIAL, "/dev/example")
        self.link = transport.transport_for(transport.SERIAL)

    def test_operations_delegate_to_the_modules_that_owned_them(self) -> None:
        with patch("am_configurator.reader.read_keymap", return_value=[["#00"]]) as keymap:
            self.assertEqual([["#00"]], self.link.read_keymap("/dev/example", layers=3))
        keymap.assert_called_once_with("/dev/example", layers=3)

        with patch("am_configurator.macros.read_macros", return_value=[]) as read:
            self.assertEqual([], self.link.read_macros("/dev/example"))
        read.assert_called_once_with("/dev/example")

        with patch("am_configurator.macros.write_macros", return_value=()) as write:
            self.link.write_macros("/dev/example", [{"original_key": "#11000000"}])
        write.assert_called_once_with("/dev/example", [{"original_key": "#11000000"}])

        with patch("am_configurator.writer.write_config", return_value=(True, b"")) as send:
            self.assertEqual((True, b""), self.link.write_config("/dev/example", (b"f",)))
        send.assert_called_once_with("/dev/example", (b"f",))

    def test_discovery_pairs_every_device_with_its_own_handle(self) -> None:
        found = SimpleNamespace(port="/dev/one", is_keyboard=True)
        with patch("am_configurator.device.list_devices", return_value=[found]):
            pairs = transport.discover()

        self.assertEqual([(self.handle.__class__(transport.SERIAL, "/dev/one"), found)], pairs)

    def test_probe_dispatches_through_the_handle(self) -> None:
        keyboard = SimpleNamespace(is_keyboard=True)
        with patch("am_configurator.device.probe", return_value=keyboard) as probe:
            self.assertIs(keyboard, _probe_keyboard(self.handle, attempts=1))
        probe.assert_called_once_with("/dev/example", full=True)


if __name__ == "__main__":
    unittest.main()
