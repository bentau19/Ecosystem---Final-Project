"""
Device connectivity service.

Manages the TauSync TCP connection lifecycle on a background thread,
emitting Qt signals when a device connects or disconnects.
"""
import threading
from typing import Callable

from PySide6.QtCore import QObject, Signal
from tausync_py import TauSync

from utils.decorators import threaded


class ConnectivityService(QObject):
    """Manages the TauSync device connection lifecycle.

    Spawns a background thread to listen for an incoming TCP connection
    without blocking the UI thread. Uses :class:`threading.Thread` rather than
    ``QThread`` because TauSync makes blocking .NET async calls via pythonnet —
    running those from a ``QThread`` (a Qt-managed native thread) corrupts the
    CLR stack and causes a fatal ``0xC0000409`` crash.

    PySide6 handles cross-thread signal emission automatically via queued
    connections, so ``Signal.emit()`` from a ``threading.Thread`` is safe.

    Exposes the underlying :class:`~tausync_py.TauSync` instance via the
    read-only ``tau`` property so that other services (e.g.
    :class:`~services.device_info.DeviceInfoService`) can share the same
    connected transport without owning it.

    Signals:
        device_connected: Emitted when a remote device connects.
        device_disconnected: Emitted after :meth:`disconnect_device` completes.
        connection_error (Signal[str]): Emitted with the exception message if
            the connection attempt fails.
    """

    device_connected = Signal()
    device_disconnected = Signal()
    connection_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the service and inject the device repository.

        The background listener is *not* started automatically so that the
        phone-side connectivity implementation can be wired in before the
        service begins accepting connections. Call :meth:`start_listening`
        explicitly when the application is ready.

        Args:
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._tau: TauSync = TauSync()
        self._threads: list[threading.Thread] = []

    # ── Public read-only access to the transport ──────────────────────────────

    @property
    def tau(self) -> TauSync:
        """The underlying TauSync transport shared with dependent services.

        Returns:
            The :class:`~tausync_py.TauSync` instance owned by this service.
        """
        return self._tau

    # ── Connection lifecycle ───────────────────────────────────────────────────

    def start_listening(self) -> None:
        """Begin waiting for an incoming device connection on a background thread.

        Safe to call from the main thread; the blocking ``TauSync.listen()``
        call runs on a daemon thread so the UI remains responsive.
        """
        self._listen()

    @threaded
    def _listen(self) -> None:
        """Block until a remote device connects, then emit ``device_connected``.

        Runs on a background :class:`threading.Thread`. Emits ``connection_error``
        on failure so the error surfaces to the UI instead of being swallowed.

        Emits:
            device_connected: When the TauSync server accepts a connection.
            connection_error: With the exception message string if listening fails.
        """
        try:
            self._tau.listen()
            self.device_connected.emit()
        except Exception as exc:
            self.connection_error.emit(str(exc))

    def disconnect_device(self) -> None:
        """Dispose the TauSync connection and emit ``device_disconnected``.

        Joins all background threads with a 2-second timeout each before
        clearing the thread registry, giving in-flight reads a chance to finish.

        Emits:
            device_disconnected: After all threads are joined and TauSync is disposed.
        """
        self._tau.dispose()
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2)
        self._threads.clear()
        self.device_disconnected.emit()

    @threaded
    def connect_to_device(self, ip: str) -> None:
        """Connect to a remote device by IP address.

        Currently, a stub — emits ``device_connected`` immediately while the
        real phone-side implementation is pending.

        Args:
            ip: The IP address of the remote TauSync server.

        Emits:
            device_connected: Immediately (stub behaviour).
        """
        # TODO: connect via Bluetooth using the previously stored device ID.
        # self._tau.dispose()
        # self._tau = TauSync()
        # print("happened")
        # self._tau.connect_to("192.168.68.1")
        # self._tau.connect_to(ip)
        # self.device_connected.emit()
