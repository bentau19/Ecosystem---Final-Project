from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt, QModelIndex, QObject, QRect, QRectF, QSize
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from domain.enums.backup_status import BackupStatus
from resources.spacing import Spacing
from utils.file_type import file_emoji, fmt_size
from views.widgets.backup.backup_progress_model import (
    ProgressColors,
    BytesDoneRole, NameRole, ROW_ICON_SIZE, SizeRole, SpeedRole, StatusRole, ThumbRole,
)

# ── Layout constants (delegate-internal) ─────────────────────────────────────
_ROW_HEIGHT:      Final[int] = 76
_STATUS_BADGE_W:  Final[int] = 90
_STATUS_BADGE_H:  Final[int] = 22
_ROW_RADIUS:      Final[int] = 8
_BAR_H:           Final[int] = 7


# ── Formatters ─────────────────────────────────────────────────────────────────
# Also imported by BackupProgressWindow for its ETA/elapsed labels.

def fmt_speed_eta(speed_bps: float, remaining_bytes: int) -> str:
    if speed_bps <= 0:
        return ""
    speed_str = fmt_size(int(speed_bps)) + "/s"
    secs = remaining_bytes / speed_bps
    if secs < 60:
        eta = f"{int(secs)}s left"
    elif secs < 3600:
        eta = f"{int(secs / 60)}m left"
    else:
        eta = f"{secs / 3600:.1f}h left"
    return f"{speed_str}  ·  {eta}"


def fmt_elapsed(secs: int) -> str:
    if secs < 60:
        return f"{secs}s elapsed"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s elapsed"
    return f"{secs // 3600}h {(secs % 3600) // 60}m elapsed"


def fmt_eta(secs: float) -> str:
    s = int(secs)
    if s < 60:
        return f"~{s}s left"
    if s < 3600:
        return f"~{s // 60}m left"
    return f"~{secs / 3600:.1f}h left"


def badge_text(status: BackupStatus) -> str:
    return {
        BackupStatus.QUEUED:  "Queued",
        BackupStatus.ACTIVE:  "● Syncing",
        BackupStatus.DONE:    "✓  Done",
        BackupStatus.FAILED:  "✗  Failed",
        BackupStatus.SKIPPED: "—  Removed",
    }[status]


# ── Delegate ──────────────────────────────────────────────────────────────────

class BackupProgressDelegate(QStyledItemDelegate):
    """Paints a single file progress row.

    Renders: icon/thumbnail · filename + size · (if ACTIVE: progress bar +
    speed/ETA) · status badge.  No interactive controls — purely informational.
    """

    def __init__(self, colors: ProgressColors, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._c = colors
        self._name_font = QFont()
        self._name_font.setPixelSize(13)
        self._name_font.setWeight(QFont.Weight.DemiBold)
        self._size_font = QFont()
        self._size_font.setPixelSize(11)
        self._speed_font = QFont()
        self._speed_font.setPixelSize(11)
        self._badge_font = QFont()
        self._badge_font.setPixelSize(11)
        self._badge_font.setWeight(QFont.Weight.DemiBold)
        self._icon_font = QFont()
        self._icon_font.setPixelSize(22)

    def update_colors(self, colors: ProgressColors) -> None:
        """Swap in new resolved color tokens (called on theme change)."""
        self._c = colors

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, _ROW_HEIGHT)

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _card_rect(option: QStyleOptionViewItem):
        return option.rect.adjusted(0, 2, 0, -2)

    @staticmethod
    def _icon_rect(card):
        cx = card.x() + Spacing.MD
        cy = card.y() + (card.height() - ROW_ICON_SIZE) // 2
        return QRect(cx, cy, ROW_ICON_SIZE, ROW_ICON_SIZE)

    @staticmethod
    def _badge_rect(card):
        bx = card.right() - Spacing.MD - _STATUS_BADGE_W
        by = card.y() + (card.height() - _STATUS_BADGE_H) // 2
        return QRect(bx, by, _STATUS_BADGE_W, _STATUS_BADGE_H)

    # ── paint ─────────────────────────────────────────────────────────────────

    def paint(
            self,
            painter: QPainter,
            option: QStyleOptionViewItem,
            index: QModelIndex,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        c = self._c
        name: str             = index.data(NameRole)      or ""
        size_bytes: int       = index.data(SizeRole)       or 0
        bytes_done: int       = index.data(BytesDoneRole)  or 0
        speed_bps: float      = index.data(SpeedRole)      or 0.0
        status: BackupStatus  = index.data(StatusRole)     or BackupStatus.QUEUED
        thumb: QPixmap | None = index.data(ThumbRole)

        card    = self._card_rect(option)
        icon_r  = self._icon_rect(card)
        badge_r = self._badge_rect(card)
        is_active = (status == BackupStatus.ACTIVE)

        # ── Row background + border ───────────────────────────────────────────
        if status == BackupStatus.ACTIVE:
            bg, border = c.row_active_bg, c.row_active_border
        elif status == BackupStatus.DONE:
            bg, border = c.done_bg, c.done_text
        elif status == BackupStatus.FAILED:
            bg, border = c.failed_bg, c.failed_text
        elif status == BackupStatus.SKIPPED:
            bg, border = c.skipped_bg, c.skipped_text
        else:
            bg, border = c.row_bg, c.row_border

        row_path = QPainterPath()
        row_path.addRoundedRect(
            float(card.x()), float(card.y()),
            float(card.width()), float(card.height()),
            _ROW_RADIUS, _ROW_RADIUS,
        )
        painter.fillPath(row_path, QColor(bg))
        painter.setPen(QPen(QColor(border), 1))
        painter.drawPath(row_path)

        # ── Icon / thumbnail ──────────────────────────────────────────────────
        if thumb is not None:
            painter.drawPixmap(icon_r, thumb)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setFont(self._icon_font)
            painter.setPen(QColor(c.text_primary))
            painter.drawText(icon_r, Qt.AlignmentFlag.AlignCenter, file_emoji(name))

        # ── Info column geometry ──────────────────────────────────────────────
        info_left  = icon_r.right() + Spacing.MD
        info_right = badge_r.x() - Spacing.MD
        info_w     = info_right - info_left

        fm_name  = QFontMetrics(self._name_font)
        fm_size  = QFontMetrics(self._size_font)
        fm_speed = QFontMetrics(self._speed_font)

        name_h  = fm_name.height()
        size_h  = fm_size.height()
        speed_h = fm_speed.height()
        gap     = Spacing.XS

        active_extra = (gap + _BAR_H + gap + speed_h) if is_active else 0
        block_h      = name_h + active_extra
        content_top  = card.y() + (card.height() - block_h) // 2

        # ── Top line: filename (left) + size (right) ──────────────────────────
        size_text = fmt_size(size_bytes)
        size_w    = fm_size.horizontalAdvance(size_text) + 4
        name_w    = info_w - size_w - Spacing.SM

        elided = fm_name.elidedText(name, Qt.TextElideMode.ElideRight, name_w)
        painter.setPen(QColor(c.text_primary))
        painter.setFont(self._name_font)
        painter.drawText(
            QRect(info_left, content_top, name_w, name_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        painter.setPen(QColor(c.text_secondary))
        painter.setFont(self._size_font)
        painter.drawText(
            QRect(info_right - size_w, content_top, size_w, size_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            size_text,
        )

        # ── Active-only: progress bar + speed/ETA ────────────────────────────
        if is_active:
            bar_top  = content_top + name_h + gap
            bar_rect = QRect(info_left, bar_top, info_w, _BAR_H)

            track_path = QPainterPath()
            track_path.addRoundedRect(QRectF(bar_rect), 3, 3)
            painter.fillPath(track_path, QColor(c.progress_track))

            pct    = bytes_done / size_bytes if size_bytes else 0
            fill_w = int(info_w * pct)
            if fill_w > 0:
                grad = QLinearGradient(info_left, 0, info_left + fill_w, 0)
                grad.setColorAt(0, QColor(c.progress_fill))
                grad.setColorAt(1, QColor(c.progress_fill_end))
                fill_path = QPainterPath()
                fill_path.addRoundedRect(
                    QRectF(info_left, bar_top, fill_w, _BAR_H), 3, 3
                )
                painter.fillPath(fill_path, grad)

            remaining  = max(0, size_bytes - bytes_done)
            speed_text = fmt_speed_eta(speed_bps, remaining)
            if speed_text:
                speed_top = bar_top + _BAR_H + gap
                painter.setPen(QColor(c.active_text))
                painter.setFont(self._speed_font)
                painter.drawText(
                    QRect(info_left, speed_top, info_w, speed_h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    speed_text,
                )

        # ── Status badge ──────────────────────────────────────────────────────
        if status == BackupStatus.QUEUED:
            badge_bg, badge_border, badge_fg = "transparent", c.row_border, c.queued_text
        elif status == BackupStatus.ACTIVE:
            badge_bg, badge_border, badge_fg = c.active_bg, c.row_active_border, c.active_text
        elif status == BackupStatus.DONE:
            badge_bg, badge_border, badge_fg = c.done_bg, c.done_text, c.done_text
        elif status == BackupStatus.SKIPPED:
            badge_bg, badge_border, badge_fg = c.skipped_bg, c.skipped_text, c.skipped_text
        else:  # FAILED
            badge_bg, badge_border, badge_fg = c.failed_bg, c.failed_text, c.failed_text

        badge_path = QPainterPath()
        badge_path.addRoundedRect(QRectF(badge_r), 4, 4)
        if badge_bg != "transparent":
            painter.fillPath(badge_path, QColor(badge_bg))
        painter.setPen(QPen(QColor(badge_border), 1))
        painter.drawPath(badge_path)

        painter.setPen(QColor(badge_fg))
        painter.setFont(self._badge_font)
        painter.drawText(badge_r, Qt.AlignmentFlag.AlignCenter, badge_text(status))

        painter.restore()
