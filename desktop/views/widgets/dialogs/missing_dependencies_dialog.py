"""
Missing Dependencies Dialog — shown at startup if required Windows components are missing.

Offers to reinstall .NET 8, WinFSP, or OBS Studio.
"""

from typing import List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QCheckBox,
)

from app.obs_checker import (
    try_reinstall_obs_from_bundled,
    open_obs_download_page,
    open_dotnet_download_page,
    open_winfsp_download_page,
)
from resources.spacing import Spacing


class MissingDependenciesDialog(QDialog):
    """
    Dialog shown when required dependencies are detected as missing at app startup.

    Missing dependencies can be:
    - .NET 8 Runtime (required by TauSync C# library via pythonnet)
    - WinFSP (required for Virtual Drive feature)
    - OBS Studio (required for phone camera streaming)

    Users can download and install each missing component.
    """

    def __init__(self, missing_deps: List[str], parent=None):
        """
        Args:
            missing_deps: List of missing dependency names ('dotnet8', 'winfsp', 'obs')
            parent: Parent widget
        """
        super().__init__(parent)
        self.missing_deps = missing_deps
        self.setWindowTitle("Missing Dependencies")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        # Title
        title = QLabel("Missing Dependencies")
        title_font = title.font()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Explanation
        explanation = QLabel(
            "The following required components are not installed:\n\n"
        )
        explanation.setWordWrap(True)

        # Build explanation text with dependency descriptions
        desc_text = ""
        for dep in self.missing_deps:
            if dep == "dotnet8":
                desc_text += "• .NET 8 Runtime — required for internal system connectivity\n"
            elif dep == "winfsp":
                desc_text += "• WinFSP — required for virtual drive mounting feature\n"
            elif dep == "obs":
                desc_text += "• OBS Studio — required for phone camera streaming\n"

        explanation.setText(explanation.text() + desc_text + "\nWould you like to install them?")
        layout.addWidget(explanation)

        # Checkboxes for selecting which to install
        self.checkboxes = {}
        for dep in self.missing_deps:
            if dep == "dotnet8":
                label = ".NET 8 Runtime"
            elif dep == "winfsp":
                label = "WinFSP"
            else:
                label = "OBS Studio"

            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            self.checkboxes[dep] = checkbox
            layout.addWidget(checkbox)

        layout.addSpacing(Spacing.MD)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(Spacing.SM)

        # Install selected button
        install_btn = QPushButton("Download & Install Selected")
        install_btn.clicked.connect(self.on_install_clicked)
        button_layout.addWidget(install_btn)

        # Skip button
        skip_btn = QPushButton("Continue Without Installing")
        skip_btn.clicked.connect(self.accept)
        button_layout.addWidget(skip_btn)

        layout.addLayout(button_layout)

    def on_install_clicked(self) -> None:
        """User clicked Install — open download pages for selected dependencies."""
        selected = [dep for dep, checkbox in self.checkboxes.items() if checkbox.isChecked()]

        if not selected:
            self.accept()
            return

        # Open download pages
        for dep in selected:
            if dep == "dotnet8":
                open_dotnet_download_page()
            elif dep == "winfsp":
                open_winfsp_download_page()
            elif dep == "obs":
                if not try_reinstall_obs_from_bundled():
                    open_obs_download_page()

        # Show info message
        deps_str = ", ".join([
            ".NET 8" if d == "dotnet8" else
            "WinFSP" if d == "winfsp" else
            "OBS Studio"
            for d in selected
        ])

        QMessageBox.information(
            self,
            "Installation Started",
            f"Download pages for {deps_str} have been opened.\n\n"
            "Please install the selected components, then restart SyncDose.",
        )
        self.accept()
