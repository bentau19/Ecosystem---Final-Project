from enum import IntEnum


class DeviceType(IntEnum):
    """Identifies the type of device information held by a DeviceInfoEntity."""

    NAME = 0
    OS = 1
    BATTERY = 2
    STORAGE = 3
