from PySide6.QtCore import Qt, QMargins, QRect, QSize
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget

from resources.spacing import Spacing


class FlowLayout(QLayout):
    """A layout that arranges its children in a left-to-right, top-to-bottom flow.

    Items are wrapped onto a new row once the current row no longer has room
    for another item of at least :attr:`_min_width`.  The number of columns
    per row and each item's width are recomputed on every :meth:`setGeometry`
    call, so the layout adapts as its container is resized.
    """

    def __init__(self, min_width: int = 200, parent: QWidget | None = None) -> None:
        """Initialize the FlowLayout.

        Args:
            min_width: The minimum width of each child widget, used to compute
                how many columns fit per row.
            parent: The optional parent widget.
        """
        super().__init__(parent)

        self._min_width: int = min_width

        if parent is not None:
            self.setContentsMargins(QMargins(Spacing.NONE, Spacing.NONE, Spacing.NONE, Spacing.NONE))

        self._item_list: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:
        """Add a child item to the layout.

        Args:
            item: The child item to add.
        """
        self._item_list.append(item)

    def count(self) -> int:
        """Return the number of child items in the layout.

        Returns:
            The number of child items.
        """
        return len(self._item_list)

    def itemAt(self, index: int) -> QLayoutItem | None:
        """Return the child item at the specified index.

        Args:
            index: The index of the child item.

        Returns:
            The child item at the specified index, or ``None`` if the index
            is out of range.
        """
        if 0 <= index < len(self._item_list):
            return self._item_list[index]

        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        """Remove and return the child item at the specified index.

        Args:
            index: The index of the child item to remove.

        Returns:
            The removed child item, or ``None`` if the index is out of range.
        """
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)

        return None

    def expandingDirections(self) -> Qt.Orientation:
        """Return the directions in which the layout expands.

        Returns:
            ``Qt.Orientation(0)`` — this layout does not expand in either
            direction; it wraps items instead.
        """
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        """Return whether the layout's height depends on its width.

        Returns:
            ``True`` — wrapping means the required height changes with width.
        """
        return True

    def heightForWidth(self, width: int) -> int:
        """Return the height required to lay out all items at the given width.

        Args:
            width: The width for which to calculate the height.

        Returns:
            The height of the layout for the given width.
        """
        height: int = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect: QRect) -> None:
        """Position all child items within *rect*.

        Args:
            rect: The geometry rectangle assigned to this layout.
        """
        super(FlowLayout, self).setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        """Return the preferred size of the layout.

        Returns:
            The same value as :meth:`minimumSize`.
        """
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        """Return the minimum size needed to display all child items.

        Returns:
            The minimum size of the layout, including content margins.
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
        # Compute item positions (or just the total height when test_only=True).
        if not self._item_list:
            return 0

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
