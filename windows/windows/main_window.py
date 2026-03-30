from PySide6.QtWidgets import QMainWindow, QWidget, QLabel

from views.widgets.dashboard.dashboard_home import DashboardPage


class MainWindow(QMainWindow):
    """
    Main window of the application.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dashboard_page: DashboardPage = DashboardPage()

        self.setCentralWidget(self.dashboard_page)
