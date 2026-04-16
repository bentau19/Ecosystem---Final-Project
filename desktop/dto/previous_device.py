from dataclasses import dataclass
from datetime import date


@dataclass
class PreviousDeviceDTO:
    """Data Transfer Object for a previously connected device.

    Consumed exclusively by the view layer — no entity or repository
    types must leak into this dataclass.

    Attributes:
        id (str): Unique device identifier.
        name (str): Human-readable device name, e.g. ``"Pixel 8 Pro"``.
        os (str): OS version string, e.g. ``"Android 14"``.
        tag (str): User-assigned label, e.g. ``"Home"``.
        last_connected (date): Calendar date of the most recent connection.
    """

    id: str
    name: str
    os: str
    tag: str
    last_connected: date
