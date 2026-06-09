from PySide6.QtCore import Qt, QSize, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout
)

from domain.enums.screen import Screen
from domain.dto.device_info import DeviceInfoDTO, DeviceNameDTO
from resources.paths import Icons, Styles
from resources.spacing import Spacing
from app.app_state import app_state
from app.navigation_manager import navigation_manager
from app.theme_manager import theme_manager
from utils.styles import load_stylesheet, themed
from resources.colors import TopbarColors, LightTopbarColors
from viewmodels.device import DeviceViewModel


class Topbar(QWidget):
    """Top navigation bar widget.

    Displays the page title, subtitle, and a disconnect button.
    Designed to align visually with the sidebar logo row via a shared height.
    """

    def __init__(
            self,
            topbar_height: int = 72,
            parent: QWidget | None = None
    ) -> None:
        """Initialize the Topbar.

        Args:
            topbar_height (int): Height of the topbar. Defaults to 72.
            parent (Optional[QWidget], optional): Optional parent widget.
                                                  Defaults to None.
        """
        super().__init__(parent)

        self._title: str = "Dashboard"
        self._topbar_height: int = topbar_height
        self._device_viewmodel: DeviceViewModel = app_state.device_viewmodel

        self._title_block: QWidget
        self._disconnect_button: QPushButton

        self._setup_ui()
        self._setup_style()
        self.setup_signals()

    def _setup_ui(self) -> None:
        # Set fixed height, enable styled background, then build widgets and layout.
        self.setFixedHeight(self._topbar_height)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._create_widgets()
        self._create_layout()

    def _create_widgets(self) -> None:
        # Create the title/subtitle block and the disconnect button.
        self._title_block = self._create_title_block()
        self._disconnect_button = self._create_disconnect_button()

    def _create_layout(self) -> None:
        # Place the title block on the left, stretch, then disconnect button on the right.
        layout: QHBoxLayout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.XXL, Spacing.NONE, Spacing.XXL, Spacing.NONE)
        layout.setSpacing(Spacing.MD)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._title_block)
        layout.addStretch()
        layout.addWidget(self._disconnect_button)

    def _create_title_block(self) -> QWidget:
        # Build a stacked title + subtitle label pair.
        block: QWidget = QWidget()

        layout: QVBoxLayout = QVBoxLayout(block)
        layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        layout.setSpacing(Spacing.SM)

        title_label: QLabel = QLabel(self._title)
        title_label.setObjectName("titleLabel")

        self._subtitle_label: QLabel = QLabel("")
        self._subtitle_label.setObjectName("subtitleLabel")

        layout.addWidget(title_label)
        layout.addWidget(self._subtitle_label)

        return block

    def _create_disconnect_button(self) -> QPushButton:
        # Create the disconnect button with icon, fixed height, and pointer cursor.
        icon_size = 16
        btn: QPushButton = QPushButton(self.tr("  Disconnect"))
        btn.setIcon(QIcon(Icons.DISCONNECT))
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setObjectName(self.tr("disconnectButton"))

        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)
        return btn

    def _setup_style(self) -> None:
        # Load and apply the themed topbar stylesheet.
        qss: str = load_stylesheet(
            Styles.TOPBAR,
            themed([TopbarColors], [LightTopbarColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    def setup_signals(self) -> None:
        """Wire the disconnect button, ViewModel signals, and theme changes to their slots."""
        self._disconnect_button.clicked.connect(self._disconnect_from_current_device)
        self._device_viewmodel.device_disconnected.connect(self._move_to_login)
        self._device_viewmodel.device_infos_updated.connect(self._update_device_info)
        theme_manager.theme_changed.connect(self._setup_style)

    @Slot()
    def _disconnect_from_current_device(self) -> None:
        # Delegate disconnect to the ViewModel; it will emit device_disconnected when done.
        self._device_viewmodel.disconnect_device()

    @Slot()
    def _move_to_login(self) -> None:
        # Navigate back to the login screen after the device disconnects.
        navigation_manager.go_to_screen(Screen.LOGIN)

    @Slot(object)
    def _update_device_info(self, infos: list[DeviceInfoDTO]):
        name: DeviceNameDTO = infos[0]
        self._subtitle_label.setText(f"{name.name}")
