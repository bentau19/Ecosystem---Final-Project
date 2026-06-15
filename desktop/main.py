"""SyncDose application entry point.

Bootstraps QApplication, defers all QObject-dependent imports until after
the application instance exists, then shows the main window.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "domain"))

from PySide6.QtWidgets import QApplication

import resources_qrc  # noqa: F401 — registers Qt virtual filesystem

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # These imports are intentionally deferred until after QApplication is
    # constructed.  The modules they pull in create QObjects (NavigationManager,
    # DeviceViewModel, QTimer …) at module-level; instantiating any QObject
    # before QApplication exists causes Qt to emit the
    # "startTimer: event dispatcher already destroyed" warning.

    # ThemeManager must be initialised before any widget is constructed so
    # that theme_manager.is_dark is already correct when the first _setup_style()
    # runs.  It is a lightweight QObject singleton — no side-effects beyond
    # reading QGuiApplication.styleHints().
    from app.theme_manager import theme_manager  # noqa: F401 — triggers singleton init
    from views.main_window import MainWindow

    main_window = MainWindow()
    main_window.show()

    result = app.exec()


    sys.exit(result)
