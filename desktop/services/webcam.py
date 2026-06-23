import io
import struct
import threading

import numpy as np
import pyvirtualcam
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, Signal

from domain.enums.webcam_channels import WebcamChannels
from services.connectivity import ConnectivityService

_WIDTH = 1280
_HEIGHT = 720
_FPS = 24


class WebcamService(QObject):
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

    def receive_start(self) -> None:
        """Called by PhoneRequestService when Android opens the WEBCAM_START channel.

        Silently drops duplicate requests if a stream is already active — guards against
        Android sending webcam_start twice (e.g. user taps Start rapidly).
        """
        with self._lock:
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            tau = self._connectivity.tau

            with tau.connect(WebcamChannels.WEBCAM_START.value) as start_stream:
                start_stream.read_all()

            with pyvirtualcam.Camera(
                width=_WIDTH, height=_HEIGHT, fps=_FPS,
                fmt=pyvirtualcam.PixelFormat.RGB,
            ) as cam:
                self.webcam_started.emit()

                with tau.connect(WebcamChannels.WEBCAM_FRAMES.value) as frame_stream:
                    while True:
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
            self.webcam_error.emit(str(exc))
        finally:
            with self._lock:
                self._running = False
            self.webcam_stopped.emit()
