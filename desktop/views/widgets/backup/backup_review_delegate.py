from __future__ import annotations

from datetime import datetime
from typing import Final

from PySide6.QtCore import Qt, QEvent, QModelIndex, QObject, QRect, QSize
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from resources.spacing import Spacing
from utils.file_type import fmt_size
from views.widgets.backup.backup_review_model import (
    DecisionRole, MtimeRole, NameRole, ReviewColors, SizeRole, THUMB_SIZE, ThumbRole,
)

# ── Layout constants (delegate-internal) ─────────────────────────────────────
_ROW_HEIGHT:    Final[int] = 76
_BUTTON_HEIGHT: Final[int] = 30
_BUTTON_WIDTH:  Final[int] = 88
_ROW_RADIUS:    Final[int] = 8


class BackupFileDelegate(QStyledItemDelegate):
    """Paints a single file review row: thumbnail, name, meta, Keep/Delete buttons.

    All geometry calculations are done in :meth:`paint` each frame; hit-testing
    for Keep/Delete clicks is in :meth:`editorEvent` using the same geometry.
    """

    def __init__(self, colors: ReviewColors, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._c = colors
        self._name_font = QFont()
        self._name_font.setPixelSize(13)
        self._name_font.setWeight(QFont.Weight.DemiBold)
        self._meta_font = QFont()
        self._meta_font.setPixelSize(11)
        self._btn_font = QFont()
        self._btn_font.setPixelSize(12)
        self._btn_font.setWeight(QFont.Weight.Medium)

    def update_colors(self, colors: ReviewColors) -> None:
        """Swap in a new set of resolved color tokens (called on theme change)."""
        self._c = colors

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, _ROW_HEIGHT)

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _card_rect(option: QStyleOptionViewItem):
        """Inset from option.rect to the visible card (preserves spacing gap)."""
        return option.rect.adjusted(0, 2, 0, -2)

    @staticmethod
    def _thumb_rect(card):
        cx = card.x() + Spacing.LG
        cy = card.y() + (card.height() - THUMB_SIZE) // 2
        return QRect(cx, cy, THUMB_SIZE, THUMB_SIZE)

    @staticmethod
    def _button_rects(card):
        """Return (keep_rect, delete_rect) — keep left of delete."""
        btn_y    = card.y() + (card.height() - _BUTTON_HEIGHT) // 2
        right    = card.right() - Spacing.LG
        delete_x = right - _BUTTON_WIDTH
        keep_x   = delete_x - Spacing.SM - _BUTTON_WIDTH
        return (
            QRect(keep_x,   btn_y, _BUTTON_WIDTH, _BUTTON_HEIGHT),
            QRect(delete_x, btn_y, _BUTTON_WIDTH, _BUTTON_HEIGHT),
        )

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
        decision: str         = index.data(DecisionRole) or "pending"
        name: str             = index.data(NameRole)      or ""
        size_bytes: int       = index.data(SizeRole)      or 0
        mtime: int            = index.data(MtimeRole)     or 0
        thumb: QPixmap | None = index.data(ThumbRole)

        card = self._card_rect(option)

        # ── Background ────────────────────────────────────────────────────────
        if decision == "keep":
            bg, border = c.keep_bg, c.keep_border
        elif decision == "delete":
            bg, border = c.delete_bg, c.delete_border
        else:
            hovered = bool(option.state & option.state.State_MouseOver)
            bg     = c.row_hover if hovered else c.row_bg
            border = c.keep_border if hovered and decision == "keep" else c.row_border

        path_obj = QPainterPath()
        path_obj.addRoundedRect(card.x(), card.y(), card.width(), card.height(),
                                _ROW_RADIUS, _ROW_RADIUS)
        painter.fillPath(path_obj, QColor(bg))
        painter.setPen(QPen(QColor(border), 1))
        painter.drawPath(path_obj)

        # ── Thumbnail ─────────────────────────────────────────────────────────
        thumb_r = self._thumb_rect(card)
        if thumb is not None:
            painter.drawPixmap(thumb_r, thumb)
        else:
            fb_path = QPainterPath()
            fb_path.addRoundedRect(
                thumb_r.x(), thumb_r.y(), thumb_r.width(), thumb_r.height(), 8, 8
            )
            painter.fillPath(fb_path, QColor(c.icon_bg))
            painter.setPen(QPen(QColor(c.icon_border), 1))
            painter.drawPath(fb_path)
            small_font = QFont()
            small_font.setPixelSize(8)
            small_font.setWeight(QFont.Weight.Bold)
            small_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
            painter.setPen(QColor(c.icon_text))
            painter.setFont(small_font)
            painter.drawText(thumb_r, Qt.AlignmentFlag.AlignCenter, "IMG")

        # ── Button rects ──────────────────────────────────────────────────────
        keep_r, delete_r = self._button_rects(card)

        # ── Info text ─────────────────────────────────────────────────────────
        info_left  = thumb_r.right() + Spacing.MD
        info_right = keep_r.x() - Spacing.MD
        info_w     = info_right - info_left

        fm_name = QFontMetrics(self._name_font)
        fm_meta = QFontMetrics(self._meta_font)
        name_h  = fm_name.height()
        meta_h  = fm_meta.height()
        text_top = card.y() + (card.height() - (name_h + 3 + meta_h)) // 2

        painter.setPen(QColor(c.text_primary))
        painter.setFont(self._name_font)
        elided = fm_name.elidedText(name, Qt.TextElideMode.ElideRight, info_w)
        painter.drawText(
            QRect(info_left, text_top, info_w, name_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

        date_str = (
            datetime.fromtimestamp(mtime / 1000).strftime("%b %d, %Y")
            if mtime else "—"
        )
        painter.setPen(QColor(c.text_secondary))
        painter.setFont(self._meta_font)
        painter.drawText(
            QRect(info_left, text_top + name_h + 3, info_w, meta_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{fmt_size(size_bytes)}  ·  {date_str}",
        )

        # ── Keep / Delete buttons ─────────────────────────────────────────────
        self._draw_button(
            painter, keep_r, text="✓  Keep", active=(decision == "keep"),
            active_bg=c.keep_bg, active_border=c.keep_border, active_text=c.keep_text,
            idle_border=c.row_border, idle_text=c.text_secondary,
        )
        self._draw_button(
            painter, delete_r, text="✗  Delete", active=(decision == "delete"),
            active_bg=c.delete_bg, active_border=c.delete_border, active_text=c.delete_text,
            idle_border=c.row_border, idle_text=c.text_secondary,
        )

        painter.restore()

    def _draw_button(
            self,
            painter: QPainter,
            rect,
            *,
            text: str,
            active: bool,
            active_bg: str,
            active_border: str,
            active_text: str,
            idle_border: str,
            idle_text: str,
    ) -> None:
        bg_color     = QColor(active_bg)     if active else QColor(0, 0, 0, 0)
        border_color = QColor(active_border) if active else QColor(idle_border)
        text_color   = QColor(active_text)   if active else QColor(idle_text)

        btn_path = QPainterPath()
        btn_path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()), 6, 6,
        )
        painter.fillPath(btn_path, bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawPath(btn_path)

        font = QFont(self._btn_font)
        if active:
            font.setWeight(QFont.Weight.DemiBold)
        painter.setPen(text_color)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # ── editorEvent — click handling ──────────────────────────────────────────

    def editorEvent(
            self,
            event,
            model,
            option: QStyleOptionViewItem,
            index: QModelIndex,
    ) -> bool:
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        card             = self._card_rect(option)
        keep_r, delete_r = self._button_rects(card)
        pos              = event.position().toPoint() if hasattr(event, "position") else event.pos()

        current = index.data(DecisionRole) or "pending"
        if keep_r.contains(pos):
            model.set_decision(index.row(), "pending" if current == "keep" else "keep")
            return True
        if delete_r.contains(pos):
            model.set_decision(index.row(), "pending" if current == "delete" else "delete")
            return True
        return False
