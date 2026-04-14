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
class DeviceIPDTO(DeviceInfoDTO):
    """DTO for the IP address card.

    Attributes:
        ip: The device's LAN IP address.
    """

    ip: str


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
        used:  Used storage in bytes.
        total: Total storage capacity in bytes.
    """

    used: int
    total: int


@dataclass
class DeviceIDDTO(DeviceInfoDTO):
    """DTO for the stable device identifier.

    Not rendered as a dashboard card — used internally by ViewModels
    that need to key records by a stable device identity.

    Attributes:
        device_id: The stable unique device identifier (e.g. Android ID).
    """

    device_id: str
