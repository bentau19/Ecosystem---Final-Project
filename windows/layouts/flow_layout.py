from typing import List, Optional

from PySide6.QtCore import Qt, QMargins, QRect, QSize
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget

from resources.spacing import Spacing


class FlowLayout(QLayout):
    """
    A layout that arranges its children in a horizontal flow.
    """

    def __init__(self, min_width: int = 200, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the FlowLayout.

        Args:
            min_width (int): The minimum width of each child widget.
            parent (Optional[QWidget]): The optional parent widget.
        """
        super().__init__(parent)

        self._min_width: int = min_width

        if parent is not None:
            self.setContentsMargins(QMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE))

        self._item_list: List[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:
        """
        Add a child item to the layout.

        Args:
            item (QLayoutItem): The child item to add.
        """
        self._item_list.append(item)

    def count(self) -> int:
        """
        Return the number of child items in the layout.

        Returns:
            int: The number of child items.
        """
        return len(self._item_list)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:
        """
        Return the child item at the specified index.

        Args:
            index (int): The index of the child item.

        Returns:
            QLayoutItem: The child item at the specified index, or None if the index is out of range.
        """
        if 0 <= index < len(self._item_list):
            return self._item_list[index]

        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:
        """
        Remove and return the child item at the specified index.

        Args:
            index (int): The index of the child item to remove.

        Returns:
            QLayoutItem: The removed child item, or None if the index is out of range.
        """
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)

        return None

    def expandingDirections(self) -> Qt.Orientation:
        """
        Return the directions in which the layout expands.

        Returns:
            Qt.Orientation: The directions in which the layout expands.
        """
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self) -> bool:
        """
        Return True if the layout provides a height for a given width.

        Returns:
            bool: True if the layout provides a height for a given width.
        """
        return True

    def heightForWidth(self, width: int) -> int:
        """
        Return the height of the layout for the given width.

        Args:
            width (int): The width for which to calculate the height.

        Returns:
            int: The height of the layout for the given width.
        """
        height: int = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect: QRect) -> None:
        """
        Set the geometry of the layout.

        Args:
            rect (QRect): The geometry rectangle.
        """
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        """
        Return the size hint of the layout.

        Returns:
            QSize: The size hint of the layout.
        """
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        """
        Return the minimum size of the layout.

        Returns:
            QSize: The minimum size of the layout.
        """
        # Get the margins of the layout
        margins: QMargins = self.contentsMargins()
        size: QSize = QSize()

        # Calculate the total minimum size of all child items
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        # Add the margins to the total size
        size += QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom()
        )
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """
        Perform the layout.

        Args:
            rect (QRect): The layout rectangle.
            test_only (bool): If True, only test the layout without performing any actual layout.
            rect: The layout rectangle.
            test_only: If True, only test the layout without performing any actual layout.

        Returns:
            int: The height of the layout.
        """
        # Get the margins of the layout
        margins: QMargins = self.contentsMargins()
        # Calculate the effective layout rectangle (after subtracting margins)
        effective_rect: QRect = rect.adjusted(
            margins.left(),
            margins.top(),
            -margins.right(),
            -margins.bottom()
        )

        x: int = effective_rect.x()  # Starting x-coordinate of the layout
        y: int = effective_rect.y()  # Starting y-coordinate of the layout

        line_height: int = 0  # Height of the current line

        spacing: int = self.spacing() if self.spacing() != -1 else Spacing.SM  # Spacing between items

        cols: int = min(len(self._item_list), max(1, (effective_rect.width() + spacing) // (self._min_width + spacing)))
        item_width: int = (effective_rect.width() - spacing * (cols - 1)) // cols

        col_count: int = 0  # Number of items in the current column

        # Iterate over each child item
        for item in self._item_list:
            # If we have reached the end of the current line, move to the next line
            if col_count >= cols:
                x = effective_rect.x()
                y = y + line_height + spacing
                line_height = 0
                col_count = 0

            # If we're not in test mode, set the geometry of the item
            if not test_only:
                item.setGeometry(QRect(x, y, item_width, item.sizeHint().height()))

            # Increment the x-coordinate by the item width and spacing
            x = x + item_width + spacing
            col_count += 1
            # Update the line height with the height of the current item
            line_height = max(line_height, item.sizeHint().height())

        # Return the height of the layout
        return y + line_height - rect.y() + margins.bottom() + margins.top()
