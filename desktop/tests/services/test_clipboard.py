"""Unit tests for services.clipboard — ClipboardService public interface."""

import json
import threading
from unittest.mock import MagicMock

from pytestqt.qtbot import QtBot

from services.clipboard import ClipboardService

_CH_ANDROID_TO_PC = "clipboard_android_to_pc"
_CH_PC_TO_ANDROID = "clipboard_pc_to_android"


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


def _make_svc(tau: MagicMock) -> ClipboardService:
    return ClipboardService(connectivity=_make_connectivity(tau))


def _wait_threads(svc: ClipboardService, qtbot: QtBot) -> None:
    """Block until all background threads finish, then flush queued signals.

    A worker emits its Qt signal and *then* exits; that cross-thread emit is
    delivered via a queued event on the main-thread loop. ``waitUntil`` returns
    as soon as ``is_alive()`` is False — which can happen before the queued slot
    runs — so flush the event loop once the threads are gone. By then the emit
    has already posted its event, so a single pass delivers it.
    """
    def _all_done() -> bool:
        with svc._threads_lock:
            return all(not t.is_alive() for t in svc._threads)

    qtbot.waitUntil(_all_done, timeout=2000)
    qtbot.wait(1)


# ---------------------------------------------------------------------------
# receive() — Android → PC
# ---------------------------------------------------------------------------


def test_receive_emits_signal_for_text_payload(qtbot: QtBot) -> None:
    tau = _make_tau()
    payload = json.dumps({"type": "text", "content": "hello"}).encode()
    tau.connect.return_value = _make_stream_cm(payload)

    svc = _make_svc(tau)
    received: list[str] = []
    svc.clipboard_text_received.connect(lambda t: received.append(t))

    svc.receive()
    _wait_threads(svc, qtbot)

    assert received == ["hello"]


def test_receive_opens_correct_channel(qtbot: QtBot) -> None:
    tau = _make_tau()
    payload = json.dumps({"type": "text", "content": "x"}).encode()
    tau.connect.return_value = _make_stream_cm(payload)

    svc = _make_svc(tau)
    svc.receive()
    _wait_threads(svc, qtbot)

    tau.connect.assert_called_once_with(_CH_ANDROID_TO_PC)


def test_receive_does_not_emit_for_unknown_type(qtbot: QtBot) -> None:
    tau = _make_tau()
    payload = json.dumps({"type": "image", "content": "data:..."}).encode()
    tau.connect.return_value = _make_stream_cm(payload)

    svc = _make_svc(tau)
    received: list[str] = []
    svc.clipboard_text_received.connect(lambda t: received.append(t))

    svc.receive()
    _wait_threads(svc, qtbot)

    assert received == []


def test_receive_survives_broken_channel(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.side_effect = RuntimeError("channel closed")

    svc = _make_svc(tau)
    received: list[str] = []
    svc.clipboard_text_received.connect(lambda t: received.append(t))

    svc.receive()
    _wait_threads(svc, qtbot)

    assert received == []


# ---------------------------------------------------------------------------
# Anti-loop guard: receive() pre-sets hash so echo is skipped
# ---------------------------------------------------------------------------


def test_receive_skips_duplicate_content(qtbot: QtBot) -> None:
    """A second receive() with the same text must not emit the signal again."""
    tau = _make_tau()
    text = "clipboard content"
    payload = json.dumps({"type": "text", "content": text}).encode()
    tau.connect.return_value = _make_stream_cm(payload)

    svc = _make_svc(tau)
    received: list[str] = []
    svc.clipboard_text_received.connect(lambda t: received.append(t))

    svc.receive()
    _wait_threads(svc, qtbot)
    svc.receive()
    _wait_threads(svc, qtbot)

    assert received == [text]  # emitted only once


def test_receive_sets_hash_so_echo_send_is_skipped(qtbot: QtBot) -> None:
    """After receive(), on_clipboard_changed with the same text must not send to Android."""
    tau = _make_tau()
    text = "clipboard content"
    payload = json.dumps({"type": "text", "content": text}).encode()
    tau.connect.return_value = _make_stream_cm(payload)

    svc = _make_svc(tau)
    svc.receive()
    _wait_threads(svc, qtbot)

    tau.reset_mock()

    svc.on_clipboard_changed(text)
    _wait_threads(svc, qtbot)

    tau.connect.assert_not_called()


# ---------------------------------------------------------------------------
# on_clipboard_changed() — PC → Android
# ---------------------------------------------------------------------------


def test_on_clipboard_changed_sends_json_to_android(qtbot: QtBot) -> None:
    tau = _make_tau()
    stream = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = stream
    cm.__exit__.return_value = False
    tau.connect.return_value = cm

    svc = _make_svc(tau)
    svc.on_clipboard_changed("hello android")
    _wait_threads(svc, qtbot)

    tau.connect.assert_called_once_with(_CH_PC_TO_ANDROID)
    written = stream.write_string.call_args[0][0]
    payload = json.loads(written)
    assert payload == {"type": "text", "content": "hello android"}


def test_on_clipboard_changed_skips_empty_text(qtbot: QtBot) -> None:
    tau = _make_tau()
    svc = _make_svc(tau)

    svc.on_clipboard_changed("")
    _wait_threads(svc, qtbot)

    tau.connect.assert_not_called()


def test_on_clipboard_changed_skips_when_disconnected(qtbot: QtBot) -> None:
    """No device connected — the PC→Android send must not open a channel."""
    tau = _make_tau()
    svc = ClipboardService(connectivity=_make_connectivity(tau, connected=False))

    svc.on_clipboard_changed("hi")
    _wait_threads(svc, qtbot)

    tau.connect.assert_not_called()


def test_on_clipboard_changed_deduplicates_identical_content(qtbot: QtBot) -> None:
    tau = _make_tau()
    svc = _make_svc(tau)

    svc.on_clipboard_changed("same text")
    _wait_threads(svc, qtbot)
    tau.reset_mock()

    svc.on_clipboard_changed("same text")
    _wait_threads(svc, qtbot)

    tau.connect.assert_not_called()


def test_on_clipboard_changed_sends_different_content(qtbot: QtBot) -> None:
    tau = _make_tau()
    svc = _make_svc(tau)

    svc.on_clipboard_changed("first")
    _wait_threads(svc, qtbot)
    tau.reset_mock()

    svc.on_clipboard_changed("second")
    _wait_threads(svc, qtbot)

    tau.connect.assert_called_once()


def test_on_clipboard_changed_survives_broken_channel(qtbot: QtBot) -> None:
    tau = _make_tau()
    tau.connect.side_effect = RuntimeError("disconnected")

    svc = _make_svc(tau)
    svc.on_clipboard_changed("text that will fail to send")
    _wait_threads(svc, qtbot)
    # Should not raise; the exception is caught inside _send_to_android


# ---------------------------------------------------------------------------
# set_enabled() — feature toggle gates both directions
# ---------------------------------------------------------------------------


def test_on_clipboard_changed_skips_when_disabled(qtbot: QtBot) -> None:
    """Disabled clipboard sync must not push PC clipboard changes to Android."""
    tau = _make_tau()
    svc = _make_svc(tau)
    svc.set_enabled(False)

    svc.on_clipboard_changed("hi")
    _wait_threads(svc, qtbot)

    tau.connect.assert_not_called()


def test_receive_skips_when_disabled(qtbot: QtBot) -> None:
    """Disabled clipboard sync must not open the Android→PC channel."""
    tau = _make_tau()
    payload = json.dumps({"type": "text", "content": "x"}).encode()
    tau.connect.return_value = _make_stream_cm(payload)
    svc = _make_svc(tau)
    svc.set_enabled(False)

    received: list[str] = []
    svc.clipboard_text_received.connect(lambda t: received.append(t))

    svc.receive()
    _wait_threads(svc, qtbot)

    tau.connect.assert_not_called()
    assert received == []


def test_re_enabling_restores_sync(qtbot: QtBot) -> None:
    """Toggling back on resumes PC→Android sends."""
    tau = _make_tau()
    svc = _make_svc(tau)
    svc.set_enabled(False)
    svc.set_enabled(True)

    svc.on_clipboard_changed("back on")
    _wait_threads(svc, qtbot)

    tau.connect.assert_called_once_with(_CH_PC_TO_ANDROID)


# ---------------------------------------------------------------------------
# Lifecycle (shutdown participation)
# ---------------------------------------------------------------------------


def test_is_active_false_when_idle(qtbot: QtBot) -> None:
    """No background threads running → is_active is False; start/stop are no-ops."""
    svc = _make_svc(_make_tau())
    svc.start()  # no-op
    svc.stop()   # no-op
    assert svc.is_active is False
