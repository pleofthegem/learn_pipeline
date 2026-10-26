@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python gui/launch.py
) else (
    py -3 gui/launch.py
)
if errorlevel 1 pause
