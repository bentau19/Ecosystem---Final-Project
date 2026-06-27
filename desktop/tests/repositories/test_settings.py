"""Unit tests for SettingsRepository — JSON round-trip incl. the tool toggles."""

import json
from pathlib import Path

import pytest

from domain.dto.settings import SettingsDTO
from repositories.settings import SettingsRepository


@pytest.fixture()
def repository(tmp_path: Path) -> SettingsRepository:
    """A SettingsRepository pointed at an isolated settings.json in tmp_path."""
    repo = SettingsRepository()
    repo._path = tmp_path / "settings.json"
    return repo


def test_load_returns_defaults_when_file_absent(repository: SettingsRepository) -> None:
    settings = repository.load()

    # Clipboard/Webcam default ON (opt-out); Virtual Drive / autostart default OFF.
    assert settings.autostart is False
    assert settings.virtual_drive_enabled is False
    assert settings.clipboard_enabled is True
    assert settings.webcam_enabled is True


def test_save_then_load_round_trips_all_fields(repository: SettingsRepository) -> None:
    repository.save(
        SettingsDTO(
            autostart=True,
            virtual_drive_enabled=True,
            clipboard_enabled=False,
            webcam_enabled=False,
        )
    )

    loaded = repository.load()
    assert loaded == SettingsDTO(
        autostart=True,
        virtual_drive_enabled=True,
        clipboard_enabled=False,
        webcam_enabled=False,
    )


def test_save_persists_new_keys_to_disk(repository: SettingsRepository) -> None:
    repository.save(SettingsDTO(clipboard_enabled=False, webcam_enabled=True))

    data = json.loads(repository._path.read_text(encoding="utf-8"))
    assert data["clipboard_enabled"] is False
    assert data["webcam_enabled"] is True


def test_load_defaults_missing_keys_for_legacy_file(repository: SettingsRepository) -> None:
    """A pre-existing file without the new keys loads them as enabled (default)."""
    repository._path.write_text(
        json.dumps({"autostart": True, "virtual_drive_enabled": True}),
        encoding="utf-8",
    )

    loaded = repository.load()
    assert loaded.autostart is True
    assert loaded.virtual_drive_enabled is True
    assert loaded.clipboard_enabled is True
    assert loaded.webcam_enabled is True
