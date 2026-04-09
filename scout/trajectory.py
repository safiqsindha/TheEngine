#!/usr/bin/env python3
"""
The Engine — Multi-Event EPA Trajectory Tracker
Team 2950 — The Devastators

Tracks how teams' EPA changes across events in a season.
Identifies improving, declining, and peaking teams — critical
for mid/late season alliance selection when Week 1 EPA ≠ Week 5 EPA.

Usage:
  # Show EPA trajectory for a team
  python3 trajectory.py team 2881 2026

  # Compare trajectories of multiple teams
  python3 trajectory.py compare 2881,148,2468 2026

  # Show all teams at an event with their trajectory context
  python3 trajectory.py event 2026txbel

  # Find rising/falling teams in a district
  python3 trajectory.py movers 2026fit
"""

import json
import sys
import time
from pathlib import Path

from statbotics_client import (
    get_team_events_in_year, get_event_teams, parse_event_team,
    epa_trend, epa_drop_pct,
)
from tba_client import (
    district_rankings, district_events, event_team_keys,
    team_events as tba_team_events,
)

CACHE_DIR = Path(__file__).parent / ".cache" / "trajectory"


def team_trajectory(team: int, year: int) -> dict:
    """Get a team's EPA trajectory across all events in a year."""
    events = get_team_events_in_year(team, year)
    if not events:
        return None

    # Sort by event key (roughly chronological for district events)
    events.sort(key=lambda e: e.event)

    epas = [e.epa_total for e in events]
    autos = [e.epa_auto for e in events]
    teleops = [e.epa_teleop for e in events]
    endgames = [e.epa_endgame for e in events]

    trend = epa_trend(events)
    drop = epa_drop_pct(events)

    # Calculate momentum (weighted recent change)
    if len(epas) >= 2:
        recent_delta = epas[-1] - epas[-2]
        overall_delta = epas[-1] - epas[0]
    else:
        recent_delta = 0
        overall_delta = 0

    # Peak detection
    peak_epa = max(epas) if epas else 0
    peak_idx = epas.index(peak_epa) if epas else 0
    peaked_early = peak_idx < len(epas) - 1  # Peak wasn't at last event

    return {
        "team": team,
        "year": year,
        "events": [
            {
                "event": e.event,
                "epa": e.epa_total,
                "auto": e.epa_auto,
                "teleop": e.epa_teleop,
                "endgame": e.epa_endgame,
                "start": e.epa_total_start,
                "end": e.epa_total_end,
            }
            for e in events
        ],
        "trend": trend,
        "drop_pct": drop,
        "recent_delta": recent_delta,
        "overall_delta": overall_delta,
        "peak_epa": peak_epa,
        "current_epa": epas[-1] if epas else 0,
        "peaked_early": peaked_early,
        "n_events": len(events),
    }


def trajectory_warning(traj: dict) -> str:
    """Generate a human-readable warning if trajectory is concerning."""
    if not traj or traj["n_events"] < 2:
        return ""

    warnings = []
    if traj["trend"] == "declining" and traj["drop_pct"] < -15:
        warnings.append(f"DECLINING ({traj['drop_pct']:.0f}% from peak)")
    if traj["peaked_early"] and traj["current_epa"] < traj["peak_epa"] * 0.85:
        warnings.append(f"PEAKED EARLY (peak {traj['peak_epa']:.1f}, now {traj['current_epa']:.1f})")
    if traj["recent_delta"] < -10:
        warnings.append(f"DROPPING FAST (last event -{abs(traj['recent_delta']):.1f})")
    if traj["trend"] == "improving" and traj["drop_pct"] > 20:
        warnings.append(f"RISING ({traj['drop_pct']:+.0f}%)")
    if traj["recent_delta"] > 10:
        warnings.append(f"HOT (last event +{traj['recent_delta']:.1f})")

    return " | ".join(warnings)


def sparkline(values: list, width: int = 12) -> str:
    """Simple ASCII sparkline for EPA trajectory."""
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn if mx > mn else 1
    chars = "▁▂▃▄▅▆▇█"
    line = ""
    for v in values:
        idx = int((v - mn) / rng * (len(chars) - 1))
        line += chars[idx]
    return line


def cmd_team(args):
    """Show EPA trajectory for a single team."""
    if len(args) < 2:
        print("Usage: trajectory.py team <team#> <year>")
        return

    team = int(args[0])
    year = int(args[1])

    print(f"\n  EPA TRAJECTORY — Team {team} ({year})")
    print(f"  {'─' * 60}")

    traj = team_trajectory(team, year)
    if not traj:
        print(f"  No data for team {team} in {year}")
        return

    # Header
    warning = trajectory_warning(traj)
    if warning:
        print(f"  ⚠ {warning}")

    epas = [e["epa"] for e in traj["events"]]
    print(f"  Trend: {traj['trend']} | {traj['n_events']} events | "
          f"Δ {traj['overall_delta']:+.1f} ({traj['drop_pct']:+.1f}%)")
    print(f"  Spark: {sparkline(epas)}")

    # Per-event detail
    print(f"\n  {'Event':<12s} {'EPA':>7s} {'Auto':>7s} {'Tele':>7s} {'End':>7s} {'Δ':>7s}")
    print(f"  {'─' * 55}")

    prev_epa = None
    for e in traj["events"]:
        delta_str = ""
        if prev_epa is not None:
            d = e["epa"] - prev_epa
            delta_str = f"{d:+.1f}"
        prev_epa = e["epa"]

        print(f"  {e['event']:<12s} {e['epa']:7.1f} {e['auto']:7.1f} "
              f"{e['teleop']:7.1f} {e['endgame']:7.1f} {delta_str:>7s}")

    print()


def cmd_compare(args):
    """Compare EPA trajectories of multiple teams."""
    if len(args) < 2:
        print("Usage: trajectory.py compare <team1,team2,...> <year>")
        return

    teams = [int(t) for t in args[0].split(",")]
    year = int(args[1])

    print(f"\n  EPA TRAJECTORY COMPARISON ({year})")
    print(f"  {'─' * 75}")

    trajectories = []
    for team in teams:
        traj = team_trajectory(team, year)
        if traj:
            trajectories.append(traj)
        time.sleep(0.2)

    if not trajectories:
        print("  No data found")
        return

    print(f"  {'Team':>6s} {'Events':>6s} {'First':>7s} {'Current':>7s} "
          f"{'Peak':>7s} {'Δ%':>6s} {'Trend':<12s} {'Spark':<14s} {'Warning'}")
    print(f"  {'─' * 90}")

    for traj in sorted(trajectories, key=lambda t: t["current_epa"], reverse=True):
        epas = [e["epa"] for e in traj["events"]]
        first_epa = epas[0] if epas else 0
        warning = trajectory_warning(traj)
        print(f"  {traj['team']:>6d} {traj['n_events']:>6d} {first_epa:>7.1f} "
              f"{traj['current_epa']:>7.1f} {traj['peak_epa']:>7.1f} "
              f"{traj['drop_pct']:>+5.0f}% {traj['trend']:<12s} "
              f"{sparkline(epas):<14s} {warning}")

    print()


def cmd_event(args):
    """Show trajectories for all teams at an event."""
    if not args:
        print("Usage: trajectory.py event <event_key>")
        return

    event_key = args[0]
    year = int(event_key[:4])

    print(f"\n  EVENT TRAJECTORIES — {event_key}")
    print(f"  {'─' * 85}")

    # Get teams at event
    raw = get_event_teams(event_key)
    if not raw:
        print("  No data")
        return

    teams = [t.get("team", 0) for t in raw if t.get("team")]
    teams.sort()

    print(f"  Loading trajectories for {len(teams)} teams...")

    results = []
    for team in teams:
        traj = team_trajectory(team, year)
        if traj:
            results.append(traj)
        time.sleep(0.15)

    # Sort by current EPA
    results.sort(key=lambda t: t["current_epa"], reverse=True)

    print(f"\n  {'#':>3s} {'Team':>6s} {'Evts':>4s} {'Current':>7s} {'Peak':>7s} "
          f"{'Δ%':>6s} {'Trend':<10s} {'Spark':<12s} {'Notes'}")
    print(f"  {'─' * 85}")

    for i, traj in enumerate(results, 1):
        epas = [e["epa"] for e in traj["events"]]
        warning = trajectory_warning(traj)
        multi = "→" if traj["n_events"] == 1 else ""
        print(f"  {i:>3d} {traj['team']:>6d} {traj['n_events']:>4d} "
              f"{traj['current_epa']:>7.1f} {traj['peak_epa']:>7.1f} "
              f"{traj['drop_pct']:>+5.0f}% {traj['trend']:<10s} "
              f"{sparkline(epas):<12s} {warning}")

    # Highlight risers and fallers
    risers = [t for t in results if t["trend"] == "improving" and t["drop_pct"] > 15]
    fallers = [t for t in results if t["trend"] == "declining" and t["drop_pct"] < -15]

    if risers:
        print(f"\n  RISERS (improving >15%):")
        for t in sorted(risers, key=lambda x: x["drop_pct"], reverse=True)[:5]:
            print(f"    {t['team']:>6d}  EPA {t['current_epa']:.1f}  ({t['drop_pct']:+.0f}%)")

    if fallers:
        print(f"\n  FALLERS (declining >15%):")
        for t in sorted(fallers, key=lambda x: x["drop_pct"])[:5]:
            print(f"    {t['team']:>6d}  EPA {t['current_epa']:.1f}  ({t['drop_pct']:+.0f}%)")

    print()


def cmd_movers(args):
    """Find biggest risers and fallers in a district."""
    if not args:
        print("Usage: trajectory.py movers <district_key>")
        return

    district_key = args[0]
    year = int(district_key[:4])

    print(f"\n  DISTRICT MOVERS — {district_key.upper()}")
    print(f"  {'─' * 70}")

    # Get all teams in district
    rankings = district_rankings(district_key)
    if not rankings:
        print("  No rankings data")
        return

    teams = [r.get("team_key", "").replace("frc", "")
             for r in rankings if r.get("team_key")]
    teams = [int(t) for t in teams if t.isdigit()]

    print(f"  Loading trajectories for {len(teams)} teams...")

    results = []
    for i, team in enumerate(teams):
        traj = team_trajectory(team, year)
        if traj and traj["n_events"] >= 2:
            results.append(traj)
        if i % 10 == 0 and i > 0:
            print(f"    ...{i}/{len(teams)}")
        time.sleep(0.15)

    # Top risers
    risers = sorted(results, key=lambda t: t["drop_pct"], reverse=True)[:10]
    fallers = sorted(results, key=lambda t: t["drop_pct"])[:10]
    hot = sorted(results, key=lambda t: t["recent_delta"], reverse=True)[:10]
    cold = sorted(results, key=lambda t: t["recent_delta"])[:10]

    print(f"\n  TOP RISERS (season-long improvement):")
    print(f"  {'Team':>6s} {'First':>7s} {'Now':>7s} {'Δ%':>6s} {'Spark'}")
    print(f"  {'─' * 45}")
    for t in risers:
        epas = [e["epa"] for e in t["events"]]
        print(f"  {t['team']:>6d} {epas[0]:>7.1f} {t['current_epa']:>7.1f} "
              f"{t['drop_pct']:>+5.0f}% {sparkline(epas)}")

    print(f"\n  TOP FALLERS (season-long decline):")
    print(f"  {'Team':>6s} {'First':>7s} {'Now':>7s} {'Δ%':>6s} {'Spark'}")
    print(f"  {'─' * 45}")
    for t in fallers:
        epas = [e["epa"] for e in t["events"]]
        print(f"  {t['team']:>6d} {epas[0]:>7.1f} {t['current_epa']:>7.1f} "
              f"{t['drop_pct']:>+5.0f}% {sparkline(epas)}")

    print(f"\n  HOTTEST RIGHT NOW (biggest recent jump):")
    print(f"  {'Team':>6s} {'Now':>7s} {'Recent Δ':>9s} {'Spark'}")
    print(f"  {'─' * 40}")
    for t in hot:
        epas = [e["epa"] for e in t["events"]]
        print(f"  {t['team']:>6d} {t['current_epa']:>7.1f} "
              f"{t['recent_delta']:>+8.1f} {sparkline(epas)}")

    print(f"\n  COLDEST RIGHT NOW (biggest recent drop):")
    print(f"  {'Team':>6s} {'Now':>7s} {'Recent Δ':>9s} {'Spark'}")
    print(f"  {'─' * 40}")
    for t in cold:
        epas = [e["epa"] for e in t["events"]]
        print(f"  {t['team']:>6d} {t['current_epa']:>7.1f} "
              f"{t['recent_delta']:>+8.1f} {sparkline(epas)}")

    print()


COMMANDS = {
    "team":    ("Show EPA trajectory for a team", cmd_team),
    "compare": ("Compare trajectories of multiple teams", cmd_compare),
    "event":   ("Show trajectories for all teams at an event", cmd_event),
    "movers":  ("Find biggest risers/fallers in a district", cmd_movers),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("\n  THE SCOUT — EPA TRAJECTORY TRACKER")
        print("  Team 2950 The Devastators\n")
        print("  Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"    {name:10s}  {desc}")
        print()
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
