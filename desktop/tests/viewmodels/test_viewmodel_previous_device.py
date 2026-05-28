"""Unit tests for DeviceViewModel — previous-device list methods."""

from unittest.mock import MagicMock

import pytest

from domain.dto.previous_device import PreviousDeviceDTO
from domain.entities.device_info import DeviceEntity
from viewmodels.device import DeviceViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_connectivity() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_device_info_service() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def view_model(qtbot, mock_connectivity: MagicMock, mock_device_info_service: MagicMock) -> DeviceViewModel:
    return DeviceViewModel(connectivity_service=mock_connectivity, device_info_service=mock_device_info_service)


# ---------------------------------------------------------------------------
# load_devices / _on_all_devices_fetched
# ---------------------------------------------------------------------------


def test_load_devices_calls_fetch_all_devices(
    view_model: DeviceViewModel,
    mock_device_info_service: MagicMock,
) -> None:
    view_model.load_devices()

    mock_device_info_service.fetch_all_devices.assert_called_once()


def test_on_all_devices_fetched_emits_previous_devices_updated(
    view_model: DeviceViewModel,
    previous_device_online: DeviceEntity,
    previous_device_recent: DeviceEntity,
) -> None:
    received: list = []
    view_model.previous_devices_updated.connect(lambda dtos: received.append(dtos))

    view_model._on_all_devices_fetched([previous_device_online, previous_device_recent])

    assert len(received) == 1


def test_on_all_devices_fetched_emits_all_entities_as_dtos(
    view_model: DeviceViewModel,
    previous_device_online: DeviceEntity,
    previous_device_recent: DeviceEntity,
    previous_device_idle: DeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.previous_devices_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_all_devices_fetched(
        [previous_device_online, previous_device_recent, previous_device_idle]
    )

    assert len(received) == 3


def test_on_all_devices_fetched_emits_empty_list_when_no_devices(
    view_model: DeviceViewModel,
) -> None:
    received: list = []
    view_model.previous_devices_updated.connect(lambda dtos: received.append(dtos))

    view_model._on_all_devices_fetched([])

    assert received == [[]]


def test_on_all_devices_fetched_converts_entities_to_previous_device_dtos(
    view_model: DeviceViewModel,
    previous_device_online: DeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.previous_devices_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_all_devices_fetched([previous_device_online])

    assert isinstance(received[0], PreviousDeviceDTO)


def test_on_all_devices_fetched_dto_id_matches_entity(
    view_model: DeviceViewModel,
    previous_device_online: DeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.previous_devices_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_all_devices_fetched([previous_device_online])

    assert received[0].id == previous_device_online.id


def test_on_all_devices_fetched_dto_fields_match_entity(
    view_model: DeviceViewModel,
    previous_device_online: DeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.previous_devices_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_all_devices_fetched([previous_device_online])

    dto = received[0]
    assert dto.name == previous_device_online.name
    assert dto.os == previous_device_online.os
    assert dto.tag == previous_device_online.tag
    assert dto.last_connected == previous_device_online.last_connected


def test_on_all_devices_fetched_single_entity_emits_single_dto(
    view_model: DeviceViewModel,
    previous_device_idle: DeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.previous_devices_updated.connect(lambda dtos: received.extend(dtos))

    view_model._on_all_devices_fetched([previous_device_idle])

    assert len(received) == 1
    assert received[0].id == "dev-003"


# ---------------------------------------------------------------------------
# _to_prev_device_dto (static helper)
# ---------------------------------------------------------------------------


def test_to_prev_device_dto_returns_previous_device_dto_instance(
    previous_device_online: DeviceEntity,
) -> None:
    result = DeviceViewModel._to_prev_device_dto(previous_device_online)

    assert isinstance(result, PreviousDeviceDTO)


def test_to_prev_device_dto_maps_id(
    previous_device_online: DeviceEntity,
) -> None:
    result = DeviceViewModel._to_prev_device_dto(previous_device_online)

    assert result.id == previous_device_online.id


def test_to_prev_device_dto_maps_name(
    previous_device_online: DeviceEntity,
) -> None:
    result = DeviceViewModel._to_prev_device_dto(previous_device_online)

    assert result.name == previous_device_online.name


def test_to_prev_device_dto_maps_os(
    previous_device_online: DeviceEntity,
) -> None:
    result = DeviceViewModel._to_prev_device_dto(previous_device_online)

    assert result.os == previous_device_online.os


def test_to_prev_device_dto_maps_tag(
    previous_device_online: DeviceEntity,
) -> None:
    result = DeviceViewModel._to_prev_device_dto(previous_device_online)

    assert result.tag == previous_device_online.tag


def test_to_prev_device_dto_maps_last_connected(
    previous_device_online: DeviceEntity,
) -> None:
    result = DeviceViewModel._to_prev_device_dto(previous_device_online)

    assert result.last_connected == previous_device_online.last_connected


def test_to_prev_device_dto_all_three_fixtures_produce_correct_ids(
    previous_device_online: DeviceEntity,
    previous_device_recent: DeviceEntity,
    previous_device_idle: DeviceEntity,
) -> None:
    assert DeviceViewModel._to_prev_device_dto(previous_device_online).id == "dev-001"
    assert DeviceViewModel._to_prev_device_dto(previous_device_recent).id == "dev-002"
    assert DeviceViewModel._to_prev_device_dto(previous_device_idle).id == "dev-003"
