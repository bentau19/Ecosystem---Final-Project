from dataclasses import asdict
from typing import Dict, Type

from entities.device_info import DeviceType, DeviceBaseInfoEntity, DeviceStorageInfoEntity, DeviceBatteryInfoEntity, \
    DeviceGeneralInfoEntity
from serializers.interfaces.base import ISerializer


class DeviceInfoSerializer(ISerializer[Dict[DeviceType, DeviceBaseInfoEntity], dict]):
    """
    Serializer for device information entities.

    Attributes:
        TYPE_MAP: A dictionary mapping device types to their corresponding entity types.
    """

    TYPE_MAP: Dict[int, Type[DeviceBaseInfoEntity]] = {
        DeviceType.DEVICE_NAME.value: DeviceGeneralInfoEntity,
        DeviceType.DEVICE_TYPE.value: DeviceGeneralInfoEntity,
        DeviceType.BATTERY.value: DeviceBatteryInfoEntity,
        DeviceType.STORAGE.value: DeviceStorageInfoEntity,
    }

    def serialize(self, data: Dict[DeviceType, DeviceBaseInfoEntity]) -> dict:
        """
        Serialize device information entities to a dictionary.

        Args:
            data: The device information entities to serialize.

        Returns:
            The serialized device information entities.
        """
        return {k.value: asdict(v) for k, v in data.items()}

    def deserialize(self, data: dict) -> Dict[DeviceType, DeviceBaseInfoEntity]:
        """
        Deserialize device information entities from a dictionary.

        Args:
            data: The serialized device information entities.

        Returns:
            The deserialized device information entities.
        """
        return {DeviceType(int(k)): self.TYPE_MAP[int(k)](**v) for k, v in data.items()}
