from PySide6.QtCore import QObject, Signal

from services.connectivity import ConnectivityService


class Service(QObject):
    device_connected = Signal()
    device_disconnected = Signal()
    connection_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connectivity_service = ConnectivityService(self)

        self._connectivity_service.device_connected.connect(self.device_connected)
        self._connectivity_service.device_disconnected.connect(self.device_disconnected)
        self._connectivity_service.connection_error.connect(self.connection_error)

    def disconnect_device(self) -> None:
        self._connectivity_service.disconnect_device()

    def connect_device(self, ip) -> None:
        self._connectivity_service.connect_to_device(ip)
