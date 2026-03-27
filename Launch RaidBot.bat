@echo off
cd /d "%~dp0"

where pythonw >nul 2>nul
if errorlevel 1 (
    echo pythonw was not found on PATH.
    echo Install Python and make sure pythonw is available, then try again.
    pause
    exit /b 1
)

start "" pythonw -m raidbot.desktop.app
exit /b 0
