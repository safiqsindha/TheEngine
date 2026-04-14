"""Root conftest.py — adds project root to sys.path for all tests."""
import sys
from pathlib import Path

# Ensure the project root is on sys.path so all packages (pitcrew, antenna, etc.)
# are importable regardless of how pytest is invoked.
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
