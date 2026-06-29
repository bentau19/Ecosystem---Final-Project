from dataclasses import dataclass


@dataclass
class SettingsDTO:
    """Data Transfer Object for user-configurable application settings.

    Consumed by :class:`~viewmodels.settings.SettingsViewModel` and persisted
    by :class:`~repositories.settings.SettingsRepository`.

    Only the autostart preference lives here.  Per-tool enable/disable state is
    the responsibility of the tool list (``tools.json`` via
    :class:`~repositories.tool.ToolRepository`) — see
    :class:`~viewmodels.tool.ToolViewModel`.

    Attributes:
        autostart: Whether SyncDose should launch automatically with Windows.
            Defaults to ``True`` (opt-out).
    """

    autostart: bool = True
    dark_mode: bool = False
