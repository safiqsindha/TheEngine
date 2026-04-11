"""Tests for eye/overlay_ocr.py — shared OCR helper for Live Scout.

All tests run offline by stubbing the Reader protocol and monkeypatching
the cv2 image loader, so neither PaddleOCR nor cv2 need to be importable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eye"))

import overlay_ocr  # noqa: E402
from overlay_ocr import (  # noqa: E402
    OverlayOCR,
    _is_transition_text,
    _normalize_paddle_output,
    _parse_breakdown,
)


# ─── Fake reader + image helpers ───


class FakeReader:
    """Canned-result reader. Returns the list it was constructed with
    every time readtext() is called, ignoring input."""

    def __init__(self, results):
        self.results = results
        self.calls = 0

    def readtext(self, image):
        self.calls += 1
        return list(self.results)


def _bbox(cx: float, cy: float, w: float = 20, h: float = 10) -> list[list[float]]:
    """Build an easyocr-style 4-corner bbox centered on (cx, cy)."""
    x1, y1 = cx - w / 2, cy - h / 2
    x2, y2 = cx + w / 2, cy + h / 2
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _fake_img(width: int = 1920, height: int = 1080):
    """Cheap stand-in for a cv2 image. Supports .shape and slicing, which
    is all overlay_ocr touches before handing it to the reader."""
    return np.zeros((height, width, 3), dtype=np.uint8)


# ─── _is_transition_text ───


def test_transition_text_matches_alliance_wins():
    assert _is_transition_text("RED ALLIANCE WINS")
    assert _is_transition_text("THE BLUE ALLIANCE WINS THE MATCH")


def test_transition_text_rejects_partial_matches():
    assert not _is_transition_text("RED WINS")               # missing ALLIANCE
    assert not _is_transition_text("ALLIANCE SELECTION")     # missing WINS
    assert not _is_transition_text("")


# ─── _parse_breakdown ───


def test_parse_breakdown_rejects_unrelated_text():
    results = [(_bbox(100, 100), "MATCH 32", 0.9)]
    out = _parse_breakdown(results, 1920, 1080)
    assert out == {"is_breakdown": False}


def test_parse_breakdown_detects_winner_and_teams():
    # RED side (x < 768): teams 2950 + 1234
    # BLUE side (x > 1152): teams 148 + 254
    # WINNER shows up, blue has a 100 on the right → winner=blue
    results = [
        (_bbox(300, 50),  "WINNER", 0.95),
        (_bbox(300, 100), "RED", 0.9),
        (_bbox(1600, 100), "BLUE", 0.9),
        (_bbox(300, 200), "2950", 0.9),
        (_bbox(300, 300), "1234", 0.9),
        (_bbox(1600, 200), "148", 0.9),
        (_bbox(1600, 300), "254", 0.9),
        (_bbox(1600, 400), "100", 0.9),   # blue's score, right side
        (_bbox(300, 400), "88", 0.9),     # red's score — will be filtered (<200)
    ]
    out = _parse_breakdown(results, 1920, 1080)
    assert out["is_breakdown"] is True
    assert out["teams"]["red"] == [2950, 1234]
    assert out["teams"]["blue"] == [254]   # 148 is < TEAM_NUM_MIN=200
    assert out["winner"] == "blue"


def test_parse_breakdown_uses_ranking_points_signal():
    results = [
        (_bbox(960, 50), "RANKING POINTS", 0.9),
        (_bbox(300, 100), "2950", 0.85),
    ]
    out = _parse_breakdown(results, 1920, 1080)
    assert out["is_breakdown"] is True
    assert out["teams"]["red"] == [2950]
    assert out["winner"] is None  # no WINNER keyword → unknown


def test_parse_breakdown_filters_low_confidence():
    results = [
        (_bbox(300, 100), "WINNER", 0.3),   # below MIN_CONF
        (_bbox(300, 200), "2950", 0.9),
    ]
    out = _parse_breakdown(results, 1920, 1080)
    assert out == {"is_breakdown": False}


def test_parse_breakdown_drops_non_digit_numbers():
    results = [
        (_bbox(300, 100), "WINNER", 0.9),
        (_bbox(300, 200), "2950a", 0.9),   # not a pure digit → excluded
        (_bbox(300, 300), "1234", 0.9),
    ]
    out = _parse_breakdown(results, 1920, 1080)
    assert out["teams"]["red"] == [1234]


# ─── OverlayOCR class-level behavior ───


def test_read_breakdown_screen_returns_empty_on_missing_image(monkeypatch):
    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: None)
    ocr = OverlayOCR(reader=FakeReader([]))
    assert ocr.read_breakdown_screen("/nonexistent.jpg") == {}


def test_read_breakdown_screen_parses_fake_reader_output(monkeypatch):
    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: _fake_img())
    reader = FakeReader([
        (_bbox(300, 100), "WINNER", 0.95),
        (_bbox(300, 200), "2950", 0.9),
    ])
    ocr = OverlayOCR(reader=reader)
    out = ocr.read_breakdown_screen("any.jpg")
    assert out["is_breakdown"] is True
    assert 2950 in out["teams"]["red"]
    assert reader.calls == 1


def test_is_transition_screen_true(monkeypatch):
    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: _fake_img())
    reader = FakeReader([
        (_bbox(960, 540), "RED ALLIANCE WINS", 0.95),
    ])
    ocr = OverlayOCR(reader=reader)
    assert ocr.is_transition_screen("frame.jpg") is True


def test_is_transition_screen_false(monkeypatch):
    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: _fake_img())
    reader = FakeReader([(_bbox(960, 540), "MATCH 32", 0.95)])
    ocr = OverlayOCR(reader=reader)
    assert ocr.is_transition_screen("frame.jpg") is False


def test_is_transition_screen_returns_false_on_missing_image(monkeypatch):
    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: None)
    ocr = OverlayOCR(reader=FakeReader([]))
    assert ocr.is_transition_screen("gone.jpg") is False


def test_read_top_overlay_joins_high_confidence_tokens(monkeypatch):
    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: _fake_img())
    reader = FakeReader([
        (_bbox(100, 20), "RED", 0.9),
        (_bbox(200, 20), "88", 0.9),
        (_bbox(300, 20), "BLUE", 0.9),
        (_bbox(400, 20), "72", 0.9),
        (_bbox(500, 20), "noise", 0.2),   # below MIN_SELECT_CONF, filtered out
    ])
    ocr = OverlayOCR(reader=reader)
    text = ocr.read_top_overlay("frame.jpg")
    assert text == "RED 88 BLUE 72"


def test_read_top_overlay_returns_empty_on_missing_image(monkeypatch):
    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: None)
    ocr = OverlayOCR(reader=FakeReader([]))
    assert ocr.read_top_overlay("gone.jpg") == ""


def test_detect_match_boundaries_emits_events_in_order(monkeypatch):
    """Frame 0 is neither, frame 1 is a transition, frame 2 is a breakdown."""
    frames = [
        {"path": "f0.jpg", "timestamp_s": 0},
        {"path": "f1.jpg", "timestamp_s": 10},
        {"path": "f2.jpg", "timestamp_s": 20},
    ]

    monkeypatch.setattr(overlay_ocr, "_imread", lambda p: _fake_img())

    state = {"count": 0}

    def side_effect(image):
        # is_transition_screen hits this once per frame (on a cropped image),
        # read_breakdown_screen hits it again per frame.
        state["count"] += 1
        return []

    class ScriptedReader:
        def readtext(self, image):
            # We can't easily distinguish transition vs breakdown calls from
            # image contents, so drive behavior via the patched methods below.
            return []

    # Rather than dual-dispatching through the reader, patch the two class
    # methods so we have explicit control over what each frame classifies as.
    classifications = {
        "f0.jpg": {"transition": False, "breakdown": {"is_breakdown": False}},
        "f1.jpg": {"transition": True,  "breakdown": {"is_breakdown": False}},
        "f2.jpg": {"transition": False, "breakdown": {"is_breakdown": True, "teams": {"red": [2950], "blue": [148]}}},
    }

    def fake_is_transition(self, path):
        return classifications[Path(path).name]["transition"]

    def fake_read_breakdown(self, path):
        return classifications[Path(path).name]["breakdown"]

    monkeypatch.setattr(OverlayOCR, "is_transition_screen", fake_is_transition)
    monkeypatch.setattr(OverlayOCR, "read_breakdown_screen", fake_read_breakdown)

    ocr = OverlayOCR(reader=ScriptedReader())
    events = ocr.detect_match_boundaries(frames)

    assert [e["type"] for e in events] == ["transition", "breakdown"]
    assert [e["frame_idx"] for e in events] == [1, 2]
    assert events[1]["data"]["teams"]["red"] == [2950]


# ─── _normalize_paddle_output adapter ───


def test_normalize_paddle_legacy_ocr_shape():
    """Legacy PaddleOCR .ocr() output: [[[bbox, (text, conf)], ...]]"""
    raw = [
        [
            [_bbox(100, 100), ("WINNER", 0.98)],
            [_bbox(200, 200), ("2950", 0.95)],
        ]
    ]
    out = _normalize_paddle_output(raw)
    assert len(out) == 2
    assert out[0][1] == "WINNER"
    assert out[0][2] == pytest.approx(0.98)
    assert out[1][1] == "2950"


def test_normalize_paddle_predict_dict_shape():
    """Newer PaddleOCR .predict() output: per-page dict/obj with rec_* fields"""
    raw = [
        {
            "rec_polys": [_bbox(100, 100), _bbox(200, 200)],
            "rec_texts": ["WINNER", "2950"],
            "rec_scores": [0.98, 0.95],
        }
    ]
    out = _normalize_paddle_output(raw)
    assert len(out) == 2
    assert out[0][1] == "WINNER"
    assert out[1][1] == "2950"
    assert out[0][2] == pytest.approx(0.98)


def test_normalize_paddle_predict_object_shape():
    """Newer .predict() can also return attribute-accessed objects."""
    page = SimpleNamespace(
        rec_polys=[_bbox(100, 100)],
        rec_texts=["WINNER"],
        rec_scores=[0.99],
    )
    out = _normalize_paddle_output([page])
    assert len(out) == 1
    assert out[0][1] == "WINNER"


def test_normalize_paddle_handles_none_and_empty():
    assert _normalize_paddle_output(None) == []
    assert _normalize_paddle_output([]) == []
    assert _normalize_paddle_output([None]) == []
