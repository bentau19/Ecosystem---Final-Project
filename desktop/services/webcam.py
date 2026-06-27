import io
import struct
import threading

import numpy as np
import pyvirtualcam
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, Signal
from tausync_py import TauSyncStream

from domain.enums.webcam_channels import WebcamChannels
from services.connectivity import ConnectivityService
from services.lifecycle import LifecycleFlag

_WIDTH = 1280
_HEIGHT = 720
_FPS = 24


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
                    while self._running:
                        header = frame_stream.read_exactly(4)
                        if not header:
                            break
                        (size,) = struct.unpack(">I", header)
                        jpeg_bytes = frame_stream.read_exactly(size)
                        if not jpeg_bytes:
                            break
                        img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
                        img = ImageOps.pad(img, (_WIDTH, _HEIGHT), color=(0, 0, 0))
                        cam.send(np.array(img))
                        cam.sleep_until_next_frame()

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
