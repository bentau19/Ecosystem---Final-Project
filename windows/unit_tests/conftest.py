import pytest

from entities.device_info import DeviceBatteryInfoEntity, DeviceStorageInfoEntity, DeviceGeneralInfoEntity
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
