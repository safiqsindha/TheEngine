"""Tests for scout/auto_path_compatibility.py — Auto-Path Compatibility Scorer.

Covers:
  - Same start position → hard conflict (score 0.0)
  - Different start positions, no shared zones → fully compatible (score 1.0)
  - Shared pickup zone with no stagger → -0.5 penalty applied
  - Shared pickup zone with stagger > 2 sec → no penalty, still compatible
  - Shared scoring zone with time overlap → -0.3 penalty applied
  - Shared scoring zone without time overlap → no penalty
  - Multiple penalties accumulate (clamped to 0.0)
  - alliance_auto_compatibility: three compatible robots → mean near 1.0
  - alliance_auto_compatibility: None (missing) paths default to 0.8
  - alliance_auto_compatibility: empty list → 1.0
  - alliance_auto_compatibility: single-robot list → 1.0 (no pairs)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from auto_path_compatibility import (  # noqa: E402
    AUTO_PATH_LIBRARY,
    AutoPath,
    _DEFAULT_UNKNOWN,
    STAGGER_THRESHOLD_SEC,
    alliance_auto_compatibility,
    compatibility_score,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _path(
    team: int = 2950,
    path_id: str = "test-path",
    pickup_zones: list[str] | None = None,
    scoring_zone: str = "speaker",
    duration_sec: float = 10.0,
    start_position: str = "center",
    start_offset_sec: float = 0.0,
) -> AutoPath:
    return AutoPath(
        team_number=team,
        path_id=path_id,
        pickup_zones=pickup_zones or [],
        scoring_zone=scoring_zone,
        duration_sec=duration_sec,
        preferred_start_position=start_position,
        start_offset_sec=start_offset_sec,
    )


# ─── compatibility_score tests ───────────────────────────────────────────────


def test_same_start_position_is_hard_conflict():
    """Two robots occupying the same start position cannot both run their auto."""
    a = _path(team=2950, start_position="amp-side")
    b = _path(team=1678, start_position="amp-side")
    assert compatibility_score(a, b) == 0.0


def test_different_start_no_shared_zones_is_fully_compatible():
    """Robots at different starts with no shared pickup/scoring zones → 1.0."""
    a = _path(team=2950, start_position="amp-side", pickup_zones=["A1"], scoring_zone="amp")
    b = _path(team=1678, start_position="source-side", pickup_zones=["S1"], scoring_zone="speaker")
    assert compatibility_score(a, b) == 1.0


def test_shared_pickup_zone_no_stagger_applies_penalty():
    """Shared pickup zone with no timing stagger → 0.5 penalty → score 0.5."""
    # Use distinct scoring zones to isolate the pickup penalty.
    a = _path(team=2950, start_position="center", pickup_zones=["C1"],
              scoring_zone="amp", start_offset_sec=0.0)
    b = _path(team=1678, start_position="amp-side", pickup_zones=["C1"],
              scoring_zone="speaker", start_offset_sec=0.0)
    score = compatibility_score(a, b)
    assert score == pytest.approx(0.5)


def test_shared_pickup_zone_with_sufficient_stagger_no_penalty():
    """Stagger > STAGGER_THRESHOLD_SEC on shared pickup zone → no penalty → 1.0."""
    stagger = STAGGER_THRESHOLD_SEC + 1.0
    # Use distinct scoring zones so only pickup penalty is in play.
    a = _path(team=2950, start_position="center", pickup_zones=["C1"],
              scoring_zone="amp", start_offset_sec=0.0)
    b = _path(team=1678, start_position="amp-side", pickup_zones=["C1"],
              scoring_zone="speaker", start_offset_sec=stagger)
    score = compatibility_score(a, b)
    assert score == pytest.approx(1.0)


def test_shared_scoring_zone_overlapping_time_applies_penalty():
    """Both target same scoring zone at overlapping times → 0.3 penalty → 0.7."""
    a = _path(team=2950, start_position="center", scoring_zone="speaker",
              start_offset_sec=0.0, duration_sec=10.0)
    b = _path(team=1678, start_position="amp-side", scoring_zone="speaker",
              start_offset_sec=5.0, duration_sec=10.0)
    score = compatibility_score(a, b)
    assert score == pytest.approx(0.7)


def test_shared_scoring_zone_no_time_overlap_no_penalty():
    """Same scoring zone but no temporal overlap → no penalty → 1.0."""
    a = _path(team=2950, start_position="center", scoring_zone="speaker",
              start_offset_sec=0.0, duration_sec=5.0)
    b = _path(team=1678, start_position="amp-side", scoring_zone="speaker",
              start_offset_sec=6.0, duration_sec=5.0)
    score = compatibility_score(a, b)
    assert score == pytest.approx(1.0)


def test_multiple_penalties_accumulate_and_clamp_at_zero():
    """Same start + shared pickup + shared scoring → total > 1.0 → clamped to 0.0."""
    a = _path(
        team=2950, start_position="center", pickup_zones=["C1"],
        scoring_zone="speaker", start_offset_sec=0.0, duration_sec=10.0,
    )
    b = _path(
        team=1678, start_position="center", pickup_zones=["C1"],
        scoring_zone="speaker", start_offset_sec=0.0, duration_sec=10.0,
    )
    score = compatibility_score(a, b)
    assert score == 0.0


def test_shared_pickup_zone_stagger_exactly_at_threshold_penalizes():
    """Stagger exactly equal to threshold (not strictly greater) → penalty applied."""
    stagger = STAGGER_THRESHOLD_SEC  # exactly 2.0 → NOT > threshold → penalized
    # Use distinct scoring zones to isolate the pickup penalty.
    a = _path(team=2950, start_position="center", pickup_zones=["C1"],
              scoring_zone="amp", start_offset_sec=0.0)
    b = _path(team=1678, start_position="amp-side", pickup_zones=["C1"],
              scoring_zone="speaker", start_offset_sec=stagger)
    score = compatibility_score(a, b)
    assert score == pytest.approx(0.5)


# ─── alliance_auto_compatibility tests ───────────────────────────────────────


def test_alliance_three_compatible_robots():
    """Three robots with no shared zones at different start positions → ~1.0."""
    paths = [
        _path(team=2950, start_position="amp-side", pickup_zones=["A1"], scoring_zone="amp"),
        _path(team=1678, start_position="center", pickup_zones=["C1"], scoring_zone="speaker"),
        _path(team=254, start_position="source-side", pickup_zones=["S1"], scoring_zone="speaker",
              start_offset_sec=3.0),  # stagger avoids scoring overlap
    ]
    # Robots 2 and 3 share scoring zone "speaker" but 254 starts at offset 3.0;
    # paths overlap in time (0..10 vs 3..13) → -0.3 penalty on that pair only.
    score = alliance_auto_compatibility(paths)
    assert 0.5 < score <= 1.0


def test_alliance_missing_path_defaults_to_unknown():
    """A None path in alliance contributes _DEFAULT_UNKNOWN per pairing."""
    # Use distinct scoring zones so (a,b) pair is fully compatible (1.0).
    a = _path(team=2950, start_position="amp-side", scoring_zone="amp")
    b = _path(team=1678, start_position="source-side", scoring_zone="speaker")
    paths = [a, b, None]
    score = alliance_auto_compatibility(paths)
    # Pairs: (a,b)=1.0, (a,None)=0.8, (b,None)=0.8 → mean = (1.0+0.8+0.8)/3
    expected = (1.0 + _DEFAULT_UNKNOWN + _DEFAULT_UNKNOWN) / 3
    assert score == pytest.approx(expected)


def test_alliance_empty_list_returns_one():
    """No robots → no conflicts → 1.0."""
    assert alliance_auto_compatibility([]) == pytest.approx(1.0)


def test_alliance_single_robot_returns_one():
    """Single robot → no pairs to evaluate → 1.0."""
    assert alliance_auto_compatibility([_path(team=2950)]) == pytest.approx(1.0)


def test_alliance_all_none_returns_unknown_mean():
    """All three paths unknown → all pairs use default → _DEFAULT_UNKNOWN."""
    score = alliance_auto_compatibility([None, None, None])
    assert score == pytest.approx(_DEFAULT_UNKNOWN)


# ─── AUTO_PATH_LIBRARY ────────────────────────────────────────────────────────


def test_auto_path_library_is_dict():
    """AUTO_PATH_LIBRARY must be a dict (may be empty — see module TODO)."""
    assert isinstance(AUTO_PATH_LIBRARY, dict)
