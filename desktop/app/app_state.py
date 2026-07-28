import logging
from typing import Final

from domain.enums.clipboard_channels import ClipboardChannels
from domain.enums.settings_channels import SettingsChannels
from domain.enums.webcam_channels import WebcamChannels
from repositories.device import DeviceRepository
from repositories.settings import SettingsRepository
from repositories.tool import ToolRepository
from services.settings import SettingsService
from services.clipboard import ClipboardService
from services.backup import BackupService
from services.connectivity import ConnectivityService
from services.device_info import DeviceInfoService
from services.file_transfer import FileTransferService
from services.lifecycle import Lifecycle
from services.phone_request import PhoneRequestService
from services.tool import ToolService
from services.virtual_drive import VirtualDriveService
from services.webcam import WebcamService
from viewmodels.backup import BackupViewModel
from viewmodels.device import DeviceViewModel
from viewmodels.file_transfer import FileTransferViewModel
from viewmodels.settings import SettingsViewModel
from viewmodels.tool import ToolViewModel
from viewmodels.webcam import WebcamViewModel

logger = logging.getLogger(__name__)


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
        self.settings_repository: Final[SettingsRepository] = SettingsRepository()

        # Services
        self.connectivity_service: Final[ConnectivityService] = ConnectivityService()
        # SettingsService needs connectivity for the tool-enabled sync, so it is
        # constructed after connectivity_service rather than next to its repository.
        self.settings_service: Final[SettingsService] = SettingsService(
            repository=self.settings_repository,
            connectivity=self.connectivity_service,
        )
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
        self.webcam_service: Final[WebcamService] = WebcamService(
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
        self.backup_viewmodel: Final[BackupViewModel] = BackupViewModel(
            backup_service=self.backup_service,
            connectivity_service=self.connectivity_service,
        )
        self.virtual_drive_service: Final[VirtualDriveService] = VirtualDriveService(
            connectivity=self.connectivity_service,
            device_info=self.device_info_service,
        )
        # drive_error reports mount failures, pipe-server faults, reaped sessions
        # and per-op failures. Nothing else consumes it, so without this every one
        # of those messages is built and discarded — leaving Explorer's generic
        # 0x8007045D as the only symptom of a failed operation.
        self.virtual_drive_service.drive_error.connect(
            lambda message: logger.error("virtual drive: %s", message)
        )

        # ToolViewModel is the tools coordinator: it owns the enable/disable side
        # effects for the four feature tools (Clipboard/Webcam/Backup set_enabled
        # and the VirtualDrive lifecycle) plus the bidirectional tool-state sync
        # with the phone.  Constructed after the services + device_viewmodel it
        # depends on.
        self.tool_viewmodel: Final[ToolViewModel] = ToolViewModel(
            tool_service=self.tool_service,
            clipboard_service=self.clipboard_service,
            webcam_service=self.webcam_service,
            backup_service=self.backup_service,
            virtual_drive_service=self.virtual_drive_service,
            connectivity_service=self.connectivity_service,
            device_viewmodel=self.device_viewmodel,
            settings_service=self.settings_service,
        )

        # ToolViewModel is the tools coordinator: it owns the enable/disable side
        # effects for the four feature tools (Clipboard/Webcam/Backup set_enabled
        # and the VirtualDrive lifecycle) plus the bidirectional tool-state sync
        # with the phone.  Constructed after the services + device_viewmodel it
        # depends on.
        self.tool_viewmodel: Final[ToolViewModel] = ToolViewModel(
            tool_service=self.tool_service,
            clipboard_service=self.clipboard_service,
            webcam_service=self.webcam_service,
            backup_service=self.backup_service,
            virtual_drive_service=self.virtual_drive_service,
            connectivity_service=self.connectivity_service,
            device_viewmodel=self.device_viewmodel,
            settings_service=self.settings_service,
        )

        self.webcam_viewmodel: Final[WebcamViewModel] = WebcamViewModel(
            webcam_service=self.webcam_service,
        )
        self.phone_request_service: Final[PhoneRequestService] = PhoneRequestService(
            connectivity_service=self.connectivity_service,
            file_transfer_service=self.file_transfer_service,
            backup_service=self.backup_service,
            device_info_service=self.device_info_service,
            webcam_service=self.webcam_service,
            clipboard_service=self.clipboard_service,
            settings_service=self.settings_service,
        )
        # Wire service lifecycles to device connection events.
        # BackupService is wired first so its executor is initialized before
        # PhoneRequestService can dispatch receive_manifest() on the first poll.
        self.device_viewmodel.device_connected.connect(self.backup_service.start)
        self.device_viewmodel.device_connected.connect(self.phone_request_service.start)
        # VirtualDriveService lifecycle is NOT wired here — ToolViewModel
        # conditionally connects device_connected/disconnected based on the
        # "Virtual Drive" tool's enabled state.  See viewmodels/tool.py.

        self.device_viewmodel.device_disconnected.connect(self.backup_service.stop)
        self.device_viewmodel.device_disconnected.connect(self.phone_request_service.stop)

        # Every background service, used by the app-exit shutdown poll
        # (stop_all / any_active).  VirtualDriveService is created after the
        # viewmodels above, so the tuple is assembled here once all exist.
        # VirtualDriveService is always included even when disabled by settings
        # so stop_all() safely calls stop() (which is a no-op if never started).
        # ClipboardService and WebcamService are non-Lifecycle in spirit (no
        # start-on-connect) but expose stop()/is_active so shutdown can release
        # the virtual camera and drain in-flight sync threads.  They sit before
        # connectivity_service, which stays last so its transport teardown
        # unblocks any read the webcam stream is parked on.
        self._services: Final[tuple[Lifecycle, ...]] = (
            self.phone_request_service,
            self.backup_service,
            self.virtual_drive_service,  # also terminates VirtualDrive.exe
            self.file_transfer_service,
            self.tool_service,
            self.device_info_service,
            self.clipboard_service,
            self.webcam_service,
            self.connectivity_service,
        )

        # SettingsViewModel now owns only the autostart flag; per-tool enable
        # state is coordinated by ToolViewModel (tools.json is the source of truth).
        self.settings_viewmodel: Final[SettingsViewModel] = SettingsViewModel(
            settings_service=self.settings_service,
        )

    def stop_all(self) -> None:
        """Fire ``stop()`` on every service (each tears down on its own thread).

        Fire-and-forget: no teardown runs on the calling (GUI) thread.  The
        caller polls :meth:`any_active` to learn when teardown has finished.
        """
        for svc in self._services:
            svc.stop()

    def any_active(self) -> bool:
        """True while any service is still running (polled during app shutdown)."""
        return any(svc.is_active for svc in self._services)


app_state: Final[AppState] = AppState()
