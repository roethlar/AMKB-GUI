from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from build_tools.native_tree_audit import audit_tree, main


class NativeTreeAuditTests(unittest.TestCase):
    def test_clean_tree_passes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "nested" / "application.bin").write_bytes(b"ordinary native data")

            self.assertEqual([], audit_tree(root))

    def test_mixed_case_path_markers_fail(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "plugins").mkdir()
            (root / "plugins" / "PyQt6_plugin.bin").write_bytes(b"ordinary data")

            findings = audit_tree(root)

        self.assertIn(
            ("plugins/PyQt6_plugin.bin", "path", "qt-binding"),
            {
                (finding.relative_path, finding.location, finding.category)
                for finding in findings
            },
        )

    def test_mixed_case_content_markers_fail(self) -> None:
        markers = {
            "retired-media-tool": b"fF" + b"MpEg",
            "libav-codec": b"LiBaVcOdEc",
            "libav-format": b"LIBAVFORMAT",
            "libav-utility": b"libavutil",
            "software-scaling": b"libswscale",
            "software-resampling": b"libswresample",
            "retired-video-adapter": b"process_VIDEO_frames",
            "retired-video-fixture": b"TINY-MOTION.MP4",
        }
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, marker in enumerate(markers.values()):
                (root / f"library-{index}.bin").write_bytes(b"prefix" + marker + b"suffix")

            findings = audit_tree(root)

        self.assertEqual(
            set(markers),
            {
                finding.category
                for finding in findings
                if finding.location == "content"
            },
        )

    def test_content_marker_split_across_chunks_fails(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "library.bin").write_bytes(b"1234567" + b"libavformat")

            findings = audit_tree(root, chunk_size=8)

        self.assertIn(
            "libav-format",
            {finding.category for finding in findings},
        )

    def test_symlink_targets_are_not_traversed(self) -> None:
        with TemporaryDirectory() as temporary, TemporaryDirectory() as external:
            root = Path(temporary)
            target = Path(external) / "outside.bin"
            target.write_bytes(b"libavcodec")
            try:
                os.symlink(target, root / "external-data.bin")
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlinks unavailable: {type(exc).__name__}")

            self.assertEqual([], audit_tree(root))

    def test_cli_reports_only_relative_paths_and_categories(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "native.bin").write_bytes(b"secret-prefix-LIBAVUTIL-secret-suffix")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main([str(root)])

        report = stderr.getvalue()
        self.assertEqual(1, result)
        self.assertEqual("", stdout.getvalue())
        self.assertIn('"native.bin" [content:libav-utility]', report)
        self.assertNotIn(str(root), report)
        self.assertNotIn("secret-prefix", report)


if __name__ == "__main__":
    unittest.main()
