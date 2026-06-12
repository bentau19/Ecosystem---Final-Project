"""Unit tests for services.connectivity — ConnectivityService lifecycle.

Covers the strictly-ordered disconnect sequence introduced to fix the
stop/restart race:

    device_disconnecting → transport teardown → executor drain → device_disconnected

and the listen-side guarantees (no spurious connection_error during a
deliberate stop, fresh TauSync on restart).
"""

import threading
from unittest.mock import MagicMock, patch

from pytestqt.qtbot import QtBot

from services.connectivity import ConnectivityService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tau() -> MagicMock:
    """Return a baseline TauSync mock that behaves like a quiet transport."""
    mock_tau = MagicMock()
    mock_tau.is_connected = False
    mock_tau.get_peer_waiting_words.return_value = []
    return mock_tau


def _gated_tau(gate: threading.Event) -> MagicMock:
    """Return a mock TauSync whose listen() blocks until *gate* is set.

    After the gate is released, is_connected flips to True so the _listen
    while-loop exits after emitting device_connected exactly once.
    """
    mock_tau = _make_tau()

    def _listen_side_effect(**kwargs: object) -> None:
        gate.wait(timeout=5)
        mock_tau.is_connected = True  # while-guard becomes False → loop exits

    mock_tau.listen.side_effect = _listen_side_effect
    return mock_tau


def _start_service(mock_tau: MagicMock) -> ConnectivityService:
    """Construct and synchronously start a service bound to *mock_tau*.

    _start() is called inside the patch context because it constructs a fresh
    TauSync at runtime (reconnects always get a new transport).
    """
    with patch("services.connectivity.TauSync", return_value=mock_tau):
        svc = ConnectivityService()
        svc._start()
    return svc


def _wait_connected(qtbot: QtBot, svc: ConnectivityService, gate: threading.Event) -> None:
    """Release the listen gate and block until device_connected fires."""
    connected: list[bool] = []
    svc.device_connected.connect(lambda: connected.append(True))
    gate.set()
    qtbot.waitUntil(lambda: len(connected) > 0, timeout=2000)


# ---------------------------------------------------------------------------
# device_connected / connection_error
# ---------------------------------------------------------------------------


def test_device_connected_emitted_when_listen_succeeds(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _start_service(_gated_tau(gate))
    received: list[bool] = []
    svc.device_connected.connect(lambda: received.append(True))

    gate.set()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    assert received == [True]


def test_connection_error_emitted_when_listen_raises_while_running(qtbot: QtBot) -> None:
    mock_tau = _make_tau()
    raised = threading.Event()
    park = threading.Event()  # never set — parks retries after the first raise

    def _raise_once(**kwargs: object) -> None:
        if not raised.is_set():
            raised.set()
            raise RuntimeError("connection refused")
        park.wait(timeout=5)

    mock_tau.listen.side_effect = _raise_once
    svc = _start_service(mock_tau)
    received: list[str] = []
    svc.connection_error.connect(lambda msg: received.append(msg))

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    assert received == ["connection refused"]


def test_no_connection_error_when_listen_aborted_by_stop(qtbot: QtBot) -> None:
    """A deliberate stop() aborts the blocking listen() — that is not an error.

    tau.disconnect() makes the in-flight listen() raise (as the real .NET
    layer does).  Because _is_running is already cleared, _listen must exit
    silently instead of emitting connection_error.
    """
    mock_tau = _make_tau()
    abort = threading.Event()

    def _blocking_listen(**kwargs: object) -> None:
        abort.wait(timeout=5)
        raise RuntimeError("listen aborted by disconnect")

    mock_tau.listen.side_effect = _blocking_listen
    mock_tau.disconnect.side_effect = lambda: abort.set()

    svc = _start_service(mock_tau)
    qtbot.waitUntil(lambda: mock_tau.listen.called, timeout=2000)

    errors: list[str] = []
    disconnected: list[bool] = []
    svc.connection_error.connect(lambda msg: errors.append(msg))
    svc.device_disconnected.connect(lambda: disconnected.append(True))

    svc.stop()

    qtbot.waitUntil(lambda: len(disconnected) > 0, timeout=2000)
    assert errors == []


# ---------------------------------------------------------------------------
# stop() — ordered teardown
# ---------------------------------------------------------------------------


def test_stop_emits_disconnecting_then_disconnected(qtbot: QtBot) -> None:
    gate = threading.Event()
    svc = _start_service(_gated_tau(gate))
    _wait_connected(qtbot, svc, gate)

    order: list[str] = []
    svc.device_disconnecting.connect(lambda: order.append("disconnecting"))
    svc.device_disconnected.connect(lambda: order.append("disconnected"))

    svc.stop()

    qtbot.waitUntil(lambda: len(order) >= 2, timeout=2000)
    assert order == ["disconnecting", "disconnected"]


def test_stop_calls_tau_disconnect_before_disconnected_signal(qtbot: QtBot) -> None:
    gate = threading.Event()
    mock_tau = _gated_tau(gate)
    svc = _start_service(mock_tau)
    _wait_connected(qtbot, svc, gate)

    call_order: list[str] = []
    mock_tau.disconnect.side_effect = lambda: call_order.append("disconnect")
    svc.device_disconnected.connect(lambda: call_order.append("signal"))

    svc.stop()

    qtbot.waitUntil(lambda: len(call_order) >= 2, timeout=2000)
    assert call_order == ["disconnect", "signal"]


def test_stop_emits_disconnected_when_tau_already_disconnected(qtbot: QtBot) -> None:
    """device_disconnected fires even when is_connected is already False.

    When Android crashes the .NET layer flips is_connected to False before
    teardown runs; the lifecycle signals must still fire so the UI returns
    to the login screen.
    """
    mock_tau = _make_tau()  # is_connected stays False
    park = threading.Event()

    def _parked_listen(**kwargs: object) -> None:
        # Mirrors the real transport: blocks, then raises TimeoutError so the
        # _listen loop re-checks its running flag.  disconnect() releases the
        # park immediately so stop() never waits out the full poll window.
        park.wait(timeout=5)
        raise TimeoutError()

    mock_tau.listen.side_effect = _parked_listen
    mock_tau.disconnect.side_effect = lambda: park.set()
    svc = _start_service(mock_tau)

    received: list[bool] = []
    svc.device_disconnected.connect(lambda: received.append(True))

    svc.stop()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=10000)
    assert received == [True]


def test_stop_emits_disconnected_when_get_peer_waiting_words_raises(qtbot: QtBot) -> None:
    """device_disconnected fires even when the peer socket is already dead."""
    gate = threading.Event()
    mock_tau = _gated_tau(gate)
    mock_tau.get_peer_waiting_words.side_effect = RuntimeError(
        "transport is not connected"
    )
    svc = _start_service(mock_tau)
    _wait_connected(qtbot, svc, gate)

    received: list[bool] = []
    svc.device_disconnected.connect(lambda: received.append(True))

    svc.stop()

    qtbot.waitUntil(lambda: len(received) > 0, timeout=2000)
    assert received == [True]


def test_stop_is_idempotent_when_not_running(qtbot: QtBot) -> None:
    """stop() on a never-started service emits nothing and does not crash."""
    with patch("services.connectivity.TauSync", return_value=_make_tau()):
        svc = ConnectivityService()

    received: list[bool] = []
    svc.device_disconnected.connect(lambda: received.append(True))

    svc._stop()  # synchronous — returns immediately via the running guard

    assert received == []


# ---------------------------------------------------------------------------
# stop() → start() — reconnect cycle
# ---------------------------------------------------------------------------


def test_stop_then_start_listens_again_with_fresh_tausync(qtbot: QtBot) -> None:
    """After a completed stop(), start() must re-listen on a brand-new TauSync.

    Guards against the executor-swap race where the old stop() shut down the
    fresh executor created by the restart, leaving the app deaf forever.
    """
    created: list[MagicMock] = []
    abort = threading.Event()

    def _factory() -> MagicMock:
        mock_tau = _make_tau()
        if not created:
            # First (session) transport: listen blocks until disconnect aborts it.
            def _blocking_listen(**kwargs: object) -> None:
                abort.wait(timeout=5)
                raise RuntimeError("listen aborted by disconnect")

            mock_tau.listen.side_effect = _blocking_listen
            mock_tau.disconnect.side_effect = lambda: abort.set()
        else:
            # Restarted transport: listen parks until disconnect() releases it.
            park = threading.Event()
            mock_tau.listen.side_effect = lambda **kwargs: park.wait(timeout=5)
            mock_tau.disconnect.side_effect = lambda: park.set()
        created.append(mock_tau)
        return mock_tau

    with patch("services.connectivity.TauSync", side_effect=_factory):
        svc = ConnectivityService()  # consumes created[0] (constructor default)
        svc._start()  # consumes created[1] — the first session transport

        qtbot.waitUntil(lambda: created[1].listen.called, timeout=2000)

        disconnected: list[bool] = []
        # Mirror production wiring: restart is triggered by device_disconnected,
        # which ConnectivityService only emits after its executor is drained.
        svc.device_disconnected.connect(lambda: disconnected.append(True))
        svc.device_disconnected.connect(svc.start)

        svc.stop()

        qtbot.waitUntil(lambda: len(disconnected) > 0, timeout=2000)
        # The restart must produce a fresh transport that is actively listening.
        qtbot.waitUntil(lambda: len(created) >= 3, timeout=2000)
        qtbot.waitUntil(lambda: created[2].listen.called, timeout=2000)

    assert created[2] is not created[1]
    assert svc._is_running.is_set()
    assert svc.tau is created[2]
