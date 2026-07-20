"""Native cross-platform window for the AM Configurator web interface."""
from __future__ import annotations

import argparse
import importlib.util
import platform
import threading
from collections.abc import Sequence
from urllib.request import urlopen

from .server import create_server


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

    server, url = create_server(config_paths)
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
