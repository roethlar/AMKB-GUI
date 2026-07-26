from __future__ import annotations

import unittest

from am_configurator import vial_macros as vm


def _macro(events: int, *, delay: int = 0) -> dict:
    return {
        "original_key": "#11070004",
        "layer_key": ["#11070004", "#10070004"] * events,
        "intvel_ms": [delay, delay] * events,
    }


class Session:
    """A recorded device. Never touches hardware."""

    def __init__(self, *, count: int = 16, buffer_bytes: int = 6677) -> None:
        self.capacity = vm.MacroCapacity(count=count, buffer_bytes=buffer_bytes)
        self.buffer = bytearray(buffer_bytes)
        self.sent: list[bytes] = []
        self._reply = b""

    def send(self, packet: bytes) -> None:
        self.sent.append(bytes(packet))
        reply = bytearray(32)
        if packet[0] == vm.VIA_MACRO_GET_COUNT:
            reply[1] = self.capacity.count
        elif packet[0] == vm.VIA_MACRO_GET_BUFFER_SIZE:
            reply[1:3] = self.capacity.buffer_bytes.to_bytes(2, "big")
        elif packet[0] == vm.VIA_MACRO_GET_BUFFER:
            offset = (packet[1] << 8) | packet[2]
            size = packet[3]
            reply[4 : 4 + size] = self.buffer[offset : offset + size]
        elif packet[0] == vm.VIA_MACRO_SET_BUFFER:
            offset = (packet[1] << 8) | packet[2]
            size = packet[3]
            self.buffer[offset : offset + size] = packet[4 : 4 + size]
        self._reply = bytes(reply)

    def receive(self, timeout_ms: int = 0) -> bytes:
        return self._reply

    @property
    def writes(self) -> list[bytes]:
        return [p for p in self.sent if p[0] == vm.VIA_MACRO_SET_BUFFER]


class CapacityBoundaryTests(unittest.TestCase):
    """Exact-count, exact-byte, and one-over. A single round-trip proves nothing.

    A Vial macro write replaces the entire buffer, so an overflow discovered
    partway through destroys macros the user already had. Every boundary is
    checked against zero packets sent.
    """

    def test_exactly_the_supported_macro_count_is_accepted(self) -> None:
        session = Session(count=16)
        macros = [_macro(1) for _ in range(16)]

        written = vm.write_macros(session, macros, capacity=session.capacity)

        self.assertGreater(written, 0)
        self.assertTrue(session.writes)

    def test_one_macro_over_the_count_sends_nothing(self) -> None:
        session = Session(count=16)
        macros = [_macro(1) for _ in range(17)]

        with self.assertRaises(vm.MacroCapacityError) as raised:
            vm.write_macros(session, macros, capacity=session.capacity)

        self.assertIn("stores 16 macros", str(raised.exception))
        self.assertIn("Nothing was sent", str(raised.exception))
        self.assertEqual([], session.writes, "packets were sent past the limit")

    def test_a_buffer_filled_to_the_exact_byte_is_accepted(self) -> None:
        # Size a single macro, then set the budget to exactly what the whole
        # compiled buffer needs.
        one = _macro(3)
        probe = vm.MacroCapacity(count=4, buffer_bytes=10_000)
        exact = len(vm.encode_macros([one] * 4, capacity=probe))

        session = Session(count=4, buffer_bytes=exact)
        written = vm.write_macros(session, [one] * 4, capacity=session.capacity)

        self.assertEqual(exact, written)

    def test_one_byte_over_the_budget_sends_nothing(self) -> None:
        one = _macro(3)
        probe = vm.MacroCapacity(count=4, buffer_bytes=10_000)
        exact = len(vm.encode_macros([one] * 4, capacity=probe))

        session = Session(count=4, buffer_bytes=exact - 1)
        with self.assertRaises(vm.MacroCapacityError) as raised:
            vm.write_macros(session, [one] * 4, capacity=session.capacity)

        self.assertIn("Nothing was sent", str(raised.exception))
        self.assertEqual([], session.writes, "packets were sent past the budget")

    def test_capacity_comes_from_the_device_not_a_default(self) -> None:
        session = Session(count=7, buffer_bytes=1234)
        capacity = vm.read_capacity(session)

        self.assertEqual(7, capacity.count)
        self.assertEqual(1234, capacity.buffer_bytes)
        # Not the serial families' 32 and 200.
        self.assertNotEqual(32, capacity.count)


class EncodingTests(unittest.TestCase):
    def test_press_release_and_tap_encode_distinctly(self) -> None:
        self.assertEqual(
            bytes([vm.SS_PREFIX, vm.SS_DOWN, 0x04]), vm._event_bytes("#11070004")
        )
        self.assertEqual(
            bytes([vm.SS_PREFIX, vm.SS_UP, 0x04]), vm._event_bytes("#10070004")
        )
        self.assertEqual(
            bytes([vm.SS_PREFIX, vm.SS_TAP, 0x04]), vm._event_bytes("#00070004")
        )

    def test_a_delay_never_encodes_a_null(self) -> None:
        """A null byte inside a delay would terminate the macro early."""

        for milliseconds in (0, 1, 254, 255, 256, 5000, vm.MAX_DELAY_MS):
            with self.subTest(ms=milliseconds):
                encoded = vm._encode_delay(milliseconds)
                self.assertNotIn(0x00, encoded[2:])
                self.assertEqual(
                    milliseconds, vm._decode_delay(encoded[2], encoded[3])
                )

    def test_an_impossible_delay_is_refused(self) -> None:
        with self.assertRaises(vm.MacroEncodingError):
            vm._encode_delay(vm.MAX_DELAY_MS + 1)

    def test_the_unsupported_code_policy_applies_to_macro_events(self) -> None:
        for code in ("#110C00E9", "#11070100"):
            with self.subTest(code=code):
                with self.assertRaises(vm.MacroEncodingError):
                    vm._event_bytes(code)

    def test_unused_macro_slots_are_still_terminated(self) -> None:
        """Without the terminator the device reads into the next macro."""

        capacity = vm.MacroCapacity(count=4, buffer_bytes=10_000)
        buffer = vm.encode_macros([_macro(1)], capacity=capacity)

        self.assertEqual(4, buffer.count(vm.MACRO_TERMINATOR))


class RoundTripTests(unittest.TestCase):
    def test_several_macros_survive_a_write_then_read(self) -> None:
        session = Session(count=4, buffer_bytes=2048)
        macros = [
            {
                "original_key": "#11070004",
                "layer_key": ["#11070004", "#10070004"],
                "intvel_ms": [25, 0],
            },
            {
                "original_key": "#11070005",
                "layer_key": ["#11070005", "#10070005", "#11070006"],
                "intvel_ms": [300, 0, 0],
            },
        ]

        vm.write_macros(session, macros, capacity=session.capacity)
        recovered = vm.read_macros(session, capacity=session.capacity)

        self.assertEqual(4, len(recovered))
        for index, original in enumerate(macros):
            with self.subTest(macro=index):
                self.assertEqual(original["layer_key"], recovered[index]["layer_key"])
                self.assertEqual(original["intvel_ms"], recovered[index]["intvel_ms"])
        # The unused slots come back empty rather than as garbage.
        self.assertEqual([], recovered[2]["layer_key"])
        self.assertEqual([], recovered[3]["layer_key"])


class SlotIdentityTests(unittest.TestCase):
    """The buffer is positional: slot N is triggered by the #009515NN token.

    Finding n567-6. Encoding by list order meant a profile whose macros were
    gapped or reordered executed under the wrong keys, and the bytes were
    written correctly the whole time — nothing would have flagged it.
    """

    def _tokened(self, slot: int, usage: int) -> dict:
        return {
            "original_key": f"#009515{slot:02X}",
            "layer_key": [f"#1107{usage:04X}", f"#1007{usage:04X}"],
            "intvel_ms": [0, 0],
        }

    def test_a_gapped_profile_lands_in_the_slots_its_tokens_name(self) -> None:
        capacity = vm.MacroCapacity(count=4, buffer_bytes=2048)
        # Slots 0 and 3 only. By list order the second would land in slot 1.
        macros = [self._tokened(0, 0x04), self._tokened(3, 0x05)]

        table = vm.slot_table(macros, capacity=capacity)
        self.assertIsNotNone(table[0])
        self.assertIsNone(table[1])
        self.assertIsNone(table[2])
        self.assertIsNotNone(table[3])
        self.assertEqual("#00951503", table[3]["original_key"])

    def test_a_reordered_profile_still_lands_correctly(self) -> None:
        capacity = vm.MacroCapacity(count=4, buffer_bytes=2048)
        macros = [self._tokened(2, 0x06), self._tokened(0, 0x04)]

        table = vm.slot_table(macros, capacity=capacity)
        self.assertEqual("#00951500", table[0]["original_key"])
        self.assertEqual("#00951502", table[2]["original_key"])

    def test_a_gapped_profile_round_trips_through_the_device(self) -> None:
        session = Session(count=4, buffer_bytes=2048)
        macros = [self._tokened(0, 0x04), self._tokened(3, 0x05)]

        vm.write_macros(session, macros, capacity=session.capacity)
        recovered = vm.read_macros(session, capacity=session.capacity)

        self.assertEqual(macros[0]["layer_key"], recovered[0]["layer_key"])
        self.assertEqual([], recovered[1]["layer_key"])
        self.assertEqual([], recovered[2]["layer_key"])
        self.assertEqual(macros[1]["layer_key"], recovered[3]["layer_key"])

    def test_read_back_carries_the_slot_token_not_the_first_event(self) -> None:
        """Otherwise the keymap and the macro list disagree about which key runs what."""

        session = Session(count=4, buffer_bytes=2048)
        vm.write_macros(session, [self._tokened(1, 0x04)], capacity=session.capacity)
        recovered = vm.read_macros(session, capacity=session.capacity)

        self.assertEqual("#00951501", recovered[1]["original_key"])
        self.assertNotEqual(
            recovered[1]["original_key"], recovered[1]["layer_key"][0]
        )

    def test_two_macros_claiming_one_slot_is_refused(self) -> None:
        capacity = vm.MacroCapacity(count=4, buffer_bytes=2048)
        with self.assertRaises(vm.MacroCapacityError) as raised:
            vm.slot_table(
                [self._tokened(1, 0x04), self._tokened(1, 0x05)], capacity=capacity
            )
        self.assertIn("slot 1", str(raised.exception))

    def test_a_slot_beyond_the_device_is_refused(self) -> None:
        capacity = vm.MacroCapacity(count=4, buffer_bytes=2048)
        with self.assertRaises(vm.MacroCapacityError):
            vm.slot_table([self._tokened(9, 0x04)], capacity=capacity)

    def test_macros_without_tokens_keep_their_list_positions(self) -> None:
        """A profile from a serial board never used the tokens."""

        capacity = vm.MacroCapacity(count=4, buffer_bytes=2048)
        macros = [_macro(1), _macro(1)]

        table = vm.slot_table(macros, capacity=capacity)
        self.assertIsNotNone(table[0])
        self.assertIsNotNone(table[1])
        self.assertIsNone(table[2])


if __name__ == "__main__":
    unittest.main()
