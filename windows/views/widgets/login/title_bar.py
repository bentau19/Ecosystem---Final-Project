from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt


class TitleBar(QWidget):
    """
    Custom title bar that mimics a macOS window chrome.

    Displays three colored dots (close / minimize / maximize) on the left
    and a centred monospaced window title label.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        """
        Initialise the title bar.

        Args:
            title:  Text shown in the centre of the bar.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(32)
        self._build_ui(title)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self, title: str) -> None:
        """Construct and arrange child widgets."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(6)

        for obj_name in ("TrafficDotRed", "TrafficDotYellow", "TrafficDotGreen"):
            dot = QLabel()
            dot.setObjectName(obj_name)
            layout.addWidget(dot)

        layout.addStretch()

        title_label = QLabel(title)
        title_label.setObjectName("TitleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        layout.addStretch()
        # Invisible spacer to balance the dots on the right
        layout.addSpacing(6 * 3 + 11 * 3)
