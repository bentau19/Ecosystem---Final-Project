from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QBrush, QPen, QPixmap, Qt, QPainterPath, QPaintEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QFrame
from typing import Optional

from resources.colors import LogoColors
from resources.paths import Icons, Styles
from resources.spacing import Spacing
from utils.styles import load_stylesheet


class LogoWidget(QFrame):
    """
    A QWidget displaying the application logo and application name.

    The widget consists of a circular logo icon and a text label with
    gradient-colored application name. Layout, margins, and spacing
    are handled internally.
    """

    def __init__(self, logo_size: int = 70, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the LogoWidget.

        Args:
            logo_size (int, optional): The size of the logo icon.
            parent (Optional[QWidget], optional): Optional parent widget.
        """
        super().__init__(parent)
        self._logo_size: int = logo_size

        self._app_name_label: LogoNameLabel
        self._logo_icon: QLabel

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize child widgets, layout, and apply stylesheet."""

        self.setObjectName("logoFrame")
        self._create_widgets()
        self._setup_layout()
        self._apply_styles()

    def _create_widgets(self) -> None:
        """Create the logo icon and application name label widgets."""
        self._app_name_label = self._create_name_label()
        self._logo_icon = self._create_logo_icon()

    def _setup_layout(self) -> None:
        """Set up a horizontal layout with margins, spacing, and stretch."""
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.LG, Spacing.SM, Spacing.LG)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._logo_icon)
        layout.addWidget(self._app_name_label)
        layout.addStretch()

    def _create_logo_icon(self) -> QLabel:
        return Logo(self._logo_size)

    @staticmethod
    def _create_name_label() -> "LogoNameLabel":
        """
        Create a label displaying the application name with gradient text.

        Returns:
            LogoNameLabel: The application name label.
        """
        label: LogoNameLabel = LogoNameLabel()
        label.setObjectName("logoText")
        return label

    def _apply_styles(self) -> None:
        """Load and apply the QSS stylesheet for this widget."""
        qss: str = load_stylesheet(Styles.LOGO_WIDGET)
        self.setStyleSheet(qss)


class LogoNameLabel(QLabel):
    """
    QLabel subclass for displaying the application name with gradient text.
    """

    def __init__(self, parent: Optional[QLabel] = None) -> None:
        """
        Initialize the gradient text label.

        Args:
            parent (Optional[QLabel], optional): Optional parent widget.
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Set the application name text."""
        self.setText(self.tr("SyncDose"))

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Paint the label text using a linear gradient.

        Args:
            event: The paint event.
        """
        super().paintEvent(event)
        painter: QPainter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gradient: QLinearGradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(LogoColors.GRADIENT_START))
        gradient.setColorAt(1.0, QColor(LogoColors.GRADIENT_END))

        painter.setPen(QPen(QBrush(gradient), 0))
        painter.setFont(self.font())
        painter.drawText(self.rect(), self.alignment(), self.text())


class Logo(QLabel):
    def __init__(self, logo_size: int = 70, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._logo_size = logo_size
        self._setup_logo()
        self._apply_style()

    def _setup_logo(self):
        pixmap: QPixmap = QPixmap(self._logo_size, self._logo_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        renderer: QSvgRenderer = QSvgRenderer(Icons.LOGO)
        painter: QPainter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Circular clipping path
        path: QPainterPath = QPainterPath()
        path.addEllipse(0, 0, self._logo_size, self._logo_size)
        painter.setClipPath(path)

        renderer.render(painter, QRectF(0, 0, self._logo_size, self._logo_size))
        painter.end()

        logo_icon: QLabel = QLabel()
        self.setPixmap(pixmap)
        self.setFixedSize(self._logo_size, self._logo_size)
        self.setObjectName("logoIcon")

    def _apply_style(self) -> None:
        """Load and apply the QSS stylesheet for this widget."""
        qss: str = load_stylesheet(Styles.LOGO_WIDGET)
        self.setStyleSheet(qss)
