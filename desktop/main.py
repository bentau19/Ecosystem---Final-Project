# SyncDose application entry point.
#
# Bootstraps QApplication, defers all QObject-dependent imports until after
# the application instance exists, then shows the main window.
import sys
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

# ---------------------------------------------------------------------------
# Standard stream guard (PyInstaller --windowed)
# ---------------------------------------------------------------------------
# A windowed (no-console) frozen build has no stdio attached, so Python sets
# sys.stdout / sys.stderr to None.  Anything that writes to them then crashes —
# logging StreamHandler in configure_logging() would silently fail on every emit.
# Redirect both to a real, line-buffered file so those diagnostics survive
# instead of taking down the app.  This MUST run before configure_logging() and

from app.logging_config import configure_logging

configure_logging()

from PySide6.QtWidgets import QApplication

import resources_qrc  # noqa: F401 — registers Qt virtual filesystem

if __name__ == "__main__":
    # Single-instance guard FIRST — before any heavy import (MainWindow pulls in
    # AppState → TauSync → pythonnet) and before QApplication.  If another
    # SyncDose is already running, bail out immediately so we never bind the
    # named pipes twice or open a duplicate TauSync connection.
    from app.single_instance import SingleInstanceGuard, show_already_running_dialog

    _instance_guard = SingleInstanceGuard()  # kept on the module stack for the process lifetime
    if not _instance_guard.try_acquire():
        show_already_running_dialog()
        sys.exit(0)

    # QApplication must exist before any QWidget/QDialog. Create it now — it has
    # no .NET dependency — so the dependency gate below can show its dialog
    # *before* the .NET-loading MainWindow import runs.
    app = QApplication(sys.argv)

    # ── Dependency gate ──────────────────────────────────────────────────────
    # Detect missing Windows components (.NET 8 / WinFSP / OBS) BEFORE importing
    # MainWindow. That import constructs AppState → ConnectivityService →
    # TauSync(), which loads the .NET 8 runtime via pythonnet; if .NET 8 is
    # absent the import itself can crash. Running the check here lets us block
    # startup (and exit) when a required component is missing so the user can
    # install it and relaunch. The service/viewmodel are bootstrap-local: a gate
    # for the DI root cannot live on the DI root.
    from services.dependency import DependencyService
    from viewmodels.dependency import DependencyViewModel
    from views.widgets.dialogs.missing_dependencies_dialog import (
        MissingDependenciesDialog,
    )

    dependency_service = DependencyService()
    missing_dependencies = dependency_service.check_missing()
    if missing_dependencies:
        dependency_viewmodel = DependencyViewModel(
            dependency_service, missing_dependencies
        )
        _dependency_dialog = MissingDependenciesDialog(dependency_viewmodel)
        _dependency_dialog.exec()
        if not _dependency_dialog.should_launch:
            sys.exit(0)

    # These imports are intentionally deferred until after QApplication is
    # constructed.  The modules they pull in create QObjects (NavigationManager,
    # DeviceViewModel, QTimer …) at module-level; instantiating any QObject
    # before QApplication exists causes Qt to emit the
    # "startTimer: event dispatcher already destroyed" warning.

    # ThemeManager must be initialized before any widget is constructed so
    # that theme_manager.is_dark is already correct when the first _setup_style()
    # runs.  It is a lightweight QObject singleton — no side-effects beyond
    # reading QGuiApplication.styleHints().
    from app.theme_manager import theme_manager  # noqa: F401 — triggers singleton init
    from views.main_window import MainWindow

    # Show a splash screen while loading the main window to avoid a black screen
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QSplashScreen
    from resources.paths import Icons

    splash_pixmap = QPixmap(Icons.LOGO.value)
    splash = QSplashScreen(splash_pixmap)
    splash.show()
    app.processEvents()

    main_window = MainWindow()
    splash.finish(main_window)

    main_window.show()
    main_window.raise_()
    main_window.activateWindow()
    sys.exit(app.exec())
