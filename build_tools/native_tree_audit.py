#!/usr/bin/env python3
"""Audit a frozen native application tree for prohibited bundled code."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys


@dataclass(frozen=True, order=True)
class AuditFinding:
    relative_path: str
    location: str
    category: str


_CONTENT_MARKERS = (
    (b"ff" + b"mpegaudiodecoder", "embedded-media-decoder"),
    (b"ff" + b"mpeg_audio_decoder", "embedded-media-decoder"),
    (b"ff" + b"mpegdemuxer", "embedded-media-demuxer"),
    (b"ff" + b"mpeg_demuxer", "embedded-media-demuxer"),
    (b"third_party/" + b"ff" + b"mpeg/", "embedded-media-source"),
    (b"libavcodec", "libav-codec"),
    (b"libavformat", "libav-format"),
    (b"libavutil", "libav-utility"),
    (b"libswscale", "software-scaling"),
    (b"libswresample", "software-resampling"),
    (b"process_video_frames", "retired-video-adapter"),
    (b"tiny-motion.mp4", "retired-video-fixture"),
)
_PATH_MARKERS = (
    (b"ff" + b"mpeg", "retired-media-tool"),
    (b"libgstlibav", "gstreamer-libav-plugin"),
    (b"gst-libav", "gstreamer-libav-plugin"),
    (b"gstreamer1.0-libav", "gstreamer-libav-plugin"),
    *_CONTENT_MARKERS,
    (b"pyqt6", "qt-binding"),
    (b"qtwebengine", "qt-webengine"),
    (b"qt6webengine", "qt-webengine"),
    (b"qtmultimedia", "qt-multimedia"),
    (b"qt6multimedia", "qt-multimedia"),
)


def _is_junction(path: Path) -> bool:
    probe = getattr(path, "is_junction", None)
    return bool(probe is not None and probe())


def _regular_files(root: Path):
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda entry: entry.name.casefold(), reverse=True)
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink() or _is_junction(path):
                continue
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif entry.is_file(follow_symlinks=False):
                yield path, path.relative_to(root).as_posix()


def _content_categories(path: Path, chunk_size: int) -> set[str]:
    overlap = max(len(marker) for marker, _category in _CONTENT_MARKERS) - 1
    found: set[str] = set()
    tail = b""
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            window = (tail + chunk).lower()
            for marker, category in _CONTENT_MARKERS:
                if category not in found and marker in window:
                    found.add(category)
            tail = window[-overlap:]
    return found


def audit_tree(root: Path, *, chunk_size: int = 64 * 1024) -> list[AuditFinding]:
    """Return prohibited path and content findings below ``root``."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    supplied_root = Path(root)
    if supplied_root.is_symlink() or _is_junction(supplied_root):
        raise ValueError("native tree root cannot be a link")
    root = supplied_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("native tree root must be a directory")

    findings: list[AuditFinding] = []
    for path, relative_path in _regular_files(root):
        lowered_path = os.fsencode(relative_path).lower()
        for marker, category in _PATH_MARKERS:
            if marker in lowered_path:
                findings.append(AuditFinding(relative_path, "path", category))
        for category in _content_categories(path, chunk_size):
            findings.append(AuditFinding(relative_path, "content", category))
    return sorted(set(findings))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path, help="Frozen native tree to audit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        findings = audit_tree(args.tree)
    except (OSError, ValueError):
        print(
            "Native tree audit failed: the supplied tree could not be audited.",
            file=sys.stderr,
        )
        return 2
    if findings:
        print(
            f"Native tree audit rejected {len(findings)} finding(s):",
            file=sys.stderr,
        )
        for finding in findings:
            safe_path = json.dumps(finding.relative_path, ensure_ascii=True)
            print(
                f"- {safe_path} [{finding.location}:{finding.category}]",
                file=sys.stderr,
            )
        return 1
    print("Native tree audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
