import os
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal

from domain.entities.device_info import DeviceEntity
from repositories.repository import IRepository
from serializers.device import DeviceSerializer
from utils.db import sqlite_connection
from utils.meta import ABCQObjectMeta


class DeviceRepository(
    IRepository[DeviceEntity, str], QObject, metaclass=ABCQObjectMeta
):
    """Repository for the currently connected device.

    Holds at most one ``PreviousDeviceEntity`` in memory — the device that is
    actively connected right now.  Data is loaded from the backing store on
    construction and every mutation flushes the cache back to disk.

    Signals:
        entity_saved:   Emitted with the saved ``PreviousDeviceEntity`` after a
            successful ``save`` call.
        entity_deleted: Emitted with the device ID (``str``) after ``delete``
            or ``clear`` completes.
    """

    entity_saved: Signal = Signal(object)
    entity_deleted: Signal = Signal(str)

    def __init__(
            self,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the repository and eagerly load data from the store.

        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)

        self._serializer = DeviceSerializer()
        # Frozen (PyInstaller): write to %APPDATA%\SyncDose\ which is always
        # writable without admin rights.  Source dev: write to desktop/data/ so
        # the database is easy to find next to the code.
        if getattr(sys, "frozen", False):
            self._db_path = Path(os.environ["APPDATA"]) / "SyncDose" / "app.db"
        else:
            self._db_path = Path(__file__).parent.parent / "data" / "app.db"

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path.touch(exist_ok=True)
        self._configure_db()

    def _configure_db(self) -> None:
        # Create the devices table if it does not already exist.
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS devices "
                               "(id TEXT PRIMARY KEY, name TEXT,"
                               " os TEXT, tag TEXT, last_connected DATETIME, battery_level INTEGER,"
                               " battery_charging BOOLEAN, storage_used REAL,"
                               " storage_total REAL, ip TEXT)")

    def id_exists(self, id: str) -> bool:
        """Check whether a device with the given ID exists in the database.

        Args:
            id: The device UUID to look up.

        Returns:
            ``True`` if a matching row exists, ``False`` otherwise.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM devices WHERE id = ?", (id,))
                return cursor.fetchone() is not None

    def get_by_id(self, id: str) -> DeviceEntity | None:
        """Return the current device if its ID matches, otherwise ``None``.

        Args:
            id: The device ID to look up.

        Returns:
            The current ``PreviousDeviceEntity`` if its ``id`` equals the
            argument, otherwise ``None``.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM devices WHERE id = ?", (id,))
                row = cursor.fetchone()
                return self._serializer.deserialize(row)

    def get_all(self) -> list[DeviceEntity]:
        """Return the current device as a single-element list, or empty.

        Returns:
            A list containing the current device, or ``[]`` if none is set.
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM devices")
                rows = cursor.fetchall()
                return [
                    entity
                    for row in rows
                    if (entity := self._serializer.deserialize(row)) is not None
                ]

    def save(self, entity: DeviceEntity) -> None:
        """Set the current device and flush to disk.

        Args:
            entity: The device to persist as the currently connected device.

        Emits:
            entity_saved: With the saved entity after the store write.
        """

        with sqlite_connection(self._db_path) as conn:
            row: tuple[str, str, str, str, str, int, bool, float, float, str] | None = self._serializer.serialize(entity)
            if row is None:
                return
            with conn:
                cursor = conn.cursor()
                cursor.execute("REPLACE INTO devices (id, name, os, tag, last_connected, battery_level,"
                               " battery_charging, storage_used, storage_total, ip) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               row)
            self.entity_saved.emit(entity)

    def delete(self, id: str) -> None:
        """Clear the current device if its ID matches and flush to disk.

        Args:
            id: The device ID to remove.

        Emits:
            entity_deleted: With ``id`` after the store write (or immediately
                if no matching device was set).
        """
        with sqlite_connection(self._db_path) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM devices WHERE id = ?", (id,))
            self.entity_deleted.emit(id)
