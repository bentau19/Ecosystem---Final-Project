"""Unit tests for CurrentDeviceInfoSerializer."""

from dataclasses import asdict

import pytest

from entities.device_info import DeviceInfoEntity
from serializers.device import DeviceSerializer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def serializer() -> DeviceSerializer:
    return DeviceSerializer()


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
# serialize
# ---------------------------------------------------------------------------


def test_serialize_none_returns_empty_dict(serializer: DeviceSerializer) -> None:
    assert serializer.serialize(None) == {}


def test_serialize_entity_returns_dict_with_all_fields(
    serializer: DeviceSerializer,
    entity: DeviceInfoEntity,
) -> None:
    result = serializer.serialize(entity)

    assert result["id"] == entity.id
    assert result["name"] == entity.name
    assert result["os"] == entity.os
    assert result["tag"] == entity.tag
    assert result["last_seen"] == entity.last_connected
    assert result["battery_level"] == entity.battery_level
    assert result["battery_charging"] == entity.battery_charging
    assert result["storage_used"] == entity.storage_used
    assert result["storage_total"] == entity.storage_total
    assert result["ip"] == entity.ip


def test_serialize_entity_result_matches_asdict(
    serializer: DeviceSerializer,
    entity: DeviceInfoEntity,
) -> None:
    assert serializer.serialize(entity) == asdict(entity)


def test_serialize_entity_result_is_json_safe(
    serializer: DeviceSerializer,
    entity: DeviceInfoEntity,
) -> None:
    import json

    json.dumps(serializer.serialize(entity))


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------


def test_deserialize_empty_dict_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.deserialize({}) is None


def test_deserialize_full_dict_returns_entity(
    serializer: DeviceSerializer,
    entity: DeviceInfoEntity,
) -> None:
    result = serializer.deserialize(asdict(entity))

    assert result == entity
    assert isinstance(result, DeviceInfoEntity)


def test_deserialize_drops_icon_path_if_present(
    serializer: DeviceSerializer,
    entity: DeviceInfoEntity,
) -> None:
    raw = asdict(entity)
    raw["icon_path"] = "legacy/icon.png"

    result = serializer.deserialize(raw)

    assert result == entity


def test_deserialize_restores_correct_field_values(
    serializer: DeviceSerializer,
    entity: DeviceInfoEntity,
) -> None:
    result = serializer.deserialize(asdict(entity))

    assert result.name == entity.name
    assert result.os == entity.os
    assert result.battery_level == entity.battery_level
    assert result.battery_charging == entity.battery_charging
    assert result.storage_used == entity.storage_used
    assert result.storage_total == entity.storage_total


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_serialize_then_deserialize_returns_original_entity(
    serializer: DeviceSerializer,
    entity: DeviceInfoEntity,
) -> None:
    assert serializer.deserialize(serializer.serialize(entity)) == entity


def test_round_trip_none_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.deserialize(serializer.serialize(None)) is None
