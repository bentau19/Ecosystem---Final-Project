from dataclasses import dataclass, field


@dataclass
class SettingsDTO:
    """Data Transfer Object for user-configurable application settings.

    Consumed by :class:`~viewmodels.settings.SettingsViewModel` and
    persisted by :class:`~repositories.settings.SettingsRepository`.

    Attributes:
        autostart: Whether SyncDose should launch automatically with Windows.
        virtual_drive_enabled: Whether the VirtualDrive service should start
            automatically when a device connects.
        clipboard_enabled: Whether two-directional clipboard sync is active.
            Defaults to ``True`` (opt-out) so existing always-on behaviour is
            preserved.
        webcam_enabled: Whether the phone may stream to the virtual webcam.
            Defaults to ``True`` (opt-out).
        backup_enabled: Whether the phone may initiate a backup session.
            Defaults to ``True`` (opt-out); synced bidirectionally with the phone.
    """

    autostart: bool = False
    virtual_drive_enabled: bool = False
    clipboard_enabled: bool = True
    webcam_enabled: bool = True
    backup_enabled: bool = True
