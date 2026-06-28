"""Unit tests for DeviceSerializer (JSON dict ↔ DeviceEntity)."""

from datetime import date

import pytest

from domain.entities.device_info import DeviceEntity
from serializers.device import DeviceSerializer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def serializer() -> DeviceSerializer:
    return DeviceSerializer()


@pytest.fixture()
def entity() -> DeviceEntity:
    return DeviceEntity(
        id="dev-001",
        name="Pixel 8 Pro",
        os="Android 14",
        tag="Work",
        last_connected=date(2024, 1, 15),
        battery_level=82,
        battery_charging=True,
        storage_used=64.0,
        storage_total=128.0,
        ip="192.168.1.10",
    )


@pytest.fixture()
def data(entity: DeviceEntity) -> dict:
    # device.json stores last_connected as an ISO date string.
    return {
        "id": entity.id,
        "name": entity.name,
        "os": entity.os,
        "tag": entity.tag,
        "last_connected": entity.last_connected.isoformat(),
        "battery_level": entity.battery_level,
        "battery_charging": entity.battery_charging,
        "storage_used": entity.storage_used,
        "storage_total": entity.storage_total,
        "ip": entity.ip,
    }


# ---------------------------------------------------------------------------
# serialize
# ---------------------------------------------------------------------------


def test_serialize_none_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.serialize(None) is None


def test_serialize_returns_dict(serializer: DeviceSerializer, entity: DeviceEntity) -> None:
    assert isinstance(serializer.serialize(entity), dict)


def test_serialize_has_expected_keys(serializer: DeviceSerializer, entity: DeviceEntity) -> None:
    assert set(serializer.serialize(entity)) == {
        "id",
        "name",
        "os",
        "tag",
        "last_connected",
        "battery_level",
        "battery_charging",
        "storage_used",
        "storage_total",
        "ip",
    }


def test_serialize_maps_last_connected_to_isoformat(
    serializer: DeviceSerializer, entity: DeviceEntity
) -> None:
    assert serializer.serialize(entity)["last_connected"] == entity.last_connected.isoformat()


def test_serialize_maps_scalar_fields(serializer: DeviceSerializer, entity: DeviceEntity) -> None:
    d = serializer.serialize(entity)
    assert d["id"] == entity.id
    assert d["name"] == entity.name
    assert d["os"] == entity.os
    assert d["tag"] == entity.tag
    assert d["battery_level"] == entity.battery_level
    assert d["battery_charging"] == entity.battery_charging
    assert d["storage_used"] == entity.storage_used
    assert d["storage_total"] == entity.storage_total
    assert d["ip"] == entity.ip


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------


def test_deserialize_none_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.deserialize(None) is None


def test_deserialize_empty_dict_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.deserialize({}) is None


def test_deserialize_returns_device_entity(serializer: DeviceSerializer, data: dict) -> None:
    assert isinstance(serializer.deserialize(data), DeviceEntity)


def test_deserialize_restores_last_connected_as_date(
    serializer: DeviceSerializer, entity: DeviceEntity, data: dict
) -> None:
    result = serializer.deserialize(data)
    assert result.last_connected == entity.last_connected
    assert isinstance(result.last_connected, date)


def test_deserialize_restores_scalar_fields(
    serializer: DeviceSerializer, entity: DeviceEntity, data: dict
) -> None:
    result = serializer.deserialize(data)
    assert result.id == entity.id
    assert result.name == entity.name
    assert result.os == entity.os
    assert result.tag == entity.tag
    assert result.battery_level == entity.battery_level
    assert result.battery_charging == entity.battery_charging
    assert result.storage_used == entity.storage_used
    assert result.storage_total == entity.storage_total
    assert result.ip == entity.ip


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_returns_original_entity(serializer: DeviceSerializer, entity: DeviceEntity) -> None:
    assert serializer.deserialize(serializer.serialize(entity)) == entity


def test_serialize_none_then_deserialize_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.deserialize(serializer.serialize(None)) is None
