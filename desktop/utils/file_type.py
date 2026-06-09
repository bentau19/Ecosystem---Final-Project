"""File-type classification helpers.

Pure Python — no Qt dependency — so these can be safely imported from any
layer (services, viewmodels, views) without creating cross-layer violations.
"""
from __future__ import annotations

# ── Extension sets ─────────────────────────────────────────────────────────────

IMAGE_EXTS: frozenset[str] = frozenset({
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "tiff", "tif", "heic", "heif", "ico",
})
VIDEO_EXTS: frozenset[str] = frozenset({
    "mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "m4v",
})
AUDIO_EXTS: frozenset[str] = frozenset({
    "mp3", "wav", "flac", "aac", "ogg", "wma", "m4a",
})
DOC_EXTS: frozenset[str] = frozenset({
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv",
})
ARCHIVE_EXTS: frozenset[str] = frozenset({
    "zip", "rar", "7z", "tar", "gz", "bz2",
})


# ── Classifiers ────────────────────────────────────────────────────────────────

def file_ext(name: str) -> str:
    """Return the lowercase extension of *name*, or ``""`` if there is none.

    Args:
        name: Filename or path whose extension is to be extracted.

    Returns:
        Lowercase extension without the leading dot (e.g. ``"jpg"``), or
        ``""`` for names that have no dot.
    """
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_image(name: str) -> bool:
    """Return ``True`` if *name* has a recognised image extension.

    Args:
        name: Filename to test.
    """
    return file_ext(name) in IMAGE_EXTS


def file_emoji(name: str) -> str:
    """Return a Unicode emoji representing the file type of *name*.

    Args:
        name: Filename whose type should be represented.

    Returns:
        A single emoji character (e.g. ``"🖼"`` for images, ``"🎬"`` for
        video).  Falls back to ``"📁"`` for unrecognised extensions.
    """
    ext = file_ext(name)
    if ext in IMAGE_EXTS:   return "🖼"
    if ext in VIDEO_EXTS:   return "🎬"
    if ext in AUDIO_EXTS:   return "🎵"
    if ext in DOC_EXTS:     return "📄"
    if ext in ARCHIVE_EXTS: return "📦"
    return "📁"


# ── Formatters ─────────────────────────────────────────────────────────────────

def fmt_size(size_bytes: int) -> str:
    """Return a concise human-readable byte-size string.

    Args:
        size_bytes: File size in bytes.

    Returns:
        Formatted string such as ``"2.3 MB"`` or ``"512 B"``.
    """
    if size_bytes < 1_024:
        return f"{size_bytes} B"
    if size_bytes < 1_024 ** 2:
        return f"{size_bytes / 1_024:.1f} KB"
    if size_bytes < 1_024 ** 3:
        return f"{size_bytes / 1_024 ** 2:.1f} MB"
    return f"{size_bytes / 1_024 ** 3:.1f} GB"
