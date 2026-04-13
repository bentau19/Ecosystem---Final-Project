"""Unit tests for PreviousDeviceViewModel."""

from unittest.mock import MagicMock, patch

import pytest

from dto.connected_device import PreviousDeviceDTO
from entities.connected_device import PreviousDeviceEntity
from enums.device_status import DeviceStatus
from viewmodels.connected_device import PreviousDeviceViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_repo() -> MagicMock:
    repo: MagicMock = MagicMock()
    repo.entity_saved.connect = MagicMock()
    repo.entity_deleted.connect = MagicMock()
    return repo


@pytest.fixture()
def view_model(mock_repo: MagicMock) -> PreviousDeviceViewModel:
    with patch("viewmodels.connected_device.repository_manager") as mock_app_state:
        mock_app_state.previous_device_repository = mock_repo
        vm = PreviousDeviceViewModel()
    return vm


# ---------------------------------------------------------------------------
# load_devices
# ---------------------------------------------------------------------------


def test_load_devices_emits_devices_loaded_signal(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
) -> None:
    mock_repo.get_all.return_value = [previous_device_online, previous_device_recent]
    received: list[list[PreviousDeviceDTO]] = []
    view_model.devices_loaded.connect(lambda dtos: received.append(dtos))

    view_model.load_devices()

    assert len(received) == 1


def test_load_devices_emits_all_entities_as_dtos(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
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
    previous_device_online: PreviousDeviceEntity,
) -> None:
    mock_repo.get_all.return_value = [previous_device_online]
    received: list[PreviousDeviceDTO] = []
    view_model.devices_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_devices()

    dto = received[0]
    assert isinstance(dto, PreviousDeviceDTO)


def test_load_devices_dto_fields_match_entity_fields(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    mock_repo.get_all.return_value = [previous_device_online]
    received: list[PreviousDeviceDTO] = []
    view_model.devices_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_devices()

    dto = received[0]
    assert dto.id == previous_device_online.id
    assert dto.name == previous_device_online.name
    assert dto.os_label == previous_device_online.os_label
    assert dto.tag == previous_device_online.tag
    assert dto.icon_path == previous_device_online.icon_path
    assert dto.status == previous_device_online.status
    assert dto.last_seen == previous_device_online.last_seen
    assert dto.ip == previous_device_online.ip


def test_load_devices_single_entity_emits_single_dto(
    view_model: PreviousDeviceViewModel,
    mock_repo: MagicMock,
    previous_device_idle: PreviousDeviceEntity,
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
    previous_device_online: PreviousDeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_online)

    assert len(received) == 1


def test_on_device_saved_emits_dto_not_entity(
    view_model: PreviousDeviceViewModel,
    previous_device_online: PreviousDeviceEntity,
) -> None:
    received: list = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_online)

    assert isinstance(received[0], PreviousDeviceDTO)


def test_on_device_saved_dto_fields_match_entity(
    view_model: PreviousDeviceViewModel,
    previous_device_recent: PreviousDeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_recent)

    dto = received[0]
    assert dto.id == previous_device_recent.id
    assert dto.name == previous_device_recent.name
    assert dto.os_label == previous_device_recent.os_label
    assert dto.tag == previous_device_recent.tag
    assert dto.icon_path == previous_device_recent.icon_path
    assert dto.status == previous_device_recent.status
    assert dto.last_seen == previous_device_recent.last_seen
    assert dto.ip == previous_device_recent.ip


def test_on_device_saved_emits_correct_dto_for_each_entity(
    view_model: PreviousDeviceViewModel,
    previous_device_online: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    received: list[PreviousDeviceDTO] = []
    view_model.device_saved.connect(lambda dto: received.append(dto))

    view_model._on_device_saved(previous_device_online)
    view_model._on_device_saved(previous_device_idle)

    assert received[0].id == "dev-001"
    assert received[1].id == "dev-003"


# ---------------------------------------------------------------------------
# _on_device_deleted (slot forwarded from repository signal)
# ---------------------------------------------------------------------------


def test_on_device_deleted_emits_device_deleted_signal(
    view_model: PreviousDeviceViewModel,
) -> None:
    received: list[str] = []
    view_model.device_deleted.connect(lambda id: received.append(id))

    view_model._on_device_deleted("dev-001")

    assert received == ["dev-001"]


def test_on_device_deleted_passes_id_unchanged(
    view_model: PreviousDeviceViewModel,
) -> None:
    received: list[str] = []
    view_model.device_deleted.connect(lambda id: received.append(id))

    view_model._on_device_deleted("dev-002")
    view_model._on_device_deleted("dev-003")

    assert received == ["dev-002", "dev-003"]


def test_on_device_deleted_works_with_arbitrary_id(
    view_model: PreviousDeviceViewModel,
) -> None:
    received: list[str] = []
    view_model.device_deleted.connect(lambda id: received.append(id))

    view_model._on_device_deleted("nonexistent-id")

    assert received == ["nonexistent-id"]


# ---------------------------------------------------------------------------
# _to_dto (static helper)
# ---------------------------------------------------------------------------


def test_to_dto_returns_previous_device_dto_instance(
    previous_device_online: PreviousDeviceEntity,
) -> None:
    result = PreviousDeviceViewModel._to_dto(previous_device_online)

    assert isinstance(result, PreviousDeviceDTO)


def test_to_dto_maps_all_fields_correctly(
    previous_device_online: PreviousDeviceEntity,
) -> None:
    result = PreviousDeviceViewModel._to_dto(previous_device_online)

    assert result.id == previous_device_online.id
    assert result.name == previous_device_online.name
    assert result.os_label == previous_device_online.os_label
    assert result.tag == previous_device_online.tag
    assert result.icon_path == previous_device_online.icon_path
    assert result.status == previous_device_online.status
    assert result.last_seen == previous_device_online.last_seen
    assert result.ip == previous_device_online.ip


def test_to_dto_preserves_device_status_enum(
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    result = PreviousDeviceViewModel._to_dto(previous_device_idle)

    assert result.status is DeviceStatus.IDLE


def test_to_dto_works_for_all_status_values(
    previous_device_online: PreviousDeviceEntity,
    previous_device_recent: PreviousDeviceEntity,
    previous_device_idle: PreviousDeviceEntity,
) -> None:
    assert PreviousDeviceViewModel._to_dto(previous_device_online).status is DeviceStatus.ONLINE
    assert PreviousDeviceViewModel._to_dto(previous_device_recent).status is DeviceStatus.RECENT
    assert PreviousDeviceViewModel._to_dto(previous_device_idle).status is DeviceStatus.IDLE
