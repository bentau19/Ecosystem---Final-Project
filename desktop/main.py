import sys

from PySide6.QtWidgets import QApplication

import resources_qrc  # noqa: F401 — registers Qt virtual filesystem
from windows.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
