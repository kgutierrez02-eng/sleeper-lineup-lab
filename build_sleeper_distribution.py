"""Create a clean, relocatable source distribution from an explicit allowlist.

Never copies caches, virtual environments, saved preferences, secrets or unrelated
workspace files. An existing destination is refused rather than overwritten.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
VERSION = "1.2.0"
FILES = [
    "Open Sleeper App.bat", "launch_sleeper.py", "sleeper_pull.py", "build_sleeper_distribution.py",
    "sleeper_app/__init__.py", "sleeper_app/app.py", "sleeper_app/analysis.py", "sleeper_app/data.py",
    "sleeper_app/presentation.py", "sleeper_app/trades.py", "sleeper_app/trade_ui.py",
    "sleeper_app/STANDALONE.md",
    "sleeper_app/requirements.txt", "sleeper_app/requirements-dev.txt", "sleeper_app/README.md",
    "sleeper_app/tests/test_analysis.py", "sleeper_app/tests/test_data.py", "sleeper_app/tests/test_app.py",
    "sleeper_app/tests/test_launcher.py", "sleeper_app/tests/test_trades.py", "sleeper_app/tests/test_distribution.py",
]


def build(destination: Path, source: Path = ROOT) -> Path:
    destination, source = destination.resolve(), source.resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}; choose a new empty destination.")
    # Validate inputs before making a half-populated folder.
    for name in FILES + ["sleeper_app/DISTRIBUTION.md"]:
        if not (source / name).is_file():
            raise FileNotFoundError(source / name)
    destination.mkdir(parents=True)
    for name in FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    shutil.copyfile(source / "sleeper_app/DISTRIBUTION.md", destination / "START_HERE.md")
    # Keep the template too, so the supplied builder remains usable by recipients.
    shutil.copyfile(source / "sleeper_app/DISTRIBUTION.md", destination / "sleeper_app/DISTRIBUTION.md")
    (destination / "distribution.json").write_text(json.dumps({"app": "Sleeper Lineup Lab", "version": VERSION,
        "creates_environment": False, "requires": "Source edition only: Windows, existing Python 3.11+ with dependencies, internet"}, indent=2), encoding="utf-8")
    paths = sorted(p for p in destination.rglob("*") if p.is_file())
    manifest = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (destination / "MANIFEST.sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "distribution" / "Sleeper Lineup Lab")
    args = parser.parse_args()
    output = build(args.output)
    print(f"Ready to zip: {output}")
    print("Zip this clean folder BEFORE launching it. Do not redistribute preferences, caches or .venv.")


if __name__ == "__main__":
    main()