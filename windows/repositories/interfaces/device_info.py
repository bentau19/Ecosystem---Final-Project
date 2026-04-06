from abc import ABC, abstractmethod
from typing import List, Optional

from PySide6.QtCore import Signal

from entities.device_info import DeviceBaseInfoEntity, DeviceType
from repositories.interfaces.base import IRepository


class IDeviceInfoRepository(IRepository[DeviceBaseInfoEntity, DeviceType], ABC):
    """
    Interface for a device repository.

    Attributes:
        device_info_saved (Signal): Emitted when a device info is added.
        device_info_deleted (Signal): Emitted when a device info is deleted.
    """

    device_info_saved: Signal
    device_info_deleted: Signal

    @abstractmethod
    def get_by_id(self, id: DeviceType) -> Optional[DeviceBaseInfoEntity]:
        """
        Get a device info by its ID.

        Args:
            id: The ID of the device info.

        Returns:
            The device info with the given ID, or None if it does not exist.
        """
        ...

    @abstractmethod
    def get_all(self) -> List[DeviceBaseInfoEntity]:
        """
        Get all device infos.

        Returns:
            A list of all device infos.
        """
        ...


    @abstractmethod
    def save(self, entity: DeviceBaseInfoEntity) -> None:
        """
        save a device info in the repository.

        Args:
            entity: The updated device info.
        """
        ...

    @abstractmethod
    def delete(self, id: DeviceType) -> None:
        """
        Delete a device info from the repository.

        Args:
            id: The ID of the device info to delete.
        """
        ...
