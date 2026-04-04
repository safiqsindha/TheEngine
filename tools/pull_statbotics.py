#!/usr/bin/env python3
"""
THE ENGINE — Phase 5: Statbotics EPA Data Pull
tools/pull_statbotics.py

Pulls EPA (Expected Points Added) data from Statbotics for all tracked teams
across all tracked seasons. Outputs a CSV for analysis.

Requirements:
    pip install statbotics

Usage:
    python tools/pull_statbotics.py

Output:
    design-intelligence/statbotics_epa_data.csv
"""

import csv
import os

try:
    import statbotics
except ImportError:
    print("ERROR: statbotics package not installed.")
    print("Run: pip install statbotics")
    exit(1)

# Teams and seasons from TEAM_DATABASE.md
TEAMS = {
    254: "The Cheesy Poofs",
    1678: "Citrus Circuits",
    6328: "Mechanical Advantage",
    4414: "HighTide",
    2910: "Jack in the Bot",
    1323: "MadTown Robotics",
    118: "Robonauts",
    971: "Spartan Robotics",
    148: "Robowranglers",
    1690: "Orbit",
    2767: "Stryke Force",
}

SEASONS = [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025]
# Skipping 2020, 2021 (COVID — incomplete/at-home seasons)


def pull_data():
    sb = statbotics.Statbotics()
    rows = []

    for team_num, team_name in TEAMS.items():
        for year in SEASONS:
            try:
                data = sb.get_team_year(team=team_num, year=year)
                if data:
                    row = {
                        "team": team_num,
                        "team_name": team_name,
                        "year": year,
                        "epa_end": data.get("epa_end", None),
                        "auto_epa_end": data.get("auto_epa_end", None),
                        "teleop_epa_end": data.get("teleop_epa_end", None),
                        "endgame_epa_end": data.get("endgame_epa_end", None),
                        "wins": data.get("record", {}).get("wins", 0),
                        "losses": data.get("record", {}).get("losses", 0),
                        "winrate": data.get("record", {}).get("winrate", 0),
                        "rank": data.get("epa_rank", None),
                        "country_rank": data.get("country_epa_rank", None),
                    }
                    rows.append(row)
                    print(
                        f"  {team_num} ({year}): EPA={row['epa_end']}, "
                        f"W-L={row['wins']}-{row['losses']}"
                    )
                else:
                    print(f"  {team_num} ({year}): No data")
            except Exception as e:
                print(f"  {team_num} ({year}): Error - {e}")

    return rows


def write_csv(rows, output_path):
    if not rows:
        print("No data collected.")
        return

    fieldnames = [
        "team",
        "team_name",
        "year",
        "epa_end",
        "auto_epa_end",
        "teleop_epa_end",
        "endgame_epa_end",
        "wins",
        "losses",
        "winrate",
        "rank",
        "country_rank",
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} records to {output_path}")


def print_summary(rows):
    """Print a summary of top performers per season."""
    if not rows:
        return

    print("\n══════════════════════════════════════════")
    print("  TOP EPA BY SEASON")
    print("══════════════════════════════════════════")

    for year in SEASONS:
        year_rows = [r for r in rows if r["year"] == year and r["epa_end"]]
        if not year_rows:
            continue
        year_rows.sort(key=lambda r: r["epa_end"] or 0, reverse=True)
        print(f"\n  {year}:")
        for i, r in enumerate(year_rows[:5]):
            print(
                f"    {i+1}. {r['team']} {r['team_name']}: "
                f"EPA={r['epa_end']:.1f} "
                f"(Auto={r['auto_epa_end']:.1f}, "
                f"Teleop={r['teleop_epa_end']:.1f}, "
                f"Endgame={r['endgame_epa_end']:.1f})"
            )


if __name__ == "__main__":
    print("Pulling Statbotics EPA data for tracked teams...\n")
    rows = pull_data()
    output_path = "design-intelligence/statbotics_epa_data.csv"
    write_csv(rows, output_path)
    print_summary(rows)
    print("\nDone. Use this data to validate the prediction engine against historical results.")
