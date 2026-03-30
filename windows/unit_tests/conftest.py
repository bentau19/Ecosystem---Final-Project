"""
Shared pytest configuration.

The `qapp` fixture is required by any test that instantiates a QObject
(ViewModels, Repositories with signals, etc.). It ensures a single
QApplication exists for the entire test session.
"""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for the test session."""
    app = QApplication.instance() or QApplication([])
    yield app
