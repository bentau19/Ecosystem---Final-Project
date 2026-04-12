from abc import abstractmethod

from PySide6.QtCore import Signal

from entities.previous_device import PreviousDeviceEntity
from repositories.interfaces.base import IRepository


class IPreviousDeviceRepository(IRepository[PreviousDeviceEntity, str]):
    """Abstract interface for the previous-device repository.

    Signals:
        device_saved: Emitted with the saved PreviousDeviceEntity after a
            successful ``save`` call.
        device_deleted: Emitted with the deleted device ID after a
            ``delete`` call.
    """

    device_saved: Signal
    device_deleted: Signal

    @abstractmethod
    def get_by_id(self, id: str) -> PreviousDeviceEntity | None:
        """Return the device with the given ID, or ``None`` if absent.

        Args:
            id: The unique device identifier.

        Returns:
            The matching PreviousDeviceEntity, or ``None`` if not found.
        """
        ...

    @abstractmethod
    def get_all(self) -> list[PreviousDeviceEntity]:
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
