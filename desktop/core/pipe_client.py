"""
File handler entry point.

Standalone Windows process launched by the OS when the user invokes the
"Send with SyncDose" shell context-menu action.  Receives the target file
path as ``sys.argv[1]``, writes it to the SyncDose named pipe, and exits.

If the pipe is not found (main app not running or phone not connected) a
:class:`~views.widgets.handlers.handler_dialog.PhoneNotDetectedDialog` is shown.
Any other failure shows a
:class:`~views.widgets.handlers.handler_dialog.TransferErrorDialog`.
In both cases the user may click **Try Again** to retry the send, or
**Dismiss** to abort.
"""
import sys
from typing import Final

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog

from pipe import Client
from views.widgets.handlers.handler_dialog import (
    PhoneNotDetectedDialog,
    TransferErrorDialog,
)

# ── Constants ──────────────────────────────────────────────────────────────────

PIPE_NAME: Final[str] = r'\\.\pipe\FileSend'

# Windows error code returned by CreateFile when the named pipe server is not
# listening (i.e. SyncDose is not running or the phone is not connected).
_WINERROR_PIPE_NOT_FOUND: Final[int] = 2  # ERROR_FILE_NOT_FOUND


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ensure_app() -> QCoreApplication | QApplication:
    """Return the existing :class:`QApplication` or create a new one."""
    return QApplication.instance() or QApplication(sys.argv)


# ── Pipe logic ─────────────────────────────────────────────────────────────────

def send_via_pipe(file_path: str) -> None:
    """Write *file_path* to the SyncDose named pipe, retrying on user request.

    Attempts to open the pipe and write the encoded path.  On success the
    function returns immediately.  On failure the appropriate error dialog is
    shown modally; if the user clicks **Try Again** the write is retried,
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
        except ConnectionError as exc:
            _ensure_app()
            dialog: QDialog = (
                PhoneNotDetectedDialog()
                if exc.winerror == _WINERROR_PIPE_NOT_FOUND
                else TransferErrorDialog()
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
        except Exception:
            _ensure_app()
            if TransferErrorDialog().exec() != QDialog.DialogCode.Accepted:
                return


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    send_via_pipe(sys.argv[1])
