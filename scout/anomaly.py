#!/usr/bin/env python3
"""
The Engine — Scout Anomaly Detection
Team 2950 — The Devastators

Flags outlier scout entries that may indicate bad scouting data, robot
malfunction, or a breakout/breakdown match.

Two algorithms are available — use `ANOMALY_METHOD` to select the default:

Z-SCORE (detect_anomalies):
  For each team, for each tracked metric:
    1. Compute team's historical mean and sigma across all observations
    2. For each observation, compute z = (value − mean) / sigma
    3. Flag entries with |z| > Z_THRESHOLD

ROBUST IQR+MAD (detect_anomalies_robust):
  For each team, for each tracked metric:
    1. Compute median and MAD (median absolute deviation) across observations
    2. Compute modified z-score: |value − median| / (1.4826 × MAD)
    3. Flag entries exceeding mad_threshold (default 3.5)

  Prefer robust when your dataset may contain a contaminating outlier that
  would inflate the mean/sigma and mask the very anomaly you're looking for.

  Comparison finding — crafted fixture [10,10,11,10,10,11,10,10,11,50]:
    - Z-score at threshold=3.0 MISSES the outlier (50 inflates sigma so its
      own z-score is only ~2.7, falling below the threshold).
    - Robust MAD at threshold=3.5 CORRECTLY FLAGS the outlier because the
      median (10) and MAD (0) are unaffected by the single extreme value.
      When MAD=0 and value ≠ median, the modified z-score is set to infinity,
      which always triggers the flag.

The flagged entries are returned as a list consumable by:
  - pick_board "review list" section (highlight teams with flagged matches)
  - pre_event_report (add to pit questions if anomalies found)
  - spr.apply_spr_weights cross-reference (scouts with many flagged entries
    get reduced weight — consistently flagged scout → lower SPR)

Metric extraction from stand_scout observations:
  - "cycle_speed"   → numeric mapping (fast=1.0, moderate=0.6, slow=0.2, unknown=0.5)
  - "auto_scored"   → 1.0 if auto.scored else 0.0
  - "climb_success" → 1.0 if endgame.climb_attempted else 0.0
  - "match_contribution" → raw if present, skip otherwise

1678 source note:
  Citrus' anomaly detection uses game-specific numeric columns from their
  scouting sheets. We generalize to a tag-mapped numeric conversion since
  our stand_scout schema uses categorical tags rather than raw numbers.
  The z-score math is identical; field names differ.

Usage:
  from anomaly import detect_anomalies, detect_anomalies_robust, AnomalyFlag

  # Robust (recommended for competition use — resistant to one bad match)
  flags = detect_anomalies_robust(matches=[obs1, obs2, ...],
                                   metrics=["cycle_speed", "auto_scored"])
  # Classic z-score (faster intuition, fine for clean data)
  flags = detect_anomalies(team_matches=[obs1, obs2, ...],
                            metrics=["cycle_speed", "auto_scored"])
  for f in flags:
      print(f.team, f.metric, f.z_score, f.reason)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

# |z| threshold beyond which an entry is flagged
Z_THRESHOLD = 2.5

# Minimum observations needed to compute meaningful mean/sigma.
# Fewer entries → skip (can't calculate reliable z-score).
MIN_OBS_FOR_ZSCORE = 3

# Which anomaly method to prefer.
# "robust" → detect_anomalies_robust (MAD-based, resistant to outlier contamination)
# "zscore" → detect_anomalies (classic mean/sigma, fine for clean or large datasets)
# Use "robust" for competition scouting where a single bad match or robot
# breakdown can inflate sigma and mask the very anomaly you're hunting for.
ANOMALY_METHOD = "robust"

# Cycle-speed → numeric contribution fraction
_SPEED_NUMERIC = {
    "fast": 1.0,
    "moderate": 0.6,
    "slow": 0.2,
    "unknown": 0.5,
}

# Severity thresholds (absolute z-score)
_SEVERITY_HIGH = 3.5
_SEVERITY_MEDIUM = 3.0
# z in [Z_THRESHOLD, 3.0) → "low"


@dataclass
class AnomalyFlag:
    """
    One flagged outlier observation for a team on a specific metric.

    Attributes
    ----------
    team : int
        Team number.
    match_key : str
        TBA-style match key or empty string if unknown.
    metric : str
        Which metric triggered the flag (e.g., "cycle_speed").
    observed_value : float
        Numeric value of the metric in this observation.
    expected_mean : float
        Team's historical mean for this metric.
    expected_sigma : float
        Team's historical sigma for this metric.
    z_score : float
        Signed z-score: (observed_value − mean) / sigma.
    severity : str
        "high" (|z| ≥ 3.5), "medium" (|z| ≥ 3.0), or "low" (|z| ≥ 2.5).
    scout_name : str
        Scout who submitted the entry (for SPR cross-reference).
    reason : str
        Human-readable description of the flag.
    """

    team: int
    match_key: str
    metric: str
    observed_value: float
    expected_mean: float
    expected_sigma: float
    z_score: float
    severity: str
    scout_name: str = ""
    reason: str = ""


def _extract_metric_value(obs: dict, metric: str) -> Optional[float]:
    """
    Extract a numeric value for the given metric from a stand_scout obs dict.

    Returns None if the metric cannot be extracted or should be skipped.
    """
    if metric == "cycle_speed":
        speed = obs.get("teleop", {}).get("cycle_speed", "unknown")
        return _SPEED_NUMERIC.get(speed, 0.5)

    if metric == "auto_scored":
        scored = obs.get("auto", {}).get("scored", False)
        return 1.0 if scored else 0.0

    if metric == "climb_success":
        climbed = obs.get("endgame", {}).get("climb_attempted", False)
        return 1.0 if climbed else 0.0

    if metric == "match_contribution":
        # Use .get with sentinel — don't use "or" since 0.0 is a valid contribution
        sentinel = object()
        val = obs.get("match_contribution", sentinel)
        if val is sentinel:
            val = obs.get("epa_contribution", sentinel)
        if val is not sentinel and val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None

    # Generic numeric fallback — check top-level and nested keys
    val = obs.get(metric)
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return None


def _mean_sigma(values: list[float]) -> tuple[float, float]:
    """Return (mean, population sigma) for a list of floats."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mu = sum(values) / n
    variance = sum((v - mu) ** 2 for v in values) / n
    return mu, math.sqrt(variance)


def _severity_label(abs_z: float) -> str:
    if abs_z >= _SEVERITY_HIGH:
        return "high"
    if abs_z >= _SEVERITY_MEDIUM:
        return "medium"
    return "low"


def detect_anomalies(
    team_matches: list[dict],
    metrics: Optional[list[str]] = None,
    *,
    z_threshold: float = Z_THRESHOLD,
    min_obs: int = MIN_OBS_FOR_ZSCORE,
) -> list[AnomalyFlag]:
    """
    Detect outlier entries in a team's match observation sequence.

    Parameters
    ----------
    team_matches : list of obs dicts for ONE team (from stand_scout).
        All observations are assumed to be for the same team.
        Mixed-team lists will still work but produce cross-team z-scores,
        which is usually not what you want.
    metrics : list of metric names to check. Defaults to the standard four:
        ["cycle_speed", "auto_scored", "climb_success", "match_contribution"]
    z_threshold : absolute z-score threshold for flagging. Default 2.5.
    min_obs : minimum observations before z-score is computed. Default 3.

    Returns
    -------
    list of AnomalyFlag — one per (observation, metric) pair that exceeds
    the z-score threshold. Empty list means no anomalies detected.
    """
    if metrics is None:
        metrics = ["cycle_speed", "auto_scored", "climb_success", "match_contribution"]

    flags: list[AnomalyFlag] = []

    for metric in metrics:
        # Collect (obs, value) pairs — skip obs where metric is unavailable
        pairs: list[tuple[dict, float]] = []
        for obs in team_matches:
            val = _extract_metric_value(obs, metric)
            if val is not None:
                pairs.append((obs, val))

        if len(pairs) < min_obs:
            # Not enough data to z-score this metric
            continue

        values = [v for _, v in pairs]
        mu, sigma = _mean_sigma(values)

        # Degenerate case: zero variance → skip (all matches identical, no outlier)
        if sigma < 1e-9:
            continue

        for obs, val in pairs:
            z = (val - mu) / sigma
            abs_z = abs(z)
            if abs_z >= z_threshold:
                meta = obs.get("_meta", {})
                match_key = meta.get("match_key", "")
                scout_name = meta.get("scout", "")
                team = obs.get("team", 0)
                severity = _severity_label(abs_z)

                direction = "above" if z > 0 else "below"
                reason = (
                    f"{metric}={val:.2f} is {abs_z:.1f}σ {direction} team mean "
                    f"({mu:.2f}±{sigma:.2f})"
                )

                flags.append(
                    AnomalyFlag(
                        team=int(team) if team else 0,
                        match_key=match_key,
                        metric=metric,
                        observed_value=round(val, 4),
                        expected_mean=round(mu, 4),
                        expected_sigma=round(sigma, 4),
                        z_score=round(z, 3),
                        severity=severity,
                        scout_name=scout_name,
                        reason=reason,
                    )
                )

    # Sort: highest |z| first for display
    flags.sort(key=lambda f: abs(f.z_score), reverse=True)
    return flags


def detect_anomalies_robust(
    matches: list[dict],
    metrics: Optional[list[str]] = None,
    *,
    mad_threshold: float = 3.5,
    min_obs: int = MIN_OBS_FOR_ZSCORE,
) -> list[AnomalyFlag]:
    """
    Detect outlier entries using robust Median + MAD (median absolute deviation).

    This is the preferred method for competition scouting. Unlike z-score, it
    is resistant to a single contaminating outlier inflating sigma and masking
    real anomalies.

    Modified z-score formula (Iglewicz & Hoaglin, 1993):
        modified_z = |value − median| / (1.4826 × MAD)
    where 1.4826 is a consistency constant so that MAD ≈ sigma for Gaussian data.

    Edge cases:
      - MAD = 0 and value == median → no flag (all values are identical)
      - MAD = 0 and value != median → flag with infinite modified z-score (definite outlier)
      - Fewer than min_obs observations → skip metric

    Parameters
    ----------
    matches : list of obs dicts for ONE team (from stand_scout).
    metrics : list of metric names to check. Defaults to the standard four.
    mad_threshold : modified z-score threshold for flagging. Default 3.5.
    min_obs : minimum observations before MAD is computed. Default 3.

    Returns
    -------
    list of AnomalyFlag — same shape as detect_anomalies(), one per
    (observation, metric) pair that exceeds mad_threshold.
    Empty list means no anomalies detected.
    """
    if metrics is None:
        metrics = ["cycle_speed", "auto_scored", "climb_success", "match_contribution"]

    flags: list[AnomalyFlag] = []

    for metric in metrics:
        # Collect (obs, value) pairs — skip obs where metric is unavailable
        pairs: list[tuple[dict, float]] = []
        for obs in matches:
            val = _extract_metric_value(obs, metric)
            if val is not None:
                pairs.append((obs, val))

        if len(pairs) < min_obs:
            continue

        values = [v for _, v in pairs]
        med = statistics.median(values)
        abs_devs = [abs(v - med) for v in values]
        mad = statistics.median(abs_devs)

        for obs, val in pairs:
            if mad < 1e-9:
                # MAD = 0: all values are identical to the median
                if abs(val - med) < 1e-9:
                    # Value equals median — definitely no outlier
                    continue
                # Value differs from a zero-MAD distribution → definite outlier
                mod_z = float("inf")
            else:
                mod_z = abs(val - med) / (1.4826 * mad)

            if mod_z >= mad_threshold:
                meta = obs.get("_meta", {})
                match_key = meta.get("match_key", "")
                scout_name = meta.get("scout", "")
                team = obs.get("team", 0)
                severity = _severity_label(mod_z)

                direction = "above" if val > med else "below"
                reason = (
                    f"{metric}={val:.2f} is {mod_z:.1f}σ* {direction} team median "
                    f"({med:.2f}, MAD={mad:.2f}) [robust]"
                )

                # Store modified z-score in z_score field for drop-in compatibility
                # expected_mean/expected_sigma carry median/scaled_MAD respectively
                flags.append(
                    AnomalyFlag(
                        team=int(team) if team else 0,
                        match_key=match_key,
                        metric=metric,
                        observed_value=round(val, 4),
                        expected_mean=round(med, 4),
                        expected_sigma=round(1.4826 * mad, 4),
                        z_score=round(mod_z if val > med else -mod_z, 3),
                        severity=severity,
                        scout_name=scout_name,
                        reason=reason,
                    )
                )

    # Sort: highest |modified z| first for display
    flags.sort(key=lambda f: abs(f.z_score), reverse=True)
    return flags


def detect_anomalies_all_teams(
    all_observations: list[dict],
    metrics: Optional[list[str]] = None,
    *,
    z_threshold: float = Z_THRESHOLD,
    min_obs: int = MIN_OBS_FOR_ZSCORE,
) -> dict[int, list[AnomalyFlag]]:
    """
    Run anomaly detection across all teams from a mixed observation list.

    Parameters
    ----------
    all_observations : list of obs dicts (mixed teams — from a full event)
    metrics, z_threshold, min_obs : forwarded to detect_anomalies()

    Returns
    -------
    dict mapping team_num → list[AnomalyFlag]
    Keys are only present for teams that have at least one flag.
    """
    # Partition by team
    by_team: dict[int, list[dict]] = {}
    for obs in all_observations:
        team = obs.get("team")
        if team is None:
            continue
        t = int(team)
        by_team.setdefault(t, []).append(obs)

    results: dict[int, list[AnomalyFlag]] = {}
    for team, obs_list in by_team.items():
        flags = detect_anomalies(
            obs_list, metrics, z_threshold=z_threshold, min_obs=min_obs
        )
        if flags:
            results[team] = flags

    return results


def anomaly_summary_line(flags: list[AnomalyFlag]) -> str:
    """
    Produce a one-line pick-board summary for a team's anomaly flags.

    Examples:
      "2 flagged matches (cycle_speed HIGH, auto_scored LOW) — review before ranking"
      "1 flagged match (match_contribution HIGH) — possible bot malfunction"
    """
    if not flags:
        return ""

    n = len(flags)
    high_flags = [f for f in flags if f.severity == "high"]
    details = ", ".join(f"{f.metric} {f.severity.upper()}" for f in flags[:3])
    if n > 3:
        details += f" +{n - 3} more"

    note = "possible bot malfunction" if high_flags else "review before ranking"
    return f"{n} flagged match(es) ({details}) — {note}"


def filter_anomaly_scouts(
    flags: list[AnomalyFlag],
    *,
    threshold: int = 2,
) -> list[str]:
    """
    Return scout names that appear in >= threshold anomaly flags.

    Used by spr.apply_spr_weights to identify scouts whose entries
    consistently drive anomaly flags (likely bad scouting data rather
    than robot breakdowns). These scouts should receive reduced SPR weight.

    Parameters
    ----------
    flags : list of AnomalyFlag (from detect_anomalies or detect_anomalies_all_teams)
    threshold : minimum flag count before a scout is returned

    Returns
    -------
    list of scout_name strings
    """
    counts: dict[str, int] = {}
    for f in flags:
        name = f.scout_name
        if name:
            counts[name] = counts.get(name, 0) + 1

    return [name for name, cnt in counts.items() if cnt >= threshold]
