"""Pure schema-v2 lighting capability and transfer contracts."""

from __future__ import annotations

import unittest

from am_configurator import hub_lighting


def _surface(
    *,
    surface_id: str = "keys",
    role: str = "keys",
    generation: str = "qmk_rgb_matrix",
    maximum: int = 255,
) -> dict:
    return {
        "id": surface_id,
        "role": role,
        "generation": generation,
        "effects": [
            {"id": 0, "semantic": "off"},
            {"id": 1, "semantic": "solid"},
        ],
        "brightness": {"min": 0, "max": maximum},
        "speed": {"min": 0, "max": maximum},
        "color": {
            "space": "hsv",
            "channels": [
                {"min": 0, "max": maximum},
                {"min": 0, "max": maximum},
            ],
        },
        "per_key": {"pixel_count": 2},
    }


def _profile(surface: dict, state: dict | None = None) -> dict:
    profile = {
        "schema_version": 2,
        "identity": {
            "ecosystem": "via",
            "family": "fixture",
            "wire_identity": surface["id"],
        },
        "capabilities": {"lighting": {"surfaces": [surface]}},
        "keymap": {
            "layers": [
                {
                    "index": 0,
                    "keys": [
                        {"key": "K_ESC", "code": 0x29},
                        {"key": "K_ENTER", "code": 0x28},
                    ],
                }
            ]
        },
    }
    if state is not None:
        profile["lighting"] = {"surfaces": [state]}
    return profile


class LightingCapabilityTests(unittest.TestCase):
    def test_surface_capability_round_trips_native_ranges(self) -> None:
        surface = {
            "id": "keys",
            "role": "keys",
            "generation": "qmk_rgb_matrix",
            "effects": [
                {"id": 0, "semantic": "off"},
                {"id": 1, "semantic": "solid"},
            ],
            "brightness": {"min": 0, "max": 255},
            "speed": {"min": 0, "max": 7},
            "color": {
                "space": "hsv",
                "channels": [
                    {"min": 0, "max": 255},
                    {"min": 0, "max": 255},
                    {"min": 0, "max": 255},
                ],
            },
            "per_key": {"pixel_count": 3},
        }

        self.assertEqual(
            hub_lighting.validate_surface_capability(surface),
            surface,
        )

    def test_duplicate_effects_invalid_ranges_and_wrong_stream_are_rejected(self) -> None:
        duplicate = _surface()
        duplicate["effects"].append({"id": 1})
        with self.assertRaises(hub_lighting.LightingModelError):
            hub_lighting.validate_surface_capability(duplicate)

        bad_range = _surface()
        bad_range["brightness"] = {"min": 10, "max": 10}
        with self.assertRaises(hub_lighting.LightingModelError):
            hub_lighting.validate_surface_capability(bad_range)

        wrong_stream = _surface()
        wrong_stream["stream"] = {
            "protocol": "vialrgb-1",
            "pixel_count": 2,
            "max_chunk_pixels": 2,
            "volatile": True,
        }
        with self.assertRaises(hub_lighting.LightingModelError):
            hub_lighting.validate_surface_capability(wrong_stream)

    def test_surface_state_retains_exact_native_values(self) -> None:
        surface = _surface(maximum=31)
        state = {
            "id": "keys",
            "effect_id": 1,
            "brightness": 17,
            "speed": 9,
            "color": [5, 29],
            "per_key": {"K_ESC": [1, 2, 3]},
        }

        self.assertEqual(
            hub_lighting.validate_surface_state(state, surface),
            state,
        )


class LightingTransferTests(unittest.TestCase):
    def test_effect_semantic_and_native_ranges_adapt_explicitly(self) -> None:
        source_surface = _surface(maximum=255)
        target_surface = _surface(generation="vialrgb", maximum=100)
        target_surface["effects"] = [
            {"id": 4, "semantic": "off"},
            {"id": 9, "semantic": "solid"},
        ]
        source = _profile(
            source_surface,
            {
                "id": "keys",
                "effect_id": 1,
                "brightness": 128,
                "speed": 255,
                "color": [64, 128],
                "per_key": {"K_ESC": [1, 2, 3]},
            },
        )
        target = _profile(
            target_surface,
            {
                "id": "keys",
                "effect_id": 4,
                "brightness": 0,
                "speed": 0,
                "color": [0, 0],
                "per_key": {},
            },
        )

        plan = hub_lighting.plan_transfer(source, target)
        state = plan.lighting["surfaces"][0]
        self.assertEqual(state["effect_id"], 9)
        self.assertEqual(state["brightness"], 50)
        self.assertEqual(state["speed"], 100)
        self.assertEqual(state["color"], [25, 50])
        self.assertEqual(state["per_key"], {"K_ESC": [1, 2, 3]})
        self.assertTrue(any(item["verdict"] == "adapted" for item in plan.items))

    def test_omitted_lighting_preserves_target_without_findings(self) -> None:
        target = _profile(
            _surface(),
            {"id": "keys", "effect_id": 1, "brightness": 99},
        )
        source = _profile(_surface())

        plan = hub_lighting.plan_transfer(source, target)

        self.assertEqual(plan.lighting, target["lighting"])
        self.assertEqual(plan.items, ())

    def test_missing_key_and_incompatible_animation_are_reported_dropped(self) -> None:
        source_surface = _surface()
        source_surface["generation"] = "vialrgb"
        source_surface["stream"] = {
            "protocol": "vialrgb-1",
            "pixel_count": 2,
            "max_chunk_pixels": 2,
            "volatile": True,
        }
        target_surface = _surface()
        target_surface["generation"] = "vialrgb"
        target_surface["stream"] = {
            "protocol": "vialrgb-1",
            "pixel_count": 1,
            "max_chunk_pixels": 1,
            "volatile": True,
        }
        source = _profile(
            source_surface,
            {"id": "keys", "per_key": {"K_MISSING": [1, 2, 3]}},
        )
        source["lighting"]["animations"] = [
            {
                "name": "two pixels",
                "surface_id": "keys",
                "pixel_ids": ["K_ESC", "K_ENTER"],
                "frames": [["#000000", "#FFFFFF"]],
                "placement": "geometry_seam",
            }
        ]
        target = _profile(target_surface, {"id": "keys", "per_key": {}})

        plan = hub_lighting.plan_transfer(source, target)

        dropped = [item for item in plan.items if item["verdict"] == "dropped"]
        self.assertTrue(any("K_MISSING" in item["path"] for item in dropped))
        self.assertTrue(any("pixel identities" in item["reason"] for item in dropped))


if __name__ == "__main__":
    unittest.main()
