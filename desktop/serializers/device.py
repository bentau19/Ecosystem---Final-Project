from datetime import datetime
from domain.entities.device_info import DeviceEntity
from serializers.serializer import ISerializer

_DeviceRow = tuple[str, str, str, str, str, int, bool, float, float, str]


class DeviceSerializer(ISerializer[DeviceEntity | None, _DeviceRow | None]):
    """Serializes and deserializes the currently connected device entity.

    Maps between a ``DeviceEntity`` (or ``None`` when no device is present)
    and its SQLite row tuple representation
    ``(id, name, os, tag, last_connected, battery_level, battery_charging,
    storage_used, storage_total, ip)``.

    A falsy row (``None`` or empty tuple) round-trips to ``None`` so that
    absent devices can be handled without special-case logic in the repository.
    """

    @staticmethod
    def serialize(entity: DeviceEntity | None) -> _DeviceRow | None:
        """Convert a ``DeviceEntity`` to a SQLite row tuple.

        Args:
            entity: The entity to serialize, or ``None`` if no device is
                currently connected.

        Returns:
            A tuple ``(id, name, os, tag, last_connected, battery_level,
            battery_charging, storage_used, storage_total, ip)`` suitable for
            ``cursor.execute``, or ``None`` when ``entity`` is ``None``.
        """
        if entity is None:
            return None
        return (entity.id, entity.name, entity.os, entity.tag, entity.last_connected.isoformat(),
                entity.battery_level, entity.battery_charging, entity.storage_used,
                entity.storage_total, entity.ip)

    @staticmethod
    def deserialize(db_row: _DeviceRow | tuple | None) -> DeviceEntity | None:
        """Reconstruct a ``DeviceEntity`` from a SQLite row tuple.

        Args:
            db_row: A tuple with columns ``(id, name, os, tag, last_connected,
                battery_level, battery_charging, storage_used, storage_total,
                ip)`` as returned by ``cursor.fetchone()``.  A falsy value
                (``None`` or empty tuple) is treated as "not found" and returns
                ``None``.

        Returns:
            A ``DeviceEntity`` if ``db_row`` is non-empty, otherwise ``None``.
        """
        if not db_row:
            return None
        return DeviceEntity(
            id=db_row[0],
            name=db_row[1],
            os=db_row[2],
            tag=db_row[3],
            last_connected=datetime.strptime(db_row[4], "%Y-%m-%d").date(),
            battery_level=db_row[5],
            battery_charging=db_row[6],
            storage_used=db_row[7],
            storage_total=db_row[8],
            ip=db_row[9]
        )
