"""Unit tests for PreviousDeviceSerializer."""

from dataclasses import asdict

import pytest

from entities.device_info import DeviceInfoEntity
from serializers.previous_device import PreviousDeviceSerializer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def serializer() -> PreviousDeviceSerializer:
    return PreviousDeviceSerializer()


# ---------------------------------------------------------------------------
# serialize
# ---------------------------------------------------------------------------


def test_serialize_empty_dict_returns_empty_dict(serializer: PreviousDeviceSerializer) -> None:
    assert serializer.serialize({}) == {}


def test_serialize_single_entity_returns_correct_dict(
    serializer: PreviousDeviceSerializer,
    previous_device_online: DeviceInfoEntity,
) -> None:
    result = serializer.serialize({"dev-001": previous_device_online})

    assert result == {"dev-001": asdict(previous_device_online)}


def test_serialize_multiple_entities_returns_all_entries(
    serializer: PreviousDeviceSerializer,
    previous_device_online: DeviceInfoEntity,
    previous_device_recent: DeviceInfoEntity,
    previous_device_idle: DeviceInfoEntity,
) -> None:
    data = {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
        "dev-003": previous_device_idle,
    }

    result = serializer.serialize(data)

    assert result == {
        "dev-001": asdict(previous_device_online),
        "dev-002": asdict(previous_device_recent),
        "dev-003": asdict(previous_device_idle),
    }


def test_serialize_preserves_all_entity_fields(
    serializer: PreviousDeviceSerializer,
    previous_device_online: DeviceInfoEntity,
) -> None:
    result = serializer.serialize({"dev-001": previous_device_online})

    entry = result["dev-001"]
    assert entry["id"] == previous_device_online.id
    assert entry["name"] == previous_device_online.name
    assert entry["os"] == previous_device_online.os
    assert entry["battery_level"] == previous_device_online.battery_level
    assert entry["storage_used"] == previous_device_online.storage_used


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------


def test_deserialize_empty_dict_returns_empty_dict(serializer: PreviousDeviceSerializer) -> None:
    assert serializer.deserialize({}) == {}


def test_deserialize_single_entry_returns_correct_entity(
    serializer: PreviousDeviceSerializer,
    previous_device_online: DeviceInfoEntity,
) -> None:
    raw = {"dev-001": asdict(previous_device_online)}

    result = serializer.deserialize(raw)

    assert result == {"dev-001": previous_device_online}
    assert isinstance(result["dev-001"], DeviceInfoEntity)


def test_deserialize_multiple_entries_returns_all_entities(
    serializer: PreviousDeviceSerializer,
    previous_device_online: DeviceInfoEntity,
    previous_device_recent: DeviceInfoEntity,
    previous_device_idle: DeviceInfoEntity,
) -> None:
    raw = {
        "dev-001": asdict(previous_device_online),
        "dev-002": asdict(previous_device_recent),
        "dev-003": asdict(previous_device_idle),
    }

    result = serializer.deserialize(raw)

    assert result == {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
        "dev-003": previous_device_idle,
    }


def test_deserialize_drops_icon_path_if_present(
    serializer: PreviousDeviceSerializer,
    previous_device_online: DeviceInfoEntity,
) -> None:
    raw = {"dev-001": asdict(previous_device_online)}
    raw["dev-001"]["icon_path"] = "legacy/icon.png"

    result = serializer.deserialize(raw)

    assert result == {"dev-001": previous_device_online}


# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------


def test_serialize_then_deserialize_returns_original_data(
    serializer: PreviousDeviceSerializer,
    previous_device_online: DeviceInfoEntity,
    previous_device_recent: DeviceInfoEntity,
    previous_device_idle: DeviceInfoEntity,
) -> None:
    original = {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
        "dev-003": previous_device_idle,
    }

    assert serializer.deserialize(serializer.serialize(original)) == original
