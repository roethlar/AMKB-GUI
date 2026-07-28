"""Generate deterministic metadata for one exact cross-platform candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z"
)
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY_PART_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_INSTALLER_SUFFIXES = (".dmg", ".exe", ".appimage")
_HASH_CHUNK_SIZE = 1024 * 1024
_SCHEMA_VERSION = 1


class ReleaseManifestError(ValueError):
    """The candidate set or its provenance is not safe to publish."""


@dataclass(frozen=True)
class ArtifactSpec:
    platform: str
    architecture: str
    filename: str


def expected_artifacts(version: str) -> tuple[ArtifactSpec, ...]:
    """Return the only installer names accepted for a canonical version."""

    _validate_version(version)
    return (
        ArtifactSpec(
            platform="macos",
            architecture="arm64",
            filename=f"AM-Configurator-{version}-macOS-arm64.dmg",
        ),
        ArtifactSpec(
            platform="windows",
            architecture="x64",
            filename=f"AM-Configurator-{version}-Windows-x64-Setup.exe",
        ),
        ArtifactSpec(
            platform="linux",
            architecture="x86_64",
            filename=f"AM-Configurator-{version}-Linux-x86_64.AppImage",
        ),
    )


def _validate_version(version: str) -> None:
    if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(version):
        raise ReleaseManifestError(
            "application version must be a canonical three-part numeric version"
        )


def _validate_source_commit(source_commit: str) -> None:
    if not isinstance(source_commit, str) or not _COMMIT_PATTERN.fullmatch(
        source_commit
    ):
        raise ReleaseManifestError(
            "source commit must be a 40-character lowercase hexadecimal SHA"
        )


def _validate_positive_integer(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReleaseManifestError(f"{field} must be a positive integer")


def _validate_repository(repository: str) -> None:
    if not isinstance(repository, str):
        raise ReleaseManifestError("repository must be an owner/name slug")
    parts = repository.split("/")
    if (
        len(parts) != 2
        or any(part in {"", ".", ".."} for part in parts)
        or any(not _REPOSITORY_PART_PATTERN.fullmatch(part) for part in parts)
    ):
        raise ReleaseManifestError("repository must be an owner/name slug")


def _resolved_candidate_root(candidate_root: Path | str) -> Path:
    supplied = Path(candidate_root)
    if supplied.is_symlink():
        raise ReleaseManifestError("candidate root must not be a symlink")
    try:
        root = supplied.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReleaseManifestError(f"candidate root is unavailable: {exc}") from None
    if not root.is_dir():
        raise ReleaseManifestError("candidate root must be a directory")
    return root


def _resolve_expected_file(root: Path, filename: str) -> Path:
    path = root / filename
    if not path.exists() and not path.is_symlink():
        raise ReleaseManifestError(f"missing required installer: {filename}")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReleaseManifestError(
            f"required installer cannot be resolved: {filename}: {exc}"
        ) from None
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ReleaseManifestError(
            f"required installer escapes the candidate root: {filename}"
        ) from None
    if path.is_symlink():
        raise ReleaseManifestError(
            f"required installer must not be a symlink: {filename}"
        )
    file_stat = path.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ReleaseManifestError(
            f"required installer must be a regular file: {filename}"
        )
    if file_stat.st_size <= 0:
        raise ReleaseManifestError(f"required installer is empty: {filename}")
    return path


def _looks_like_installer(path: Path) -> bool:
    return path.name.casefold().endswith(_INSTALLER_SUFFIXES)


def _reject_unexpected_installers(
    root: Path,
    expected_paths: set[Path],
) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ReleaseManifestError(
                f"candidate root contains a symlink: {path.relative_to(root)}"
            )
        if _looks_like_installer(path) and path not in expected_paths:
            raise ReleaseManifestError(
                f"unexpected installer in candidate root: {path.relative_to(root)}"
            )


def _stream_sha256(path: Path) -> tuple[int, str]:
    before = path.lstat()
    digest = hashlib.sha256()
    with path.open("rb") as candidate:
        while chunk := candidate.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    after = path.lstat()
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or not stat.S_ISREG(after.st_mode):
        raise ReleaseManifestError(
            f"installer changed while hashing: {path.name}"
        )
    return after.st_size, digest.hexdigest()


def _encoded_outputs(
    *,
    version: str,
    source_commit: str,
    workflow_run_id: int,
    workflow_run_number: int,
    repository: str,
    specs: tuple[ArtifactSpec, ...],
    paths: dict[str, Path],
) -> tuple[bytes, bytes]:
    artifacts = []
    checksum_rows = []
    for spec in sorted(specs, key=lambda item: item.filename):
        byte_size, sha256 = _stream_sha256(paths[spec.filename])
        artifacts.append(
            {
                "architecture": spec.architecture,
                "byte_size": byte_size,
                "filename": spec.filename,
                "platform": spec.platform,
                "sha256": sha256,
            }
        )
        checksum_rows.append(f"{sha256}  {spec.filename}")

    manifest = {
        "app_version": version,
        "artifacts": artifacts,
        "repository": repository,
        "schema_version": _SCHEMA_VERSION,
        "source_commit": source_commit,
        "workflow": {
            "run_id": workflow_run_id,
            "run_number": workflow_run_number,
        },
    }
    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    checksums_bytes = ("\n".join(checksum_rows) + "\n").encode("utf-8")
    return manifest_bytes, checksums_bytes


def _output_needs_write(path: Path, expected_name: str, payload: bytes) -> bool:
    if path.name != expected_name:
        raise ReleaseManifestError(f"output path must end with {expected_name}")
    if path.is_symlink():
        raise ReleaseManifestError(f"output must not be a symlink: {expected_name}")
    if not path.exists():
        return True
    if not path.is_file():
        raise ReleaseManifestError(f"output must be a regular file: {expected_name}")
    if path.read_bytes() != payload:
        raise ReleaseManifestError(
            f"refusing to replace conflicting output: {expected_name}"
        )
    return False


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
                raise ReleaseManifestError(
                    f"refusing to replace conflicting output: {path.name}"
                )
            return
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_release_metadata(
    *,
    version: str,
    source_commit: str,
    workflow_run_id: int,
    workflow_run_number: int,
    repository: str,
    candidate_root: Path | str,
    manifest_path: Path | str,
    checksums_path: Path | str,
) -> None:
    """Validate three installers and write their deterministic release metadata."""

    specs = expected_artifacts(version)
    _validate_source_commit(source_commit)
    _validate_positive_integer(workflow_run_id, "workflow run ID")
    _validate_positive_integer(workflow_run_number, "workflow run number")
    _validate_repository(repository)

    root = _resolved_candidate_root(candidate_root)
    paths = {
        spec.filename: _resolve_expected_file(root, spec.filename) for spec in specs
    }
    _reject_unexpected_installers(root, set(paths.values()))

    manifest = Path(manifest_path)
    checksums = Path(checksums_path)
    if manifest.absolute() == checksums.absolute():
        raise ReleaseManifestError("manifest and checksum outputs must differ")
    artifact_paths = {path.absolute() for path in paths.values()}
    if manifest.absolute() in artifact_paths or checksums.absolute() in artifact_paths:
        raise ReleaseManifestError("metadata output cannot replace an installer")

    manifest_bytes, checksums_bytes = _encoded_outputs(
        version=version,
        source_commit=source_commit,
        workflow_run_id=workflow_run_id,
        workflow_run_number=workflow_run_number,
        repository=repository,
        specs=specs,
        paths=paths,
    )

    write_manifest = _output_needs_write(
        manifest,
        "release-manifest.json",
        manifest_bytes,
    )
    write_checksums = _output_needs_write(
        checksums,
        "SHA256SUMS.txt",
        checksums_bytes,
    )
    if write_manifest:
        _atomic_write(manifest, manifest_bytes)
    if write_checksums:
        _atomic_write(checksums, checksums_bytes)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate strict release metadata for three native installers."
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-number", required=True, type=int)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--checksums", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        write_release_metadata(
            version=arguments.version,
            source_commit=arguments.commit,
            workflow_run_id=arguments.run_id,
            workflow_run_number=arguments.run_number,
            repository=arguments.repository,
            candidate_root=arguments.input_dir,
            manifest_path=arguments.manifest,
            checksums_path=arguments.checksums,
        )
    except (OSError, ReleaseManifestError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
