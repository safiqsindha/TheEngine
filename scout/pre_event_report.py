#!/usr/bin/env python3
"""
The Engine — Pre-Event Report Generator (Layer 1)
Team 2950 — The Devastators

Pulls TBA + Statbotics data for an event and generates team profiles
with EPA breakdowns, anomaly detection, and targeted pit questions.

Usage:
  python3 pre_event_report.py <event_key>                    # Full report
  python3 pre_event_report.py <event_key> --team 2950        # Highlight your team
  python3 pre_event_report.py <event_key> --json              # JSON output
  python3 pre_event_report.py <event_key> --top 15            # Top N only
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from statbotics_client import (
    get_event_teams, parse_event_team, get_team_events_in_year,
    epa_trend, epa_drop_pct, TeamEventEPA,
)

try:
    from tba_client import (
        event_teams, event_info, event_matches, event_rankings,
        team_key, team_number, team_record_at_event,
    )
    HAS_TBA = True
except Exception:
    HAS_TBA = False

BASE_DIR = Path(__file__).parent


# ═══════════════════════════════════════════════════════════════════
# TEAM PROFILE
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Anomaly:
    """A detected anomaly for a team."""
    type: str           # epa_drop, epa_spike, high_variance, weak_auto, no_endgame, first_event
    severity: str       # high, medium, low
    description: str
    pit_question: str   # generated question for pit visit


@dataclass
class TeamProfile:
    """Complete pre-event profile for one team."""
    team: int = 0
    name: str = ""
    location: str = ""
    rookie_year: int = 0

    # EPA at this event (or season-level if event hasn't started)
    epa_total: float = 0.0
    epa_auto: float = 0.0
    epa_teleop: float = 0.0
    epa_endgame: float = 0.0
    epa_rank_at_event: int = 0

    # Trend across events this season
    trend: str = ""           # improving, declining, stable
    epa_change_pct: float = 0.0
    events_this_season: int = 0

    # Match history
    wins: int = 0
    losses: int = 0
    ties: int = 0
    avg_score: float = 0.0
    score_std: float = 0.0

    # Anomalies
    anomalies: list = field(default_factory=list)

    # Scouting priority
    priority: str = ""        # HIGH, MEDIUM, LOW
    priority_reason: str = ""

    # Event-level EPA breakdown (2025 Reefscape specific)
    game_breakdown: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# ANOMALY DETECTION
# ═══════════════════════════════════════════════════════════════════

def detect_anomalies(profile: TeamProfile, event_epas: list[TeamEventEPA],
                     event_avg_epa: float) -> list[Anomaly]:
    """Detect anomalies in a team's data and generate pit questions."""
    anomalies = []

    # EPA dropped significantly between events
    if profile.epa_change_pct < -15:
        anomalies.append(Anomaly(
            type="epa_drop",
            severity="high",
            description=f"EPA dropped {abs(profile.epa_change_pct):.0f}% across events this season",
            pit_question="Your performance dropped since your last event. Did you change anything? Mechanism issue or strategy change?",
        ))

    # EPA spiked up
    if profile.epa_change_pct > 20:
        anomalies.append(Anomaly(
            type="epa_spike",
            severity="medium",
            description=f"EPA improved {profile.epa_change_pct:.0f}% across events",
            pit_question="Your performance jumped since your last event. What did you change or upgrade?",
        ))

    # Auto is weak relative to total
    if profile.epa_total > 0:
        auto_pct = profile.epa_auto / profile.epa_total * 100
        if auto_pct < 15 and profile.epa_total > event_avg_epa * 0.8:
            anomalies.append(Anomaly(
                type="weak_auto",
                severity="medium",
                description=f"Auto EPA is only {auto_pct:.0f}% of total — below typical",
                pit_question="Your auto seems inconsistent. Is your auto reliable? What causes it to miss?",
            ))

    # No endgame contribution
    if profile.epa_endgame <= 0 and profile.epa_total > event_avg_epa * 0.5:
        anomalies.append(Anomaly(
            type="no_endgame",
            severity="medium",
            description=f"Endgame EPA is {profile.epa_endgame:.1f} — not contributing",
            pit_question="Are you planning to climb/score in endgame? Is your endgame mechanism working?",
        ))

    # First event this season
    if profile.events_this_season <= 1:
        anomalies.append(Anomaly(
            type="first_event",
            severity="low",
            description="First or second event of the season — limited data",
            pit_question="Is this your first event? What's your robot capable of? Any issues from build season?",
        ))

    # High scoring variance (if we have match data)
    if profile.score_std > 0 and profile.avg_score > 0:
        cv = profile.score_std / profile.avg_score
        if cv > 0.5:
            anomalies.append(Anomaly(
                type="high_variance",
                severity="medium",
                description=f"High scoring variance (CV={cv:.2f}) — inconsistent match-to-match",
                pit_question="Your scores vary a lot between matches. What causes the inconsistency? Mechanism jams? Driver errors?",
            ))

    return anomalies


# ═══════════════════════════════════════════════════════════════════
# SCOUTING PRIORITY
# ═══════════════════════════════════════════════════════════════════

def assign_priority(profile: TeamProfile, event_avg_epa: float,
                    our_team: Optional[int] = None) -> tuple[str, str]:
    """Assign scouting priority: HIGH, MEDIUM, or LOW."""
    # HIGH: potential alliance picks (top ~25% EPA at event)
    if profile.epa_total > event_avg_epa * 1.3:
        return "HIGH", "Top EPA — potential alliance pick"

    # HIGH: has anomalies worth investigating
    high_anomalies = [a for a in profile.anomalies if a.severity == "high"]
    if high_anomalies:
        return "HIGH", f"Anomaly: {high_anomalies[0].description}"

    # MEDIUM: above average or has medium anomalies
    if profile.epa_total > event_avg_epa:
        return "MEDIUM", "Above-average EPA — worth watching"

    med_anomalies = [a for a in profile.anomalies if a.severity == "medium"]
    if med_anomalies:
        return "MEDIUM", f"Anomaly: {med_anomalies[0].description}"

    return "LOW", "Below-average EPA — Layer 1 data sufficient"


# ═══════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════

def build_profiles(event_key: str, year: int = 2025,
                   our_team: Optional[int] = None) -> list[TeamProfile]:
    """Build team profiles for all teams at an event."""
    print(f"  Fetching Statbotics EPA data for {event_key}...")
    raw_teams = get_event_teams(event_key)
    if not raw_teams:
        print(f"  No Statbotics data for {event_key} — event may not have started")
        return []

    epas = [parse_event_team(t) for t in raw_teams]
    epa_values = [e.epa_total for e in epas if e.epa_total > 0]
    event_avg = sum(epa_values) / len(epa_values) if epa_values else 0
    event_std = (sum((v - event_avg) ** 2 for v in epa_values) / len(epa_values)) ** 0.5 if epa_values else 0

    # TBA data if available
    tba_teams = {}
    if HAS_TBA:
        try:
            print(f"  Fetching TBA team data for {event_key}...")
            for t in event_teams(event_key):
                tba_teams[t["team_number"]] = t
        except Exception as e:
            print(f"  TBA data unavailable: {e}")

    profiles = []
    for i, team_epa in enumerate(epas):
        if team_epa.team == 0:
            continue

        p = TeamProfile(
            team=team_epa.team,
            epa_total=team_epa.epa_total,
            epa_auto=team_epa.epa_auto,
            epa_teleop=team_epa.epa_teleop,
            epa_endgame=team_epa.epa_endgame,
        )

        # TBA metadata
        tba = tba_teams.get(team_epa.team, {})
        p.name = tba.get("nickname", raw_teams[i].get("team_name", ""))
        p.location = f"{tba.get('state_prov', '')}, {tba.get('country', '')}".strip(", ")
        p.rookie_year = tba.get("rookie_year", 0)

        # Trend analysis (multi-event)
        try:
            events = get_team_events_in_year(team_epa.team, year)
            p.events_this_season = len(events)
            p.trend = epa_trend(events)
            p.epa_change_pct = epa_drop_pct(events)
        except Exception:
            p.events_this_season = 1
            p.trend = "insufficient_data"

        # Anomaly detection
        p.anomalies = detect_anomalies(p, [], event_avg)

        # Scouting priority
        p.priority, p.priority_reason = assign_priority(p, event_avg, our_team)

        # Game-specific breakdown from raw Statbotics data
        raw_epa = raw_teams[i].get("epa", {}).get("breakdown", {})
        p.game_breakdown = {k: round(v, 2) for k, v in raw_epa.items()
                           if isinstance(v, (int, float)) and k != "total_points"}

        profiles.append(p)

    # Rank by EPA
    profiles.sort(key=lambda p: p.epa_total, reverse=True)
    for rank, p in enumerate(profiles, 1):
        p.epa_rank_at_event = rank

    return profiles


def display_report(profiles: list[TeamProfile], event_key: str,
                   our_team: Optional[int] = None, top_n: int = 0):
    """Display the pre-event report."""
    if not profiles:
        print("No profiles to display.")
        return

    epa_values = [p.epa_total for p in profiles]
    avg_epa = sum(epa_values) / len(epa_values) if epa_values else 0
    std_epa = (sum((v - avg_epa) ** 2 for v in epa_values) / len(epa_values)) ** 0.5 if epa_values else 0

    print(f"\n{'═' * 70}")
    print(f"  THE SCOUT — PRE-EVENT INTELLIGENCE REPORT")
    print(f"  Event: {event_key}")
    print(f"  Teams: {len(profiles)}")
    print(f"  Avg EPA: {avg_epa:.1f} ± {std_epa:.1f}")
    print(f"{'═' * 70}")

    # Section 1: Event overview
    notable = [p for p in profiles if p.epa_total > avg_epa + std_epa]
    print(f"\n  NOTABLE TEAMS (EPA > {avg_epa + std_epa:.1f}):")
    for p in notable[:10]:
        print(f"    {p.team:5d} {p.name:25s}  EPA={p.epa_total:6.1f}  "
              f"(auto={p.epa_auto:.1f} teleop={p.epa_teleop:.1f} end={p.epa_endgame:.1f})")

    # Section 2: Highlight our team
    if our_team:
        ours = next((p for p in profiles if p.team == our_team), None)
        if ours:
            print(f"\n  {'─' * 60}")
            print(f"  YOUR TEAM: {ours.team} {ours.name}")
            print(f"  EPA: {ours.epa_total:.1f} (#{ours.epa_rank_at_event} of {len(profiles)})")
            print(f"  Auto: {ours.epa_auto:.1f} | Teleop: {ours.epa_teleop:.1f} | Endgame: {ours.epa_endgame:.1f}")
            print(f"  Trend: {ours.trend} ({ours.epa_change_pct:+.0f}%)")
            print(f"  {'─' * 60}")

    # Section 3: Team profiles
    display_list = profiles[:top_n] if top_n else profiles
    print(f"\n  TEAM PROFILES ({len(display_list)} teams)")
    print(f"  {'─' * 60}")

    for p in display_list:
        marker = " ★" if our_team and p.team == our_team else ""
        print(f"\n  #{p.epa_rank_at_event:2d} TEAM {p.team} — {p.name}{marker}")
        if p.location:
            print(f"      Location: {p.location}")
        print(f"      EPA: {p.epa_total:6.1f}  (auto={p.epa_auto:.1f}  teleop={p.epa_teleop:.1f}  endgame={p.epa_endgame:.1f})")
        print(f"      Trend: {p.trend} ({p.epa_change_pct:+.1f}%)  |  Events: {p.events_this_season}")

        if p.anomalies:
            for a in p.anomalies:
                icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(a.severity, "⚪")
                print(f"      {icon} {a.description}")

        print(f"      Priority: {p.priority} — {p.priority_reason}")

    # Section 4: Pit visit targets
    pit_targets = [p for p in profiles if p.priority == "HIGH" and p.anomalies]
    if pit_targets:
        print(f"\n  {'═' * 60}")
        print(f"  PIT VISIT TARGETS ({len(pit_targets)} teams)")
        print(f"  {'─' * 60}")
        for p in pit_targets:
            print(f"\n  TEAM {p.team} {p.name} (EPA #{p.epa_rank_at_event})")
            for a in p.anomalies:
                print(f"    Q: {a.pit_question}")

    # Section 5: Scouting priority summary
    high = sum(1 for p in profiles if p.priority == "HIGH")
    med = sum(1 for p in profiles if p.priority == "MEDIUM")
    low = sum(1 for p in profiles if p.priority == "LOW")
    print(f"\n  {'═' * 60}")
    print(f"  SCOUTING PRIORITIES")
    print(f"    HIGH:   {high:3d} teams (pit visit + stand scout)")
    print(f"    MEDIUM: {med:3d} teams (stand scout only)")
    print(f"    LOW:    {low:3d} teams (data sufficient)")
    print(f"{'═' * 70}\n")


def save_report(profiles: list[TeamProfile], event_key: str):
    """Save report as JSON."""
    out_path = BASE_DIR / f"report_{event_key}.json"
    data = {
        "event": event_key,
        "team_count": len(profiles),
        "profiles": [asdict(p) for p in profiles],
    }
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Report saved: {out_path}")
    return out_path


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def build_report_for_team(event_key: str, team_num: int,
                          year: Optional[int] = None) -> str:
    """Return a compact pre-event report for a single team as a string.

    This is the function `antenna/live_scout_commands.cmd_preview` uses.
    It builds the full event profile list (which is cached by Statbotics
    so the first call is network-bound, subsequent calls in the same
    process are fast) and extracts + formats the one team's profile.

    Returns an empty string if the team is not found at the event.
    Raises nothing — all exceptions are caught and returned as error lines.
    """
    if year is None:
        year = int(event_key[:4]) if event_key[:4].isdigit() else 2025

    try:
        profiles = build_profiles(event_key, year=year)
    except Exception as e:
        return f"[pre_event_report error: {e}]"

    if not profiles:
        return ""

    p = next((x for x in profiles if x.team == team_num), None)
    if p is None:
        return ""

    epa_values = [x.epa_total for x in profiles]
    avg_epa = sum(epa_values) / len(epa_values) if epa_values else 0

    lines = [
        f"TEAM {p.team} — {p.name}",
        f"Location: {p.location}" if p.location else "",
        f"Rank at {event_key}: #{p.epa_rank_at_event} of {len(profiles)}",
        f"EPA: {p.epa_total:.1f}  (avg {avg_epa:.1f})",
        f"  Auto:    {p.epa_auto:.1f}",
        f"  Teleop:  {p.epa_teleop:.1f}",
        f"  Endgame: {p.epa_endgame:.1f}",
        f"Trend: {p.trend}  ({p.epa_change_pct:+.0f}% vs prev event)",
        f"Events this season: {p.events_this_season}",
        f"Scouting priority: {p.priority} — {p.priority_reason}",
    ]
    lines = [l for l in lines if l]  # strip empty location line if missing

    if p.anomalies:
        lines.append("")
        lines.append("ANOMALIES:")
        for a in p.anomalies:
            icon = {"high": "!! ", "medium": "!  ", "low": "   "}.get(a.severity, "   ")
            lines.append(f"  {icon}{a.description}")
            if a.pit_question:
                lines.append(f"     Q: {a.pit_question}")

    if p.game_breakdown:
        lines.append("")
        lines.append("GAME BREAKDOWN (Statbotics):")
        for k, v in sorted(p.game_breakdown.items()):
            lines.append(f"  {k}: {v}")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("The Scout — Pre-Event Report Generator")
        print()
        print("Usage:")
        print("  python3 pre_event_report.py <event_key>")
        print("  python3 pre_event_report.py <event_key> --team 2950")
        print("  python3 pre_event_report.py <event_key> --top 15")
        print("  python3 pre_event_report.py <event_key> --json")
        print()
        print("Examples:")
        print("  python3 pre_event_report.py 2025txcmp2")
        print("  python3 pre_event_report.py 2025miket --team 2950 --top 20")
        return

    event_key = sys.argv[1]
    our_team = None
    top_n = 0
    json_output = False
    year = int(event_key[:4]) if event_key[:4].isdigit() else 2025

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--team" and i + 1 < len(args):
            our_team = int(args[i + 1])
            i += 2
        elif args[i] == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])
            i += 2
        elif args[i] == "--json":
            json_output = True
            i += 1
        else:
            i += 1

    print(f"\n{'═' * 70}")
    print(f"  THE SCOUT — GENERATING PRE-EVENT REPORT")
    print(f"  Event: {event_key}")
    print(f"{'═' * 70}\n")

    profiles = build_profiles(event_key, year=year, our_team=our_team)

    if json_output:
        save_report(profiles, event_key)
    else:
        display_report(profiles, event_key, our_team=our_team, top_n=top_n)
        save_report(profiles, event_key)


if __name__ == "__main__":
    main()
