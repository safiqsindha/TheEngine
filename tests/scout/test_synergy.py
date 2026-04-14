"""Tests for scout/synergy.py — Pair Synergy Scoring.

Covers:
  - compute_pair_synergy: empty shared_matches returns zero synergy
  - compute_pair_synergy: positive synergy when alliance consistently over-performs
  - compute_pair_synergy: negative synergy when alliance consistently under-performs
  - compute_pair_synergy: zero synergy when actual == expected
  - compute_pair_synergy: n_matches tracked correctly
  - compute_pair_synergy: used_fallback=True when n_matches < MIN_SHARED_MATCHES
  - compute_pair_synergy: used_fallback=False when n_matches >= MIN_SHARED_MATCHES
  - compute_pair_synergy: component breakdown computed when phase data present
  - compute_pair_synergy: has_component_data=False when phase data absent
  - compute_pair_synergy: match skipped when target teams not in alliance
  - compute_pair_synergy: component_breakdown=False skips phase computation
  - build_shared_match: extracts actual_total from TBA breakdown
  - build_shared_match: extracts phase components when present
  - build_shared_match: handles missing phase data gracefully
  - compute_team_synergy_profile: returns entry for every seen partner
  - compute_team_synergy_profile: skips matches where home team absent
  - best_synergy_partners: returns top N by overall synergy
  - best_synergy_partners: reliable pairs ranked before fallback pairs at same score
  - format_synergy_row: shows [ELITE] tag when carry_delta > 3 and overall > 5
  - format_synergy_row: no [ELITE] tag when carry_delta absent
  - format_synergy_row: shows [low-n] tag for fallback pairs
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from synergy import (  # noqa: E402
    MIN_SHARED_MATCHES,
    best_synergy_partners,
    build_shared_match,
    compute_pair_synergy,
    compute_team_synergy_profile,
    format_synergy_row,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _team_epas(a: int = 2950, b: int = 1678, c: int = 254,
               epa_a: float = 40.0, epa_b: float = 50.0, epa_c: float = 60.0,
               epa_auto: float = 15.0, epa_teleop: float = 30.0,
               epa_endgame: float = 5.0) -> dict:
    """Build a minimal team_epas dict for three teams."""
    return {
        a: {"epa": epa_a, "epa_auto": epa_auto, "epa_teleop": epa_teleop, "epa_endgame": epa_endgame},
        b: {"epa": epa_b, "epa_auto": epa_auto, "epa_teleop": epa_teleop, "epa_endgame": epa_endgame},
        c: {"epa": epa_c, "epa_auto": epa_auto, "epa_teleop": epa_teleop, "epa_endgame": epa_endgame},
    }


def _match(teams=(2950, 1678, 254), actual_total=160.0, epas=None,
           actual_auto=None, actual_teleop=None, actual_endgame=None) -> dict:
    """Build a minimal shared_match dict."""
    if epas is None:
        epas = _team_epas()
    m = {
        "alliance_teams": list(teams),
        "actual_total": actual_total,
        "team_epas": epas,
    }
    if actual_auto is not None:
        m["actual_auto"] = actual_auto
    if actual_teleop is not None:
        m["actual_teleop"] = actual_teleop
    if actual_endgame is not None:
        m["actual_endgame"] = actual_endgame
    return m


# ─── compute_pair_synergy ─────────────────────────────────────────────────────


def test_empty_shared_matches_returns_zero():
    result = compute_pair_synergy(2950, 1678, [])
    assert result["overall"] == 0.0
    assert result["n_matches"] == 0
    assert result["used_fallback"] is True


def test_positive_synergy_when_overperforming():
    # Expected = 40+50+60 = 150, actual = 170 → delta = +20 per match
    matches = [_match(actual_total=170.0), _match(actual_total=175.0)]
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["overall"] > 0.0
    assert result["n_matches"] == 2


def test_negative_synergy_when_underperforming():
    matches = [_match(actual_total=120.0), _match(actual_total=115.0)]
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["overall"] < 0.0


def test_zero_synergy_when_actual_equals_expected():
    # Expected = 40+50+60 = 150
    matches = [_match(actual_total=150.0), _match(actual_total=150.0)]
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["overall"] == pytest.approx(0.0, abs=0.01)


def test_n_matches_tracked():
    matches = [_match() for _ in range(4)]
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["n_matches"] == 4


def test_used_fallback_true_when_below_min():
    matches = [_match()]  # only 1 match < MIN_SHARED_MATCHES (2)
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["used_fallback"] is True


def test_used_fallback_false_when_enough_matches():
    matches = [_match() for _ in range(MIN_SHARED_MATCHES)]
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["used_fallback"] is False


def test_component_breakdown_computed_when_phase_data_present():
    matches = [
        _match(actual_total=170.0, actual_auto=50.0, actual_teleop=95.0, actual_endgame=25.0),
        _match(actual_total=165.0, actual_auto=48.0, actual_teleop=92.0, actual_endgame=25.0),
    ]
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["has_component_data"] is True
    # auto expected = 15+15+15 = 45; actual = 50/48 → positive auto synergy
    assert result["auto"] > 0.0


def test_has_component_data_false_when_no_phase_data():
    matches = [_match(actual_total=160.0), _match(actual_total=155.0)]
    result = compute_pair_synergy(2950, 1678, matches)
    assert result["has_component_data"] is False
    assert result["auto"] == 0.0
    assert result["teleop"] == 0.0
    assert result["endgame"] == 0.0


def test_match_skipped_when_target_teams_not_in_alliance():
    # Match where team_b (1678) is replaced by 9999 — pair (2950, 1678) not present
    match_without_pair = _match(teams=(2950, 9999, 254), actual_total=200.0)
    match_with_pair = _match(teams=(2950, 1678, 254), actual_total=170.0)
    result = compute_pair_synergy(2950, 1678, [match_without_pair, match_with_pair])
    assert result["n_matches"] == 1


def test_component_breakdown_false_skips_phase():
    matches = [
        _match(actual_total=170.0, actual_auto=50.0, actual_teleop=95.0, actual_endgame=25.0),
        _match(actual_total=165.0, actual_auto=48.0, actual_teleop=92.0, actual_endgame=25.0),
    ]
    result = compute_pair_synergy(2950, 1678, matches, component_breakdown=False)
    assert result["has_component_data"] is False
    assert result["auto"] == 0.0


# ─── build_shared_match ───────────────────────────────────────────────────────


def test_build_shared_match_extracts_total():
    breakdown = {"total": 165.0, "autoPoints": 50.0}
    epas = _team_epas()
    m = build_shared_match([2950, 1678, 254], breakdown, epas)
    assert m["actual_total"] == pytest.approx(165.0)


def test_build_shared_match_extracts_phase_components():
    breakdown = {
        "total": 165.0,
        "autoPoints": 48.0,
        "teleopPoints": 92.0,
        "endgamePoints": 25.0,
    }
    epas = _team_epas()
    m = build_shared_match([2950, 1678, 254], breakdown, epas)
    assert m["actual_auto"] == pytest.approx(48.0)
    assert m["actual_teleop"] == pytest.approx(92.0)
    assert m["actual_endgame"] == pytest.approx(25.0)


def test_build_shared_match_missing_phase_data_graceful():
    breakdown = {"total": 150.0}  # No phase data
    epas = _team_epas()
    m = build_shared_match([2950, 1678, 254], breakdown, epas)
    assert "actual_auto" not in m
    assert "actual_teleop" not in m
    assert "actual_endgame" not in m


# ─── compute_team_synergy_profile ─────────────────────────────────────────────


def test_profile_returns_entry_for_every_seen_partner():
    matches = [
        _match(teams=(2950, 1678, 254), actual_total=170.0),
        _match(teams=(2950, 1678, 148), actual_total=165.0),
    ]
    profile = compute_team_synergy_profile(2950, [2950, 1678, 254, 148], matches)
    # Partners: 1678 (2 matches), 254 (1 match), 148 (1 match)
    assert 1678 in profile
    assert 254 in profile
    assert 148 in profile
    assert 2950 not in profile  # self excluded


def test_profile_skips_matches_where_home_team_absent():
    matches = [
        _match(teams=(2950, 1678, 254), actual_total=170.0),
        _match(teams=(9999, 1678, 254), actual_total=200.0),  # home team absent
    ]
    profile = compute_team_synergy_profile(2950, [2950, 1678, 254, 9999], matches)
    # 1678 and 254 each appear in 1 match with 2950
    assert profile[1678]["n_matches"] == 1
    assert profile[254]["n_matches"] == 1


# ─── best_synergy_partners ────────────────────────────────────────────────────


def test_best_partners_returns_top_n():
    profile = {
        1678: {"overall": 8.0, "n_matches": 3, "used_fallback": False, "has_component_data": False},
        254: {"overall": 6.0, "n_matches": 3, "used_fallback": False, "has_component_data": False},
        148: {"overall": 4.0, "n_matches": 3, "used_fallback": False, "has_component_data": False},
        9999: {"overall": 2.0, "n_matches": 3, "used_fallback": False, "has_component_data": False},
    }
    top2 = best_synergy_partners(2950, profile, top_n=2)
    assert len(top2) == 2
    assert top2[0][0] == 1678
    assert top2[1][0] == 254


def test_reliable_pairs_ranked_before_fallback():
    profile = {
        1678: {"overall": 5.0, "n_matches": 1, "used_fallback": True, "has_component_data": False},
        254: {"overall": 4.0, "n_matches": 3, "used_fallback": False, "has_component_data": False},
    }
    top = best_synergy_partners(2950, profile, top_n=2)
    # 254 has lower overall but reliable data — should rank first
    assert top[0][0] == 254


# ─── format_synergy_row ───────────────────────────────────────────────────────


def test_format_shows_elite_tag_when_conditions_met():
    syn = {"overall": 9.0, "auto": 3.0, "teleop": 4.5, "endgame": 1.5,
           "n_matches": 6, "has_component_data": True, "used_fallback": False}
    row = format_synergy_row(2468, syn, carry_delta=5.0)
    assert "[ELITE]" in row


def test_format_no_elite_tag_without_carry_delta():
    syn = {"overall": 9.0, "auto": 3.0, "teleop": 4.5, "endgame": 1.5,
           "n_matches": 6, "has_component_data": True, "used_fallback": False}
    row = format_synergy_row(2468, syn)
    assert "[ELITE]" not in row


def test_format_shows_low_n_tag_for_fallback():
    syn = {"overall": 5.0, "auto": 0.0, "teleop": 0.0, "endgame": 0.0,
           "n_matches": 1, "has_component_data": False, "used_fallback": True}
    row = format_synergy_row(1234, syn)
    assert "[low-n]" in row
    assert "no component data" in row
