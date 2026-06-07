"""
Device connectivity service.

Manages the TauSync TCP connection lifecycle on a background thread,
emitting Qt signals when a device connects or disconnects.
"""
import threading

from PySide6.QtCore import QObject, Signal

from domain.enums.session_channels import SessionChannels
from tausync_py import TauSync
from utils import network


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
    device_disconnecting = Signal()
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
        self._is_running = threading.Event()

        self._lifecycle_lock = threading.Lock()
        self._threads_lock = threading.Lock()

    # ── Public read-only access to the transport ──────────────────────────────

    @property
    def tau(self) -> TauSync:
        """The underlying TauSync transport shared with dependent services.

        Returns:
            The :class:`~tausync_py.TauSync` instance owned by this service.
        """
        return self._tau

    @property
    def connected(self) -> bool:
        """``True`` when the TauSync transport has an active peer connection."""
        return self._tau.is_connected

    # ── Public API ───────────────────────────────────────────────────

    def start(self) -> None:
        """Start the connection listener on a background thread."""
        threading.Thread(target=self._start, daemon=True).start()

    def stop(self) -> None:
        """Stop the service on a background thread, joining all pending workers."""
        threading.Thread(target=self._stop, daemon=True).start()

    def connect_to_device(self, hostname: str) -> None:
        """Initiate an outbound connection to *hostname* on a background thread.

        No-ops when the service is not running.

        Args:
            hostname: DNS name or IP address of the target device.
        """
        if not self._is_running.is_set():
            return
        self._spawn(self._connect_to_device, hostname)

    def disconnect(self) -> None:
        if not self._is_running.is_set():
            return
        self._spawn(self._disconnect_device)

    # ── Private Functions ───────────────────────────────────────────────────

    def _start(self) -> None:
        # Guard against double-start; replace the transport so reconnects get a fresh TauSync.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._is_running.set()
            self._tau = TauSync()
        self._spawn(self._listen)

    def _stop(self) -> None:
        # Join every worker thread except the one calling _stop (which is itself a thread).
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                return
            self._is_running.clear()
            self._close_transport()  # tear-down only — no listener restart
            pending_threads: list[threading.Thread] = self._get_pending_threads()
            for t in pending_threads:
                if t == threading.current_thread():
                    continue
                t.join()

    def _spawn(self, target, *args):
        # All thread creation must go through here so teardown can join every worker.
        if not self._is_running.is_set():
            return  # reject new spawns during teardown
        t = threading.Thread(target=target, args=args, daemon=True)
        with self._threads_lock:
            self._threads.append(t)
        t.start()

    def _disconnect_device(self) -> None:
        """Graceful session tear-down followed by an immediate listener restart.

        Handles the disconnect handshake (phone-initiated or PC-initiated),
        closes the transport, emits :attr:`device_disconnected`, then recycles
        the current background thread as the next connection listener by calling
        :meth:`_listen` inline.  This keeps one persistent listener thread alive
        across sessions without spawning an extra thread per reconnect.

        Used only by the mid-session ``disconnect()`` public path.  The full
        teardown path (:meth:`_stop`) calls :meth:`_close_transport` directly
        to avoid an unwanted listener restart.

        Emits:
            device_disconnecting: Before the transport tear-down begins, so the
                UI can show a loading state on both phone-initiated and
                PC-initiated disconnect paths.
            device_disconnected: After the transport is closed.
        """
        self.device_disconnecting.emit()
        self._close_transport()
        self._listen()  # recycle this thread as the next connection listener

    def _close_transport(self) -> None:
        """Close the TauSync transport and emit ``device_disconnected`` — no restart.

        Shared tear-down primitive: handles the phone/PC handshake, closes
        ``tau``, and emits the signal.  Does **not** restart the listener loop —
        callers that want to keep accepting connections must call :meth:`_listen`
        (or spawn it) themselves.

        Emits:
            device_disconnected: After the transport is closed.
        """
        waiting_words = self._tau.get_peer_waiting_words()

        if SessionChannels.DISCONNECT_FROM_PHONE.value in waiting_words:
            try:
                _ = network.read_string_from_channel(self._tau, SessionChannels.DISCONNECT_FROM_PHONE.value)
            except Exception as e:
                print(f"[Desktop] ⚠ Failed to read phone disconnect signal: {e}")
        else:
            self._notify_phone_of_disconnect()

        self._tau.disconnect()
        self.device_disconnected.emit()

    def _notify_phone_of_disconnect(self) -> None:
        # Failures are swallowed so a missing/gone phone never blocks our own teardown.
        # timeout_seconds is mandatory: without it tau.connect() blocks forever waiting
        # for the phone to open the meeting-word channel, which prevents device_disconnected
        # from ever being emitted and leaves the UI stuck on the dashboard.
        try:
            with self._tau.connect(SessionChannels.DISCONNECT_FROM_PC.value, timeout_seconds=10) as stream:
                stream.write_string("disconnect")
        except Exception as e:
            print(f"[Desktop] Warning: Failed to notify phone of disconnect: {e}")

    def _connect_to_device(self, hostname: str) -> None:
        # TODO: connect via Bluetooth using the previously stored device ID.
        self.device_connected.emit()
        pass

    def _listen(self) -> None:
        # Retries on timeout; surfaces unexpected exceptions via connection_error.
        while self._is_running.is_set() and not self.connected:
            try:
                self._tau.listen(timeout_seconds=10)
                self.device_connected.emit()
            except TimeoutError:
                continue
            except Exception as exc:
                print(exc)
                self.connection_error.emit(str(exc))

    def _get_pending_threads(self) -> list[threading.Thread]:
        # Snapshot alive threads under the lock so callers can join without holding it.
        with self._threads_lock:
            return [t for t in self._threads if t.is_alive()]
