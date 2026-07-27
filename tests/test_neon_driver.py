from __future__ import annotations

import unittest
from unittest.mock import patch

from am_configurator import (
    neon_driver,
    neon_lighting,
    transport,
    vial_keymap,
    vial_macros,
)


def _neon_config(frames: int = 2, *, keymap: bool = True, macros: int = 1, slots: int = 3) -> dict:
    config: dict = {
        "product_info": {"product_id": "NEON80"},
        "page_data": [
            {
                "page_index": page,
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
            for page in range(5, 5 + slots)
        ],
        "macro_key": [
            {
                "original_key": "#11070004",
                "layer_key": ["#11070004", "#10070004"],
                "intvel_ms": [25, 0],
            }
            for _ in range(macros)
        ],
    }
    if keymap:
        config["key_layer"] = {
            "layer_num": 4,
            "layer_data": [
                {"layer": [f"#0007{(4 + n) % 0x100:04X}" for n in range(90)]}
                for _ in range(4)
            ],
        }
    return config


class Session:
    """A recorded Neon. Answers the reads the preflight makes."""

    def __init__(
        self,
        *,
        unlocked: bool = True,
        unlock_after_polls: int | None = None,
        macro_count: int = 16,
        macro_bytes: int = 6677,
    ):
        self.unlocked = unlocked
        self.unlock_after_polls = unlock_after_polls
        self.unlock_in_progress = False
        self.unlock_polls = 0
        self.capacity = vial_macros.MacroCapacity(macro_count, macro_bytes)
        self.sent: list[bytes] = []
        self.closed = False
        self._reply = b""

    def send(self, packet: bytes) -> None:
        self.sent.append(bytes(packet))
        reply = bytearray(32)
        if packet[0] == vial_macros.VIA_MACRO_GET_COUNT:
            reply[1] = self.capacity.count
        elif packet[0] == vial_macros.VIA_MACRO_GET_BUFFER_SIZE:
            reply[1:3] = self.capacity.buffer_bytes.to_bytes(2, "big")
        elif packet[0] == 0xFE:
            command = packet[1]
            if command == vial_keymap.VIAL_GET_UNLOCK_STATUS:
                reply[:] = b"\xFF" * len(reply)
                reply[0] = 1 if self.unlocked else 0
                reply[1] = 1 if self.unlock_in_progress else 0
                reply[2:6] = bytes((0, 0, 0, 2))
            elif command == vial_keymap.VIAL_UNLOCK_START:
                self.unlock_in_progress = True
                self.unlock_polls = 0
            elif command == vial_keymap.VIAL_UNLOCK_POLL:
                if self.unlock_in_progress:
                    self.unlock_polls += 1
                    if (
                        self.unlock_after_polls is not None
                        and self.unlock_polls >= self.unlock_after_polls
                    ):
                        self.unlocked = True
                        self.unlock_in_progress = False
                reply[0] = 1 if self.unlocked else 0
                reply[1] = 1 if self.unlock_in_progress else 0
                reply[2] = max(0, 50 - self.unlock_polls)
        elif packet[0] == neon_lighting.LIGHTING_COMMAND:
            reply[:] = packet
            if reply[3] == 0xFF:
                same_frame = [
                    sent
                    for sent in self.sent
                    if sent[0] == neon_lighting.LIGHTING_COMMAND
                    and sent[1] == reply[1]
                    and sent[2] == reply[2]
                ]
                reply[3] = len(same_frame) - 1
                reply[31] = sum(reply[:31]) & 0xFF
        elif packet[0] == vial_keymap.VIA_GET_LAYER_COUNT:
            reply[1] = 4
        self._reply = bytes(reply)

    def receive(self, timeout_ms: int = 0) -> bytes:
        return self._reply

    def close(self) -> None:
        self.closed = True

    @property
    def lighting_packets(self) -> list[bytes]:
        return [p for p in self.sent if p and p[0] == neon_lighting.LIGHTING_COMMAND]

    @property
    def keymap_writes(self) -> list[bytes]:
        return [p for p in self.sent if p and p[0] == vial_keymap.VIA_SET_BUFFER]

    @property
    def macro_writes(self) -> list[bytes]:
        return [p for p in self.sent if p and p[0] == vial_macros.VIA_MACRO_SET_BUFFER]

    @property
    def unlock_starts(self) -> list[bytes]:
        return [
            packet
            for packet in self.sent
            if packet[:2] == bytes((0xFE, vial_keymap.VIAL_UNLOCK_START))
        ]


class RegistrationTests(unittest.TestCase):
    def test_the_neon_driver_is_registered_under_the_hid_transport(self) -> None:
        self.assertIn(neon_driver.NEON_TRANSPORT, transport.transport_kinds())
        self.assertIsInstance(
            transport.transport_for(neon_driver.NEON_TRANSPORT),
            neon_driver.NeonTransport,
        )

    def test_it_satisfies_the_driver_interface(self) -> None:
        driver = transport.transport_for(neon_driver.NEON_TRANSPORT)
        for operation in (
            "list_devices",
            "handle_for",
            "probe",
            "read_keymap",
            "read_macros",
            "read_macro_state",
            "write_macros",
            "describe_write",
            "write_config",
        ):
            with self.subTest(operation=operation):
                self.assertTrue(callable(getattr(driver, operation, None)))


class PreflightTests(unittest.TestCase):
    """Lighting, keymap, and macros are three writes, not one transaction.

    Nothing can make them atomic. What stands in for atomicity is finding every
    detectable failure before the first byte, so a write that starts is very
    unlikely to stop halfway and leave the keyboard mixed.
    """

    def setUp(self) -> None:
        self.driver = neon_driver.NeonTransport()

    def _write(self, config, session):
        with (
            patch.object(neon_driver.hid_transport, "find"),
            patch.object(neon_driver.hid_transport, "approve_write"),
            patch.object(neon_driver.hid_transport, "open_approved", return_value=session),
            patch.object(vial_keymap.time, "sleep"),
        ):
            return self.driver.write_config("hid:00", config)

    def test_a_valid_configuration_transmits_everything_it_holds(self) -> None:
        """Lighting, keymap, and macros. The keymap used to be silently skipped."""

        session = Session()
        receipt = self._write(_neon_config(), session)

        self.assertGreater(receipt.units, 0)
        self.assertEqual(receipt.units, len(session.lighting_packets))
        self.assertTrue(session.keymap_writes, "the keymap was never transmitted")
        self.assertTrue(session.macro_writes, "the macros were never transmitted")
        self.assertTrue(session.closed)

    def test_every_custom_lighting_slot_is_written(self) -> None:
        """Three user slots, nine channels. Writing only slot 1 left two stale."""

        session = Session()
        self._write(_neon_config(slots=3), session)

        channels = {p[1] for p in session.lighting_packets}
        self.assertEqual(
            {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09},
            channels,
            "not every slot's axial, head, and side channel was written",
        )

    def test_a_configuration_with_one_slot_writes_only_that_slot(self) -> None:
        session = Session()
        self._write(_neon_config(slots=1), session)

        self.assertEqual(
            {0x01, 0x04, 0x07}, {p[1] for p in session.lighting_packets}
        )

    def test_a_slot_writes_independent_axial_and_head_frame_counts(self) -> None:
        config = _neon_config(frames=1, slots=1)
        config["page_data"][0]["axial"]["frame_data"].append(
            {"frame_RGB": ["#070809"] * neon_lighting.AXIAL_LED_COUNT}
        )
        session = Session()

        self._write(config, session)

        frames_by_channel = {
            channel: {
                packet[2]
                for packet in session.lighting_packets
                if packet[1] == channel
            }
            for channel in (0x01, 0x04, 0x07)
        }
        self.assertEqual({0, 1}, frames_by_channel[0x01])
        self.assertEqual({0}, frames_by_channel[0x04])
        self.assertEqual({0}, frames_by_channel[0x07])

    def test_the_transmitted_keymap_is_the_one_that_was_validated(self) -> None:
        session = Session()
        config = _neon_config()
        self._write(config, session)

        expected = vial_keymap.encode_layers(
            [entry["layer"] for entry in config["key_layer"]["layer_data"]]
        )
        rebuilt = b"".join(p[4 : 4 + p[3]] for p in session.keymap_writes)
        self.assertEqual(expected, rebuilt)

    def test_a_locked_keyboard_stops_the_write_before_any_lighting(self) -> None:
        session = Session(unlocked=False)

        with self.assertRaises(vial_keymap.KeyboardLocked) as raised:
            self._write(_neon_config(), session)

        self.assertIn("Esc and F2", str(raised.exception))
        self.assertIn("Nothing was written", str(raised.exception))
        self.assertEqual([], session.lighting_packets)
        self.assertEqual([], session.keymap_writes)
        self.assertEqual([], session.macro_writes)
        self.assertEqual(1, len(session.unlock_starts))
        self.assertTrue(session.closed, "the session leaked on failure")

    def test_a_locked_keyboard_is_unlocked_before_the_first_configuration_set(self) -> None:
        session = Session(unlocked=False, unlock_after_polls=2)

        self._write(_neon_config(), session)

        unlock_polls = [
            index
            for index, packet in enumerate(session.sent)
            if packet[:2] == bytes((0xFE, vial_keymap.VIAL_UNLOCK_POLL))
        ]
        first_set = min(
            index
            for index, packet in enumerate(session.sent)
            if packet[0]
            in {
                neon_lighting.LIGHTING_COMMAND,
                vial_keymap.VIA_SET_BUFFER,
                vial_macros.VIA_MACRO_SET_BUFFER,
            }
        )
        self.assertEqual(2, len(unlock_polls))
        self.assertLess(unlock_polls[-1], first_set)
        self.assertTrue(session.unlocked)

    def test_an_unsupported_keycode_stops_the_write_before_any_lighting(self) -> None:
        config = _neon_config()
        config["key_layer"]["layer_data"][2]["layer"][7] = "#000C00E9"
        session = Session()

        with self.assertRaises(vial_keymap.UnsupportedKeycode) as raised:
            self._write(config, session)

        self.assertIn("layer 2 key 7", str(raised.exception))
        self.assertEqual([], session.lighting_packets)
        self.assertEqual([], session.unlock_starts)

    def test_too_many_macros_stop_the_write_before_any_lighting(self) -> None:
        session = Session(macro_count=16)

        with self.assertRaises(vial_macros.MacroCapacityError):
            self._write(_neon_config(macros=17), session)

        self.assertEqual([], session.lighting_packets)
        self.assertEqual([], session.unlock_starts)

    def test_macros_that_overflow_the_byte_budget_stop_the_write(self) -> None:
        session = Session(macro_count=16, macro_bytes=20)

        with self.assertRaises(vial_macros.MacroCapacityError) as raised:
            self._write(_neon_config(macros=4), session)

        self.assertIn("Nothing was sent", str(raised.exception))
        self.assertEqual([], session.lighting_packets)
        self.assertEqual([], session.unlock_starts)

    def test_the_preflight_runs_before_the_first_lighting_packet(self) -> None:
        """Ordering is the property, not merely that the checks exist."""

        session = Session(unlocked=False)
        with self.assertRaises(vial_keymap.KeyboardLocked):
            self._write(_neon_config(), session)

        # It did talk to the device — capacity reads and the volatile Vial
        # unlock handshake — but transmitted no lighting, keymap, or macro SET.
        self.assertTrue(session.sent, "the preflight made no device reads")
        self.assertEqual([], session.lighting_packets)


class LayerCountTests(unittest.TestCase):
    def test_reading_the_keymap_ignores_the_routes_seven_layer_default(self) -> None:
        """The serial families have seven layers; this keyboard has four."""

        driver = neon_driver.NeonTransport()
        session = Session()
        captured: dict = {}

        def _read(sess, *, keys_per_layer):
            captured["keys_per_layer"] = keys_per_layer
            return [[]]

        with (
            patch.object(neon_driver, "_", create=True),
            patch.object(neon_driver.hid_transport, "find"),
            patch.object(neon_driver.hid_transport, "approve_write"),
            patch.object(neon_driver.hid_transport, "open_approved", return_value=session),
            patch.object(neon_driver.vial_keymap, "read_keymap", _read),
        ):
            driver.read_keymap("hid:00", layers=7)

        self.assertEqual(neon_driver.NEON_KEYS_PER_LAYER, captured["keys_per_layer"])

    def test_reading_macros_keeps_the_device_reported_capacity(self) -> None:
        driver = neon_driver.NeonTransport()
        session = Session(macro_count=9, macro_bytes=321)
        slots = [
            {
                "original_key": "#00951500",
                "layer_key": ["#11070004"],
                "intvel_ms": [0],
            },
            {
                "original_key": "#00951501",
                "layer_key": [],
                "intvel_ms": [],
            },
            {
                "original_key": "#00951502",
                "layer_key": ["#11070005"],
                "intvel_ms": [0],
            },
        ]

        with (
            patch.object(neon_driver.hid_transport, "find"),
            patch.object(neon_driver.hid_transport, "approve_write"),
            patch.object(
                neon_driver.hid_transport,
                "open_approved",
                return_value=session,
            ),
            patch.object(
                neon_driver.vial_macros,
                "read_macros",
                return_value=slots,
            ) as read,
        ):
            result = driver.read_macro_state("hid:00")

        self.assertEqual([slots[0], slots[2]], result.macros)
        self.assertTrue(result.device_reported)
        self.assertEqual(9, result.device_macro_count)
        self.assertEqual(321, result.device_macro_buffer_bytes)
        read.assert_called_once_with(session, capacity=session.capacity)
        self.assertTrue(session.closed)


class PlanExtractionTests(unittest.TestCase):
    def test_a_slot_with_no_page_is_refused(self) -> None:
        with self.assertRaises(neon_lighting.NeonLightingError):
            neon_driver.NeonTransport()._plan({"page_data": []})

    def test_the_plan_uses_the_pages_brightness_and_interval(self) -> None:
        config = _neon_config()
        config["page_data"][0]["lightness"] = 42
        config["page_data"][0]["speed_ms"] = 7

        plan = neon_driver.NeonTransport()._plan(config)
        first = plan.uploads[0].frames[0][0]
        self.assertEqual(42, first[4])
        self.assertEqual(7, first[5])


if __name__ == "__main__":
    unittest.main()
