#!/usr/bin/env python3
"""
The Engine — Scout Precision Rating (SPR)
Team 2950 — The Devastators

Validates human scout trustworthiness by comparing individual scout entries
against TBA ground truth over time. Produces a 0–1 trust score per scout
that weights future entries in pick_board and pre_event_report.

Algorithm (ported from 1678 Citrus Circuits scouting paper / Obsidian docs):
  For each (scout, match) entry where TBA ground truth exists:
    residual = |scout_value − tba_value| / tba_range
  SPR = 1 − mean(residuals), clamped to [0, 1]

  scouts with < MIN_ENTRIES get a neutral score of 0.5 (insufficient data).

Fields validated against TBA score_breakdown:
  - auto_scored  → score_breakdown auto points (binary / 0-or->0 check)
  - climb_attempted → endgame points (binary)
  - cycle_speed  → teleop_points normalized (fast/moderate/slow mapped to quartiles)

1678 source gap note:
  Citrus' SPR implementation uses their own scoring sheet fields (game-specific
  numeric columns). We implement the documented residual-error / normalize pattern
  applied to our stand_scout tag schema. The math is equivalent; field names differ.

Usage:
  from spr import compute_spr, get_scout_weight

  scores = compute_spr(observations_with_tba)   # {scout_name: 0.0–1.0}
  weight = get_scout_weight(scores, "Alice")     # float
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

MIN_ENTRIES = 3        # fewer entries → neutral score
NEUTRAL_SCORE = 0.5    # returned when insufficient data
FALLBACK_SD = 10.0     # teleop normalizer when tba_range=0

# Cycle-speed → expected teleop contribution fraction of event average
_SPEED_FRACTIONS = {
    "fast": 0.90,
    "moderate": 0.60,
    "slow": 0.30,
    "unknown": 0.55,
}


@dataclass
class ScoutEntry:
    """One human-scouted observation with optional TBA ground truth."""
    scout_name: str
    team: int
    match_key: str

    # Scout-reported values (from stand_scout.parse_scout_input output)
    auto_scored: bool = False          # obs["auto"]["scored"]
    climb_attempted: bool = False      # obs["endgame"]["climb_attempted"]
    cycle_speed: str = "unknown"       # obs["teleop"]["cycle_speed"]

    # TBA ground truth (from tba_client.match_detail score_breakdown)
    tba_auto_points: Optional[float] = None   # e.g. 18.0
    tba_teleop_points: Optional[float] = None # e.g. 42.0
    tba_endgame_points: Optional[float] = None

    # Event-level context for normalization
    event_teleop_avg: float = 40.0   # typical event teleop avg per team


@dataclass
class _ScoutAccumulator:
    residuals: list[float] = field(default_factory=list)
    n: int = 0


def _auto_residual(entry: ScoutEntry) -> Optional[float]:
    """Binary residual: scout said scored vs TBA had any auto points."""
    if entry.tba_auto_points is None:
        return None
    tba_scored = entry.tba_auto_points > 0
    scout_scored = entry.auto_scored
    return 0.0 if tba_scored == scout_scored else 1.0


def _endgame_residual(entry: ScoutEntry) -> Optional[float]:
    """Binary residual: scout said climb vs TBA had endgame points."""
    if entry.tba_endgame_points is None:
        return None
    tba_climbed = entry.tba_endgame_points > 0
    scout_climbed = entry.climb_attempted
    return 0.0 if tba_climbed == scout_climbed else 1.0


def _teleop_residual(entry: ScoutEntry) -> Optional[float]:
    """Continuous residual: map cycle_speed tag to expected fraction, compare to TBA."""
    if entry.tba_teleop_points is None:
        return None

    expected_fraction = _SPEED_FRACTIONS.get(entry.cycle_speed, _SPEED_FRACTIONS["unknown"])
    expected_pts = expected_fraction * entry.event_teleop_avg

    normalizer = entry.event_teleop_avg if entry.event_teleop_avg > 0 else FALLBACK_SD
    residual = abs(entry.tba_teleop_points - expected_pts) / normalizer
    # Clamp to [0, 1] — large outliers still count but don't blow up the mean
    return min(1.0, residual)


def compute_spr(entries: list[ScoutEntry]) -> dict[str, float]:
    """
    Compute Scout Precision Rating for each scout who has TBA-validated entries.

    Parameters
    ----------
    entries : list of ScoutEntry with at least some tba_* fields filled in

    Returns
    -------
    dict mapping scout_name → SPR score in [0.0, 1.0]
    Scouts with < MIN_ENTRIES validated entries receive NEUTRAL_SCORE (0.5).
    """
    accumulators: dict[str, _ScoutAccumulator] = {}

    for entry in entries:
        name = entry.scout_name or "unknown"
        if name not in accumulators:
            accumulators[name] = _ScoutAccumulator()
        acc = accumulators[name]

        residuals_this_entry = []

        r = _auto_residual(entry)
        if r is not None:
            residuals_this_entry.append(r)

        r = _endgame_residual(entry)
        if r is not None:
            residuals_this_entry.append(r)

        r = _teleop_residual(entry)
        if r is not None:
            residuals_this_entry.append(r)

        if residuals_this_entry:
            acc.residuals.append(sum(residuals_this_entry) / len(residuals_this_entry))
            acc.n += 1

    scores: dict[str, float] = {}
    for name, acc in accumulators.items():
        if acc.n < MIN_ENTRIES:
            scores[name] = NEUTRAL_SCORE
        else:
            mean_residual = sum(acc.residuals) / len(acc.residuals)
            scores[name] = max(0.0, min(1.0, 1.0 - mean_residual))

    return scores


def get_scout_weight(scores: dict[str, float], scout_name: str) -> float:
    """Return the trust weight for a scout. Falls back to NEUTRAL_SCORE if unknown."""
    return scores.get(scout_name, NEUTRAL_SCORE)


def apply_spr_weights(
    observations: list[dict],
    spr_scores: dict[str, float],
) -> list[dict]:
    """
    Annotate a list of stand_scout observation dicts with a 'spr_weight' field.

    Used by pre_event_report and pick_board when aggregating human scout data
    so that high-precision scouts count more than low-precision scouts.

    Parameters
    ----------
    observations : list of obs dicts from stand_scout.get_team_observations()
    spr_scores   : output of compute_spr()

    Returns
    -------
    Same list, each dict augmented with 'spr_weight' key.
    """
    for obs in observations:
        meta = obs.get("_meta", {})
        scout = meta.get("scout", "")
        obs["spr_weight"] = get_scout_weight(spr_scores, scout)
    return observations


def build_entry_from_obs(
    obs: dict,
    match_detail: dict,
    alliance: str,
    event_teleop_avg: float = 40.0,
) -> Optional[ScoutEntry]:
    """
    Construct a ScoutEntry from a stand_scout obs dict + TBA match_detail dict.

    Parameters
    ----------
    obs          : dict from stand_scout.parse_scout_input / load_all_observations
    match_detail : dict from tba_client.match_detail (full match with score_breakdown)
    alliance     : 'red' or 'blue' — which alliance this team was on
    event_teleop_avg : avg per-team teleop pts at this event (for normalization)

    Returns None if the obs is missing required fields.
    """
    meta = obs.get("_meta", {})
    scout_name = meta.get("scout", "")
    team = obs.get("team")
    match_key = meta.get("match_key", "") or match_detail.get("key", "")

    if not team or not match_key:
        return None

    # Extract TBA breakdown for this alliance
    breakdown = match_detail.get("score_breakdown", {}).get(alliance, {})
    if not breakdown:
        return None

    tba_auto = breakdown.get("autoPoints") or breakdown.get("auto_points")
    tba_teleop = breakdown.get("teleopPoints") or breakdown.get("teleop_points")
    tba_endgame = breakdown.get("endgamePoints") or breakdown.get("endgame_points")

    # Divide alliance totals by 3 teams for per-team estimate
    def _per_team(val) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val) / 3.0
        except (TypeError, ValueError):
            return None

    auto_obs = obs.get("auto", {})
    endgame_obs = obs.get("endgame", {})
    teleop_obs = obs.get("teleop", {})

    return ScoutEntry(
        scout_name=scout_name,
        team=int(team),
        match_key=match_key,
        auto_scored=bool(auto_obs.get("scored", False)),
        climb_attempted=bool(endgame_obs.get("climb_attempted", False)),
        cycle_speed=teleop_obs.get("cycle_speed", "unknown"),
        tba_auto_points=_per_team(tba_auto),
        tba_teleop_points=_per_team(tba_teleop),
        tba_endgame_points=_per_team(tba_endgame),
        event_teleop_avg=event_teleop_avg,
    )
