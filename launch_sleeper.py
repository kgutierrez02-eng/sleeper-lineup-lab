"""Source launcher using the existing interpreter; never installs or creates an environment."""

import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import threading
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser


def available_port() -> int:
    """Do not disturb another local app if the usual Streamlit port is busy."""
    for port in range(8501, 8522):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError("No free local port in 8501–8521. Close an old Sleeper window and retry.")


def open_when_ready(port: int, process: subprocess.Popen) -> None:
    """Open only after startup, bypassing corporate proxies for loopback health checks."""
    opener = build_opener(ProxyHandler({}))
    pause = threading.Event()
    for _ in range(120):
        if process.poll() is not None:
            return
        try:
            with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(f"http://127.0.0.1:{port}")
                    return
        except (OSError, URLError):
            pass
        pause.wait(0.25)


def main() -> int:
    root = Path(__file__).resolve().parent
    app = root / "sleeper_app"
    if sys.version_info < (3, 11):
        print("Sleeper Lineup Lab requires Python 3.11 or newer.")
        return 1
    missing = [name for name in ("streamlit", "requests", "scipy", "pandas") if importlib.util.find_spec(name) is None]
    if missing:
        print("Missing source dependencies: " + ", ".join(missing))
        print("Use the standalone Sleeper Lineup Lab.exe instead. No environment was created or changed.")
        return 1
    port = available_port()
    print(f"Opening Sleeper Lineup Lab at http://127.0.0.1:{port} — Ctrl+C closes the server.", flush=True)
    # Headless suppresses Streamlit's first-run email prompt. The launcher opens
    # the browser itself once the local server is ready.
    process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(app / "app.py"),
                                "--server.address=127.0.0.1", f"--server.port={port}", "--server.headless=true",
                                "--browser.gatherUsageStats=false", "--theme.base=dark", "--theme.primaryColor=#7598ff"], cwd=root)
    threading.Thread(target=open_when_ready, args=(port, process), daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=10)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Could not start Sleeper Lineup Lab: {exc}")
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(0)