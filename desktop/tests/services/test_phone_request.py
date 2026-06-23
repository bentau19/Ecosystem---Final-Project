"""Unit tests for services.phone_request — PhoneRequestService."""

import threading
from unittest.mock import MagicMock, call

import pytest
from pytestqt.qtbot import QtBot

from services.phone_request import PhoneRequestService
from domain.enums.session_channels import SessionChannels


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> tuple[PhoneRequestService, MagicMock, MagicMock]:
    """Construct PhoneRequestService with all collaborator services mocked.

    Returns:
        Tuple of ``(service, mock_connectivity, mock_file_transfer)``.
    """
    mock_connectivity = MagicMock()
    mock_connectivity.connected = True
    mock_file_transfer = MagicMock()
    mock_backup = MagicMock()
    mock_device_info = MagicMock()

    svc = PhoneRequestService(
        connectivity_service=mock_connectivity,
        file_transfer_service=mock_file_transfer,
        device_info_service=mock_device_info,
        backup_service=mock_backup,
    )
    svc._is_running.set()
    return svc, mock_connectivity, mock_file_transfer


def _gated_channel_context(gate: threading.Event) -> MagicMock:
    """Return a mock context manager whose ``__enter__`` blocks until *gate* is set.

    Used to simulate ``tau.connect()`` blocking until the phone side meets.

    Args:
        gate: Event that releases the block when set.

    Returns:
        A MagicMock usable as ``with tau.connect(...) as _:``.
    """
    cm = MagicMock()
    cm.__enter__ = MagicMock(side_effect=lambda s: gate.wait())
    cm.__exit__ = MagicMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# operations dict
# ---------------------------------------------------------------------------

#
# def test_operations_contains_disconnect_from_phone() -> None:
#     """DISCONNECT_FROM_PHONE is registered in operations pointing to disconnect_device."""
#     svc, mock_connectivity, _ = _make_service()
#     key = SessionChannels.DISCONNECT_FROM_PHONE.value
#     assert key in svc.operations
#     assert svc.operations[key] == mock_connectivity.disconnect


# ---------------------------------------------------------------------------
# Android crash passive detection
# ---------------------------------------------------------------------------


def test_listen_to_channels_calls_connectivity_stop_when_poll_raises(
        qtbot: QtBot,
) -> None:
    """connectivity.stop() is called when get_peer_waiting_words() raises.

    When Android crashes, TauSync's get_peer_waiting_words() raises RuntimeError
    on the dead socket.  The fix wraps the poll in try/except and calls
    connectivity.stop() — the same path used for a graceful phone-initiated
    disconnect — so the UI navigates back to the login screen automatically.
    """
    svc, mock_connectivity, _ = _make_service()

    # Simulate Android crash: first poll raises, subsequent ones block forever
    # on an internal event so stop() is only called once.
    _block = threading.Event()

    def _raise_then_block() -> list[str]:
        if not hasattr(_raise_then_block, "_raised"):
            _raise_then_block._raised = True  # type: ignore[attr-defined]
            raise RuntimeError("transport is not connected")
        _block.wait()
        return []

    mock_connectivity.tau.get_peer_waiting_words.side_effect = _raise_then_block

    # Run the listener directly on a background thread (mirroring _start internals).
    t = threading.Thread(target=svc._listen_to_channels, daemon=True)
    t.start()

    qtbot.waitUntil(lambda: mock_connectivity.stop.called, timeout=1000)
    mock_connectivity.stop.assert_called_once()
