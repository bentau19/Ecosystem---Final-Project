from typing import Final
from repositories.device_info import DeviceInfoRepository
from repositories.tool import ToolRepository


class AppState:
    """
    Class representing the application state.
    """

    def __init__(self) -> None:
        """
        Initialize an instance of the AppState class.
        """
        self.tools_repository: Final[ToolRepository] = ToolRepository()
        self.device_repository: Final[DeviceInfoRepository] = DeviceInfoRepository()


app_state: Final[AppState] = AppState()
