from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal

from entities.device_info import DeviceBaseInfoEntity, DeviceType
from repositories.interfaces.device_info import IDeviceInfoRepository
from stores.device_info import DeviceInfoStore
from stores.interfaces.base import IStore
from utils.meta import ABCQObjectMeta


class DeviceInfoRepository(IDeviceInfoRepository, QObject, metaclass=ABCQObjectMeta):
    """
    Repository for device information.

    Attributes:
        device_info_saved (Signal): Emitted when device information is added.
        device_info_deleted (Signal): Emitted when device information is deleted.
    """

    device_info_saved: Signal = Signal(object)

    device_info_deleted: Signal = Signal(object)

    def __init__(self, store: IStore = DeviceInfoStore(), parent: Optional[QObject] = None) -> None:
        """
        Initialize the device repository.

        Args:
            parent: The parent QObject.
        """
        super().__init__(parent)

        self._store: IStore = store

        self._data: Dict[DeviceType, DeviceBaseInfoEntity] = self.load()

    def load(self) -> Dict[DeviceType, DeviceBaseInfoEntity]:
        """
        Load device information from the store.

        Returns:
            A dictionary mapping device types to device information entities.
        """
        return self._store.load()

    def get_by_id(self, id: DeviceType) -> Optional[DeviceBaseInfoEntity]:
        """
        Get device information by ID.

        Args:
            id: The ID of the device information.

        Returns:
            The device information with the given ID, or None if it does not exist.
        """
        return self._data.get(id, None)

    def get_all(self) -> list[DeviceBaseInfoEntity]:
        """
        Get all device information.

        Returns:
            A list of all device information.
        """
        return list(self._data.values())

    def save(self, entity: DeviceBaseInfoEntity) -> None:
        """
        Add device information to the repository.

        Args:
            entity: The device information to add.
        """
        if entity.type not in DeviceType:
            raise ValueError(f"Invalid device type: '{entity.type}'")

        self._data[entity.type] = entity
        self.device_info_saved.emit(entity)
        self._store.save(self._data)

    def delete(self, id: DeviceType) -> None:
        """
        Delete device information from the repository.

        Args:
            id: The ID of the device information to delete.
        """
        if id not in self._data:
            raise ValueError(f"Device with title '{id}' does not exist.")
        del self._data[id]
        self.device_info_deleted.emit(id)
        self._store.save(self._data)
