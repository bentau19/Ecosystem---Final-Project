"""
Device connectivity service.

Manages the TauSync TCP connection lifecycle on a background thread,
emitting Qt signals when a device connects or disconnects.
"""
import functools
import threading
import uuid
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from tausync_py import TauSync

from entities.device_info import DeviceEntity
from enums.device_info_channels import DeviceInfoChannels
from repositories.device import DeviceRepository
from utils import network


def threaded(func: Callable) -> Callable[..., threading.Thread]:
    """Decorator that runs a bound method on a new daemon :class:`threading.Thread`.

    The spawned thread is appended to ``self._threads`` so it can be joined
    during cleanup. The first positional argument of the decorated method must
    be the instance (``self``) and must expose a ``_threads: list`` attribute.

    Args:
        func: The bound method to wrap.

    Returns:
        A wrapper that starts the method on a background thread and returns
        the :class:`threading.Thread` object to the caller.
    """
    @functools.wraps(func)
    def run_as_thread(*args, **kwargs) -> threading.Thread:
        self = args[0]
        thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        self._threads.append(thread)
        thread.start()
        return thread

    return run_as_thread


class ConnectivityService(QObject):
    """Manages the TauSync device connection lifecycle.

    Spawns a background thread to listen for an incoming TCP connection
    without blocking the UI thread. Uses :class:`threading.Thread` rather than
    ``QThread`` because TauSync makes blocking .NET async calls via pythonnet —
    running those from a ``QThread`` (a Qt-managed native thread) corrupts the
    CLR stack and causes a fatal ``0xC0000409`` crash.

    PySide6 handles cross-thread signal emission automatically via queued
    connections, so ``Signal.emit()`` from a ``threading.Thread`` is safe.

    Signals:
        device_connected (Signal): Emitted when a remote device connects.
        device_disconnected (Signal): Emitted after :meth:`disconnect_device` completes.
        connection_error (Signal[str]): Emitted if the connection attempt fails.
        device_info_ready (Signal[object]): Emitted with a
            :class:`~entities.device_info.DeviceEntity` when all channel reads
            in :meth:`get_device_info` finish successfully.
    """

    device_connected = Signal()
    device_disconnected = Signal()
    connection_error = Signal(str)
    device_info_ready = Signal(object)

    def __init__(self, repository: DeviceRepository, parent: Optional[QObject] = None) -> None:
        """Initialize the service and set up the TauSync connection.

        Args:
            repository: The shared :class:`~repositories.device.DeviceRepository`
                instance from the application's DI root, used to check for
                existing device IDs before generating new ones.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._tau: TauSync = TauSync()
        self._device_repository: DeviceRepository = repository
        self._threads: list[threading.Thread] = []

        # self._listen()

    def _generated_id(self) -> str:
        """Generate a UUID that does not already exist in the device repository.

        Loops until a UUID is found that is absent from the local database,
        guaranteeing uniqueness before the ID is assigned to a new device.

        Returns:
            A UUID string guaranteed to be absent from the local database.
        """
        while True:
            random_id = str(uuid.uuid4())
            if not self._device_repository.id_exists(random_id):
                return random_id

    def _get_id(self) -> str:
        """Read the device ID from the TauSync ID channel, generating one if absent.

        Returns:
            The device ID provided by the remote device, or a freshly generated
            UUID that is unique within the local repository.
        """
        device_id = network.read_from_channel(self._tau, DeviceInfoChannels.ID)
        if device_id == "":
            return self._generated_id()
        return device_id

    def get_tag(self) -> str:
        """Read the device tag from the TauSync TAG channel, falling back to ``'default'``.

        Returns:
            The tag string provided by the remote device, or ``"default"`` if
            the channel returns an empty string.
        """
        tag = network.read_from_channel(self._tau, DeviceInfoChannels.TAG)
        if tag == "":
            return "default"
        return tag

    @threaded
    def get_device_info(self) -> None:
        """Read all device fields from TauSync channels and emit a DeviceEntity.

        Runs on a background thread (via the ``@threaded`` decorator). Silently
        no-ops if TauSync is not currently connected.

        Emits:
            device_info_ready: With the assembled
                :class:`~entities.device_info.DeviceEntity` once all channel
                reads complete.
        """
        if not self._tau.is_connected:
            return
        entity = DeviceEntity(
            id=self._get_id(),
            tag=network.read_from_channel(self._tau, DeviceInfoChannels.TAG),
            name=network.read_from_channel(self._tau, DeviceInfoChannels.NAME),
            os=network.read_from_channel(self._tau, DeviceInfoChannels.OS),
            battery_level=int(network.read_from_channel(self._tau, DeviceInfoChannels.BATTERY_LEVEL)),
            battery_charging=bool(network.read_from_channel(self._tau, DeviceInfoChannels.BATTERY_CHARGING)),
            storage_total=int(network.read_from_channel(self._tau, DeviceInfoChannels.STORAGE_TOTAL)),
            storage_used=int(network.read_from_channel(self._tau, DeviceInfoChannels.STORAGE_USED)),
            last_connected=network.read_from_channel(self._tau, DeviceInfoChannels.LAST_SEEN),
            ip=network.read_from_channel(self._tau, DeviceInfoChannels.IP)
        )
        self.device_info_ready.emit(entity)

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
        # TODO: via Bluetooth with prev id...
        # self._tau.connect_to(ip)
        self.device_connected.emit()
