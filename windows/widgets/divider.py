from pathlib import Path

from PySide6.QtCore import QFile, QTextStream
from PySide6.QtWidgets import QFrame

from resources.colors import Colors
from resources.resources import Resources
from utils.styles import load_stylesheet


class Divider(QFrame):
    """A horizontal divider line widget for visual separation.
    
    This widget creates a simple 1-pixel high horizontal line that can be used
    to visually separate UI elements. It's styled using QSS and uses the border
    color from the application's color scheme.
    
    Args:
        parent (Optional[QWidget]): Parent widget, defaults to None
    """

    def __init__(self, parent=None):
        """Initialize the Divider widget.
        
        Sets up the frame shape, dimensions, and applies styling.
        
        Args:
            parent (Optional[QWidget]): Parent widget, defaults to None
        """
        super().__init__(parent)
        self._setup()
        self._load_style()

    def _setup(self) -> None:
        """Configure the divider's basic properties.
        
        Sets the frame shape to a horizontal line and fixes the height to 1 pixel.
        """
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)

    def _load_style(self) -> None:
        """Load and apply QSS styling to the divider.
        
        Reads the divider.styles file, replaces the BORDER color placeholder
        with the actual color value from the Colors class, and applies the stylesheet.
        """

        qss = load_stylesheet(Resources.DIVIDER_QSS_PATH)

        self.setStyleSheet(qss)
