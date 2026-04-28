from typing import Final

from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService
from services.file_transfer import FileTransferService
from utils.repository_manger import repository_manager


class ServicesManager:
    """Application-level DI root for service singletons.

    Constructs each service exactly once and injects its dependencies from
    :data:`~utils.repository_manger.repository_manager` so that no service
    ever instantiates a repository directly.

    :class:`~services.device_info.DeviceInfoService` shares the
    :class:`~tausync_py.TauSync` transport owned by
    :class:`~services.connectivity.ConnectivityService` via the ``tau``
    property, keeping a single live connection across both services.

    :class:`~services.file_transfer.FileTransferService` receives the full
    :class:`~services.connectivity.ConnectivityService` instance rather than a
    ``tau`` snapshot.  This is intentional: ``connect_to_device`` replaces
    ``ConnectivityService._tau`` on every reconnect, so any service that cached
    ``tau`` at construction time would hold a stale, disposed reference.
    ``FileTransferService`` reads ``connectivity.tau`` at the start of every
    call, guaranteeing it always has the current live transport.
    """

    def __init__(self) -> None:
        """Initialize all service instances with their injected dependencies."""
        self.connectivity_service: Final[ConnectivityService] = ConnectivityService()
        self.device_info_service: Final[DeviceInfoService] = DeviceInfoService(
            connectivity=self.connectivity_service,
            repository=repository_manager.device_repository,
        )
        self.file_transfer_service: Final[FileTransferService] = FileTransferService(
            connectivity=self.connectivity_service,
        )


services_manager: Final[ServicesManager] = ServicesManager()
