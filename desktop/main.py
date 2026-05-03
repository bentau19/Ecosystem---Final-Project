"""SyncDose application entry point.

Bootstraps QApplication, defers all QObject-dependent imports until after
the application instance exists, then shows the main window.
"""

import sys

from PySide6.QtWidgets import QApplication

import resources_qrc  # noqa: F401 — registers Qt virtual filesystem

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # These imports are intentionally deferred until after QApplication is
    # constructed.  The modules they pull in create QObjects (NavigationManager,
    # DeviceViewModel, QTimer …) at module-level; instantiating any QObject
    # before QApplication exists causes Qt to emit the
    # "startTimer: event dispatcher already destroyed" warning.
    from views.main_window import MainWindow

    main_window = MainWindow()
    main_window.show()

    result = app.exec()


    sys.exit(result)
