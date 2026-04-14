"""Tests for scout/win_probability.py — NormalDist win probability.

Covers:
  - Symmetric alliances → P = 0.5
  - Strong favorite → P > 0.85
  - Heavy underdog → P < 0.15
  - P(Red) + P(Blue) = 1.0
  - Fallback SD from EPA fraction when sd=0
  - win_prob_for_match returns correctly structured dict
  - label_from_prob labels across all six thresholds
  - Zero EPA edge case doesn't crash
  - MIN_SIGMA prevents division by zero
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from win_probability import (  # noqa: E402
    DEFAULT_SD_FRACTION,
    MIN_SIGMA,
    alliance_win_prob,
    label_from_prob,
    win_prob_for_match,
    win_prob_from_team_data,
)


# ─── alliance_win_prob ────────────────────────────────────────────────────────


def test_symmetric_alliances_returns_half():
    p = alliance_win_prob(mu_red=120.0, sigma_red=15.0,
                          mu_blue=120.0, sigma_blue=15.0)
    assert abs(p - 0.5) < 1e-9


def test_strong_favorite_high_prob():
    # Red EPA 180, blue EPA 100 — big gap
    p = alliance_win_prob(mu_red=180.0, sigma_red=10.0,
                          mu_blue=100.0, sigma_blue=10.0)
    assert p > 0.85


def test_underdog_low_prob():
    p = alliance_win_prob(mu_red=100.0, sigma_red=10.0,
                          mu_blue=180.0, sigma_blue=10.0)
    assert p < 0.15


def test_probabilities_sum_to_one():
    p_red = alliance_win_prob(mu_red=150.0, sigma_red=20.0,
                              mu_blue=135.0, sigma_blue=18.0)
    p_blue = 1.0 - p_red
    assert abs(p_red + p_blue - 1.0) < 1e-12


def test_result_in_zero_one():
    p = alliance_win_prob(mu_red=200.0, sigma_red=5.0,
                          mu_blue=50.0, sigma_blue=5.0)
    assert 0.0 <= p <= 1.0


def test_zero_sigma_uses_min_sigma():
    # Should not raise; sigma clamped by MIN_SIGMA
    p = alliance_win_prob(mu_red=130.0, sigma_red=0.0,
                          mu_blue=120.0, sigma_blue=0.0)
    assert 0.0 <= p <= 1.0


def test_equal_mu_higher_sigma_stays_at_half():
    # Equal means → still 0.5 regardless of sigma magnitude
    p = alliance_win_prob(mu_red=100.0, sigma_red=50.0,
                          mu_blue=100.0, sigma_blue=50.0)
    assert abs(p - 0.5) < 1e-9


# ─── win_prob_from_team_data ─────────────────────────────────────────────────


def _team(epa: float, sd: float = 0.0) -> dict:
    return {"epa": epa, "sd": sd}


def test_from_team_data_symmetric():
    red = [_team(50.0, 8.0)] * 3
    blue = [_team(50.0, 8.0)] * 3
    p = win_prob_from_team_data(red, blue)
    assert abs(p - 0.5) < 1e-9


def test_from_team_data_red_favored():
    red = [_team(60.0, 8.0)] * 3
    blue = [_team(40.0, 8.0)] * 3
    p = win_prob_from_team_data(red, blue)
    assert p > 0.5


def test_from_team_data_fallback_sd_when_zero():
    """When sd=0 the fallback (epa * fraction) should still produce a valid prob."""
    red = [_team(60.0, 0.0)] * 3
    blue = [_team(40.0, 0.0)] * 3
    p = win_prob_from_team_data(red, blue, sd_fraction=DEFAULT_SD_FRACTION)
    assert 0.0 < p <= 1.0
    assert p > 0.5


def test_from_team_data_zero_epa_no_crash():
    red = [_team(0.0, 0.0)] * 3
    blue = [_team(0.0, 0.0)] * 3
    p = win_prob_from_team_data(red, blue)
    assert abs(p - 0.5) < 1e-6


# ─── win_prob_for_match ───────────────────────────────────────────────────────


def _make_teams_db(*epas_sds) -> dict:
    """Build a pick_board-style teams_db keyed by str(team_num)."""
    db = {}
    for i, (epa, sd) in enumerate(epas_sds, start=1000):
        db[str(i)] = {"epa": epa, "sd": sd, "name": f"Team {i}"}
    return db


def test_win_prob_for_match_structure():
    db = _make_teams_db((60.0, 8.0), (55.0, 7.0), (50.0, 6.0),
                        (40.0, 5.0), (38.0, 5.0), (35.0, 4.0))
    result = win_prob_for_match(
        red_team_keys=[1000, 1001, 1002],
        blue_team_keys=[1003, 1004, 1005],
        teams_db=db,
    )
    assert "red_win_prob" in result
    assert "blue_win_prob" in result
    assert "label" in result
    assert "red_mu" in result
    assert "blue_mu" in result
    assert "red_sigma" in result
    assert "blue_sigma" in result
    assert "used_fallback_sd" in result


def test_win_prob_for_match_probabilities_sum_to_one():
    db = _make_teams_db((55.0, 9.0), (48.0, 8.0), (45.0, 7.0),
                        (42.0, 6.0), (40.0, 6.0), (38.0, 5.0))
    result = win_prob_for_match([1000, 1001, 1002], [1003, 1004, 1005], db)
    assert abs(result["red_win_prob"] + result["blue_win_prob"] - 1.0) < 1e-6


def test_win_prob_for_match_detects_fallback_sd():
    # sd=0 for all teams → used_fallback_sd should be True
    db = _make_teams_db((50.0, 0.0), (50.0, 0.0), (50.0, 0.0),
                        (50.0, 0.0), (50.0, 0.0), (50.0, 0.0))
    result = win_prob_for_match([1000, 1001, 1002], [1003, 1004, 1005], db)
    assert result["used_fallback_sd"] is True


def test_win_prob_for_match_missing_team_treated_as_zero():
    db = _make_teams_db((50.0, 8.0), (50.0, 8.0), (50.0, 8.0))
    # Blue teams not in db → EPA 0
    result = win_prob_for_match([1000, 1001, 1002], [9999, 9998, 9997], db)
    # Red should be heavy favorite
    assert result["red_win_prob"] > 0.8


# ─── label_from_prob ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("prob,expected_label", [
    (0.95, "Strong Red"),
    (0.85, "Strong Red"),
    (0.75, "Lean Red"),
    (0.65, "Lean Red"),
    (0.55, "Slight Red"),
    (0.50, "Slight Red"),
    (0.40, "Slight Blue"),
    (0.35, "Slight Blue"),
    (0.20, "Lean Blue"),
    (0.15, "Lean Blue"),
    (0.05, "Strong Blue"),
    (0.00, "Strong Blue"),
])
def test_label_from_prob_all_thresholds(prob, expected_label):
    assert label_from_prob(prob) == expected_label
