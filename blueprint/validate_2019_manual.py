"""Backward-compat shim — delegates to ``blueprint/validate_manual.py``.

The multi-year driver is the source of truth; this wrapper preserves the
old entry point so existing docs (``design-intelligence/MANUAL_PARSER_VALIDATION.md``)
still work.

Usage::

    export ANTHROPIC_API_KEY=sk-ant-...
    python blueprint/validate_2019_manual.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from blueprint.validate_manual import run  # noqa: E402


def main() -> int:
    return run(2019)


if __name__ == "__main__":
    sys.exit(main())
