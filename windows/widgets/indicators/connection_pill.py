from typing import Final

from PySide6.QtCore import Qt, QFile, QTextStream
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from resources.colors import Colors
from resources.resources import Resources
from resources.strings import Strings
from utils.styles import load_stylesheet
from widgets.indicators.pulsing_dot import PulsingDot


class ConnectionPill(QWidget):
    """A pill-shaped widget that displays connection status with a visual indicator.
    
    This widget shows connection information with a pulsing dot indicator and
    connection type text. It's styled using QSS and displays connection status
    in a compact horizontal pill format.
    
    Args:
        parent (Optional[QWidget]): Parent widget, defaults to None
    """

    _MARGIN_LEFT: Final[int] = 12
    _MARGIN_RIGHT: Final[int] = 8
    _MARGIN_TOP: Final[int] = 12
    _MARGIN_BOTTOM: Final[int] = 8
    _SPACING: Final[int] = 8

    _CONNECTION_PILL_LABEL_OBJECT_NAME: Final[str] = "label"

    def __init__(self, parent=None):
        """Initialize the ConnectionPill widget.
        
        Creates all child widgets, sets up the layout, and applies styling.
        
        Args:
            parent (Optional[QWidget]): Parent widget, defaults to None
        """
        super().__init__(parent)

        self._create_widgets()
        self._create_layout()
        self._load_style()

    def _create_widgets(self):
        """Create all child widgets for the connection pill.
        
        Instantiates the pulsing dot indicator and connection type label.
        """
        self._pulsing_dot: PulsingDot = self._create_pulsing_dot()
        self._connection_type_label: QLabel = self._create_connection_type_label()

    @staticmethod
    def _create_pulsing_dot() -> PulsingDot:
        """Create the pulsing dot indicator.
        
        Returns:
            PulsingDot: A pulsing dot widget to indicate active connection
        """
        dot = PulsingDot()
        return dot

    def _create_connection_type_label(self) -> QLabel:
        """Create the connection type label.
        
        Returns:
            QLabel: A label displaying "Connected via USB" with object name "label"
        """

        label = QLabel(Strings.CONNECTED_USB)
        label.setObjectName(self._CONNECTION_PILL_LABEL_OBJECT_NAME)
        return label

    def _create_layout(self):
        """Create and configure the horizontal layout for the connection pill.
        
        Sets up a QHBoxLayout with specific margins and spacing, then adds
        the pulsing dot and connection label with a stretch at the end.
        """

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(
            self._MARGIN_LEFT, self._MARGIN_TOP, self._MARGIN_RIGHT, self._MARGIN_BOTTOM
        )
        layout.setSpacing(self._SPACING)

        layout.addWidget(self._pulsing_dot)

        layout.addWidget(self._connection_type_label)

        layout.addStretch()

    def _load_style(self) -> None:
        """Load and apply QSS styling to the connection pill.
        
        Reads the connection_pill.styles file, replaces the GREEN color placeholder
        with the actual color value from the Colors class, and applies the stylesheet.
        """
        qss: str = load_stylesheet(Resources.CONNECTION_PILL_QSS_PATH)
        self.setStyleSheet(qss)
