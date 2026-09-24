import hashlib
import json
import pytest

from build_sleeper_distribution import FILES, ROOT, build


def test_distribution_is_clean_relocatable_and_complete(tmp_path):
    destination = build(tmp_path / "A folder with spaces")
    assert (destination / "Open Sleeper App.bat").exists()
    assert not (destination / "sleeper_app/preferences.json").exists()
    assert not (destination / "sleeper_app/.cache").exists()
    assert not (destination / "sleeper_app/.venv").exists()
    manifest = json.loads((destination / "MANIFEST.sha256.json").read_text())
    for name, checksum in manifest.items():
        assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == checksum
    for file in destination.rglob("*"):
        if file.is_file():
            content = file.read_text(encoding="utf-8")
            assert str(ROOT) not in content
    assert 'DEFAULTS = {"league": "", "team": "", "week": 3}' in (destination / "sleeper_app/data.py").read_text()
    with pytest.raises(FileExistsError):
        build(destination)


def test_allowlist_excludes_runtime_artifacts():
    assert all("preferences" not in p and ".cache" not in p and ".venv" not in p for p in FILES)


def test_missing_source_does_not_create_partial_release(tmp_path):
    with pytest.raises(FileNotFoundError):
        build(tmp_path / "destination", tmp_path / "no source")
    assert not (tmp_path / "destination").exists()