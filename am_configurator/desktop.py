"""Native cross-platform window for the AM Configurator web interface."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

from .server import create_server


_NATIVE_WEBVIEW_POLICIES = {
    "Darwin": ("webview.platforms.cocoa", None, "wkwebview"),
    "Windows": ("webview.platforms.winforms", None, "edgechromium"),
    "Linux": ("webview.platforms.qt", "qt", "qtwebengine"),
}
_NATIVE_POLICY_PHASES = ("seed", "verify")
_NATIVE_POLICY_MARKER = "am-native-private-probe"
_NATIVE_POLICY_VERIFY_KEYS = (
    "private_storage_clean",
    "token_history_clean",
    "token_session_present",
    "bridge_methods_hidden",
    "downloads_supported",
    "csp_enforced",
    "loopback_loaded",
    "settings_ollama_api_only",
)
_NATIVE_POLICY_TIMEOUT_SECONDS = 45


def _safe_native_failure_name(value: object, fallback: str) -> str:
    if (
        isinstance(value, str)
        and len(value) <= 200
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", value) is not None
    ):
        return value
    return fallback


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
    """Narrow native bridge for Library selection and reveal.

    Settings persistence intentionally remains behind the authenticated loopback
    HTTP API. Browser JavaScript reaches these methods only through those
    authenticated handlers; the pywebview ``js_api`` surface stays empty so
    private Python methods can never be injected into page scope.
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


def _native_webview_policy() -> tuple[str, str | None, str]:
    try:
        return _NATIVE_WEBVIEW_POLICIES[platform.system()]
    except KeyError:
        raise SystemExit(
            "Native webview policy smoke failed: unsupported platform."
        ) from None


def _native_policy_probe_script(phase: str) -> str:
    if phase not in _NATIVE_POLICY_PHASES:
        raise ValueError("Native policy phase is invalid.")
    if phase == "seed":
        return f"""
(() => {{
  const marker = {json.dumps(_NATIVE_POLICY_MARKER)};
  const report = value => history.replaceState(
    {{}}, "", `${{location.pathname}}#/__native_policy__/${{encodeURIComponent(JSON.stringify(value))}}`
  );
  localStorage.setItem(marker, "seeded");
  document.cookie = `${{marker}}=seeded; Path=/; SameSite=Strict`;
  report({{
    seeded: localStorage.getItem(marker) === "seeded" &&
      document.cookie.includes(`${{marker}}=seeded`)
  }});
}})()
""".strip()
    return f"""
(() => {{
  const marker = {json.dumps(_NATIVE_POLICY_MARKER)};
  const api = window.pywebview && window.pywebview.api
    ? window.pywebview.api : {{}};
  const report = value => history.replaceState(
    {{}}, "", `${{location.pathname}}#/__native_policy__/${{encodeURIComponent(JSON.stringify(value))}}`
  );
  const bridgeKeys = Object.keys(api).sort();
  const settings = document.querySelector("#settings-screen");
  const localPanel = document.querySelector("#settings-local-panel");
  const apiPanel = document.querySelector("#settings-api-panel");
  const settingsText = settings ? settings.textContent : "";
  const backendValues = settings
    ? Array.from(settings.querySelectorAll(
        'input[name="settings-ai-backend"]'
      )).map(input => input.value).sort()
    : [];
  const anchor = document.createElement("a");
  const ALLOW_DOWNLOADS = "download" in anchor &&
    typeof Blob === "function" &&
    typeof URL.createObjectURL === "function";

  let csp = "";
  try {{
    const request = new XMLHttpRequest();
    request.open("GET", "/", false);
    request.send(null);
    csp = request.getResponseHeader("Content-Security-Policy") || "";
  }} catch (_error) {{
    csp = "";
  }}
  window.__amNativeCspProbe = false;
  const inlineScript = document.createElement("script");
  inlineScript.textContent = "window.__amNativeCspProbe = true;";
  document.head.appendChild(inlineScript);
  inlineScript.remove();
  const inlineBlocked = window.__amNativeCspProbe === false;
  delete window.__amNativeCspProbe;

  report({{
    private_storage_clean: localStorage.getItem(marker) === null &&
      !document.cookie.includes(`${{marker}}=`),
    token_history_clean: location.search === "" &&
      !location.href.includes("token="),
    token_session_present: Boolean(
      sessionStorage.getItem("am-configurator-token")
    ),
    bridge_methods_hidden:
      bridgeKeys.length === 0 &&
      !bridgeKeys.includes("choose_library_folder") &&
      !bridgeKeys.includes("reveal_library_path") &&
      !bridgeKeys.includes("_bind_window") &&
      bridgeKeys.every(name => !name.startsWith("_")),
    downloads_supported: ALLOW_DOWNLOADS &&
      Boolean(document.querySelector("#save-button")),
    csp_enforced: csp.includes("default-src 'self'") &&
      csp.includes("script-src 'self'") && inlineBlocked,
    loopback_loaded: location.protocol === "http:" &&
      location.hostname === "127.0.0.1" &&
      document.title.includes("AM Configurator") && Boolean(settings),
    settings_ollama_api_only:
      backendValues.join(",") === "api,local" &&
      /Ollama/.test(settingsText) && /xAI/.test(settingsText) &&
      !/(GGUF|llama\\.cpp|direct model)/i.test(settingsText) &&
      Boolean(localPanel) && Boolean(apiPanel) &&
      !settings.querySelector('input[type="file"]'),
    csp
  }});
}})()
""".strip()


def _native_policy_descriptor_url(root: Path) -> str:
    descriptor = root / "probe.json"
    try:
        if descriptor.is_symlink() or descriptor.stat().st_size > 4096:
            raise ValueError
        value = json.loads(descriptor.read_text(encoding="utf-8"))
        url = value["url"]
        if not isinstance(url, str):
            raise ValueError
        parsed = urlsplit(url)
        token_values = parse_qs(parsed.query, strict_parsing=True).get("token", [])
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.path != "/"
            or len(token_values) != 1
            or not token_values[0]
        ):
            raise ValueError
        return url
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(
            "Native webview policy smoke failed: invalid private descriptor."
        ) from None


def _write_native_policy_result(root: Path, phase: str, result: dict[str, Any]) -> None:
    target = root / f"{phase}.json"
    temporary = root / f".{phase}-{os.getpid()}.tmp"
    temporary.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)


def _read_native_policy_result(root: Path, phase: str) -> dict[str, Any]:
    try:
        path = root / f"{phase}.json"
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) - {"ok", "reason", "renderer"}:
            raise ValueError
        return value
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "reason": "result_invalid"}


def _run_native_policy_probe(phase: str, raw_root: str | Path) -> int:
    """Drive one real renderer process for the frozen policy acceptance."""
    if phase not in _NATIVE_POLICY_PHASES:
        raise SystemExit("Native webview policy smoke failed: invalid probe phase.")
    root = Path(raw_root)
    url = _native_policy_descriptor_url(root)
    backend, renderer_choice, expected_renderer = _native_webview_policy()
    if importlib.util.find_spec(backend) is None:
        raise SystemExit(
            "Native webview policy smoke failed: platform backend is unavailable."
        )
    try:
        importlib.import_module(backend)
    except ImportError as exc:
        failure = _safe_native_failure_name(exc.name, "ImportError")
        _write_native_policy_result(
            root,
            phase,
            {"ok": False, "reason": f"backend_import_{failure}"},
        )
        raise SystemExit(
            "Native webview policy smoke failed: platform backend import failed "
            f"({failure})."
        ) from None
    except Exception as exc:
        failure = _safe_native_failure_name(type(exc).__name__, "Exception")
        _write_native_policy_result(
            root,
            phase,
            {"ok": False, "reason": f"backend_import_{failure}"},
        )
        raise SystemExit(
            "Native webview policy smoke failed: platform backend import failed "
            f"({failure})."
        ) from None
    try:
        import webview
    except ModuleNotFoundError:
        raise SystemExit(
            "Native webview policy smoke failed: pywebview is unavailable."
        ) from None

    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        "AM Configurator native policy probe",
        url,
        width=1000,
        height=680,
        min_size=(1000, 680),
        hidden=True,
    )
    if window is None:
        raise SystemExit(
            "Native webview policy smoke failed: renderer window was not created."
        )

    def inspect_policy() -> None:
        result: dict[str, Any] = {"ok": False, "reason": "probe_failed"}
        stage = "renderer"
        try:
            actual_renderer = getattr(webview, "renderer", None)
            stage = "load"
            if not window.events.loaded.wait(15):
                raise TimeoutError("Native renderer did not finish loading.")
            stage = "inject"
            window.run_js(_native_policy_probe_script(phase))
            stage = "report"
            deadline = time.monotonic() + 10
            current_url = ""
            raw = None
            while time.monotonic() < deadline:
                current_url = window.get_current_url() or ""
                fragment = urlsplit(current_url).fragment
                prefix = "/__native_policy__/"
                if fragment.startswith(prefix):
                    raw = unquote(fragment[len(prefix):])
                    break
                time.sleep(0.05)
            if raw is None:
                raise TimeoutError("Native renderer did not report its policy result.")
            stage = "decode"
            payload = json.loads(raw)
            current = urlsplit(current_url)
            required = ("seeded",) if phase == "seed" else _NATIVE_POLICY_VERIFY_KEYS
            stage = "validate"
            if actual_renderer != expected_renderer:
                result["reason"] = "renderer_mismatch"
            elif webview.settings.get("ALLOW_DOWNLOADS") is not True:
                result["reason"] = "downloads_disabled"
            elif not isinstance(payload, dict) or any(
                payload.get(name) is not True for name in required
            ):
                result["reason"] = "browser_policy_failed"
            elif current.query or "token=" in current_url:
                result["reason"] = "token_history_failed"
            else:
                result = {"ok": True, "renderer": actual_renderer}
        except Exception:
            result = {"ok": False, "reason": f"{stage}_failed"}
        finally:
            try:
                _write_native_policy_result(root, phase, result)
            finally:
                window.destroy()

    try:
        webview.start(
            inspect_policy,
            args=(),
            gui=renderer_choice,
            debug=False,
            private_mode=True,
        )
    except Exception as exc:
        if not (root / f"{phase}.json").exists():
            failure = _safe_native_failure_name(type(exc).__name__, "Exception")
            _write_native_policy_result(
                root,
                phase,
                {"ok": False, "reason": f"renderer_start_{failure}"},
            )
    result = _read_native_policy_result(root, phase)
    if result.get("ok") is not True:
        reason = result.get("reason", "unknown")
        raise SystemExit(f"Native webview policy smoke failed: {reason}.")
    return 0


def _native_policy_child_command(phase: str, root: Path) -> list[str]:
    prefix = [sys.executable]
    if not getattr(sys, "frozen", False):
        prefix.extend(("-m", "am_configurator.desktop"))
    return [*prefix, "--native-policy-probe", phase, "--native-policy-dir", str(root)]


class _OfflineOllamaInventory:
    def list_models(self, *, deadline: float) -> tuple:
        del deadline
        return ()


def run_native_policy_smoke() -> int:
    """Verify native renderer policy in two isolated frozen child processes."""
    from .credentials import MemoryCredentialStore

    _assert_ollama_api_only_bundle()
    prior_data_dir = os.environ.get("AM_CONFIGURATOR_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="am-native-policy-") as raw_root:
        root = Path(raw_root)
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = str(root / "data")
        server = None
        server_thread = None
        try:
            server, url = create_server(
                ollama_client=_OfflineOllamaInventory(),
                credential_store=MemoryCredentialStore(),
            )
            server_thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name="am-native-policy-api",
                daemon=True,
            )
            server_thread.start()
            descriptor = root / "probe.json"
            descriptor.write_text(json.dumps({"url": url}), encoding="utf-8")
            descriptor.chmod(0o600)
            for phase in _NATIVE_POLICY_PHASES:
                try:
                    completed = subprocess.run(
                        _native_policy_child_command(phase, root),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=_NATIVE_POLICY_TIMEOUT_SECONDS,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    raise SystemExit(
                        f"Native webview policy smoke failed: {phase} process failed."
                    ) from None
                result = _read_native_policy_result(root, phase)
                if completed.returncode != 0 or result.get("ok") is not True:
                    reason = result.get("reason", "process_failed")
                    raise SystemExit(
                        f"Native webview policy smoke failed: {phase} {reason}."
                    )
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if server_thread is not None:
                server_thread.join(timeout=2)
            if prior_data_dir is None:
                os.environ.pop("AM_CONFIGURATOR_DATA_DIR", None)
            else:
                os.environ["AM_CONFIGURATOR_DATA_DIR"] = prior_data_dir

    print(
        f"Native webview policy smoke passed ({platform.system()}, "
        f"{_native_webview_policy()[2]})."
    )
    return 0


def _assert_ollama_api_only_bundle() -> None:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root is None:
        return
    root = Path(frozen_root)
    forbidden_stems = {"llama-cli", "llama-server"}
    forbidden_names = {"llama-runtime.json", "local-model.json"}
    for path in root.rglob("*"):
        name = path.name.lower()
        if (
            path.suffix.lower() == ".gguf"
            or path.stem.lower() in forbidden_stems
            or name in forbidden_names
        ):
            raise SystemExit(
                "Desktop smoke test failed: application bundle contains a direct model runtime."
            )


def _run_disabled_ai_smoke() -> None:
    """Verify disabled startup does not construct an inference provider."""
    from unittest.mock import patch

    from . import store
    from .ai_capability import AICapabilityService
    from .credentials import MemoryCredentialStore
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
                credential_status_loader=lambda: store.credential_status(
                    credential_store=credentials
                ),
                credential_resolver=lambda: None,
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


def _run_ffmpeg_media_smoke() -> None:
    """Resolve the bundled runtime and process real MP4 frames fully offline."""
    from .device_mapping import MODEL_FRAME_CAPS
    from .ffmpeg_runtime import get_ffmpeg_runtime
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
    from .credentials import MemoryCredentialStore

    try:
        import webview  # noqa: F401 - verifies the desktop dependency is bundled
    except ModuleNotFoundError:
        raise SystemExit("Desktop smoke test failed: pywebview is unavailable.") from None

    backend, _renderer_choice, _expected_renderer = _native_webview_policy()
    if importlib.util.find_spec(backend) is None:
        raise SystemExit(f"Desktop smoke test failed: {backend} is unavailable.")

    tls_context = ssl.create_default_context()
    _assert_ollama_api_only_bundle()
    _run_disabled_ai_smoke()
    _run_api_recipe_smoke()
    _run_ollama_recipe_smoke()
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

    prior_data_dir = os.environ.get("AM_CONFIGURATOR_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="am-loopback-smoke-") as temporary:
        os.environ["AM_CONFIGURATOR_DATA_DIR"] = temporary
        server = None
        server_thread = None
        server_started = False
        try:
            server, url = create_server(
                credential_store=MemoryCredentialStore(),
                ollama_client=_OfflineOllamaInventory(),
            )
            server_thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name="am-configurator-smoke-api",
                daemon=True,
            )
            server_thread.start()
            server_started = True
            with urlopen(url, timeout=5) as response:  # noqa: S310 - loopback URL we created
                page = response.read()
            if response.status != 200 or b"AM Configurator" not in page:
                raise SystemExit("Desktop smoke test failed: bundled UI did not load.")
        finally:
            if server is not None:
                if server_started:
                    server.shutdown()
                server.server_close()
            if server_thread is not None:
                server_thread.join(timeout=2)
            if prior_data_dir is None:
                os.environ.pop("AM_CONFIGURATOR_DATA_DIR", None)
            else:
                os.environ["AM_CONFIGURATOR_DATA_DIR"] = prior_data_dir

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
    )
    bridge._bind_window(window)
    window.events.closed += stop_server
    _backend, renderer, _expected_renderer = _native_webview_policy()
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
    parser.add_argument(
        "--native-policy-smoke",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--native-policy-probe",
        choices=_NATIVE_POLICY_PHASES,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--native-policy-dir",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    if args.smoke_test:
        return run_smoke_test()
    if args.native_policy_smoke:
        if args.native_policy_probe or args.native_policy_dir:
            parser.error("native policy modes cannot be combined")
        return run_native_policy_smoke()
    if args.native_policy_probe:
        if not args.native_policy_dir:
            parser.error("--native-policy-dir is required for a native policy probe")
        return _run_native_policy_probe(
            args.native_policy_probe,
            args.native_policy_dir,
        )
    if args.native_policy_dir:
        parser.error("--native-policy-dir requires --native-policy-probe")
    return run_desktop(args.config, debug=args.debug)


if __name__ == "__main__":
    raise SystemExit(main())
