import sys

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication

from views.widgets.login.qr import QR


class LeftPanel(QWidget):

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self._create_widgets()
        self._setup_layout()
        pass

    def _create_widgets(self):
        self._qr = self._create_qr()
        self._logo = self._create_logo()

        pass

    def _setup_layout(self):
        layout = QVBoxLayout(self)

        layout.addWidget(self._logo)
        layout.addWidget(self._qr)

        layout.addStretch()
        pass

    @staticmethod
    def _create_qr() -> QR:
        qr = QR()
        qr.setObjectName("QR")
        return qr

    @staticmethod
    def _create_logo() -> QLabel:
        logo = QLabel()
        #  TODO: logo.setPixmap(QPixmap.fromImage(self._logo))
        logo.setObjectName("Logo")
        return logo


if __name__ == '__main__':
    app = QApplication(sys.argv)
    left_panel = LeftPanel()
    left_panel.show()
    app.exec()
