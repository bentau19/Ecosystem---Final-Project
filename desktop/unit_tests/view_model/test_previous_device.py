"""Unit tests for PreviousDeviceViewModel."""

from unittest.mock import MagicMock, patch

import pytest

from dto.previous_device import PreviousDeviceDTO
from entities.device_info import DeviceInfoEntity
from enums.device_status import DeviceStatus
from viewmodels.previous_device import PreviousDeviceViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_repo() -> MagicMock:
    repo: MagicMock = MagicMock()
    repo.entity_saved.connect = MagicMock()
    return repo


@pytest.fixture()
def view_model(mock_repo: MagicMock) -> PreviousDeviceViewModel:
    with patch("viewmodels.previous_device.repository_manager") as mock_rm:
        mock_rm.previous_device_repository = mock_repo
        vm = PreviousDeviceViewModel()
    return vm


# ---------------------------------------------------------------------------
# load_devices
# ---------------------------------------------------------------------------


def test_load_devices_emits_devices_loaded_signal(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_online: DeviceInfoEntity,
    previous_device_recent: DeviceInfoEntity,
) -> None:
    mock_repo.get_all.return_value = [previous_device_online, previous_device_recent]
    received: list[list[PreviousDeviceDTO]] = []
    view_model.devices_loaded.connect(lambda dtos: received.append(dtos))

    view_model.load_devices()

    assert len(received) == 1


def test_load_devices_emits_all_entities_as_dtos(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_online: DeviceInfoEntity,
    previous_device_recent: DeviceInfoEntity,
    previous_device_idle: DeviceInfoEntity,
) -> None:
    mock_repo.get_all.return_value = [
        previous_device_online,
        previous_device_recent,
        previous_device_idle,
    ]
    received: list[PreviousDeviceDTO] = []
    view_model.devices_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_devices()

    assert len(received) == 3


def test_load_devices_when_repo_empty_emits_empty_list(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
) -> None:
    mock_repo.get_all.return_value = []
    received: list[list] = []
    view_model.devices_loaded.connect(lambda dtos: received.append(dtos))

    view_model.load_devices()

    assert received == [[]]


def test_load_devices_converts_entities_to_dtos(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_online: DeviceInfoEntity,
) -> None:
    mock_repo.get_all.return_value = [previous_device_online]
    received: list[PreviousDeviceDTO] = []
    view_model.devices_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_devices()

    assert isinstance(received[0], PreviousDeviceDTO)


def test_load_devices_dto_fields_match_entity_fields(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_online: DeviceInfoEntity,
) -> None:
    mock_repo.get_all.return_value = [previous_device_online]
    received: list[PreviousDeviceDTO] = []
    view_model.devices_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_devices()

    dto = received[0]
    assert dto.id == previous_device_online.id
    assert dto.name == previous_device_online.name
    assert dto.os == previous_device_online.os
    assert dto.tag == previous_device_online.tag
    assert dto.last_connected == previous_device_online.last_connected
    assert dto.ip == previous_device_online.ip


def test_load_devices_single_entity_emits_single_dto(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_idle: DeviceInfoEntity,
) -> None:
    mock_repo.get_all.return_value = [previous_device_idle]
    received: list[PreviousDeviceDTO] = []
    view_model.devices_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_devices()

    assert len(received) == 1
    assert received[0].id == "dev-003"


# ---------------------------------------------------------------------------
# _on_device_saved (slot forwarded from repository signal)
# ---------------------------------------------------------------------------


def test_on_device_saved_emits_device_saved_signal(
    view_model: PreviousDeviceViewModel,
    previous_device_online: DeviceInfoEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_online)

    assert len(received) == 1


def test_on_device_saved_emits_dto_not_entity(
    view_model: PreviousDeviceViewModel,
    previous_device_online: DeviceInfoEntity,
) -> None:
    received: list = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_online)

    assert isinstance(received[0], PreviousDeviceDTO)


def test_on_device_saved_dto_fields_match_entity(
    view_model: PreviousDeviceViewModel,
    previous_device_recent: DeviceInfoEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_recent)

    dto = received[0]
    assert dto.id == previous_device_recent.id
    assert dto.name == previous_device_recent.name
    assert dto.os == previous_device_recent.os
    assert dto.tag == previous_device_recent.tag
    assert dto.last_connected == previous_device_recent.last_connected
    assert dto.ip == previous_device_recent.ip


def test_on_device_saved_emits_correct_dto_for_each_entity(
    view_model: PreviousDeviceViewModel,
    previous_device_online: DeviceInfoEntity,
    previous_device_idle: DeviceInfoEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_online)
    view_model._on_device_saved(previous_device_idle)

    assert received[0].id == "dev-001"
    assert received[1].id == "dev-003"


# ---------------------------------------------------------------------------
# _to_dto (static helper)
# ---------------------------------------------------------------------------


def test_to_dto_returns_previous_device_dto_instance(
    previous_device_online: DeviceInfoEntity,
) -> None:
    result = PreviousDeviceViewModel._to_dto(previous_device_online)

    assert isinstance(result, PreviousDeviceDTO)


def test_to_dto_maps_all_fields_correctly(
    previous_device_online: DeviceInfoEntity,
) -> None:
    result = PreviousDeviceViewModel._to_dto(previous_device_online)

    assert result.id == previous_device_online.id
    assert result.name == previous_device_online.name
    assert result.os == previous_device_online.os
    assert result.tag == previous_device_online.tag
    assert result.last_connected == previous_device_online.last_connected
    assert result.ip == previous_device_online.ip


def test_to_dto_last_seen_now_produces_recent_status(
    previous_device_online: DeviceInfoEntity,
) -> None:
    # previous_device_online has last_seen="now"
    result = PreviousDeviceViewModel._to_dto(previous_device_online)

    assert result.status is DeviceStatus.RECENT


def test_to_dto_last_seen_today_produces_recent_status(
    previous_device_recent: DeviceInfoEntity,
) -> None:
    # previous_device_recent has last_seen="today"
    result = PreviousDeviceViewModel._to_dto(previous_device_recent)

    assert result.status is DeviceStatus.RECENT


def test_to_dto_old_last_seen_produces_idle_status(
    previous_device_idle: DeviceInfoEntity,
) -> None:
    # previous_device_idle has last_seen="3 days ago"
    result = PreviousDeviceViewModel._to_dto(previous_device_idle)

    assert result.status is DeviceStatus.IDLE
