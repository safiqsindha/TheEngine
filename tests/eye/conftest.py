"""
tests/eye/conftest.py

Installs a lightweight overlay_ocr stub for the eye-module tests, then
restores the original (or removes the stub) after the test session ends.

This prevents the stub from leaking into scout/ tests that need the real
overlay_ocr with _parse_breakdown and _is_transition_text.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Lightweight overlay_ocr stub — no PaddleOCR / cv2 required
# ---------------------------------------------------------------------------

def _make_stub() -> types.ModuleType:
    mod = types.ModuleType("overlay_ocr")

    class _FakeOverlayOCR:
        def read_breakdown_screen(self, path):
            return {"is_breakdown": False}

        def read_top_overlay(self, path):
            return ""

        def is_transition_screen(self, path):
            return False

    mod.OverlayOCR = _FakeOverlayOCR
    # Add stubs for any private helpers the scout tests need
    mod._parse_breakdown = lambda *a, **kw: {}
    mod._is_transition_text = lambda *a, **kw: False
    return mod


# ---------------------------------------------------------------------------
# Session-scoped fixture — install stub once, restore at session end
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def _install_overlay_ocr_stub():
    """Install stub before any eye test runs; restore original at session end."""
    _original = sys.modules.get("overlay_ocr")
    sys.modules["overlay_ocr"] = _make_stub()
    yield
    if _original is None:
        sys.modules.pop("overlay_ocr", None)
    else:
        sys.modules["overlay_ocr"] = _original
