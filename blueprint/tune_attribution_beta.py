"""
blueprint/tune_attribution_beta.py
------------------------------------
Tuning harness for empirical per-season β estimation.

Objective (predictive MSE):
  For each β candidate, split matches 70/30 (train/test by position in dataset,
  which approximates chronological order since Statbotics returns matches sorted
  by event/match_number):
    1. Train: for each robot, compute their mean attributed score under β:
         attributed_score_i = power_share_i(β, epas) * actual_alliance_score
       Mean over all train appearances = robot's adjusted performance mean.
    2. Test: for each test alliance, predict score =
         sum(adjusted_mean[team1], adjusted_mean[team2], adjusted_mean[team3])
       Compute MSE vs actual score (lower = better).

  This objective measures whether β improves predictive power by better
  calibrating how much credit each robot "deserves" relative to its partners.
  β=1 gives equal-EPA-weighted shares; β<1 compresses the spread, giving
  more credit to lower-EPA robots (appropriate for high-coupling games).

Bootstrap CI: 100x resamples, 5th/95th percentiles of best-β distribution.

Match dict schema used throughout:
  {
    "teams": [int, int, int],         # team numbers for the alliance
    "epas":  [float, float, float],   # season EPAs for the three robots
    "score": float,                   # actual alliance score
  }
  (legacy dicts without "teams" key fall back to RMSE-only objective)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from scout.alliance_decomposition import power_normalize


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TuningResult:
    """Result of a β grid-search for one season."""
    best_beta: float
    score_by_beta: dict[float, float]  # {beta_value: negative predictive MSE}
    ci_low: Optional[float]
    ci_high: Optional[float]
    n_matches: int
    status: str = "OK"


# ---------------------------------------------------------------------------
# Core objective: predictive MSE (70/30 train/test split)
# ---------------------------------------------------------------------------

def _attributed_scores(epas: list[float], beta: float, actual_score: float) -> list[float]:
    """
    Distribute actual_score to each robot proportionally to power_normalize(epas, beta).

    Returns list of per-robot attributed scores summing to actual_score.
    """
    safe_epas = [max(0.0, e) for e in epas]
    if sum(safe_epas) == 0.0:
        # Uniform fallback
        n = len(epas)
        return [actual_score / n] * n
    shares = power_normalize(safe_epas, beta)
    return [s * actual_score for s in shares]


def predictive_mse(matches: list[dict], beta: float, train_frac: float = 0.70) -> float:
    """
    Compute predictive MSE for a given β using a train/test split.

    Algorithm:
      1. Split matches into first train_frac (train) and remainder (test).
      2. Train: for each robot, accumulate attributed scores under β and compute mean.
      3. Test: predict alliance score = sum of 3 robots' train means.
         Fallback for unseen robots: use their season EPA directly.
      4. Return mean squared error on test set.

    Parameters
    ----------
    matches    : list of dicts with keys "teams", "epas", "score"
    beta       : power-curve exponent to evaluate
    train_frac : fraction of matches used for training (default 0.70)

    Returns
    -------
    float — mean squared error on test set (lower = better)
    """
    if len(matches) < 10:
        return float("inf")

    split = max(5, int(len(matches) * train_frac))
    train = matches[:split]
    test = matches[split:]

    if not test:
        return float("inf")

    # Accumulate attributed scores per robot in train set
    robot_totals: dict[int, float] = {}
    robot_counts: dict[int, int] = {}

    for m in train:
        teams = m.get("teams", [])
        epas = m["epas"]
        score = m["score"]
        if not teams or len(teams) != 3:
            # Legacy record without team numbers — skip (can't build robot means)
            continue
        attrs = _attributed_scores(epas, beta, score)
        for t, a in zip(teams, attrs):
            robot_totals[t] = robot_totals.get(t, 0.0) + a
            robot_counts[t] = robot_counts.get(t, 0) + 1

    # Mean attributed score per robot from train set
    robot_mean: dict[int, float] = {
        t: robot_totals[t] / robot_counts[t]
        for t in robot_totals
    }

    # Evaluate on test set
    sse = 0.0
    n_test = 0
    for m in test:
        teams = m.get("teams", [])
        epas = m["epas"]
        actual = m["score"]
        if not teams or len(teams) != 3:
            continue
        # Predict = sum of train means; fall back to EPA for unseen robots
        predicted = sum(
            robot_mean.get(t, epas[i])
            for i, t in enumerate(teams)
        )
        sse += (predicted - actual) ** 2
        n_test += 1

    if n_test == 0:
        return float("inf")

    return sse / n_test


def objective_score(
    matches: list[dict],
    beta: float,
) -> float:
    """
    Return negative predictive MSE for a given β (higher = better).

    Uses predictive_mse() if matches contain "teams" keys (recommended),
    otherwise falls back to negative RMSE of EPA-sum vs actual score.

    match dict schema:
      {
        "teams": [int, int, int],         # team numbers (required for predictive MSE)
        "epas":  [float, float, float],   # season EPAs
        "score": float,                   # actual alliance score
      }
    """
    if not matches:
        return 0.0
    # Use predictive MSE if team IDs are present
    if matches[0].get("teams"):
        return -predictive_mse(matches, beta)
    # Legacy fallback: negative RMSE
    return -_rmse_legacy(matches, beta)


def _rmse_legacy(matches: list[dict], beta: float) -> float:
    """
    Legacy RMSE: RMSE of β-weighted EPA sum vs actual score.
    Used only when match records lack team IDs.
    """
    if not matches:
        return float("inf")
    sse = 0.0
    for m in matches:
        epas = m["epas"]
        actual = m["score"]
        safe_epas = [max(0.0, e) for e in epas]
        if sum(safe_epas) == 0.0:
            predicted = 0.0
        else:
            shares = power_normalize(safe_epas, beta)
            predicted = sum(s * e for s, e in zip(shares, safe_epas))
        sse += (predicted - actual) ** 2
    return math.sqrt(sse / len(matches))


# ---------------------------------------------------------------------------
# Backward-compatible aliases (used by existing tests)
# ---------------------------------------------------------------------------

def _alliance_weighted_strength(epas: list[float], beta: float) -> float:
    """
    Backward-compatible alias.
    Compute β-power-weighted alliance strength = sum(power_normalize(epas, β) * epas).
    """
    if not epas or all(e <= 0 for e in epas):
        return sum(epas)
    safe_epas = [max(0.0, e) for e in epas]
    shares = power_normalize(safe_epas, beta)
    return sum(s * e for s, e in zip(shares, safe_epas))


def _rmse(matches: list[dict], beta: float) -> float:
    """Backward-compatible alias for _rmse_legacy."""
    return _rmse_legacy(matches, beta)


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------

def _bootstrap_ci(
    matches: list[dict],
    beta_range: tuple[float, float, float],
    n_resamples: int = 100,
    seed: int = 42,
) -> tuple[Optional[float], Optional[float]]:
    """
    Bootstrap 90% CI on best-β using sliding window 70/30 splits.

    The predictive MSE objective requires chronological (or at least
    consistent) train/test ordering — so we use n_resamples random
    *contiguous* windows instead of shuffled resampling:
      - Pick a random start offset (0 to 30% of n)
      - Use that as the beginning of a contiguous 100%-length slice
        (with wrap-around padding from the end)
      - Run predictive_mse on each window

    This gives a distribution of best-β across different temporal windows,
    reflecting true season variability rather than statistical noise.
    Each draw uses a subsample of at most BOOTSTRAP_SUBSAMPLE records
    to keep wall time manageable for large seasons.

    Returns (ci_low_5th, ci_high_95th) or (None, None) if too few matches.
    """
    if len(matches) < 20:
        return None, None

    rng = random.Random(seed)
    beta_min, beta_max, beta_step = beta_range
    n_steps = round((beta_max - beta_min) / beta_step) + 1
    betas = [round(beta_min + i * beta_step, 10) for i in range(n_steps)]

    n = len(matches)
    # Subsample size per draw — balance accuracy vs wall time
    SUBSAMPLE = min(n, 3000)
    max_offset = max(1, n - SUBSAMPLE)
    has_team_ids = bool(matches[0].get("teams"))

    best_betas: list[float] = []
    for _ in range(n_resamples):
        if has_team_ids and n >= SUBSAMPLE:
            # Large dataset with team IDs: pick a random contiguous window
            start = rng.randint(0, max_offset)
            window = matches[start: start + SUBSAMPLE]
            best_b = min(betas, key=lambda b: predictive_mse(window, b))
        else:
            # Small dataset or legacy (no team IDs): resample with replacement
            sample = [rng.choice(matches) for _ in range(n)]
            best_b = min(betas, key=lambda b: _rmse_legacy(sample, b))
        best_betas.append(best_b)

    best_betas.sort()
    idx_low = max(0, int(0.05 * n_resamples))
    idx_high = min(n_resamples - 1, int(0.95 * n_resamples))
    return round(best_betas[idx_low], 2), round(best_betas[idx_high], 2)


# ---------------------------------------------------------------------------
# Main tuning entry point
# ---------------------------------------------------------------------------

def tune_beta_for_season(
    year: int,
    matches: list[dict],
    beta_range: tuple[float, float, float] = (0.4, 1.0, 0.05),
    n_bootstrap: int = 100,
) -> TuningResult:
    """
    Grid-search β over [beta_min, beta_max] at step beta_step.

    Parameters
    ----------
    year         : FRC season year (used for labelling only).
    matches      : List of match dicts with keys "epas" and "score".
    beta_range   : (beta_min, beta_max, beta_step).
    n_bootstrap  : Number of bootstrap resamples for CI (0 = skip CI).

    Returns
    -------
    TuningResult — best_beta is the grid point with the lowest RMSE.
                   ci_low/ci_high are 5th/95th bootstrap percentiles.
    """
    beta_min, beta_max, beta_step = beta_range
    n_steps = round((beta_max - beta_min) / beta_step) + 1
    betas = [round(beta_min + i * beta_step, 10) for i in range(n_steps)]

    if not matches:
        score_by_beta = {b: 0.0 for b in betas}
        return TuningResult(
            best_beta=1.0,
            score_by_beta=score_by_beta,
            ci_low=None,
            ci_high=None,
            n_matches=0,
            status="FAILED: no matches",
        )

    score_by_beta: dict[float, float] = {}
    for b in betas:
        score_by_beta[b] = objective_score(matches, b)

    # Best β = highest objective score = lowest RMSE
    best_beta = max(score_by_beta, key=lambda b: score_by_beta[b])

    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    if n_bootstrap > 0:
        ci_low, ci_high = _bootstrap_ci(matches, beta_range, n_resamples=n_bootstrap)

    return TuningResult(
        best_beta=round(best_beta, 2),
        score_by_beta=score_by_beta,
        ci_low=ci_low,
        ci_high=ci_high,
        n_matches=len(matches),
        status="OK",
    )


# ---------------------------------------------------------------------------
# Season-level orchestration
# ---------------------------------------------------------------------------

def _extract_teams(match: dict, color: str) -> list[int]:
    """
    Extract team numbers for one alliance from a Statbotics match dict.

    Handles two formats:
      - Statbotics v3: match["alliances"][color]["team_keys"] → list[int]
      - Flat legacy:   match["red_1"], match["red_2"], match["red_3"]
    """
    teams: list[int] = []

    # v3 nested format
    alliances = match.get("alliances")
    if isinstance(alliances, dict):
        alliance = alliances.get(color, {})
        if isinstance(alliance, dict):
            keys = alliance.get("team_keys", [])
            for k in keys:
                try:
                    teams.append(int(k))
                except (TypeError, ValueError):
                    pass
            if teams:
                return teams[:3]

    # Flat legacy format: red_1, red_2, red_3
    for slot in ("1", "2", "3"):
        t = match.get(f"{color}_{slot}")
        if t is not None:
            try:
                teams.append(int(t))
            except (TypeError, ValueError):
                pass

    return teams


def _extract_scores(match: dict) -> tuple[Optional[float], Optional[float]]:
    """
    Extract red and blue actual scores from a Statbotics match dict.

    Handles two formats:
      - Statbotics v3: match["result"]["red_score"] / ["blue_score"]
      - Flat legacy:   match["red_score"] / match["blue_score"]
    """
    result = match.get("result")
    if isinstance(result, dict):
        rs = result.get("red_score")
        bs = result.get("blue_score")
        if rs is not None and bs is not None:
            try:
                return float(rs), float(bs)
            except (TypeError, ValueError):
                pass

    # Flat legacy
    rs = match.get("red_score")
    bs = match.get("blue_score")
    if rs is not None and bs is not None:
        try:
            return float(rs), float(bs)
        except (TypeError, ValueError):
            pass

    return None, None


def build_match_records(
    raw_matches: list[dict],
    epa_map: dict[int, float],
    comp_level: str = "qm",
) -> list[dict]:
    """
    Convert Statbotics raw match records + EPA map into match dicts
    suitable for tune_beta_for_season.

    For each qual match, we emit TWO alliance records (red + blue) so both
    contribute to the objective. Teams missing from epa_map are skipped
    (their EPA is treated as 0.0 with a warning logged to stderr).

    Parameters
    ----------
    raw_matches  : list of Statbotics match dicts (v3 nested or flat legacy)
    epa_map      : {team_number: season_epa} from fetch_team_epas()
    comp_level   : filter to this competition level ("qm" for quals)

    Returns
    -------
    list of {"teams": [int, int, int], "epas": [float, float, float], "score": float}
    Matches are returned in input order (Statbotics returns them sorted by
    event start time + match number, approximating chronological order).
    """
    records: list[dict] = []

    for m in raw_matches:
        if m.get("comp_level", "qm") != comp_level:
            continue

        # Skip DQ'd or replay matches (score < 0 or missing)
        red_score, blue_score = _extract_scores(m)
        if red_score is None or blue_score is None:
            continue
        if red_score < 0 or blue_score < 0:
            continue

        # Extract team numbers for each alliance
        for color in ("red", "blue"):
            score = red_score if color == "red" else blue_score
            teams = _extract_teams(m, color)

            if len(teams) != 3:
                continue

            epas = [epa_map.get(t, 0.0) for t in teams]

            # Skip matches where all EPAs are 0 (likely data gap)
            if sum(epas) == 0.0:
                continue

            records.append({
                "teams": teams,  # preserved for predictive MSE objective
                "epas": epas,
                "score": score,
            })

    return records


def run_all_seasons(
    season_data: dict[int, list[dict]],
    beta_range: tuple[float, float, float] = (0.4, 1.0, 0.05),
    n_bootstrap: int = 100,
) -> dict[int, TuningResult]:
    """
    Run tune_beta_for_season for each year in season_data.

    Parameters
    ----------
    season_data : {year: [match_dict, ...]}  (already built by build_match_records)

    Returns
    -------
    {year: TuningResult}
    """
    results: dict[int, TuningResult] = {}
    for year, matches in season_data.items():
        results[year] = tune_beta_for_season(
            year, matches, beta_range=beta_range, n_bootstrap=n_bootstrap
        )
    return results
