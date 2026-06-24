import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

import utils
from domain.enums.session_channels import SessionChannels
from services.lifecycle import LifecycleFlag
from tausync_py import TauSync
# Imported for its side effect of binding the `network` submodule onto the
# `utils` package object so `utils.network.*` below resolves correctly.
from utils import network

logger = logging.getLogger(__name__)


class ConnectivityService(LifecycleFlag, QObject):
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

    Disconnecting (PC- or phone-initiated) always goes through :meth:`stop`,
    which tears down the transport, drains all background work, and only then
    emits ``device_disconnected``.  Restarting the listener after a disconnect
    is owned by ``DeviceViewModel`` (it calls :meth:`start` in reaction to
    ``device_disconnected``) — this service never re-listens on its own.

    Signals:
        device_connected: Emitted when a remote device connects.
        device_disconnecting: Emitted at the very start of :meth:`stop`,
            before any teardown work begins, so the UI can immediately show
            a "Disconnecting…" state.
        device_disconnected: Emitted after :meth:`stop` has fully completed —
            transport closed and every background worker joined.  Slots wired
            to this signal may safely call :meth:`start` to re-listen.
        connection_error (Signal[str]): Emitted with the exception message if
            the connection attempt fails.
    """

    device_connected: Signal = Signal()
    device_disconnecting: Signal = Signal()
    device_disconnected: Signal = Signal()
    connection_error: Signal = Signal(str)

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
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor()
        self._is_running: threading.Event = threading.Event()
        self._init_lifecycle()

        self._lifecycle_lock: threading.Lock = threading.Lock()

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
        """Stop the service on a background thread, joining all pending workers.

        This is the single disconnect path (PC- and phone-initiated).  The
        teardown sequence is strictly ordered:

        1. ``device_disconnecting`` is emitted so the UI can show a
           "Disconnecting…" state immediately.
        2. The phone is notified (best-effort) and the transport is closed.
        3. Every pending background worker is joined.
        4. ``device_disconnected`` is emitted — only now, so any slot that
           restarts the service cannot race the executor shutdown above.

        Safe to call even when the peer has already gone away (e.g. Android
        crash): the transport teardown fast-paths when ``tau.is_connected``
        is already ``False``, so the lifecycle signals are always emitted.
        """
        threading.Thread(target=self._stop, daemon=True).start()

    def connect_to_device(self, hostname: str) -> None:
        """Initiate an outbound connection to *hostname* on a background thread.

        No-ops when the service is not running.

        Args:
            hostname: DNS name or IP address of the target device.
        """
        if not self._is_running.is_set():
            return
        self._executor.submit(self._connect_to_device, hostname)

    # ── Private Functions ───────────────────────────────────────────────────

    def _start(self) -> None:
        # Guard against double-start; replace both the transport and executor so
        # reconnects get a fresh TauSync and a clean thread pool.
        with self._lifecycle_lock:
            if self._is_running.is_set():
                return
            self._executor = ThreadPoolExecutor()
            self._is_running.set()
            self._mark_started()
            self._tau = TauSync()
        self._executor.submit(self._listen)

    def _stop(self) -> None:
        # Strictly ordered teardown — see stop() docstring.
        #
        # The whole teardown runs *inside* _lifecycle_lock so the running-state
        # flip, the transport teardown, the executor drain, and the lifecycle
        # signals form one atomic unit.  A queued start() takes the same lock and
        # therefore waits for this stop to finish before it re-listens — the
        # serialisation we want, so a stop and an immediately-following restart
        # can never interleave.
        #
        # tau and executor are still captured into locals: once
        # device_disconnected is emitted a slot may call start(), which (after
        # this lock is released) swaps self._tau / self._executor for fresh ones.
        # Tearing down the captured references guarantees a racing restart's new
        # transport and pool are never disconnected or cancelled by this stop.
        with self._lifecycle_lock:
            if not self._is_running.is_set():
                logger.debug("_stop: already stopped — no-op")
                return
            self._is_running.clear()
            tau = self._tau
            executor = self._executor

            logger.debug("_stop: tearing down transport and draining workers")
            self.device_disconnecting.emit()

            # Teardown runs under the lock (see above): a queued start() waits
            # rather than re-listening mid-teardown.  The captured tau (not
            # self._tau) is torn down so a later start() that swaps in a fresh
            # transport can never have its replacement disconnected by this stop.
            self._teardown_transport(tau)

            # tau.disconnect() aborts the blocking tau.listen() inside _listen, so
            # the listener future exits promptly and this join completes.
            executor.shutdown(wait=True, cancel_futures=True)

            self.device_disconnected.emit()
            logger.debug("_stop: teardown complete — device_disconnected emitted")

            # Mark fully stopped unless a concurrent start() re-armed us mid-teardown.
            self._mark_stopped()

    def _teardown_transport(self, tau: TauSync) -> None:
        # Notify the peer (best-effort) and close the transport.  Emits no
        # signals — lifecycle signal ordering is owned entirely by _stop().
        #
        # Only attempt network I/O when the transport still reports a live
        # peer.  If Android already crashed, is_connected is False and we skip
        # straight to the finally block — no 10-second
        # _notify_phone_of_disconnect wait.
        try:
            if tau.is_connected:
                waiting_words = tau.get_peer_waiting_words()
                if SessionChannels.DISCONNECT_FROM_PHONE.value in waiting_words:
                    try:
                        _ = utils.network.read_string_from_channel(
                            tau, SessionChannels.DISCONNECT_FROM_PHONE.value
                        )
                    except Exception as e:
                        logger.warning("Failed to read phone disconnect signal: %s", e)
                else:
                    self._notify_phone_of_disconnect(tau)
        except Exception as e:
            # get_peer_waiting_words() raises RuntimeError on a dead connection.
            # Swallow it so teardown always completes.
            logger.warning("Peer appears to have disconnected unexpectedly: %s", e)
        finally:
            try:
                tau.disconnect()
            except Exception as e:
                logger.warning("Error during tau.disconnect(): %s", e)

    @staticmethod
    def _notify_phone_of_disconnect(tau: TauSync) -> None:
        # Failures are swallowed so a missing/gone phone never blocks our own teardown.
        # timeout_seconds is mandatory: without it tau.connect() blocks forever waiting
        # for the phone to open the meeting-word channel, which prevents device_disconnected
        # from ever being emitted and leaves the UI stuck on the dashboard.
        try:
            logger.debug("Sending disconnect notification to phone")
            with tau.connect(SessionChannels.DISCONNECT_FROM_PC.value, timeout_seconds=10) as stream:
                stream.write_string("disconnect")
            logger.debug("Disconnect notification sent to phone")
        except Exception as e:
            logger.warning("Failed to notify phone of disconnect: %s", e)

    def _connect_to_device(self, hostname: str) -> None:
        # TODO: connect via Bluetooth using the previously stored device ID.
        pass

    def _reset_transport(self) -> None:
        # Clear a stale/stuck transport role so the next listen() re-arms a real accept.
        # tau.disconnect() always resets the process-wide role to NONE (and only touches
        # the socket when it is actually live), so this is safe on a phantom/dead transport.
        try:
            self._tau.disconnect()
        except Exception as exc:
            logger.debug("_listen: reset/disconnect failed: %s", exc)

    def _listen(self) -> None:
        # Retries on timeout; surfaces unexpected exceptions via connection_error.
        while self._is_running.is_set() and not self.connected:
            logger.debug(
                "_listen: waiting for connection (running=%s, connected=%s)",
                self._is_running.is_set(),
                self.connected,
            )
            try:
                self._tau.listen(timeout_seconds=10)
                # listen() returning does NOT guarantee a live peer: a stale transport can
                # return instantly with is_connected still False (the "phantom connect").
                # Never emit a phantom device_connected — reset the role so the next
                # listen() re-arms a real accept, then back off and retry.
                if not self.connected:
                    logger.warning("_listen: listen() returned with no live peer — resetting")
                    self._reset_transport()
                    time.sleep(1)
                    continue
                logger.info("_listen: device connected")
                self.device_connected.emit()
            except TimeoutError:
                logger.debug("_listen: listen timed out — retrying")
                time.sleep(1)
            except Exception as exc:
                # A deliberate stop() aborts the blocking listen() via
                # tau.disconnect() — that is normal teardown, not an error.
                if not self._is_running.is_set():
                    logger.debug("_listen: listen aborted by stop() — exiting")
                    return
                logger.error("Connection listener error: %s", exc)
                self.connection_error.emit(str(exc))
                # Clear any stuck role (e.g. a surfaced "already connected" RuntimeError)
                # so the next attempt can re-arm a real listen.
                self._reset_transport()
                # Brief backoff so a persistent failure (e.g. port in use)
                # never hot-spins the listener thread.
                time.sleep(1)
