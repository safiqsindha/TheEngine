#!/usr/bin/env python3
"""
The Engine — The Scout
Team 2950 — The Devastators

Unified CLI for all scouting operations:
  - Pre-event reports (Layer 1)
  - Alliance selection advisor with Monte Carlo
  - Team lookup
  - Cache management

Usage:
  python3 the_scout.py report <event_key> [--team 2950] [--top 15]
  python3 the_scout.py picks  <event_key> --team 2950 [--sims 1000]
  python3 the_scout.py lookup <team_number> [--year 2025]
  python3 the_scout.py compare <event_key> --teams 2950,3005,6800
  python3 the_scout.py clear-cache
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent


def cmd_report(args):
    """Generate pre-event report."""
    from pre_event_report import build_profiles, display_report, save_report

    if not args:
        print("Usage: the_scout.py report <event_key> [--team N] [--top N]")
        return

    event_key = args[0]
    our_team = None
    top_n = 0
    year = int(event_key[:4]) if event_key[:4].isdigit() else 2025

    i = 1
    while i < len(args):
        if args[i] == "--team" and i + 1 < len(args):
            our_team = int(args[i + 1]); i += 2
        elif args[i] == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1]); i += 2
        else:
            i += 1

    profiles = build_profiles(event_key, year=year, our_team=our_team)
    display_report(profiles, event_key, our_team=our_team, top_n=top_n)
    save_report(profiles, event_key)


def cmd_picks(args):
    """Run alliance selection advisor."""
    from alliance_advisor import rank_picks, display_picks, save_picks

    if not args:
        print("Usage: the_scout.py picks <event_key> --team N [--sims N] [--top N]")
        return

    event_key = args[0]
    our_team = None
    n_sims = 1000
    top_n = 15

    i = 1
    while i < len(args):
        if args[i] == "--team" and i + 1 < len(args):
            our_team = int(args[i + 1]); i += 2
        elif args[i] == "--sims" and i + 1 < len(args):
            n_sims = int(args[i + 1]); i += 2
        elif args[i] == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1]); i += 2
        else:
            i += 1

    if not our_team:
        print("Error: --team is required for alliance picks")
        return

    candidates = rank_picks(event_key, our_team, n_sims=n_sims)
    display_picks(candidates, our_team, event_key, top_n=top_n)
    save_picks(candidates, event_key, our_team)


def cmd_lookup(args):
    """Look up a team's EPA and history."""
    from statbotics_client import get_team_year, get_team_events_in_year, epa_trend

    if not args:
        print("Usage: the_scout.py lookup <team_number> [--year 2025]")
        return

    team = int(args[0])
    year = 2025
    if len(args) > 2 and args[1] == "--year":
        year = int(args[2])

    epa = get_team_year(team, year)
    events = get_team_events_in_year(team, year)
    trend = epa_trend(events)

    print(f"\n  TEAM {epa.team} ({epa.year})")
    print(f"  {'─' * 45}")
    print(f"  EPA Total:   {epa.epa_total:6.1f}  (rank #{epa.epa_rank})")
    print(f"  EPA Auto:    {epa.epa_auto:6.1f}  ({epa.auto_pct:.0f}%)")
    print(f"  EPA Teleop:  {epa.epa_teleop:6.1f}  ({epa.teleop_pct:.0f}%)")
    print(f"  EPA Endgame: {epa.epa_endgame:6.1f}  ({epa.endgame_pct:.0f}%)")
    print(f"  Record: {epa.wins}-{epa.losses}-{epa.ties} ({epa.winrate:.0%})")
    print(f"  Trend: {trend}")
    print(f"  Events: {len(events)}")

    if events:
        print(f"\n  EVENT HISTORY:")
        for e in events:
            print(f"    {e.event:20s}  EPA={e.epa_total:6.1f}  "
                  f"(auto={e.epa_auto:.1f} teleop={e.epa_teleop:.1f} end={e.epa_endgame:.1f})")
    print()


def cmd_compare(args):
    """Compare multiple teams side-by-side at an event."""
    from statbotics_client import get_event_teams, parse_event_team

    if not args:
        print("Usage: the_scout.py compare <event_key> --teams 2950,3005,6800")
        return

    event_key = args[0]
    team_nums = []

    i = 1
    while i < len(args):
        if args[i] == "--teams" and i + 1 < len(args):
            team_nums = [int(t) for t in args[i + 1].split(",")]
            i += 2
        else:
            i += 1

    if not team_nums:
        print("Error: --teams is required")
        return

    raw = get_event_teams(event_key)
    all_epas = {t.get("team"): parse_event_team(t) for t in raw}

    print(f"\n  TEAM COMPARISON — {event_key}")
    print(f"  {'─' * 60}")
    print(f"  {'Team':>8s}  {'Total':>7s}  {'Auto':>7s}  {'Teleop':>7s}  {'Endgame':>7s}")
    print(f"  {'─' * 60}")

    for num in team_nums:
        e = all_epas.get(num)
        if e:
            print(f"  {num:>8d}  {e.epa_total:7.1f}  {e.epa_auto:7.1f}  {e.epa_teleop:7.1f}  {e.epa_endgame:7.1f}")
        else:
            print(f"  {num:>8d}  — not found at event")

    # Combined alliance EPA
    found = [all_epas[n] for n in team_nums if n in all_epas]
    if len(found) >= 2:
        total = sum(e.epa_total for e in found)
        auto = sum(e.epa_auto for e in found)
        teleop = sum(e.epa_teleop for e in found)
        endgame = sum(e.epa_endgame for e in found)
        print(f"  {'─' * 60}")
        print(f"  {'ALLIANCE':>8s}  {total:7.1f}  {auto:7.1f}  {teleop:7.1f}  {endgame:7.1f}")
    print()


def cmd_board(args):
    """Live pick board commands."""
    from pick_board import main as board_main
    # Pass through to pick_board's CLI
    import sys
    orig = sys.argv
    if not args:
        sys.argv = ["pick_board.py"]
    else:
        sys.argv = ["pick_board.py"] + list(args)
    board_main()
    sys.argv = orig


def cmd_clear_cache(args):
    """Clear all cached API responses."""
    from statbotics_client import clear_cache as clear_sb
    from tba_client import clear_cache as clear_tba
    clear_sb()
    clear_tba()


COMMANDS = {
    "report": ("Generate pre-event report", cmd_report),
    "picks": ("Alliance selection advisor", cmd_picks),
    "board": ("Live pick board (setup/pick/rec/sim)", cmd_board),
    "lookup": ("Team EPA lookup", cmd_lookup),
    "compare": ("Compare teams side-by-side", cmd_compare),
    "clear-cache": ("Clear API cache", cmd_clear_cache),
}


def main():
    print(f"\n  THE SCOUT — Team 2950 The Devastators")
    print(f"  Scouting & Match Intelligence System\n")

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"  {name:15s}  {desc}")
        print()
        print("Examples:")
        print("  python3 the_scout.py report 2025txcmp2 --team 2950 --top 15")
        print("  python3 the_scout.py picks 2025txcmp2 --team 2950 --sims 1000")
        print("  python3 the_scout.py lookup 2950 --year 2025")
        print("  python3 the_scout.py compare 2025txcmp2 --teams 2950,3005,6800")
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
