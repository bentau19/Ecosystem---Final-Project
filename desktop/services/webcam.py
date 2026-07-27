import logging
import struct
import threading

import cv2
import numpy as np
import pyvirtualcam
from PySide6.QtCore import QObject, Signal
from tausync_py import TauSyncStream

from domain.enums.webcam_channels import WebcamChannels
from services.connectivity import ConnectivityService
from services.lifecycle import LifecycleFlag

logger = logging.getLogger(__name__)

_WIDTH = 1280
_HEIGHT = 720
_FPS = 24


def _fit_to_camera(image: np.ndarray) -> np.ndarray:
    """Scale *image* to the virtual camera's size, preserving aspect and padding with black.

    Returns the image untouched when it already matches, which is the normal case — the phone
    caps its capture at the same resolution — so a well-behaved stream pays nothing here.
    """
    height, width = image.shape[:2]
    if (width, height) == (_WIDTH, _HEIGHT):
        return image

    scale = min(_WIDTH / width, _HEIGHT / height)
    scaled_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    # INTER_AREA is the right filter for shrinking; it degrades to a plain average when enlarging,
    # so pick the cheaper linear interpolation in that direction.
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    scaled = cv2.resize(image, scaled_size, interpolation=interpolation)

    horizontal_padding = _WIDTH - scaled_size[0]
    vertical_padding = _HEIGHT - scaled_size[1]
    return cv2.copyMakeBorder(
        scaled,
        vertical_padding // 2, vertical_padding - vertical_padding // 2,
        horizontal_padding // 2, horizontal_padding - horizontal_padding // 2,
        cv2.BORDER_CONSTANT, value=(0, 0, 0),
    )


class WebcamService(LifecycleFlag, QObject):
    """Receives a live camera stream from Android and feeds it into a virtual webcam.

    Flow:
        1. PhoneRequestService detects Android waiting on WEBCAM_START and calls receive_start().
        2. A daemon thread connects to WEBCAM_START (reads the handshake) then opens pyvirtualcam.
        3. The same thread connects to WEBCAM_FRAMES and reads length-prefixed JPEG frames in a loop.
        4. Each frame is decoded and pushed to the virtual camera.
        5. When Android closes the channel (or an error occurs) the virtual camera is released.

    Frame wire format (agreed with Android):
        [4 bytes big-endian uint32 = JPEG size][N bytes JPEG data]
    """

    webcam_started: Signal = Signal()
    webcam_stopped: Signal = Signal()
    webcam_error: Signal = Signal(str)

    def __init__(self, connectivity: ConnectivityService, parent=None) -> None:
        super().__init__(parent)
        self._connectivity = connectivity
        self._running = False
        self._lock = threading.Lock()
        self._init_lifecycle()

        # Feature toggle (Settings → Webcam).  When False, incoming start
        # requests are ignored.  Defaults to enabled; SettingsViewModel applies
        # the persisted value on construction.
        self._enabled: bool = True

        # Live stream handles, stored so stop() can close them from another
        # thread to unblock a parked read and release the virtual camera.
        self._start_stream: TauSyncStream | None = None
        self._frame_stream: TauSyncStream | None = None

    # ── Feature toggle ────────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the phone→virtual-camera stream.

        Disabling while a stream is active stops it immediately (the virtual
        camera is released), reusing the same teardown as app shutdown.

        Args:
            enabled: ``True`` to allow streaming, ``False`` to block/stop it.
        """
        self._enabled = enabled
        if not enabled:
            self.stop()

    def receive_start(self) -> None:
        """Called by PhoneRequestService when Android opens the WEBCAM_START channel.

        No-op when the feature is disabled.  Silently drops duplicate requests if
        a stream is already active — guards against Android sending webcam_start
        twice (e.g. user taps Start rapidly).
        """
        if not self._enabled:
            return
        with self._lock:
            if self._running:
                return
            self._running = True
            self._mark_started()
        threading.Thread(target=self._run, daemon=True).start()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """No-op — the stream starts on an Android request, not at app start.

        Present so :class:`~app.app_state.AppState` can hold this service as a
        :class:`~services.lifecycle.Lifecycle` and drive it from the shutdown poll.
        """

    def stop(self) -> None:
        """Abort any active stream so the virtual camera is released.

        Clears ``_running`` (so the frame loop does not re-iterate) and closes the
        stored streams (thread-safe) to unblock a read parked in
        ``read_exactly`` / ``read_all``.  The actual camera release and
        :meth:`_mark_stopped` happen on the ``_run`` thread; :attr:`is_active`
        reports when teardown has finished.  Safe to call when not streaming.
        """
        with self._lock:
            self._running = False
            start_stream = self._start_stream
            frame_stream = self._frame_stream
        for stream in (frame_stream, start_stream):
            if stream is not None:
                stream.close()

    # ── Frame pipeline ─────────────────────────────────────────────────────────

    def _render_newest_frames(self, frame_stream: TauSyncStream, cam) -> None:
        """Feed the virtual camera, always with the most recent frame received.

        Reading and rendering run at different speeds — the phone sends at its own rate while
        decoding and the camera's frame pacing take whatever time they take.  Rendering every
        frame in arrival order would therefore let any shortfall accumulate: the excess sits in
        the transport's receive buffer (which is unbounded), so the picture falls further and
        further behind real time and never catches up.

        Instead a reader thread parks the newest frame in a single slot, overwriting any frame
        that has not been rendered yet, and this loop always takes whatever is there now.  Late
        frames are dropped rather than queued, which bounds the delay at roughly one frame no
        matter how the two rates drift.  The phone already discards stale frames the same way, so
        the whole path from camera to virtual webcam prefers the freshest picture over a complete
        one.
        """
        newest: list[bytes | None] = [None]
        finished = threading.Event()
        frame_ready = threading.Condition()

        def read_frames() -> None:
            try:
                while self._running:
                    header = frame_stream.read_exactly(4)
                    if not header:
                        break
                    (size,) = struct.unpack(">I", header)
                    jpeg_bytes = frame_stream.read_exactly(size)
                    if not jpeg_bytes:
                        break
                    with frame_ready:
                        newest[0] = jpeg_bytes  # drops any frame not yet rendered
                        frame_ready.notify()
            except Exception as exc:
                # A closed stream during teardown is expected; anything else ends the stream just
                # the same, and _run's own error handling reports it if it was not deliberate.
                logger.debug("Webcam frame reader ended: %s", exc)
            finally:
                finished.set()
                with frame_ready:
                    frame_ready.notify()

        reader = threading.Thread(target=read_frames, name="webcam-frame-reader", daemon=True)
        reader.start()
        try:
            while self._running:
                with frame_ready:
                    while newest[0] is None and not finished.is_set():
                        frame_ready.wait(timeout=0.5)
                    jpeg_bytes = newest[0]
                    newest[0] = None
                if jpeg_bytes is None:
                    if finished.is_set():
                        break
                    continue  # woken by the timeout with nothing to show — keep waiting
                image = self._to_camera_frame(jpeg_bytes)
                if image is None:
                    continue  # undecodable frame — skip it, the next one is already on its way
                cam.send(image)
                cam.sleep_until_next_frame()
        finally:
            reader.join(timeout=1)

    @staticmethod
    def _to_camera_frame(jpeg_bytes: bytes) -> np.ndarray | None:
        """Decode a JPEG frame into the RGB array the virtual camera expects.

        Uses OpenCV rather than Pillow: this runs once per frame inside the render loop, so
        decode time comes directly out of the budget for keeping up with the phone.

        Returns ``None`` if the frame could not be decoded.
        """
        decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            return None
        return cv2.cvtColor(_fit_to_camera(decoded), cv2.COLOR_BGR2RGB)

    def _run(self) -> None:
        try:
            tau = self._connectivity.tau

            with tau.connect(WebcamChannels.WEBCAM_START.value) as start_stream:
                self._start_stream = start_stream
                start_stream.read_all()

            with pyvirtualcam.Camera(
                width=_WIDTH, height=_HEIGHT, fps=_FPS,
                fmt=pyvirtualcam.PixelFormat.RGB,
            ) as cam:
                self.webcam_started.emit()

                with tau.connect(WebcamChannels.WEBCAM_FRAMES.value) as frame_stream:
                    self._frame_stream = frame_stream
                    self._render_newest_frames(frame_stream, cam)

        except Exception as exc:
            # A deliberate stop() closes the stream mid-read, surfacing here as an
            # EOF / closed-stream error — that is graceful teardown, not a fault.
            if self._running:
                self.webcam_error.emit(str(exc))
        finally:
            with self._lock:
                self._running = False
                self._start_stream = None
                self._frame_stream = None
            self._mark_stopped()
            self.webcam_stopped.emit()
