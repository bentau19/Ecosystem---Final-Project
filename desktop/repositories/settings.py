import json
import os
import sys
from pathlib import Path

from domain.dto.settings import SettingsDTO


# Sentinel defaults — applied when the JSON file is absent or a key is missing.
_DEFAULTS = SettingsDTO(autostart=False, virtual_drive_enabled=False, backup_enabled=True)


class SettingsRepository:
    """Thin JSON-backed repository for user application settings.

    Persists a :class:`~domain.dto.settings.SettingsDTO` to disk as a
    small JSON file.  In a frozen (PyInstaller) build the file lives at
    ``%APPDATA%\\SyncDose\\settings.json``; in development it lives at
    ``desktop/data/settings.json`` alongside the SQLite database.

    Writes are atomic: the new content is written to a ``.tmp`` sibling
    and then renamed over the real file so a crash mid-write never leaves
    a corrupt settings file on disk.
    """

    def __init__(self) -> None:
        """Locate (and create if necessary) the settings directory."""
        if getattr(sys, "frozen", False):
            self._path = Path(os.environ["APPDATA"]) / "SyncDose" / "settings.json"
        else:
            self._path = Path(__file__).parent.parent / "data" / "settings.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> SettingsDTO:
        """Read settings from disk, returning defaults for any missing keys.

        Returns:
            A :class:`~domain.dto.settings.SettingsDTO` with values from
            the JSON file, falling back to defaults when the file is absent
            or any key is missing.
        """
        try:
            if not self._path.exists():
                return SettingsDTO(
                    autostart=_DEFAULTS.autostart,
                    virtual_drive_enabled=_DEFAULTS.virtual_drive_enabled,
                    clipboard_enabled=_DEFAULTS.clipboard_enabled,
                    webcam_enabled=_DEFAULTS.webcam_enabled,
                    backup_enabled=_DEFAULTS.backup_enabled,
                )
            with open(self._path, "r", encoding="utf-8") as fh:
                data: dict = json.load(fh)
            return SettingsDTO(
                autostart=bool(data.get("autostart", _DEFAULTS.autostart)),
                virtual_drive_enabled=bool(
                    data.get("virtual_drive_enabled", _DEFAULTS.virtual_drive_enabled)
                ),
                clipboard_enabled=bool(
                    data.get("clipboard_enabled", _DEFAULTS.clipboard_enabled)
                ),
                webcam_enabled=bool(
                    data.get("webcam_enabled", _DEFAULTS.webcam_enabled)
                ),
                backup_enabled=bool(
                    data.get("backup_enabled", _DEFAULTS.backup_enabled)
                ),
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            # Corrupt file or permission error — return defaults silently.
            return SettingsDTO(
                autostart=_DEFAULTS.autostart,
                virtual_drive_enabled=_DEFAULTS.virtual_drive_enabled,
                clipboard_enabled=_DEFAULTS.clipboard_enabled,
                webcam_enabled=_DEFAULTS.webcam_enabled,
                backup_enabled=_DEFAULTS.backup_enabled,
            )

    def save(self, settings: SettingsDTO) -> None:
        """Persist *settings* to disk atomically.

        Args:
            settings: The :class:`~domain.dto.settings.SettingsDTO` to save.
        """
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "autostart": settings.autostart,
                        "virtual_drive_enabled": settings.virtual_drive_enabled,
                        "clipboard_enabled": settings.clipboard_enabled,
                        "webcam_enabled": settings.webcam_enabled,
                        "backup_enabled": settings.backup_enabled,
                    },
                    fh,
                    indent=2,
                )
            tmp.replace(self._path)
        except OSError:
            # Best-effort write — if the disk is full or the path is read-only
            # we just skip silently rather than crashing the UI.
            pass
