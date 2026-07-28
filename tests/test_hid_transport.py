from __future__ import annotations

import dataclasses
import json
import lzma
import struct
import unittest
from unittest.mock import patch

from am_configurator import hid_transport, transport


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
        if prefix != 0xFE:
            # Non-Vial traffic (a 0xF0 lighting packet, say) is recorded but not
            # answered. The read-only rule below applies to Vial subcommands.
            return len(data)
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
            found = hid_transport.list_devices(deep=True)

        self.assertEqual(1, len(found))
        info = found[0]
        self.assertTrue(info.is_vial)
        self.assertIsNone(info.model)
        self.assertFalse(info.writable)
        # It *is* a keyboard — it simply is not this one. Listing it is right;
        # the property that must stay false is `writable`.
        self.assertTrue(info.is_keyboard)
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
                "layouts": {
                    "keymap": [
                        [{"c": "#777777"}, "0,0", {"x": 0.25, "w": 2}, "0,1"],
                        [{"y": 0.25}, "1,0"],
                    ]
                },
            }
        )

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=real),
        ):
            info = hid_transport.list_devices(deep=True)[0]

        self.assertEqual("NEON80", info.model)
        self.assertTrue(info.writable)
        self.assertIsNone(info.identity_error)
        self.assertEqual("AM Neon 80", info.definition_name)
        self.assertEqual([0, 1, 15], [key["index"] for key in info.key_layout])
        self.assertEqual(
            [(0, 0), (0, 1), (1, 0)],
            [
                (key["matrix_row"], key["matrix_col"])
                for key in info.key_layout
            ],
        )
        self.assertGreater(info.key_layout[1]["width"], info.key_layout[0]["width"])
        self.assertGreater(info.key_layout[2]["y"], info.key_layout[0]["y"])
        self.assertTrue(
            all(
                0 <= key["x"] < 100
                and 0 <= key["y"] < 100
                and key["x"] + key["width"] <= 100
                and key["y"] + key["height"] <= 100
                for key in info.key_layout
            )
        )
        payload = transport.device_json(
            transport.DeviceHandle("hid", info.address), info
        )
        self.assertEqual([0, 1, 15], [key["index"] for key in payload["key_layout"]])

    def test_a_malformed_physical_layout_never_becomes_a_guessed_matrix(self) -> None:
        definition = {
            "matrix": {"rows": 6, "cols": 15},
            "layouts": {"keymap": [["0,0", "0,0"]]},
        }

        self.assertEqual((), hid_transport.project_key_layout(definition))

    def test_a_board_without_the_vial_prefix_is_rejected_without_being_opened(self) -> None:
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry(serial="AM21")]),
            patch.object(hid_transport, "_open", side_effect=AssertionError("must not open")),
        ):
            info = hid_transport.list_devices(deep=True)[0]

        self.assertFalse(info.is_vial)
        self.assertFalse(info.writable)

    def test_identifying_a_device_never_issues_a_mutating_command(self) -> None:
        handle = FakeHandle({"name": "AM Neon 80"})

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            hid_transport.list_devices(deep=True)

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


class ShallowDiscoveryTests(unittest.TestCase):
    """A scan lists candidates and opens nothing.

    Interrogating every attached Vial board on every scan is slow, contends for
    exclusive access with other applications, and made the suite trap at
    interpreter shutdown. The definition gate runs when a device is resolved.
    """

    def test_a_scan_never_opens_a_device(self) -> None:
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", side_effect=AssertionError("scan opened a device")),
        ):
            found = hid_transport.list_devices()

        self.assertEqual(1, len(found))
        info = found[0]
        self.assertTrue(info.is_vial)
        self.assertTrue(info.is_keyboard, "a Vial board must still be listed")
        self.assertFalse(info.writable, "an uninterrogated device is not writable")
        self.assertIsNone(info.model)
        # The canonical id, not the USB product string. Reporting the string
        # here and the model after identification meant the browser asked the
        # user to confirm one value while the server demanded the other, so no
        # write could succeed (finding n567-3).
        self.assertEqual("NEON80", info.product_id)
        self.assertEqual("AM Neon 80", info.product_string)

    def test_resolving_an_address_runs_the_full_gate(self) -> None:
        handle = FakeHandle({"name": "AM Neon 80"})
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            info = hid_transport.find(hid_transport.endpoint_address(b"DevSrvsID:1"))

        self.assertEqual("NEON80", info.model)
        self.assertTrue(info.writable)

    def test_a_listed_device_cannot_be_approved_without_being_resolved(self) -> None:
        """Listing is not authorization."""

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", side_effect=AssertionError("must not open")),
        ):
            info = hid_transport.list_devices()[0]

        with self.assertRaises(hid_transport.HidIdentityError):
            hid_transport.approve_write(info, "NEON80")


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
            return hid_transport.list_devices(deep=True)[0]

    def test_two_units_of_the_same_model_get_different_addresses(self) -> None:
        # The case that cannot be reproduced with one keyboard: two Neon 80s,
        # same firmware, therefore identical serial AND identical Vial UID.
        # Only the endpoint differs.
        same_uid = b"\x01\x23\x45\x67\x89\xab\xcd\xef"
        first = self._identify(same_uid, path=b"DevSrvsID:1")
        second = self._identify(same_uid, path=b"DevSrvsID:2")

        self.assertEqual(first.serial_number, second.serial_number)
        self.assertEqual(first.firmware_uid, second.firmware_uid)
        self.assertNotEqual(
            first.address, second.address,
            "two units of one model must not share an address",
        )

    def test_an_address_leaks_neither_shared_identifier(self) -> None:
        info = self._identify(b"\x01\x23\x45\x67\x89\xab\xcd\xef")

        self.assertNotIn("f64c2b3c", info.address)
        self.assertNotIn("0123456789abcdef", info.address)

    def test_the_firmware_uid_is_kept_as_model_identity(self) -> None:
        info = self._identify(b"\x01\x23\x45\x67\x89\xab\xcd\xef")

        self.assertEqual("0123456789abcdef", info.firmware_uid)
        self.assertEqual(5, info.protocol_version)
        self.assertEqual("NEON80", info.model)

    def test_an_incoherent_vial_identity_is_refused(self) -> None:
        handle = FakeHandle({"name": "AM Neon 80"}, protocol=0)
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            info = hid_transport.list_devices(deep=True)[0]

        self.assertIsNone(info.model)
        self.assertFalse(info.writable)

    def test_an_approval_does_not_transfer_between_units(self) -> None:
        same_uid = b"\x01\x23\x45\x67\x89\xab\xcd\xef"
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
            return hid_transport.list_devices(deep=True)[0]

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
            info = hid_transport.list_devices(deep=True)[0]

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

    def test_the_classifier_never_raises_even_if_enumeration_fails(self) -> None:
        """Its contract is to return an error, not raise one.

        `identify` catches only `HidError`, so anything escaping the classifier
        crashes discovery for every device instead of marking one unidentified.
        Re-enumeration touches the USB stack and can fail on its own.
        """

        with (
            patch("sys.platform", "darwin"),
            patch.object(hid_transport, "raw_endpoints", side_effect=OSError("usb went away")),
        ):
            error = hid_transport._classify_open_failure(b"DevSrvsID:9")

        self.assertIsInstance(error, hid_transport.HidError)

    def test_discovery_survives_an_open_failure_with_broken_enumeration(self) -> None:
        """The end-to-end consequence: one bad device must not kill the scan."""

        calls = {"n": 0}

        def _flaky_endpoints(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return [_entry()]
            raise OSError("usb went away")

        class RefusingHandle:
            def open_path(self, path):
                raise OSError("open failed")

        fake_hid = type("FakeHid", (), {"device": staticmethod(RefusingHandle)})

        # Patch the binding, not `_open`: `_open` is what converts the OSError,
        # so replacing it would bypass the behaviour under test.
        with (
            patch("sys.platform", "darwin"),
            patch.object(hid_transport, "raw_endpoints", side_effect=_flaky_endpoints),
            patch.object(hid_transport, "_hid", return_value=fake_hid),
        ):
            found = hid_transport.list_devices(deep=True)

        self.assertEqual(1, len(found))
        self.assertFalse(found[0].writable)
        self.assertIsNotNone(found[0].identity_error)

    def test_a_vanished_endpoint_is_absent(self) -> None:
        with (
            patch("sys.platform", "darwin"),
            patch.object(hid_transport, "raw_endpoints", return_value=[]),
        ):
            error = hid_transport._classify_open_failure(b"DevSrvsID:9")

        self.assertIsInstance(error, hid_transport.HidDeviceAbsent)


class ApprovalIsLoadBearingTests(unittest.TestCase):
    """An approval that nothing requires is decoration, not a control."""

    def _writable(self, path: bytes = b"DevSrvsID:1", uid: bytes = b"\x01\x23\x45\x67\x89\xab\xcd\xef"):
        handle = FakeHandle({"name": "AM Neon 80"})
        handle.uid = uid
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry(path=path)]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            return hid_transport.list_devices(deep=True)[0]

    def test_there_is_no_public_way_to_send_without_an_approval(self) -> None:
        """The old public session took a bare path and wrote with no approval."""

        self.assertFalse(
            hasattr(hid_transport, "HidSession"),
            "a public path-taking session lets callers skip the approval",
        )
        public_senders = [
            name
            for name in dir(hid_transport)
            if not name.startswith("_") and name.lower().endswith("session")
        ]
        self.assertEqual([], public_senders, public_senders)

    def test_a_swapped_device_on_the_same_path_is_refused_at_open(self) -> None:
        """The gap this closes: validation and writing on different handles."""

        approval = hid_transport.approve_write(self._writable(), "NEON80")

        # A different keyboard now answers on the same OS path.
        impostor = FakeHandle({"name": "Some Other Vial Board"})
        impostor.uid = b"\x99" * 8
        with patch.object(hid_transport, "_open", return_value=impostor):
            with self.assertRaises(hid_transport.HidIdentityError) as raised:
                hid_transport.open_approved(approval)

        self.assertIn("not the keyboard", str(raised.exception))
        self.assertTrue(impostor.closed, "the handle must be closed on refusal")

    def test_a_neon_with_a_different_firmware_uid_is_refused(self) -> None:
        approval = hid_transport.approve_write(self._writable(), "NEON80")

        other = FakeHandle({"name": "AM Neon 80"})
        other.uid = b"\x01" * 8
        with patch.object(hid_transport, "_open", return_value=other):
            with self.assertRaises(hid_transport.HidIdentityError):
                hid_transport.open_approved(approval)

    def test_using_the_session_as_a_context_manager_keeps_the_checked_handle(self) -> None:
        """`with session:` must not silently replace the validated handle.

        `open_approved` returns an already-open, already-checked session. If
        `__enter__` reopened, the ordinary idiom would swap in a second handle
        that nothing validated — defeating the whole re-check.
        """

        approval = hid_transport.approve_write(self._writable(), "NEON80")

        genuine = FakeHandle({"name": "AM Neon 80"})
        genuine.uid = b"\x01\x23\x45\x67\x89\xab\xcd\xef"
        opens: list = []

        with patch.object(hid_transport, "_open", side_effect=lambda p: (opens.append(p), genuine)[1]):
            session = hid_transport.open_approved(approval)
            with session as entered:
                entered.send(bytes([0xF0, 0x0E, 0x01]))

        self.assertEqual(1, len(opens), "the validated handle was reopened")

    def test_a_forged_approval_is_refused(self) -> None:
        """An approval must prove it came from `approve_write`.

        `WriteApproval` is a public dataclass, so a caller can build one with
        every field correct. Only provenance distinguishes it from a real one.
        """

        info = self._writable()
        forged = hid_transport.WriteApproval(
            address=info.address,
            model="NEON80",
            path=info.path,
            confirmation="NEON80",
            model_uid=info.firmware_uid,
        )

        genuine = FakeHandle({"name": "AM Neon 80"})
        genuine.uid = b"\x01\x23\x45\x67\x89\xab\xcd\xef"
        with patch.object(hid_transport, "_open", return_value=genuine):
            with self.assertRaises(hid_transport.HidIdentityError) as raised:
                hid_transport.open_approved(forged)

        self.assertIn("not issued by approve_write", str(raised.exception))

    def test_a_tampered_confirmation_is_refused_at_open(self) -> None:
        """The typed confirmation is re-checked, not trusted from issue time."""

        approval = hid_transport.approve_write(self._writable(), "NEON80")
        tampered = dataclasses.replace(approval, confirmation="yes")

        genuine = FakeHandle({"name": "AM Neon 80"})
        genuine.uid = b"\x01\x23\x45\x67\x89\xab\xcd\xef"
        with patch.object(hid_transport, "_open", return_value=genuine):
            with self.assertRaises(hid_transport.HidIdentityError):
                hid_transport.open_approved(tampered)

    def test_the_approved_device_opens_and_can_transmit(self) -> None:
        approval = hid_transport.approve_write(self._writable(), "NEON80")

        genuine = FakeHandle({"name": "AM Neon 80"})
        genuine.uid = b"\x01\x23\x45\x67\x89\xab\xcd\xef"
        with patch.object(hid_transport, "_open", return_value=genuine):
            session = hid_transport.open_approved(approval)
            try:
                session.send(bytes([0xF0, 0x0E, 0x01]))
            finally:
                session.close()

        self.assertIn(bytes([0xF0, 0x0E, 0x01]).ljust(32, b"\x00"), genuine.written)
        self.assertTrue(genuine.closed)

    def test_identity_is_reproved_on_the_handle_that_is_returned(self) -> None:
        """Not on a fresh handle opened afterwards, which reopens the gap."""

        approval = hid_transport.approve_write(self._writable(), "NEON80")

        genuine = FakeHandle({"name": "AM Neon 80"})
        genuine.uid = b"\x01\x23\x45\x67\x89\xab\xcd\xef"
        opens: list = []

        def _tracking_open(path):
            opens.append(path)
            return genuine

        with patch.object(hid_transport, "_open", side_effect=_tracking_open):
            session = hid_transport.open_approved(approval)
            session.close()

        self.assertEqual(1, len(opens), "the device must be opened exactly once")


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
            info = hid_transport.list_devices(deep=True)[0]

        self.assertIsNotNone(info.identity_error)
        self.assertNotIn("DevSrvsID", info.identity_error)

    def test_a_missing_address_raises_absent(self) -> None:
        with patch.object(hid_transport, "raw_endpoints", return_value=[]):
            with self.assertRaises(hid_transport.HidDeviceAbsent):
                hid_transport.find("05AC:024F:vial:f64c2b3c")


if __name__ == "__main__":
    unittest.main()


class CanonicalProductIdTests(unittest.TestCase):
    """One product id, everywhere. A write confirmation is compared against it.

    Finding n567-3: discovery reported the USB product string and deep
    identification reported the model, so the browser asked the user to confirm
    one value and the server demanded the other. No Neon write could succeed.
    """

    def test_the_id_is_identical_before_and_after_identification(self) -> None:
        handle = FakeHandle({"name": "AM Neon 80"})

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", return_value=handle),
        ):
            shallow = hid_transport.list_devices()[0]
            deep = hid_transport.find(shallow.address)

        self.assertEqual(shallow.product_id, deep.product_id)
        self.assertEqual("NEON80", shallow.product_id)

    def test_the_untrusted_usb_string_stays_separate(self) -> None:
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", side_effect=AssertionError("must not open")),
        ):
            info = hid_transport.list_devices()[0]

        self.assertNotEqual(info.product_id, info.product_string)
        self.assertEqual("AM Neon 80", info.product_string)

    def test_an_unrecognised_board_has_no_product_id(self) -> None:
        """It must not inherit a family from a firmware-authored string."""

        entry = _entry()
        entry["product_string"] = "Some Other Vial Board"
        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[entry]),
            patch.object(hid_transport, "_open", side_effect=AssertionError("must not open")),
        ):
            info = hid_transport.list_devices()[0]

        self.assertEqual("", info.product_id)

    def test_device_info_carries_the_fields_every_route_reads(self) -> None:
        """`version` was absent, so a successful write raised after mutating."""

        with (
            patch.object(hid_transport, "raw_endpoints", return_value=[_entry()]),
            patch.object(hid_transport, "_open", side_effect=AssertionError("must not open")),
        ):
            info = hid_transport.list_devices()[0]

        for field in ("version", "pages", "product_id", "is_keyboard"):
            with self.subTest(field=field):
                self.assertTrue(hasattr(info, field))
