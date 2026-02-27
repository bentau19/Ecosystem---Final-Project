from PySide6.QtCore import QRect, QPoint, QSize
from PySide6.QtWidgets import QLayout, QLayoutItem


class FlowLayout(QLayout):
    def __init__(self):
        super().__init__()
        self.items: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem):
        self.items.append(item)

    def removeItem(self, item: QLayoutItem):
        self.items.remove(item)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self.set_components(rect)

    def count(self) -> int:
        return len(self.items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < self.count():
            return self.items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem:
        return self.items.pop(index)

    def set_components(self, rect: QRect):
        x: int = rect.x()
        y: int = rect.y()

        spacing: int = self.spacing()

        for item in self.items:
            item_width: int = item.sizeHint().width()
            item_height: int = item.sizeHint().height()

            next_x: int = x + item_width + spacing

            if next_x - spacing > rect.width():
                x = rect.x()
                y += item_height + spacing
                next_x = x + item_width + spacing

            item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size: QSize = QSize()
        for item in self.items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size
