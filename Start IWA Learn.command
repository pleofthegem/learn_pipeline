#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if command -v git >/dev/null 2>&1; then
    echo 'Updating IWA Learn...'
    if ! git pull --ff-only; then
        echo 'Warning: Update failed. Starting the installed version of IWA Learn.'
    fi
else
    echo 'Warning: Git was not found. Starting the installed version of IWA Learn.'
fi
if command -v python3 >/dev/null 2>&1; then
    python3 gui/launch.py
    result=$?
else
    echo 'Python 3.10 or later is required. Install Python, then open this launcher again.'
    result=1
fi
if [ "$result" -ne 0 ]; then
    printf '\nPress Enter to close…'
    read -r reply
fi
exit "$result"
