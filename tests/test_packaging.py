from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tomllib
import unittest
from collections import Counter
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from build import build_installer
from am_configurator import __version__, desktop
from build_tools.release_info import (
    artifact_filename,
    normalize_arch,
    project_version,
)
from build_tools.release_manifest import (
    ReleaseManifestError,
    write_release_metadata,
)


ROOT = Path(__file__).resolve().parents[1]

# Governance, internal planning history, and repo-only config. None of it may
# reach a published artifact; `machines.md` alone records the owner's checkout
# path, host OS, and local toolchain.
_SDIST_FORBIDDEN = (
    ".agents/",
    ".claude/",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/design/",
    "docs/superpowers/",
    "docs/verification/",
)


class ReleaseManifestTests(unittest.TestCase):
    VERSION = "0.1.68"
    COMMIT = "0123456789abcdef0123456789abcdef01234567"
    REPOSITORY = "roethlar/AMKB-GUI"
    FILENAMES = (
        "AM-Configurator-0.1.68-macOS-arm64.dmg",
        "AM-Configurator-0.1.68-Windows-x64-Setup.exe",
        "AM-Configurator-0.1.68-Linux-x86_64.AppImage",
    )

    def _write_candidates(self, root: Path) -> dict[str, bytes]:
        payloads = {
            self.FILENAMES[2]: b"linux candidate\n",
            self.FILENAMES[1]: b"windows candidate\n",
            self.FILENAMES[0]: b"macOS candidate\n",
        }
        for filename, payload in payloads.items():
            (root / filename).write_bytes(payload)
        return payloads

    def _write_metadata(
        self,
        root: Path,
        *,
        version: str | None = None,
        commit: str | None = None,
        output_root: Path | None = None,
    ) -> tuple[Path, Path]:
        destination = output_root or root.parent / "metadata"
        manifest = destination / "release-manifest.json"
        checksums = destination / "SHA256SUMS.txt"
        write_release_metadata(
            version=version or self.VERSION,
            source_commit=commit or self.COMMIT,
            workflow_run_id=30369190195,
            workflow_run_number=34,
            repository=self.REPOSITORY,
            candidate_root=root,
            manifest_path=manifest,
            checksums_path=checksums,
        )
        return manifest, checksums

    def test_happy_path_is_deterministic_sorted_and_pathless(self) -> None:
        with TemporaryDirectory(prefix="am-release-private-owner-") as temporary:
            workspace = Path(temporary)
            candidates = workspace / "candidate-installers"
            candidates.mkdir()
            payloads = self._write_candidates(candidates)

            first_manifest, first_checksums = self._write_metadata(candidates)
            second_manifest, second_checksums = self._write_metadata(
                candidates,
                output_root=workspace / "metadata-copy",
            )

            self.assertEqual(first_manifest.read_bytes(), second_manifest.read_bytes())
            self.assertEqual(first_checksums.read_bytes(), second_checksums.read_bytes())
            self.assertNotIn(b"\r", first_manifest.read_bytes())
            self.assertNotIn(b"\r", first_checksums.read_bytes())

            manifest = json.loads(first_manifest.read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["schema_version"])
            self.assertEqual(self.VERSION, manifest["app_version"])
            self.assertEqual(self.COMMIT, manifest["source_commit"])
            self.assertEqual(self.REPOSITORY, manifest["repository"])
            self.assertEqual(
                {"run_id": 30369190195, "run_number": 34},
                manifest["workflow"],
            )
            filenames = [artifact["filename"] for artifact in manifest["artifacts"]]
            self.assertEqual(sorted(self.FILENAMES), filenames)
            for artifact in manifest["artifacts"]:
                payload = payloads[artifact["filename"]]
                self.assertEqual(len(payload), artifact["byte_size"])
                self.assertEqual(
                    hashlib.sha256(payload).hexdigest(),
                    artifact["sha256"],
                )

            expected_rows = [
                f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}"
                for name in sorted(self.FILENAMES)
            ]
            self.assertEqual(
                "\n".join(expected_rows) + "\n",
                first_checksums.read_text(encoding="utf-8"),
            )
            published = first_manifest.read_text(encoding="utf-8")
            self.assertNotIn(str(workspace), published)
            self.assertNotIn("private-owner", published)

    def test_filename_version_mismatch_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            candidates = Path(temporary) / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)

            with self.assertRaises(ReleaseManifestError):
                self._write_metadata(candidates, version="0.1.35")

    def test_missing_platform_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            candidates = Path(temporary) / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)
            (candidates / self.FILENAMES[0]).unlink()

            with self.assertRaises(ReleaseManifestError):
                self._write_metadata(candidates)

    def test_extra_or_nested_installer_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            candidates = Path(temporary) / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)
            duplicate = candidates / "duplicate"
            duplicate.mkdir()
            (duplicate / self.FILENAMES[0]).write_bytes(b"duplicate")

            with self.assertRaises(ReleaseManifestError):
                self._write_metadata(candidates)

    def test_empty_installer_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            candidates = Path(temporary) / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)
            (candidates / self.FILENAMES[1]).write_bytes(b"")

            with self.assertRaises(ReleaseManifestError):
                self._write_metadata(candidates)

    @unittest.skipIf(os.name == "nt", "Windows CI cannot create symlinks reliably")
    def test_symlinked_installer_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            candidates = Path(temporary) / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)
            expected = candidates / self.FILENAMES[2]
            expected.unlink()
            target = candidates / "candidate.bin"
            target.write_bytes(b"candidate")
            expected.symlink_to(target)

            with self.assertRaises(ReleaseManifestError):
                self._write_metadata(candidates)

    @unittest.skipIf(os.name == "nt", "Windows CI cannot create symlinks reliably")
    def test_candidate_path_cannot_escape_the_supplied_root(self) -> None:
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            candidates = workspace / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)
            expected = candidates / self.FILENAMES[0]
            expected.unlink()
            outside = workspace / "outside.dmg"
            outside.write_bytes(b"outside")
            expected.symlink_to(outside)

            with self.assertRaises(ReleaseManifestError):
                self._write_metadata(candidates)

    def test_malformed_version_commit_and_run_identity_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            candidates = Path(temporary) / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)
            for invalid in ("0.1", "01.1.34", "0.1.64.dev1", "v0.1.64"):
                with self.subTest(version=invalid), self.assertRaises(
                    ReleaseManifestError
                ):
                    self._write_metadata(candidates, version=invalid)
            for invalid in ("ABC", "a" * 39, "A" * 40, "g" * 40):
                with self.subTest(commit=invalid), self.assertRaises(
                    ReleaseManifestError
                ):
                    self._write_metadata(candidates, commit=invalid)

            destination = candidates.parent / "invalid-run"
            with self.assertRaises(ReleaseManifestError):
                write_release_metadata(
                    version=self.VERSION,
                    source_commit=self.COMMIT,
                    workflow_run_id=0,
                    workflow_run_number=34,
                    repository=self.REPOSITORY,
                    candidate_root=candidates,
                    manifest_path=destination / "release-manifest.json",
                    checksums_path=destination / "SHA256SUMS.txt",
                )

    def test_conflicting_replacement_changes_neither_output(self) -> None:
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            candidates = workspace / "candidate-installers"
            candidates.mkdir()
            self._write_candidates(candidates)
            destination = workspace / "metadata"
            destination.mkdir()
            manifest = destination / "release-manifest.json"
            checksums = destination / "SHA256SUMS.txt"
            manifest.write_bytes(b"different manifest\n")

            with self.assertRaises(ReleaseManifestError):
                self._write_metadata(candidates, output_root=destination)

            self.assertEqual(b"different manifest\n", manifest.read_bytes())
            self.assertFalse(checksums.exists())

    def test_workflow_collects_exact_candidates_only_after_all_installers(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        metadata_job = workflow.split("  candidate-metadata:\n", 1)[1]

        self.assertIn("needs: installer", metadata_job)
        self.assertIn("github.event_name == 'workflow_dispatch'", metadata_job)
        self.assertIn("github.event_name == 'push'", metadata_job)
        self.assertIn("github.ref == 'refs/heads/main'", metadata_job)
        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
            metadata_job,
        )
        self.assertIn("merge-multiple: true", metadata_job)
        self.assertIn("build_tools/release_manifest.py", metadata_job)
        self.assertIn("--commit \"${{ github.sha }}\"", metadata_job)
        self.assertIn("--run-id \"${{ github.run_id }}\"", metadata_job)
        self.assertIn("--run-number \"${{ github.run_number }}\"", metadata_job)
        self.assertIn("--repository \"${{ github.repository }}\"", metadata_job)
        self.assertIn("release-manifest.json", metadata_job)
        self.assertIn("SHA256SUMS.txt", metadata_job)
        self.assertIn("retention-days: 30", metadata_job)

    def test_experimental_arm_ci_is_nonblocking_and_isolated(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        arm_job = workflow.split("  experimental-arm:\n", 1)[1].split(
            "  candidate-metadata:\n", 1
        )[0]
        self.assertIn("continue-on-error: true", arm_job)
        self.assertIn("windows-11-arm", arm_job)
        self.assertIn("ubuntu-24.04-arm", arm_job)
        self.assertIn("native_tree_audit.py", arm_job)
        self.assertIn("--native-policy-smoke", arm_job)
        self.assertIn("--smoke-test", arm_job)
        self.assertIn("0xAA64", arm_job)
        self.assertIn("aarch64", arm_job)
        self.assertIn("Experimental-ARM64-${{ matrix.artifact }}", arm_job)
        self.assertNotIn("AM-Configurator-${{", arm_job)
        remainder = workflow.split("  candidate-metadata:\n", 1)[1]
        self.assertIn("needs: installer", remainder)
        self.assertNotIn("experimental-arm", remainder)


class ReleaseInfoTests(unittest.TestCase):
    def test_build_script_dispatches_without_mutating_canonical_version(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "am_configurator"
            package.mkdir()
            (root / "dist").mkdir()
            version_file = package / "_version.py"
            original = '__version__ = "0.1.64"\n'
            version_file.write_text(original, encoding="utf-8")
            expected_name = artifact_filename("macos", root=root)
            commands: list[list[str]] = []

            def run_command(command: list[str], cwd: Path) -> None:
                self.assertEqual(root, cwd)
                commands.append(command)
                self.assertEqual("0.1.64", project_version(root))
                if command[-1].endswith("build_dmg.sh"):
                    (root / "dist" / expected_name).touch()

            artifact = build_installer(
                root=root,
                platform_name="darwin",
                run_command=run_command,
            )

            self.assertEqual(
                root / "dist" / expected_name,
                artifact,
            )
            self.assertEqual(original, version_file.read_text(encoding="utf-8"))
            self.assertEqual("uv", commands[0][0])
            self.assertIn("sync", commands[0])
            self.assertIn("pyinstaller", commands[1])
            self.assertTrue(commands[2][1].endswith("native_tree_audit.py"))
            self.assertTrue(commands[2][2].endswith("AM Configurator.app"))
            self.assertTrue(commands[3][-1].endswith("build_dmg.sh"))

    def test_failed_build_does_not_mutate_canonical_version(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            package = root / "am_configurator"
            package.mkdir()
            version_file = package / "_version.py"
            original = '__version__ = "0.1.64"\n'
            version_file.write_text(original, encoding="utf-8")

            def fail(_command: list[str], _cwd: Path) -> None:
                raise CalledProcessError(1, "uv")

            with self.assertRaises(CalledProcessError):
                build_installer(
                    root=root,
                    platform_name="linux",
                    run_command=fail,
                )
            self.assertEqual(original, version_file.read_text(encoding="utf-8"))

    def test_project_version_requires_one_three_part_canonical_source(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "am_configurator"
            package.mkdir()
            version_file = package / "_version.py"

            with self.assertRaises(ValueError):
                project_version(root)
            for invalid in ("0.1", "0.1.64.dev1", "v0.1.64", "01.1.34"):
                with self.subTest(invalid=invalid):
                    version_file.write_text(
                        f'__version__ = "{invalid}"\n', encoding="utf-8"
                    )
                    with self.assertRaises(ValueError):
                        project_version(root)
            version_file.write_text('__version__ = "0.1.64"\n', encoding="utf-8")
            self.assertEqual("0.1.64", project_version(root))

    def test_release_names_use_project_version_and_normalized_architecture(self) -> None:
        self.assertEqual(__version__, project_version(ROOT))
        self.assertEqual("0.1.68", project_version(ROOT))
        self.assertEqual("x86_64", normalize_arch("AMD64"))
        self.assertEqual("aarch64", normalize_arch("arm64"))
        self.assertEqual(
            "AM-Configurator-0.1.68-macOS-arm64.dmg",
            artifact_filename("macos", "arm64", root=ROOT),
        )
        self.assertEqual(
            "AM-Configurator-0.1.68-Windows-x64-Setup.exe",
            artifact_filename("windows", "AMD64", root=ROOT),
        )
        self.assertEqual(
            "AM-Configurator-0.1.68-Linux-x86_64.AppImage",
            artifact_filename("linux", "x86_64", root=ROOT),
        )

    def test_one_canonical_version_drives_every_build(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("version", project["project"])
        self.assertEqual(["version"], project["project"]["dynamic"])
        self.assertEqual(
            "am_configurator/_version.py",
            project["tool"]["hatch"]["version"]["path"],
        )
        self.assertEqual("0.1.68", __version__)
        installer_job = workflow.split("  candidate-metadata:\n", 1)[0]
        self.assertNotIn("github.run_number", installer_job)
        self.assertEqual(1, workflow.count("github.run_number"))
        self.assertIn('--run-number "${{ github.run_number }}"', workflow)
        self.assertNotIn("stamp --build-number", workflow)
        self.assertIn("version --github-output", workflow)
        self.assertNotIn("reserve_local_build_number", build_script)
        self.assertNotIn("--build-number", build_script)
        self.assertNotIn("--build-number", readme)
        self.assertFalse((ROOT / ".am-configurator-build-number").exists())

    def test_active_release_docs_and_plan_pointers_use_distinct_candidate(self) -> None:
        for path in (
            ROOT / "docs" / "installing.md",
            ROOT / "docs" / "neon-80-linux.md",
        ):
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertIn("AM-Configurator-0.1.68", text)
                self.assertNotIn("AM-Configurator-0.1.64", text)

        decisions = (ROOT / ".agents" / "decisions.md").read_text(encoding="utf-8")
        backend_plan = (
            ROOT
            / "docs"
            / "superpowers"
            / "plans"
            / "2026-07-29-ollama-backend-correctness.md"
        ).read_text(encoding="utf-8")
        release_plan = (
            ROOT
            / "docs"
            / "superpowers"
            / "plans"
            / "2026-07-28-public-release.md"
        ).read_text(encoding="utf-8")
        release_preamble = release_plan.split("## Objective", 1)[0]

        self.assertIn("current product/release version is `0.1.68`", decisions)
        self.assertIn("rejected unpublished `0.1.64` candidate", decisions)
        self.assertIn("distinct `0.1.65` candidate", backend_plan)
        self.assertIn("status: historical", release_preamble.casefold())
        self.assertIn("`0.1.65` candidate", release_preamble)
        self.assertIn("remaining `0.1.64` publication instructions", release_preamble)

    def test_desktop_workflow_publishes_native_installers(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("*.dmg", workflow)
        self.assertIn("*-Setup.exe", workflow)
        self.assertIn("*.AppImage", workflow)
        self.assertIn("version --github-output", workflow)
        self.assertIn(
            "AM-Configurator-${{ steps.build_version.outputs.version }}-"
            "${{ matrix.artifact }}",
            workflow,
        )
        upload = workflow.split("- name: Upload native installer", 1)[1]
        self.assertNotIn(".zip", upload)
        self.assertNotIn(".tar.gz", upload)

        for path in (
            "assets/am-configurator.png",
            "packaging/macos/build_dmg.sh",
            "packaging/linux/build_appimage.sh",
            "packaging/windows/AMConfigurator.iss",
            "packaging/windows/build_installer.ps1",
        ):
                with self.subTest(path=path):
                    self.assertTrue((ROOT / path).is_file())

    def test_workflow_actions_match_the_reviewed_node24_contract(self) -> None:
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in (
                ROOT / ".github" / "workflows" / "ci.yml",
                ROOT / ".github" / "workflows" / "desktop.yml",
                ROOT / ".github" / "workflows" / "release.yml",
            )
        }
        uses_refs = [
            re.sub(r"\s+#.*$", "", match.group(1)).strip()
            for workflow in workflows.values()
            for match in re.finditer(
                r"^\s*(?:-\s*)?uses:\s*(.+?)\s*$",
                workflow,
                flags=re.MULTILINE,
            )
        ]
        action_refs = Counter(ref for ref in uses_refs if not ref.startswith("./"))
        expected_refs = Counter(
            {
                "actions/checkout@v7": 10,
                (
                    "astral-sh/setup-uv@"
                    "c771a70e6277c0a99b617c7a806ffedaca235ff9"
                ): 6,
                "actions/upload-artifact@v7": 6,
                (
                    "actions/download-artifact@"
                    "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
                ): 3,
                (
                    "actions/attest-build-provenance@"
                    "0f67c3f4856b2e3261c31976d6725780e5e4c373"
                ): 4,
                "softprops/action-gh-release@v2": 1,
            }
        )

        self.assertEqual(expected_refs, action_refs)

        retired_refs = (
            "actions/checkout@v4",
            "actions/upload-artifact@v4",
            "astral-sh/setup-uv@v6",
            (
                "actions/download-artifact@"
                "d3f86a106a0bac45b974a628896c90dbdf5c8093"
            ),
            (
                "actions/attest-build-provenance@"
                "e8998f949152b193b063cb0ec769d69d929409be"
            ),
        )
        combined_workflows = "\n".join(workflows.values())
        for retired_ref in retired_refs:
            with self.subTest(retired_ref=retired_ref):
                self.assertNotIn(retired_ref, combined_workflows)

        for name, workflow in workflows.items():
            setup_steps = [
                block
                for block in re.split(r"(?m)(?=^      - )", workflow)
                if "uses: astral-sh/setup-uv@" in block
            ]
            with self.subTest(workflow=name):
                self.assertGreaterEqual(len(setup_steps), 1)
                for setup_step in setup_steps:
                    self.assertRegex(
                        setup_step,
                        (
                            r"(?m)^        with:\n"
                            r"(?:          .*\n)*"
                            r"          prune-cache: true$"
                        ),
                    )

    def test_signed_release_publishes_one_release_only_from_a_tag(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        signed, publish = workflow.split("  publish:\n", 1)
        version = "${{ steps.build_version.outputs.version }}"

        # Publication is one downstream upload, never three concurrent ones.
        self.assertEqual(1, workflow.count("softprops/action-gh-release@v2"))
        self.assertNotIn("softprops/action-gh-release", signed)
        self.assertIn("needs: [macos, windows, linux]", publish)

        # A manual dispatch has no tag to attach assets to.
        self.assertIn(
            "if: github.event_name == 'push' && "
            "startsWith(github.ref, 'refs/tags/v')",
            publish,
        )

        # Only this job may write to the repository.
        self.assertNotIn("contents: write", signed)
        self.assertIn("permissions:\n      contents: write", publish)

        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
            publish,
        )
        self.assertIn(f"pattern: AM-Configurator-{version}-*", publish)
        self.assertIn("merge-multiple: true", publish)
        self.assertIn("build_tools/release_manifest.py", publish)
        self.assertIn(f'--version "{version}"', publish)
        self.assertIn('--commit "${{ github.sha }}"', publish)
        self.assertIn('--run-id "${{ github.run_id }}"', publish)
        self.assertIn('--run-number "${{ github.run_number }}"', publish)
        self.assertIn('--repository "${{ github.repository }}"', publish)

        # Title, body source, and flags of every release published so far.
        self.assertIn("tag_name: ${{ github.ref_name }}", publish)
        self.assertIn(f"name: AM Configurator {version}", publish)
        self.assertIn(f"body_path: docs/releases/{version}.md", publish)
        self.assertIn("draft: false", publish)
        self.assertIn("prerelease: false", publish)
        self.assertIn("make_latest: true", publish)
        self.assertNotIn("generate_release_notes", publish)

        # An unmatched file is otherwise ignored, publishing a short release.
        self.assertIn("fail_on_unmatched_files: true", publish)
        for filename in (
            f"AM-Configurator-{version}-macOS-arm64.dmg",
            f"AM-Configurator-{version}-Windows-x64-Setup.exe",
            f"AM-Configurator-{version}-Linux-x86_64.AppImage",
        ):
            with self.subTest(asset=filename):
                self.assertIn(f"release-installers/{filename}", publish)
        self.assertIn("release-metadata/SHA256SUMS.txt", publish)
        self.assertIn("release-metadata/release-manifest.json", publish)

        # The release body is committed, so a tag without it fails in seconds
        # instead of after signing and notarization.
        identity = workflow.split("  release-identity:\n", 1)[1].split(
            "  macos:\n", 1
        )[0]
        self.assertIn('notes="docs/releases/$RELEASE_VERSION.md"', identity)
        self.assertIn('if [ ! -s "$notes" ]; then', identity)

    def test_release_tags_do_not_rebuild_a_different_version(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        trigger = workflow.split("permissions:", 1)[0]

        self.assertIn("branches:", trigger)
        self.assertIn("- main", trigger)
        self.assertNotIn("tags:", trigger)

    def test_main_installers_receive_keyless_provenance(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        installing = (ROOT / "docs" / "installing.md").read_text(encoding="utf-8")
        unprivileged, provenance = workflow.split("  provenance:\n", 1)
        pinned_action = (
            "actions/attest-build-provenance@"
            "0f67c3f4856b2e3261c31976d6725780e5e4c373"
        )

        self.assertNotIn("id-token: write", unprivileged)
        self.assertNotIn("attestations: write", unprivileged)
        self.assertIn("needs: [installer, candidate-metadata]", provenance)
        self.assertIn("github.event_name == 'push'", provenance)
        self.assertIn("github.ref == 'refs/heads/main'", provenance)
        self.assertIn(
            "permissions:\n"
            "      contents: read\n"
            "      id-token: write\n"
            "      attestations: write",
            provenance,
        )
        self.assertEqual(4, provenance.count(pinned_action))
        self.assertNotIn("actions/attest-build-provenance@v", provenance)
        for filename in (
            "AM-Configurator-${{ steps.build_version.outputs.version }}"
            "-macOS-arm64.dmg",
            "AM-Configurator-${{ steps.build_version.outputs.version }}"
            "-Windows-x64-Setup.exe",
            "AM-Configurator-${{ steps.build_version.outputs.version }}"
            "-Linux-x86_64.AppImage",
        ):
            with self.subTest(subject=filename):
                self.assertIn(f"subject-path: candidate-provenance/{filename}", provenance)
        self.assertIn(
            "subject-path: |\n"
            "            candidate-provenance/release-manifest.json\n"
            "            candidate-provenance/SHA256SUMS.txt",
            provenance,
        )
        self.assertIn(
            "gh attestation verify <downloaded-file> --repo roethlar/AMKB-GUI",
            installing,
        )
        self.assertIn(
            "does not replace platform code signing",
            " ".join(installing.split()),
        )

    def test_desktop_workflow_runs_frozen_native_policy_on_every_platform(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        # Three supported platforms plus the two experimental ARM64 targets.
        self.assertEqual(5, workflow.count("--native-policy-smoke"))
        for platform_name in ("macos", "windows", "linux"):
            with self.subTest(platform=platform_name):
                self.assertIn(
                    f"Verify native webview policy ({platform_name})",
                    workflow,
                )
        self.assertIn("xvfb-run", workflow)

    def test_linux_native_webview_prerequisites_are_installed(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        for package in (
            "gcc",
            "pkg-config",
            "libcairo2-dev",
            "libgirepository1.0-dev",
            "gir1.2-gtk-3.0",
            "gir1.2-webkit2-4.1",
            "libwebkit2gtk-4.1-dev",
            "xauth",
            "xvfb",
        ):
            with self.subTest(package=package):
                self.assertIn(package, workflow)
        prerequisite_step = workflow.split(
            "- name: Install native build prerequisites (Linux)", 1
        )[1].split("- name: Install desktop build environment", 1)[0]
        self.assertIn("--no-install-recommends", prerequisite_step)
        for forbidden in (
            "libegl1",
            "libxcb-cursor0",
            "libxcb-icccm4",
            "libxcb-keysyms1",
            "libxcb-shape0",
            "libxcb-xkb1",
            "libxkbcommon-x11-0",
            "gstreamer1.0-libav",
            "libgirepository-2.0-dev",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, prerequisite_step)

    def test_linux_bundle_uses_gtk_and_repository_gi_hooks(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text("utf-8")

        for hidden_import in (
            "webview.platforms.gtk",
            "gi.repository.Gtk",
            "gi.repository.Gdk",
            "gi.repository.Gio",
            "gi.repository.GLib",
            "gi.repository.WebKit2",
            "gi.repository.Soup",
            "gi.repository.JavaScriptCore",
        ):
            with self.subTest(hidden_import=hidden_import):
                self.assertIn(f'"{hidden_import}"', spec)
        self.assertNotIn('"webview.platforms.qt"', spec)
        self.assertIn(
            'hookspath=[str(project / "packaging" / "hooks")]',
            spec,
        )
        hook_contracts = {
            "hook-gi.repository.WebKit2.py": (
                '("WebKit2", "4.1")',
                '("JavaScriptCore", "4.1")',
            ),
            "hook-gi.repository.Soup.py": ('("Soup", "3.0")',),
            "hook-gi.repository.JavaScriptCore.py": (
                '("JavaScriptCore", "4.1")',
            ),
        }
        for filename, contracts in hook_contracts.items():
            with self.subTest(hook=filename):
                hook = ROOT / "packaging" / "hooks" / filename
                self.assertTrue(hook.is_file())
                source = hook.read_text("utf-8")
                self.assertIn("get_gi_typelibs", source)
                for contract in contracts:
                    self.assertIn(contract, source)

        webkit_hook = (
            ROOT / "packaging" / "hooks" / "hook-gi.repository.WebKit2.py"
        ).read_text("utf-8")
        self.assertIn("prepare_webkitgtk_bundle", webkit_hook)
        self.assertIn('CONF["workpath"]', webkit_hook)

        pre_safe_hooks = ROOT / "packaging" / "hooks" / "pre_safe_import_module"
        for namespace in ("WebKit2", "Soup", "JavaScriptCore"):
            with self.subTest(pre_safe_hook=namespace):
                hook = pre_safe_hooks / f"hook-gi.repository.{namespace}.py"
                self.assertTrue(hook.is_file())
                source = hook.read_text("utf-8")
                self.assertIn("def pre_safe_import_module(api):", source)
                self.assertIn("api.add_runtime_module(api.module_name)", source)

    def test_linux_bundle_carries_native_backend_licenses(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text("utf-8")
        notices = (ROOT / "THIRD_PARTY_NOTICES").read_text("utf-8").casefold()

        for component in ("gtk", "webkitgtk", "libsoup"):
            with self.subTest(component=component):
                self.assertIn(component, notices)
                self.assertIn(
                    f'required_linux_license(\n                "{component}"',
                    spec,
                )
        self.assertIn('f"licenses/linux-native/{component}"', spec)
        for required_source in (
            "/usr/share/common-licenses/LGPL-2.1",
            "/usr/share/common-licenses/LGPL-2",
            "/usr/share/licenses/webkit2gtk-4.1/LICENSE",
            "/usr/share/doc/libwebkit2gtk-4.1-0/copyright",
        ):
            with self.subTest(required_source=required_source):
                self.assertIn(required_source, spec)

    def test_native_tree_audit_is_wired_into_every_packaging_path(self) -> None:
        build_script = (ROOT / "build.py").read_text("utf-8")
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            "utf-8"
        )
        appimage = (ROOT / "packaging" / "linux" / "build_appimage.sh").read_text(
            "utf-8"
        )

        audit_command = "build_tools/native_tree_audit.py"
        self.assertIn(audit_command, build_script)
        # Once per supported build and once per experimental ARM64 target.
        self.assertEqual(2, workflow.count(audit_command))
        self.assertLess(
            workflow.index("Build native application"),
            workflow.index("Audit frozen native tree"),
        )
        self.assertLess(
            workflow.index("Audit frozen native tree"),
            workflow.index("Verify native webview policy (macos)"),
        )
        self.assertIn('audit_root="$(mktemp -d ', appimage)
        self.assertIn("--appimage-extract", appimage)
        self.assertIn(audit_command, appimage)
        self.assertLess(appimage.index(audit_command), appimage.index("--smoke-test"))

    def test_desktop_workflow_has_no_retired_media_build_toolchain(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        lowered = workflow.casefold()
        retired_tool = "ff" + "mpeg"
        for forbidden in (
            retired_tool,
            "gnupg",
            "msys2",
            "mingw",
            "diffutils",
            "build-essential",
            "zlib1g-dev",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_desktop_workflow_has_no_obsolete_vulkan_setup(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("vulkan", workflow.casefold())

    def test_ci_runs_each_node_gate_as_a_failure_sensitive_step(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for command in (
            "node --test tests/web/*.test.js",
            "node --check am_configurator/web/lighting_state.js",
            "node --check am_configurator/web/lighting_workspace.js",
            "node --check am_configurator/web/lighting_review.js",
            "node --check am_configurator/web/lighting_targets.js",
            "node --check am_configurator/web/lighting_composer.js",
            "node --check am_configurator/web/library_state.js",
            "node --check am_configurator/web/app.js",
        ):
            self.assertIn(f"run: {command}", workflow)

    def test_ci_exercises_the_declared_python_floor(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        # library.py gates Windows private directories on CPython 3.11.10+, so
        # the floor is load-bearing rather than a nominal metadata value.
        self.assertEqual(">=3.11", metadata["project"]["requires-python"])
        self.assertIn('python: "3.11"', workflow)
        self.assertIn("python-version: ${{ matrix.python }}", workflow)
        self.assertNotIn('python-version: "3.12"', workflow)

    def test_release_pipeline_has_no_llama_build_commands(self) -> None:
        paths = (
            ROOT / "build.py",
            ROOT / ".github" / "workflows" / "desktop.yml",
            ROOT / "packaging" / "am_configurator.spec",
            ROOT / "packaging" / "macos" / "build_dmg.sh",
            ROOT / "packaging" / "linux" / "build_appimage.sh",
            ROOT / "packaging" / "windows" / "build_installer.ps1",
        )
        release_surface = "\n".join(path.read_text("utf-8") for path in paths)
        release_surface = release_surface.casefold().replace("ollama", "")

        for forbidden in ("llama", "gguf", "ggml"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, release_surface)

    def test_linux_appimagetool_uses_immutable_release_assets(self) -> None:
        script = (ROOT / "packaging" / "linux" / "build_appimage.sh").read_text(
            encoding="utf-8"
        )
        checksums = {
            "x86_64": "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
            "aarch64": "f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158",
            "i686": "7ad9ff47c203aae0149b18f6df9e3018b2e2f470ea644a0413e3ded39e9e3bdb",
            "armhf": "42b61cba5495d8aaf418a5c9a015a49b85ad92efabcbd3c341f1540440e4e23d",
        }

        self.assertIn('appimagetool_version="1.9.1"', script)
        self.assertNotIn("/continuous/", script)
        self.assertIn(
            "releases/download/$appimagetool_version/appimagetool-$arch.AppImage",
            script,
        )
        for arch, checksum in checksums.items():
            with self.subTest(arch=arch):
                self.assertIn(f'{arch}) checksum="{checksum}" ;;', script)
        self.assertIn(
            '  *)\n'
            '    echo "Unsupported appimagetool architecture: $arch" >&2\n'
            "    exit 1\n"
            "    ;;",
            script,
        )
        self.assertIn(
            'tool_dir="$project_root/build/appimage-tools/$appimagetool_version"',
            script,
        )
        self.assertIn(
            'tool_path="$tool_dir/appimagetool-$arch-$checksum.AppImage"',
            script,
        )

    def test_brand_icon_is_wired_into_every_distribution(self) -> None:
        icon_paths = {
            "assets/am-configurator.png": (1024, 1024),
            "assets/am-configurator-512.png": (512, 512),
            "am_configurator/web/icon.png": (128, 128),
        }
        for relative_path, expected_size in icon_paths.items():
            with self.subTest(path=relative_path):
                with Image.open(ROOT / relative_path) as icon:
                    self.assertEqual(expected_size, icon.size)

        self.assertTrue((ROOT / "assets" / "am-configurator.icns").is_file())
        self.assertTrue((ROOT / "assets" / "am-configurator.ico").is_file())

        spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")
        windows = (ROOT / "packaging" / "windows" / "AMConfigurator.iss").read_text(
            encoding="utf-8"
        )
        linux = (ROOT / "packaging" / "linux" / "build_appimage.sh").read_text(
            encoding="utf-8"
        )
        server = (ROOT / "am_configurator" / "server.py").read_text(encoding="utf-8")
        html = (ROOT / "am_configurator" / "web" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("am-configurator.icns", spec)
        self.assertIn("am-configurator.ico", spec)
        self.assertIn("SetupIconFile=..\\..\\assets\\am-configurator.ico", windows)
        self.assertIn("assets/am-configurator-512.png", linux)
        self.assertIn('"/icon.png": "icon.png"', server)
        self.assertIn('<link rel="icon" href="/icon.png"', html)
        self.assertIn('<img src="/icon.png" alt="">', html)
        self.assertNotIn('class="brand-mark"', html)

    def test_public_screenshots_are_release_sized_and_metadata_free(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        expected = {
            "keymap.png": (1600, 1000),
            "macros.png": (1600, 1000),
            "lighting.png": (1600, 1000),
            "ai-setup.png": (1600, 1000),
            "ai-generate.png": (1600, 1000),
            "board-cyberboard.png": (1600, 1000),
            "board-relic80.png": (1600, 1000),
            "board-afa.png": (1600, 1000),
            "board-neon80.png": (1600, 1000),
        }
        for filename, dimensions in expected.items():
            with self.subTest(filename=filename):
                path = ROOT / "docs" / "images" / filename
                with Image.open(path) as screenshot:
                    self.assertEqual("PNG", screenshot.format)
                    self.assertEqual("RGB", screenshot.mode)
                    self.assertEqual(dimensions, screenshot.size)
                    self.assertEqual({}, screenshot.info)
                self.assertEqual(1, readme.count(f"docs/images/{filename}"))

    def test_native_bundle_ships_project_license_and_attribution(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")

        # The protocol layer is derived from MIT-licensed cyberboard-cli, whose
        # notice must travel with every copy. Shipping it only as the Windows
        # installer's click-through LicenseFile leaves the macOS app bundle and
        # the Linux AppImage carrying derived code with no notice at all.
        self.assertIn('(str(project / "LICENSE"), ".")', spec)
        self.assertIn('(str(project / "THIRD_PARTY_NOTICES"), ".")', spec)
        # GeneralD's full MIT text and copyright are preserved as a bundled
        # file; native distributions must carry it, not only the repository.
        self.assertIn(
            '(str(project / "licenses" / "cyberboard-cli-LICENSE.txt"), "licenses")',
            spec,
        )
        upstream = ROOT / "licenses" / "cyberboard-cli-LICENSE.txt"
        self.assertTrue(upstream.is_file())
        upstream_text = " ".join(upstream.read_text("utf-8").split())
        self.assertIn("Copyright (c) 2026 GeneralD", upstream_text)
        self.assertIn("MIT License", upstream_text)

        self.assertTrue((ROOT / "LICENSE").is_file())
        # Both notices are hard-wrapped prose; compare on collapsed whitespace so
        # rewrapping a paragraph cannot silently void the assertion.
        notices = " ".join((ROOT / "THIRD_PARTY_NOTICES").read_text("utf-8").split())
        licence = " ".join((ROOT / "LICENSE").read_text("utf-8").split())
        self.assertIn("cyberboard-cli", notices)
        self.assertIn("MIT License", licence)
        # The project's own license carries the project's copyright, not the
        # upstream's; GeneralD's notice is preserved in the bundled file above.
        self.assertIn("Copyright (c) 2026 Michael Coelho", licence)
        self.assertNotIn("ff" + "mpeg", notices.casefold())
        # The Neon's axial LED payload ordering is derived from the Apache-2.0
        # neon80_driver. The obligation attaches to the derived data, so the
        # attribution has to travel in every artifact, not only the repository.
        self.assertIn("neon80_driver", notices)
        self.assertIn("Apache License, Version 2.0", notices)
        # And the application's own licence is unchanged: the superseding
        # decision keeps it MIT, so a stray GPL grant here would be a
        # regression, not an addition.
        self.assertNotIn("GNU General Public License", licence)

    def _sdist_include(self) -> list[str]:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        targets = metadata["tool"]["hatch"]["build"]["targets"]
        self.assertIn(
            "sdist",
            targets,
            "pyproject.toml declares no [tool.hatch.build.targets.sdist]; hatchling "
            "then falls back to shipping every tracked file, which publishes "
            ".agents/, .claude/, and the internal plan documents.",
        )
        return targets["sdist"]["include"]

    def test_sdist_allowlist_excludes_governance_and_internal_material(self) -> None:
        include = self._sdist_include()

        for forbidden in _SDIST_FORBIDDEN:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, include)
                self.assertNotIn(f"/{forbidden}", include)
                self.assertNotIn(forbidden.rstrip("/"), include)
        for required in (
            "/am_configurator/",
            "/build_tools/",
            "/packaging/",
            "/tests/",
            "/LICENSE",
            "/THIRD_PARTY_NOTICES",
            "/licenses/",
        ):
            with self.subTest(required=required):
                self.assertIn(required, include)

        # Root-anchored patterns only. A bare "README.md" is gitignore-style and
        # also matches docs/verification/*/README.md, which silently republishes
        # internal material; that exact leak was observed before anchoring.
        for pattern in include:
            with self.subTest(pattern=pattern):
                self.assertTrue(pattern.startswith("/"), pattern)

    def test_every_tracked_top_level_entry_is_classified(self) -> None:
        """A new top-level entry must be classified before it can silently ship.

        This is what keeps the allowlist honest without anyone remembering it
        exists: add a directory and forget it here, and the gate says so.
        """
        listing = subprocess.run(
            ("git", "ls-tree", "--name-only", "HEAD"),
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if listing.returncode != 0:
            self.skipTest("git is unavailable")

        allowlisted = {
            entry.strip("/").split("/", 1)[0] for entry in self._sdist_include()
        }
        # Deliberately excluded. "docs" is here because only docs/images/ ships.
        excluded = {
            ".agents",
            ".claude",
            ".codex",
            ".gitattributes",
            ".github",
            ".gitignore",
            "AGENTS.md",
            "CLAUDE.md",
            "docs",
        }

        entries = listing.stdout.split()
        self.assertTrue(entries, "git listed no tracked top-level entries")
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertIn(entry, allowlisted | excluded)

    def test_the_neon_udev_rule_ships_and_keeps_the_shared_vial_serial(self) -> None:
        """The Linux permission remedy is useless if the rule is not published.

        The serial in the rule is Vial's fixed magic string, shared by every
        Vial keyboard. Narrowing it to one board's identifier would silently
        break the rule for every other unit, so the guard pins it.
        """
        rule_path = ROOT / "am_configurator" / "data" / "60-am-neon-80.rules"
        self.assertTrue(rule_path.is_file(), "the udev rule is missing")

        rule = rule_path.read_text(encoding="utf-8")
        self.assertIn('KERNEL=="hidraw*"', rule)
        self.assertIn('ATTRS{serial}=="*vial:f64c2b3c*"', rule)
        self.assertIn('TAG+="uaccess"', rule)

    def test_the_udev_rule_reaches_the_artifacts_users_actually_install(self) -> None:
        """Checking the sdist alone is what let this ship broken.

        A wheel user and an AppImage user have no source archive. The previous
        guard asserted only that /packaging/ was on the sdist allowlist, which
        looked like coverage and was not: the built wheel contained the rule
        zero times.
        """
        # Wheel: `packages` does not carry non-Python files by itself.
        wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        artifacts = wheel["tool"]["hatch"]["build"]["targets"]["wheel"].get("artifacts", [])
        self.assertTrue(
            any("rules" in pattern for pattern in artifacts),
            f"the wheel ships no udev rule: {artifacts}",
        )

        # PyInstaller bundle, which is what the AppImage wraps.
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")
        self.assertIn('"am_configurator" / "data"', spec)
        self.assertIn('"am_configurator/data"', spec)

    def test_the_runtime_names_the_rule_where_it_is_actually_installed(self) -> None:
        """The message must resolve a real path, not a source-tree path."""
        from am_configurator import hid_transport

        self.assertTrue(hid_transport.udev_rule_path().is_file())

        source = (ROOT / "am_configurator" / "hid_transport.py").read_text(encoding="utf-8")
        self.assertNotIn("packaging/linux/60-am-neon-80.rules", source)
        self.assertNotIn("docs/neon-80-linux.md", source)

    def test_the_rule_is_obtainable_without_a_filesystem_path(self) -> None:
        """A path is worthless to an AppImage user, who has the greatest need.

        Inside an AppImage the package sits on a temporary mount that vanishes
        on exit, and the shell's Python cannot import it to ask where it is. So
        the application prints the rule's contents, which works identically for
        an AppImage, a wheel, and a source checkout.
        """
        from am_configurator import desktop, hid_transport

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(0, desktop.main(["--print-udev-rule"]))
        self.assertIn('ATTRS{serial}=="*vial:f64c2b3c*"', buffer.getvalue())

        # The guidance must not tell a user to resolve a path.
        remedy = hid_transport._permission_remedy.__doc__ or ""
        source = (ROOT / "am_configurator" / "hid_transport.py").read_text(encoding="utf-8")
        self.assertIn("--print-udev-rule", source)

        doc = (ROOT / "docs" / "neon-80-linux.md").read_text(encoding="utf-8")
        self.assertIn("--print-udev-rule", doc)
        self.assertNotIn("from am_configurator.hid_transport import udev_rule_path", doc)

    def test_spec_bundles_the_llm_module(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text(encoding="utf-8")

        # The LLM provider layer is imported lazily inside server.py, so
        # PyInstaller's static analysis misses it; it must be a hidden import or
        # the frozen app cannot generate effects.
        self.assertIn("hidden_imports", spec)
        self.assertIn('"am_configurator.llm"', spec)

    def test_secure_credential_dependency_and_os_backends_are_frozen(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text("utf-8")

        self.assertIn("keyring==25.7.0", metadata["project"]["dependencies"])
        self.assertIn('"am_configurator.credentials"', spec)
        for backend in ("macOS", "SecretService", "Windows"):
            self.assertIn(f'"keyring.backends.{backend}"', spec)

    def test_native_bundle_and_build_surface_have_no_retired_video_stack(self) -> None:
        paths = (
            ROOT / "packaging" / "am_configurator.spec",
            ROOT / "build.py",
            ROOT / "am_configurator" / "desktop.py",
            ROOT / ".github" / "workflows" / "desktop.yml",
            ROOT / "packaging" / "macos" / "build_dmg.sh",
            ROOT / "THIRD_PARTY_NOTICES",
            ROOT / "pyproject.toml",
        )
        shipping_surface = "\n".join(path.read_text("utf-8") for path in paths)
        lowered = shipping_surface.casefold()
        retired_tool = "ff" + "mpeg"
        retired_fixture = "tiny-motion" + ".mp4"
        retired_processor = "process_video" + "_frames"
        for forbidden in (
            retired_tool,
            retired_fixture,
            retired_processor,
            "video/mp4",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

        spec = paths[0].read_text("utf-8")
        macos = paths[4].read_text("utf-8")
        self.assertNotIn("upx=True", spec)
        self.assertEqual(spec.count("upx=False"), 2)
        self.assertIn("codesign --force --sign -", macos)

        removed_paths = (
            ROOT / ".gitattributes",
            ROOT / "am_configurator" / f"{retired_tool}_runtime.py",
            ROOT / "am_configurator" / "media.py",
            ROOT / "build_tools" / f"{retired_tool}_bundle.py",
            ROOT / "build_tools" / f"prepare_{retired_tool}.py",
            ROOT / "build_tools" / f"finalize_{retired_tool}_bundle.py",
            ROOT / "packaging" / retired_tool,
            ROOT / "tests" / "fixtures" / retired_fixture,
            ROOT / "tests" / f"test_{retired_tool}_bundle.py",
        )
        for path in removed_paths:
            with self.subTest(removed=str(path.relative_to(ROOT))):
                self.assertFalse(path.exists())
        for module in (
            f"am_configurator.{retired_tool}_runtime",
            "am_configurator.media",
            f"build_tools.{retired_tool}_bundle",
            f"build_tools.prepare_{retired_tool}",
            f"build_tools.finalize_{retired_tool}_bundle",
        ):
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(module))

    def test_current_surfaces_have_no_retired_media_tool_reference(self) -> None:
        retired_tool = (b"ff" + b"mpeg").lower()
        paths = [
            ROOT / "build.py",
            ROOT / "pyproject.toml",
            ROOT / "README.md",
            ROOT / "THIRD_PARTY_NOTICES",
        ]
        attributes = ROOT / ".gitattributes"
        if attributes.exists():
            paths.append(attributes)
        for root in (
            ROOT / "am_configurator",
            ROOT / "build_tools",
            ROOT / "packaging",
            ROOT / ".github" / "workflows",
            ROOT / "tests",
        ):
            paths.extend(
                path
                for path in root.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix.casefold() not in {".pyc", ".pyo"}
            )

        for path in sorted(set(paths)):
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(path=relative):
                self.assertNotIn(retired_tool.decode("ascii"), relative.casefold())
                if retired_tool in path.read_bytes().lower():
                    self.fail(f"{relative} contains a retired media-tool reference")

    def test_native_packages_are_ollama_api_only(self) -> None:
        spec = (ROOT / "packaging" / "am_configurator.spec").read_text("utf-8")
        build_script = (ROOT / "build.py").read_text("utf-8")
        smoke = (ROOT / "am_configurator" / "desktop.py").read_text("utf-8")
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text("utf-8")
        macos = (ROOT / "packaging" / "macos" / "build_dmg.sh").read_text("utf-8")
        packaged_surface = "\n".join((spec, build_script, workflow, macos)).lower()
        self.assertNotIn("llama", packaged_surface.replace("ollama", ""))

        removed_paths = (
            ROOT / "am_configurator" / "local_ai_runtime.py",
            ROOT / "am_configurator" / "local_model.py",
            ROOT / "build_tools" / "finalize_llama_bundle.py",
            ROOT / "build_tools" / "llama_bundle.py",
            ROOT / "build_tools" / "prepare_llama.py",
            ROOT / "packaging" / "llama",
            ROOT / "tests" / "test_local_ai_runtime.py",
        )
        for path in removed_paths:
            self.assertFalse(path.exists(), str(path.relative_to(ROOT)))
        for forbidden in (
            "llama.cpp",
            "llama-cli",
            "llama-server",
            "llama-runtime",
            "prepare_llama",
            "finalize_llama",
            "local_ai_runtime",
            "local_model",
            "packaging/llama",
            ".gguf",
        ):
            self.assertNotIn(forbidden, packaged_surface)

        product_surface = "\n".join(
            (ROOT / "am_configurator" / name).read_text("utf-8")
            for name in ("procedural_generation.py", "server.py", "web/app.js")
        ).lower()
        self.assertNotIn("llama.cpp", product_surface)
        self.assertNotIn("/api/ai/local/gguf", product_surface)
        self.assertIn("_assert_ollama_api_only_bundle", smoke)
        for forbidden_artifact in ('".gguf"', '"llama-cli"', '"llama-server"'):
            self.assertIn(forbidden_artifact, smoke)

    def test_active_ollama_contract_has_no_local_backend_alias(self) -> None:
        active_sources = {
            name: (ROOT / "am_configurator" / name).read_text("utf-8")
            for name in (
                "ai_capability.py",
                "desktop.py",
                "procedural_generation.py",
                "recipe_provider.py",
                "server.py",
                "web/app.js",
                "web/index.html",
                "web/lighting_state.js",
            )
        }
        combined = "\n".join(active_sources.values())
        for forbidden in (
            "/api/ai/local/",
            "discover_local_models",
            "_local_components",
            'backend == "local"',
            'backend != "local"',
            '"backend": "local"',
            '["ai"]["local"]',
            '["local"]',
            'value="local"',
            'id="settings-ai-local"',
            "settings-local-panel",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

        store_source = (ROOT / "am_configurator" / "store.py").read_text("utf-8")
        active_store = store_source[store_source.index("def update_ai_settings(") :]
        for forbidden in (
            "update_local_ai_settings",
            '["ai"]["local"]',
            '"backend": "local"',
        ):
            with self.subTest(store_forbidden=forbidden):
                self.assertNotIn(forbidden, active_store)

    def test_application_forbids_managed_llama_processes_and_credentials(self) -> None:
        executable_modules = (
            "ai_capability.py",
            "desktop.py",
            "recipe_provider.py",
            "server.py",
        )
        sources = {
            name: (ROOT / "am_configurator" / name).read_text("utf-8")
            for name in executable_modules
        }
        combined = "\n".join(sources.values())

        for forbidden in (
            "ManagedLlamaServer",
            "ManagedLocalRecipeProvider",
            "probe_full_gpu_offload",
            "_run_local_recipe_smoke",
            '"--api-key"',
            "Bearer {token}",
        ):
            self.assertNotIn(forbidden, combined)
        for name in ("ai_capability.py", "recipe_provider.py"):
            self.assertNotIn("subprocess", sources[name])
            self.assertNotIn("Popen", sources[name])

    def test_local_model_and_runtime_attestations_cannot_return(self) -> None:
        removed_paths = (
            ROOT / "am_configurator" / "local_model.py",
            ROOT / "am_configurator" / "local_ai_runtime.py",
            ROOT / "build_tools" / "llama_bundle.py",
            ROOT / "build_tools" / "prepare_llama.py",
            ROOT / "build_tools" / "finalize_llama_bundle.py",
            ROOT / "packaging" / "llama",
        )
        for path in removed_paths:
            self.assertFalse(path.exists(), str(path.relative_to(ROOT)))
        for module in (
            "am_configurator.local_model",
            "am_configurator.local_ai_runtime",
            "build_tools.llama_bundle",
        ):
            self.assertIsNone(importlib.util.find_spec(module), module)

        source_paths = [
            path
            for root in (ROOT / "am_configurator", ROOT / "build_tools")
            for path in root.glob("*.py")
        ]
        source_paths.extend((ROOT / "build.py", ROOT / "packaging" / "am_configurator.spec"))
        source_paths.extend((ROOT / ".github" / "workflows").glob("*"))
        shipping_source = "\n".join(
            path.read_text("utf-8") for path in source_paths if path.is_file()
        )
        shipping_source = shipping_source.replace('"llama-runtime.json"', "").replace(
            '"local-model.json"', ""
        )
        for forbidden in (
            "LocalModelManager",
            "SelectedModel",
            "LocalRuntimeError",
            "RuntimePaths",
            "ATTESTATION_SCHEMA_VERSION",
            "MAX_RUNTIME_ATTESTATION_BYTES",
            "_read_runtime_attestation",
            "runtime_attestation_schema_version",
            "verify_runtime_attestation",
            "packaging/llama",
        ):
            self.assertNotIn(forbidden, shipping_source)

        for path in (ROOT / "packaging").rglob("*"):
            relative = path.relative_to(ROOT / "packaging")
            lowered = relative.as_posix().lower()
            self.assertNotIn("llama", lowered)
            self.assertNotIn(".gguf", lowered)
            self.assertNotIn("local-model.json", lowered)

        capability = (ROOT / "am_configurator" / "ai_capability.py").read_text("utf-8")
        for forbidden in (
            "attestation",
            "from .local_model",
            "import local_model",
            "localmodelmanager",
            "local_ai_runtime",
            "model_path",
            "verify_runtime_attestation",
        ):
            self.assertNotIn(forbidden, capability.lower())

        with TemporaryDirectory(prefix="am-attestation-artifact-") as temporary:
            root = Path(temporary)
            with patch.object(sys, "_MEIPASS", str(root), create=True):
                for name in ("local-model.json", "llama-runtime.json"):
                    artifact = root / name
                    artifact.write_text("{}", encoding="utf-8")
                    with self.subTest(artifact=name), self.assertRaises(SystemExit):
                        desktop._assert_ollama_api_only_bundle()
                    artifact.unlink()

    def test_macos_dmg_detach_survives_a_busy_volume(self) -> None:
        script = (ROOT / "packaging" / "macos" / "build_dmg.sh").read_text(
            encoding="utf-8"
        )

        # A single detach immediately after the smoke-test process exits loses a
        # race with macOS releasing the volume, and under `set -e` that fired the
        # exit trap, which then ran rm -rf across a still-mounted read-only image.
        self.assertIn("detach_mount()", script)
        self.assertIn("-force", script)
        self.assertNotIn('hdiutil detach "$mount_dir" -quiet\nmounted=0', script)
        # rm must never run against a mount that is still attached.
        self.assertIn('if [[ "$mounted" == 0 ]]; then\n    rm -rf "$mount_dir"', script)
        # Detaching is cleanup, not a product signal: the image is verified and
        # smoke-tested before this point, so it must not fail the build.
        self.assertIn('|| echo "warning: could not detach', script)
        self.assertIn('echo "$output_path"', script)

    def test_windows_installer_smoke_test_waits_for_gui_processes(self) -> None:
        script = (ROOT / "packaging" / "windows" / "build_installer.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "Start-Process -FilePath $installer -ArgumentList $installerArgs -Wait -PassThru",
            script,
        )
        self.assertIn(
            "Start-Process -FilePath $installedApp -ArgumentList \"--smoke-test\" -Wait -PassThru",
            script,
        )

    def test_windows_installer_accepts_official_inno_install_scopes(self) -> None:
        script = (ROOT / "packaging" / "windows" / "build_installer.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("${env:ProgramFiles(x86)}", script)
        self.assertIn("$env:LOCALAPPDATA", script)
        self.assertIn('"Programs\\Inno Setup 6\\ISCC.exe"', script)
        self.assertIn("Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }", script)

    def test_the_udev_install_command_elevates_the_write_not_the_reader(self) -> None:
        """`sudo app > /etc/...` cannot work, however natural it looks.

        The shell opens a `>` target as the invoking user, before `sudo` runs,
        so redirecting into a root-owned directory fails with permission denied
        no matter how the application is elevated. Only the write may be
        elevated, which means piping into `tee`.
        """
        doc = (ROOT / "docs" / "neon-80-linux.md").read_text(encoding="utf-8")
        source = (ROOT / "am_configurator" / "hid_transport.py").read_text(encoding="utf-8")

        for name, text in (("docs", doc), ("runtime", source)):
            with self.subTest(surface=name):
                self.assertIn("sudo tee", text)
                self.assertNotIn("sudo ./AM_Configurator.AppImage --print-udev-rule >", text)
                self.assertNotIn("sudo am-configurator --print-udev-rule >", text)
                self.assertNotIn("--print-udev-rule > /etc/udev", text)

    def test_public_docs_describe_the_current_release_without_security_bypasses(
        self,
    ) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        installing = (ROOT / "docs" / "installing.md").read_text(encoding="utf-8")
        neon_linux = (ROOT / "docs" / "neon-80-linux.md").read_text(
            encoding="utf-8"
        )
        download = readme.split("## Download", 1)[1].split("\n## ", 1)[0]
        public_docs = "\n".join((readme, installing, neon_linux))
        collapsed = " ".join(public_docs.split())

        self.assertNotIn("Before the first tagged release", readme)
        self.assertNotIn("increasing build version", readme)
        self.assertNotIn("Desktop installers workflow", download)
        self.assertIn(
            "https://github.com/roethlar/AMKB-GUI/releases",
            download,
        )
        self.assertIn("| AM Neon 80 | `NEON80` |", readme)
        for expected in (
            "87-key physical layout",
            "89 axial LEDs",
            "46×5",
            "four keymap layers",
            "16 macros",
            "GIF, PNG, BMP, and JPEG",
            "pan, zoom, or stretch",
            "Pulse, Hue cycle, Sweep, Shimmer, and Move & zoom",
            "AI is off by default",
            "no automatic Ollama discovery",
            "full write replaces keymaps, macros, and LED data",
            "does not expose LED read-back",
            "docs/neon-80-linux.md",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, collapsed)

        # Verification steps a user can actually perform on a signed release:
        # digest, publisher signature, and the one platform prompt that survives
        # signing (SmartScreen reputation on Windows). The macOS Privacy &
        # Security "Open Anyway" detour belonged to the unsigned era and is
        # prohibited below, not expected here.
        for expected in (
            "SHA256SUMS.txt",
            "gh attestation verify",
            "xcrun stapler validate",
            "Get-AuthenticodeSignature",
            "More info",
            "Run anyway",
            "Get-FileHash",
            "chmod +x",
        ):
            with self.subTest(installing=expected):
                self.assertIn(expected, installing)

        for prohibited in (
            "xattr -dr",
            "spctl --master-disable",
            "disable gatekeeper",
            "disable smartscreen",
            "disable defender",
            "defender exclusion",
            # Unsigned-era copy. Installers are platform-signed as of the
            # 2026-08-07 owner override, so instructions that route a user
            # through the Gatekeeper override, or that call the packages
            # unsigned, are now false rather than merely stale.
            "open anyway",
            "not code-signed",
            "not notarized",
            "no authenticode publisher signature",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, public_docs.casefold())

    def test_current_0_1_67_release_notes_describe_the_signed_release(self) -> None:
        """0.1.67 is the first platform-signed release.

        The release notes are the published Release body (`release-identity`
        refuses a tag without them), so the signing claims in this file are the
        public claims. 0.1.66 stated the opposite — not notarized, no
        Authenticode publisher signature — and that copy must not survive a
        version bump, in either direction: an unsigned-era sentence left behind,
        or a warning-free Windows promise the certificate has not earned yet.
        The `docs/installing.md` filename examples moved to 0.1.68 with the
        version bump, so this test no longer asserts them.
        """

        release_path = ROOT / "docs" / "releases" / "0.1.67.md"
        self.assertTrue(release_path.is_file(), "0.1.67 release notes are missing")

        release = release_path.read_text(encoding="utf-8")
        collapsed = " ".join(release.split())

        self.assertIn("# AM Configurator 0.1.67", release)

        for filename in (
            "AM-Configurator-0.1.67-macOS-arm64.dmg",
            "AM-Configurator-0.1.67-Windows-x64-Setup.exe",
            "AM-Configurator-0.1.67-Linux-x86_64.AppImage",
        ):
            with self.subTest(filename=filename):
                self.assertIn(filename, release)

        for expected in (
            "Apple Developer ID Application certificate",
            "notarized by Apple",
            "Azure Trusted Signing",
            "The Linux AppImage is unsigned",
            "SmartScreen",
            "reports no attestation for them",
            "AI is optional and off by default",
            "procedural LED settings",
            "rendered locally",
            "does not expose LED read-back",
            "Remote provider paths are experimental",
            "not affiliated with or endorsed by Angry Miao",
            "https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.67",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, collapsed)

        for prohibited in (
            "not notarized",
            "no Authenticode publisher signature",
            "not code-signed",
            "unsigned by design",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, collapsed.casefold())
        self.assertNotRegex(collapsed.casefold(), r"\b(?:beta|prerelease)\b")

        # The 2026-08-03 copy ruling: announcement and release-note copy states
        # benefits and safety properties, never dialog-level mechanics (how a
        # confirmation or unlock is performed). Commit 4c60d3c stripped exactly
        # this kind of button copy out of the 0.1.66 announcement draft. The
        # per-operating-system first-launch steps belong to
        # docs/installing.md, which this body links.
        for mechanics in (r"\bmore info\b", r"\brun anyway\b", r"\bopen anyway\b"):
            with self.subTest(mechanics=mechanics):
                self.assertNotRegex(collapsed.casefold(), mechanics)

    def test_current_0_1_66_release_packet_is_consistent(self) -> None:
        release_path = ROOT / "docs" / "releases" / "0.1.66.md"
        reddit_path = ROOT / "docs" / "announcements" / "reddit-0.1.66.md"

        self.assertTrue(release_path.is_file(), "0.1.66 release notes are missing")
        self.assertTrue(reddit_path.is_file(), "0.1.66 Reddit draft is missing")

        release = release_path.read_text(encoding="utf-8")
        reddit = reddit_path.read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        installing = (ROOT / "docs" / "installing.md").read_text(encoding="utf-8")
        current_packet = "\n".join((release, reddit))

        self.assertIn("# AM Configurator 0.1.66", release)
        self.assertIn("> **Unposted draft.**", reddit)
        self.assertIn("AM Configurator 0.1.66", reddit)
        self.assertNotIn("docs/releases/0.1.65.md", readme)
        self.assertIn("Release notes are published with each GitHub Release.", readme)

        for filename in (
            "AM-Configurator-0.1.66-macOS-arm64.dmg",
            "AM-Configurator-0.1.66-Windows-x64-Setup.exe",
            "AM-Configurator-0.1.66-Linux-x86_64.AppImage",
        ):
            with self.subTest(filename=filename):
                self.assertIn(filename, release)
                self.assertIn(filename, reddit)

        for expected in (
            "Keymap",
            "Macros",
            "Text entry",
            "Flow",
            "Repeat",
            "JPEG",
            "Lighting",
            "Library",
            "AI is optional and off by default",
            "procedural LED settings",
            "rendered locally",
            "does not expose LED read-back",
            "Remote provider paths are experimental",
            "not affiliated with or endorsed by Angry Miao",
            "https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.66",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, current_packet)

        for prohibited in ("ff" + "mpeg", "ai video"):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, current_packet.casefold())

    def test_current_0_1_65_release_packet_is_consistent(self) -> None:
        release_path = ROOT / "docs" / "releases" / "0.1.65.md"
        reddit_path = ROOT / "docs" / "announcements" / "reddit-0.1.65.md"

        self.assertTrue(release_path.is_file(), "0.1.65 release notes are missing")
        self.assertTrue(reddit_path.is_file(), "0.1.65 Reddit draft is missing")

        release = release_path.read_text(encoding="utf-8")
        reddit = reddit_path.read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        installing = (ROOT / "docs" / "installing.md").read_text(encoding="utf-8")
        historical = (
            ROOT / "docs" / "releases" / "0.1.64.md"
        ).read_text(encoding="utf-8") + (
            ROOT / "docs" / "announcements" / "reddit-0.1.64.md"
        ).read_text(encoding="utf-8")
        current_packet = "\n".join((release, reddit))

        self.assertIn("# AM Configurator 0.1.65", release)
        self.assertIn("> **Unposted draft.**", reddit)
        self.assertIn("AM Configurator 0.1.65", reddit)
        self.assertNotIn("0.1.64", current_packet)
        self.assertIn("Rejected unpublished 0.1.64 candidate", historical)
        self.assertNotIn("docs/releases/0.1.64.md", readme)
        self.assertIn("Release notes are published with each GitHub Release.", readme)

        for filename in (
            "AM-Configurator-0.1.65-macOS-arm64.dmg",
            "AM-Configurator-0.1.65-Windows-x64-Setup.exe",
            "AM-Configurator-0.1.65-Linux-x86_64.AppImage",
        ):
            with self.subTest(filename=filename):
                self.assertIn(filename, release)
                self.assertIn(filename, reddit)

        for expected in (
            "Keymap",
            "Macros",
            "Lighting",
            "Library",
            "AI is optional and off by default",
            "procedural LED settings",
            "rendered locally",
            "does not expose LED read-back",
            "Remote provider paths are experimental",
            "not affiliated with or endorsed by Angry Miao",
            "https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.65",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, current_packet)

        for prohibited in ("ff" + "mpeg", "ai video"):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, current_packet.casefold())

    def test_rejected_0_1_64_packet_is_historical_and_not_the_readme_target(
        self,
    ) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        release = (ROOT / "docs" / "releases" / "0.1.64.md").read_text(
            encoding="utf-8"
        )
        reddit = (
            ROOT / "docs" / "announcements" / "reddit-0.1.64.md"
        ).read_text(encoding="utf-8")
        packet = "\n".join((release, reddit))
        collapsed = " ".join(packet.split())

        for text in (release, reddit):
            self.assertIn("Rejected unpublished 0.1.64 candidate", text)
            self.assertIn("AM Configurator 0.1.64", text)
            self.assertNotRegex(text.casefold(), r"\b(?:beta|prerelease)\b")
            self.assertNotIn("unsigned by design", text.casefold())
            self.assertNotIn("UNSIGNED", text)
        for expected in (
            "live-tested on one AM Neon 80",
            "does not expose LED read-back",
            "Windows and Linux installers receive automated native smoke tests",
            "not manually qualified on Windows or Linux",
            "Remote API adapters are experimental",
            "not live-qualified with paid credentials",
            "AM Master",
            "Esc+F2",
            "SHA256SUMS.txt",
            "gh attestation verify",
            "independent community project",
            "not affiliated with or endorsed by Angry Miao",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected.casefold(), collapsed.casefold())
        self.assertNotIn("docs/releases/0.1.64.md", readme)
        self.assertIn("Release notes are published with each GitHub Release.", readme)
        self.assertIn("docs/installing.md", release)
        self.assertIn(
            "https://github.com/roethlar/AMKB-GUI/releases/tag/v0.1.64",
            reddit,
        )
        self.assertIn(
            "https://github.com/roethlar/AMKB-GUI/issues/new/choose",
            reddit,
        )

    def test_bug_report_form_collects_release_and_hardware_context(self) -> None:
        form = (
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
        ).read_text(encoding="utf-8")
        config = (
            ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml"
        ).read_text(encoding="utf-8")

        for field in (
            "id: keyboard",
            "id: firmware",
            "id: os",
            "id: version",
            "id: operation",
            "id: write",
            "id: installer",
            "id: steps",
            "id: expected",
            "id: actual",
            "id: logs",
        ):
            with self.subTest(field=field):
                self.assertIn(field, form)
        for operation in (
            "Device detection / read / write",
            "Keymap",
            "Macros",
            "Lighting paint / media import / local animation",
            "Library / profile import",
            "Optional AI / Ollama",
            "Optional AI / remote API",
        ):
            with self.subTest(operation=operation):
                self.assertIn(operation, form)
        self.assertIn("AM Neon 80", form)
        self.assertIn("0.1.68", form)
        self.assertIn("Remove API keys", form)
        self.assertIn("sanitized", form)
        self.assertIn("blank_issues_enabled: false", config)

if __name__ == "__main__":
    unittest.main()
