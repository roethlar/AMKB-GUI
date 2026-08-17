"""Definition-backed VIA hub spoke through fake raw HID."""

from __future__ import annotations

import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from am_configurator import hid_transport, hub_via, via_transport, vial_keymap
from am_configurator.server import create_server


class FakeViaState:
    def __init__(self, *, protocol: int = 9, layout_options: int = 1) -> None:
        self.protocol = protocol
        self.layout_options = layout_options
        self.layer_count = 4
        values = range(self.layer_count * 2 * 3)
        self.keymap = bytearray(
            b"".join(value.to_bytes(2, "big") for value in values)
        )
        self.macro_count = 2
        self.macro_buffer = bytearray(
            bytes([1, 4, 0, 0]).ljust(12, b"\x00")
        )
        self.keycodes_version = bytes.fromhex("00000008")
        self.keymap_bytes_written = 0
        self.macro_bytes_written = 0
        self.corrupt_keymap_readback = False
        self.fail_after_keymap_bytes: int | None = None

    def answer(self, packet: bytes) -> bytes:
        command = packet[0]
        if command == vial_keymap.VIA_GET_PROTOCOL_VERSION:
            return bytes([command]) + self.protocol.to_bytes(2, "big")
        if command == vial_keymap.VIA_GET_KEYBOARD_VALUE:
            value = packet[1]
            if value == vial_keymap.VIA_LAYOUT_OPTIONS:
                return packet[:2] + self.layout_options.to_bytes(4, "big")
            if value == vial_keymap.VIA_KEYCODES_VERSION:
                return packet[:2] + self.keycodes_version
            raise AssertionError(f"unexpected VIA keyboard value 0x{value:02X}")
        if command == vial_keymap.VIA_GET_KEYCODE:
            layer, row, col = packet[1:4]
            offset = ((layer * 2 * 3) + (row * 3) + col) * 2
            value = bytes(self.keymap[offset : offset + 2])
            if self.corrupt_keymap_readback and self.keymap_bytes_written:
                value = bytes([value[0] ^ 0xFF, value[1]])
            return packet[:4] + value
        if command == 0x05:
            layer, row, col = packet[1:4]
            offset = ((layer * 2 * 3) + (row * 3) + col) * 2
            self.keymap[offset : offset + 2] = packet[4:6]
            self.keymap_bytes_written += 2
            if (
                self.fail_after_keymap_bytes is not None
                and self.keymap_bytes_written >= self.fail_after_keymap_bytes
            ):
                raise OSError("fake lost keymap setter reply")
            return packet[:4]
        if command == vial_keymap.VIA_GET_LAYER_COUNT:
            return bytes([command, self.layer_count])
        if command == vial_keymap.VIA_GET_BUFFER:
            offset = int.from_bytes(packet[1:3], "big")
            size = packet[3]
            value = bytes(self.keymap[offset : offset + size])
            if self.corrupt_keymap_readback and self.keymap_bytes_written and value:
                value = bytes([value[0] ^ 0xFF]) + value[1:]
            return packet[:4] + value
        if command == vial_keymap.VIA_SET_BUFFER:
            offset = int.from_bytes(packet[1:3], "big")
            size = packet[3]
            self.keymap[offset : offset + size] = packet[4 : 4 + size]
            self.keymap_bytes_written += size
            if (
                self.fail_after_keymap_bytes is not None
                and self.keymap_bytes_written >= self.fail_after_keymap_bytes
            ):
                raise OSError("fake lost keymap setter reply")
            return packet[:4]
        if command == 0x0C:
            return bytes([command, self.macro_count])
        if command == 0x0D:
            return bytes([command]) + len(self.macro_buffer).to_bytes(2, "big")
        if command == 0x0E:
            offset = int.from_bytes(packet[1:3], "big")
            size = packet[3]
            return packet[:4] + bytes(self.macro_buffer[offset : offset + size])
        if command == 0x0F:
            offset = int.from_bytes(packet[1:3], "big")
            size = packet[3]
            self.macro_buffer[offset : offset + size] = packet[4 : 4 + size]
            self.macro_bytes_written += size
            return packet[:4]
        raise AssertionError(f"unexpected VIA command 0x{command:02X}")


class FakeHandle:
    def __init__(self, backend: "FakeHid") -> None:
        self.backend = backend
        self.path: bytes | None = None
        self.reply = b""

    def open_path(self, path: bytes) -> None:
        if path not in self.backend.states:
            raise OSError("open failed")
        self.path = path

    def write(self, data: bytes) -> int:
        if self.path is None:
            raise OSError("not open")
        packet = bytes(data[1:])
        self.backend.commands.append((self.path, packet))
        self.reply = self.backend.states[self.path].answer(packet)
        return len(data)

    def read(self, length: int, timeout_ms: int = 0) -> bytes:
        reply, self.reply = self.reply, b""
        return list(reply.ljust(length, b"\x00"))

    def close(self) -> None:
        self.path = None


class FakeHid:
    def __init__(self, entries: list[dict], states: dict[bytes, FakeViaState]) -> None:
        self.entries = entries
        self.states = states
        self.commands: list[tuple[bytes, bytes]] = []

    def enumerate(self, vendor_id: int = 0, product_id: int = 0) -> list[dict]:
        return [
            copy.deepcopy(entry)
            for entry in self.entries
            if (not vendor_id or entry["vendor_id"] == vendor_id)
            and (not product_id or entry["product_id"] == product_id)
        ]

    def device(self) -> FakeHandle:
        return FakeHandle(self)


def _entry(path: bytes, *, serial: str = "fixture-via") -> dict:
    return {
        "path": path,
        "vendor_id": 0xCAFE,
        "product_id": 0xBEEF,
        "serial_number": serial,
        "product_string": "Fixture VIA USB",
        "manufacturer_string": "Fixture Works",
        "usage_page": hid_transport.RAW_USAGE_PAGE,
        "usage": hid_transport.RAW_USAGE,
        "interface_number": 1,
    }


FIXTURE = Path(__file__).with_name("fixtures") / "via" / "minimal_definition.json"


class ViaDefinitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _snapshot_value(self, **changes):
        value = {
            "definition": self.definition,
            "via_protocol": 9,
            "keycode_spec": None,
            "usb_vendor_id": 0xCAFE,
            "usb_product_id": 0xBEEF,
            "layout_options": 1,
            "layer_count": 4,
            "keymap_hex": b"".join(
                value.to_bytes(2, "big") for value in range(24)
            ).hex(),
            "macro_count": 2,
            "macro_buffer_bytes": 12,
            "macro_hex": bytes([1, 4, 0, 0]).ljust(12, b"\x00").hex(),
        }
        value.update(changes)
        return value

    def test_active_layout_option_selects_one_physical_variant(self) -> None:
        option_zero = hub_via.load_snapshot(self._snapshot_value(layout_options=0))
        option_one = hub_via.load_snapshot(self._snapshot_value(layout_options=1))

        self.assertEqual(6, len(option_zero.key_layout))
        self.assertEqual(6, len(option_one.key_layout))
        zero_key = next(
            key for key in option_zero.key_layout
            if (key["matrix_row"], key["matrix_col"]) == (0, 2)
        )
        one_key = next(
            key for key in option_one.key_layout
            if (key["matrix_row"], key["matrix_col"]) == (0, 2)
        )
        self.assertNotEqual((zero_key["x"], zero_key["y"]), (one_key["x"], one_key["y"]))

    def test_definition_and_snapshot_bounds_fail_closed(self) -> None:
        bad_id = copy.deepcopy(self.definition)
        bad_id["productId"] = "not-hex"
        with self.assertRaisesRegex(hub_via.ViaSpokeError, "productId"):
            hub_via.load_definition(bad_id)

        too_large = copy.deepcopy(self.definition)
        too_large["matrix"]["cols"] = 1000
        with self.assertRaisesRegex(hub_via.ViaSpokeError, "columns"):
            hub_via.load_definition(too_large)

        with self.assertRaisesRegex(hub_via.ViaSpokeError, "keymap buffer"):
            hub_via.load_snapshot(self._snapshot_value(keymap_hex="0000"))

    def test_via_macro_delay_dialect_is_protocol_gated(self) -> None:
        delayed = bytes([1, 4]) + b"250|" + b"\x00"
        self.assertEqual(
            [{"slot": 0, "events": [{"delay_ms": 250}]}],
            hub_via.decode_macro_buffer(delayed, count=1, via_protocol=11),
        )
        self.assertEqual(
            [
                {
                    "slot": 0,
                    "events": [{"tap": 4}, {"text": "250|"}],
                }
            ],
            hub_via.decode_macro_buffer(delayed, count=1, via_protocol=9),
        )

    def test_snapshot_builds_complete_via_hub_profile(self) -> None:
        snapshot = hub_via.load_snapshot(self._snapshot_value())
        profile = hub_via.build_hub_profile(snapshot)

        self.assertEqual("via", profile["identity"]["ecosystem"])
        self.assertEqual("user_import", profile["identity"]["definition"]["source"])
        self.assertEqual(6, len(profile["keymap"]["layers"][0]["keys"]))
        self.assertEqual([{"tap": 4}], profile["macros"][0]["events"])
        self.assertFalse(profile["capabilities"]["macros"]["delays"])

    def test_write_plan_updates_addressed_key_and_preserves_omitted_macros(
        self,
    ) -> None:
        snapshot = hub_via.load_snapshot(self._snapshot_value())
        profile = hub_via.build_hub_profile(snapshot)
        profile["keymap"]["layers"] = [
            {
                "index": 0,
                "keys": [
                    {"key": "K_R0_C0", "code": 0x1234},
                    {"key": "K_R9_C9", "code": 0x0004},
                ],
            },
            {
                "index": 4,
                "keys": [{"key": "K_R0_C0", "code": 0x0005}],
            },
        ]
        profile.pop("macros")
        profile["provenance"].pop("/macros")
        unchanged = copy.deepcopy(profile)

        plan = hub_via.plan_via_write(profile, target=snapshot)

        self.assertEqual(unchanged, profile)
        expected = bytearray(snapshot.keymap_buffer)
        expected[:2] = (0x1234).to_bytes(2, "big")
        self.assertEqual(bytes(expected), plan.keymap_buffer)
        self.assertIsNone(plan.macro_buffer)
        self.assertEqual(
            [
                {
                    "path": "keymap.layers[0].keys[K_R0_C0]",
                    "verdict": "carried",
                },
                {
                    "path": "keymap.layers[0].keys[K_R9_C9]",
                    "verdict": "dropped",
                    "reason": (
                        "this VIA keyboard has no matrix address for that key; "
                        "H4 overlay must assign one."
                    ),
                },
                {
                    "path": "keymap.layers[4].keys[K_R0_C0]",
                    "verdict": "dropped",
                    "reason": "this VIA keyboard only stores 4 layers.",
                },
            ],
            plan.report["items"],
        )
        self.assertEqual(plan, hub_via.plan_via_write(profile, target=snapshot))

    def test_via_macro_encoder_round_trips_protocol_9_and_11(self) -> None:
        protocol_9 = [{"tap": 4}, {"text": "250|"}]
        encoded_9 = hub_via.encode_macro_buffer(
            [{"slot": 0, "events": protocol_9}],
            count=1,
            buffer_bytes=12,
            via_protocol=9,
        )
        self.assertEqual(
            [{"slot": 0, "events": protocol_9}],
            hub_via.decode_macro_buffer(encoded_9, count=1, via_protocol=9),
        )

        protocol_11 = [
            {"tap": 4},
            {"delay_ms": 250},
            {"text": "ok"},
        ]
        encoded_11 = hub_via.encode_macro_buffer(
            [{"slot": 0, "events": protocol_11}],
            count=1,
            buffer_bytes=16,
            via_protocol=11,
        )
        self.assertEqual(
            [{"slot": 0, "events": protocol_11}],
            hub_via.decode_macro_buffer(encoded_11, count=1, via_protocol=11),
        )
        with self.assertRaisesRegex(hub_via.ViaSpokeError, "reserved"):
            hub_via.encode_macro_events([{"text": "\x01"}], via_protocol=9)
        with self.assertRaisesRegex(hub_via.ViaSpokeError, "valid UTF-8"):
            hub_via.encode_macro_events([{"text": "\ud800"}], via_protocol=11)

    def test_snapshot_profile_plans_back_byte_identically(self) -> None:
        snapshot = hub_via.load_snapshot(self._snapshot_value())

        plan = hub_via.plan_via_write(
            hub_via.build_hub_profile(snapshot), target=snapshot
        )

        self.assertEqual(snapshot.keymap_buffer, plan.keymap_buffer)
        self.assertEqual(snapshot.macro_buffer, plan.macro_buffer)
        self.assertTrue(plan.report["items"])
        self.assertEqual(
            {"carried"}, {item["verdict"] for item in plan.report["items"]}
        )

    def test_macro_plan_reports_unrepresentable_events_before_compiling(self) -> None:
        snapshot = hub_via.load_snapshot(self._snapshot_value())
        profile = hub_via.build_hub_profile(snapshot)
        profile.pop("keymap")
        profile["provenance"].pop("/keymap")
        profile["macros"] = [
            {"slot": 0, "events": [{"delay_ms": 10}]},
            {"slot": 1, "events": [{"tap": 0x1234}]},
            {"slot": 2, "events": [{"tap": 4}]},
        ]

        plan = hub_via.plan_via_write(profile, target=snapshot)

        self.assertIsNone(plan.keymap_buffer)
        self.assertEqual(bytes(12), plan.macro_buffer)
        self.assertEqual(
            ["dropped", "dropped", "dropped"],
            [item["verdict"] for item in plan.report["items"]],
        )
        with self.assertRaisesRegex(hub_via.ViaSpokeError, "compile"):
            hub_via.encode_macro_buffer(
                [{"slot": 0, "events": [{"text": "hello"}]}],
                count=1,
                buffer_bytes=4,
                via_protocol=11,
            )

    def test_keycode_spec_mismatch_preserves_target_and_reports_drop(self) -> None:
        macro = bytes([1, 1, 4, 0, 0]).ljust(12, b"\x00")
        snapshot = hub_via.load_snapshot(
            self._snapshot_value(
                via_protocol=13,
                keycode_spec="0.0.8",
                macro_hex=macro.hex(),
            )
        )
        profile = hub_via.build_hub_profile(snapshot)
        profile["identity"]["protocol"]["keycode_spec"] = "0.0.7"
        profile["keymap"]["layers"] = [
            {"index": 0, "keys": [{"key": "K_R0_C0", "code": 0x1234}]}
        ]
        profile.pop("macros")
        profile["provenance"].pop("/macros")

        plan = hub_via.plan_via_write(profile, target=snapshot)

        self.assertEqual(snapshot.keymap_buffer, plan.keymap_buffer)
        self.assertEqual("dropped", plan.report["items"][0]["verdict"])
        self.assertIn("keycode spec", plan.report["items"][0]["reason"])

    def test_protocol_7_has_no_macro_write_plan(self) -> None:
        target = hub_via.load_snapshot(
            self._snapshot_value(
                via_protocol=7,
                macro_count=0,
                macro_buffer_bytes=0,
                macro_hex="",
            )
        )
        source = hub_via.build_hub_profile(
            hub_via.load_snapshot(self._snapshot_value())
        )
        source.pop("keymap")
        source["provenance"].pop("/keymap")

        plan = hub_via.plan_via_write(source, target=target)

        self.assertIsNone(plan.keymap_buffer)
        self.assertIsNone(plan.macro_buffer)
        self.assertEqual("dropped", plan.report["items"][0]["verdict"])


class GenericViaTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.path = b"via-device-a"
        self.other_path = b"via-device-b"
        self.state = FakeViaState()
        self.backend = FakeHid(
            [
                _entry(self.path),
                _entry(self.other_path),
                _entry(b"vial-board", serial="vial:f64c2b3c"),
                {**_entry(b"keyboard-interface"), "usage_page": 0x01, "usage": 0x06},
            ],
            {
                self.path: self.state,
                self.other_path: FakeViaState(layout_options=0),
                b"vial-board": FakeViaState(),
            },
        )
        self.hid_patch = mock.patch(
            "am_configurator.hid_transport._hid", return_value=self.backend
        )
        self.hid_patch.start()
        self.addCleanup(self.hid_patch.stop)
        self.address = hid_transport.endpoint_address(self.path)

    @staticmethod
    def _setters(commands: list[tuple[bytes, bytes]]) -> set[int]:
        return {packet[0] for _path, packet in commands} & {0x05, 0x0F, 0x13}

    def _prepared(self):
        snapshot = via_transport.read_snapshot(self.address, self.definition)
        profile = hub_via.build_hub_profile(snapshot)
        profile["keymap"]["layers"][0]["keys"][0]["code"] = 0x0005
        return via_transport.prepare_write(
            self.address, self.definition, profile
        )

    def test_discovery_is_shallow_and_keeps_same_model_endpoints_distinct(self) -> None:
        devices = via_transport.list_devices()
        self.assertEqual(2, len(devices))
        self.assertNotEqual(devices[0].address, devices[1].address)
        self.assertEqual([], self.backend.commands)

    def test_complete_snapshot_uses_only_allowlisted_reads(self) -> None:
        snapshot = via_transport.read_snapshot(self.address, self.definition)
        profile = hub_via.build_hub_profile(snapshot)

        self.assertEqual(9, snapshot.via_protocol)
        self.assertEqual(1, snapshot.layout_options)
        self.assertEqual(self.state.keymap, snapshot.keymap_buffer)
        self.assertEqual(self.state.macro_buffer, snapshot.macro_buffer)
        self.assertEqual("via", profile["identity"]["ecosystem"])
        commands = {packet[0] for _path, packet in self.backend.commands}
        self.assertTrue({0x01, 0x02, 0x0C, 0x0D, 0x0E, 0x11, 0x12} <= commands)
        self.assertFalse(commands & {0x03, 0x05, 0x0F, 0x13})

    def test_editor_document_comes_from_one_read_only_snapshot(self) -> None:
        document = via_transport.read_hub_document(self.address, self.definition)

        self.assertEqual(self.address, document.device["address"])
        self.assertTrue(document.device["definition_required"])
        self.assertEqual("Fixture VIA Pad", document.profile["identity"]["family"])
        self.assertEqual("K_R0_C0", document.layout[0]["key"])
        self.assertEqual(0, document.layout[0]["matrix_row"])
        self.assertEqual(0, document.layout[0]["matrix_col"])
        self.assertEqual(set(), self._setters(self.backend.commands))

    def test_wrong_definition_is_refused_before_opening(self) -> None:
        wrong = copy.deepcopy(self.definition)
        wrong["productId"] = "0x0001"
        with self.assertRaisesRegex(hid_transport.HidIdentityError, "VID/PID"):
            via_transport.read_snapshot(self.address, wrong)
        self.assertEqual([], self.backend.commands)

    def test_read_session_refuses_a_set_command_before_transmission(self) -> None:
        endpoint = hid_transport.find_via_endpoint(self.address)
        session = hid_transport.open_via_read(endpoint)
        self.backend.commands.clear()
        try:
            with self.assertRaises(hid_transport.HidError):
                session.send(bytes([vial_keymap.VIA_SET_BUFFER, 0, 0, 1, 0]))
        finally:
            session.close()
        self.assertEqual([], self.backend.commands)

    def test_preflight_plans_without_sending_a_setter(self) -> None:
        prepared = self._prepared()

        self.assertEqual("VIA Fixture VIA Pad CAFE:BEEF", prepared.confirmation)
        self.assertEqual(
            prepared.definition.definition_hash, prepared.target.definition_hash
        )
        self.assertEqual(set(), self._setters(self.backend.commands))

    def test_forged_via_write_approval_is_refused_without_opening(self) -> None:
        forged = hid_transport.ViaWriteApproval(
            address=self.address,
            path=self.path,
            definition_name="Fixture VIA Pad",
            definition_hash="sha256-forged",
            confirmation="VIA Fixture VIA Pad CAFE:BEEF",
            expected_confirmation="VIA Fixture VIA Pad CAFE:BEEF",
            usb_vendor_id=0xCAFE,
            usb_product_id=0xBEEF,
            serial_number="fixture-via",
            product_string="Fixture VIA USB",
            manufacturer_string="Fixture Works",
            interface_number=1,
        )
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidIdentityError):
            hid_transport.open_via_approved(forged)

        self.assertEqual([], self.backend.commands)

    def test_wrong_confirmation_stops_before_reopening_endpoint(self) -> None:
        prepared = self._prepared()
        self.backend.commands.clear()

        with self.assertRaisesRegex(hid_transport.HidIdentityError, "Type VIA"):
            via_transport.execute_write(
                prepared, confirmation="Fixture VIA Pad"
            )

        self.assertEqual([], self.backend.commands)

    def test_changed_usb_metadata_stops_before_opening_endpoint(self) -> None:
        prepared = self._prepared()
        self.backend.entries[0]["product_string"] = "Impostor VIA USB"
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidIdentityError):
            via_transport.execute_write(
                prepared, confirmation=prepared.confirmation
            )

        self.assertEqual([], self.backend.commands)

    def test_changed_imported_definition_hash_stops_before_opening(self) -> None:
        prepared = self._prepared()
        changed = copy.deepcopy(self.definition)
        changed["customKeycodes"] = []
        forged = replace(
            prepared, definition=hub_via.load_definition(changed)
        )
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidIdentityError):
            via_transport.execute_write(
                forged, confirmation=forged.confirmation
            )

        self.assertEqual([], self.backend.commands)

    def test_replug_invalidates_prepared_endpoint_before_opening(self) -> None:
        prepared = self._prepared()
        replacement = b"via-device-replugged"
        self.backend.entries[0] = _entry(replacement)
        self.backend.states[replacement] = self.state
        del self.backend.states[self.path]
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidDeviceAbsent):
            via_transport.execute_write(
                prepared, confirmation=prepared.confirmation
            )

        self.assertEqual([], self.backend.commands)

    def test_changed_protocol_shape_or_capacity_stops_before_setter(self) -> None:
        cases = (
            ("protocol", lambda state: setattr(state, "protocol", 10)),
            ("layout", lambda state: setattr(state, "layout_options", 0)),
            ("layers", lambda state: setattr(state, "layer_count", 3)),
            ("macros", lambda state: setattr(state, "macro_count", 3)),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                self.state = FakeViaState()
                self.backend.states[self.path] = self.state
                prepared = self._prepared()
                mutate(self.state)
                self.backend.commands.clear()

                with self.assertRaises(hid_transport.HidIdentityError):
                    via_transport.execute_write(
                        prepared, confirmation=prepared.confirmation
                    )

                self.assertEqual(set(), self._setters(self.backend.commands))

    def test_changed_protocol_13_keycode_spec_stops_before_setter(self) -> None:
        self.state = FakeViaState(protocol=13)
        self.state.macro_buffer = bytearray(
            bytes([1, 1, 4, 0, 0]).ljust(12, b"\x00")
        )
        self.backend.states[self.path] = self.state
        prepared = self._prepared()
        self.state.keycodes_version = bytes.fromhex("00000007")
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidIdentityError):
            via_transport.execute_write(
                prepared, confirmation=prepared.confirmation
            )

        self.assertEqual(set(), self._setters(self.backend.commands))

    def test_approved_session_refuses_every_unplanned_mutation(self) -> None:
        prepared = self._prepared()
        endpoint = hid_transport.find_via_endpoint(self.address)
        approval = hid_transport.approve_via_write(
            endpoint,
            definition_name=prepared.definition.name,
            definition_hash=prepared.definition.definition_hash,
            confirmation=prepared.confirmation,
        )
        session = hid_transport.open_via_approved(approval)
        self.backend.commands.clear()
        try:
            for command in (0x03, 0x0A, 0x0B, 0x10, 0x15, 0x99):
                with self.subTest(command=command):
                    with self.assertRaises(hid_transport.HidError):
                        session.send(bytes([command]))
        finally:
            session.close()
        self.assertEqual([], self.backend.commands)

    def test_protocol_9_write_uses_exact_plan_and_readback(self) -> None:
        prepared = self._prepared()
        self.backend.commands.clear()

        receipt = via_transport.execute_write(
            prepared, confirmation=prepared.confirmation
        )

        self.assertEqual(prepared.plan.keymap_buffer, bytes(self.state.keymap))
        self.assertEqual(
            prepared.plan.macro_buffer, bytes(self.state.macro_buffer)
        )
        self.assertEqual(len(prepared.plan.keymap_buffer or b""), receipt.keymap_bytes)
        self.assertEqual(len(prepared.plan.macro_buffer or b""), receipt.macro_bytes)
        self.assertEqual(prepared.plan.report, receipt.report)
        commands = {packet[0] for _path, packet in self.backend.commands}
        self.assertTrue({0x0F, 0x13} <= commands)
        self.assertNotIn(0x05, commands)

    def test_omitted_keymap_never_sends_a_keymap_setter(self) -> None:
        snapshot = via_transport.read_snapshot(self.address, self.definition)
        profile = hub_via.build_hub_profile(snapshot)
        profile.pop("keymap")
        profile["provenance"].pop("/keymap")
        profile["macros"][0]["events"] = [{"tap": 5}]
        prepared = via_transport.prepare_write(
            self.address, self.definition, profile
        )
        self.backend.commands.clear()

        receipt = via_transport.execute_write(
            prepared, confirmation=prepared.confirmation
        )

        self.assertEqual(0, receipt.keymap_bytes)
        self.assertEqual(12, receipt.macro_bytes)
        commands = {packet[0] for _path, packet in self.backend.commands}
        self.assertIn(0x0F, commands)
        self.assertFalse(commands & {0x05, 0x13})

    def test_protocol_7_write_uses_per_key_setters_only(self) -> None:
        self.state.protocol = 7
        prepared = self._prepared()
        self.backend.commands.clear()

        receipt = via_transport.execute_write(
            prepared, confirmation=prepared.confirmation
        )

        self.assertEqual(prepared.plan.keymap_buffer, bytes(self.state.keymap))
        self.assertEqual(len(prepared.plan.keymap_buffer or b""), receipt.keymap_bytes)
        commands = {packet[0] for _path, packet in self.backend.commands}
        self.assertIn(0x05, commands)
        self.assertFalse(commands & {0x0F, 0x13})

    def test_readback_mismatch_reports_accepted_write(self) -> None:
        prepared = self._prepared()
        self.state.corrupt_keymap_readback = True
        self.backend.commands.clear()

        with self.assertRaises(via_transport.ViaAcceptedWriteError) as caught:
            via_transport.execute_write(
                prepared, confirmation=prepared.confirmation
            )

        self.assertGreater(caught.exception.keymap_bytes, 0)
        self.assertTrue(self._setters(self.backend.commands))

    def test_lost_first_setter_reply_reports_possible_accepted_bytes(self) -> None:
        prepared = self._prepared()
        self.state.fail_after_keymap_bytes = 28
        self.backend.commands.clear()

        with self.assertRaises(via_transport.ViaAcceptedWriteError) as caught:
            via_transport.execute_write(
                prepared, confirmation=prepared.confirmation
            )

        self.assertEqual(28, caught.exception.keymap_bytes)
        self.assertEqual(0, caught.exception.macro_bytes)

    def test_protocol_seven_uses_per_key_reads_without_macro_probes(self) -> None:
        self.state.protocol = 7
        snapshot = via_transport.read_snapshot(self.address, self.definition)

        self.assertEqual(4, snapshot.layer_count)
        self.assertEqual(0, snapshot.macro_count)
        commands = [packet[0] for _path, packet in self.backend.commands]
        self.assertIn(vial_keymap.VIA_GET_KEYCODE, commands)
        self.assertNotIn(vial_keymap.VIA_GET_BUFFER, commands)
        self.assertFalse(set(commands) & {0x0C, 0x0D, 0x0E})

    def test_protocol_thirteen_reads_and_formats_keycode_spec(self) -> None:
        self.state.protocol = 13
        self.state.macro_buffer = bytes([1, 1, 4, 0, 0]).ljust(12, b"\x00")
        snapshot = via_transport.read_snapshot(self.address, self.definition)
        profile = hub_via.build_hub_profile(snapshot)
        self.assertEqual("0.0.8", snapshot.keycode_spec)
        self.assertEqual("0.0.8", profile["identity"]["protocol"]["keycode_spec"])

    def test_local_api_lists_candidates_and_reads_with_imported_definition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openkeeb_via_api_") as data_dir:
            with mock.patch.dict(os.environ, {"AM_CONFIGURATOR_DATA_DIR": data_dir}):
                server, url = create_server()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            parsed = urlparse(url)
            token = parse_qs(parsed.query)["token"][0]
            base = f"http://127.0.0.1:{server.server_port}"

            def request(method: str, path: str, body: dict | None = None):
                data = None if body is None else json.dumps(body).encode("utf-8")
                headers = {"X-AM-Token": token}
                if data is not None:
                    headers["Content-Type"] = "application/json"
                call = Request(base + path, data=data, method=method, headers=headers)
                try:
                    with urlopen(call, timeout=5) as response:
                        return response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    return error.code, json.loads(error.read())

            try:
                status, listed = request("GET", "/api/hub/via/devices")
                self.assertEqual(200, status)
                self.assertEqual(2, len(listed["devices"]))
                status, read = request(
                    "POST",
                    "/api/hub/via/read",
                    {"address": self.address, "definition": self.definition},
                )
                self.assertEqual(200, status)
                self.assertEqual("Fixture VIA Pad", read["profile"]["identity"]["family"])
                self.assertEqual(self.address, read["device"]["address"])
                self.assertTrue(read["device"]["definition_required"])
                self.assertEqual("K_R0_C0", read["layout"][0]["key"])
                self.assertEqual(0, read["layout"][0]["matrix_row"])
                self.assertEqual(0, read["layout"][0]["matrix_col"])

                self.backend.commands.clear()
                status, missing_definition = request(
                    "POST", "/api/hub/via/read", {"address": self.address}
                )
                self.assertEqual(400, status)
                self.assertIn("unsupported fields", missing_definition["error"])
                self.assertEqual([], self.backend.commands)

                status, preflight = request(
                    "POST",
                    "/api/hub/via/preflight",
                    {
                        "address": self.address,
                        "definition": self.definition,
                        "profile": read["profile"],
                    },
                )
                self.assertEqual(200, status)
                self.assertEqual(
                    "VIA Fixture VIA Pad CAFE:BEEF",
                    preflight["confirmation"],
                )
                self.assertEqual(48, preflight["keymap_bytes"])

                self.backend.commands.clear()
                status, refused = request(
                    "POST",
                    "/api/hub/via/write",
                    {
                        "address": self.address,
                        "definition": self.definition,
                        "profile": read["profile"],
                        "confirmation": "Fixture VIA Pad",
                    },
                )
                self.assertEqual(400, status)
                self.assertIn("Type VIA Fixture VIA Pad", refused["error"])
                self.assertEqual(set(), self._setters(self.backend.commands))

                self.state.corrupt_keymap_readback = True
                self.backend.commands.clear()
                status, accepted_error = request(
                    "POST",
                    "/api/hub/via/write",
                    {
                        "address": self.address,
                        "definition": self.definition,
                        "profile": read["profile"],
                        "confirmation": preflight["confirmation"],
                    },
                )
                self.assertEqual(409, status)
                self.assertTrue(accepted_error["accepted"])
                self.assertEqual(48, accepted_error["keymap_bytes"])
                self.assertEqual(12, accepted_error["macro_bytes"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
