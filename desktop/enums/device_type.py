from enum import IntEnum


class DeviceType(IntEnum):
    """Identifies the type of device information held by a DeviceInfoEntity."""

    NAME = 0
    OS = 1
    IP = 2
    BATTERY = 3
    STORAGE = 4
    DEVICE_ID = 5
