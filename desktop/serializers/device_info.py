from dataclasses import asdict
from typing import Dict, Type

from entities.device_info import (
    DeviceInfoEntity,
    DeviceNameEntity,
    DeviceOSEntity,
    DeviceIPEntity,
    DeviceBatteryEntity,
    DeviceStorageEntity,
    DeviceIDEntity,
)
from enums.device_type import DeviceType
from serializers.interfaces.base import ISerializer


class DeviceInfoSerializer(ISerializer[Dict[DeviceType, DeviceInfoEntity], dict]):
    """Serializer for device information entities.

    Maps between a ``{DeviceType: DeviceInfoEntity}`` dict and its JSON
    representation, using ``TYPE_MAP`` to reconstruct the correct subclass
    on deserialization.

    Attributes:
        TYPE_MAP: Maps each DeviceType integer key to its concrete entity class.
    """

    TYPE_MAP: Dict[int, Type[DeviceInfoEntity]] = {
        DeviceType.NAME.value:      DeviceNameEntity,
        DeviceType.OS.value:        DeviceOSEntity,
        DeviceType.IP.value:        DeviceIPEntity,
        DeviceType.BATTERY.value:   DeviceBatteryEntity,
        DeviceType.STORAGE.value:   DeviceStorageEntity,
        DeviceType.DEVICE_ID.value: DeviceIDEntity,
    }

    def serialize(self, data: Dict[DeviceType, DeviceInfoEntity]) -> dict:
        """Convert a device info dict to a plain JSON-serializable dictionary.

        Args:
            data: Mapping of DeviceType keys to DeviceInfoEntity instances.

        Returns:
            A dictionary keyed by the integer DeviceType value.
        """
        return {k.value: asdict(v) for k, v in data.items()}

    def deserialize(self, data: dict) -> Dict[DeviceType, DeviceInfoEntity]:
        """Reconstruct a device info dict from a plain dictionary.

        Args:
            data: A dictionary keyed by integer DeviceType values.

        Returns:
            A mapping of DeviceType keys to the correct DeviceInfoEntity subclass.
        """
        return {
            DeviceType(int(k)): self.TYPE_MAP[int(k)](**v)
            for k, v in data.items()
        }
