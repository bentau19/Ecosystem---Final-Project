"""Unit tests for SettingsRepository — autostart-only JSON round-trip."""

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


def test_load_returns_default_when_file_absent(repository: SettingsRepository) -> None:
    # Autostart defaults ON (opt-out) on a fresh install.
    assert repository.load().autostart is True


def test_save_then_load_round_trips_autostart(repository: SettingsRepository) -> None:
    repository.save(SettingsDTO(autostart=False))

    assert repository.load() == SettingsDTO(autostart=False)


def test_save_persists_only_autostart_to_disk(repository: SettingsRepository) -> None:
    repository.save(SettingsDTO(autostart=False))

    data = json.loads(repository._path.read_text(encoding="utf-8"))
    assert data == {"autostart": False}


def test_load_defaults_when_key_missing(repository: SettingsRepository) -> None:
    repository._path.write_text(json.dumps({}), encoding="utf-8")

    assert repository.load().autostart is True


def test_load_ignores_legacy_feature_keys(repository: SettingsRepository) -> None:
    """A pre-consolidation file with the old feature keys still loads autostart."""
    repository._path.write_text(
        json.dumps({"autostart": False, "clipboard_enabled": True, "webcam_enabled": False}),
        encoding="utf-8",
    )

    assert repository.load().autostart is False
