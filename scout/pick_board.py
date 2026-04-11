#!/usr/bin/env python3
"""
The Engine — Live Alliance Selection Pick Board
Team 2950 — The Devastators

Two-phase tool:
  PHASE 1 (Lunch): Generate pick board from EPA data + captains
  PHASE 2 (Live):  Students feed in picks as they happen, board recalculates

Usage:
  # Setup: generate board (captains = top 8 by qual rank)
  python3 pick_board.py setup <event_key> --team 2881 --seed 3

  # Or manually set captains if known
  python3 pick_board.py setup <event_key> --team 2881 --seed 3 --captains 2468,2689,2881,1296,11178,436,2687,9506

  # Record a pick during live draft
  python3 pick_board.py pick <alliance#> <team#>
  python3 pick_board.py pick 1 148       # Alliance 1 picks team 148

  # Show current board + recommendation
  python3 pick_board.py board

  # Show recommendation only (what to pick RIGHT NOW)
  python3 pick_board.py rec

  # Undo last pick (misheard a number)
  python3 pick_board.py undo

  # Show all alliances as currently built
  python3 pick_board.py alliances

  # Monte Carlo: simulate playoffs with current alliances
  python3 pick_board.py sim [--sims 5000]
"""

import json
import math
import random
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from statbotics_client import get_event_teams

try:
    from tba_client import event_matches, event_alliances as tba_alliances
    HAS_TBA = True
except Exception:
    HAS_TBA = False

STATE_DIR = Path(__file__).parent / ".cache" / "draft"
STATE_FILE = STATE_DIR / "live_draft.json"


# ─── Data Structures ───


@dataclass
class TeamData:
    team: int
    name: str
    epa: float
    sd: float
    floor: float
    ceiling: float
    epa_auto: float
    epa_teleop: float
    epa_endgame: float
    total_fuel: float
    total_tower: float
    qual_rank: int
    qual_record: str
    # Scoring zone breakdown (game-piece level)
    auto_fuel: float = 0.0
    auto_tower: float = 0.0
    first_shift: float = 0.0
    second_shift: float = 0.0
    transition_fuel: float = 0.0
    endgame_fuel: float = 0.0
    endgame_tower: float = 0.0


def _parse_team(raw: dict) -> TeamData:
    epa = raw.get("epa", {})
    bd = epa.get("breakdown", {})
    sd = epa.get("total_points", {}).get("sd", 0) or 0
    mean = epa.get("total_points", {}).get("mean", 0) or 0
    rec = raw.get("record", {}).get("qual", {})
    return TeamData(
        team=raw.get("team", 0),
        name=raw.get("team_name", ""),
        epa=mean,
        sd=sd,
        floor=mean - 1.5 * sd,
        ceiling=mean + 1.5 * sd,
        epa_auto=bd.get("auto_points", 0) or 0,
        epa_teleop=bd.get("teleop_points", 0) or 0,
        epa_endgame=bd.get("endgame_points", 0) or 0,
        total_fuel=bd.get("total_fuel", bd.get("teleop_points", 0)) or 0,
        total_tower=bd.get("total_tower", 0) or 0,
        qual_rank=rec.get("rank", 99),
        qual_record=f"{rec.get('wins', 0)}-{rec.get('losses', 0)}",
        auto_fuel=bd.get("auto_fuel", 0) or 0,
        auto_tower=bd.get("auto_tower", 0) or 0,
        first_shift=bd.get("first_shift_fuel", 0) or 0,
        second_shift=bd.get("second_shift_fuel", 0) or 0,
        transition_fuel=bd.get("transition_fuel", 0) or 0,
        endgame_fuel=bd.get("endgame_fuel", 0) or 0,
        endgame_tower=bd.get("endgame_tower", 0) or 0,
    )


# ─── State Management ───


def _blank_state():
    return {
        "event_key": "",
        "our_team": 0,
        "our_seed": 0,
        "captains": [],          # [team#] indexed 0-7 for alliances 1-8
        "picks": [],             # [{alliance: int, team: int, round: int}]
        "teams": {},             # {team#: TeamData as dict}
        "history": [],           # for undo
        "dnp": [],                  # [team#] Do Not Pick — excluded from rec
        "live_matches": {},         # {match_key: LiveMatch.to_dict()} — from Live Scout workers
    }


def save_state(state: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_state() -> dict:
    if not STATE_FILE.exists():
        print("  No active draft. Run 'setup' first.")
        sys.exit(1)
    return json.loads(STATE_FILE.read_text())


# ─── Live Scout integration ───
#
# Live Scout workers produce LiveMatch records (see scout/live_match.py) and
# feed them into pick_board state via append_live_match(). recompute_team_aggregates()
# then walks every live match and updates the per-team real_sd / real_avg_score /
# streak / match_count fields that cmd_enrich writes from TBA. This lets the
# board stay fresh during an event without waiting on TBA's post-match delay.


def append_live_match(state: dict, live_match) -> bool:
    """Idempotent upsert of a LiveMatch into state['live_matches'].

    Accepts either a LiveMatch instance or a plain dict (already-serialized
    record). Records are keyed by match_key so re-processing the same match
    overwrites the prior record. Matches for events other than
    state['event_key'] are silently ignored.

    Returns True if state was mutated, False otherwise.

    Caller is responsible for calling save_state() and (usually)
    recompute_team_aggregates() after batching updates.
    """
    if hasattr(live_match, "to_dict"):
        record = live_match.to_dict()
    else:
        record = dict(live_match)

    event_key = record.get("event_key")
    match_key = record.get("match_key")
    if not event_key or not match_key:
        raise ValueError(
            f"live_match missing event_key/match_key: {record!r}"
        )

    # Scope guard — don't cross-contaminate boards from different events
    if state.get("event_key") and event_key != state["event_key"]:
        return False

    live_matches = state.setdefault("live_matches", {})
    prior = live_matches.get(match_key)
    if prior == record:
        return False

    live_matches[match_key] = record
    return True


def _aggregate_scores(scores: list) -> dict:
    """Compute avg / per-robot SD / hot-cold streak from a list of
    alliance scores. Matches the shape cmd_enrich writes."""
    n = len(scores)
    if n < 3:
        return {}

    avg = sum(scores) / n
    variance = sum((s - avg) ** 2 for s in scores) / n
    # Alliance score is 3 robots — divide by 3 to get per-robot SD
    real_sd = math.sqrt(variance) / 3

    recent = scores[-3:]
    recent_avg = sum(recent) / len(recent)
    streak = ""
    if recent_avg > avg * 1.15:
        streak = "HOT"
    elif recent_avg < avg * 0.85:
        streak = "COLD"

    return {
        "real_sd": round(real_sd, 1),
        "real_avg_score": round(avg, 1),
        "streak": streak,
        "match_count": n,
    }


def recompute_team_aggregates(state: dict) -> int:
    """Walk state['live_matches'] and rewrite per-team enrichment fields.

    For every team in state['teams'], sum all alliance scores from live
    matches where that team played (using whichever alliance they were on)
    and recompute real_sd / real_avg_score / streak / match_count the same
    way cmd_enrich does from TBA. Only considers `is_complete` matches
    (both red and blue scores present) and only qualification matches
    (comp_level == 'qm'), matching cmd_enrich's scope.

    Returns the number of teams whose aggregates were updated.
    """
    live_matches = state.get("live_matches", {})
    teams_db = state.get("teams", {})

    # Collect per-team ordered score lists. Iterate matches in a stable
    # order (by match_num within comp_level) so the "recent 3" streak
    # window is deterministic.
    def sort_key(record: dict):
        return (record.get("comp_level", ""), int(record.get("match_num", 0)))

    ordered = sorted(
        (m for m in live_matches.values() if m.get("comp_level") == "qm"),
        key=sort_key,
    )

    team_scores: dict = {}
    for m in ordered:
        red_score = m.get("red_score")
        blue_score = m.get("blue_score")
        if red_score is None or blue_score is None:
            continue  # match not finalized yet
        for team in m.get("red_teams", []):
            team_scores.setdefault(team, []).append(red_score)
        for team in m.get("blue_teams", []):
            team_scores.setdefault(team, []).append(blue_score)

    updated = 0
    for team, scores in team_scores.items():
        key = str(team)
        if key not in teams_db:
            continue
        agg = _aggregate_scores(scores)
        if not agg:
            continue
        teams_db[key].update(agg)
        updated += 1
    return updated


# ─── Draft Logic ───


def get_alliances(state: dict) -> dict:
    """Build current alliance map from state."""
    alliances = {}
    for i, cap in enumerate(state["captains"], 1):
        alliances[i] = [cap]

    for p in state["picks"]:
        a = p["alliance"]
        if a in alliances:
            alliances[a].append(p["team"])

    return alliances


def get_taken(state: dict) -> set:
    """All teams currently on an alliance."""
    taken = set(state["captains"])
    for p in state["picks"]:
        taken.add(p["team"])
    return taken


def get_available(state: dict) -> list:
    """Available teams sorted by EPA descending. Excludes DNP teams."""
    taken = get_taken(state)
    dnp = set(state.get("dnp", []))
    pool = []
    for key, td in state["teams"].items():
        t = int(key)
        if t not in taken and t not in dnp:
            pool.append(td)
    pool.sort(key=lambda x: x["epa"], reverse=True)
    return pool


def current_round(state: dict) -> int:
    """Which round are we in? (1 or 2)"""
    n_picks = len(state["picks"])
    n_captains = len(state["captains"])
    if n_picks < n_captains:
        return 1
    return 2


def current_pick_position(state: dict) -> tuple:
    """Returns (alliance#_picking, round#)."""
    n_picks = len(state["picks"])
    n_cap = len(state["captains"])

    if n_picks < n_cap:
        # Round 1: picks go 1 → 8
        return n_picks + 1, 1
    else:
        # Round 2: picks go 8 → 1 (snake)
        r2_pick = n_picks - n_cap
        return n_cap - r2_pick, 2


def picks_before_us(state: dict, round_num: int) -> int:
    """How many picks happen before our team in a given round."""
    seed = state["our_seed"]
    if round_num == 1:
        return seed - 1  # Alliance 1 picks first
    else:
        n_cap = len(state["captains"])
        return n_cap - seed  # Alliance 8 picks first in R2


def project_board(state: dict) -> list:
    """
    Project the full board: for each available team, show if they're
    realistically available as R1 or R2 for our team.

    Assumes all other alliances draft greedily by EPA.
    """
    available = get_available(state)
    rd = current_round(state)
    seed = state["our_seed"]
    n_cap = len(state["captains"])
    our_team = state["our_team"]

    # Count picks already made this round
    picks_this_round = 0
    for p in state["picks"]:
        if p["round"] == rd:
            picks_this_round += 1

    board = []
    for i, td in enumerate(available):
        # What overall pick # is this team (in the greedy draft)?
        pick_num = i + 1

        if rd == 1:
            # R1: our team picks at position = seed
            # picks already done this round shifts remaining
            adjusted_pos = seed - picks_this_round
            if pick_num < adjusted_pos:
                status = "GONE R1"
            elif pick_num == adjusted_pos:
                status = ">>> YOUR R1 <<<"
            elif pick_num <= n_cap - picks_this_round:
                status = "GONE R1"
            else:
                # Would carry into R2
                r2_pos = pick_num - (n_cap - picks_this_round)
                r2_our_pos = n_cap - seed + 1
                if r2_pos < r2_our_pos:
                    status = "GONE R2"
                elif r2_pos == r2_our_pos:
                    status = ">>> YOUR R2 <<<"
                elif r2_pos <= n_cap:
                    status = "GONE R2"
                else:
                    status = "AVAILABLE"
        elif rd == 2:
            # R2: snake order (8→1). Our position = n_cap - seed + 1
            adjusted_pos = (n_cap - seed + 1) - picks_this_round
            if pick_num < adjusted_pos:
                status = "GONE R2"
            elif pick_num == adjusted_pos:
                status = ">>> YOUR R2 <<<"
            elif pick_num <= n_cap - picks_this_round:
                status = "GONE R2"
            else:
                status = "AVAILABLE"
        else:
            status = "DRAFT OVER"

        board.append({**td, "pick_order": pick_num, "status": status})

    return board


def _zone_complementarity(us: dict, them: dict) -> tuple:
    """
    Score how well a candidate complements our alliance's scoring zones.

    Key insight: a partner strong where we're weak > partner strong where
    we're already strong (diminishing returns on same zones).

    Returns (score 0-100, reasoning string).
    """
    reasons = []
    score = 0.0

    us_fuel = us.get("total_fuel", 0)
    us_tower = us.get("total_tower", 0)
    them_fuel = them.get("total_fuel", 0)
    them_tower = them.get("total_tower", 0)

    # ── Tower gap coverage (most impactful — tower scorers are rare) ──
    if us_tower < 2.0 and them_tower > 1.0:
        tower_bonus = min(30, them_tower * 12)
        score += tower_bonus
        reasons.append(f"Tower ({them_tower:.1f}) covers our gap ({us_tower:.1f})")
    elif them_tower > 2.0:
        score += min(15, them_tower * 5)
        reasons.append(f"Tower scorer ({them_tower:.1f})")

    # ── Auto gap coverage ──
    us_auto = us.get("epa_auto", 0)
    them_auto = them.get("epa_auto", 0)
    if them_auto > us_auto * 1.2 and them_auto > 8:
        auto_bonus = min(20, (them_auto - us_auto) * 2)
        score += auto_bonus
        reasons.append(f"Strong auto ({them_auto:.1f} vs our {us_auto:.1f})")

    # ── Endgame stacking (both having endgame is multiplicative) ──
    us_end = us.get("epa_endgame", 0)
    them_end = them.get("epa_endgame", 0)
    if them_end > 5 and us_end > 5:
        end_bonus = min(15, them_end * 1.0)
        score += end_bonus
        reasons.append(f"Endgame stacks ({them_end:.1f} + our {us_end:.1f})")
    elif them_end > 8 and us_end <= 3:
        end_bonus = min(20, them_end * 1.5)
        score += end_bonus
        reasons.append(f"Endgame covers our weakness ({them_end:.1f})")

    # ── Shift coverage (don't want both robots only scoring in same shift) ──
    us_1st = us.get("first_shift", 0)
    us_2nd = us.get("second_shift", 0)
    them_1st = them.get("first_shift", 0)
    them_2nd = them.get("second_shift", 0)

    # Bonus if they're strong in our weak shift
    if us_1st > us_2nd * 1.5 and them_2nd > them_1st:
        score += 10
        reasons.append("Covers 2nd shift (our weak phase)")
    elif us_2nd > us_1st * 1.5 and them_1st > them_2nd:
        score += 10
        reasons.append("Covers 1st shift (our weak phase)")

    # ── Raw floor bonus (don't pick "complementary" but bad teams) ──
    them_floor = them.get("floor", 0)
    if them_floor > 15:
        score += min(10, them_floor * 0.3)
    elif them_floor < 0:
        score -= 5
        reasons.append(f"WARNING: negative floor ({them_floor:.0f})")

    score = max(0, min(100, score))
    reasoning = "; ".join(reasons) if reasons else "Fuel overlap, average complementarity"
    return round(score, 1), reasoning


def _mc_quick(us_teams: list, them_teams: list, teams_db: dict,
              n_sims: int = 3000) -> float:
    """Quick Monte Carlo best-of-3 win%. Returns series win rate 0-1."""
    wins = 0
    for _ in range(n_sims):
        mw = 0
        for _ in range(3):
            us_score = sum(
                max(0, random.gauss(
                    teams_db.get(str(t), {}).get("epa", 0),
                    teams_db.get(str(t), {}).get("sd", 10)
                )) for t in us_teams
            )
            them_score = sum(
                max(0, random.gauss(
                    teams_db.get(str(t), {}).get("epa", 0),
                    teams_db.get(str(t), {}).get("sd", 10)
                )) for t in them_teams
            )
            if us_score > them_score:
                mw += 1
        if mw >= 2:
            wins += 1
    return wins / n_sims


def recommend_pick(state: dict) -> list:
    """
    Return top recommended picks for our team's current turn.

    Scoring: EPA (30%) + Floor (10%) + Complementarity (25%) + Monte Carlo (25%) + EYE (10%).
    If no EYE data, weights redistribute to EPA (35%) + Floor (15%) + Comp (25%) + MC (25%).
    Complementarity uses game-piece-level scoring zone analysis.
    Monte Carlo simulates QF matchup with projected opponent.
    EYE adds qualitative scouting: reliability, driver skill, defense resistance.
    """
    available = get_available(state)
    if not available:
        return []

    our_seed = state["our_seed"]
    our_data = state["teams"].get(str(state["our_team"]))
    if not our_data:
        return available[:10]

    # Get our current alliance (captain + any existing picks)
    alliances = get_alliances(state)
    our_members = alliances.get(our_seed, [])

    # Aggregate our alliance's scoring profile
    our_profile = {"epa_auto": 0, "epa_endgame": 0, "total_fuel": 0,
                   "total_tower": 0, "first_shift": 0, "second_shift": 0,
                   "floor": 0, "epa": 0}
    for t in our_members:
        td = state["teams"].get(str(t), {})
        for k in our_profile:
            our_profile[k] += td.get(k, 0)

    # Determine QF opponent (seed-based: 1v8, 2v7, 3v6, 4v5)
    n_cap = len(state["captains"])
    opp_seed = n_cap + 1 - our_seed
    opp_members = alliances.get(opp_seed, [])

    max_epa = available[0]["epa"] if available else 1

    random.seed(42)

    scored = []
    for td in available:
        # ── EPA + Floor (raw strength) ──
        epa_norm = td["epa"] / max_epa if max_epa > 0 else 0
        floor_norm = max(0, td["floor"]) / max_epa if max_epa > 0 else 0

        # ── Complementarity (scoring zone analysis) ──
        comp_score, comp_reason = _zone_complementarity(our_profile, td)
        comp_norm = comp_score / 100.0

        # ── Monte Carlo vs QF opponent (if opponent alliance is known) ──
        mc_win = 0.0
        if len(opp_members) >= 1:
            test_alliance = our_members + [td["team"]]
            mc_win = _mc_quick(test_alliance, opp_members, state["teams"], 2000)
        mc_norm = mc_win

        # ── EYE scouting (qualitative data) ──
        eye_composite = td.get("eye_composite", 0)
        eye_confidence = td.get("eye_confidence", 0)
        eye_norm = (eye_composite / 100.0) * (eye_confidence / 100.0)

        # ── Combined score ──
        # With EYE data: EPA 30% + Floor 10% + Comp 25% + MC 25% + EYE 10%
        # Without: redistribute EYE weight to EPA + Floor
        if eye_confidence > 0:
            pick_score = (epa_norm * 0.30 + floor_norm * 0.10 +
                          comp_norm * 0.25 + mc_norm * 0.25 +
                          eye_norm * 0.10)
        else:
            pick_score = (epa_norm * 0.35 + floor_norm * 0.15 +
                          comp_norm * 0.25 + mc_norm * 0.25)

        scored.append({
            **td,
            "pick_score": pick_score,
            "comp_score": comp_score,
            "comp_reason": comp_reason,
            "mc_win": mc_win,
            "eye_score": eye_composite,
            "eye_conf": eye_confidence,
        })

    scored.sort(key=lambda x: x["pick_score"], reverse=True)
    return scored[:15]


# ─── Monte Carlo ───


def sim_bo3(a_teams: list, b_teams: list, teams_db: dict, n: int = 5000):
    """Simulate best-of-3 series. Returns (series_win%, avg_match_wins)."""
    series_w = 0
    total_mw = 0
    for _ in range(n):
        mw = 0
        for _ in range(3):
            a_score = sum(
                max(0, random.gauss(
                    teams_db.get(str(t), {}).get("epa", 0),
                    teams_db.get(str(t), {}).get("sd", 10)
                ))
                for t in a_teams
            )
            b_score = sum(
                max(0, random.gauss(
                    teams_db.get(str(t), {}).get("epa", 0),
                    teams_db.get(str(t), {}).get("sd", 10)
                ))
                for t in b_teams
            )
            if a_score > b_score:
                mw += 1
        if mw >= 2:
            series_w += 1
        total_mw += mw
    return series_w / n * 100, total_mw / n


def sim_playoffs(state: dict, n_sims: int = 5000):
    """Simulate full playoff bracket with current alliances."""
    alliances = get_alliances(state)
    n_cap = len(state["captains"])

    # QF matchups: 1v8, 2v7, 3v6, 4v5
    matchups = [(1, n_cap), (2, n_cap - 1), (3, n_cap - 2), (4, n_cap - 3)]

    our_seed = state["our_seed"]
    print(f"\n  PLAYOFF SIMULATION ({n_sims} sims)")
    print(f"  {'─' * 60}")

    for a, b in matchups:
        a_teams = alliances.get(a, [])
        b_teams = alliances.get(b, [])
        a_epa = sum(state["teams"].get(str(t), {}).get("epa", 0) for t in a_teams)
        b_epa = sum(state["teams"].get(str(t), {}).get("epa", 0) for t in b_teams)

        win_pct, avg_mw = sim_bo3(a_teams, b_teams, state["teams"], n_sims)

        tag_a = " ← US" if a == our_seed else ""
        tag_b = " ← US" if b == our_seed else ""

        # Show from perspective of higher seed
        print(f"\n  QF: A{a} ({a_epa:.0f}){tag_a} vs A{b} ({b_epa:.0f}){tag_b}")
        print(f"    A{a} team: {a_teams}")
        print(f"    A{b} team: {b_teams}")
        print(f"    A{a} wins: {win_pct:.1f}%  |  A{b} wins: {100-win_pct:.1f}%")


# ─── CLI Commands ───


def cmd_setup(args):
    """Setup draft board from event data."""
    if not args:
        print("Usage: pick_board.py setup <event_key> --team N --seed N [--captains 1,2,3,...]")
        return

    event_key = args[0]
    our_team = None
    our_seed = None
    manual_captains = None

    i = 1
    while i < len(args):
        if args[i] == "--team" and i + 1 < len(args):
            our_team = int(args[i + 1]); i += 2
        elif args[i] == "--seed" and i + 1 < len(args):
            our_seed = int(args[i + 1]); i += 2
        elif args[i] == "--captains" and i + 1 < len(args):
            manual_captains = [int(t) for t in args[i + 1].split(",")]
            i += 2
        else:
            i += 1

    if not our_team or not our_seed:
        print("Error: --team and --seed are required")
        return

    print(f"\n  THE SCOUT — PICK BOARD SETUP")
    print(f"  Event: {event_key}")
    print(f"  Our team: {our_team} | Seed: Alliance {our_seed}")
    print(f"  {'─' * 50}")

    # Fetch EPA data
    print(f"  Fetching EPA data...")
    raw = get_event_teams(event_key)
    if not raw:
        print(f"  ERROR: No data for {event_key}")
        return

    # Parse all teams
    teams_db = {}
    for t in raw:
        td = _parse_team(t)
        teams_db[str(td.team)] = asdict(td)

    # Determine captains
    if manual_captains:
        captains = manual_captains
        print(f"  Captains (manual): {captains}")
    else:
        # Default: top 8 by qual rank
        by_rank = sorted(teams_db.values(), key=lambda x: x["qual_rank"])
        captains = [t["team"] for t in by_rank[:8]]
        print(f"  Captains (top 8 by rank): {captains}")

    # Verify our team is a captain at the right seed
    if our_team not in captains:
        print(f"  WARNING: {our_team} not in captain list!")
    elif captains[our_seed - 1] != our_team:
        print(f"  WARNING: {our_team} is in captain list but not at seed {our_seed}")
        print(f"  Captain at seed {our_seed}: {captains[our_seed - 1]}")

    state = _blank_state()
    state["event_key"] = event_key
    state["our_team"] = our_team
    state["our_seed"] = our_seed
    state["captains"] = captains
    state["teams"] = teams_db
    save_state(state)

    n_avail = len(teams_db) - len(captains)
    print(f"  {len(teams_db)} teams loaded, {n_avail} available for picking")
    print(f"\n  Draft state saved. Ready for picks!")
    print(f"  Run 'pick_board.py board' to see the full board.")
    print(f"  Run 'pick_board.py pick <alliance#> <team#>' to record picks.\n")


def cmd_pick(args):
    """Record a pick."""
    if len(args) < 2:
        print("Usage: pick_board.py pick <alliance#> <team#>")
        return

    alliance = int(args[0])
    team = int(args[1])
    state = load_state()

    # Validate
    if alliance < 1 or alliance > len(state["captains"]):
        print(f"  ERROR: Alliance must be 1-{len(state['captains'])}")
        return
    if str(team) not in state["teams"]:
        print(f"  ERROR: Team {team} not found at event")
        return
    taken = get_taken(state)
    if team in taken:
        print(f"  ERROR: Team {team} already taken")
        return

    rd = current_round(state)

    # Save for undo
    state["history"].append(json.dumps(state["picks"]))

    state["picks"].append({
        "alliance": alliance,
        "team": team,
        "round": rd,
    })
    save_state(state)

    td = state["teams"][str(team)]
    pos, new_rd = current_pick_position(state)

    print(f"\n  ✓ RECORDED: Alliance {alliance} picks {team} {td['name']} (EPA {td['epa']:.1f}) [R{rd}]")

    # Check if it's our turn next
    our_seed = state["our_seed"]
    if (new_rd == 1 and pos == our_seed) or (new_rd == 2 and pos == our_seed):
        print(f"\n  ★ IT'S YOUR TURN! Alliance {our_seed} picks next (Round {new_rd})")
        print(f"  Run 'pick_board.py rec' for recommendation\n")
    else:
        print(f"  Next: Alliance {pos} picks (Round {new_rd})\n")


def cmd_undo(args):
    """Undo last pick."""
    state = load_state()
    if not state["history"]:
        print("  Nothing to undo.")
        return

    prev = json.loads(state["history"].pop())
    removed = state["picks"][-1] if state["picks"] else None
    state["picks"] = prev
    save_state(state)

    if removed:
        print(f"  ✓ Undid: Alliance {removed['alliance']} pick of {removed['team']}")
    else:
        print(f"  ✓ Undo complete")


def cmd_board(args):
    """Show the full pick board."""
    state = load_state()
    board = project_board(state)
    pos, rd = current_pick_position(state)

    our_team = state["our_team"]
    our_seed = state["our_seed"]
    our_data = state["teams"].get(str(our_team), {})

    print(f"\n  THE SCOUT — LIVE PICK BOARD")
    print(f"  {state['event_key']} | Team {our_team} | Alliance {our_seed}")
    print(f"  Round {rd}, Alliance {pos} picking next")
    print(f"  Our EPA: {our_data.get('epa', 0):.1f} | Floor: {our_data.get('floor', 0):.1f}")
    print(f"  {'─' * 90}")

    print(f"\n  {'#':>3} {'Team':>6} {'Name':>22} {'EPA':>7} {'Floor':>7} {'Ceil':>7} {'SD':>6} {'Status':>16}")
    print(f"  {'─' * 90}")

    for entry in board:
        status = entry["status"]
        marker = "  "
        if "YOUR R1" in status:
            marker = ">>"
        elif "YOUR R2" in status:
            marker = ">>"

        print(f"{marker}{entry['pick_order']:3d} {entry['team']:6d} {entry['name'][:22]:>22} "
              f"{entry['epa']:7.1f} {entry['floor']:7.1f} {entry['ceiling']:7.1f} "
              f"{entry['sd']:6.1f} {status:>16}")

    # Show current alliances
    alliances = get_alliances(state)
    print(f"\n  CURRENT ALLIANCES:")
    for a in sorted(alliances.keys()):
        members = alliances[a]
        cap = members[0]
        picks = members[1:]
        epa_total = sum(state["teams"].get(str(t), {}).get("epa", 0) for t in members)
        tag = " ← US" if a == our_seed else ""
        pick_str = ", ".join(
            f"{t} ({state['teams'].get(str(t), {}).get('epa', 0):.0f})"
            for t in picks
        ) if picks else "—"
        print(f"  A{a}: {cap} ({state['teams'].get(str(cap), {}).get('epa', 0):.0f}) + {pick_str} = {epa_total:.0f}{tag}")

    print()


def cmd_rec(args):
    """Show pick recommendation."""
    state = load_state()
    pos, rd = current_pick_position(state)
    our_seed = state["our_seed"]
    our_data = state["teams"].get(str(state["our_team"]), {})
    n_cap = len(state["captains"])

    is_our_turn = (rd == 1 and pos == our_seed) or (rd == 2 and pos == our_seed)

    picks = recommend_pick(state)

    print(f"\n  THE SCOUT — PICK RECOMMENDATION")
    if is_our_turn:
        print(f"  ★ IT'S YOUR TURN (Round {rd})")
    else:
        print(f"  Preview — Alliance {pos} picking next (Round {rd})")
    print(f"  {'─' * 85}")

    # Show current alliance
    alliances = get_alliances(state)
    our_members = alliances.get(our_seed, [])
    our_epa = sum(state["teams"].get(str(t), {}).get("epa", 0) for t in our_members)
    our_tower = sum(state["teams"].get(str(t), {}).get("total_tower", 0) for t in our_members)
    our_fuel = sum(state["teams"].get(str(t), {}).get("total_fuel", 0) for t in our_members)
    print(f"  Our alliance: {our_members} (EPA {our_epa:.0f} | Fuel {our_fuel:.0f} | Tower {our_tower:.1f})")

    # Show QF opponent
    opp_seed = n_cap + 1 - our_seed
    opp_members = alliances.get(opp_seed, [])
    opp_epa = sum(state["teams"].get(str(t), {}).get("epa", 0) for t in opp_members)
    if opp_members:
        print(f"  QF opponent: A{opp_seed} {opp_members} (EPA {opp_epa:.0f})")
    print()

    # Check if any teams have EYE data
    has_eye = any(p.get("eye_score", 0) > 0 for p in picks[:10])

    # Top 10 recommendations with complementarity
    if has_eye:
        print(f"  {'#':>2} {'Team':>6} {'Name':>18} {'EPA':>6} {'Floor':>6} {'Comp':>5} {'QFWin':>6} {'EYE':>5} {'Score':>6}  Why")
        print(f"  {'─' * 95}")
    else:
        print(f"  {'#':>2} {'Team':>6} {'Name':>18} {'EPA':>6} {'Floor':>6} {'Comp':>5} {'QFWin':>6} {'Score':>6}  Why")
        print(f"  {'─' * 85}")

    for i, p in enumerate(picks[:10], 1):
        mc_str = f"{p.get('mc_win', 0)*100:.0f}%" if p.get('mc_win', 0) > 0 else "  —"
        reason = p.get('comp_reason', '')[:40]
        if has_eye:
            eye_str = f"{p.get('eye_score', 0):.0f}" if p.get('eye_conf', 0) > 0 else "  —"
            print(f"  {i:2d} {p['team']:6d} {p['name'][:18]:>18} {p['epa']:6.1f} "
                  f"{p['floor']:6.1f} {p.get('comp_score', 0):5.0f} {mc_str:>6} "
                  f"{eye_str:>5} {p['pick_score']:6.3f}  {reason}")
        else:
            print(f"  {i:2d} {p['team']:6d} {p['name'][:18]:>18} {p['epa']:6.1f} "
                  f"{p['floor']:6.1f} {p.get('comp_score', 0):5.0f} {mc_str:>6} "
                  f"{p['pick_score']:6.3f}  {reason}")

    if picks:
        top = picks[0]
        new_epa = our_epa + top["epa"]
        print(f"\n  ★ RECOMMENDATION: Pick {top['team']} {top['name']}")
        print(f"    Alliance EPA: {our_epa:.0f} → {new_epa:.0f} (+{top['epa']:.0f})")
        print(f"    Floor: {top['floor']:.1f} | Ceiling: {top['ceiling']:.1f}")
        if top.get('comp_reason'):
            print(f"    Why: {top['comp_reason']}")
        if top.get('mc_win', 0) > 0:
            print(f"    QF win probability: {top['mc_win']*100:.1f}%")
        if top.get('eye_conf', 0) > 0:
            print(f"    EYE scouting: {top['eye_score']:.0f}/100 "
                  f"(reliability {top.get('eye_reliability', 0):.0f}, "
                  f"driver {top.get('eye_driver', 0):.0f}) "
                  f"[{top['eye_conf']:.0f}% confidence]")

    print()


def cmd_alliances(args):
    """Show all alliances."""
    state = load_state()
    alliances = get_alliances(state)
    our_seed = state["our_seed"]

    print(f"\n  ALLIANCES — {state['event_key']}")
    print(f"  {'─' * 70}")

    for a in sorted(alliances.keys()):
        members = alliances[a]
        epa_total = sum(state["teams"].get(str(t), {}).get("epa", 0) for t in members)
        sd_total = sum(state["teams"].get(str(t), {}).get("sd", 0) ** 2 for t in members) ** 0.5
        floor_total = epa_total - 1.5 * sd_total

        tag = " ← US" if a == our_seed else ""
        member_str = " + ".join(
            f"{t} ({state['teams'].get(str(t), {}).get('name', '')[:15]}, {state['teams'].get(str(t), {}).get('epa', 0):.0f})"
            for t in members
        )
        print(f"\n  Alliance {a}{tag}:")
        print(f"    {member_str}")
        print(f"    EPA: {epa_total:.0f} | Floor: {floor_total:.0f} | SD: {sd_total:.0f}")

    print()


def cmd_sim(args):
    """Run playoff simulation."""
    state = load_state()
    n_sims = 5000
    if args and args[0] == "--sims" and len(args) > 1:
        n_sims = int(args[1])

    random.seed(42)
    sim_playoffs(state, n_sims)
    print()


# ─── Captain Prediction ───


def predict_captains(state: dict) -> list:
    """
    Predict which initial captains will get picked by higher seeds,
    and who backfills. Returns predicted final captain list.

    Logic: Alliance 1 picks the highest EPA non-captain available.
    If the best available is an existing captain (ranked below the picker),
    that captain likely accepts (giving up their spot) because joining
    a stronger alliance is usually better than captaining a weaker one.

    Key pattern: #1 seed almost always picks #2 seed if #2 is significantly
    stronger than the best non-captain (EPA gap > 15).

    Decline modeling (from SPLAT/CHEESE):
    An invited captain may DECLINE if they believe their own alliance
    (as captain) would be competitive. They compare:
      - Accept: join picker's alliance (picker_epa + their_epa)
      - Decline: stay captain and pick best available (their_epa + best_avail_to_them)
    A captain declines when picker_epa < best_available_to_them + decline_margin.
    This means the invited captain thinks they can build a comparable alliance.
    Default decline_margin=5 (conservative — most captains accept).
    """
    teams_db = state["teams"]
    # Initial captains = top 8 by qual rank
    by_rank = sorted(teams_db.values(), key=lambda x: x["qual_rank"])
    initial_captains = [t["team"] for t in by_rank[:8]]
    all_by_rank = [t["team"] for t in by_rank]

    predictions = []
    current_captains = list(initial_captains)
    taken = set()
    decline_margin = 5  # EPA margin — captain declines if picker barely better than their R1

    # Non-captain pool
    non_captains = [t for t in all_by_rank if t not in current_captains]
    non_captains_epa = {t: teams_db[str(t)]["epa"] for t in non_captains}

    for pick_idx in range(len(current_captains)):
        picker = current_captains[pick_idx]
        picker_epa = teams_db[str(picker)]["epa"]

        # Best non-captain available
        avail_nc = [t for t in non_captains if t not in taken]
        best_nc = max(avail_nc, key=lambda t: non_captains_epa.get(t, 0),
                      default=None)
        best_nc_epa = non_captains_epa.get(best_nc, 0) if best_nc else 0

        # Best captain below the picker (could be invited)
        lower_captains = [c for c in current_captains[pick_idx + 1:]
                          if c not in taken]
        best_lower_cap = max(
            lower_captains,
            key=lambda c: teams_db[str(c)]["epa"],
            default=None
        ) if lower_captains else None
        best_lower_epa = teams_db[str(best_lower_cap)]["epa"] if best_lower_cap else 0

        # Decision: pick the captain if they're significantly better
        pick = best_nc
        pick_type = "non-captain"
        declined = False

        if best_lower_cap and best_lower_epa > best_nc_epa + 15:
            # Picker wants to invite the captain. Will they accept?
            # Captain compares: picker's EPA vs best R1 they could pick as captain
            # If picker is weaker than what the captain could get, decline
            cap_best_r1 = max(
                (t for t in avail_nc if t != best_lower_cap),
                key=lambda t: non_captains_epa.get(t, 0),
                default=None
            )
            cap_best_r1_epa = non_captains_epa.get(cap_best_r1, 0) if cap_best_r1 else 0

            if picker_epa < cap_best_r1_epa + decline_margin:
                # Captain declines — picker not strong enough to justify giving up captaincy
                declined = True
                pick = best_nc
                pick_type = "non-captain"
            else:
                pick = best_lower_cap
                pick_type = "captain"

        if pick:
            taken.add(pick)
            pred = {
                "alliance": pick_idx + 1,
                "captain": picker,
                "r1_pick": pick,
                "pick_type": pick_type,
                "pick_epa": teams_db[str(pick)]["epa"],
                "captain_epa": picker_epa,
            }
            if declined:
                pred["declined"] = best_lower_cap
                pred["declined_epa"] = best_lower_epa
                pred["decline_reason"] = (
                    f"{best_lower_cap} declines — as captain can pick "
                    f"{cap_best_r1} (EPA {cap_best_r1_epa:.1f}), "
                    f"picker EPA {picker_epa:.1f} < threshold"
                )
            predictions.append(pred)

            # If a captain was picked, backfill
            if pick_type == "captain":
                current_captains.remove(pick)
                # Next non-captain by rank backfills
                for t in all_by_rank:
                    if t not in current_captains and t not in taken:
                        current_captains.append(t)
                        non_captains.remove(t) if t in non_captains else None
                        break

    return predictions, current_captains


def cmd_predict(args):
    """Predict captain picks and show projected final captains."""
    state = load_state()
    predictions, final_captains = predict_captains(state)

    teams_db = state["teams"]
    by_rank = sorted(teams_db.values(), key=lambda x: x["qual_rank"])
    initial_captains = [t["team"] for t in by_rank[:8]]

    print(f"\n  THE SCOUT — CAPTAIN PREDICTION")
    print(f"  {state['event_key']}")
    print(f"  {'─' * 65}")

    print(f"\n  Initial captains (by qual rank):")
    for i, cap in enumerate(initial_captains, 1):
        td = teams_db[str(cap)]
        print(f"    A{i}: {cap} {td['name'][:20]} (EPA {td['epa']:.1f}, Rank #{td['qual_rank']})")

    print(f"\n  Predicted R1 picks:")
    for p in predictions:
        tag = " ← CAPTAIN PICKED" if p["pick_type"] == "captain" else ""
        print(f"    A{p['alliance']}: {p['captain']} picks {p['r1_pick']} "
              f"(EPA {p['pick_epa']:.1f}){tag}")
        if "declined" in p:
            print(f"      ⚠ {p['decline_reason']}")

    # Show backfill
    changes = [c for c in final_captains if c not in initial_captains]
    removed = [c for c in initial_captains if c not in final_captains]
    if changes:
        print(f"\n  Captain changes:")
        for c in removed:
            td = teams_db[str(c)]
            print(f"    {c} {td['name'][:20]} — PICKED (no longer captain)")
        for c in changes:
            td = teams_db[str(c)]
            print(f"    {c} {td['name'][:20]} — BACKFILL (new captain)")

    print(f"\n  Predicted final captains:")
    for i, cap in enumerate(final_captains[:8], 1):
        td = teams_db[str(cap)]
        our_tag = " ← US" if cap == state["our_team"] else ""
        print(f"    A{i}: {cap} {td['name'][:20]} (EPA {td['epa']:.1f}){our_tag}")

    # What seed would we be?
    our_team = state["our_team"]
    if our_team in final_captains[:8]:
        pred_seed = final_captains[:8].index(our_team) + 1
        curr_seed = state["our_seed"]
        if pred_seed != curr_seed:
            print(f"\n  ⚠ Our predicted seed: Alliance {pred_seed} (currently set to {curr_seed})")
            print(f"    Run: pick_board.py setup {state['event_key']} --team {our_team} --seed {pred_seed}")

    print()


# ─── TBA Match Data Enrichment ───


def cmd_enrich(args):
    """Enrich team data with real match scores from TBA.
    Computes actual SD, hot/cold streaks, and breakdown validation."""
    if not HAS_TBA:
        print("  ERROR: TBA client not available. Check tba_client.py")
        return

    state = load_state()
    event_key = state["event_key"]

    print(f"\n  THE SCOUT — TBA MATCH DATA ENRICHMENT")
    print(f"  Event: {event_key}")
    print(f"  {'─' * 60}")
    print(f"  Fetching match data from TBA...")

    try:
        matches = event_matches(event_key)
    except Exception as e:
        print(f"  ERROR: {e}")
        print(f"  Make sure TBA API key is set in scout/.tba_key")
        return

    quals = [m for m in matches if m.get("comp_level") == "qm"]
    elims = [m for m in matches if m.get("comp_level") != "qm"]

    print(f"  {len(matches)} matches ({len(quals)} quals, {len(elims)} elims)")

    # Compute real scores per team from match data
    team_scores = {}  # team -> [scores]
    team_breakdowns = {}  # team -> [breakdown_dicts]

    for m in quals:
        alliances = m.get("alliances", {})
        breakdown = m.get("score_breakdown", {})

        for color in ("red", "blue"):
            score = alliances.get(color, {}).get("score", 0)
            team_keys = alliances.get(color, {}).get("team_keys", [])
            bd = breakdown.get(color, {})

            for tk in team_keys:
                team_num = int(tk.replace("frc", ""))
                if str(team_num) not in state["teams"]:
                    continue
                if team_num not in team_scores:
                    team_scores[team_num] = []
                    team_breakdowns[team_num] = []
                team_scores[team_num].append(score)
                team_breakdowns[team_num].append(bd)

    # Compute real SD and streaks for each team
    enriched = 0
    for team_num, scores in team_scores.items():
        key = str(team_num)
        if key not in state["teams"]:
            continue

        n = len(scores)
        if n < 3:
            continue

        avg = sum(scores) / n
        variance = sum((s - avg) ** 2 for s in scores) / n
        real_sd = math.sqrt(variance) / 3  # per-robot SD (alliance score / 3 robots)

        # Detect hot/cold streaks (last 3 matches)
        recent = scores[-3:]
        recent_avg = sum(recent) / len(recent)
        streak = ""
        if recent_avg > avg * 1.15:
            streak = "HOT"
        elif recent_avg < avg * 0.85:
            streak = "COLD"

        # Update state
        state["teams"][key]["real_sd"] = round(real_sd, 1)
        state["teams"][key]["real_avg_score"] = round(avg, 1)
        state["teams"][key]["streak"] = streak
        state["teams"][key]["match_count"] = n
        enriched += 1

    save_state(state)

    # Display enrichment results
    print(f"  Enriched {enriched} teams with real match data\n")

    # Show teams with notable streaks or SD discrepancies
    print(f"  {'Team':>6} {'Name':>20} {'EPA':>6} {'RealAvg':>8} {'EPA_SD':>7} {'RealSD':>7} {'Streak':>7}")
    print(f"  {'─' * 70}")

    notable = []
    for key, td in state["teams"].items():
        if "real_sd" not in td:
            continue
        epa_sd = td.get("sd", 0)
        real_sd = td.get("real_sd", 0)
        streak = td.get("streak", "")

        # Flag if real SD differs significantly from EPA SD, or has streak
        sd_diff = abs(real_sd - epa_sd)
        if sd_diff > 5 or streak:
            notable.append(td)

    notable.sort(key=lambda x: x["epa"], reverse=True)
    for td in notable[:15]:
        streak_tag = td.get("streak", "")
        print(f"  {td['team']:6d} {td['name'][:20]:>20} {td['epa']:6.1f} "
              f"{td.get('real_avg_score', 0):8.1f} {td['sd']:7.1f} "
              f"{td.get('real_sd', 0):7.1f} {streak_tag:>7}")

    # Also try to validate against actual alliances from TBA
    try:
        tba_als = tba_alliances(event_key)
        if tba_als:
            print(f"\n  TBA ALLIANCE VALIDATION:")
            for i, a in enumerate(tba_als, 1):
                picks = [p.replace("frc", "") for p in a.get("picks", [])]
                print(f"    A{i}: {picks}")
    except Exception:
        pass

    print()


# ─── Main ───


def cmd_dnp(args):
    """Toggle Do Not Pick for a team. Excludes them from recommendations."""
    if not args:
        state = load_state()
        dnp = state.get("dnp", [])
        if not dnp:
            print("\n  No teams on DNP list.")
            print("  Usage: pick_board.py dnp <team#>  (toggles on/off)\n")
            return
        teams_db = state["teams"]
        print(f"\n  DO NOT PICK LIST ({len(dnp)} teams):")
        for t in dnp:
            td = teams_db.get(str(t), {})
            name = td.get("name", "?")[:25]
            epa = td.get("epa", 0)
            print(f"    {t:5d}  {name}  (EPA {epa:.1f})")
        print(f"\n  To remove: pick_board.py dnp <team#>\n")
        return

    team = int(args[0])
    state = load_state()

    if str(team) not in state["teams"]:
        print(f"  ERROR: Team {team} not found at event")
        return

    dnp = state.get("dnp", [])
    td = state["teams"][str(team)]
    if team in dnp:
        dnp.remove(team)
        state["dnp"] = dnp
        save_state(state)
        print(f"  ✓ Removed {team} {td['name']} from DNP list")
    else:
        dnp.append(team)
        state["dnp"] = dnp
        save_state(state)
        print(f"  ✓ Added {team} {td['name']} to DNP list — excluded from recommendations")


def cmd_dp(args):
    """Project district ranking points from playoff simulation."""
    state = load_state()
    alliances = get_alliances(state)
    teams_db = state["teams"]
    n_cap = len(state["captains"])
    n_sims = 10000

    for a in args:
        if a.startswith("--sims"):
            continue
        if a.isdigit():
            n_sims = int(a)

    # QF matchups: 1v8, 2v7, 3v6, 4v5
    matchups = [(1, n_cap), (2, n_cap - 1), (3, n_cap - 2), (4, n_cap - 3)]

    random.seed(42)

    # Simulate full bracket: QF → SF → F
    # Track match wins per alliance across all sims
    alliance_match_wins = {i: 0.0 for i in range(1, n_cap + 1)}
    alliance_series_record = {i: {"qf_w": 0, "sf_w": 0, "f_w": 0} for i in range(1, n_cap + 1)}

    for _ in range(n_sims):
        # QF
        qf_winners = []
        for a, b in matchups:
            a_teams = alliances.get(a, [])
            b_teams = alliances.get(b, [])
            a_mw, b_mw = 0, 0
            for _ in range(3):
                a_score = sum(
                    max(0, random.gauss(
                        teams_db.get(str(t), {}).get("epa", 0),
                        teams_db.get(str(t), {}).get("sd", 10)
                    )) for t in a_teams
                )
                b_score = sum(
                    max(0, random.gauss(
                        teams_db.get(str(t), {}).get("epa", 0),
                        teams_db.get(str(t), {}).get("sd", 10)
                    )) for t in b_teams
                )
                if a_score > b_score:
                    a_mw += 1
                else:
                    b_mw += 1
            alliance_match_wins[a] += a_mw
            alliance_match_wins[b] += b_mw
            if a_mw >= 2:
                qf_winners.append(a)
                alliance_series_record[a]["qf_w"] += 1
            else:
                qf_winners.append(b)
                alliance_series_record[b]["qf_w"] += 1

        # SF: QF1 winner vs QF2 winner, QF3 winner vs QF4 winner
        sf_winners = []
        for i in range(0, 4, 2):
            a, b = qf_winners[i], qf_winners[i + 1]
            a_teams = alliances.get(a, [])
            b_teams = alliances.get(b, [])
            a_mw, b_mw = 0, 0
            for _ in range(3):
                a_score = sum(
                    max(0, random.gauss(
                        teams_db.get(str(t), {}).get("epa", 0),
                        teams_db.get(str(t), {}).get("sd", 10)
                    )) for t in a_teams
                )
                b_score = sum(
                    max(0, random.gauss(
                        teams_db.get(str(t), {}).get("epa", 0),
                        teams_db.get(str(t), {}).get("sd", 10)
                    )) for t in b_teams
                )
                if a_score > b_score:
                    a_mw += 1
                else:
                    b_mw += 1
            alliance_match_wins[a] += a_mw
            alliance_match_wins[b] += b_mw
            if a_mw >= 2:
                sf_winners.append(a)
                alliance_series_record[a]["sf_w"] += 1
            else:
                sf_winners.append(b)
                alliance_series_record[b]["sf_w"] += 1

        # Finals
        a, b = sf_winners[0], sf_winners[1]
        a_teams = alliances.get(a, [])
        b_teams = alliances.get(b, [])
        a_mw, b_mw = 0, 0
        for _ in range(3):
            a_score = sum(
                max(0, random.gauss(
                    teams_db.get(str(t), {}).get("epa", 0),
                    teams_db.get(str(t), {}).get("sd", 10)
                )) for t in a_teams
            )
            b_score = sum(
                max(0, random.gauss(
                    teams_db.get(str(t), {}).get("epa", 0),
                    teams_db.get(str(t), {}).get("sd", 10)
                )) for t in b_teams
            )
            if a_score > b_score:
                a_mw += 1
            else:
                b_mw += 1
        alliance_match_wins[a] += a_mw
        alliance_match_wins[b] += b_mw
        if a_mw >= 2:
            alliance_series_record[a]["f_w"] += 1
        else:
            alliance_series_record[b]["f_w"] += 1

    # District points model (FRC 2024+ districts):
    # Alliance selection: 16 - (seed-1) for captains, 17 - pick_order for picks
    #   Simplified: captain gets 16-seed+1, R1 pick gets ~same range
    # Playoff match wins: 5 pts each
    # Advancing: QF win +0 extra, SF win +0 extra, Finals win +0 extra
    #   (points come purely from match wins in districts)
    print(f"\n  DISTRICT POINT PROJECTION ({n_sims:,} sims)")
    print(f"  {'─' * 70}")
    print(f"  {'Alliance':>10s}  {'Avg MW':>7s}  {'QF%':>6s}  {'SF%':>6s}  {'Win%':>6s}  {'Playoff DP':>10s}  {'Total DP':>10s}")
    print(f"  {'─' * 70}")

    our_seed = state["our_seed"]
    for seed in range(1, n_cap + 1):
        avg_mw = alliance_match_wins[seed] / n_sims
        rec = alliance_series_record[seed]
        qf_pct = rec["qf_w"] / n_sims * 100
        sf_pct = rec["sf_w"] / n_sims * 100
        f_pct = rec["f_w"] / n_sims * 100

        # Alliance selection points (captain + R1 pick share)
        # Captain: 17 - seed, R1 pick: 17 - (seed + 8) roughly
        allsel_pts = 17 - seed

        # Playoff match win points: 5 per match win
        playoff_dp = avg_mw * 5.0

        # Total = alliance selection + playoff
        total_dp = allsel_pts + playoff_dp

        tag = " ← US" if seed == our_seed else ""
        members = alliances.get(seed, [])
        member_str = ",".join(str(t) for t in members[:3])

        print(f"  A{seed:1d} {member_str:>18s}  {avg_mw:6.1f}  {qf_pct:5.1f}%  {sf_pct:5.1f}%  {f_pct:5.1f}%  "
              f"{playoff_dp:9.1f}  {total_dp:9.1f}{tag}")

    print(f"\n  DP = Alliance Selection pts (17 - seed) + Playoff Match Wins (5 pts/win)")
    print(f"  Note: Actual district points also include qual ranking pts (not shown)\n")


COMMANDS = {
    "setup":     ("Initialize draft board from event data", cmd_setup),
    "pick":      ("Record a pick: pick <alliance#> <team#>", cmd_pick),
    "board":     ("Show full pick board with projections", cmd_board),
    "rec":       ("Show pick recommendation (with complementarity)", cmd_rec),
    "undo":      ("Undo last pick", cmd_undo),
    "alliances": ("Show current alliances", cmd_alliances),
    "sim":       ("Monte Carlo playoff simulation", cmd_sim),
    "predict":   ("Predict captain picks + backfill before lunch", cmd_predict),
    "enrich":    ("Enrich data with real TBA match scores", cmd_enrich),
    "dnp":       ("Toggle Do Not Pick for a team", cmd_dnp),
    "dp":        ("Project district ranking points from playoffs", cmd_dp),
}


def main():
    print(f"\n  THE SCOUT — LIVE PICK BOARD")
    print(f"  Team 2950 The Devastators\n")

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("  Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"    {name:12s}  {desc}")
        print()
        print("  Workflow:")
        print("    1. Before alliance selection:")
        print("       python3 pick_board.py setup 2026txbel --team 2881 --seed 3")
        print()
        print("    2. During draft (students call out picks):")
        print("       python3 pick_board.py pick 1 148")
        print("       python3 pick_board.py pick 2 624")
        print("       python3 pick_board.py board     # see updated board")
        print("       python3 pick_board.py rec       # when it's your turn")
        print()
        print("    3. After draft:")
        print("       python3 pick_board.py alliances")
        print("       python3 pick_board.py sim --sims 10000")
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
