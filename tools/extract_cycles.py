#!/usr/bin/env python3
"""
THE ENGINE — Cycle Time Extraction
tools/extract_cycles.py

Parses an AdvantageKit WPILOG file and identifies FUEL scoring cycles.
A cycle = intake start → FUEL acquired → drive to HUB → FUEL scored.

Usage:
    python tools/extract_cycles.py path/to/match.wpilog

Output:
    CSV file with columns: match, cycle_number, start_time, end_time,
    duration_sec, fuel_scored, hub_was_active, distance_m

Requires: pip install wpilog  (or parse manually — WPILOG is a binary format)
"""

import sys
import csv
import json
import os
from pathlib import Path

# WPILOG parsing — lightweight implementation
# In production, use the wpiutil WPILOG reader or convert to JSON first


def parse_wpilog_json(filepath):
    """
    Parse a WPILOG file that has been converted to JSON format.
    Use AdvantageScope's export or CTRE's owlet tool to convert.

    Expected structure: list of entries with timestamp, key, value
    """
    with open(filepath) as f:
        return json.load(f)


def extract_cycles_from_log(log_entries, match_name="unknown"):
    """
    Extract scoring cycles from AdvantageKit log entries.

    Looks for state transitions in the SuperstructureStateMachine log:
      IDLE → INTAKING (cycle start)
      INTAKING → STAGING (FUEL acquired)
      STAGING → SCORING (drive to HUB complete, scoring)
      SCORING → IDLE (cycle end, FUEL scored)

    Also tracks:
      - HUB active status at score time
      - Robot pose at cycle start vs end (distance traveled)
    """
    cycles = []
    current_cycle = None
    cycle_number = 0

    # Key names to look for in AdvantageKit logs
    STATE_KEY = "Superstructure/State"
    HUB_ACTIVE_KEY = "GameState/HubActive"
    POSE_X_KEY = "Drive/Pose/x"
    POSE_Y_KEY = "Drive/Pose/y"

    last_pose_x = 0.0
    last_pose_y = 0.0
    hub_active = True

    for entry in log_entries:
        timestamp = entry.get("timestamp", 0.0)
        key = entry.get("key", "")
        value = entry.get("value", "")

        # Track pose
        if key == POSE_X_KEY:
            last_pose_x = float(value)
        elif key == POSE_Y_KEY:
            last_pose_y = float(value)
        elif key == HUB_ACTIVE_KEY:
            hub_active = bool(value)

        # Track state transitions
        if key == STATE_KEY:
            state = str(value)

            if state == "INTAKING" and current_cycle is None:
                cycle_number += 1
                current_cycle = {
                    "match": match_name,
                    "cycle_number": cycle_number,
                    "start_time": timestamp,
                    "start_x": last_pose_x,
                    "start_y": last_pose_y,
                }

            elif state == "SCORING" and current_cycle is not None:
                current_cycle["hub_was_active"] = hub_active

            elif state == "IDLE" and current_cycle is not None:
                # Cycle complete
                import math
                dx = last_pose_x - current_cycle["start_x"]
                dy = last_pose_y - current_cycle["start_y"]
                distance = math.sqrt(dx * dx + dy * dy)

                current_cycle["end_time"] = timestamp
                current_cycle["duration_sec"] = round(
                    timestamp - current_cycle["start_time"], 3
                )
                current_cycle["fuel_scored"] = True
                current_cycle["hub_was_active"] = current_cycle.get(
                    "hub_was_active", True
                )
                current_cycle["distance_m"] = round(distance, 2)

                # Remove internal tracking fields
                del current_cycle["start_x"]
                del current_cycle["start_y"]

                cycles.append(current_cycle)
                current_cycle = None

    return cycles


def write_csv(cycles, output_path):
    """Write extracted cycles to CSV."""
    if not cycles:
        print("No cycles found in log.")
        return

    fieldnames = [
        "match",
        "cycle_number",
        "start_time",
        "end_time",
        "duration_sec",
        "fuel_scored",
        "hub_was_active",
        "distance_m",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cycles)

    print(f"Wrote {len(cycles)} cycles to {output_path}")

    # Print summary
    durations = [c["duration_sec"] for c in cycles]
    avg = sum(durations) / len(durations)
    print(f"  Average cycle time: {avg:.2f}s")
    print(f"  Min: {min(durations):.2f}s  Max: {max(durations):.2f}s")

    if len(cycles) >= 2:
        first_half = durations[: len(durations) // 2]
        second_half = durations[len(durations) // 2 :]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        degradation = (avg_second - avg_first) / avg_first * 100
        if degradation > 15:
            print(
                f"  ⚠️  ALERT: Cycle time increased {degradation:.0f}% in second half!"
            )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/extract_cycles.py <log_file.json>")
        print("  Convert WPILOG to JSON first using AdvantageScope export")
        sys.exit(1)

    input_path = sys.argv[1]
    match_name = Path(input_path).stem

    print(f"Parsing {input_path}...")
    entries = parse_wpilog_json(input_path)
    cycles = extract_cycles_from_log(entries, match_name)

    output_path = input_path.replace(".json", "_cycles.csv")
    write_csv(cycles, output_path)
