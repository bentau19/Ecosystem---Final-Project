"""Unit tests for services.connectivity — ConnectivityService public interface."""

import threading
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from services.connectivity import ConnectivityService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_connectivity(mock_tau: MagicMock) -> ConnectivityService:
    """Construct ConnectivityService with TauSync replaced by a mock.

    Mirrors what start() does: sets is_running then spawns _listen() on a
    background thread.  is_running must be set before disconnect_device() or
    connect_to_device() will pass their is_running guard and execute.
    """
    with patch("services.connectivity.TauSync", return_value=mock_tau):
        svc = ConnectivityService()
    svc._is_running.set()
    threading.Thread(target=svc._listen, daemon=True).start()
    return svc


def _gated_tau(gate: threading.Event) -> MagicMock:
    """Return a mock TauSync whose listen() blocks until gate is set.

    After the gate is released, is_connected is set to True so that the
    _listen while-loop exits after emitting device_connected exactly once.
    """
    mock_tau = MagicMock()
    mock_tau.is_connected = False

    def _listen_side_effect(**kwargs: object) -> None:
        gate.wait()
        mock_tau.is_connected = True   # causes the while-guard to become False

    mock_tau.listen.side_effect = _listen_side_effect
    return mock_tau


def _raising_tau(gate: threading.Event, exc: Exception) -> MagicMock:
    """Return a mock TauSync whose listen() blocks then raises exc exactly once.

    Subsequent calls block on an internal event that is never set, keeping
    the _listen thread alive but preventing connection_error from firing more
    than once.
    """
    mock_tau = MagicMock()
    mock_tau.is_connected = False
    _raised = threading.Event()
    _block = threading.Event()   # never set

    def _raise_after_gate(**kwargs: object) -> None:
        if not _raised.is_set():
            gate.wait()
            _raised.set()
            raise exc
        _block.wait()   # park subsequent calls so the signal fires only once

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

    qtbot.waitUntil(lambda: len(error_received) > 0, timeout=1000)
    assert connected_received == []


# ---------------------------------------------------------------------------
# disconnect_device
# ---------------------------------------------------------------------------


def test_stop_emits_device_disconnected(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _make_connectivity(_gated_tau(gate))
    connected_received: list[bool] = []
    svc.device_connected.connect(lambda: connected_received.append(True))
    gate.set()
    qtbot.waitUntil(lambda: len(connected_received) > 0, timeout=1000)

    received: list[bool] = []
    svc.device_disconnected.connect(lambda: received.append(True))
    svc.stop()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received == [True]


def test_stop_calls_tau_dispose(qtbot: QtBot) -> None:
    gate = threading.Event()
    mock_tau = _gated_tau(gate)
    svc = _make_connectivity(mock_tau)
    connected_received: list[bool] = []
    svc.device_connected.connect(lambda: connected_received.append(True))
    gate.set()
    qtbot.waitUntil(lambda: len(connected_received) > 0, timeout=1000)

    disposed: list[bool] = []
    mock_tau.dispose.side_effect = lambda: disposed.append(True)
    svc.stop()
    qtbot.waitUntil(lambda: len(disposed) > 0, timeout=1000)

    mock_tau.dispose.assert_called_once()


def test_stop_dispose_called_before_signal(qtbot: QtBot) -> None:
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
    svc.stop()
    qtbot.waitUntil(lambda: len(call_order) >= 2, timeout=1000)

    assert call_order == ["dispose", "signal"]


# ---------------------------------------------------------------------------
# connect_to_device
# ---------------------------------------------------------------------------


def test_connect_to_device_emits_device_connected(qtbot: QtBot) -> None:
    mock_tau = MagicMock()
    with patch("services.connectivity.TauSync", return_value=mock_tau):
        svc = ConnectivityService()
    # connect_to_device() guards on is_running; set it to allow execution.
    svc._is_running.set()

    received: list[bool] = []
    svc.device_connected.connect(lambda: received.append(True))


    svc.connect_to_device("192.168.1.1")

    qtbot.waitUntil(lambda: len(received) > 0, timeout=1000)
    assert received == [True]
