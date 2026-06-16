import threading
from pathlib import Path

from PIL import Image, ImageFile, UnidentifiedImageError

# Serialises concurrent callers so that the save-mutate-restore sequence on
# the module-level ImageFile.LOAD_TRUNCATED_IMAGES global is atomic. Without
# this, thread A's finally-block restore could overwrite thread B's intended
# setting while B is mid-decode.
_image_check_lock: threading.Lock = threading.Lock()


def check_image(file_path: Path) -> bool:
    """Check whether an image file is structurally corrupt.

    Uses Pillow to fully decode the image into memory via ``img.load()``,
    which catches:

    - Truncated files (data ends before the image is complete)
    - Invalid or unrecognized format headers
    - Broken chunk/segment structure (e.g. bad JPEG markers, bad PNG CRCs)

    Any format-level error during decode is caught and reported as
    corruption.

    Args:
        file_path: Path to the image file to inspect.

    Returns:
        True if the image is corrupt (Pillow raised during decode), False if
        it decoded successfully.
    """
    with _image_check_lock:
        # Disable truncated-image tolerance so Pillow raises on truncation
        # instead of silently padding with gray pixels.
        original: bool = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        try:
            with Image.open(file_path) as img:
                img.load()
            return False
        except (UnidentifiedImageError, OSError, SyntaxError):
            return True
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = original
