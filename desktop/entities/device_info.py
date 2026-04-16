from dataclasses import dataclass
from datetime import date


@dataclass
class DeviceEntity:
    """Canonical domain object representing a connected Android device.

    Populated by the device repository and consumed by view-models.
    All timestamps are stored as :class:`datetime.date` values; human-readable
    formatting is the responsibility of the DTO layer.

    Attributes:
        id (str): Unique device identifier (UUID or similar).
        name (str): Human-readable device name, e.g. ``"Pixel 8 Pro"``.
        os (str): OS version string, e.g. ``"Android 14"``.
        tag (str): User-assigned label, e.g. ``"Home"``.
        last_connected (date): Calendar date of the most recent connection.
        battery_level (int): Battery percentage in the range 0–100.
        battery_charging (bool): ``True`` if the device is currently charging.
        storage_used (int): Used storage in bytes.
        storage_total (int): Total storage capacity in bytes.
        ip (str): IPv4 or IPv6 address of the device on the local network.
    """

    id: str
    name: str
    os: str
    tag: str
    last_connected: date
    battery_level: int
    battery_charging: bool
    storage_used: int
    storage_total: int
    ip: str
