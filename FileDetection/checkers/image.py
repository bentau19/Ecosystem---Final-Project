"""
Structural corruption checker for image files.

Uses Pillow to fully decode the image into memory. Any format-level error —
truncated data, invalid headers, broken chunk structure — will raise an
exception that is caught and reported as corruption.
"""

from pathlib import Path

from PIL import Image, ImageFile, UnidentifiedImageError


def check_image(file_path: Path) -> bool:
    """
    Returns True if the image file is structurally corrupt.

    Forces a full pixel-level decode via ``img.load()``, which catches:
    - Truncated files (data ends before the image is complete)
    - Invalid or unrecognized format headers
    - Broken chunk/segment structure (e.g. bad JPEG markers, bad PNG CRCs)

    ``LOAD_TRUNCATED_IMAGES`` is explicitly set to False so that Pillow raises
    on truncation instead of silently padding with gray pixels.

    Args:
        file_path: Path to the image file to inspect.

    Returns:
        True  → image is corrupt (Pillow raised during decode).
        False → image decoded successfully.
    """
    original_truncated_setting: bool = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False

    try:
        with Image.open(file_path) as img:
            img.load()
        return False
    except (UnidentifiedImageError, OSError, SyntaxError):
        return True
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = original_truncated_setting
