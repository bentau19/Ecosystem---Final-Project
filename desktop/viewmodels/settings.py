import sys

from PySide6.QtCore import QObject, Signal, Slot

from domain.dto.settings import SettingsDTO
from services.settings import SettingsService


class SettingsViewModel(QObject):
    """ViewModel for application settings — the Windows autostart flag.

    Per-tool enable/disable state now lives in the tool list and is coordinated
    by :class:`~viewmodels.tool.ToolViewModel`; this viewmodel only owns the
    autostart preference and the matching Windows Registry "Run" entry.

    Signals:
        autostart_changed (Signal[bool]): Emitted after the autostart setting changes.
    """

    autostart_changed: Signal = Signal(bool)

    def __init__(
        self,
        settings_service: SettingsService,
        parent: QObject | None = None,
    ) -> None:
        """Load the persisted autostart setting and reconcile the Registry entry.

        Args:
            settings_service: The settings service layer (wraps the repository).
            parent: Optional parent QObject.
        """
        super().__init__(parent)

        self._service: SettingsService = settings_service
        self._settings: SettingsDTO = settings_service.load()

        # Reconcile the Windows autostart registry entry with the persisted/default
        # setting on every launch (idempotent: writes when ON, deletes when OFF) so
        # a fresh install with autostart defaulting ON actually registers, and the
        # entry self-heals if it drifts. No-op in dev builds (guarded by sys.frozen).
        self._apply_autostart(self._settings.autostart)

    @property
    def autostart(self) -> bool:
        """Whether SyncDose is currently set to launch with Windows."""
        return self._settings.autostart

    @Slot(bool)
    def set_autostart(self, value: bool) -> None:
        """Persist the autostart setting and update the Windows Registry.

        In development builds (not frozen) the Registry write is skipped — only
        the setting is saved to disk.

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
