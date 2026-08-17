"""Live-bound generic Vial transport, exercised through a fake HID device."""

from __future__ import annotations

import copy
import json
import lzma
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from am_configurator import (
    hid_transport,
    hub_vial,
    vial_keymap,
    vial_lighting,
    vial_transport,
)
from am_configurator.server import create_server


FIXTURE = Path(__file__).with_name("fixtures") / "vial" / "minimal_snapshot.json"


class FakeVialState:
    """Mutable device buffers shared by every fake handle opened for one path."""

    def __init__(self, record: dict) -> None:
        self.definition = copy.deepcopy(record["definition"])
        self.via_protocol = int(record["via_protocol"])
        self.vial_protocol = int(record["vial_protocol"])
        self.firmware_uid = bytes.fromhex(record["firmware_uid"])
        self.feature_flags = 0
        self.layer_count = int(record["layer_count"])
        self.keymap = bytearray.fromhex(record["keymap_hex"])
        self.macro_count = int(record["macro_count"])
        self.macro_buffer = bytearray.fromhex(record["macro_hex"])
        self.unlocked = False
        self.unlock_in_progress = False
        self.unlock_after_poll = True
        self.vialrgb_effects = (0, 1, 7)
        self.vialrgb_protocol = 1
        self.vialrgb_maximum_brightness = 128
        self.vialrgb_mode = (7, 31, 11, 22, 99)
        self.vialrgb_leds = (
            (10, 20, 4, 0, 1),
            (30, 40, 2, 0xFF, 0xFF),
        )
        self.legacy_lighting_values = {
            vial_lighting.QMK_BACKLIGHT_BRIGHTNESS: bytes([101]),
            vial_lighting.QMK_BACKLIGHT_EFFECT: bytes([7]),
            vial_lighting.QMK_RGBLIGHT_BRIGHTNESS: bytes([200]),
            vial_lighting.QMK_RGBLIGHT_EFFECT: bytes([9]),
            vial_lighting.QMK_RGBLIGHT_EFFECT_SPEED: bytes([55]),
            vial_lighting.QMK_RGBLIGHT_COLOR: bytes([33, 44]),
        }
        self.lighting_sets = 0
        self.lighting_saves = 0
        self.fail_lighting_set_number: int | None = None
        self.fail_lighting_save = False
        self.ignore_lighting_sets = False

    @property
    def definition_blob(self) -> bytes:
        return lzma.compress(
            json.dumps(self.definition, separators=(",", ":")).encode("utf-8")
        )

    def answer(self, packet: bytes) -> bytes:
        command = packet[0]
        if command == 0xFE:
            subcommand = packet[1]
            if subcommand == 0x00:
                return (
                    self.vial_protocol.to_bytes(4, "little")
                    + self.firmware_uid
                    + bytes([self.feature_flags])
                )
            if subcommand == 0x01:
                return len(self.definition_blob).to_bytes(4, "little")
            if subcommand == 0x02:
                block = packet[2] | (packet[3] << 8)
                return self.definition_blob[block * 32 : (block + 1) * 32]
            if subcommand == 0x05:
                return bytes(
                    [int(self.unlocked), int(self.unlock_in_progress), 0, 0, 0, 2, 0xFF, 0xFF]
                )
            if subcommand == 0x06:
                self.unlock_in_progress = True
                return b""
            if subcommand == 0x07:
                if self.unlock_after_poll:
                    self.unlocked = True
                self.unlock_in_progress = False
                return bytes([int(self.unlocked), 0])
            raise AssertionError(f"unexpected Vial subcommand 0x{subcommand:02X}")

        if command == vial_lighting.CMD_LIGHTING_GET_VALUE:
            value_id = packet[1]
            if value_id in self.legacy_lighting_values:
                return packet[:2] + self.legacy_lighting_values[value_id]
            if value_id == vial_lighting.VIALRGB_GET_INFO:
                return (
                    packet[:2]
                    + self.vialrgb_protocol.to_bytes(2, "little")
                    + bytes([self.vialrgb_maximum_brightness])
                )
            if value_id == vial_lighting.VIALRGB_GET_SUPPORTED:
                lower = int.from_bytes(packet[2:4], "little")
                remaining = [effect for effect in self.vialrgb_effects if effect >= lower]
                payload = b"".join(effect.to_bytes(2, "little") for effect in remaining)
                return packet[:2] + payload + b"\xff\xff"
            if value_id == vial_lighting.VIALRGB_GET_MODE:
                effect, speed, hue, saturation, value = self.vialrgb_mode
                return (
                    packet[:2]
                    + effect.to_bytes(2, "little")
                    + bytes([speed, hue, saturation, value])
                )
            if value_id == vial_lighting.VIALRGB_GET_NUMBER_LEDS:
                return packet[:2] + len(self.vialrgb_leds).to_bytes(2, "little")
            if value_id == vial_lighting.VIALRGB_GET_LED_INFO:
                index = int.from_bytes(packet[2:4], "little")
                return packet[:2] + bytes(self.vialrgb_leds[index])
            raise AssertionError(f"unexpected lighting GET 0x{value_id:02X}")
        if command == vial_lighting.CMD_LIGHTING_SET_VALUE:
            value_id = packet[1]
            if not self.ignore_lighting_sets:
                if value_id == vial_lighting.VIALRGB_SET_MODE:
                    effect = int.from_bytes(packet[2:4], "little")
                    self.vialrgb_mode = (effect, *packet[4:8])
                elif value_id == vial_lighting.QMK_RGBLIGHT_COLOR:
                    self.legacy_lighting_values[value_id] = packet[2:4]
                elif value_id in self.legacy_lighting_values:
                    self.legacy_lighting_values[value_id] = packet[2:3]
                else:
                    raise AssertionError(f"unexpected lighting SET 0x{value_id:02X}")
            self.lighting_sets += 1
            if self.fail_lighting_set_number == self.lighting_sets:
                raise OSError("fake lost lighting setter reply")
            return packet[:2]
        if command == vial_lighting.CMD_LIGHTING_SAVE:
            self.lighting_saves += 1
            if self.fail_lighting_save:
                raise OSError("fake lost lighting save reply")
            return packet[:1]

        if command == 0x01:
            return bytes([command]) + self.via_protocol.to_bytes(2, "big")
        if command == vial_keymap.VIA_GET_LAYER_COUNT:
            return bytes([command, self.layer_count])
        if command == vial_keymap.VIA_GET_BUFFER:
            offset = (packet[1] << 8) | packet[2]
            size = packet[3]
            return packet[:4] + self.keymap[offset : offset + size]
        if command == vial_keymap.VIA_SET_BUFFER:
            offset = (packet[1] << 8) | packet[2]
            size = packet[3]
            self.keymap[offset : offset + size] = packet[4 : 4 + size]
            return packet[:4]
        if command == 0x0C:
            return bytes([command, self.macro_count])
        if command == 0x0D:
            return bytes([command]) + len(self.macro_buffer).to_bytes(2, "big")
        if command == 0x0E:
            offset = (packet[1] << 8) | packet[2]
            size = packet[3]
            return packet[:4] + self.macro_buffer[offset : offset + size]
        if command == 0x0F:
            offset = (packet[1] << 8) | packet[2]
            size = packet[3]
            self.macro_buffer[offset : offset + size] = packet[4 : 4 + size]
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
        return reply.ljust(length, b"\x00")

    def close(self) -> None:
        self.path = None


class FakeHid:
    def __init__(self, entries: list[dict], states: dict[bytes, FakeVialState]) -> None:
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


def _entry(path: bytes, *, serial: str = "vial:f64c2b3c") -> dict:
    return {
        "path": path,
        "vendor_id": 0xCAFE,
        "product_id": 0xBEEF,
        "serial_number": serial,
        "product_string": "Fixture Pad USB",
        "manufacturer_string": "Fixture Works",
        "usage_page": hid_transport.RAW_USAGE_PAGE,
        "usage": hid_transport.RAW_USAGE,
    }


class GenericVialTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.path = b"vial-device-a"
        self.other_path = b"vial-device-b"
        self.state = FakeVialState(self.record)
        self.other_state = FakeVialState(self.record)
        self.backend = FakeHid(
            [
                _entry(self.path),
                _entry(self.other_path),
                _entry(b"not-vial", serial="ordinary:serial"),
                {
                    **_entry(b"keyboard-interface"),
                    "usage_page": 0x01,
                    "usage": 0x06,
                },
            ],
            {self.path: self.state, self.other_path: self.other_state},
        )
        self.hid_patch = mock.patch(
            "am_configurator.hid_transport._hid", return_value=self.backend
        )
        self.hid_patch.start()
        self.addCleanup(self.hid_patch.stop)
        self.address = hid_transport.endpoint_address(self.path)

    @staticmethod
    def _operation(packet: bytes) -> tuple[int, int | None]:
        return packet[0], packet[1] if packet[0] == 0xFE else None

    def _prepared(self):
        snapshot = vial_transport.read_snapshot(self.address)
        profile = hub_vial.build_hub_profile(snapshot)
        profile["keymap"]["layers"][0]["keys"][0]["code"] = 0x0005
        return vial_transport.prepare_write(self.address, profile)

    def _prepared_legacy_lighting(self, **changes: int):
        self.state.definition["lighting"] = "qmk_rgblight"
        self.state.unlocked = True
        profile = vial_transport.read_hub_profile(self.address)
        profile["lighting"]["surfaces"][0].update(changes)
        return vial_transport.prepare_write(self.address, profile)

    def test_discovery_filters_non_vial_interfaces_and_keeps_two_endpoints(self) -> None:
        devices = vial_transport.list_devices()

        self.assertEqual(2, len(devices))
        self.assertNotEqual(devices[0].address, devices[1].address)
        self.assertTrue(all(device.is_vial for device in devices))
        self.assertEqual([], self.backend.commands)

    def test_read_snapshot_uses_only_read_commands(self) -> None:
        snapshot = vial_transport.read_snapshot(self.address)
        profile = hub_vial.build_hub_profile(snapshot)

        self.assertEqual("Fixture Pad", snapshot.name)
        self.assertEqual(9, snapshot.via_protocol)
        self.assertEqual(6, snapshot.vial_protocol)
        self.assertEqual(2, snapshot.layer_count)
        self.assertEqual(self.record["keymap_hex"], snapshot.keymap_buffer.hex())
        self.assertEqual(self.record["macro_hex"], snapshot.macro_buffer.hex())
        self.assertEqual("vial", profile["identity"]["ecosystem"])
        operations = {self._operation(packet) for _path, packet in self.backend.commands}
        self.assertTrue({(0xFE, 0x00), (0xFE, 0x01), (0xFE, 0x02)} <= operations)
        self.assertTrue({(0x01, None), (0x11, None), (0x12, None)} <= operations)
        self.assertTrue({(0x0C, None), (0x0D, None), (0x0E, None)} <= operations)
        self.assertFalse(
            operations
            & {(0xFE, 0x06), (0xFE, 0x07), (0x13, None), (0x0F, None)}
        )

    def test_editor_document_comes_from_one_read_only_snapshot(self) -> None:
        document = vial_transport.read_hub_document(self.address)

        self.assertEqual(self.address, document.device["address"])
        self.assertEqual("Fixture Pad", document.profile["identity"]["family"])
        self.assertEqual("K_R0_C0", document.layout[0]["key"])
        self.assertEqual(0, document.layout[0]["matrix_row"])
        self.assertEqual(0, document.layout[0]["matrix_col"])
        self.assertEqual((), document.lighting_geometry)
        operations = {
            self._operation(packet) for _path, packet in self.backend.commands
        }
        self.assertFalse(
            operations & {(0xFE, 0x06), (0xFE, 0x07), (0x13, None), (0x0F, None)}
        )

    def test_vialrgb_snapshot_preserves_flags_state_and_ephemeral_geometry(self) -> None:
        self.state.definition["lighting"] = "vialrgb"
        self.state.feature_flags = vial_lighting.VIALRGB_FEATURE_FLAG

        document = vial_transport.read_hub_document(self.address)

        self.assertEqual(
            vial_lighting.VIALRGB_FEATURE_FLAG,
            document.device["vial_feature_flags"],
        )
        self.assertEqual(
            {
                "id": "vialrgb",
                "effect_id": 7,
                "brightness": 99,
                "speed": 31,
                "color": [11, 22],
            },
            document.profile["lighting"]["surfaces"][0],
        )
        self.assertEqual(
            (
                {
                    "surface_id": "vialrgb",
                    "pixel_id": "K_R0_C1",
                    "led_index": 0,
                    "x": 3.9216,
                    "y": 7.8431,
                    "flags": 4,
                    "key": "K_R0_C1",
                },
                {
                    "surface_id": "vialrgb",
                    "pixel_id": "LED_I1",
                    "led_index": 1,
                    "x": 11.7647,
                    "y": 15.6863,
                    "flags": 2,
                },
            ),
            document.lighting_geometry,
        )
        lighting_gets = [
            packet[1]
            for _path, packet in self.backend.commands
            if packet[0] == vial_lighting.CMD_LIGHTING_GET_VALUE
        ]
        self.assertEqual(
            [
                vial_lighting.VIALRGB_GET_INFO,
                vial_lighting.VIALRGB_GET_SUPPORTED,
                vial_lighting.VIALRGB_GET_MODE,
                vial_lighting.VIALRGB_GET_NUMBER_LEDS,
                vial_lighting.VIALRGB_GET_LED_INFO,
                vial_lighting.VIALRGB_GET_LED_INFO,
            ],
            lighting_gets,
        )
        operations = {self._operation(packet) for _path, packet in self.backend.commands}
        self.assertFalse(
            {
                (vial_lighting.CMD_LIGHTING_SET_VALUE, None),
                (vial_lighting.CMD_LIGHTING_SAVE, None),
                (0xFE, vial_keymap.VIAL_UNLOCK_START),
                (0xFE, vial_keymap.VIAL_UNLOCK_POLL),
                (vial_keymap.VIA_SET_BUFFER, None),
                (0x0F, None),
            }
            & operations
        )

    def test_unknown_vial_lighting_definition_stays_explicitly_empty(self) -> None:
        self.state.definition["lighting"] = "vendor_magic"
        self.state.feature_flags = vial_lighting.VIALRGB_FEATURE_FLAG

        document = vial_transport.read_hub_document(self.address)

        self.assertEqual([], document.profile["capabilities"]["lighting"]["surfaces"])
        self.assertNotIn("lighting", document.profile)
        self.assertEqual((), document.lighting_geometry)
        self.assertFalse(
            any(
                packet[0] == vial_lighting.CMD_LIGHTING_GET_VALUE
                for _path, packet in self.backend.commands
            )
        )

    def test_vialrgb_definition_without_feature_flag_sends_no_lighting_get(self) -> None:
        self.state.definition["lighting"] = "vialrgb"

        document = vial_transport.read_hub_document(self.address)

        self.assertEqual([], document.profile["capabilities"]["lighting"]["surfaces"])
        self.assertNotIn("lighting", document.profile)
        self.assertFalse(
            any(
                packet[0] == vial_lighting.CMD_LIGHTING_GET_VALUE
                for _path, packet in self.backend.commands
            )
        )

    def test_vialrgb_led_count_is_bounded_before_led_metadata_reads(self) -> None:
        self.state.definition["lighting"] = "vialrgb"
        self.state.feature_flags = vial_lighting.VIALRGB_FEATURE_FLAG
        self.state.vialrgb_leds = ((0, 0, 0, 0xFF, 0xFF),) * 1025

        with self.assertRaisesRegex(vial_transport.VialTransportError, "1..1024"):
            vial_transport.read_hub_document(self.address)

        lighting_gets = [
            packet[1]
            for _path, packet in self.backend.commands
            if packet[0] == vial_lighting.CMD_LIGHTING_GET_VALUE
        ]
        self.assertNotIn(vial_lighting.VIALRGB_GET_LED_INFO, lighting_gets)

    def test_legacy_vial_lighting_reads_only_definition_proved_values(self) -> None:
        self.state.definition["lighting"] = "qmk_backlight_rgblight"

        document = vial_transport.read_hub_document(self.address)

        surfaces = {
            surface["id"]: surface
            for surface in document.profile["lighting"]["surfaces"]
        }
        self.assertEqual(
            {"id": "backlight", "brightness": 101, "effect_id": 7},
            surfaces["backlight"],
        )
        self.assertEqual(
            {
                "id": "underglow",
                "brightness": 200,
                "effect_id": 9,
                "speed": 55,
                "color": [33, 44],
            },
            surfaces["underglow"],
        )
        self.assertEqual(
            [
                vial_lighting.QMK_BACKLIGHT_BRIGHTNESS,
                vial_lighting.QMK_BACKLIGHT_EFFECT,
                vial_lighting.QMK_RGBLIGHT_BRIGHTNESS,
                vial_lighting.QMK_RGBLIGHT_EFFECT,
                vial_lighting.QMK_RGBLIGHT_EFFECT_SPEED,
                vial_lighting.QMK_RGBLIGHT_COLOR,
            ],
            [
                packet[1]
                for _path, packet in self.backend.commands
                if packet[0] == vial_lighting.CMD_LIGHTING_GET_VALUE
            ],
        )
        self.assertFalse(
            {vial_lighting.CMD_LIGHTING_SET_VALUE, vial_lighting.CMD_LIGHTING_SAVE}
            & {packet[0] for _path, packet in self.backend.commands}
        )

    def test_confirmed_legacy_lighting_write_reads_back_then_saves_once(self) -> None:
        self.state.definition["lighting"] = "qmk_rgblight"
        profile = vial_transport.read_hub_profile(self.address)
        profile.pop("keymap")
        profile.pop("macros")
        profile["provenance"].pop("/keymap")
        profile["provenance"].pop("/macros")
        profile["lighting"]["surfaces"][0]["brightness"] = 201

        prepared = vial_transport.prepare_write(self.address, profile)

        self.assertEqual(1, len(prepared.lighting_plan.commands))
        self.assertIsNone(prepared.plan.keymap_buffer)
        self.assertIsNone(prepared.plan.macro_buffer)
        self.assertEqual(
            {
                "surfaces": [
                    {
                        "id": "underglow",
                        "brightness": 200,
                        "effect_id": 9,
                        "speed": 55,
                        "color": [33, 44],
                    }
                ]
            },
            prepared.lighting_backup,
        )
        self.assertRegex(prepared.target_fingerprint, r"^sha256-[0-9a-f]{64}$")
        self.backend.commands.clear()

        receipt = vial_transport.execute_write(
            prepared,
            confirmation=prepared.confirmation,
        )

        self.assertEqual(1, receipt.lighting_changes)
        self.assertEqual(1, receipt.lighting_saves)
        self.assertEqual(1, self.state.lighting_sets)
        self.assertEqual(1, self.state.lighting_saves)
        operations = {
            self._operation(packet) for _path, packet in self.backend.commands
        }
        self.assertFalse(
            operations
            & {(0xFE, 0x06), (0xFE, 0x07), (0x0F, None), (0x13, None)}
        )
        lighting_commands = [
            packet[0]
            for _path, packet in self.backend.commands
            if packet[0]
            in {
                vial_lighting.CMD_LIGHTING_SET_VALUE,
                vial_lighting.CMD_LIGHTING_GET_VALUE,
                vial_lighting.CMD_LIGHTING_SAVE,
            }
        ]
        setter = lighting_commands.index(vial_lighting.CMD_LIGHTING_SET_VALUE)
        save = lighting_commands.index(vial_lighting.CMD_LIGHTING_SAVE)
        self.assertIn(
            vial_lighting.CMD_LIGHTING_GET_VALUE,
            lighting_commands[setter + 1 : save],
        )

    def test_lighting_failures_keep_possible_setter_and_save_counts(self) -> None:
        cases = (
            ("readback", {"brightness": 201}, "ignore_lighting_sets", True, 1, 0),
            (
                "partial",
                {"brightness": 201, "speed": 56},
                "fail_lighting_set_number",
                2,
                2,
                0,
            ),
            ("save", {"brightness": 201}, "fail_lighting_save", True, 1, 1),
        )
        for name, changes, flag, value, expected_changes, expected_saves in cases:
            with self.subTest(name=name):
                prepared = self._prepared_legacy_lighting(**changes)
                setattr(self.state, flag, value)
                self.backend.commands.clear()

                with self.assertRaises(vial_transport.VialAcceptedWriteError) as caught:
                    vial_transport.execute_write(
                        prepared,
                        confirmation=prepared.confirmation,
                    )

                self.assertEqual(expected_changes, caught.exception.lighting_changes)
                self.assertEqual(expected_saves, caught.exception.lighting_saves)
                self.state.legacy_lighting_values.update(
                    {
                        vial_lighting.QMK_RGBLIGHT_BRIGHTNESS: bytes([200]),
                        vial_lighting.QMK_RGBLIGHT_EFFECT_SPEED: bytes([55]),
                    }
                )
                self.state.ignore_lighting_sets = False
                self.state.fail_lighting_set_number = None
                self.state.fail_lighting_save = False
                self.state.lighting_sets = 0
                self.state.lighting_saves = 0

    def test_vialrgb_capability_or_feature_change_stops_before_setter(self) -> None:
        for change in ("feature", "effects"):
            with self.subTest(change=change):
                self.state.definition["lighting"] = "vialrgb"
                self.state.feature_flags = vial_lighting.VIALRGB_FEATURE_FLAG
                self.state.unlocked = True
                profile = vial_transport.read_hub_profile(self.address)
                profile["lighting"]["surfaces"][0]["brightness"] = 100
                prepared = vial_transport.prepare_write(self.address, profile)
                if change == "feature":
                    self.state.feature_flags = 0
                else:
                    self.state.vialrgb_effects = (0, 1)
                self.backend.commands.clear()

                with self.assertRaises((hid_transport.HidError, ValueError)):
                    vial_transport.execute_write(
                        prepared,
                        confirmation=prepared.confirmation,
                    )

                self.assertFalse(
                    any(
                        packet[0] == vial_lighting.CMD_LIGHTING_SET_VALUE
                        for _path, packet in self.backend.commands
                    )
                )
                self.state.feature_flags = vial_lighting.VIALRGB_FEATURE_FLAG
                self.state.vialrgb_effects = (0, 1, 7)

    def test_read_session_refuses_a_set_command_before_transmission(self) -> None:
        info = hid_transport.find_vial(self.address)
        session = hid_transport.open_vial_read(info)
        self.backend.commands.clear()
        try:
            with self.assertRaises(hid_transport.HidError):
                session.send(bytes([vial_keymap.VIA_SET_BUFFER, 0, 0, 1, 0]))
            with self.assertRaises(hid_transport.HidError):
                session.send(
                    bytes(
                        [
                            vial_lighting.CMD_LIGHTING_GET_VALUE,
                            vial_lighting.VIALRGB_GET_INFO,
                        ]
                    )
                )
        finally:
            session.close()
        self.assertEqual([], self.backend.commands)

    def test_approved_session_refuses_unplanned_lighting_commands(self) -> None:
        prepared = self._prepared()
        approval = hid_transport.approve_vial_write(
            prepared.endpoint,
            prepared.confirmation,
        )
        session = hid_transport.open_vial_approved(approval)
        self.backend.commands.clear()
        try:
            for payload in (
                bytes([0x07]),
                bytes([0x08]),
                bytes([0x09]),
                bytes([0x0F]),
                bytes([0x13]),
                bytes([0xFE, 0x06]),
                bytes([0xFE, 0x07]),
            ):
                with self.subTest(payload=payload):
                    with self.assertRaises(hid_transport.HidError):
                        session.send(payload)
        finally:
            session.close()
        self.assertEqual([], self.backend.commands)

    def test_a_forged_generic_write_approval_is_refused_without_opening(self) -> None:
        forged = hid_transport.VialWriteApproval(
            address=self.address,
            path=self.path,
            name="Fixture Pad",
            confirmation="Fixture Pad",
            firmware_uid=self.record["firmware_uid"],
            protocol_version=self.record["vial_protocol"],
            definition_hash="sha256-forged",
        )
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidIdentityError):
            hid_transport.open_vial_approved(forged)

        self.assertEqual([], self.backend.commands)

    def test_wrong_typed_confirmation_stops_before_reopening_device(self) -> None:
        prepared = self._prepared()
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidIdentityError):
            vial_transport.execute_write(prepared, confirmation="Fixture Pad USB")

        self.assertEqual([], self.backend.commands)

    def test_locked_board_never_receives_keymap_or_macro_set(self) -> None:
        prepared = self._prepared()
        self.state.unlock_after_poll = False
        self.backend.commands.clear()

        with (
            mock.patch("am_configurator.vial_keymap.time.sleep"),
            self.assertRaises(vial_keymap.KeyboardLocked),
        ):
            vial_transport.execute_write(prepared, confirmation="Fixture Pad")

        operations = {self._operation(packet) for _path, packet in self.backend.commands}
        self.assertTrue({(0xFE, 0x06), (0xFE, 0x07)} <= operations)
        self.assertFalse(operations & {(0x13, None), (0x0F, None)})

    def test_replug_invalidates_prepared_endpoint_before_unlock(self) -> None:
        prepared = self._prepared()
        replacement = b"vial-device-replugged"
        self.backend.entries[0] = _entry(replacement)
        self.backend.states[replacement] = self.state
        del self.backend.states[self.path]
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidDeviceAbsent):
            vial_transport.execute_write(prepared, confirmation="Fixture Pad")

        self.assertEqual([], self.backend.commands)

    def test_changed_definition_at_same_endpoint_is_refused_before_unlock(self) -> None:
        prepared = self._prepared()
        self.state.definition["name"] = "Impostor Pad"
        self.backend.commands.clear()

        with self.assertRaises(hid_transport.HidIdentityError):
            vial_transport.execute_write(prepared, confirmation="Fixture Pad")

        operations = {self._operation(packet) for _path, packet in self.backend.commands}
        self.assertFalse(operations & {(0xFE, 0x06), (0xFE, 0x07), (0x13, None), (0x0F, None)})

    def test_confirmed_unlocked_write_uses_exact_plan_and_verifies_readback(self) -> None:
        prepared = self._prepared()
        self.backend.commands.clear()

        with mock.patch("am_configurator.vial_keymap.time.sleep"):
            receipt = vial_transport.execute_write(
                prepared, confirmation="Fixture Pad"
            )

        self.assertEqual(prepared.plan.keymap_buffer, bytes(self.state.keymap))
        self.assertEqual(prepared.plan.macro_buffer, bytes(self.state.macro_buffer))
        self.assertEqual(len(prepared.plan.keymap_buffer or b""), receipt.keymap_bytes)
        self.assertEqual(len(prepared.plan.macro_buffer or b""), receipt.macro_bytes)
        self.assertEqual(prepared.plan.report, receipt.report)
        operations = {self._operation(packet) for _path, packet in self.backend.commands}
        self.assertTrue({(0x13, None), (0x0F, None)} <= operations)

    def test_local_api_exposes_read_preflight_and_typed_write_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="openkeeb_vial_api_") as data_dir, mock.patch.dict(
            os.environ, {"AM_CONFIGURATOR_DATA_DIR": data_dir}
        ):
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
                status, listed = request("GET", "/api/hub/vial/devices")
                self.assertEqual(200, status)
                self.assertEqual(2, len(listed["devices"]))

                status, read = request(
                    "POST", "/api/hub/vial/read", {"address": self.address}
                )
                self.assertEqual(200, status)
                self.assertEqual("Fixture Pad", read["profile"]["identity"]["family"])
                self.assertEqual(self.address, read["device"]["address"])
                self.assertEqual("K_R0_C0", read["layout"][0]["key"])
                self.assertEqual(0, read["layout"][0]["matrix_row"])
                self.assertEqual(0, read["layout"][0]["matrix_col"])
                self.assertEqual([], read["lighting_geometry"])

                status, preflight = request(
                    "POST",
                    "/api/hub/vial/preflight",
                    {"address": self.address, "profile": read["profile"]},
                )
                self.assertEqual(200, status)
                self.assertEqual("Fixture Pad", preflight["confirmation"])
                self.assertEqual(0, preflight["lighting_changes"])
                self.assertEqual(0, preflight["lighting_saves"])
                self.assertIsNone(preflight["lighting_backup"])
                self.assertRegex(
                    preflight["target_fingerprint"],
                    r"^sha256-[0-9a-f]{64}$",
                )
                self.assertTrue(preflight["matches_target"])
                self.assertEqual(
                    {
                        "unlocked": False,
                        "in_progress": False,
                        "keys": [
                            {
                                "key": "K_R0_C0",
                                "matrix_row": 0,
                                "matrix_col": 0,
                            },
                            {
                                "key": "K_R0_C2",
                                "matrix_row": 0,
                                "matrix_col": 2,
                            },
                        ],
                    },
                    preflight["unlock"],
                )
                preflight_operations = {
                    self._operation(packet) for _path, packet in self.backend.commands
                }
                self.assertIn((0xFE, 0x05), preflight_operations)
                self.assertFalse(
                    preflight_operations
                    & {(0xFE, 0x06), (0xFE, 0x07), (0x13, None), (0x0F, None)}
                )

                self.backend.commands.clear()
                status, refused = request(
                    "POST",
                    "/api/hub/vial/write",
                    {
                        "address": self.address,
                        "profile": read["profile"],
                        "confirmation": "Fixture Pad USB",
                    },
                )
                self.assertEqual(400, status)
                self.assertIn("Type Fixture Pad exactly", refused["error"])
                operations = {
                    self._operation(packet) for _path, packet in self.backend.commands
                }
                self.assertFalse(
                    operations
                    & {(0xFE, 0x06), (0xFE, 0x07), (0x13, None), (0x0F, None)}
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
