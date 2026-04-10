import pytest

from entities.device_info import DeviceBatteryInfoEntity, DeviceStorageInfoEntity, DeviceGeneralInfoEntity
from entities.previous_device import PreviousDeviceEntity
from enums.device_status import DeviceStatus
from enums.device_type import DeviceType


@pytest.fixture()
def battery_entity() -> DeviceBatteryInfoEntity:
    return DeviceBatteryInfoEntity(
        title="Battery",
        icon_path="icons/battery.png",
        icon_background_color="#FF0000",
        type=DeviceType.BATTERY,
        battery_percentage=75,
        is_charging=False,
    )


@pytest.fixture()
def storage_entity() -> DeviceStorageInfoEntity:
    return DeviceStorageInfoEntity(
        title="Storage",
        icon_path="icons/storage.png",
        icon_background_color="#00FF00",
        type=DeviceType.STORAGE,
        used_storage=1024,
        total_storage=4096,
    )


@pytest.fixture()
def device_name_entity() -> DeviceGeneralInfoEntity:
    return DeviceGeneralInfoEntity(
        icon_path="icons/general.png",
        icon_background_color="#0000FF",
        title="General",
        type=DeviceType.DEVICE_NAME,
        description="my name is inigo"
    )


@pytest.fixture()
def previous_device_online() -> PreviousDeviceEntity:
    return PreviousDeviceEntity(
        id="dev-001",
        name="Pixel 8 Pro",
        os_label="Android 14",
        tag="Work",
        icon_color="#4CAF50",
        status=DeviceStatus.ONLINE,
        last_seen="now",
    )


@pytest.fixture()
def previous_device_recent() -> PreviousDeviceEntity:
    return PreviousDeviceEntity(
        id="dev-002",
        name="Galaxy S24",
        os_label="Android 14",
        tag="Home",
        icon_color="#2196F3",
        status=DeviceStatus.RECENT,
        last_seen="today",
    )


@pytest.fixture()
def previous_device_idle() -> PreviousDeviceEntity:
    return PreviousDeviceEntity(
        id="dev-003",
        name="OnePlus 12",
        os_label="Android 13",
        tag="Travel",
        icon_color="#9C27B0",
        status=DeviceStatus.IDLE,
        last_seen="3 days ago",
    )
