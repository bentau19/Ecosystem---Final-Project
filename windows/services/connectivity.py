"""
Device connectivity service.

Manages the TauSync TCP connection lifecycle on a background thread,
emitting Qt signals when a device connects or disconnects.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from tausync_py import TauSync


class ConnectivityService(QObject):
    """Manages the TauSync device connection lifecycle.

    Spawns a background thread to listen for an incoming TCP connection
    without blocking the UI thread. Uses threading.Thread (not QThread)
    because TauSync makes blocking .NET async calls via pythonnet — running
    those from a QThread (a Qt-managed native thread) corrupts the CLR stack
    and causes a fatal 0xC0000409 crash.

    PySide6 handles cross-thread signal emission automatically via queued
    connections, so Signal.emit() from a threading.Thread is safe.

    Singleton — use ConnectivityService() to get the shared instance.

    Attributes:
        device_connected (Signal): Emitted when a remote device connects.
        device_disconnected (Signal): Emitted after dispose() completes.
        connection_error (Signal[str]): Emitted if the connection attempt fails.
    """


    device_connected = Signal()
    device_disconnected = Signal()
    connection_error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Initialize ConnectivityService and immediately start listening.

        No-op on subsequent calls — initialization runs exactly once.

        Args:
            parent: Optional parent QObject for memory management.
        """


        self._initialized = True
        super().__init__(parent)
        self._tau = TauSync()

        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self) -> None:
        """Block until a remote device connects, then emit device_connected.

        Runs on a background threading.Thread. Emits connection_error on
        failure so the error surfaces to the UI instead of being swallowed.
        """
        try:
            self._tau.listen()
            self.device_connected.emit()
        except Exception as exc:
            self.connection_error.emit(str(exc))

    def connect_to_device(self, ip: str) -> None:
        """Connect to a remote device by IP address.

        Args:
            ip: The IP address of the remote TauSync server.
        """
        self._tau.connect_to(ip)
        self.device_connected.emit()

    def disconnect_device(self) -> None:
        """Dispose the TauSync connection and emit device_disconnected.

        Blocks briefly to let the background thread finish cleanly.
        """
        self._tau.dispose()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        self.device_disconnected.emit()
