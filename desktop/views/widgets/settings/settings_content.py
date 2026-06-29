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

    Two sections:

    * **System** — "Launch SyncDose at startup" (autostart).
    * **Tools** — one on/off row per feature tool (Virtual Drive, Clipboard Sync,
      Webcam, Backup), backed by ``tools.json``. Toggling a row writes through
      :meth:`~viewmodels.tool.ToolViewModel.set_tool_enabled`, which persists the
      change, applies it to the matching service, and syncs it with the phone.
      "Send File to Phone" is always enabled and has no row.

    External changes (autostart via ``SettingsViewModel``, tool state via
    ``ToolViewModel``) are reflected back with ``set_checked`` so there is no
    signal-write-back loop.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build and wire the settings content widget."""
        super().__init__(parent)

        self._dark_mode_row: SettingRow
        self._autostart_row: SettingRow
        self._tool_rows: dict[str, SettingRow] = {}

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
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        layout.setSpacing(Spacing.NONE)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Page title ────────────────────────────────────────────────────────
        page_title = QLabel("Settings")
        page_title.setObjectName("pageTitle")
        layout.addWidget(page_title)
        layout.addSpacing(Spacing.XL)

        # ── Appearance section ────────────────────────────────────────────────
        layout.addWidget(self._make_section_label("APPEARANCE"))
        layout.addSpacing(Spacing.SM)

        self._dark_mode_row = SettingRow(
            title="Dark mode",
            description="Switch to a dark color scheme. Synced with the phone.",
            checked=app_state.settings_viewmodel.dark_mode,
        )
        layout.addWidget(self._dark_mode_row)
        layout.addSpacing(Spacing.LG)

        # ── Section divider ────────────────────────────────────────────────────
        layout.addWidget(self._make_separator())
        layout.addSpacing(Spacing.LG)

        # ── System section ────────────────────────────────────────────────────
        layout.addWidget(self._make_section_label("SYSTEM"))
        layout.addSpacing(Spacing.SM)

        self._autostart_row = SettingRow(
            title="Launch SyncDose at startup",
            description="Start SyncDose automatically when you log in to Windows.",
            checked=app_state.settings_viewmodel.autostart,
        )
        layout.addWidget(self._autostart_row)
        layout.addSpacing(Spacing.LG)

        # ── Section divider ────────────────────────────────────────────────────
        layout.addWidget(self._make_separator())
        layout.addSpacing(Spacing.LG)

        # ── Tools section ──────────────────────────────────────────────────────
        # One on/off row per feature tool (Send File is always on, so it is
        # excluded by ToolViewModel.feature_tools()).
        layout.addWidget(self._make_section_label("TOOLS"))
        layout.addSpacing(Spacing.SM)

        for tool in app_state.tool_viewmodel.feature_tools():
            row = SettingRow(
                title=tool.title,
                description=tool.description,
                checked=tool.is_enabled,
            )
            self._tool_rows[tool.title] = row
            layout.addWidget(row)
            layout.addSpacing(Spacing.LG)

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
        settings_vm = app_state.settings_viewmodel
        tool_vm = app_state.tool_viewmodel

        # Dark mode (Appearance) — bidirectional with the phone
        self._dark_mode_row.toggled.connect(settings_vm.set_dark_mode)
        settings_vm.dark_mode_changed.connect(self._on_dark_mode_changed)

        # Autostart (System)
        self._autostart_row.toggled.connect(settings_vm.set_autostart)
        settings_vm.autostart_changed.connect(self._on_autostart_changed)

        # Tools — each row drives ToolViewModel.set_tool_enabled; external changes
        # (e.g. pushed from the phone) flip the row back via tool_enabled_changed.
        for title, row in self._tool_rows.items():
            row.toggled.connect(
                lambda enabled, t=title: tool_vm.set_tool_enabled(t, enabled)
            )
        tool_vm.tool_enabled_changed.connect(self._on_tool_enabled_changed)

        # Re-apply stylesheet when system theme changes.
        theme_manager.theme_changed.connect(self._apply_style)

    @Slot(bool)
    def _on_dark_mode_changed(self, value: bool) -> None:
        self._dark_mode_row.set_checked(value)

    @Slot(bool)
    def _on_autostart_changed(self, value: bool) -> None:
        self._autostart_row.set_checked(value)

    @Slot(str, bool)
    def _on_tool_enabled_changed(self, title: str, enabled: bool) -> None:
        row = self._tool_rows.get(title)
        if row is not None:
            row.set_checked(enabled)
