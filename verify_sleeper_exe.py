"""Integration checks for a built EXE with no Python interpreter on its PATH.

The test controller uses the existing development interpreter. The app itself
must run from its bundled runtime, with an isolated profile and arbitrary cwd.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import tkinter as tk
from urllib.request import ProxyHandler, build_opener


def window_for_pid(pid):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    matches = []

    @callback_type
    def collect(hwnd, _):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == pid:
            text = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, text, 512)
            if "Sleeper Lineup Lab" in text.value:
                matches.append((hwnd, text.value))
        return True

    user32.EnumWindows(collect, 0)
    return matches


def verify(exe: Path):
    exe = exe.resolve()
    results = {}
    env = {k: v for k, v in os.environ.items() if k not in {
        "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"}}
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    with tempfile.TemporaryDirectory(prefix="Sleeper standalone test ") as tmp:
        profile = Path(tmp) / "profile"
        env["SLEEPER_APP_DATA_DIR"] = str(profile)
        report = Path(tmp) / "runtime-report.json"
        test = subprocess.run([str(exe), "--self-test", str(report)], cwd=tmp, env=env, timeout=150)
        results["runtime"] = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        assert test.returncode == 0 and results["runtime"].get("ok"), results["runtime"]

        process = subprocess.Popen([str(exe), "--no-browser"], cwd=tmp, env=env)
        # Tk's event loop schedules checks without blocking the UI or using shell
        # sleep commands. This checks the actual separate native EXE window.
        controller = tk.Tk()
        controller.withdraw()
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 90
        discovered = {}

        def check():
            try:
                windows = window_for_pid(process.pid)
                for path in profile.glob("*.log"):
                    text = path.read_text(encoding="utf-8", errors="replace")
                    match = re.search(r"http://127\.0\.0\.1:(\d+)", text)
                    if match:
                        discovered["url"] = match.group(0)
                if windows and discovered.get("url"):
                    with opener.open(discovered["url"] + "/_stcore/health", timeout=2) as response:
                        if response.status == 200:
                            discovered["title"] = windows[0][1]
                            discovered["hwnd"] = windows[0][0]
                            discovered["health"] = response.read().decode()
                            controller.quit()
                            return
                if process.poll() is not None or time.monotonic() > deadline:
                    controller.quit()
                    return
            except OSError:
                pass
            controller.after(300, check)

        controller.after(100, check)
        try:
            controller.mainloop()
            assert discovered.get("health") == "ok", {"discovered": discovered,
                "logs": {p.name: p.read_text(encoding="utf-8", errors="replace")[-3000:] for p in profile.glob("*.log")}}
            with opener.open(discovered["url"], timeout=5) as response:
                assert response.status == 200
                assert b"<html" in response.read().lower()
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.PostMessageW(discovered["hwnd"], 0x0010, 0, 0)  # WM_CLOSE
            assert process.wait(timeout=15) == 0
            try:
                opener.open(discovered["url"] + "/_stcore/health", timeout=2)
                raise AssertionError("Owned server was still running after the native window closed")
            except OSError:
                pass
            results["native_window"] = discovered["title"]
            results["server_health"] = "passed"
            results["server_cleanup"] = "passed"
            results["no_created_environment"] = not list(Path(tmp).rglob("pyvenv.cfg"))
            results["isolated_path"] = env["PATH"]
        finally:
            controller.destroy()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.exe), indent=2))