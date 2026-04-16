from typing import Final

from services.connectivity import ConnectivityService
from utils.repository_manger import repository_manager


class ServicesManager:
    """Application-level DI root for service singletons.

    Constructs each service exactly once and injects its dependencies from
    :data:`~utils.repository_manger.repository_manager` so that no service
    ever instantiates a repository directly.
    """

    def __init__(self) -> None:
        """Initialize all service instances with their injected dependencies."""
        self.connectivity_service: Final[ConnectivityService] = ConnectivityService(
            repository=repository_manager.device_repository
        )


services_manager: Final[ServicesManager] = ServicesManager()
