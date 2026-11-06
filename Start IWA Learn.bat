@echo off
cd /d "%~dp0"
if errorlevel 1 exit /b 1
where git >nul 2>nul
if errorlevel 1 (
    echo Warning: Git was not found. Starting the installed version of IWA Learn.
) else (
    echo Updating IWA Learn...
    git pull --ff-only
    if errorlevel 1 (
        echo Warning: Update failed. Starting the installed version of IWA Learn.
    )
)
where py >nul 2>nul
if errorlevel 1 (
    python gui/launch.py
) else (
    py -3 gui/launch.py
)
if errorlevel 1 pause
