"""Metaclass utilities for combining Qt and Python abstract base classes."""

from abc import ABCMeta

from PySide6.QtCore import QObject

QObjectMeta = type(QObject)


class ABCQObjectMeta(QObjectMeta, ABCMeta):
    """Combined metaclass that satisfies both QObject and ABCMeta.

    PySide6's ``QObject`` uses its own C++-backed metaclass (``Shiboken``),
    which conflicts with Python's ``ABCMeta`` when you try to inherit from
    both ``QObject`` and ``ABC`` in the same class.  This merged metaclass
    resolves the MRO conflict so repositories and other classes can be both
    a ``QObject`` (for signals) and an abstract base class simultaneously.

    Usage::

        class MyRepo(IRepo, QObject, metaclass=ABCQObjectMeta):
            ...
    """

