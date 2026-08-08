"""Shared version, digest, and asset helpers for package-manager stubs."""

from __future__ import annotations

import json
import re
from pathlib import Path

from build_tools.release_manifest import expected_artifacts

_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z"
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
# GNU coreutils `sha256sum` / `shasum -a 256` rows: digest, two spaces, filename.
_SUMS_ROW_PATTERN = re.compile(
    r"^([0-9a-f]{64})  (.+)\Z",
    re.IGNORECASE,
)

DEFAULT_RELEASE_ASSET_BASE = (
    "https://github.com/roethlar/AMKB-GUI/releases/download/v{version}"
)
DEFAULT_REPOSITORY = "roethlar/AMKB-GUI"
DEFAULT_HOMEPAGE = "https://github.com/roethlar/AMKB-GUI"


class PackageManagerError(ValueError):
    """A package-manager stub cannot be generated safely."""


def validate_version(version: str) -> str:
    if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(version):
        raise PackageManagerError(
            "application version must be a canonical three-part numeric version"
        )
    return version


def _normalize_digest(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise PackageManagerError(f"{field} must be a 64-character hex SHA-256")
    digest = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(digest):
        raise PackageManagerError(f"{field} must be a 64-character hex SHA-256")
    return digest


def digests_from_sums(path: Path | str) -> dict[str, str]:
    """Parse a SHA256SUMS.txt into filename -> lowercase hex digest."""

    sums_path = Path(path)
    try:
        text = sums_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackageManagerError(f"cannot read checksums file: {exc}") from None
    if not text:
        raise PackageManagerError("checksums file is empty")

    digests: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SUMS_ROW_PATTERN.fullmatch(line)
        if match is None:
            raise PackageManagerError(
                f"checksums file line {line_number} is not a SHA-256 row"
            )
        digest = _normalize_digest(match.group(1), field=f"line {line_number} digest")
        filename = match.group(2).strip()
        if not filename or "/" in filename or "\\" in filename:
            raise PackageManagerError(
                f"checksums file line {line_number} has an unsafe filename"
            )
        if filename in digests and digests[filename] != digest:
            raise PackageManagerError(
                f"checksums file lists conflicting digests for {filename}"
            )
        digests[filename] = digest
    if not digests:
        raise PackageManagerError("checksums file lists no digests")
    return digests


def digests_from_manifest(path: Path | str) -> tuple[str, dict[str, str]]:
    """Parse release-manifest.json into (app_version, filename -> digest)."""

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PackageManagerError(f"cannot read release manifest: {exc}") from None
    except json.JSONDecodeError as exc:
        raise PackageManagerError(f"release manifest is not valid JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise PackageManagerError("release manifest must be a JSON object")

    version = payload.get("app_version")
    if not isinstance(version, str):
        raise PackageManagerError("release manifest is missing app_version")
    version = validate_version(version)

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise PackageManagerError("release manifest lists no artifacts")

    digests: dict[str, str] = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise PackageManagerError(f"artifact {index} must be an object")
        filename = artifact.get("filename")
        sha256 = artifact.get("sha256")
        if not isinstance(filename, str) or not filename:
            raise PackageManagerError(f"artifact {index} is missing filename")
        if "/" in filename or "\\" in filename:
            raise PackageManagerError(f"artifact {index} has an unsafe filename")
        digest = _normalize_digest(sha256, field=f"artifact {filename} sha256")
        if filename in digests and digests[filename] != digest:
            raise PackageManagerError(
                f"release manifest lists conflicting digests for {filename}"
            )
        digests[filename] = digest
    return version, digests


def linux_appimage_filename(version: str) -> str:
    version = validate_version(version)
    for spec in expected_artifacts(version):
        if spec.platform == "linux" and spec.architecture == "x86_64":
            return spec.filename
    raise PackageManagerError(
        f"no Linux x86_64 AppImage is defined for version {version}"
    )


def require_digest(digests: dict[str, str], filename: str) -> str:
    if filename not in digests:
        raise PackageManagerError(f"missing digest for required artifact: {filename}")
    return digests[filename]


def release_download_url(
    version: str,
    filename: str,
    *,
    asset_base: str | None = None,
) -> str:
    version = validate_version(version)
    if not filename or "/" in filename or "\\" in filename:
        raise PackageManagerError("release asset filename is unsafe")
    base_template = asset_base or DEFAULT_RELEASE_ASSET_BASE
    try:
        base = base_template.format(version=version)
    except (KeyError, ValueError) as exc:
        raise PackageManagerError(
            f"asset base URL template is invalid: {exc}"
        ) from None
    return f"{base.rstrip('/')}/{filename}"


def file_sha256(path: Path | str) -> str:
    import hashlib

    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise PackageManagerError(f"cannot hash {target}: {exc}") from None
    if not data:
        raise PackageManagerError(f"refusing to hash empty file: {target}")
    return hashlib.sha256(data).hexdigest()
