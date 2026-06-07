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
    """Construct PhoneRequestService with connectivity and file-transfer mocked.

    Returns:
        Tuple of ``(service, mock_connectivity, mock_file_transfer)``.
    """
    mock_connectivity = MagicMock()
    mock_connectivity.connected = True
    mock_file_transfer = MagicMock()

    svc = PhoneRequestService(
        connectivity_service=mock_connectivity,
        file_transfer_service=mock_file_transfer,
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


def test_operations_contains_disconnect_from_phone() -> None:
    """DISCONNECT_FROM_PHONE is registered in operations pointing to disconnect_device."""
    svc, mock_connectivity, _ = _make_service()
    key = SessionChannels.DISCONNECT_FROM_PHONE.value
    assert key in svc.operations
    assert svc.operations[key] == mock_connectivity.disconnect
