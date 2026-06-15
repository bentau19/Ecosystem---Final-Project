import sys
from pathlib import Path

# Insert the FileDetection/ package root onto sys.path so that all
# bare-module imports (e.g. "from checkers.registry import get_checker")
# resolve regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).parent.parent))
