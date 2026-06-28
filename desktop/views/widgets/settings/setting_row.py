from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
)

from resources.spacing import Spacing
from views.widgets.settings.toggle_switch import ToggleSwitch


class SettingRow(QWidget):
    """A single settings row: title (+ optional description) on the left, toggle on the right.

    Signals:
        toggled (bool): Re-emitted from the inner :class:`ToggleSwitch` whenever the
            user flips the toggle.  Connect to a ViewModel slot to persist the change.
    """

    toggled: Signal = Signal(bool)

    def __init__(
        self,
        title: str,
        description: str = "",
        checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Create a setting row.

        Args:
            title:       Bold title text shown on the left.
            description: Optional muted helper text shown below the title.
            checked:     Initial toggle state.
            parent:      Optional parent widget.
        """
        super().__init__(parent)

        self._title: str = title
        self._description: str = description
        self._checked: bool = checked

        self._title_label: QLabel
        self._description_label: QLabel
        self._toggle: ToggleSwitch

        self._setup_ui()
        self._connect_signals()

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("settingRow")
        # WA_StyledBackground: lets QWidget render a QSS background colour.
        # WA_Hover:            delivers hover-enter/leave events so QSS :hover works.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._create_widgets()
        self._setup_layout()

    def _create_widgets(self) -> None:
        self._title_label = QLabel(self._title)
        self._title_label.setObjectName("settingTitle")

        self._description_label = QLabel(self._description)
        self._description_label.setObjectName("settingDescription")
        self._description_label.setWordWrap(True)
        # Hide the description label entirely when no text is provided so it
        # doesn't consume vertical space.
        self._description_label.setVisible(bool(self._description))

        self._toggle = ToggleSwitch(checked=self._checked)

    def _setup_layout(self) -> None:
        # Left side: stacked title + description
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE)
        text_layout.setSpacing(Spacing.XS)
        text_layout.addWidget(self._title_label)
        text_layout.addWidget(self._description_label)

        # Root: text (stretch) | toggle
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        root_layout.setSpacing(Spacing.LG)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        root_layout.addLayout(text_layout, stretch=1)
        root_layout.addWidget(self._toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _connect_signals(self) -> None:
        self._toggle.toggled.connect(self.toggled)

    # ── Public API ─────────────────────────────────────────────────────────────

    @Slot(bool)
    def set_checked(self, value: bool) -> None:
        """Update the toggle state and knob position without emitting :attr:`toggled`.

        Used to reflect an externally-driven change (e.g. the ViewModel
        emitting ``clipboard_changed`` after the phone pushes a new setting)
        without triggering a write-back loop.  Delegates to
        :meth:`ToggleSwitch.set_checked_silent` so the knob actually animates —
        a bare ``setChecked`` under blocked signals would leave the knob in place.

        Args:
            value: New checked state.
        """
        self._toggle.set_checked_silent(value)
