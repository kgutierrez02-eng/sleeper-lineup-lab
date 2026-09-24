"""Build a portable Windows EXE using ONLY the current Python environment."""

import argparse
import ast
import hashlib
from importlib import metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
NAME = "Sleeper Lineup Lab Desktop"


def bundled_distributions(toc_path):
    """Include pure-Python packages stored inside PYZ, not just loose folders."""
    _, modules = ast.literal_eval(toc_path.read_text(encoding="utf-8"))
    mapping = metadata.packages_distributions()
    return {name.casefold().replace("-", "_")
            for module, _source, _kind in modules
            for name in mapping.get(module.partition(".")[0], [])}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(output: Path, archive=False, replace=False):
    if sys.platform != "win32":
        raise RuntimeError("Build the Windows app on Windows.")
    if importlib.util.find_spec("PyInstaller") is None:
        raise RuntimeError("PyInstaller is missing from the CURRENT interpreter. No environment will be created.")
    destination = output.resolve() / NAME
    if destination.exists():
        if not replace:
            raise FileExistsError(f"Refusing to overwrite {destination}. Choose a new --output folder or --replace for an unchanged generated build.")
        manifest_path = destination / "MANIFEST.sha256.json"
        if not manifest_path.is_file():
            raise RuntimeError("Cannot replace a folder without a generated checksum manifest.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()}
        if actual != set(manifest) | {"MANIFEST.sha256.json"}:
            raise RuntimeError("Build folder contains unexpected/missing files; refusing to replace it.")
        if not all(file_hash(destination / name) == checksum for name, checksum in manifest.items()):
            raise RuntimeError("Build files have been modified; refusing to replace them.")
        shutil.rmtree(destination)
    # Build outside the release; package contents are collected from a strict spec.
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(output.resolve()), "--workpath", str(ROOT / ".build-sleeper"),
                    str(ROOT / "SleeperDesktop.spec")], cwd=ROOT, check=True)
    shutil.copyfile(ROOT / "sleeper_app/STANDALONE.md", destination / "START_HERE.md")
    license_dir = destination / "THIRD_PARTY_LICENSES"
    license_dir.mkdir()
    versions = {}
    collected = bundled_distributions(ROOT / ".build-sleeper/SleeperDesktop/PYZ-00.toc")
    entries = list((destination / "_internal").iterdir())
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or "unknown"
        # Only distributions actually collected by this spec/hooks.
        stems = {name.casefold().replace("-", "_"), name.casefold().replace("-", "")}
        if name.casefold().replace("-", "_") not in collected and not any(
                any(p.name.casefold().replace("-", "_").startswith(s) for s in stems) for p in entries):
            continue
        versions[name] = dist.version
        for file in dist.files or []:
            if any(part.casefold().startswith(("license", "copying", "notice")) for part in file.parts):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = license_dir / name / str(file).replace("/", "__").replace("\\", "__")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    # CPython's license is normally included by PyInstaller; include explicitly
    # when present in the build interpreter's base installation as well.
    for filename in ["LICENSE.txt", "LICENSE"]:
        source = Path(sys.base_prefix) / filename
        if source.is_file():
            shutil.copyfile(source, license_dir / "Python-LICENSE.txt")
            break
    (destination / "BUILD_INFO.json").write_text(json.dumps({"app_version": "1.2.0", "platform": "Windows x64",
        "python_bundled": sys.version.split()[0], "requires_installed_python": False,
        "dependencies": versions}, indent=2), encoding="utf-8")
    manifest = {p.relative_to(destination).as_posix(): file_hash(p) for p in sorted(destination.rglob("*")) if p.is_file()}
    (destination / "MANIFEST.sha256.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Standalone app ready: {destination}", flush=True)
    if archive:
        zip_path = shutil.make_archive(str(destination), "zip", root_dir=destination.parent, base_dir=destination.name)
        print(f"Shareable ZIP: {zip_path}", flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "distribution")
    parser.add_argument("--zip", action="store_true")
    parser.add_argument("--replace", action="store_true", help="Replace only a previously generated, manifest-verified unchanged build")
    args = parser.parse_args()
    build(args.output, args.zip, args.replace)