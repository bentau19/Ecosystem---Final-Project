from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QFrame, QVBoxLayout,
    QHBoxLayout, QLabel, QGridLayout, QPushButton
)

from resources.colors import Colors
from widgets.cards.battery_card import BatteryCard
from widgets.cards.stat_card import StatCard
from widgets.cards.storage_card import StorageCard
from widgets.cards.tool_card import ToolCard

ToolData = Tuple[str, str, str, str, str]

TOOL_DATA: List[ToolData] = [
    ("📁", "File Transfer", "Move files, photos and documents between PC and phone instantly.", Colors.ACCENT,
     "rgba(0,229,255,0.08)"),
    ("🖥️", "Screen Mirror", "View and control your phone screen directly on your desktop.", Colors.ACCENT2,
     "rgba(123,97,255,0.08)"),
    ("🔔", "Notifications", "See all phone notifications on your PC without picking up your phone.", Colors.GREEN,
     "rgba(0,230,118,0.08)"),
    ("💬", "SMS & Calls", "Send texts and manage calls from your keyboard.", "#ffab00", "rgba(255,171,0,0.08)"),
    ("🔋", "Battery Manager", "Monitor charging status, health, and set smart charge limits.", Colors.ACCENT3,
     "rgba(255,92,135,0.08)"),
    ("📦", "App Manager", "Install, uninstall, and manage apps on your phone from your PC.", "#40c4ff",
     "rgba(64,196,255,0.08)"),
]


class MainContent(QWidget):
    """Main content widget for the dashboard page.
    
    Displays device status cards, tool cards, and navigation controls
    in a scrollable layout with proper styling and organization.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the MainContent widget.
        
        Args:
            parent: Parent widget, defaults to None
        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the main UI components and layout."""
        self.setStyleSheet(f"background: transparent;")

        scroll_area = self._create_scroll_area()
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner_widget = self._create_inner_content()

        scroll_area.setWidget(inner_widget)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll_area)

    def _create_scroll_area(self) -> QScrollArea:
        """Create and configure the scroll area.
        
        Returns:
            QScrollArea: Configured scroll area with no frame and horizontal scroll disabled
        """
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        return scroll

    def _create_inner_content(self) -> QWidget:
        """Create the inner content widget with all dashboard components.
        
        Returns:
            QWidget: Inner widget containing all dashboard content
        """
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(40, 36, 40, 40)
        layout.setSpacing(0)

        layout.addWidget(self._create_topbar())
        layout.addSpacing(28)

        layout.addWidget(self._create_device_status_row())
        layout.addSpacing(32)

        layout.addWidget(self._create_tools_section_header())
        layout.addSpacing(16)

        layout.addWidget(self._create_tools_grid())
        layout.addStretch()

        return inner

    def _create_topbar(self) -> QWidget:
        """Create the top navigation bar with title and disconnect button.
        
        Returns:
            QWidget: Topbar widget with title block and disconnect button
        """
        topbar = QWidget()
        topbar.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(0, 0, 0, 0)

        title_block = self._create_title_block()
        disconnect_btn = self._create_disconnect_button()

        layout.addWidget(title_block)
        layout.addStretch()
        layout.addWidget(disconnect_btn)

        return topbar

    def _create_title_block(self) -> QWidget:
        """Create the title block with main title and subtitle.
        
        Returns:
            QWidget: Title block with dashboard title and device info
        """
        title_block = QWidget()
        title_block.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(title_block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel("Dashboard")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 26px; font-weight: 800; background: transparent;")

        subtitle = QLabel("Samsung Galaxy S23 — Last synced just now")
        subtitle.setStyleSheet(f"color: {Colors.MUTED}; font-size: 13px; background: transparent;")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        return title_block

    def _create_disconnect_button(self) -> QPushButton:
        """Create the disconnect button with styling.
        
        Returns:
            QPushButton: Styled disconnect button
        """
        btn = QPushButton("⏏  Disconnect")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,92,135,0.12);
                color: {Colors.ACCENT3};
                border: 1px solid rgba(255,92,135,0.28);
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 18px;
            }}
            QPushButton:hover {{
                background: rgba(255,92,135,0.22);
            }}
        """)
        return btn

    def _create_device_status_row(self) -> QWidget:
        """Create the row containing device status cards.
        
        Returns:
            QWidget: Row with device, type, storage, and battery cards
        """
        stat_row = QWidget()
        stat_row.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(stat_row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(StatCard("📱", "Device", "Galaxy S23", "Samsung"))
        layout.addWidget(StatCard("🤖", "Type", "Android", "Android 13"))
        layout.addWidget(StorageCard())
        layout.addWidget(BatteryCard(89,True))

        return stat_row

    def _create_tools_section_header(self) -> QWidget:
        """Create the tools section header with title and tag.
        
        Returns:
            QWidget: Section header with title and tool count tag
        """
        header = QWidget()
        header.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Available Tools")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 17px; font-weight: 700; background: transparent;")

        tag = QLabel("6 tools available")
        tag.setStyleSheet(
            f"color: {Colors.MUTED}; font-size: 13px; background: {Colors.SURFACE2};"
            f"border: 1px solid {Colors.BORDER}; border-radius: 10px; padding: 3px 12px;"
        )

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(tag)

        return header

    def _create_tools_grid(self) -> QWidget:
        """Create the grid layout for tool cards.
        
        Returns:
            QWidget: Grid widget containing all tool cards in 3 columns
        """
        grid_widget = QWidget()
        grid_widget.setStyleSheet("background: transparent;")

        grid = QGridLayout(grid_widget)
        grid.setSpacing(14)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, (icon, name, desc, accent, icon_bg) in enumerate(TOOL_DATA):
            card = ToolCard(icon, name, desc, accent, icon_bg)
            grid.addWidget(card, i // 3, i % 3)

        return grid_widget
