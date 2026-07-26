from __future__ import annotations

import json
import lzma
import struct
import unittest
from unittest.mock import patch

from am_configurator import hid_transport


def _definition_blob(payload: dict) -> bytes:
    return lzma.compress(json.dumps(payload).encode("utf-8"))


class FakeHandle:
    """A stand-in raw-HID endpoint that answers the three Vial read commands.

    Records every packet it is written so a test can prove discovery never
    issues a mutating subcommand.
    """

    def __init__(self, definition: dict | None, *, protocol: int = 5) -> None:
        self.blob = _definition_blob(definition) if definition is not None else b""
        self.protocol = protocol
        self.uid = b"\xaa" * 8
        self.written: list[bytes] = []
        self.closed = False
        self._queue: list[bytes] = []

    def write(self, data: bytes) -> int:
        packet = bytes(data[1:])  # strip the report-ID byte
        self.written.append(packet)
        prefix, sub = packet[0], packet[1]
        assert prefix == 0xFE, f"unexpected command prefix 0x{prefix:02X}"
        if sub == 0x00:
            self._queue.append(struct.pack("<I", self.protocol) + self.uid)
        elif sub == 0x01:
            self._queue.append(struct.pack("<I", len(self.blob)))
        elif sub == 0x02:
            block = packet[2] | (packet[3] << 8)
            chunk = self.blob[block * 32 : (block + 1) * 32]
            self._queue.append(chunk)
        else:
            raise AssertionError(f"mutating subcommand 0x{sub:02X} was issued")
        return len(data)

    def read(self, length: int, timeout_ms: int = 0) -> bytes:
        return (self._queue.pop(0) if self._queue else b"").ljust(length, b"\x00")

    def close(self) -> None:
        self.closed = True


def _entry(serial: str = "vial:f64c2b3c", path: bytes = b"DevSrvsID:1") -> dict:
    return {
        "path": path,
        "vendor_id": hid_transport.NEON_VENDOR_ID,
        "product_id": hid_transport.NEON_PRODUCT_ID,
        "serial_number": serial,
        "product_string": "AM Neon 80",
        "manufacturer_string": "AngryMiao",
        "usage_page": hid_transport.RAW_USAGE_PAGE,
        "usage": hid_transport.RAW_USAGE,
    }


class IdentityGateTests(unittest.TestCase):
    """The decoy case the plan names: right VID/PID, right prefix, wrong board."""

    def test_a_vial_board_that_is_not_a_neon_is_never_writable(self) -> None:
        # Everything a weaker check would accept: Apple's borrowed VID/PID, a
        # valid `vial:` prefix, and a plausible USB product string.
        decoy = FakeHandle({"name": "Some Other Vial Board", "matrix": {"rows": 6, "cols": 15}})

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=decoy),
        ):
            found = hid_transport.list_devices()

        self.assertEqual(1, len(found))
        info = found[0]
        self.assertTrue(info.is_vial)
        self.assertIsNone(info.model)
        self.assertFalse(info.writable)
        self.assertFalse(info.is_keyboard)
        self.assertIn("Some Other Vial Board", info.identity_error)
        self.assertTrue(decoy.closed)

        with self.assertRaises(hid_transport.HidIdentityError):
            hid_transport.approve_write(info, "NEON80")

    def test_the_real_definition_is_accepted(self) -> None:
        real = FakeHandle(
            {
                "name": "AM Neon 80",
                "vendorId": "05AC",
                "productId": "024F",
                "matrix": {"rows": 6, "cols": 15},
                "layouts": {},
            }
        )

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=real),
        ):
            info = hid_transport.list_devices()[0]

        self.assertEqual("NEON80", info.model)
        self.assertTrue(info.writable)
        self.assertIsNone(info.identity_error)
        self.assertEqual("AM Neon 80", info.definition_name)

    def test_a_board_without_the_vial_prefix_is_rejected_without_being_opened(self) -> None:
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry(serial="AM21")]),
            patch.object(hid_transport, "_open", side_effect=AssertionError("must not open")),
        ):
            info = hid_transport.list_devices()[0]

        self.assertFalse(info.is_vial)
        self.assertFalse(info.writable)

    def test_identifying_a_device_never_issues_a_mutating_command(self) -> None:
        handle = FakeHandle({"name": "AM Neon 80"})

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            hid_transport.list_devices()

        issued = {packet[1] for packet in handle.written}
        self.assertTrue(issued)
        self.assertTrue(
            issued <= {0x00, 0x01, 0x02},
            f"discovery issued non-read subcommands: {sorted(issued)}",
        )

    def test_the_transport_refuses_a_mutating_subcommand_outright(self) -> None:
        """The guard lives here so a mistyped constant cannot reach the board."""

        handle = FakeHandle({"name": "AM Neon 80"})
        for subcommand in (0x04, 0x06, 0x07, 0x08):
            with self.subTest(subcommand=subcommand):
                with self.assertRaises(hid_transport.HidError):
                    hid_transport._vial_request(handle, subcommand)
        self.assertEqual([], handle.written)

    def test_an_implausible_definition_size_does_not_become_an_unbounded_read(self) -> None:
        handle = FakeHandle({"name": "AM Neon 80"})
        handle.blob = b"x" * (hid_transport._MAX_DEFINITION_BYTES + 1)

        with self.assertRaises(hid_transport.HidIdentityError):
            hid_transport.fetch_definition(handle)


class AddressIdentityTests(unittest.TestCase):
    """Model identity and instance identity are different questions.

    Two USB-visible values look like unique identifiers and are not. Every Vial
    board reports the serial `vial:f64c2b3c`. Every *unit of a model* reports
    the same Vial keyboard UID, because that UID is a firmware build-time
    constant. Both were used as an address in turn and both collide.
    """

    def _identify(self, uid: bytes, path: bytes = b"DevSrvsID:1"):
        handle = FakeHandle({"name": "AM Neon 80"})
        handle.uid = uid
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry(path=path)]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            return hid_transport.list_devices()[0]

    def test_two_units_of_the_same_model_get_different_addresses(self) -> None:
        # The case that cannot be reproduced with one keyboard: two Neon 80s,
        # same firmware, therefore identical serial AND identical Vial UID.
        # Only the endpoint differs.
        same_uid = b"\xd4\x7a\xf3\x8a\x35\xb8\xed\x73"
        first = self._identify(same_uid, path=b"DevSrvsID:1")
        second = self._identify(same_uid, path=b"DevSrvsID:2")

        self.assertEqual(first.serial_number, second.serial_number)
        self.assertEqual(first.firmware_uid, second.firmware_uid)
        self.assertNotEqual(
            first.address, second.address,
            "two units of one model must not share an address",
        )

    def test_an_address_leaks_neither_shared_identifier(self) -> None:
        info = self._identify(b"\xd4\x7a\xf3\x8a\x35\xb8\xed\x73")

        self.assertNotIn("f64c2b3c", info.address)
        self.assertNotIn("d47af38a35b8ed73", info.address)

    def test_the_firmware_uid_is_kept_as_model_identity(self) -> None:
        info = self._identify(b"\xd4\x7a\xf3\x8a\x35\xb8\xed\x73")

        self.assertEqual("d47af38a35b8ed73", info.firmware_uid)
        self.assertEqual(5, info.protocol_version)
        self.assertEqual("NEON80", info.model)

    def test_an_incoherent_vial_identity_is_refused(self) -> None:
        handle = FakeHandle({"name": "AM Neon 80"}, protocol=0)
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            info = hid_transport.list_devices()[0]

        self.assertIsNone(info.model)
        self.assertFalse(info.writable)

    def test_an_approval_does_not_transfer_between_units(self) -> None:
        same_uid = b"\xd4\x7a\xf3\x8a\x35\xb8\xed\x73"
        approval = hid_transport.approve_write(
            self._identify(same_uid, path=b"DevSrvsID:1"), "NEON80"
        )
        other_unit = self._identify(same_uid, path=b"DevSrvsID:2")

        self.assertFalse(approval.matches(other_unit))


class BoundedDecompressionTests(unittest.TestCase):
    """Definition decoding runs against any attached board, before any write."""

    def test_a_small_payload_that_expands_enormously_is_rejected(self) -> None:
        # 200 MiB of zeros compresses to roughly 30 KB, which passes any
        # compressed-size cap and then expands in full. Bounding the compressed
        # size alone bounds the wrong quantity.
        bomb = lzma.compress(b"\x00" * (200 * 1024 * 1024))
        self.assertLess(len(bomb), hid_transport._MAX_DEFINITION_BYTES)

        with self.assertRaises(hid_transport.HidIdentityError) as raised:
            hid_transport._decompress_bounded(bomb)
        self.assertIn("expands beyond", str(raised.exception))

    def test_fetch_definition_actually_applies_the_bound(self) -> None:
        """Guards the call site, not just the helper.

        Testing `_decompress_bounded` alone proves nothing about whether
        `fetch_definition` calls it — reverting the call site to a plain
        `lzma.decompress` left every helper test green.
        """

        handle = FakeHandle({"name": "AM Neon 80"})
        handle.blob = lzma.compress(b"\x00" * (200 * 1024 * 1024))
        self.assertLess(len(handle.blob), hid_transport._MAX_DEFINITION_BYTES)

        with self.assertRaises(hid_transport.HidIdentityError) as raised:
            hid_transport.fetch_definition(handle)
        self.assertIn("expands beyond", str(raised.exception))

    def test_a_normal_definition_still_decodes(self) -> None:
        payload = json.dumps({"name": "AM Neon 80"}).encode("utf-8")
        self.assertEqual(payload, hid_transport._decompress_bounded(lzma.compress(payload)))

    def test_a_truncated_stream_is_rejected(self) -> None:
        blob = lzma.compress(json.dumps({"name": "AM Neon 80"}).encode("utf-8"))
        with self.assertRaises(hid_transport.HidIdentityError):
            hid_transport._decompress_bounded(blob[:-8])

    def test_trailing_data_after_the_stream_is_rejected(self) -> None:
        blob = lzma.compress(json.dumps({"name": "AM Neon 80"}).encode("utf-8"))
        with self.assertRaises(hid_transport.HidIdentityError) as raised:
            hid_transport._decompress_bounded(blob + b"junk")
        self.assertIn("trailing", str(raised.exception))


class WriteApprovalTests(unittest.TestCase):
    def _writable(self, path: bytes = b"DevSrvsID:1") -> hid_transport.HidDeviceInfo:
        handle = FakeHandle({"name": "AM Neon 80"})
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry(path=path)]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            return hid_transport.list_devices()[0]

    def test_a_changed_path_invalidates_a_prior_confirmation(self) -> None:
        """A device swapped after confirmation must not inherit the approval."""

        approval = hid_transport.approve_write(self._writable(b"DevSrvsID:1"), "NEON80")

        self.assertTrue(approval.matches(self._writable(b"DevSrvsID:1")))
        # Same model, same address, different connection: the board was replugged
        # or swapped, so the typed confirmation no longer covers it.
        self.assertFalse(approval.matches(self._writable(b"DevSrvsID:2")))

    def test_confirmation_must_equal_the_validated_model(self) -> None:
        info = self._writable()

        for wrong in ("", "neon80", "AM Neon 80", "NEON"):
            with self.subTest(confirmation=wrong):
                with self.assertRaises(hid_transport.HidIdentityError):
                    hid_transport.approve_write(info, wrong)

        self.assertEqual("NEON80", hid_transport.approve_write(info, " NEON80 ").model)

    def test_an_unidentified_device_cannot_be_approved(self) -> None:
        decoy = FakeHandle({"name": "Not A Neon"})
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=decoy),
        ):
            info = hid_transport.list_devices()[0]

        with self.assertRaises(hid_transport.HidIdentityError):
            hid_transport.approve_write(info, "NEON80")


class OpenFailureClassificationTests(unittest.TestCase):
    """hidapi says only 'open failed', so the cause must be worked out elsewhere."""

    def test_the_binding_really_does_hide_the_cause(self) -> None:
        """Pins the premise. If a future hidapi reports errno, revisit this."""

        import hid

        handle = hid.device()
        with self.assertRaises(OSError) as raised:
            handle.open_path(b"/nonexistent-hid-path")
        text = str(raised.exception).lower()
        self.assertNotIn("permission", text)
        self.assertNotIn("busy", text)

    def test_open_routes_failures_through_the_classifier(self) -> None:
        """Guards the call site in `_open`, not just the classifier.

        Testing `_classify_open_failure` alone proves nothing: reverting `_open`
        to the old substring matching left every classifier test green.
        """

        class RefusingHandle:
            def open_path(self, path):
                raise OSError("open failed")

        fake_hid = type("FakeHid", (), {"device": staticmethod(RefusingHandle)})

        with (
            patch("sys.platform", "linux"),
            patch("os.path.exists", return_value=True),
            patch("os.access", return_value=False),
            patch.object(hid_transport, "_hid", return_value=fake_hid),
        ):
            with self.assertRaises(hid_transport.HidPermissionDenied) as raised:
                hid_transport._open(b"/dev/hidraw3")

        # The exact failure this finding is about: before the fix, a Linux user
        # with no udev rule was told the keyboard was not attached.
        self.assertIn("60-am-neon-80.rules", str(raised.exception))

    def test_linux_permission_denied_names_the_udev_remedy(self) -> None:
        with (
            patch("sys.platform", "linux"),
            patch("os.path.exists", return_value=True),
            patch("os.access", return_value=False),
        ):
            error = hid_transport._classify_open_failure(b"/dev/hidraw3")

        self.assertIsInstance(error, hid_transport.HidPermissionDenied)
        self.assertIn("udev", str(error))
        self.assertIn("60-am-neon-80.rules", str(error))

    def test_linux_missing_node_is_absent_not_permission(self) -> None:
        with (
            patch("sys.platform", "linux"),
            patch("os.path.exists", return_value=False),
        ):
            error = hid_transport._classify_open_failure(b"/dev/hidraw3")

        self.assertIsInstance(error, hid_transport.HidDeviceAbsent)

    def test_linux_accessible_node_that_will_not_open_is_busy(self) -> None:
        with (
            patch("sys.platform", "linux"),
            patch("os.path.exists", return_value=True),
            patch("os.access", return_value=True),
        ):
            error = hid_transport._classify_open_failure(b"/dev/hidraw3")

        self.assertIsInstance(error, hid_transport.HidDeviceBusy)

    def test_an_undeterminable_cause_is_reported_honestly(self) -> None:
        """Never assert a cause that was not determined."""

        with (
            patch("sys.platform", "darwin"),
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry(path=b"DevSrvsID:9")]),
        ):
            error = hid_transport._classify_open_failure(b"DevSrvsID:9")

        self.assertIsInstance(error, hid_transport.HidError)
        self.assertNotIsInstance(error, hid_transport.HidDeviceAbsent)
        self.assertIn("may be in use", str(error))

    def test_a_vanished_endpoint_is_absent(self) -> None:
        with (
            patch("sys.platform", "darwin"),
            patch.object(hid_transport, "raw_endpoints", return_value=[]),
        ):
            error = hid_transport._classify_open_failure(b"DevSrvsID:9")

        self.assertIsInstance(error, hid_transport.HidDeviceAbsent)


class ErrorSurfaceTests(unittest.TestCase):
    def test_errors_never_leak_a_device_path(self) -> None:
        path = b"DevSrvsID:4295309077"

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry(path=path)]),
            patch.object(
                hid_transport,
                "_open",
                side_effect=hid_transport.HidPermissionDenied("Permission denied opening the keyboard."),
            ),
        ):
            info = hid_transport.list_devices()[0]

        self.assertIsNotNone(info.identity_error)
        self.assertNotIn("DevSrvsID", info.identity_error)

    def test_a_missing_address_raises_absent(self) -> None:
        with patch.object(hid_transport, "raw_endpoints", return_value=[]):
            with self.assertRaises(hid_transport.HidDeviceAbsent):
                hid_transport.find("05AC:024F:vial:f64c2b3c")


if __name__ == "__main__":
    unittest.main()
