# SyncDose application entry point.
#
# Bootstraps QApplication, defers all QObject-dependent imports until after
# the application instance exists, then shows the main window.
import sys
import os  # [diag] temporary — for SYNCDOSE_DIAG_AUTOQUIT env gate
import faulthandler  # [diag] temporary

# import os

# sys.path.insert(0, os.path.join(os.path.dirname(__file__), "domain"))

from pathlib import Path

# ---------------------------------------------------------------------------
# FileDetection path injection
# ---------------------------------------------------------------------------
# BackupService imports classifer, image_classifer, detector, file_duplicates
# as bare top-level modules.  They live in FileDetection/ which is NOT a
# proper package on sys.path, so we add it here before any deferred imports.
#
# Two locations depending on execution context:
#   • Frozen (PyInstaller): FileDetection/ was bundled into sys._MEIPASS
#   • Source: FileDetection/ is one level above this desktop/ directory
#
# The insert is idempotent (guards against double-registration).
if getattr(sys, 'frozen', False):
    _FILE_DETECTION_DIR: Path = Path(sys._MEIPASS) / "FileDetection"  # type: ignore[attr-defined]
else:
    _FILE_DETECTION_DIR: Path = Path(__file__).resolve().parent.parent / "FileDetection"
if str(_FILE_DETECTION_DIR) not in sys.path:
    sys.path.insert(0, str(_FILE_DETECTION_DIR))
# ---------------------------------------------------------------------------

from app.logging_config import configure_logging

configure_logging()

faulthandler.enable()  # [diag] temporary — dump Python stacks on fatal signal

from PySide6.QtWidgets import QApplication

import resources_qrc  # noqa: F401 — registers Qt virtual filesystem

if __name__ == "__main__":
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

    # Importing MainWindow pulls in app_state → ConnectivityService → TauSync(),
    # which calls pythonnet.load() and registers an atexit handler that runs
    # Python.Runtime.Loader.Shutdown("full_shutdown") at interpreter exit.  That
    # CLR shutdown hangs forever during Py_Finalize, wedging the process even
    # after app.exec() returns.  We don't need the CLR unloaded — the process is
    # exiting and the OS reclaims it — so unregister the handler for a clean exit.
    import atexit
    import pythonnet

    atexit.unregister(pythonnet.unload)

    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    main_window.raise_()
    main_window.activateWindow()
    sys.exit(app.exec())
