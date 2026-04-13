from dataclasses import dataclass

from enums.device_type import DeviceType


@dataclass
class DeviceInfoEntity:
    """Base class for all device info cards.

    Carries the display configuration (title, icon, color) shared by every
    card, plus the DeviceType key used to identify and store the entity.

    Attributes:
        title:                Display label shown on the dashboard card.
        icon_path:            Qt virtual path to the card's icon.
        type:                 The DeviceType key this card represents.
    """

    title: str
    icon_path: str
    type: DeviceType


@dataclass
class DeviceNameEntity(DeviceInfoEntity):
    """Device name info — received on Channel.DEVICE_INFO.

    Attributes:
        name: Human-readable device name, e.g. ``"Galaxy S23"``.
    """

    name: str


@dataclass
class DeviceOSEntity(DeviceInfoEntity):
    """Operating system info — received on Channel.DEVICE_INFO.

    Attributes:
        os: OS identifier string, e.g. ``"Android 14"``.
    """

    os: str


@dataclass
class DeviceIPEntity(DeviceInfoEntity):
    """Device IP address — received on Channel.DEVICE_INFO.

    Attributes:
        ip: The device's LAN IP address, e.g. ``"192.168.1.42"``.
    """

    ip: str


@dataclass
class DeviceBatteryEntity(DeviceInfoEntity):
    """Live battery state — updated via Channel.BATTERY.

    Attributes:
        level:       Battery level as an integer percentage (0–100).
        is_charging: Whether the device is currently charging.
    """

    level: int
    is_charging: bool


@dataclass
class DeviceStorageEntity(DeviceInfoEntity):
    """Live storage state — updated via Channel.STORAGE.

    Attributes:
        used:  Used storage in bytes.
        total: Total storage capacity in bytes.
    """

    used: int
    total: int


@dataclass
class DeviceIDEntity(DeviceInfoEntity):
    """Stable unique device identifier — received on Channel.DEVICE_INFO.

    Not displayed on the dashboard; used internally to key previous-device
    records so the same physical phone is always recognised across sessions
    regardless of IP changes.

    Attributes:
        device_id: The Android ``ANDROID_ID`` (or equivalent stable ID).
    """

    device_id: str
