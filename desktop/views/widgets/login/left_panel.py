import sys

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import utils.styles
from resources.paths import Icons, LoginStyles
from resources.spacing import Spacing
from views.widgets.indicators.pulsing_dot import PulsingDot
from views.widgets.login.qr import QR
from views.widgets.logo_widget import Logo, LogoNameLabel


class LeftPanel(QWidget):
    """
    Left panel of the login screen.

    Displays the application logo, a live QR code encoding the host's
    local IP address, scan instructions, a refresh button, and a
    'Waiting for connection' indicator.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._logo: Logo
        self._logo_name: LogoNameLabel
        self._app_description: QLabel
        self._qr: QR
        self._generic_scan_instructions: QLabel
        self._detailed_scan_instructions: QLabel
        self._refresh_button: QPushButton
        self._waiting_for_connection: QWidget

        self._setup_ui()
        self._setup_style()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """Configure the widget and build child layout."""
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("LeftPanel")
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        """Instantiate all child widgets."""
        self._logo = self._create_logo()
        self._logo_name = self._create_logo_name()
        self._app_description = self._create_description()
        self._qr = self._create_qr()
        self._generic_scan_instructions = self._create_generic_scan_instructions()
        self._detailed_scan_instructions = self._create_detailed_scan_instructions()
        self._refresh_button = self._create_refresh_button()
        self._waiting_for_connection = self._create_waiting_for_connection_widget()

    def _setup_layout(self) -> None:
        """Arrange all child widgets in a centred vertical stack."""
        layout = QVBoxLayout(self)

        layout.setContentsMargins(Spacing.XXL, Spacing.SM, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.SM)

        # Stretch at top and bottom centres the content block vertically
        layout.addStretch()

        layout.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._logo_name, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._app_description, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(Spacing.MD)

        layout.addWidget(self._qr, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(Spacing.LG)

        layout.addWidget(self._generic_scan_instructions, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._detailed_scan_instructions)

        layout.addSpacing(Spacing.XS)

        layout.addWidget(self._refresh_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._waiting_for_connection, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch()

    # ── Widget factories ───────────────────────────────────────────────────────

    @staticmethod
    def _create_qr() -> QR:
        """Create and configure the QR code widget.

        Returns:
            A QR instance capped at 420×420 px.
        """
        # 420 px gives a QR dense enough to scan comfortably at arm's length
        qr_size: int = 420
        qr = QR()
        qr.setMaximumSize(qr_size, qr_size)
        qr.setObjectName("QR")
        return qr

    @staticmethod
    def _create_logo() -> Logo:
        """Create the application logo widget.

        Returns:
            A Logo label with the default icon size.
        """

        logo = Logo(logo_size=100)
        return logo

    def _create_description(self) -> QLabel:
        """Create the app tagline label.

        Returns:
            A centred QLabel with the application description text.
        """
        label = QLabel(self)
        label.setText("Seamless cross-device connectivity")
        label.setObjectName("DescriptionLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _create_logo_name() -> LogoNameLabel:
        """Create the gradient application-name label.

        Returns:
            A LogoNameLabel instance (gradient-painted 'SyncDose').
        """
        logo_label = LogoNameLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setObjectName("LogoName")
        return logo_label

    @staticmethod
    def _create_generic_scan_instructions() -> QLabel:
        """Create the primary scan-instruction label.

        Returns:
            A centred QLabel with a short instruction string.
        """
        label = QLabel()
        label.setText("Scan with SyncDose on your phone")
        label.setObjectName("GenericScanInstructions")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _create_detailed_scan_instructions() -> QLabel:
        """Create the secondary step-by-step scan-instruction label.

        Returns:
            A word-wrapping, centred QLabel with detailed steps.
        """
        label = QLabel()
        label.setText("Open the app → tap the scan icon → point your camera here")
        label.setWordWrap(True)
        label.setObjectName("DetailedScanInstructions")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _create_refresh_button() -> QPushButton:
        """Create the 'Refresh QR' button.

        Returns:
            A fixed-size QPushButton with the refresh icon and label.
        """
        button = QPushButton()
        button.setIcon(QIcon(Icons.REFRESH))
        button.setText("  Refresh QR")
        button.setFixedSize(140, 36)
        button.setObjectName("RefreshButton")
        return button

    @staticmethod
    def _create_waiting_for_connection_widget() -> QWidget:
        """Create the pulsing-dot 'Waiting for connection…' indicator row.

        Returns:
            A QWidget containing a PulsingDot and a status label side-by-side.
        """
        widget = QWidget()
        # WA_StyledBackground lets QSS target this plain QWidget with a background rule
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(widget)

        indicator = PulsingDot()
        layout.addWidget(indicator)

        label = QLabel()
        label.setText("Waiting for connection…")
        label.setObjectName("WaitingForConnectionLabel")
        layout.addWidget(label)

        return widget

    # ── Style ──────────────────────────────────────────────────────────────────

    def _setup_style(self) -> None:
        """Load and apply the left-panel QSS stylesheet."""
        qss = utils.styles.load_stylesheet(LoginStyles.LEFT_PANEL)
        self.setStyleSheet(qss)

    def _connect_signals(self) -> None:
        """Wire up internal widget signals."""
        self._refresh_button.clicked.connect(self._refresh_qr_code)

    @Slot()
    def _refresh_qr_code(self) -> None:
        """Regenerate the QR code and update the display."""
        self._qr.refresh_qr()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    left_panel = LeftPanel()
    left_panel.show()
    app.exec()
