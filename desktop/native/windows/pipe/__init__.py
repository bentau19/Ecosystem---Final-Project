"""
Named-pipe package.

Exposes ``Client`` (``ClientNamedPipe``) and ``Server`` (``ServerNamedPipe``)
from the compiled ``pipe_module`` C extension.

PyInstaller note
----------------
When frozen, packages loaded from the PYZ archive have a synthetic
``__path__`` pointing into the archive, not the real filesystem.  Relative
imports from a frozen sub-package therefore cannot locate ``.pyd`` extension
modules that live on disk.  The frozen branch sidesteps this by adding the
concrete on-disk directory to ``sys.path`` so Python's built-in importer can
load the ``.pyd`` by its bare name, bypassing the broken PYZ ``__path__``.
"""

import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller frozen environment ----------------------------------------
    # _MEIPASS is the unpacked bundle directory (_internal/).
    # pipe_module.pyd lives at: _MEIPASS/native/windows/pipe/
    _pipe_dir: str = os.path.join(sys._MEIPASS, "native", "windows", "pipe")
    if _pipe_dir not in sys.path:
        sys.path.insert(0, _pipe_dir)
    from pipe_module import ClientNamedPipe as Client, ServerNamedPipe as Server  # type: ignore[import]
else:
    # Development environment -----------------------------------------------
    # Python 3.8+ no longer searches the package directory for dependent DLLs.
    # Register it explicitly so libgcc/libstdc++ next to the .pyd are found.
    _pipe_dir: str = os.path.dirname(os.path.abspath(__file__))
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(_pipe_dir)
    from .pipe_module import ClientNamedPipe as Client, ServerNamedPipe as Server

__all__ = ["Client", "Server"]
