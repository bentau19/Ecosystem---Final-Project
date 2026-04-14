"""
Device connectivity service.

Manages the TauSync TCP connection lifecycle on a background thread,
emitting Qt signals when a device connects or disconnects.
"""
import functools
import threading
import uuid
from typing import Optional

from PySide6.QtCore import QObject, Signal
from tausync_py import TauSync

from entities.device_info import DeviceEntity
from enums.device_info_channels import DeviceInfoChannels
from repositories.device import DeviceRepository
from utils import network


def threaded(func):
    @functools.wraps(func)
    def run_as_thread(*args, **kwargs):
        self = args[0]
        thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        self._threads.append(thread)
        thread.start()
        return thread

    return run_as_thread


class ConnectivityService(QObject):
    """Manages the TauSync device connection lifecycle.
    Spawns a background thread to listen for an incoming TCP connection
    without blocking the UI thread. Uses threading.Thread (not qthread)
    because TauSync makes blocking .NET async calls via pythonnet — running
    those from a qthread (a Qt-managed native thread) corrupts the CLR stack
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
    device_info_ready = Signal(object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """
        Initialize ConnectivityService and immediately start listening.

        No-op on subsequent calls — initialization runs exactly once.

        Args:
            parent: Optional parent QObject for memory management.
        """

        super().__init__(parent)
        self._tau = TauSync()
        self._device_repository = DeviceRepository()

        self._threads = []

        # self._listen()




    def _generated_id(self):
        while True:
            random_id = str(uuid.uuid4())
            if self._device_repository.id_exists(random_id):
                continue
        return random_id

    def _get_id(self) -> str:
        id = network.read_from_channel(self._tau, DeviceInfoChannels.ID)
        if id == "":
            return self._generated_id()
        return id

    def get_tag(self) -> str:
        tag = network.read_from_channel(self._tau, DeviceInfoChannels.TAG)
        if tag == "":
            return "default"
        return tag

    # @threaded
    def get_device_info(self) -> None:
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
        """Block until a remote device connects, then emit device_connected.

        Runs on a background threading.Thread. Emits connection_error on
        failure so the error surfaces to the UI instead of being swallowed.
        """
        try:
            self._tau.listen()
            self.device_connected.emit()
        except Exception as exc:
            self.connection_error.emit(str(exc))

    def disconnect_device(self) -> None:
        """Dispose the TauSync connection and emit device_disconnected.

        Blocks briefly to let the background thread finish cleanly.
        """
        self._tau.dispose()
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2)
        self._threads.clear()
        self.device_disconnected.emit()



    def connect_to_device(self, ip: str) -> None:
        """Connect to a remote device by IP address.

        Args:
            ip: The IP address of the remote TauSync server.
        """
        self._tau.connect_to(ip)
        self.device_connected.emit()
        # TODO: via Bluetooth with prev id...
        pass





