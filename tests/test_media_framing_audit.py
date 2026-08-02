from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from am_configurator import desktop, device_mapping, media_composition
from am_configurator import media_framing_audit


class MediaFramingFixtureTests(unittest.TestCase):
    def test_anonymous_asymmetric_fixtures_map_exact_sentinel_pixels(self) -> None:
        fixtures = media_framing_audit.build_media_fixtures()

        self.assertEqual(["gif", "png", "bmp"], [case.format for case in fixtures])
        self.assertEqual(3, len({case.payload for case in fixtures}))
        for case in fixtures:
            with self.subTest(format=case.format):
                decoded = media_composition.decode_media(case.payload)
                self.assertEqual(case.mime_type, decoded.mime_type)
                self.assertEqual((20, 5), (decoded.width, decoded.height))
                self.assertNotEqual(decoded.width, decoded.height)
                self.assertEqual(case.source_frame_count, decoded.frame_count)

                mapped = device_mapping.compose_media_frames_to_led_tracks(
                    decoded.frames,
                    decoded.durations_ms,
                    ["frames"],
                    media_framing_audit.AUDIT_TRANSFORM,
                    "CB04",
                )
                frames = mapped["tracks"]["frames"]["frames"]
                self.assertEqual(len(case.expected_frames), len(frames))
                for index, expected in enumerate(case.expected_frames):
                    colors = frames[index]
                    self.assertEqual(200, len(colors))
                    self.assertEqual(
                        expected.non_black,
                        sum(color.casefold() != "#000000" for color in colors),
                    )
                    for pixel, color in expected.sentinels:
                        self.assertEqual(color.casefold(), colors[pixel].casefold())

    def test_fixture_payloads_are_pathless_and_small(self) -> None:
        for case in media_framing_audit.build_media_fixtures():
            with self.subTest(format=case.format):
                self.assertEqual(f"audit.{case.format}", case.name)
                self.assertNotIn("/", case.name)
                self.assertNotIn("\\", case.name)
                self.assertLess(len(case.payload), 64_000)

    def test_audit_document_has_distinct_playback_destinations(self) -> None:
        document = media_framing_audit.build_audit_document()
        for page in document["page_data"][5:8]:
            with self.subTest(page=page["page_index"]):
                self.assertEqual(48, page["speed_ms"])
                self.assertEqual(2, page["keyframes"]["frame_num"])
                self.assertEqual(2, page["frames"]["frame_num"])
                self.assertEqual(90, len(page["keyframes"]["frame_data"][0]["frame_RGB"]))
                self.assertEqual(200, len(page["frames"]["frame_data"][0]["frame_RGB"]))
                self.assertNotEqual(
                    page["keyframes"]["frame_data"][0]["frame_RGB"][0],
                    page["frames"]["frame_data"][0]["frame_RGB"][0],
                )

    def test_native_script_checks_destination_playback_before_media_mutation(self) -> None:
        script = media_framing_audit._audit_script()
        playback = script.index("await verifyDestinationPlaybackIsolation()")
        baseline = script.index("const baselinePage = pageFingerprint()", playback)
        self.assertLess(playback, baseline)
        self.assertIn(
            "destination_playback_isolation",
            media_framing_audit.REQUIRED_CASE_CHECKS,
        )
        self.assertIn("playback_destination_colors_mismatch", script)
        self.assertIn("playback_changed_document", script)

    def test_native_script_checks_the_synchronized_source_board_and_timeline_shell(self) -> None:
        script = media_framing_audit._audit_script()

        self.assertIn("synchronized_workspace", media_framing_audit.REQUIRED_CASE_CHECKS)
        self.assertIn("shared_timeline", media_framing_audit.REQUIRED_CASE_CHECKS)
        self.assertIn(
            "preview_session_recovery",
            media_framing_audit.REQUIRED_CASE_CHECKS,
        )
        self.assertIn('#lighting-source-pane', script)
        self.assertIn('#lighting-board-pane', script)
        self.assertIn('#lighting-timeline', script)
        self.assertIn('.source-frame-image', script)
        self.assertIn('board.querySelector("img,picture,video,canvas,svg,image")', script)
        self.assertIn('timelineScrubber.dispatchEvent(new Event("input"', script)
        self.assertIn('selectSourceProjection(lightingWorkspace)', script)
        self.assertIn(
            'for (let eviction = 0; eviction < 2; eviction += 1)',
            script,
        )
        self.assertIn('preview_session_recovery_timeout', script)
        self.assertIn('currentPreviewSessionId !== expiredPreviewSessionId', script)
        self.assertNotIn('.media-source-overlay', script)


class MediaFramingReportTests(unittest.TestCase):
    @staticmethod
    def _valid_report() -> dict:
        return {
            "schema_version": 1,
            "status": "passed",
            "failure": None,
            "viewports": [
                {
                    "width": width,
                    "height": height,
                    "cases": [
                        {
                            "format": format_name,
                            "checks": media_framing_audit.REQUIRED_CASE_CHECKS,
                        }
                        for format_name in ("gif", "png", "bmp")
                    ],
                    "layout_findings": [],
                    "console_errors": [],
                }
                for width, height in media_framing_audit.AUDIT_VIEWPORTS
            ],
        }

    def test_report_schema_is_exact_bounded_and_sanitized(self) -> None:
        report = self._valid_report()

        checked = media_framing_audit.validate_audit_report(report)

        self.assertEqual(report, checked)
        self.assertLessEqual(
            len(json.dumps(checked, separators=(",", ":")).encode("utf-8")),
            media_framing_audit.MAX_REPORT_BYTES,
        )

    def test_report_rejects_paths_identifiers_and_unbounded_text(self) -> None:
        invalid_values = (
            {"path": "C:/Users/private"},
            {"product_id": "CB04"},
            {"error": "x" * 600},
        )
        for value in invalid_values:
            with self.subTest(value=next(iter(value))):
                report = self._valid_report()
                report["viewports"][0]["cases"][0].update(value)
                with self.assertRaises(media_framing_audit.MediaFramingAuditError):
                    media_framing_audit.validate_audit_report(report)

    def test_failed_report_accepts_only_one_sanitized_failure_code(self) -> None:
        report = {
            "schema_version": 1,
            "status": "failed",
            "failure": "pointer_feedback_missing",
            "viewports": [],
        }
        self.assertEqual(report, media_framing_audit.validate_audit_report(report))
        for failure in (None, "C:/private/path", "x" * 201):
            with self.subTest(failure=failure):
                report["failure"] = failure
                with self.assertRaises(media_framing_audit.MediaFramingAuditError):
                    media_framing_audit.validate_audit_report(report)

    def test_report_writer_never_emits_an_invalid_result(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            output = Path(raw_root) / "result.json"
            media_framing_audit.write_audit_report(output, self._valid_report())
            self.assertEqual(
                self._valid_report(),
                json.loads(output.read_text(encoding="utf-8")),
            )


class MediaFramingIsolationTests(unittest.TestCase):
    def test_cleanup_removes_only_the_exact_verified_audit_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw_parent:
            parent = Path(raw_parent).resolve()
            root = parent / "am-media-framing-audit-owned"
            data = root / "data"
            library = root / "library"
            data.mkdir(parents=True)
            library.mkdir()
            (data / "owned.txt").write_text("owned", encoding="utf-8")
            expected_root = root.resolve(strict=True)
            expected_children = (data.resolve(strict=True), library.resolve(strict=True))

            media_framing_audit.cleanup_audit_root(
                root,
                expected_root=expected_root,
                expected_parent=parent,
                expected_children=expected_children,
            )

            self.assertFalse(root.exists())

    def test_cleanup_rejects_a_mismatched_root_without_deleting_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw_parent:
            parent = Path(raw_parent).resolve()
            root = parent / "am-media-framing-audit-owned"
            data = root / "data"
            library = root / "library"
            data.mkdir(parents=True)
            library.mkdir()

            with self.assertRaises(media_framing_audit.MediaFramingAuditError):
                media_framing_audit.cleanup_audit_root(
                    root,
                    expected_root=parent,
                    expected_parent=parent,
                    expected_children=(
                        data.resolve(strict=True),
                        library.resolve(strict=True),
                    ),
                )

            self.assertTrue(root.is_dir())


class MediaFramingNativeWindowTests(unittest.TestCase):
    def test_native_audit_activates_the_window_before_asserting_focus(self) -> None:
        window = mock.Mock()
        window.evaluate_js.side_effect = [False, True]

        with mock.patch("am_configurator.media_framing_audit.time.sleep") as sleep:
            media_framing_audit._activate_webview_window(window, timeout=1)

        window.show.assert_called_once_with()
        self.assertEqual(
            [mock.call("document.hasFocus()"), mock.call("document.hasFocus()")],
            window.evaluate_js.call_args_list,
        )
        sleep.assert_called_once_with(0.05)


class MediaFramingCliTests(unittest.TestCase):
    def test_cli_dispatches_the_explicit_audit_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            output = Path(raw_root) / "audit.json"
            with mock.patch(
                "am_configurator.media_framing_audit.run_media_framing_audit",
                return_value=0,
            ) as run:
                self.assertEqual(
                    0,
                    desktop.main(["--media-framing-audit", str(output)]),
                )
            run.assert_called_once_with(output)

    def test_cli_rejects_every_conflicting_audit_mode(self) -> None:
        conflicts = (
            ["profile.json"],
            ["--debug"],
            ["--print-udev-rule"],
            ["--smoke-test"],
            ["--native-policy-smoke"],
            ["--native-policy-probe", "seed", "--native-policy-dir", "probe"],
            ["--native-policy-dir", "probe"],
        )
        for conflict in conflicts:
            with self.subTest(conflict=conflict):
                with (
                    mock.patch("sys.stderr", new_callable=io.StringIO),
                    self.assertRaises(SystemExit) as raised,
                ):
                    desktop.main(
                        ["--media-framing-audit", "audit.json", *conflict]
                    )
                self.assertEqual(2, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
