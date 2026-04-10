from abc import abstractmethod
from typing import List, Optional

from PySide6.QtCore import Signal

from entities.previous_device import PreviousDeviceEntity
from repositories.interfaces.base import IRepository


class IPreviousDeviceRepository(IRepository[PreviousDeviceEntity, str]):
    """Interface for the previous-device repository.

    Attributes:
        device_saved (Signal): Emitted with the saved PreviousDeviceEntity after
            a successful ``save`` call.
        device_deleted (Signal): Emitted with the deleted device ID after a
            successful ``delete`` call.
    """

    device_saved: Signal
    device_deleted: Signal

    @abstractmethod
    def get_by_id(self, id: str) -> Optional[PreviousDeviceEntity]:
        """Return the device with the given ID, or ``None`` if absent.

        Args:
            id: The unique device identifier.

        Returns:
            The matching PreviousDeviceEntity, or ``None`` if not found.
        """
        ...

    @abstractmethod
    def get_all(self) -> List[PreviousDeviceEntity]:
        """Return all stored previous devices.

        Returns:
            A list of all PreviousDeviceEntity objects.
        """
        ...

    @abstractmethod
    def save(self, entity: PreviousDeviceEntity) -> None:
        """Persist a device and emit ``device_saved``.

        Args:
            entity: The device to save (insert or update).
        """
        ...

    @abstractmethod
    def delete(self, id: str) -> None:
        """Remove the device with the given ID and emit ``device_deleted``.

        Args:
            id: The unique device identifier to remove.
        """
        ...
