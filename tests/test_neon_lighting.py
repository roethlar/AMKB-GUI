from __future__ import annotations

import unittest

from am_configurator import neon_lighting as nl


def _axial(color: str = "#010203") -> list[str]:
    return [color] * nl.AXIAL_LED_COUNT


def _head(color: str = "#040506") -> list[str]:
    return [color] * nl.HEAD_LED_COUNT


class SideDerivationTests(unittest.TestCase):
    """Side is derived, never authored. The count is the load-bearing fact."""

    def test_the_derivation_yields_exactly_seventy_leds(self) -> None:
        # 4x21 candidates minus the fourteen skipped positions. Any other count
        # means the skip rules are wrong, and the firmware will not accept it.
        self.assertEqual(nl.SIDE_LED_COUNT, len(nl.derive_side_frame(_head())))
        self.assertEqual(70, nl.SIDE_LED_COUNT)

    def test_it_samples_the_head_matrix_by_nearest_neighbour(self) -> None:
        # A head frame whose every cell encodes its own row-major index, so a
        # derived colour identifies exactly which source cell it came from.
        head = [f"#{index:06X}" for index in range(nl.HEAD_LED_COUNT)]
        side = nl.derive_side_frame(head)

        expected = []
        for y in range(nl.SIDE_ROWS):
            for x in range(nl.SIDE_COLUMNS):
                if y == 0 and 4 < x < 16:
                    continue
                if y == 1 and x in (6, 7):
                    continue
                if y == 3 and x == 6:
                    continue
                source_x = (x * nl.HEAD_COLUMNS) // nl.SIDE_COLUMNS
                source_y = (y * nl.HEAD_ROWS) // nl.SIDE_ROWS
                expected.append(head[source_y * nl.HEAD_COLUMNS + source_x])

        self.assertEqual(expected, side)
        self.assertEqual(70, len(side))

    def test_the_skipped_positions_are_exactly_fourteen(self) -> None:
        skipped = sum(
            1
            for y in range(nl.SIDE_ROWS)
            for x in range(nl.SIDE_COLUMNS)
            if (y == 0 and 4 < x < 16) or (y == 1 and x in (6, 7)) or (y == 3 and x == 6)
        )
        self.assertEqual(14, skipped)
        self.assertEqual(nl.SIDE_ROWS * nl.SIDE_COLUMNS - skipped, nl.SIDE_LED_COUNT)

    def test_a_wrong_length_head_frame_is_refused(self) -> None:
        with self.assertRaises(nl.NeonLightingError):
            nl.derive_side_frame(_head()[:-1])


class GoldenPacketTests(unittest.TestCase):
    """Every emitted byte for a three-frame effect across all three channels."""

    def setUp(self) -> None:
        # Head frames must be *positional*, not uniform. With a flat colour the
        # derived side frame is byte-identical to simply taking the first 70
        # head values, so the derivation could be deleted entirely and every
        # assertion here would still pass. Each cell encodes its own index.
        self.head_frames = [
            [f"#{frame:02X}{index // 256:02X}{index % 256:02X}" for index in range(nl.HEAD_LED_COUNT)]
            for frame in range(3)
        ]
        self.axial_frames = [_axial(f"#{n:02X}0000") for n in range(3)]
        self.plan = nl.plan_push(
            self.axial_frames,
            self.head_frames,
            slot=1,
            lightness=100,
            interval=90,
        )

    def test_channels_are_slot_n_and_n_plus_three_and_six(self) -> None:
        self.assertEqual(
            [("axial", 0x01), ("head", 0x04), ("side", 0x07)],
            [(u.zone, u.channel) for u in self.plan.uploads],
        )

        slot_three = nl.plan_push([_axial()], [_head()], slot=3)
        self.assertEqual(
            [0x03, 0x06, 0x09], [u.channel for u in slot_three.uploads]
        )

    def test_packetization_matches_the_documented_counts(self) -> None:
        axial, head, side = self.plan.uploads

        # 89 axial LEDs at 8 per packet: 12 packets, the last carrying 1 LED.
        self.assertEqual(12, len(axial.frames[0]))
        self.assertEqual(3, axial.frames[0][-1][6])
        # 230 head LEDs: 29 packets, the last carrying 6 LEDs.
        self.assertEqual(29, len(head.frames[0]))
        self.assertEqual(18, head.frames[0][-1][6])
        # 70 side LEDs: 9 packets, the last carrying 6 LEDs.
        self.assertEqual(9, len(side.frames[0]))
        self.assertEqual(18, side.frames[0][-1][6])

    def test_every_packet_is_well_formed_and_checksummed(self) -> None:
        for upload in self.plan.uploads:
            for frame_index, frame in enumerate(upload.frames):
                for packet in frame:
                    with self.subTest(zone=upload.zone, frame=frame_index):
                        self.assertEqual(nl.PACKET_LENGTH, len(packet))
                        self.assertEqual(nl.LIGHTING_COMMAND, packet[0])
                        self.assertEqual(upload.channel, packet[1])
                        self.assertEqual(frame_index, packet[2])
                        self.assertEqual(100, packet[4])
                        self.assertEqual(90, packet[5])
                        self.assertLessEqual(packet[6], nl.MAX_RGB_BYTES)
                        self.assertEqual(sum(packet[0:31]) & 0xFF, packet[31])

    def test_only_the_last_packet_of_the_last_frame_carries_the_terminator(self) -> None:
        for upload in self.plan.uploads:
            with self.subTest(zone=upload.zone):
                terminators = [
                    (frame_index, packet_index)
                    for frame_index, frame in enumerate(upload.frames)
                    for packet_index, packet in enumerate(frame)
                    if packet[3] == 255
                ]
                self.assertEqual(1, len(terminators), terminators)
                frame_index, packet_index = terminators[0]
                self.assertEqual(len(upload.frames) - 1, frame_index)
                self.assertEqual(len(upload.frames[-1]) - 1, packet_index)

    def test_the_side_channel_carries_the_derived_colours(self) -> None:
        _axial_u, _head_u, side = self.plan.uploads

        for frame_index, source in enumerate(self.head_frames):
            expected = b"".join(
                bytes.fromhex(color[1:]) for color in nl.derive_side_frame(source)
            )
            emitted = b"".join(
                packet[7 : 7 + packet[6]] for packet in side.frames[frame_index]
            )
            self.assertEqual(expected, emitted)

            # And it is genuinely derived, not the first 70 head values. With a
            # uniform frame these are identical, which is what made an earlier
            # version of this test vacuous.
            naive = b"".join(
                bytes.fromhex(color[1:]) for color in source[: nl.SIDE_LED_COUNT]
            )
            self.assertNotEqual(naive, emitted)

    def test_rgb_payload_round_trips_for_every_channel(self) -> None:
        axial, head, _side = self.plan.uploads
        for frame_index in range(3):
            with self.subTest(frame=frame_index):
                emitted = b"".join(
                    packet[7 : 7 + packet[6]] for packet in axial.frames[frame_index]
                )
                self.assertEqual(
                    b"".join(bytes.fromhex(f"{frame_index:02X}0000") for _ in range(89)),
                    emitted,
                )
                emitted_head = b"".join(
                    packet[7 : 7 + packet[6]] for packet in head.frames[frame_index]
                )
                self.assertEqual(
                    b"".join(
                        bytes.fromhex(color[1:])
                        for color in self.head_frames[frame_index]
                    ),
                    emitted_head,
                )


class PlanValidationTests(unittest.TestCase):
    """Everything checkable is checked before a single packet is sent."""

    def test_mismatched_track_lengths_are_refused(self) -> None:
        for axial, head in (
            ([_axial()[:-1]], [_head()]),
            ([_axial()], [_head()[:-1]]),
        ):
            with self.subTest():
                with self.assertRaises(nl.NeonLightingError):
                    nl.plan_push(axial, head, slot=1)

    def test_channels_may_have_independent_frame_counts(self) -> None:
        plan = nl.plan_push(
            [_axial(), _axial()],
            [_head(), _head(), _head()],
            slot=1,
        )

        axial, head, side = plan.uploads
        self.assertEqual([2, 3, 3], [len(upload.frames) for upload in plan.uploads])
        for upload in (axial, head, side):
            terminators = [
                (frame_index, packet_index)
                for frame_index, frame in enumerate(upload.frames)
                for packet_index, packet in enumerate(frame)
                if packet[3] == 255
            ]
            self.assertEqual(
                [(len(upload.frames) - 1, len(upload.frames[-1]) - 1)],
                terminators,
                upload.zone,
            )

    def test_more_than_the_frame_cap_is_refused(self) -> None:
        for axial, head in (
            ([_axial()] * (nl.MAX_FRAMES + 1), [_head()]),
            ([_axial()], [_head()] * (nl.MAX_FRAMES + 1)),
        ):
            with self.subTest(axial=len(axial), head=len(head)):
                with self.assertRaises(nl.NeonLightingError):
                    nl.plan_push(axial, head, slot=1)

    def test_an_empty_effect_and_a_bad_slot_are_refused(self) -> None:
        for axial, head in (([], [_head()]), ([_axial()], []), ([], [])):
            with self.subTest(axial=len(axial), head=len(head)):
                with self.assertRaises(nl.NeonLightingError):
                    nl.plan_push(axial, head, slot=1)
        with self.assertRaises(nl.NeonLightingError):
            nl.plan_push([_axial()], [_head()], slot=4)

    def test_a_malformed_colour_is_refused(self) -> None:
        bad = [["#GGGGGG"] * nl.AXIAL_LED_COUNT]
        with self.assertRaises(nl.NeonLightingError):
            nl.plan_push(bad, [_head()], slot=1)


class FakeSession:
    """Records packets and returns the firmware's packet echo."""

    def __init__(self, corrupt_at: int | None = None) -> None:
        self.sent: list[bytes] = []
        self.corrupt_at = corrupt_at

    def send(self, packet: bytes) -> None:
        self.sent.append(packet)

    def receive(self, timeout_ms: int = 0) -> bytes:
        reply = bytearray(self.sent[-1])
        if reply[3] == 0xFF:
            same_frame = [
                packet
                for packet in self.sent
                if packet[1] == reply[1] and packet[2] == reply[2]
            ]
            reply[3] = len(same_frame) - 1
            reply[31] = sum(reply[:31]) & 0xFF
        if self.corrupt_at is not None and len(self.sent) - 1 == self.corrupt_at:
            reply[1] ^= 0x01
        return bytes(reply)


class PushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = nl.plan_push([_axial()], [_head()], slot=1)

    def test_a_complete_push_sends_every_planned_packet(self) -> None:
        session = FakeSession()
        sent = nl.push(session, self.plan)

        self.assertEqual(self.plan.packet_count, sent)
        self.assertEqual(self.plan.packet_count, len(session.sent))

    def test_an_echoed_red_payload_byte_is_not_a_rejection(self) -> None:
        """Firmware byte 7 is echoed RGB data, so 0xFF is a valid red channel."""

        plan = nl.plan_push([_axial("#FF0000")], [_head("#00FF00")], slot=1)
        session = FakeSession()

        self.assertEqual(plan.packet_count, nl.push(session, plan))
        self.assertEqual(plan.packet_count, len(session.sent))

    def test_an_unexpected_echo_aborts_and_names_the_zone_and_frame(self) -> None:
        """A reply that does not echo the accepted packet must stop the upload."""

        session = FakeSession(corrupt_at=0)
        with self.assertRaises(nl.NeonLightingRejected) as raised:
            nl.push(session, self.plan)

        self.assertIn("axial", str(raised.exception))
        self.assertIn("frame 0", str(raised.exception))
        self.assertIn("incomplete", str(raised.exception))
        self.assertEqual(1, len(session.sent), "sending continued past a rejection")

    def test_cancellation_stops_the_upload(self) -> None:
        session = FakeSession()
        with self.assertRaises(nl.NeonLightingError):
            nl.push(session, self.plan, is_cancelled=lambda: True)
        self.assertEqual([], session.sent)

    def test_an_expired_deadline_stops_the_upload(self) -> None:
        session = FakeSession()
        with self.assertRaises(nl.NeonLightingError) as raised:
            nl.push(session, self.plan, deadline=0.0)
        self.assertIn("deadline", str(raised.exception))
        self.assertEqual([], session.sent)

    def test_progress_reports_the_final_count(self) -> None:
        session = FakeSession()
        seen: list[tuple[int, int]] = []
        nl.push(session, self.plan, on_progress=lambda done, total: seen.append((done, total)))

        self.assertTrue(seen)
        self.assertEqual((self.plan.packet_count, self.plan.packet_count), seen[-1])


if __name__ == "__main__":
    unittest.main()
