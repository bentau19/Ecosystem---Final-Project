from dataclasses import dataclass


@dataclass
class DeviceInfoDTO:
    """Base DTO shared by all device info card views.

    Attributes:
        title:     Display label shown on the card.
        icon_path: Qt virtual path to the card's icon.
    """

    title: str
    icon_path: str


@dataclass
class DeviceNameDTO(DeviceInfoDTO):
    """DTO for the device name card.

    Attributes:
        name: Human-readable device name.
    """

    name: str


@dataclass
class DeviceOSDTO(DeviceInfoDTO):
    """DTO for the operating system card.

    Attributes:
        os: OS identifier string.
    """

    os: str


@dataclass
class DeviceBatteryDTO(DeviceInfoDTO):
    """DTO for the battery status card.

    Attributes:
        level:       Current battery level (0–100).
        is_charging: Whether the device is currently charging.
    """

    level: int
    is_charging: bool


@dataclass
class DeviceStorageDTO(DeviceInfoDTO):
    """DTO for the storage usage card.

    Attributes:
        used:  Used storage in GB.
        total: Total storage capacity in GB.
    """

    used: float
    total: float

