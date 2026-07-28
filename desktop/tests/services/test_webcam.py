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


# ---------------------------------------------------------------------------
# set_enabled() — feature toggle
# ---------------------------------------------------------------------------


def test_receive_start_noop_when_disabled() -> None:
    """A disabled webcam ignores incoming start requests — no channel is opened."""
    start_cm, _ = _make_stream_cm()
    frames_cm, _ = _make_frame_stream_cm(b"", b"")
    tau = _make_tau(start_cm, frames_cm)

    svc = _make_svc(tau)
    svc.set_enabled(False)
    started: list[bool] = []
    svc.webcam_started.connect(lambda: started.append(True))

    with patch("services.webcam.pyvirtualcam.Camera"):
        svc.receive_start()

    tau.connect.assert_not_called()
    assert not svc._running
    assert started == []


def test_stop_aborts_active_stream(qtbot: QtBot) -> None:
    """stop() closes the live stream so the frame loop exits and the camera releases."""
    started: list[bool] = []
    stopped: list[bool] = []
    errors: list[str] = []
    release = threading.Event()

    start_cm, _ = _make_stream_cm()

    # Frame stream parks in read_exactly until close() releases it, then raises EOF
    # (mirrors a stream disposed from another thread).
    frame_stream = MagicMock()

    def _blocked_read(_n: int) -> bytes:
        release.wait(timeout=3)
        raise EOFError("stream closed")

    frame_stream.read_exactly.side_effect = _blocked_read
    frame_stream.close.side_effect = lambda: release.set()
    frame_cm = MagicMock()
    frame_cm.__enter__.return_value = frame_stream
    frame_cm.__exit__.return_value = False

    tau = _make_tau(start_cm, frame_cm)
    cam_cm, _ = _make_cam_cm()
    svc = _make_svc(tau)
    svc.webcam_started.connect(lambda: started.append(True))
    svc.webcam_stopped.connect(lambda: stopped.append(True))
    svc.webcam_error.connect(lambda msg: errors.append(msg))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(started) > 0, timeout=3000)
        assert svc.is_active  # streaming

        svc.stop()
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    frame_stream.close.assert_called()
    assert not svc._running
    assert not svc.is_active
    assert errors == []  # deliberate stop is not surfaced as an error


def test_disable_while_streaming_stops_it(qtbot: QtBot) -> None:
    """set_enabled(False) mid-stream tears the stream down via stop()."""
    started: list[bool] = []
    stopped: list[bool] = []
    release = threading.Event()

    start_cm, _ = _make_stream_cm()
    frame_stream = MagicMock()

    def _blocked_read(_n: int) -> bytes:
        release.wait(timeout=3)
        raise EOFError("stream closed")

    frame_stream.read_exactly.side_effect = _blocked_read
    frame_stream.close.side_effect = lambda: release.set()
    frame_cm = MagicMock()
    frame_cm.__enter__.return_value = frame_stream
    frame_cm.__exit__.return_value = False

    tau = _make_tau(start_cm, frame_cm)
    cam_cm, _ = _make_cam_cm()
    svc = _make_svc(tau)
    svc.webcam_started.connect(lambda: started.append(True))
    svc.webcam_stopped.connect(lambda: stopped.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(lambda: len(started) > 0, timeout=3000)

        svc.set_enabled(False)
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    assert not svc._running


# ---------------------------------------------------------------------------
# Latency — stale frames are dropped rather than queued
# ---------------------------------------------------------------------------


def _solid_jpeg(color: tuple[int, int, int]) -> bytes:
    """A full-size solid-colour JPEG, so the decoded frame needs no rescaling."""
    buf = io.BytesIO()
    Image.new("RGB", (1280, 720), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def test_stale_frames_are_dropped_while_rendering(qtbot: QtBot) -> None:
    """Frames that arrive while one is being rendered must be skipped, not queued.

    Rendering every frame in order lets any shortfall accumulate in the transport's unbounded
    receive buffer, so the picture drifts further behind real time the longer it runs. Only the
    newest frame should survive a slow render — here frames 2 and 3 arrive during the first
    render, and only the last of them may reach the camera.
    """
    frames = [_solid_jpeg(c) for c in ((200, 0, 0), (0, 200, 0), (0, 0, 200))]

    reads: list[bytes | None] = []
    for jpeg in frames:
        reads.extend([struct.pack(">I", len(jpeg)), jpeg])
    reads.append(None)  # EOF

    frame_stream = MagicMock()
    frame_stream.read_exactly.side_effect = reads
    frames_cm = MagicMock()
    frames_cm.__enter__.return_value = frame_stream
    frames_cm.__exit__.return_value = False

    start_cm, _ = _make_stream_cm()
    tau = _make_tau(start_cm, frames_cm)
    cam_cm, cam = _make_cam_cm()

    all_frames_read = threading.Event()

    def _blocking_send(_image: object) -> None:
        # Hold the first render open until every frame has been read, so frames 2 and 3 are
        # both waiting by the time the loop asks for the next one.
        all_frames_read.wait(timeout=3)

    cam.send.side_effect = _blocking_send

    def _watch_reads() -> bool:
        if frame_stream.read_exactly.call_count >= len(reads):
            all_frames_read.set()
        return all_frames_read.is_set()

    svc = _make_svc(tau)
    stopped: list[bool] = []
    svc.webcam_stopped.connect(lambda: stopped.append(True))

    with patch("services.webcam.pyvirtualcam.Camera", return_value=cam_cm):
        svc.receive_start()
        qtbot.waitUntil(_watch_reads, timeout=3000)
        qtbot.waitUntil(lambda: len(stopped) > 0, timeout=3000)

    # Three frames arrived while the first render was held open, so at least one was superseded
    # before it could be shown. (How many depends on how far the reader ran ahead — the guarantee
    # is that frames are dropped, not queued.)
    assert 0 < cam.send.call_count < len(frames)
    # And the frame that survived is the newest (blue), not one it overtook (red/green).
    last_sent = cam.send.call_args_list[-1].args[0]
    assert int(last_sent[:, :, 2].mean()) > int(last_sent[:, :, 1].mean())
    assert int(last_sent[:, :, 2].mean()) > int(last_sent[:, :, 0].mean())
