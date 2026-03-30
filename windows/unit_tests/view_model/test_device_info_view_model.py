from unittest.mock import MagicMock, patch

import pytest

from dto.device_info import (
    DeviceBatteryInfoDTO,
    DeviceStorageInfoDTO,
    DeviceGeneralInfoDTO,
    DeviceType,
)
from entities.device_info import (
    DeviceBaseInfoEntity, DeviceBatteryInfoEntity, DeviceStorageInfoEntity, DeviceGeneralInfoEntity,
)


@pytest.fixture()
def mock_repo():
    repo = MagicMock()
    repo.device_info_saved = MagicMock()
    repo.device_info_deleted = MagicMock()
    repo.get_all.return_value = []
    return repo


@pytest.fixture()
def view_model(mock_repo, qapp):
    with patch("view_model.device_info.app_state") as mock_app_state:
        mock_app_state.device_repository = mock_repo
        from view_model.device_info import DeviceViewModel
        vm = DeviceViewModel()
    return vm, mock_repo


class _BaseTest:
    def setup_method(self):
        with patch("view_model.device_info.app_state") as mock_app_state:
            mock_app_state.device_repository = MagicMock(
                device_info_saved=MagicMock(),
                device_info_deleted=MagicMock(),
                get_all=MagicMock(return_value=[]),
            )
            from view_model.device_info import DeviceViewModel
            self.DeviceViewModel = DeviceViewModel

    @staticmethod
    def _make_battery_entity():
        battery_entity: DeviceBatteryInfoEntity = MagicMock(spec=DeviceBatteryInfoEntity)
        battery_entity.title = "Battery"
        battery_entity.icon_path = "icons/battery.png"
        battery_entity.icon_background_color = "#FF0000"
        battery_entity.type = DeviceType.BATTERY
        battery_entity.battery_percentage = 80
        battery_entity.is_charging = True
        return battery_entity

    @staticmethod
    def _make_storage_entity():
        storage_entity = MagicMock(spec=DeviceStorageInfoEntity)

        storage_entity.title = "Storage"
        storage_entity.icon_path = "icons/storage.png"
        storage_entity.icon_background_color = "#00FF00"
        storage_entity.type = DeviceType.STORAGE
        storage_entity.used_storage = 50
        storage_entity.total_storage = 256

        return storage_entity

    @staticmethod
    def _make_general_entity():
        general_entity = MagicMock(spec=DeviceGeneralInfoEntity)

        general_entity.title = "Device Name"
        general_entity.icon_path = "icons/device.png"
        general_entity.icon_background_color = "#0000FF"
        general_entity.type = DeviceType.DEVICE_NAME
        general_entity.description = "My Phone"
        return general_entity


class TestConvertToDto(_BaseTest):
    def test_converts_battery_entity(self):
        entity = self._make_battery_entity()
        dto = self.DeviceViewModel._convert_to_dto(entity)
        print(dto)
        assert isinstance(dto, DeviceBatteryInfoDTO)
        assert dto.battery_percentage == 80
        assert dto.is_charging is True

    def test_converts_storage_entity(self):
        entity = self._make_storage_entity()
        dto = self.DeviceViewModel._convert_to_dto(entity)
        assert isinstance(dto, DeviceStorageInfoDTO)
        assert dto.used_storage == 50
        assert dto.total_storage == 256

    def test_converts_general_entity(self):
        entity = self._make_general_entity()
        dto = self.DeviceViewModel._convert_to_dto(entity)
        assert isinstance(dto, DeviceGeneralInfoDTO)
        assert dto.description == "My Phone"

    def test_raises_for_unknown_entity_type(self):
        unknown = MagicMock(spec=DeviceBaseInfoEntity)
        with pytest.raises(ValueError, match="Unknown entity type"):
            self.DeviceViewModel._convert_to_dto(unknown)


class TestLoadDeviceInfos(_BaseTest):
    def test_emits_all_entities_as_dtos(self, view_model):
        vm, repo = view_model
        battery = self._make_battery_entity()
        storage = self._make_storage_entity()
        repo.get_all.return_value = [battery, storage]

        received = []
        vm.device_infos_loaded.connect(received.append)
        vm.load_device_infos()

        assert len(received) == 1
        dtos = received[0]
        assert len(dtos) == 2
        assert isinstance(dtos[0], DeviceBatteryInfoDTO)
        assert isinstance(dtos[1], DeviceStorageInfoDTO)

    def test_emits_empty_list_when_repo_is_empty(self, view_model):
        vm, repo = view_model
        repo.get_all.return_value = []

        received = []
        vm.device_infos_loaded.connect(received.append)
        vm.load_device_infos()

        assert received == [[]]


class TestOnDeviceAdded(_BaseTest):
    def test_emits_device_info_added_with_dto(self, view_model):
        vm, _ = view_model
        entity = self._make_battery_entity()

        received = []
        vm.device_info_added.connect(received.append)
        vm._on_device_added(entity)

        assert len(received) == 1
        assert isinstance(received[0], DeviceBatteryInfoDTO)

    def test_dto_fields_match_entity(self, view_model):
        vm, _ = view_model
        entity = self._make_storage_entity()

        received = []
        vm.device_info_added.connect(received.append)
        vm._on_device_added(entity)

        dto = received[0]
        assert dto.used_storage == entity.used_storage
        assert dto.total_storage == entity.total_storage


class TestOnDeviceDeleted(_BaseTest):
    def test_emits_device_info_deleted_with_id(self, view_model):
        vm, _ = view_model
        received = []
        vm.device_info_deleted.connect(received.append)
        vm._on_device_deleted(DeviceType.BATTERY)

        assert received == [DeviceType.BATTERY]

    def test_emits_correct_device_type(self, view_model):
        vm, _ = view_model
        received = []
        vm.device_info_deleted.connect(received.append)
        vm._on_device_deleted(DeviceType.STORAGE)

        assert received[0] == DeviceType.STORAGE


class TestOnDeviceUpdated(_BaseTest):
    def test_emits_device_info_updated_as_string(self, view_model):
        vm, _ = view_model
        entity = self._make_general_entity()

        received = []
        vm.device_info_updated.connect(received.append)
        vm._on_device_updated(entity)

        assert len(received) == 1
        assert isinstance(received[0], str)
