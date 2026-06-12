import sys
from datetime import date
from pathlib import Path

import pytest

from domain.entities.device_info import DeviceEntity

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