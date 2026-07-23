from __future__ import annotations

import hashlib
import io
import os
import socket
import stat
import subprocess
import tempfile
import time
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
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


class _ProductionShapedResponse:
    """Models HTTPResponse clearing ``fp`` when Content-Length is exhausted."""

    def __init__(self, body: bytes, *, declared_length: bool = True) -> None:
        self.body = body
        self.status = 200
        self.headers = (
            {"Content-Length": str(len(body))} if declared_length else {}
        )
        self.socket_timeouts: list[float] = []
        sock = SimpleNamespace(settimeout=self.socket_timeouts.append)
        self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=sock))
        self.closed = False

    def read(self, amount: int) -> bytes:
        result, self.body = self.body[:amount], self.body[amount:]
        if not self.body:
            self.fp = None
        return result

    def close(self) -> None:
        self.closed = True


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
        malformed_ftyp = (8).to_bytes(4, "big") + b"ftyp" + b"x" * 8
        malformed_extended_ftyp = (
            (1).to_bytes(4, "big")
            + b"ftyp"
            + (16).to_bytes(8, "big")
            + b"x" * 8
        )
        for payload in (
            b"",
            b"not an mp4 payload",
            b"\x00\x00\x00\x08free",
            malformed_ftyp,
            malformed_extended_ftyp,
        ):
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

    def test_declared_length_stops_before_urllib_clears_response_socket(self) -> None:
        payload = _mp4_bytes()
        response = _ProductionShapedResponse(payload)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            result = media.download_video(
                self._URL,
                destination,
                self._deadline(),
                opener=_Opener(response),
            )
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(result.size_bytes, len(payload))
            self.assertTrue(response.socket_timeouts)
            self.assertTrue(response.closed)

    def test_closed_chunked_response_is_recognized_as_eof(self) -> None:
        payload = _mp4_bytes()
        response = _ProductionShapedResponse(payload, declared_length=False)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "source.mp4"
            result = media.download_video(
                self._URL,
                destination,
                self._deadline(),
                opener=_Opener(response),
            )
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(result.size_bytes, len(payload))

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


class _FrameRunner:
    def __init__(
        self,
        *,
        extra_output: bool = False,
        wrong_dimensions: bool = False,
        wrong_mode: bool = False,
    ) -> None:
        self.extra_output = extra_output
        self.wrong_dimensions = wrong_dimensions
        self.wrong_mode = wrong_mode
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command, *, deadline: float, cancelled=None) -> None:
        from PIL import Image

        del deadline, cancelled
        command = tuple(command)
        self.calls.append(command)
        count = int(command[command.index("-frames:v") + 1])
        filter_graph = command[command.index("-vf") + 1]
        crop = next(
            part for part in filter_graph.split(",") if part.startswith("crop=")
        )
        width, height = (int(value) for value in crop[5:].split(":", 2)[:2])
        if self.wrong_dimensions:
            width += 1
        pattern = Path(command[-1])
        for index in range(1, count + 1):
            color = (index % 256, (index * 3) % 256, (index * 7) % 256)
            mode = "RGBA" if self.wrong_mode else "RGB"
            fill = (*color, 255) if self.wrong_mode else color
            Image.new(mode, (width, height), fill).save(
                Path(str(pattern).replace("%04d", f"{index:04d}")),
                format="PNG",
            )
        if self.extra_output:
            (pattern.parent / "unexpected.txt").write_text("not a frame")


class _BlockingProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.killed:
            self.returncode = -9
            return self.returncode
        raise subprocess.TimeoutExpired(["ffmpeg"], timeout)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class _CompletedErrorProcess:
    def __init__(self, diagnostics: bytes) -> None:
        self.returncode: int | None = None
        self.stderr = io.BytesIO(diagnostics)

    def wait(self, timeout=None):
        self.returncode = 1
        return self.returncode


class AnimationProcessorTests(unittest.TestCase):
    def _paths(self, root: str) -> tuple[Path, Path, Path, Path]:
        base = Path(root)
        binary = base / "runtime" / "ffmpeg"
        binary.parent.mkdir()
        binary.write_bytes(b"test runtime")
        binary.chmod(0o700)
        source = base / "video" / "source.mp4"
        source.parent.mkdir()
        source.write_bytes(_mp4_bytes())
        work = base / ".work"
        work.mkdir()
        destination = base / "frames"
        return binary, source, work, destination

    def test_loop_formulas_reserve_the_exact_content_frame_counts(self) -> None:
        expected = {
            (80, "smooth"): 70,
            (200, "smooth"): 175,
            (186, "smooth"): 162,
            (80, "none"): 80,
            (200, "none"): 200,
            (186, "none"): 186,
            (80, "ping_pong"): 41,
            (200, "ping_pong"): 101,
            (186, "ping_pong"): 94,
        }
        for arguments, count in expected.items():
            with self.subTest(arguments=arguments):
                self.assertEqual(media.content_frame_count(*arguments), count)

    def test_command_is_local_argument_array_and_interpolates_before_cover_crop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary, source, work, _destination = self._paths(tmp)
            pattern = work / "frame-%04d.png"
            command = media.build_ffmpeg_frame_command(
                binary,
                source,
                pattern,
                width=160,
                height=36,
                content_frame_count=70,
            )
        self.assertIsInstance(command, tuple)
        self.assertEqual(command[0], str(binary.resolve()))
        self.assertIn("-nostdin", command)
        self.assertEqual(command[command.index("-protocol_whitelist") + 1], "file")
        self.assertEqual(command[command.index("-frames:v") + 1], "70")
        self.assertFalse(any("http://" in value or "https://" in value for value in command))
        filter_graph = command[command.index("-vf") + 1]
        self.assertLess(filter_graph.index("minterpolate="), filter_graph.index("scale="))
        self.assertLess(filter_graph.index("scale="), filter_graph.index("crop=160:36"))
        self.assertIn(
            "scale=w=160:h=36:force_original_aspect_ratio=increase",
            filter_graph,
        )

    def test_all_device_caps_publish_exact_validated_frames(self) -> None:
        cases = (
            (80, "smooth", 160, 36),
            (200, "none", 128, 32),
            (186, "ping_pong", 144, 36),
        )
        for frame_count, loop_mode, width, height in cases:
            with self.subTest(frame_count=frame_count, loop_mode=loop_mode), tempfile.TemporaryDirectory() as tmp:
                from PIL import Image

                binary, source, work, destination = self._paths(tmp)
                runner = _FrameRunner()
                result = media.process_video_frames(
                    source,
                    destination,
                    work,
                    ffmpeg_path=binary,
                    width=width,
                    height=height,
                    frame_count=frame_count,
                    loop_mode=loop_mode,
                    deadline=time.monotonic() + 30,
                    runner=runner,
                )
                names = [path.name for path in result.frame_paths]
                self.assertEqual(result.frame_count, frame_count)
                self.assertEqual(result.frame_paths[0], destination / "frame-0001.png")
                self.assertEqual(names, [f"frame-{index:04d}.png" for index in range(1, frame_count + 1)])
                self.assertEqual(len(list(destination.iterdir())), frame_count)
                self.assertEqual(len(runner.calls), 1)
                self.assertEqual(
                    int(runner.calls[0][runner.calls[0].index("-frames:v") + 1]),
                    media.content_frame_count(frame_count, loop_mode),
                )
                with Image.open(result.frame_paths[-1]) as image:
                    self.assertEqual(image.format, "PNG")
                    self.assertEqual(image.size, (width, height))
                self.assertEqual(list(work.iterdir()), [])
                self.assertEqual(source.read_bytes(), _mp4_bytes())

    def test_invalid_ffmpeg_output_preserves_existing_frames_and_cleans_work(self) -> None:
        for runner in (
            _FrameRunner(extra_output=True),
            _FrameRunner(wrong_dimensions=True),
            _FrameRunner(wrong_mode=True),
        ):
            with self.subTest(runner=runner.__dict__), tempfile.TemporaryDirectory() as tmp:
                binary, source, work, destination = self._paths(tmp)
                destination.mkdir()
                marker = destination / "existing.txt"
                marker.write_text("preserved")
                with self.assertRaises(media.MediaError) as raised:
                    media.process_video_frames(
                        source,
                        destination,
                        work,
                        ffmpeg_path=binary,
                        width=20,
                        height=5,
                        frame_count=80,
                        loop_mode="none",
                        deadline=time.monotonic() + 30,
                        runner=runner,
                    )
                self.assertEqual(raised.exception.code, "bad_output")
                self.assertEqual(marker.read_text(), "preserved")
                self.assertEqual(list(work.iterdir()), [])

    def test_interrupted_publication_backup_is_restored_before_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary, source, work, destination = self._paths(tmp)
            backup = destination.with_name(".frames.previous")
            backup.mkdir()
            marker = backup / "existing.txt"
            marker.write_text("preserved")
            with self.assertRaises(media.MediaError):
                media.process_video_frames(
                    source,
                    destination,
                    work,
                    ffmpeg_path=binary,
                    width=20,
                    height=5,
                    frame_count=80,
                    loop_mode="none",
                    deadline=time.monotonic() + 30,
                    runner=_FrameRunner(extra_output=True),
                )
            self.assertEqual((destination / "existing.txt").read_text(), "preserved")
            self.assertFalse(backup.exists())

    def test_cancellation_terminates_then_kills_without_shell(self) -> None:
        process = _BlockingProcess()
        calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
        checks = iter((False, True))

        def factory(command, **kwargs):
            calls.append((tuple(command), kwargs))
            return process

        with self.assertRaises(media.MediaCancelled):
            media.run_ffmpeg_command(
                ("/absolute/ffmpeg", "-nostdin", "-version"),
                deadline=time.monotonic() + 30,
                cancelled=lambda: next(checks),
                popen_factory=factory,
            )
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][1]["shell"], False)
        self.assertEqual(calls[0][1]["stdin"], subprocess.DEVNULL)
        self.assertEqual(calls[0][1]["stdout"], subprocess.DEVNULL)
        self.assertEqual(calls[0][1]["stderr"], subprocess.PIPE)

    def test_runner_rejects_provider_urls_before_starting_process(self) -> None:
        def must_not_start(command, **kwargs):
            raise AssertionError("URL-bearing FFmpeg command reached the process boundary")

        with self.assertRaises(media.MediaError) as raised:
            media.run_ffmpeg_command(
                (
                    "/absolute/ffmpeg",
                    "-nostdin",
                    "-i",
                    "https://vidgen.x.ai/signed.mp4?secret=value",
                ),
                deadline=time.monotonic() + 30,
                popen_factory=must_not_start,
            )
        self.assertEqual(raised.exception.code, "config")
        self.assertNotIn("secret", str(raised.exception))

    def test_failed_process_separates_bounded_diagnostics_from_stable_error(self) -> None:
        process = _CompletedErrorProcess(b"HEAD-MARKER" + b"x" * 20_000 + b"TAIL-MARKER")
        with self.assertRaises(media.MediaError) as raised:
            media.run_ffmpeg_command(
                ("/absolute/ffmpeg", "-nostdin", "-version"),
                deadline=time.monotonic() + 30,
                popen_factory=lambda command, **kwargs: process,
            )
        self.assertEqual(raised.exception.code, "processing")
        self.assertEqual("FFmpeg could not process the video", str(raised.exception))
        self.assertIn("TAIL-MARKER", raised.exception.process_diagnostics)
        self.assertNotIn("HEAD-MARKER", raised.exception.process_diagnostics)
        self.assertLessEqual(len(raised.exception.process_diagnostics), 8192)

    def test_timeout_stops_process_and_windows_uses_no_console_flag(self) -> None:
        unstarted = _BlockingProcess()
        with self.assertRaises(media.MediaError) as raised:
            media.run_ffmpeg_command(
                ("/absolute/ffmpeg", "-nostdin", "-version"),
                deadline=time.monotonic() - 1,
                popen_factory=lambda command, **kwargs: unstarted,
            )
        self.assertEqual(raised.exception.code, "timeout")
        self.assertFalse(unstarted.terminated, "expired work must not be spawned")

        running = _BlockingProcess()
        with patch.object(media.time, "monotonic", side_effect=(100.0, 101.0)):
            with self.assertRaises(media.MediaError) as raised:
                media.run_ffmpeg_command(
                    ("/absolute/ffmpeg", "-nostdin", "-version"),
                    deadline=100.5,
                    popen_factory=lambda command, **kwargs: running,
                )
        self.assertEqual(raised.exception.code, "timeout")
        self.assertTrue(running.terminated)
        self.assertTrue(running.killed)
        with patch.object(media.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            self.assertEqual(media.subprocess_creation_flags("nt"), 0x08000000)
        self.assertEqual(media.subprocess_creation_flags("posix"), 0)

    @unittest.skipUnless(
        os.environ.get("AM_CONFIGURATOR_TEST_FFMPEG"),
        "set AM_CONFIGURATOR_TEST_FFMPEG to exercise the prepared native runtime",
    )
    def test_prepared_current_host_runtime_processes_real_mp4(self) -> None:
        from PIL import Image

        binary = Path(os.environ["AM_CONFIGURATOR_TEST_FFMPEG"])
        fixture = Path(__file__).parent / "fixtures" / "tiny-motion.mp4"
        cases = (
            (80, "smooth", 15, 6),
            (200, "none", 18, 7),
            (186, "ping_pong", 16, 5),
        )
        for frame_count, loop_mode, width, height in cases:
            with self.subTest(frame_count=frame_count, loop_mode=loop_mode), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                work = base / ".work"
                work.mkdir()
                result = media.process_video_frames(
                    fixture.resolve(),
                    base / "frames",
                    work,
                    ffmpeg_path=binary.resolve(),
                    width=width,
                    height=height,
                    frame_count=frame_count,
                    loop_mode=loop_mode,
                    deadline=time.monotonic() + 60,
                )
                self.assertEqual(len(result.frame_paths), frame_count)
                self.assertEqual(list(work.iterdir()), [])
                for frame in result.frame_paths:
                    with Image.open(frame) as image:
                        self.assertEqual(image.format, "PNG")
                        self.assertEqual(image.mode, "RGB")
                        self.assertEqual(image.size, (width, height))


if __name__ == "__main__":
    unittest.main()
