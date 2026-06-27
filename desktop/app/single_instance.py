# Single-instance enforcement for SyncDose.
#
# SyncDose is a tray-resident app: minimizing hides the window instead of
# closing it, and it can be relaunched silently (Start menu, the "Send with
# SyncDose" shell handler, etc.).  Without a guard each relaunch would spawn a
# second SyncDose.exe that tries to bind the same named pipes
# (\\.\pipe\FileSend, \\.\pipe\SyncDoseVDrive) and open a second TauSync
# connection — producing confusing duplicate windows and pipe-bind failures.
#
# A Windows named mutex is the canonical, dependency-free way to detect a
# running instance: the kernel guarantees the name is unique per namespace, so
# the second process to call CreateMutexW learns it lost the race via
# ERROR_ALREADY_EXISTS without any IPC of our own.
import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Final

logger: Final[logging.Logger] = logging.getLogger(__name__)

# GetLastError() value returned by CreateMutexW when the named mutex already
# exists (another process created it first).  See WinError.h.
_ERROR_ALREADY_EXISTS: Final[int] = 183

# Per-session mutex name.  The "Local\" prefix scopes the name to the current
# user's logon session, so two different logged-in users may each run their own
# SyncDose instance, but a single user cannot launch two at once.  The GUID-like
# suffix avoids colliding with any unrelated mutex.
_DEFAULT_MUTEX_NAME: Final[str] = r"Local\SyncDose-SingleInstance-9F2C1A6E"

# user32.MessageBoxW style flags used by show_already_running_dialog().
_MB_OK: Final[int] = 0x00000000
_MB_ICONINFORMATION: Final[int] = 0x00000040
_MB_SETFOREGROUND: Final[int] = 0x00010000


class SingleInstanceGuard:
    """Cross-process lock ensuring only one SyncDose instance runs per session.

    Wraps a Windows named mutex obtained via ``CreateMutexW``.  The first
    process to construct the named mutex owns it; any later process observes
    ``ERROR_ALREADY_EXISTS`` and should exit.

    The owning handle is held for the lifetime of the guard (and therefore the
    process, since the guard is created at bootstrap and kept on the module
    stack in ``main.py``).  The OS releases the mutex automatically when the
    owning process exits, so an orphaned lock can never block future launches.

    On non-Windows platforms the guard is an inert no-op that always reports the
    instance as unique, keeping import-time behavior safe in test environments.
    """

    def __init__(self, name: str = _DEFAULT_MUTEX_NAME) -> None:
        """Initialize the guard.

        Args:
            name: Fully-qualified named-mutex string (including any namespace
                prefix such as ``Local\\`` or ``Global\\``).  Defaults to a
                per-session SyncDose-specific name.
        """
        self._name: Final[str] = name
        self._handle: int | None = None

    def try_acquire(self) -> bool:
        """Attempt to become the single running instance.

        Creates (or opens) the named mutex and reports whether this process is
        the first to do so.

        Returns:
            ``True`` if this process now owns the lock and may continue
            launching; ``False`` if another instance already holds it and this
            process should exit.

        Notes:
            Fails open: if the platform is not Windows, or the Win32 call fails
            unexpectedly, the method logs and returns ``True`` so a transient
            OS error can never permanently lock the user out of the app.
        """
        if not sys.platform.startswith("win"):
            # SyncDose only ships on Windows; on any other platform (e.g. CI
            # running headless tests) there is nothing to guard against.
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # HANDLE is pointer-sized — declaring restype is essential, otherwise
        # ctypes truncates the 64-bit handle to a 32-bit int and we leak/close
        # the wrong handle.
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPCVOID,  # lpMutexAttributes (NULL → default security)
            wintypes.BOOL,     # bInitialOwner
            wintypes.LPCWSTR,  # lpName
        ]

        handle: int = kernel32.CreateMutexW(None, False, self._name)
        last_error: int = ctypes.get_last_error()

        if not handle:
            # Creation failed outright (very unusual).  Fail open: allow the
            # launch rather than soft-bricking the app over a transient error.
            logger.warning(
                "CreateMutexW failed (error=%d); allowing launch without single-instance guard.",
                last_error,
            )
            return True

        if last_error == _ERROR_ALREADY_EXISTS:
            # The mutex pre-existed: another instance owns it.  We received a
            # valid handle to the *existing* object — close it so we don't leak,
            # then report that we are NOT the unique instance.
            kernel32.CloseHandle(handle)
            logger.info("Another SyncDose instance is already running; this launch will exit.")
            return False

        # We created the mutex first — keep the handle alive for the process
        # lifetime so the lock persists.
        self._handle = handle
        logger.debug("Single-instance lock acquired (mutex=%s).", self._name)
        return True

    def release(self) -> None:
        """Release the named mutex if this process owns it.

        Optional — the OS frees the mutex on process exit regardless.  Provided
        for symmetry and for tests that want deterministic cleanup.
        """
        if self._handle is None:
            return
        if sys.platform.startswith("win"):
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._handle)
        self._handle = None


def show_already_running_dialog() -> None:
    """Show a native "already running" message box (no Qt/QApplication needed).

    Uses ``user32.MessageBoxW`` directly so the bail-out path stays lightweight
    and never imports the Qt/AppState/TauSync stack.  No-op off Windows.
    """
    if not sys.platform.startswith("win"):
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MessageBoxW(
        None,
        "SyncDose is already running.\n\nCheck the system tray for the existing window.",
        "SyncDose",
        _MB_OK | _MB_ICONINFORMATION | _MB_SETFOREGROUND,
    )
