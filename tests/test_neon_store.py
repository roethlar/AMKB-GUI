from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from am_configurator import store, vial_keymap, vial_macros


def _neon_profile(*, unsupported_key: bool = False, macros: int = 0) -> dict:
    layer = [f"#0007{(4 + n) % 0x100:04X}" for n in range(90)]
    if unsupported_key:
        # A code the profile may legitimately hold and a Neon cannot accept.
        # Storing it must work; only applying it to the device may object.
        layer[13] = "#000C00E9"

    return {
        "product_info": {"product_id": "NEON80"},
        "key_layer": {"layer_num": 4, "layer_data": [{"layer": layer} for _ in range(4)]},
        "macro_key": [
            {
                "original_key": f"#1107{0x04 + index:04X}",
                "layer_key": [f"#1107{0x04 + index:04X}", f"#1007{0x04 + index:04X}"],
                "intvel_ms": [25, 0],
            }
            for index in range(macros)
        ],
        "page_data": [{"page_index": index} for index in range(8)],
    }


class NeonProfileStoreTests(unittest.TestCase):
    """The store is keyed by product id, so this proves it rather than assumes it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(store, "store_root", lambda: Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_product_key_is_accepted_and_stays_inside_the_store(self) -> None:
        self.assertEqual("NEON80", store._safe_key("NEON80"))
        directory = store.device_dir("NEON80", create=True)
        self.assertTrue(directory.is_dir())
        self.assertEqual(
            Path(self._tmp.name) / "devices" / "NEON80", directory
        )

    def test_a_profile_saves_and_reloads_unchanged(self) -> None:
        profile = _neon_profile(macros=4)
        path = store.save_current("NEON80", profile)

        self.assertTrue(path.is_file())
        self.assertEqual(profile, store.load_current("NEON80"))
        self.assertEqual("NEON80", store.load_meta("NEON80")["product_id"])

    def test_a_profile_holding_an_unwritable_keycode_still_stores(self) -> None:
        """Storing is not applying.

        A profile may hold codes this keyboard cannot accept — it may have come
        from another device entirely. It must load and display; the objection
        belongs to the moment it is applied, and names the keys.
        """

        profile = _neon_profile(unsupported_key=True)
        store.save_current("NEON80", profile)
        recovered = store.load_current("NEON80")

        self.assertEqual(profile, recovered)
        self.assertEqual("#000C00E9", recovered["key_layer"]["layer_data"][0]["layer"][13])

        # And it is the apply path that objects, by name.
        with self.assertRaises(vial_keymap.UnsupportedKeycode) as raised:
            vial_keymap.encode_layers(
                [entry["layer"] for entry in recovered["key_layer"]["layer_data"]]
            )
        self.assertIn("key 13", str(raised.exception))

    def test_a_profile_at_the_macro_capacity_boundary_round_trips(self) -> None:
        capacity = vial_macros.MacroCapacity(count=16, buffer_bytes=6677)
        profile = _neon_profile(macros=capacity.count)

        store.save_current("NEON80", profile)
        recovered = store.load_current("NEON80")

        self.assertEqual(capacity.count, len(recovered["macro_key"]))
        self.assertEqual(profile, recovered)
        # Exactly at the limit is acceptable to the device path too.
        vial_macros.encode_macros(recovered["macro_key"], capacity=capacity)

    def test_a_snapshot_round_trips_through_json(self) -> None:
        profile = _neon_profile(macros=2)
        store.save_current("NEON80", profile)
        snapshot = store.snapshot("NEON80", profile)

        self.assertTrue(snapshot.is_file())
        self.assertEqual(profile, json.loads(snapshot.read_text(encoding="utf-8")))
        self.assertIn(snapshot, store.list_history("NEON80"))

    def test_a_neon_and_a_serial_board_coexist(self) -> None:
        """Two stored devices must not collide or be guessed between."""

        store.save_current("NEON80", _neon_profile())
        store.save_current("CB04", {"product_info": {"product_id": "CB04"}})

        self.assertEqual("NEON80", store.load_current("NEON80")["product_info"]["product_id"])
        self.assertEqual("CB04", store.load_current("CB04")["product_info"]["product_id"])
        # With two devices stored, the store refuses to pick one.
        self.assertIsNone(store.sole_device())


if __name__ == "__main__":
    unittest.main()
