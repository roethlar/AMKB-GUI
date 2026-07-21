from __future__ import annotations

import hashlib
import os
import socket
import stat
import tempfile
import time
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

from am_configurator import media


def _mp4_bytes() -> bytes:
    return (
        (24).to_bytes(4, "big")
        + b"ftyp"
        + b"isom"
        + b"\x00\x00\x00\x00"
        + b"isomiso2"
    )


class _Response:
    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        read_error: BaseException | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.read_error = read_error
        self.read_calls = 0
        self.timeout_values: list[float] = []
        self.closed = False

    def getcode(self) -> int:
        return self.status

    def read(self, amount: int = -1) -> bytes:
        self.read_calls += 1
        if self.read_error is not None:
            raise self.read_error
        if amount < 0:
            result, self.body = self.body, b""
        else:
            result, self.body = self.body[:amount], self.body[amount:]
        return result

    def close(self) -> None:
        self.closed = True

    def settimeout(self, value: float) -> None:
        self.timeout_values.append(value)


class _Opener:
    def __init__(self, *responses: _Response) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[object, float]] = []

    def __call__(self, request, timeout: float):
        self.calls.append((request, timeout))
        if not self.responses:
            raise AssertionError("unexpected opener call")
        return self.responses.pop(0)


class VideoDownloaderTests(unittest.TestCase):
    _URL = "https://vidgen.x.ai/output/source.mp4?signature=temporary-secret"

    def _deadline(self) -> float:
        return time.monotonic() + 30.0

    def test_rejects_unsafe_urls_before_opening_and_never_echoes_them(self) -> None:
        unsafe = (
            "http://vidgen.x.ai/source.mp4",
            "https://evil.example/source.mp4",
            "https://user:pass@vidgen.x.ai/source.mp4",
            "https://vidgen.x.ai:443/source.mp4",
            "https://VIDGEN.x.ai/source.mp4",
            "https://vidgen.x.ai/source.mp4#secret-fragment",
            "https://vidgen.x.ai/source.mp4?signature=line\nbreak",
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            for url in unsafe:
                opener = _Opener()
                with self.subTest(url=url):
                    with self.assertRaises(media.MediaError) as ctx:
                        media.download_video(
                            url, destination, self._deadline(), opener=opener
                        )
                    self.assertEqual(opener.calls, [])
                    self.assertNotIn(url, str(ctx.exception))

    def test_unsuccessful_response_is_closed_without_exposing_signed_url(self) -> None:
        response = _Response(status=403)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(media.MediaError) as ctx:
                media.download_video(
                    self._URL,
                    Path(tmp) / "source.mp4",
                    self._deadline(),
                    opener=_Opener(response),
                )
        self.assertTrue(response.closed)
        self.assertNotIn("temporary-secret", str(ctx.exception))

    def test_redirect_is_revalidated_auth_is_absent_and_success_is_hashed(self) -> None:
        first = _Response(
            status=302,
            headers={"Location": "/final.mp4?signature=second-secret"},
        )
        payload = _mp4_bytes()
        second = _Response(payload, headers={"Content-Length": str(len(payload))})
        opener = _Opener(first, second)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            result = media.download_video(
                self._URL, destination, self._deadline(), opener=opener
            )

            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(result.path, destination)
            self.assertEqual(result.size_bytes, len(payload))
            self.assertEqual(result.sha256, hashlib.sha256(payload).hexdigest())
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())
            self.assertTrue(first.closed)
            self.assertTrue(second.closed)
            self.assertEqual(len(opener.calls), 2)
            for request, timeout in opener.calls:
                headers = {key.lower(): value for key, value in request.header_items()}
                self.assertNotIn("authorization", headers)
                self.assertGreater(timeout, 0)
                self.assertLessEqual(timeout, media.MEDIA_CALL_TIMEOUT_SECONDS)
            self.assertNotIn("signature", repr(result).lower())

    def test_cross_host_redirect_is_rejected_and_destination_is_preserved(self) -> None:
        redirect = _Response(
            status=307,
            headers={"Location": "https://evil.example/stolen.mp4?signature=secret"},
        )
        opener = _Opener(redirect)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            with self.assertRaises(media.MediaError) as ctx:
                media.download_video(
                    self._URL, destination, self._deadline(), opener=opener
                )
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())
            self.assertEqual(len(opener.calls), 1)
            self.assertTrue(redirect.closed)
            self.assertNotIn("secret", str(ctx.exception))

    def test_redirect_count_is_bounded(self) -> None:
        redirects = [
            _Response(status=302, headers={"Location": f"/r{index}.mp4"})
            for index in range(media.MAX_MEDIA_REDIRECTS + 1)
        ]
        opener = _Opener(*redirects)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(media.MediaError):
                media.download_video(
                    self._URL,
                    Path(tmp) / "source.mp4",
                    self._deadline(),
                    opener=opener,
                )
        self.assertEqual(len(opener.calls), media.MAX_MEDIA_REDIRECTS + 1)
        self.assertTrue(all(response.closed for response in redirects))

    def test_content_length_and_streamed_size_caps_preserve_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            media, "MAX_VIDEO_BYTES", 20
        ):
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            responses = (
                _Response(b"unused", headers={"Content-Length": "21"}),
                _Response(b"x" * 21),
            )
            for response in responses:
                with self.subTest(headers=response.headers):
                    with self.assertRaises(media.MediaError):
                        media.download_video(
                            self._URL,
                            destination,
                            self._deadline(),
                            opener=_Opener(response),
                        )
                    self.assertEqual(destination.read_bytes(), b"existing")
                    self.assertFalse((Path(tmp) / "source.mp4.part").exists())
                    self.assertTrue(response.closed)

    def test_truncated_declared_content_length_is_not_published(self) -> None:
        payload = _mp4_bytes()
        response = _Response(
            payload,
            headers={"Content-Length": str(len(payload) + 10)},
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            with self.assertRaises(media.MediaError) as ctx:
                media.download_video(
                    self._URL,
                    destination,
                    self._deadline(),
                    opener=_Opener(response),
                )
            self.assertEqual(ctx.exception.code, "bad_response")
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())

    def test_empty_or_non_mp4_payload_is_not_published(self) -> None:
        for payload in (b"", b"not an mp4 payload", b"\x00\x00\x00\x08free"):
            with tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp) / "source.mp4"
                destination.write_bytes(b"existing")
                with self.subTest(payload=payload):
                    with self.assertRaises(media.MediaError):
                        media.download_video(
                            self._URL,
                            destination,
                            self._deadline(),
                            opener=_Opener(_Response(payload)),
                        )
                    self.assertEqual(destination.read_bytes(), b"existing")
                    self.assertFalse((Path(tmp) / "source.mp4.part").exists())

    def test_timeout_before_or_during_read_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            opener = _Opener()
            with self.assertRaises(media.MediaError) as ctx:
                media.download_video(
                    self._URL,
                    destination,
                    time.monotonic() - 1,
                    opener=opener,
                )
            self.assertEqual(ctx.exception.code, "timeout")
            self.assertEqual(opener.calls, [])

            response = _Response(read_error=socket.timeout("signed-url-secret"))
            with self.assertRaises(media.MediaError) as ctx:
                media.download_video(
                    self._URL,
                    destination,
                    self._deadline(),
                    opener=_Opener(response),
                )
            self.assertEqual(ctx.exception.code, "timeout")
            self.assertNotIn("secret", str(ctx.exception))
            self.assertNotIn(
                "signed-url-secret", "".join(traceback.format_exception(ctx.exception))
            )
            self.assertIsNone(ctx.exception.__cause__)
            self.assertIsNone(ctx.exception.__context__)
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())
            self.assertTrue(response.closed)

    def test_stream_timeout_tracks_deadline_and_eof_cannot_publish_late(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            response = _Response(_mp4_bytes())
            with patch.object(
                media.time, "monotonic", side_effect=(0.0, 0.0, 9.75, 10.1)
            ):
                with self.assertRaises(media.MediaError) as ctx:
                    media.download_video(
                        self._URL,
                        destination,
                        10.0,
                        opener=_Opener(response),
                    )
            self.assertEqual(ctx.exception.code, "timeout")
            self.assertEqual(response.timeout_values, [0.25])
            self.assertFalse(destination.exists())

            late_eof = _Response(_mp4_bytes())
            with patch.object(
                media.time,
                "monotonic",
                side_effect=(0.0, 0.0, 0.0, 0.0, 10.1),
            ):
                with self.assertRaises(media.MediaError) as ctx:
                    media.download_video(
                        self._URL,
                        destination,
                        10.0,
                        opener=_Opener(late_eof),
                    )
            self.assertEqual(ctx.exception.code, "timeout")
            self.assertFalse(destination.exists())

    def test_cancellation_before_or_during_stream_preserves_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            opener = _Opener()
            with self.assertRaises(media.MediaCancelled):
                media.download_video(
                    self._URL,
                    destination,
                    self._deadline(),
                    opener=opener,
                    cancelled=lambda: True,
                )
            self.assertEqual(opener.calls, [])

            response = _Response(_mp4_bytes())
            with self.assertRaises(media.MediaCancelled):
                media.download_video(
                    self._URL,
                    destination,
                    self._deadline(),
                    opener=_Opener(response),
                    cancelled=lambda: response.read_calls >= 1,
                )
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())
            self.assertTrue(response.closed)

    def test_file_fsync_failure_cleans_part_and_preserves_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            with patch.object(media.os, "fsync", side_effect=OSError("disk failure")):
                with self.assertRaises(media.MediaError):
                    media.download_video(
                        self._URL,
                        destination,
                        self._deadline(),
                        opener=_Opener(_Response(_mp4_bytes())),
                    )
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())

    def test_directory_fsync_failure_rolls_back_existing_destination(self) -> None:
        real_fsync = os.fsync
        call_count = 0

        def fail_directory_sync(fd: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                real_fsync(fd)
                return
            raise OSError("directory sync failure")

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            media.os, "fsync", side_effect=fail_directory_sync
        ):
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            with self.assertRaises(media.MediaError):
                media.download_video(
                    self._URL,
                    destination,
                    self._deadline(),
                    opener=_Opener(_Response(_mp4_bytes())),
                )
            self.assertEqual(destination.read_bytes(), b"existing")
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())
            self.assertFalse((Path(tmp) / "source.mp4.previous").exists())

    def test_failed_rollback_preserves_previous_destination_backup(self) -> None:
        real_fsync = os.fsync
        real_replace = os.replace
        fsync_calls = 0
        replace_calls = 0

        def fail_directory_sync(fd: int) -> None:
            nonlocal fsync_calls
            fsync_calls += 1
            if fsync_calls == 1:
                real_fsync(fd)
                return
            raise OSError("directory sync failure")

        def fail_rollback(source, destination) -> None:
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 2:
                raise OSError("rollback failure")
            real_replace(source, destination)

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            media.os, "fsync", side_effect=fail_directory_sync
        ), patch.object(media.os, "replace", side_effect=fail_rollback):
            destination = Path(tmp) / "source.mp4"
            destination.write_bytes(b"existing")
            with self.assertRaises(media.MediaError):
                media.download_video(
                    self._URL,
                    destination,
                    self._deadline(),
                    opener=_Opener(_Response(_mp4_bytes())),
                )
            self.assertEqual(
                (Path(tmp) / "source.mp4.previous").read_bytes(), b"existing"
            )
            self.assertFalse((Path(tmp) / "source.mp4.part").exists())

    def test_success_is_private_and_fsyncs_before_atomic_publication(self) -> None:
        real_fsync = os.fsync
        calls: list[int] = []

        def recording_fsync(fd: int) -> None:
            calls.append(fd)
            real_fsync(fd)

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            media.os, "fsync", side_effect=recording_fsync
        ):
            destination = Path(tmp) / "source.mp4"
            media.download_video(
                self._URL,
                destination,
                self._deadline(),
                opener=_Opener(_Response(_mp4_bytes())),
            )
            self.assertTrue(calls)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
