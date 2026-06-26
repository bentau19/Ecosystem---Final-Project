from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from services.webcam import WebcamService


class WebcamViewModel(QObject):
    """ViewModel for the webcam streaming feature.

    Bridges WebcamService signals to the View layer.  The View never imports
    from services directly — it connects to this ViewModel's signals and calls
    its public methods in response to user actions.

    Flow::

        Android opens webcam_start channel
          → PhoneRequestService calls webcam_service.receive_start()
          → service emits webcam_started
          → _on_webcam_started → emits webcam_active_changed(True)
          → MainWindow shows tray toast "Webcam connected"

        Android closes webcam_frames channel (user taps Stop)
          → service emits webcam_stopped
          → _on_webcam_stopped → emits webcam_active_changed(False)
          → MainWindow shows tray toast "Webcam disconnected"

    Signals:
        webcam_active_changed (Signal[bool]): True when the virtual camera is
            streaming, False when it stops.
        webcam_error_occurred (Signal[str]): Emitted with an error message when
            the stream fails unexpectedly.
    """

    webcam_active_changed: Signal = Signal(bool)
    webcam_error_occurred: Signal = Signal(str)

    def __init__(self, webcam_service: WebcamService, parent=None) -> None:
        super().__init__(parent)
        self._service = webcam_service
        self._service.webcam_started.connect(self._on_webcam_started)
        self._service.webcam_stopped.connect(self._on_webcam_stopped)
        self._service.webcam_error.connect(self._on_webcam_error)

    @Slot()
    def _on_webcam_started(self) -> None:
        self.webcam_active_changed.emit(True)

    @Slot()
    def _on_webcam_stopped(self) -> None:
        self.webcam_active_changed.emit(False)

    @Slot(str)
    def _on_webcam_error(self, error: str) -> None:
        self.webcam_error_occurred.emit(error)
