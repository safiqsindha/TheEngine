#!/usr/bin/env python3
"""
The Engine — Alliance Stat Decomposition
Team 2950 — The Devastators

Ports Caleb Sykes / 1678 alliance decomposition: attributes alliance
over/under-performance to individual robot contributors within each match,
then rolls per-match attribution into event-level carry/ride delta EMAs.

Algorithm (from Caleb Sykes CD posts on alliance contribution decomposition):
  1. expected_alliance_score = sum(team.epa) for the three alliance teams
  2. actual_alliance_score   = match_breakdown.total (from TBA)
  3. alliance_delta          = actual - expected

  Per-team attribution:
    If stand_scout observations exist with contribution weights (coral counts,
    climb flags, cycle speed), compute each team's share of observed output.
    If a team contributed 60% of observed stand-scout signal, they absorb 60%
    of the alliance_delta.

    SCHEMA GAP: The current stand_scout schema does not expose raw game-piece
    counts (e.g., pieces_scored_teleop, coral_placed, etc.) as numeric fields.
    It stores categorical tags (cycle_speed: fast/moderate/slow) and binary
    flags (auto.scored, endgame.climb_attempted). When numeric piece counts
    are absent, the code falls back to UNIFORM attribution (1/3 per team).

    As the stand_scout schema matures, populate obs["match_contribution"] or
    obs["score_points"] with a per-team numeric contribution (from TBA
    score_breakdown per-robot fields if available) and this module will
    automatically use observation-driven shares instead of the fallback.

  Event-level aggregation:
    carry_delta_ema > 0: team consistently drives alliance above EPA-sum baseline
    ride_delta_ema  < 0: team consistently underperforms relative to alliance expectation

    EMA alpha=0.3 (default) weights recent matches more heavily, matching 1678's
    rolling-window approach for in-event signal freshness.

Cross-wire with anomaly.filter_anomaly_scouts():
  flag_carry_variance_by_scout() computes per-scout carry_delta variance and
  flags scouts whose entries swing wildly while the aggregate is stable —
  a signal that one scout is mis-recording rather than the robot swinging.

1678 source note:
  Caleb Sykes' decomposition papers (Chief Delphi, ~2019-2022) describe
  allocating alliance surplus/deficit to robots proportionally to their
  observed contribution share. Citrus uses game-specific numeric columns;
  we approximate with stand_scout's categorical schema, falling back to
  uniform allocation when numerics are unavailable.

Usage:
  from alliance_decomposition import (
      compute_alliance_decomposition,
      aggregate_team_delta_ema,
      flag_carry_variance_by_scout,
      format_carry_delta_row,
  )

  decomp = compute_alliance_decomposition(
      alliance_epas={2950: 42.0, 1678: 55.0, 254: 60.0},
      match_breakdown={"total": 170},
      stand_scout_obs=[obs_2950, obs_1678, obs_254],
  )

  ema = aggregate_team_delta_ema(
      team_num=2950,
      event_matches=[  # list of compute_alliance_decomposition outputs
          {2950: {...}, 1678: {...}, 254: {...}},
          ...
      ],
      alpha=0.3,
  )
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy import of get_attribution_beta from blueprint/attribution_betas.py.
#
# blueprint/ has no __init__.py, so we cannot use `from blueprint.attribution_betas
# import ...` as a package import.  Instead we locate the file relative to this
# module's own path and import it directly, which works regardless of how
# sys.path is configured by the caller.
# ---------------------------------------------------------------------------

def _load_get_attribution_beta():
    """Load get_attribution_beta from blueprint/attribution_betas.py at call time."""
    _blueprint_path = Path(__file__).resolve().parents[1] / "blueprint" / "attribution_betas.py"
    spec = importlib.util.spec_from_file_location("attribution_betas", _blueprint_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get_attribution_beta

# EMA smoothing factor: 0.3 matches recent-match weighting used in 1678 event analysis
DEFAULT_EMA_ALPHA = 0.3

# Minimum matches before EMA is considered reliable
MIN_MATCHES_FOR_EMA = 3

# Cycle-speed → relative scoring weight (used for observation-driven contribution share)
# Maps categorical stand_scout tags to a numeric proxy for output rate.
_SPEED_WEIGHT = {
    "fast": 1.0,
    "moderate": 0.6,
    "slow": 0.2,
    "unknown": 0.55,
}

# Climb bonus weight: teams that climbed contributed more to endgame total
_CLIMB_WEIGHT = 1.5

# Auto bonus weight: teams that scored in auto contributed more to auto total
_AUTO_WEIGHT = 1.2


# ─── Schema gap documentation ────────────────────────────────────────────────
#
# Fields NOT present in the current stand_scout schema that would improve
# attribution accuracy when available:
#
#   obs["score_points"]      — per-team TBA-backed points (would give exact share)
#   obs["match_contribution"] — already checked; used when present (from TBA enrichment)
#   obs["teleop"]["pieces_scored"] — raw piece count (not logged yet)
#   obs["auto"]["pieces_scored"]   — raw auto piece count (not logged yet)
#
# When obs["match_contribution"] is set (e.g., from tba_client enrichment), that
# numeric is used directly and uniform fallback is NOT needed.
#
# FALLBACK BEHAVIOR: If no numeric contribution is available for ANY of the three
# alliance teams, contribution_share defaults to 1/3 each (UNIFORM_SHARE = True).
# ─────────────────────────────────────────────────────────────────────────────

UNIFORM_SHARE = 1.0 / 3.0


# ─── Power-curve normalization ────────────────────────────────────────────────


def power_normalize(contributions: list[float], beta: float = 1.0) -> list[float]:
    """
    Normalize a list of contribution weights using a power curve.

    share_i = c_i^beta / sum_j(c_j^beta)

    Parameters
    ----------
    contributions : list of non-negative floats representing each agent's
        observed output (coral counts, cycle speed proxy, etc.).
    beta : float
        Concavity exponent.
          beta=1.0  → linear (identical to simple proportional share)
          beta<1.0  → concave (dampens high-volume bias, compresses spread)
          beta→0    → uniform (every agent gets 1/n regardless of output)

    Returns
    -------
    list[float] of shares summing to 1.0, same length as contributions.
    Returns [] for empty input.
    Raises ValueError for any negative contribution.

    Edge cases
    ----------
    - Empty list → []
    - Any negative value → ValueError
    - All zeros → uniform [1/n, ..., 1/n]
    - Single element → [1.0]
    """
    if not contributions:
        return []

    for c in contributions:
        if c < 0:
            raise ValueError(
                f"power_normalize: all contributions must be >= 0, got {c}"
            )

    n = len(contributions)

    # All zeros → uniform (no signal to distinguish agents)
    if all(c == 0.0 for c in contributions):
        return [1.0 / n] * n

    powered = [c ** beta for c in contributions]
    total = sum(powered)

    if total == 0.0:
        # Defensive guard: shouldn't happen given non-zero contributions and beta>0,
        # but protect against float underflow for very small c with large negative beta
        return [1.0 / n] * n

    return [p / total for p in powered]


@dataclass
class TeamDecomposition:
    """
    Per-team decomposition result for one match.

    Attributes
    ----------
    team : int
        Team number.
    expected_pts : float
        Team's EPA (input expectation for this match).
    actual_pts : float
        Team's attributed actual contribution = expected + actual_delta.
    contribution_share : float
        Fraction of alliance output attributed to this team (0.0–1.0, sums to ~1.0).
    actual_delta : float
        How many points above/below expectation were attributed to this team.
        Positive = over-performed; negative = under-performed.
    used_uniform_fallback : bool
        True when stand_scout observations lacked numeric data and 1/3 uniform
        allocation was used. False when observation-driven shares were computed.
    match_key : str
        TBA match key (for traceability).
    """

    team: int
    expected_pts: float
    actual_pts: float
    contribution_share: float
    actual_delta: float
    used_uniform_fallback: bool = True
    match_key: str = ""


@dataclass
class AllianceDecomposition:
    """Full alliance decomposition for one match."""

    match_key: str
    expected_alliance_score: float
    actual_alliance_score: float
    alliance_delta: float
    teams: dict[int, TeamDecomposition] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class TeamDeltaEMA:
    """
    Rolled-up carry/ride signal for one team across an event.

    Attributes
    ----------
    team : int
    carry_delta : float
        EMA of per-match actual_delta. Positive = team consistently elevates
        alliance above EPA-sum baseline ("carry"). Negative = consistently
        underperforms ("ride").
    ride_delta : float
        Same sign convention as carry_delta. Semantically: teams with
        carry_delta > 3 are carry candidates; < -3 are ride candidates.
    consistency : float
        Inverse variance of carry deltas across matches. High = predictable.
        Computed as 1.0 / (1.0 + sigma) — range (0, 1].
    match_count : int
        Matches contributing to this EMA.
    used_fallback_count : int
        Matches where uniform allocation was used (reduces signal confidence).
    """

    team: int
    carry_delta: float
    ride_delta: float
    consistency: float
    match_count: int
    used_fallback_count: int = 0


# ─── Contribution share computation ─────────────────────────────────────────


def _obs_weight(obs: dict) -> Optional[float]:
    """
    Derive a numeric contribution weight from a stand_scout observation.

    Priority order:
      1. obs["match_contribution"] or obs["score_points"] — exact numeric (best)
      2. Constructed from cycle_speed + climb + auto tags (approximate)
      3. None — no data available (caller falls back to uniform)
    """
    # Priority 1: explicit numeric contribution (set by TBA-enriched observations)
    sentinel = object()
    for key in ("match_contribution", "score_points", "epa_contribution"):
        val = obs.get(key, sentinel)
        if val is not sentinel and val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    # Priority 2: construct weight proxy from categorical tags
    teleop = obs.get("teleop", {})
    auto = obs.get("auto", {})
    endgame = obs.get("endgame", {})
    defense = obs.get("defense", {})

    # If team played defense, their scoring contribution was near zero
    if isinstance(defense, dict) and defense.get("played_defense", False):
        return 0.0

    speed = teleop.get("cycle_speed", "unknown") if isinstance(teleop, dict) else "unknown"
    auto_scored = bool(auto.get("scored", False)) if isinstance(auto, dict) else False
    climbed = bool(endgame.get("climb_attempted", False)) if isinstance(endgame, dict) else False

    weight = _SPEED_WEIGHT.get(speed, _SPEED_WEIGHT["unknown"])
    if auto_scored:
        weight += _AUTO_WEIGHT
    if climbed:
        weight += _CLIMB_WEIGHT

    # Return None only if ALL fields are missing (no obs dict at all)
    return weight


def _compute_contribution_shares(
    alliance_teams: list[int],
    obs_by_team: dict[int, dict],
) -> tuple[dict[int, float], bool]:
    """
    Compute each team's fraction of alliance output.

    Returns (shares_dict, used_uniform_fallback).
    used_uniform_fallback=True when:
      - No observations are available for any team, OR
      - All computed weights are zero (e.g., all played defense)
    used_uniform_fallback=False when at least one team has usable obs data.
    """
    # Fast path: no obs for any alliance team → pure uniform
    if not any(t in obs_by_team for t in alliance_teams):
        shares = {t: UNIFORM_SHARE for t in alliance_teams}
        return shares, True

    weights: dict[int, float] = {}

    for team in alliance_teams:
        obs = obs_by_team.get(team, {})
        w = _obs_weight(obs)
        weights[team] = max(0.0, w) if w is not None else 0.0

    total_weight = sum(weights.values())

    if total_weight <= 0.0:
        # All zeros — complete data gap (e.g., all defense), use uniform
        shares = {t: UNIFORM_SHARE for t in alliance_teams}
        return shares, True

    shares = {t: w / total_weight for t, w in weights.items()}
    # We had at least some obs data — not pure uniform fallback
    return shares, False


# ─── Core decomposition ──────────────────────────────────────────────────────


def compute_alliance_decomposition(
    alliance_epas: dict[int, float],
    match_breakdown: dict,
    stand_scout_obs: Optional[list[dict]] = None,
    *,
    match_key: str = "",
    beta: float = 1.0,
    year: Optional[int] = None,
    phase: str = "overall",
) -> dict[int, dict]:
    """
    Decompose alliance match performance into per-team contributions.

    Parameters
    ----------
    alliance_epas : dict mapping team_num → EPA (the season/event mean expectation)
        Must contain exactly the 3 teams that played this alliance.
    match_breakdown : dict with at least a "total" key (alliance total score).
        Optionally may have per-alliance breakdown keys from TBA.
    stand_scout_obs : optional list of stand_scout observation dicts for the alliance's
        teams in this match. Observations are matched to teams via obs["team"].
        If None or empty, uniform attribution (1/3) is used.
    match_key : str — TBA match key, for record-keeping.
    beta : float — power-curve exponent passed to power_normalize().
        1.0 (default) → linear shares (back-compat).
        <1.0 → concave (dampens high-volume bias).
        Precedence: explicit beta > year-based lookup > 1.0 fallback.
    year : int | None — FRC season year used to auto-select β from
        blueprint.attribution_betas.get_attribution_beta(year, phase).
        Only used when beta is not explicitly passed (i.e., equals the default 1.0
        sentinel). If None, no lookup is performed and β=1.0 is used (back-compat).
    phase : str — game phase for per-phase β lookup (e.g. "cycle", "climb",
        "overall"). Only meaningful for seasons with per-phase β (e.g. 2019).
        Ignored when year is None.

    β precedence
    ------------
    1. Explicit ``beta`` kwarg (anything other than the default 1.0 sentinel
       is treated as explicit) — always wins.
    2. Year-based lookup via ``get_attribution_beta(year, phase)`` — used when
       ``year`` is provided and ``beta`` is the default 1.0.
    3. 1.0 fallback — linear attribution, safe default when year is None.

    Returns
    -------
    dict mapping team_num → dict with keys:
        contribution_share  : float [0.0, 1.0]
        actual_delta        : float (points above/below expectation attributed)
        expected_pts        : float (team's EPA input)
        actual_pts          : float (expected_pts + actual_delta)
        used_uniform_fallback : bool
        match_key           : str

    Notes
    -----
    Schema gaps documented at module level. When stand_scout obs include
    "match_contribution", shares are observation-driven. Otherwise uniform.
    """
    # β resolution: explicit > year-lookup > 1.0 fallback
    # We detect "explicit" by checking if the caller passed beta != default sentinel.
    # Because Python keyword defaults are evaluated once, we use a sentinel approach:
    # if beta is still 1.0 AND year is provided, do the lookup.
    _beta_explicit = beta != 1.0  # explicit if caller chose a non-default value
    if not _beta_explicit and year is not None:
        _get_beta = _load_get_attribution_beta()
        beta = _get_beta(year, phase)
    # If year is None and beta==1.0, we keep beta=1.0 (back-compat)
    alliance_teams = list(alliance_epas.keys())
    expected_total = sum(alliance_epas.values())

    # Extract actual score
    actual_total = None
    for key in ("total", "totalPoints", "total_points"):
        val = match_breakdown.get(key)
        if val is not None:
            try:
                actual_total = float(val)
                break
            except (TypeError, ValueError):
                pass
    if actual_total is None:
        actual_total = expected_total  # Graceful fallback: assume no delta

    alliance_delta = actual_total - expected_total

    # Map observations by team
    obs_by_team: dict[int, dict] = {}
    for obs in (stand_scout_obs or []):
        t = obs.get("team")
        if t is not None:
            obs_by_team[int(t)] = obs

    # Compute contribution shares
    shares, used_uniform = _compute_contribution_shares(alliance_teams, obs_by_team)

    # Apply power-curve normalization when beta != 1.0 (or always, for consistency)
    if not used_uniform:
        raw_weights = [shares[t] for t in alliance_teams]
        normalized = power_normalize(raw_weights, beta=beta)
        shares = dict(zip(alliance_teams, normalized))

    # Attribute delta
    result: dict[int, dict] = {}
    for team in alliance_teams:
        share = shares.get(team, UNIFORM_SHARE)
        team_delta = alliance_delta * share
        expected_pts = alliance_epas[team]
        result[team] = {
            "contribution_share": round(share, 4),
            "actual_delta": round(team_delta, 2),
            "expected_pts": round(expected_pts, 2),
            "actual_pts": round(expected_pts + team_delta, 2),
            "used_uniform_fallback": used_uniform,
            "match_key": match_key,
        }

    return result


# ─── Event-level EMA aggregation ────────────────────────────────────────────


def aggregate_team_delta_ema(
    team_num: int,
    event_matches: list[dict[int, dict]],
    alpha: float = DEFAULT_EMA_ALPHA,
) -> TeamDeltaEMA:
    """
    Aggregate per-match actual_delta into a carry/ride EMA for one team.

    Parameters
    ----------
    team_num : int
        Team to aggregate.
    event_matches : list of compute_alliance_decomposition() outputs.
        Each element is a {team_num: decomp_dict} mapping.
        Matches where team_num is not present are skipped.
    alpha : EMA smoothing factor. 0.3 = recent-weighted (1678 default).

    Returns
    -------
    TeamDeltaEMA with carry_delta (EMA), ride_delta (same value, labeled
    differently by sign convention), consistency (inverse variance), and counts.

    Raises
    ------
    ValueError if alpha is not in (0, 1].
    """
    if not (0.0 < alpha <= 1.0):
        raise ValueError(f"EMA alpha must be in (0, 1], got {alpha}")

    deltas: list[float] = []
    fallback_count = 0

    for match_decomp in event_matches:
        team_data = match_decomp.get(team_num)
        if team_data is None:
            continue
        delta = team_data.get("actual_delta", 0.0)
        deltas.append(delta)
        if team_data.get("used_uniform_fallback", True):
            fallback_count += 1

    if not deltas:
        return TeamDeltaEMA(
            team=team_num,
            carry_delta=0.0,
            ride_delta=0.0,
            consistency=0.0,
            match_count=0,
            used_fallback_count=0,
        )

    # Compute EMA (chronological order assumed in event_matches)
    ema = deltas[0]
    for d in deltas[1:]:
        ema = alpha * d + (1.0 - alpha) * ema

    # Consistency: inverse of sigma (high sigma = low consistency)
    n = len(deltas)
    if n >= 2:
        mean = sum(deltas) / n
        variance = sum((d - mean) ** 2 for d in deltas) / n
        sigma = math.sqrt(variance)
    else:
        sigma = 0.0

    consistency = 1.0 / (1.0 + sigma)  # Range (0, 1]; high = consistent

    carry_delta = round(ema, 2)
    # ride_delta mirrors carry_delta — the sign tells you which camp
    ride_delta = carry_delta

    return TeamDeltaEMA(
        team=team_num,
        carry_delta=carry_delta,
        ride_delta=ride_delta,
        consistency=round(consistency, 3),
        match_count=n,
        used_fallback_count=fallback_count,
    )


# ─── Scout variance cross-wire (anomaly.py pipeline feed) ───────────────────


def flag_carry_variance_by_scout(
    team_num: int,
    event_matches: list[dict[int, dict]],
    scout_obs_by_match: dict[str, dict],
    *,
    variance_threshold: float = 25.0,
    aggregate_stability_threshold: float = 5.0,
) -> list[str]:
    """
    Identify scouts whose per-entry carry_delta variance is high while the
    aggregate (EMA) is stable — a signal of inconsistent recording rather
    than genuine robot variance.

    Feeds into anomaly.filter_anomaly_scouts() via the suspect-scout pipeline.

    Parameters
    ----------
    team_num : int
        Team to analyze.
    event_matches : list of compute_alliance_decomposition() outputs (chronological).
    scout_obs_by_match : dict mapping match_key → obs dict for this team.
        Used to look up which scout recorded each match.
    variance_threshold : per-scout delta variance above which a scout is suspect.
        Default 25.0 (5-point sigma).
    aggregate_stability_threshold : if the team's aggregate carry_delta EMA has
        abs value < this, a high-variance scout is flagged more aggressively.
        Default 5.0.

    Returns
    -------
    list of suspect scout_name strings (suitable for anomaly.filter_anomaly_scouts input).
    """
    # Gather per-scout delta sequences
    scout_deltas: dict[str, list[float]] = {}

    for match_decomp in event_matches:
        team_data = match_decomp.get(team_num)
        if team_data is None:
            continue
        match_key = team_data.get("match_key", "")
        obs = scout_obs_by_match.get(match_key, {})
        meta = obs.get("_meta", {}) if isinstance(obs, dict) else {}
        scout = meta.get("scout", "") or "unknown"
        delta = team_data.get("actual_delta", 0.0)
        scout_deltas.setdefault(scout, []).append(delta)

    # Compute aggregate EMA sigma for reference
    ema_result = aggregate_team_delta_ema(team_num, event_matches)
    agg_is_stable = abs(ema_result.carry_delta) < aggregate_stability_threshold

    suspects: list[str] = []
    for scout, deltas in scout_deltas.items():
        if len(deltas) < 2:
            continue
        mean = sum(deltas) / len(deltas)
        variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)

        # Flag if variance exceeds threshold (especially when aggregate is stable)
        effective_threshold = (
            variance_threshold * 0.75 if agg_is_stable else variance_threshold
        )
        if variance > effective_threshold and scout not in suspects:
            suspects.append(scout)

    return suspects


# ─── Display helpers ─────────────────────────────────────────────────────────


def format_carry_delta_row(ema: TeamDeltaEMA, team_name: str = "") -> str:
    """
    Format a TeamDeltaEMA as a single pick-board display row.

    Example output:
      carry: +7.2 | consistency: 0.82 | 8 matches (3 uniform fallback)
      carry:  -3.1 | consistency: 0.45 | 5 matches ★ ride risk
    """
    sign = "+" if ema.carry_delta >= 0 else ""
    carry_str = f"carry: {sign}{ema.carry_delta:.1f}"
    cons_str = f"consistency: {ema.consistency:.2f}"
    match_str = f"{ema.match_count} match(es)"
    fallback_str = (
        f" ({ema.used_fallback_count} uniform fallback)"
        if ema.used_fallback_count > 0
        else ""
    )

    tag = ""
    if ema.carry_delta >= 5.0:
        tag = " ★ carry bot"
    elif ema.carry_delta <= -5.0:
        tag = " ★ ride risk"
    elif ema.match_count < MIN_MATCHES_FOR_EMA:
        tag = " [insufficient data]"

    name_str = f" {team_name[:18]}" if team_name else ""

    return f"{carry_str} | {cons_str} | {match_str}{fallback_str}{tag}{name_str}"
