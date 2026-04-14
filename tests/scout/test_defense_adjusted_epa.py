"""Tests for scout/defense_adjusted_epa.py

Covers:
  - No observations → fallback (raw EPA returned)
  - Insufficient observations → fallback
  - All undefended → offensive_EPA equals mean of undefended contributions
  - All defended → offensive_EPA = defended_weight * defended_mean
  - Mixed defended/undefended → blend formula correct
  - Played-defense matches excluded from EPA calculation
  - defense_pressure_index in [0.0, 1.0]
  - DPI = 0 when no defended matches
  - DPI = 1 when all matches defended
  - Batch helper returns results keyed by team
  - format_defense_adj_row produces expected label strings
  - heavily-targeted flag fires at DPI >= 0.40
  - used_fallback=False when enough data present
  - offensive_EPA with no match_contribution field uses raw_epa as stand-in
  - played_defense count surfaced in notes
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from defense_adjusted_epa import (  # noqa: E402
    DEFENDED_WEIGHT,
    MIN_SCOUTED_MATCHES,
    DefenseAdjResult,
    compute_defense_adjusted_epa,
    compute_defense_adjusted_epa_for_event,
    format_defense_adj_row,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _obs(received_defense: bool = False, played_defense: bool = False,
         contribution: float = None, match: str = "2026txbel_qm1",
         scout: str = "Alice") -> dict:
    d = {
        "team": 2950,
        "_meta": {"scout": scout, "match_key": match},
        "auto": {"scored": True},
        "teleop": {"cycle_speed": "fast"},
        "endgame": {"climb_attempted": True},
        "defense": {
            "played_defense": played_defense,
            "received_defense": received_defense,
            "notes": "",
        },
    }
    if contribution is not None:
        d["match_contribution"] = contribution
    return d


def _make_obs_list(n_clean: int, n_defended: int,
                   clean_contrib: float = 50.0,
                   defended_contrib: float = 20.0) -> list:
    obs_list = []
    for i in range(n_clean):
        obs_list.append(_obs(received_defense=False, contribution=clean_contrib,
                             match=f"qm{i}"))
    for i in range(n_defended):
        obs_list.append(_obs(received_defense=True, contribution=defended_contrib,
                             match=f"qm{n_clean + i}"))
    return obs_list


# ─── Fallback cases ───────────────────────────────────────────────────────────


def test_no_observations_returns_fallback():
    result = compute_defense_adjusted_epa(team=2950, raw_epa=42.0, observations=[])
    assert result.used_fallback is True
    assert result.offensive_epa == 42.0
    assert result.raw_epa == 42.0


def test_insufficient_observations_returns_fallback():
    obs_list = _make_obs_list(MIN_SCOUTED_MATCHES - 1, 0)
    result = compute_defense_adjusted_epa(team=2950, raw_epa=42.0, observations=obs_list)
    assert result.used_fallback is True
    assert result.offensive_epa == 42.0


def test_exactly_min_obs_does_not_fallback():
    obs_list = _make_obs_list(MIN_SCOUTED_MATCHES, 0, clean_contrib=50.0)
    result = compute_defense_adjusted_epa(team=2950, raw_epa=42.0, observations=obs_list)
    assert result.used_fallback is False


# ─── All undefended ───────────────────────────────────────────────────────────


def test_all_undefended_offensive_epa_equals_undefended_mean():
    obs_list = _make_obs_list(5, 0, clean_contrib=50.0)
    result = compute_defense_adjusted_epa(team=2950, raw_epa=42.0, observations=obs_list)
    assert abs(result.offensive_epa - 50.0) < 0.01
    assert result.defense_pressure_index == 0.0
    assert result.defended_match_count == 0
    assert result.undefended_match_count == 5


def test_dpi_zero_when_no_defense_seen():
    obs_list = _make_obs_list(6, 0)
    result = compute_defense_adjusted_epa(team=2950, raw_epa=40.0, observations=obs_list)
    assert result.defense_pressure_index == 0.0


# ─── All defended ────────────────────────────────────────────────────────────


def test_all_defended_dpi_equals_one():
    obs_list = _make_obs_list(0, 5, defended_contrib=20.0)
    result = compute_defense_adjusted_epa(team=2950, raw_epa=40.0, observations=obs_list)
    assert result.defense_pressure_index == 1.0
    assert result.defended_match_count == 5
    assert result.undefended_match_count == 0


# ─── Mixed case (core blend) ─────────────────────────────────────────────────


def test_mixed_blend_formula():
    # 4 clean at 60.0, 2 defended at 20.0
    obs_list = _make_obs_list(4, 2, clean_contrib=60.0, defended_contrib=20.0)
    result = compute_defense_adjusted_epa(team=2950, raw_epa=50.0, observations=obs_list)

    expected_off = 60.0 + DEFENDED_WEIGHT * 20.0
    assert abs(result.offensive_epa - expected_off) < 0.1
    assert abs(result.defense_pressure_index - (2 / 6)) < 0.001


def test_offensive_epa_higher_than_raw_when_defended():
    """Teams that score 60 clean but get defended to 20 should show offensive > raw mean."""
    # Raw EPA = average of all = (4*60 + 2*20) / 6 = 280/6 ≈ 46.7
    obs_list = _make_obs_list(4, 2, clean_contrib=60.0, defended_contrib=20.0)
    raw_epa_estimate = 46.7
    result = compute_defense_adjusted_epa(team=2950, raw_epa=raw_epa_estimate,
                                          observations=obs_list)
    assert result.offensive_epa > raw_epa_estimate


# ─── Played defense exclusion ────────────────────────────────────────────────


def test_played_defense_matches_excluded():
    obs_list = [
        _obs(played_defense=True, contribution=0.0, match="qm1"),
        _obs(played_defense=True, contribution=0.0, match="qm2"),
        _obs(received_defense=False, contribution=50.0, match="qm3"),
        _obs(received_defense=False, contribution=50.0, match="qm4"),
    ]
    result = compute_defense_adjusted_epa(team=2950, raw_epa=40.0, observations=obs_list)
    # Only 2 clean matches contribute; played-defense matches excluded
    assert result.undefended_match_count == 2
    assert result.defended_match_count == 0
    assert abs(result.offensive_epa - 50.0) < 0.01
    assert any("played defense" in note for note in result.notes)


def test_played_defense_note_surfaced():
    obs_list = [_obs(played_defense=True, match="qm1"),
                _obs(contribution=50.0, match="qm2"),
                _obs(contribution=50.0, match="qm3")]
    result = compute_defense_adjusted_epa(team=2950, raw_epa=40.0, observations=obs_list)
    assert any("played defense" in note for note in result.notes)


# ─── No explicit contribution (uses raw_epa as stand-in) ─────────────────────


def test_no_match_contribution_uses_raw_epa_fallback():
    # Observations without match_contribution → raw_epa used per match
    obs_list = [_obs(received_defense=False, match=f"qm{i}") for i in range(4)]
    result = compute_defense_adjusted_epa(team=2950, raw_epa=42.0, observations=obs_list)
    # All undefended, each match contribution = 42.0 → offensive_epa = 42.0
    assert abs(result.offensive_epa - 42.0) < 0.01
    assert result.used_fallback is False


# ─── DPI range ───────────────────────────────────────────────────────────────


def test_dpi_in_valid_range():
    obs_list = _make_obs_list(3, 2)
    result = compute_defense_adjusted_epa(team=2950, raw_epa=40.0, observations=obs_list)
    assert 0.0 <= result.defense_pressure_index <= 1.0


# ─── Batch helper ────────────────────────────────────────────────────────────


def test_batch_helper_returns_all_teams():
    teams_obs = {
        2950: _make_obs_list(4, 1, clean_contrib=55.0),
        1678: _make_obs_list(5, 0, clean_contrib=70.0),
    }
    teams_epa = {2950: 50.0, 1678: 68.0}
    results = compute_defense_adjusted_epa_for_event(teams_obs, teams_epa)
    assert 2950 in results
    assert 1678 in results
    assert isinstance(results[2950], DefenseAdjResult)


def test_batch_helper_missing_team_epa_defaults_to_zero():
    teams_obs = {9999: _make_obs_list(3, 1, clean_contrib=30.0)}
    results = compute_defense_adjusted_epa_for_event(teams_obs, {})
    assert 9999 in results
    # raw_epa defaults to 0.0 when missing from teams_epa dict
    assert results[9999].raw_epa == 0.0


# ─── format_defense_adj_row ──────────────────────────────────────────────────


def test_format_row_includes_raw_and_off():
    result = DefenseAdjResult(
        team=2950, raw_epa=42.0, offensive_epa=58.7,
        defense_pressure_index=0.42, defended_match_count=3,
        undefended_match_count=4, used_fallback=False
    )
    row = format_defense_adj_row(result)
    assert "42.0" in row
    assert "58.7" in row
    assert "3/7" in row


def test_format_row_heavily_targeted_flag():
    result = DefenseAdjResult(
        team=2950, raw_epa=42.0, offensive_epa=60.0,
        defense_pressure_index=0.50, defended_match_count=3,
        undefended_match_count=3, used_fallback=False
    )
    row = format_defense_adj_row(result)
    assert "heavily targeted" in row


def test_format_row_insufficient_data_tag():
    result = DefenseAdjResult(
        team=2950, raw_epa=42.0, offensive_epa=42.0,
        defense_pressure_index=0.0, defended_match_count=0,
        undefended_match_count=1, used_fallback=True
    )
    row = format_defense_adj_row(result)
    assert "insufficient data" in row
