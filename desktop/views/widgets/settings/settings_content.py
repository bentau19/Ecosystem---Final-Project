from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QLabel, QFrame,
)

import resources_qrc  # noqa: F401  — required for Qt virtual-filesystem paths
from app.app_state import app_state
from app.theme_manager import theme_manager
from resources.colors import SettingsColors, LightSettingsColors
from resources.paths import SettingsStyles
from resources.spacing import Spacing
from utils.styles import load_stylesheet, themed
from views.widgets.settings.setting_row import SettingRow


class SettingsContent(QScrollArea):
    """Scrollable settings content area.

    Displays two sections:

    * **System** — Launch at startup toggle.
    * **Features** — Virtual Drive toggle.

    Reads initial toggle states from :data:`~app.app_state.app_state` and
    wires each toggle to the appropriate :class:`~viewmodels.settings.SettingsViewModel`
    slot.  External changes (via ViewModel signals) are reflected back with
    ``set_checked`` so there is no signal-write-back loop.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build and wire the settings content widget."""
        super().__init__(parent)

        self._autostart_row: SettingRow
        self._vdrive_row: SettingRow
        self._clipboard_row: SettingRow
        self._webcam_row: SettingRow
        self._backup_row: SettingRow

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("settingsScrollArea")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner.setObjectName("settingsInnerWidget")
        self.setWidget(inner)

        self._build_inner_layout(inner)

    def _build_inner_layout(self, parent: QWidget) -> None:
        vm = app_state.settings_viewmodel

        layout = QVBoxLayout(parent)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.NONE)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Page title ────────────────────────────────────────────────────────
        page_title = QLabel("Settings")
        page_title.setObjectName("pageTitle")
        layout.addWidget(page_title)
        layout.addSpacing(Spacing.XL)

        # ── System section ────────────────────────────────────────────────────
        layout.addWidget(self._make_section_label("SYSTEM"))
        layout.addSpacing(Spacing.SM)

        self._autostart_row = SettingRow(
            title="Launch SyncDose at startup",
            description="Start SyncDose automatically when you log in to Windows.",
            checked=vm.autostart,
        )
        layout.addWidget(self._autostart_row)
        layout.addSpacing(Spacing.LG)

        # ── Section divider ────────────────────────────────────────────────────
        layout.addWidget(self._make_separator())
        layout.addSpacing(Spacing.LG)

        # ── Features section ──────────────────────────────────────────────────
        layout.addWidget(self._make_section_label("FEATURES"))
        layout.addSpacing(Spacing.SM)

        self._vdrive_row = SettingRow(
            title="Virtual Drive",
            description=(
                "Mount your phone as a Windows drive letter whenever a device is connected, "
                "so you can browse phone files directly in Explorer."
            ),
            checked=vm.virtual_drive_enabled,
        )
        layout.addWidget(self._vdrive_row)
        layout.addSpacing(Spacing.LG)

        self._clipboard_row = SettingRow(
            title="Clipboard Sync",
            description=(
                "Keep the clipboard in sync between this PC and your phone while a "
                "device is connected."
            ),
            checked=vm.clipboard_enabled,
        )
        layout.addWidget(self._clipboard_row)
        layout.addSpacing(Spacing.LG)

        self._webcam_row = SettingRow(
            title="Webcam",
            description=(
                "Let your phone stream its camera to a virtual webcam that other "
                "apps (Zoom, OBS, …) can use."
            ),
            checked=vm.webcam_enabled,
        )
        layout.addWidget(self._webcam_row)
        layout.addSpacing(Spacing.LG)

        self._backup_row = SettingRow(
            title="Backup",
            description=(
                "Allow your phone to back up photos and files to this PC. "
                "Disabling this prevents new backup sessions from starting."
            ),
            checked=vm.backup_enabled,
        )
        layout.addWidget(self._backup_row)

        layout.addStretch()

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setObjectName("sectionSeparator")
        sep.setFrameShape(QFrame.Shape.HLine)
        return sep

    # ── Style ──────────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        qss = load_stylesheet(
            SettingsStyles.SETTINGS_CONTENT,
            themed([SettingsColors], [LightSettingsColors], theme_manager.is_dark),
        )
        self.setStyleSheet(qss)

    # ── Signals ────────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        vm = app_state.settings_viewmodel

        # UI → ViewModel: user flips a toggle
        self._autostart_row.toggled.connect(vm.set_autostart)
        self._vdrive_row.toggled.connect(vm.set_virtual_drive_enabled)
        self._clipboard_row.toggled.connect(vm.set_clipboard_enabled)
        self._webcam_row.toggled.connect(vm.set_webcam_enabled)
        self._backup_row.toggled.connect(vm.set_backup_enabled)

        # ViewModel → UI: setting changed externally (or on construction echo)
        vm.autostart_changed.connect(self._on_autostart_changed)
        vm.virtual_drive_changed.connect(self._on_vdrive_changed)
        vm.clipboard_changed.connect(self._on_clipboard_changed)
        vm.webcam_changed.connect(self._on_webcam_changed)
        vm.backup_changed.connect(self._on_backup_changed)

        # Re-apply stylesheet when system theme changes.
        theme_manager.theme_changed.connect(self._apply_style)

    @Slot(bool)
    def _on_autostart_changed(self, value: bool) -> None:
        self._autostart_row.set_checked(value)

    @Slot(bool)
    def _on_vdrive_changed(self, value: bool) -> None:
        self._vdrive_row.set_checked(value)

    @Slot(bool)
    def _on_clipboard_changed(self, value: bool) -> None:
        self._clipboard_row.set_checked(value)

    @Slot(bool)
    def _on_webcam_changed(self, value: bool) -> None:
        self._webcam_row.set_checked(value)

    @Slot(bool)
    def _on_backup_changed(self, value: bool) -> None:
        self._backup_row.set_checked(value)
