"""Tests for eye/match_boundary.py — Phase 2 U1.

Hermetic — uses a FakeOCR that returns scripted boundary events, no
PaddleOCR or cv2 import.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eye"))

from match_boundary import (  # noqa: E402
    MatchBoundary,
    MatchBoundaryDetector,
    ScheduleAlignmentResult,
    detect_boundaries_from_frames,
    validate_against_tba_schedule,
)


# ─── Fakes ───


class FakeOCR:
    def __init__(self, events):
        self.events = events
        self.call_count = 0

    def detect_match_boundaries(self, frames):
        self.call_count += 1
        return list(self.events)


def _frames(n, fps_interval=3.0):
    return [{"path": f"frame_{i:04d}.jpg", "timestamp_s": i * fps_interval} for i in range(n)]


# ─── MatchBoundary dataclass ───


def test_match_boundary_round_trip():
    b = MatchBoundary(
        start_frame_idx=0, end_frame_idx=50,
        start_timestamp_s=0.0, end_timestamp_s=150.0,
        video_key="abc123", match_key="2026txbel_qm1",
        comp_level="qm", match_num=1,
    )
    d = b.to_dict()
    assert d["match_key"] == "2026txbel_qm1"
    rebuilt = MatchBoundary.from_dict(d)
    assert rebuilt.to_dict() == d


def test_match_boundary_rejects_negative_start():
    with pytest.raises(ValueError, match="start_frame_idx"):
        MatchBoundary(
            start_frame_idx=-1, end_frame_idx=5,
            start_timestamp_s=0.0, end_timestamp_s=15.0,
            video_key="v",
        )


def test_match_boundary_rejects_end_before_start():
    with pytest.raises(ValueError, match="end_frame_idx"):
        MatchBoundary(
            start_frame_idx=10, end_frame_idx=5,
            start_timestamp_s=30.0, end_timestamp_s=15.0,
            video_key="v",
        )


def test_match_boundary_rejects_end_timestamp_before_start():
    with pytest.raises(ValueError, match="end_timestamp_s"):
        MatchBoundary(
            start_frame_idx=0, end_frame_idx=5,
            start_timestamp_s=30.0, end_timestamp_s=15.0,
            video_key="v",
        )


def test_match_boundary_rejects_bad_boundary_type():
    with pytest.raises(ValueError, match="boundary_type"):
        MatchBoundary(
            start_frame_idx=0, end_frame_idx=5,
            start_timestamp_s=0.0, end_timestamp_s=15.0,
            video_key="v", boundary_type="wat",
        )


# ─── Detector ───


def test_detector_rejects_zero_total_frames():
    with pytest.raises(ValueError, match="total_frames"):
        MatchBoundaryDetector(
            video_key="v", total_frames=0, frame_timestamps=[],
        )


def test_detector_rejects_mismatched_timestamps():
    with pytest.raises(ValueError, match="frame_timestamps"):
        MatchBoundaryDetector(
            video_key="v", total_frames=5, frame_timestamps=[0.0, 1.0],
        )


def test_detector_single_breakdown_emits_one_segment_plus_tail():
    det = MatchBoundaryDetector(
        video_key="v", total_frames=20,
        frame_timestamps=[i * 3.0 for i in range(20)],
    )
    segments = det.process([
        {"frame_idx": 10, "timestamp_s": 30.0, "type": "breakdown"},
    ])
    assert len(segments) == 2
    assert segments[0].start_frame_idx == 0
    assert segments[0].end_frame_idx == 10
    assert segments[0].boundary_type == "breakdown"
    # Tail segment is the "final" type
    assert segments[1].start_frame_idx == 11
    assert segments[1].end_frame_idx == 19
    assert segments[1].boundary_type == "final"


def test_detector_collapses_transition_after_breakdown():
    det = MatchBoundaryDetector(
        video_key="v", total_frames=30,
        frame_timestamps=[i * 2.0 for i in range(30)],
    )
    segments = det.process([
        {"frame_idx": 5, "timestamp_s": 10.0, "type": "breakdown"},
        {"frame_idx": 6, "timestamp_s": 12.0, "type": "transition"},  # collapsed
        {"frame_idx": 15, "timestamp_s": 30.0, "type": "breakdown"},
        {"frame_idx": 16, "timestamp_s": 32.0, "type": "transition"},  # collapsed
    ])
    # Two breakdowns + one tail = 3 segments
    assert [s.boundary_type for s in segments] == ["breakdown", "breakdown", "final"]
    # The second segment starts right after the first breakdown (frame 6),
    # because the transition that followed was collapsed.
    assert segments[1].start_frame_idx == 6
    assert segments[1].end_frame_idx == 15


def test_detector_transition_only_pattern():
    """Some broadcasts show only transitions, no breakdowns."""
    det = MatchBoundaryDetector(
        video_key="v", total_frames=30,
        frame_timestamps=[i for i in range(30)],
    )
    segments = det.process([
        {"frame_idx": 10, "timestamp_s": 10.0, "type": "transition"},
        {"frame_idx": 20, "timestamp_s": 20.0, "type": "transition"},
    ])
    assert [s.boundary_type for s in segments] == ["transition", "transition", "final"]


def test_detector_drops_out_of_range_events():
    det = MatchBoundaryDetector(
        video_key="v", total_frames=10,
        frame_timestamps=[float(i) for i in range(10)],
    )
    segments = det.process([
        {"frame_idx": -1, "type": "breakdown"},  # dropped
        {"frame_idx": 99, "type": "breakdown"},  # dropped
        {"frame_idx": 5, "timestamp_s": 5.0, "type": "breakdown"},
    ])
    assert len(segments) == 2  # one real + one tail
    assert segments[0].end_frame_idx == 5


def test_detector_drops_non_boundary_events():
    det = MatchBoundaryDetector(
        video_key="v", total_frames=10,
        frame_timestamps=[float(i) for i in range(10)],
    )
    segments = det.process([
        {"frame_idx": 3, "type": "random_unknown_event"},
        {"frame_idx": 5, "timestamp_s": 5.0, "type": "breakdown"},
    ])
    assert len(segments) == 2
    assert segments[0].start_frame_idx == 0
    assert segments[0].end_frame_idx == 5


def test_detector_skips_tiny_tail():
    """If the last boundary is right at the last frame, the tail
    segment would be a single-frame-or-nothing sliver — don't emit it."""
    det = MatchBoundaryDetector(
        video_key="v", total_frames=10,
        frame_timestamps=[float(i) for i in range(10)],
    )
    segments = det.process([
        {"frame_idx": 9, "timestamp_s": 9.0, "type": "breakdown"},
    ])
    assert len(segments) == 1
    assert segments[0].end_frame_idx == 9


# ─── High-level entry point ───


def test_detect_boundaries_from_frames_end_to_end():
    frames = _frames(20)
    ocr = FakeOCR([
        {"frame_idx": 8, "timestamp_s": 24.0, "type": "breakdown"},
        {"frame_idx": 9, "timestamp_s": 27.0, "type": "transition"},
        {"frame_idx": 16, "timestamp_s": 48.0, "type": "breakdown"},
    ])
    segments = detect_boundaries_from_frames(frames, ocr=ocr, video_key="yt_abc")
    assert len(segments) == 3
    assert all(s.video_key == "yt_abc" for s in segments)
    assert ocr.call_count == 1


def test_detect_boundaries_empty_frames_short_circuits():
    ocr = FakeOCR([])
    assert detect_boundaries_from_frames([], ocr=ocr, video_key="v") == []
    assert ocr.call_count == 0


# ─── TBA schedule alignment ───


def _b(start, end, ts_start, ts_end, **kw):
    return MatchBoundary(
        start_frame_idx=start, end_frame_idx=end,
        start_timestamp_s=ts_start, end_timestamp_s=ts_end,
        video_key="v", **kw,
    )


def _tba(comp_level, match_num, set_num=None):
    out = {"comp_level": comp_level, "match_number": match_num}
    if set_num is not None:
        out["set_number"] = set_num
    return out


def test_align_one_to_one_happy_path():
    boundaries = [_b(0, 10, 0, 30), _b(11, 20, 33, 60), _b(21, 30, 63, 90)]
    schedule = [_tba("qm", 1), _tba("qm", 2), _tba("qm", 3)]
    result = validate_against_tba_schedule(
        boundaries, schedule, event_key="2026txbel"
    )
    assert [b.match_key for b in result.aligned] == [
        "2026txbel_qm1", "2026txbel_qm2", "2026txbel_qm3",
    ]
    assert result.extra_boundaries == 0
    assert result.missing_matches == []


def test_align_sorts_schedule_deterministically():
    boundaries = [_b(0, 10, 0, 30), _b(11, 20, 33, 60)]
    # TBA returned in reverse order
    schedule = [_tba("qm", 2), _tba("qm", 1)]
    result = validate_against_tba_schedule(
        boundaries, schedule, event_key="2026txbel"
    )
    assert [b.match_num for b in result.aligned] == [1, 2]


def test_align_reports_extra_boundaries():
    boundaries = [_b(0, 10, 0, 30), _b(11, 20, 33, 60), _b(21, 30, 63, 90)]
    schedule = [_tba("qm", 1), _tba("qm", 2)]
    result = validate_against_tba_schedule(
        boundaries, schedule, event_key="2026txbel"
    )
    assert len(result.aligned) == 2
    assert result.extra_boundaries == 1


def test_align_reports_missing_matches():
    boundaries = [_b(0, 10, 0, 30)]
    schedule = [_tba("qm", 1), _tba("qm", 2), _tba("qm", 3)]
    result = validate_against_tba_schedule(
        boundaries, schedule, event_key="2026txbel"
    )
    assert [b.match_key for b in result.aligned] == ["2026txbel_qm1"]
    assert result.missing_matches == ["2026txbel_qm2", "2026txbel_qm3"]


def test_align_filters_non_qm_by_default():
    boundaries = [_b(0, 10, 0, 30)]
    schedule = [_tba("qm", 1), _tba("qf", 1, set_num=1), _tba("qm", 2)]
    result = validate_against_tba_schedule(
        boundaries, schedule, event_key="2026txbel"
    )
    # Only 2 qm entries → 1 aligned + 1 missing, qf ignored
    assert [b.match_key for b in result.aligned] == ["2026txbel_qm1"]
    assert result.missing_matches == ["2026txbel_qm2"]


def test_align_supports_playoffs():
    boundaries = [_b(0, 10, 0, 30), _b(11, 20, 33, 60)]
    schedule = [
        _tba("qf", 1, set_num=1),
        _tba("qf", 1, set_num=2),
    ]
    result = validate_against_tba_schedule(
        boundaries, schedule, event_key="2026txbel",
        comp_levels=("qf",),
    )
    keys = [b.match_key for b in result.aligned]
    assert keys == ["2026txbel_qf1m1", "2026txbel_qf2m1"]


def test_align_result_to_dict_round_trip():
    result = ScheduleAlignmentResult(
        aligned=[_b(0, 5, 0, 15, match_key="2026txbel_qm1", comp_level="qm", match_num=1)],
        extra_boundaries=2,
        missing_matches=["2026txbel_qm5"],
    )
    d = result.to_dict()
    assert d["extra_boundaries"] == 2
    assert len(d["aligned"]) == 1
    assert d["missing_matches"] == ["2026txbel_qm5"]
