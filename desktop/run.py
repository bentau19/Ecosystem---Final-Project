import subprocess
import sys
import os
from pathlib import Path

import pytest

import resources_qrc  # noqa: F401

START_FILE = "./main.py"
TESTS_DIR = "./unit_tests"


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


def run_tests():
    print("🧪 Running tests...")
    exit_code = pytest.main([TESTS_DIR, "-v"])
    if exit_code != 0:
        print("❌ Tests failed. Aborting app launch.")
        sys.exit(exit_code)
    print("✅ All tests passed")


def run_app():
    print("🚀 Launching Syncdose...")
    subprocess.run([sys.executable, f"{START_FILE}"])


if __name__ == "__main__":
    print("Using Python:", sys.executable)


    compile_resources()

    # run_tests()

    run_app()
