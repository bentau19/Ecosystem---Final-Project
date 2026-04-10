from dataclasses import dataclass

from enums.device_status import DeviceStatus


@dataclass
class PreviousDeviceDTO:
    """Data Transfer Object for a previously connected device.

    Consumed exclusively by the view layer — no entity or repository
    types must leak into this dataclass.

    Attributes:
        id (str): Unique device identifier.
        name (str): Human-readable device name, e.g. ``"Pixel 8 Pro"``.
        os_label (str): OS version string, e.g. ``"Android 14"``.
        tag (str): User-assigned label, e.g. ``"Home"``.
        icon_color (str): Hex colour used for the device icon background.
        status (DeviceStatus): Current connection status.
        last_seen (str): Human-readable timestamp, e.g. ``"now"``, ``"today"``,
            ``"3 days ago"``.
    """

    id: str
    name: str
    os_label: str
    tag: str
    icon_color: str
    status: DeviceStatus
    last_seen: str
