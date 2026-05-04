from typing import Final

from repositories.device import DeviceRepository
from repositories.tool import ToolRepository
from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService
from services.file_transfer import FileTransferService
from viewmodels.device import DeviceViewModel
from viewmodels.file_transfer import FileTransferViewModel


class AppState:
    """Global application state — the single DI root for all singletons.

    Consolidates repositories, services, and viewmodels into a single
    entry point. All layers access application infrastructure through this
    singleton rather than instantiating or importing from scattered managers.
    """

    def __init__(self) -> None:
        """Initialize all repositories, services, and viewmodels."""
        # Repositories
        self.tools_repository: Final[ToolRepository] = ToolRepository()
        self.device_repository: Final[DeviceRepository] = DeviceRepository()

        # Services
        self.connectivity_service: Final[ConnectivityService] = ConnectivityService()
        self.device_info_service: Final[DeviceInfoService] = DeviceInfoService(
            connectivity=self.connectivity_service,
            repository=self.device_repository,
        )
        self.file_transfer_service: Final[FileTransferService] = FileTransferService(
            connectivity=self.connectivity_service,
        )

        # ViewModels
        self.device_viewmodel: Final[DeviceViewModel] = DeviceViewModel(
            self.device_repository,
            self.connectivity_service,
            self.device_info_service,
        )
        self.file_transfer_viewmodel: Final[FileTransferViewModel] = FileTransferViewModel(
            file_transfer_service=self.file_transfer_service,
            connectivity_service=self.connectivity_service,
        )


app_state: Final[AppState] = AppState()
