import platform
import socket

from tausync_py import TauSync


def get_ip() -> str:
    """Return the local machine's primary LAN IP address.

    Resolves the OS-assigned hostname to its IPv4 address via the system's
    name resolver.

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


def get_ip_by_hostname(hostname: str) -> str:
    """Resolve a hostname to its IPv4 address.

    Args:
        hostname: DNS name or NetBIOS name of the target machine.

    Returns:
        A dotted-decimal IPv4 string (e.g. ``"192.168.1.20"``).
    """
    ip = socket.gethostbyname(hostname)
    return ip


def read_string_from_channel(
        tau: TauSync,
        channel: str,
        timeout_seconds: int | None = None,
) -> str:
    """Open a named TauSync channel, read all incoming data, and return it as a string.

    Opens the stream via a meeting-word handshake, reads until the remote peer
    closes its end (EOF), decodes the bytes as UTF-8, and closes the stream.

    Args:
        tau: An already-connected ``TauSync`` instance (``listen()`` or
            ``connect_to()`` must have been called beforehand).
        channel: The meeting-word that identifies the channel
            (e.g. ``Channel.DEVICE_INFO``).  Both sides must use the same word.
        timeout_seconds: Optional seconds to wait for the meeting-word handshake.
            ``None`` blocks indefinitely.  Raises ``TimeoutError`` if the peer
            does not connect within the allotted time.

    Returns:
        The full payload decoded as a UTF-8 string.

    Raises:
        TimeoutError: If *timeout_seconds* is set and the peer does not connect
            in time.
    """
    with tau.connect(str(channel), timeout_seconds=timeout_seconds) as stream:
        return stream.read_all().decode("utf-8")


def write_string_to_channel(
        tau: TauSync,
        channel: str,
        data: str,
        timeout_seconds: int | None = None,
) -> None:
    """Open a named TauSync channel, write *data*, flush, and close.

    Encodes *data* as UTF-8, writes the full payload into the channel, flushes
    the underlying stream, then closes it so the remote peer receives EOF.

    Args:
        tau: An already-connected ``TauSync`` instance (``listen()`` or
            ``connect_to()`` must have been called beforehand).
        channel: The meeting-word that identifies the channel
            (e.g. ``Channel.DEVICE_INFO``).  Both sides must use the same word.
        data: UTF-8 string payload to send (e.g. a serialized JSON object).
        timeout_seconds: Optional seconds to wait for the meeting-word handshake.
            ``None`` blocks indefinitely.  Raises ``TimeoutError`` if the peer
            does not connect within the allotted time.

    Raises:
        TimeoutError: If *timeout_seconds* is set and the peer does not connect
            in time.
    """
    with tau.connect(str(channel), timeout_seconds=timeout_seconds) as stream:
        stream.write_string(data)
        stream.flush()
