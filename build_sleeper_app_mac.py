"""Build a portable macOS .app bundle using ONLY the current Python environment."""

import argparse
import hashlib
from importlib import metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
APP_NAME = "Sleeper Lineup Lab.app"
VERSION = "1.2.0"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(output: Path, archive: bool = False) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("Build the macOS app on macOS.")
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError("PyInstaller is missing from the CURRENT interpreter. No environment will be created.")
    destination = output.resolve() / APP_NAME
    if destination.exists():
        shutil.rmtree(destination)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(output.resolve()), "--workpath", str(ROOT / ".build-sleeper-mac"),
                    str(ROOT / "SleeperDesktop-mac.spec")], cwd=ROOT, check=True)
    resources = destination / "Contents" / "Resources"
    license_dir = resources / "THIRD_PARTY_LICENSES"
    license_dir.mkdir(parents=True, exist_ok=True)
    versions = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or "unknown"
        versions[name] = dist.version
        for file in dist.files or []:
            if any(part.casefold().startswith(("license", "copying", "notice")) for part in file.parts):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = license_dir / name / str(file).replace("/", "__")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    (resources / "BUILD_INFO.json").write_text(json.dumps({"app_version": VERSION, "platform": "macOS",
        "python_bundled": sys.version.split()[0], "requires_installed_python": False,
        "dependencies": versions}, indent=2), encoding="utf-8")
    shutil.copyfile(ROOT / "sleeper_app/STANDALONE_MAC.md", output.resolve() / "START_HERE.md")
    manifest = {p.relative_to(destination).as_posix(): file_hash(p)
                for p in sorted(destination.rglob("*")) if p.is_file()}
    (output.resolve() / "MANIFEST.sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Standalone app ready: {destination}", flush=True)
    if archive:
        zip_path = shutil.make_archive(str(output.resolve() / "Sleeper Lineup Lab macOS"), "zip",
                                        root_dir=output.resolve(), base_dir=".")
        print(f"Shareable ZIP: {zip_path}", flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "distribution-mac")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args()
    args.output.resolve().mkdir(parents=True, exist_ok=True)
    build(args.output, args.zip)
