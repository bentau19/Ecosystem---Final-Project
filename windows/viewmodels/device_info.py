from PySide6.QtCore import QObject, Signal, Slot

from dto.device_info import DeviceBaseInfoDTO, DeviceBatteryInfoDTO, DeviceStorageInfoDTO, DeviceGeneralInfoDTO, \
    DeviceType
from entities.device_info import DeviceBaseInfoEntity, DeviceBatteryInfoEntity, DeviceStorageInfoEntity, \
    DeviceGeneralInfoEntity
from utils.app_state import app_state


class DeviceInfoViewModel(QObject):
    """
    ViewModel for the DeviceView.

    Attributes:
        device_info_updated (Signal): Emitted when device info is updated.
        device_info_added (Signal): Emitted when device info is added.
        device_info_deleted (Signal): Emitted when device info is deleted.
        device_infos_loaded (Signal): Emitted when device infos are loaded.
    """
    device_info_updated: Signal = Signal(object)

    device_info_added: Signal = Signal(object)

    device_info_deleted: Signal = Signal(object)

    device_infos_loaded: Signal = Signal(list)

    def __init__(self, parent: QObject = None) -> None:
        """
        Initialize the controller with a view and a model.

        Args:
            parent: The parent QObject.
        """
        super().__init__(parent)
        self._repo = app_state.device_repository

        self._repo.device_info_saved.connect(self._on_device_added)
        self._repo.device_info_deleted.connect(self._on_device_deleted)

    def load_device_infos(self) -> None:
        """
        Load the devices from the repository and emit the device_loaded signal.
        """
        device_infos_dto = [self._convert_to_dto(entity) for entity in self._repo.get_all()]
        self.device_infos_loaded.emit(device_infos_dto)

    @Slot(DeviceBaseInfoEntity)
    def _on_device_updated(self, entity: DeviceBaseInfoEntity) -> None:
        """
        Slot called when a device info is updated.

        Args:
            entity: The updated device info.
        """
        device_info_dto = self._convert_to_dto(entity)
        self.device_info_updated.emit(str(device_info_dto))

    @Slot(DeviceBaseInfoEntity)
    def _on_device_added(self, entity: DeviceBaseInfoEntity) -> None:
        """
        Slot called when a device info is added.

        Args:
            entity: The added device info.
        """
        device_info_dto = self._convert_to_dto(entity)
        self.device_info_added.emit(device_info_dto)

    @Slot(DeviceType)
    def _on_device_deleted(self, id: DeviceType) -> None:
        """
        Slot called when a device info is deleted.

        Args:
            id: The ID of the deleted device info.
        """
        self.device_info_deleted.emit(id)

    @staticmethod
    def _convert_to_dto(entity: DeviceBaseInfoEntity) -> DeviceBaseInfoDTO:
        """
        Convert a device info entity to a device info DTO.

        Args:
            entity: The device info entity to convert.

        Returns:
            The converted device info DTO.

        Raises:
            ValueError: If the entity type is unknown.
        """
        if isinstance(entity, DeviceBatteryInfoEntity):
            return DeviceBatteryInfoDTO(entity.title, entity.icon_path, entity.icon_background_color,
                                        entity.type, entity.battery_percentage, entity.is_charging)
        elif isinstance(entity, DeviceStorageInfoEntity):
            return DeviceStorageInfoDTO(entity.title, entity.icon_path, entity.icon_background_color,
                                        entity.type, entity.used_storage, entity.total_storage)
        elif isinstance(entity, DeviceGeneralInfoEntity):
            return DeviceGeneralInfoDTO(entity.title, entity.icon_path, entity.icon_background_color,
                                        entity.type, entity.description)
        else:
            raise ValueError(f"Unknown entity type: {type(entity)}")
