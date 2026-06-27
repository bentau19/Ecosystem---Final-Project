from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from domain.dto.dependency_info import DependencyInfoDTO
from resources.spacing import Spacing
from viewmodels.dependency import DependencyViewModel


class MissingDependenciesDialog(QDialog):
    """Startup dialog listing required Windows components that are missing.

    Presentational only: it renders the
    :class:`~domain.dto.dependency_info.DependencyInfoDTO` list held by
    :class:`~viewmodels.dependency.DependencyViewModel`, forwards install
    choices to the ViewModel, and records whether the app should keep launching.

    Launch gating (the app must not start until missing components are
    installed):

    * **Download & Install Selected** — triggers the installs, asks the user to
      restart, and leaves :attr:`should_launch` ``False`` so the bootstrap
      exits; freshly installed runtimes are only picked up on relaunch.
    * **Continue Without Installing** — offered only when no *required*
      component is missing; sets :attr:`should_launch` ``True``.
    * **Closing the dialog** — launches only when no required component is
      missing.
    """

    def __init__(
            self,
            viewmodel: DependencyViewModel,
            parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog from its ViewModel.

        Args:
            viewmodel: Supplies the missing-dependency DTOs and performs installs.
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)
        self._viewmodel: DependencyViewModel = viewmodel
        # Default: launch only when nothing required is missing. Closing the
        # dialog therefore exits the app while a required component is absent.
        self._should_launch: bool = not viewmodel.has_required_missing
        self._checkboxes: dict[DependencyInfoDTO, QCheckBox] = {}

        self.setWindowTitle("Missing Dependencies")
        self.setModal(True)
        self.setMinimumWidth(500)
        self._setup_ui()

    @property
    def should_launch(self) -> bool:
        """Whether the bootstrap should continue launching after the dialog."""
        return self._should_launch

    def _setup_ui(self) -> None:
        # Build the layout from the ViewModel's missing-dependency DTOs.
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        title = QLabel("Missing Dependencies")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        explanation = QLabel(self._build_explanation())
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        for info in self._viewmodel.missing:
            checkbox = QCheckBox(info.display_name)
            checkbox.setChecked(True)
            self._checkboxes[info] = checkbox
            layout.addWidget(checkbox)

        layout.addSpacing(Spacing.MD)
        layout.addLayout(self._build_buttons())

    def _build_explanation(self) -> str:
        # Compose the body text from each missing component's description.
        lines = ["The following required components are not installed:\n"]
        lines += [
            f"• {info.display_name} — {info.description}"
            for info in self._viewmodel.missing
        ]
        lines.append("\nWould you like to install them?")
        return "\n".join(lines)

    def _build_buttons(self) -> QHBoxLayout:
        # Install is always available; Continue only when nothing required is missing.
        button_layout = QHBoxLayout()
        button_layout.setSpacing(Spacing.SM)

        install_btn = QPushButton("Download & Install Selected")
        install_btn.clicked.connect(self._on_install_clicked)
        button_layout.addWidget(install_btn)

        if not self._viewmodel.has_required_missing:
            continue_btn = QPushButton("Continue Without Installing")
            continue_btn.clicked.connect(self._on_continue_clicked)
            button_layout.addWidget(continue_btn)

        return button_layout

    def _on_continue_clicked(self) -> None:
        # User skipped optional installs — allow the app to launch.
        self._should_launch = True
        self.accept()

    def _on_install_clicked(self) -> None:
        # Forward each checked component to the ViewModel, then require a restart.
        selected = [
            info.dependency
            for info, checkbox in self._checkboxes.items()
            if checkbox.isChecked()
        ]
        if not selected:
            self.accept()
            return

        for dependency in selected:
            self._viewmodel.request_install(dependency)

        QMessageBox.information(
            self,
            "Installation Started",
            "Download pages for the selected components have been opened.\n\n"
            "Please install them, then restart SyncDose.",
        )
        # A freshly installed runtime is only picked up on relaunch — do not
        # continue into the app on this run.
        self._should_launch = False
        self.accept()
