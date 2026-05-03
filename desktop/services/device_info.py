"""
Device-info service.

Reads device metadata from TauSync named channels on a background thread
and emits a fully-populated DeviceEntity so the ViewModel can persist and
display it without touching the network layer directly.
"""
import uuid
from datetime import date

from PySide6.QtCore import QObject, Signal
from tausync_py import TauSync

from domain.entities.device_info import DeviceEntity
from domain.enums.device_info_channels import DeviceInfoChannels
from repositories.device import DeviceRepository
from services.connectivity import ConnectivityService
from utils import network
from utils.decorators import threaded


class DeviceInfoService(QObject):
    """Reads device metadata from TauSync channels and emits a DeviceEntity.

    Depends on a live :class:`~tausync_py.TauSync` transport (obtained from
    :class:`~services.connectivity.ConnectivityService`) and the device
    repository (to guarantee UUID uniqueness when the remote device has no
    previously assigned ID).

    All channel reads run on a background :class:`threading.Thread` via the
    ``@threaded`` decorator so the UI thread is never blocked. PySide6's queued
    connection mechanism ensures ``Signal.emit()`` from that thread is safe.

    Signals:
        device_info_ready (Signal[object]): Emitted with a fully-populated
            :class:`~entities.device_info.DeviceEntity` once all channel reads
            complete successfully.
        read_error (Signal[str]): Emitted with the exception message string if
            any channel read raises an exception.
    """

    device_info_ready = Signal(object)
    read_error = Signal(str)

    def __init__(
            self,
            connectivity: ConnectivityService,
            repository: DeviceRepository,
            parent: QObject | None = None,
    ) -> None:
        """Initialize the service with the shared connectivity service and repository.

        Args:
            connectivity: The application's
                :class:`~services.connectivity.ConnectivityService` singleton.
                ``listen()`` or ``connect_to()`` must have been called on it
                before :meth:`fetch_device_info` is invoked.
            repository: The shared :class:`~repositories.device.DeviceRepository`
                instance from the application's DI root, used to check for
                existing device IDs before generating new ones.
            parent: Optional parent QObject for Qt memory management.
        """
        super().__init__(parent)
        self._tau: TauSync = connectivity.tau
        self._device_repository: DeviceRepository = repository
        self._threads: list = []

    # ── Public API ─────────────────────────────────────────────────────────────

    @threaded
    def fetch_device_info(self) -> None:
        """Read all device fields from TauSync channels and emit a DeviceEntity.

        Runs on a background thread. Silently no-ops if TauSync is not currently
        connected. Emits ``read_error`` if any channel read raises an exception
        so the caller is notified rather than left in an unknown state.

        Emits:
            device_info_ready: With the assembled
                :class:`~entities.device_info.DeviceEntity` once all channel
                reads complete successfully.
            read_error: With the exception message string if a read fails.
        """
        if not self._tau.is_connected:
            return
        try:
            entity = DeviceEntity(
                id=self._read_device_id(),
                tag=self._read_channel_string(DeviceInfoChannels.TAG) or "default",
                name=self._read_channel_string(DeviceInfoChannels.NAME),
                os=self._read_channel_string(DeviceInfoChannels.OS),
                battery_level=int(self._read_channel_string(DeviceInfoChannels.BATTERY_LEVEL)),
                battery_charging=(
                        self._read_channel_string(DeviceInfoChannels.BATTERY_CHARGING).lower() == "true"
                ),
                storage_total=int(self._read_channel_string(DeviceInfoChannels.STORAGE_TOTAL)),
                storage_used=int(self._read_channel_string(DeviceInfoChannels.STORAGE_USED)),
                last_connected=date.fromisoformat(
                    self._read_channel_string(DeviceInfoChannels.LAST_SEEN)
                ),
                ip=self._read_channel_string(DeviceInfoChannels.IP),
            )
            self.device_info_ready.emit(entity)
        except Exception as exc:
            self.read_error.emit(str(exc))

    # ── Private helpers ────────────────────────────────────────────────────────

    def _read_channel_string(self, channel: DeviceInfoChannels) -> str:
        """Read the full payload from a named TauSync channel as a UTF-8 string.

        Args:
            channel: The :class:`~enums.device_info_channels.DeviceInfoChannels`
                member identifying the channel to read from.

        Returns:
            The decoded payload string, which may be empty if the remote peer
            sent nothing before closing the stream.
        """
        return network.read_from_channel(self._tau, channel)

    def _read_device_id(self) -> str:
        """Read the device ID from the TauSync ID channel, generating one if absent.

        If the remote device sends an empty string on the ID channel (i.e. it
        has no previously assigned ID), a new UUID is generated that is
        guaranteed to be absent from the local repository.

        Returns:
            The device ID provided by the remote device, or a freshly generated
            UUID that is unique within the local repository.
        """
        device_id = self._read_channel_string(DeviceInfoChannels.ID)
        if device_id == "":
            return self._generate_unique_id()
        return device_id

    def _generate_unique_id(self) -> str:
        """Generate a UUID that does not already exist in the device repository.

        Loops until a candidate UUID is absent from the local database,
        guaranteeing uniqueness before the ID is assigned to a new device.

        Returns:
            A UUID string guaranteed to be absent from the local database.
        """
        while True:
            candidate_id = str(uuid.uuid4())
            if not self._device_repository.id_exists(candidate_id):
                return candidate_id
