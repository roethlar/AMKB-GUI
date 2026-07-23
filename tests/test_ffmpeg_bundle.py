"""Offline contract tests for the reproducible LGPL FFmpeg bundle helper."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import shutil
import stat
import tarfile
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from am_configurator import ffmpeg_runtime
from build_tools import ffmpeg_bundle, finalize_ffmpeg_bundle, prepare_ffmpeg


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "packaging" / "ffmpeg" / "manifest.json"
SOURCE_ROOT_NAME = "ffmpeg-8.1.2"


def _listing(*names: str) -> str:
    return "\n".join(f" ...... {name} synthetic capability" for name in names)


def _write_tar_xz(path: Path, entries: list[tuple[tarfile.TarInfo, bytes]]) -> None:
    with tarfile.open(path, "w:xz") as archive:
        for member, content in entries:
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content) if member.isreg() else None)


def _source_entries() -> list[tuple[tarfile.TarInfo, bytes]]:
    root = tarfile.TarInfo(SOURCE_ROOT_NAME)
    root.type = tarfile.DIRTYPE
    root.mode = 0o755
    configure = tarfile.TarInfo(f"{SOURCE_ROOT_NAME}/configure")
    configure.mode = 0o755
    return [(root, b""), (configure, b"#!/bin/sh\n")]


class _FakeRunner:
    def __init__(
        self,
        manifest: dict,
        *,
        missing_filter: str | None = None,
        missing_parser: str | None = None,
        extra_reported_args: tuple[str, ...] = (),
        platform_name: str = "linux",
        architecture: str = "x86_64",
    ) -> None:
        self.manifest = manifest
        self.missing_filter = missing_filter
        self.missing_parser = missing_parser
        self.extra_reported_args = extra_reported_args
        self.platform_name = platform_name
        self.architecture = architecture
        self.calls: list[tuple[tuple[str, ...], dict]] = []

    def __call__(self, args, **kwargs):
        args = tuple(str(value) for value in args)
        self.calls.append((args, kwargs))
        if "--verify" in args:
            fingerprint = self.manifest["source"]["release_key_fingerprint"]
            return ffmpeg_bundle.CommandResult(
                0, f"[GNUPG:] VALIDSIG {fingerprint} 2026 0 4 0 1 10 00", ""
            )
        if len(args) == 2 and args[1] == "--version":
            return ffmpeg_bundle.CommandResult(0, "synthetic cc 1.0\nextra detail\n", "")
        switch = args[1] if len(args) > 1 else ""
        required = self.manifest["required_capabilities"]
        if switch == "-version":
            return ffmpeg_bundle.CommandResult(
                0, f"ffmpeg version {self.manifest['ffmpeg_version']} Copyright", ""
            )
        if switch == "-buildconf":
            reported = [
                *self.manifest["configure_args"],
                "--prefix=/usr/local/am-configurator-ffmpeg",
                f"--arch={self.architecture}",
                *self.manifest["build_recipe"]["architecture_extra_args"][
                    self.architecture
                ],
                self.manifest["build_recipe"]["target_os_args"][self.platform_name],
                "--cc=/opt/am-tools/cc",
                "--ar=/opt/am-tools/ar",
                "--ranlib=/opt/am-tools/ranlib",
                "--strip=/opt/am-tools/strip",
                *self.extra_reported_args,
            ]
            if self.missing_parser is not None:
                for index, argument in enumerate(reported):
                    if argument.startswith("--enable-parser="):
                        parsers = argument.split("=", 1)[1].split(",")
                        parsers.remove(self.missing_parser)
                        reported[index] = "--enable-parser=" + ",".join(parsers)
            displayed = (
                f"{arg.split('=', 1)[0]}='{arg.split('=', 1)[1]}'"
                if "," in arg and "=" in arg
                else arg
                for arg in reported
            )
            configure = "\n".join(f"    {arg}" for arg in displayed)
            return ffmpeg_bundle.CommandResult(0, f"configuration:\n{configure}\n", "")
        category = {
            "-decoders": "decoders",
            "-parsers": "parsers",
            "-encoders": "encoders",
            "-demuxers": "demuxers",
            "-muxers": "muxers",
            "-protocols": "protocols",
            "-filters": "filters",
        }.get(switch)
        if category is not None:
            names = list(required[category])
            if category == "filters" and self.missing_filter in names:
                names.remove(self.missing_filter)
            if category == "demuxers" and names == ["mov"]:
                names = ["mov,mp4,m4a,3gp,3g2,mj2"]
            return ffmpeg_bundle.CommandResult(0, _listing(*names), "")
        return ffmpeg_bundle.CommandResult(0, "", "")


class _SigningRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args, **_kwargs):
        command = tuple(str(value) for value in args)
        self.calls.append(command)
        if "-s" in command:
            binary = Path(command[-1])
            binary.write_bytes(binary.read_bytes() + b"-signed")
            return ffmpeg_bundle.CommandResult(0, "", "")
        if "--verify" in command:
            return ffmpeg_bundle.CommandResult(0, "", "")
        if "-d" in command:
            return ffmpeg_bundle.CommandResult(
                0,
                "",
                "\n".join(
                    (
                        "Identifier=ffmpeg-test",
                        f"CDHash={'a' * 40}",
                        "Signature=adhoc",
                    )
                ),
            )
        raise AssertionError(command)


class FfmpegBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = ffmpeg_bundle.load_manifest(MANIFEST_PATH)
        self.assertEqual(ffmpeg_runtime.load_manifest(MANIFEST_PATH), self.manifest)

    def test_committed_manifest_pins_release_recipe_and_license_metadata(self) -> None:
        source = self.manifest["source"]
        self.assertEqual(self.manifest["schema_version"], 2)
        self.assertEqual(self.manifest["ffmpeg_version"], "8.1.2")
        self.assertEqual(
            source["url"], "https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz"
        )
        self.assertEqual(source["signature_url"], source["url"] + ".asc")
        self.assertEqual(
            source["sha256"],
            "464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c",
        )
        self.assertEqual(
            source["release_key_fingerprint"],
            "FCF986EA15E6E293A5644F10B4322F04D67658D8",
        )
        self.assertEqual(self.manifest["source_date_epoch"], 1781664417)
        self.assertEqual(self.manifest["runtime_attestation_schema_version"], 1)
        args = self.manifest["configure_args"]
        for required in (
            "--disable-everything",
            "--disable-autodetect",
            "--disable-network",
            "--disable-gpl",
            "--disable-nonfree",
            "--disable-version3",
            "--disable-avdevice",
            "--disable-swresample",
            "--enable-static",
            "--disable-shared",
            "--enable-pic",
            "--enable-ffmpeg",
        ):
            self.assertIn(required, args)
        for forbidden in (
            "--enable-gpl",
            "--enable-nonfree",
            "--enable-avcodec",
            "--enable-avformat",
            "--enable-avfilter",
            "--enable-avutil",
            "--enable-swscale",
            "--enable-swresample",
            "--disable-postproc",
        ):
            self.assertNotIn(forbidden, args)

        build_recipe = self.manifest["build_recipe"]
        self.assertEqual(
            build_recipe,
            {
                "build_prefix": "/usr/local/am-configurator-ffmpeg",
                "source_prefix": "/usr/src/ffmpeg-8.1.2",
                "prefix_arg": "--prefix={build_prefix}",
                "architecture_arg": "--arch={architecture}",
                "target_os_args": {
                    "macos": "--target-os=darwin",
                    "linux": "--target-os=linux",
                    "windows": "--target-os=mingw32",
                },
                "architecture_extra_args": {
                    "x86_64": ["--disable-x86asm"],
                    "arm64": [],
                },
                "tool_args": {
                    "cc": "--cc={path}",
                    "ar": "--ar={path}",
                    "ranlib": "--ranlib={path}",
                    "strip": "--strip={path}",
                },
                "cflags": [
                    "-O2",
                    "-ffile-prefix-map={source_dir}={source_prefix}",
                    "-fdebug-prefix-map={source_dir}={source_prefix}",
                ],
                "ldflags": {
                    "macos": ["-Wl,-dead_strip"],
                    "linux": ["-Wl,--gc-sections"],
                    "windows": ["-Wl,--gc-sections"],
                },
                "make_target": "ffmpeg",
                "tool_roles": ["cc", "ar", "ranlib", "strip"],
            },
        )

        readme = (MANIFEST_PATH.parent / "README.md").read_text("utf-8")
        license_text = (MANIFEST_PATH.parent / "LGPL-2.1.txt").read_text("utf-8")
        self.assertIn(source["url"], readme)
        self.assertIn(source["signature_url"], readme)
        self.assertIn(source["release_key_fingerprint"], readme)
        self.assertIn("written offer", readme.lower())
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 2.1, February 1999", license_text)

    def test_manifest_schema_is_exact_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            bad_values = []
            unknown = json.loads(json.dumps(self.manifest))
            unknown["unexpected"] = True
            bad_values.append(unknown)
            bad_hash = json.loads(json.dumps(self.manifest))
            bad_hash["source"]["sha256"] = "0" * 64
            bad_values.append(bad_hash)
            bad_recipe = json.loads(json.dumps(self.manifest))
            bad_recipe["configure_args"].append("--enable-gpl")
            bad_values.append(bad_recipe)
            missing_filter = json.loads(json.dumps(self.manifest))
            missing_filter["required_capabilities"]["filters"].remove("minterpolate")
            bad_values.append(missing_filter)
            for index, value in enumerate(bad_values):
                with self.subTest(index=index):
                    path.write_text(json.dumps(value), "utf-8")
                    with self.assertRaises(ffmpeg_bundle.BundleError):
                        ffmpeg_bundle.load_manifest(path)

    def test_shared_ffmpeg_reader_is_bounded_nofollow_and_identity_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            oversized = root / "oversized.json"
            oversized.write_bytes(b" " * (ffmpeg_runtime.MAX_FFMPEG_JSON_BYTES + 1))
            with (
                patch(
                    "am_configurator.ffmpeg_runtime.os.read",
                    side_effect=AssertionError("oversized input must not be read"),
                ),
                self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError),
            ):
                ffmpeg_runtime.read_bounded_json(oversized)

            payload = root / "payload.json"
            payload.write_text('{"ok": true}', "utf-8")
            link = root / "payload-link.json"
            try:
                link.symlink_to(payload)
            except (OSError, NotImplementedError):
                pass
            else:
                with self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError):
                    ffmpeg_runtime.read_bounded_json(link)
                with self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError):
                    ffmpeg_runtime.sha256_file(link)

            real_fstat = os.fstat
            calls = 0

            def changed_fstat(descriptor: int):
                nonlocal calls
                calls += 1
                details = real_fstat(descriptor)
                if calls != 2:
                    return details
                return SimpleNamespace(
                    st_mode=details.st_mode,
                    st_dev=details.st_dev,
                    st_ino=details.st_ino,
                    st_size=details.st_size,
                    st_mtime_ns=details.st_mtime_ns + 1,
                    st_ctime_ns=details.st_ctime_ns,
                    st_file_attributes=getattr(details, "st_file_attributes", 0),
                )

            with (
                patch("am_configurator.ffmpeg_runtime.os.fstat", changed_fstat),
                self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError),
            ):
                ffmpeg_runtime.sha256_file(payload)

            self.assertEqual({"ok": True}, ffmpeg_runtime.read_bounded_json(payload))
            self.assertEqual(
                hashlib.sha256(payload.read_bytes()).hexdigest(),
                ffmpeg_runtime.sha256_file(payload),
            )

    def test_shared_ffmpeg_reader_opens_windows_files_in_binary_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp) / "payload.json"
            payload.write_text('{"ok": true}\r\n', "utf-8")
            real_open = os.open
            binary_flag = 1 << 29
            observed_flags: list[int] = []

            def open_without_synthetic_flag(path, flags):
                observed_flags.append(flags)
                return real_open(path, flags & ~binary_flag)

            with (
                patch.object(ffmpeg_runtime.os, "O_BINARY", binary_flag, create=True),
                patch.object(
                    ffmpeg_runtime.os,
                    "open",
                    side_effect=open_without_synthetic_flag,
                ),
            ):
                self.assertEqual(
                    {"ok": True},
                    ffmpeg_runtime.read_bounded_json(payload),
                )

            self.assertEqual(1, len(observed_flags))
            self.assertTrue(observed_flags[0] & binary_flag)

    def test_shared_ffmpeg_reader_reports_only_the_failed_read_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp) / "source.tar.xz"
            payload.write_bytes(b"archive")
            with (
                patch.object(
                    ffmpeg_runtime.os,
                    "open",
                    side_effect=OSError("secret /private/path"),
                ),
                self.assertRaisesRegex(
                    ffmpeg_bundle.BundleError,
                    r"^FFmpeg file could not be read \(open\)$",
                ) as raised,
            ):
                ffmpeg_bundle.sha256_file(payload)

        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("/private/path", str(raised.exception))

    def test_shared_ffmpeg_reader_retries_a_transient_opened_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp) / "source.tar.xz"
            payload.write_bytes(b"archive")
            real_lstat = Path.lstat
            calls = 0

            def transient_lstat(candidate):
                nonlocal calls
                calls += 1
                details = real_lstat(candidate)
                if calls != 1:
                    return details
                return SimpleNamespace(
                    st_mode=details.st_mode,
                    st_dev=details.st_dev,
                    st_ino=details.st_ino,
                    st_size=details.st_size,
                    st_mtime_ns=details.st_mtime_ns + 1,
                    st_ctime_ns=details.st_ctime_ns,
                    st_file_attributes=getattr(details, "st_file_attributes", 0),
                )

            with (
                patch.object(Path, "lstat", transient_lstat),
                patch.object(ffmpeg_runtime.time, "sleep") as sleep,
            ):
                digest = ffmpeg_runtime.sha256_file(payload)

        self.assertEqual(hashlib.sha256(b"archive").hexdigest(), digest)
        sleep.assert_called_once_with(0.05)

    def test_shared_ffmpeg_reader_ignores_non_content_stat_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp) / "source.tar.xz"
            payload.write_bytes(b"archive")
            real_fstat = os.fstat
            calls = 0

            def metadata_different_fstat(descriptor: int):
                nonlocal calls
                calls += 1
                details = real_fstat(descriptor)
                if calls > 3:
                    return details
                return SimpleNamespace(
                    st_mode=details.st_mode ^ stat.S_IWUSR,
                    st_dev=details.st_dev,
                    st_ino=details.st_ino,
                    st_size=details.st_size,
                    st_mtime_ns=details.st_mtime_ns,
                    st_ctime_ns=details.st_ctime_ns + 1,
                    st_file_attributes=(
                        getattr(details, "st_file_attributes", 0)
                        ^ getattr(stat, "FILE_ATTRIBUTE_ARCHIVE", 0)
                    ),
                )

            with patch.object(
                ffmpeg_runtime.os,
                "fstat",
                side_effect=metadata_different_fstat,
            ):
                digest = ffmpeg_runtime.sha256_file(payload)

        self.assertEqual(hashlib.sha256(b"archive").hexdigest(), digest)

    def test_windows_gpg_runs_inside_the_profileless_msys2_shell(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(
            prepare_ffmpeg.subprocess,
            "run",
            return_value=completed,
        ) as run:
            runner = prepare_ffmpeg._runner_with_environment(
                {"GNUPGHOME": "/private/gnupg"},
                msys2_bash=Path("/msys2/usr/bin/bash.exe"),
                msys2_gpg=Path("/msys2/usr/bin/gpg.exe"),
            )
            result = runner(
                (
                    "/msys2/usr/bin/gpg.exe",
                    "--batch",
                    "--import",
                    "/workspace/ffmpeg-devel.asc",
                )
            )

        self.assertEqual(0, result.returncode)
        command = run.call_args.args[0]
        self.assertEqual("/msys2/usr/bin/bash.exe", command[0])
        self.assertEqual(("--noprofile", "--norc", "-lc"), command[1:4])
        self.assertIn("export PATH=/usr/bin:/mingw64/bin:$PATH", command[4])
        self.assertIn("export GNUPGHOME=/private/gnupg", command[4])
        self.assertIn(
            "exec /msys2/usr/bin/gpg.exe --batch --import "
            "/workspace/ffmpeg-devel.asc",
            command[4],
        )

    def test_build_readers_delegate_to_the_shared_ffmpeg_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "value.json"
            path.write_text("{}", "utf-8")
            with patch.object(
                ffmpeg_runtime,
                "read_bounded_json",
                return_value={"shared": True},
            ) as read_shared:
                self.assertEqual(
                    {"shared": True},
                    ffmpeg_bundle.read_bounded_json(path, "test JSON"),
                )
            read_shared.assert_called_once()
            with patch.object(
                ffmpeg_runtime,
                "sha256_file",
                return_value="a" * 64,
            ) as hash_shared:
                self.assertEqual("a" * 64, ffmpeg_bundle.sha256_file(path))
            hash_shared.assert_called_once()

    def test_recipe_hash_and_cache_key_are_deterministic(self) -> None:
        first = ffmpeg_bundle.recipe_sha256(self.manifest)
        second = ffmpeg_bundle.recipe_sha256(json.loads(json.dumps(self.manifest)))
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        key = ffmpeg_bundle.cache_key(self.manifest, "linux", "x86_64")
        self.assertEqual(
            key,
            "ffmpeg-8.1.2-linux-x86_64-"
            + self.manifest["source"]["sha256"]
            + "-"
            + first,
        )

        mutations = (
            ("build_prefix", "/different/prefix"),
            ("source_prefix", "/different/source"),
            ("prefix_arg", "--prefix={build_prefix}/changed"),
            ("architecture_arg", "--arch={architecture}-changed"),
            ("make_target", "different-target"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = json.loads(json.dumps(self.manifest))
                changed["build_recipe"][field] = value
                self.assertNotEqual(ffmpeg_runtime.recipe_sha256(changed), first)
        nested_mutations = (
            ("target_os_args", "linux", "--target-os=changed"),
            ("architecture_extra_args", "x86_64", ["--changed"]),
            ("tool_args", "cc", "--changed={path}"),
            ("ldflags", "linux", ["-Wl,--changed"]),
        )
        for field, key, value in nested_mutations:
            with self.subTest(field=field, key=key):
                changed = json.loads(json.dumps(self.manifest))
                changed["build_recipe"][field][key] = value
                self.assertNotEqual(ffmpeg_runtime.recipe_sha256(changed), first)
        for field in ("cflags", "tool_roles"):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(self.manifest))
                changed["build_recipe"][field] = [*changed["build_recipe"][field], "changed"]
                self.assertNotEqual(ffmpeg_runtime.recipe_sha256(changed), first)

    def test_source_archive_hash_and_detached_signature_are_verified_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "ffmpeg.tar.xz"
            signature = Path(temp) / "ffmpeg.tar.xz.asc"
            archive.write_bytes(b"pinned source bytes")
            signature.write_bytes(b"detached signature")
            manifest = json.loads(json.dumps(self.manifest))
            manifest["source"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
            ffmpeg_bundle.verify_source_archive(archive, manifest)
            archive.write_bytes(b"tampered")
            with self.assertRaises(ffmpeg_bundle.BundleError):
                ffmpeg_bundle.verify_source_archive(archive, manifest)

            archive.write_bytes(b"pinned source bytes")
            runner = _FakeRunner(manifest)
            ffmpeg_bundle.verify_source_signature(archive, signature, manifest, runner=runner)
            args, kwargs = runner.calls[0]
            self.assertIn("--no-auto-key-retrieve", args)
            self.assertEqual(args[-2:], (str(signature), str(archive)))
            self.assertNotIn("shell", kwargs)

    def test_signature_requires_one_exact_well_formed_pinned_validsig(self) -> None:
        archive = Path("/trusted/ffmpeg-8.1.2.tar.xz")
        signature = Path("/trusted/ffmpeg-8.1.2.tar.xz.asc")
        pinned = self.manifest["source"]["release_key_fingerprint"]

        def runner(stdout: str):
            def run(_args, **_kwargs):
                return ffmpeg_bundle.CommandResult(0, stdout, "")

            return run

        valid = f"[GNUPG:] VALIDSIG {pinned} 2026 0 4 0 1 10 00"
        ffmpeg_bundle.verify_source_signature(
            archive,
            signature,
            self.manifest,
            runner=runner(valid),
        )

        wrong = "A" * 40
        cases = {
            "absent": "[GNUPG:] GOODSIG synthetic release key",
            "wrong": f"[GNUPG:] VALIDSIG {wrong} 2026 0 4 0 1 10 00",
            "lowercase": f"[GNUPG:] VALIDSIG {pinned.lower()} 2026 0 4 0 1 10 00",
            "short": f"[GNUPG:] VALIDSIG {pinned[:-1]} 2026 0 4 0 1 10 00",
            "overlong": f"[GNUPG:] VALIDSIG {pinned}0 2026 0 4 0 1 10 00",
            "duplicate pinned": f"{valid}\n{valid}",
            "pinned plus wrong": (
                f"{valid}\n[GNUPG:] VALIDSIG {wrong} 2026 0 4 0 1 10 00"
            ),
        }
        for name, status_output in cases.items():
            with self.subTest(status=name):
                with self.assertRaises(ffmpeg_bundle.BundleError) as captured:
                    ffmpeg_bundle.verify_source_signature(
                        archive,
                        signature,
                        self.manifest,
                        runner=runner(status_output),
                    )
                self.assertEqual(
                    "FFmpeg detached signature did not match the release key",
                    str(captured.exception),
                )

    def test_source_extraction_is_private_fresh_and_rooted_at_the_pinned_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "source.tar.xz"
            destination = root / "private extraction"
            _write_tar_xz(archive, _source_entries())

            source = ffmpeg_bundle.extract_source_archive(archive, destination)

            self.assertEqual(source, destination.resolve() / SOURCE_ROOT_NAME)
            self.assertEqual((source / "configure").read_bytes(), b"#!/bin/sh\n")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
                self.assertTrue((source / "configure").stat().st_mode & stat.S_IXUSR)
            with self.assertRaises(ffmpeg_bundle.BundleError):
                ffmpeg_bundle.extract_source_archive(archive, destination)

    def test_source_extraction_rejects_unsafe_members_and_cleans_partial_output(self) -> None:
        unsafe_members: list[tuple[str, tarfile.TarInfo]] = []
        for label, name in (
            ("absolute", f"/{SOURCE_ROOT_NAME}/escape"),
            ("traversal", f"{SOURCE_ROOT_NAME}/../escape"),
            ("second root", "not-ffmpeg/source"),
            ("drive-qualified segment", f"{SOURCE_ROOT_NAME}/C:/escape"),
            ("drive-relative segment", f"{SOURCE_ROOT_NAME}/D:escape"),
            ("alternate data stream", f"{SOURCE_ROOT_NAME}/binary.exe:payload"),
            (
                "alternate data stream type",
                f"{SOURCE_ROOT_NAME}/binary.exe:payload:$DATA",
            ),
            ("unc path", rf"\\server\share\{SOURCE_ROOT_NAME}\escape"),
        ):
            unsafe_members.append((label, tarfile.TarInfo(name)))
        for label, member_type in (
            ("symbolic link", tarfile.SYMTYPE),
            ("hard link", tarfile.LNKTYPE),
            ("character device", tarfile.CHRTYPE),
            ("block device", tarfile.BLKTYPE),
            ("fifo", tarfile.FIFOTYPE),
        ):
            member = tarfile.TarInfo(f"{SOURCE_ROOT_NAME}/{label.replace(' ', '-')}")
            member.type = member_type
            member.linkname = f"{SOURCE_ROOT_NAME}/configure"
            unsafe_members.append((label, member))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (label, unsafe) in enumerate(unsafe_members):
                with self.subTest(label=label):
                    archive = root / f"unsafe-{index}.tar.xz"
                    destination = root / f"destination-{index}"
                    _write_tar_xz(archive, [*_source_entries(), (unsafe, b"unsafe")])
                    with self.assertRaises(ffmpeg_bundle.BundleError):
                        ffmpeg_bundle.extract_source_archive(archive, destination)
                    self.assertFalse(os.path.lexists(destination))

            malformed = root / "malformed.tar.xz"
            malformed.write_bytes(b"not an xz archive")
            destination = root / "malformed destination"
            with self.assertRaises(ffmpeg_bundle.BundleError):
                ffmpeg_bundle.extract_source_archive(malformed, destination)
            self.assertFalse(os.path.lexists(destination))

    def test_no_retired_llama_source_extractor_remains(self) -> None:
        self.assertFalse((ROOT / "build_tools" / "llama_bundle.py").exists())

    def test_runtime_inspection_requires_version_buildconf_and_every_capability(self) -> None:
        binary = Path("/trusted/ffmpeg")
        runner = _FakeRunner(self.manifest)
        inspection = ffmpeg_bundle.inspect_runtime(binary, self.manifest, runner=runner)
        self.assertEqual(inspection["ffmpeg_version"], "8.1.2")
        self.assertTrue(all(inspection["capabilities"].values()))
        self.assertIn("--arch=x86_64", inspection["reported_configure_args"])
        self.assertIn("--cc=/opt/am-tools/cc", inspection["reported_configure_args"])
        self.assertEqual(len(runner.calls), 8)
        self.assertNotIn("-parsers", {args[1] for args, _kwargs in runner.calls})
        for args, kwargs in runner.calls:
            self.assertEqual(args[0], str(binary))
            self.assertNotIn("shell", kwargs)
            self.assertLessEqual(kwargs["timeout"], ffmpeg_bundle.COMMAND_TIMEOUT_SECONDS)

        with self.assertRaises(ffmpeg_bundle.BundleError):
            ffmpeg_bundle.inspect_runtime(
                binary,
                self.manifest,
                runner=_FakeRunner(self.manifest, missing_filter="minterpolate"),
            )
        with self.assertRaises(ffmpeg_bundle.BundleError):
            ffmpeg_bundle.inspect_runtime(
                binary,
                self.manifest,
                runner=_FakeRunner(self.manifest, missing_parser="hevc"),
            )
        with self.assertRaises(ffmpeg_bundle.BundleError):
            ffmpeg_bundle.inspect_runtime(
                binary,
                self.manifest,
                runner=_FakeRunner(
                    self.manifest, extra_reported_args=("--enable-gpl",)
                ),
            )

    def test_runtime_attestation_binds_binary_recipe_platform_and_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "ffmpeg"
            binary.write_bytes(b"fake executable")
            inspection = ffmpeg_bundle.inspect_runtime(
                binary, self.manifest, runner=_FakeRunner(self.manifest)
            )
            attestation = root / "ffmpeg-runtime.json"
            ffmpeg_bundle.emit_runtime_attestation(
                binary,
                attestation,
                self.manifest,
                inspection,
                compiler_identity="synthetic clang",
                platform_name="linux",
                architecture="x86_64",
            )
            verified = ffmpeg_bundle.verify_runtime_attestation(
                binary,
                attestation,
                self.manifest,
                platform_name="linux",
                architecture="x86_64",
            )
            self.assertEqual(verified["binary_sha256"], hashlib.sha256(binary.read_bytes()).hexdigest())
            self.assertIn("--arch=x86_64", verified["reported_configure_args"])
            self.assertIn("--cc=/opt/am-tools/cc", verified["reported_configure_args"])
            self.assertEqual(
                ffmpeg_runtime.verify_runtime_attestation(
                    binary,
                    attestation,
                    self.manifest,
                    platform_name="linux",
                    architecture="x86_64",
                )["binary_sha256"],
                verified["binary_sha256"],
            )
            attestation_bytes = attestation.read_bytes()
            oversized_identity = json.loads(attestation_bytes)
            oversized_identity["compiler_identity"] = "x" * 1001
            attestation.write_text(json.dumps(oversized_identity), "utf-8")
            with self.assertRaises(ffmpeg_bundle.BundleError):
                ffmpeg_bundle.verify_runtime_attestation(
                    binary,
                    attestation,
                    self.manifest,
                    platform_name="linux",
                    architecture="x86_64",
                )
            attestation.write_bytes(attestation_bytes)
            binary.write_bytes(b"tampered executable")
            with self.assertRaises(ffmpeg_bundle.BundleError):
                ffmpeg_bundle.verify_runtime_attestation(
                    binary,
                    attestation,
                    self.manifest,
                    platform_name="linux",
                    architecture="x86_64",
                )

    def _macos_finalization_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        manifest_path = root / "packaging" / "ffmpeg" / "manifest.json"
        manifest_path.parent.mkdir(parents=True)
        shutil.copy2(MANIFEST_PATH, manifest_path)
        cache = (
            root
            / "build"
            / "ffmpeg"
            / ffmpeg_bundle.cache_key(self.manifest, "macos", "arm64")
            / "bin"
        )
        cache.mkdir(parents=True)
        prepared = cache / "ffmpeg"
        prepared.write_bytes(b"verified-prepared-ffmpeg")
        inspection = ffmpeg_bundle.inspect_runtime(
            prepared,
            self.manifest,
            runner=_FakeRunner(
                self.manifest,
                platform_name="macos",
                architecture="arm64",
            ),
        )
        prepared_attestation = cache / "ffmpeg-runtime.json"
        ffmpeg_bundle.emit_runtime_attestation(
            prepared,
            prepared_attestation,
            self.manifest,
            inspection,
            compiler_identity="synthetic apple clang",
            platform_name="macos",
            architecture="arm64",
        )

        app = root / "dist" / "AM Configurator.app"
        frameworks = app / "Contents" / "Frameworks" / "ffmpeg"
        resources = app / "Contents" / "Resources" / "ffmpeg"
        frameworks.mkdir(parents=True)
        resources.mkdir(parents=True)
        bundled = frameworks / "ffmpeg"
        bundled.write_bytes(prepared.read_bytes() + b"-signed")
        shutil.copy2(prepared_attestation, resources / "ffmpeg-runtime.json")
        shutil.copy2(manifest_path, resources / "manifest.json")
        return app, prepared, bundled

    def test_macos_finalization_binds_prepared_and_signed_runtime_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app, prepared, bundled = self._macos_finalization_fixture(root)
            runner = _SigningRunner()
            with patch.object(
                finalize_ffmpeg_bundle.platform,
                "machine",
                return_value="arm64",
            ):
                provenance_path = finalize_ffmpeg_bundle.finalize_macos_app(
                    app,
                    root=root,
                    runner=runner,
                )

            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            signed_attestation = ffmpeg_bundle.verify_runtime_attestation(
                bundled,
                app / "Contents" / "Resources" / "ffmpeg" / "ffmpeg-runtime.json",
                self.manifest,
                platform_name="macos",
                architecture="arm64",
            )
            self.assertEqual(1, provenance["schema_version"])
            self.assertEqual(
                hashlib.sha256(prepared.read_bytes()).hexdigest(),
                provenance["prepared_binary_sha256"],
            )
            self.assertEqual(
                hashlib.sha256(bundled.read_bytes()).hexdigest(),
                provenance["signed_binary_sha256"],
            )
            self.assertEqual("adhoc", provenance["signing_identity"])
            self.assertEqual("a" * 40, provenance["cdhash"])
            self.assertEqual(
                signed_attestation["capabilities"],
                provenance["capabilities"],
            )
            self.assertEqual(
                signed_attestation["reported_configure_args"],
                provenance["reported_configure_args"],
            )

    def test_macos_finalization_rejects_an_unrecognized_signed_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app, _prepared, bundled = self._macos_finalization_fixture(root)
            bundled.write_bytes(b"behavior-compatible-replacement-signed")
            with (
                patch.object(
                    finalize_ffmpeg_bundle.platform,
                    "machine",
                    return_value="arm64",
                ),
                self.assertRaises(ffmpeg_bundle.BundleError),
            ):
                finalize_ffmpeg_bundle.finalize_macos_app(
                    app,
                    root=root,
                    runner=_SigningRunner(),
                )
            self.assertFalse(
                (
                    app
                    / "Contents"
                    / "Resources"
                    / "ffmpeg"
                    / "ffmpeg-signing.json"
                ).exists()
            )

    def test_runtime_resolution_has_fixed_order_and_never_searches_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            platform_name, architecture = "linux", "x86_64"

            def prepare(binary: Path, marker: bytes) -> Path:
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.write_bytes(marker)
                if os.name != "nt":
                    binary.chmod(0o700)
                inspection = ffmpeg_bundle.inspect_runtime(
                    binary, self.manifest, runner=_FakeRunner(self.manifest)
                )
                ffmpeg_bundle.emit_runtime_attestation(
                    binary,
                    binary.with_name("ffmpeg-runtime.json"),
                    self.manifest,
                    inspection,
                    compiler_identity="synthetic",
                    platform_name=platform_name,
                    architecture=architecture,
                )
                return binary

            injected = prepare(root / "injected" / "ffmpeg", b"injected")
            override = prepare(root / "override" / "ffmpeg", b"override")
            dev_root = root / "cache"
            cached = prepare(
                dev_root
                / ffmpeg_runtime.cache_key(self.manifest, platform_name, architecture)
                / "bin"
                / "ffmpeg",
                b"cached",
            )
            bundle_root = root / "bundle"
            bundled = prepare(bundle_root / "ffmpeg" / "ffmpeg", b"bundled")
            common = dict(
                manifest=self.manifest,
                environment={"AM_CONFIGURATOR_FFMPEG": str(override), "PATH": str(root)},
                development_root=dev_root,
                bundle_root=bundle_root,
                platform_name=platform_name,
                architecture=architecture,
            )
            self.assertEqual(
                ffmpeg_runtime.resolve_ffmpeg(injected=injected, **common), injected.resolve()
            )
            self.assertEqual(ffmpeg_runtime.resolve_ffmpeg(**common), override.resolve())
            self.assertEqual(
                ffmpeg_runtime.resolve_ffmpeg(
                    **{**common, "environment": {"PATH": str(root)}}
                ),
                cached.resolve(),
            )
            cached.unlink()
            self.assertEqual(
                ffmpeg_runtime.resolve_ffmpeg(
                    **{**common, "environment": {"PATH": str(root)}}
                ),
                bundled.resolve(),
            )
            bundled.unlink()
            prepare(root / "ffmpeg", b"path executable")
            with self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError):
                ffmpeg_runtime.resolve_ffmpeg(
                    **{**common, "environment": {"PATH": str(root)}, "bundle_root": None}
                )

            symlink = root / "symlink-ffmpeg"
            try:
                symlink.symlink_to(injected)
            except (OSError, NotImplementedError):
                pass
            else:
                with self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError):
                    ffmpeg_runtime.resolve_ffmpeg(injected=symlink, **common)

    def test_app_runtime_entry_point_owns_source_and_frozen_manifest_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            platform_name, architecture = "linux", "x86_64"

            def prepare(binary: Path, marker: bytes) -> Path:
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.write_bytes(marker)
                if os.name != "nt":
                    binary.chmod(0o700)
                inspection = ffmpeg_bundle.inspect_runtime(
                    binary, self.manifest, runner=_FakeRunner(self.manifest)
                )
                ffmpeg_bundle.emit_runtime_attestation(
                    binary,
                    binary.with_name("ffmpeg-runtime.json"),
                    self.manifest,
                    inspection,
                    compiler_identity="synthetic",
                    platform_name=platform_name,
                    architecture=architecture,
                )
                return binary

            dev_root = root / "cache"
            cached = prepare(
                dev_root
                / ffmpeg_runtime.cache_key(self.manifest, platform_name, architecture)
                / "bin"
                / "ffmpeg",
                b"cached",
            )
            self.assertEqual(
                ffmpeg_runtime.get_ffmpeg_runtime(
                    environment={},
                    development_root=dev_root,
                    platform_name=platform_name,
                    architecture=architecture,
                ),
                cached.resolve(),
            )
            override = prepare(root / "override" / "ffmpeg", b"override")
            self.assertEqual(
                ffmpeg_runtime.get_ffmpeg_runtime(
                    environment={"AM_CONFIGURATOR_FFMPEG": str(override)},
                    development_root=dev_root,
                    platform_name=platform_name,
                    architecture=architecture,
                ),
                override.resolve(),
            )

            frozen_root = root / "frozen"
            frozen_manifest = frozen_root / "ffmpeg" / "manifest.json"
            frozen_manifest.parent.mkdir(parents=True)
            frozen_manifest.write_bytes(MANIFEST_PATH.read_bytes())
            bundled = prepare(frozen_root / "ffmpeg" / "ffmpeg", b"bundled")
            with patch.object(ffmpeg_runtime.sys, "_MEIPASS", str(frozen_root), create=True):
                self.assertEqual(
                    ffmpeg_runtime.get_ffmpeg_runtime(
                        environment={},
                        platform_name=platform_name,
                        architecture=architecture,
                    ),
                    bundled.resolve(),
                )

    def test_frozen_macos_layout_accepts_only_an_internal_attestation_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frameworks = root / "Contents" / "Frameworks"
            resources = root / "Contents" / "Resources"
            binary = frameworks / "ffmpeg" / "ffmpeg"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"bundled")
            if os.name != "nt":
                binary.chmod(0o700)
            inspection = ffmpeg_bundle.inspect_runtime(
                binary, self.manifest, runner=_FakeRunner(self.manifest)
            )
            resource_attestation = resources / "ffmpeg" / "ffmpeg-runtime.json"
            resource_attestation.parent.mkdir(parents=True)
            ffmpeg_bundle.emit_runtime_attestation(
                binary,
                resource_attestation,
                self.manifest,
                inspection,
                compiler_identity="synthetic",
                platform_name="linux",
                architecture="x86_64",
            )
            resource_manifest = resources / "ffmpeg" / "manifest.json"
            resource_manifest.write_bytes(MANIFEST_PATH.read_bytes())
            bundled_manifest = frameworks / "ffmpeg" / "manifest.json"
            bundled_manifest.symlink_to(resource_manifest)
            attestation_link = binary.with_name("ffmpeg-runtime.json")
            attestation_link.symlink_to(resource_attestation)

            with patch.object(ffmpeg_runtime.sys, "_MEIPASS", str(frameworks), create=True):
                self.assertEqual(
                    ffmpeg_runtime.get_ffmpeg_runtime(
                        environment={}, platform_name="linux", architecture="x86_64"
                    ),
                    binary.resolve(),
                )
                bundled_manifest.unlink()
                outside_manifest = root / "outside-manifest.json"
                outside_manifest.write_bytes(resource_manifest.read_bytes())
                bundled_manifest.symlink_to(outside_manifest)
                with self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError):
                    ffmpeg_runtime.get_ffmpeg_runtime(
                        environment={}, platform_name="linux", architecture="x86_64"
                    )
                bundled_manifest.unlink()
                bundled_manifest.symlink_to(resource_manifest)
                attestation_link.unlink()
                outside = root / "outside-attestation.json"
                outside.write_bytes(resource_attestation.read_bytes())
                attestation_link.symlink_to(outside)
                with self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError):
                    ffmpeg_runtime.get_ffmpeg_runtime(
                        environment={}, platform_name="linux", architecture="x86_64"
                    )

    def test_build_plan_uses_argument_arrays_reproducible_flags_and_no_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source-tree"
            output = Path(temp) / "output tree"
            source.mkdir()
            tools = {
                "cc": Path("/opt/am-tools/cc"),
                "ar": Path("/opt/am-tools/ar"),
                "ranlib": Path("/opt/am-tools/ranlib"),
                "strip": Path("/opt/am-tools/strip"),
            }
            plan = ffmpeg_bundle.build_command_plan(
                source,
                output,
                self.manifest,
                platform_name="linux",
                architecture="x86_64",
                jobs=3,
                tool_paths=tools,
            )
            self.assertEqual(len(plan), 2)
            self.assertTrue(all(isinstance(command.args, tuple) for command in plan))
            configure = plan[0]
            self.assertEqual(configure.args[0], str(source.resolve() / "configure"))
            self.assertIn("--disable-network", configure.args)
            self.assertIn("--disable-gpl", configure.args)
            self.assertIn("--disable-nonfree", configure.args)
            self.assertIn("--disable-version3", configure.args)
            self.assertIn("--enable-pic", configure.args)
            self.assertIn("--disable-x86asm", configure.args)
            self.assertIn(
                f"--prefix={self.manifest['build_recipe']['build_prefix']}",
                configure.args,
            )
            for role, path in tools.items():
                option = "cc" if role == "cc" else role
                self.assertIn(f"--{option}={path}", configure.args)
            self.assertEqual(configure.environment["SOURCE_DATE_EPOCH"], "1781664417")
            self.assertEqual(
                shlex.split(configure.environment["CFLAGS"]),
                [
                    "-O2",
                    f"-ffile-prefix-map={source.resolve()}=/usr/src/ffmpeg-8.1.2",
                    f"-fdebug-prefix-map={source.resolve()}=/usr/src/ffmpeg-8.1.2",
                ],
            )
            self.assertNotIn(str(ROOT), " ".join(configure.args))
            self.assertNotIn(str(ROOT), json.dumps(configure.environment))
            self.assertEqual(plan[1].args, ("make", "-j3", "ffmpeg"))
            flattened = " ".join(arg for command in plan for arg in command.args).lower()
            self.assertNotIn("curl", flattened)
            self.assertNotIn("wget", flattened)
            self.assertNotIn("http://", flattened)
            self.assertNotIn("https://", flattened)

            windows_tools = {
                "cc": Path("/msys2/mingw64/bin/gcc.exe"),
                "ar": Path("/msys2/mingw64/bin/ar.exe"),
                "ranlib": Path("/msys2/mingw64/bin/ranlib.exe"),
                "strip": Path("/msys2/mingw64/bin/strip.exe"),
            }
            windows_plan = ffmpeg_bundle.build_command_plan(
                source,
                output,
                self.manifest,
                platform_name="windows",
                architecture="x86_64",
                jobs=2,
                msys2_bash=Path("/msys2/usr/bin/bash.exe"),
                tool_paths=windows_tools,
            )
            self.assertEqual(2, len(windows_plan))
            for command in windows_plan:
                self.assertEqual("/msys2/usr/bin/bash.exe", command.args[0])
                self.assertEqual(("--noprofile", "--norc", "-lc"), command.args[1:4])
                self.assertTrue(
                    command.args[4].startswith(
                        "export PATH=/usr/bin:/mingw64/bin:$PATH && cd "
                    )
                )
            self.assertTrue(windows_plan[1].args[4].endswith("make -j2 ffmpeg.exe"))

            mac_plan = ffmpeg_bundle.build_command_plan(
                source,
                output,
                self.manifest,
                platform_name="macos",
                architecture="arm64",
                jobs=1,
                tool_paths=tools,
            )
            self.assertIn("--arch=arm64", mac_plan[0].args)
            self.assertNotIn("CPPFLAGS", mac_plan[0].environment)
            self.assertNotIn("--disable-x86asm", mac_plan[0].args)
            self.assertEqual(mac_plan[0].environment["LDFLAGS"], "-Wl,-dead_strip")
            with self.assertRaises(ffmpeg_bundle.BundleError):
                ffmpeg_bundle.build_command_plan(
                    ROOT / "build" / "ffmpeg" / "source",
                    output,
                    self.manifest,
                    platform_name="macos",
                    architecture="arm64",
                    jobs=1,
                    tool_paths=tools,
                )
            spaced_source = Path(temp) / "source tree"
            spaced_source.mkdir()
            with self.assertRaises(ffmpeg_bundle.BundleError):
                ffmpeg_bundle.build_command_plan(
                    spaced_source,
                    output,
                    self.manifest,
                    platform_name="macos",
                    architecture="arm64",
                    jobs=1,
                    tool_paths=tools,
                )

    def test_verified_archive_build_extracts_its_own_fresh_source_then_attests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "ffmpeg.tar.xz"
            signature = root / "ffmpeg.tar.xz.asc"
            extraction = root / "fresh-extraction"
            output = root / "output"
            _write_tar_xz(archive, _source_entries())
            signature.write_bytes(b"synthetic signature")
            tools = {
                "cc": Path("/opt/am-tools/cc"),
                "ar": Path("/opt/am-tools/ar"),
                "ranlib": Path("/opt/am-tools/ranlib"),
                "strip": Path("/opt/am-tools/strip"),
            }
            fake_runner = _FakeRunner(self.manifest)

            def runner(args, **kwargs):
                if tuple(args) == ("make", "-j2", "ffmpeg"):
                    built_binary = kwargs["cwd"] / "ffmpeg"
                    built_binary.write_bytes(b"synthetic built executable")
                    if os.name != "nt":
                        built_binary.chmod(0o700)
                return fake_runner(args, **kwargs)

            with (
                patch.object(ffmpeg_bundle, "verify_source_archive") as verify_hash,
                patch.object(ffmpeg_bundle, "verify_source_signature") as verify_signature,
            ):
                result = ffmpeg_bundle.build_verified_archive(
                    archive,
                    signature,
                    extraction,
                    output,
                    self.manifest,
                    runner=runner,
                    jobs=2,
                    platform_name="linux",
                    architecture="x86_64",
                    tool_paths=tools,
                )
            verify_hash.assert_called_once_with(archive, self.manifest)
            verify_signature.assert_called_once_with(
                archive, signature, self.manifest, runner=runner, gpg="gpg"
            )
            binary = output.resolve() / "bin" / "ffmpeg"
            self.assertEqual(result, binary.resolve())
            self.assertEqual(len(fake_runner.calls), 11)
            extracted_source = extraction.resolve() / SOURCE_ROOT_NAME
            self.assertEqual(
                fake_runner.calls[0][0][0], str(extracted_source / "configure")
            )
            self.assertEqual(fake_runner.calls[1][0], ("make", "-j2", "ffmpeg"))
            self.assertEqual(fake_runner.calls[10][0], ("/opt/am-tools/cc", "--version"))
            self.assertEqual(binary.read_bytes(), b"synthetic built executable")
            self.assertFalse(os.path.lexists(extraction))
            attestation = binary.with_name("ffmpeg-runtime.json")
            self.assertTrue(attestation.is_file())
            self.assertEqual(
                json.loads(attestation.read_text("utf-8"))["compiler_identity"],
                "synthetic cc 1.0",
            )
            ffmpeg_bundle.verify_runtime_attestation(
                binary,
                attestation,
                self.manifest,
                platform_name="linux",
                architecture="x86_64",
            )

    def test_build_cli_has_no_caller_supplied_source_tree_escape_hatch(self) -> None:
        binary = Path("/prepared/ffmpeg")
        args = [
            "build",
            "--archive",
            "/sources/ffmpeg-8.1.2.tar.xz",
            "--signature",
            "/sources/ffmpeg-8.1.2.tar.xz.asc",
            "--extract-dir",
            "/private/tmp/am-ffmpeg-fresh",
            "--output-dir",
            "/cache/ffmpeg",
            "--platform",
            "macos",
            "--architecture",
            "arm64",
            "--cc",
            "/usr/bin/cc",
            "--ar",
            "/usr/bin/ar",
            "--ranlib",
            "/usr/bin/ranlib",
            "--strip",
            "/usr/bin/strip",
        ]
        @contextmanager
        def isolated(_key, _gpg):
            yield object(), "/tools/gpg"

        with (
            patch.object(ffmpeg_bundle, "_isolated_gpg_runner", isolated),
            patch.object(
                ffmpeg_bundle, "build_verified_archive", return_value=binary
            ) as build,
        ):
            self.assertEqual(ffmpeg_bundle.main(args), 0)
        self.assertEqual(build.call_args.args[:3], (Path(args[2]), Path(args[4]), Path(args[6])))
        self.assertNotIn("--source-dir", args)
        with self.assertRaises(SystemExit):
            ffmpeg_bundle.main([*args, "--source-dir", "/untrusted/source"])

    def test_direct_cli_gpg_context_is_private_and_ephemeral(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            public_key = Path(temporary) / "ffmpeg-devel.asc"
            public_key.write_text("pinned public key", encoding="utf-8")
            calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
            keyring: Path | None = None

            def runner(args, **kwargs):
                nonlocal keyring
                environment = kwargs["env"]
                keyring = Path(environment["GNUPGHOME"])
                self.assertTrue(keyring.is_dir())
                self.assertNotEqual("/user/keyring", str(keyring))
                if os.name != "nt":
                    self.assertEqual(0o700, stat.S_IMODE(keyring.stat().st_mode))
                calls.append((tuple(args), kwargs))
                return ffmpeg_bundle.CommandResult(0, "", "")

            with (
                patch.dict(os.environ, {"GNUPGHOME": "/user/keyring"}),
                patch.object(ffmpeg_bundle.shutil, "which", return_value="/tools/gpg"),
                patch.object(ffmpeg_bundle, "_default_runner", side_effect=runner),
            ):
                with ffmpeg_bundle._isolated_gpg_runner(
                    public_key, "gpg"
                ) as (isolated_runner, gpg):
                    self.assertEqual("/tools/gpg", gpg)
                    isolated_runner((gpg, "--batch", "--version"))

            self.assertIsNotNone(keyring)
            self.assertFalse(keyring.exists())
            self.assertEqual(
                ("/tools/gpg", "--batch", "--import", str(public_key.resolve())),
                calls[0][0],
            )
            self.assertEqual(("/tools/gpg", "--batch", "--version"), calls[1][0])
            self.assertEqual(calls[0][1]["env"]["GNUPGHOME"], calls[1][1]["env"]["GNUPGHOME"])

    def test_every_direct_cli_path_uses_the_isolated_keyring(self) -> None:
        public_key = Path("/trusted/ffmpeg-devel.asc")
        isolated_calls: list[tuple[Path, str]] = []
        isolated_runner = object()

        @contextmanager
        def isolated(key, gpg):
            isolated_calls.append((Path(key), str(gpg)))
            yield isolated_runner, "/tools/gpg"

        verify_args = [
            "verify-source",
            "--archive",
            "/sources/ffmpeg.tar.xz",
            "--signature",
            "/sources/ffmpeg.tar.xz.asc",
            "--public-key",
            str(public_key),
        ]
        build_args = [
            "build",
            "--archive",
            "/sources/ffmpeg.tar.xz",
            "--signature",
            "/sources/ffmpeg.tar.xz.asc",
            "--public-key",
            str(public_key),
            "--extract-dir",
            "/private/tmp/ffmpeg-source",
            "--output-dir",
            "/cache/ffmpeg",
        ]
        with (
            patch.object(ffmpeg_bundle, "_isolated_gpg_runner", isolated, create=True),
            patch.object(ffmpeg_bundle, "verify_source_archive") as verify_hash,
            patch.object(ffmpeg_bundle, "verify_source_signature") as verify_signature,
            patch.object(
                ffmpeg_bundle,
                "build_verified_archive",
                return_value=Path("/prepared/ffmpeg"),
            ) as build,
        ):
            self.assertEqual(0, ffmpeg_bundle.main(verify_args))
            self.assertEqual(0, ffmpeg_bundle.main(build_args))

        self.assertEqual([(public_key, "gpg"), (public_key, "gpg")], isolated_calls)
        verify_hash.assert_called_once()
        self.assertIs(verify_signature.call_args.kwargs["runner"], isolated_runner)
        self.assertEqual("/tools/gpg", verify_signature.call_args.kwargs["gpg"])
        self.assertIs(build.call_args.kwargs["runner"], isolated_runner)
        self.assertEqual("/tools/gpg", build.call_args.kwargs["gpg"])

    def test_developer_override_must_be_absolute_and_attested(self) -> None:
        with self.assertRaises(ffmpeg_runtime.FfmpegRuntimeError):
            ffmpeg_runtime.resolve_ffmpeg(
                manifest=self.manifest,
                environment={"AM_CONFIGURATOR_FFMPEG": "relative/ffmpeg"},
                development_root=None,
                bundle_root=None,
                platform_name="linux",
                architecture="x86_64",
            )


if __name__ == "__main__":
    unittest.main()
