from PySide6.QtCore import QObject, Slot

from domain.dto.dependency_info import DependencyInfoDTO
from domain.enums.dependency import Dependency
from services.dependency import DependencyService


class DependencyViewModel(QObject):
    """ViewModel backing the missing-dependencies startup dialog.

    Holds the components detected as missing at startup and forwards the user's
    install choices to :class:`~services.dependency.DependencyService`, keeping
    the view free of any service or system import.

    Constructed by the ``main.py`` bootstrap rather than ``AppState``: the
    dependency gate must run before the AppState import loads .NET, so it cannot
    itself live on the DI root.
    """

    def __init__(
            self,
            dependency_service: DependencyService,
            missing: list[DependencyInfoDTO],
            parent: QObject | None = None,
    ) -> None:
        """Initialize the ViewModel.

        Args:
            dependency_service: Service used to perform installs.
            missing: Components detected as missing, surfaced to the view.
            parent: Optional Qt parent object for memory management.
        """
        super().__init__(parent)
        self._dependency_service: DependencyService = dependency_service
        self._missing: list[DependencyInfoDTO] = missing

    @property
    def missing(self) -> list[DependencyInfoDTO]:
        """The components detected as missing at startup."""
        return self._missing

    @property
    def has_required_missing(self) -> bool:
        """``True`` when at least one *required* component is missing.

        The dialog uses this to decide whether to offer a "continue without
        installing" path — withheld while the app cannot run.
        """
        return any(info.required for info in self._missing)

    @Slot(object)
    def request_install(self, dependency: Dependency) -> None:
        """Install a single *dependency* via the service.

        Args:
            dependency: The component the user chose to install.
        """
        self._dependency_service.install(dependency)
