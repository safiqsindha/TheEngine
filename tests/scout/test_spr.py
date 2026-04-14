"""Tests for scout/spr.py — Scout Precision Rating algorithm.

Covers:
  - compute_spr returns 0.5 for scouts with insufficient entries
  - perfect-accuracy scouts score close to 1.0
  - always-wrong scouts score close to 0.0
  - mixed residuals land in mid-range
  - get_scout_weight fallback behavior
  - apply_spr_weights annotates obs dicts
  - build_entry_from_obs parses TBA match_detail correctly
  - binary residuals (auto / endgame) behave correctly
  - teleop residual clamps to [0, 1]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from spr import (  # noqa: E402
    MIN_ENTRIES,
    NEUTRAL_SCORE,
    ScoutEntry,
    apply_spr_weights,
    build_entry_from_obs,
    compute_spr,
    get_scout_weight,
)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _entry(
    scout: str = "Alice",
    auto_scored: bool = True,
    climb: bool = True,
    speed: str = "fast",
    tba_auto: float = 5.0,
    tba_teleop: float = 36.0,
    tba_endgame: float = 4.0,
    teleop_avg: float = 40.0,
    match: str = "2026txbel_qm1",
    team: int = 2950,
) -> ScoutEntry:
    return ScoutEntry(
        scout_name=scout,
        team=team,
        match_key=match,
        auto_scored=auto_scored,
        climb_attempted=climb,
        cycle_speed=speed,
        tba_auto_points=tba_auto,
        tba_teleop_points=tba_teleop,
        tba_endgame_points=tba_endgame,
        event_teleop_avg=teleop_avg,
    )


def _perfect_entries(scout: str, n: int) -> list[ScoutEntry]:
    """Entries where scout is always correct: auto scored + climb + fast speed near event avg."""
    return [
        _entry(scout=scout, auto_scored=True, climb=True, speed="fast",
               tba_auto=5.0, tba_teleop=36.0, tba_endgame=4.0, teleop_avg=40.0,
               match=f"2026txbel_qm{i}")
        for i in range(1, n + 1)
    ]


def _wrong_entries(scout: str, n: int) -> list[ScoutEntry]:
    """Entries where scout is maximally wrong: said scored/climbed but TBA shows 0."""
    return [
        _entry(scout=scout, auto_scored=True, climb=True, speed="fast",
               tba_auto=0.0, tba_teleop=0.0, tba_endgame=0.0, teleop_avg=40.0,
               match=f"2026txbel_qm{i}")
        for i in range(1, n + 1)
    ]


# ─── Insufficient data ────────────────────────────────────────────────────────


def test_no_entries_returns_empty():
    scores = compute_spr([])
    assert scores == {}


def test_fewer_than_min_entries_returns_neutral():
    entries = _perfect_entries("Bob", MIN_ENTRIES - 1)
    scores = compute_spr(entries)
    assert scores["Bob"] == NEUTRAL_SCORE


def test_exactly_min_entries_scores_normally():
    entries = _perfect_entries("Carol", MIN_ENTRIES)
    scores = compute_spr(entries)
    # Perfect scout should score above neutral
    assert scores["Carol"] > NEUTRAL_SCORE


# ─── Perfect accuracy ─────────────────────────────────────────────────────────


def test_perfect_scout_scores_near_one():
    entries = _perfect_entries("Alice", 10)
    scores = compute_spr(entries)
    # Perfect agreement: residuals should be low → score near 1.0
    assert scores["Alice"] >= 0.75, f"Expected ≥0.75, got {scores['Alice']}"


def test_perfect_scout_score_clamped_at_most_one():
    entries = _perfect_entries("Alice", 20)
    scores = compute_spr(entries)
    assert scores["Alice"] <= 1.0


# ─── Poor accuracy ────────────────────────────────────────────────────────────


def test_always_wrong_scout_scores_low():
    entries = _wrong_entries("BadScout", 10)
    scores = compute_spr(entries)
    # Binary auto: said scored, TBA=0 → residual 1.0
    # Binary endgame: said climbed, TBA=0 → residual 1.0
    # Teleop: said fast (expected 90% of 40=36), actual 0 → residual ~0.9 clamped
    assert scores["BadScout"] < 0.2, f"Expected <0.2, got {scores['BadScout']}"


def test_scout_score_in_valid_range():
    entries = _wrong_entries("X", 5) + _perfect_entries("X", 5)
    scores = compute_spr(entries)
    assert 0.0 <= scores["X"] <= 1.0


# ─── Multiple scouts ──────────────────────────────────────────────────────────


def test_multiple_scouts_independent():
    entries = _perfect_entries("Good", 10) + _wrong_entries("Bad", 10)
    scores = compute_spr(entries)
    assert scores["Good"] > scores["Bad"]
    assert "Good" in scores and "Bad" in scores


def test_unknown_scout_defaults_to_empty_key():
    entries = _perfect_entries("", 5)
    scores = compute_spr(entries)
    # Empty name → stored under "unknown" key
    assert "unknown" in scores


# ─── get_scout_weight ─────────────────────────────────────────────────────────


def test_get_scout_weight_known():
    scores = {"Alice": 0.9}
    assert get_scout_weight(scores, "Alice") == 0.9


def test_get_scout_weight_unknown_falls_back():
    assert get_scout_weight({}, "Nobody") == NEUTRAL_SCORE


# ─── apply_spr_weights ───────────────────────────────────────────────────────


def test_apply_spr_weights_annotates_dicts():
    obs = [
        {"team": 2950, "_meta": {"scout": "Alice"}},
        {"team": 1678, "_meta": {"scout": "Bob"}},
    ]
    scores = {"Alice": 0.9, "Bob": 0.4}
    result = apply_spr_weights(obs, scores)
    assert result[0]["spr_weight"] == 0.9
    assert result[1]["spr_weight"] == 0.4


def test_apply_spr_weights_unknown_scout_gets_neutral():
    obs = [{"team": 2950, "_meta": {"scout": "Ghost"}}]
    result = apply_spr_weights(obs, {})
    assert result[0]["spr_weight"] == NEUTRAL_SCORE


def test_apply_spr_weights_missing_meta_gets_neutral():
    obs = [{"team": 2950}]
    result = apply_spr_weights(obs, {"Alice": 0.9})
    assert result[0]["spr_weight"] == NEUTRAL_SCORE


# ─── build_entry_from_obs ────────────────────────────────────────────────────


def _fake_obs(scout="Alice", team=2950, match="2026txbel_qm5",
              auto_scored=True, climbed=True, speed="fast"):
    return {
        "team": team,
        "_meta": {"scout": scout, "match_key": match},
        "auto": {"scored": auto_scored, "moved": True},
        "endgame": {"climb_attempted": climbed, "notes": "climbed"},
        "teleop": {"cycle_speed": speed, "primary_zone": "fuel"},
    }


def _fake_match_detail(key="2026txbel_qm5", red_auto=18.0, red_teleop=45.0,
                        red_endgame=12.0):
    return {
        "key": key,
        "score_breakdown": {
            "red": {
                "autoPoints": red_auto,
                "teleopPoints": red_teleop,
                "endgamePoints": red_endgame,
            },
            "blue": {
                "autoPoints": 12.0,
                "teleopPoints": 39.0,
                "endgamePoints": 9.0,
            },
        },
    }


def test_build_entry_parses_correctly():
    obs = _fake_obs()
    detail = _fake_match_detail()
    entry = build_entry_from_obs(obs, detail, alliance="red", event_teleop_avg=40.0)

    assert entry is not None
    assert entry.scout_name == "Alice"
    assert entry.team == 2950
    assert entry.match_key == "2026txbel_qm5"
    assert entry.auto_scored is True
    assert entry.climb_attempted is True
    assert entry.cycle_speed == "fast"
    # Per-team: 18 / 3 = 6.0
    assert abs(entry.tba_auto_points - 6.0) < 0.01
    assert abs(entry.tba_teleop_points - 15.0) < 0.01   # 45/3
    assert abs(entry.tba_endgame_points - 4.0) < 0.01   # 12/3


def test_build_entry_missing_team_returns_none():
    obs = _fake_obs()
    obs.pop("team")
    entry = build_entry_from_obs(obs, _fake_match_detail(), "red")
    assert entry is None


def test_build_entry_missing_breakdown_returns_none():
    obs = _fake_obs()
    detail = {"key": "2026txbel_qm5", "score_breakdown": {}}
    entry = build_entry_from_obs(obs, detail, "red")
    assert entry is None
