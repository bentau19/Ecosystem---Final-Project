from typing import Final

from PySide6.QtCore import QObject, Signal

from enums.screen import Screen


class NavigationManager(QObject):
    navigate: Signal = Signal(int)  # emits Screen.value

    def __init__(self, parent=None):
        super().__init__(parent)
    def go_to_screen(self, screen: Screen) -> None:
        self.navigate.emit(screen.value)


navigation_manager:Final[NavigationManager] = NavigationManager()
