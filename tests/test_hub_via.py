"""Pure VIA lighting capability and command planning contracts."""

from __future__ import annotations

import copy
import unittest

from am_configurator import via_lighting


class ViaLightingCapabilityTests(unittest.TestCase):
    def test_version_two_builtin_definition_exposes_independent_surfaces(self) -> None:
        capabilities = via_lighting.capabilities_from_definition(
            {"lighting": "qmk_backlight_rgblight"},
            via_protocol=9,
        )

        self.assertEqual(
            [surface["id"] for surface in capabilities["surfaces"]],
            ["backlight", "underglow"],
        )

    def test_protocol_eleven_common_menu_is_recognized_but_vendor_menu_is_inert(self) -> None:
        capabilities = via_lighting.capabilities_from_definition(
            {"menus": ["vendor_magic", "qmk_rgb_matrix"]},
            via_protocol=11,
        )

        surface = capabilities["surfaces"][0]
        self.assertEqual(surface["id"], "rgb_matrix")
        self.assertEqual(surface["generation"], "qmk_rgb_matrix")
        self.assertEqual(surface["brightness"], {"min": 0, "max": 255})

        unsupported = via_lighting.capabilities_from_definition(
            {"menus": ["vendor_magic"]},
            via_protocol=11,
        )
        self.assertEqual(unsupported, {"surfaces": []})

    def test_inline_control_must_match_closed_channel_command_and_range(self) -> None:
        definition = {
            "menus": [
                {
                    "label": "Lighting",
                    "content": [
                        {
                            "label": "Brightness",
                            "type": "range",
                            "options": [0, 31],
                            "content": ["id_qmk_rgb_matrix_brightness", 3, 1],
                        },
                        {
                            "label": "Effect",
                            "type": "dropdown",
                            "options": ["All Off", "Solid Color", ["Vendor", 9]],
                            "content": ["id_qmk_rgb_matrix_effect", 3, 2],
                        },
                    ],
                }
            ]
        }
        capabilities = via_lighting.capabilities_from_definition(
            definition,
            via_protocol=11,
        )
        surface = capabilities["surfaces"][0]
        self.assertEqual(surface["brightness"], {"min": 0, "max": 31})
        self.assertEqual([effect["id"] for effect in surface["effects"]], [0, 1, 9])

        hostile = copy.deepcopy(definition)
        hostile["menus"][0]["content"][0]["content"][1] = 7
        with self.assertRaises(via_lighting.ViaLightingError) as caught:
            via_lighting.capabilities_from_definition(hostile, via_protocol=11)
        self.assertIn("closed contract", str(caught.exception))


class ViaLightingWritePlanTests(unittest.TestCase):
    def test_protocol_eleven_plan_uses_only_recognized_channel_commands(self) -> None:
        capabilities = via_lighting.capabilities_from_definition(
            {"menus": ["qmk_rgb_matrix"]},
            via_protocol=11,
        )
        target = {
            "capabilities": {"lighting": capabilities},
            "lighting": {
                "surfaces": [
                    {
                        "id": "rgb_matrix",
                        "effect_id": 0,
                        "brightness": 1,
                        "speed": 2,
                        "color": [3, 4],
                    }
                ]
            },
        }
        source = copy.deepcopy(target)
        source["lighting"]["surfaces"][0].update(
            {"effect_id": 1, "brightness": 5, "speed": 6, "color": [7, 8]}
        )

        plan = via_lighting.plan_write(source, target, via_protocol=11)

        self.assertEqual(
            [(command.channel, command.command, command.payload) for command in plan.commands],
            [
                (3, 2, b"\x01"),
                (3, 1, b"\x05"),
                (3, 3, b"\x06"),
                (3, 4, b"\x07\x08"),
            ],
        )
        self.assertEqual(plan.save_channels, (3,))

    def test_per_key_plan_requires_unique_definition_led_indexes(self) -> None:
        led_mapping = {"K_ESC": 7}
        capabilities = via_lighting.capabilities_from_definition(
            {"menus": ["qmk_rgb_matrix"]},
            via_protocol=11,
            led_mapping=led_mapping,
        )
        target = {
            "capabilities": {"lighting": capabilities},
            "keymap": {
                "layers": [{"index": 0, "keys": [{"key": "K_ESC", "code": 0x29}]}]
            },
            "lighting": {
                "surfaces": [{"id": "rgb_matrix", "per_key": {"K_ESC": [1, 2]}}]
            },
        }
        source = copy.deepcopy(target)
        source["lighting"]["surfaces"][0]["per_key"]["K_ESC"] = [10, 20]

        plan = via_lighting.plan_write(
            source,
            target,
            via_protocol=11,
            led_mapping=led_mapping,
        )

        self.assertEqual(
            [(command.channel, command.command, command.payload) for command in plan.commands],
            [(0, 1, b"\x07\x01\x0a\x14")],
        )
        self.assertEqual(plan.save_channels, (0,))

        with self.assertRaises(via_lighting.ViaLightingError):
            via_lighting.validate_led_mapping({"K_ESC": 7, "K_ENTER": 7})


if __name__ == "__main__":
    unittest.main()
