"""Pure scheduling and lifecycle tests for volatile VialRGB preview."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import unittest

from am_configurator import vial_rgb_stream


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def wait(self, event: threading.Event, timeout: float) -> bool:
        if event.is_set():
            return True
        self.now += max(0.0, timeout)
        return event.is_set()

    def advance(self, seconds: float) -> None:
        self.now += seconds


class VialRGBStreamCoreTests(unittest.TestCase):
    def test_rgb_to_hsv8_is_deterministic_and_bounded(self) -> None:
        self.assertEqual((0, 255, 255), vial_rgb_stream.rgb_to_hsv8("#FF0000"))
        self.assertEqual((85, 255, 255), vial_rgb_stream.rgb_to_hsv8("#00FF00"))
        self.assertEqual((170, 255, 255), vial_rgb_stream.rgb_to_hsv8("#0000FF"))
        self.assertEqual((0, 0, 255), vial_rgb_stream.rgb_to_hsv8("#FFFFFF"))
        self.assertEqual((0, 0, 0), vial_rgb_stream.rgb_to_hsv8("#000000"))
        self.assertEqual(
            (0, 255, 128),
            vial_rgb_stream.rgb_to_hsv8("#FF0000", brightness=50),
        )
        with self.assertRaises(ValueError):
            vial_rgb_stream.rgb_to_hsv8("#ff0000")

    def test_first_frame_is_complete_unchanged_chunks_skip_and_rate_is_bounded(self) -> None:
        red = ["#FF0000"] * 10
        changed = [*red[:9], "#0000FF"]
        plan = vial_rgb_stream.build_plan(
            [red, red, changed],
            frame_ms=100,
            maximum_duration_ms=300,
        )
        clock = FakeClock()
        stop = threading.Event()
        entered: list[float] = []
        restored: list[float] = []
        sent: list[tuple[float, int, tuple[tuple[int, int, int], ...]]] = []

        outcome = vial_rgb_stream.run_stream(
            plan,
            stop_event=stop,
            enter_direct=lambda: entered.append(clock.monotonic()),
            send_chunk=lambda offset, pixels: sent.append(
                (clock.monotonic(), offset, pixels)
            ),
            restore=lambda: restored.append(clock.monotonic()),
            clock=clock,
        )

        self.assertEqual([0.0], entered)
        self.assertEqual(1, len(restored))
        self.assertEqual([0, 9, 9], [item[1] for item in sent])
        self.assertEqual(9, len(sent[0][2]))
        self.assertEqual(1, len(sent[1][2]))
        self.assertEqual((170, 255, 255), sent[2][2][0])
        self.assertTrue(
            all(
                later[0] - earlier[0] >= (1 / 30) - 1e-9
                for earlier, later in zip(sent, sent[1:])
            )
        )
        self.assertEqual("completed", outcome.state)
        self.assertEqual(3, outcome.reports_sent)
        self.assertEqual(3, outcome.reports_skipped)
        self.assertEqual("restored", outcome.restoration)

    def test_late_frames_are_skipped_instead_of_queued(self) -> None:
        plan = vial_rgb_stream.build_plan(
            [
                ["#FF0000"],
                ["#00FF00"],
                ["#0000FF"],
                ["#FFFFFF"],
            ],
            frame_ms=20,
            maximum_duration_ms=220,
        )
        clock = FakeClock()
        sent: list[float] = []

        def slow_send(_offset, _pixels) -> None:
            sent.append(clock.monotonic())
            clock.advance(0.09)

        outcome = vial_rgb_stream.run_stream(
            plan,
            stop_event=threading.Event(),
            enter_direct=lambda: None,
            send_chunk=slow_send,
            restore=lambda: None,
            clock=clock,
        )

        self.assertGreater(outcome.frames_skipped, 0)
        self.assertLess(len(sent), 6)
        self.assertEqual("completed", outcome.state)

    def test_send_failure_is_not_retried_and_restoration_runs_once(self) -> None:
        plan = vial_rgb_stream.build_plan(
            [["#FF0000"]],
            frame_ms=90,
            maximum_duration_ms=180,
        )
        sends = 0
        restores = 0

        def fail_send(_offset, _pixels) -> None:
            nonlocal sends
            sends += 1
            raise OSError("fake setter timeout")

        def restore() -> None:
            nonlocal restores
            restores += 1

        outcome = vial_rgb_stream.run_stream(
            plan,
            stop_event=threading.Event(),
            enter_direct=lambda: None,
            send_chunk=fail_send,
            restore=restore,
            clock=FakeClock(),
        )

        self.assertEqual(1, sends)
        self.assertEqual(1, restores)
        self.assertEqual("error", outcome.state)
        self.assertIn("fake setter timeout", outcome.error or "")
        self.assertEqual("restored", outcome.restoration)

    def test_failed_restore_is_reported_without_retry(self) -> None:
        plan = vial_rgb_stream.build_plan(
            [["#FF0000"]],
            frame_ms=90,
            maximum_duration_ms=90,
        )
        restores = 0

        def fail_restore() -> None:
            nonlocal restores
            restores += 1
            raise OSError("fake restore timeout")

        outcome = vial_rgb_stream.run_stream(
            plan,
            stop_event=threading.Event(),
            enter_direct=lambda: None,
            send_chunk=lambda _offset, _pixels: None,
            restore=fail_restore,
            clock=FakeClock(),
        )

        self.assertEqual(1, restores)
        self.assertEqual("error", outcome.state)
        self.assertEqual("failed", outcome.restoration)
        self.assertIn("fake restore timeout", outcome.restoration_error or "")


@dataclass(frozen=True)
class Prepared:
    confirmation: str = "PREVIEW Fixture Pad"
    subject: str = "Fixture animation"


class VialRGBStreamManagerTests(unittest.TestCase):
    def test_one_token_one_worker_and_stop_closes_with_restoration_result(self) -> None:
        started = threading.Event()

        def runner(_prepared, stop_event, progress):
            started.set()
            progress({"frames_presented": 1, "reports_sent": 2})
            stop_event.wait(1)
            return vial_rgb_stream.StreamOutcome(
                state="stopped",
                frames_presented=1,
                reports_sent=2,
                restoration="restored",
            )

        manager = vial_rgb_stream.StreamManager(runner=runner)
        first = manager.preflight(Prepared())
        second = manager.preflight(Prepared(subject="Replacement"))
        self.assertNotEqual(first, second)
        with self.assertRaises(vial_rgb_stream.StreamTokenError):
            manager.status(first)
        with self.assertRaises(vial_rgb_stream.StreamConfirmationError):
            manager.start(second, "Fixture Pad")
        self.assertFalse(started.is_set())

        status = manager.start(second, "PREVIEW Fixture Pad")
        self.assertIn(status["state"], {"starting", "running"})
        self.assertTrue(started.wait(1))
        with self.assertRaises(vial_rgb_stream.StreamBusyError):
            manager.preflight(Prepared())

        stopped = manager.stop(second, wait=True)
        self.assertEqual("stopped", stopped["state"])
        self.assertEqual("restored", stopped["restoration"])
        self.assertEqual(2, stopped["reports_sent"])
        self.assertFalse(manager.active)
        manager.close()


if __name__ == "__main__":
    unittest.main()
