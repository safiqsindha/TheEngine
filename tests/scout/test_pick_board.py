"""Tests for β-aware pick_board ranking.

Covers:
  - year=2024 (β=0.55) vs year=2014 (β=0.95) produce different rankings
    on identical input when complementarity varies across teams.
  - year=None preserves legacy β=1.0 behaviour (season_beta is None).
  - Display (recommend_pick output) includes season_beta and season_year keys.
  - Existing recommend_pick call path without year still works (DEFAULT_YEAR).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

import pick_board as pb  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_team(team: int, epa: float, **overrides) -> dict:
    """Minimal team dict compatible with pick_board TeamData shape."""
    base = {
        "team": team,
        "name": f"Team {team}",
        "epa": epa,
        "sd": max(epa * 0.15, 5.0),
        "floor": epa * 0.8,
        "ceiling": epa * 1.2,
        "epa_auto": epa * 0.25,
        "epa_teleop": epa * 0.55,
        "epa_endgame": epa * 0.20,
        "total_fuel": epa * 0.50,
        "total_tower": 0.0,
        "qual_rank": 1,
        "qual_record": "8-2",
        "auto_fuel": epa * 0.10,
        "auto_tower": 0.0,
        "first_shift": epa * 0.25,
        "second_shift": epa * 0.25,
        "transition_fuel": 0.0,
        "endgame_fuel": 0.0,
        "endgame_tower": epa * 0.20,
    }
    base.update(overrides)
    return base


def _minimal_state(our_team: int = 2950, our_seed: int = 3) -> dict:
    """
    Build a minimal draft state with enough captains for recommend_pick to run.

    Alliance 3 (us) faces Alliance 6 in QF.  We have 8 captains so the
    opponent seed = 8+1-3 = 6.
    """
    teams = {}
    captains = []
    # 8 captains, each at a different seed
    for i in range(8):
        t = 1000 + i
        epa = 80.0 - i * 5
        teams[str(t)] = _make_team(t, epa)
        captains.append(t)

    # Our team = captain at seed 3
    teams[str(our_team)] = _make_team(our_team, epa=65.0)
    captains[2] = our_team

    # Available pool: teams not in captains
    for i in range(8, 30):
        t = 2000 + i
        epa = 30.0 + i * 0.5
        teams[str(t)] = _make_team(t, epa)

    # Add two candidates with clearly different complementarity profiles:
    #   - Team 9001: strong tower (rare resource → high complementarity with us)
    #   - Team 9002: strong fuel only (overlaps with us → low complementarity)
    teams["9001"] = _make_team(
        9001, epa=50.0,
        total_tower=8.0,    # big tower — covers our gap
        epa_endgame=12.0,
        endgame_tower=12.0,
    )
    teams["9002"] = _make_team(
        9002, epa=50.0,
        total_tower=0.0,    # no tower
        total_fuel=45.0,    # just fuel (same as us → low comp)
    )

    return {
        "event_key": "2025test",
        "our_team": our_team,
        "our_seed": our_seed,
        "captains": captains,
        "picks": [],
        "teams": teams,
        "history": [],
        "dnp": [],
        "live_matches": {},
    }


# ── Test 1: year=2024 vs year=2014 produce different scores ──────────────────


def test_beta_year_changes_ranking():
    """
    year=2024 (β=0.55, Crescendo) vs year=2014 (β=0.95, Aerial Assist).

    With β=0.55 the coupling factor (0.70 - 0.55 = 0.15) amplifies
    complementarity by 15%.  With β=0.95 there is no amplification
    (coupling_factor = max(0, 0.70 - 0.95) = 0).

    The complementarity-boosted candidate (9001, strong tower) should rank
    higher relative to the non-complementary one (9002) in the 2024 ranking
    than in 2014, or at least produce a different comp_score.
    """
    state = _minimal_state()

    picks_2024 = pb.recommend_pick(state, year=2024)
    picks_2014 = pb.recommend_pick(state, year=2014)

    # Both should return non-empty results
    assert picks_2024, "recommend_pick(year=2024) returned empty"
    assert picks_2014, "recommend_pick(year=2014) returned empty"

    # Find 9001 in both result sets
    def _find(picks, team):
        return next((p for p in picks if p["team"] == team), None)

    t9001_2024 = _find(picks_2024, 9001)
    t9001_2014 = _find(picks_2014, 9001)

    # At least one should appear (EPA ~50 keeps it in top-15)
    if t9001_2024 is not None and t9001_2014 is not None:
        # comp_score should differ between the two years due to β modulation
        assert t9001_2024["comp_score"] != t9001_2014["comp_score"], (
            f"Expected comp_score to differ by year: "
            f"2024={t9001_2024['comp_score']}, 2014={t9001_2014['comp_score']}"
        )
    else:
        # If team isn't in top-15 for one year, check the overall ranking shifted
        teams_2024 = [p["team"] for p in picks_2024]
        teams_2014 = [p["team"] for p in picks_2014]
        assert teams_2024 != teams_2014, (
            "Rankings should differ between year=2024 and year=2014"
        )


# ── Test 2: year=None → legacy path (season_beta is None) ────────────────────


def test_year_none_legacy_path():
    """
    recommend_pick(year=None) must set season_beta=None on every result entry.
    This is the back-compat path for callers that don't pass year.
    """
    state = _minimal_state()
    picks = pb.recommend_pick(state, year=None)

    assert picks, "recommend_pick(year=None) returned empty"
    for p in picks:
        assert p.get("season_beta") is None, (
            f"Expected season_beta=None for year=None, got {p.get('season_beta')} "
            f"for team {p['team']}"
        )
        assert p.get("season_year") is None, (
            f"Expected season_year=None for year=None, got {p.get('season_year')}"
        )


# ── Test 3: Display includes β value ─────────────────────────────────────────


def test_results_include_beta_keys():
    """
    Every entry returned by recommend_pick() must carry 'season_beta' and
    'season_year' keys when year is provided — so cmd_rec can display them.
    """
    state = _minimal_state()

    for year in (2024, 2025, 2014):
        picks = pb.recommend_pick(state, year=year)
        assert picks, f"recommend_pick(year={year}) returned empty"

        for p in picks:
            assert "season_beta" in p, (
                f"Missing 'season_beta' key for year={year}, team={p['team']}"
            )
            assert "season_year" in p, (
                f"Missing 'season_year' key for year={year}, team={p['team']}"
            )
            assert p["season_year"] == year, (
                f"season_year mismatch: expected {year}, got {p['season_year']}"
            )
            # β must be a float in a reasonable range
            beta = p["season_beta"]
            assert isinstance(beta, float), (
                f"season_beta should be float, got {type(beta)} for year={year}"
            )
            assert 0.4 <= beta <= 1.0, (
                f"season_beta out of expected range [0.4, 1.0]: {beta} for year={year}"
            )


# ── Test 4: DEFAULT_YEAR path (no year arg) still works ──────────────────────


def test_default_year_back_compat():
    """
    Existing callers that call recommend_pick(state) without a year kwarg
    must continue to work, using DEFAULT_YEAR (2025, β=0.65).
    """
    state = _minimal_state()

    # Call without year kwarg — must not raise
    picks = pb.recommend_pick(state)

    assert picks, "recommend_pick() with no year arg returned empty"

    # Should use DEFAULT_YEAR
    assert picks[0].get("season_year") == pb.DEFAULT_YEAR, (
        f"Expected season_year={pb.DEFAULT_YEAR}, got {picks[0].get('season_year')}"
    )
    # β should be the 2025 empirical value (0.65 per attribution_betas)
    assert picks[0].get("season_beta") == pytest.approx(0.65, abs=0.01), (
        f"Expected β≈0.65 for DEFAULT_YEAR=2025, got {picks[0].get('season_beta')}"
    )
