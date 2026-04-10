from typing import Final

from repositories.device_info import DeviceInfoRepository
from repositories.previous_device import PreviousDeviceRepository
from repositories.tool import ToolRepository


class AppState:
    """Global DI root — holds all repository singletons.

    All viewmodels must access repositories through this singleton rather than
    instantiating them directly.
    """

    def __init__(self) -> None:
        """Initialize all repository instances."""
        self.tools_repository: Final[ToolRepository] = ToolRepository()
        self.device_repository: Final[DeviceInfoRepository] = DeviceInfoRepository()
        self.previous_device_repository: Final[PreviousDeviceRepository] = PreviousDeviceRepository()


app_state: Final[AppState] = AppState()
