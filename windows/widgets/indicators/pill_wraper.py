from typing import Final
from PySide6.QtWidgets import QWidget, QVBoxLayout
from widgets.indicators.connection_pill import ConnectionPill


class PillWrapper(QWidget):
    """
    A wrapper widget that holds one or more connection indicator pills in a
    vertical layout with predefined spacing and margins.

     Args:
        parent (Optional[QWidget]): Parent widget, defaults to None
    """

    _MARGIN_LEFT: Final[int] = 12
    _MARGIN_RIGHT: Final[int] = 14
    _MARGIN_TOP: Final[int] = 12
    _MARGIN_BOTTOM: Final[int] = 0
    _SPACING: Final[int] = 2
    _MINIMUM_HEIGHT: Final[int] = 55

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the PillWrapper.

        Args:
            parent (QWidget | None): Optional parent widget.
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """
        Set up the vertical layout, add the ConnectionPill widget,
        and enforce the minimum height of the wrapper.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._MARGIN_LEFT, self._MARGIN_TOP, self._MARGIN_RIGHT, self._MARGIN_BOTTOM
        )
        layout.addWidget(ConnectionPill())
        self.setMinimumHeight(self._MINIMUM_HEIGHT)
