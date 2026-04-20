from typing import Final

from PySide6.QtCore import QObject, Signal

from enums.screen import Screen


class NavigationManager(QObject):
    """Application-wide navigation controller.

    Holds no screen references of its own — it simply emits an integer index
    that ``MainWindow`` uses to switch the active page in its
    :class:`~PySide6.QtWidgets.QStackedWidget`.

    Using a singleton (``navigation_manager``) avoids prop-drilling the
    manager through every widget that needs to trigger a page change.

    Signals:
        navigate (Signal[int]): Emitted with the :attr:`~enums.screen.Screen`
            integer value of the target screen.
    """

    navigate: Signal = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the navigation manager.

        Args:
            parent: Optional Qt parent object.
        """
        super().__init__(parent)

    def go_to_screen(self, screen: Screen) -> None:
        """Emit the navigate signal for the given screen.

        Args:
            screen: The target :class:`~enums.screen.Screen` enum member.

        Emits:
            navigate: With ``screen.value`` (an ``int``) as the payload.
        """
        self.navigate.emit(screen.value)


navigation_manager: Final[NavigationManager] = NavigationManager()
