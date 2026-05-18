from PySide6.QtWidgets import QFrame

from app.theme_manager import theme_manager
from resources.colors import Colors, LightColors
from resources.paths import Styles
from utils.styles import load_stylesheet, themed


class Divider(QFrame):
    """A horizontal divider line widget for visual separation.
    
    This widget creates a simple 1-pixel high horizontal line that can be used
    to visually separate UI elements. It's styled using QSS and uses the border
    color from the application's color scheme.
    
    Args:
        parent (Optional[QWidget]): Parent widget, defaults to None
    """

    def __init__(self, parent: "QWidget | None" = None) -> None:
        """Initialize the Divider widget.
        
        Sets up the frame shape, dimensions, and applies styling.
        
        Args:
            parent (Optional[QWidget]): Parent widget, defaults to None
        """
        super().__init__(parent)
        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    def _setup_ui(self) -> None:
        # Configure as a horizontal frame line exactly 1 px tall.
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)

    def _setup_style(self) -> None:
        # Load and apply the themed divider QSS.
        qss: str = load_stylesheet(
            Styles.DIVIDER,
            themed([Colors], [LightColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        # Wire theme_changed to re-apply the stylesheet.
        theme_manager.theme_changed.connect(self._setup_style)
