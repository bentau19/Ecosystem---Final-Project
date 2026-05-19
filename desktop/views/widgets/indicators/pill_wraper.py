from PySide6.QtWidgets import QWidget, QVBoxLayout

from resources.spacing import Spacing
from views.widgets.indicators.connection_pill import ConnectionPill


class PillWrapper(QWidget):
    """
    A wrapper widget that holds one or more connection indicator pills in a
    vertical layout with predefined spacing and margins.
    """

    def __init__(self, minimum_height: int = 55, parent: QWidget | None = None) -> None:
        """
        Initialize the PillWrapper.

        Args:
            minimum_height (int, optional): Minimum height of the PillWrapper. Defaults to 55.
            parent (Optional[QWidget], optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)

        self._minimum_height: int = minimum_height

        self._setup_ui()

    def _setup_ui(self) -> None:
        # Build the vertical layout, add ConnectionPill, and enforce minimum height.
        layout: QVBoxLayout = QVBoxLayout(self)

        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.NONE)
        layout.addWidget(ConnectionPill())
        self.setMinimumHeight(self._minimum_height)