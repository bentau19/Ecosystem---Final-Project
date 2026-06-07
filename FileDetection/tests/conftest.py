"""
Pytest configuration for FileDetection tests.

Inserts the FileDetection/ package root onto sys.path so that all bare-module
imports (e.g. ``from checkers.registry import get_checker``) resolve
regardless of where pytest is invoked from.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
