#!/usr/bin/env python3
"""
The Engine — TrueSkill Bayesian Ratings
Team 2950 — The Devastators

Bayesian alternative to EPA for FRC team ratings using Microsoft TrueSkill.
Provides online match-by-match updates and conservative skill estimates.

Default parameters follow Microsoft's published TrueSkill spec:
  mu=25, sigma=25/3, beta=25/6, tau=25/300, draw_prob=0.1

Conservative estimate (mu - 3*sigma) gives a 99% lower bound on true skill,
matching the published Microsoft formula used on Xbox Live.

Reference:
  Herbrich, R., Minka, T., & Graepel, T. (2007). TrueSkill™: A Bayesian Skill
  Rating System. Advances in Neural Information Processing Systems 20.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

import trueskill

from math_utils import normal_cdf as _normal_cdf

# ---------------------------------------------------------------------------
# TrueSkill environment — standard FRC parameters
# beta = half the sigma; controls how much a single game outcome matters
# tau = sigma/100; slow skill drift between seasons (set low for within-season)
# draw_prob = 0.1 — ties happen rarely in FRC but not never
# ---------------------------------------------------------------------------
_ENV = trueskill.TrueSkill(
    mu=25.0,
    sigma=25.0 / 3.0,
    beta=25.0 / 6.0,
    tau=25.0 / 300.0,
    draw_probability=0.1,
    backend="scipy",
)

# Ties are declared when |red_score - blue_score| <= this threshold
DRAW_THRESHOLD = 2


@dataclass
class TeamRating:
    """Bayesian skill rating for a single FRC team."""

    team_number: int
    mu: float = field(default=25.0)
    sigma: float = field(default=25.0 / 3.0)
    matches_played: int = field(default=0)

    def _ts_rating(self) -> trueskill.Rating:
        return _ENV.create_rating(mu=self.mu, sigma=self.sigma)

    def __repr__(self) -> str:
        return (
            f"TeamRating(team={self.team_number}, "
            f"mu={self.mu:.2f}, sigma={self.sigma:.2f}, "
            f"matches={self.matches_played})"
        )


# ---------------------------------------------------------------------------
# Core update
# ---------------------------------------------------------------------------

def update_alliance_match(
    red: List[TeamRating],
    blue: List[TeamRating],
    red_score: int,
    blue_score: int,
) -> tuple[List[TeamRating], List[TeamRating]]:
    """Run a TrueSkill 3v3 match update and return updated ratings.

    Draws are declared when |red_score - blue_score| <= DRAW_THRESHOLD (2).

    Args:
        red:        List of TeamRating for red alliance (1-3 teams).
        blue:       List of TeamRating for blue alliance (1-3 teams).
        red_score:  Red alliance final score.
        blue_score: Blue alliance final score.

    Returns:
        (new_red_ratings, new_blue_ratings) — same order as inputs.
    """
    diff = abs(red_score - blue_score)
    drawn = diff <= DRAW_THRESHOLD

    red_ts = [r._ts_rating() for r in red]
    blue_ts = [b._ts_rating() for b in blue]

    if drawn:
        new_red_ts, new_blue_ts = _ENV.rate(
            [red_ts, blue_ts], ranks=[0, 0]
        )
    elif red_score > blue_score:
        new_red_ts, new_blue_ts = _ENV.rate(
            [red_ts, blue_ts], ranks=[0, 1]
        )
    else:
        new_red_ts, new_blue_ts = _ENV.rate(
            [red_ts, blue_ts], ranks=[1, 0]
        )

    new_red = [
        TeamRating(
            team_number=r.team_number,
            mu=nr.mu,
            sigma=nr.sigma,
            matches_played=r.matches_played + 1,
        )
        for r, nr in zip(red, new_red_ts)
    ]
    new_blue = [
        TeamRating(
            team_number=b.team_number,
            mu=nb.mu,
            sigma=nb.sigma,
            matches_played=b.matches_played + 1,
        )
        for b, nb in zip(blue, new_blue_ts)
    ]
    return new_red, new_blue


# ---------------------------------------------------------------------------
# Derived statistics
# ---------------------------------------------------------------------------

def conservative_skill(rating: TeamRating) -> float:
    """Return mu - 3*sigma — Microsoft's published 99% lower-bound estimate."""
    return rating.mu - 3.0 * rating.sigma


def predict_match_win_prob(
    red: List[TeamRating],
    blue: List[TeamRating],
) -> float:
    """Probability that red wins using TrueSkill's Gaussian difference model.

    Models each alliance's total skill as the sum of individual Gaussians,
    then integrates the difference distribution:

        mu_diff  = sum(red mu) - sum(blue mu)
        var_total = sum(red sigma²) + sum(blue sigma²) + 6*beta²
        P(red wins) = Phi(mu_diff / sqrt(var_total))

    The 6*beta² term accounts for per-player performance variance (3 red + 3
    blue), matching TrueSkill's internal win-probability derivation.

    Returns a float in [0, 1].
    """
    if not red or not blue:
        return 0.5

    beta = _ENV.beta
    mu_diff = sum(r.mu for r in red) - sum(b.mu for b in blue)
    variance = (
        sum(r.sigma ** 2 for r in red)
        + sum(b.sigma ** 2 for b in blue)
        + (len(red) + len(blue)) * beta ** 2
    )
    denom = math.sqrt(variance)
    return _normal_cdf(mu_diff / denom)


# ---------------------------------------------------------------------------
# Batch seeding from match history
# ---------------------------------------------------------------------------

def from_match_history(matches: list[dict]) -> dict[int, TeamRating]:
    """Seed ratings from a season's qualification matches.

    Each match dict must contain:
        "red_alliance":  list of team numbers  (int or str)
        "blue_alliance": list of team numbers
        "red_score":     int
        "blue_score":    int

    Matches are processed in list order; unrecognised keys are ignored.
    Teams absent from a given match are unaffected.

    Returns a mapping of team_number -> TeamRating.
    """
    ratings: dict[int, TeamRating] = {}

    def _get(team_number: int) -> TeamRating:
        if team_number not in ratings:
            ratings[team_number] = TeamRating(team_number=team_number)
        return ratings[team_number]

    for match in matches:
        red_nums = [int(t) for t in match["red_alliance"]]
        blue_nums = [int(t) for t in match["blue_alliance"]]
        red_score = int(match["red_score"])
        blue_score = int(match["blue_score"])

        red_ratings = [_get(t) for t in red_nums]
        blue_ratings = [_get(t) for t in blue_nums]

        new_red, new_blue = update_alliance_match(
            red_ratings, blue_ratings, red_score, blue_score
        )

        for r in new_red:
            ratings[r.team_number] = r
        for b in new_blue:
            ratings[b.team_number] = b

    return ratings
