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

    def test_a_vendor_usage_page_is_rejected(self) -> None:
        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.to_qmk("#00FF0004")
        self.assertIn("usage page", raised.exception.reason)
        self.assertEqual("#00FF0004", raised.exception.code)

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
        for bad in ("#00FF0004", "#11070004", "", "nonsense"):
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

        layers = [["#00070004", "#00FF0004", "#00070005"]]
        with self.assertRaises(vk.UnsupportedKeycode) as raised:
            vk.encode_layers(layers)

        self.assertIn("layer 0 key 1", str(raised.exception))

    def test_every_offending_key_is_reported_at_once(self) -> None:
        layers = [["#00FF0001", "#00070004"], ["#11070004", "#00070900"]]
        problems = vk.unsupported_codes(layers)

        self.assertEqual(
            [(0, 0, "#00FF0001"), (1, 0, "#11070004"), (1, 1, "#00070900")],
            [(layer, index, code) for layer, index, code, _ in problems],
        )

    def test_a_short_buffer_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            vk.decode_layers(b"\x00\x04", layers=2, keys_per_layer=4)

    def test_a_qmk_feature_keycode_has_no_representation(self) -> None:
        # 0x5C00 is well outside the modifier-plus-basic space.
        with self.assertRaises(vk.UnsupportedKeycode):
            vk.from_qmk(0x5C00)


if __name__ == "__main__":
    unittest.main()
