import sys

from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.settings import SettingsDTO
from services.backup import BackupService
from services.clipboard import ClipboardService
from services.connectivity import ConnectivityService
from services.settings import SettingsService
from services.virtual_drive import VirtualDriveService
from services.webcam import WebcamService
from viewmodels.device import DeviceViewModel


class SettingsViewModel(QObject):
    """ViewModel for application settings.

    Owns the runtime lifecycle wiring of :class:`~services.virtual_drive.VirtualDriveService`
    (connecting / disconnecting it from the device connect/disconnect signals based on
    whether the feature is enabled), and manages the Windows Registry autostart entry.

    Signals:
        autostart_changed (Signal[bool]): Emitted after the autostart setting changes.
        virtual_drive_changed (Signal[bool]): Emitted after the virtual-drive setting changes.
        clipboard_changed (Signal[bool]): Emitted after the clipboard-sync setting changes.
        webcam_changed (Signal[bool]): Emitted after the webcam setting changes.
        backup_changed (Signal[bool]): Emitted after the backup setting changes.
    """

    autostart_changed: Signal = Signal(bool)
    virtual_drive_changed: Signal = Signal(bool)
    clipboard_changed: Signal = Signal(bool)
    webcam_changed: Signal = Signal(bool)
    backup_changed: Signal = Signal(bool)

    def __init__(
        self,
        settings_service: SettingsService,
        device_viewmodel: DeviceViewModel,
        virtual_drive_service: VirtualDriveService,
        connectivity_service: ConnectivityService,
        clipboard_service: ClipboardService,
        webcam_service: WebcamService,
        backup_service: BackupService,
        parent: QObject | None = None,
    ) -> None:
        """Load persisted settings and conditionally wire VirtualDrive lifecycle.

        Args:
            settings_service: The settings service layer (wraps the repository).
            device_viewmodel: Used to connect/disconnect VirtualDrive start/stop.
            virtual_drive_service: The service whose lifecycle is conditionally managed.
            connectivity_service: Used to check current connection state when
                Virtual Drive is disabled while a device is connected.
            clipboard_service: Clipboard sync service, gated by the persisted
                ``clipboard_enabled`` setting.
            webcam_service: Webcam streaming service, gated by the persisted
                ``webcam_enabled`` setting.
            backup_service: Backup reception service, gated by the persisted
                ``backup_enabled`` setting.
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._service: SettingsService = settings_service
        self._device_vm: DeviceViewModel = device_viewmodel
        self._vdrive: VirtualDriveService = virtual_drive_service
        self._connectivity: ConnectivityService = connectivity_service
        self._clipboard: ClipboardService = clipboard_service
        self._webcam: WebcamService = webcam_service
        self._backup: BackupService = backup_service

        self._settings: SettingsDTO = settings_service.load()
        # Track whether the VirtualDrive lifecycle signals are currently wired.
        self._vdrive_wired: bool = False

        if self._settings.virtual_drive_enabled:
            self._wire_virtual_drive()

        # Apply the persisted enable state to the always-constructed services.
        # Idempotent — all services default to enabled.
        self._clipboard.set_enabled(self._settings.clipboard_enabled)
        self._webcam.set_enabled(self._settings.webcam_enabled)
        self._backup.set_enabled(self._settings.backup_enabled)

        # Apply tool-enabled state pushed by the phone. These are queued
        # cross-thread connections (signals emitted from TauSync daemon threads),
        # so each slot runs on the GUI thread. They do NOT echo back to the phone.
        self._service.tools_state_received.connect(self._apply_virtual_drive_from_phone)
        self._service.clipboard_state_received.connect(self._apply_clipboard_from_phone)
        self._service.webcam_state_received.connect(self._apply_webcam_from_phone)
        self._service.backup_state_received.connect(self._apply_backup_from_phone)

    # ── Public properties ──────────────────────────────────────────────────────

    @property
    def autostart(self) -> bool:
        """Whether SyncDose is currently set to launch with Windows."""
        return self._settings.autostart

    @property
    def virtual_drive_enabled(self) -> bool:
        """Whether the Virtual Drive service starts on device connect."""
        return self._settings.virtual_drive_enabled

    @property
    def clipboard_enabled(self) -> bool:
        """Whether two-directional clipboard sync is active."""
        return self._settings.clipboard_enabled

    @property
    def webcam_enabled(self) -> bool:
        """Whether the phone may stream to the virtual webcam."""
        return self._settings.webcam_enabled

    @property
    def backup_enabled(self) -> bool:
        """Whether the phone may initiate a backup session."""
        return self._settings.backup_enabled

    # ── Public slots (called by the Settings UI) ───────────────────────────────

    @Slot(bool)
    def set_autostart(self, value: bool) -> None:
        """Persist the autostart setting and update the Windows Registry.

        In development builds (not frozen) the Registry write is skipped —
        only the setting is saved to disk.

        Args:
            value: ``True`` to enable autostart, ``False`` to disable it.

        Emits:
            autostart_changed: With the new value.
        """
        if value == self._settings.autostart:
            return
        self._settings.autostart = value
        self._service.save(self._settings)
        self._apply_autostart(value)
        self.autostart_changed.emit(value)

    @Slot(bool)
    def set_virtual_drive_enabled(self, value: bool) -> None:
        """Persist the Virtual Drive setting, adjust its wiring, and sync the phone.

        When disabled while a device is currently connected the service is
        stopped immediately (drive unmounted).  When enabled, the service
        will start on the *next* device connection.  After applying the change
        the new state is pushed to the connected phone (no-op if disconnected).

        Args:
            value: ``True`` to enable, ``False`` to disable.

        Emits:
            virtual_drive_changed: With the new value.
        """
        if not self._apply_virtual_drive(value):
            return
        # User-initiated change → push all four tool states to the phone.
        self._service.push_tools_state(
            value,
            self._settings.clipboard_enabled,
            self._settings.webcam_enabled,
            self._settings.backup_enabled,
        )

    @Slot(bool)
    def set_clipboard_enabled(self, value: bool) -> None:
        """Persist the clipboard-sync setting, apply it to the service, and sync the phone.

        Args:
            value: ``True`` to enable clipboard sync, ``False`` to disable it.

        Emits:
            clipboard_changed: With the new value.
        """
        if value == self._settings.clipboard_enabled:
            return
        self._settings.clipboard_enabled = value
        self._service.save(self._settings)
        self._clipboard.set_enabled(value)
        self.clipboard_changed.emit(value)
        # Push all four tool states to the phone (no-op if disconnected).
        self._service.push_tools_state(
            self._settings.virtual_drive_enabled,
            value,
            self._settings.webcam_enabled,
            self._settings.backup_enabled,
        )

    @Slot(bool)
    def set_webcam_enabled(self, value: bool) -> None:
        """Persist the webcam setting, apply it to the service, and sync the phone.

        Disabling while a stream is active stops it immediately (the virtual
        camera is released) — handled inside :meth:`WebcamService.set_enabled`.

        Args:
            value: ``True`` to enable webcam streaming, ``False`` to disable it.

        Emits:
            webcam_changed: With the new value.
        """
        if value == self._settings.webcam_enabled:
            return
        self._settings.webcam_enabled = value
        self._service.save(self._settings)
        self._webcam.set_enabled(value)
        self.webcam_changed.emit(value)
        # Push all four tool states to the phone (no-op if disconnected).
        self._service.push_tools_state(
            self._settings.virtual_drive_enabled,
            self._settings.clipboard_enabled,
            value,
            self._settings.backup_enabled,
        )

    @Slot(bool)
    def set_backup_enabled(self, value: bool) -> None:
        """Persist the backup setting, apply it to the service, and sync the phone.

        Disabling prevents Android from initiating new backup sessions — handled
        inside :meth:`BackupService.set_enabled`.  In-flight sessions already
        underway are unaffected.

        Args:
            value: ``True`` to allow backup sessions, ``False`` to block them.

        Emits:
            backup_changed: With the new value.
        """
        if value == self._settings.backup_enabled:
            return
        self._settings.backup_enabled = value
        self._service.save(self._settings)
        self._backup.set_enabled(value)
        self.backup_changed.emit(value)
        # Push all four tool states to the phone (no-op if disconnected).
        self._service.push_tools_state(
            self._settings.virtual_drive_enabled,
            self._settings.clipboard_enabled,
            self._settings.webcam_enabled,
            value,
        )

    @Slot(bool)
    def _apply_virtual_drive_from_phone(self, value: bool) -> None:
        # Phone-initiated change: persist + re-wire + update the UI, but do NOT
        # push back to the phone (that would echo into a sync loop). Mirrors the
        # Android SettingsRepository.setVirtualDriveEnabledFromPc path.
        self._apply_virtual_drive(value)

    @Slot(bool)
    def _apply_clipboard_from_phone(self, value: bool) -> None:
        # Phone-initiated change: persist + apply to service + update the UI.
        # Does NOT push back to avoid a sync echo loop.
        if value == self._settings.clipboard_enabled:
            return
        self._settings.clipboard_enabled = value
        self._service.save(self._settings)
        self._clipboard.set_enabled(value)
        self.clipboard_changed.emit(value)

    @Slot(bool)
    def _apply_webcam_from_phone(self, value: bool) -> None:
        # Phone-initiated change: persist + apply to service + update the UI.
        # Does NOT push back to avoid a sync echo loop.
        if value == self._settings.webcam_enabled:
            return
        self._settings.webcam_enabled = value
        self._service.save(self._settings)
        self._webcam.set_enabled(value)
        self.webcam_changed.emit(value)

    @Slot(bool)
    def _apply_backup_from_phone(self, value: bool) -> None:
        # Phone-initiated change: persist + apply to service + update the UI.
        # Does NOT push back to avoid a sync echo loop.
        if value == self._settings.backup_enabled:
            return
        self._settings.backup_enabled = value
        self._service.save(self._settings)
        self._backup.set_enabled(value)
        self.backup_changed.emit(value)

    # ── Private lifecycle helpers ──────────────────────────────────────────────

    def _apply_virtual_drive(self, value: bool) -> bool:
        # Persist the new Virtual Drive state, adjust lifecycle wiring, and emit
        # virtual_drive_changed. Returns False (a no-op) when the value is
        # unchanged so callers can skip any follow-up work (e.g. a phone push).
        if value == self._settings.virtual_drive_enabled:
            return False
        self._settings.virtual_drive_enabled = value
        self._service.save(self._settings)

        if value:
            self._wire_virtual_drive()
        else:
            self._unwire_virtual_drive()

        self.virtual_drive_changed.emit(value)
        return True

    def _wire_virtual_drive(self) -> None:
        # Connect device_connected/disconnected to the VirtualDrive service lifecycle.
        # Guard against double-connecting (Qt allows duplicate signal connections).
        if self._vdrive_wired:
            return
        self._device_vm.device_connected.connect(self._vdrive.start)
        self._device_vm.device_disconnected.connect(self._vdrive.stop)
        self._vdrive_wired = True

        # Mount immediately if a device is already connected — device_connected is a
        # one-shot transition signal and won't re-fire for this existing session, so
        # a runtime re-enable would otherwise wait until the next reconnect. Mirrors
        # _unwire_virtual_drive()'s immediate stop. start() is idempotent.
        if self._connectivity.connected:
            self._vdrive.start()

    def _unwire_virtual_drive(self) -> None:
        # Disconnect lifecycle signals and stop the service if a device is connected now.
        if self._vdrive_wired:
            try:
                self._device_vm.device_connected.disconnect(self._vdrive.start)
                self._device_vm.device_disconnected.disconnect(self._vdrive.stop)
            except RuntimeError:
                pass  # Signal was never connected — safe to ignore.
            self._vdrive_wired = False

        # Unmount immediately if the drive is currently running.
        if self._connectivity.connected:
            self._vdrive.stop()

    def _apply_autostart(self, enabled: bool) -> None:
        # Write / delete the Windows Registry run key.
        # Skipped in development builds (not frozen by PyInstaller).
        if not getattr(sys, "frozen", False):
            return
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if enabled:
                    exe: str = sys.executable  # Path to SyncDose.exe
                    winreg.SetValueEx(key, "SyncDose", 0, winreg.REG_SZ, f'"{exe}"')
                else:
                    try:
                        winreg.DeleteValue(key, "SyncDose")
                    except FileNotFoundError:
                        pass  # Key was never written — nothing to remove.
        except OSError:
            pass  # Registry unavailable (non-Windows or insufficient permissions).
