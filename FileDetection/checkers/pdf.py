from pathlib import Path

_PDF_HEADER: bytes = b"%PDF-"
_PDF_EOF_MARKER: bytes = b"%%EOF"

# How many bytes to read from the end of the file when scanning for %%EOF.
# The marker is always near the end; 1 KB is generous.
_EOF_SCAN_SIZE: int = 1024


def check_pdf(file_path: Path) -> bool:
    """Check whether a PDF file is structurally corrupt.

    Performs two lightweight checks without loading the full document into
    memory:

    1. Header check — the file must start with ``%PDF-`` (PDF spec §7.5.2).
    2. EOF check — the file must contain ``%%EOF`` in its final 1 KB, which
       marks the end of the cross-reference table (PDF spec §7.5.5).

    These two markers bracket a valid PDF. A file missing either is either
    not a PDF at all, or has had its tail truncated during transfer.

    Args:
        file_path: Path to the PDF file to inspect.

    Returns:
        True if the PDF header or EOF marker is missing (file is corrupt),
        False if both structural markers are present.
    """
    try:
        with open(file_path, "rb") as f:
            header: bytes = f.read(len(_PDF_HEADER))
            if header != _PDF_HEADER:
                return True

            # Seek to the last _EOF_SCAN_SIZE bytes to locate %%EOF
            f.seek(0, 2)
            file_size: int = f.tell()
            seek_offset: int = max(0, file_size - _EOF_SCAN_SIZE)
            f.seek(seek_offset)
            tail: bytes = f.read()

        return _PDF_EOF_MARKER not in tail

    except OSError:
        return True
