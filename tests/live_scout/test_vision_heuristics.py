"""Tests for eye/vision_heuristics.py — game-agnostic climb + defense layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "eye"))

from vision_heuristics import (  # noqa: E402
    FrameState,
    GroundPlaneEstimator,
    RobotDetection,
    ZoneMap,
    _point_in_polygon,
    detect_climb_events,
    detect_defense_events,
)


def _robot(
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    team: int | None = None,
    alliance: str | None = None,
    track_id: int | None = None,
    conf: float = 0.9,
) -> RobotDetection:
    return RobotDetection(
        bbox=(x1, y1, x2, y2),
        confidence=conf,
        team_num=team,
        alliance=alliance,
        track_id=track_id,
    )


# ─── GroundPlaneEstimator ───


def test_ground_plane_empty_returns_none():
    gpe = GroundPlaneEstimator.from_frames([])
    assert gpe.estimate() is None


def test_ground_plane_percentile_of_bottom_ys():
    # 10 robots, bottom-Y spread from 500 to 650 (floor-ish).
    # Plus 2 outliers sitting high on the frame (climbers at Y=200).
    frames: list[FrameState] = []
    for i, y in enumerate([500, 510, 520, 530, 540, 550, 560, 570, 580, 650]):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=100, y1=y - 100, x2=200, y2=y),
        ]))
    # Add outliers — 2 climbers already up high
    frames.append(FrameState(frame_idx=100, unix_ts=100.0, robots=[
        _robot(x1=100, y1=100, x2=200, y2=200),
    ]))
    frames.append(FrameState(frame_idx=101, unix_ts=101.0, robots=[
        _robot(x1=100, y1=100, x2=200, y2=210),
    ]))

    gpe = GroundPlaneEstimator.from_frames(frames)
    # 90th percentile should pick out a floor-level Y, not a climber.
    floor = gpe.estimate(percentile=0.90)
    assert floor is not None
    # Should be well above the climber Y values (which are ~200-210).
    assert floor >= 560, f"floor={floor} looks like a climber not the floor"
    # And it should not be pushed down by outliers either.
    assert floor <= 650


def test_ground_plane_rejects_out_of_range_percentile():
    gpe = GroundPlaneEstimator(bottom_ys=[100.0])
    with pytest.raises(ValueError):
        gpe.estimate(percentile=1.5)
    with pytest.raises(ValueError):
        gpe.estimate(percentile=-0.1)


# ─── Point in polygon ───


def test_point_in_polygon_square():
    square = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    assert _point_in_polygon(50.0, 50.0, square)
    assert not _point_in_polygon(150.0, 50.0, square)
    assert not _point_in_polygon(50.0, 150.0, square)


def test_point_in_polygon_degenerate():
    assert not _point_in_polygon(1.0, 1.0, [])
    assert not _point_in_polygon(1.0, 1.0, [(0.0, 0.0), (1.0, 1.0)])


# ─── detect_climb_events ───


def test_climb_empty_frames_returns_empty():
    assert detect_climb_events(
        [], ground_plane_y=500.0, endgame_start_unix=100.0,
    ) == []


def test_climb_success_robot_leaves_ground_and_stays_up():
    # Floor Y = 500. Robot starts on floor (bbox bottom=500), then
    # rises to bbox bottom=300 (200 px above floor) at frame 10.
    frames: list[FrameState] = []
    # Pre-endgame: 5 frames on the floor
    for i in range(5):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=100, y1=400, x2=200, y2=500, track_id=42, team=2950),
        ]))
    # Endgame starts at unix_ts=5. Robot stays on floor for 2 more
    # frames, then rises to bbox bottom=300 for 4 frames.
    for i in range(5, 7):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=100, y1=400, x2=200, y2=500, track_id=42, team=2950),
        ]))
    for i in range(7, 11):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=100, y1=200, x2=200, y2=300, track_id=42, team=2950),
        ]))

    events = detect_climb_events(
        frames,
        ground_plane_y=500.0,
        endgame_start_unix=5.0,
        threshold_px=80.0,
        persist_frames=3,
    )
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "climb_success"
    assert e.team_num == 2950


def test_climb_attempt_robot_rises_then_falls():
    # Floor Y = 500. Robot rises to 300 for 3 frames, then comes back
    # to 500 at match end → climb_attempt (not success).
    frames: list[FrameState] = []
    # Endgame the whole time for simplicity.
    for i, y2 in enumerate([500, 300, 300, 300, 500]):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=100, y1=y2 - 100, x2=200, y2=y2, track_id=7, team=148),
        ]))

    events = detect_climb_events(
        frames,
        ground_plane_y=500.0,
        endgame_start_unix=0.0,
        threshold_px=80.0,
        persist_frames=3,
    )
    assert len(events) == 1
    assert events[0].event_type == "climb_attempt"
    assert events[0].team_num == 148


def test_climb_no_event_if_never_above_threshold():
    # Robot wobbles but never rises more than 50 px above floor.
    frames: list[FrameState] = []
    for i, y2 in enumerate([500, 480, 490, 500, 485]):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=100, y1=y2 - 100, x2=200, y2=y2, track_id=9, team=1678),
        ]))
    events = detect_climb_events(
        frames,
        ground_plane_y=500.0,
        endgame_start_unix=0.0,
        threshold_px=80.0,
        persist_frames=3,
    )
    assert events == []


def test_climb_requires_persist_frames():
    # Only 1 frame above floor; persist_frames=3 → no event.
    frames: list[FrameState] = []
    for i, y2 in enumerate([500, 500, 300, 500, 500]):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=100, y1=y2 - 100, x2=200, y2=y2, track_id=1, team=1),
        ]))
    events = detect_climb_events(
        frames,
        ground_plane_y=500.0,
        endgame_start_unix=0.0,
        threshold_px=80.0,
        persist_frames=3,
    )
    assert events == []


def test_climb_multiple_robots_independent():
    # Two robots with different fates in the same match.
    frames: list[FrameState] = []
    for i in range(6):
        robots = [
            # Robot A: climbs and stays up from frame 2 onward.
            _robot(x1=100, y1=200, x2=200, y2=300, track_id=1, team=2950)
            if i >= 2 else
            _robot(x1=100, y1=400, x2=200, y2=500, track_id=1, team=2950),
            # Robot B: stays on floor the whole time.
            _robot(x1=300, y1=400, x2=400, y2=500, track_id=2, team=148),
        ]
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=robots))

    events = detect_climb_events(
        frames,
        ground_plane_y=500.0,
        endgame_start_unix=0.0,
        threshold_px=80.0,
        persist_frames=3,
    )
    # Only robot A produces a climb event.
    assert len(events) == 1
    assert events[0].team_num == 2950
    assert events[0].event_type == "climb_success"


# ─── detect_defense_events ───


def _zone_map() -> ZoneMap:
    return ZoneMap(
        red_scoring_zone=[
            (0.0, 0.0), (500.0, 0.0), (500.0, 500.0), (0.0, 500.0),
        ],
        blue_scoring_zone=[
            (500.0, 0.0), (1000.0, 0.0), (1000.0, 500.0), (500.0, 500.0),
        ],
    )


def test_defense_empty_returns_empty():
    assert detect_defense_events([], zone_map=_zone_map()) == []


def test_defense_red_robot_in_blue_zone_persistently():
    # Red robot team 2950 sits in the blue scoring zone (x>500) for
    # 6 consecutive frames → defense event.
    frames: list[FrameState] = []
    for i in range(6):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(
                x1=700, y1=200, x2=800, y2=300,
                track_id=10, team=2950, alliance="red",
            ),
        ]))
    events = detect_defense_events(
        frames, zone_map=_zone_map(), persist_frames=5,
    )
    assert len(events) == 1
    assert events[0].event_type == "defense"
    assert events[0].team_num == 2950


def test_defense_not_emitted_for_robot_in_own_zone():
    # Red robot sits in the RED zone — that's its own zone, not
    # defense.
    frames: list[FrameState] = []
    for i in range(10):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(
                x1=100, y1=200, x2=200, y2=300,
                track_id=11, team=2950, alliance="red",
            ),
        ]))
    events = detect_defense_events(
        frames, zone_map=_zone_map(), persist_frames=5,
    )
    assert events == []


def test_defense_requires_persistence():
    # Red robot in blue zone for only 3 frames with persist=5 → no event.
    frames: list[FrameState] = []
    for i, x1 in enumerate([700, 700, 700, 100, 100]):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(
                x1=x1, y1=200, x2=x1 + 100, y2=300,
                track_id=12, team=148, alliance="red",
            ),
        ]))
    events = detect_defense_events(
        frames, zone_map=_zone_map(), persist_frames=5,
    )
    assert events == []


def test_defense_robot_can_have_multiple_sessions():
    # In blue zone for 5, out for 2, back in for 5 → 2 defense events.
    frames: list[FrameState] = []
    seq = [700] * 5 + [100] * 2 + [800] * 5
    for i, x1 in enumerate(seq):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(
                x1=x1, y1=200, x2=x1 + 100, y2=300,
                track_id=13, team=2056, alliance="red",
            ),
        ]))
    events = detect_defense_events(
        frames, zone_map=_zone_map(), persist_frames=5,
    )
    assert len(events) == 2
    for e in events:
        assert e.event_type == "defense"
        assert e.team_num == 2056


def test_defense_requires_alliance_by_default():
    # No alliance → skipped (we can't decide "opposing").
    frames: list[FrameState] = []
    for i in range(10):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(x1=700, y1=200, x2=800, y2=300, track_id=14, team=999),
        ]))
    events = detect_defense_events(
        frames, zone_map=_zone_map(), persist_frames=5,
    )
    assert events == []


def test_defense_blue_robot_in_red_zone():
    # Symmetric: blue robot in red zone (x<500).
    frames: list[FrameState] = []
    for i in range(8):
        frames.append(FrameState(frame_idx=i, unix_ts=float(i), robots=[
            _robot(
                x1=200, y1=200, x2=300, y2=300,
                track_id=15, team=118, alliance="blue",
            ),
        ]))
    events = detect_defense_events(
        frames, zone_map=_zone_map(), persist_frames=5,
    )
    assert len(events) == 1
    assert events[0].team_num == 118
