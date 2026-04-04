"""
build.py — Build OpenClay into a single executable via PyInstaller.
Usage: python build.py
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def build():
    # Ensure PyInstaller is installed
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "openclay",
        "--add-data", f"profiles{':' if sys.platform != 'win32' else ';'}profiles",
        "--add-data", f"config.json{':' if sys.platform != 'win32' else ';'}.",
        "--hidden-import", "gradio",
        "--hidden-import", "sqlite3",
        str(BASE_DIR / "app.py"),
    ]

    print("Building OpenClay executable...")
    subprocess.run(cmd, cwd=str(BASE_DIR), check=True)
    print(f"\nBuild complete. Executable at: {BASE_DIR / 'dist' / 'openclay'}")


if __name__ == "__main__":
    build()
