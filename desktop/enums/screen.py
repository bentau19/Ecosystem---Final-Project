from enum import IntEnum


class Screen(IntEnum):
    """Screen identifiers used by the navigation manager to switch views."""

    LOGIN = 0,
    DASHBOARD = 1,
