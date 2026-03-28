from dataclasses import dataclass


@dataclass
class BasicPhoneDetail:
    """
    Represents general information about a phone.

    Attributes:
        title (str): The title of the phone.
        icon_path (str): The path to the icon of the phone.
        icon_background_color (str): The background color of the icon.
    """
    title: str
    icon_path: str
    icon_background_color: str


@dataclass
class BatteryDetail(BasicPhoneDetail):
    """
    Represents battery information about a phone.

    Attributes:
        battery_percentage (int): The battery percentage.
        is_charging (bool): Indicates if the phone is charging.
    """
    battery_percentage: int
    is_charging: bool


@dataclass
class StorageDetail(BasicPhoneDetail):
    """
    Represents storage information about a phone.

    Attributes:
        used_storage (int): The used storage in bytes.
        total_storage (int): The total storage in bytes.
    """
    used_storage: int
    total_storage: int


@dataclass
class DeviceInfoDetail(BasicPhoneDetail):
    """
    Represents device information about a phone.

    Attributes:
        description (str): The description of the phone.
    """
    description: str
