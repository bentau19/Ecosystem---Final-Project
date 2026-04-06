from PySide6.QtWidgets import QMainWindow, QWidget

from views.screens.dashboard_screen import DashboardScreen


class MainWindow(QMainWindow):
    """
    Main window of the application.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dashboard_page: DashboardScreen = DashboardScreen()

        self.setCentralWidget(self.dashboard_page)
