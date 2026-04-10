from dataclasses import dataclass

from enums.device_status import DeviceStatus


@dataclass
class PreviousDeviceEntity:
    """Represents a previously connected device shown on the login screen.

    Attributes:
        id: Unique device identifier.
        name: Human-readable device name, e.g. ``"Pixel 8 Pro"``.
        os_label: OS version string, e.g. ``"Android 14"``.
        tag: User-assigned label, e.g. ``"Home"``.
        icon_color: Hex colour used for the device icon background.
        status: Current connection status of the device.
        last_seen: Human-readable recency string, e.g. ``"now"``, ``"today"``,
            ``"3 days ago"``.
    """

    id: str
    name: str
    os_label: str
    tag: str
    icon_color: str
    status: DeviceStatus
    last_seen: str
