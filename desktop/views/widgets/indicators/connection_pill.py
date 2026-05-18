from PySide6.QtWidgets import QHBoxLayout, QLabel, QFrame, QWidget

from app.theme_manager import theme_manager
from resources.colors import Colors, LightColors
from resources.paths import IndicatorStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.indicators.pulsing_dot import PulsingDot


class ConnectionPill(QFrame):
    """A pill-shaped widget that displays connection status with a visual indicator.

    This widget shows connection information with a pulsing dot indicator and
    connection type text. It's styled using QSS and displays connection status
    in a compact horizontal pill format.

    Args:
        parent: Optional[QWidget]
            Parent widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the ConnectionPill widget.

        Creates all child widgets, sets up the layout, and applies styling.

        Args:
            parent (Optional[QWidget]): Parent widget.
        """
        super().__init__(parent)

        self._pulsing_dot: PulsingDot
        self._connection_type_label: QLabel

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        # Create child widgets and assemble the horizontal pill layout.
        self._create_widgets()
        self._create_layout()

    def _setup_style(self) -> None:
        # Load and apply the themed connection-pill stylesheet.
        qss: str = load_stylesheet(
            IndicatorStyles.CONNECTION_PILL,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Wire theme_changed to re-apply the stylesheet.
        theme_manager.theme_changed.connect(self._setup_style)

    def _create_widgets(self) -> None:
        # Instantiate the pulsing-dot indicator and the connection-type label.
        self._pulsing_dot = self._create_pulsing_dot()
        self._connection_type_label = self._create_connection_type_label()

    @staticmethod
    def _create_pulsing_dot() -> PulsingDot:
        # Return a default PulsingDot that starts its animation on construction.
        return PulsingDot()

    def _create_connection_type_label(self) -> QLabel:
        # Create the 'Connected via USB' status label.
        label: QLabel = QLabel(self.tr("Connected via USB"))
        label.setObjectName("label")
        return label

    def _create_layout(self) -> None:
        # Build the horizontal layout: dot → label → stretch.
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._pulsing_dot)
        layout.addWidget(self._connection_type_label)
        layout.addStretch()
