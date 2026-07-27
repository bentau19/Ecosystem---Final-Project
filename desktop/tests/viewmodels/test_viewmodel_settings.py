"""Unit tests for SettingsViewModel — autostart only (dev build: no Registry)."""

from unittest.mock import MagicMock

import pytest

from domain.dto.settings import SettingsDTO
from viewmodels.settings import SettingsViewModel


@pytest.fixture()
def mock_settings_service() -> MagicMock:
    """Mock SettingsService whose load() returns autostart=False."""
    service = MagicMock()
    service.load.return_value = SettingsDTO(autostart=False)
    return service


@pytest.fixture()
def view_model(mock_settings_service: MagicMock) -> SettingsViewModel:
    return SettingsViewModel(settings_service=mock_settings_service)


def test_autostart_property_reflects_loaded_value(mock_settings_service: MagicMock) -> None:
    mock_settings_service.load.return_value = SettingsDTO(autostart=True)

    vm = SettingsViewModel(settings_service=mock_settings_service)

    assert vm.autostart is True


def test_set_autostart_persists_and_emits(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.autostart_changed.connect(lambda v: received.append(v))

    view_model.set_autostart(True)  # current value is False

    assert received == [True]
    assert view_model.autostart is True
    mock_settings_service.save.assert_called_once()


def test_set_autostart_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.autostart_changed.connect(lambda v: received.append(v))

    view_model.set_autostart(False)  # already False

    assert received == []
    mock_settings_service.save.assert_not_called()
