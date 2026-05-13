import subprocess
import sys
import os
from pathlib import Path

import pytest

import resources_qrc  # noqa: F401

START_FILE = "./main.py"
TESTS_DIR = "."




def compile_resources() -> None:
    """Compile the Qt resource file (syncdose.qrc) into resources_qrc.py.

    Locates ``pyside6-rcc`` on the PATH and invokes it.  Exits the process
    with code 1 if the tool is not found.  Skips silently when the ``.qrc``
    source file does not exist.
    """
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


def run_tests() -> None:
    """Run the full pytest test suite from colocated ``__tests__/`` directories.

    Tests live next to their code: ``module/__tests__/test_*.py``.
    Exits the process with the pytest exit code if any test fails so that the
    application is never launched against a broken build.
    """
    print("🧪 Running tests...")
    exit_code = pytest.main([TESTS_DIR, "-v"])
    if exit_code != 0:
        print("❌ Tests failed. Aborting app launch.")
        sys.exit(exit_code)
    print("✅ All tests passed")


def run_app() -> None:
    """Launch the SyncDose application by executing ``main.py`` in a subprocess."""
    print("🚀 Launching Syncdose...")
    subprocess.run([sys.executable, f"{START_FILE}"])


if __name__ == "__main__":
    print("Using Python:", sys.executable)

    compile_resources()

    run_tests()

    run_app()
