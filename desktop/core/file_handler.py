import logging
import sys
from pathlib import Path
from typing import Final

# Add the desktop/ root to sys.path so imports work both when run directly
# and when bundled by PyInstaller (which sets pathex correctly in the spec).
_DESKTOP_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_DESKTOP_ROOT) not in sys.path:
    sys.path.insert(0, str(_DESKTOP_ROOT))

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog

from native.windows.pipe import Client
from views.widgets.dialogs.file_handler import (
    PhoneNotDetectedDialog,
    TransferErrorDialog,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

PIPE_NAME: Final[str] = r'\\.\pipe\FileSend'


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ensure_app() -> QCoreApplication | QApplication:
    # Reuse an existing QApplication if one is already running, otherwise
    # construct one — a QApplication instance is required before any
    # QDialog can be shown.
    return QApplication.instance() or QApplication(sys.argv)


# ── Pipe logic ─────────────────────────────────────────────────────────────────

def send_via_pipe(file_path: str) -> None:
    """Write *file_path* to the SyncDose named pipe, retrying on user request.

    Attempts to open the pipe and write the encoded path.  On success the
    function returns immediately.  On failure the appropriate error dialog is
    shown modally; if the user clicks **Try Again** to write is retried,
    otherwise the function returns without sending.

    Args:
        file_path: Absolute path of the file the user wants to transfer.
    """
    while True:
        try:
            client = Client(65536, 65536, PIPE_NAME)
            client.write(file_path.encode('utf-8'))
            client.close()
            return

        except ConnectionError:
            _ensure_app()
            if PhoneNotDetectedDialog().exec() != QDialog.DialogCode.Accepted:
                return
        except Exception as exe:
            _ensure_app()
            logger.error("Pipe write error: %s", exe)
            if TransferErrorDialog().exec() != QDialog.DialogCode.Accepted:
                return


# ── Entry point ────────────────────────────────────────────────────────────────
# Standalone Windows process launched by the OS when the user invokes the
# "Send with SyncDose" shell context-menu action.  Receives the target file
# path as sys.argv[1], writes it to the SyncDose named pipe, and exits.
#
# If the pipe is not found (main app not running or phone not connected) a
# PhoneNotDetectedDialog is shown.  Any other failure shows a
# TransferErrorDialog.  In both cases the user may click "Try Again" to retry
# to send, or "Dismiss" to abort.

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    send_via_pipe(sys.argv[1])
