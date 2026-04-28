from PySide6.QtWidgets import QHBoxLayout, QLabel, QFrame, QWidget

from resources.paths import IndicatorStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet
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

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self._create_widgets()
        self._create_layout()

    def _setup_style(self) -> None:
        """Load and apply QSS styling to the connection pill.

        Reads the connection_pill.styles file, replaces the GREEN color placeholder
        with the actual color value from the Colors class, and applies the stylesheet.
        """
        qss: str = load_stylesheet(IndicatorStyles.CONNECTION_PILL)
        self.setStyleSheet(qss)

    def _create_widgets(self) -> None:
        """Create all child widgets for the connection pill.

        Instantiates the pulsing dot indicator and connection type label.
        """
        self._pulsing_dot = self._create_pulsing_dot()
        self._connection_type_label = self._create_connection_type_label()

    @staticmethod
    def _create_pulsing_dot() -> PulsingDot:
        """Create the pulsing dot indicator.

        Returns:
            PulsingDot: A pulsing dot widget to indicate active connection.
        """
        return PulsingDot()

    def _create_connection_type_label(self) -> QLabel:
        """Create the connection type label.

        Returns:
            QLabel: A label displaying "Connected via USB" with object name "label".
        """
        label: QLabel = QLabel(self.tr("Connected via USB"))
        label.setObjectName("label")
        return label

    def _create_layout(self) -> None:
        """Create and configure the horizontal layout for the connection pill.

        Sets up a QHBoxLayout with specific margins and spacing, then adds
        the pulsing dot and connection label with a stretch at the end.
        """
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._pulsing_dot)
        layout.addWidget(self._connection_type_label)
        layout.addStretch()
