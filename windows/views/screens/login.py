from PySide6.QtWidgets import QWidget


class LoginScreen(QWidget):
    """
    Login Screen.
    """""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # self.title_bar: TitleBar

        self._setup_ui()

    def _setup_ui(self):
        """Construct and arrange all child widgets."""
        self.create_widgets()
        self.setup_layout()

    def create_widgets(self):
        # self.title_bar = TitleBar("syncdose — connect a device", app_frame)
        pass

    def setup_layout(self):
        pass
