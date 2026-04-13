from typing import Final

from services.connectivity import ConnectivityService


class ServicesManager:
    def __init__(self) -> None:
        self.connectivity_service: Final[ConnectivityService] = ConnectivityService()




services_manager: Final[ServicesManager] = ServicesManager()
