"""Unit tests for services.connectivity — DeviceConnectivity public interface."""

import threading
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from services.connectivity import ConnectivityService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    """Reset the ConnectivityService singleton before and after every test.

    Without this, the first test's instance (and its mock TauSync) leaks
    into every subsequent test — __init__ is guarded by _initialized so
    new mocks would never be injected.
    """
    ConnectivityService._instance = None
    ConnectivityService._initialized = False
    yield
    ConnectivityService._instance = None
    ConnectivityService._initialized = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_connectivity(mock_tau: MagicMock) -> ConnectivityService:
    """Construct DeviceConnectivity with TauSync replaced by a mock."""
    with patch("services.connectivity.TauSync", return_value=mock_tau):
        return ConnectivityService()


def _gated_tau(gate: threading.Event) -> MagicMock:
    """Return a mock TauSync whose listen() blocks until gate is set."""
    mock_tau = MagicMock()
    mock_tau.listen.side_effect = lambda: gate.wait()
    return mock_tau


def _raising_tau(gate: threading.Event, exc: Exception) -> MagicMock:
    """Return a mock TauSync whose listen() blocks then raises exc."""
    mock_tau = MagicMock()

    def _raise_after_gate() -> None:
        gate.wait()
        raise exc

    mock_tau.listen.side_effect = _raise_after_gate
    return mock_tau


# ---------------------------------------------------------------------------
# device_connected signal
# ---------------------------------------------------------------------------


def test_device_connected_emitted_when_listen_succeeds(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _make_connectivity(_gated_tau(gate))
    received: list[bool] = []
    svc.device_connected.connect(lambda: received.append(True))

    gate.set()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received == [True]


def test_connection_error_not_emitted_when_listen_succeeds(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _make_connectivity(_gated_tau(gate))
    error_received: list[str] = []
    connected_received: list[bool] = []
    svc.connection_error.connect(lambda msg: error_received.append(msg))
    svc.device_connected.connect(lambda: connected_received.append(True))

    gate.set()

    # Wait for the success signal to confirm the thread finished, then assert no error
    qtbot.waitUntil(lambda: len(connected_received) > 0, timeout=1000)
    assert error_received == []


# ---------------------------------------------------------------------------
# connection_error signal
# ---------------------------------------------------------------------------


def test_connection_error_emitted_when_listen_raises(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _make_connectivity(_raising_tau(gate, RuntimeError("connection refused")))
    received: list[str] = []
    svc.connection_error.connect(lambda msg: received.append(msg))

    gate.set()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert len(received) == 1


def test_connection_error_message_matches_exception(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _make_connectivity(_raising_tau(gate, Exception("timeout after 30s")))
    received: list[str] = []
    svc.connection_error.connect(lambda msg: received.append(msg))

    gate.set()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received == ["timeout after 30s"]


def test_device_connected_not_emitted_when_listen_raises(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _make_connectivity(_raising_tau(gate, OSError("host unreachable")))
    connected_received: list[bool] = []
    error_received: list[str] = []
    svc.device_connected.connect(lambda: connected_received.append(True))
    svc.connection_error.connect(lambda msg: error_received.append(msg))

    gate.set()

    # Wait for the error signal to confirm the thread finished, then assert no connected
    qtbot.waitUntil(lambda: len(error_received) > 0, timeout=1000)
    assert connected_received == []


# ---------------------------------------------------------------------------
# disconnect_device
# ---------------------------------------------------------------------------


def test_disconnect_device_emits_device_disconnected(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _make_connectivity(_gated_tau(gate))
    connected_received: list[bool] = []
    svc.device_connected.connect(lambda: connected_received.append(True))
    gate.set()
    qtbot.waitUntil(lambda: len(connected_received) > 0, timeout=1000)

    received: list[bool] = []
    svc.device_disconnected.connect(lambda: received.append(True))
    svc.disconnect_device()

    assert received == [True]


def test_disconnect_device_calls_tau_dispose(qtbot: QtBot) -> None:
    gate = threading.Event()
    mock_tau = _gated_tau(gate)
    svc = _make_connectivity(mock_tau)
    connected_received: list[bool] = []
    svc.device_connected.connect(lambda: connected_received.append(True))
    gate.set()
    qtbot.waitUntil(lambda: len(connected_received) > 0, timeout=1000)

    svc.disconnect_device()

    mock_tau.dispose.assert_called_once()


def test_disconnect_device_dispose_called_before_signal(qtbot: QtBot) -> None:
    gate = threading.Event()
    mock_tau = _gated_tau(gate)
    svc = _make_connectivity(mock_tau)
    connected_received: list[bool] = []
    svc.device_connected.connect(lambda: connected_received.append(True))
    gate.set()
    qtbot.waitUntil(lambda: len(connected_received) > 0, timeout=1000)

    call_order: list[str] = []
    mock_tau.dispose.side_effect = lambda: call_order.append("dispose")
    svc.device_disconnected.connect(lambda: call_order.append("signal"))
    svc.disconnect_device()

    assert call_order == ["dispose", "signal"]
