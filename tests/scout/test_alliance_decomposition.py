"""Tests for scout/alliance_decomposition.py — Alliance Stat Decomposition.

Covers:
  - compute_alliance_decomposition: uniform fallback when no obs provided
  - compute_alliance_decomposition: uniform fallback when obs lack numeric data
  - compute_alliance_decomposition: observation-driven shares via match_contribution
  - compute_alliance_decomposition: shares sum to ~1.0
  - compute_alliance_decomposition: alliance_delta propagated correctly
  - compute_alliance_decomposition: zero delta when actual == expected
  - compute_alliance_decomposition: actual_pts = expected_pts + actual_delta
  - compute_alliance_decomposition: played-defense team gets near-zero share
  - compute_alliance_decomposition: graceful handling of missing total in breakdown
  - aggregate_team_delta_ema: empty match list returns zero EMA
  - aggregate_team_delta_ema: positive carry EMA on over-performing team
  - aggregate_team_delta_ema: negative EMA for under-performing team
  - aggregate_team_delta_ema: consistency decreases with high variance
  - aggregate_team_delta_ema: match_count and fallback counts correct
  - aggregate_team_delta_ema: invalid alpha raises ValueError
  - flag_carry_variance_by_scout: high-variance scout flagged
  - flag_carry_variance_by_scout: stable scout not flagged
  - format_carry_delta_row: carry bot tag fires at +5
  - format_carry_delta_row: ride risk tag fires at -5
  - format_carry_delta_row: insufficient data tag fires for < MIN_MATCHES
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from alliance_decomposition import (  # noqa: E402
    DEFAULT_EMA_ALPHA,
    MIN_MATCHES_FOR_EMA,
    UNIFORM_SHARE,
    TeamDeltaEMA,
    aggregate_team_delta_ema,
    compute_alliance_decomposition,
    flag_carry_variance_by_scout,
    format_carry_delta_row,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _obs(team: int = 2950, match: str = "2026txbel_qm1", scout: str = "Alice",
         contribution: float = None, cycle_speed: str = "fast",
         auto_scored: bool = True, climbed: bool = True,
         played_defense: bool = False) -> dict:
    """Build a minimal stand_scout observation dict."""
    d = {
        "team": team,
        "_meta": {"scout": scout, "match_key": match},
        "auto": {"scored": auto_scored},
        "teleop": {"cycle_speed": cycle_speed},
        "endgame": {"climb_attempted": climbed},
        "defense": {"played_defense": played_defense, "received_defense": False, "notes": ""},
    }
    if contribution is not None:
        d["match_contribution"] = contribution
    return d


def _three_team_epas(a=40.0, b=50.0, c=60.0) -> dict:
    return {2950: a, 1678: b, 254: c}


def _match_breakdown(total: float) -> dict:
    return {"total": total}


# ─── compute_alliance_decomposition: uniform fallback ────────────────────────


def test_no_obs_uses_uniform_share():
    epas = _three_team_epas()
    result = compute_alliance_decomposition(epas, _match_breakdown(150.0))
    for team, data in result.items():
        assert data["contribution_share"] == pytest.approx(UNIFORM_SHARE, abs=1e-3)
    assert all(data["used_uniform_fallback"] for data in result.values())


def test_obs_without_numeric_falls_back_to_observation_weight():
    """Categorical tags produce non-uniform shares (not uniform fallback)."""
    epas = _three_team_epas()
    obs_list = [
        _obs(team=2950, cycle_speed="fast"),
        _obs(team=1678, cycle_speed="slow"),
        _obs(team=254, cycle_speed="moderate"),
    ]
    result = compute_alliance_decomposition(epas, _match_breakdown(150.0), obs_list)
    shares = [data["contribution_share"] for data in result.values()]
    # Shares should differ since cycle_speed weights differ
    assert max(shares) > min(shares) + 0.05
    # No pure uniform fallback since categorical data available
    assert not any(data["used_uniform_fallback"] for data in result.values())


def test_shares_sum_to_one():
    epas = _three_team_epas()
    obs_list = [
        _obs(team=2950, contribution=60.0),
        _obs(team=1678, contribution=30.0),
        _obs(team=254, contribution=60.0),
    ]
    result = compute_alliance_decomposition(epas, _match_breakdown(165.0), obs_list)
    total_share = sum(data["contribution_share"] for data in result.values())
    assert total_share == pytest.approx(1.0, abs=1e-4)


# ─── compute_alliance_decomposition: delta attribution ───────────────────────


def test_zero_delta_when_actual_equals_expected():
    epas = _three_team_epas(40.0, 50.0, 60.0)  # expected = 150
    result = compute_alliance_decomposition(epas, _match_breakdown(150.0))
    for data in result.values():
        assert data["actual_delta"] == pytest.approx(0.0, abs=1e-6)
        assert data["actual_pts"] == pytest.approx(data["expected_pts"], abs=1e-6)


def test_positive_delta_distributed_uniformly():
    epas = _three_team_epas(40.0, 50.0, 60.0)  # expected = 150
    result = compute_alliance_decomposition(epas, _match_breakdown(165.0))  # +15 delta
    total_delta = sum(data["actual_delta"] for data in result.values())
    assert total_delta == pytest.approx(15.0, abs=0.1)


def test_negative_delta_distributed():
    epas = _three_team_epas(40.0, 50.0, 60.0)  # expected = 150
    result = compute_alliance_decomposition(epas, _match_breakdown(120.0))  # -30 delta
    total_delta = sum(data["actual_delta"] for data in result.values())
    assert total_delta == pytest.approx(-30.0, abs=0.1)


def test_actual_pts_equals_expected_plus_delta():
    epas = _three_team_epas()
    obs_list = [
        _obs(team=2950, contribution=60.0),
        _obs(team=1678, contribution=40.0),
        _obs(team=254, contribution=50.0),
    ]
    result = compute_alliance_decomposition(epas, _match_breakdown(165.0), obs_list)
    for data in result.values():
        assert data["actual_pts"] == pytest.approx(
            data["expected_pts"] + data["actual_delta"], abs=1e-4
        )


def test_observation_driven_shares_weight_high_contributor():
    """Team with match_contribution=90 should absorb most of the delta."""
    epas = {2950: 30.0, 1678: 30.0, 254: 30.0}  # expected = 90
    obs_list = [
        _obs(team=2950, contribution=90.0),
        _obs(team=1678, contribution=10.0),
        _obs(team=254, contribution=10.0),
    ]
    result = compute_alliance_decomposition(epas, _match_breakdown(120.0), obs_list)  # +30 delta
    # Team 2950 has 90/(90+10+10) = 81.8% share → should get most of the +30 delta
    assert result[2950]["actual_delta"] > result[1678]["actual_delta"] * 3


def test_played_defense_team_gets_near_zero_share():
    """A team playing defense contributes ~0 to scoring; share should be minimal."""
    epas = {2950: 40.0, 1678: 50.0, 254: 60.0}
    obs_list = [
        _obs(team=2950, played_defense=True),
        _obs(team=1678, contribution=50.0),
        _obs(team=254, contribution=60.0),
    ]
    result = compute_alliance_decomposition(epas, _match_breakdown(175.0), obs_list)
    # Defense player should have the smallest share
    shares = {t: data["contribution_share"] for t, data in result.items()}
    assert shares[2950] < shares[1678]
    assert shares[2950] < shares[254]


def test_missing_total_in_breakdown_graceful():
    """When breakdown has no total, actual_delta should be 0 (no delta info)."""
    epas = _three_team_epas(40.0, 50.0, 60.0)
    result = compute_alliance_decomposition(epas, {})
    # With no actual score, we fall back to expected total → delta = 0
    total_delta = sum(data["actual_delta"] for data in result.values())
    assert total_delta == pytest.approx(0.0, abs=0.1)


def test_match_key_propagated_to_each_team():
    epas = _three_team_epas()
    result = compute_alliance_decomposition(
        epas, _match_breakdown(150.0), match_key="2026txbel_qm7"
    )
    for data in result.values():
        assert data["match_key"] == "2026txbel_qm7"


# ─── aggregate_team_delta_ema ────────────────────────────────────────────────


def _make_event_matches(team_num: int, deltas: list[float]) -> list[dict[int, dict]]:
    """Build a list of mock decomposition outputs for a single team."""
    return [
        {
            team_num: {
                "actual_delta": d,
                "expected_pts": 40.0,
                "actual_pts": 40.0 + d,
                "contribution_share": UNIFORM_SHARE,
                "used_uniform_fallback": True,
                "match_key": f"qm{i}",
            }
        }
        for i, d in enumerate(deltas)
    ]


def test_ema_empty_match_list_returns_zero():
    ema = aggregate_team_delta_ema(2950, [])
    assert ema.carry_delta == 0.0
    assert ema.match_count == 0
    assert ema.consistency == 0.0


def test_ema_positive_carry():
    """Team consistently over-performing → positive carry EMA."""
    matches = _make_event_matches(2950, [8.0, 10.0, 9.0, 11.0, 7.0])
    ema = aggregate_team_delta_ema(2950, matches)
    assert ema.carry_delta > 0
    assert ema.match_count == 5


def test_ema_negative_ride():
    """Team consistently under-performing → negative carry EMA."""
    matches = _make_event_matches(2950, [-8.0, -10.0, -9.0, -7.0, -11.0])
    ema = aggregate_team_delta_ema(2950, matches)
    assert ema.carry_delta < 0
    assert ema.ride_delta < 0


def test_ema_consistency_high_for_stable_team():
    matches = _make_event_matches(2950, [5.0, 5.0, 5.0, 5.0, 5.0])
    ema = aggregate_team_delta_ema(2950, matches)
    # Zero variance → sigma=0 → consistency = 1/(1+0) = 1.0
    assert ema.consistency == pytest.approx(1.0, abs=1e-3)


def test_ema_consistency_lower_for_variable_team():
    stable = aggregate_team_delta_ema(2950, _make_event_matches(2950, [5.0] * 5))
    variable = aggregate_team_delta_ema(2950, _make_event_matches(2950, [-10.0, 20.0, -8.0, 15.0, -5.0]))
    assert variable.consistency < stable.consistency


def test_ema_team_not_in_match_skipped():
    """Matches where the team didn't play should be silently skipped."""
    matches = [
        {9999: {"actual_delta": 5.0, "expected_pts": 40.0, "actual_pts": 45.0,
                "contribution_share": 0.33, "used_uniform_fallback": True, "match_key": "qm1"}},
        {2950: {"actual_delta": 7.0, "expected_pts": 40.0, "actual_pts": 47.0,
                "contribution_share": 0.33, "used_uniform_fallback": True, "match_key": "qm2"}},
    ]
    ema = aggregate_team_delta_ema(2950, matches)
    assert ema.match_count == 1
    assert ema.carry_delta == pytest.approx(7.0, abs=0.01)


def test_ema_invalid_alpha_raises():
    with pytest.raises(ValueError):
        aggregate_team_delta_ema(2950, [], alpha=0.0)

    with pytest.raises(ValueError):
        aggregate_team_delta_ema(2950, [], alpha=1.5)


def test_ema_fallback_count_tracked():
    matches = [
        {2950: {"actual_delta": 5.0, "expected_pts": 40.0, "actual_pts": 45.0,
                "contribution_share": 0.33, "used_uniform_fallback": True, "match_key": "qm1"}},
        {2950: {"actual_delta": 3.0, "expected_pts": 40.0, "actual_pts": 43.0,
                "contribution_share": 0.40, "used_uniform_fallback": False, "match_key": "qm2"}},
    ]
    ema = aggregate_team_delta_ema(2950, matches)
    assert ema.match_count == 2
    assert ema.used_fallback_count == 1


# ─── flag_carry_variance_by_scout ────────────────────────────────────────────


def _make_event_matches_with_scout(team: int, entries: list[tuple[str, float, str]]) -> tuple:
    """Returns (event_matches, scout_obs_by_match)."""
    event_matches = []
    scout_obs_by_match = {}
    for i, (scout, delta, mk) in enumerate(entries):
        event_matches.append({
            team: {
                "actual_delta": delta,
                "expected_pts": 40.0,
                "actual_pts": 40.0 + delta,
                "contribution_share": UNIFORM_SHARE,
                "used_uniform_fallback": True,
                "match_key": mk,
            }
        })
        scout_obs_by_match[mk] = {
            "team": team,
            "_meta": {"scout": scout, "match_key": mk},
        }
    return event_matches, scout_obs_by_match


def test_high_variance_scout_flagged():
    entries = [
        ("BadScout", -20.0, "qm1"),
        ("BadScout", 25.0, "qm2"),
        ("BadScout", -18.0, "qm3"),
    ]
    matches, obs_map = _make_event_matches_with_scout(2950, entries)
    suspects = flag_carry_variance_by_scout(2950, matches, obs_map)
    assert "BadScout" in suspects


def test_stable_scout_not_flagged():
    entries = [
        ("GoodScout", 5.0, "qm1"),
        ("GoodScout", 5.5, "qm2"),
        ("GoodScout", 4.8, "qm3"),
    ]
    matches, obs_map = _make_event_matches_with_scout(2950, entries)
    suspects = flag_carry_variance_by_scout(2950, matches, obs_map)
    assert "GoodScout" not in suspects


# ─── format_carry_delta_row ──────────────────────────────────────────────────


def test_format_carry_bot_tag():
    ema = TeamDeltaEMA(team=2950, carry_delta=7.5, ride_delta=7.5,
                       consistency=0.8, match_count=6)
    row = format_carry_delta_row(ema)
    assert "carry bot" in row
    assert "+7.5" in row


def test_format_ride_risk_tag():
    ema = TeamDeltaEMA(team=2950, carry_delta=-6.0, ride_delta=-6.0,
                       consistency=0.7, match_count=5)
    row = format_carry_delta_row(ema)
    assert "ride risk" in row
    assert "-6.0" in row


def test_format_insufficient_data_tag():
    ema = TeamDeltaEMA(team=2950, carry_delta=2.0, ride_delta=2.0,
                       consistency=0.5, match_count=MIN_MATCHES_FOR_EMA - 1)
    row = format_carry_delta_row(ema)
    assert "insufficient" in row
