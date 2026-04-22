import subprocess
import sys
import os
from pathlib import Path

import pytest

import resources_qrc  # noqa: F401

START_FILE = "main.py"


def compile_resources():
    print("🔄 Compiling resources...")

    # Auto-detect which pyrcc tool is available
    qrc_input: Path = Path(__file__).parent / "resources" / "syncdose.qrc"
    qrc_output: Path = Path(__file__).parent / "resources_qrc.py"

    print(f"Input: {qrc_input}")
    print(f"Output: {qrc_output}")

    if os.path.exists(qrc_input):
        try:
            subprocess.run(["pyside6-rcc", str(qrc_input), "-o", str(qrc_output)], check=True)
            print("✅ Resources compiled successfully")
        except FileNotFoundError:
            print("❌ pyside6-rcc not found. Install PySide6.")
            sys.exit(1)
    else:
        print("⚠️ No .qrc file found, skipping...")


def run_app():
    print("🚀 Launching Syncdose...")
    subprocess.run([sys.executable, f"{START_FILE}"])


if __name__ == "__main__":
    compile_resources()
    run_app()
