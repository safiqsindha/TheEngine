"""
The Engine — Centralized Logging Configuration
Team 2950 — The Devastators

Provides a single setup_logging() helper consumed by library modules.
CLI entry points (the_scout.py, the_eye.py, live_scout_commands.py) may
call setup_logging() at startup to configure the root logger; library
modules simply call logging.getLogger(__name__) and emit records.

Usage (library module):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("fetching data for %s", event_key)

Usage (CLI entry point):
    from engine.logging_config import setup_logging
    setup_logging(level=logging.INFO)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


_DEFAULT_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    fmt: str = _DEFAULT_FORMAT,
) -> None:
    """Configure the root logger with a timestamp + level + module formatter.

    Parameters
    ----------
    level : int
        Root logging level (e.g. logging.DEBUG, logging.INFO).
    log_file : str | None
        Optional path to a file handler.  When None only stdout is used.
    fmt : str
        Log format string passed to logging.Formatter.

    Notes
    -----
    Safe to call multiple times — subsequent calls are no-ops once handlers
    are already attached to the root logger.
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured — don't duplicate handlers.
        return

    root.setLevel(level)
    formatter = logging.Formatter(fmt, datefmt=_DATE_FORMAT)

    # Console handler — always emit to stdout (not stderr) so Discord bots
    # and subprocess callers see the output on the normal channel.
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(Path(log_file), encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        root.addHandler(fh)
