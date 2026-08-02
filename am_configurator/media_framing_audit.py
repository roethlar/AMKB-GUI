"""Isolated native-WebView proof for the imported-media framing workflow."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from typing import Any, Iterator, Mapping


AUDIT_VIEWPORTS = ((1000, 680), (1280, 800))
AUDIT_TRANSFORM = {
    "version": 1,
    "offset_x": 0.0,
    "offset_y": 0.0,
    "scale_x": 1.5,
    "scale_y": 1.5,
    "aspect_locked": True,
    "sampling": "box",
    "background": "#000000",
}
REQUIRED_CASE_CHECKS = [
    "raw_import",
    "native_picker_import",
    "unsupported_rejection",
    "saved_source_retrieval",
    "pointer_not_found_capture",
    "pointer_feedback",
    "keyboard_feedback",
    "slider_feedback",
    "selected_frame_tier",
    "render_coalescing",
    "queued_render_ownership",
    "overlay_geometry",
    "synchronized_workspace",
    "shared_timeline",
    "late_source_hold",
    "preview_session_recovery",
    "stale_preview_guard",
    "destination_playback_isolation",
    "canonical_backend_equality",
    "sentinel_pixels",
    "single_apply",
    "undo_dirty_state",
    "save_to_library",
    "library_preview",
    "library_preview_cancel",
    "library_apply",
    "library_apply_undo",
    "library_remove_undo",
    "library_restore",
    "library_permanent_delete",
    "cancel",
    "focus_visible",
    "layout_contained",
]
REQUIRED_PROFILE_CHECKS = [
    "effects_live",
    "effects_apply_undo",
    "reduced_motion",
    "app_native_round_trip",
    "am_master_profile",
    "am_master_lighting_missing_layout",
    "portable_neon_layout",
    "am_master_lighting_offline_layout",
    "am_master_lighting_save_library",
    "am_master_lighting_apply_undo",
]
MAX_REPORT_BYTES = 32_768
_MAX_REPORT_TEXT = 200
_AUDIT_ROOT_PREFIX = "am-media-framing-audit-"
_RESULT_SLOT = "__amMediaFramingAuditResult"


class MediaFramingAuditError(RuntimeError):
    """A bounded, non-sensitive native-audit failure."""


@dataclass(frozen=True)
class ExpectedFrame:
    sentinels: tuple[tuple[int, str], ...]
    non_black: int


@dataclass(frozen=True)
class MediaFixture:
    format: str
    name: str
    mime_type: str
    payload: bytes
    source_frame_count: int
    expected_frames: tuple[ExpectedFrame, ...]


@dataclass(frozen=True)
class JsonFixture:
    kind: str
    name: str
    payload: bytes


class _AuditMediaBridge:
    """Serve one pathless, bounded native-picker selection at a time."""

    def __init__(self, selections: tuple[object, ...]) -> None:
        self._selections = iter(selections)

    def choose_media_file(self) -> dict[str, object] | None:
        try:
            selected = next(self._selections)
        except StopIteration:
            return None
        if isinstance(selected, MediaFixture):
            return {"name": selected.name, "payload": selected.payload}
        if isinstance(selected, Mapping):
            return dict(selected)
        raise TypeError("Unsupported audit media selection.")


_FRAME_ZERO = ExpectedFrame(
    sentinels=((6, "#FF0000"), (101, "#00FF00"), (193, "#0000FF")),
    non_black=15,
)
_FRAME_ONE = ExpectedFrame(
    sentinels=((6, "#00FFFF"), (101, "#FF00FF"), (193, "#FFFF00")),
    non_black=15,
)


def _fixture_frame(colors: tuple[tuple[int, int, int], ...]):
    from PIL import Image

    image = Image.new("RGB", (20, 5), (0, 0, 0))
    for point, color in zip(((5, 1), (10, 2), (14, 3)), colors, strict=True):
        image.putpixel(point, color)
    return image


def build_media_fixtures() -> tuple[MediaFixture, ...]:
    """Build pathless asymmetric fixtures with exact destination sentinels."""

    first = _fixture_frame(((255, 0, 0), (0, 255, 0), (0, 0, 255)))
    second = _fixture_frame(((0, 255, 255), (255, 0, 255), (255, 255, 0)))
    fixtures: list[MediaFixture] = []
    for format_name, mime_type in (
        ("GIF", "image/gif"),
        ("PNG", "image/png"),
        ("BMP", "image/bmp"),
    ):
        output = BytesIO()
        if format_name == "GIF":
            first.save(
                output,
                format="GIF",
                save_all=True,
                append_images=[second],
                duration=[80, 120],
                loop=0,
                disposal=2,
                optimize=False,
            )
            source_frame_count = 2
            expected = (
                _FRAME_ZERO,
                _FRAME_ZERO,
                _FRAME_ZERO,
                _FRAME_ONE,
                _FRAME_ONE,
                _FRAME_ONE,
            )
        else:
            first.save(output, format=format_name)
            source_frame_count = 1
            expected = (_FRAME_ZERO,)
        extension = format_name.casefold()
        fixtures.append(
            MediaFixture(
                format=extension,
                name=f"audit.{extension}",
                mime_type=mime_type,
                payload=output.getvalue(),
                source_frame_count=source_frame_count,
                expected_frames=expected,
            )
        )
    return tuple(fixtures)


def _synthetic_neon_key_layout() -> list[dict[str, int | float]]:
    from .device_mapping import device_descriptor, target_capabilities

    axial = next(
        target
        for target in target_capabilities()["NEON"]["targets"]
        if target["name"] == "axial"
    )
    width = axial["width"]
    height = axial["height"]
    pixel_map = axial["map"]
    matrix_columns = device_descriptor("NEON80")["keymap"]["matrix_columns"]
    layout: list[dict[str, int | float]] = []
    key_width = 96.0 / width
    for row in range(height):
        for column in range(width):
            if pixel_map[row * width + column] < 0:
                continue
            matrix_index = len(layout)
            layout.append(
                {
                    "index": matrix_index,
                    "matrix_row": matrix_index // matrix_columns,
                    "matrix_col": matrix_index % matrix_columns,
                    "x": column * key_width,
                    "y": row * (88.0 / height),
                    "width": key_width,
                    "height": 12.0,
                    "rotation": 0.0,
                }
            )
    if len(layout) != 89:
        raise RuntimeError("The synthetic Neon layout is incomplete.")
    return layout


def build_json_fixtures() -> tuple[JsonFixture, ...]:
    """Build pathless app-native and recognized AM Master JSON fixtures."""

    from . import profile_metadata
    from .server import blank_config

    cyberboard = build_audit_document()
    neon = blank_config(
        "NEON80",
        [["#00000000"] * 90 for _ in range(4)],
        [],
    )
    neon_evidence = profile_metadata.build_dynamic_layout(
        "NEON80",
        _synthetic_neon_key_layout(),
    )
    portable_neon = profile_metadata.attach_dynamic_layout(neon, neon_evidence)

    am_master_profile = blank_config(
        "ALICE",
        [["#00000000"] * 200 for _ in range(7)],
        [],
    )
    am_master_profile["page_data"][0]["//"] = "synthetic vendor page"
    am_master_profile["page_data"][0]["frames"] = {
        "valid": False,
        "frame_num": 0,
        "frame_data": [{"frame_index": "0", "frame_RGB": ["not-a-color"]}],
    }

    def color(frame: int, pixel: int, salt: int) -> str:
        return f"{(frame * 4099 + pixel * 17 + salt) & 0xFFFFFF:06x}"

    am_master_lighting = {
        "speed": 90,
        "brightness": 255,
        "description": "Synthetic offline lighting",
        "frames": [
            [color(frame, pixel, 0x123456) for pixel in range(230)]
            for frame in range(2)
        ],
        "frames_axial": [
            [color(frame, pixel, 0x654321) for pixel in range(89)]
            for frame in range(2)
        ],
    }

    def fixture(kind: str, name: str, value: object) -> JsonFixture:
        return JsonFixture(
            kind=kind,
            name=name,
            payload=json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

    return (
        fixture("app_native_cyberboard", "audit-cyberboard.json", cyberboard),
        fixture("portable_neon", "audit-portable-neon.json", portable_neon),
        fixture("am_master_profile", "audit-am-master-profile.json", am_master_profile),
        fixture("am_master_lighting", "audit-am-master-lighting.json", am_master_lighting),
    )


def build_audit_document() -> dict[str, Any]:
    """Build a hardware-free CyberBoard document with distinguishable tracks."""

    from .server import blank_config

    document = blank_config("CB04", [["#00000000"] * 200 for _ in range(7)], [])
    keyframes = (
        [f"#{0x910000 + index:06X}" for index in range(90)],
        [f"#{0x920000 + index:06X}" for index in range(90)],
    )
    display_frames = (
        [f"#{0x210000 + index:06X}" for index in range(200)],
        [f"#{0x220000 + index:06X}" for index in range(200)],
    )
    for page in document["page_data"][5:8]:
        page["valid"] = 1
        page["speed_ms"] = 48
        page["keyframes"] = {
            "valid": 1,
            "frame_num": 2,
            "frame_data": [
                {"frame_index": index, "frame_RGB": list(colors)}
                for index, colors in enumerate(keyframes)
            ],
        }
        page["frames"] = {
            "valid": 1,
            "frame_num": 2,
            "frame_data": [
                {"frame_index": index, "frame_RGB": list(colors)}
                for index, colors in enumerate(display_frames)
            ],
        }
    return document


def _is_linklike(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(junction and junction())


def cleanup_audit_root(
    root: Path,
    *,
    expected_root: Path,
    expected_parent: Path,
    expected_children: tuple[Path, Path],
) -> None:
    """Remove only the exact private root and its two verified data roots."""

    try:
        candidate = Path(root)
        canonical_parent = candidate.parent.resolve(strict=True)
        canonical_root = candidate.resolve(strict=True)
        if (
            not candidate.is_absolute()
            or candidate.name.startswith(_AUDIT_ROOT_PREFIX) is False
            or canonical_parent != Path(expected_parent)
            or canonical_root != Path(expected_root)
            or _is_linklike(candidate)
        ):
            raise MediaFramingAuditError("audit_cleanup_root_mismatch")
        expected_names = ("data", "library")
        if len(expected_children) != len(expected_names):
            raise MediaFramingAuditError("audit_cleanup_children_mismatch")
        for name, expected in zip(expected_names, expected_children, strict=True):
            child = candidate / name
            canonical_child = child.resolve(strict=True)
            if (
                canonical_child != Path(expected)
                or canonical_child.parent != canonical_root
                or not child.is_dir()
                or _is_linklike(child)
            ):
                raise MediaFramingAuditError("audit_cleanup_child_mismatch")
    except MediaFramingAuditError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise MediaFramingAuditError("audit_cleanup_verification_failed") from None
    shutil.rmtree(canonical_root)
    if candidate.exists() or candidate.is_symlink():
        raise MediaFramingAuditError("audit_cleanup_incomplete")


def _bounded_text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        raise MediaFramingAuditError(f"invalid_{label}")
    for item in value:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > _MAX_REPORT_TEXT
            or re.fullmatch(r"[a-z0-9_:-]+", item) is None
        ):
            raise MediaFramingAuditError(f"invalid_{label}")
    return value


def validate_audit_report(report: object) -> dict:
    """Accept only the bounded pathless result schema written by this audit."""

    if not isinstance(report, dict) or set(report) != {
        "schema_version",
        "status",
        "failure",
        "viewports",
    }:
        raise MediaFramingAuditError("invalid_report")
    if report["schema_version"] != 2 or report["status"] not in {"passed", "failed"}:
        raise MediaFramingAuditError("invalid_report")
    failure = report["failure"]
    if report["status"] == "passed":
        if failure is not None:
            raise MediaFramingAuditError("invalid_failure")
    elif (
        not isinstance(failure, str)
        or re.fullmatch(r"[a-z0-9_:-]{1,200}", failure) is None
    ):
        raise MediaFramingAuditError("invalid_failure")
    viewports = report["viewports"]
    if not isinstance(viewports, list) or len(viewports) > len(AUDIT_VIEWPORTS):
        raise MediaFramingAuditError("invalid_viewports")
    if report["status"] == "passed" and len(viewports) != len(AUDIT_VIEWPORTS):
        raise MediaFramingAuditError("incomplete_viewports")
    for index, viewport in enumerate(viewports):
        if not isinstance(viewport, dict) or set(viewport) != {
            "width",
            "height",
            "cases",
            "layout_findings",
            "console_errors",
            "profile_checks",
        }:
            raise MediaFramingAuditError("invalid_viewport")
        if (viewport["width"], viewport["height"]) != AUDIT_VIEWPORTS[index]:
            raise MediaFramingAuditError("invalid_viewport_size")
        cases = viewport["cases"]
        if not isinstance(cases, list) or len(cases) > 3:
            raise MediaFramingAuditError("invalid_cases")
        if report["status"] == "passed" and len(cases) != 3:
            raise MediaFramingAuditError("incomplete_cases")
        for case_index, case in enumerate(cases):
            if not isinstance(case, dict) or set(case) != {"format", "checks"}:
                raise MediaFramingAuditError("invalid_case")
            if case["format"] != ("gif", "png", "bmp")[case_index]:
                raise MediaFramingAuditError("invalid_case_format")
            if case["checks"] != REQUIRED_CASE_CHECKS:
                raise MediaFramingAuditError("invalid_case_checks")
        findings = _bounded_text_list(viewport["layout_findings"], "layout_findings")
        console_errors = _bounded_text_list(viewport["console_errors"], "console_errors")
        profile_checks = _bounded_text_list(viewport["profile_checks"], "profile_checks")
        expected_profile_checks = (
            REQUIRED_PROFILE_CHECKS if index == len(AUDIT_VIEWPORTS) - 1 else []
        )
        if profile_checks != expected_profile_checks:
            raise MediaFramingAuditError("invalid_profile_checks")
        if report["status"] == "passed" and (findings or console_errors):
            raise MediaFramingAuditError("failed_checks_in_passed_report")
    encoded = json.dumps(
        report,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(encoded) > MAX_REPORT_BYTES:
        raise MediaFramingAuditError("report_too_large")
    return report


def write_audit_report(output: Path, report: object) -> None:
    """Atomically write one validated JSON result outside the audit root."""

    checked = validate_audit_report(report)
    destination = Path(output).expanduser()
    if destination.suffix.casefold() != ".json":
        raise MediaFramingAuditError("audit_output_must_be_json")
    try:
        parent = destination.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise MediaFramingAuditError("audit_output_parent_unavailable") from None
    destination = parent / destination.name
    payload = (
        json.dumps(checked, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise MediaFramingAuditError("report_too_large")
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    except OSError:
        raise MediaFramingAuditError("audit_output_write_failed") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _fixture_payload(fixtures: tuple[MediaFixture, ...]) -> list[dict[str, object]]:
    return [
        {
            "format": case.format,
            "name": case.name,
            "mime_type": case.mime_type,
            "payload": base64.b64encode(case.payload).decode("ascii"),
            "source_frame_count": case.source_frame_count,
            "expected_frames": [
                {
                    "sentinels": [list(sentinel) for sentinel in frame.sentinels],
                    "non_black": frame.non_black,
                }
                for frame in case.expected_frames
            ],
        }
        for case in fixtures
    ]


def _json_fixture_payload(fixtures: tuple[JsonFixture, ...]) -> list[dict[str, str]]:
    return [
        {
            "kind": fixture.kind,
            "name": fixture.name,
            "payload": base64.b64encode(fixture.payload).decode("ascii"),
        }
        for fixture in fixtures
    ]


_AUDIT_SCRIPT = r"""
(() => {
  const resultSlot = "__RESULT_SLOT__";
  const requiredChecks = __REQUIRED_CHECKS__;
  const requiredProfileChecks = __REQUIRED_PROFILE_CHECKS__;
  const consoleErrors = [];
  const consoleErrorKind = value => {
    const raw = value?.name || value?.constructor?.name || typeof value;
    const token = String(raw || "unknown").toLowerCase().replace(/[^a-z0-9_]+/g, "_");
    return /^[a-z0-9_]{1,40}$/.test(token) ? token : "unknown";
  };
  const originalConsoleError = console.error.bind(console);
  console.error = (...args) => {
    if (consoleErrors.length < 20) {
      consoleErrors.push(`console_error:${consoleErrorKind(args[0])}`);
    }
    originalConsoleError(...args);
  };
  window.addEventListener("error", event => {
    if (consoleErrors.length < 20) {
      consoleErrors.push(`window_error:${consoleErrorKind(event.error)}`);
    }
  });
  window.addEventListener("unhandledrejection", event => {
    if (consoleErrors.length < 20) {
      consoleErrors.push(`unhandled_rejection:${consoleErrorKind(event.reason)}`);
    }
  });

  class AuditFailure extends Error {
    constructor(code) {
      super(code);
      this.auditCode = code;
    }
  }
  const requireAudit = (condition, code) => {
    if (!condition) throw new AuditFailure(code);
  };
  const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  async function waitFor(check, code, timeout = 20000) {
    const deadline = performance.now() + timeout;
    while (performance.now() < deadline) {
      try {
        const value = await check();
        if (value) return value;
      } catch (error) {
        if (error instanceof AuditFailure) throw error;
      }
      await delay(25);
    }
    throw new AuditFailure(code);
  }
  const sameJson = (left, right) => JSON.stringify(left) === JSON.stringify(right);
  const pageFingerprint = () => JSON.stringify(getPage(state.ledSlot));
  const canonicalLightingValue = value => {
    if (typeof value === "string" && /^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(value)) {
      return value.toUpperCase();
    }
    if (Array.isArray(value)) return value.map(canonicalLightingValue);
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.keys(value).sort().map(key => [key, canonicalLightingValue(value[key])]),
      );
    }
    return value;
  };
  const lightingFingerprint = page => JSON.stringify(canonicalLightingValue(page));
  const overlayStyle = overlay => [
    overlay.style.getPropertyValue("--source-left"),
    overlay.style.getPropertyValue("--source-top"),
    overlay.style.getPropertyValue("--source-width"),
    overlay.style.getPropertyValue("--source-height"),
  ].join("|");
  const bytesEqual = (left, right) => {
    if (left.length !== right.length) return false;
    for (let index = 0; index < left.length; index += 1) {
      if (left[index] !== right[index]) return false;
    }
    return true;
  };
  const boardPixelColors = () => [...document.querySelectorAll(
    "#lighting-board-pane #led-canvas .pixel",
  )].map(pixel => pixel.style.getPropertyValue("--pixel-color").trim().toUpperCase());
  const auditJsonBlob = fixture => {
    const bytes = Uint8Array.from(
      atob(fixture.payload),
      character => character.charCodeAt(0),
    );
    return new Blob([bytes], {type: "application/json"});
  };
  const auditJsonInput = (name, payload) => {
    const file = payload instanceof Blob
      ? payload
      : new Blob([payload], {type: "application/json"});
    Object.defineProperty(file, "name", {value: name, configurable: true});
    return {files: [file], value: ""};
  };
  const auditJsonFixture = (fixtures, kind) => {
    const fixture = fixtures.find(candidate => candidate.kind === kind);
    requireAudit(fixture, `json_fixture_${kind}_missing`);
    return fixture;
  };
  async function openAuditJson(fixtures, kind) {
    const fixture = auditJsonFixture(fixtures, kind);
    await readFiles(auditJsonInput(fixture.name, auditJsonBlob(fixture)), false);
    return fixture;
  }
  const mediaImportFailureCode = prefix => {
    const message = String(state.mediaImportStatus || "").toLowerCase();
    const category = message.includes("pillow")
      ? "pillow"
      : message.includes("library")
        ? "library"
        : message.includes("decode") || message.includes("image")
          ? "decode"
          : message.includes("request failed")
            ? "api"
            : "unknown";
    return `${prefix}_rejected:${category}`;
  };

  async function catalogItems(filter) {
    const query = libraryCatalogQuery({filter, page: 1, limit: 100});
    const result = await api(`/api/library/items?${query}`);
    return result.items || [];
  }

  async function selectLibraryFilter(filter) {
    const button = [...document.querySelectorAll("[data-library-filter]")]
      .find(candidate => candidate.dataset.libraryFilter === filter);
    requireAudit(button, "library_filter_missing");
    button.click();
    await waitFor(
      () => state.library.filter === filter && state.library.loaded && !state.library.loading,
      "library_filter_timeout",
    );
  }

  async function openLibraryItemById(catalogId) {
    await waitFor(() => {
      if (
        state.library.selectedCatalogId === catalogId
        && state.library.details.has(catalogId)
        && document.querySelector("#library-detail-title")
      ) return true;
      const card = [...document.querySelectorAll("[data-library-item]")]
        .find(candidate => candidate.dataset.libraryItem === catalogId);
      if (!card) return false;
      card.click();
      return true;
    }, "library_item_missing");
    await waitFor(
      () => state.library.selectedCatalogId === catalogId
        && state.library.details.has(catalogId)
        && document.querySelector("#library-detail-title"),
      "library_detail_timeout",
    );
  }

  function overlayGeometryFinding() {
    const stage = document.querySelector("#media-compositor-stage");
    const viewport = stage?.querySelector(".media-source-viewport");
    const overlay = stage?.querySelector(".source-frame-image");
    const plane = stage?.querySelector(".media-compositor-plane");
    const context = mediaGeometryContext();
    if (!stage || !viewport || !overlay || !plane || !context) return "overlay_geometry_missing";
    const primary = context.destinationSizes[context.primaryIndex];
    const box = resolveSourceGeometry(
      context.sourceSize,
      context.destinationSizes,
      state.sourceTransform,
    ).boxes[context.primaryIndex];
    const viewportRect = viewport.getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();
    const planeRect = plane.getBoundingClientRect();
    const close = (left, right) => Math.abs(left - right) <= 1.25;
    const expectedLeft = viewportRect.left + box.left / primary.width * viewportRect.width;
    const expectedTop = viewportRect.top + box.top / primary.height * viewportRect.height;
    const expectedWidth = box.rendered_width / primary.width * viewportRect.width;
    const expectedHeight = box.rendered_height / primary.height * viewportRect.height;
    if (getComputedStyle(viewport).overflow !== "hidden") return "overlay_viewport_not_clipped";
    if (!close(viewportRect.left, planeRect.left) || !close(viewportRect.top, planeRect.top)) {
      return "overlay_viewport_origin_mismatch";
    }
    if (!close(viewportRect.width, planeRect.width) || !close(viewportRect.height, planeRect.height)) {
      return "overlay_viewport_size_mismatch";
    }
    if (!close(overlayRect.left, expectedLeft)) return "overlay_left_mismatch";
    if (!close(overlayRect.top, expectedTop)) return "overlay_top_mismatch";
    if (!close(overlayRect.width, expectedWidth) || !close(overlayRect.height, expectedHeight)) {
      return "overlay_size_mismatch";
    }
    return null;
  }

  function layoutFindings() {
    const findings = [];
    const seen = new Set();
    const viewportWidth = document.documentElement.clientWidth;
    for (const element of document.querySelectorAll("body *")) {
      if (!(element instanceof HTMLElement)) continue;
      if (element.closest("[hidden]")) continue;
      if (element.closest("dialog") && !element.closest("dialog").open) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      const style = getComputedStyle(element);
      if (style.position === "fixed") continue;
      let ancestor = element.parentElement;
      let scrollable = false;
      while (ancestor) {
        const ancestorStyle = getComputedStyle(ancestor);
        if (["auto", "scroll"].includes(ancestorStyle.overflowX)) {
          scrollable = true;
          break;
        }
        ancestor = ancestor.parentElement;
      }
      if (!scrollable && rect.right > viewportWidth + 2) {
        if (!seen.has("viewport_escape")) findings.push("viewport_escape");
        seen.add("viewport_escape");
      }
    }
    const boxes = document.querySelectorAll(
      ".card,.lighting-context,.studio-tool-panel,.led-controls,.lighting-pane,.lighting-timeline,.studio-inspector,.library-toolbar",
    );
    for (const box of boxes) {
      if (box.closest("[hidden]")) continue;
      const boxRect = box.getBoundingClientRect();
      if (boxRect.width <= 0 || boxRect.height <= 0) continue;
      if (["auto", "scroll", "hidden", "clip"].includes(getComputedStyle(box).overflowX)) continue;
      for (const descendant of box.querySelectorAll("*")) {
        if (!(descendant instanceof HTMLElement) || descendant.closest("[hidden]")) continue;
        let ancestor = descendant.parentElement;
        let contained = false;
        while (ancestor && ancestor !== box) {
          if (["auto", "scroll", "hidden", "clip"].includes(getComputedStyle(ancestor).overflowX)) {
            contained = true;
            break;
          }
          ancestor = ancestor.parentElement;
        }
        const rect = descendant.getBoundingClientRect();
        if (!contained && rect.width > 0 && rect.height > 0 && rect.right > boxRect.right + 2) {
          if (!seen.has("container_escape")) findings.push("container_escape");
          seen.add("container_escape");
        }
      }
    }
    return findings.slice(0, 20);
  }

  function synchronizedWorkspaceFinding() {
    const panes = document.querySelector("#lighting-preview-panes");
    const source = document.querySelector("#lighting-source-pane");
    const board = document.querySelector("#lighting-board-pane");
    const timeline = document.querySelector("#lighting-timeline");
    const apply = document.querySelector("#media-compose-apply");
    const cancel = document.querySelector("#media-compose-cancel");
    if (!panes || !source || !board || !timeline || !apply || !cancel) {
      return "synchronized_workspace_missing";
    }
    if (source.parentElement !== panes || board.parentElement !== panes) {
      return "synchronized_workspace_not_siblings";
    }
    if (!source.querySelector(".source-frame-image")) return "source_projection_missing";
    if (board.querySelector("img,picture,video,canvas,svg,image")) {
      return "board_contains_image";
    }
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    for (const [name, element] of [
      ["source", source],
      ["board", board],
      ["timeline", timeline],
      ["apply", apply],
      ["cancel", cancel],
    ]) {
      const rect = element.getBoundingClientRect();
      if (
        rect.width <= 0
        || rect.height <= 0
        || rect.left < -2
        || rect.right > viewportWidth + 2
        || rect.top < -2
        || rect.bottom > viewportHeight + 2
      ) {
        const timelineDetail = name === "timeline"
          ? `:th${Math.round(timeline.querySelector(".lighting-timeline-toolbar")?.getBoundingClientRect().height || 0)}:fh${Math.round(timeline.querySelector(".lighting-timeline-frames")?.getBoundingClientRect().height || 0)}:ah${Math.round(timeline.querySelector(".lighting-timeline-actions")?.getBoundingClientRect().height || 0)}`
          : "";
        return `${name}_outside_first_viewport:t${Math.round(rect.top)}:b${Math.round(rect.bottom)}:vh${Math.round(viewportHeight)}${timelineDetail}`;
      }
    }
    return null;
  }

  async function prepareStudio() {
    document.querySelector('[data-route="lighting/edit"]')?.click();
    await waitFor(
      () => state.config && state.lighting.route === ROUTES.EDIT
        && document.querySelector('[data-lighting-target="frames"]'),
      "lighting_route_timeout",
    );
    if (state.ledTarget !== "frames") {
      document.querySelector('[data-lighting-target="frames"]')?.click();
    }
    await waitFor(
      () => state.ledTarget === "frames" && document.querySelector("#studio-source-tab"),
      "display_target_timeout",
    );
    document.querySelector("#studio-source-tab").click();
    await waitFor(
      () => state.studioTool === "source" && document.querySelector("#media-input"),
      "source_tool_timeout",
    );
  }

  async function verifyDestinationPlaybackIsolation() {
    const baseline = pageFingerprint();
    window.__mediaFramingAuditStep = "destination_playback_select_source";
    document.querySelector('[data-lighting-target="keyframes"]')?.click();
    await waitFor(
      () => state.ledTarget === "keyframes"
        && document.querySelectorAll("#led-canvas .pixel").length >= 80,
      "playback_source_target_timeout",
    );
    const page = getPage(state.ledSlot);
    requireAudit(page?.keyframes?.frame_data?.length === 2, "playback_source_track_missing");
    requireAudit(page?.frames?.frame_data?.length === 2, "playback_destination_track_missing");
    window.__mediaFramingAuditStep = "destination_playback_start";
    document.querySelector("#play-led")?.click();
    await waitFor(() => state.playing, "playback_start_timeout");
    window.__mediaFramingAuditStep = "destination_playback_select_destination";
    document.querySelector('[data-lighting-target="frames"]')?.click();
    await waitFor(
      () => state.ledTarget === "frames"
        && !state.playing
        && document.querySelectorAll("#led-canvas .pixel").length === 200,
      "playback_destination_timeout",
    );
    window.__mediaFramingAuditStep = "destination_playback_verify";
    await delay(Math.max(150, Number(page.speed_ms || 48) * 3));
    requireAudit(state.ledTarget === "frames", "playback_target_leaked");
    requireAudit(!state.playing, "playback_timer_leaked");
    window.__mediaFramingAuditStep = "destination_playback_expected";
    const expected = page.frames.frame_data[0].frame_RGB.map(color => color.toUpperCase());
    window.__mediaFramingAuditStep = "destination_playback_actual";
    const actual = [...document.querySelectorAll("#led-canvas .pixel")].map(
      pixel => pixel.style.getPropertyValue("--pixel-color").trim().toUpperCase(),
    );
    window.__mediaFramingAuditStep = "destination_playback_compare";
    requireAudit(sameJson(actual, expected), "playback_destination_colors_mismatch");
    requireAudit(pageFingerprint() === baseline, "playback_changed_document");
  }

  async function runProfileChecks(jsonFixtures) {
    const originalMotionPreference = prefersReducedLightingMotion;
    const originalCyberboardConfig = lightingFingerprint(state.config);
    window.__mediaFramingAuditStep = "effects_live";
    document.querySelector('[data-route="lighting/edit"]')?.click();
    await waitFor(
      () => state.lighting.route === ROUTES.EDIT
        && document.querySelector('[data-lighting-target="frames"]'),
      "effects_route_timeout",
    );
    if (state.ledTarget !== "frames") {
      document.querySelector('[data-lighting-target="frames"]')?.click();
    }
    await waitFor(
      () => state.ledTarget === "frames"
        && document.querySelector('[data-studio-tool="animate"]'),
      "effects_display_timeout",
    );
    document.querySelector('[data-studio-tool="animate"]').click();
    await waitFor(
      () => state.studioTool === "animate"
        && document.querySelector('[data-effect-preset="pulse"]'),
      "effects_tool_timeout",
    );

    prefersReducedLightingMotion = () => false;
    const effectBaselinePage = pageFingerprint();
    const effectBaselineUndo = state.undo.length;
    document.querySelector('[data-effect-preset="pulse"]').click();
    await waitFor(
      () => currentLocalAnimationDraft()?.specification?.type === "pulse",
      "effects_pulse_timeout",
    );
    const liveDraft = currentLocalAnimationDraft();
    const liveFrames = liveDraft.board_frame_set.frames_by_target.frames;
    const liveSource = canonicalLightingValue(localAnimationSourceFrame().frame.frame_RGB);
    requireAudit(
      liveFrames.length >= 2
        && liveDraft.demonstrative_frame !== null
        && liveFrames.some(frame => !sameJson(canonicalLightingValue(frame), liveSource)),
      "effects_live_output_missing",
    );
    await waitFor(
      () => {
        const projection = selectBoardProjection(lightingWorkspace);
        return projection
          && sameJson(boardPixelColors(), canonicalLightingValue(projection.colors))
          && !document.querySelector("#lighting-board-pane img,#lighting-board-pane video,#lighting-board-pane canvas");
      },
      "effects_live_board_mismatch",
    );
    await waitFor(() => lightingWorkspace.playhead.playing, "effects_autoplay_timeout");
    const liveIndex = lightingWorkspace.playhead.index;
    await waitFor(
      () => lightingWorkspace.playhead.index !== liveIndex,
      "effects_frame_advance_timeout",
    );
    const initialPulseFrames = lightingFingerprint(liveFrames);
    const minimum = document.querySelector("#animate-minimum");
    requireAudit(minimum, "effects_parameter_missing");
    minimum.value = "65";
    minimum.dispatchEvent(new Event("input", {bubbles: true}));
    await waitFor(
      () => currentLocalAnimationDraft()?.specification?.parameters?.minimum_brightness === 0.65
        && lightingFingerprint(
          currentLocalAnimationDraft().board_frame_set.frames_by_target.frames,
        ) !== initialPulseFrames,
      "effects_parameter_timeout",
    );
    const effectFrameSet = currentLocalAnimationDraft().board_frame_set;
    await waitFor(
      () => {
        const projection = selectBoardProjection(lightingWorkspace);
        return projection
          && sameJson(boardPixelColors(), canonicalLightingValue(projection.colors));
      },
      "effects_parameter_board_mismatch",
    );

    window.__mediaFramingAuditStep = "effects_apply_undo";
    const originalEffectApply = applyBoardFrameSetToPage;
    let effectApplyCalls = 0;
    applyBoardFrameSetToPage = (...args) => {
      effectApplyCalls += 1;
      return originalEffectApply(...args);
    };
    document.querySelector("#animate-accept").click();
    await waitFor(
      () => !currentLocalAnimationDraft()
        && state.undo.length === effectBaselineUndo + 1,
      "effects_apply_timeout",
    );
    requireAudit(effectApplyCalls === 1, "effects_apply_count_mismatch");
    requireAudit(
      sameJson(
        canonicalLightingValue(
          getPage(state.ledSlot).frames.frame_data.map(frame => frame.frame_RGB),
        ),
        canonicalLightingValue(effectFrameSet.frames_by_target.frames),
      ),
      "effects_apply_frames_mismatch",
    );
    applyBoardFrameSetToPage = originalEffectApply;
    document.querySelector("#undo-button").click();
    await waitFor(
      () => pageFingerprint() === effectBaselinePage
        && state.undo.length === effectBaselineUndo,
      "effects_undo_timeout",
    );
    requireAudit(consoleErrors.length === 0, "effects_console_errors");

    window.__mediaFramingAuditStep = "reduced_motion";
    prefersReducedLightingMotion = () => true;
    document.querySelector('[data-effect-preset="pulse"]').click();
    await waitFor(
      () => currentLocalAnimationDraft()?.specification?.type === "pulse",
      "reduced_motion_draft_timeout",
    );
    const reducedDraft = currentLocalAnimationDraft();
    const reducedIndex = reducedDraft.demonstrative_frame;
    await delay(Math.max(250, reducedDraft.board_frame_set.duration_ms * 3));
    const reducedProjection = selectBoardProjection(lightingWorkspace);
    requireAudit(
      reducedIndex !== null
        && !lightingWorkspace.playhead.playing
        && lightingWorkspace.playhead.index === reducedIndex
        && reducedProjection?.index === reducedIndex
        && sameJson(boardPixelColors(), canonicalLightingValue(reducedProjection.colors))
        && document.querySelector("#animate-draft-status")?.textContent.includes(
          "representative frame",
        ),
      "reduced_motion_autoplay_or_frame_mismatch",
    );
    document.querySelector("#animate-cancel").click();
    await waitFor(() => !currentLocalAnimationDraft(), "reduced_motion_cancel_timeout");
    requireAudit(pageFingerprint() === effectBaselinePage, "reduced_motion_changed_document");
    prefersReducedLightingMotion = originalMotionPreference;
    requireAudit(consoleErrors.length === 0, "reduced_motion_console_errors");

    window.__mediaFramingAuditStep = "app_native_round_trip";
    let savedBlob = null;
    let savedName = "";
    const originalCreateObjectURL = URL.createObjectURL;
    const originalAnchorClick = HTMLAnchorElement.prototype.click;
    URL.createObjectURL = blob => {
      savedBlob = blob;
      return originalCreateObjectURL.call(URL, blob);
    };
    HTMLAnchorElement.prototype.click = function auditCaptureSave() {
      savedName = this.download;
    };
    await saveConfig();
    URL.createObjectURL = originalCreateObjectURL;
    HTMLAnchorElement.prototype.click = originalAnchorClick;
    requireAudit(
      savedBlob instanceof Blob
        && savedName.endsWith(".json")
        && !savedName.includes("/")
        && !savedName.includes("\\"),
      "app_native_save_capture_missing",
    );
    const savedConfig = JSON.parse(await savedBlob.text());
    const savedFingerprint = lightingFingerprint(savedConfig);
    const currentPage = getPage(state.ledSlot);
    const currentLightness = Number(currentPage.lightness ?? 0);
    mutate(() => {
      getPage(state.ledSlot).lightness = currentLightness === 99 ? 98 : 99;
    });
    requireAudit(
      lightingFingerprint(state.config) !== savedFingerprint
        && state.undo.length > 0
        && state.fileName !== "audit-round-trip.json",
      "app_native_pre_reopen_not_distinct",
    );
    await readFiles(auditJsonInput("audit-round-trip.json", savedBlob), false);
    await waitFor(
      () => productId() === "CB04"
        && state.fileName === "audit-round-trip.json"
        && documentSynchronized(),
      "app_native_reopen_timeout",
      30000,
    );
    requireAudit(
      lightingFingerprint(state.config) === savedFingerprint
        && state.undo.length === 0,
      "app_native_round_trip_mismatch",
    );
    requireAudit(consoleErrors.length === 0, "app_native_round_trip_console_errors");

    window.__mediaFramingAuditStep = "am_master_lighting_missing_layout";
    const cyberboardPage = pageFingerprint();
    const cyberboardUndo = state.undo.length;
    const lightingBeforeMissing = (await catalogItems("lighting"))
      .map(item => item.catalog_id)
      .sort();
    await openAuditJson(jsonFixtures, "am_master_lighting");
    await waitFor(
      () => importedLightingReport()?.source_format === "am_master_am80_lighting"
        && state.ledTarget === "head"
        && boardPixelColors().length === 230,
      "am_master_lighting_head_timeout",
      30000,
    );
    const missingLayoutReport = importedLightingReport();
    const missingHead = canonicalLightingValue(
      missingLayoutReport.lighting.mapped_result.tracks.head.frames[
        lightingWorkspace.playhead.index
      ],
    );
    requireAudit(
      sameJson(boardPixelColors(), missingHead)
        && !document.querySelector("#lighting-board-pane img,#lighting-board-pane video,#lighting-board-pane canvas"),
      "am_master_lighting_head_mismatch",
    );
    requireAudit(
      consoleErrors.length === 0,
      `missing_layout_open_console_errors:${consoleErrors[0] || "unknown"}`,
    );
    document.querySelector('[data-lighting-target="axial"]').click();
    await waitFor(
      () => state.ledTarget === "axial"
        && document.querySelector("#led-canvas .route-requirement"),
      "am_master_lighting_missing_layout_timeout",
    );
    requireAudit(
      boardPixelColors().length === 0
        && document.querySelector("#led-canvas").textContent.includes(
          "Per-key layout unavailable",
        )
        && document.querySelector("#imported-lighting-apply").disabled,
      "am_master_lighting_missing_layout",
    );
    requireAudit(
      consoleErrors.length === 0,
      `missing_layout_target_console_errors:${consoleErrors[0] || "unknown"}`,
    );
    const lightingAfterMissing = (await catalogItems("lighting"))
      .map(item => item.catalog_id)
      .sort();
    requireAudit(
      sameJson(lightingAfterMissing, lightingBeforeMissing)
        && pageFingerprint() === cyberboardPage
        && state.undo.length === cyberboardUndo,
      "am_master_lighting_missing_layout_mutated_state",
    );
    requireAudit(
      consoleErrors.length === 0,
      `missing_layout_catalog_console_errors:${consoleErrors[0] || "unknown"}`,
    );
    document.querySelector("#imported-lighting-close").click();
    await waitFor(() => !importedLightingReport(), "am_master_lighting_close_timeout");
    requireAudit(
      consoleErrors.length === 0,
      `missing_layout_console_errors:${consoleErrors[0] || "unknown"}`,
    );

    window.__mediaFramingAuditStep = "portable_neon_layout";
    await openAuditJson(jsonFixtures, "portable_neon");
    await waitFor(
      () => productId() === "NEON80"
        && documentSynchronized()
        && state.layoutEvidence?.key_layout?.length === 89,
      "portable_neon_open_timeout",
      30000,
    );
    document.querySelector('[data-route="lighting/edit"]')?.click();
    await waitFor(
      () => state.lighting.route === ROUTES.EDIT
        && document.querySelector('[data-lighting-target="axial"]'),
      "portable_neon_route_timeout",
    );
    document.querySelector('[data-lighting-target="axial"]').click();
    await waitFor(
      () => state.ledTarget === "axial"
        && document.querySelectorAll("#lighting-board-pane .physical-pixel").length === 89,
      "portable_neon_layout_timeout",
    );
    requireAudit(
      state.layoutEvidence.source === "embedded"
        && state.layoutEvidence.keymap_signature
          === state.config._am_configurator.dynamic_layout.keymap_signature,
      "portable_neon_layout",
    );
    requireAudit(consoleErrors.length === 0, "portable_neon_console_errors");
    const neonBaselinePage = pageFingerprint();
    const neonBaselineUndo = state.undo.length;

    window.__mediaFramingAuditStep = "am_master_lighting_offline_layout";
    await openAuditJson(jsonFixtures, "am_master_lighting");
    await waitFor(
      () => importedLightingReport()?.source_format === "am_master_am80_lighting"
        && state.ledTarget === "head"
        && boardPixelColors().length === 230,
      "am_master_lighting_reimport_timeout",
      30000,
    );
    const offlineReport = importedLightingReport();
    const offlineHead = canonicalLightingValue(
      offlineReport.lighting.mapped_result.tracks.head.frames[
        lightingWorkspace.playhead.index
      ],
    );
    requireAudit(
      sameJson(boardPixelColors(), offlineHead),
      "am_master_lighting_offline_head_mismatch",
    );
    document.querySelector('[data-lighting-target="axial"]').click();
    await waitFor(
      () => state.ledTarget === "axial"
        && document.querySelectorAll("#lighting-board-pane .physical-pixel").length === 89,
      "am_master_lighting_offline_layout_timeout",
    );
    const offlineAxial = canonicalLightingValue(
      offlineReport.lighting.mapped_result.tracks.axial.frames[
        lightingWorkspace.playhead.index
      ],
    );
    requireAudit(
      sameJson(boardPixelColors(), offlineAxial)
        && !document.querySelector("#imported-lighting-apply").disabled,
      "am_master_lighting_offline_layout",
    );

    window.__mediaFramingAuditStep = "am_master_lighting_save_library";
    const lightingBeforeSave = (await catalogItems("lighting"))
      .map(item => item.catalog_id);
    document.querySelector("#imported-lighting-save").click();
    const importedCatalogId = await waitFor(
      () => state.importedLighting?.savedCatalogId,
      "am_master_lighting_save_timeout",
      30000,
    );
    const lightingAfterSave = (await catalogItems("lighting"))
      .map(item => item.catalog_id);
    requireAudit(
      !lightingBeforeSave.includes(importedCatalogId)
        && lightingAfterSave.includes(importedCatalogId),
      "am_master_lighting_save_library",
    );

    window.__mediaFramingAuditStep = "am_master_lighting_apply_undo";
    const expectedHeadFrames = canonicalLightingValue(
      offlineReport.lighting.mapped_result.tracks.head.frames,
    );
    const expectedAxialFrames = canonicalLightingValue(
      offlineReport.lighting.mapped_result.tracks.axial.frames,
    );
    const originalImportedApply = applyBoardFrameSetToPage;
    let importedApplyCalls = 0;
    applyBoardFrameSetToPage = (...args) => {
      importedApplyCalls += 1;
      return originalImportedApply(...args);
    };
    document.querySelector("#imported-lighting-apply").click();
    await waitFor(
      () => !importedLightingReport()
        && state.undo.length === neonBaselineUndo + 1,
      "am_master_lighting_apply_timeout",
      30000,
    );
    const appliedNeonPage = getPage(state.ledSlot);
    requireAudit(
      importedApplyCalls === 1
        && sameJson(
          canonicalLightingValue(
            appliedNeonPage.head.frame_data.map(frame => frame.frame_RGB),
          ),
          expectedHeadFrames,
        )
        && sameJson(
          canonicalLightingValue(
            appliedNeonPage.axial.frame_data.map(frame => frame.frame_RGB),
          ),
          expectedAxialFrames,
        ),
      "am_master_lighting_apply_undo",
    );
    applyBoardFrameSetToPage = originalImportedApply;
    document.querySelector("#undo-button").click();
    await waitFor(
      () => pageFingerprint() === neonBaselinePage
        && state.undo.length === neonBaselineUndo,
      "am_master_lighting_undo_timeout",
    );
    requireAudit(consoleErrors.length === 0, "am_master_lighting_console_errors");

    window.__mediaFramingAuditStep = "am_master_profile";
    await openAuditJson(jsonFixtures, "am_master_profile");
    await waitFor(
      () => productId() === "ALICE" && documentSynchronized(),
      "am_master_profile_open_timeout",
      30000,
    );
    const normalizedFrames = state.config.page_data[0].frames;
    requireAudit(
      normalizedFrames.valid === false
        && normalizedFrames.frame_num === 0
        && sameJson(normalizedFrames.frame_data, []),
      "am_master_profile",
    );

    window.__mediaFramingAuditStep = "restore_cyberboard_profile";
    await openAuditJson(jsonFixtures, "app_native_cyberboard");
    await waitFor(
      () => productId() === "CB04" && documentSynchronized(),
      "restore_cyberboard_timeout",
      30000,
    );
    requireAudit(
      lightingFingerprint(state.config) === originalCyberboardConfig,
      "restore_cyberboard_mismatch",
    );
    requireAudit(consoleErrors.length === 0, "am_master_profile_console_errors");
    return requiredProfileChecks;
  }

  async function runCase(fixture, width, height) {
    window.__mediaFramingAuditStep = "prepare_studio";
    await prepareStudio();
    window.__mediaFramingAuditStep = "destination_playback_isolation";
    await verifyDestinationPlaybackIsolation();
    const baselinePage = pageFingerprint();
    const baselineUndo = state.undo.length;
    const raw = Uint8Array.from(atob(fixture.payload), character => character.charCodeAt(0));
    const mediaBefore = (await catalogItems("sources")).map(item => item.catalog_id);
    const toastsBefore = new Set(document.querySelectorAll("#toast-region .toast"));
    window.__mediaFramingAuditStep = "unsupported_rejection";
    document.querySelector("#import-media").click();
    await waitFor(() => {
      const status = document.querySelector("#media-import-status");
      return status?.classList.contains("failed") && status.textContent.trim();
    }, "unsupported_rejection_timeout");
    const mediaAfterBad = (await catalogItems("sources")).map(item => item.catalog_id);
    requireAudit(sameJson(mediaAfterBad, mediaBefore), "unsupported_published_item");
    requireAudit(
      [...document.querySelectorAll("#toast-region .toast")].every(
        toast => toastsBefore.has(toast),
      ),
      "unsupported_created_toast",
    );
    window.__mediaFramingAuditStep = "raw_import";
    document.querySelector("#import-media").click();
    try {
      await waitFor(
        () => {
          if (state.mediaImportError) {
            throw new AuditFailure(mediaImportFailureCode("raw_import"));
          }
          return state.mediaComposition?.source?.mime_type === fixture.mime_type
            && state.mediaComposition.status === "ready";
        },
        "raw_import_timeout",
        30000,
      );
    } catch (error) {
      if (error?.auditCode !== "raw_import_timeout") throw error;
      const status = String(state.mediaComposition?.status || "none");
      const boundedStatus = /^[a-z0-9_]{1,40}$/.test(status) ? status : "unknown";
      throw new AuditFailure(`raw_import_timeout:${boundedStatus}`);
    }
    requireAudit(pageFingerprint() === baselinePage, "import_changed_document");
    const importedItems = (await catalogItems("sources")).map(item => item.catalog_id);
    requireAudit(
      importedItems.includes(state.mediaComposition.catalogId)
        && importedItems.length >= mediaBefore.length
        && importedItems.length <= mediaBefore.length + 1,
      "native_picker_import_missing",
    );

    const originalFetch = window.fetch;
    let countLiveRenders = false;
    let liveRenderCount = 0;
    let lateSourceArmed = false;
    let lateSourceBlocked = false;
    let lateSourceFrameIndex = null;
    let lateSourceRelease = null;
    let queuedRenderArmed = false;
    let queuedRenderBlocked = false;
    let queuedRenderSettled = false;
    let queuedRenderCalls = 0;
    let queuedRenderRelease = null;
    let selectedFrameArmed = false;
    let selectedFrameCalls = 0;
    let selectedFrameActive = 0;
    let selectedFrameMaxActive = 0;
    let selectedFrameBlocked = false;
    let selectedFrameSettled = 0;
    let selectedFrameRelease = null;
    let selectedFrameRequests = [];
    let selectedFrameResponses = [];
    let selectedFullArmed = false;
    let selectedFullBlocked = false;
    let selectedFullSettled = false;
    let selectedFullRelease = null;
    function releaseLateSource() {
      const release = lateSourceRelease;
      lateSourceRelease = null;
      if (release) release();
    }
    function releaseQueuedRender() {
      const release = queuedRenderRelease;
      queuedRenderRelease = null;
      if (release) release();
    }
    function releaseSelectedFrame() {
      const release = selectedFrameRelease;
      selectedFrameRelease = null;
      if (release) release();
    }
    function releaseSelectedFull() {
      const release = selectedFullRelease;
      selectedFullRelease = null;
      if (release) release();
    }
    window.fetch = (resource, options) => {
      const requestUrl = typeof resource === "string" ? resource : String(resource?.url || "");
      const parsed = new URL(requestUrl, location.href);
      const method = String(options?.method || resource?.method || "GET").toUpperCase();
      if (countLiveRenders && parsed.pathname.endsWith("/render") && method === "POST") {
        liveRenderCount += 1;
      }
      if (
        selectedFrameArmed
        && parsed.pathname.endsWith("/render-frame")
        && method === "POST"
      ) {
        selectedFrameCalls += 1;
        selectedFrameActive += 1;
        selectedFrameMaxActive = Math.max(selectedFrameMaxActive, selectedFrameActive);
        selectedFrameRequests.push(JSON.parse(String(options?.body || "{}")));
        let gate = Promise.resolve();
        if (selectedFrameCalls === 1) {
          selectedFrameBlocked = true;
          gate = new Promise(resolve => { selectedFrameRelease = resolve; });
        }
        return gate
          .then(() => originalFetch.call(window, resource, options))
          .then(async response => {
            if (response.ok) selectedFrameResponses.push(await response.clone().json());
            return response;
          })
          .finally(() => {
            selectedFrameActive -= 1;
            selectedFrameSettled += 1;
          });
      }
      if (selectedFullArmed && parsed.pathname.endsWith("/render") && method === "POST") {
        selectedFullBlocked = true;
        const gate = new Promise(resolve => { selectedFullRelease = resolve; });
        return gate
          .then(() => originalFetch.call(window, resource, options))
          .finally(() => { selectedFullSettled = true; });
      }
      if (queuedRenderArmed && parsed.pathname.endsWith("/render") && method === "POST") {
        queuedRenderCalls += 1;
        if (queuedRenderCalls === 1) {
          queuedRenderBlocked = true;
          const gate = new Promise(resolve => { queuedRenderRelease = resolve; });
          return gate
            .then(() => originalFetch.call(window, resource, options))
            .finally(() => { queuedRenderSettled = true; });
        }
      }
      if (
        lateSourceArmed
        && parsed.pathname.endsWith("/source-frame")
        && parsed.searchParams.get("source_frame_index") === String(lateSourceFrameIndex)
      ) {
        lateSourceArmed = false;
        lateSourceBlocked = true;
        const gate = new Promise(resolve => { lateSourceRelease = resolve; });
        return gate.then(() => originalFetch.call(window, resource, options));
      }
      return originalFetch.call(window, resource, options);
    };

    window.__mediaFramingAuditStep = "saved_source_retrieval";
    const sourceImage = await waitFor(() => {
      const image = document.querySelector(".source-frame-image");
      return image?.complete && image.naturalWidth === 20 && image.naturalHeight === 5
        ? image
        : false;
    }, "saved_source_image_timeout");
    requireAudit(sourceImage.src.startsWith("blob:"), "saved_source_blob_missing");
    window.__mediaFramingAuditStep = "shared_timeline";
    const timelineScrubber = document.querySelector("#lighting-timeline-scrubber");
    const initialSourceProjection = selectSourceProjection(lightingWorkspace);
    const acceptedBoard = selectBoardProjection(lightingWorkspace);
    requireAudit(timelineScrubber && initialSourceProjection && acceptedBoard, "shared_timeline_missing");
    const initialSourceUrl = sourceImage.src;
    const alternateTimelineIndex = acceptedBoard.frame_set.timeline.findIndex(
      entry => entry.source_frame_index !== initialSourceProjection.source_frame_index,
    );
    if (alternateTimelineIndex >= 0) {
      const expectedAlternate = state.mediaComposition.mappedResult.tracks.frames.frames[alternateTimelineIndex];
      timelineScrubber.value = String(alternateTimelineIndex);
      timelineScrubber.dispatchEvent(new Event("input", {bubbles: true}));
      await waitFor(() => {
        const projection = selectSourceProjection(lightingWorkspace);
        const image = document.querySelector(".source-frame-image");
        const actual = [...document.querySelectorAll("#led-canvas .pixel")].map(
          pixel => pixel.style.getPropertyValue("--pixel-color").trim().toUpperCase(),
        );
        return projection?.timeline_index === alternateTimelineIndex
          && projection.source_frame_index !== initialSourceProjection.source_frame_index
          && image?.src !== initialSourceUrl
          && sameJson(actual, expectedAlternate.map(color => color.toUpperCase()));
      }, "shared_timeline_advance_timeout");
      timelineScrubber.value = "0";
      timelineScrubber.dispatchEvent(new Event("input", {bubbles: true}));
      await waitFor(
        () => selectSourceProjection(lightingWorkspace)?.timeline_index === 0
          && document.querySelector(".source-frame-image")?.src === initialSourceUrl,
        "shared_timeline_return_timeout",
      );
    } else {
      requireAudit(
        timelineScrubber.disabled
          && acceptedBoard.frame_set.frame_count === 1
          && initialSourceProjection.timeline_index === 0,
        "single_frame_timeline_mismatch",
      );
    }
    window.__mediaFramingAuditStep = "late_source_hold";
    if (fixture.source_frame_count > 1) {
      const playbackBoard = selectBoardProjection(lightingWorkspace);
      const playbackSource = selectSourceProjection(lightingWorkspace);
      const lateTimelineIndex = playbackBoard.frame_set.timeline.findIndex(
        entry => entry.source_frame_index !== playbackSource.source_frame_index,
      );
      requireAudit(lateTimelineIndex > 0, "late_source_timeline_missing");
      lateSourceFrameIndex = playbackBoard.frame_set.timeline[lateTimelineIndex].source_frame_index;
      const lateProjection = {
        ...playbackSource,
        source_frame_index: lateSourceFrameIndex,
        timeline_index: lateTimelineIndex,
      };
      const lateCacheKey = sourceProjectionCacheKey(lateProjection);
      const cachedLateSource = sourceProjectionUrls.get(lateCacheKey);
      if (cachedLateSource) URL.revokeObjectURL(cachedLateSource);
      sourceProjectionUrls.delete(lateCacheKey);
      lateSourceArmed = true;
      document.querySelector("#play-led").click();
      await waitFor(() => state.playing, "late_source_playback_start_timeout");
      const heldIndex = lateTimelineIndex - 1;
      await waitFor(
        () => lateSourceBlocked && lightingWorkspace.playhead.index === heldIndex,
        "late_source_request_timeout",
      );
      const heldColors = [...document.querySelectorAll("#led-canvas .pixel")].map(
        pixel => pixel.style.getPropertyValue("--pixel-color").trim().toUpperCase(),
      );
      await delay(Math.max(160, playbackBoard.frame_set.duration_ms * 3));
      requireAudit(
        lightingWorkspace.playhead.index === heldIndex
          && sameJson(
            heldColors,
            [...document.querySelectorAll("#led-canvas .pixel")].map(
              pixel => pixel.style.getPropertyValue("--pixel-color").trim().toUpperCase(),
            ),
          ),
        "late_source_advanced_early",
      );
      releaseLateSource();
      await waitFor(() => {
        const projection = selectSourceProjection(lightingWorkspace);
        const image = document.querySelector(".source-frame-image");
        if (
          lightingWorkspace.playhead.index !== heldIndex
          && projection?.source_frame_index === lateSourceFrameIndex
          && image?.complete
          && !image.hidden
        ) {
          document.querySelector("#play-led").click();
          return true;
        }
        return false;
      }, "late_source_release_timeout");
      await waitFor(() => !state.playing, "late_source_pause_timeout");
    } else {
      requireAudit(
        selectBoardProjection(lightingWorkspace)?.frame_set.frame_count === 1
          && document.querySelector("#play-led")?.disabled,
        "late_source_single_frame_mismatch",
      );
    }
    const draftForSource = state.mediaComposition;
    const sourceResponse = await fetch(
      `/api/library/assets/${libraryCatalogPath(draftForSource.catalogId)}/${encodeURIComponent(draftForSource.source.asset_id)}`,
      {headers: {"X-AM-Token": token}},
    );
    requireAudit(sourceResponse.ok, "saved_source_fetch_failed");
    const retrieved = new Uint8Array(await sourceResponse.arrayBuffer());
    requireAudit(bytesEqual(raw, retrieved), "saved_source_bytes_mismatch");

    window.__mediaFramingAuditStep = "preview_session_recovery";
    const expiredPreviewSessionId = lightingWorkspace.media?.preview_session_id;
    const expiredSourceUrl = document.querySelector(".source-frame-image")?.src || "";
    requireAudit(expiredPreviewSessionId && expiredSourceUrl, "preview_session_recovery_missing");
    for (let eviction = 0; eviction < 2; eviction += 1) {
      await api(`/api/library/items/${libraryCatalogPath(draftForSource.catalogId)}/preview-session`, {
        method: "POST",
        body: "{}",
      });
    }
    const previewButton = document.querySelector("#media-compose-preview");
    requireAudit(previewButton && !previewButton.disabled, "preview_session_recovery_button_missing");
    previewButton.click();
    await waitFor(() => {
      const currentPreviewSessionId = lightingWorkspace.media?.preview_session_id;
      const projection = selectSourceProjection(lightingWorkspace);
      const image = document.querySelector(".source-frame-image");
      return state.mediaComposition?.status === "ready"
        && currentPreviewSessionId
        && currentPreviewSessionId !== expiredPreviewSessionId
        && projection?.preview_session_id === currentPreviewSessionId
        && image?.complete
        && image.src
        && image.src !== expiredSourceUrl;
    }, "preview_session_recovery_timeout", 30000);
    requireAudit(pageFingerprint() === baselinePage, "preview_session_recovery_changed_document");
    requireAudit(state.undo.length === baselineUndo, "preview_session_recovery_changed_undo");

    window.__mediaFramingAuditStep = "pointer_input";
    liveRenderCount = 0;
    countLiveRenders = true;
    const stage = document.querySelector("#media-compositor-stage");
    const plane = stage?.querySelector(".media-compositor-plane");
    const overlay = stage?.querySelector(".source-frame-image");
    requireAudit(stage && plane && overlay, "framing_stage_missing");
    const beforePointer = overlayStyle(overlay);
    const beforePointerTransform = JSON.stringify(state.sourceTransform);
    const hadOwnCapture = Object.prototype.hasOwnProperty.call(stage, "setPointerCapture");
    const nativeCapture = stage.setPointerCapture;
    requireAudit(typeof nativeCapture === "function", "pointer_capture_unavailable");
    let notFoundObserved = false;
    stage.setPointerCapture = function (pointerId) {
      try {
        return nativeCapture.call(this, pointerId);
      } catch (error) {
        if (error?.name === "NotFoundError") notFoundObserved = true;
        throw error;
      }
    };
    const bounds = plane.getBoundingClientRect();
    const pointerId = 9417;
    const startX = bounds.left + bounds.width / 2;
    const startY = bounds.top + bounds.height / 2;
    const deltaY = Math.max(8, Math.min(40, bounds.height * 0.4));
    stage.dispatchEvent(new PointerEvent("pointerdown", {
      bubbles: true,
      cancelable: true,
      pointerId,
      pointerType: "mouse",
      isPrimary: true,
      button: 0,
      buttons: 1,
      clientX: startX,
      clientY: startY,
    }));
    requireAudit(stage.classList.contains("dragging"), "drag_state_missing");
    requireAudit(document.activeElement === stage, "stage_focus_missing");
    stage.dispatchEvent(new PointerEvent("pointermove", {
      bubbles: true,
      cancelable: true,
      pointerId,
      pointerType: "mouse",
      isPrimary: true,
      button: 0,
      buttons: 1,
      clientX: startX,
      clientY: startY + deltaY,
    }));
    requireAudit(
      JSON.stringify(state.sourceTransform) !== beforePointerTransform,
      "pointer_state_missing",
    );
    requireAudit(
      overlayStyle(overlay) !== beforePointer,
      "pointer_overlay_missing",
    );
    await waitFor(
      () => state.mediaComposition?.status === "ready" && liveRenderCount === 1,
      "pointer_live_render_timeout",
      30000,
    );
    requireAudit(
      document.querySelector("#media-compositor-stage") === stage
        && stage.classList.contains("dragging"),
      "drag_stage_replaced_during_live_render",
    );
    const afterLiveRenderTransform = JSON.stringify(state.sourceTransform);
    stage.dispatchEvent(new PointerEvent("pointermove", {
      bubbles: true,
      cancelable: true,
      pointerId,
      pointerType: "mouse",
      isPrimary: true,
      button: 0,
      buttons: 1,
      clientX: startX,
      clientY: startY - deltaY,
    }));
    requireAudit(
      JSON.stringify(state.sourceTransform) !== afterLiveRenderTransform,
      "drag_did_not_continue_after_live_render",
    );
    liveRenderCount = 0;
    stage.dispatchEvent(new PointerEvent("pointerup", {
      bubbles: true,
      cancelable: true,
      pointerId,
      pointerType: "mouse",
      isPrimary: true,
      button: 0,
      buttons: 0,
      clientX: startX,
      clientY: startY - deltaY,
    }));
    if (hadOwnCapture) stage.setPointerCapture = nativeCapture;
    else delete stage.setPointerCapture;
    requireAudit(notFoundObserved, "not_found_capture_path_missing");
    requireAudit(!stage.classList.contains("dragging"), "drag_state_not_released");

    window.__mediaFramingAuditStep = "keyboard_input";
    const keyboardBaseline = document.querySelector('[data-source-preset="fill"]');
    requireAudit(keyboardBaseline, "keyboard_baseline_missing");
    keyboardBaseline.click();
    requireAudit(
      state.sourceTransform.scale_x === 1
        && state.sourceTransform.scale_y === 1
        && state.sourceTransform.offset_x === 0
        && state.sourceTransform.offset_y === 0,
      "keyboard_baseline_failed",
    );
    const beforeKeyboard = overlayStyle(overlay);
    const beforeKeyboardTransform = JSON.stringify(state.sourceTransform);
    stage.focus({focusVisible: true});
    stage.dispatchEvent(new KeyboardEvent("keydown", {
      bubbles: true,
      cancelable: true,
      key: "ArrowUp",
    }));
    requireAudit(
      JSON.stringify(state.sourceTransform) !== beforeKeyboardTransform,
      "keyboard_state_missing",
    );
    requireAudit(overlayStyle(overlay) !== beforeKeyboard, "keyboard_feedback_missing");
    const focusStyle = getComputedStyle(stage);
    requireAudit(
      document.activeElement === stage
        && (stage.matches(":focus-visible") || focusStyle.boxShadow !== "none"),
      "focus_not_visible",
    );

    window.__mediaFramingAuditStep = "slider_input";
    document.querySelector('[data-source-preset="fill"]').click();
    const slider = document.querySelector("#source-zoom");
    const beforeSlider = overlayStyle(overlay);
    slider.value = "150";
    slider.dispatchEvent(new Event("input", {bubbles: true}));
    requireAudit(
      overlayStyle(overlay) !== beforeSlider
        && state.sourceTransform.scale_x === 1.5
        && state.sourceTransform.scale_y === 1.5
        && state.sourceTransform.offset_x === 0
        && state.sourceTransform.offset_y === 0,
      "slider_feedback_missing",
    );
    const overlayFinding = overlayGeometryFinding();
    requireAudit(!overlayFinding, overlayFinding || "overlay_geometry_mismatch");
    const workspaceFinding = synchronizedWorkspaceFinding();
    requireAudit(!workspaceFinding, workspaceFinding || "synchronized_workspace_mismatch");
    requireAudit(layoutFindings().length === 0, "layout_escape");

    window.__mediaFramingAuditStep = "stale_preview";
    const browserTransform = canonicalizeSourceTransform(
      state.sourceTransform,
      {width: 20, height: 5},
      mediaDestinationSizes(),
    );
    requireAudit(sameJson(browserTransform, state.sourceTransform), "browser_transform_not_canonical");
    requireAudit(state.mediaComposition.status !== "ready", "preview_not_invalidated");
    requireAudit(document.querySelector("#media-compose-apply").disabled, "stale_apply_enabled");
    const stalePage = pageFingerprint();
    const staleUndo = state.undo.length;
    applyMediaCompositionDraft();
    requireAudit(
      pageFingerprint() === stalePage && state.undo.length === staleUndo,
      "stale_apply_mutated_document",
    );

    window.__mediaFramingAuditStep = "render_coalescing";
    await waitFor(
      () => state.mediaComposition?.status === "ready"
        && mediaCompositionCanApply(state.mediaComposition)
        && liveRenderCount === 1,
      "render_coalescing_timeout",
      30000,
    );
    countLiveRenders = false;
    requireAudit(liveRenderCount === 1, "render_coalescing_overlap");

    window.__mediaFramingAuditStep = "preview";
    document.querySelector("#media-compose-preview").click();
    await waitFor(
      () => state.mediaComposition?.status === "ready"
        && !document.querySelector("#media-compose-apply")?.disabled,
      "preview_timeout",
      30000,
    );
    requireAudit(
      sameJson(browserTransform, state.mediaComposition.transform),
      "backend_transform_mismatch",
    );
    const mappedFrames = state.mediaComposition.mappedResult?.tracks?.frames?.frames;
    requireAudit(
      Array.isArray(mappedFrames) && mappedFrames.length === fixture.expected_frames.length,
      "mapped_frames_mismatch",
    );
    fixture.expected_frames.forEach((expected, frameIndex) => {
      const colors = mappedFrames[frameIndex];
      requireAudit(Array.isArray(colors) && colors.length === 200, "mapped_pixel_count_mismatch");
      const nonBlack = colors.filter(color => String(color).toLowerCase() !== "#000000").length;
      requireAudit(nonBlack === expected.non_black, "mapped_non_black_mismatch");
      for (const [pixel, color] of expected.sentinels) {
        requireAudit(
          String(colors[pixel]).toLowerCase() === String(color).toLowerCase(),
          "mapped_sentinel_mismatch",
        );
      }
    });

    window.__mediaFramingAuditStep = "selected_frame_tier";
    selectedFrameArmed = true;
    selectedFullArmed = true;
    selectedFrameCalls = 0;
    selectedFrameActive = 0;
    selectedFrameMaxActive = 0;
    selectedFrameBlocked = false;
    selectedFrameSettled = 0;
    selectedFrameRequests = [];
    selectedFrameResponses = [];
    selectedFullBlocked = false;
    selectedFullSettled = false;
    const selectedPage = pageFingerprint();
    const selectedUndo = state.undo.length;
    const selectedSlider = document.querySelector("#source-zoom");
    requireAudit(selectedSlider, "selected_frame_slider_missing");
    const selectedStart = Number(selectedSlider.value);
    const selectedDirection = selectedStart <= 3196 ? 1 : -1;
    selectedSlider.value = String(selectedStart + selectedDirection);
    selectedSlider.dispatchEvent(new Event("input", {bubbles: true}));
    await waitFor(() => selectedFrameBlocked, "selected_frame_block_timeout", 30000);
    selectedSlider.value = String(selectedStart + (selectedDirection * 2));
    selectedSlider.dispatchEvent(new Event("input", {bubbles: true}));
    selectedSlider.value = String(selectedStart + (selectedDirection * 3));
    selectedSlider.dispatchEvent(new Event("input", {bubbles: true}));
    releaseSelectedFrame();
    await waitFor(
      () => selectedFrameCalls === 2
        && selectedFrameSettled === 2
        && selectedFullBlocked
        && lightingWorkspace.media?.accepted_frame_revision
          === state.mediaComposition?.revision,
      "selected_frame_latest_timeout",
      30000,
    );
    requireAudit(selectedFrameCalls === 2, "selected_frame_not_latest_only");
    requireAudit(selectedFrameMaxActive === 1, "selected_frame_overlap");
    const latestSelectedRequest = selectedFrameRequests.at(-1);
    const latestSelectedResponse = selectedFrameResponses.at(-1);
    const selectedColors = latestSelectedResponse?.mapped_frame?.tracks?.[
      state.ledTarget
    ]?.colors;
    const selectedProjection = selectBoardProjection(lightingWorkspace);
    const selectedPainted = [...document.querySelectorAll("#led-canvas .pixel")].map(
      pixel => pixel.style.getPropertyValue("--pixel-color").trim().toUpperCase(),
    );
    requireAudit(
      latestSelectedRequest?.transform?.scale_x === state.sourceTransform.scale_x
        && latestSelectedResponse?.timeline_entry?.index
          === latestSelectedRequest?.frame_index,
      "selected_frame_request_not_latest",
    );
    requireAudit(
      Array.isArray(selectedColors)
        && sameJson(selectedProjection?.colors, selectedColors.map(color => color.toUpperCase()))
        && sameJson(selectedPainted, selectedColors.map(color => color.toUpperCase())),
      "selected_frame_board_mismatch",
    );
    requireAudit(
      !mediaCompositionCanApply(state.mediaComposition)
        && document.querySelector("#media-compose-apply")?.disabled,
      "selected_frame_enabled_apply",
    );
    requireAudit(
      pageFingerprint() === selectedPage && state.undo.length === selectedUndo,
      "selected_frame_changed_document",
    );
    releaseSelectedFull();
    await waitFor(
      () => selectedFullSettled
        && state.mediaComposition?.status === "ready"
        && mediaCompositionCanApply(state.mediaComposition),
      "selected_full_release_timeout",
      30000,
    );
    const selectedFullColors = state.mediaComposition.mappedResult?.tracks?.[
      state.ledTarget
    ]?.frames?.[latestSelectedRequest.frame_index];
    requireAudit(
      sameJson(selectedFullColors, selectedColors)
        && lightingWorkspace.preview.selected_frame === null,
      "selected_full_equality_mismatch",
    );
    requireAudit(
      pageFingerprint() === selectedPage && state.undo.length === selectedUndo,
      "selected_full_changed_document",
    );
    selectedFrameArmed = false;
    selectedFullArmed = false;

    window.__mediaFramingAuditStep = "queued_render_ownership";
    queuedRenderArmed = true;
    queuedRenderBlocked = false;
    queuedRenderSettled = false;
    queuedRenderCalls = 0;
    const ownershipSlider = document.querySelector("#source-zoom");
    requireAudit(ownershipSlider, "queued_render_slider_missing");
    const ownershipSliderValue = Number(ownershipSlider.value);
    const ownershipDirection = ownershipSliderValue <= 3198 ? 1 : -1;
    ownershipSlider.value = String(ownershipSliderValue + ownershipDirection);
    ownershipSlider.dispatchEvent(new Event("input", {bubbles: true}));
    await waitFor(() => queuedRenderBlocked, "queued_render_block_timeout", 30000);
    ownershipSlider.value = String(ownershipSliderValue + (ownershipDirection * 2));
    ownershipSlider.dispatchEvent(new Event("input", {bubbles: true}));
    document.querySelector("#studio-paint-tab").click();
    await waitFor(
      () => state.studioTool === "paint" && document.querySelector("#play-led"),
      "queued_render_paint_timeout",
    );
    const ownershipBoard = selectBoardProjection(lightingWorkspace);
    requireAudit(
      ownershipBoard?.frame_set?.frame_count > 1,
      "queued_render_playback_frames_missing",
    );
    document.querySelector("#play-led").click();
    await waitFor(() => state.playing, "queued_render_playback_start_timeout");
    const ownershipPreview = JSON.stringify(lightingWorkspace.preview);
    releaseQueuedRender();
    await waitFor(() => queuedRenderSettled, "queued_render_release_timeout", 30000);
    await delay(250);
    requireAudit(state.playing, "queued_render_stopped_playback");
    requireAudit(
      JSON.stringify(lightingWorkspace.preview) === ownershipPreview,
      "queued_render_changed_preview",
    );
    requireAudit(queuedRenderCalls === 1, "queued_render_was_not_cancelled");
    document.querySelector("#play-led").click();
    await waitFor(() => !state.playing, "queued_render_playback_stop_timeout");
    queuedRenderArmed = false;
    document.querySelector("#studio-source-tab").click();
    await waitFor(
      () => state.studioTool === "source" && document.querySelector("#media-compose-preview"),
      "queued_render_source_timeout",
    );
    document.querySelector("#media-compose-preview").click();
    await waitFor(
      () => state.mediaComposition?.status === "ready"
        && mediaCompositionCanApply(state.mediaComposition),
      "queued_render_preview_restore_timeout",
      30000,
    );

    window.__mediaFramingAuditStep = "apply_and_save";
    const beforeLighting = new Set(
      (await catalogItems("lighting")).map(item => item.catalog_id),
    );
    const originalApply = applyLedResultToPage;
    let mediaApplyCalls = 0;
    applyLedResultToPage = (...args) => {
      mediaApplyCalls += 1;
      return originalApply(...args);
    };
    document.querySelector("#media-compose-apply").click();
    await waitFor(() => state.mediaComposition?.status === "applied", "media_apply_timeout");
    const appliedPage = pageFingerprint();
    const appliedLighting = lightingFingerprint(JSON.parse(appliedPage));
    requireAudit(
      appliedPage !== baselinePage
        && state.undo.length === baselineUndo + 1
        && state.dirty
        && document.querySelector("#dirty-dot").classList.contains("visible")
        && mediaApplyCalls === 1,
      "media_apply_count_mismatch",
    );
    applyMediaCompositionDraft();
    requireAudit(
      pageFingerprint() === appliedPage
        && state.undo.length === baselineUndo + 1
        && mediaApplyCalls === 1,
      "media_apply_repeated",
    );
    applyLedResultToPage = originalApply;

    document.querySelector("#save-lighting-library").click();
    const savedLighting = await waitFor(async () => {
      const items = await catalogItems("lighting");
      return items.find(item => !beforeLighting.has(item.catalog_id)) || false;
    }, "save_to_library_timeout", 30000);
    const lightingId = savedLighting.catalog_id;

    document.querySelector("#undo-button").click();
    await waitFor(() => pageFingerprint() === baselinePage, "media_undo_timeout");
    requireAudit(
      state.undo.length === baselineUndo
        && state.dirty === document.querySelector("#dirty-dot").classList.contains("visible"),
      "undo_dirty_state_mismatch",
    );

    window.__mediaFramingAuditStep = "library_workflow";
    document.querySelector("#lighting-library-tab").click();
    await waitFor(
      () => state.lighting.route === ROUTES.LIBRARY && state.library.loaded,
      "library_route_timeout",
    );
    await selectLibraryFilter("lighting");
    await openLibraryItemById(lightingId);
    await waitFor(
      () => {
        const button = document.querySelector("[data-library-preview-lighting]");
        return button && !button.disabled ? button : false;
      },
      "library_preview_unavailable",
      30000,
    );
    const lightingItemsBeforePreview = (await catalogItems("lighting"))
      .map(item => item.catalog_id)
      .sort();
    const previewToastsBefore = new Set(document.querySelectorAll("#toast-region .toast"));
    document.querySelector("[data-library-preview-lighting]").click();
    const previewOutcome = await waitFor(
      () => {
        if (
          document.querySelector("#library-preview-apply")
          && document.querySelector("#library-preview-cancel")
        ) return "ready";
        const failure = [...document.querySelectorAll("#toast-region .toast.error")]
          .find(candidate => !previewToastsBefore.has(candidate));
        return failure ? "rejected" : false;
      },
      "library_preview_timeout",
      30000,
    );
    requireAudit(previewOutcome === "ready", "library_preview_rejected");
    const preview = activeTransientLightingPreview();
    const board = document.querySelector("#lighting-board-pane");
    requireAudit(
      state.lighting.route === ROUTES.EDIT
        && preview?.kind === "library_lighting"
        && preview.catalogId === lightingId
        && board,
      "library_preview_state_mismatch",
    );
    const projection = selectBoardProjection(lightingWorkspace);
    const previewColors = preview?.boardFrameSet?.frames_by_target?.[preview.target]?.[
      projection?.index
    ];
    const paintedPreviewColors = [...board.querySelectorAll("#led-canvas .pixel")].map(
      pixel => pixel.style.getPropertyValue("--pixel-color").trim().toUpperCase(),
    );
    requireAudit(
      pageFingerprint() === baselinePage && state.undo.length === baselineUndo,
      "library_preview_changed_document",
    );
    requireAudit(
      projection?.frame_set === preview.boardFrameSet
        && sameJson(projection.colors, previewColors)
        && sameJson(paintedPreviewColors, previewColors)
        && !board.querySelector("img,picture,video,canvas,svg,image"),
      "library_preview_board_mismatch",
    );
    const lightingItemsAfterPreview = (await catalogItems("lighting"))
      .map(item => item.catalog_id)
      .sort();
    requireAudit(
      sameJson(lightingItemsAfterPreview, lightingItemsBeforePreview),
      "library_preview_created_item",
    );

    document.querySelector("#library-preview-cancel").click();
    await waitFor(
      () => state.lighting.route === ROUTES.LIBRARY
        && state.transientLightingPreview === null
        && state.library.selectedCatalogId === lightingId,
      "library_preview_cancel_timeout",
      30000,
    );
    requireAudit(
      pageFingerprint() === baselinePage && state.undo.length === baselineUndo,
      "library_preview_cancel_changed_document",
    );

    await waitFor(
      () => {
        const button = document.querySelector("[data-library-preview-lighting]");
        return button && !button.disabled ? button : false;
      },
      "library_preview_reopen_unavailable",
      30000,
    );
    document.querySelector("[data-library-preview-lighting]").click();
    await waitFor(
      () => activeTransientLightingPreview()?.catalogId === lightingId
        && document.querySelector("#library-preview-apply"),
      "library_preview_reopen_timeout",
      30000,
    );
    const originalLibraryApply = applyLedResultToPage;
    let libraryApplyCalls = 0;
    applyLedResultToPage = (...args) => {
      libraryApplyCalls += 1;
      return originalLibraryApply(...args);
    };
    document.querySelector("#library-preview-apply").click();
    await waitFor(
      () => state.lighting.route === ROUTES.EDIT
        && !activeTransientLightingPreview()
        && lightingFingerprint(getPage(state.ledSlot)) === appliedLighting,
      "library_apply_timeout",
      30000,
    );
    requireAudit(
      state.undo.length === baselineUndo + 1 && libraryApplyCalls === 1,
      "library_apply_count_mismatch",
    );
    applyLedResultToPage = originalLibraryApply;

    document.querySelector("#undo-button").click();
    await waitFor(() => pageFingerprint() === baselinePage, "library_apply_undo_timeout");
    requireAudit(state.undo.length === baselineUndo, "library_apply_undo_count_mismatch");

    document.querySelector("#lighting-library-tab").click();
    await waitFor(() => state.lighting.route === ROUTES.LIBRARY, "library_return_timeout");
    await selectLibraryFilter("lighting");
    await openLibraryItemById(lightingId);
    document.querySelector("[data-library-remove]").click();
    await waitFor(
      () => {
        const undo = document.querySelector("[data-library-undo-remove]");
        return state.library.undoRemoval?.catalogId === lightingId && undo && !undo.disabled
          ?undo
          :false;
      },
      "library_remove_timeout",
      30000,
    );
    document.querySelector("[data-library-undo-remove]").click();
    await waitFor(async () => {
      const items = await catalogItems("lighting");
      return !state.library.undoRemoval
        && !state.library.mutatingCatalogId
        && !state.library.loading
        && items.some(item => item.catalog_id === lightingId);
    }, "library_remove_undo_timeout", 30000);

    await selectLibraryFilter("lighting");
    await openLibraryItemById(lightingId);
    document.querySelector("[data-library-remove]").click();
    await waitFor(
      () => state.library.undoRemoval?.catalogId === lightingId
        && !state.library.mutatingCatalogId
        && !state.library.loading,
      "library_second_remove_timeout",
      30000,
    );
    await selectLibraryFilter("removed");
    await openLibraryItemById(lightingId);
    const restoreButton = await waitFor(() => {
      const button = document.querySelector("[data-library-restore]");
      return button && !button.disabled ? button : false;
    }, "library_restore_unavailable", 30000);
    restoreButton.click();
    await waitFor(async () => {
      const items = await catalogItems("lighting");
      return !state.library.mutatingCatalogId
        && !state.library.loading
        && items.some(item => item.catalog_id === lightingId);
    }, "library_restore_timeout", 30000);

    await selectLibraryFilter("lighting");
    await openLibraryItemById(lightingId);
    document.querySelector("[data-library-remove]").click();
    await waitFor(
      () => state.library.undoRemoval?.catalogId === lightingId
        && !state.library.mutatingCatalogId
        && !state.library.loading,
      "library_third_remove_timeout",
      30000,
    );
    await selectLibraryFilter("removed");
    await openLibraryItemById(lightingId);
    const deleteButton = await waitFor(() => {
      const button = document.querySelector("[data-library-delete]");
      return button && !button.disabled ? button : false;
    }, "library_delete_unavailable", 30000);
    deleteButton.click();
    requireAudit(document.querySelector("#library-confirm-dialog").open, "delete_confirmation_missing");
    document.querySelector("#library-confirm-action").click();
    await waitFor(async () => {
      const live = await catalogItems("lighting");
      const removed = await catalogItems("removed");
      return !state.library.mutatingCatalogId
        && !state.library.loading
        && !live.some(item => item.catalog_id === lightingId)
        && !removed.some(item => item.catalog_id === lightingId);
    }, "library_delete_timeout", 30000);

    window.__mediaFramingAuditStep = "cancel";
    document.querySelector('[data-route="lighting/edit"]')?.click();
    await waitFor(() => state.lighting.route === ROUTES.EDIT, "edit_return_timeout");
    requireAudit(
      pageFingerprint() === baselinePage && state.undo.length === baselineUndo,
      "library_workflow_changed_document",
    );
    document.querySelector("#studio-source-tab").click();
    await waitFor(() => document.querySelector("#media-compose-cancel"), "cancel_button_missing");
    document.querySelector("#media-compose-cancel").click();
    requireAudit(
      state.mediaComposition?.status === "cancelled" && pageFingerprint() === baselinePage,
      "cancel_changed_document",
    );
    releaseLateSource();
    window.fetch = originalFetch;
    requireAudit(consoleErrors.length === 0, "console_errors_present");

    return {format: fixture.format, checks: requiredChecks};
  }

  window.__runMediaFramingAudit = async (
    fixtures,
    jsonFixtures,
    width,
    height,
    includeProfileChecks,
  ) => {
    const cases = [];
    for (const fixture of fixtures) {
      cases.push(await runCase(fixture, width, height));
    }
    const profileChecks = includeProfileChecks
      ? await runProfileChecks(jsonFixtures)
      : [];
    const findings = layoutFindings();
    requireAudit(findings.length === 0, "layout_escape");
    requireAudit(consoleErrors.length === 0, "console_errors_present");
    return {
      width,
      height,
      cases,
      layout_findings: findings,
      console_errors: consoleErrors.slice(),
      profile_checks: profileChecks,
    };
  };
  window.__mediaFramingAuditFailure = error => ({
    failure: /^[a-z0-9_:-]{1,200}$/.test(String(error?.auditCode || ""))
      ? String(error.auditCode)
      : `workflow_${/^[a-z0-9_:-]{1,180}$/.test(String(window.__mediaFramingAuditStep || ""))
        ? String(window.__mediaFramingAuditStep)
        : "failed"}`,
  });
  window[resultSlot] = null;
})()
"""


def _audit_script() -> str:
    return (
        _AUDIT_SCRIPT.replace("__RESULT_SLOT__", _RESULT_SLOT)
        .replace(
            "__REQUIRED_CHECKS__",
            json.dumps(REQUIRED_CASE_CHECKS, ensure_ascii=True, separators=(",", ":")),
        )
        .replace(
            "__REQUIRED_PROFILE_CHECKS__",
            json.dumps(
                REQUIRED_PROFILE_CHECKS,
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        )
    )


def _poll_async_result(window: Any, kickoff: str, *, timeout: float) -> dict:
    window.run_js(f"window.{_RESULT_SLOT}=undefined;{kickoff}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = window.run_js(
            f"window.{_RESULT_SLOT}===undefined?null:JSON.stringify(window.{_RESULT_SLOT})"
        )
        if raw:
            try:
                result = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                raise MediaFramingAuditError("invalid_webview_result") from None
            if not isinstance(result, dict):
                raise MediaFramingAuditError("invalid_webview_result")
            failure = result.get("failure")
            if isinstance(failure, str) and re.fullmatch(r"[a-z0-9_:-]{1,200}", failure):
                raise MediaFramingAuditError(failure)
            return result
        time.sleep(0.05)
    raise MediaFramingAuditError("webview_audit_timeout")


def _activate_webview_window(window: Any, *, timeout: float = 5) -> None:
    """Show and activate the native window before inspecting focus styling."""

    window.show()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if window.run_js("document.hasFocus()"):
            return
        time.sleep(0.05)
    raise MediaFramingAuditError("webview_focus_timeout")


def _run_webview_workflow(
    window: Any,
    fixtures: list[dict[str, object]],
    json_fixtures: list[dict[str, str]],
) -> list[dict]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        ready = window.run_js(
            "Boolean(window.LibraryState&&window.LightingComposer&&"
            "typeof state==='object'&&state.config&&"
            "document.querySelector('[data-route=\"lighting/edit\"]'))"
        )
        if ready:
            break
        time.sleep(0.05)
    else:
        raise MediaFramingAuditError("webview_boot_timeout")
    window.run_js(_audit_script())
    encoded_fixtures = json.dumps(
        fixtures,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    encoded_json_fixtures = json.dumps(
        json_fixtures,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    results: list[dict] = []
    for index, (width, height) in enumerate(AUDIT_VIEWPORTS):
        window.resize(width, height)
        time.sleep(0.4)
        _activate_webview_window(window)
        kickoff = (
            "void window.__runMediaFramingAudit("
            f"{encoded_fixtures},{encoded_json_fixtures},{width},{height},"
            f"{str(index == len(AUDIT_VIEWPORTS) - 1).lower()})"
            f".then(value=>{{window.{_RESULT_SLOT}=value;}})"
            f".catch(error=>{{window.{_RESULT_SLOT}=window.__mediaFramingAuditFailure(error);}});"
        )
        results.append(_poll_async_result(window, kickoff, timeout=180))
    return results


@contextmanager
def _isolated_environment(data_root: Path) -> Iterator[None]:
    from .ai_catalog import PROVIDER_ENVIRONMENT_VARIABLES

    names = ("AM_CONFIGURATOR_DATA_DIR", *PROVIDER_ENVIRONMENT_VARIABLES.values())
    previous = {name: os.environ.get(name) for name in names}
    os.environ["AM_CONFIGURATOR_DATA_DIR"] = str(data_root)
    for name in PROVIDER_ENVIRONMENT_VARIABLES.values():
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _native_audit_report() -> dict:
    try:
        import webview
    except ModuleNotFoundError as exc:
        if exc.name == "webview":
            raise MediaFramingAuditError("webview_unavailable") from None
        raise

    from .credentials import MemoryCredentialStore
    from .desktop import (
        _OfflineOllamaInventory,
        _disable_macos_automatic_window_tabbing,
        _native_webview_policy,
        _native_webview_start_options,
        _offline_device_discovery,
    )
    from .library import GeneratedAssetLibrary
    from .server import create_server

    temporary_parent = Path(tempfile.gettempdir()).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix=_AUDIT_ROOT_PREFIX, dir=temporary_parent))
    expected_root = root.resolve(strict=True)
    data_root = root / "data"
    library_root = root / "library"
    data_root.mkdir()
    library_root.mkdir()
    expected_children = (
        data_root.resolve(strict=True),
        library_root.resolve(strict=True),
    )
    document_path = root / "document.json"
    document = build_audit_document()
    fixtures = build_media_fixtures()
    json_fixtures = build_json_fixtures()
    selections: list[object] = []
    for _viewport in AUDIT_VIEWPORTS:
        for fixture in fixtures:
            selections.extend((
                {"name": "unsupported.gif", "payload": b"not supported media"},
                fixture,
            ))
    media_bridge = _AuditMediaBridge(tuple(selections))
    document_path.write_text(
        json.dumps(document, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    server = None
    server_thread = None
    result_holder: dict[str, object] = {}
    prior_downloads = webview.settings.get("ALLOW_DOWNLOADS")
    had_download_setting = "ALLOW_DOWNLOADS" in webview.settings
    try:
        with _isolated_environment(data_root):
            library = GeneratedAssetLibrary(library_root, minimum_free_bytes=1)
            server, url = create_server(
                [str(document_path)],
                lighting_library=library,
                ollama_client=_OfflineOllamaInventory(),
                credential_store=MemoryCredentialStore(),
                device_discovery=_offline_device_discovery,
            )
            server.state.desktop_bridge = media_bridge
            server_thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name="am-media-framing-audit-api",
                daemon=True,
            )
            server_thread.start()
            _disable_macos_automatic_window_tabbing()
            webview.settings["ALLOW_DOWNLOADS"] = False
            window = webview.create_window(
                "AM Configurator media framing audit",
                url,
                width=AUDIT_VIEWPORTS[0][0],
                height=AUDIT_VIEWPORTS[0][1],
                min_size=AUDIT_VIEWPORTS[0],
                background_color="#0d0d0f",
                text_select=False,
                zoomable=False,
            )

            def execute() -> None:
                try:
                    result_holder["viewports"] = _run_webview_workflow(
                        window,
                        _fixture_payload(fixtures),
                        _json_fixture_payload(json_fixtures),
                    )
                except Exception as exc:  # noqa: BLE001 - marshal to the GUI owner
                    result_holder["error"] = exc
                finally:
                    window.destroy()

            _backend, renderer, _expected = _native_webview_policy()
            with _native_webview_start_options() as start_options:
                webview.start(
                    func=execute,
                    gui=renderer,
                    debug=False,
                    **start_options,
                )
            error = result_holder.get("error")
            if isinstance(error, MediaFramingAuditError):
                raise error
            if error is not None:
                raise MediaFramingAuditError("webview_workflow_failed")
            report = {
                "schema_version": 2,
                "status": "passed",
                "failure": None,
                "viewports": result_holder.get("viewports"),
            }
            return validate_audit_report(report)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if server_thread is not None:
            server_thread.join(timeout=2)
        if had_download_setting:
            webview.settings["ALLOW_DOWNLOADS"] = prior_downloads
        else:
            webview.settings.pop("ALLOW_DOWNLOADS", None)
        cleanup_audit_root(
            root,
            expected_root=expected_root,
            expected_parent=temporary_parent,
            expected_children=expected_children,
        )


def run_media_framing_audit(output: Path) -> int:
    """Run both native viewports and emit one bounded sanitized JSON result."""

    try:
        report = _native_audit_report()
    except Exception as exc:  # noqa: BLE001 - never persist runtime or host details
        failure = (
            str(exc)
            if isinstance(exc, MediaFramingAuditError)
            and re.fullmatch(r"[a-z0-9_:-]{1,200}", str(exc)) is not None
            else "audit_failed"
        )
        failed = {
            "schema_version": 2,
            "status": "failed",
            "failure": failure,
            "viewports": [],
        }
        try:
            write_audit_report(output, failed)
        except MediaFramingAuditError:
            return 2
        return 1
    try:
        write_audit_report(output, report)
    except MediaFramingAuditError:
        return 2
    return 0
