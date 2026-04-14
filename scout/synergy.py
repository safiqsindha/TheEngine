#!/usr/bin/env python3
"""
The Engine — Pair Synergy Scoring
Team 2950 — The Devastators

Ports Caleb Sykes' predictobics pair-synergy analysis: for each pair of teams
that shared an alliance, measures whether they made each other *better* or
*worse* than their individual EPAs would predict.

Algorithm (from predictobics docs / Caleb Sykes' Chief Delphi writeups):

  synergy(A, B) = mean(actual_alliance_score - expected_alliance_score) / n_matches_together

  where:
    expected = sum of individual EPAs of all three alliance members
    actual   = TBA match_breakdown total score

  Positive synergy: these teams elevate each other beyond individual projections.
  Negative synergy: these teams step on each other's workflow.

Component-level synergy (bonus signal when Statbotics breakdown available):
  Decompose synergy by phase — auto_synergy, teleop_synergy, endgame_synergy.
  "They synergize in auto but not endgame" is directly actionable during
  alliance selection when you're trying to lock down a specific phase.

Predictobics source note:
  Caleb Sykes describes pair synergy as the residual from a linear model fit
  on alliance scores: after accounting for each robot's individual contribution,
  consistent over/under-performance as a pair signals a pairwise interaction term.
  We implement the mean-delta formulation (equivalent for the common case) to
  stay dependency-free and match the existing defense_adjusted_epa / alliance_decomposition
  style in this codebase.

Public API:
  compute_pair_synergy(team_a, team_b, shared_matches, component_breakdown=True)
      → {"overall": float, "auto": float, "teleop": float, "endgame": float, "n_matches": int}

  compute_team_synergy_profile(team, all_teams, event_matches)
      → dict mapping teammate → synergy dict

  best_synergy_partners(team, profile, top_n=5)
      → list of (teammate, synergy_dict) sorted by overall synergy descending

Usage:
  from synergy import compute_pair_synergy, compute_team_synergy_profile, best_synergy_partners

  profile = compute_team_synergy_profile(2950, all_team_nums, event_matches)
  top5 = best_synergy_partners(2950, profile, top_n=5)
  for partner, syn in top5:
      print(f"  {partner}: overall={syn['overall']:+.1f} auto={syn['auto']:+.1f}")
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Allow importing defense_adjusted_epa from the same scout/ directory
_SCOUT_DIR = Path(__file__).resolve().parent
if str(_SCOUT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCOUT_DIR))

from defense_adjusted_epa import compute_defense_adjusted_epa  # noqa: E402

# Minimum shared matches before a synergy score is considered reliable.
# Below this count the pair result is flagged with used_fallback=True.
MIN_SHARED_MATCHES = 2

# Component keys used for phase-level synergy extraction.
_COMPONENT_KEYS = ("auto", "teleop", "endgame")

# Keys tried (in order) when extracting actual totals from TBA match_breakdown.
# TBA varies its field names across seasons.
_TOTAL_KEYS = ("total", "totalPoints", "total_points")
_AUTO_KEYS = ("autoPoints", "auto_points", "autoScore")
_TELEOP_KEYS = ("teleopPoints", "teleop_points", "teleopScore")
_ENDGAME_KEYS = ("endgamePoints", "endgame_points", "endgameScore")


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _extract_float(d: dict, keys: tuple) -> Optional[float]:
    """Try each key in `keys` until a numeric value is found."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _alliance_epa(team_epas: dict[int, dict], team_nums: list[int]) -> float:
    """Sum component EPA for a given phase key across alliance members."""
    return sum(team_epas.get(t, {}).get("epa", 0.0) for t in team_nums)


def _alliance_component_epa(
    team_epas: dict[int, dict], team_nums: list[int], component: str
) -> float:
    """Sum per-phase EPA (auto/teleop/endgame) across alliance members."""
    comp_key = f"epa_{component}"
    return sum(team_epas.get(t, {}).get(comp_key, 0.0) for t in team_nums)


# ─── Core synergy computation ─────────────────────────────────────────────────


def defense_adjusted_synergy(
    team_a: dict,
    team_b: dict,
    matches: list[dict],
) -> float:
    """
    Compute defense-adjusted synergy for a pair of teams.

    Uses defense-adjusted EPA for each team (via compute_defense_adjusted_epa),
    then computes synergy as the residual:

        synergy_ab = mean(actual_alliance_score_with_both - (da_epa_a + da_epa_b))

    averaged over matches where both teams played together.

    Parameters
    ----------
    team_a : dict with keys:
        "team"         : int  — team number
        "raw_epa"      : float — season/event raw EPA from Statbotics
        "observations" : list[dict] — stand_scout obs for this team
    team_b : dict — same schema as team_a
    matches : list of shared_match dicts (same shape as compute_pair_synergy uses):
        {
          "alliance_teams": [int, int, int],
          "actual_total": float,
          "team_epas": {team_num: {"epa": float, ...}},
        }
        Only matches containing BOTH team_a and team_b in alliance_teams are used.

    Returns
    -------
    float — defense-adjusted synergy (positive = elevating each other beyond
    DA-EPA predictions; negative = stepping on each other's workflow).
    Returns 0.0 if no valid shared matches.

    Notes
    -----
    The third alliance member's raw EPA (from team_epas) is used as-is for the
    third-robot baseline since we only have defense observation data for team_a/b.
    The residual therefore captures the A+B interaction term net of the third bot.
    """
    if not matches:
        return 0.0

    num_a = team_a.get("team")
    num_b = team_b.get("team")

    # Compute defense-adjusted EPA for each team
    try:
        da_result_a = compute_defense_adjusted_epa(
            team=num_a,
            raw_epa=team_a.get("raw_epa", 0.0),
            observations=team_a.get("observations", []),
        )
        da_epa_a = da_result_a.offensive_epa
    except Exception:
        da_epa_a = team_a.get("raw_epa", 0.0)

    try:
        da_result_b = compute_defense_adjusted_epa(
            team=num_b,
            raw_epa=team_b.get("raw_epa", 0.0),
            observations=team_b.get("observations", []),
        )
        da_epa_b = da_result_b.offensive_epa
    except Exception:
        da_epa_b = team_b.get("raw_epa", 0.0)

    deltas: list[float] = []

    for match in matches:
        alliance_teams = match.get("alliance_teams", [])
        if num_a not in alliance_teams or num_b not in alliance_teams:
            continue

        actual_total = match.get("actual_total")
        if actual_total is None:
            continue

        # Third team baseline from raw team_epas in match record
        team_epas: dict = match.get("team_epas", {})
        third_epa = sum(
            team_epas.get(t, {}).get("epa", 0.0)
            for t in alliance_teams
            if t != num_a and t != num_b
        )

        expected = da_epa_a + da_epa_b + third_epa
        deltas.append(actual_total - expected)

    if not deltas:
        return 0.0

    return round(sum(deltas) / len(deltas), 2)


def compute_pair_synergy(
    team_a: int,
    team_b: int,
    shared_matches: list[dict],
    component_breakdown: bool = True,
    *,
    use_defense_adjustment: bool = False,
    team_a_data: Optional[dict] = None,
    team_b_data: Optional[dict] = None,
) -> dict:
    """
    Compute synergy score for a pair of teams (A, B) from their shared matches.

    Parameters
    ----------
    team_a, team_b : int
        Team numbers of the pair being evaluated.
    shared_matches : list of match dicts, each containing:
        {
          "alliance_teams": [int, int, int],   # all three teammates for this match
          "actual_total": float,               # TBA match total (alliance score)
          "team_epas": {team_num: {"epa": float, "epa_auto": float,
                                   "epa_teleop": float, "epa_endgame": float}},
          # Optional per-phase actuals (from TBA score_breakdown):
          "actual_auto": float,
          "actual_teleop": float,
          "actual_endgame": float,
        }
        Each dict must include both team_a and team_b in alliance_teams.
    component_breakdown : bool
        If True, compute auto/teleop/endgame synergy when phase actuals are
        available. If phase data is absent, those fields return 0.0 and the
        caller should rely on "overall" only.
    use_defense_adjustment : bool (keyword-only, default False)
        When True, substitutes defense-adjusted EPA for team_a and team_b in
        the expected-total baseline. Requires team_a_data and team_b_data to
        provide observations; falls back to raw EPA if data is missing.
        Default False preserves backward-compatible behavior.
    team_a_data : optional dict — {"team": int, "raw_epa": float, "observations": list}
        Required when use_defense_adjustment=True; ignored otherwise.
    team_b_data : optional dict — same schema as team_a_data.

    Returns
    -------
    dict with keys:
        "overall"   : float — mean(actual - expected) per match (overall synergy)
        "auto"      : float — phase synergy for auto (0.0 if data unavailable)
        "teleop"    : float — phase synergy for teleop (0.0 if data unavailable)
        "endgame"   : float — phase synergy for endgame (0.0 if data unavailable)
        "n_matches" : int — number of shared matches
        "has_component_data": bool — True when phase-level breakdown was used
        "used_fallback": bool — True when n_matches < MIN_SHARED_MATCHES
        "defense_adjusted": bool — True when use_defense_adjustment=True and
            at least one team's DA-EPA differed from raw EPA
    """
    # Pre-compute defense-adjusted EPAs when requested (outside the match loop)
    _da_epa_a: Optional[float] = None
    _da_epa_b: Optional[float] = None
    if use_defense_adjustment:
        if team_a_data is not None:
            try:
                da_r = compute_defense_adjusted_epa(
                    team=team_a_data.get("team", team_a),
                    raw_epa=team_a_data.get("raw_epa", 0.0),
                    observations=team_a_data.get("observations", []),
                )
                _da_epa_a = da_r.offensive_epa
            except Exception:
                pass
        if team_b_data is not None:
            try:
                da_r = compute_defense_adjusted_epa(
                    team=team_b_data.get("team", team_b),
                    raw_epa=team_b_data.get("raw_epa", 0.0),
                    observations=team_b_data.get("observations", []),
                )
                _da_epa_b = da_r.offensive_epa
            except Exception:
                pass

    if not shared_matches:
        return {
            "overall": 0.0,
            "auto": 0.0,
            "teleop": 0.0,
            "endgame": 0.0,
            "n_matches": 0,
            "has_component_data": False,
            "used_fallback": True,
            "defense_adjusted": False,
        }

    overall_deltas: list[float] = []
    auto_deltas: list[float] = []
    teleop_deltas: list[float] = []
    endgame_deltas: list[float] = []

    for match in shared_matches:
        alliance_teams = match.get("alliance_teams", [])
        # Ensure both target teams are present in this match's alliance
        if team_a not in alliance_teams or team_b not in alliance_teams:
            continue

        team_epas: dict = match.get("team_epas", {})
        actual_total = match.get("actual_total")
        if actual_total is None:
            continue  # Can't compute synergy without actual score

        # Expected = sum of individual EPAs (optionally defense-adjusted for A and B)
        def _epa_for(t: int) -> float:
            if use_defense_adjustment and t == team_a and _da_epa_a is not None:
                return _da_epa_a
            if use_defense_adjustment and t == team_b and _da_epa_b is not None:
                return _da_epa_b
            return team_epas.get(t, {}).get("epa", 0.0)

        expected_total = sum(_epa_for(t) for t in alliance_teams)
        overall_deltas.append(actual_total - expected_total)

        # Component-level synergy (auto / teleop / endgame)
        if component_breakdown:
            for phase, actual_key, epa_key in (
                ("auto", "actual_auto", "epa_auto"),
                ("teleop", "actual_teleop", "epa_teleop"),
                ("endgame", "actual_endgame", "epa_endgame"),
            ):
                actual_phase = match.get(actual_key)
                if actual_phase is None:
                    continue
                expected_phase = sum(
                    team_epas.get(t, {}).get(epa_key, 0.0) for t in alliance_teams
                )
                delta = actual_phase - expected_phase
                if phase == "auto":
                    auto_deltas.append(delta)
                elif phase == "teleop":
                    teleop_deltas.append(delta)
                elif phase == "endgame":
                    endgame_deltas.append(delta)

    n = len(overall_deltas)
    if n == 0:
        return {
            "overall": 0.0,
            "auto": 0.0,
            "teleop": 0.0,
            "endgame": 0.0,
            "n_matches": 0,
            "has_component_data": False,
            "used_fallback": True,
            "defense_adjusted": False,
        }

    def _mean(lst: list[float]) -> float:
        return round(sum(lst) / len(lst), 2) if lst else 0.0

    has_component = bool(auto_deltas or teleop_deltas or endgame_deltas)
    _defense_adjusted = use_defense_adjustment and (
        _da_epa_a is not None or _da_epa_b is not None
    )

    return {
        "overall": _mean(overall_deltas),
        "auto": _mean(auto_deltas),
        "teleop": _mean(teleop_deltas),
        "endgame": _mean(endgame_deltas),
        "n_matches": n,
        "has_component_data": has_component,
        "used_fallback": n < MIN_SHARED_MATCHES,
        "defense_adjusted": _defense_adjusted,
    }


# ─── Match builder from TBA/Statbotics dicts ─────────────────────────────────


def build_shared_match(
    alliance_teams: list[int],
    match_breakdown: dict,
    team_epas: dict[int, dict],
    match_key: str = "",
) -> dict:
    """
    Build a shared_match dict from TBA match_breakdown and Statbotics EPA dicts.

    Convenience constructor so callers don't need to know the internal shape.

    Parameters
    ----------
    alliance_teams : list of 3 int team numbers that played together
    match_breakdown : TBA score_breakdown dict for this alliance (red or blue subtree)
        Must contain at minimum a total-points field.
    team_epas : dict mapping team_num → {"epa": float, "epa_auto": float,
                                          "epa_teleop": float, "epa_endgame": float}
        Component keys are optional; if absent, phase synergy will be skipped.
    match_key : str — TBA match key (for debugging only)

    Returns
    -------
    shared_match dict suitable for compute_pair_synergy / compute_team_synergy_profile
    """
    actual_total = _extract_float(match_breakdown, _TOTAL_KEYS)
    actual_auto = _extract_float(match_breakdown, _AUTO_KEYS)
    actual_teleop = _extract_float(match_breakdown, _TELEOP_KEYS)
    actual_endgame = _extract_float(match_breakdown, _ENDGAME_KEYS)

    record: dict = {
        "match_key": match_key,
        "alliance_teams": list(alliance_teams),
        "actual_total": actual_total,
        "team_epas": team_epas,
    }
    if actual_auto is not None:
        record["actual_auto"] = actual_auto
    if actual_teleop is not None:
        record["actual_teleop"] = actual_teleop
    if actual_endgame is not None:
        record["actual_endgame"] = actual_endgame

    return record


# ─── Event-level profile ──────────────────────────────────────────────────────


def compute_team_synergy_profile(
    team: int,
    all_teams: list[int],
    event_matches: list[dict],
) -> dict[int, dict]:
    """
    Compute synergy of `team` with every other team they played alongside.

    Answers: "Who does team 2950 play best with on this field?"

    Parameters
    ----------
    team : int
        The "home" team to build a profile for.
    all_teams : list[int]
        All team numbers at the event (used to enumerate potential partners).
    event_matches : list of shared_match dicts (as returned by build_shared_match).
        Each dict is one alliance appearance; team must appear in alliance_teams
        to count.

    Returns
    -------
    dict mapping teammate_num → synergy dict (from compute_pair_synergy).
    Only teams that shared at least one match with `team` appear in the result.
    """
    # Group shared_match records by co-teammate
    # Each match has 3 teams; for our home team, we pair with the other 2.
    matches_by_partner: dict[int, list[dict]] = {}

    for match in event_matches:
        alliance = match.get("alliance_teams", [])
        if team not in alliance:
            continue
        for other in alliance:
            if other == team:
                continue
            matches_by_partner.setdefault(other, []).append(match)

    profile: dict[int, dict] = {}
    for partner, shared in matches_by_partner.items():
        profile[partner] = compute_pair_synergy(team, partner, shared)

    return profile


def best_synergy_partners(
    team: int,
    profile: dict[int, dict],
    top_n: int = 5,
) -> list[tuple[int, dict]]:
    """
    Return the top N synergy partners for a team, ranked by overall synergy.

    Parameters
    ----------
    team : int
        The home team (used to filter self from profile if present).
    profile : dict — output of compute_team_synergy_profile
    top_n : int — max partners to return (default 5)

    Returns
    -------
    list of (partner_num, synergy_dict) tuples, sorted by synergy["overall"]
    descending (best partners first). Pairs with used_fallback=True appear
    after reliable pairs at the same score level.
    """
    pairs = [
        (partner, syn)
        for partner, syn in profile.items()
        if partner != team
    ]

    # Sort: reliable data first (not used_fallback), then by overall score desc
    pairs.sort(
        key=lambda x: (not x[1].get("used_fallback", True), x[1].get("overall", 0.0)),
        reverse=True,
    )

    return pairs[:top_n]


# ─── Display helpers ──────────────────────────────────────────────────────────


def format_synergy_row(
    partner: int,
    syn: dict,
    partner_name: str = "",
    carry_delta: Optional[float] = None,
    *,
    defense_adjusted_synergy_val: Optional[float] = None,
) -> str:
    """
    Format a synergy dict as a single pick-board display row.

    Parameters
    ----------
    partner : int — team number of the partner
    syn : dict — output of compute_pair_synergy
    partner_name : str — optional display name (truncated to 18 chars)
    carry_delta : optional float from alliance_decomposition.aggregate_team_delta_ema.
        When both carry_delta > 3 AND overall synergy > 5, an [ELITE] marker is shown.
    defense_adjusted_synergy_val : optional float from defense_adjusted_synergy().
        When carry_delta > 3 AND defense_adjusted_synergy_val > 5, emits [ELITE+D]
        instead of [ELITE] to signal defense-confirmed elite status.

    Example output:
        Team  2468 [GoodName         ]  overall: +8.3 | auto: +2.1 | teleop: +4.5 | endgame: +1.7  (5 matches)
        Team  1296 [OtherTeam        ]  overall: +7.1 [no component data]  (2 matches) [low-n]
        Team   836 [EliteMatch       ]  overall: +9.0 | auto: +3.0 | teleop: +4.5 | endgame: +1.5  (6 matches) [ELITE]
        Team   836 [EliteMatch       ]  overall: +9.0 | auto: +3.0 | teleop: +4.5 | endgame: +1.5  (6 matches) [ELITE+D]
    """
    overall = syn.get("overall", 0.0)
    n = syn.get("n_matches", 0)
    fallback = syn.get("used_fallback", False)
    has_comp = syn.get("has_component_data", False)

    sign = "+" if overall >= 0 else ""
    overall_str = f"overall: {sign}{overall:.1f}"

    if has_comp:
        auto = syn.get("auto", 0.0)
        teleop = syn.get("teleop", 0.0)
        endgame = syn.get("endgame", 0.0)
        comp_str = (
            f" | auto: {'+' if auto >= 0 else ''}{auto:.1f}"
            f" | teleop: {'+' if teleop >= 0 else ''}{teleop:.1f}"
            f" | endgame: {'+' if endgame >= 0 else ''}{endgame:.1f}"
        )
    else:
        comp_str = " [no component data]"

    n_str = f"({n} match{'es' if n != 1 else ''})"
    low_n_tag = " [low-n]" if fallback else ""

    # Elite pairing: both carry_delta > 3 AND overall synergy > 5
    # [ELITE+D] when additionally defense_adjusted_synergy > 5 (defense-confirmed)
    elite_tag = ""
    if carry_delta is not None and carry_delta > 3.0 and overall > 5.0:
        if (
            defense_adjusted_synergy_val is not None
            and defense_adjusted_synergy_val > 5.0
        ):
            elite_tag = " [ELITE+D]"
        else:
            elite_tag = " [ELITE]"

    name_str = f" [{partner_name[:18]:<18}]" if partner_name else ""
    return (
        f"Team {partner:5d}{name_str}  {overall_str}{comp_str}  {n_str}{low_n_tag}{elite_tag}"
    )
