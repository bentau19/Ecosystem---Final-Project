from unittest.mock import MagicMock, patch

import pytest

from dto.device_info import DeviceBatteryDTO, DeviceStorageDTO, DeviceNameDTO
from entities.device_info import DeviceBatteryEntity, DeviceStorageEntity, DeviceNameEntity
from enums.device_type import DeviceType
from viewmodels.device_info import DeviceInfoViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.entity_saved.connect = MagicMock()
    repo.entity_deleted.connect = MagicMock()
    return repo


@pytest.fixture()
def view_model(mock_repo: MagicMock) -> DeviceInfoViewModel:
    with patch("viewmodels.device_info.repository_manager") as mock_app_state:
        mock_app_state.device_repository = mock_repo
        vm = DeviceInfoViewModel()
    return vm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# --- load_device_infos ---

def test_load_device_infos_emits_device_infos_loaded_signal(
        view_model: DeviceInfoViewModel,
        mock_repo: MagicMock,
        battery_entity: DeviceBatteryEntity,
        storage_entity: DeviceStorageEntity,
):
    mock_repo.get_all.return_value = [battery_entity, storage_entity]
    received = []
    view_model.device_infos_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_device_infos()

    assert len(received) == 2


def test_load_device_infos_when_repo_empty_emits_empty_list(
        view_model: DeviceInfoViewModel,
        mock_repo: MagicMock,
):
    mock_repo.get_all.return_value = []
    received = []
    view_model.device_infos_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_device_infos()

    assert received == []


def test_load_device_infos_converts_entities_to_dtos(
        view_model: DeviceInfoViewModel,
        mock_repo: MagicMock,
        battery_entity: DeviceBatteryEntity,
):
    mock_repo.get_all.return_value = [battery_entity]
    received = []
    view_model.device_infos_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_device_infos()

    dto = received[0]
    assert isinstance(dto, DeviceBatteryDTO)
    assert dto.title == battery_entity.title


# --- _on_entity_saved ---

def test_on_entity_saved_emits_device_info_added_signal(
        view_model: DeviceInfoViewModel,
        battery_entity: DeviceBatteryEntity,
):
    received = []
    view_model.device_info_added.connect(lambda dto: received.append(dto))

    view_model._on_entity_saved(battery_entity)

    assert len(received) == 1
    assert isinstance(received[0], DeviceBatteryDTO)


def test_on_entity_saved_converts_entity_to_dto(
        view_model: DeviceInfoViewModel,
        battery_entity: DeviceBatteryEntity,
):
    received = []
    view_model.device_info_added.connect(lambda obj: received.append(obj))

    view_model._on_entity_saved(battery_entity)

    dto = received[0]
    assert dto.title == battery_entity.title
    assert dto.level == battery_entity.level
    assert dto.is_charging == battery_entity.is_charging


# --- _on_entity_deleted ---

def test_on_entity_deleted_emits_device_info_deleted_signal(
        view_model: DeviceInfoViewModel,
):
    received = []
    view_model.device_info_deleted.connect(lambda id: received.append(id))

    view_model._on_entity_deleted(DeviceType.BATTERY)

    assert received == [DeviceType.BATTERY]


# --- _to_dto ---

def test_to_dto_battery_entity_returns_battery_dto(
        battery_entity: DeviceBatteryEntity,
):
    result = DeviceInfoViewModel._to_dto(battery_entity)
    assert isinstance(result, DeviceBatteryDTO)
    assert result.level == battery_entity.level
    assert result.is_charging == battery_entity.is_charging


def test_to_dto_storage_entity_returns_storage_dto(
        storage_entity: DeviceStorageEntity,
):
    result = DeviceInfoViewModel._to_dto(storage_entity)
    assert isinstance(result, DeviceStorageDTO)
    assert result.used == storage_entity.used
    assert result.total == storage_entity.total


def test_to_dto_name_entity_returns_name_dto(
        device_name_entity: DeviceNameEntity,
):
    result = DeviceInfoViewModel._to_dto(device_name_entity)
    assert isinstance(result, DeviceNameDTO)
    assert result.name == device_name_entity.name


def test_to_dto_unknown_entity_raises_value_error():
    unknown_entity = MagicMock(spec=[])
    with pytest.raises(ValueError, match="Unknown DeviceInfoEntity subclass"):
        DeviceInfoViewModel._to_dto(unknown_entity)
