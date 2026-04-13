from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from dto.device_info import (
    DeviceInfoDTO,
    DeviceNameDTO,
    DeviceOSDTO,
    DeviceIPDTO,
    DeviceBatteryDTO,
    DeviceStorageDTO,
    DeviceIDDTO,
)
from entities.device_info import (
    DeviceInfoEntity,
    DeviceNameEntity,
    DeviceOSEntity,
    DeviceIPEntity,
    DeviceBatteryEntity,
    DeviceStorageEntity,
    DeviceIDEntity,
)
from enums.device_type import DeviceType
from utils.repository_manger import repository_manager


class DeviceInfoViewModel(QObject):
    """ViewModel for the connected device info dashboard.

    Signals:
        device_info_added:   Emitted with a DeviceInfoDTO when an entity is saved.
        device_info_deleted: Emitted with the DeviceType key when an entity is deleted.
        device_infos_loaded: Emitted with a list of DeviceInfoDTOs on initial load.
    """

    device_info_added: Signal = Signal(object)
    device_info_deleted: Signal = Signal(object)
    device_infos_loaded: Signal = Signal(list)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize the ViewModel and wire up repository signals.

        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._repo = repository_manager.device_repository
        self._repo.entity_saved.connect(self._on_entity_saved)
        self._repo.entity_deleted.connect(self._on_entity_deleted)

    def load_device_infos(self) -> None:
        """Load all stored device info entities and emit ``device_infos_loaded``."""
        dtos = [self._to_dto(entity) for entity in self._repo.get_all()]
        self.device_infos_loaded.emit(dtos)

    @Slot(object)
    def _on_entity_saved(self, entity: DeviceInfoEntity) -> None:
        """Forward a repository save event to the view as a DTO.

        Args:
            entity: The saved DeviceInfoEntity.
        """
        self.device_info_added.emit(self._to_dto(entity))

    @Slot(object)
    def _on_entity_deleted(self, device_type: DeviceType) -> None:
        """Forward a repository delete event to the view.

        Args:
            device_type: The DeviceType key of the deleted entity.
        """
        self.device_info_deleted.emit(device_type)

    @staticmethod
    def _to_dto(entity: DeviceInfoEntity) -> DeviceInfoDTO:
        """Convert a DeviceInfoEntity subclass to its matching DTO.

        Args:
            entity: The entity to convert.

        Returns:
            The corresponding DeviceInfoDTO subclass instance.

        Raises:
            ValueError: If the entity type is not recognized.
        """

        if not isinstance(entity, DeviceInfoEntity):
            raise ValueError(f"Unknown DeviceInfoEntity subclass: {type(entity)}")
        base = (entity.title, entity.icon_path, entity.type)
        if isinstance(entity, DeviceNameEntity):
            return DeviceNameDTO(*base, name=entity.name)
        if isinstance(entity, DeviceOSEntity):
            return DeviceOSDTO(*base, os=entity.os)
        if isinstance(entity, DeviceIPEntity):
            return DeviceIPDTO(*base, ip=entity.ip)
        if isinstance(entity, DeviceBatteryEntity):
            return DeviceBatteryDTO(*base, level=entity.level, is_charging=entity.is_charging)
        if isinstance(entity, DeviceStorageEntity):
            return DeviceStorageDTO(*base, used=entity.used, total=entity.total)
        if isinstance(entity, DeviceIDEntity):
            return DeviceIDDTO(*base, device_id=entity.device_id)
        raise ValueError(f"Unknown DeviceInfoEntity subclass: {type(entity)}")
