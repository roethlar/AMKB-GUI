from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from am_configurator import profile_metadata, store


def _layout(*, width: float = 6.0) -> list[dict[str, int | float]]:
    return [
        {
            "index": 0,
            "matrix_row": 0,
            "matrix_col": 0,
            "x": 0.0,
            "y": 0.0,
            "width": width,
            "height": 12.0,
            "rotation": 0.0,
        },
        {
            "index": 1,
            "matrix_row": 0,
            "matrix_col": 1,
            "x": 12.0,
            "y": 0.0,
            "width": 8.0,
            "height": 12.0,
            "rotation": 0.0,
        },
    ]


def _profile(product_id: str = "NEON80") -> dict:
    return {
        "product_info": {"product_id": product_id},
        "key_layer": {"layer_num": 0, "layer_data": []},
        "macro_key": [],
        "page_data": [],
    }


class PortableLayoutMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._store_root = Path(self._tmp.name)
        patcher = patch.object(store, "store_root", lambda: self._store_root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saved_neon_profile_is_self_contained_on_a_fresh_install(self) -> None:
        evidence = profile_metadata.remember_dynamic_layout("NEON80", _layout())
        saved = profile_metadata.portable_profile(
            _profile(),
            preferred_signature=evidence["keymap_signature"],
        )

        metadata = saved["config"]["_am_configurator"]
        self.assertEqual(
            {"schema_version", "dynamic_layout"},
            set(metadata),
        )
        self.assertEqual(
            {
                "schema_version",
                "product_id",
                "keymap_signature",
                "key_layout",
            },
            set(metadata["dynamic_layout"]),
        )
        self.assertEqual(evidence["keymap_signature"], saved["evidence"]["keymap_signature"])

        fresh_root = self._store_root / "fresh-install"
        with patch.object(store, "store_root", lambda: fresh_root):
            reopened = profile_metadata.resolve_layout_evidence(saved["config"])

        self.assertEqual("embedded", reopened["evidence"]["source"])
        self.assertEqual(evidence["key_layout"], reopened["evidence"]["key_layout"])
        self.assertIsNone(reopened["warning"])

    def test_malformed_or_unbounded_metadata_never_becomes_layout_evidence(self) -> None:
        evidence = profile_metadata.remember_dynamic_layout("NEON80", _layout())
        valid = profile_metadata.attach_dynamic_layout(_profile(), evidence)
        variants: dict[str, dict] = {}

        outer_unknown = copy.deepcopy(valid)
        outer_unknown["_am_configurator"]["machine"] = "netwatch-01"
        variants["unknown outer field"] = outer_unknown

        inner_unknown = copy.deepcopy(valid)
        inner_unknown["_am_configurator"]["dynamic_layout"]["address"] = "hid:path"
        variants["unknown layout field"] = inner_unknown

        wrong_product = copy.deepcopy(valid)
        wrong_product["_am_configurator"]["dynamic_layout"]["product_id"] = "CB04"
        variants["wrong product"] = wrong_product

        wrong_signature = copy.deepcopy(valid)
        wrong_signature["_am_configurator"]["dynamic_layout"]["keymap_signature"] = (
            "keymap:v1:" + "0" * 64
        )
        variants["wrong signature"] = wrong_signature

        key_unknown = copy.deepcopy(valid)
        key_unknown["_am_configurator"]["dynamic_layout"]["key_layout"][0][
            "serial"
        ] = "shared-dummy"
        variants["unknown key field"] = key_unknown

        oversized = copy.deepcopy(valid)
        oversized["_am_configurator"]["dynamic_layout"]["keymap_signature"] = (
            "x" * (profile_metadata.MAX_METADATA_BYTES + 1)
        )
        variants["oversized"] = oversized

        for name, candidate in variants.items():
            with self.subTest(name=name):
                resolved = profile_metadata.resolve_layout_evidence(candidate)
                self.assertIsNone(resolved["evidence"])
                self.assertIn("ignored", resolved["warning"].lower())

    def test_legacy_profile_uses_only_one_unambiguous_remembered_layout(self) -> None:
        legacy = _profile()
        missing = profile_metadata.resolve_layout_evidence(legacy)
        self.assertIsNone(missing["evidence"])
        self.assertIn("per-key", missing["warning"].lower())

        first = profile_metadata.remember_dynamic_layout("NEON80", _layout())
        remembered = profile_metadata.resolve_layout_evidence(legacy)
        self.assertEqual("remembered", remembered["evidence"]["source"])
        self.assertEqual(first["keymap_signature"], remembered["evidence"]["keymap_signature"])

        profile_metadata.remember_dynamic_layout("NEON80", _layout(width=7.0))
        ambiguous = profile_metadata.resolve_layout_evidence(legacy)
        self.assertIsNone(ambiguous["evidence"])
        self.assertIn("more than one", ambiguous["warning"].lower())

        selected = profile_metadata.resolve_layout_evidence(
            legacy,
            preferred_signature=first["keymap_signature"],
        )
        self.assertEqual(first["keymap_signature"], selected["evidence"]["keymap_signature"])

    def test_fixed_family_export_drops_app_metadata_without_other_changes(self) -> None:
        fixed = _profile("AM21")
        fixed["_am_configurator"] = {
            "schema_version": 1,
            "dynamic_layout": {"not": "for this family"},
        }
        result = profile_metadata.portable_profile(fixed)

        expected = copy.deepcopy(fixed)
        expected.pop("_am_configurator")
        self.assertEqual(expected, result["config"])
        self.assertIsNone(result["evidence"])

    def test_remembered_layouts_are_pathless_and_bounded(self) -> None:
        for index in range(store.LAYOUT_EVIDENCE_MAX + 3):
            profile_metadata.remember_dynamic_layout(
                "NEON80",
                _layout(width=5.0 + index / 10),
            )

        payload = store.load_layout_evidence("NEON80")
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual(store.LAYOUT_EVIDENCE_MAX, len(payload["layouts"]))
        encoded = json.dumps(payload, sort_keys=True).lower()
        for forbidden in (
            "address",
            "credential",
            "machine",
            "path",
            "serial",
            "username",
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
