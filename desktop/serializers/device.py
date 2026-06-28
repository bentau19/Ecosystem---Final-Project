from datetime import date

from domain.entities.device_info import DeviceEntity
from serializers.serializer import ISerializer

_DeviceDict = dict[str, object]


class DeviceSerializer(ISerializer[DeviceEntity | None, _DeviceDict | None]):
    """Serializes and deserializes the currently connected device entity.

    Maps between a ``DeviceEntity`` (or ``None`` when no device is present)
    and a plain, JSON-ready dict.  ``last_connected`` is stored as an ISO-8601
    date string (``YYYY-MM-DD``) and parsed back to a :class:`datetime.date`.

    A falsy value (``None`` or empty dict) round-trips to ``None`` so that an
    absent device can be handled without special-case logic in the repository.
    """

    @staticmethod
    def serialize(entity: DeviceEntity | None) -> _DeviceDict | None:
        """Convert a ``DeviceEntity`` to a JSON-ready dict.

        Args:
            entity: The entity to serialize, or ``None`` if no device is
                currently connected.

        Returns:
            A dict of the device's fields ready for ``json.dump``, or ``None``
            when ``entity`` is ``None``.
        """
        if entity is None:
            return None
        return {
            "id": entity.id,
            "name": entity.name,
            "os": entity.os,
            "tag": entity.tag,
            "last_connected": entity.last_connected.isoformat(),
            "battery_level": entity.battery_level,
            "battery_charging": entity.battery_charging,
            "storage_used": entity.storage_used,
            "storage_total": entity.storage_total,
            "ip": entity.ip,
        }

    @staticmethod
    def deserialize(data: _DeviceDict | None) -> DeviceEntity | None:
        """Reconstruct a ``DeviceEntity`` from a JSON dict.

        Args:
            data: A dict of the device's fields as parsed from ``device.json``.
                A falsy value (``None`` or empty dict) is treated as "not found"
                and returns ``None``.

        Returns:
            A ``DeviceEntity`` if ``data`` is non-empty, otherwise ``None``.
        """
        if not data:
            return None
        return DeviceEntity(
            id=str(data["id"]),
            name=str(data["name"]),
            os=str(data["os"]),
            tag=str(data["tag"]),
            last_connected=date.fromisoformat(str(data["last_connected"])),
            battery_level=int(data["battery_level"]),
            battery_charging=bool(data["battery_charging"]),
            storage_used=float(data["storage_used"]),
            storage_total=float(data["storage_total"]),
            ip=str(data["ip"]),
        )
