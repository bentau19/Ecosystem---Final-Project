import os
import sys
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

from domain.entities.device_info import DeviceEntity

# ---------------------------------------------------------------------------
# Qt Platform Configuration
# ---------------------------------------------------------------------------
# For headless CI environments (GitHub Actions), ensure Qt uses offscreen rendering.
# This must be set BEFORE any Qt imports to take effect.
if "QT_QPA_PLATFORM" not in os.environ:
    # Try to detect if we have a display; if not, use offscreen
    has_display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not has_display and sys.platform != "win32":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # On Windows CI, offscreen is set explicitly in the workflow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Ensure a QApplication exists for all tests with proper cleanup.

    This fixture is auto-used by pytestqt; providing it explicitly ensures
    we control initialization, avoid race conditions during test startup,
    and properly tear down Qt after all tests complete.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    yield app  # Tests run here

    # Cleanup after all tests complete
    # Process any remaining events in the Qt event loop
    QCoreApplication.processEvents()
    # Quit the application to release resources and allow pytest to exit
    app.quit()


# ---------------------------------------------------------------------------
# Torch stub — must run BEFORE FileDetection is added to sys.path
# ---------------------------------------------------------------------------
# image_classifer.py has `import torch` at module level.  On the desktop CI
# runner torch is not installed (only the FileDetection job installs it).
# Installing stubs here prevents an ImportError during test collection for
# test_backup.py and test_phone_request.py (which both import BackupService →
# classifer → image_classifer → torch).
#
# The stub only activates when torch is absent; machines with a real torch
# installation are unaffected.
#
# nn.Module must be a *real* Python class — not a MagicMock — because
# `class ImageClassifier(nn.Module)` is evaluated at class-definition time and
# Python's metaclass machinery raises TypeError for non-type bases.


def _ensure_torch_stub() -> None:
    if "torch" in sys.modules:
        return  # real torch (or a prior stub) already present

    from unittest.mock import MagicMock

    class _FakeNNModule:
        """Minimal nn.Module stand-in so ImageClassifier can be defined."""

        def __init__(self, *args, **kwargs) -> None:
            super().__init__()

        def to(self, device: object) -> "_FakeNNModule":
            return self

        def parameters(self):  # noqa: ANN201
            return iter([])

        def train(self, mode: bool = True) -> "_FakeNNModule":
            return self

        def eval(self) -> "_FakeNNModule":
            return self

    nn_stub = MagicMock()
    nn_stub.Module = _FakeNNModule

    torch_stub = MagicMock()
    torch_stub.nn = nn_stub
    torch_stub.device = MagicMock(return_value="cpu")
    torch_stub.cuda.is_available = MagicMock(return_value=False)

    sys.modules["torch"] = torch_stub
    sys.modules["torch.nn"] = nn_stub
    sys.modules["torch.nn.functional"] = MagicMock()
    sys.modules["torch.utils"] = MagicMock()
    sys.modules["torch.utils.data"] = MagicMock()
    sys.modules["torchvision"] = MagicMock()
    sys.modules["torchvision.models"] = MagicMock()
    sys.modules["torchvision.transforms"] = MagicMock()


_ensure_torch_stub()

# ---------------------------------------------------------------------------
# FileDetection sys.path injection
# ---------------------------------------------------------------------------
# BackupService (and its tests) import from classifer, image_classifer, etc.
# which live in FileDetection/ at the project root — two levels above
# desktop/tests/.  Inserting it here applies to every test collected under
# desktop/tests/ regardless of which subdirectory they live in.
_FILE_DETECTION_DIR = Path(__file__).resolve().parents[2] / "FileDetection"
if str(_FILE_DETECTION_DIR) not in sys.path:
    sys.path.insert(0, str(_FILE_DETECTION_DIR))

@pytest.fixture()
def previous_device_online() -> DeviceEntity:
    return DeviceEntity(
        id="dev-001",
        name="Pixel 8 Pro",
        os="Android 14",
        tag="Work",
        last_connected=date(2024, 1, 15),
        battery_level=82,
        battery_charging=True,
        storage_used=64,
        storage_total=128,
        ip="192.168.1.10",
    )


@pytest.fixture()
def previous_device_recent() -> DeviceEntity:
    return DeviceEntity(
        id="dev-002",
        name="Galaxy S24",
        os="Android 14",
        tag="Home",
        last_connected=date(2024, 1, 14),
        battery_level=45,
        battery_charging=False,
        storage_used=110,
        storage_total=256,
        ip="192.168.1.11",
    )


@pytest.fixture()
def previous_device_idle() -> DeviceEntity:
    return DeviceEntity(
        id="dev-003",
        name="OnePlus 12",
        os="Android 13",
        tag="Travel",
        last_connected=date(2024, 1, 12),
        battery_level=60,
        battery_charging=False,
        storage_used=30,
        storage_total=128,
        ip="",
    )