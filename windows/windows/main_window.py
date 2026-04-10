from PySide6.QtWidgets import QMainWindow, QWidget

from views.screens.login import LoginScreen


class MainWindow(QMainWindow):
    """Main window of the application."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._login_screen = LoginScreen(self)
        self.setCentralWidget(self._login_screen)
