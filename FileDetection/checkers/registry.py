from collections.abc import Callable
from pathlib import Path

from checkers.image import check_image
from checkers.zip_based import check_zip
from checkers.pdf import check_pdf

# Dispatch table mapping file extensions to their structural corruption
# checker. Extensions not present here have no deep checker — the caller
# should treat them as structurally unverifiable (not corrupt by default).
#
# Adding support for a new format:
#   1. Implement a check_<format>(file_path: Path) -> bool function.
#   2. Import it here.
#   3. Add the extension(s) to _CHECKERS below.
_CHECKERS: dict[str, Callable[[Path], bool]] = {
    # Images — Pillow full decode
    ".jpg":  check_image,
    ".jpeg": check_image,
    ".png":  check_image,
    ".gif":  check_image,
    ".bmp":  check_image,
    ".webp": check_image,
    ".tiff": check_image,
    ".tif":  check_image,
    ".ico":  check_image,
    # ZIP-based containers — CRC-32 verification of all entries
    ".zip":  check_zip,
    ".docx": check_zip,
    ".xlsx": check_zip,
    ".pptx": check_zip,
    ".odt":  check_zip,
    ".ods":  check_zip,
    ".odp":  check_zip,
    ".epub": check_zip,
    ".apk":  check_zip,
    ".jar":  check_zip,
    # PDF — header + EOF marker
    ".pdf":  check_pdf,
}


def get_checker(extension: str) -> Callable[[Path], bool] | None:
    """Look up the structural corruption checker for a file extension.

    Args:
        extension: Lowercase file extension including the leading dot
            (e.g. ``'.jpg'``, ``'.pdf'``).

    Returns:
        A callable ``(Path) -> bool`` that returns True if the file is
        corrupt, or None if no checker is registered for this extension.
    """
    return _CHECKERS.get(extension)
