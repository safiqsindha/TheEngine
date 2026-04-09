#!/usr/bin/env python3
"""
The Engine — Stand Scout
Team 2950 — The Devastators

Human-in-the-loop scouting data collection. Students in the stands
record observations during matches using quick-tap shorthand.
Data flows into the same pipeline as The EYE (vision scouting).

Input format (designed for Discord mobile):
  !scout <team> <tags...> [note:"free text"]

Tags (combinable, order doesn't matter):
  Auto:      auto:scored  auto:moved  auto:none  auto:foul
  Teleop:    fast  moderate  slow  fuel  tower  both
  Endgame:   climbed  barge  parked  no-endgame  fell
  Defense:   played-defense  received-defense  effective-d  weak-d
  Mechanism: intake-jam  drivetrain-issue  disabled  tipped  brownout
  Quality:   elite  solid  average  weak  carried

Examples:
  !scout 2950 auto:scored fast fuel climbed elite
  !scout 7521 auto:moved moderate tower barge played-defense
  !scout 3035 slow no-endgame intake-jam note:"dropped 3 corals mid-teleop"
  !scout 4364 auto:none disabled note:"dead on field after 30s"

Data is stored in the same JSON format as EYE reports so eye_bridge.py
can aggregate both sources into pick_board recommendations.
"""

import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

SCOUT_DATA_DIR = Path(__file__).parent / ".state" / "stand_scout"

# ─── Tag Definitions ───

AUTO_TAGS = {
    "auto:scored": {"moved": True, "scored": True},
    "auto:moved": {"moved": True, "scored": False},
    "auto:none": {"moved": False, "scored": False},
    "auto:foul": {"moved": True, "scored": False, "notes": "Auto foul"},
}

TELEOP_SPEED_TAGS = {
    "fast": "fast",
    "moderate": "moderate",
    "slow": "slow",
}

TELEOP_ZONE_TAGS = {
    "fuel": {"primary_zone": "fuel_scoring", "fuel_dominant": True},
    "tower": {"primary_zone": "tower_scoring", "tower_scoring": True},
    "both": {"primary_zone": "both", "fuel_dominant": False, "tower_scoring": True},
}

ENDGAME_TAGS = {
    "climbed": {"climb_attempted": True, "notes": "Successful climb"},
    "barge": {"climb_attempted": True, "notes": "Barge attempt"},
    "parked": {"climb_attempted": False, "notes": "Parked"},
    "no-endgame": {"climb_attempted": False, "notes": "No endgame attempt"},
    "fell": {"climb_attempted": True, "notes": "Fell during climb"},
}

DEFENSE_TAGS = {
    "played-defense": {"played_defense": True},
    "received-defense": {"received_defense": True},
    "effective-d": {"played_defense": True, "notes": "Effective defense"},
    "weak-d": {"played_defense": True, "notes": "Weak/ineffective defense"},
}

MECHANISM_TAGS = {
    "intake-jam": {"issues": "intake jam observed"},
    "drivetrain-issue": {"issues": "drivetrain problems"},
    "disabled": {"issues": "disabled during match"},
    "tipped": {"issues": "tipped over"},
    "brownout": {"issues": "brownout observed"},
}

QUALITY_MAP = {
    "elite": "Elite performance. Top-tier output.",
    "solid": "Solid performance. Reliable contributor.",
    "average": "Average performance. Functional but not standout.",
    "weak": "Weak performance. Below average output.",
    "carried": "Carried by alliance partners. Minimal contribution.",
}

ALL_TAGS = (set(AUTO_TAGS) | set(TELEOP_SPEED_TAGS) | set(TELEOP_ZONE_TAGS) |
            set(ENDGAME_TAGS) | set(DEFENSE_TAGS) | set(MECHANISM_TAGS) |
            set(QUALITY_MAP))


# ─── Parsing ───


def parse_scout_input(team_num: int, tags: list, note: str = "",
                      match_key: str = "", event_key: str = "",
                      scout_name: str = "") -> dict:
    """Parse quick-tap tags into EYE-compatible observation dict.

    Returns a dict matching the per-team structure in EYE reports:
    {team, alliance, auto, teleop, endgame, defense,
     mechanism_observations, overall, _meta}
    """
    obs = {
        "team": team_num,
        "alliance": "unknown",
        "auto": {"moved": False, "scored": False, "notes": ""},
        "teleop": {
            "primary_zone": "unknown",
            "cycle_speed": "unknown",
            "scoring_consistency": "unknown",
            "notes": "",
        },
        "endgame": {
            "climb_attempted": False,
            "notes": "",
        },
        "defense": {
            "played_defense": False,
            "received_defense": False,
            "notes": "",
        },
        "mechanism_observations": {
            "intake": "unknown",
            "drivetrain": "unknown",
            "issues": "none observed",
        },
        "overall": "",
        "_meta": {
            "source": "stand_scout",
            "scout": scout_name,
            "match_key": match_key,
            "event_key": event_key,
            "timestamp": time.time(),
        },
    }

    tags_lower = [t.lower().strip() for t in tags]

    # Parse auto tags
    for tag in tags_lower:
        if tag in AUTO_TAGS:
            obs["auto"].update(AUTO_TAGS[tag])

    # Parse teleop speed
    for tag in tags_lower:
        if tag in TELEOP_SPEED_TAGS:
            obs["teleop"]["cycle_speed"] = TELEOP_SPEED_TAGS[tag]
            # Infer consistency from speed
            if tag == "fast":
                obs["teleop"]["scoring_consistency"] = "high"
            elif tag == "slow":
                obs["teleop"]["scoring_consistency"] = "low"
            else:
                obs["teleop"]["scoring_consistency"] = "moderate"

    # Parse teleop zone
    for tag in tags_lower:
        if tag in TELEOP_ZONE_TAGS:
            obs["teleop"].update(TELEOP_ZONE_TAGS[tag])

    # Parse endgame
    for tag in tags_lower:
        if tag in ENDGAME_TAGS:
            obs["endgame"].update(ENDGAME_TAGS[tag])

    # Parse defense
    for tag in tags_lower:
        if tag in DEFENSE_TAGS:
            obs["defense"].update(DEFENSE_TAGS[tag])

    # Parse mechanism issues
    mech_issues = []
    for tag in tags_lower:
        if tag in MECHANISM_TAGS:
            mech_issues.append(MECHANISM_TAGS[tag]["issues"])
            # Update specific mechanism status
            if "intake" in tag:
                obs["mechanism_observations"]["intake"] = "jam observed"
            if "drivetrain" in tag:
                obs["mechanism_observations"]["drivetrain"] = "issue observed"

    if mech_issues:
        obs["mechanism_observations"]["issues"] = "; ".join(mech_issues)
    else:
        # No issues reported = positive signal
        obs["mechanism_observations"]["issues"] = "none observed"
        obs["mechanism_observations"]["intake"] = "functional"
        obs["mechanism_observations"]["drivetrain"] = "functional"

    # Parse quality/overall
    for tag in tags_lower:
        if tag in QUALITY_MAP:
            obs["overall"] = QUALITY_MAP[tag]

    # Add free-text note
    if note:
        obs["teleop"]["notes"] = note
        if not obs["overall"]:
            obs["overall"] = note

    # Generate overall if not set
    if not obs["overall"]:
        parts = []
        if obs["teleop"]["cycle_speed"] != "unknown":
            parts.append(f"{obs['teleop']['cycle_speed']} cycler")
        if obs["endgame"]["climb_attempted"]:
            parts.append("endgame active")
        if obs["defense"]["played_defense"]:
            parts.append("played defense")
        if mech_issues:
            parts.append(f"issues: {', '.join(mech_issues)}")
        obs["overall"] = ". ".join(parts) if parts else "Observed, no notable tags."

    return obs


# ─── Storage ───


def save_observation(obs: dict, event_key: str = ""):
    """Save a stand scout observation to the data directory.

    Stores in the same directory structure as EYE reports for
    eye_bridge.py to find and aggregate.
    """
    SCOUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    team = obs["team"]
    match_key = obs.get("_meta", {}).get("match_key", "")
    ts = int(time.time())

    # Build filename
    if match_key:
        filename = f"scout_{team}_{match_key}_{ts}.json"
    else:
        filename = f"scout_{team}_{ts}.json"

    # Wrap in report format compatible with eye_bridge
    report = {
        "teams": {str(team): obs},
        "match": {
            "event": event_key or obs.get("_meta", {}).get("event_key", ""),
            "match_key": match_key,
        },
        "source": {
            "type": "stand_scout",
            "scout": obs.get("_meta", {}).get("scout", ""),
            "timestamp": obs.get("_meta", {}).get("timestamp", ts),
        },
    }

    path = SCOUT_DATA_DIR / filename
    path.write_text(json.dumps(report, indent=2))
    return path


def load_all_observations(event_key: str = None) -> list:
    """Load all stand scout observations, optionally filtered by event."""
    if not SCOUT_DATA_DIR.exists():
        return []

    reports = []
    for f in sorted(SCOUT_DATA_DIR.glob("scout_*.json")):
        try:
            data = json.loads(f.read_text())
            if event_key and data.get("match", {}).get("event") != event_key:
                continue
            reports.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    return reports


def get_team_observations(team_num: int, event_key: str = None) -> list:
    """Get all observations for a specific team."""
    reports = load_all_observations(event_key)
    obs = []
    for r in reports:
        td = r.get("teams", {}).get(str(team_num))
        if td:
            obs.append(td)
    return obs


def get_observation_summary(event_key: str = None) -> dict:
    """Get summary statistics for all stand scout data."""
    reports = load_all_observations(event_key)

    teams_scouted = set()
    total_obs = 0
    scouts = set()

    for r in reports:
        for team_key in r.get("teams", {}):
            teams_scouted.add(team_key)
            total_obs += 1
            meta = r.get("teams", {}).get(team_key, {}).get("_meta", {})
            if meta.get("scout"):
                scouts.add(meta["scout"])

    return {
        "total_observations": total_obs,
        "teams_scouted": len(teams_scouted),
        "team_list": sorted(teams_scouted),
        "scouts": sorted(scouts),
        "reports": len(reports),
    }


# ─── Display ───


def format_observation_discord(obs: dict) -> str:
    """Format an observation for Discord display."""
    team = obs.get("team", "?")
    auto = obs.get("auto", {})
    teleop = obs.get("teleop", {})
    endgame = obs.get("endgame", {})
    defense = obs.get("defense", {})
    mechs = obs.get("mechanism_observations", {})
    overall = obs.get("overall", "")

    lines = [f"**{team}**"]

    # Auto
    auto_parts = []
    if auto.get("scored"):
        auto_parts.append("scored")
    elif auto.get("moved"):
        auto_parts.append("moved")
    else:
        auto_parts.append("none")
    if auto.get("notes"):
        auto_parts.append(auto["notes"])
    lines.append(f"Auto: {', '.join(auto_parts)}")

    # Teleop
    speed = teleop.get("cycle_speed", "?")
    zone = teleop.get("primary_zone", "?")
    lines.append(f"Teleop: {speed} | {zone}")
    if teleop.get("notes"):
        lines.append(f"  _{teleop['notes']}_")

    # Endgame
    if endgame.get("climb_attempted"):
        lines.append(f"Endgame: {endgame.get('notes', 'attempted')}")
    else:
        lines.append(f"Endgame: {endgame.get('notes', 'none')}")

    # Defense
    if defense.get("played_defense"):
        lines.append(f"Defense: played ({defense.get('notes', '')})")
    if defense.get("received_defense"):
        lines.append(f"Received defense: {defense.get('notes', 'yes')}")

    # Mechanism issues
    issues = mechs.get("issues", "none")
    if issues and issues != "none observed":
        lines.append(f"Issues: {issues}")

    # Overall
    if overall:
        lines.append(f"**{overall}**")

    return "\n".join(lines)


def format_team_summary_discord(team_num: int, observations: list) -> str:
    """Format all observations for a team into a Discord summary."""
    if not observations:
        return f"No scout data for team {team_num}"

    lines = [f"**STAND SCOUT — Team {team_num}** ({len(observations)} observations)"]
    lines.append("```")

    # Aggregate stats
    auto_scored = sum(1 for o in observations if o.get("auto", {}).get("scored"))
    auto_moved = sum(1 for o in observations if o.get("auto", {}).get("moved"))
    climbed = sum(1 for o in observations if o.get("endgame", {}).get("climb_attempted"))
    played_d = sum(1 for o in observations if o.get("defense", {}).get("played_defense"))
    has_issues = sum(1 for o in observations
                     if o.get("mechanism_observations", {}).get("issues", "none") not in ("none", "none observed"))

    n = len(observations)
    lines.append(f"Auto scored:  {auto_scored}/{n}")
    lines.append(f"Auto moved:   {auto_moved}/{n}")
    lines.append(f"Climbed:      {climbed}/{n}")
    lines.append(f"Played def:   {played_d}/{n}")
    lines.append(f"Mech issues:  {has_issues}/{n}")

    # Speed distribution
    speeds = [o.get("teleop", {}).get("cycle_speed", "?") for o in observations]
    speed_counts = {}
    for s in speeds:
        speed_counts[s] = speed_counts.get(s, 0) + 1
    speed_str = ", ".join(f"{k}:{v}" for k, v in sorted(speed_counts.items()))
    lines.append(f"Cycle speed:  {speed_str}")

    # Quality distribution
    overalls = [o.get("overall", "") for o in observations if o.get("overall")]
    quality_tags = []
    for o in overalls:
        ol = o.lower()
        if "elite" in ol:
            quality_tags.append("elite")
        elif "solid" in ol or "reliable" in ol:
            quality_tags.append("solid")
        elif "weak" in ol or "carried" in ol:
            quality_tags.append("weak")
        elif "average" in ol or "functional" in ol:
            quality_tags.append("average")
    if quality_tags:
        q_counts = {}
        for q in quality_tags:
            q_counts[q] = q_counts.get(q, 0) + 1
        q_str = ", ".join(f"{k}:{v}" for k, v in sorted(q_counts.items()))
        lines.append(f"Quality:      {q_str}")

    lines.append("```")

    # Individual match notes
    for i, o in enumerate(observations[-5:], 1):  # Last 5
        match_key = o.get("_meta", {}).get("match_key", "?")
        overall = o.get("overall", "")
        scout = o.get("_meta", {}).get("scout", "")
        tag = f" _{scout}_" if scout else ""
        lines.append(f"{i}. `{match_key}` — {overall}{tag}")

    return "\n".join(lines)


# ─── CLI ───


def cmd_add(args):
    """Add a scouting observation from CLI."""
    if len(args) < 2:
        print("Usage: stand_scout.py add <team> <tags...> [note:\"text\"] [--match key] [--event key]")
        print()
        print("Tags:")
        print(f"  Auto:      {', '.join(AUTO_TAGS.keys())}")
        print(f"  Speed:     {', '.join(TELEOP_SPEED_TAGS.keys())}")
        print(f"  Zone:      {', '.join(TELEOP_ZONE_TAGS.keys())}")
        print(f"  Endgame:   {', '.join(ENDGAME_TAGS.keys())}")
        print(f"  Defense:   {', '.join(DEFENSE_TAGS.keys())}")
        print(f"  Mechanism: {', '.join(MECHANISM_TAGS.keys())}")
        print(f"  Quality:   {', '.join(QUALITY_MAP.keys())}")
        return

    team_num = int(args[0])
    tags = []
    note = ""
    match_key = ""
    event_key = ""

    i = 1
    while i < len(args):
        if args[i].startswith("note:"):
            # Handle note:"text with spaces"
            note_text = args[i][5:].strip('"')
            # Collect rest if quoted
            while not note_text.endswith('"') and i + 1 < len(args):
                i += 1
                note_text += " " + args[i].strip('"')
            note = note_text.strip('"')
            i += 1
        elif args[i] == "--match" and i + 1 < len(args):
            match_key = args[i + 1]; i += 2
        elif args[i] == "--event" and i + 1 < len(args):
            event_key = args[i + 1]; i += 2
        else:
            tags.append(args[i])
            i += 1

    # Validate tags
    unknown = [t for t in tags if t.lower() not in ALL_TAGS]
    if unknown:
        print(f"  Unknown tags: {', '.join(unknown)}")
        print(f"  Valid tags: {', '.join(sorted(ALL_TAGS))}")
        return

    obs = parse_scout_input(team_num, tags, note=note,
                            match_key=match_key, event_key=event_key)
    path = save_observation(obs, event_key=event_key)
    print(f"  Saved: {path.name}")
    print(f"  {format_observation_discord(obs)}")


def cmd_team(args):
    """Show all observations for a team."""
    if not args:
        print("Usage: stand_scout.py team <team_number> [event_key]")
        return

    team_num = int(args[0])
    event_key = args[1] if len(args) > 1 else None
    observations = get_team_observations(team_num, event_key)

    if not observations:
        print(f"  No scout data for team {team_num}")
        return

    print(format_team_summary_discord(team_num, observations))


def cmd_summary(args):
    """Show scouting coverage summary."""
    event_key = args[0] if args else None
    summary = get_observation_summary(event_key)

    print(f"\n  STAND SCOUT — COVERAGE SUMMARY")
    print(f"  {'─' * 40}")
    print(f"  Total observations: {summary['total_observations']}")
    print(f"  Teams scouted:      {summary['teams_scouted']}")
    print(f"  Reports:            {summary['reports']}")
    if summary["scouts"]:
        print(f"  Scouts:             {', '.join(summary['scouts'])}")
    if summary["team_list"]:
        print(f"  Teams: {', '.join(summary['team_list'])}")
    print()


COMMANDS = {
    "add":     ("Add a scouting observation", cmd_add),
    "team":    ("Show observations for a team", cmd_team),
    "summary": ("Show scouting coverage", cmd_summary),
}


def main():
    print(f"\n  STAND SCOUT — Human Scouting")
    print(f"  Team 2950 The Devastators\n")

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("  Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"    {name:10s}  {desc}")
        print()
        print("  Quick-add example:")
        print("    python3 stand_scout.py add 2950 auto:scored fast fuel climbed elite")
        print("    python3 stand_scout.py add 7521 moderate tower barge played-defense")
        print()
        print("  Tags:")
        print(f"    Auto:      {', '.join(AUTO_TAGS.keys())}")
        print(f"    Speed:     {', '.join(TELEOP_SPEED_TAGS.keys())}")
        print(f"    Zone:      {', '.join(TELEOP_ZONE_TAGS.keys())}")
        print(f"    Endgame:   {', '.join(ENDGAME_TAGS.keys())}")
        print(f"    Defense:   {', '.join(DEFENSE_TAGS.keys())}")
        print(f"    Mechanism: {', '.join(MECHANISM_TAGS.keys())}")
        print(f"    Quality:   {', '.join(QUALITY_MAP.keys())}")
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
