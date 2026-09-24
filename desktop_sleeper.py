"""Native desktop launcher for the bundled local dashboard. Never invokes pip/venv."""

import argparse
import ctypes
import json
import multiprocessing
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import traceback
from urllib.request import ProxyHandler, build_opener
import webbrowser


VERSION = "1.2.0"


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def user_data_dir() -> Path:
    override = os.environ.get("SLEEPER_APP_DATA_DIR")
    if override:
        return Path(override).resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SleeperLineupLab"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "SleeperLineupLab"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "SleeperLineupLab"


def server_command(port: int) -> list[str]:
    args = ["--serve", "--port", str(port), "--parent-pid", str(os.getpid())]
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def open_in_file_manager(path: Path) -> None:
    """Reveal the app-data folder using each OS's native file manager."""
    if os.name == "nt":
        os.startfile(str(path))  # Windows-only API, guarded by os.name
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def find_port() -> int:
    # Ask the OS for an unused loopback port; avoids common local application conflicts.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def watch_parent(pid: int) -> None:
    """Exit our server if the launcher crashes or is force-closed (Windows only)."""
    if not pid or os.name != "nt":
        return
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    if not handle:
        os._exit(0)

    def wait():
        result = kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        kernel.CloseHandle(handle)
        if result == 0:
            os._exit(0)

    threading.Thread(target=wait, daemon=True).start()


def serve(port: int, parent_pid: int = 0) -> int:
    watch_parent(parent_pid)
    from streamlit.web import cli

    # No interpreter subprocess here: the EXE imports its BUNDLED Streamlit.
    return cli.main(args=["run", str(bundle_root() / "sleeper_app" / "app.py"),
        "--server.address=127.0.0.1", f"--server.port={port}", "--server.headless=true",
        "--server.fileWatcherType=none", "--server.runOnSave=false",
        "--browser.gatherUsageStats=false", "--global.developmentMode=false",
        "--theme.base=dark", "--theme.primaryColor=#7598ff"], standalone_mode=False) or 0


class DesktopWindow:
    def __init__(self, *, auto_open=True):
        import tkinter as tk
        from tkinter import ttk

        self.root = tk.Tk()
        self.root.title(f"Sleeper Lineup Lab {VERSION}")
        self.root.geometry("640x400")
        self.root.minsize(600, 380)
        self.root.configure(bg="#0b1120")
        self.process = None
        self.log = None
        self.port = None
        self.ready = False
        self.closed = False
        self.auto_open = auto_open
        self.events = queue.Queue()
        self.data = user_data_dir()
        self.data.mkdir(parents=True, exist_ok=True)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Lab.TButton", font=("Segoe UI", 10), padding=(14, 10), background="#244475", foreground="white")
        tk.Label(self.root, text="SLEEPER  /  LINEUP LAB", font=("Segoe UI", 11, "bold"), fg="#75e7ce", bg="#0b1120").pack(anchor="w", padx=32, pady=(28, 10))
        tk.Label(self.root, text="Your team. Your trade lab.", font=("Segoe UI", 24, "bold"), fg="white", bg="#0b1120").pack(anchor="w", padx=32)
        tk.Label(self.root, text="Standalone app • No Python installation • Read-only Sleeper data",
                 font=("Segoe UI", 10), fg="#bdcce4", bg="#0b1120").pack(anchor="w", padx=32, pady=(8, 18))
        self.status = tk.StringVar(value="Starting your local dashboard…")
        self.address = tk.StringVar(value="The dashboard opens in your default browser when ready.")
        tk.Label(self.root, textvariable=self.status, wraplength=565, justify="left", font=("Segoe UI", 11), fg="white", bg="#0b1120").pack(anchor="w", padx=32)
        tk.Label(self.root, textvariable=self.address, font=("Segoe UI", 10), fg="#99b5df", bg="#0b1120").pack(anchor="w", padx=32, pady=(8, 18))
        row = tk.Frame(self.root, bg="#0b1120")
        row.pack(anchor="w", padx=32)
        self.open_button = ttk.Button(row, text="Open dashboard", style="Lab.TButton", command=self.open_dashboard, state="disabled")
        self.open_button.pack(side="left", padx=(0, 10))
        self.restart_button = ttk.Button(row, text="Restart", style="Lab.TButton", command=self.restart, state="disabled")
        self.restart_button.pack(side="left", padx=(0, 10))
        ttk.Button(row, text="Open logs & settings", style="Lab.TButton", command=lambda: open_in_file_manager(self.data)).pack(side="left")
        tk.Label(self.root, text="Keep this window open while using the dashboard.\nClosing it stops the local app. Internet is needed for fresh league data.",
                 justify="left", font=("Segoe UI", 9), fg="#9dacc4", bg="#0b1120").pack(anchor="w", padx=32, pady=(22, 0))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.start)
        self.root.after(200, self.poll)

    def start(self):
        try:
            self.ready = False
            self.status.set("Starting your local dashboard…")
            self.open_button.configure(state="disabled")
            self.restart_button.configure(state="disabled")
            self.port = find_port()
            # One log per session prevents two app instances contending for a file.
            self.log = (self.data / f"server-{os.getpid()}.log").open("a", encoding="utf-8")
            env = {**os.environ, "SLEEPER_APP_DATA_DIR": str(self.data), "PYTHONUTF8": "1"}
            self.process = subprocess.Popen(server_command(self.port), cwd=self.data, env=env,
                stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            threading.Thread(target=self.wait_ready, args=(self.process, self.port), daemon=True).start()
        except Exception as exc:
            self.status.set(f"Could not start: {exc}")
            self.restart_button.configure(state="normal")

    def wait_ready(self, process, port):
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 90
        tick = threading.Event()
        while not self.closed and time.monotonic() < deadline and process.poll() is None:
            try:
                with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        self.events.put((process, True))
                        return
            except OSError:
                pass
            tick.wait(0.3)
        self.events.put((process, False))

    def poll(self):
        if self.closed:
            return
        while not self.events.empty():
            process, ready = self.events.get_nowait()
            if process is not self.process:
                continue
            self.ready = ready
            self.restart_button.configure(state="normal")
            if ready:
                self.status.set("Ready — your dashboard is running on this computer only.")
                self.address.set(f"http://127.0.0.1:{self.port}")
                self.open_button.configure(state="normal")
                if self.auto_open:
                    self.open_dashboard()
            else:
                self.status.set("Startup failed or timed out. Open logs & settings for details, then try Restart.")
        if self.ready and self.process and self.process.poll() is not None:
            self.ready = False
            self.status.set("The local server stopped. Select Restart or check its log.")
            self.open_button.configure(state="disabled")
        self.root.after(300, self.poll)

    def open_dashboard(self):
        if self.ready:
            # PyInstaller adjusts DLL search paths; restore the OS default for
            # launching an external browser, then restore our bundled DLL path.
            if os.name == "nt" and getattr(sys, "frozen", False):
                from ctypes import wintypes

                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
                kernel.SetDllDirectoryW(None)
                try:
                    webbrowser.open(f"http://127.0.0.1:{self.port}")
                finally:
                    kernel.SetDllDirectoryW(str(bundle_root()))
            else:
                webbrowser.open(f"http://127.0.0.1:{self.port}")

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()
            self.log = None

    def restart(self):
        self.stop()
        self.start()

    def close(self):
        self.closed = True
        self.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def self_test(destination: Path) -> int:
    """Offline validation of the frozen runtime, native GUI, and full app render."""
    report = {"frozen": bool(getattr(sys, "frozen", False)), "executable": sys.executable, "version": VERSION}
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        report["tk"] = root.tk.call("info", "patchlevel")
        root.destroy()
        from sleeper_app.smoke import run_smoke_tests
        report.update(run_smoke_tests(bundle_root()))
        report["ok"] = True
    except BaseException:
        report["ok"] = False
        report["error"] = traceback.format_exc()
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


def main():
    multiprocessing.freeze_support()
    # Windowed executables have no Python stdout/stderr; libraries still expect
    # writable streams. Logs remain outside the distribution beside user settings.
    if sys.stdout is None or sys.stderr is None:
        directory = user_data_dir()
        directory.mkdir(parents=True, exist_ok=True)
        stream = (directory / f"runtime-{os.getpid()}.log").open("a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
    parser = argparse.ArgumentParser(description="Sleeper Lineup Lab desktop app")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=8501, help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--self-test", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return self_test(args.self_test)
    if args.serve:
        return serve(args.port, args.parent_pid)
    DesktopWindow(auto_open=not args.no_browser).run()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        data = user_data_dir()
        data.mkdir(parents=True, exist_ok=True)
        (data / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        if "--serve" not in sys.argv:
            from tkinter import messagebox
            messagebox.showerror("Sleeper Lineup Lab", f"Could not start. Details saved in:\n{data / 'startup-error.log'}")
        raise SystemExit(1)