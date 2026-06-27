"""Unit tests for SettingsViewModel — tool-enabled sync apply/echo behavior."""

from unittest.mock import MagicMock, call

import pytest

from domain.dto.settings import SettingsDTO
from viewmodels.settings import SettingsViewModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_settings_service() -> MagicMock:
    """Mock SettingsService whose load() returns a concrete DTO (all features at defaults)."""
    service = MagicMock()
    service.load.return_value = SettingsDTO(autostart=False, virtual_drive_enabled=False)
    return service


@pytest.fixture()
def view_model(mock_settings_service: MagicMock) -> SettingsViewModel:
    return SettingsViewModel(
        settings_service=mock_settings_service,
        device_viewmodel=MagicMock(),
        virtual_drive_service=MagicMock(),
        connectivity_service=MagicMock(),
        clipboard_service=MagicMock(),
        webcam_service=MagicMock(),
        backup_service=MagicMock(),
    )


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_init_connects_tools_state_received(mock_settings_service: MagicMock) -> None:
    vm = SettingsViewModel(
        settings_service=mock_settings_service,
        device_viewmodel=MagicMock(),
        virtual_drive_service=MagicMock(),
        connectivity_service=MagicMock(),
        clipboard_service=MagicMock(),
        webcam_service=MagicMock(),
        backup_service=MagicMock(),
    )
    mock_settings_service.tools_state_received.connect.assert_called_once_with(
        vm._apply_virtual_drive_from_phone
    )
    mock_settings_service.clipboard_state_received.connect.assert_called_once_with(
        vm._apply_clipboard_from_phone
    )
    mock_settings_service.webcam_state_received.connect.assert_called_once_with(
        vm._apply_webcam_from_phone
    )
    mock_settings_service.backup_state_received.connect.assert_called_once_with(
        vm._apply_backup_from_phone
    )


def test_init_applies_persisted_tool_state(mock_settings_service: MagicMock) -> None:
    """Construction pushes the persisted enabled flags into all feature services."""
    mock_settings_service.load.return_value = SettingsDTO(
        clipboard_enabled=False, webcam_enabled=True, backup_enabled=False
    )
    clipboard = MagicMock()
    webcam = MagicMock()
    backup = MagicMock()

    SettingsViewModel(
        settings_service=mock_settings_service,
        device_viewmodel=MagicMock(),
        virtual_drive_service=MagicMock(),
        connectivity_service=MagicMock(),
        clipboard_service=clipboard,
        webcam_service=webcam,
        backup_service=backup,
    )

    clipboard.set_enabled.assert_called_once_with(False)
    webcam.set_enabled.assert_called_once_with(True)
    backup.set_enabled.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# User-initiated Virtual Drive toggle: persists, emits, AND pushes all three
# ---------------------------------------------------------------------------


def test_user_toggle_pushes_to_phone(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.virtual_drive_changed.connect(lambda v: received.append(v))

    # Fixture DTO: vdrive=False, clipboard=True, webcam=True
    view_model.set_virtual_drive_enabled(True)

    assert received == [True]
    mock_settings_service.save.assert_called_once()
    # All four current states are pushed together (backup default = True)
    mock_settings_service.push_tools_state.assert_called_once_with(True, True, True, True)


def test_user_toggle_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    # Current value is False; setting False again must do nothing.
    view_model.set_virtual_drive_enabled(False)

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()


# ---------------------------------------------------------------------------
# Re-enable while connected must mount immediately (device_connected is a
# one-shot transition signal and won't re-fire for the existing session).
# ---------------------------------------------------------------------------


def test_enable_while_connected_starts_drive_now(
    mock_settings_service: MagicMock,
) -> None:
    """Re-enabling Virtual Drive while a device is connected mounts it now."""
    vdrive = MagicMock()
    connectivity = MagicMock()
    connectivity.connected = True

    vm = SettingsViewModel(
        settings_service=mock_settings_service,
        device_viewmodel=MagicMock(),
        virtual_drive_service=vdrive,
        connectivity_service=connectivity,
        clipboard_service=MagicMock(),
        webcam_service=MagicMock(),
        backup_service=MagicMock(),
    )

    # Fixture DTO: virtual_drive_enabled=False, so it was not wired at construction.
    vm.set_virtual_drive_enabled(True)

    vdrive.start.assert_called_once()


def test_enable_while_disconnected_does_not_start_drive(
    mock_settings_service: MagicMock,
) -> None:
    """Re-enabling while disconnected defers the mount to the next connect."""
    vdrive = MagicMock()
    connectivity = MagicMock()
    connectivity.connected = False

    vm = SettingsViewModel(
        settings_service=mock_settings_service,
        device_viewmodel=MagicMock(),
        virtual_drive_service=vdrive,
        connectivity_service=connectivity,
        clipboard_service=MagicMock(),
        webcam_service=MagicMock(),
        backup_service=MagicMock(),
    )

    vm.set_virtual_drive_enabled(True)

    vdrive.start.assert_not_called()


def test_init_enabled_while_disconnected_does_not_start_drive(
    mock_settings_service: MagicMock,
) -> None:
    """Startup with the setting enabled but no device connected must not mount eagerly."""
    mock_settings_service.load.return_value = SettingsDTO(virtual_drive_enabled=True)
    vdrive = MagicMock()
    connectivity = MagicMock()
    connectivity.connected = False

    SettingsViewModel(
        settings_service=mock_settings_service,
        device_viewmodel=MagicMock(),
        virtual_drive_service=vdrive,
        connectivity_service=connectivity,
        clipboard_service=MagicMock(),
        webcam_service=MagicMock(),
        backup_service=MagicMock(),
    )

    vdrive.start.assert_not_called()


# ---------------------------------------------------------------------------
# Phone-initiated apply (phone → PC): persists, emits, but does NOT echo back
# ---------------------------------------------------------------------------


def test_phone_apply_does_not_echo(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.virtual_drive_changed.connect(lambda v: received.append(v))

    view_model._apply_virtual_drive_from_phone(True)

    assert received == [True]
    mock_settings_service.save.assert_called_once()
    mock_settings_service.push_tools_state.assert_not_called()


def test_phone_apply_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    view_model._apply_virtual_drive_from_phone(False)

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()


# ---------------------------------------------------------------------------
# Clipboard toggle: persists + applies to service + pushes to phone
# ---------------------------------------------------------------------------


def test_set_clipboard_enabled_persists_and_applies(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.clipboard_changed.connect(lambda v: received.append(v))

    view_model.set_clipboard_enabled(False)  # default is True

    assert received == [False]
    mock_settings_service.save.assert_called_once()
    view_model._clipboard.set_enabled.assert_called_with(False)
    # vdrive=False (fixture default), clipboard=False (new value), webcam=True (default), backup=True (default)
    mock_settings_service.push_tools_state.assert_called_once_with(False, False, True, True)


def test_set_clipboard_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    view_model.set_clipboard_enabled(True)  # already True

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()


def test_phone_clipboard_apply_does_not_echo(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.clipboard_changed.connect(lambda v: received.append(v))

    view_model._apply_clipboard_from_phone(False)

    assert received == [False]
    mock_settings_service.save.assert_called_once()
    mock_settings_service.push_tools_state.assert_not_called()


def test_phone_clipboard_apply_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    view_model._apply_clipboard_from_phone(True)  # already True

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()


# ---------------------------------------------------------------------------
# Webcam toggle: persists + applies to service + pushes to phone
# ---------------------------------------------------------------------------


def test_set_webcam_enabled_persists_and_applies(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.webcam_changed.connect(lambda v: received.append(v))

    view_model.set_webcam_enabled(False)  # default is True

    assert received == [False]
    mock_settings_service.save.assert_called_once()
    view_model._webcam.set_enabled.assert_called_with(False)
    # vdrive=False (fixture default), clipboard=True (default), webcam=False (new value), backup=True (default)
    mock_settings_service.push_tools_state.assert_called_once_with(False, True, False, True)


def test_set_webcam_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    view_model.set_webcam_enabled(True)  # already True

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()


def test_phone_webcam_apply_does_not_echo(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.webcam_changed.connect(lambda v: received.append(v))

    view_model._apply_webcam_from_phone(False)

    assert received == [False]
    mock_settings_service.save.assert_called_once()
    mock_settings_service.push_tools_state.assert_not_called()


def test_phone_webcam_apply_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    view_model._apply_webcam_from_phone(True)  # already True

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()


# ---------------------------------------------------------------------------
# Backup toggle: persists + applies to service + pushes to phone
# ---------------------------------------------------------------------------


def test_set_backup_enabled_persists_and_applies(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.backup_changed.connect(lambda v: received.append(v))

    view_model.set_backup_enabled(False)  # default is True

    assert received == [False]
    mock_settings_service.save.assert_called_once()
    view_model._backup.set_enabled.assert_called_with(False)
    # vdrive=False (fixture default), clipboard=True (default), webcam=True (default), backup=False (new value)
    mock_settings_service.push_tools_state.assert_called_once_with(False, True, True, False)


def test_set_backup_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    view_model.set_backup_enabled(True)  # already True

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()


def test_phone_backup_apply_does_not_echo(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    received: list[bool] = []
    view_model.backup_changed.connect(lambda v: received.append(v))

    view_model._apply_backup_from_phone(False)

    assert received == [False]
    mock_settings_service.save.assert_called_once()
    mock_settings_service.push_tools_state.assert_not_called()


def test_phone_backup_apply_unchanged_is_noop(
    view_model: SettingsViewModel, mock_settings_service: MagicMock
) -> None:
    view_model._apply_backup_from_phone(True)  # already True

    mock_settings_service.save.assert_not_called()
    mock_settings_service.push_tools_state.assert_not_called()
