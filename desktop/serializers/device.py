from datetime import datetime, date
from entities.device_info import DeviceEntity
from serializers.interfaces.base import ISerializer


class DeviceSerializer(ISerializer[DeviceEntity | None, dict]):
    """Serializes and deserializes the currently connected device entity.

    Maps between a ``PreviousDeviceEntity`` (or ``None`` when no device is
    connected) and its JSON-safe dictionary representation.

    An empty dict (``{}``) round-trips to ``None`` so that an absent device
    can be stored as an empty JSON object without any special-case logic in
    the store.
    """

    def serialize(self, entity: DeviceEntity | None) -> tuple[
                                                            str, str, str, str, str, int, bool, int, int, str] | None:
        """Convert a PreviousDeviceEntity to a JSON-serializable dictionary.

        Args:
            entity: The entity to serialize, or ``None`` if no device is
                currently connected.

        Returns:
            A plain dict suitable for ``json.dump``, or ``{}`` when ``data``
            is ``None``.
        """
        if entity is None:
            return None
        return (entity.id, entity.name, entity.os, entity.tag, entity.last_connected.isoformat(),
                entity.battery_level, entity.battery_charging, entity.storage_used,
                entity.storage_total, entity.ip)

    def deserialize(self, db_row: tuple) -> DeviceEntity | None:
        """Reconstruct a PreviousDeviceEntity from a plain dictionary.

        Args:
            db_row: A plain dict loaded via ``json.load``.  An empty dict is
                treated as "no current device" and returns ``None``.

        Returns:
            A ``PreviousDeviceEntity`` if ``data`` is non-empty, otherwise
            ``None``.
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
