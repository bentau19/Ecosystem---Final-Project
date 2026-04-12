from typing import Final

from PySide6.QtCore import QThread

from repositories.device_info import DeviceInfoRepository
from repositories.previous_device import PreviousDeviceRepository
from repositories.tool import ToolRepository
from services.connectivity import ConnectivityService
from services.service import Service


class AppState:
    """Global DI root — holds all repository singletons.

    All view models must access repositories through this singleton rather than
    instantiating them directly.
    """

    def __init__(self) -> None:
        """Initialize all repository instances."""
        self.tools_repository: Final[ToolRepository] = ToolRepository()
        self.device_repository: Final[DeviceInfoRepository] = DeviceInfoRepository()
        self.previous_device_repository: Final[PreviousDeviceRepository] = PreviousDeviceRepository()
        self.service: Final[Service] = Service()


app_state: Final[AppState] = AppState()
