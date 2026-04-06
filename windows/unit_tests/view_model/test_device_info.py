from unittest.mock import MagicMock, patch

import pytest
from dto.device_info import (
    DeviceBatteryInfoDTO,
    DeviceStorageInfoDTO,
    DeviceGeneralInfoDTO,
    DeviceType,
)
from entities.device_info import (
    DeviceBatteryInfoEntity,
    DeviceStorageInfoEntity,
    DeviceGeneralInfoEntity,
)
from viewmodels.device_info import DeviceInfoViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.device_info_saved.connect = MagicMock()
    repo.device_info_deleted.connect = MagicMock()
    return repo


@pytest.fixture()
def view_model(mock_repo: MagicMock) -> DeviceInfoViewModel:
    with patch("viewmodels.device_info.app_state") as mock_app_state:
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
        battery_entity: DeviceBatteryInfoEntity,
        storage_entity: DeviceStorageInfoEntity,
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
        battery_entity: DeviceBatteryInfoEntity,
):
    mock_repo.get_all.return_value = [battery_entity]
    received = []
    view_model.device_infos_loaded.connect(lambda dtos: received.extend(dtos))

    view_model.load_device_infos()

    dto = received[0]
    assert isinstance(dto, DeviceBatteryInfoDTO)
    assert dto.title == battery_entity.title

    # --- _on_device_added ---


def test_on_device_added_emits_device_info_added_signal(
        view_model: DeviceInfoViewModel,
        battery_entity: DeviceBatteryInfoEntity,
):
    received = []
    view_model.device_info_added.connect(lambda dto: received.append(dto))

    view_model._on_device_added(battery_entity)

    assert len(received) == 1
    assert isinstance(received[0], DeviceBatteryInfoDTO)


def test_on_device_added_converts_entity_to_dto(
        view_model: DeviceInfoViewModel,
        battery_entity: DeviceBatteryInfoEntity,
):
    received = []
    view_model.device_info_added.connect(lambda obj: received.append(obj))

    view_model._on_device_added(battery_entity)

    dto = received[0]
    assert dto.title == battery_entity.title
    assert dto.battery_percentage == battery_entity.battery_percentage
    assert dto.is_charging == battery_entity.is_charging

    # --- _on_device_deleted ---


def test_on_device_deleted_emits_device_info_deleted_signal(
        view_model: DeviceInfoViewModel,
):
    received = []
    view_model.device_info_deleted.connect(lambda id: received.append(id))

    view_model._on_device_deleted(DeviceType.BATTERY)

    assert received == [DeviceType.BATTERY]

    # --- _on_device_updated ---


def test_on_device_updated_emits_device_info_updated_signal(
        view_model: DeviceInfoViewModel,
        battery_entity: DeviceBatteryInfoEntity,
):
    received = []
    view_model.device_info_updated.connect(lambda dto: received.append(dto))

    view_model._on_device_updated(battery_entity)

    assert len(received) == 1


def test_on_device_updated_emits_string_representation(
        view_model: DeviceInfoViewModel,
        battery_entity: DeviceBatteryInfoEntity,
):
    received = []
    view_model.device_info_updated.connect(lambda dto: received.append(dto))

    view_model._on_device_updated(battery_entity)

    assert isinstance(received[0], str)

    # --- _convert_to_dto ---


def test_convert_to_dto_battery_entity_returns_battery_dto(
        battery_entity: DeviceBatteryInfoEntity,
):
    result = DeviceInfoViewModel._convert_to_dto(battery_entity)
    assert isinstance(result, DeviceBatteryInfoDTO)


def test_convert_to_dto_storage_entity_returns_storage_dto(
        storage_entity: DeviceStorageInfoEntity,
):
    result = DeviceInfoViewModel._convert_to_dto(storage_entity)
    assert isinstance(result, DeviceStorageInfoDTO)


def test_convert_to_dto_general_entity_returns_general_dto(

        device_name_entity: DeviceGeneralInfoEntity,
):
    result = DeviceInfoViewModel._convert_to_dto(device_name_entity)
    assert isinstance(result, DeviceGeneralInfoDTO)


def test_convert_to_dto_unknown_entity_raises_value_error(
        view_model: DeviceInfoViewModel,
):
    unknown_entity = MagicMock()
    with pytest.raises(ValueError, match="Unknown entity type"):
        DeviceInfoViewModel._convert_to_dto(unknown_entity)
