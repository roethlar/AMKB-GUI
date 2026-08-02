from __future__ import annotations

import argparse
import ctypes
import json
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

import webview
from PIL import ImageGrab

from am_configurator.credentials import MemoryCredentialStore
from am_configurator.desktop import (
    _OfflineOllamaInventory,
    _disable_macos_automatic_window_tabbing,
    _native_webview_policy,
    _native_webview_start_options,
    _offline_device_discovery,
)
from am_configurator.library import GeneratedAssetLibrary
from am_configurator.media_framing_audit import (
    _AUDIT_ROOT_PREFIX,
    _activate_webview_window,
    _isolated_environment,
    build_audit_document,
    cleanup_audit_root,
)
from am_configurator.server import create_server


TITLE = "AM Configurator LSR-6 Effects audit"
VIEWPORT = (1000, 680)


def wait_js(window: Any, expression: str, code: str, timeout: float = 20) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = window.evaluate_js(expression)
            if value:
                return value
        except Exception:
            pass
        time.sleep(0.05)
    raise RuntimeError(code)


def capture_window(path: Path) -> None:
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, TITLE)
    if not hwnd:
        raise RuntimeError("native_window_not_found")
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("native_window_rect_unavailable")
    image = ImageGrab.grab(
        bbox=(rect.left, rect.top, rect.right, rect.bottom),
        all_screens=True,
    )
    image.save(path, format="PNG")


def run_workflow(window: Any, screenshot_path: Path) -> dict[str, object]:
    wait_js(
        window,
        "Boolean(window.LightingWorkspace&&typeof state==='object'&&state.config&&"
        "document.querySelector('[data-route=\"lighting/edit\"]'))",
        "webview_boot_timeout",
    )
    window.resize(*VIEWPORT)
    time.sleep(0.4)
    _activate_webview_window(window)
    window.evaluate_js(
        "document.querySelector('[data-route=\"lighting/edit\"]')?.click(); true"
    )
    wait_js(
        window,
        "state.lighting.route===ROUTES.EDIT&&"
        "Boolean(document.querySelector('[data-lighting-target=\"frames\"]'))",
        "lighting_route_timeout",
    )
    window.evaluate_js(
        "document.querySelector('[data-lighting-target=\"frames\"]')?.click(); true"
    )
    wait_js(
        window,
        "state.ledTarget==='frames'&&Boolean(document.querySelector('[data-studio-tool=\"animate\"]'))",
        "display_target_timeout",
    )
    before = window.evaluate_js("JSON.stringify(getPage(state.ledSlot))")
    window.evaluate_js(
        "document.querySelector('[data-studio-tool=\"animate\"]')?.click(); true"
    )
    wait_js(
        window,
        "state.studioTool==='animate'&&"
        "document.querySelectorAll('[data-effect-preset]').length===5",
        "effects_tool_timeout",
    )
    window.evaluate_js(
        "document.querySelector('[data-effect-preset=\"hue_cycle\"]')?.click(); true"
    )
    wait_js(
        window,
        "lightingWorkspace.effect_draft?.specification?.type==='hue_cycle'&&"
        "Boolean(document.querySelector('#animate-draft-status'))",
        "effect_draft_timeout",
    )
    reduced_motion = bool(
        window.evaluate_js("matchMedia('(prefers-reduced-motion: reduce)').matches")
    )
    start_index = int(window.evaluate_js("lightingWorkspace.playhead.index"))
    if reduced_motion:
        wait_js(
            window,
            "!lightingWorkspace.playhead.playing&&"
            "lightingWorkspace.effect_draft.demonstrative_frame!==null",
            "reduced_motion_effect_timeout",
        )
        advanced = False
    else:
        wait_js(
            window,
            "lightingWorkspace.playhead.playing",
            "effect_autoplay_timeout",
        )
        wait_js(
            window,
            f"lightingWorkspace.playhead.index!=={start_index}",
            "effect_frame_advance_timeout",
        )
        advanced = True
    result = window.evaluate_js(
        """
        (() => {
          const status = document.querySelector('#animate-draft-status');
          const cards = [...document.querySelectorAll('[data-effect-preset]')];
          const selected = document.querySelector('[data-effect-preset="hue_cycle"]');
          const apply = document.querySelector('#animate-accept');
          const cancel = document.querySelector('#animate-cancel');
          const board = document.querySelector('#led-canvas');
          const rect = status?.getBoundingClientRect();
          return {
            labels: cards.map(card => card.querySelector('strong')?.textContent || ''),
            selected: selected?.getAttribute('aria-pressed') === 'true',
            status: status?.innerText || '',
            status_tone: status?.className || '',
            helper_font_px: Number.parseFloat(getComputedStyle(selected.querySelector('small')).fontSize),
            apply_enabled: Boolean(apply && !apply.disabled),
            cancel_enabled: Boolean(cancel && !cancel.disabled),
            board_pixels: board?.querySelectorAll('.pixel').length || 0,
            frame_count: lightingWorkspace.effect_draft?.board_frame_set?.frame_count || 0,
            playing: lightingWorkspace.playhead.playing,
            status_visible: Boolean(rect && rect.width > 0 && rect.height > 0),
            viewport_contained: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 2,
          };
        })()
        """
    )
    if result["labels"] != ["Pulse", "Hue cycle", "Sweep", "Shimmer", "Move & zoom"]:
        raise RuntimeError("effect_cards_mismatch")
    if not result["selected"] or "Hue cycle" not in result["status"]:
        raise RuntimeError("effect_selection_not_visible")
    if result["helper_font_px"] < 13:
        raise RuntimeError("effect_helper_text_too_small")
    if not result["apply_enabled"] or not result["cancel_enabled"]:
        raise RuntimeError("effect_actions_unavailable")
    if result["board_pixels"] != 200 or result["frame_count"] < 2:
        raise RuntimeError("effect_board_output_missing")
    if not result["status_visible"] or not result["viewport_contained"]:
        raise RuntimeError("effect_layout_not_visible")
    time.sleep(0.25)
    capture_window(screenshot_path)
    window.evaluate_js("document.querySelector('#animate-cancel')?.click(); true")
    wait_js(window, "!lightingWorkspace.effect_draft", "effect_cancel_timeout")
    after = window.evaluate_js("JSON.stringify(getPage(state.ledSlot))")
    if before != after:
        raise RuntimeError("effect_cancel_mutated_document")
    return {
        **result,
        "reduced_motion": reduced_motion,
        "frame_advanced": advanced,
        "cancel_preserved_document": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    review_directory = Path(__file__).resolve().parent
    report_path = args.report.resolve()
    screenshot_path = args.screenshot.resolve()
    if report_path.parent != review_directory or screenshot_path.parent != review_directory:
        raise RuntimeError("audit_outputs_must_stay_in_review_directory")
    if report_path.exists() or screenshot_path.exists():
        raise RuntimeError("audit_output_already_exists")

    temporary_parent = Path(tempfile.gettempdir()).resolve(strict=True)
    root = Path(tempfile.mkdtemp(prefix=_AUDIT_ROOT_PREFIX, dir=temporary_parent))
    expected_root = root.resolve(strict=True)
    data_root = root / "data"
    library_root = root / "library"
    data_root.mkdir()
    library_root.mkdir()
    expected_children = (data_root.resolve(strict=True), library_root.resolve(strict=True))
    document_path = root / "document.json"
    document_path.write_text(
        json.dumps(build_audit_document(), ensure_ascii=True, separators=(",", ":")),
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
            server_thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name="am-lsr6-effects-audit-api",
                daemon=True,
            )
            server_thread.start()
            _disable_macos_automatic_window_tabbing()
            webview.settings["ALLOW_DOWNLOADS"] = False
            window = webview.create_window(
                TITLE,
                url,
                x=40,
                y=40,
                width=VIEWPORT[0],
                height=VIEWPORT[1],
                min_size=VIEWPORT,
                background_color="#0d0d0f",
                text_select=False,
                zoomable=False,
            )

            def execute() -> None:
                try:
                    result_holder["result"] = run_workflow(window, screenshot_path)
                except Exception as exc:  # noqa: BLE001 - report through GUI owner
                    result_holder["error"] = exc
                finally:
                    window.destroy()

            _backend, renderer, _expected = _native_webview_policy()
            with _native_webview_start_options() as start_options:
                webview.start(func=execute, gui=renderer, debug=False, **start_options)
            error = result_holder.get("error")
            if error is not None:
                raise error
            report = {
                "schema_version": 1,
                "status": "passed",
                "viewport": list(VIEWPORT),
                "result": result_holder["result"],
            }
            report_path.write_text(
                json.dumps(report, ensure_ascii=True, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
            return 0
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


if __name__ == "__main__":
    raise SystemExit(main())
