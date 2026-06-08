"""
Shared display utilities for the backup widgets.

Centralises the file-type classification, thumbnail loading, and
size-formatting helpers that are used by both
:mod:`~views.widgets.backup.backup_progress_window` and
:mod:`~views.widgets.backup.backup_review_dialog`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QImageReader, QPainter, QPainterPath, QPixmap

# ── File-type extension sets ───────────────────────────────────────────────────

IMAGE_EXTS: frozenset[str] = frozenset({
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "tiff", "tif", "heic", "heif", "ico",
})
VIDEO_EXTS:   frozenset[str] = frozenset({"mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "m4v"})
AUDIO_EXTS:   frozenset[str] = frozenset({"mp3", "wav", "flac", "aac", "ogg", "wma", "m4a"})
DOC_EXTS:     frozenset[str] = frozenset({"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv"})
ARCHIVE_EXTS: frozenset[str] = frozenset({"zip", "rar", "7z", "tar", "gz", "bz2"})


def file_ext(name: str) -> str:
    """Return the lowercase extension of *name*, or ``""`` if none."""
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_image(name: str) -> bool:
    """Return ``True`` if *name* has a recognised image extension."""
    return file_ext(name) in IMAGE_EXTS


def file_emoji(name: str) -> str:
    """Return a Unicode emoji representing the file type of *name*."""
    ext = file_ext(name)
    if ext in IMAGE_EXTS:   return "🖼"
    if ext in VIDEO_EXTS:   return "🎬"
    if ext in AUDIO_EXTS:   return "🎵"
    if ext in DOC_EXTS:     return "📄"
    if ext in ARCHIVE_EXTS: return "📦"
    return "📁"


# ── Formatting helpers ─────────────────────────────────────────────────────────

def fmt_size(size_bytes: int) -> str:
    """Return a concise human-readable byte-size string (e.g. ``"2.3 MB"``)."""
    if size_bytes < 1_024:       return f"{size_bytes} B"
    if size_bytes < 1_024 ** 2:  return f"{size_bytes / 1_024:.1f} KB"
    if size_bytes < 1_024 ** 3:  return f"{size_bytes / 1_024 ** 2:.1f} MB"
    return f"{size_bytes / 1_024 ** 3:.1f} GB"


# ── Thumbnail helpers ──────────────────────────────────────────────────────────

def make_rounded_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    """Clip *pixmap* to a rounded rectangle, preserving transparency."""
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
    Returns ``None`` if the file is missing, corrupt, or an unsupported format.
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
