import sys

from PySide6.QtWidgets import QApplication

import resources_qrc  # noqa: F401 — registers Qt virtual filesystem

from windows.dashboard_window import DashboardWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dash = DashboardWindow()
    dash.show()
    app.exec()
