"""Unit tests for services.settings — SettingsService tool-enabled sync."""

import json
from unittest.mock import MagicMock

from pytestqt.qtbot import QtBot

from services.settings import SettingsService

_CH_ANDROID_TO_PC = "settings_tools_android_to_pc"
_CH_PC_TO_ANDROID = "settings_tools_pc_to_android"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stream_cm(read_data: bytes = b"") -> MagicMock:
    """Return a context-manager mock whose stream yields *read_data* on read_all()."""
    stream = MagicMock()
    stream.read_all.return_value = read_data
    cm = MagicMock()
    cm.__enter__.return_value = stream
    cm.__exit__.return_value = False
    return cm


def _make_connectivity(tau: MagicMock, connected: bool = True) -> MagicMock:
    connectivity = MagicMock()
    connectivity.tau = tau
    connectivity.connected = connected
    return connectivity


def _make_tau() -> MagicMock:
    tau = MagicMock()
    tau.connect.return_value = _make_stream_cm()
    return tau


def _make_svc(tau: MagicMock, connected: bool = True) -> SettingsService:
    return SettingsService(
        repository=MagicMock(),
        connectivity=_make_connectivity(tau, connected),
    )


def _wait_threads(svc: SettingsService, qtbot: QtBot) -> None:
    """Block until all background threads spawned by *svc* have finished."""
    def _all_done() -> bool:
        with svc._threads_lock:
            return all(not t.is_alive() for t in svc._threads)

    qtbot.waitUntil(_all_done, timeout=2000)


# ---------------------------------------------------------------------------
# receive_tools_state() — Android → PC: virtualDrive
# ---------------------------------------------------------------------------


def test_receive_emits_true_for_enabled_payload(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(json.dumps({"virtualDrive": True}).encode())

    svc = _make_svc(tau)
    received: list[bool] = []
    svc.tools_state_received.connect(lambda v: received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert received == [True]


def test_receive_emits_false_for_disabled_payload(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(json.dumps({"virtualDrive": False}).encode())

    svc = _make_svc(tau)
    received: list[bool] = []
    svc.tools_state_received.connect(lambda v: received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert received == [False]


def test_receive_opens_correct_channel(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(json.dumps({"virtualDrive": True}).encode())

    svc = _make_svc(tau)
    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    tau.connect.assert_called_once_with(_CH_ANDROID_TO_PC)


def test_receive_ignores_payload_without_key(qtbot: QtBot) -> None:
    """An absent key is a forward-compatible no-op — no signal is emitted."""
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(json.dumps({}).encode())

    svc = _make_svc(tau)
    received: list[bool] = []
    svc.tools_state_received.connect(lambda v: received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert received == []


def test_receive_survives_broken_channel(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.side_effect = RuntimeError("channel closed")

    svc = _make_svc(tau)
    received: list[bool] = []
    svc.tools_state_received.connect(lambda v: received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert received == []


# ---------------------------------------------------------------------------
# receive_tools_state() — Android → PC: clipboard + webcam signals
# ---------------------------------------------------------------------------


def test_receive_emits_clipboard_signal(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(
        json.dumps({"clipboard": False}).encode()
    )

    svc = _make_svc(tau)
    received: list[bool] = []
    svc.clipboard_state_received.connect(lambda v: received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert received == [False]


def test_receive_emits_backup_signal(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(
        json.dumps({"backup": False}).encode()
    )

    svc = _make_svc(tau)
    received: list[bool] = []
    svc.backup_state_received.connect(lambda v: received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert received == [False]


def test_receive_emits_webcam_signal(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(
        json.dumps({"webcam": True}).encode()
    )

    svc = _make_svc(tau)
    received: list[bool] = []
    svc.webcam_state_received.connect(lambda v: received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert received == [True]


def test_receive_emits_all_signals(qtbot: QtBot) -> None:
    """A full payload from a new phone build triggers all four signals."""
    tau = _make_tau()
    tau.connect.return_value = _make_stream_cm(
        json.dumps({"virtualDrive": True, "clipboard": False, "webcam": True, "backup": False}).encode()
    )

    svc = _make_svc(tau)
    vd_received: list[bool] = []
    cb_received: list[bool] = []
    wc_received: list[bool] = []
    bk_received: list[bool] = []
    svc.tools_state_received.connect(lambda v: vd_received.append(v))
    svc.clipboard_state_received.connect(lambda v: cb_received.append(v))
    svc.webcam_state_received.connect(lambda v: wc_received.append(v))
    svc.backup_state_received.connect(lambda v: bk_received.append(v))

    svc.receive_tools_state()
    _wait_threads(svc, qtbot)

    assert vd_received == [True]
    assert cb_received == [False]
    assert wc_received == [True]
    assert bk_received == [False]


# ---------------------------------------------------------------------------
# push_tools_state() — PC → Android
# ---------------------------------------------------------------------------


def test_push_writes_payload_to_correct_channel(qtbot: QtBot) -> None:
    tau = _make_tau()
    stream = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = stream
    cm.__exit__.return_value = False
    tau.connect.return_value = cm

    svc = _make_svc(tau, connected=True)
    svc.push_tools_state(True, False, True, False)
    _wait_threads(svc, qtbot)

    tau.connect.assert_called_once_with(_CH_PC_TO_ANDROID)
    written = stream.write_string.call_args[0][0]
    assert json.loads(written) == {
        "virtualDrive": True, "clipboard": False, "webcam": True, "backup": False
    }


def test_push_is_noop_when_disconnected() -> None:
    tau = _make_tau()
    svc = _make_svc(tau, connected=False)

    svc.push_tools_state(True, True, True, True)

    tau.connect.assert_not_called()


def test_push_survives_broken_channel(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.side_effect = RuntimeError("disconnected")

    svc = _make_svc(tau, connected=True)
    svc.push_tools_state(False, True, True, True)
    _wait_threads(svc, qtbot)
    # Should not raise; the exception is caught inside _push_tools_state.
