from dataclasses import asdict

from entities.previous_device import PreviousDeviceEntity
from enums.device_status import DeviceStatus
from serializers.interfaces.base import ISerializer


class PreviousDeviceSerializer(ISerializer[dict[str, PreviousDeviceEntity], dict]):
    """Serializes and deserializes PreviousDeviceEntity objects to and from plain dicts.

    The on-disk format is a flat JSON object keyed by device ID::

        {
            "dev-001": { "id": "dev-001", "name": "Pixel 8 Pro", ... },
            ...
        }
    """

    def serialize(self, data: dict[str, PreviousDeviceEntity]) -> dict:
        """Convert a mapping of PreviousDeviceEntity objects to a JSON-safe dict.

        Args:
            data: Mapping of device ID → PreviousDeviceEntity.

        Returns:
            A plain dict suitable for ``json.dump``.
        """
        # asdict() calls copy.deepcopy on non-dataclass fields such as the
        # DeviceStatus enum.  Because DeviceStatus is a StrEnum its instances
        # ARE str objects, so json.dump can serialise them without a custom
        # encoder.
        return {device_id: asdict(entity) for device_id, entity in data.items()}

    def deserialize(self, data: dict) -> dict[str, PreviousDeviceEntity]:
        """Reconstruct a mapping of PreviousDeviceEntity objects from a plain dict.

        Args:
            data: A plain dict loaded via ``json.load``.

        Returns:
            Mapping of device ID → PreviousDeviceEntity.
        """
        result: dict[str, PreviousDeviceEntity] = {}
        for device_id, fields in data.items():
            # json.load returns the status as a plain str; reconstruct the enum.
            entity_fields = {**fields, "status": DeviceStatus(fields["status"])}
            result[device_id] = PreviousDeviceEntity(**entity_fields)
        return result
