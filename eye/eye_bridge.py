#!/usr/bin/env python3
"""
The Engine — EYE Bridge
Team 2950 — The Devastators

Bridges EYE vision reports AND stand scout observations into the pick
board's team data. Both sources produce the same JSON observation format,
so this module aggregates them identically.

EYE + Stand Scout data captures what EPA can't:
  - Mechanism reliability (jams, breakdowns, recovery time)
  - Defense effectiveness (both playing and receiving)
  - Driver skill (pathing, cycle efficiency, awareness)
  - Consistency under pressure (endgame execution, close matches)
  - Field control (game piece dominance, zone control)

When both sources exist for a team, stand scout observations are weighted
higher (human tracked one robot deliberately) but EYE provides broader
coverage (every match on stream).

Usage:
  # Load all EYE + stand scout reports for an event into pick board state
  python3 eye_bridge.py load <event_key>

  # Show scores for all scouted teams
  python3 eye_bridge.py scores

  # Show raw scouting data for a specific team
  python3 eye_bridge.py team <team_number>
"""

import json
import sys
from pathlib import Path

EYE_RESULTS_DIR = Path(__file__).parent / ".cache" / "results"
SCOUT_DIR = Path(__file__).parent.parent / "scout"
STATE_DIR = SCOUT_DIR / ".state"
STATE_FILE = STATE_DIR / "draft_state.json"
STAND_SCOUT_DIR = STATE_DIR / "stand_scout"


# ─── Report Loading (EYE + Stand Scout) ───


def load_eye_reports(event_key: str = None) -> list:
    """Load all EYE scouting reports, optionally filtered by event."""
    if not EYE_RESULTS_DIR.exists():
        return []

    reports = []
    for f in EYE_RESULTS_DIR.glob("*_report.json"):
        try:
            data = json.loads(f.read_text())
            if event_key and data.get("match", {}).get("event") != event_key:
                continue
            reports.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    return reports


def load_stand_scout_reports(event_key: str = None) -> list:
    """Load all stand scout observations."""
    if not STAND_SCOUT_DIR.exists():
        return []

    reports = []
    for f in sorted(STAND_SCOUT_DIR.glob("scout_*.json")):
        try:
            data = json.loads(f.read_text())
            if event_key and data.get("match", {}).get("event") != event_key:
                continue
            reports.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    return reports


def load_all_reports(event_key: str = None) -> tuple:
    """Load both EYE and stand scout reports.

    Returns (eye_reports, stand_reports) so callers can weight them differently.
    """
    return load_eye_reports(event_key), load_stand_scout_reports(event_key)


def aggregate_team_eye_data(reports: list) -> dict:
    """Aggregate observations across all matches into per-team scores.

    Accepts both EYE and stand scout reports (same JSON structure).
    Returns: {team_number_str: {eye scores dict}}
    """
    team_obs = {}  # team -> list of per-match observations

    for report in reports:
        teams = report.get("teams", {})
        for team_key, td in teams.items():
            if team_key not in team_obs:
                team_obs[team_key] = []
            team_obs[team_key].append(td)

    # Score each team
    team_scores = {}
    for team_key, observations in team_obs.items():
        team_scores[team_key] = _score_team(team_key, observations)

    return team_scores


def aggregate_blended(eye_reports: list, stand_reports: list) -> dict:
    """Aggregate with source-aware confidence blending.

    Stand scout observations get higher per-observation confidence
    (human deliberately tracked one robot) but EYE provides broader
    coverage. The blending weights the composite score accordingly.
    """
    # Score each source separately
    eye_scores = aggregate_team_eye_data(eye_reports) if eye_reports else {}
    stand_scores = aggregate_team_eye_data(stand_reports) if stand_reports else {}

    # Merge all teams
    all_teams = set(eye_scores.keys()) | set(stand_scores.keys())
    blended = {}

    for team_key in all_teams:
        eye = eye_scores.get(team_key)
        stand = stand_scores.get(team_key)

        if eye and stand:
            # Blend: stand scout observations worth 1.5x per match
            eye_weight = eye.get("eye_matches", 0)
            stand_weight = stand.get("eye_matches", 0) * 1.5
            total_weight = eye_weight + stand_weight

            if total_weight == 0:
                blended[team_key] = eye or stand
                continue

            ew = eye_weight / total_weight
            sw = stand_weight / total_weight

            result = {}
            for key in ("eye_composite", "eye_reliability", "eye_driver",
                        "eye_overall"):
                ev = eye.get(key, 0)
                sv = stand.get(key, 0)
                result[key] = round(ev * ew + sv * sw, 1)

            # Take max confidence, sum matches
            result["eye_matches"] = eye.get("eye_matches", 0) + stand.get("eye_matches", 0)
            result["eye_confidence"] = min(100, result["eye_matches"] * 20)
            result["eye_sources"] = {"eye": eye.get("eye_matches", 0),
                                      "stand": stand.get("eye_matches", 0)}

            # Keep optional fields from whichever source has them
            for key in ("eye_defense_ability", "eye_defense_resistance", "eye_endgame"):
                ev = eye.get(key)
                sv = stand.get(key)
                if ev is not None and sv is not None:
                    result[key] = round(ev * ew + sv * sw, 1)
                elif ev is not None:
                    result[key] = ev
                elif sv is not None:
                    result[key] = sv

            blended[team_key] = result

        elif eye:
            blended[team_key] = eye
        else:
            # Stand-only: bump confidence slightly (human observation)
            result = dict(stand)
            result["eye_confidence"] = min(100, stand.get("eye_matches", 0) * 30)
            blended[team_key] = result

    return blended


def _score_team(team_key: str, observations: list) -> dict:
    """Convert raw EYE observations into quantitative scores (0-100 scale).

    Scoring dimensions:
      - reliability: mechanism consistency, no jams/breakdowns
      - defense_ability: effectiveness when playing defense
      - defense_resistance: ability to score under defensive pressure
      - driver_skill: pathing, cycle speed, awareness
      - consistency: scoring variance across matches
      - endgame_execution: climb/barge success rate
      - eye_composite: weighted combination of all dimensions
    """
    n = len(observations)
    if n == 0:
        return {"eye_composite": 0, "eye_matches": 0, "eye_confidence": 0}

    # ── Reliability (mechanism health) ──
    reliability_scores = []
    for obs in observations:
        mechs = obs.get("mechanism_observations", obs.get("mechanisms", {}))
        if isinstance(mechs, dict):
            issues = mechs.get("issues", "none")
        elif isinstance(mechs, list):
            issues = " ".join(str(m) for m in mechs)
        else:
            issues = str(mechs)

        issues_lower = issues.lower() if issues else ""
        if any(w in issues_lower for w in ("none", "no issues", "functional", "clean", "smooth")):
            reliability_scores.append(90)
        elif any(w in issues_lower for w in ("jam", "stuck", "breakdown", "fail", "disabled", "dead")):
            reliability_scores.append(20)
        elif any(w in issues_lower for w in ("slow", "inconsistent", "difficulty", "struggled")):
            reliability_scores.append(50)
        else:
            reliability_scores.append(65)  # neutral/unknown

    reliability = sum(reliability_scores) / len(reliability_scores) if reliability_scores else 65

    # ── Defense ability ──
    defense_scores = []
    for obs in observations:
        defense = obs.get("defense", {})
        if isinstance(defense, dict):
            played = defense.get("played_defense", False)
            notes = defense.get("notes", "").lower()
        elif isinstance(defense, list):
            played = bool(defense)
            notes = " ".join(str(d) for d in defense).lower()
        else:
            played = False
            notes = ""

        if played:
            if any(w in notes for w in ("effective", "strong", "shut down", "disrupted")):
                defense_scores.append(85)
            elif any(w in notes for w in ("weak", "ineffective", "penalty", "foul")):
                defense_scores.append(30)
            else:
                defense_scores.append(60)

    defense_ability = sum(defense_scores) / len(defense_scores) if defense_scores else None

    # ── Defense resistance ──
    resistance_scores = []
    for obs in observations:
        defense = obs.get("defense", {})
        if isinstance(defense, dict):
            received = defense.get("received_defense", False)
            notes = defense.get("notes", "").lower()
        elif isinstance(defense, list):
            received = any("received" in str(d).lower() for d in defense)
            notes = " ".join(str(d) for d in defense).lower()
        else:
            received = False
            notes = ""

        if received:
            if any(w in notes for w in ("still scored", "unaffected", "pushed through")):
                resistance_scores.append(85)
            elif any(w in notes for w in ("stopped", "shut down", "couldn't score")):
                resistance_scores.append(25)
            else:
                resistance_scores.append(50)

    defense_resistance = sum(resistance_scores) / len(resistance_scores) if resistance_scores else None

    # ── Driver skill (cycle speed, pathing) ──
    driver_scores = []
    for obs in observations:
        teleop = obs.get("teleop", {})
        if isinstance(teleop, dict):
            speed = teleop.get("cycle_speed", "").lower()
            consistency = teleop.get("scoring_consistency", "").lower()
            notes = teleop.get("notes", "").lower()
        elif isinstance(teleop, list):
            speed = ""
            consistency = ""
            notes = " ".join(str(t) for t in teleop).lower()
        else:
            speed = ""
            consistency = ""
            notes = ""

        score = 60  # baseline
        if "fast" in speed:
            score += 15
        elif "slow" in speed:
            score -= 15

        if "high" in consistency:
            score += 10
        elif "low" in consistency:
            score -= 10

        if any(w in notes for w in ("dominant", "elite", "primary scorer")):
            score += 10
        elif any(w in notes for w in ("carried", "low output", "minimal")):
            score -= 15

        driver_scores.append(max(0, min(100, score)))

    driver_skill = sum(driver_scores) / len(driver_scores) if driver_scores else 60

    # ── Endgame execution ──
    endgame_scores = []
    for obs in observations:
        endgame = obs.get("endgame", {})
        if isinstance(endgame, dict):
            attempted = endgame.get("climb_attempted", False)
            notes = endgame.get("notes", "").lower()
        elif isinstance(endgame, list):
            attempted = bool(endgame)
            notes = " ".join(str(e) for e in endgame).lower()
        else:
            attempted = False
            notes = ""

        if attempted:
            if any(w in notes for w in ("success", "completed", "strong", "contributing")):
                endgame_scores.append(85)
            elif any(w in notes for w in ("failed", "fell", "tipped", "couldn't")):
                endgame_scores.append(25)
            else:
                endgame_scores.append(60)
        else:
            endgame_scores.append(30)

    endgame_execution = sum(endgame_scores) / len(endgame_scores) if endgame_scores else None

    # ── Overall assessment ──
    overall_scores = []
    for obs in observations:
        overall = obs.get("overall", "").lower()
        if any(w in overall for w in ("elite", "dominant", "exceptional", "best")):
            overall_scores.append(90)
        elif any(w in overall for w in ("strong", "solid", "good", "reliable")):
            overall_scores.append(75)
        elif any(w in overall for w in ("functional", "average", "decent", "support")):
            overall_scores.append(55)
        elif any(w in overall for w in ("weak", "outmatched", "carried", "limited", "niche")):
            overall_scores.append(30)
        else:
            overall_scores.append(55)

    overall = sum(overall_scores) / len(overall_scores) if overall_scores else 55

    # ── Composite score ──
    # Weight: reliability 25%, driver 25%, overall 20%, endgame 15%, defense 15%
    components = [
        (reliability, 0.25),
        (driver_skill, 0.25),
        (overall, 0.20),
    ]

    remaining_weight = 0.30
    if endgame_execution is not None:
        components.append((endgame_execution, 0.15))
        remaining_weight -= 0.15
    if defense_resistance is not None:
        components.append((defense_resistance, remaining_weight))
    elif defense_ability is not None:
        components.append((defense_ability, remaining_weight))
    else:
        # Redistribute to existing components
        for i in range(len(components)):
            components[i] = (components[i][0], components[i][1] + remaining_weight / len(components))

    composite = sum(score * weight for score, weight in components)

    # Confidence scales with number of matches observed
    confidence = min(100, n * 25)  # 1 match = 25%, 4+ matches = 100%

    result = {
        "eye_composite": round(composite, 1),
        "eye_reliability": round(reliability, 1),
        "eye_driver": round(driver_skill, 1),
        "eye_overall": round(overall, 1),
        "eye_matches": n,
        "eye_confidence": confidence,
    }

    if defense_ability is not None:
        result["eye_defense_ability"] = round(defense_ability, 1)
    if defense_resistance is not None:
        result["eye_defense_resistance"] = round(defense_resistance, 1)
    if endgame_execution is not None:
        result["eye_endgame"] = round(endgame_execution, 1)

    return result


# ─── Pick Board Integration ───


def inject_eye_data(state: dict, eye_scores: dict) -> int:
    """Inject EYE scores into pick board team data.

    Returns number of teams enriched.
    """
    enriched = 0
    for team_key, scores in eye_scores.items():
        if team_key in state["teams"]:
            state["teams"][team_key].update(scores)
            enriched += 1
    return enriched


# ─── Commands ───


def cmd_load(args):
    """Load EYE + stand scout reports into pick board state."""
    if not STATE_FILE.exists():
        print("  No active draft. Run 'pick_board.py setup' first.")
        return

    state = json.loads(STATE_FILE.read_text())
    event_key = args[0] if args else state.get("event_key", "")

    print(f"\n  THE EYE — BRIDGE TO PICK BOARD")
    print(f"  Event: {event_key}")
    print(f"  {'─' * 50}")

    eye_reports = load_eye_reports(event_key)
    stand_reports = load_stand_scout_reports(event_key)

    if not eye_reports and not stand_reports:
        # Try loading all reports (may be from YouTube without event tagging)
        eye_reports = load_eye_reports()
        stand_reports = load_stand_scout_reports()
        if eye_reports or stand_reports:
            print(f"  No event-specific reports. Loading all available.")
        else:
            print(f"  No scouting reports found.")
            print(f"    EYE: {EYE_RESULTS_DIR}")
            print(f"    Stand: {STAND_SCOUT_DIR}")
            return

    print(f"  EYE reports:    {len(eye_reports)}")
    print(f"  Stand reports:  {len(stand_reports)}")

    eye_scores = aggregate_blended(eye_reports, stand_reports)
    enriched = inject_eye_data(state, eye_scores)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

    print(f"  Enriched {enriched} teams with EYE scouting data")

    # Show enriched teams
    if eye_scores:
        print(f"\n  {'Team':>6} {'Composite':>10} {'Reliab':>8} {'Driver':>8} {'Overall':>8} {'Src':>10} {'Conf':>6}")
        print(f"  {'─' * 62}")

        sorted_teams = sorted(eye_scores.items(),
                              key=lambda x: x[1].get("eye_composite", 0), reverse=True)
        for team_key, scores in sorted_teams:
            in_draft = "  " if team_key in state["teams"] else "* "
            sources = scores.get("eye_sources", {})
            if sources:
                src_str = f"E{sources.get('eye', 0)}+S{sources.get('stand', 0)}"
            else:
                src_str = f"{scores['eye_matches']}m"
            print(f"  {in_draft}{int(team_key):4d} {scores['eye_composite']:10.1f} "
                  f"{scores.get('eye_reliability', 0):8.1f} "
                  f"{scores.get('eye_driver', 0):8.1f} "
                  f"{scores.get('eye_overall', 0):8.1f} "
                  f"{src_str:>10} {scores['eye_confidence']:5d}%")

    print()


def cmd_scores(args):
    """Show EYE scores for all scouted teams."""
    if not STATE_FILE.exists():
        print("  No active draft.")
        return

    state = json.loads(STATE_FILE.read_text())

    print(f"\n  THE EYE — TEAM SCORES")
    print(f"  {'─' * 70}")
    print(f"  {'Team':>6} {'EPA':>6} {'EYE':>6} {'Reliab':>8} {'Driver':>8} {'Endgame':>8} {'DefRes':>8} {'Conf':>6}")
    print(f"  {'─' * 70}")

    teams_with_eye = [(k, v) for k, v in state["teams"].items()
                      if v.get("eye_composite")]
    teams_with_eye.sort(key=lambda x: x[1]["eye_composite"], reverse=True)

    for team_key, td in teams_with_eye:
        print(f"  {td['team']:6d} {td['epa']:6.1f} {td['eye_composite']:6.1f} "
              f"{td.get('eye_reliability', 0):8.1f} "
              f"{td.get('eye_driver', 0):8.1f} "
              f"{td.get('eye_endgame', 0):8.1f} "
              f"{td.get('eye_defense_resistance', 0):8.1f} "
              f"{td.get('eye_confidence', 0):5d}%")

    if not teams_with_eye:
        print("  No teams have EYE data. Run 'eye_bridge.py load' first.")

    print()


def cmd_team(args):
    """Show detailed EYE data for a specific team."""
    if not args:
        print("Usage: eye_bridge.py team <team_number>")
        return

    team_key = args[0]
    reports = load_eye_reports()

    print(f"\n  THE EYE — TEAM {team_key} SCOUTING DATA")
    print(f"  {'─' * 50}")

    match_count = 0
    for report in reports:
        teams = report.get("teams", {})
        if team_key in teams:
            match_count += 1
            td = teams[team_key]
            source = report.get("source", {})
            match_info = report.get("match", {})

            label = ""
            if match_info:
                label = f"{match_info.get('event', '?')} {match_info.get('comp_level', 'qm')}{match_info.get('match_number', '?')}"
            elif source.get("video_url"):
                label = source["video_url"][-11:]

            print(f"\n  Match {match_count}: {label}")
            print(f"    Alliance: {td.get('alliance', '?')}")

            if td.get("auto"):
                auto = td["auto"]
                if isinstance(auto, dict):
                    print(f"    Auto: moved={auto.get('moved')}, scored={auto.get('scored')}")
                    if auto.get("notes"):
                        print(f"          {auto['notes']}")

            if td.get("teleop"):
                teleop = td["teleop"]
                if isinstance(teleop, dict):
                    print(f"    Teleop: zone={teleop.get('primary_zone', '?')}, "
                          f"speed={teleop.get('cycle_speed', '?')}, "
                          f"consistency={teleop.get('scoring_consistency', '?')}")
                    if teleop.get("notes"):
                        print(f"            {teleop['notes']}")

            if td.get("defense"):
                defense = td["defense"]
                if isinstance(defense, dict):
                    print(f"    Defense: played={defense.get('played_defense')}, "
                          f"received={defense.get('received_defense')}")

            if td.get("overall"):
                print(f"    Overall: {td['overall']}")

    if match_count == 0:
        print(f"  No EYE data for team {team_key}")
    else:
        # Show computed scores
        scores = aggregate_team_eye_data(reports).get(team_key, {})
        if scores:
            print(f"\n  COMPUTED SCORES:")
            for k, v in sorted(scores.items()):
                print(f"    {k}: {v}")

    print()


COMMANDS = {
    "load":   ("Load EYE reports into pick board state", cmd_load),
    "scores": ("Show EYE scores for all scouted teams", cmd_scores),
    "team":   ("Show detailed EYE data for a team", cmd_team),
}


def main():
    print(f"\n  THE EYE — BRIDGE")
    print(f"  Team 2950 The Devastators\n")

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("  Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"    {name:10s}  {desc}")
        print()
        print("  Workflow:")
        print("    1. Run EYE analysis on match videos (the_eye.py analyze ...)")
        print("    2. Load scores into draft: eye_bridge.py load")
        print("    3. Pick board now uses EYE data in recommendations")
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
