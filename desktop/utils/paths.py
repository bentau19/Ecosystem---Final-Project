"""Shared filesystem locations for SyncDose's JSON data files."""

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Return the directory where SyncDose stores its JSON data files.

    Frozen (PyInstaller) builds write to ``%APPDATA%\\SyncDose`` which is always
    writable without admin rights.  Source/dev runs write to ``desktop/data`` so
    the files sit next to the code and are easy to inspect.  The directory is
    created if it does not already exist.

    Returns:
        The data directory as a :class:`~pathlib.Path` (guaranteed to exist).
    """
    if getattr(sys, "frozen", False):
        directory = Path(os.environ["APPDATA"]) / "SyncDose"
    else:
        directory = Path(__file__).parent.parent / "data"
    directory.mkdir(parents=True, exist_ok=True)
    return directory
