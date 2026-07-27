import json

from domain.dto.settings import SettingsDTO
from utils.paths import data_dir


# Sentinel defaults — applied when the JSON file is absent or a key is missing.
_DEFAULTS = SettingsDTO()


class SettingsRepository:
    """Thin JSON-backed repository for user application settings.

    Persists a :class:`~domain.dto.settings.SettingsDTO` (just the autostart
    flag) to disk as a small JSON file.  In a frozen (PyInstaller) build the
    file lives at ``%APPDATA%\\SyncDose\\settings.json``; in development it lives
    at ``desktop/data/settings.json`` alongside the other JSON data files.

    Writes are atomic: the new content is written to a ``.tmp`` sibling and then
    renamed over the real file so a crash mid-write never leaves a corrupt
    settings file on disk.
    """

    def __init__(self) -> None:
        """Locate (and create if necessary) the settings directory."""
        self._path = data_dir() / "settings.json"

    def load(self) -> SettingsDTO:
        """Read settings from disk, returning defaults when absent or invalid.

        Returns:
            A :class:`~domain.dto.settings.SettingsDTO` with the value from the
            JSON file, falling back to the default when the file is absent or
            the key is missing.
        """
        try:
            if not self._path.exists():
                return SettingsDTO(autostart=_DEFAULTS.autostart)
            with open(self._path, "r", encoding="utf-8") as fh:
                data: dict = json.load(fh)
            return SettingsDTO(autostart=bool(data.get("autostart", _DEFAULTS.autostart)))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            # Corrupt file or permission error — return defaults silently.
            return SettingsDTO(autostart=_DEFAULTS.autostart)

    def save(self, settings: SettingsDTO) -> None:
        """Persist *settings* to disk atomically.

        Args:
            settings: The :class:`~domain.dto.settings.SettingsDTO` to save.
        """
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"autostart": settings.autostart}, fh, indent=2)
            tmp.replace(self._path)
        except OSError:
            # Best-effort write — if the disk is full or the path is read-only
            # we just skip silently rather than crashing the UI.
            pass
