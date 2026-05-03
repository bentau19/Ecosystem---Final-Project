from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout
)

from domain.enums.screen import Screen
from resources.paths import Icons, Styles
from resources.spacing import Spacing
from app.app_state import app_state
from app.navigation_manager import navigation_manager
from utils.styles import load_stylesheet
from viewmodels.device import DeviceViewModel


class Topbar(QWidget):
    """Top navigation bar widget.

    Displays the page title, subtitle, and a disconnect button.
    Designed to align visually with the sidebar logo row via a shared height.
    """

    def __init__(
            self,
            title: str,
            subtitle: str,
            topbar_height: int = 72,
            parent: QWidget | None = None
    ) -> None:
        """Initialize the Topbar.

        Args:
            title (str): Main page title displayed on the left.
            subtitle (str): Secondary text shown below the title.
            topbar_height (int): Height of the topbar. Defaults to 72.
            parent (Optional[QWidget], optional): Optional parent widget.
                                                  Defaults to None.
        """
        super().__init__(parent)

        self._title: str = title
        self._subtitle: str = subtitle
        self._topbar_height: int = topbar_height
        self._device_viewmodel: DeviceViewModel = app_state.device_viewmodel

        self._title_block: QWidget
        self._disconnect_button: QPushButton

        self._setup_ui()
        self._setup_style()
        self.setup_signals()

    def _setup_ui(self) -> None:
        """Configure the widget and build the UI."""
        self.setFixedHeight(self._topbar_height)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        """Instantiate all child widgets."""
        self._title_block = self._create_title_block()
        self._disconnect_button = self._create_disconnect_button()

    def _create_layout(self) -> None:
        """Arrange child widgets in the topbar layout."""
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.NONE, Spacing.XXL, Spacing.NONE)
        layout.setSpacing(Spacing.MD)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._title_block)
        layout.addStretch()
        layout.addWidget(self._disconnect_button)

    def _create_title_block(self) -> QWidget:
        """Create the title and subtitle stacked vertically.

        Returns:
            QWidget containing the title and subtitle labels.
        """
        block: QWidget = QWidget()

        layout: QVBoxLayout = QVBoxLayout(block)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.setSpacing(Spacing.SM)

        title_label: QLabel = QLabel(self._title)
        title_label.setObjectName("titleLabel")

        subtitle_label: QLabel = QLabel(self._subtitle)
        subtitle_label.setObjectName("subtitleLabel")

        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)

        return block

    def _create_disconnect_button(self) -> QPushButton:
        """Create the disconnect button.

        Returns:
            QPushButton styled as a destructive action button.
        """
        icon_size = 16
        btn: QPushButton = QPushButton(self.tr("  Disconnect"))
        btn.setIcon(QIcon(Icons.DISCONNECT))
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setObjectName(self.tr("disconnectButton"))

        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)
        return btn

    def _setup_style(self) -> None:
        """Load and apply the QSS stylesheet to the topbar."""
        qss: str = load_stylesheet(Styles.TOPBAR)
        self.setStyleSheet(qss)

    def setup_signals(self) -> None:
        """Wire the disconnect button and ViewModel signals to their slots."""
        self._disconnect_button.clicked.connect(self._disconnect_from_current_device)
        self._device_viewmodel.device_disconnected.connect(self._move_to_login)

    @Slot()
    def _disconnect_from_current_device(self) -> None:
        """Request device disconnection from the ViewModel."""
        self._device_viewmodel.disconnect_device()

    @Slot()
    def _move_to_login(self) -> None:
        """Navigate back to the login screen after the device disconnects."""
        navigation_manager.go_to_screen(Screen.LOGIN)
