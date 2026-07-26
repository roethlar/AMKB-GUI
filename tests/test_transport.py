from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from am_configurator import transport
from am_configurator.server import _probe_keyboard


ROOT = Path(__file__).resolve().parents[1]


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

    def test_the_driver_receives_the_configuration_and_plans_its_own_protocol(self) -> None:
        """The seam must sit below the encoding, not above it.

        A driver handed pre-encoded AM frames could not be implemented for a
        device that speaks another protocol, which is the whole reason the
        handle exists.
        """

        config = {"page_data": [], "product_info": {"product_id": "AM21"}}
        plan = SimpleNamespace(total=7, frames=(b"frame",))

        with (
            patch("am_configurator.writer.plan", return_value=plan) as planned,
            patch("am_configurator.writer.write_config", return_value=(True, b"")) as send,
            patch("am_configurator.writer.SETTLE_SECONDS", 0),
        ):
            receipt = self.link.write_config("/dev/example", config)

        planned.assert_called_once_with(config)
        send.assert_called_once_with("/dev/example", plan.frames)
        self.assertEqual(7, receipt.units)
        self.assertEqual("configuration frames", receipt.unit_label)

    def test_a_refused_write_raises_the_drivers_own_protocol_error(self) -> None:
        """`JSON_END` is a serial concept; the routes must never name it."""

        config = {"page_data": [], "product_info": {"product_id": "AM21"}}
        plan = SimpleNamespace(total=1, frames=(b"frame",))

        with (
            patch("am_configurator.writer.plan", return_value=plan),
            patch("am_configurator.writer.write_config", return_value=(False, b"\xde\xad")),
        ):
            with self.assertRaises(transport.DeviceWriteError) as raised:
                self.link.write_config("/dev/example", config)

        self.assertIn("JSON_END", str(raised.exception))
        self.assertIn("dead", str(raised.exception))

        server_source = (ROOT / "am_configurator/server.py").read_text(encoding="utf-8")
        self.assertNotIn("JSON_END", server_source)
        self.assertNotIn("from . import writer\n\n        handle", server_source)

    def test_describing_a_write_performs_no_io(self) -> None:
        """The verify route reports a unit count without resending anything."""

        config = {"page_data": [], "product_info": {"product_id": "AM21"}}

        with (
            patch("am_configurator.writer.plan", return_value=SimpleNamespace(total=4)),
            patch("am_configurator.writer.write_config") as send,
        ):
            receipt = self.link.describe_write(config)

        send.assert_not_called()
        self.assertEqual(4, receipt.units)
        self.assertEqual("configuration frames", receipt.unit_label)

    def test_discovery_pairs_every_device_with_its_own_handle(self) -> None:
        found = SimpleNamespace(port="/dev/one", is_keyboard=True)

        # Isolate the registry to the serial transport. Discovery now walks
        # every registered transport, so without this the test enumerates
        # whatever hardware happens to be plugged into the machine running it.
        only_serial = {transport.SERIAL: transport.transport_for(transport.SERIAL)}
        with (
            patch.dict(transport._TRANSPORTS, only_serial, clear=True),
            patch("am_configurator.device.list_devices", return_value=[found]),
        ):
            pairs = transport.discover()

        self.assertEqual([(self.handle.__class__(transport.SERIAL, "/dev/one"), found)], pairs)

    def test_probe_dispatches_through_the_handle(self) -> None:
        keyboard = SimpleNamespace(is_keyboard=True)
        with patch("am_configurator.device.probe", return_value=keyboard) as probe:
            self.assertIs(keyboard, _probe_keyboard(self.handle, attempts=1))
        probe.assert_called_once_with("/dev/example", full=True)


class NonSerialDriverTests(unittest.TestCase):
    """A driver sharing no encoding with serial must be implementable.

    This is the property or-1 found missing: while the seam passed AM 64-byte
    frames, a driver for any other protocol had nothing it could implement.
    """

    class RecordingDriver:
        kind = "recording"
        write_unit_label = "reports"

        def __init__(self) -> None:
            self.written: list[tuple[str, dict]] = []

        def list_devices(self, *, full: bool = False) -> list:
            return []

        def handle_for(self, info: object) -> transport.DeviceHandle:
            return transport.DeviceHandle(self.kind, "recorder")

        def probe(self, address: str, *, full: bool = False) -> object:
            return None

        def read_keymap(self, address: str, *, layers: int) -> list[list[str]]:
            return []

        def read_macros(self, address: str) -> list[dict]:
            return []

        def write_macros(self, address: str, entries: list[dict]) -> None:
            return None

        def describe_write(self, config: dict) -> transport.WriteReceipt:
            return transport.WriteReceipt(len(config["page_data"]), self.write_unit_label)

        def write_config(self, address: str, config: dict) -> transport.WriteReceipt:
            self.written.append((address, config))
            return transport.WriteReceipt(len(config["page_data"]), self.write_unit_label)

    def setUp(self) -> None:
        self.driver = self.RecordingDriver()
        self.original = dict(transport._TRANSPORTS)
        transport.register_transport(self.driver)
        self.addCleanup(self._restore_registry)

    def _restore_registry(self) -> None:
        transport._TRANSPORTS.clear()
        transport._TRANSPORTS.update(self.original)

    def test_a_write_arrives_as_the_configuration_not_as_encoded_frames(self) -> None:
        config = {"page_data": [{"page_index": 0}, {"page_index": 1}], "key_layer": {}}
        handle = transport.handle_from_payload(
            {"transport": "recording", "address": "usb-0001"}
        )
        link = transport.transport_for_handle(handle)

        receipt = link.write_config(handle.address, config)

        self.assertEqual([("usb-0001", config)], self.driver.written)
        self.assertIs(config, self.driver.written[0][1])
        self.assertEqual(2, receipt.units)
        self.assertEqual("reports", receipt.unit_label)

    def test_each_driver_reports_writes_in_its_own_unit(self) -> None:
        """The response payload must not assume every device writes frames."""

        serial_label = transport.transport_for(transport.SERIAL).write_unit_label
        self.assertNotEqual(serial_label, self.driver.write_unit_label)

        server_source = (ROOT / "am_configurator/server.py").read_text(encoding="utf-8")
        self.assertIn('"write_unit_label": receipt.unit_label', server_source)
        self.assertNotIn('"frames": frame_total', server_source)


if __name__ == "__main__":
    unittest.main()
