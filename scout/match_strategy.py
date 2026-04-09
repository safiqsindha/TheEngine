#!/usr/bin/env python3
"""
The Engine — Match Strategy Generator
Team 2950 — The Devastators

Generates pre-match strategy briefs for upcoming qualification and playoff matches.
Combines EPA data, EYE scouting observations, and opponent analysis into
actionable game plans.

What this provides that EPA alone can't:
  - Opponent-specific counter-strategies (who to defend, who to ignore)
  - Scoring zone priorities (where to focus based on alliance composition)
  - Auto coordination (who goes where, avoid collisions)
  - Endgame sequencing (who climbs first, barge priority)
  - Risk flags (unreliable mechanisms, hot/cold streaks, penalty-prone teams)

Usage:
  # Strategy for a specific match
  python3 match_strategy.py match <event_key> <match_key> --team 2950

  # Strategy for next upcoming match (uses TBA schedule)
  python3 match_strategy.py next <event_key> --team 2950

  # Quick opponent report
  python3 match_strategy.py opponent <event_key> --teams 4364,9311,10032

  # Alliance synergy analysis (what's our best scoring plan?)
  python3 match_strategy.py synergy <event_key> --alliance 2950,7521,3035
"""

import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

SCOUT_DIR = Path(__file__).parent
STATE_DIR = SCOUT_DIR / ".state"
EYE_RESULTS_DIR = Path(__file__).parent.parent / "eye" / ".cache" / "results"

try:
    from statbotics_client import get_event_teams
    HAS_STATBOTICS = True
except ImportError:
    HAS_STATBOTICS = False

try:
    from tba_client import (event_matches, event_rankings, team_event_matches,
                            team_key as make_team_key)
    HAS_TBA = True
except ImportError:
    HAS_TBA = False


# ─── Data Loading ───


def load_teams_db(event_key: str) -> dict:
    """Load team EPA data for an event. Tries draft state first, then API."""
    state_file = STATE_DIR / "draft_state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state.get("event_key") == event_key and state.get("teams"):
            return state["teams"]

    if not HAS_STATBOTICS:
        print("  ERROR: No draft state and statbotics_client not available")
        return {}

    raw = get_event_teams(event_key)
    if not raw:
        return {}

    teams_db = {}
    for t in raw:
        epa = t.get("epa", {})
        bd = epa.get("breakdown", {})
        sd = epa.get("total_points", {}).get("sd", 0) or 0
        mean = epa.get("total_points", {}).get("mean", 0) or 0
        teams_db[str(t.get("team", 0))] = {
            "team": t.get("team", 0),
            "name": t.get("team_name", ""),
            "epa": mean,
            "sd": sd,
            "floor": mean - 1.5 * sd,
            "ceiling": mean + 1.5 * sd,
            "epa_auto": bd.get("auto_points", 0) or 0,
            "epa_teleop": bd.get("teleop_points", 0) or 0,
            "epa_endgame": bd.get("endgame_points", 0) or 0,
            "total_fuel": bd.get("total_fuel", bd.get("teleop_points", 0)) or 0,
            "total_tower": bd.get("total_tower", 0) or 0,
            "auto_fuel": bd.get("auto_fuel", 0) or 0,
            "auto_tower": bd.get("auto_tower", 0) or 0,
            "first_shift": bd.get("first_shift_fuel", 0) or 0,
            "second_shift": bd.get("second_shift_fuel", 0) or 0,
            "endgame_fuel": bd.get("endgame_fuel", 0) or 0,
            "endgame_tower": bd.get("endgame_tower", 0) or 0,
        }
    return teams_db


def load_eye_data(team_num: int) -> dict:
    """Load EYE scouting data for a team from cached reports."""
    if not EYE_RESULTS_DIR.exists():
        return {}

    observations = []
    for f in EYE_RESULTS_DIR.glob("*_report.json"):
        try:
            data = json.loads(f.read_text())
            teams = data.get("teams", {})
            if str(team_num) in teams:
                observations.append(teams[str(team_num)])
        except (json.JSONDecodeError, KeyError):
            continue

    if not observations:
        return {}

    # Extract key qualitative data
    result = {"matches_scouted": len(observations)}

    # Aggregate mechanism issues
    issues = []
    for obs in observations:
        mechs = obs.get("mechanism_observations", {})
        if isinstance(mechs, dict):
            issue = mechs.get("issues", "")
            if issue and issue.lower() not in ("none", "none observed", "no issues"):
                issues.append(issue)

    result["mechanism_issues"] = issues

    # Aggregate defense notes
    defense_notes = []
    for obs in observations:
        defense = obs.get("defense", {})
        if isinstance(defense, dict):
            if defense.get("played_defense"):
                defense_notes.append(f"played defense: {defense.get('notes', '')}")
            if defense.get("received_defense"):
                defense_notes.append(f"received defense: {defense.get('notes', '')}")

    result["defense_notes"] = defense_notes

    # Overall assessments
    overalls = [obs.get("overall", "") for obs in observations if obs.get("overall")]
    result["overall_assessments"] = overalls

    # Cycle speed observations
    speeds = []
    for obs in observations:
        teleop = obs.get("teleop", {})
        if isinstance(teleop, dict) and teleop.get("cycle_speed"):
            speeds.append(teleop["cycle_speed"])
    result["cycle_speeds"] = speeds

    # Endgame observations
    endgames = []
    for obs in observations:
        eg = obs.get("endgame", {})
        if isinstance(eg, dict):
            endgames.append({
                "attempted": eg.get("climb_attempted", False),
                "notes": eg.get("notes", ""),
            })
    result["endgame_obs"] = endgames

    # Pull numeric scores from draft state if available
    state_file = STATE_DIR / "draft_state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        td = state.get("teams", {}).get(str(team_num), {})
        if td.get("eye_composite"):
            result["eye_composite"] = td["eye_composite"]
            result["eye_reliability"] = td.get("eye_reliability", 0)
            result["eye_driver"] = td.get("eye_driver", 0)

    return result


def get_match_teams(event_key: str, match_key: str) -> dict:
    """Get red/blue team lists for a specific match from TBA."""
    if not HAS_TBA:
        return {}

    matches = event_matches(event_key)
    for m in matches:
        if m.get("key") == match_key:
            alliances = m.get("alliances", {})
            red = [int(t.replace("frc", "")) for t in
                   alliances.get("red", {}).get("team_keys", [])]
            blue = [int(t.replace("frc", "")) for t in
                    alliances.get("blue", {}).get("team_keys", [])]
            return {"red": red, "blue": blue,
                    "comp_level": m.get("comp_level", "qm"),
                    "match_number": m.get("match_number", 0)}
    return {}


def find_next_match(event_key: str, our_team: int) -> dict:
    """Find the next unplayed match for our team."""
    if not HAS_TBA:
        return {}

    matches = event_matches(event_key)
    # Sort by match order
    quals = [m for m in matches if m.get("comp_level") == "qm"]
    quals.sort(key=lambda m: m.get("match_number", 0))

    for m in quals:
        if m.get("winning_alliance"):
            continue  # Already played
        alliances = m.get("alliances", {})
        all_teams = []
        for color in ("red", "blue"):
            all_teams.extend(
                int(t.replace("frc", ""))
                for t in alliances.get(color, {}).get("team_keys", [])
            )
        if our_team in all_teams:
            return {
                "match_key": m["key"],
                "match_number": m.get("match_number", 0),
                "comp_level": m.get("comp_level", "qm"),
            }
    return {}


# ─── Strategy Analysis ───


def analyze_alliance(teams_db: dict, team_nums: list) -> dict:
    """Analyze an alliance's combined strengths and weaknesses."""
    profile = {
        "teams": team_nums,
        "total_epa": 0,
        "total_floor": 0,
        "total_ceiling": 0,
        "auto_epa": 0,
        "teleop_epa": 0,
        "endgame_epa": 0,
        "fuel_total": 0,
        "tower_total": 0,
        "strengths": [],
        "weaknesses": [],
        "team_details": [],
    }

    for t in team_nums:
        td = teams_db.get(str(t), {})
        epa = td.get("epa", 0)
        profile["total_epa"] += epa
        profile["total_floor"] += td.get("floor", 0)
        profile["total_ceiling"] += td.get("ceiling", 0)
        profile["auto_epa"] += td.get("epa_auto", 0)
        profile["teleop_epa"] += td.get("epa_teleop", 0)
        profile["endgame_epa"] += td.get("epa_endgame", 0)
        profile["fuel_total"] += td.get("total_fuel", 0)
        profile["tower_total"] += td.get("total_tower", 0)

        # Per-team detail
        eye = load_eye_data(t)
        detail = {
            "team": t,
            "name": td.get("name", "?"),
            "epa": epa,
            "role": _classify_role(td),
            "eye": eye if eye else None,
        }
        profile["team_details"].append(detail)

    # Identify strengths/weaknesses
    if profile["auto_epa"] > 30:
        profile["strengths"].append("Strong auto")
    elif profile["auto_epa"] < 15:
        profile["weaknesses"].append("Weak auto")

    if profile["endgame_epa"] > 20:
        profile["strengths"].append("Strong endgame")
    elif profile["endgame_epa"] < 8:
        profile["weaknesses"].append("Weak endgame")

    if profile["tower_total"] > 5:
        profile["strengths"].append("Tower capability")
    elif profile["tower_total"] < 1:
        profile["weaknesses"].append("No tower scoring")

    if profile["fuel_total"] > 40:
        profile["strengths"].append("High fuel output")

    # Check for high variance (unreliable alliance)
    total_sd = sum(teams_db.get(str(t), {}).get("sd", 0) for t in team_nums)
    if total_sd > profile["total_epa"] * 0.3:
        profile["weaknesses"].append("High variance — inconsistent")

    return profile


def _classify_role(td: dict) -> str:
    """Classify a team's primary role from their EPA breakdown."""
    fuel = td.get("total_fuel", 0)
    tower = td.get("total_tower", 0)
    endgame = td.get("epa_endgame", 0)
    auto = td.get("epa_auto", 0)

    if tower > fuel * 0.5 and tower > 2:
        return "tower-scorer"
    if endgame > 10:
        if fuel > 15:
            return "all-rounder"
        return "endgame-specialist"
    if auto > 12:
        return "auto-strong"
    if fuel > 15:
        return "fuel-cycler"
    return "support"


def simulate_match(us_teams: list, them_teams: list, teams_db: dict,
                   n_sims: int = 5000) -> dict:
    """Simulate a match and return detailed outcome stats."""
    random.seed(42)
    us_wins = 0
    us_scores = []
    them_scores = []
    margins = []

    for _ in range(n_sims):
        us_total = sum(
            max(0, random.gauss(
                teams_db.get(str(t), {}).get("epa", 0),
                teams_db.get(str(t), {}).get("sd", 10)
            )) for t in us_teams
        )
        them_total = sum(
            max(0, random.gauss(
                teams_db.get(str(t), {}).get("epa", 0),
                teams_db.get(str(t), {}).get("sd", 10)
            )) for t in them_teams
        )
        us_scores.append(us_total)
        them_scores.append(them_total)
        margins.append(us_total - them_total)
        if us_total > them_total:
            us_wins += 1

    return {
        "win_pct": us_wins / n_sims,
        "us_avg": sum(us_scores) / n_sims,
        "them_avg": sum(them_scores) / n_sims,
        "avg_margin": sum(margins) / n_sims,
        "blowout_pct": sum(1 for m in margins if m > 30) / n_sims,
        "upset_pct": sum(1 for m in margins if m < -20) / n_sims,
    }


def generate_strategy(our_team: int, our_alliance: list,
                      opp_alliance: list, teams_db: dict,
                      match_info: dict = None) -> dict:
    """Generate a complete match strategy brief."""
    us = analyze_alliance(teams_db, our_alliance)
    them = analyze_alliance(teams_db, opp_alliance)
    sim = simulate_match(our_alliance, opp_alliance, teams_db)

    strategy = {
        "match": match_info or {},
        "our_team": our_team,
        "prediction": sim,
        "our_alliance": us,
        "opponent": them,
        "game_plan": {},
        "risk_flags": [],
        "key_insight": "",
    }

    # ── Determine scoring priority ──
    game_plan = {}

    # Auto plan
    auto_robots = sorted(us["team_details"],
                         key=lambda x: teams_db.get(str(x["team"]), {}).get("epa_auto", 0),
                         reverse=True)
    game_plan["auto"] = {
        "primary_scorer": auto_robots[0]["team"] if auto_robots else None,
        "notes": [],
    }
    if us["auto_epa"] > them["auto_epa"] * 1.2:
        game_plan["auto"]["notes"].append("We have auto advantage — be aggressive")
    elif us["auto_epa"] < them["auto_epa"] * 0.8:
        game_plan["auto"]["notes"].append("They have auto advantage — focus on clean execution, no collisions")

    # Teleop plan — figure out who does what
    game_plan["teleop"] = {"assignments": [], "notes": []}
    for detail in us["team_details"]:
        td = teams_db.get(str(detail["team"]), {})
        assignment = {
            "team": detail["team"],
            "role": detail["role"],
            "primary_task": "fuel cycling" if detail["role"] in ("fuel-cycler", "all-rounder", "auto-strong") else
                           "tower scoring" if detail["role"] == "tower-scorer" else
                           "support scoring",
        }
        game_plan["teleop"]["assignments"].append(assignment)

    # Defense decision
    game_plan["defense"] = _defense_decision(us, them, teams_db, sim)

    # Endgame sequencing
    endgame_order = sorted(us["team_details"],
                           key=lambda x: teams_db.get(str(x["team"]), {}).get("epa_endgame", 0),
                           reverse=True)
    game_plan["endgame"] = {
        "sequence": [d["team"] for d in endgame_order],
        "notes": [],
    }
    if us["endgame_epa"] > 20:
        game_plan["endgame"]["notes"].append("Strong endgame — start early for clean execution")
    elif us["endgame_epa"] < 8:
        game_plan["endgame"]["notes"].append("Weak endgame — maximize teleop scoring time instead")

    strategy["game_plan"] = game_plan

    # ── Risk flags ──
    for detail in us["team_details"]:
        eye = detail.get("eye")
        if eye:
            if eye.get("mechanism_issues"):
                strategy["risk_flags"].append(
                    f"{detail['team']}: mechanism issues observed — {eye['mechanism_issues'][0]}"
                )
            if eye.get("eye_reliability", 100) < 50:
                strategy["risk_flags"].append(
                    f"{detail['team']}: low reliability score ({eye['eye_reliability']:.0f}/100)")

        td = teams_db.get(str(detail["team"]), {})
        if td.get("streak") == "COLD":
            strategy["risk_flags"].append(f"{detail['team']}: on a COLD streak")
        if td.get("sd", 0) > td.get("epa", 0) * 0.4:
            strategy["risk_flags"].append(f"{detail['team']}: high variance (SD={td['sd']:.1f})")

    # For opponents too
    for detail in them["team_details"]:
        eye = detail.get("eye")
        if eye and eye.get("mechanism_issues"):
            strategy["risk_flags"].append(
                f"OPP {detail['team']}: has mechanism issues — may underperform"
            )

    # ── Key insight ──
    if sim["win_pct"] > 0.75:
        strategy["key_insight"] = (
            f"Strong favorite ({sim['win_pct']*100:.0f}%). "
            f"Play clean, maximize scoring, don't take risks."
        )
    elif sim["win_pct"] > 0.55:
        strategy["key_insight"] = (
            f"Slight favorite ({sim['win_pct']*100:.0f}%). "
            f"Execute the game plan — {'defend their best scorer' if game_plan['defense'].get('target') else 'outscore them'}."
        )
    elif sim["win_pct"] > 0.45:
        strategy["key_insight"] = (
            f"Toss-up match ({sim['win_pct']*100:.0f}%). "
            f"This is winnable but requires perfect execution. "
            f"Focus on {'our strengths: ' + ', '.join(us['strengths'][:2]) if us['strengths'] else 'minimizing errors'}."
        )
    else:
        strategy["key_insight"] = (
            f"Underdog ({sim['win_pct']*100:.0f}%). "
            f"Need their weak link to underperform or our ceiling games. "
            f"{'Play defense on ' + str(game_plan['defense'].get('target', '?')) if game_plan['defense'].get('play_defense') else 'All-out scoring is our best shot'}."
        )

    return strategy


def _defense_decision(us: dict, them: dict, teams_db: dict,
                      sim: dict) -> dict:
    """Decide whether to play defense and on whom."""
    result = {"play_defense": False, "target": None, "defender": None, "notes": []}

    # Find opponent's best scorer
    opp_sorted = sorted(them["team_details"],
                        key=lambda x: teams_db.get(str(x["team"]), {}).get("epa", 0),
                        reverse=True)

    if not opp_sorted:
        return result

    best_opp = opp_sorted[0]
    best_opp_epa = teams_db.get(str(best_opp["team"]), {}).get("epa", 0)
    second_opp_epa = (teams_db.get(str(opp_sorted[1]["team"]), {}).get("epa", 0)
                      if len(opp_sorted) > 1 else 0)

    # Defense is worth it if:
    # 1. Their best scorer is significantly better than their second
    # 2. We're the underdog (defense can equalize)
    # 3. We have a robot better suited to defense than scoring

    epa_gap = best_opp_epa - second_opp_epa
    our_weakest = min(us["team_details"],
                      key=lambda x: teams_db.get(str(x["team"]), {}).get("epa", 0))
    our_weakest_epa = teams_db.get(str(our_weakest["team"]), {}).get("epa", 0)

    # Check if our weakest robot's scoring contribution < disruption value
    # Rule of thumb: defense can reduce a robot's output by ~40-60%
    defense_value = best_opp_epa * 0.4  # estimated points prevented
    scoring_loss = our_weakest_epa  # points we lose by not scoring

    should_defend = (
        defense_value > scoring_loss * 1.2 and  # defense worth more than scoring
        epa_gap > 8 and  # their best is clearly better than their second
        sim["win_pct"] < 0.65  # we're not already dominant
    )

    if should_defend:
        result["play_defense"] = True
        result["target"] = best_opp["team"]
        result["defender"] = our_weakest["team"]
        result["notes"].append(
            f"Send {our_weakest['team']} to defend {best_opp['team']} "
            f"(their EPA {best_opp_epa:.0f}, defense value ~{defense_value:.0f} > "
            f"scoring loss ~{scoring_loss:.0f})")

        # Check EYE data for defense-specific info
        eye = load_eye_data(best_opp["team"])
        if eye and eye.get("defense_notes"):
            result["notes"].append(f"EYE: {eye['defense_notes'][0]}")
    else:
        result["notes"].append("All-out scoring is the better strategy")
        if epa_gap < 5:
            result["notes"].append("Opponent scoring is spread evenly — no clear defense target")
        if sim["win_pct"] > 0.65:
            result["notes"].append("We're favored — no need to risk defense")

    return result


# ─── Display ───


def print_strategy(strategy: dict):
    """Pretty-print a match strategy brief."""
    match = strategy.get("match", {})
    pred = strategy.get("prediction", {})
    plan = strategy.get("game_plan", {})
    us = strategy.get("our_alliance", {})
    them = strategy.get("opponent", {})

    match_label = f"{match.get('comp_level', 'qm').upper()} {match.get('match_number', '?')}"

    print(f"\n  THE ENGINE — MATCH STRATEGY BRIEF")
    print(f"  {'═' * 65}")
    if match:
        print(f"  Match: {match_label}")
    print(f"  Our team: {strategy.get('our_team', '?')}")
    print()

    # ── Prediction ──
    win_pct = pred.get("win_pct", 0) * 100
    bar_len = int(win_pct / 5)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    print(f"  PREDICTION: {win_pct:.0f}% win  [{bar}]")
    print(f"  Expected score: {pred.get('us_avg', 0):.0f} — {pred.get('them_avg', 0):.0f} "
          f"(margin {pred.get('avg_margin', 0):+.0f})")
    print()

    # ── Key Insight ──
    if strategy.get("key_insight"):
        print(f"  KEY: {strategy['key_insight']}")
        print()

    # ── Alliance Overview ──
    our_color = "?"
    our_teams = us.get("teams", [])
    opp_teams = them.get("teams", [])
    # Determine color from match data
    match_data = strategy.get("match", {})
    if match_data.get("red") and strategy["our_team"] in match_data["red"]:
        our_color = "RED"
    elif match_data.get("blue") and strategy["our_team"] in match_data["blue"]:
        our_color = "BLUE"

    print(f"  OUR ALLIANCE ({our_color}):")
    for detail in us.get("team_details", []):
        td_epa = detail.get("epa", 0)
        role = detail.get("role", "?")
        eye_tag = ""
        if detail.get("eye"):
            comp = detail["eye"].get("eye_composite", 0)
            if comp > 75:
                eye_tag = " [EYE: elite]"
            elif comp > 55:
                eye_tag = " [EYE: solid]"
            elif comp < 40:
                eye_tag = " [EYE: concern]"
        me = " ← US" if detail["team"] == strategy["our_team"] else ""
        print(f"    {detail['team']} {detail.get('name', '')[:20]:20s} EPA {td_epa:5.1f}  {role}{eye_tag}{me}")

    print(f"    Combined: EPA {us.get('total_epa', 0):.0f} | "
          f"Auto {us.get('auto_epa', 0):.0f} | Teleop {us.get('teleop_epa', 0):.0f} | "
          f"Endgame {us.get('endgame_epa', 0):.0f}")
    if us.get("strengths"):
        print(f"    Strengths: {', '.join(us['strengths'])}")
    if us.get("weaknesses"):
        print(f"    Weaknesses: {', '.join(us['weaknesses'])}")

    print()
    print(f"  OPPONENT:")
    for detail in them.get("team_details", []):
        td_epa = detail.get("epa", 0)
        role = detail.get("role", "?")
        eye_tag = ""
        if detail.get("eye") and detail["eye"].get("mechanism_issues"):
            eye_tag = " [EYE: mech issues!]"
        print(f"    {detail['team']} {detail.get('name', '')[:20]:20s} EPA {td_epa:5.1f}  {role}{eye_tag}")

    print(f"    Combined: EPA {them.get('total_epa', 0):.0f} | "
          f"Auto {them.get('auto_epa', 0):.0f} | Teleop {them.get('teleop_epa', 0):.0f} | "
          f"Endgame {them.get('endgame_epa', 0):.0f}")
    if them.get("weaknesses"):
        print(f"    Weaknesses: {', '.join(them['weaknesses'])}")

    # ── Game Plan ──
    print(f"\n  {'─' * 65}")
    print(f"  GAME PLAN")
    print(f"  {'─' * 65}")

    # Auto
    auto = plan.get("auto", {})
    if auto:
        print(f"\n  AUTO:")
        if auto.get("primary_scorer"):
            print(f"    Primary scorer: {auto['primary_scorer']}")
        for note in auto.get("notes", []):
            print(f"    • {note}")

    # Teleop
    teleop = plan.get("teleop", {})
    if teleop:
        print(f"\n  TELEOP:")
        for a in teleop.get("assignments", []):
            print(f"    {a['team']}: {a['primary_task']} ({a['role']})")
        for note in teleop.get("notes", []):
            print(f"    • {note}")

    # Defense
    defense = plan.get("defense", {})
    if defense:
        print(f"\n  DEFENSE:")
        if defense.get("play_defense"):
            print(f"    ★ PLAY DEFENSE: {defense['defender']} → defend {defense['target']}")
        for note in defense.get("notes", []):
            print(f"    • {note}")

    # Endgame
    endgame = plan.get("endgame", {})
    if endgame:
        print(f"\n  ENDGAME:")
        seq = endgame.get("sequence", [])
        if seq:
            print(f"    Sequence: {' → '.join(str(t) for t in seq)}")
        for note in endgame.get("notes", []):
            print(f"    • {note}")

    # ── Risk Flags ──
    risks = strategy.get("risk_flags", [])
    if risks:
        print(f"\n  {'─' * 65}")
        print(f"  RISK FLAGS:")
        for r in risks:
            print(f"    ⚠ {r}")

    print(f"\n  {'═' * 65}\n")


# ─── Commands ───


def cmd_match(args):
    """Generate strategy for a specific match."""
    if len(args) < 2:
        print("Usage: match_strategy.py match <event_key> <match_key> --team 2950")
        return

    event_key = args[0]
    match_key = args[1]
    our_team = None

    i = 2
    while i < len(args):
        if args[i] == "--team" and i + 1 < len(args):
            our_team = int(args[i + 1]); i += 2
        else:
            i += 1

    if not our_team:
        print("  --team is required")
        return

    teams_db = load_teams_db(event_key)
    if not teams_db:
        print(f"  No team data for {event_key}")
        return

    match_teams = get_match_teams(event_key, match_key)
    if not match_teams:
        print(f"  Match {match_key} not found")
        return

    # Determine our alliance
    if our_team in match_teams.get("red", []):
        our_alliance = match_teams["red"]
        opp_alliance = match_teams["blue"]
    elif our_team in match_teams.get("blue", []):
        our_alliance = match_teams["blue"]
        opp_alliance = match_teams["red"]
    else:
        print(f"  Team {our_team} not in match {match_key}")
        return

    match_info = {
        "match_key": match_key,
        "comp_level": match_teams.get("comp_level", "qm"),
        "match_number": match_teams.get("match_number", 0),
        "red": match_teams["red"],
        "blue": match_teams["blue"],
    }

    strategy = generate_strategy(our_team, our_alliance, opp_alliance,
                                 teams_db, match_info)
    print_strategy(strategy)
    return strategy


def cmd_next(args):
    """Generate strategy for the next upcoming match."""
    if not args:
        print("Usage: match_strategy.py next <event_key> --team 2950")
        return

    event_key = args[0]
    our_team = None
    i = 1
    while i < len(args):
        if args[i] == "--team" and i + 1 < len(args):
            our_team = int(args[i + 1]); i += 2
        else:
            i += 1

    if not our_team:
        print("  --team is required")
        return

    if not HAS_TBA:
        print("  TBA client required for 'next' command")
        return

    next_match = find_next_match(event_key, our_team)
    if not next_match:
        print(f"  No upcoming match for {our_team} at {event_key}")
        return

    print(f"  Next match: {next_match['match_key']}")
    return cmd_match([event_key, next_match["match_key"], "--team", str(our_team)])


def cmd_opponent(args):
    """Quick opponent scouting report."""
    if not args:
        print("Usage: match_strategy.py opponent <event_key> --teams 4364,9311,10032")
        return

    event_key = args[0]
    opp_teams = None
    i = 1
    while i < len(args):
        if args[i] == "--teams" and i + 1 < len(args):
            opp_teams = [int(t) for t in args[i + 1].split(",")]
            i += 2
        else:
            i += 1

    if not opp_teams:
        print("  --teams is required")
        return

    teams_db = load_teams_db(event_key)
    opp = analyze_alliance(teams_db, opp_teams)

    print(f"\n  OPPONENT REPORT")
    print(f"  {'─' * 60}")

    for detail in opp["team_details"]:
        td = teams_db.get(str(detail["team"]), {})
        print(f"\n  {detail['team']} — {detail.get('name', '?')}")
        print(f"    EPA: {td.get('epa', 0):.1f} (floor {td.get('floor', 0):.1f}, ceiling {td.get('ceiling', 0):.1f})")
        print(f"    Role: {detail['role']}")
        print(f"    Auto: {td.get('epa_auto', 0):.1f} | Teleop: {td.get('epa_teleop', 0):.1f} | "
              f"Endgame: {td.get('epa_endgame', 0):.1f}")

        eye = detail.get("eye")
        if eye:
            print(f"    EYE ({eye['matches_scouted']} matches):")
            if eye.get("overall_assessments"):
                print(f"      Overall: {eye['overall_assessments'][0]}")
            if eye.get("mechanism_issues"):
                print(f"      Issues: {'; '.join(eye['mechanism_issues'])}")
            if eye.get("cycle_speeds"):
                print(f"      Cycle speed: {', '.join(eye['cycle_speeds'])}")

    print(f"\n  Combined EPA: {opp['total_epa']:.0f}")
    if opp["strengths"]:
        print(f"  Strengths: {', '.join(opp['strengths'])}")
    if opp["weaknesses"]:
        print(f"  Weaknesses: {', '.join(opp['weaknesses'])}")
    print()


def cmd_synergy(args):
    """Analyze alliance synergy — what's our best scoring plan?"""
    if not args:
        print("Usage: match_strategy.py synergy <event_key> --alliance 2950,7521,3035")
        return

    event_key = args[0]
    alliance_teams = None
    i = 1
    while i < len(args):
        if args[i] == "--alliance" and i + 1 < len(args):
            alliance_teams = [int(t) for t in args[i + 1].split(",")]
            i += 2
        else:
            i += 1

    if not alliance_teams:
        print("  --alliance is required")
        return

    teams_db = load_teams_db(event_key)
    profile = analyze_alliance(teams_db, alliance_teams)

    print(f"\n  ALLIANCE SYNERGY ANALYSIS")
    print(f"  {'═' * 60}")
    print(f"  Teams: {', '.join(str(t) for t in alliance_teams)}")
    print(f"  Combined EPA: {profile['total_epa']:.0f} "
          f"(floor {profile['total_floor']:.0f}, ceiling {profile['total_ceiling']:.0f})")
    print()

    # Role assignments
    print(f"  ROLE ASSIGNMENTS:")
    for detail in profile["team_details"]:
        td = teams_db.get(str(detail["team"]), {})
        print(f"    {detail['team']} {detail.get('name', '')[:20]:20s} — {detail['role']}")
        print(f"      Auto {td.get('epa_auto', 0):5.1f} | Fuel {td.get('total_fuel', 0):5.1f} | "
              f"Tower {td.get('total_tower', 0):5.1f} | Endgame {td.get('epa_endgame', 0):5.1f}")

    # Scoring zone analysis
    print(f"\n  SCORING ZONE BREAKDOWN:")
    print(f"    Auto:    {profile['auto_epa']:5.1f} pts")
    print(f"    Teleop:  {profile['teleop_epa']:5.1f} pts")
    print(f"    Endgame: {profile['endgame_epa']:5.1f} pts")
    print(f"    Fuel:    {profile['fuel_total']:5.1f} (teleop)")
    print(f"    Tower:   {profile['tower_total']:5.1f} (teleop)")

    # Synergy score
    roles = [d["role"] for d in profile["team_details"]]
    unique_roles = len(set(roles))
    diversity_bonus = unique_roles * 15

    # Check for tower coverage
    tower_covered = profile["tower_total"] > 2
    endgame_covered = profile["endgame_epa"] > 15

    synergy = min(100, diversity_bonus +
                  (20 if tower_covered else 0) +
                  (20 if endgame_covered else 0) +
                  (10 if profile["auto_epa"] > 25 else 0))

    print(f"\n  SYNERGY SCORE: {synergy}/100")
    if profile["strengths"]:
        print(f"  Strengths: {', '.join(profile['strengths'])}")
    if profile["weaknesses"]:
        print(f"  Weaknesses: {', '.join(profile['weaknesses'])}")

    # EYE insights
    eye_insights = []
    for detail in profile["team_details"]:
        eye = detail.get("eye")
        if eye and eye.get("overall_assessments"):
            eye_insights.append(f"  {detail['team']}: {eye['overall_assessments'][0]}")

    if eye_insights:
        print(f"\n  EYE SCOUTING NOTES:")
        for note in eye_insights:
            print(f"    {note}")

    print()


COMMANDS = {
    "match":    ("Strategy for a specific match", cmd_match),
    "next":     ("Strategy for next upcoming match", cmd_next),
    "opponent": ("Quick opponent scouting report", cmd_opponent),
    "synergy":  ("Alliance synergy analysis", cmd_synergy),
}


def main():
    print(f"\n  THE ENGINE — MATCH STRATEGY")
    print(f"  Team 2950 The Devastators\n")

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("  Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"    {name:12s}  {desc}")
        print()
        print("  Examples:")
        print("    python3 match_strategy.py match 2026txbel 2026txbel_qm15 --team 2950")
        print("    python3 match_strategy.py next 2026txbel --team 2950")
        print("    python3 match_strategy.py opponent 2026txbel --teams 4364,9311,10032")
        print("    python3 match_strategy.py synergy 2026txbel --alliance 2950,7521,3035")
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
