from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize
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
    """Load an image at *size* × *size* resolution with centre-crop.

    Uses :class:`QImageReader` scaled-size hint for memory efficiency.

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
    hint = QSize(size * 2, size * 2)
    reader.setScaledSize(
        original.scaled(hint, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
    )
    image = reader.read()
    if image.isNull():
        return None
    pixmap = QPixmap.fromImage(image)
    w, h = pixmap.width(), pixmap.height()
    if w > size or h > size:
        x = max(0, (w - size) // 2)
        y = max(0, (h - size) // 2)
        pixmap = pixmap.copy(x, y, min(w, size), min(h, size))
    pixmap = pixmap.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return make_rounded_pixmap(pixmap, radius=8)
