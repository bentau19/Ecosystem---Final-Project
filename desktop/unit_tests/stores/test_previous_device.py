"""Unit tests for PreviousDeviceStore."""

import json
from unittest.mock import MagicMock

import pytest

from entities.connected_device import PreviousDeviceEntity
from enums.device_status import DeviceStatus
from serializers.interfaces.base import ISerializer
from stores.connected_device import PreviousDeviceStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_serializer() -> MagicMock:
    return MagicMock(spec=ISerializer)


@pytest.fixture()
def store(mock_serializer: MagicMock, tmp_path) -> PreviousDeviceStore:
    return PreviousDeviceStore(
        serializer=mock_serializer,
        json_path=str(tmp_path / "connected_devices.json"),
    )


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_when_file_does_not_exist_returns_empty_dict(store: PreviousDeviceStore) -> None:
    assert store.load() == {}


def test_load_when_file_does_not_exist_does_not_call_serializer(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
) -> None:
    store.load()

    mock_serializer.deserialize.assert_not_called()


def test_load_when_file_exists_calls_deserialize_with_file_contents(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    tmp_path,
) -> None:
    raw = {"dev-001": {"id": "dev-001", "name": "Pixel 8 Pro", "os_label": "Android 14",
                       "tag": "Work", "status": "online", "last_seen": "now", "ip": ""}}
    (tmp_path / "connected_devices.json").write_text(json.dumps(raw), encoding="utf-8")
    mock_serializer.deserialize.return_value = {"dev-001": previous_device_online}

    result = store.load()

    mock_serializer.deserialize.assert_called_once_with(raw)
    assert result == {"dev-001": previous_device_online}


def test_load_when_file_contains_empty_object_returns_deserialized_empty(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
    tmp_path,
) -> None:
    (tmp_path / "connected_devices.json").write_text(json.dumps({}), encoding="utf-8")
    mock_serializer.deserialize.return_value = {}

    result = store.load()

    mock_serializer.deserialize.assert_called_once_with({})
    assert result == {}


def test_load_multiple_devices_returns_all_deserialized(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    tmp_path,
) -> None:
    raw = {
        "dev-001": {"id": "dev-001", "status": "online"},
        "dev-002": {"id": "dev-002", "status": "recent"},
    }
    (tmp_path / "connected_devices.json").write_text(json.dumps(raw), encoding="utf-8")
    mock_serializer.deserialize.return_value = {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
    }

    result = store.load()

    assert result == {"dev-001": previous_device_online, "dev-002": previous_device_recent}


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


def test_save_calls_serializer_with_provided_data(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    data = {"dev-001": previous_device_online}
    mock_serializer.serialize.return_value = {}

    store.save(data)

    mock_serializer.serialize.assert_called_once_with(data)


def test_save_writes_serialized_data_to_file(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    tmp_path,
) -> None:
    data = {"dev-001": previous_device_online}
    serialized = {"dev-001": {"id": "dev-001", "name": "Pixel 8 Pro", "status": "online"}}
    mock_serializer.serialize.return_value = serialized

    store.save(data)

    written = json.loads((tmp_path / "connected_devices.json").read_text(encoding="utf-8"))
    assert written == serialized


def test_save_multiple_devices_writes_all_to_file(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    tmp_path,
) -> None:
    data = {"dev-001": previous_device_online, "dev-002": previous_device_recent}
    serialized = {
        "dev-001": {"id": "dev-001", "status": "online"},
        "dev-002": {"id": "dev-002", "status": "recent"},
    }
    mock_serializer.serialize.return_value = serialized

    store.save(data)

    written = json.loads((tmp_path / "connected_devices.json").read_text(encoding="utf-8"))
    assert written == serialized


def test_save_empty_dict_writes_empty_object_to_file(
    store: PreviousDeviceStore,
    mock_serializer: MagicMock,
    tmp_path,
) -> None:
    mock_serializer.serialize.return_value = {}

    store.save({})

    written = json.loads((tmp_path / "connected_devices.json").read_text(encoding="utf-8"))
    assert written == {}


# ---------------------------------------------------------------------------
# round-trip (real serializer)
# ---------------------------------------------------------------------------


def test_save_then_load_returns_original_data(
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
    tmp_path,
) -> None:
    from serializers.previous_device import PreviousDeviceSerializer

    real_store = PreviousDeviceStore(
        serializer=PreviousDeviceSerializer(),
        json_path=str(tmp_path / "connected_devices.json"),
    )
    original = {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
        "dev-003": previous_device_idle,
    }

    real_store.save(original)
    result = real_store.load()

    assert result == original
