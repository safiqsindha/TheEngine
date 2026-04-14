"""Tests for power_normalize() helper in scout/alliance_decomposition.py.

Covers:
  - beta=1.0 matches linear share on [12, 3, 1]
  - beta=0.7 on [12, 3, 1] gives shares ≈ [0.645, 0.243, 0.112]
  - beta→0.01 approaches uniform within tolerance
  - All-zero input → uniform [1/3, 1/3, 1/3]
  - Empty input → []
  - Negative contribution raises ValueError
  - Single element → [1.0]
  - End-to-end: compute_alliance_decomposition(..., beta=0.7) produces expected attributed deltas
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from alliance_decomposition import (  # noqa: E402
    compute_alliance_decomposition,
    power_normalize,
)


# ─── power_normalize unit tests ───────────────────────────────────────────────


def test_beta1_matches_linear():
    """beta=1.0 must reproduce simple proportional shares exactly."""
    contributions = [12.0, 3.0, 1.0]
    total = sum(contributions)
    expected = [c / total for c in contributions]
    result = power_normalize(contributions, beta=1.0)
    assert len(result) == 3
    for r, e in zip(result, expected):
        assert r == pytest.approx(e, abs=1e-9)


def test_beta_07_worked_example():
    """beta=0.7 on [12, 3, 1] → shares ≈ [0.645, 0.243, 0.112]."""
    result = power_normalize([12.0, 3.0, 1.0], beta=0.7)
    assert result[0] == pytest.approx(0.645, abs=0.005)
    assert result[1] == pytest.approx(0.243, abs=0.005)
    assert result[2] == pytest.approx(0.112, abs=0.005)


def test_beta_near_zero_approaches_uniform():
    """beta→0.01 should yield shares within 2% of 1/3 each."""
    result = power_normalize([12.0, 3.0, 1.0], beta=0.01)
    for share in result:
        assert share == pytest.approx(1.0 / 3.0, abs=0.02)


def test_all_zeros_returns_uniform():
    result = power_normalize([0.0, 0.0, 0.0])
    assert len(result) == 3
    for share in result:
        assert share == pytest.approx(1.0 / 3.0, abs=1e-9)


def test_empty_input_returns_empty():
    assert power_normalize([]) == []


def test_negative_contribution_raises():
    with pytest.raises(ValueError):
        power_normalize([10.0, -1.0, 5.0])


def test_single_element_returns_one():
    result = power_normalize([42.0], beta=0.7)
    assert result == [pytest.approx(1.0)]


def test_shares_sum_to_one():
    """Shares must always sum to 1.0 regardless of beta."""
    for beta in [0.01, 0.5, 1.0, 2.0]:
        result = power_normalize([12.0, 3.0, 1.0], beta=beta)
        assert sum(result) == pytest.approx(1.0, abs=1e-9), f"failed for beta={beta}"


def test_beta_less_than_one_compresses_spread():
    """beta<1 should give the low contributor more share than linear."""
    linear = power_normalize([12.0, 3.0, 1.0], beta=1.0)
    concave = power_normalize([12.0, 3.0, 1.0], beta=0.5)
    # Low contributor (index 2) gets more under concave
    assert concave[2] > linear[2]
    # High contributor (index 0) gets less under concave
    assert concave[0] < linear[0]


# ─── End-to-end: compute_alliance_decomposition with beta=0.7 ────────────────


def _obs(team: int, contribution: float) -> dict:
    return {
        "team": team,
        "match_contribution": contribution,
    }


def test_e2e_beta07_attributed_deltas():
    """
    With contributions [12, 3, 1] and beta=0.7, shares ≈ [0.645, 0.243, 0.112].
    Alliance delta = 100 - 90 = +10.
    Expected deltas ≈ [6.45, 2.43, 1.12].
    """
    epas = {2950: 30.0, 1678: 30.0, 254: 30.0}  # expected total = 90
    obs_list = [
        _obs(team=2950, contribution=12.0),
        _obs(team=1678, contribution=3.0),
        _obs(team=254, contribution=1.0),
    ]
    result = compute_alliance_decomposition(
        epas, {"total": 100.0}, obs_list, beta=0.7
    )
    assert result[2950]["actual_delta"] == pytest.approx(6.45, abs=0.1)
    assert result[1678]["actual_delta"] == pytest.approx(2.43, abs=0.1)
    assert result[254]["actual_delta"] == pytest.approx(1.12, abs=0.1)
    # Shares should sum to 1
    total_share = sum(d["contribution_share"] for d in result.values())
    assert total_share == pytest.approx(1.0, abs=1e-3)


def test_e2e_beta1_preserves_linear():
    """beta=1.0 (default) must give identical results to omitting beta."""
    epas = {2950: 30.0, 1678: 30.0, 254: 30.0}
    obs_list = [
        _obs(team=2950, contribution=12.0),
        _obs(team=1678, contribution=3.0),
        _obs(team=254, contribution=1.0),
    ]
    default_result = compute_alliance_decomposition(epas, {"total": 100.0}, obs_list)
    beta1_result = compute_alliance_decomposition(
        epas, {"total": 100.0}, obs_list, beta=1.0
    )
    for team in [2950, 1678, 254]:
        assert default_result[team]["actual_delta"] == pytest.approx(
            beta1_result[team]["actual_delta"], abs=1e-6
        )
        assert default_result[team]["contribution_share"] == pytest.approx(
            beta1_result[team]["contribution_share"], abs=1e-6
        )
