from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame

from resources.colors import Colors

_USAGE_RATIO = 0.50


class StorageCard(QWidget):
    """A card widget that displays storage usage information with a visual progress bar.
    
    This widget shows storage information including an icon, title, usage values,
    a progress bar with gradient fill, and usage percentage. It's styled with a
    card appearance and dynamically adjusts the progress bar width on resize.
    
    Args:
        parent (Optional[QWidget]): Parent widget, defaults to None
    """

    def __init__(self, parent=None):
        """Initialize the StorageCard widget.
        
        Creates all child widgets, sets up the layout, and applies styling.
        
        Args:
            parent (Optional[QWidget]): Parent widget, defaults to None
        """
        super().__init__(parent)
        self._setup_ui()

    # ── Setup ────────────────────────────────────────────────────────────────

    def _create_widgets(self) -> None:
        """Create all child widgets for the storage card.
        
        Instantiates the icon label, title label, value label, progress bar
        background, progress bar fill, and sub-label components.
        """
        self._icon_label = self._create_icon_label()
        self._title_label = self._create_title_label()
        self._value_label = self._create_value_label()
        self._bar_bg = self._create_bar_bg()
        self._bar_fill = self._create_bar_fill()
        self._sub_label = self._create_sub_label()

    def _create_layout(self) -> None:
        """Create and configure the vertical layout for the storage card.
        
        Sets up a QVBoxLayout with specific margins and spacing, then adds
        all child widgets in the correct order with appropriate spacing.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)
        layout.addWidget(self._icon_label)
        layout.addSpacing(6)
        layout.addWidget(self._title_label)
        layout.addWidget(self._value_label)
        layout.addSpacing(4)
        layout.addWidget(self._bar_bg)
        layout.addSpacing(2)
        layout.addWidget(self._sub_label)
        layout.addStretch()

    def _apply_style(self) -> None:
        """Apply card styling to the storage card.
        
        Sets the background, border, and border-radius to create a card appearance
        using the application's color scheme.
        """
        self.setStyleSheet(f"""
            StorageCard {{
                background: {Colors.SIDEBAR_BACKGROUND};
                border: 1px solid {Colors.BORDER};
                border-radius: 14px;
            }}
        """)

    # ── Widgets ──────────────────────────────────────────────────────────────

    @staticmethod
    def _create_icon_label() -> QLabel:
        """Create the storage icon label.
        
        Returns:
            QLabel: A label with disk emoji icon, 30x30 size, centered alignment,
                   and purple background with rounded corners
        """
        label = QLabel("💾")
        label.setFixedSize(30, 30)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "background: rgba(123,97,255,0.1);"
            "border-radius: 8px;"
            "font-size: 14px;"
        )
        return label

    @staticmethod
    def _create_title_label() -> QLabel:
        """Create the title label for the storage card.
        
        Returns:
            QLabel: A label displaying "STORAGE" with muted color, small font,
                   increased letter spacing, and transparent background
        """
        label = QLabel("STORAGE")
        label.setStyleSheet(
            f"color: {Colors.MUTED};"
            f"font-size: 10px;"
            f"font-weight: 600;"
            f"letter-spacing: 1.5px;"
            f"background: transparent;"
        )
        return label

    @staticmethod
    def _create_value_label() -> QLabel:
        """Create the storage usage value label.
        
        Returns:
            QLabel: A label displaying "128 / 256 GB" with text color,
                   larger font, bold weight, and transparent background
        """
        label = QLabel("128 / 256 GB")
        label.setStyleSheet(
            f"color: {Colors.TEXT};"
            f"font-size: 16px;"
            f"font-weight: 700;"
            f"background: transparent;"
        )
        return label

    @staticmethod
    def _create_bar_bg() -> QFrame:
        """Create the background frame for the progress bar.
        
        Returns:
            QFrame: A 6px high frame with surface color background and rounded corners
        """
        frame = QFrame()
        frame.setFixedHeight(6)
        frame.setStyleSheet(
            f"background: {Colors.SURFACE2};"
            f"border-radius: 3px;"
        )
        return frame

    def _create_bar_fill(self) -> QFrame:
        """Create the fill frame for the progress bar.
        
        Returns:
            QFrame: A 6px high frame with gradient background, rounded corners,
                   initially 0 width, parented to the background frame
        """
        frame = QFrame(self._bar_bg)
        frame.setFixedHeight(6)
        frame.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f"  stop:0 {Colors.ACCENT2}, stop:1 #a78bfa);"
            f"border-radius: 3px;"
        )
        frame.setFixedWidth(0)
        return frame

    @staticmethod
    def _create_sub_label() -> QLabel:
        """Create the usage percentage sub-label.
        
        Returns:
            QLabel: A label displaying "50% used" with muted color and small font
        """
        label = QLabel("50% used")
        label.setStyleSheet(
            f"color: {Colors.MUTED};"
            f"font-size: 11px;"
            f"background: transparent;"
        )
        return label

    # ── Events ───────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        """Handle resize events to update the progress bar width.
        
        Adjusts the fill bar width based on the current background bar width
        and the usage ratio to maintain proper progress visualization.
        
        Args:
            event: The resize event
        """
        super().resizeEvent(event)
        self._bar_fill.setFixedWidth(int(self._bar_bg.width() * _USAGE_RATIO))


    def _setup_ui(self):
        self._create_widgets()
        self._create_layout()

        self.setObjectName("batteryCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        # self._load_style()
        self._apply_style()