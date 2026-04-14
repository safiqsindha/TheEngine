#!/usr/bin/env python3
"""
The Engine — Monte Carlo Alliance Simulation
Team 2950 — The Devastators

Distribution-based win probability that samples individual robot score
distributions (EPA + uncertainty) and simulates N match outcomes.
Supplements (does not replace) the analytic NormalDist estimator in
scout/win_probability.py.

Key advantages over the analytic one-shot estimate:
  - Non-normal confidence intervals for skewed alliance compositions
  - Dropout / no-show modelling (bimodal robot distributions)
  - Per-robot sigma from Statbotics EPA_sd; fallback = 0.2 * mu

Usage
-----
    from blueprint.monte_carlo import (
        RobotDistribution,
        simulate_alliance_score,
        simulate_match,
        predict_alliance_with_uncertainty,
    )

    rng = numpy.random.default_rng(42)
    robots = [RobotDistribution(mu=50.0, sigma=8.0),
              RobotDistribution(mu=45.0, sigma=7.0),
              RobotDistribution(mu=30.0, sigma=5.0, dropout_prob=0.15)]
    scores = simulate_alliance_score(robots, n_sims=5000, rng=rng)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default sigma fraction of mu when per-robot sigma is not provided
DEFAULT_SIGMA_FRACTION: float = 0.2

#: Minimum sigma to prevent degenerate zero-variance distributions
MIN_SIGMA: float = 1e-6


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RobotDistribution:
    """
    Gaussian score distribution for a single robot.

    Attributes
    ----------
    mu : float
        Expected contribution to alliance score (EPA mean).
    sigma : float
        Standard deviation of the robot's score contribution (EPA_sd).
        Defaults to ``DEFAULT_SIGMA_FRACTION * abs(mu)`` if not set (< 0).
    dropout_prob : float
        Probability [0, 1] that the robot fails to score (no-show / disable).
        When the robot "drops out" its score contribution is replaced by
        ``dropout_penalty``.
    dropout_penalty : float
        Score credited when the robot drops out (often 0 or negative for
        fouls).  Only used when a dropout event fires.
    """

    mu: float
    sigma: float = -1.0  # sentinel → auto-set in __post_init__
    dropout_prob: float = 0.0
    dropout_penalty: float = 0.0

    def __post_init__(self) -> None:
        if self.sigma < 0:
            self.sigma = DEFAULT_SIGMA_FRACTION * abs(self.mu)
        self.sigma = max(self.sigma, MIN_SIGMA)
        if not 0.0 <= self.dropout_prob <= 1.0:
            raise ValueError(
                f"dropout_prob must be in [0, 1]; got {self.dropout_prob}"
            )


# ---------------------------------------------------------------------------
# Core simulation functions
# ---------------------------------------------------------------------------


def simulate_alliance_score(
    robots: list[RobotDistribution],
    n_sims: int = 1000,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """
    Simulate ``n_sims`` alliance score totals by sampling each robot's
    Gaussian contribution and applying dropout events.

    Parameters
    ----------
    robots : list[RobotDistribution]
        Each robot's score distribution.  Must be non-empty.
    n_sims : int
        Number of Monte Carlo draws.  Must be >= 1.
    rng : numpy.random.Generator, optional
        Random number generator for deterministic testing.
        Created with ``numpy.random.default_rng()`` if not provided.

    Returns
    -------
    numpy.ndarray, shape (n_sims,)
        Simulated alliance score totals (float64).

    Raises
    ------
    ValueError
        If ``robots`` is empty or ``n_sims`` < 1.
    """
    if not robots:
        raise ValueError("robots list must be non-empty")
    if n_sims < 1:
        raise ValueError(f"n_sims must be >= 1; got {n_sims}")

    if rng is None:
        rng = np.random.default_rng()

    total = np.zeros(n_sims, dtype=np.float64)

    for robot in robots:
        # Draw Gaussian scores for this robot across all sims
        raw = rng.normal(loc=robot.mu, scale=robot.sigma, size=n_sims)

        if robot.dropout_prob > 0.0:
            # Each sim independently determines if this robot drops out
            dropped = rng.random(size=n_sims) < robot.dropout_prob
            contribution = np.where(dropped, robot.dropout_penalty, raw)
        else:
            contribution = raw

        total += contribution

    return total


def simulate_match(
    red: list[RobotDistribution],
    blue: list[RobotDistribution],
    n_sims: int = 1000,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """
    Simulate a full match between Red and Blue alliances.

    Parameters
    ----------
    red : list[RobotDistribution]
        Red alliance robots.
    blue : list[RobotDistribution]
        Blue alliance robots.
    n_sims : int
        Number of simulation draws.
    rng : numpy.random.Generator, optional
        Shared RNG for reproducibility.  If None, a fresh one is created.

    Returns
    -------
    dict with keys:
        red_win_prob     float   — fraction of sims Red outscored Blue
        blue_win_prob    float   — fraction of sims Blue outscored Red
        tie_prob         float   — fraction of sims scores are equal
        score_diff_mean  float   — mean(red_scores - blue_scores)
        score_diff_ci_90 tuple   — (5th-pctile, 95th-pctile) of score diff
        red_scores       ndarray — raw simulated red totals
        blue_scores      ndarray — raw simulated blue totals

    Raises
    ------
    ValueError
        Propagated from ``simulate_alliance_score`` if either alliance is empty.
    """
    if rng is None:
        rng = np.random.default_rng()

    red_scores = simulate_alliance_score(red, n_sims=n_sims, rng=rng)
    blue_scores = simulate_alliance_score(blue, n_sims=n_sims, rng=rng)

    diff = red_scores - blue_scores

    red_wins = np.sum(diff > 0)
    blue_wins = np.sum(diff < 0)
    ties = np.sum(diff == 0)

    red_win_prob = float(red_wins) / n_sims
    blue_win_prob = float(blue_wins) / n_sims
    tie_prob = float(ties) / n_sims

    ci_lo, ci_hi = float(np.percentile(diff, 5)), float(np.percentile(diff, 95))

    return {
        "red_win_prob": round(red_win_prob, 4),
        "blue_win_prob": round(blue_win_prob, 4),
        "tie_prob": round(tie_prob, 4),
        "score_diff_mean": round(float(diff.mean()), 2),
        "score_diff_ci_90": (round(ci_lo, 2), round(ci_hi, 2)),
        "red_scores": red_scores,
        "blue_scores": blue_scores,
    }


# ---------------------------------------------------------------------------
# High-level wrapper (Scout-data integration)
# ---------------------------------------------------------------------------


def predict_alliance_with_uncertainty(
    teams: list[int],
    epa_lookup: dict[int, float],
    sigma_lookup: dict[int, float],
    *,
    n_sims: int = 1000,
    dropout_prob: float = 0.0,
    dropout_penalty: float = 0.0,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """
    Build ``RobotDistribution`` objects for each team from Scout/Statbotics
    data and simulate alliance score uncertainty.

    Parameters
    ----------
    teams : list[int]
        Team numbers.
    epa_lookup : dict[int, float]
        Maps team number → EPA mean (total points).
    sigma_lookup : dict[int, float]
        Maps team number → EPA standard deviation.
        Missing teams fall back to ``DEFAULT_SIGMA_FRACTION * epa``.
    n_sims : int
        Monte Carlo iterations.
    dropout_prob : float
        Per-robot dropout probability applied uniformly if not team-specific.
    dropout_penalty : float
        Score when a robot drops out.
    rng : numpy.random.Generator, optional
        For reproducibility.

    Returns
    -------
    dict with keys:
        scores      ndarray — simulated alliance score array
        mean        float   — mean simulated score
        std         float   — std-dev of simulated scores
        ci_90       tuple   — (5th, 95th) percentile
        robots      list    — RobotDistribution objects used
    """
    robots: list[RobotDistribution] = []
    for team in teams:
        mu = float(epa_lookup.get(team, 0.0))
        sigma = float(sigma_lookup.get(team, DEFAULT_SIGMA_FRACTION * abs(mu)))
        robots.append(
            RobotDistribution(
                mu=mu,
                sigma=sigma,
                dropout_prob=dropout_prob,
                dropout_penalty=dropout_penalty,
            )
        )

    scores = simulate_alliance_score(robots, n_sims=n_sims, rng=rng)
    ci_lo, ci_hi = float(np.percentile(scores, 5)), float(np.percentile(scores, 95))

    return {
        "scores": scores,
        "mean": round(float(scores.mean()), 2),
        "std": round(float(scores.std()), 2),
        "ci_90": (round(ci_lo, 2), round(ci_hi, 2)),
        "robots": robots,
    }
