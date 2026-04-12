from abc import ABC, abstractmethod

from PySide6.QtCore import Signal

from entities.device_info import DeviceBaseInfoEntity, DeviceType
from repositories.interfaces.base import IRepository


class IDeviceInfoRepository(IRepository[DeviceBaseInfoEntity, DeviceType], ABC):
    """Abstract interface for the device-information repository.

    Signals:
        device_info_saved: Emitted when a device info is added or updated.
        device_info_deleted: Emitted when a device info is deleted.
    """

    device_info_saved: Signal
    device_info_deleted: Signal

    @abstractmethod
    def get_by_id(self, id: DeviceType) -> DeviceBaseInfoEntity | None:
        """Return the device info for the given DeviceType, or ``None``.

        Args:
            id: The DeviceType key to look up.

        Returns:
            The DeviceBaseInfoEntity for the given type, or ``None`` if not found.
        """
        ...

    @abstractmethod
    def get_all(self) -> list[DeviceBaseInfoEntity]:
        """Return all stored device-information entities.

        Returns:
            A list of all DeviceBaseInfoEntity objects.
        """
        ...

    @abstractmethod
    def save(self, entity: DeviceBaseInfoEntity) -> None:
        """Persist a device-information entity to the repository.

        Args:
            entity: The device information to save (insert or update).
        """
        ...

    @abstractmethod
    def delete(self, id: DeviceType) -> None:
        """Remove a device-information entity by DeviceType key.

        Args:
            id: The DeviceType key of the entity to delete.
        """
        ...
