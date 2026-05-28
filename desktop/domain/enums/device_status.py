from enum import StrEnum


class DeviceStatus(StrEnum):
    """Connection status of a previously paired device on the login screen."""
    RECENT = "recent"
    IDLE = "idle"
