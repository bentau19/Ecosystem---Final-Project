"""Unit tests for DeviceSerializer (SQLite row tuple ↔ DeviceEntity)."""

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
        storage_used=64,
        storage_total=128,
        ip="192.168.1.10",
    )


@pytest.fixture()
def row(entity: DeviceEntity) -> tuple:
    # SQLite returns date columns as ISO-format strings ("YYYY-MM-DD"),
    # so position 4 must be a string — not a date object.
    return (
        entity.id,
        entity.name,
        entity.os,
        entity.tag,
        entity.last_connected.isoformat(),
        entity.battery_level,
        entity.battery_charging,
        entity.storage_used,
        entity.storage_total,
        entity.ip,
    )


# ---------------------------------------------------------------------------
# serialize
# ---------------------------------------------------------------------------


def test_serialize_none_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.serialize(None) is None


def test_serialize_returns_tuple(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert isinstance(serializer.serialize(entity), tuple)


def test_serialize_tuple_has_ten_elements(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert len(serializer.serialize(entity)) == 10


def test_serialize_first_element_is_id(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[0] == entity.id


def test_serialize_second_element_is_name(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[1] == entity.name


def test_serialize_third_element_is_os(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[2] == entity.os


def test_serialize_fourth_element_is_tag(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[3] == entity.tag


def test_serialize_fifth_element_is_last_connected(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[4] == entity.last_connected.isoformat()


def test_serialize_sixth_element_is_battery_level(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[5] == entity.battery_level


def test_serialize_seventh_element_is_battery_charging(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[6] == entity.battery_charging


def test_serialize_eighth_element_is_storage_used(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[7] == entity.storage_used


def test_serialize_ninth_element_is_storage_total(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[8] == entity.storage_total


def test_serialize_tenth_element_is_ip(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.serialize(entity)[9] == entity.ip


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------


def test_deserialize_none_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.deserialize(None) is None


def test_deserialize_empty_tuple_returns_none(serializer: DeviceSerializer) -> None:
    assert serializer.deserialize(()) is None


def test_deserialize_full_row_returns_device_entity(
    serializer: DeviceSerializer,
    row: tuple,
) -> None:
    result = serializer.deserialize(row)

    assert isinstance(result, DeviceEntity)


def test_deserialize_restores_id(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).id == entity.id


def test_deserialize_restores_name(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).name == entity.name


def test_deserialize_restores_os(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).os == entity.os


def test_deserialize_restores_battery_level(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).battery_level == entity.battery_level


def test_deserialize_restores_battery_charging(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).battery_charging == entity.battery_charging


def test_deserialize_restores_storage_used(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).storage_used == entity.storage_used


def test_deserialize_restores_storage_total(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).storage_total == entity.storage_total


def test_deserialize_restores_last_connected(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).last_connected == entity.last_connected


def test_deserialize_restores_ip(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
    row: tuple,
) -> None:
    assert serializer.deserialize(row).ip == entity.ip


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_serialize_then_deserialize_returns_original_entity(
    serializer: DeviceSerializer,
    entity: DeviceEntity,
) -> None:
    assert serializer.deserialize(serializer.serialize(entity)) == entity


def test_serialize_none_then_deserialize_returns_none(
    serializer: DeviceSerializer,
) -> None:
    assert serializer.deserialize(serializer.serialize(None)) is None
