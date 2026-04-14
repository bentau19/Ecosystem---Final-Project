from typing import Final

from utils.repository_manger import repository_manager
from utils.services_manager import services_manager
from viewmodels.device import DeviceViewModel


class ViewModelManager:
    def __init__(self) -> None:
        self.device_viewmodel: DeviceViewModel = DeviceViewModel(repository_manager.device_repository,
                                                                  services_manager.connectivity_service)


viewmodel_manager: Final[ViewModelManager] = ViewModelManager()
