import pytest

from entities.device_info import (
    DeviceNameEntity,
    DeviceStorageEntity,
    DeviceBatteryEntity,
)
from entities.connected_device import PreviousDeviceEntity
from enums.device_status import DeviceStatus
from enums.device_type import DeviceType


@pytest.fixture()
def battery_entity() -> DeviceBatteryEntity:
    return DeviceBatteryEntity(
        title="Battery",
        icon_path="icons/battery.png",
        type=DeviceType.BATTERY,
        level=75,
        is_charging=False,
    )


@pytest.fixture()
def storage_entity() -> DeviceStorageEntity:
    return DeviceStorageEntity(
        title="Storage",
        icon_path="icons/storage.png",
        type=DeviceType.STORAGE,
        used=1024,
        total=4096,
    )


@pytest.fixture()
def device_name_entity() -> DeviceNameEntity:
    return DeviceNameEntity(
        title="Name",
        icon_path="icons/general.png",
        type=DeviceType.NAME,
        name="my name is inigo",
    )


@pytest.fixture()
def previous_device_online() -> PreviousDeviceEntity:
    return PreviousDeviceEntity(
        id="dev-001",
        name="Pixel 8 Pro",
        os_label="Android 14",
        tag="Work",
        icon_path=":/icons/smartphone.svg",
        status=DeviceStatus.ONLINE,
        last_seen="now",
        ip="192.168.1.10",
    )


@pytest.fixture()
def previous_device_recent() -> PreviousDeviceEntity:
    return PreviousDeviceEntity(
        id="dev-002",
        name="Galaxy S24",
        os_label="Android 14",
        tag="Home",
        icon_path=":/icons/smartphone.svg",
        status=DeviceStatus.RECENT,
        last_seen="today",
        ip="192.168.1.11",
    )


@pytest.fixture()
def previous_device_idle() -> PreviousDeviceEntity:
    return PreviousDeviceEntity(
        id="dev-003",
        name="OnePlus 12",
        os_label="Android 13",
        tag="Travel",
        icon_path=":/icons/smartphone.svg",
        status=DeviceStatus.IDLE,
        last_seen="3 days ago",
        ip="",
    )
