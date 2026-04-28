from typing import Final

from utils.repository_manger import repository_manager
from utils.services_manager import services_manager
from viewmodels.device import DeviceViewModel


class ViewModelManager:
    """Application-level DI root for ViewModel singletons.

    Constructs each ViewModel exactly once with its required repository and
    service dependencies injected from the shared manager singletons.
    All view widgets must obtain ViewModels through this object rather than
    instantiating them directly.
    """

    def __init__(self) -> None:
        """Initialize all ViewModel instances with their injected dependencies."""
        self.device_viewmodel: DeviceViewModel = DeviceViewModel(
            repository_manager.device_repository,
            services_manager.connectivity_service,
        )


viewmodel_manager: Final[ViewModelManager] = ViewModelManager()
