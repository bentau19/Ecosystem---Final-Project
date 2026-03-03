from typing import List, Optional, Tuple

from PySide6.QtCore import QRect, QSize, Qt, QMargins
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class GridFlowLayout(QLayout):
    """
    Custom flow layout similar to HTML/CSS flexbox with 'flex-wrap: wrap'.

    Arranges child widgets horizontally and wraps to the next line when
    horizontal space is exhausted. This specific implementation requires
    all items to have the same base width for grid-like consistency.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the flow layout.

        Args:
            parent: Optional parent widget to attach this layout to.
        """
        super().__init__(parent)
        if parent:
            self.setContentsMargins(QMargins(0, 0, 0, 0))

        self._item_width: int = 0
        self._item_list: List[QLayoutItem] = []

    def __del__(self) -> None:
        """Safely clear layout items on destruction."""
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        """
        Add a layout item to the flow layout.

        Args:
            item: The layout item (usually a QWidgetItem) to add.

        Raises:
            ValueError: If the item is None or its width doesn't match
                        the existing items in the layout.
        """
        if not item:
            raise ValueError("Cannot add None item to layout")

        # Enforce uniform width logic
        if not self._item_list:
            self._item_width = item.sizeHint().width()
        elif item.sizeHint().width() != self._item_width:
            raise ValueError("All items must have the same width for this GridFlowLayout implementation")

        self._item_list.append(item)

    def count(self) -> int:
        """
        Return the number of items currently in the layout.

        Returns:
            Total count of QLayoutItems.
        """
        return len(self._item_list)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:
        """
        Return the item at the given index.

        Args:
            index: The zero-based index of the item.

        Returns:
            The QLayoutItem if found, otherwise None.
        """
        return self._item_list[index] if 0 <= index < len(self._item_list) else None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:
        """
        Remove and return the item at the given index.

        Args:
            index: The zero-based index of the item to remove.

        Returns:
            The removed QLayoutItem, or None if the index is out of bounds.
        """
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        """
        Indicate the directions in which this layout can expand.

        Returns:
            Horizontal orientation by default.
        """
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self) -> bool:
        """
        Enable height-for-width calculations.

        Returns:
            True, as the height depends on the current width (wrapping).
        """
        return True

    def heightForWidth(self, width: int) -> int:
        """
        Calculate the height required for a specific width.

        Args:
            width: The available width.

        Returns:
            The total height required to display all items.
        """
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        """
        Apply geometry settings to the layout and its children.

        Args:
            rect: The bounding rectangle for the layout.
        """
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        """
        Calculate the recommended size for the layout.

        Returns:
            QSize representing the width for all items in one row and the max item height.
        """
        width: int = 0
        height: int = 0
        margins: QMargins = self.contentsMargins()

        for item in self._item_list:
            size: QSize = item.sizeHint()
            width += size.width() + self.spacing()
            height = max(height, size.height())

        return QSize(width, height + margins.top() + margins.bottom())

    def minimumSize(self) -> QSize:
        """
        Calculate the minimum size needed to display at least one item.

        Returns:
            QSize encompassing the largest minimum item size plus margins.
        """
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        margins: QMargins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(),
                      margins.top() + margins.bottom())
        return size

    def _calculate_columns_and_stretch(self, available_width: int) -> Tuple[int, int, int]:
        """
        Determine how many items fit per row and how to distribute extra space.

        Args:
            available_width: The total horizontal pixels available.

        Returns:
            A tuple of (columns, stretch_per_item, remainder_pixels).
        """
        spacing: int = self.spacing()
        # Calculate how many items + spacing can fit
        columns = (available_width + spacing) // (self._item_width + spacing)
        columns = max(1, columns)

        # Calculate space distribution (flex-grow style)
        base_row_width = (columns * self._item_width) + (columns - 1) * spacing
        total_stretch = max(0, available_width - base_row_width)

        stretch_per_item = total_stretch // columns
        extra_pixels = total_stretch % columns

        return columns, stretch_per_item, extra_pixels

    def _compute_item_width_in_row(self, available_width: int, stretch_per_item: int, add_extra: int) -> int:
        """
        Calculate the final width of an item after stretching.

        Args:
            available_width: Total width of the container.
            stretch_per_item: Base pixels to add to each item.
            add_extra: Additional 1 pixel for remainder distribution.

        Returns:
            The calculated width for the item.
        """
        item_width = self._item_width + stretch_per_item + add_extra
        return min(item_width, available_width)

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """
        The core engine that positions items or calculates total height.

        Args:
            rect: The available geometry rectangle.
            test_only: If True, it calculates height without moving widgets.

        Returns:
            The total vertical height consumed by the layout.
        """
        if not self._item_list:
            return 0

        margins: QMargins = self.contentsMargins()
        effective_rect: QRect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())

        columns, stretch_per_item, extra_pixels = self._calculate_columns_and_stretch(effective_rect.width())

        x: int = effective_rect.x()
        y: int = effective_rect.y()
        line_height: int = 0
        items_in_row: int = 0
        row_extra: int = extra_pixels

        for item in self._item_list:
            # Check if we need to wrap to next row
            if items_in_row >= columns:
                x = effective_rect.x()
                y += line_height + self.spacing()
                line_height = 0
                items_in_row = 0
                row_extra = extra_pixels

            add_extra = 1 if row_extra > 0 else 0
            current_item_width = self._compute_item_width_in_row(effective_rect.width(), stretch_per_item, add_extra)

            if not test_only:
                item.setGeometry(QRect(x, y, current_item_width, item.sizeHint().height()))

            x += current_item_width + self.spacing()
            line_height = max(line_height, item.sizeHint().height())
            row_extra = max(0, row_extra - 1)
            items_in_row += 1

        return y + line_height - rect.y() + margins.bottom()
