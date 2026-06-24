"""Unit tests for services.webcam — WebcamService public interface."""

import io
import struct
import threading
from unittest.mock import MagicMock, patch

from PIL import Image
from pytestqt.qtbot import QtBot

from services.webcam import WebcamService

_CH_WEBCAM_START = "webcam_start"
_CH_WEBCAM_FRAMES = "webcam_frames"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg() -> bytes:
    """Return a minimal 4×4 RGB JPEG for frame tests."""
    img = Image.new("RGB", (4, 4), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_stream_cm(read_all_data: bytes = b"") -> MagicMock:
    """Return a context-manager mock for a TauSync stream."""
    stream = MagicMock()
    stream.read_all.return_value = read_all_data
    cm = MagicMock()
    cm.__enter__.return_value = stream
    cm.__exit__.return_value = False
    return cm, stream


def _make_frame_stream_cm(header_bytes: bytes, jpeg_bytes: bytes) -> MagicMock:
    """Return a frame-channel context-manager that yields one frame then EOF."""
    stream = MagicMock()
    stream.read_exactly.side_effect = [header_bytes, jpeg_bytes, None]
    cm = MagicMock()
    cm.__enter__.return_value = stream
    cm.__exit__.return_value = False
    return cm, stream


def _make_tau(start_cm: MagicMock, frames_cm: MagicMock) -> MagicMock:
    """Return a tau mock that dispatches connect() by channel name."""
    tau = MagicMock()

    def _connect(channel: str) -> MagicMock:
        return start_cm if channel == _CH_WEBCAM_START else frames_cm

    tau.connect.side_effect = _connect
    return tau


def _make_connectivity(tau: MagicMock) -> MagicMock:
    connectivity = MagicMock()
    connectivity.tau = tau
    return connectivity


def _make_cam_cm() -> tuple[MagicMock, MagicMock]:
    """Return (context-manager, cam mock) for pyvirtualcam.Camera."""
    cam = MagicMock()
    cam_cm = MagicMock()
    cam_cm.__enter__.return_value = cam
    cam_cm.__exit__.return_value = False
    return cam_cm, cam


def _make_svc(tau: MagicMock) -> WebcamService:
    return WebcamService(connectivity=_make_connectivity(tau))


# ---------------------------------------------------------------------------
# receive_start() — lifecycle
# ---------------------------------------------------------------------------


def test_webcam_started_emitted_after_handshake(qtbot: QtBot) -> None:
    jpeg = _make_jpeg()
    header = struct.pack(">I", len(jpeg))
    start_cm, _ = _make_stream_cm()
    frames_cm, _ = _make_frame_stream_cm(header, jpeg)
    tau = _make_tau(start_cm, frames_cm)

    cam_cm, _ = _make_cam_cm()
    svc = _make_svc(tau)
    received: list[bool] = []
    svc.webcam_started.connect(lambda: received.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(received) > 0, timeout=3000)

    assert received == [True]


def test_webcam_stopped_emitted_when_stream_ends(qtbot: QtBot) -> None:
    jpeg = _make_jpeg()
    header = struct.pack(">I", len(jpeg))
    start_cm, _ = _make_stream_cm()
    frames_cm, _ = _make_frame_stream_cm(header, jpeg)
    tau = _make_tau(start_cm, frames_cm)

    cam_cm, _ = _make_cam_cm()
    svc = _make_svc(tau)
    stopped: list[bool] = []
    svc.webcam_stopped.connect(lambda: stopped.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    assert stopped == [True]


def test_running_flag_reset_after_stream_ends(qtbot: QtBot) -> None:
    jpeg = _make_jpeg()
    header = struct.pack(">I", len(jpeg))
    start_cm, _ = _make_stream_cm()
    frames_cm, _ = _make_frame_stream_cm(header, jpeg)
    tau = _make_tau(start_cm, frames_cm)

    cam_cm, _ = _make_cam_cm()
    svc = _make_svc(tau)
    stopped: list[bool] = []
    svc.webcam_stopped.connect(lambda: stopped.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    assert not svc._running


def test_receive_start_is_idempotent_while_running(qtbot: QtBot) -> None:
    """A second receive_start() while streaming must be silently ignored."""
    started: list[bool] = []
    gate = threading.Event()

    start_cm, _ = _make_stream_cm()

    # Frame stream blocks until gate is released so _running stays True
    blocked_stream = MagicMock()
    blocked_stream.read_exactly.side_effect = lambda n: (gate.wait(timeout=3), None)[1]
    blocked_cm = MagicMock()
    blocked_cm.__enter__.return_value = blocked_stream
    blocked_cm.__exit__.return_value = False

    tau = _make_tau(start_cm, blocked_cm)
    cam_cm, _ = _make_cam_cm()
    svc = _make_svc(tau)
    svc.webcam_started.connect(lambda: started.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(started) > 0, timeout=3000)

        # Second call — must be a no-op
        svc.receive_start()
        gate.set()

    # Camera should have been opened exactly once
    assert len(started) == 1


# ---------------------------------------------------------------------------
# webcam_error — exception handling
# ---------------------------------------------------------------------------


def test_webcam_error_emitted_when_start_channel_raises(qtbot: QtBot) -> None:
    tau = MagicMock()
    tau.connect.side_effect = RuntimeError("connection refused")

    svc = _make_svc(tau)
    errors: list[str] = []
    svc.webcam_error.connect(lambda msg: errors.append(msg))

    with patch("services.webcam.pyvirtualcam.Camera"):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(errors) > 0, timeout=3000)

    assert "connection refused" in errors[0]


def test_webcam_stopped_still_emitted_on_error(qtbot: QtBot) -> None:
    tau = MagicMock()
    tau.connect.side_effect = RuntimeError("lost connection")

    svc = _make_svc(tau)
    stopped: list[bool] = []
    svc.webcam_stopped.connect(lambda: stopped.append(True))

    with patch("services.webcam.pyvirtualcam.Camera"):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    assert stopped == [True]


# ---------------------------------------------------------------------------
# Frame delivery
# ---------------------------------------------------------------------------


def test_frame_sent_to_virtual_cam(qtbot: QtBot) -> None:
    jpeg = _make_jpeg()
    header = struct.pack(">I", len(jpeg))
    start_cm, _ = _make_stream_cm()
    frames_cm, _ = _make_frame_stream_cm(header, jpeg)
    tau = _make_tau(start_cm, frames_cm)

    cam_cm, cam = _make_cam_cm()
    svc = _make_svc(tau)
    stopped: list[bool] = []
    svc.webcam_stopped.connect(lambda: stopped.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    cam.send.assert_called_once()


def test_correct_channels_opened(qtbot: QtBot) -> None:
    jpeg = _make_jpeg()
    header = struct.pack(">I", len(jpeg))
    start_cm, _ = _make_stream_cm()
    frames_cm, _ = _make_frame_stream_cm(header, jpeg)
    tau = _make_tau(start_cm, frames_cm)

    cam_cm, _ = _make_cam_cm()
    svc = _make_svc(tau)
    stopped: list[bool] = []
    svc.webcam_stopped.connect(lambda: stopped.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    channels = [call.args[0] for call in tau.connect.call_args_list]
    assert _CH_WEBCAM_START in channels
    assert _CH_WEBCAM_FRAMES in channels
