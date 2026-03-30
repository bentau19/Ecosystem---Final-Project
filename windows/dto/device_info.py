from dataclasses import dataclass
from enum import IntEnum

from enums.device_type import DeviceType


@dataclass
class DeviceBaseInfoDTO:
    """
    Base information shared across all device detail views.

    Attributes:
        title (str): The display name of the device.
        icon_path (str): The path to the device icon.
        icon_background_color (str): The background color of the icon.
    """
    title: str
    icon_path: str
    icon_background_color: str
    type: DeviceType


@dataclass
class DeviceBatteryInfoDTO(DeviceBaseInfoDTO):
    """
    Battery status information for a device.

    Attributes:
        battery_percentage (int): Current battery level (0–100).
        is_charging (bool): Whether the device is currently charging.
    """
    battery_percentage: int
    is_charging: bool


@dataclass
class DeviceStorageInfoDTO(DeviceBaseInfoDTO):
    """
    Storage usage information for a device.

    Attributes:
        used_storage (int): Used storage in bytes.
        total_storage (int): Total storage capacity in bytes.
    """
    used_storage: int
    total_storage: int


@dataclass
class DeviceGeneralInfoDTO(DeviceBaseInfoDTO):
    """
    General descriptive information for a device.

    Attributes:
        description (str): A description of the device.
    """
    description: str
