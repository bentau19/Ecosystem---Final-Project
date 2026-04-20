from PySide6.QtWidgets import QFrame

from resources.paths import Styles
from utils.styles import load_stylesheet


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

    def _setup_ui(self) -> None:
        """Configure the divider's basic properties.
        
        Sets the frame shape to a horizontal line and fixes the height to 1 pixel.
        """
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)

    def _setup_style(self) -> None:
        """Load and apply QSS styling to the divider.
        
        Reads the divider.styles file, replaces the BORDER color placeholder
        with the actual color value from the Colors class, and applies the stylesheet.
        """

        qss: str = load_stylesheet(Styles.DIVIDER)

        self.setStyleSheet(qss)
