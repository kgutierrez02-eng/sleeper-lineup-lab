# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
app_modules = ["__init__", "app", "analysis", "data", "presentation", "trades", "trade_ui", "smoke"]
datas = [(str(root / "sleeper_app" / f"{name}.py"), "sleeper_app") for name in app_modules]
datas += collect_data_files("streamlit")
datas += collect_data_files("altair")
datas += copy_metadata("streamlit")
datas += copy_metadata("altair")

a = Analysis(
    [str(root / "desktop_sleeper.py")],
    pathex=[str(root)],
    binaries=[], datas=datas,
    # Streamlit injects imports (e.g. magic_funcs) while compiling app scripts;
    # static dependency analysis cannot discover those generated imports.
    hiddenimports=collect_submodules("streamlit") + ["scipy.optimize",
                   "pandas", "numpy", "requests", "altair", "pyarrow",
                   "sleeper_app.analysis", "sleeper_app.data", "sleeper_app.presentation",
                   "sleeper_app.trades", "sleeper_app.trade_ui", "sleeper_app.smoke"],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["pytest", "IPython", "notebook", "matplotlib", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Sleeper Lineup Lab",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Sleeper Lineup Lab Desktop")