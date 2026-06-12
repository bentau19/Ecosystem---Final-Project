from __future__ import annotations

from pathlib import Path

from checkers.registry import get_checker


def is_corrupt(file_path: Path) -> bool:
    """Check whether a file appears structurally corrupt.

    Runs two checks in order:

    1. Universal — empty file or unreadable path.
    2. Format — deep structural validation for registered file types
       (images via Pillow, ZIP containers via CRC check, PDF via header +
       EOF marker). Files whose extension is not in the registry pass this
       stage by default.

    Designed to be extended later with an ML-based content check (torch) as
    a third stage without changing the public interface.

    Args:
        file_path: Path to the file to inspect.

    Returns:
        True if the file is (likely) corrupt, False if it passes all
        applicable structural checks.
    """
    if _is_empty_or_unreadable(file_path):
        return True

    checker = get_checker(file_path.suffix.lower())
    if checker is not None:
        return checker(file_path)

    return False


def _is_empty_or_unreadable(file_path: Path) -> bool:
    # A zero-byte file is always considered corrupt — no valid format
    # produces an empty file. Returns True if the file is empty or an
    # OS-level error occurs while stat-ing it.
    try:
        return file_path.stat().st_size == 0
    except OSError:
        return True
