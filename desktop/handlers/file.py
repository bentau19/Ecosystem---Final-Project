"""
File handler entry point.

Standalone Windows process launched by the OS when the user invokes the
"Send with SyncDose" shell context-menu action.  Receives the target file
path as ``sys.argv[1]``, writes it to the SyncDose named pipe, and exits.

If the pipe is not found (main app not running or phone not connected) a
:class:`~views.widgets.handlers.handler_dialog.PhoneNotDetectedDialog` is shown.
Any other failure shows a
:class:`~views.widgets.handlers.handler_dialog.TransferErrorDialog`.
"""
import sys
from typing import Final

import pywintypes
import win32file
from PySide6.QtWidgets import QApplication

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

def _ensure_app() -> QApplication:
    """Return the existing :class:`QApplication` or create a new one."""
    return QApplication.instance() or QApplication(sys.argv)


# ── Pipe logic ─────────────────────────────────────────────────────────────────

def send_via_pipe(file_path: str) -> None:
    """Write *file_path* to the SyncDose named pipe.

    Opens the pipe in write-only mode, encodes the path as UTF-8, writes it
    in a single call, then closes the handle.  On failure a
    :class:`QApplication` is created if needed and the appropriate error
    dialog is shown modally before the process exits.

    Args:
        file_path: Absolute path of the file the user wants to transfer.
    """
    try:
        handle = win32file.CreateFile(
            PIPE_NAME,
            win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            0,
            None,
        )
        win32file.WriteFile(handle, file_path.encode("utf-8"))
        win32file.CloseHandle(handle)

    except pywintypes.error as exc:
        _ensure_app()
        dialog = (
            PhoneNotDetectedDialog()
            if exc.winerror == _WINERROR_PIPE_NOT_FOUND
            else TransferErrorDialog()
        )
        dialog.exec()

    except Exception:
        _ensure_app()
        TransferErrorDialog().exec()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_via_pipe(sys.argv[1])
