"""
Structural corruption checker for ZIP-based file formats.

Covers any format that uses a ZIP container: .zip, .docx, .xlsx, .pptx,
.odt, .ods, .odp, .apk, .jar, .epub.

Uses the standard library ``zipfile.ZipFile.testzip()`` which reads every
compressed entry, decompresses it fully, and verifies its CRC-32 checksum.
"""

import zipfile
from pathlib import Path


def check_zip(file_path: Path) -> bool:
    """
    Returns True if the ZIP-based file is structurally corrupt.

    ``zipfile.testzip()`` decompresses each entry and checks CRC-32. It
    returns the name of the first bad entry, or None if all entries are
    intact. A ``BadZipFile`` exception means the central directory itself
    is unreadable (e.g. the file is truncated or completely malformed).

    Args:
        file_path: Path to the ZIP-based file to inspect.

    Returns:
        True  → file is corrupt (bad CRC, truncated, or unreadable container).
        False → all entries passed CRC verification.
    """
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            first_bad: str | None = zf.testzip()
            return first_bad is not None
    except zipfile.BadZipFile:
        return True
    except Exception:
        return True
