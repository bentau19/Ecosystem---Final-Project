from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QRectF, QRunnable, QSize, Signal
from PySide6.QtGui import QImageReader, QPainter, QPainterPath, QPixmap

# Re-export the pure helpers so existing imports of the form
#   ``from views.widgets.backup.helpers import IMAGE_EXTS, file_ext, …``
# continue to work without change.
from utils.file_type import (  # noqa: F401
    ARCHIVE_EXTS,
    AUDIO_EXTS,
    DOC_EXTS,
    IMAGE_EXTS,
    VIDEO_EXTS,
    file_emoji,
    file_ext,
    fmt_size,
    is_image,
)

# ── Thumbnail helpers ──────────────────────────────────────────────────────────
# Qt-bound display helpers for the backup widgets: thumbnail loading and
# rounded-pixmap utilities that require PySide6. Pure file-type helpers
# (extension sets, classifiers, formatters) live in utils.file_type so they
# can be imported by any layer without creating a cross-layer dependency.

def make_rounded_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    """Clip *pixmap* to a rounded rectangle, preserving transparency.

    Args:
        pixmap: Source pixmap to clip.
        radius: Corner radius, in pixels.

    Returns:
        A new pixmap the same size as *pixmap*, with its corners clipped to
        a rounded rectangle and the rest filled transparently.
    """
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(result.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


def load_thumb(path: str, size: int) -> QPixmap | None:
    """Load an image at *size* × *size* resolution with fit-letterbox.

    Scales the image to fit entirely within a *size* × *size* square
    (preserving aspect ratio), then centres it on a transparent canvas of
    that size.  No content is ever cropped; transparent padding shows through
    as the card background colour.  Uses :class:`QImageReader` scaled-size
    hint for memory efficiency.

    Args:
        path: Filesystem path to the image file.
        size: Target width and height, in pixels, of the square thumbnail.

    Returns:
        A square, rounded-corner thumbnail pixmap, or ``None`` if the file is
        missing, corrupt, or an unsupported format.
    """
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    original = reader.size()
    if not original.isValid():
        return None

    # Scale to FIT within (size*2 × size*2) — aspect ratio preserved, no crop.
    # The 2× oversampling keeps quality high; Qt downsamples efficiently on decode.
    hint = QSize(size * 2, size * 2)
    reader.setScaledSize(
        original.scaled(hint, Qt.AspectRatioMode.KeepAspectRatio)
    )
    image = reader.read()
    if image.isNull():
        return None

    pixmap = QPixmap.fromImage(image)
    # Final fit-scale to the exact target size (corrects any decode rounding).
    pixmap = pixmap.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    # Centre the (possibly non-square) scaled image on a size×size transparent
    # canvas so downstream drawPixmap(square_rect, thumb) never distorts it.
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.drawPixmap((size - pixmap.width()) // 2, (size - pixmap.height()) // 2, pixmap)
    p.end()

    return make_rounded_pixmap(canvas, radius=8)


# ── Async thumbnail infrastructure ─────────────────────────────────────────────
# Shared by BackupProgressModel and BackupReviewModel so the implementation
# lives in exactly one place.

class ThumbResult(QObject):
    """Carrier object that lives on the main thread and receives thumb signals."""
    ready: Signal = Signal(str, object)  # (key, QPixmap | None)


class ThumbLoader(QRunnable):
    """Loads one thumbnail on a QThreadPool worker, then signals the result.

    ``key`` is the model lookup key emitted back via ``ThumbResult.ready``; it
    may differ from ``abs_path`` (e.g. in the progress window the key is a
    relative filename while the path is absolute).  When both are the same,
    just pass the same value for both arguments.
    """

    def __init__(self, key: str, abs_path: str, size: int, result: ThumbResult) -> None:
        super().__init__()
        self._key = key
        self._abs_path = abs_path
        self._size = size
        self._result = result
        self.setAutoDelete(True)

    def run(self) -> None:
        pixmap = load_thumb(self._abs_path, self._size)
        self._result.ready.emit(self._key, pixmap)
