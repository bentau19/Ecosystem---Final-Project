from abc import ABCMeta, ABC

from PySide6.QtCore import QObject

QObjectMeta = type(QObject)

class ABCQObjectMeta(QObjectMeta, ABCMeta):...

