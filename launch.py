"""Bootstrap a local environment once, then launch the desktop app."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        print("Setting up IWA Learn for first use…", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
    check = subprocess.run([str(python), "-c", "import tkinter"], capture_output=True)
    if check.returncode:
        print("Tkinter is missing. On Ubuntu/Debian, install python3-tk. On Windows/macOS, use a Python installation with Tcl/Tk support.")
        return 1
    check = subprocess.run([str(python), "-c", "import fitz, pandas, openpyxl, tkinterdnd2"], capture_output=True)
    if check.returncode:
        print("Installing dependencies. This first setup needs internet access…", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    return subprocess.call([str(python), str(ROOT / "gui.py")], cwd=ROOT)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Could not start IWA Learn: {exc}")
        sys.exit(1)
