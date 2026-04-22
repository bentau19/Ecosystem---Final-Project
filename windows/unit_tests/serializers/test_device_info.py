from dataclasses import asdict

import pytest

from entities.device_info import (
    DeviceType,
    DeviceStorageInfoEntity,
    DeviceBatteryInfoEntity,
    DeviceGeneralInfoEntity,
)
from serializers.device_info import DeviceInfoSerializer


@pytest.fixture()
def serializer() -> DeviceInfoSerializer:
    return DeviceInfoSerializer()


def test_serialize_empty_dict_returns_empty_dict(serializer: DeviceInfoSerializer):
    assert serializer.serialize({}) == {}


def test_serialize_single_entity_returns_correct_dict(
        serializer: DeviceInfoSerializer,
        battery_entity: DeviceBatteryInfoEntity,
):
    result = serializer.serialize({DeviceType.BATTERY: battery_entity})
    assert result == {DeviceType.BATTERY.value: asdict(battery_entity)}


def test_serialize_multiple_entities_returns_correct_dict(
        serializer: DeviceInfoSerializer,
        battery_entity: DeviceBatteryInfoEntity,
        storage_entity: DeviceStorageInfoEntity,
        device_name_entity: DeviceGeneralInfoEntity,
):
    data = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
        DeviceType.DEVICE_NAME: device_name_entity,
    }
    result = serializer.serialize(data)
    assert result == {
        DeviceType.BATTERY.value: asdict(battery_entity),
        DeviceType.STORAGE.value: asdict(storage_entity),
        DeviceType.DEVICE_NAME.value: asdict(device_name_entity),
    }

def test_deserialize_empty_dict_returns_empty_dict(serializer: DeviceInfoSerializer):
    assert serializer.deserialize({}) == {}


def test_deserialize_battery_returns_battery_entity(
        serializer: DeviceInfoSerializer,
        battery_entity: DeviceBatteryInfoEntity,
):
    data = {DeviceType.BATTERY.value: asdict(battery_entity)}
    result = serializer.deserialize(data)
    assert result == {DeviceType.BATTERY: battery_entity}
    assert isinstance(result[DeviceType.BATTERY], DeviceBatteryInfoEntity)


def test_deserialize_storage_returns_storage_entity(
        serializer: DeviceInfoSerializer,
        storage_entity: DeviceStorageInfoEntity,
):
    data = {DeviceType.STORAGE.value: asdict(storage_entity)}
    result = serializer.deserialize(data)
    assert result == {DeviceType.STORAGE: storage_entity}
    assert isinstance(result[DeviceType.STORAGE], DeviceStorageInfoEntity)


def test_deserialize_device_name_returns_general_entity(
        serializer: DeviceInfoSerializer,
        device_name_entity: DeviceGeneralInfoEntity,
):
    data = {DeviceType.DEVICE_NAME.value: asdict(device_name_entity)}
    result = serializer.deserialize(data)
    assert result == {DeviceType.DEVICE_NAME: device_name_entity}
    assert isinstance(result[DeviceType.DEVICE_NAME], DeviceGeneralInfoEntity)


def test_deserialize_multiple_entities_returns_correct_entities(
        serializer: DeviceInfoSerializer,
        battery_entity: DeviceBatteryInfoEntity,
        storage_entity: DeviceStorageInfoEntity,
        device_name_entity: DeviceGeneralInfoEntity,
):
    data = {
        DeviceType.BATTERY.value: asdict(battery_entity),
        DeviceType.STORAGE.value: asdict(storage_entity),
        DeviceType.DEVICE_NAME.value: asdict(device_name_entity),
    }
    result = serializer.deserialize(data)
    assert result == {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
        DeviceType.DEVICE_NAME: device_name_entity,
    }


def test_serialize_then_deserialize_returns_original_data(
        serializer: DeviceInfoSerializer,
        battery_entity: DeviceBatteryInfoEntity,
        storage_entity: DeviceStorageInfoEntity,
        device_name_entity: DeviceGeneralInfoEntity,
):
    original = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
        DeviceType.DEVICE_NAME: device_name_entity,
    }
    assert serializer.deserialize(serializer.serialize(original)) == original
