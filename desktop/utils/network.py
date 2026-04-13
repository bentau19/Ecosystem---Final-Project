import json
import platform
import socket

from tausync_py import TauSyncStream


def get_ip() -> str:
    """Return the local machine's primary LAN IP address.

    Opens a dummy UDP socket toward a public address to let the OS pick the
    correct outbound interface, then reads the bound local address.  No
    packets are actually sent.

    Returns:
        A dotted-decimal IPv4 string (e.g. ``"192.168.1.10"``).
    """

    return socket.gethostbyname(socket.gethostname())


def get_pc_name() -> str:
    """Return the OS-assigned hostname of this machine.

    Returns:
        The hostname string as reported by the operating system
        (e.g. ``"DESKTOP-ABC123"``).
    """
    return platform.node()


def get_battery_status():
    """Return the device's current battery status as a percentage.

    Returns:
        An integer from 0 to 100 representing the battery level, or None if
        the battery status cannot be determined.
    """
    pass


def get_storage_status():
    pass
