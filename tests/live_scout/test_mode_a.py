"""Tests for workers/mode_a.py — W2 Mode A worker.

All tests run offline. The TBA fetcher and frame source are injected as
fakes; the OverlayOCR instance is replaced with a FakeOCR that returns
canned breakdown dicts so we never load PaddleOCR or touch real images.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.mode_a import (  # noqa: E402
    OCRResult,
    build_live_match_from_ocr,
    build_match_key,
    find_target_match,
    parse_match_short,
    run_mode_a,
    scan_frames_for_breakdown,
    teams_from_tba_match,
)


# ─── Fixtures ───


def _tba_match(
    *,
    comp_level: str = "qm",
    match_number: int,
    set_number: Optional[int] = None,
    red_teams: list[int],
    blue_teams: list[int],
    red_score: int = -1,
    blue_score: int = -1,
    actual_time: int = 0,
) -> dict:
    return {
        "comp_level": comp_level,
        "match_number": match_number,
        "set_number": set_number,
        "actual_time": actual_time,
        "alliances": {
            "red": {
                "team_keys": [f"frc{t}" for t in red_teams],
                "score": red_score,
            },
            "blue": {
                "team_keys": [f"frc{t}" for t in blue_teams],
                "score": blue_score,
            },
        },
    }


class FakeOCR:
    """OverlayOCR stand-in. Returns canned breakdown dicts keyed by frame path."""
    def __init__(self, by_path: dict[str, dict]):
        self._by_path = by_path

    def read_breakdown_screen(self, frame_path: str) -> dict:
        return self._by_path.get(str(frame_path), {"is_breakdown": False})


# ─── parse_match_short / build_match_key ───


def test_parse_match_short_qm():
    assert parse_match_short("qm32") == ("qm", 32, None)


def test_parse_match_short_quarterfinal():
    assert parse_match_short("qf1m1") == ("qf", 1, 1)


def test_parse_match_short_semifinal():
    assert parse_match_short("sf2m3") == ("sf", 3, 2)


def test_parse_match_short_final():
    assert parse_match_short("f1m2") == ("f", 2, 1)


def test_parse_match_short_rejects_garbage():
    with pytest.raises(ValueError, match="unrecognized"):
        parse_match_short("playoff_5")
    with pytest.raises(ValueError, match="unrecognized"):
        parse_match_short("QM32")  # uppercase


def test_build_match_key_qm():
    assert build_match_key("2026txbel", "qm", 32) == "2026txbel_qm32"


def test_build_match_key_playoff():
    assert build_match_key("2026txbel", "qf", 1, set_num=1) == "2026txbel_qf1m1"
    assert build_match_key("2026txbel", "sf", 3, set_num=2) == "2026txbel_sf2m3"


def test_build_match_key_playoff_requires_set_num():
    with pytest.raises(ValueError, match="set_num"):
        build_match_key("2026txbel", "qf", 1)


# ─── teams_from_tba_match ───


def test_teams_from_tba_match_strips_frc_prefix_preserves_order():
    m = _tba_match(match_number=1, red_teams=[2950, 1234, 5678], blue_teams=[148, 254, 1678])
    red, blue = teams_from_tba_match(m)
    assert red == [2950, 1234, 5678]
    assert blue == [148, 254, 1678]


def test_teams_from_tba_match_handles_missing_alliances():
    red, blue = teams_from_tba_match({})
    assert red == [] and blue == []


# ─── find_target_match ───


def _qm(num: int, *, red, blue, red_score=-1, blue_score=-1, actual_time=0):
    return _tba_match(
        match_number=num,
        red_teams=red, blue_teams=blue,
        red_score=red_score, blue_score=blue_score,
        actual_time=actual_time,
    )


def test_find_target_match_explicit_qm_hit():
    matches = [
        _qm(31, red=[2950], blue=[148]),
        _qm(32, red=[2950], blue=[254]),
        _qm(33, red=[2950], blue=[1678]),
    ]
    out = find_target_match(matches, explicit_short="qm32")
    assert out is not None
    assert out["match_number"] == 32


def test_find_target_match_explicit_miss_returns_none():
    matches = [_qm(31, red=[2950], blue=[148])]
    assert find_target_match(matches, explicit_short="qm99") is None


def test_find_target_match_explicit_playoff():
    matches = [
        _tba_match(comp_level="qf", match_number=1, set_number=1,
                   red_teams=[2950], blue_teams=[148]),
        _tba_match(comp_level="qf", match_number=1, set_number=2,
                   red_teams=[2881], blue_teams=[254]),
    ]
    out = find_target_match(matches, explicit_short="qf2m1")
    assert out is not None
    assert out["set_number"] == 2


def test_find_target_match_picks_most_recent_finalized_qm():
    """When no explicit short is given, prefer the qm with the latest
    actual_time that has both scores set."""
    matches = [
        _qm(30, red=[2950], blue=[148], red_score=80, blue_score=70, actual_time=1000),
        _qm(31, red=[2950], blue=[148], red_score=85, blue_score=72, actual_time=2000),
        _qm(32, red=[2950], blue=[148]),  # not finalized
    ]
    out = find_target_match(matches)
    assert out["match_number"] == 31


def test_find_target_match_falls_back_to_match_number_when_actual_time_missing():
    matches = [
        _qm(30, red=[2950], blue=[148], red_score=80, blue_score=70),
        _qm(31, red=[2950], blue=[148], red_score=85, blue_score=72),
    ]
    out = find_target_match(matches)
    assert out["match_number"] == 31


def test_find_target_match_returns_none_when_nothing_finalized():
    matches = [_qm(30, red=[2950], blue=[148])]
    assert find_target_match(matches) is None


def test_find_target_match_skips_playoff_in_default_mode():
    """Default-mode picker is qm-only — playoffs are out of scope for Mode A
    autonomous selection."""
    matches = [
        _tba_match(comp_level="qf", match_number=1, set_number=1,
                   red_teams=[2950], blue_teams=[148],
                   red_score=120, blue_score=90, actual_time=5000),
        _qm(20, red=[2950], blue=[148], red_score=80, blue_score=70, actual_time=1000),
    ]
    out = find_target_match(matches)
    assert out["comp_level"] == "qm"
    assert out["match_number"] == 20


# ─── scan_frames_for_breakdown ───


def test_scan_returns_first_complete_breakdown(tmp_path):
    f0 = tmp_path / "frame_0001.jpg"
    f1 = tmp_path / "frame_0002.jpg"
    f2 = tmp_path / "frame_0003.jpg"
    for f in (f0, f1, f2):
        f.write_bytes(b"")  # placeholder

    ocr = FakeOCR({
        str(f0): {"is_breakdown": False},
        str(f1): {"is_breakdown": True, "scores": {"red": 88, "blue": 72},
                  "winner": "red", "teams": {"red": [2950], "blue": [148]}},
        str(f2): {"is_breakdown": True, "scores": {"red": 88, "blue": 72},
                  "winner": "red", "teams": {"red": [2950], "blue": [148]}},
    })
    result = scan_frames_for_breakdown([f0, f1, f2], ocr)
    assert result.breakdown_found is True
    assert result.red_score == 88
    assert result.blue_score == 72
    assert result.winner == "red"
    assert result.breakdown_frame == f1
    assert result.confidence > 0.5


def test_scan_skips_partial_breakdown_frames(tmp_path):
    """A breakdown screen with only one side's score (fade-in / glitch)
    should be skipped — keep scanning."""
    f0 = tmp_path / "frame_0001.jpg"
    f1 = tmp_path / "frame_0002.jpg"
    for f in (f0, f1):
        f.write_bytes(b"")

    ocr = FakeOCR({
        str(f0): {"is_breakdown": True, "scores": {"red": 88, "blue": None}, "winner": None},
        str(f1): {"is_breakdown": True, "scores": {"red": 88, "blue": 72}, "winner": "red"},
    })
    result = scan_frames_for_breakdown([f0, f1], ocr)
    assert result.breakdown_frame == f1


def test_scan_returns_incomplete_when_no_breakdown_found(tmp_path):
    f0 = tmp_path / "frame_0001.jpg"
    f0.write_bytes(b"")
    ocr = FakeOCR({})
    result = scan_frames_for_breakdown([f0], ocr)
    assert result.breakdown_found is False
    assert result.red_score is None
    assert result.blue_score is None
    assert result.confidence < DEFAULT_FLOOR


DEFAULT_FLOOR = 0.5  # Test sentinel — confidence for incomplete reads should be below this


# ─── build_live_match_from_ocr ───


def test_build_live_match_from_ocr_qm_complete():
    tba = _qm(32, red=[2950, 1234, 5678], blue=[148, 254, 1678])
    ocr = OCRResult(
        breakdown_found=True,
        red_score=88, blue_score=72, winner="red",
        confidence=0.9,
    )
    lm = build_live_match_from_ocr(
        event_key="2026txbel",
        tba_match=tba,
        ocr_result=ocr,
        source_video_id="abc123",
        source_tier="live",
    )
    assert lm.match_key == "2026txbel_qm32"
    assert lm.red_teams == [2950, 1234, 5678]
    assert lm.blue_teams == [148, 254, 1678]
    assert lm.red_score == 88
    assert lm.blue_score == 72
    assert lm.winning_alliance == "red"
    assert lm.timer_state == "post"
    assert lm.source_tier == "live"
    assert lm.confidence == pytest.approx(0.9)


def test_build_live_match_from_ocr_incomplete_match():
    tba = _qm(32, red=[2950, 1234, 5678], blue=[148, 254, 1678])
    ocr = OCRResult(
        breakdown_found=False,
        red_score=None, blue_score=None, winner=None,
        confidence=0.4,
    )
    lm = build_live_match_from_ocr(
        event_key="2026txbel",
        tba_match=tba,
        ocr_result=ocr,
        source_video_id="abc123",
        source_tier="live",
    )
    assert lm.red_score is None
    assert lm.blue_score is None
    assert lm.timer_state == "teleop"
    assert not lm.is_complete


def test_build_live_match_from_ocr_playoff():
    tba = _tba_match(
        comp_level="qf", match_number=1, set_number=2,
        red_teams=[2950, 1234, 5678], blue_teams=[148, 254, 1678],
    )
    ocr = OCRResult(True, 120, 90, "red", confidence=0.9)
    lm = build_live_match_from_ocr(
        event_key="2026txbel",
        tba_match=tba,
        ocr_result=ocr,
        source_video_id="abc123",
        source_tier="vod",
    )
    assert lm.match_key == "2026txbel_qf2m1"
    assert lm.comp_level == "qf"


def test_build_live_match_from_ocr_validates_via_dataclass():
    """Bad TBA data should raise ValueError via LiveMatch.__post_init__."""
    tba = _qm(32, red=[2950, 0, 5678], blue=[148, 254, 1678])  # 0 is not a valid team
    ocr = OCRResult(True, 88, 72, "red", confidence=0.9)
    with pytest.raises(ValueError, match="red_teams"):
        build_live_match_from_ocr(
            event_key="2026txbel",
            tba_match=tba,
            ocr_result=ocr,
            source_video_id="abc",
            source_tier="live",
        )


# ─── run_mode_a end-to-end with stubs ───


def test_run_mode_a_full_pipeline_with_stubs(tmp_path):
    """End-to-end: stub TBA, stub frames, fake OCR. Verify the LiveMatch
    written matches expectations."""
    f0 = tmp_path / "frame_0001.jpg"
    f1 = tmp_path / "frame_0002.jpg"
    for f in (f0, f1):
        f.write_bytes(b"")

    matches = [
        _qm(31, red=[2950, 1234, 5678], blue=[148, 254, 1678],
            red_score=80, blue_score=70, actual_time=1000),
        _qm(32, red=[2950, 1234, 5678], blue=[148, 254, 1678],
            red_score=88, blue_score=72, actual_time=2000),
    ]

    fake_ocr = FakeOCR({
        str(f1): {
            "is_breakdown": True,
            "scores": {"red": 88, "blue": 72},
            "winner": "red",
            "teams": {"red": [2950, 1234, 5678], "blue": [148, 254, 1678]},
        },
    })

    lm = run_mode_a(
        event_key="2026txbel",
        source_video_id="vod_xyz",
        source_tier="vod",
        frames=[f0, f1],
        ocr=fake_ocr,
        matches_fetcher=lambda ek: matches,
    )

    assert lm is not None
    # Default selection picks the most recent finalized qm — qm32
    assert lm.match_key == "2026txbel_qm32"
    assert lm.red_score == 88
    assert lm.blue_score == 72
    assert lm.winning_alliance == "red"
    assert lm.timer_state == "post"
    assert lm.source_video_id == "vod_xyz"
    assert lm.source_tier == "vod"


def test_run_mode_a_explicit_match_short(tmp_path):
    f1 = tmp_path / "frame_0001.jpg"
    f1.write_bytes(b"")

    matches = [
        _qm(31, red=[2950, 1234, 5678], blue=[148, 254, 1678],
            red_score=80, blue_score=70, actual_time=1000),
        _qm(32, red=[2950, 1234, 5678], blue=[148, 254, 1678],
            red_score=88, blue_score=72, actual_time=2000),
    ]
    fake_ocr = FakeOCR({
        str(f1): {
            "is_breakdown": True,
            "scores": {"red": 80, "blue": 70},
            "winner": "red",
        },
    })

    lm = run_mode_a(
        event_key="2026txbel",
        explicit_match_short="qm31",   # request older match by name
        source_video_id="vod_xyz",
        source_tier="vod",
        frames=[f1],
        ocr=fake_ocr,
        matches_fetcher=lambda ek: matches,
    )

    assert lm.match_key == "2026txbel_qm31"
    assert lm.red_score == 80
    assert lm.blue_score == 70


def test_run_mode_a_returns_none_when_no_target_match():
    matches = []
    lm = run_mode_a(
        event_key="2026txbel",
        source_video_id="vod_xyz",
        source_tier="vod",
        frames=[],
        ocr=FakeOCR({}),
        matches_fetcher=lambda ek: matches,
    )
    assert lm is None


def test_run_mode_a_writes_to_state_when_provided(tmp_path):
    f1 = tmp_path / "frame_0001.jpg"
    f1.write_bytes(b"")

    sys.path.insert(0, str(ROOT / "scout"))
    from pick_board import _blank_state

    state = _blank_state()
    state["event_key"] = "2026txbel"
    state["teams"] = {
        str(t): {"team": t, "name": f"Team {t}", "epa": 50.0, "sd": 10.0}
        for t in [2950, 1234, 5678, 148, 254, 1678]
    }

    matches = [
        _qm(32, red=[2950, 1234, 5678], blue=[148, 254, 1678],
            red_score=88, blue_score=72, actual_time=2000),
    ]
    fake_ocr = FakeOCR({
        str(f1): {
            "is_breakdown": True,
            "scores": {"red": 88, "blue": 72},
            "winner": "red",
        },
    })

    lm = run_mode_a(
        event_key="2026txbel",
        source_video_id="vod_xyz",
        source_tier="vod",
        frames=[f1],
        ocr=fake_ocr,
        matches_fetcher=lambda ek: matches,
        state=state,
    )

    assert lm is not None
    assert "2026txbel_qm32" in state["live_matches"]
    # Only one match → recompute_team_aggregates won't write fields (n<3 floor)
    assert "real_sd" not in state["teams"]["2950"]


def test_run_mode_a_records_incomplete_match_when_no_breakdown(tmp_path):
    """If OCR doesn't find a breakdown, we still produce a record with
    None scores and timer_state='teleop'."""
    f1 = tmp_path / "frame_0001.jpg"
    f1.write_bytes(b"")

    matches = [
        _qm(32, red=[2950, 1234, 5678], blue=[148, 254, 1678],
            red_score=88, blue_score=72, actual_time=2000),
    ]
    fake_ocr = FakeOCR({})  # nothing matches

    lm = run_mode_a(
        event_key="2026txbel",
        source_video_id="vod_xyz",
        source_tier="live",
        frames=[f1],
        ocr=fake_ocr,
        matches_fetcher=lambda ek: matches,
    )
    assert lm is not None
    assert lm.red_score is None
    assert lm.blue_score is None
    assert lm.timer_state == "teleop"
    assert not lm.is_complete
