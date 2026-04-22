from enum import IntEnum


class DeviceType(IntEnum):
    """
    An enumeration representing the different types of device information.
    """

    # Represents device name information.
    DEVICE_NAME = 0

    # Represents device type information.
    DEVICE_TYPE = 1

    # Represents battery information.
    BATTERY = 2

    # Represents storage information.
    STORAGE = 3
