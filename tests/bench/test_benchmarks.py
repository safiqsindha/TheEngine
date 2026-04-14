"""
pytest-benchmark coverage for 5 hot paths.

Opt-in via `pytest -m benchmark --benchmark-only`.
These tests are excluded from the default `pytest -q` run through
the `benchmark` marker registered in pytest.ini.

Hot paths benchmarked:
  1. blueprint/oracle.py — predict_game (full R1–R19 pipeline on one GameRules)
  2. scout/alliance_decomposition.py — compute_alliance_decomposition (β=0.7, year=2025)
  3. blueprint/oracle.py — Rule #18 via get_rule_breakdown["R18"]
  4. scout/pick_board.py — recommend_pick with ~50 teams, β-awareness via year=2025
  5. scout/synergy.py — defense_adjusted_synergy over a small shared-match list
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_BLUEPRINT_DIR = ROOT / "blueprint"
_SCOUT_DIR = ROOT / "scout"
for _p in (_BLUEPRINT_DIR, _SCOUT_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from oracle import (  # noqa: E402
    GameRules,
    apply_rules,
    get_rule_breakdown,
    predict_game,
)
from alliance_decomposition import compute_alliance_decomposition  # noqa: E402
from synergy import defense_adjusted_synergy  # noqa: E402
import pick_board as pb  # noqa: E402


pytestmark = pytest.mark.benchmark


# ── Fixtures ────────────────────────────────────────────────────────────────


def _canonical_game() -> GameRules:
    """Realistic 2025-era Reefscape-ish GameRules for oracle benchmarks."""
    return GameRules(
        game_name="BenchGame",
        year=2025,
        game_piece_name="coral",
        game_piece_shape="cylindrical",
        game_piece_diameter_in=4.5,
        pieces_floor_pickup=True,
        scoring_targets=[
            {"name": "L1", "height_in": 18, "distance_ft": 3, "auto_pts": 3,
             "teleop_pts": 2, "type": "placement", "distributed": True,
             "cap_type": "uncapped", "max_alliance_pts": 999},
            {"name": "L4", "height_in": 72, "distance_ft": 6, "auto_pts": 7,
             "teleop_pts": 5, "type": "placement", "distributed": True,
             "cap_type": "uncapped", "max_alliance_pts": 999},
        ],
        endgame_type="climb",
        endgame_height_in=30,
        endgame_points=12,
        endgame_pct_of_winning_score=0.15,
        field_is_small=False,
        max_frame_perimeter_in=120,
        estimated_winning_score=120,
    )


def _alliance_decomp_inputs():
    alliance_epas = {2950: 40.0, 1678: 55.0, 254: 65.0}
    match_breakdown = {"total": 175.0}
    obs = [
        {"team": 2950, "_meta": {"scout": "A", "match_key": "2025txbel_qm1"},
         "auto": {"scored": True}, "teleop": {"cycle_speed": "fast"},
         "endgame": {"climb_attempted": True},
         "defense": {"played_defense": False, "received_defense": False, "notes": ""},
         "match_contribution": 45.0},
        {"team": 1678, "_meta": {"scout": "B", "match_key": "2025txbel_qm1"},
         "auto": {"scored": True}, "teleop": {"cycle_speed": "fast"},
         "endgame": {"climb_attempted": True},
         "defense": {"played_defense": False, "received_defense": False, "notes": ""},
         "match_contribution": 60.0},
        {"team": 254, "_meta": {"scout": "C", "match_key": "2025txbel_qm1"},
         "auto": {"scored": True}, "teleop": {"cycle_speed": "fast"},
         "endgame": {"climb_attempted": True},
         "defense": {"played_defense": False, "received_defense": False, "notes": ""},
         "match_contribution": 70.0},
    ]
    return alliance_epas, match_breakdown, obs


def _pick_board_state(n_pool: int = 50) -> dict:
    """Build a state with ~n_pool teams in the available pool."""
    def _team(t, epa):
        return {
            "team": t, "name": f"Team {t}", "epa": epa,
            "sd": max(epa * 0.15, 5.0),
            "floor": epa * 0.8, "ceiling": epa * 1.2,
            "epa_auto": epa * 0.25, "epa_teleop": epa * 0.55,
            "epa_endgame": epa * 0.20,
            "total_fuel": epa * 0.50, "total_tower": epa * 0.10,
            "qual_rank": 1, "qual_record": "8-2",
            "auto_fuel": epa * 0.10, "auto_tower": 0.0,
            "first_shift": epa * 0.25, "second_shift": epa * 0.25,
            "transition_fuel": 0.0,
            "endgame_fuel": 0.0, "endgame_tower": epa * 0.20,
        }

    teams = {}
    captains = []
    for i in range(8):
        t = 1000 + i
        captains.append(t)
        teams[str(t)] = _team(t, 80.0 - i * 4)

    our_team = 2950
    teams[str(our_team)] = _team(our_team, 65.0)
    captains[2] = our_team

    for i in range(n_pool):
        t = 2000 + i
        teams[str(t)] = _team(t, 30.0 + i * 0.4)

    return {
        "event_key": "2025bench",
        "our_team": our_team,
        "our_seed": 3,
        "captains": captains,
        "picks": [],
        "teams": teams,
        "history": [],
        "dnp": [],
        "live_matches": {},
    }


def _synergy_inputs():
    team_a = {
        "team": 2950, "raw_epa": 40.0,
        "observations": [
            {"defense": {"received_defense": True}, "match_contribution": 25.0},
            {"defense": {"received_defense": False}, "match_contribution": 58.0},
            {"defense": {"received_defense": False}, "match_contribution": 60.0},
        ],
    }
    team_b = {
        "team": 1678, "raw_epa": 50.0,
        "observations": [
            {"defense": {"received_defense": False}, "match_contribution": 55.0},
            {"defense": {"received_defense": False}, "match_contribution": 52.0},
        ],
    }
    epas = {
        2950: {"epa": 40.0}, 1678: {"epa": 50.0}, 254: {"epa": 60.0},
    }
    matches = [
        {"alliance_teams": [2950, 1678, 254], "actual_total": 170.0, "team_epas": epas},
        {"alliance_teams": [2950, 1678, 254], "actual_total": 165.0, "team_epas": epas},
        {"alliance_teams": [2950, 1678, 254], "actual_total": 172.0, "team_epas": epas},
    ]
    return team_a, team_b, matches


# ── Benchmarks ──────────────────────────────────────────────────────────────


def test_bench_oracle_predict_game(benchmark):
    """Hot path #1: predict a single match via Oracle R1–R19 pipeline."""
    game = _canonical_game()
    result = benchmark(predict_game, game)
    assert result["rule_log"], "rule_log should be non-empty"


def test_bench_alliance_decomposition(benchmark):
    """Hot path #2: compute_alliance_decomposition with β=0.7, year=2025."""
    alliance_epas, mb, obs = _alliance_decomp_inputs()

    def _run():
        return compute_alliance_decomposition(
            alliance_epas, mb, obs,
            match_key="2025txbel_qm1",
            beta=0.7,
            year=2025,
        )

    out = benchmark(_run)
    assert len(out) == 3


def test_bench_oracle_rule_18_breakdown(benchmark):
    """Hot path #3: Rule #18 via get_rule_breakdown — apply_rules + extraction."""
    game = _canonical_game()

    def _run():
        pred = apply_rules(game)
        bd = get_rule_breakdown(pred["rule_log"])
        return bd.get("R18")

    r18 = benchmark(_run)
    # R18 is the EPA-win / alliance-complementarity rule; it may or may not
    # fire on this fixture but the breakdown dict should be indexable regardless.
    assert r18 is None or "confidence" in r18


def test_bench_pick_board_recommend_50_teams(benchmark):
    """Hot path #4: pick_board.recommend_pick ranking ~50 teams with β-awareness."""
    state = _pick_board_state(n_pool=50)
    picks = benchmark(pb.recommend_pick, state, 2025)
    assert picks, "recommend_pick should return a non-empty ranking"
    assert picks[0].get("season_year") == 2025


def test_bench_defense_adjusted_synergy(benchmark):
    """Hot path #5: synergy.defense_adjusted_synergy over shared matches."""
    team_a, team_b, matches = _synergy_inputs()
    result = benchmark(defense_adjusted_synergy, team_a, team_b, matches)
    assert isinstance(result, float)
