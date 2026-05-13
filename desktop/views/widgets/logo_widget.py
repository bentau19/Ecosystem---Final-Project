from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QBrush, QPen, QPixmap, Qt, QPainterPath, QPaintEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QFrame

from resources.colors import LogoColors
from resources.paths import Icons, Styles
from resources.spacing import Spacing
from utils.styles import load_stylesheet


class LogoWidget(QFrame):
    """Sidebar header widget displaying the circular logo and gradient app name.

    Composed of a :class:`Logo` icon on the left and a :class:`LogoNameLabel`
    on the right, laid out horizontally with a trailing stretch.
    """

    def __init__(self, logo_size: int = 70, parent: QWidget | None = None) -> None:
        """Initialize the LogoWidget.

        Args:
            logo_size: Diameter of the circular logo icon in pixels.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._logo_size: int = logo_size

        self._app_name_label: LogoNameLabel
        self._logo_icon: QLabel

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("logoFrame")
        self._create_widgets()
        self._setup_layout()
        self._apply_styles()

    def _create_widgets(self) -> None:
        self._app_name_label = self._create_name_label()
        self._logo_icon = self._create_logo_icon()

    def _setup_layout(self) -> None:
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.LG, Spacing.SM, Spacing.LG)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._logo_icon)
        layout.addWidget(self._app_name_label)
        layout.addStretch()

    def _create_logo_icon(self) -> "Logo":
        return Logo(self._logo_size)

    @staticmethod
    def _create_name_label() -> "LogoNameLabel":
        label: LogoNameLabel = LogoNameLabel()
        label.setObjectName("logoText")
        return label

    def _apply_styles(self) -> None:
        qss: str = load_stylesheet(Styles.LOGO_WIDGET)
        self.setStyleSheet(qss)


class LogoNameLabel(QLabel):
    """QLabel subclass that paints the app name text with a linear gradient fill."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the gradient text label.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        self.setText(self.tr("SyncDose"))

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the label text using a linear gradient.

        Calls the base ``paintEvent`` first so the standard label geometry is
        established, then overlays the gradient-painted text on top.

        Args:
            event: The paint event delivered by Qt.
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
    """Circular clipped SVG logo widget.

    Renders ``Icons.LOGO`` into a square pixmap with an elliptical clip path
    so the icon appears as a circle regardless of the SVG's original shape.
    """

    def __init__(self, logo_size: int = 70, parent: QWidget | None = None) -> None:
        """Initialize the Logo widget.

        Args:
            logo_size: Width and height of the circular logo in pixels.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._logo_size: int = logo_size
        self._setup_logo()
        self._apply_style()

    def _setup_logo(self) -> None:
        # Render the SVG into a square pixmap, then clip to an ellipse so the
        # icon appears circular regardless of the SVG's original dimensions.
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

        self.setPixmap(pixmap)
        self.setFixedSize(self._logo_size, self._logo_size)
        self.setObjectName("logoIcon")

    def _apply_style(self) -> None:
        qss: str = load_stylesheet(Styles.LOGO_WIDGET)
        self.setStyleSheet(qss)
