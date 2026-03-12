from typing import Final

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QBrush, QPen, QPixmap, Qt, QPainterPath, QPaintEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout

from resources.colors import Colors
from resources.resources import Resources
from resources.strings import Strings
from utils.styles import load_stylesheet


class LogoWidget(QWidget):
    """
    A QWidget displaying the application logo and application name.

    The widget consists of a circular logo icon and a text label with
    gradient-colored application name. Layout, margins, and spacing
    are handled internally.
    """

    # Private constants
    _LOGO_ICON_QSS_NAME: Final[str] = "logoIcon"  # Object name used in QSS for the logo icon
    _APP_NAME_LABEL_QSS_NAME: Final[str] = "logoText"  # Object name used in QSS for the app name label
    _LOGO_SIZE: Final[int] = 70  # Diameter of the circular logo

    _MARGIN_LEFT: Final[int] = 10
    _MARGIN_RIGHT: Final[int] = 20
    _MARGIN_TOP: Final[int] = 20
    _MARGIN_BOTTOM: Final[int] = 20
    _SPACING: Final[int] = 10  # Layout spacing between logo and label

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the LogoWidget."""
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize child widgets, layout, and apply stylesheet."""
        self._create_widgets()
        self._setup_layout()
        self._apply_styles()

    def _create_widgets(self) -> None:
        """Create the logo icon and application name label widgets."""
        self._app_name_label: "LogoWidget.AppNameLabel" = self._create_name_label()
        self._logo_icon: QLabel = self._create_logo_icon()

    def _setup_layout(self) -> None:
        """Set up a horizontal layout with margins, spacing, and stretch."""
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(
            self._MARGIN_LEFT, self._MARGIN_TOP, self._MARGIN_RIGHT, self._MARGIN_BOTTOM
        )
        layout.setSpacing(self._SPACING)
        layout.addWidget(self._logo_icon)
        layout.addWidget(self._app_name_label)
        layout.addStretch()

    def _create_logo_icon(self) -> QLabel:
        """Create a QLabel displaying a circular SVG logo."""

        pixmap: QPixmap = QPixmap(self._LOGO_SIZE, self._LOGO_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        renderer: QSvgRenderer = QSvgRenderer(Resources.LOGO_ICON_PATH)
        painter: QPainter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Circular clipping path
        path: QPainterPath = QPainterPath()
        path.addEllipse(0, 0, self._LOGO_SIZE, self._LOGO_SIZE)
        painter.setClipPath(path)

        renderer.render(painter, QRectF(0, 0, self._LOGO_SIZE, self._LOGO_SIZE))
        painter.end()

        logo_icon: QLabel = QLabel()
        logo_icon.setPixmap(pixmap)
        logo_icon.setFixedSize(self._LOGO_SIZE, self._LOGO_SIZE)
        logo_icon.setObjectName(self._LOGO_ICON_QSS_NAME)
        return logo_icon

    def _create_name_label(self) -> "LogoWidget.AppNameLabel":
        """Create a label displaying the application name with gradient text."""
        label: LogoWidget.AppNameLabel = self.AppNameLabel()
        label.setObjectName(self._APP_NAME_LABEL_QSS_NAME)
        return label

    def _apply_styles(self) -> None:
        """Load and apply the QSS stylesheet for this widget."""
        qss: str = load_stylesheet(Resources.LOGO_WIDGET_QSS_PATH)
        self.setStyleSheet(qss)

    class AppNameLabel(QLabel):
        """
        QLabel subclass for displaying the application name with gradient text.
        """

        def __init__(self, parent: QLabel | None = None) -> None:
            """Initialize the gradient text label."""
            super().__init__(parent)
            self._init_ui()

        def _init_ui(self) -> None:
            """Set the application name text."""
            self.setText(Strings.APP_NAME)

        def paintEvent(self, event: QPaintEvent) -> None:
            """Paint the label text using a linear gradient."""
            super().paintEvent(event)
            painter: QPainter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            gradient: QLinearGradient = QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0.0, QColor(Colors.LOGO_TEXT_GRADIENT_1))
            gradient.setColorAt(1.0, QColor(Colors.LOGO_TEXT_GRADIENT_2))

            painter.setPen(QPen(QBrush(gradient), 0))
            painter.setFont(self.font())
            painter.drawText(self.rect(), self.alignment(), self.text())
