import json
from unittest.mock import MagicMock

import pytest

from entities.device_info import DeviceType, DeviceBatteryInfoEntity, DeviceStorageInfoEntity
from serializers.interfaces.base import ISerializer
from stores.device_info import DeviceInfoStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_serializer() -> MagicMock:
    return MagicMock(spec=ISerializer)


@pytest.fixture()
def store(mock_serializer: MagicMock, tmp_path) -> DeviceInfoStore:
    return DeviceInfoStore(serializer=mock_serializer, json_path=str(tmp_path / "device_info.json"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_when_file_does_not_exist_returns_empty_dict(store: DeviceInfoStore):
    assert store.load() == {}


def test_load_when_file_exists_returns_deserialized_data(
        store: DeviceInfoStore,
        mock_serializer: MagicMock,
        battery_entity: DeviceBatteryInfoEntity,
        tmp_path,
):
    raw = {str(DeviceType.BATTERY.value): {"title": "Battery"}}
    json_file = tmp_path / "device_info.json"
    json_file.write_text(json.dumps(raw))

    mock_serializer.deserialize.return_value = {DeviceType.BATTERY: battery_entity}

    result = store.load()

    mock_serializer.deserialize.assert_called_once_with(raw)
    assert result == {DeviceType.BATTERY: battery_entity}


def test_load_when_file_is_empty_json_returns_deserialized_empty(
        store: DeviceInfoStore,
        mock_serializer: MagicMock,
        tmp_path,
):
    json_file = tmp_path / "device_info.json"
    json_file.write_text(json.dumps({}))

    mock_serializer.deserialize.return_value = {}

    result = store.load()

    mock_serializer.deserialize.assert_called_once_with({})
    assert result == {}


def test_save_serializes_data_and_writes_to_file(
        store: DeviceInfoStore,
        mock_serializer: MagicMock,
        battery_entity: DeviceBatteryInfoEntity,
        tmp_path,
):
    data = {DeviceType.BATTERY: battery_entity}
    serialized = {f"'{DeviceType.BATTERY.value}'": {"title": "Battery"}}
    mock_serializer.serialize.return_value = serialized

    store.save(data)

    mock_serializer.serialize.assert_called_once_with(data)
    json_file = tmp_path / "device_info.json"
    assert json_file.exists()
    assert json.loads(json_file.read_text()) == serialized


def test_save_multiple_entities_writes_all_to_file(
        store: DeviceInfoStore,
        mock_serializer: MagicMock,
        battery_entity: DeviceBatteryInfoEntity,
        storage_entity: DeviceStorageInfoEntity,
        tmp_path,
):
    data = {DeviceType.BATTERY: battery_entity, DeviceType.STORAGE: storage_entity}
    serialized = {
        f"'{DeviceType.BATTERY.value}'": {"title": "Battery"},
        f"'{DeviceType.STORAGE.value}'": {"title": "Storage"},
    }
    mock_serializer.serialize.return_value = serialized

    store.save(data)

    json_file = tmp_path / "device_info.json"
    assert json.loads(json_file.read_text()) == serialized


# --- round trip ---
def test_save_then_load_returns_original_data(
        battery_entity: DeviceBatteryInfoEntity,
        storage_entity: DeviceStorageInfoEntity,
        tmp_path,
):
    from serializers.device_info import DeviceInfoSerializer

    real_serializer = DeviceInfoSerializer()
    store = DeviceInfoStore(serializer=real_serializer, json_path=str(tmp_path / "device_info.json"))

    original = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
    }

    store.save(original)
    result = store.load()

    assert result == original
