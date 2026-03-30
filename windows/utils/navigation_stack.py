from PySide6.QtWidgets import QStackedWidget, QWidget
from typing import Dict


class NavigationStack(QStackedWidget):
    """
    A stacked widget that allows navigation between registered widgets.
    """

    def __init__(self) -> None:
        """
        Initialize the navigation stack.
        """
        super().__init__()
        self._registry: Dict[str, QWidget] = {}

    def register(self, name: str, widget: QWidget) -> None:
        """
        Register a widget with the given name.

        Args:
            name (str): The name of the widget.
            widget (QWidget): The widget to register.
        """
        self._registry[name] = widget
        self.addWidget(widget)

    def navigate(self, name: str) -> None:
        """
        Navigate to the widget with the given name.

        Args:
            name (str): The name of the widget.
        """
        self.setCurrentWidget(self._registry[name])
