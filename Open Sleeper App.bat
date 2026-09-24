@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
if exist "distribution\Sleeper Lineup Lab Desktop\Sleeper Lineup Lab.exe" (
    start "" "distribution\Sleeper Lineup Lab Desktop\Sleeper Lineup Lab.exe"
    exit /b 0
)
if exist "sleeper_app\.venv\Scripts\python.exe" (
    "sleeper_app\.venv\Scripts\python.exe" launch_sleeper.py
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" launch_sleeper.py
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 launch_sleeper.py
    ) else (
        python launch_sleeper.py
    )
)
if errorlevel 1 (
    echo.
    echo Could not launch the app. Python 3.11+ and internet access are needed on first launch.
    pause
)
endlocal