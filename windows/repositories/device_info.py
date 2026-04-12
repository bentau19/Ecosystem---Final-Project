from typing import Optional

from PySide6.QtCore import QObject, Signal

from entities.device_info import DeviceBaseInfoEntity, DeviceType
from repositories.interfaces.device_info import IDeviceInfoRepository
from stores.device_info import DeviceInfoStore
from stores.interfaces.base import IStore
from utils.meta import ABCQObjectMeta


class DeviceInfoRepository(IDeviceInfoRepository, QObject, metaclass=ABCQObjectMeta):
    """Repository for device base-information entities, keyed by DeviceType.

    Implements the singleton pattern so that a single shared instance is used
    throughout the application.  Data is eagerly loaded from the backing store
    on first construction and kept in an in-memory cache; every mutation
    flushes the full cache back to disk.

    Signals:
        device_info_saved: Emitted with the saved DeviceBaseInfoEntity after a
            successful ``save`` call.
        device_info_deleted: Emitted with the DeviceType key after a successful
            ``delete`` call.
    """

    device_info_saved: Signal = Signal(object)
    device_info_deleted: Signal = Signal(object)

    def __init__(self, store: IStore = DeviceInfoStore(), parent: Optional[QObject] = None) -> None:
        """Initialize the device-info repository.

        Guarded by ``_initialized`` so that the singleton body only runs once
        even if the constructor is called multiple times.

        Args:
            store: Backing store used for file I/O.  Defaults to a fresh
                ``DeviceInfoStore`` instance.
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._store: IStore = store
        self._data: dict[DeviceType, DeviceBaseInfoEntity] = self.load()
        self._initialized = True

    def load(self) -> dict[DeviceType, DeviceBaseInfoEntity]:
        """Load device information from the backing store.

        Returns:
            A dictionary mapping DeviceType keys to DeviceBaseInfoEntity instances.
        """
        return self._store.load()

    def get_by_id(self, id: DeviceType) -> Optional[DeviceBaseInfoEntity]:
        """Return the device information for the given DeviceType, or ``None``.

        Args:
            id: The DeviceType key to look up.

        Returns:
            The DeviceBaseInfoEntity for the given type, or ``None`` if absent.
        """
        return self._data.get(id, None)

    def get_all(self) -> list[DeviceBaseInfoEntity]:
        """Return all stored device-information entities.

        Returns:
            A list of all DeviceBaseInfoEntity objects in the cache.
        """
        return list(self._data.values())

    def save(self, entity: DeviceBaseInfoEntity) -> None:
        """Insert or update a device-information entity and flush to disk.

        Args:
            entity: The device information to persist.

        Raises:
            ValueError: If ``entity.type`` is not a recognised ``DeviceType``
                value (runtime guard against untyped callers passing raw ints).

        Emits:
            device_info_saved: With the saved entity after the store write.
        """
        if entity.type not in DeviceType:  # guards against raw-int values bypassing the type system
            raise ValueError(f"Invalid device type: '{entity.type}'")

        self._data[entity.type] = entity
        self.device_info_saved.emit(entity)
        self._store.save(self._data)

    def delete(self, id: DeviceType) -> None:
        """Remove the device information for the given DeviceType and flush to disk.

        Args:
            id: The DeviceType key to remove.

        Raises:
            ValueError: If no entry exists for the given ``id``.

        Emits:
            device_info_deleted: With the deleted DeviceType key after the store
                write.
        """
        if id not in self._data:
            raise ValueError(f"Device with title '{id}' does not exist.")
        del self._data[id]
        self.device_info_deleted.emit(id)
        self._store.save(self._data)
