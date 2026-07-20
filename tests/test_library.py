from __future__ import annotations

import hashlib
import errno
import json
import multiprocessing
import os
import shutil
import stat
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from am_configurator import library as library_module
from am_configurator.library import (
    AssetNotFoundError,
    GeneratedAssetLibrary,
    InvalidIdentifierError,
    LibraryRootError,
    ManifestError,
)


def _holding_manifest_process(
    root: str,
    job_id: str,
    entered: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
    completed: multiprocessing.synchronize.Event,
) -> None:
    library = GeneratedAssetLibrary(root, minimum_free_bytes=1)

    def increment(current: dict) -> None:
        entered.set()
        if not release.wait(10):
            raise TimeoutError("test process was not released")
        current["progress"]["completed"] += 1

    library.update_manifest(job_id, increment)
    completed.set()


def _waiting_manifest_process(
    root: str,
    job_id: str,
    attempting: multiprocessing.synchronize.Event,
    completed: multiprocessing.synchronize.Event,
) -> None:
    library = GeneratedAssetLibrary(root, minimum_free_bytes=1)

    def increment(current: dict) -> None:
        current["progress"]["completed"] += 1

    attempting.set()
    library.update_manifest(job_id, increment)
    completed.set()


class GeneratedAssetLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.root = self.base / "generated"
        self.library = GeneratedAssetLibrary(
            self.root,
            minimum_free_bytes=1,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _create_job(self, **overrides: object) -> dict:
        values = {
            "prompt": "A calm ember ribbon",
            "target": {
                "family": "CB",
                "raster": {"width": 20, "height": 9},
                "targets": ["display"],
            },
            "models": {
                "interpreter": "grok-4.5",
                "concept": "grok-imagine-image",
                "video": "grok-imagine-video-1.5",
            },
            "loop_mode": "smooth",
        }
        values.update(overrides)
        return self.library.create_job(**values)

    def _job_dir(self, job_id: str, root: Path | None = None) -> Path:
        return (root or self.root).resolve() / "jobs" / job_id

    def _write_manifest_directly(self, job_id: str, manifest: dict) -> None:
        path = self._job_dir(job_id) / "manifest.json"
        path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    @staticmethod
    def _try_symlink(target: Path, link: Path, *, directory: bool = False) -> bool:
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError):
            return False
        return True

    def test_root_preflight_requires_configuration_and_never_falls_back(self) -> None:
        missing = GeneratedAssetLibrary(None, historical_roots=[self.base / "old"])
        with self.assertRaisesRegex(LibraryRootError, "configured"):
            missing.preflight()
        self.assertFalse((self.base / "old" / "jobs").exists())

        with self.assertRaisesRegex(LibraryRootError, "absolute"):
            GeneratedAssetLibrary(Path("relative-library")).preflight()

    def test_root_preflight_canonicalizes_probes_and_checks_free_space(self) -> None:
        spelling = self.base / "parent" / ".." / "generated"
        probe = GeneratedAssetLibrary(spelling, minimum_free_bytes=1)
        self.assertEqual(self.root.resolve(), probe.preflight())
        self.assertTrue((self.root / "jobs").is_dir())
        self.assertEqual([], list(self.root.glob(".am-write-probe-*")))

        no_space = GeneratedAssetLibrary(
            self.base / "full",
            minimum_free_bytes=50,
            disk_usage=lambda _path: SimpleNamespace(total=100, used=60, free=40),
        )
        with self.assertRaisesRegex(LibraryRootError, "free space"):
            no_space.preflight()

        unwritable = GeneratedAssetLibrary(self.base / "denied", minimum_free_bytes=1)
        with patch(
            "am_configurator.library._run_write_probe",
            side_effect=OSError("/private/path: permission denied"),
        ):
            with self.assertRaises(LibraryRootError) as raised:
                unwritable.preflight()
        self.assertNotIn("/private/path", str(raised.exception))

    def test_private_uuid_job_creation_has_complete_schema_and_directories(self) -> None:
        manifest = self._create_job()
        job_id = manifest["job_id"]
        self.assertEqual(job_id, str(uuid.UUID(job_id)))
        self.assertEqual(1, manifest["schema_version"])
        self.assertEqual("created", manifest["status"])
        self.assertEqual("preflight", manifest["phase"])
        self.assertEqual("smooth", manifest["loop_mode"])

        job_dir = self._job_dir(job_id)
        for relative in (
            "manifest.json",
            "concepts",
            "video",
            "frames",
            "preview",
            "result",
            ".work",
        ):
            self.assertTrue((job_dir / relative).exists(), relative)

        if os.name != "nt":
            for directory in (self.root, self.root / "jobs", job_dir):
                self.assertEqual(0o700, stat.S_IMODE(directory.stat().st_mode))
            for relative in ("concepts", "video", "frames", "preview", "result", ".work"):
                self.assertEqual(
                    0o700,
                    stat.S_IMODE((job_dir / relative).stat().st_mode),
                )
            self.assertEqual(
                0o600,
                stat.S_IMODE((job_dir / "manifest.json").stat().st_mode),
            )
            self.assertEqual(0o600, stat.S_IMODE((job_dir / ".lock").stat().st_mode))

    @unittest.skipIf(os.name == "nt", "directory fsync is not exposed on Windows")
    def test_directory_fsync_surfaces_real_io_errors_only(self) -> None:
        with patch(
            "am_configurator.library.os.open",
            side_effect=OSError(errno.EIO, "simulated directory I/O failure"),
        ):
            with self.assertRaises(OSError) as raised:
                library_module._fsync_directory(self.root)
        self.assertEqual(errno.EIO, raised.exception.errno)

        with patch(
            "am_configurator.library.os.open",
            side_effect=OSError(errno.EINVAL, "directory fsync unsupported"),
        ):
            library_module._fsync_directory(self.root)

    def test_windows_private_mode_runtime_boundaries(self) -> None:
        cases = {
            (3, 10, 99): False,
            (3, 11, 9): False,
            (3, 11, 10): True,
            (3, 12, 3): False,
            (3, 12, 4): True,
            (3, 13, 0): True,
            (3, 14, 0): True,
        }
        for version, expected in cases.items():
            with self.subTest(version=version):
                self.assertEqual(
                    expected,
                    library_module._windows_private_mode_supported(version),
                )

    def test_preflight_rejects_old_windows_before_touching_root(self) -> None:
        guarded_root = self.base / "old-windows-must-not-exist"
        guarded = GeneratedAssetLibrary(guarded_root, minimum_free_bytes=1)
        with (
            patch("am_configurator.library.os.name", "nt"),
            patch("am_configurator.library.sys.version_info", (3, 12, 3)),
        ):
            with self.assertRaisesRegex(LibraryRootError, "3.12.4"):
                guarded.preflight()
        self.assertFalse(guarded_root.exists())

    def test_uuid_collisions_never_reuse_or_delete_existing_jobs_or_assets(self) -> None:
        self.library.preflight()
        collision = uuid.uuid4()
        fresh = uuid.uuid4()
        existing_job_dir = self.root / "jobs" / str(collision)
        existing_job_dir.mkdir(mode=0o700)
        sentinel = existing_job_dir / "owner-data.bin"
        sentinel.write_bytes(b"do not touch")

        with (
            patch("am_configurator.library._run_write_probe"),
            patch("am_configurator.library.uuid.uuid4", side_effect=[collision, fresh]),
        ):
            created = self.library.create_job(prompt="collision-safe")
        self.assertEqual(str(fresh), created["job_id"])
        self.assertEqual(b"do not touch", sentinel.read_bytes())

        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        with patch("am_configurator.library.uuid.uuid4", return_value=first_id):
            first = self.library.bank_asset(
                created["job_id"],
                kind="concept",
                data=b"\x89PNG\r\n\x1a\nfirst",
                mime_type="image/png",
                origin="xai",
            )
        first_path = self.library.resolve_asset(created["job_id"], first["asset_id"]).path
        with patch(
            "am_configurator.library.uuid.uuid4",
            side_effect=[first_id, second_id],
        ):
            second = self.library.bank_asset(
                created["job_id"],
                kind="concept",
                data=b"\x89PNG\r\n\x1a\nsecond",
                mime_type="image/png",
                origin="xai",
            )
        self.assertEqual(str(second_id), second["asset_id"])
        self.assertEqual(b"\x89PNG\r\n\x1a\nfirst", first_path.read_bytes())

    def test_manifest_updates_are_atomic_and_serialized_by_job_lock(self) -> None:
        manifest = self._create_job()
        job_id = manifest["job_id"]
        manifest_path = self._job_dir(job_id) / "manifest.json"
        original = manifest_path.read_bytes()

        real_replace = os.replace

        def fail_manifest_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            if Path(destination) == manifest_path:
                raise OSError("simulated replace failure")
            real_replace(source, destination)

        with patch("am_configurator.library.os.replace", side_effect=fail_manifest_replace):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.library.update_manifest(job_id, {"status": "in_progress"})
        self.assertEqual(original, manifest_path.read_bytes())
        self.assertEqual([], list(manifest_path.parent.glob(".manifest.json.*.tmp")))

        def increment() -> None:
            def mutate(current: dict) -> None:
                current["progress"]["completed"] += 1

            self.library.update_manifest(job_id, mutate)

        threads = [threading.Thread(target=increment) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(12, self.library.load_manifest(job_id)["progress"]["completed"])

        context = multiprocessing.get_context("spawn")
        entered = context.Event()
        release = context.Event()
        holder_done = context.Event()
        waiter_started = context.Event()
        waiter_done = context.Event()
        holder = context.Process(
            target=_holding_manifest_process,
            args=(str(self.root), job_id, entered, release, holder_done),
        )
        waiter = context.Process(
            target=_waiting_manifest_process,
            args=(str(self.root), job_id, waiter_started, waiter_done),
        )
        processes = (holder, waiter)
        try:
            holder.start()
            self.assertTrue(entered.wait(5), "holder never entered its locked mutator")
            waiter.start()
            self.assertTrue(waiter_started.wait(5), "waiter never attempted its update")
            self.assertFalse(waiter_done.wait(0.5), "waiter bypassed the process lock")
            release.set()
            self.assertTrue(holder_done.wait(5), "holder did not complete")
            self.assertTrue(waiter_done.wait(5), "waiter did not complete after release")
            for process in processes:
                process.join(timeout=5)
                self.assertEqual(0, process.exitcode)
        finally:
            release.set()
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
        self.assertEqual(14, self.library.load_manifest(job_id)["progress"]["completed"])

    def test_asset_is_banked_before_publication_with_hash_and_opaque_id(self) -> None:
        manifest = self._create_job()
        job_id = manifest["job_id"]
        payload = b"\x89PNG\r\n\x1a\nprovider-image"

        record = self.library.bank_asset(
            job_id,
            kind="concept",
            data=payload,
            mime_type="image/png",
            origin="xai",
            status="complete",
        )
        self.assertEqual(record["asset_id"], str(uuid.UUID(record["asset_id"])))
        self.assertEqual(len(payload), record["byte_size"])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), record["sha256"])
        self.assertEqual("concepts/" + record["asset_id"] + ".png", record["relative_path"])

        owned = self.library.resolve_asset(job_id, record["asset_id"])
        self.assertEqual(payload, owned.path.read_bytes())
        with owned.open_verified() as verified:
            self.assertEqual(payload, verified.read())
        stored = self.library.load_manifest(job_id)
        self.assertEqual(record, stored["assets"][0])
        self.assertEqual([], list(owned.path.parent.glob(".*.tmp")))
        if os.name != "nt":
            self.assertEqual(0o600, stat.S_IMODE(owned.path.stat().st_mode))

    def test_asset_banking_rejects_replaced_kind_directory_symlink(self) -> None:
        job = self._create_job()
        job_dir = self._job_dir(job["job_id"])
        outside = self.base / "outside-assets"
        outside.mkdir()
        shutil.rmtree(job_dir / "concepts")
        if not self._try_symlink(outside, job_dir / "concepts", directory=True):
            (job_dir / "concepts").mkdir(mode=0o700)
            self.skipTest("symlinks are not available on this host")

        with self.assertRaises(ManifestError):
            self.library.bank_asset(
                job["job_id"],
                kind="concept",
                data=b"\x89PNG\r\n\x1a\noutside",
                mime_type="image/png",
                origin="xai",
            )
        self.assertEqual([], list(outside.iterdir()))

    def test_reconcile_recovers_an_atomic_asset_left_before_manifest_commit(self) -> None:
        job = self._create_job(prompt="crash-window")
        orphan_id = str(uuid.uuid4())
        payload = b"\x89PNG\r\n\x1a\ncommitted-before-crash"
        manifest_path = self._job_dir(job["job_id"]) / "manifest.json"
        real_replace = os.replace

        def fail_manifest_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            if Path(destination) == manifest_path:
                raise OSError("crash before manifest publication")
            real_replace(source, destination)

        with (
            patch("am_configurator.library.uuid.uuid4", return_value=uuid.UUID(orphan_id)),
            patch("am_configurator.library.os.replace", side_effect=fail_manifest_replace),
        ):
            with self.assertRaisesRegex(OSError, "crash"):
                self.library.bank_asset(
                    job["job_id"],
                    kind="selected_still",
                    data=payload,
                    mime_type="image/png",
                    origin="xai",
                    status="partial",
                )

        orphan = self._job_dir(job["job_id"]) / "concepts" / f"{orphan_id}.png"
        self.assertEqual(payload, orphan.read_bytes())
        self.assertEqual([], self.library.load_manifest(job["job_id"])["assets"])

        self.library.reconcile()
        manifest = self.library.load_manifest(job["job_id"])
        recovered = next(asset for asset in manifest["assets"] if asset["asset_id"] == orphan_id)
        self.assertEqual("xai", recovered["origin"])
        self.assertEqual("selected_still", recovered["kind"])
        self.assertEqual("partial", recovered["status"])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), recovered["sha256"])
        self.assertEqual(
            payload,
            self.library.resolve_asset(job["job_id"], orphan_id).path.read_bytes(),
        )

    def test_manifest_symlink_and_asset_content_tampering_are_rejected(self) -> None:
        linked_job = self._create_job(prompt="linked manifest")
        linked_path = self._job_dir(linked_job["job_id"]) / "manifest.json"
        outside_manifest = self.base / "outside-manifest.json"
        outside_manifest.write_bytes(linked_path.read_bytes())
        linked_path.unlink()
        if self._try_symlink(outside_manifest, linked_path):
            with self.assertRaises(ManifestError):
                self.library.load_manifest(linked_job["job_id"])
        else:
            linked_path.write_bytes(outside_manifest.read_bytes())

        tampered_job = self._create_job(prompt="tampered asset")
        asset = self.library.bank_asset(
            tampered_job["job_id"],
            kind="concept",
            data=b"\x89PNG\r\n\x1a\noriginal",
            mime_type="image/png",
            origin="xai",
        )
        owned = self.library.resolve_asset(tampered_job["job_id"], asset["asset_id"])
        owned.path.write_bytes(b"\x89PNG\r\n\x1a\nmodified")
        with self.assertRaisesRegex(ManifestError, "integrity"):
            self.library.resolve_asset(tampered_job["job_id"], asset["asset_id"])

    def test_partial_assets_survive_interrupted_concept_reconciliation(self) -> None:
        job = self._create_job()
        job_id = job["job_id"]
        asset = self.library.bank_asset(
            job_id,
            kind="concept",
            data=b"\xff\xd8\xffcandidate",
            mime_type="image/jpeg",
            origin="xai",
        )
        self.library.update_manifest(
            job_id,
            {
                "status": "in_progress",
                "phase": "concept_generation",
                "candidates": [
                    {
                        "candidate_id": asset["asset_id"],
                        "asset_id": asset["asset_id"],
                        "status": "complete",
                    }
                ],
            },
        )
        work_file = self._job_dir(job_id) / ".work" / "temporary.bin"
        work_file.write_bytes(b"discard")

        self.assertEqual([], self.library.reconcile())
        reconciled = self.library.load_manifest(job_id)
        self.assertEqual("partial", reconciled["status"])
        self.assertEqual("interrupted", reconciled["phase"])
        self.assertFalse(work_file.exists())
        self.assertEqual(b"\xff\xd8\xffcandidate", self.library.resolve_asset(job_id, asset["asset_id"]).path.read_bytes())

        empty = self._create_job()
        self.library.update_manifest(
            empty["job_id"],
            {"status": "in_progress", "phase": "concept_generation"},
        )
        self.library.reconcile()
        self.assertEqual("interrupted", self.library.load_manifest(empty["job_id"])["status"])

        corrupt = self._create_job(prompt="tampered candidate")
        corrupt_asset = self.library.bank_asset(
            corrupt["job_id"],
            kind="concept",
            data=b"\x89PNG\r\n\x1a\nvalid",
            mime_type="image/png",
            origin="xai",
        )
        corrupt_path = self.library.resolve_asset(
            corrupt["job_id"], corrupt_asset["asset_id"]
        ).path
        corrupt_path.write_bytes(b"tampered")
        self.library.update_manifest(
            corrupt["job_id"],
            {
                "status": "in_progress",
                "phase": "concept_generation",
                "candidates": [
                    {
                        "candidate_id": corrupt_asset["asset_id"],
                        "asset_id": corrupt_asset["asset_id"],
                        "status": "complete",
                    }
                ],
            },
        )
        self.library.reconcile()
        self.assertEqual(
            "interrupted",
            self.library.load_manifest(corrupt["job_id"])["status"],
        )

    def test_scan_covers_current_and_historical_roots_with_canonical_dedupe(self) -> None:
        previous_root = self.base / "previous"
        previous = GeneratedAssetLibrary(previous_root, minimum_free_bytes=1)
        old_job = previous.create_job(prompt="old")
        current_job = self.library.create_job(prompt="new")

        combined = GeneratedAssetLibrary(
            self.root,
            historical_roots=[previous_root, previous_root / ".", self.root],
            minimum_free_bytes=1,
        )
        scan = combined.scan()
        self.assertEqual([], scan["errors"])
        self.assertEqual(
            {old_job["job_id"], current_job["job_id"]},
            {job["job_id"] for job in scan["jobs"]},
        )

        history_only = GeneratedAssetLibrary(None, historical_roots=[previous_root])
        self.assertEqual([old_job["job_id"]], [job["job_id"] for job in history_only.scan()["jobs"]])

        shadow_root = self.base / "shadow"
        corrupt_duplicate = shadow_root / "jobs" / old_job["job_id"]
        corrupt_duplicate.mkdir(parents=True)
        (corrupt_duplicate / "manifest.json").write_text("{corrupt", encoding="utf-8")
        isolated = GeneratedAssetLibrary(
            shadow_root,
            historical_roots=[Path("relative-root"), previous_root],
        ).scan()
        self.assertEqual([old_job["job_id"]], [job["job_id"] for job in isolated["jobs"]])
        self.assertEqual(
            {"root_unavailable", "corrupt_manifest"},
            {error["code"] for error in isolated["errors"]},
        )
        self.assertNotIn(str(shadow_root), json.dumps(isolated["errors"]))
        direct = GeneratedAssetLibrary(
            shadow_root,
            historical_roots=[previous_root],
        ).load_manifest(old_job["job_id"])
        self.assertEqual(old_job["job_id"], direct["job_id"])

    def test_corrupt_manifest_is_isolated_and_scan_errors_are_pathless(self) -> None:
        good = self._create_job()
        corrupt_id = str(uuid.uuid4())
        corrupt_dir = self.root / "jobs" / corrupt_id
        corrupt_dir.mkdir(mode=0o700)
        secret = "xai-secret-that-must-not-leak"
        (corrupt_dir / "manifest.json").write_text("{not-json " + secret, encoding="utf-8")
        recursive_id = str(uuid.uuid4())
        recursive_dir = self.root / "jobs" / recursive_id
        recursive_dir.mkdir(mode=0o700)
        (recursive_dir / "manifest.json").write_text(
            '{"nested":' + ("[" * 2000) + "0" + ("]" * 2000) + "}",
            encoding="utf-8",
        )

        scan = self.library.scan()
        self.assertEqual([good["job_id"]], [job["job_id"] for job in scan["jobs"]])
        self.assertEqual(
            {corrupt_id, recursive_id},
            {error["job_id"] for error in scan["errors"]},
        )
        self.assertTrue(all(error["code"] == "corrupt_manifest" for error in scan["errors"]))
        rendered = json.dumps(scan)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(secret, rendered)

    def test_restart_reconciliation_never_repeats_paid_work(self) -> None:
        accepted = self._create_job(prompt="accepted")
        self.library.update_manifest(
            accepted["job_id"],
            lambda current: current.update(
                {
                    "status": "in_progress",
                    "phase": "video_polling",
                    "provider_requests": {
                        "video": {"request_id": "vid_request_123", "status": "accepted"}
                    },
                }
            ),
        )

        cancelled_visible = self._create_job(prompt="cancelled but paid")
        self.library.update_manifest(
            cancelled_visible["job_id"],
            lambda current: current.update(
                {
                    "status": "cancelled",
                    "phase": "video_polling",
                    "cancel_requested_at": current["updated_at"],
                    "provider_requests": {
                        "video": {"request_id": "vid_cancelled_456", "status": "accepted"}
                    },
                }
            ),
        )

        submitted = self._create_job(prompt="accepted before phase advance")
        self.library.update_manifest(
            submitted["job_id"],
            lambda current: current.update(
                {
                    "status": "in_progress",
                    "phase": "video_submitting",
                    "provider_requests": {
                        "video": {"request_id": "vid_submitted_789", "status": "accepted"}
                    },
                }
            ),
        )

        unknown = self._create_job(prompt="unknown")
        self.library.update_manifest(
            unknown["job_id"],
            {"status": "in_progress", "phase": "video_submitting"},
        )

        provider_failed = self._create_job(prompt="provider failed")
        self.library.update_manifest(
            provider_failed["job_id"],
            {
                "status": "in_progress",
                "phase": "video_polling",
                "provider_requests": {
                    "video": {"request_id": "vid_failed_345", "status": "failed"}
                },
            },
        )

        local = self._create_job(prompt="local")
        video = self.library.bank_asset(
            local["job_id"],
            kind="source_video",
            data=b"\x00\x00\x00\x18ftypisomvideo",
            mime_type="video/mp4",
            origin="xai",
        )
        self.library.update_manifest(
            local["job_id"],
            {"status": "in_progress", "phase": "local_processing"},
        )
        local_work = self._job_dir(local["job_id"]) / ".work" / "frame.png"
        local_work.write_bytes(b"temp")

        banked_before_phase = self._create_job(prompt="banked before phase advance")
        banked_video = self.library.bank_asset(
            banked_before_phase["job_id"],
            kind="source_video",
            data=b"\x00\x00\x00\x18ftypisomcrash",
            mime_type="video/mp4",
            origin="xai",
        )
        self.library.update_manifest(
            banked_before_phase["job_id"],
            {
                "status": "in_progress",
                "phase": "video_downloading",
                "provider_requests": {
                    "video": {"request_id": "vid_banked_012", "status": "done"}
                },
            },
        )

        actions = self.library.reconcile()
        self.assertEqual(
            {
                (accepted["job_id"], "vid_request_123"),
                (cancelled_visible["job_id"], "vid_cancelled_456"),
                (submitted["job_id"], "vid_submitted_789"),
            },
            {(action["job_id"], action["request_id"]) for action in actions},
        )
        self.assertTrue(
            all(action["action"] == "resume_video_poll" for action in actions),
            actions,
        )
        self.assertEqual("in_progress", self.library.load_manifest(accepted["job_id"])["status"])
        self.assertEqual("submission_unknown", self.library.load_manifest(unknown["job_id"])["status"])
        self.assertEqual(
            "failed",
            self.library.load_manifest(provider_failed["job_id"])["status"],
        )
        local_manifest = self.library.load_manifest(local["job_id"])
        self.assertEqual("ready_to_process", local_manifest["status"])
        self.assertEqual(video["asset_id"], local_manifest["recovery"]["source_video_asset_id"])
        self.assertFalse(local_work.exists())
        banked_manifest = self.library.load_manifest(banked_before_phase["job_id"])
        self.assertEqual("ready_to_process", banked_manifest["status"])
        self.assertEqual(
            banked_video["asset_id"],
            banked_manifest["recovery"]["source_video_asset_id"],
        )

        tampered = self._create_job(prompt="tampered mp4")
        tampered_video = self.library.bank_asset(
            tampered["job_id"],
            kind="source_video",
            data=b"\x00\x00\x00\x18ftypisomvalid",
            mime_type="video/mp4",
            origin="xai",
        )
        tampered_path = self.library.resolve_asset(
            tampered["job_id"], tampered_video["asset_id"]
        ).path
        tampered_path.write_bytes(b"tampered")
        self.library.update_manifest(
            tampered["job_id"],
            {"status": "in_progress", "phase": "local_processing"},
        )
        self.library.reconcile()
        self.assertEqual(
            "interrupted",
            self.library.load_manifest(tampered["job_id"])["status"],
        )

    def test_terminal_reconciliation_purges_work_without_following_symlinks(self) -> None:
        terminal = self._create_job()
        job_dir = self._job_dir(terminal["job_id"])
        self.library.update_manifest(terminal["job_id"], {"status": "ready", "phase": "complete"})
        (job_dir / ".work" / "stale.bin").write_bytes(b"stale")
        self.library.reconcile()
        self.assertEqual([], list((job_dir / ".work").iterdir()))

        outside = self.base / "outside"
        outside.mkdir()
        protected = outside / "keep.bin"
        protected.write_bytes(b"keep")
        shutil.rmtree(job_dir / ".work")
        if self._try_symlink(outside, job_dir / ".work", directory=True):
            self.library.reconcile()
            self.assertEqual(b"keep", protected.read_bytes())
            self.assertTrue((job_dir / ".work").is_dir())
            self.assertFalse((job_dir / ".work").is_symlink())
        else:
            (job_dir / ".work").mkdir(mode=0o700)

    def test_traversal_symlink_escape_and_wrong_ownership_are_rejected(self) -> None:
        first = self._create_job(prompt="one")
        second = self._create_job(prompt="two")
        asset = self.library.bank_asset(
            first["job_id"],
            kind="concept",
            data=b"\x89PNG\r\n\x1a\nowned",
            mime_type="image/png",
            origin="xai",
        )

        with self.assertRaises(InvalidIdentifierError):
            self.library.resolve_asset("../jobs", asset["asset_id"])
        with self.assertRaises(InvalidIdentifierError):
            self.library.resolve_asset(first["job_id"], "../manifest.json")
        with self.assertRaises(AssetNotFoundError):
            self.library.resolve_asset(second["job_id"], asset["asset_id"])

        manifest = self.library.load_manifest(first["job_id"])
        manifest["assets"][0]["relative_path"] = "../manifest.json"
        self._write_manifest_directly(first["job_id"], manifest)
        with self.assertRaises(ManifestError):
            self.library.resolve_asset(first["job_id"], asset["asset_id"])

        third = self._create_job(prompt="three")
        linked_asset = self.library.bank_asset(
            third["job_id"],
            kind="concept",
            data=b"\x89PNG\r\n\x1a\nlinked",
            mime_type="image/png",
            origin="xai",
        )
        outside = self.base / "outside.png"
        outside.write_bytes(b"outside")
        linked_path = self.library.resolve_asset(third["job_id"], linked_asset["asset_id"]).path
        linked_path.unlink()
        if self._try_symlink(outside, linked_path):
            with self.assertRaises(ManifestError):
                self.library.resolve_asset(third["job_id"], linked_asset["asset_id"])
        else:
            linked_path.write_bytes(b"restored")

        windows_escape = self._create_job(prompt="windows traversal")
        windows_asset = self.library.bank_asset(
            windows_escape["job_id"],
            kind="concept",
            data=b"\x89PNG\r\n\x1a\nwindows",
            mime_type="image/png",
            origin="xai",
        )
        windows_manifest = self.library.load_manifest(windows_escape["job_id"])
        windows_manifest["assets"][0]["relative_path"] = (
            "concepts/..\\" + windows_asset["asset_id"] + ".png"
        )
        self._write_manifest_directly(windows_escape["job_id"], windows_manifest)
        with self.assertRaises(ManifestError):
            self.library.load_manifest(windows_escape["job_id"])

        jobs_dir = self.root / "jobs"
        relocated_jobs = self.base / "relocated-jobs"
        jobs_dir.rename(relocated_jobs)
        if self._try_symlink(relocated_jobs, jobs_dir, directory=True):
            with self.assertRaises(ManifestError):
                self.library.load_manifest(third["job_id"])
        else:
            relocated_jobs.rename(jobs_dir)

    def test_public_views_hide_paths_and_reject_secret_manifest_values(self) -> None:
        job = self._create_job(prompt="public prompt")
        asset = self.library.bank_asset(
            job["job_id"],
            kind="concept",
            data=b"\x89PNG\r\n\x1a\npublic",
            mime_type="image/png",
            origin="xai",
        )
        self.library.update_manifest(
            job["job_id"],
            {
                "target": {
                    "family": "CB",
                    "debug_path": str(self.root / "internal"),
                    "nested": {
                        "source_root": str(self.root),
                        "diagnostic": (
                            "failed at /Users/example/private.json and "
                            "C:\\Users\\example\\private.json"
                        ),
                    },
                },
                "provider_requests": {
                    "video": {"request_id": "safe_request_id", "status": "accepted"}
                }
            },
        )
        public = self.library.get_job(job["job_id"])
        self.assertEqual("public prompt", public["prompt"])
        self.assertEqual(asset["asset_id"], public["assets"][0]["asset_id"])
        self.assertNotIn("relative_path", public["assets"][0])
        self.assertNotIn("debug_path", public["target"])
        self.assertNotIn("source_root", public["target"]["nested"])
        self.assertNotIn(str(self.root), json.dumps(public))
        self.assertNotIn("/Users/example", json.dumps(public))
        self.assertNotIn("C:", json.dumps(public))

        with self.assertRaisesRegex(ManifestError, "sensitive"):
            self.library.update_manifest(job["job_id"], {"api_key": "xai-secret"})
        for credential_key in (
            "access_token",
            "client_secret",
            "password",
            "credentials",
            "xai_api_key",
            "provider_private_key",
        ):
            with self.subTest(credential_key=credential_key):
                with self.assertRaisesRegex(ManifestError, "sensitive"):
                    self.library.update_manifest(job["job_id"], {credential_key: "private"})
        with self.assertRaisesRegex(ManifestError, "sensitive"):
            self.library.update_manifest(
                job["job_id"],
                {"provider_requests": {"video": {"media_url": "data:image/png;base64,AAAA"}}},
            )
        with self.assertRaisesRegex(ManifestError, "request ID"):
            self.library.update_manifest(
                job["job_id"],
                {
                    "provider_requests": {
                        "video": {
                            "request_id": "https://vidgen.x.ai/file?token=secret",
                            "status": "accepted",
                        }
                    }
                },
            )
        with self.assertRaisesRegex(ManifestError, "provider request"):
            self.library.update_manifest(
                job["job_id"],
                {
                    "provider_requests": {
                        "video": {
                            "request_id": "safe_request_id",
                            "status": "accepted",
                            "raw_response": {"provider": "opaque"},
                        }
                    }
                },
            )
        with self.assertRaisesRegex(ManifestError, "sensitive"):
            self.library.update_manifest(
                job["job_id"],
                {
                    "provider_requests": {
                        "video": {
                            "request_id": "safe_request_id",
                            "status": "done",
                            "url": (
                                "https://vidgen.x.ai/file.mp4?"
                                "X-Goog-Signature=private"
                            ),
                        }
                    }
                },
            )
        with self.assertRaisesRegex(ManifestError, "cost"):
            self.library.update_manifest(
                job["job_id"],
                {
                    "costs": {
                        "estimated_ticks": 1.5,
                        "actual_by_operation": {},
                        "actual_incomplete": False,
                    }
                },
            )
        with self.assertRaisesRegex(ManifestError, "error record"):
            self.library.update_manifest(
                job["job_id"],
                {
                    "errors": [
                        {
                            "code": "provider_error",
                            "message": "safe summary",
                            "created_at": "2026-07-20T00:00:00+00:00",
                            "trace": "internal detail",
                        }
                    ]
                },
            )

        saved = self.library.record_error(
            job["job_id"],
            code="provider_error",
            message=(
                "Authorization: Bearer secret-token "
                "https://vidgen.x.ai/file.mp4?X-Amz-Signature=private "
                "data:image/png;base64,AAAA "
                "api_key=sk-plain token: raw-token client_secret=plain-secret "
                f"library={self.root} opaque-known-key-123 "
                "failed at /Users/example/secret.json and "
                "C:\\Users\\example\\secret.json"
            ),
            sensitive_values=("opaque-known-key-123",),
        )
        rendered = json.dumps(saved["errors"])
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("private", rendered)
        self.assertNotIn("AAAA", rendered)
        self.assertNotIn("https://", rendered)
        self.assertNotIn("sk-plain", rendered)
        self.assertNotIn("raw-token", rendered)
        self.assertNotIn("plain-secret", rendered)
        self.assertNotIn("opaque-known-key-123", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("/Users/example", rendered)
        self.assertNotIn("C:", rendered)


if __name__ == "__main__":
    unittest.main()
