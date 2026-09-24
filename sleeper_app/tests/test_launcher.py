from unittest.mock import MagicMock

import launch_sleeper


def test_launcher_skips_an_occupied_port(monkeypatch):
    sock = MagicMock()
    sock.__enter__.return_value = sock
    sock.bind.side_effect = [OSError("occupied"), None]
    monkeypatch.setattr(launch_sleeper.socket, "socket", lambda: sock)
    assert launch_sleeper.available_port() == 8502


def test_missing_dependencies_never_creates_environment(monkeypatch):
    monkeypatch.setattr(launch_sleeper.importlib.util, "find_spec", lambda name: None)
    run = MagicMock()
    call = MagicMock(return_value=0)
    monkeypatch.setattr(launch_sleeper.subprocess, "run", run)
    monkeypatch.setattr(launch_sleeper.subprocess, "call", call)
    assert launch_sleeper.main() == 1
    run.assert_not_called()
    call.assert_not_called()


def test_source_launcher_uses_existing_interpreter_only(monkeypatch, tmp_path):
    (tmp_path / "distribution.json").write_text("{}")
    monkeypatch.setattr(launch_sleeper, "__file__", str(tmp_path / "launch_sleeper.py"))
    monkeypatch.setattr(launch_sleeper.importlib.util, "find_spec", lambda name: object())
    run = MagicMock()
    process = MagicMock()
    process.wait.return_value = 0
    monkeypatch.setattr(launch_sleeper.subprocess, "run", run)
    monkeypatch.setattr(launch_sleeper.subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(launch_sleeper.threading, "Thread", MagicMock())
    monkeypatch.setattr(launch_sleeper, "available_port", lambda: 8502)
    assert launch_sleeper.main() == 0
    run.assert_not_called()
    assert launch_sleeper.subprocess.Popen.call_args.args[0][0] == launch_sleeper.sys.executable