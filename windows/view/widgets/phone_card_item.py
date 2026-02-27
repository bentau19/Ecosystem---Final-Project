from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame


class PhoneCardItemWidget(QFrame):
    """A  widget displaying an icon with a colored background, a description, and custom content.

    :param description: Text shown below the icon.
    :param content: Any widget placed under the description.
    :param icon: Icon displayed inside the colored background label.
    :param icon_background_color: Background color of the icon label.
    """

    def __init__(self, description: str, content: QWidget, icon: QIcon, icon_background_color: QColor):
        super().__init__()
        self.description = description
        self.content = content
        self.icon = icon
        self.icon_background_color = icon_background_color

        self._load_style()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize and arrange all child widgets and layouts."""
        main_layout = QHBoxLayout()
        main_layout.setObjectName("main_layout")
        main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.setLayout(main_layout)

        main_layout.addWidget(self._create_icon_label())
        main_layout.addLayout(self._create_desc_content_layout())

    def _create_icon_label(self) -> QLabel:
        """Create the icon label with a rounded colored background.

        :return: Configured ``QLabel`` displaying the icon.
        """
        label = QLabel()
        label.setPixmap(self.icon.pixmap(25, 25))
        label.setObjectName("icon")
        label.setFixedSize(30, 30)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f" background-color: {self.icon_background_color.name()}")
        return label

    def _create_desc_content_layout(self) -> QVBoxLayout:
        """Create the vertical layout containing the description and content widget.

        :return: ``QVBoxLayout`` with description label and content widget added.
        """
        layout = QVBoxLayout()
        layout.setObjectName("desc_content_layout")
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        description_label = QLabel(self.description)
        description_label.setObjectName("description")

        layout.addWidget(description_label)
        layout.addWidget(self.content)
        return layout

    def _load_style(self) -> None:
        """Load and apply the external QSS stylesheet from ``../qss/phone_card_item.qss``.

        :raises FileNotFoundError: If the QSS file does not exist at the expected path.
        """
        with open("../qss/phone_card_item.qss", "r") as f:
            self.setStyleSheet(f.read())
