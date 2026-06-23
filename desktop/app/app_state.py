from typing import Final

from domain.enums.clipboard_channels import ClipboardChannels
from repositories.device import DeviceRepository
from repositories.tool import ToolRepository
from services.clipboard import ClipboardService
from services.backup import BackupService
from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService
from services.file_transfer import FileTransferService
from services.phone_request import PhoneRequestService
from services.tool import ToolService
from services.virtual_drive import VirtualDriveService
from viewmodels.backup import BackupViewModel
from viewmodels.device import DeviceViewModel
from viewmodels.file_transfer import FileTransferViewModel
from viewmodels.tool import ToolViewModel


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
        self.clipboard_service: Final[ClipboardService] = ClipboardService(
            connectivity=self.connectivity_service,
        )
        self.tool_service: Final[ToolService] = ToolService(
            repository=self.tools_repository,
        )
        self.backup_service: Final[BackupService] = BackupService(
            connectivity=self.connectivity_service,
        )

        # ViewModels
        self.device_viewmodel: Final[DeviceViewModel] = DeviceViewModel(
            connectivity_service=self.connectivity_service,
            device_info_service=self.device_info_service,
        )
        self.file_transfer_viewmodel: Final[FileTransferViewModel] = FileTransferViewModel(
            file_transfer_service=self.file_transfer_service,
            connectivity_service=self.connectivity_service,
        )
        self.tool_viewmodel: Final[ToolViewModel] = ToolViewModel(
            tool_service=self.tool_service,
        )
        self.backup_viewmodel: Final[BackupViewModel] = BackupViewModel(
            backup_service=self.backup_service,
            connectivity_service=self.connectivity_service,
        )
        self.virtual_drive_service: Final[VirtualDriveService] = VirtualDriveService(
            connectivity=self.connectivity_service,
            device_info=self.device_info_service,
        )

        self.phone_request_service: Final[PhoneRequestService] = PhoneRequestService(
            connectivity_service=self.connectivity_service,
            file_transfer_service=self.file_transfer_service,
            backup_service=self.backup_service,
            device_info_service=self.device_info_service,
        )
        self.phone_request_service.operations[
            ClipboardChannels.CLIPBOARD_ANDROID_TO_PC.value
        ] = self.clipboard_service.receive

        # Wire service lifecycles to device connection events.
        # BackupService is wired first so its executor is initialized before
        # PhoneRequestService can dispatch receive_manifest() on the first poll.
        self.device_viewmodel.device_connected.connect(self.backup_service.start)
        self.device_viewmodel.device_connected.connect(self.phone_request_service.start)
        self.device_viewmodel.device_connected.connect(self.virtual_drive_service.start)

        self.device_viewmodel.device_disconnected.connect(self.backup_service.stop)
        self.device_viewmodel.device_disconnected.connect(self.phone_request_service.stop)
        self.device_viewmodel.device_disconnected.connect(self.virtual_drive_service.stop)
        # Wire VirtualDriveService lifecycle to device connection events.
        # start() opens \\.\pipe\SyncDoseVDrive and begins serving VirtualDrive.exe.
        # stop() shuts the executor down after all in-flight ops complete.

    def shutdown(self) -> None:
        """Stop all background services in dependency order on app exit.

        Called via ``QApplication.aboutToQuit`` so every exit path is covered
        (X button, tray Quit, sys.exit, etc.).  All ``stop()`` implementations
        are idempotent and non-blocking (they spawn daemon threads), so this
        returns immediately and the process exits cleanly.

        Order: dependent services first, connectivity last so the phone
        receives a disconnect notification before the transport closes.
        """
        self.phone_request_service.stop()
        self.backup_service.stop()
        self.virtual_drive_service.stop()   # also terminates VirtualDrive.exe
        self.connectivity_service.stop()    # notifies phone, then closes TauSync


app_state: Final[AppState] = AppState()
