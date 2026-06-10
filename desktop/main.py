# SyncDose application entry point.
#
# Bootstraps QApplication, defers all QObject-dependent imports until after
# the application instance exists, then shows the main window.

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# FileDetection path injection
# ---------------------------------------------------------------------------
# BackupService imports is_corrupt, check_for_duplicates, and is_wanted from
# the FileDetection/ module that lives at the project root (one level above
# this desktop/ directory).  Adding it to sys.path here — before any deferred
# imports — ensures those bare-module imports resolve at app startup rather
# than silently failing mid-backup.
#
# The insert is intentionally idempotent (guards against double-registration
# if this block is somehow executed twice).
_FILE_DETECTION_DIR: Path = Path(__file__).resolve().parent.parent / "FileDetection"
if str(_FILE_DETECTION_DIR) not in sys.path:
    sys.path.insert(0, str(_FILE_DETECTION_DIR))
# ---------------------------------------------------------------------------

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
