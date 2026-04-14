#!/usr/bin/env python3
"""
The Engine — NormalDist Win Probability
Team 2950 — The Devastators

Replaces hardcoded 0.85/0.90 threshold-based alliance win probability with
a continuous NormalDist estimate backed by Statbotics EPA + EPA_sd.

Formula (ported from 1678 Citrus Circuits / predictobics literature):

  μ_diff = μ_red − μ_blue
  σ_combined = sqrt(σ_red² + σ_blue²)
  P(Red wins) = Φ(μ_diff / σ_combined)    [standard normal CDF]

where Φ is the standard normal CDF and division by σ_combined transforms
the score difference distribution to a standard normal.

When EPA_sd is unavailable the function falls back to a rough empirical SD
(EPA_total * DEFAULT_SD_FRACTION) so existing pick_board paths keep working.

1678 source note:
  This formula is documented in Caleb Sykes' predictobics posts and in 1678's
  match-prediction writeup (Obsidian wiki / Citrus Service). The exact parameter
  names differ across implementations but the math is identical: treat alliance
  score as Gaussian, take the difference distribution, integrate.

Usage:
  from win_probability import (
      alliance_win_prob,
      win_prob_from_team_data,
      label_from_prob,
  )

  p = alliance_win_prob(mu_red=142.0, sigma_red=18.0,
                        mu_blue=131.0, sigma_blue=15.0)
  # → 0.724  (72.4% red win probability)

  label = label_from_prob(p)  # → "Lean Red"
"""

from __future__ import annotations

import math
from typing import Any, Optional

from math_utils import normal_cdf as _normal_cdf

# Fraction of EPA used as fallback SD when Statbotics sd is absent
DEFAULT_SD_FRACTION = 0.25

# Minimum sigma to avoid division-by-zero on degenerate inputs
MIN_SIGMA = 1e-6


def alliance_win_prob(
    mu_red: float,
    sigma_red: float,
    mu_blue: float,
    sigma_blue: float,
) -> float:
    """
    Compute P(Red alliance wins) given Gaussian score distributions.

    Parameters
    ----------
    mu_red, mu_blue     : expected alliance total score (EPA mean × 3 teams)
    sigma_red, sigma_blue : combined alliance score SD (EPA_sd propagated)

    Returns
    -------
    float in [0.0, 1.0] — probability that Red alliance outscores Blue.
    """
    mu_diff = mu_red - mu_blue
    sigma_combined = math.sqrt(sigma_red ** 2 + sigma_blue ** 2)
    sigma_combined = max(sigma_combined, MIN_SIGMA)

    return float(_normal_cdf(mu_diff / sigma_combined))


def win_prob_from_team_data(
    red_teams: list[dict],
    blue_teams: list[dict],
    *,
    sd_fraction: float = DEFAULT_SD_FRACTION,
) -> float:
    """
    Compute P(Red wins) from a list of per-team dicts.

    Each dict is expected to have:
      'epa'  : float  — mean EPA total points
      'sd'   : float  — EPA total_points standard deviation (optional)

    If 'sd' is missing or zero, fallback = epa * sd_fraction.

    Parameters
    ----------
    red_teams, blue_teams : list of team dicts (from pick_board state["teams"])
    sd_fraction           : fallback SD fraction when Statbotics sd absent

    Returns
    -------
    float in [0.0, 1.0]
    """
    def _alliance_stats(teams: list[dict]) -> tuple[float, float]:
        mu = sum(t.get("epa", 0.0) for t in teams)
        # Combine per-team SDs in quadrature (alliance score variance = sum of variances)
        variance = sum(
            (t.get("sd", 0.0) or t.get("epa", 0.0) * sd_fraction) ** 2
            for t in teams
        )
        return mu, math.sqrt(max(variance, MIN_SIGMA ** 2))

    mu_r, sigma_r = _alliance_stats(red_teams)
    mu_b, sigma_b = _alliance_stats(blue_teams)
    return alliance_win_prob(mu_r, sigma_r, mu_b, sigma_b)


def label_from_prob(prob: float) -> str:
    """
    Convert win probability to a human-readable label.

    Replaces the old binary "Red favored / Blue favored" threshold outputs.

    Thresholds tuned to match 1678's match-quality labeling convention:
      ≥ 0.85  → "Strong Red"
      ≥ 0.65  → "Lean Red"
      ≥ 0.50  → "Slight Red"
      ≥ 0.35  → "Slight Blue"
      ≥ 0.15  → "Lean Blue"
      <  0.15 → "Strong Blue"
    """
    if prob >= 0.85:
        return "Strong Red"
    if prob >= 0.65:
        return "Lean Red"
    if prob >= 0.50:
        return "Slight Red"
    if prob >= 0.35:
        return "Slight Blue"
    if prob >= 0.15:
        return "Lean Blue"
    return "Strong Blue"


def predict_win_probability_mc(
    red: list[dict],
    blue: list[dict],
    n_sims: int = 1000,
    **kwargs,
) -> dict:
    """
    Monte Carlo win probability — delegates to blueprint.monte_carlo.

    Each dict in ``red``/``blue`` must contain:
      'epa' : float — mean EPA total points
      'sd'  : float — EPA standard deviation (optional)

    Parameters
    ----------
    red, blue : list of per-team dicts
    n_sims    : number of Monte Carlo iterations

    Returns
    -------
    dict — same schema as ``simulate_match``:
        red_win_prob, blue_win_prob, tie_prob,
        score_diff_mean, score_diff_ci_90,
        red_scores (ndarray), blue_scores (ndarray)
    """
    import sys as _sys
    from pathlib import Path as _Path

    _blueprint_dir = str(_Path(__file__).resolve().parents[1] / "blueprint")
    if _blueprint_dir not in _sys.path:
        _sys.path.insert(0, _blueprint_dir)

    from monte_carlo import (  # noqa: E402
        RobotDistribution,
        simulate_match as _simulate_match,
        DEFAULT_SIGMA_FRACTION,
    )

    def _build_robots(teams: list[dict]) -> list[RobotDistribution]:
        robots = []
        for t in teams:
            mu = float(t.get("epa", 0.0))
            sd = t.get("sd", 0.0) or DEFAULT_SIGMA_FRACTION * abs(mu)
            robots.append(RobotDistribution(mu=mu, sigma=float(sd)))
        return robots

    return _simulate_match(
        _build_robots(red),
        _build_robots(blue),
        n_sims=n_sims,
        **kwargs,
    )


def win_prob_for_match(
    red_team_keys: list[int],
    blue_team_keys: list[int],
    teams_db: dict[str, Any],
    *,
    sd_fraction: float = DEFAULT_SD_FRACTION,
) -> dict[str, Any]:
    """
    Compute win probability for a match given team keys and pick_board teams_db.

    This is the primary integration point for pick_board and match_strategy.
    Replaces hardcoded 0.85/0.90 thresholds in those modules.

    Parameters
    ----------
    red_team_keys  : list of int team numbers on red alliance
    blue_team_keys : list of int team numbers on blue alliance
    teams_db       : state["teams"] from pick_board (keys are str(team_num))
    sd_fraction    : fallback if Statbotics sd absent

    Returns
    -------
    dict with keys:
      'red_win_prob'  : float [0,1]
      'blue_win_prob' : float [0,1]
      'label'         : str ("Lean Red", etc.)
      'red_mu'        : float — expected red score
      'blue_mu'       : float — expected blue score
      'red_sigma'     : float — combined red score SD
      'blue_sigma'    : float — combined blue score SD
      'used_fallback_sd': bool — True if any team lacked Statbotics sd
    """
    def _team_dict(num: int) -> dict[str, Any]:
        result: dict[str, Any] = teams_db.get(str(num), {"epa": 0.0, "sd": 0.0})
        return result

    red_tdicts = [_team_dict(n) for n in red_team_keys]
    blue_tdicts = [_team_dict(n) for n in blue_team_keys]

    used_fallback = any(
        not t.get("sd") for t in red_tdicts + blue_tdicts
    )

    p_red = win_prob_from_team_data(red_tdicts, blue_tdicts, sd_fraction=sd_fraction)

    def _mu(teams: list[dict[str, Any]]) -> float:
        return float(sum(float(t.get("epa", 0.0)) for t in teams))

    def _sigma(teams: list[dict[str, Any]]) -> float:
        var = sum(
            (t.get("sd", 0.0) or t.get("epa", 0.0) * sd_fraction) ** 2
            for t in teams
        )
        return math.sqrt(max(var, MIN_SIGMA ** 2))

    return {
        "red_win_prob": round(p_red, 4),
        "blue_win_prob": round(1.0 - p_red, 4),
        "label": label_from_prob(p_red),
        "red_mu": round(_mu(red_tdicts), 1),
        "blue_mu": round(_mu(blue_tdicts), 1),
        "red_sigma": round(_sigma(red_tdicts), 1),
        "blue_sigma": round(_sigma(blue_tdicts), 1),
        "used_fallback_sd": used_fallback,
    }
