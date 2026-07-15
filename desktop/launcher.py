"""
CodeMonkeys desktop launcher.

Starts the existing FastAPI server on loopback only and opens a native
WebView2 window (pywebview). Data lives under %APPDATA%\\codemonkeys.
"""

from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


def _repo_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _ensure_tailwind_css(root: Path) -> None:
    """Vendored Tailwind CSS (static/forge/tailwind.css) is a gitignored build
    artifact — Docker/CI compile it via `npx tailwindcss`, but a plain
    `python -m desktop` from a fresh checkout never runs that step, so the UI
    loads with zero CSS (blank page). Build it here for source (non-frozen)
    runs; a packaged build is expected to already have it baked in by
    scripts/build-windows.ps1.
    """
    if getattr(sys, "frozen", False):
        return
    css = root / "static" / "forge" / "tailwind.css"
    if css.exists():
        return
    npx = shutil.which("npx")
    if not npx:
        print(
            "CodeMonkeys: static/forge/tailwind.css is missing and `npx` was not "
            "found, so the UI will render unstyled. Install Node.js, then run:\n"
            "  npx --yes tailwindcss@3.4.17 -i static/forge/tailwind.input.css "
            "-o static/forge/tailwind.css --minify",
            file=sys.stderr,
        )
        return
    print("CodeMonkeys: building vendored Tailwind CSS (first run)...")
    try:
        subprocess.run(
            [
                npx, "--yes", "tailwindcss@3.4.17",
                "-i", str(root / "static" / "forge" / "tailwind.input.css"),
                "-o", str(css),
                "--minify",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        print("CodeMonkeys: Tailwind CSS build complete.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        print(
            f"CodeMonkeys: Tailwind CSS build failed, UI will render unstyled:\n{detail}",
            file=sys.stderr,
        )


def _default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "codemonkeys" / "data"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "codemonkeys" / "data"


def _free_port(preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ready(url: str, timeout: float = 30.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    return False


def _configure_env(data_dir: Path, port: int) -> None:
    os.environ.setdefault("CM_DESKTOP", "1")
    os.environ.setdefault("DATA_DIR", str(data_dir))
    os.environ.setdefault("WORKSPACE_DIR", str(data_dir / "workspace"))
    os.environ.setdefault("HOST", "127.0.0.1")
    os.environ.setdefault("PORT", str(port))
    # Desktop is single-machine; skip Fly proxy header trust.
    os.environ.pop("FORWARDED_ALLOW_IPS", None)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "workspace").mkdir(parents=True, exist_ok=True)


def _start_server(host: str, port: int):
    import uvicorn

    # Import after env is set so server.py picks up DATA_DIR / CM_DESKTOP.
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from server import app  # noqa: WPS433 — intentional late import

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=os.environ.get("CM_LOG_LEVEL", "info"),
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="codemonkeys-uvicorn", daemon=True)
    thread.start()
    return server, thread


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host = "127.0.0.1"
    preferred = int(os.environ.get("PORT", "8765"))
    port = _free_port(preferred)
    data_dir = Path(os.environ.get("DATA_DIR") or _default_data_dir())
    _configure_env(data_dir, port)

    # Ensure repo root is importable when run as `python -m desktop`.
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    _ensure_tailwind_css(root)

    server, _thread = _start_server(host, port)
    url = f"http://{host}:{port}/"

    def _shutdown() -> None:
        server.should_exit = True

    atexit.register(_shutdown)

    if not _wait_ready(f"http://{host}:{port}/healthz"):
        print(
            f"CodeMonkeys server failed to become ready at {url}",
            file=sys.stderr,
        )
        _shutdown()
        return 1

    # Headless / CI: start server only.
    if "--no-window" in argv or os.environ.get("CM_DESKTOP_HEADLESS") == "1":
        print(f"CodeMonkeys desktop (headless) listening on {url}")
        print(f"Data dir: {data_dir}")
        try:
            while not server.should_exit:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            _shutdown()
        return 0

    try:
        import webview
    except ImportError:
        print(
            "pywebview is required for the desktop window.\n"
            "  pip install -r requirements-desktop.txt\n"
            f"Server is up at {url} — open it in a browser, or install pywebview.",
            file=sys.stderr,
        )
        # Keep server alive so browser fallback still works.
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            _shutdown()
        return 2

    window = webview.create_window(
        title="CodeMonkeys",
        url=url,
        width=1280,
        height=860,
        min_size=(900, 600),
        text_select=True,
    )

    def _on_closed() -> None:
        _shutdown()

    window.events.closed += _on_closed
    webview.start(debug=os.environ.get("CM_DESKTOP_DEBUG") == "1")
    _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
