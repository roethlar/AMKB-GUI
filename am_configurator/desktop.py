"""Native cross-platform window for the AM Configurator web interface."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from .server import create_server


def _smoke_recipe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": "Offline procedural smoke",
        "density": "dense",
        "background": "#080810",
        "palette": ["#00E5C9", "#8B4FFF"],
        "layers": [{
            "kind": "wave",
            "color_index": 0,
            "secondary_color_index": 1,
            "speed": 1,
            "phase": 0.25,
            "direction_degrees": 45.0,
            "center_x": 0.5,
            "center_y": 0.5,
            "scale": 1.2,
            "width": 0.8,
            "trail": 0.6,
            "count": 3,
            "intensity": 1.0,
            "seed": 42,
        }],
    }


def _folder_dialog_type() -> Any:
    """Resolve pywebview's folder-dialog enum without making it a base install."""
    import webview

    return webview.FileDialog.FOLDER


def _model_dialog_type() -> Any:
    """Resolve pywebview's file-open enum without making it a base install."""
    import webview

    return webview.FileDialog.OPEN


def _open_reveal_target(target: Path) -> None:
    """Open a validated target in the platform file manager."""
    system = platform.system()
    if system == "Darwin":
        command = ["open", str(target)] if target.is_dir() else ["open", "-R", str(target)]
    elif system == "Windows":
        command = (
            ["explorer", str(target)]
            if target.is_dir()
            else ["explorer", "/select,", str(target)]
        )
    else:
        command = ["xdg-open", str(target if target.is_dir() else target.parent)]
    subprocess.Popen(  # noqa: S603 - fixed executable and validated path argument
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class DesktopBridge:
    """Narrow native bridge for model/library selection and Library reveal.

    Settings persistence intentionally remains behind the authenticated loopback
    HTTP API. Only these narrow chooser/reveal methods are exposed to JavaScript
    by pywebview.
    """

    def __init__(
        self,
        window: Any | None = None,
        *,
        settings_loader: Callable[[], dict] | None = None,
        opener: Callable[[Path], None] | None = None,
    ) -> None:
        self._window = window
        self._settings_loader = settings_loader
        self._opener = opener or _open_reveal_target

    def _bind_window(self, window: Any) -> None:
        self._window = window

    def choose_library_folder(self) -> str | None:
        """Return one canonical absolute directory, or ``None`` on cancellation."""
        if self._window is None:
            return None
        selected = self._window.create_file_dialog(
            dialog_type=_folder_dialog_type(),
            allow_multiple=False,
        )
        if not selected:
            return None
        raw = selected if isinstance(selected, str) else selected[0]
        if not isinstance(raw, str) or not raw:
            return None
        try:
            path = Path(raw).expanduser()
            if not path.is_absolute() or not path.is_dir():
                return None
            return str(path.resolve(strict=True))
        except (OSError, RuntimeError):
            return None

    def _choose_local_model(self) -> str | None:
        """Return a native-picked GGUF path only to the loopback server.

        The leading underscore keeps pywebview from exposing this path-returning
        method to browser JavaScript.
        """
        if self._window is None:
            return None
        selected = self._window.create_file_dialog(
            dialog_type=_model_dialog_type(),
            allow_multiple=False,
            file_types=("GGUF model (*.gguf)",),
        )
        if not selected:
            return None
        raw = selected if isinstance(selected, str) else selected[0]
        if not isinstance(raw, str) or not raw:
            return None
        try:
            path = Path(raw).expanduser()
            if (
                not path.is_absolute()
                or path.suffix.lower() != ".gguf"
                or path.is_symlink()
                or not path.is_file()
            ):
                return None
            return str(path.resolve(strict=True))
        except (OSError, RuntimeError):
            return None

    def reveal_library_path(self, value: object) -> bool:
        """Reveal an existing target only when a recorded library root owns it."""
        if not isinstance(value, str) or not value:
            return False
        try:
            target = Path(value).expanduser()
            if not target.is_absolute():
                return False
            target = target.resolve(strict=True)
            settings = self._load_settings()
            library = settings.get("library", {})
            configured = [library.get("current_root"), *(library.get("roots") or [])]
            roots = [self._canonical_root(root) for root in configured]
            if not any(
                root is not None and (target == root or root in target.parents)
                for root in roots
            ):
                return False
            self._opener(target)
            return True
        except (OSError, RuntimeError, TypeError, ValueError):
            return False

    def _load_settings(self) -> dict:
        if self._settings_loader is not None:
            return self._settings_loader()
        from . import store

        return store.load_settings()

    @staticmethod
    def _canonical_root(value: object) -> Path | None:
        if not isinstance(value, str) or not value:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        return path.resolve(strict=False)


def _assert_no_bundled_models() -> None:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root is None:
        return
    root = Path(frozen_root)
    if any(root.rglob("*.gguf")):
        raise SystemExit("Desktop smoke test failed: application bundle contains model weights.")


def _run_disabled_ai_smoke() -> None:
    """Verify disabled startup attests files without constructing a provider."""
    from unittest.mock import patch

    from . import store
    from .ai_capability import AICapabilityService
    from .credentials import MemoryCredentialStore
    from .local_ai_runtime import get_local_ai_runtime
    from .local_model import LocalModelManager

    runtime = get_local_ai_runtime()
    provider_calls: list[str] = []

    def provider_created(*_args):
        provider_calls.append("created")
        raise AssertionError("disabled AI constructed an inference provider")

    with tempfile.TemporaryDirectory(prefix="am-disabled-ai-smoke-") as temporary:
        credentials = MemoryCredentialStore()
        with patch.dict(os.environ, {"AM_CONFIGURATOR_DATA_DIR": temporary}):
            service = AICapabilityService(
                settings_loader=lambda: store.load_settings(
                    credential_store=credentials
                ),
                model_manager=LocalModelManager(Path(temporary) / "model"),
                runtime_resolver=lambda: runtime,
                credential_status_loader=lambda: store.credential_status(
                    credential_store=credentials
                ),
                credential_resolver=lambda: None,
                local_provider_factory=provider_created,
                api_provider_factory=provider_created,
            )
            try:
                status = service.status()
            finally:
                service.close()
    if status.get("enabled") or status.get("ready") or provider_calls:
        raise SystemExit("Desktop smoke test failed: disabled AI started a backend.")


def _run_api_recipe_smoke() -> None:
    """Exercise the production API recipe adapter through an offline transport."""
    from . import procedural
    from .recipe_provider import RecipeRequest, XaiRecipeProvider

    recipe = _smoke_recipe()
    calls: list[tuple[str, dict]] = []

    def fake_transport(url: str, payload: dict, api_key: str, deadline: float) -> dict:
        del deadline
        if api_key != "smoke-test-key":
            raise AssertionError("API smoke used an unexpected credential")
        calls.append((url, payload))
        return {
            "output": [{
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(recipe)}],
            }]
        }

    result = XaiRecipeProvider(
        "smoke-test-key", transport=fake_transport
    ).generate(
        RecipeRequest(
            prompt="offline API smoke test",
            width=18,
            height=7,
            frame_count=32,
            density_default="dense",
        ),
        time.monotonic() + 10,
        lambda: False,
    )
    frames = procedural.render_recipe(
        result.recipe, width=18, height=7, frame_count=32
    )
    mapped = procedural.map_frames_to_led_tracks(
        frames,
        duration_ms=34,
        product_id="AM21",
        targets=["keyframes", "spotlight_frames"],
    )
    if (
        result.backend != "api"
        or result.model_id != "grok-4.5"
        or len(calls) != 1
        or mapped.get("source_frames") != 32
    ):
        raise SystemExit("Desktop smoke test failed: fake API recipe generation was invalid.")


def _run_ollama_recipe_smoke() -> None:
    """Exercise the primary local recipe adapter through an offline client."""
    from . import procedural
    from .ollama_client import OllamaModel
    from .recipe_provider import OllamaRecipeProvider, RecipeRequest

    recipe = _smoke_recipe()

    class FakeOllamaClient:
        calls: list[dict] = []

        def chat(self, payload: dict, *, deadline: float, cancelled) -> dict:
            del deadline
            if cancelled():
                raise AssertionError("Ollama smoke was unexpectedly cancelled")
            self.calls.append(payload)
            return {"message": {"content": json.dumps(recipe)}}

    client = FakeOllamaClient()
    provider = OllamaRecipeProvider(
        OllamaModel(
            model_id="smoke:latest",
            digest="a" * 64,
            size_bytes=1,
            parameter_size=None,
            quantization=None,
        ),
        client=client,
    )
    result = provider.generate(
        RecipeRequest(
            prompt="offline Ollama smoke test",
            width=18,
            height=7,
            frame_count=32,
            density_default="dense",
        ),
        time.monotonic() + 10,
        lambda: False,
    )
    frames = procedural.render_recipe(
        result.recipe,
        width=18,
        height=7,
        frame_count=32,
    )
    mapped = procedural.map_frames_to_led_tracks(
        frames,
        duration_ms=34,
        product_id="AM21",
        targets=["keyframes", "spotlight_frames"],
    )
    if (
        result.backend != "local"
        or result.provider != "ollama"
        or result.model_id != "smoke:latest"
        or len(client.calls) != 1
        or client.calls[0].get("model") != "smoke:latest"
        or mapped.get("source_frames") != 32
        or mapped.get("duration_ms") != 34
    ):
        raise SystemExit(
            "Desktop smoke test failed: fake Ollama recipe generation was invalid."
        )


def _run_local_recipe_smoke() -> None:
    """Exercise the advanced direct-GGUF adapter through a fake runtime."""
    from . import procedural
    from .recipe_provider import (
        ManagedLocalRecipeProvider,
        RecipeRequest,
    )

    recipe = _smoke_recipe()
    runtime = object()

    class ModelManager:
        @staticmethod
        def resolve_selected():
            return type("SmokeModel", (), {"filename": "smoke.gguf"})()

    class FakeRuntime:
        calls: list[tuple] = []
        closed = False

        def complete(self, *args):
            self.calls.append(args)
            return {
                "choices": [{
                    "message": {"content": json.dumps(recipe)}
                }]
            }

        def close(self):
            self.closed = True

    fake_runtime = FakeRuntime()
    provider = ManagedLocalRecipeProvider(
        model_manager=ModelManager(),
        runtime_resolver=lambda: runtime,
        server=fake_runtime,
    )
    try:
        result = provider.generate(
            RecipeRequest(
                prompt="offline local smoke test",
                width=18,
                height=7,
                frame_count=32,
                density_default="dense",
            ),
            time.monotonic() + 10,
            lambda: False,
        )
        frames = procedural.render_recipe(
            result.recipe,
            width=18,
            height=7,
            frame_count=32,
        )
        mapped = procedural.map_frames_to_led_tracks(
            frames,
            duration_ms=34,
            product_id="AM21",
            targets=["keyframes", "spotlight_frames"],
        )
        if (
            result.model_id != "smoke.gguf"
            or len(fake_runtime.calls) != 1
            or mapped.get("source_frames") != 32
            or mapped.get("duration_ms") != 34
        ):
            raise SystemExit(
                "Desktop smoke test failed: fake local recipe generation was invalid."
            )
    finally:
        provider.close()
    if not fake_runtime.closed:
        raise SystemExit("Desktop smoke test failed: fake local runtime stayed open.")


def _run_ffmpeg_media_smoke() -> None:
    """Resolve the bundled runtime and process real MP4 frames fully offline."""
    from .ffmpeg_runtime import get_ffmpeg_runtime
    from .llm import MODEL_FRAME_CAPS
    from .media import process_video_frames

    frozen_root = getattr(sys, "_MEIPASS", None)
    fixture = (
        Path(frozen_root) / "smoke" / "tiny-motion.mp4"
        if frozen_root is not None
        else Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tiny-motion.mp4"
    )
    if not fixture.is_file():
        raise SystemExit("Desktop smoke test failed: bundled MP4 fixture is unavailable.")
    ffmpeg = get_ffmpeg_runtime()
    geometry = {"CB": (15, 6), "80": (18, 7), "ALICE": (16, 5)}
    loops = {"CB": "smooth", "80": "none", "ALICE": "ping_pong"}
    with tempfile.TemporaryDirectory(prefix="am-media-smoke-") as temporary:
        root = Path(temporary)
        work = root / ".work"
        work.mkdir()
        for family, frame_count in MODEL_FRAME_CAPS.items():
            width, height = geometry[family]
            result = process_video_frames(
                fixture.resolve(),
                root / f"frames-{family}",
                work,
                ffmpeg_path=ffmpeg,
                width=width,
                height=height,
                frame_count=frame_count,
                loop_mode=loops[family],
                deadline=time.monotonic() + 60,
            )
            if len(result.frame_paths) != frame_count or any(not path.is_file() for path in result.frame_paths):
                raise SystemExit("Desktop smoke test failed: bundled FFmpeg produced invalid frames.")
        if list(work.iterdir()):
            raise SystemExit("Desktop smoke test failed: FFmpeg left temporary media behind.")


def run_smoke_test() -> int:
    """Exercise the frozen entry point, bundled assets, and loopback server."""
    try:
        import webview  # noqa: F401 - verifies the desktop dependency is bundled
    except ModuleNotFoundError:
        raise SystemExit("Desktop smoke test failed: pywebview is unavailable.") from None

    backend = {
        "Darwin": "webview.platforms.cocoa",
        "Windows": "webview.platforms.winforms",
        "Linux": "webview.platforms.qt",
    }.get(platform.system())
    if backend and importlib.util.find_spec(backend) is None:
        raise SystemExit(f"Desktop smoke test failed: {backend} is unavailable.")

    tls_context = ssl.create_default_context()
    _assert_no_bundled_models()
    _run_disabled_ai_smoke()
    _run_api_recipe_smoke()
    _run_ollama_recipe_smoke()
    _run_local_recipe_smoke()
    _run_ffmpeg_media_smoke()
    if os.environ.get("AM_SMOKE_NET") == "1":
        request = Request("https://example.com/", method="HEAD")
        with urlopen(  # noqa: S310 - explicit opt-in packaged CA trust check
            request, timeout=5, context=tls_context
        ) as response:
            if response.status != 200:
                raise SystemExit(
                    "Desktop smoke test failed: opt-in TLS reach check failed."
                )

    server, url = create_server()
    server_thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name="am-configurator-smoke-api",
        daemon=True,
    )
    server_thread.start()
    try:
        with urlopen(url, timeout=5) as response:  # noqa: S310 - loopback URL we created
            page = response.read()
        if response.status != 200 or b"AM Configurator" not in page:
            raise SystemExit("Desktop smoke test failed: bundled UI did not load.")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    print(f"Desktop smoke test passed ({platform.system()}).")
    return 0


def run_desktop(config_paths: list[str] | None = None, *, debug: bool = False) -> int:
    """Run the loopback API inside a native webview window."""
    try:
        import webview
    except ModuleNotFoundError as exc:
        if exc.name == "webview":
            raise SystemExit(
                "AM Configurator desktop needs pywebview. Install with: "
                "pip install 'am-configurator[desktop]'"
            ) from None
        raise

    bridge = DesktopBridge()
    server, url = create_server(config_paths)
    server_state = getattr(server, "state", None)
    if server_state is not None:
        server_state.desktop_bridge = bridge
    server_thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.2},
        name="am-configurator-api",
        daemon=True,
    )
    server_thread.start()
    stopped = threading.Event()

    def stop_server() -> None:
        if stopped.is_set():
            return
        stopped.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        "AM Configurator",
        url,
        width=1440,
        height=920,
        min_size=(1000, 680),
        background_color="#0d0d0f",
        text_select=True,
        zoomable=True,
        js_api=bridge,
    )
    bridge._bind_window(window)
    window.events.closed += stop_server
    renderer = "qt" if platform.system() == "Linux" else None
    try:
        webview.start(gui=renderer, debug=debug, private_mode=True)
    finally:
        stop_server()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="am-configurator",
        description="Open AM Configurator as a native desktop application.",
    )
    parser.add_argument(
        "config",
        nargs="*",
        help="one or more official Angry Miao JSON exports to open and merge",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable the native webview's developer diagnostics",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.smoke_test:
        return run_smoke_test()
    return run_desktop(args.config, debug=args.debug)


if __name__ == "__main__":
    raise SystemExit(main())
