from __future__ import annotations

import unittest

from am_configurator import vial_keymap as vk


class InjectivityTests(unittest.TestCase):
    """Read-back is only stable if translation is injective.

    A 32-bit surface cannot round-trip onto 16-bit keycodes in general, so the
    contract is narrower and must actually hold: over the representable subset,
    write-then-read returns exactly what was written.
    """

    def test_every_representable_code_round_trips_byte_for_byte(self) -> None:
        seen: dict[int, str] = {}
        for usage in range(0x00, 0x100):
            for modifier in (0x00, 0x01, 0x02, 0x04, 0x08, 0x0F, 0x10, 0x20, 0x40, 0x80, 0xF0):
                code = f"#{modifier:02X}07{usage:04X}"
                if code == "#00070000":
                    # An empty key is spelled #00000000. This page-7 form is
                    # rejected as a duplicate spelling of the same keycode,
                    # which is what keeps read-back stable.
                    continue
                with self.subTest(code=code):
                    value = vk.to_qmk(code)
                    self.assertEqual(code, vk.from_qmk(value))
                    # Injective: no two distinct codes may share a keycode.
                    self.assertNotIn(value, seen, f"{code} collides with {seen.get(value)}")
                    seen[value] = code

    def test_the_basic_range_maps_to_the_identity(self) -> None:
        for usage in (0x04, 0x1D, 0x28, 0xFF):
            with self.subTest(usage=usage):
                self.assertEqual(usage, vk.to_qmk(f"#0007{usage:04X}"))

    def test_left_and_right_modifiers_are_distinct_keycodes(self) -> None:
        left = vk.to_qmk("#01070004")
        right = vk.to_qmk("#10070004")
        self.assertNotEqual(left, right)
        self.assertEqual("#01070004", vk.from_qmk(left))
        self.assertEqual("#10070004", vk.from_qmk(right))


class RejectionTests(unittest.TestCase):
    """Unsupported codes are named and refused, never coerced."""

    def test_a_usage_page_with_no_qmk_equivalent_is_rejected(self) -> None:
        # The HID consumer page. Real, emittable by the palette, and with no
        # QMK basic keycode. (0xFF is not an example any more: it is the
        # reserved passthrough page.)
        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.to_qmk("#000C00E9")
        self.assertIn("usage page", raised.exception.reason)
        self.assertEqual("#000C00E9", raised.exception.code)

    def test_a_usage_above_the_basic_range_is_rejected(self) -> None:
        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.to_qmk("#00070100")
        self.assertIn("basic keycode range", raised.exception.reason)

    def test_mixed_side_modifiers_are_rejected_not_flattened(self) -> None:
        """Flattening would silently change which key the user pressed."""

        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.to_qmk("#11070004")
        self.assertIn("left and right", raised.exception.reason)

    def test_a_malformed_code_is_rejected(self) -> None:
        for bad in ("", "#123", "0007004", "#GG070004"):
            with self.subTest(code=bad):
                with self.assertRaises(vk.UnsupportedKeycode):
                    vk.to_qmk(bad)

    def test_is_representable_never_raises(self) -> None:
        self.assertTrue(vk.is_representable("#00070004"))
        self.assertTrue(vk.is_representable("#00FF5101"), "passthrough is writable")
        for bad in ("#000C00E9", "#11070004", "", "nonsense"):
            with self.subTest(code=bad):
                self.assertFalse(vk.is_representable(bad))


class BufferTests(unittest.TestCase):
    def test_a_keymap_round_trips_through_the_buffer(self) -> None:
        layers = [
            [f"#0007{usage:04X}" for usage in range(0x04, 0x14)],
            [f"#0207{usage:04X}" for usage in range(0x04, 0x14)],
        ]
        buffer = vk.encode_layers(layers)

        self.assertEqual(len(layers) * len(layers[0]) * 2, len(buffer))
        self.assertEqual(
            layers, vk.decode_layers(buffer, layers=2, keys_per_layer=len(layers[0]))
        )

    def test_an_unsupported_code_stops_the_whole_keymap(self) -> None:
        """A partially translated keymap on a device is worse than none."""

        layers = [["#00070004", "#000C00E9", "#00070005"]]
        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.encode_layers(layers)

        self.assertIn("layer 0 key 1", str(raised.exception))

    def test_every_offending_key_is_reported_at_once(self) -> None:
        layers = [["#000C0001", "#00070004"], ["#11070004", "#00070900"]]
        problems = vk.unsupported_codes(layers)

        self.assertEqual(
            [(0, 0, "#000C0001"), (1, 0, "#11070004"), (1, 1, "#00070900")],
            [(layer, index, code) for layer, index, code, _ in problems],
        )

    def test_a_short_buffer_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            vk.decode_layers(b"\x00\x04", layers=2, keys_per_layer=4)

    def test_a_qmk_feature_keycode_is_carried_not_refused(self) -> None:
        """Reading must never fail, or a real keyboard becomes unreadable."""

        # The owner's board ships 0x5101 in its keymap. Refusing it made
        # read_keymap raise on the real device.
        self.assertEqual("#00FF5101", vk.from_qmk(0x5101))
        self.assertEqual(0x5101, vk.to_qmk("#00FF5101"))



class TotalityTests(unittest.TestCase):
    """The translation must be a bijection, proven over the whole space.

    Hardware forced this. The first design refused QMK feature keycodes, which
    made reading the owner's own keyboard fail on its shipped keymap: a keymap
    is full of layer switches and macros that have no HID spelling.
    """

    def test_every_keycode_round_trips(self) -> None:
        failures = [
            value for value in range(0x10000) if vk.to_qmk(vk.from_qmk(value)) != value
        ]
        self.assertEqual([], failures[:20])
        self.assertEqual(0, len(failures))

    def test_no_two_keycodes_share_a_spelling(self) -> None:
        spellings = {vk.from_qmk(value) for value in range(0x10000)}
        self.assertEqual(0x10000, len(spellings))

    def test_a_natural_code_may_not_also_be_written_as_passthrough(self) -> None:
        """Two spellings for one keycode would make read-back unstable."""

        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.to_qmk("#00FF0004")
        self.assertIn("#00070004", raised.exception.reason)

    def test_the_right_hand_flag_alone_has_no_hid_spelling(self) -> None:
        # QMK can set its right-hand bit with no modifier selected; the HID mask
        # has no bit for "right" on its own, so collapsing it to an unmodified
        # key would silently drop the flag.
        self.assertEqual("#00FF1004", vk.from_qmk(0x1004))
        self.assertEqual(0x1004, vk.to_qmk("#00FF1004"))


class DeviceKeymapTests(unittest.TestCase):
    """Buffer transport, against a recorded session rather than hardware."""

    class Session:
        def __init__(self, buffer: bytes = b"", *, layers: int = 4, unlocked: bool = True):
            self.buffer = bytearray(buffer)
            self.layers = layers
            self.unlocked = unlocked
            self.sent: list[bytes] = []
            self._reply = b""

        def send(self, packet: bytes) -> None:
            self.sent.append(bytes(packet))
            reply = bytearray(32)
            if packet[0] == vk.VIA_GET_LAYER_COUNT:
                reply[1] = self.layers
            elif packet[0] == vk.VIA_GET_BUFFER:
                offset = (packet[1] << 8) | packet[2]
                size = packet[3]
                reply[4 : 4 + size] = self.buffer[offset : offset + size]
            elif packet[0] == vk.VIA_SET_BUFFER:
                offset = (packet[1] << 8) | packet[2]
                size = packet[3]
                needed = offset + size
                if len(self.buffer) < needed:
                    self.buffer.extend(b"\x00" * (needed - len(self.buffer)))
                self.buffer[offset:needed] = packet[4 : 4 + size]
            elif packet[0] == 0xFE:
                reply[0] = 1 if self.unlocked else 0
                reply[1] = 0 if self.unlocked else 2
            self._reply = bytes(reply)

        def receive(self, timeout_ms: int = 0) -> bytes:
            return self._reply

    def test_the_layer_count_is_asked_not_assumed(self) -> None:
        session = self.Session(layers=4)
        self.assertEqual(4, vk.read_layer_count(session))

    def test_a_keymap_survives_a_write_then_read(self) -> None:
        layers = [[f"#0007{usage:04X}" for usage in range(4, 94)] for _ in range(4)]
        session = self.Session()

        written = vk.write_keymap(session, layers)
        self.assertEqual(4 * 90 * 2, written)

        recovered = vk.read_keymap(session, layers=4, keys_per_layer=90)
        self.assertEqual(layers, recovered)

    def test_a_locked_keyboard_reports_an_actionable_state(self) -> None:
        """Not a generic write failure: only the user can resolve it."""

        layers = [[f"#0007{usage:04X}" for usage in range(4, 94)] for _ in range(4)]
        session = self.Session(unlocked=False)

        with self.assertRaises(vk.KeyboardLocked) as raised:
            vk.write_keymap(session, layers)

        self.assertIn("unlocked from", str(raised.exception))
        self.assertIn("Nothing was", str(raised.exception))
        self.assertEqual(
            [], [p for p in session.sent if p[0] == vk.VIA_SET_BUFFER],
            "a locked keyboard was written to",
        )

    def test_an_unsupported_code_is_refused_before_any_byte_is_sent(self) -> None:
        layers = [["#000C00E9"] + [f"#0007{u:04X}" for u in range(4, 93)] for _ in range(4)]
        session = self.Session()

        with self.assertRaises(vk.UnsupportedKeycode):
            vk.write_keymap(session, layers)

        self.assertEqual([], session.sent, "the device was touched before validation")


class UiEmittableCodeTests(unittest.TestCase):
    """Every code the palette can produce must translate.

    Finding n567-5: clearing a key or assigning a macro made the entire keymap
    fail preflight, because the two most common assignments in the application
    had no mapping at all.
    """

    def test_clearing_a_key_translates(self) -> None:
        self.assertEqual(vk.KC_NO, vk.to_qmk("#00000000"))
        self.assertEqual("#00000000", vk.from_qmk(vk.KC_NO))

    def test_an_empty_key_has_exactly_one_spelling(self) -> None:
        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.to_qmk("#00070000")
        self.assertIn("#00000000", raised.exception.reason)

    def test_every_macro_slot_translates(self) -> None:
        for slot in range(vk.MACRO_SLOTS):
            code = f"#009515{slot:02X}"
            with self.subTest(slot=slot):
                value = vk.to_qmk(code)
                self.assertEqual(vk.QK_MACRO_BASE + slot, value)
                self.assertEqual(code, vk.from_qmk(value))

    def test_a_macro_slot_the_device_lacks_is_refused(self) -> None:
        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.to_qmk("#00951510")
        self.assertIn("macro slot 16", raised.exception.reason)

    def test_a_realistic_keymap_with_clears_and_macros_encodes(self) -> None:
        layer = [f"#0007{(4 + n) % 0x100:04X}" for n in range(90)]
        layer[0] = "#00000000"
        layer[1] = "#00951500"
        layer[2] = "#0095150F"

        encoded = vk.encode_layers([layer])
        self.assertEqual(90 * 2, len(encoded))
        self.assertEqual([layer], vk.decode_layers(encoded, layers=1, keys_per_layer=90))


if __name__ == "__main__":
    unittest.main()
