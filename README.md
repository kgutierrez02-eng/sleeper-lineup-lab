# Sleeper Lineup Lab

A local, read-only Sleeper fantasy-football lineup optimizer and trade lab —
runs entirely on your own machine, no installed server or account required.

- Full app docs, features and model explanation: [sleeper_app/README.md](sleeper_app/README.md)
- Standalone Windows build instructions: [sleeper_app/STANDALONE.md](sleeper_app/STANDALONE.md)
- Standalone macOS build instructions: [sleeper_app/STANDALONE_MAC.md](sleeper_app/STANDALONE_MAC.md)
- Building a clean distribution / desktop app yourself: [sleeper_app/DISTRIBUTION.md](sleeper_app/DISTRIBUTION.md)

## Get the app

Download the latest Windows or macOS build from this repo's **Releases** page
(built automatically by GitHub Actions from [`.github/workflows/build.yml`](.github/workflows/build.yml)).

## Run from source

Requires Python 3.11+.

```
pip install -r sleeper_app/requirements.txt
python launch_sleeper.py
```

On Windows, `Open Sleeper App.bat` does this for you.

## Build the desktop apps yourself

```
pip install -r sleeper_app/requirements-build.txt
python build_sleeper_exe.py --zip           # Windows, run on Windows
python build_sleeper_app_mac.py --zip       # macOS, run on macOS
```

## Tests

```
pip install -r sleeper_app/requirements-dev.txt
python -m pytest sleeper_app/tests
```
