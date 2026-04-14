"""Unit tests for CurrentDeviceInfoStore."""

import json
from unittest.mock import MagicMock

import pytest

from entities.device_info import DeviceInfoEntity
from serializers.interfaces.base import ISerializer
from stores.device import DeviceStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_serializer() -> MagicMock:
    return MagicMock(spec=ISerializer)


@pytest.fixture()
def store(mock_serializer: MagicMock, tmp_path) -> DeviceStore:
    return DeviceStore(
        serializer=mock_serializer,
        json_path=str(tmp_path / "device_info.json"),
    )


@pytest.fixture()
def entity() -> DeviceInfoEntity:
    return DeviceInfoEntity(
        id="dev-001",
        name="Pixel 8 Pro",
        os="Android 14",
        tag="Work",
        last_seen="now",
        battery_level=82,
        battery_charging=True,
        storage_used=64,
        storage_total=128,
        ip="192.168.1.10",
    )


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_when_file_does_not_exist_returns_none(store: DeviceStore) -> None:
    assert store.load() is None


def test_load_when_file_exists_calls_deserialize(
    store: DeviceStore,
    mock_serializer: MagicMock,
    entity: DeviceInfoEntity,
    tmp_path,
) -> None:
    raw = {"id": "dev-001", "os": "Android 14"}
    (tmp_path / "device_info.json").write_text(json.dumps(raw))
    mock_serializer.deserialize.return_value = entity

    store.load()

    mock_serializer.deserialize.assert_called_once_with(raw)


def test_load_when_file_exists_returns_deserialized_entity(
    store: DeviceStore,
    mock_serializer: MagicMock,
    entity: DeviceInfoEntity,
    tmp_path,
) -> None:
    (tmp_path / "device_info.json").write_text(json.dumps({"id": "dev-001"}))
    mock_serializer.deserialize.return_value = entity

    result = store.load()

    assert result == entity


def test_load_when_file_has_empty_object_deserializes_to_none(
    store: DeviceStore,
    mock_serializer: MagicMock,
    tmp_path,
) -> None:
    (tmp_path / "device_info.json").write_text(json.dumps({}))
    mock_serializer.deserialize.return_value = None

    result = store.load()

    mock_serializer.deserialize.assert_called_once_with({})
    assert result is None


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_none_calls_serialize_with_none(
    store: DeviceStore,
    mock_serializer: MagicMock,
) -> None:
    mock_serializer.serialize.return_value = {}

    store.save(None)

    mock_serializer.serialize.assert_called_once_with(None)


def test_save_none_writes_empty_object_to_file(
    store: DeviceStore,
    mock_serializer: MagicMock,
    tmp_path,
) -> None:
    mock_serializer.serialize.return_value = {}

    store.save(None)

    assert json.loads((tmp_path / "device_info.json").read_text()) == {}


def test_save_entity_calls_serialize_with_entity(
    store: DeviceStore,
    mock_serializer: MagicMock,
    entity: DeviceInfoEntity,
) -> None:
    mock_serializer.serialize.return_value = {"id": "dev-001"}

    store.save(entity)

    mock_serializer.serialize.assert_called_once_with(entity)


def test_save_entity_writes_serialized_data_to_file(
    store: DeviceStore,
    mock_serializer: MagicMock,
    entity: DeviceInfoEntity,
    tmp_path,
) -> None:
    serialized = {"id": "dev-001", "name": "Pixel 8 Pro", "os": "Android 14"}
    mock_serializer.serialize.return_value = serialized

    store.save(entity)

    assert json.loads((tmp_path / "device_info.json").read_text()) == serialized


def test_save_creates_file_if_not_existing(
    store: DeviceStore,
    mock_serializer: MagicMock,
    entity: DeviceInfoEntity,
    tmp_path,
) -> None:
    mock_serializer.serialize.return_value = {"id": "dev-001"}

    store.save(entity)

    assert (tmp_path / "device_info.json").exists()


# ---------------------------------------------------------------------------
# Round-trip with real serializer
# ---------------------------------------------------------------------------


def test_save_then_load_returns_original_entity(
    entity: DeviceInfoEntity,
    tmp_path,
) -> None:
    from serializers.device import DeviceSerializer

    real_store = DeviceStore(
        serializer=DeviceSerializer(),
        json_path=str(tmp_path / "device_info.json"),
    )

    real_store.save(entity)

    assert real_store.load() == entity


def test_save_none_then_load_returns_none(tmp_path) -> None:
    from serializers.device import DeviceSerializer

    real_store = DeviceStore(
        serializer=DeviceSerializer(),
        json_path=str(tmp_path / "device_info.json"),
    )

    real_store.save(None)

    assert real_store.load() is None
