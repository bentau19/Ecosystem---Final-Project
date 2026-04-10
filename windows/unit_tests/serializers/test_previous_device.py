"""Unit tests for PreviousDeviceSerializer."""

from dataclasses import asdict

import pytest

from entities.previous_device import PreviousDeviceEntity
from enums.device_status import DeviceStatus
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
    previous_device_online: PreviousDeviceEntity,
) -> None:
    result = serializer.serialize({"dev-001": previous_device_online})

    assert result == {"dev-001": asdict(previous_device_online)}


def test_serialize_multiple_entities_returns_all_entries(
    serializer: PreviousDeviceSerializer,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
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


def test_serialize_status_stored_as_string(
    serializer: PreviousDeviceSerializer,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    result = serializer.serialize({"dev-001": previous_device_online})

    assert result["dev-001"]["status"] == "online"


# ---------------------------------------------------------------------------
# deserialize
# ---------------------------------------------------------------------------


def test_deserialize_empty_dict_returns_empty_dict(serializer: PreviousDeviceSerializer) -> None:
    assert serializer.deserialize({}) == {}


def test_deserialize_single_entry_returns_correct_entity(
    serializer: PreviousDeviceSerializer,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    raw = {"dev-001": asdict(previous_device_online)}

    result = serializer.deserialize(raw)

    assert result == {"dev-001": previous_device_online}
    assert isinstance(result["dev-001"], PreviousDeviceEntity)


def test_deserialize_status_converted_to_enum(
    serializer: PreviousDeviceSerializer,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    raw = {"dev-001": asdict(previous_device_online)}

    result = serializer.deserialize(raw)

    assert result["dev-001"].status is DeviceStatus.ONLINE


def test_deserialize_multiple_entries_returns_all_entities(
    serializer: PreviousDeviceSerializer,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
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


def test_deserialize_all_statuses_reconstruct_correctly(
    serializer: PreviousDeviceSerializer,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    raw = {
        "dev-001": asdict(previous_device_online),
        "dev-002": asdict(previous_device_recent),
        "dev-003": asdict(previous_device_idle),
    }

    result = serializer.deserialize(raw)

    assert result["dev-001"].status is DeviceStatus.ONLINE
    assert result["dev-002"].status is DeviceStatus.RECENT
    assert result["dev-003"].status is DeviceStatus.IDLE


# ---------------------------------------------------------------------------
# round-trip
# ---------------------------------------------------------------------------


def test_serialize_then_deserialize_returns_original_data(
    serializer: PreviousDeviceSerializer,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    original = {
        "dev-001": previous_device_online,
        "dev-002": previous_device_recent,
        "dev-003": previous_device_idle,
    }

    assert serializer.deserialize(serializer.serialize(original)) == original
