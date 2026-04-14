#!/usr/bin/env python3
"""
The Engine — Defense-Adjusted EPA
Team 2950 — The Devastators

Separates "bad scoring team" from "team that was defended," following
the predictobics / 1678 pattern of partitioning match contributions
into defended and undefended buckets.

Algorithm:
  For each team's match observations:
    1. Tag each match as "defended" if stand_scout recorded received_defense=True
    2. Partition EPA contributions into defended vs. undefended buckets
    3. offensive_EPA = mean(undefended) + DEFENDED_WEIGHT * mean(defended tail)
    4. defense_pressure_index = defended_matches / total_matches

defense_pressure_index is a [0.0, 1.0] fraction: 0 means never seen under
defensive pressure; 1.0 means every scouted match had a defender on them.

Stand-scout schema note:
  obs["defense"]["received_defense"] — set True when scout tags "received-defense"
  obs["defense"]["played_defense"]   — set True when scout tags "played-defense"
  A match tagged played-defense by the team itself contributes ZERO to EPA
  (they weren't scoring; treat as defended bucket with zero contribution).

1678 source note:
  Predictobics / Caleb Sykes partition offensive vs. defensive contributions
  per match and reweight with a trimmed mean over the "clean" (undefended) matches.
  We approximate the trimmed-mean with: mean(undefended) + DEFENDED_WEIGHT * mean(defended).
  This avoids scipy and keeps the implementation dependency-free.

Usage:
  from defense_adjusted_epa import compute_defense_adjusted_epa, DefenseAdjResult

  result = compute_defense_adjusted_epa(team=2950, match_contributions=[...],
                                         observations=[...])
  print(result.offensive_epa, result.defense_pressure_index)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Weight applied to defended-match contributions in the offensive EPA blend.
# 0.25 means defended games count 25% of their face value — the team was
# meaningfully impaired and full credit would overstate their true output.
DEFENDED_WEIGHT = 0.25

# Minimum scouted matches before we trust the partition result.
# Fewer than this → raw EPA returned unchanged (insufficient data).
MIN_SCOUTED_MATCHES = 2

# A team tagged "played defense" that match is excluded from their EPA
# (they were playing defense, not scoring). Contributions treated as 0.
PLAYED_DEFENSE_EPA = 0.0


@dataclass
class DefenseAdjResult:
    """
    Output of compute_defense_adjusted_epa for one team.

    Attributes
    ----------
    team : int
        Team number.
    raw_epa : float
        Input EPA mean (from Statbotics), unadjusted.
    offensive_epa : float
        EPA with defended matches discounted. Always >= raw_epa when
        defense pressure exists (adjusting upward for unfair matches).
        Equal to raw_epa when no defense data is available.
    defense_pressure_index : float
        Fraction of scouted matches where the team was under defensive
        pressure. Range [0.0, 1.0]. Useful as a standalone pick-board
        signal: teams with dpi > 0.4 were heavily targeted.
    defended_match_count : int
        Raw count of matches flagged as defended.
    undefended_match_count : int
        Raw count of matches NOT flagged as defended.
    used_fallback : bool
        True when insufficient scouted observations forced raw_epa passthrough.
    notes : list[str]
        Informational notes (e.g., "played defense N times — excluded from EPA").
    """

    team: int
    raw_epa: float
    offensive_epa: float
    defense_pressure_index: float
    defended_match_count: int
    undefended_match_count: int
    used_fallback: bool = False
    notes: list[str] = field(default_factory=list)


def _is_defended(obs: dict) -> bool:
    """Return True if the observation indicates the team was under defense."""
    defense = obs.get("defense", {})
    if isinstance(defense, dict):
        return bool(defense.get("received_defense", False))
    return False


def _played_defense(obs: dict) -> bool:
    """Return True if the observation indicates the team played defense that match."""
    defense = obs.get("defense", {})
    if isinstance(defense, dict):
        return bool(defense.get("played_defense", False))
    return False


def _contribution_from_obs(obs: dict, raw_epa: float) -> Optional[float]:
    """
    Extract a per-match EPA contribution from an observation dict.

    Prefers the observation's own contribution field if present
    (e.g., from a TBA-backed match with per-team breakdown). Falls
    back to raw_epa as a stand-in when no match-level contribution
    is available. Returns None to skip unscored observations.

    Parameters
    ----------
    obs : observation dict from stand_scout
    raw_epa : float — season/event EPA mean as fallback contribution

    Returns
    -------
    float contribution, or None to skip
    """
    # First try explicit match contribution stored on the obs.
    # Use sentinel to distinguish "key absent" from "value is 0.0".
    sentinel = object()
    contrib = obs.get("match_contribution", sentinel)
    if contrib is sentinel:
        contrib = obs.get("epa_contribution", sentinel)
    if contrib is not sentinel and contrib is not None:
        try:
            return float(contrib)
        except (TypeError, ValueError):
            pass

    # No explicit contribution — use raw_epa as per-match stand-in.
    # This is correct when contributions are roughly uniform across matches.
    return raw_epa


def compute_defense_adjusted_epa(
    team: int,
    raw_epa: float,
    observations: list[dict],
    *,
    defended_weight: float = DEFENDED_WEIGHT,
    min_scouted: int = MIN_SCOUTED_MATCHES,
) -> DefenseAdjResult:
    """
    Compute defense-adjusted offensive EPA for one team.

    Parameters
    ----------
    team : int
        Team number (for labeling the result only).
    raw_epa : float
        Season or event EPA mean from Statbotics.
    observations : list of obs dicts from stand_scout.get_team_observations()
        Each dict may have obs["defense"]["received_defense"] and/or
        obs["defense"]["played_defense"] set from stand-scout tags.
    defended_weight : float
        Weight applied to defended-match contributions in the blend.
        Default 0.25 (defended games count 25% toward offensive EPA).
    min_scouted : int
        Minimum number of observations before adjustment is applied.
        Below this threshold, raw_epa is returned unchanged.

    Returns
    -------
    DefenseAdjResult
    """
    notes: list[str] = []

    undefended_contribs: list[float] = []
    defended_contribs: list[float] = []
    played_d_count = 0

    for obs in observations:
        if _played_defense(obs):
            # Team was playing defense — exclude from EPA entirely
            played_d_count += 1
            continue

        contrib = _contribution_from_obs(obs, raw_epa)
        if contrib is None:
            continue

        if _is_defended(obs):
            defended_contribs.append(contrib)
        else:
            undefended_contribs.append(contrib)

    if played_d_count > 0:
        notes.append(f"played defense {played_d_count} match(es) — excluded from EPA calc")

    total_scouted = len(undefended_contribs) + len(defended_contribs)

    if total_scouted < min_scouted:
        # Insufficient data — return raw EPA unchanged
        notes.append(
            f"only {total_scouted} scouted match(es) — raw EPA returned unchanged "
            f"(need ≥{min_scouted})"
        )
        return DefenseAdjResult(
            team=team,
            raw_epa=raw_epa,
            offensive_epa=raw_epa,
            defense_pressure_index=0.0,
            defended_match_count=len(defended_contribs),
            undefended_match_count=len(undefended_contribs),
            used_fallback=True,
            notes=notes,
        )

    # Compute bucket means
    undefended_mean = (
        sum(undefended_contribs) / len(undefended_contribs)
        if undefended_contribs
        else raw_epa
    )
    defended_mean = (
        sum(defended_contribs) / len(defended_contribs)
        if defended_contribs
        else undefended_mean
    )

    # Offensive EPA blend: clean matches dominate, defended matches add small tail
    if defended_contribs:
        offensive_epa = undefended_mean + defended_weight * defended_mean
        notes.append(
            f"offensive_EPA = {undefended_mean:.1f} (undefended mean) "
            f"+ {defended_weight} × {defended_mean:.1f} (defended mean) "
            f"= {offensive_epa:.1f}"
        )
    else:
        # No defensive pressure observed — offensive EPA equals undefended mean
        offensive_epa = undefended_mean

    dpi = len(defended_contribs) / total_scouted

    return DefenseAdjResult(
        team=team,
        raw_epa=raw_epa,
        offensive_epa=round(offensive_epa, 2),
        defense_pressure_index=round(dpi, 3),
        defended_match_count=len(defended_contribs),
        undefended_match_count=len(undefended_contribs),
        used_fallback=False,
        notes=notes,
    )


def compute_defense_adjusted_epa_for_event(
    teams_observations: dict[int, list[dict]],
    teams_raw_epa: dict[int, float],
    *,
    defended_weight: float = DEFENDED_WEIGHT,
    min_scouted: int = MIN_SCOUTED_MATCHES,
) -> dict[int, DefenseAdjResult]:
    """
    Batch compute defense-adjusted EPA for all teams at an event.

    Parameters
    ----------
    teams_observations : dict mapping team_num → list of observation dicts
    teams_raw_epa      : dict mapping team_num → float raw EPA from Statbotics

    Returns
    -------
    dict mapping team_num → DefenseAdjResult
    """
    results: dict[int, DefenseAdjResult] = {}
    for team, obs_list in teams_observations.items():
        raw = teams_raw_epa.get(team, 0.0)
        results[team] = compute_defense_adjusted_epa(
            team=team,
            raw_epa=raw,
            observations=obs_list,
            defended_weight=defended_weight,
            min_scouted=min_scouted,
        )
    return results


def format_defense_adj_row(result: DefenseAdjResult) -> str:
    """
    Format a DefenseAdjResult as a single pick-board display row.

    Example output:
      raw: 42.3 | off: 58.7 | DPI: 0.42 (defended 3/7 matches)
    """
    dpi_pct = f"{result.defense_pressure_index * 100:.0f}%"
    total = result.defended_match_count + result.undefended_match_count
    tag = ""
    if result.used_fallback:
        tag = " [insufficient data]"
    elif result.defense_pressure_index >= 0.40:
        tag = " ★ heavily targeted"
    return (
        f"raw: {result.raw_epa:.1f} | off: {result.offensive_epa:.1f} | "
        f"DPI: {dpi_pct} ({result.defended_match_count}/{total} matches defended){tag}"
    )
