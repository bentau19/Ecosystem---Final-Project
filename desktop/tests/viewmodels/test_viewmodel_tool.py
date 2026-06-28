"""Unit tests for ToolViewModel — grid DTOs + feature orchestration."""

from unittest.mock import MagicMock

import pytest

from domain.dto.tool import ToolDTO
from domain.entities.tool import ToolEntity
from domain.tool_catalog import (
    TITLE_BACKUP,
    TITLE_CLIPBOARD,
    TITLE_SEND_FILE,
    TITLE_VIRTUAL_DRIVE,
    TITLE_WEBCAM,
)
from viewmodels.tool import ToolViewModel


def _tool(title: str, enabled: bool) -> ToolEntity:
    return ToolEntity(title, f"{title} description", "icon", enabled)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tools() -> list[ToolEntity]:
    # Virtual Drive starts disabled so construction does not wire its lifecycle.
    return [
        _tool(TITLE_SEND_FILE, True),
        _tool(TITLE_VIRTUAL_DRIVE, False),
        _tool(TITLE_CLIPBOARD, True),
        _tool(TITLE_WEBCAM, True),
        _tool(TITLE_BACKUP, True),
    ]


@pytest.fixture()
def mock_tool_service(tools: list[ToolEntity]) -> MagicMock:
    """A ToolService mock whose get_by_id/save_tool share one in-memory map."""
    by_id = {t.title: t for t in tools}

    service = MagicMock()
    service.get_all.return_value = list(tools)
    service.get_by_id.side_effect = lambda title: by_id.get(title)

    def _save(entity: ToolEntity) -> None:
        by_id[entity.title] = entity

    service.save_tool.side_effect = _save
    return service


def _make_vm(
    tool_service: MagicMock,
    *,
    clipboard: MagicMock | None = None,
    webcam: MagicMock | None = None,
    backup: MagicMock | None = None,
    vdrive: MagicMock | None = None,
    connectivity: MagicMock | None = None,
    device_vm: MagicMock | None = None,
    settings: MagicMock | None = None,
) -> ToolViewModel:
    if connectivity is None:
        connectivity = MagicMock()
        connectivity.connected = False
    return ToolViewModel(
        tool_service=tool_service,
        clipboard_service=clipboard or MagicMock(),
        webcam_service=webcam or MagicMock(),
        backup_service=backup or MagicMock(),
        virtual_drive_service=vdrive or MagicMock(),
        connectivity_service=connectivity,
        device_viewmodel=device_vm or MagicMock(),
        settings_service=settings or MagicMock(),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_init_applies_persisted_feature_state(mock_tool_service: MagicMock) -> None:
    clipboard, webcam, backup = MagicMock(), MagicMock(), MagicMock()

    _make_vm(mock_tool_service, clipboard=clipboard, webcam=webcam, backup=backup)

    clipboard.set_enabled.assert_called_once_with(True)
    webcam.set_enabled.assert_called_once_with(True)
    backup.set_enabled.assert_called_once_with(True)


def test_init_does_not_wire_disabled_virtual_drive(mock_tool_service: MagicMock) -> None:
    device_vm = MagicMock()

    _make_vm(mock_tool_service, device_vm=device_vm)

    device_vm.device_connected.connect.assert_not_called()


def test_init_connects_phone_signals(mock_tool_service: MagicMock) -> None:
    settings = MagicMock()

    vm = _make_vm(mock_tool_service, settings=settings)

    settings.tools_state_received.connect.assert_called_once_with(vm._apply_virtual_drive_from_phone)
    settings.clipboard_state_received.connect.assert_called_once_with(vm._apply_clipboard_from_phone)
    settings.webcam_state_received.connect.assert_called_once_with(vm._apply_webcam_from_phone)
    settings.backup_state_received.connect.assert_called_once_with(vm._apply_backup_from_phone)


# ---------------------------------------------------------------------------
# Grid population
# ---------------------------------------------------------------------------


def test_load_tools_emits_dtos(
    mock_tool_service: MagicMock, tools: list[ToolEntity]
) -> None:
    vm = _make_vm(mock_tool_service)
    received: list = []
    vm.tools_loaded.connect(lambda t: received.append(t))

    vm.load_tools()

    assert len(received) == 1
    assert all(isinstance(d, ToolDTO) for d in received[0])
    assert {d.title for d in received[0]} == {t.title for t in tools}


def test_feature_tools_returns_four_features(mock_tool_service: MagicMock) -> None:
    vm = _make_vm(mock_tool_service)

    titles = [d.title for d in vm.feature_tools()]

    # Catalog order, and the Send File action tool is excluded.
    assert titles == [TITLE_VIRTUAL_DRIVE, TITLE_CLIPBOARD, TITLE_WEBCAM, TITLE_BACKUP]
    assert TITLE_SEND_FILE not in titles


# ---------------------------------------------------------------------------
# User toggle: persists + applies to service + pushes to phone
# ---------------------------------------------------------------------------


def test_set_tool_enabled_persists_applies_and_pushes(mock_tool_service: MagicMock) -> None:
    clipboard, settings = MagicMock(), MagicMock()
    vm = _make_vm(mock_tool_service, clipboard=clipboard, settings=settings)

    changed: list = []
    vm.tool_enabled_changed.connect(lambda title, enabled: changed.append((title, enabled)))

    vm.set_tool_enabled(TITLE_CLIPBOARD, False)

    mock_tool_service.save_tool.assert_called_once_with(
        ToolEntity(TITLE_CLIPBOARD, "Clipboard Sync description", "icon", False)
    )
    clipboard.set_enabled.assert_called_with(False)
    assert changed == [(TITLE_CLIPBOARD, False)]
    # vdrive=False, clipboard=False (new value), webcam=True, backup=True
    settings.push_tools_state.assert_called_once_with(False, False, True, True)


def test_set_tool_enabled_unchanged_is_noop(mock_tool_service: MagicMock) -> None:
    settings = MagicMock()
    vm = _make_vm(mock_tool_service, settings=settings)

    vm.set_tool_enabled(TITLE_CLIPBOARD, True)  # already enabled

    mock_tool_service.save_tool.assert_not_called()
    settings.push_tools_state.assert_not_called()


def test_enable_virtual_drive_while_connected_starts_now(mock_tool_service: MagicMock) -> None:
    vdrive, device_vm = MagicMock(), MagicMock()
    connectivity = MagicMock()
    connectivity.connected = True

    vm = _make_vm(
        mock_tool_service, vdrive=vdrive, device_vm=device_vm, connectivity=connectivity
    )

    vm.set_tool_enabled(TITLE_VIRTUAL_DRIVE, True)  # was disabled

    device_vm.device_connected.connect.assert_called_once_with(vdrive.start)
    vdrive.start.assert_called_once()


# ---------------------------------------------------------------------------
# Phone-initiated apply: persists + applies, but does NOT echo back
# ---------------------------------------------------------------------------


def test_phone_apply_does_not_push(mock_tool_service: MagicMock) -> None:
    clipboard, settings = MagicMock(), MagicMock()
    vm = _make_vm(mock_tool_service, clipboard=clipboard, settings=settings)

    changed: list = []
    vm.tool_enabled_changed.connect(lambda title, enabled: changed.append((title, enabled)))

    vm._apply_clipboard_from_phone(False)

    mock_tool_service.save_tool.assert_called_once()
    clipboard.set_enabled.assert_called_with(False)
    assert changed == [(TITLE_CLIPBOARD, False)]
    settings.push_tools_state.assert_not_called()


def test_phone_apply_unchanged_is_noop(mock_tool_service: MagicMock) -> None:
    settings = MagicMock()
    vm = _make_vm(mock_tool_service, settings=settings)

    vm._apply_backup_from_phone(True)  # already enabled

    mock_tool_service.save_tool.assert_not_called()
    settings.push_tools_state.assert_not_called()


# ---------------------------------------------------------------------------
# Push outcome: failure reverts to the last approved baseline; success advances it
# ---------------------------------------------------------------------------


def test_init_connects_push_result_signals(mock_tool_service: MagicMock) -> None:
    settings = MagicMock()

    vm = _make_vm(mock_tool_service, settings=settings)

    settings.tools_push_succeeded.connect.assert_called_once_with(vm._on_push_succeeded)
    settings.tools_push_failed.connect.assert_called_once_with(vm._on_push_failed)


def test_push_failed_reverts_to_last_approved(mock_tool_service: MagicMock) -> None:
    clipboard, settings = MagicMock(), MagicMock()
    vm = _make_vm(mock_tool_service, clipboard=clipboard, settings=settings)

    changed: list = []
    vm.tool_enabled_changed.connect(lambda title, enabled: changed.append((title, enabled)))

    vm.set_tool_enabled(TITLE_CLIPBOARD, False)  # optimistic; baseline still True
    vm._on_push_failed()

    # Reverted back to the approved value (True).
    assert mock_tool_service.get_by_id(TITLE_CLIPBOARD).is_enabled is True
    assert clipboard.set_enabled.call_args_list[-1].args == (True,)
    assert changed == [(TITLE_CLIPBOARD, False), (TITLE_CLIPBOARD, True)]


def test_push_succeeded_advances_baseline(mock_tool_service: MagicMock) -> None:
    clipboard, settings = MagicMock(), MagicMock()
    vm = _make_vm(mock_tool_service, clipboard=clipboard, settings=settings)

    vm.set_tool_enabled(TITLE_CLIPBOARD, False)
    vm._on_push_succeeded(False, False, True, True)  # phone confirmed the new state
    vm._on_push_failed()  # a later failure must not undo a confirmed value

    assert mock_tool_service.get_by_id(TITLE_CLIPBOARD).is_enabled is False


def test_phone_apply_advances_baseline(mock_tool_service: MagicMock) -> None:
    clipboard, settings = MagicMock(), MagicMock()
    vm = _make_vm(mock_tool_service, clipboard=clipboard, settings=settings)

    vm._apply_clipboard_from_phone(False)  # phone-agreed value → new baseline
    vm._on_push_failed()  # must not roll the phone's own value back

    assert mock_tool_service.get_by_id(TITLE_CLIPBOARD).is_enabled is False
