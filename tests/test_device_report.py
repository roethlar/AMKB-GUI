"""Guards for sanitized unsupported-board support reports."""

from __future__ import annotations

import json
import unittest

from am_configurator.device_report import (
    build_support_report,
    classify_devices,
    is_supported_product,
    sanitize_device,
)


class ProductSupportTests(unittest.TestCase):
    def test_known_families_are_supported(self) -> None:
        for product in ("CB04", "AM21", "80", "ALICE", "NEON80", "NEON"):
            with self.subTest(product=product):
                self.assertTrue(is_supported_product(product))

    def test_unknown_and_empty_are_unsupported(self) -> None:
        for product in ("", "NOT_A_BOARD", "XYZ99", None, 12):
            with self.subTest(product=product):
                self.assertFalse(is_supported_product(product))


class SanitizeTests(unittest.TestCase):
    def test_strips_paths_addresses_and_serials(self) -> None:
        raw = {
            "product_id": "FUTURE80",
            "is_keyboard": True,
            "transport": "serial",
            "address": "/dev/tty.usbmodem123",
            "path": "/Users/michael/Library/something",
            "port": "COM3",
            "serial_number": "secret-unit-serial",
            "version": "1.2.3",
            "pages": 8,
            "usb_vendor_id": 0x1234,
            "usb_product_id": 0x5678,
            "manufacturer": "ShouldNotLeak",
        }
        safe = sanitize_device(raw)
        self.assertEqual("FUTURE80", safe["product_id"])
        self.assertFalse(safe["supported"])
        self.assertTrue(safe["is_keyboard"])
        self.assertEqual("1.2.3", safe["version"])
        self.assertEqual(8, safe["pages"])
        self.assertEqual(0x1234, safe["usb_vendor_id"])
        for banned in (
            "address",
            "path",
            "port",
            "serial_number",
            "manufacturer",
        ):
            self.assertNotIn(banned, safe)
        blob = json.dumps(safe)
        self.assertNotIn("/Users/", blob)
        self.assertNotIn("usbmodem", blob)
        self.assertNotIn("secret-unit", blob)

    def test_redacts_path_like_strings_in_kept_fields(self) -> None:
        safe = sanitize_device(
            {
                "product_id": "FUTURE80",
                "is_keyboard": True,
                "product_name": "Board at /home/alice/dev/kb",
            }
        )
        self.assertIn("[redacted-path]", safe["product_name"])
        self.assertNotIn("/home/alice", safe["product_name"])

    def test_supported_neon_is_flagged(self) -> None:
        safe = sanitize_device(
            {
                "product_id": "NEON80",
                "is_keyboard": True,
                "transport": "hid",
            }
        )
        self.assertTrue(safe["supported"])


class ReportTests(unittest.TestCase):
    def test_headline_for_unsupported_keyboard(self) -> None:
        report = build_support_report(
            [
                {
                    "product_id": "FUTURE80",
                    "is_keyboard": True,
                    "transport": "serial",
                    "address": "/dev/ttyUSB0",
                }
            ],
            app_version="0.1.68",
            platform_name="Linux",
            platform_release="6.1",
            platform_machine="x86_64",
        )
        self.assertEqual(1, report["schema_version"])
        self.assertEqual("New keyboard model detected", report["headline"])
        self.assertEqual(1, report["counts"]["unsupported_keyboards"])
        self.assertEqual(0, report["counts"]["supported_keyboards"])
        self.assertEqual("0.1.68", report["app_version"])
        self.assertEqual("Linux", report["platform"]["system"])
        devices = report["devices"]["unsupported_keyboards"]
        self.assertEqual(1, len(devices))
        self.assertEqual("FUTURE80", devices[0]["product_id"])
        self.assertNotIn("address", devices[0])

    def test_empty_scan(self) -> None:
        report = build_support_report([])
        self.assertEqual("No devices detected", report["headline"])

    def test_supported_only(self) -> None:
        report = build_support_report(
            [{"product_id": "CB04", "is_keyboard": True, "transport": "serial"}]
        )
        self.assertEqual("Supported keyboard connected", report["headline"])
        self.assertEqual(1, report["counts"]["supported_keyboards"])

    def test_classify_splits_groups(self) -> None:
        groups = classify_devices(
            [
                {"product_id": "CB04", "is_keyboard": True},
                {"product_id": "WEIRD", "is_keyboard": True},
                {"product_id": None, "is_keyboard": False},
            ]
        )
        self.assertEqual(1, len(groups["supported_keyboards"]))
        self.assertEqual(1, len(groups["unsupported_keyboards"]))
        self.assertEqual(1, len(groups["other_devices"]))


if __name__ == "__main__":
    unittest.main()
