import sys

import qtawesome as qta
from PySide6.QtWidgets import QFrame, QApplication

from view.layouts.grid_flow_layout import GridFlowLayout
from view.widgets.tool_card import ToolCard


class AllToolsCards(QFrame):

    def __init__(self):
        super().__init__()

        self._init_ui()
        self._load_style()

    def _init_ui(self):
        self.tools_layouts = GridFlowLayout(self)
        self.tools_layouts.setContentsMargins(8, 8, 8, 8)
        self.tools_layouts.setSpacing(8)

        for i in range(5):
            tl = ToolCard(qta.icon("fa6s.battery-quarter", color="orange"), "grr", "hyr")
            tl.setMinimumSize(250, 200)
            self.tools_layouts.addWidget(tl)

    def _load_style(self):
        with open("../qss/all_tools_cards.qss", "r") as f:
            self.setStyleSheet(f.read())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AllToolsCards()
    window.show()
    sys.exit(app.exec())
