"""
tests/pitcrew/conftest.py

Ensures the project root is on sys.path so `pitcrew` package is importable
without conflicting with the tests/pitcrew directory.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
