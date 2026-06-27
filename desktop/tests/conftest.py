import os
import sys
import threading
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

# ---------------------------------------------------------------------------
# Qt Platform Configuration
# ---------------------------------------------------------------------------
# For headless CI environments (GitHub Actions), ensure Qt uses offscreen rendering.
# This must be set BEFORE any Qt imports to take effect.
if "QT_QPA_PLATFORM" not in os.environ:
    # Try to detect if we have a display; if not, use offscreen
    has_display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not has_display and sys.platform != "win32":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    # On Windows CI, offscreen is set explicitly in the workflow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Ensure a QApplication exists for all tests with proper cleanup.

    This fixture is auto-used by pytestqt; providing it explicitly ensures
    we control initialization, avoid race conditions during test startup,
    and properly tear down Qt after all tests complete.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    yield app  # Tests run here

    # Cleanup after all tests complete
    # Process any remaining events in the Qt event loop
    QCoreApplication.processEvents()
    # Quit the application to release resources and allow pytest to exit
    app.quit()


@pytest.fixture(scope="session", autouse=True)
def _drain_leaked_service_executors():
    """Force-stop background service executors a test left running.

    Every services.* class (ConnectivityService, FileTransferService, …) owns a
    NON-daemon ``concurrent.futures.ThreadPoolExecutor``.  The connectivity
    listener loops in ``_listen`` while ``_is_running`` is set.  Tests that start
    a listener (``svc._start()``) to assert a signal fires but never call
    ``stop()`` leak a worker thread stuck in that loop.

    At interpreter shutdown ``concurrent.futures`` installs an atexit hook that
    *joins* every executor worker — the daemon flag is irrelevant, the join is
    explicit — and a worker still spinning in the listen loop never returns.  So
    the suite prints "N passed" and then hangs forever in CI.

    This runs once after the whole session (pytest finalizers run before the
    interpreter's atexit hooks).  Clearing ``_is_running`` lets each leaked loop
    exit at its next iteration; shutting the executor down releases its workers,
    so the atexit join returns immediately and pytest exits cleanly.  Session
    scope (vs per-test) keeps the suite fast: the leaked listeners merely sleep
    on bounded mock waits (``timeout<=5s``) in the meantime — they never
    busy-spin — so there is nothing to clean up until the very end.

    ``__dict__.get`` is used rather than ``getattr`` so ``MagicMock`` instances
    don't fabricate attributes and no ``__getattr__`` side effects fire while
    scanning live objects.
    """
    yield

    import gc
    from concurrent.futures import ThreadPoolExecutor

    for obj in gc.get_objects():
        d = getattr(obj, "__dict__", None)
        if not isinstance(d, dict):
            continue
        running = d.get("_is_running")
        if isinstance(running, threading.Event):
            running.clear()
        # Shut down every executor on the instance (BackupService owns two:
        # _executor and _slot_executor).
        for value in d.values():
            if isinstance(value, ThreadPoolExecutor):
                value.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# Torch stub — must run BEFORE FileDetection is added to sys.path
# ---------------------------------------------------------------------------
# image_classifer.py has `import torch` at module level.  On the desktop CI
# runner torch is not installed (only the FileDetection job installs it).
# Installing stubs here prevents an ImportError during test collection for
# test_backup.py and test_phone_request.py (which both import BackupService →
# classifer → image_classifer → torch).
#
# The stub only activates when torch is absent; machines with a real torch
# installation are unaffected.
#
# nn.Module must be a *real* Python class — not a MagicMock — because
# `class ImageClassifier(nn.Module)` is evaluated at class-definition time and
# Python's metaclass machinery raises TypeError for non-type bases.


def _ensure_torch_stub() -> None:
    if "torch" in sys.modules:
        return  # real torch (or a prior stub) already present

    from unittest.mock import MagicMock

    class _FakeNNModule:
        """Minimal nn.Module stand-in so ImageClassifier can be defined."""

        def __init__(self, *args, **kwargs) -> None:
            super().__init__()

        def to(self, device: object) -> "_FakeNNModule":
            return self

        def parameters(self):  # noqa: ANN201
            return iter([])

        def train(self, mode: bool = True) -> "_FakeNNModule":
            return self

        def eval(self) -> "_FakeNNModule":
            return self

    nn_stub = MagicMock()
    nn_stub.Module = _FakeNNModule

    torch_stub = MagicMock()
    torch_stub.nn = nn_stub
    torch_stub.device = MagicMock(return_value="cpu")
    torch_stub.cuda.is_available = MagicMock(return_value=False)

    sys.modules["torch"] = torch_stub
    sys.modules["torch.nn"] = nn_stub
    sys.modules["torch.nn.functional"] = MagicMock()
    sys.modules["torch.utils"] = MagicMock()
    sys.modules["torch.utils.data"] = MagicMock()
    sys.modules["torchvision"] = MagicMock()
    sys.modules["torchvision.models"] = MagicMock()
    sys.modules["torchvision.transforms"] = MagicMock()


_ensure_torch_stub()

# ---------------------------------------------------------------------------
# FileDetection sys.path injection
# ---------------------------------------------------------------------------
# BackupService (and its tests) import from classifer, image_classifer, etc.
# which live in FileDetection/ at the project root — two levels above
# desktop/tests/.  Inserting it here applies to every test collected under
# desktop/tests/ regardless of which subdirectory they live in.
_FILE_DETECTION_DIR = Path(__file__).resolve().parents[2] / "FileDetection"
if str(_FILE_DETECTION_DIR) not in sys.path:
    sys.path.insert(0, str(_FILE_DETECTION_DIR))

