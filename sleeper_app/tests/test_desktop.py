import importlib
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

import desktop_sleeper as desktop
from sleeper_app import data
import build_sleeper_exe as builder
import pytest


def test_frozen_child_relaunches_exe_not_python(monkeypatch):
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop.sys, "executable", "C:/Portable/Sleeper Lineup Lab.exe")
    command = desktop.server_command(32123)
    assert command[:4] == ["C:/Portable/Sleeper Lineup Lab.exe", "--serve", "--port", "32123"]
    assert "-m" not in command and "python" not in " ".join(command).lower()


@pytest.mark.skipif(sys.platform != "win32", reason="Exercises the Windows LOCALAPPDATA convention")
def test_desktop_data_is_not_stored_in_bundle(monkeypatch, tmp_path):
    monkeypatch.delenv("SLEEPER_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop.user_data_dir() == tmp_path / "SleeperLineupLab"


def test_preferences_and_cache_honor_user_storage(monkeypatch, tmp_path):
    with monkeypatch.context() as m:
        m.setenv("SLEEPER_APP_DATA_DIR", str(tmp_path / "profile"))
        importlib.reload(data)
        data.save_preferences("123", "example", 3)
        assert data.load_preferences()["league"] == "123"
        assert data.SleeperClient().cache_dir == tmp_path / "profile/.cache"
        assert json.loads((tmp_path / "profile/preferences.json").read_text())["team"] == "example"
    importlib.reload(data)


def test_port_is_loopback_available():
    assert 0 < desktop.find_port() < 65536


def test_close_only_stops_owned_server():
    window = object.__new__(desktop.DesktopWindow)
    window.process = MagicMock()
    window.process.poll.return_value = None
    window.log = MagicMock()
    log = window.log
    window.stop()
    window.process.terminate.assert_called_once()
    window.process.wait.assert_called_once()
    log.close.assert_called_once()
    assert window.log is None


def test_frozen_assets_resolve_from_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(desktop.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert desktop.bundle_root() == tmp_path


def test_licenses_include_archived_pure_python_packages(monkeypatch, tmp_path):
    toc = tmp_path / "PYZ-00.toc"
    toc.write_text(repr(("archive.pyz", [("requests.api", "requests/api.py", "PYMODULE"),
                                          ("PIL.Image", "PIL/Image.py", "PYMODULE")])))
    monkeypatch.setattr(builder.metadata, "packages_distributions",
                        lambda: {"requests": ["requests"], "PIL": ["Pillow"]})
    assert builder.bundled_distributions(toc) == {"requests", "pillow"}


def test_replacement_rejects_unknown_files(monkeypatch, tmp_path):
    monkeypatch.setattr(builder.sys, "platform", "win32")
    monkeypatch.setattr(builder.importlib.util, "find_spec", lambda _: object())
    folder = tmp_path / builder.NAME
    folder.mkdir()
    (folder / "MANIFEST.sha256.json").write_text("{}")
    personal = folder / "my-notes.txt"
    personal.write_text("keep me")
    with pytest.raises(RuntimeError, match="unexpected/missing"):
        builder.build(tmp_path, replace=True)
    assert personal.read_text() == "keep me"


def test_replacement_rejects_modified_files(monkeypatch, tmp_path):
    monkeypatch.setattr(builder.sys, "platform", "win32")
    monkeypatch.setattr(builder.importlib.util, "find_spec", lambda _: object())
    folder = tmp_path / builder.NAME
    folder.mkdir()
    (folder / "MANIFEST.sha256.json").write_text(json.dumps({"app.exe": "original-checksum"}))
    (folder / "app.exe").write_text("changed")
    with pytest.raises(RuntimeError, match="modified"):
        builder.build(tmp_path, replace=True)
    assert (folder / "app.exe").exists()