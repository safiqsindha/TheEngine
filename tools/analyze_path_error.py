#!/usr/bin/env python3
"""
THE ENGINE — Path Error Analysis
tools/analyze_path_error.py

Compares commanded vs actual robot pose during autonomous trajectory following.
Identifies overshoot, lateral error, and settling time. Recommends PID adjustments.

Usage:
    python tools/analyze_path_error.py path/to/match.json

Output:
    Console report with PID recommendations
    CSV file with per-waypoint error data
"""

import sys
import json
import csv
import math
from pathlib import Path


def parse_log(filepath):
    """Load AdvantageKit log exported as JSON."""
    with open(filepath) as f:
        return json.load(f)


def extract_trajectory_data(entries):
    """
    Extract commanded and actual poses during autonomous.

    Looks for:
      Drive/Pose/x, Drive/Pose/y — actual robot position
      Auto/CommandedPose/x, Auto/CommandedPose/y — where the robot should be
      Auto/Active — whether autonomous is running
    """
    actual_poses = []  # (timestamp, x, y)
    commanded_poses = []  # (timestamp, x, y)
    auto_active = False

    actual_x, actual_y = 0.0, 0.0
    cmd_x, cmd_y = 0.0, 0.0

    for entry in entries:
        ts = entry.get("timestamp", 0.0)
        key = entry.get("key", "")
        value = entry.get("value", 0.0)

        if key == "Auto/Active":
            auto_active = bool(value)

        if not auto_active:
            continue

        if key == "Drive/Pose/x":
            actual_x = float(value)
        elif key == "Drive/Pose/y":
            actual_y = float(value)
            actual_poses.append((ts, actual_x, actual_y))
        elif key == "Auto/CommandedPose/x":
            cmd_x = float(value)
        elif key == "Auto/CommandedPose/y":
            cmd_y = float(value)
            commanded_poses.append((ts, cmd_x, cmd_y))

    return actual_poses, commanded_poses


def compute_errors(actual_poses, commanded_poses):
    """
    Compute lateral error between actual and commanded poses.
    Matches by closest timestamp.
    """
    errors = []

    for a_ts, a_x, a_y in actual_poses:
        # Find closest commanded pose by timestamp
        closest = min(commanded_poses, key=lambda c: abs(c[0] - a_ts), default=None)
        if closest is None:
            continue

        c_ts, c_x, c_y = closest
        if abs(a_ts - c_ts) > 0.1:
            continue  # Too far apart in time

        lateral_error = math.sqrt((a_x - c_x) ** 2 + (a_y - c_y) ** 2)
        errors.append(
            {
                "timestamp": a_ts,
                "actual_x": round(a_x, 4),
                "actual_y": round(a_y, 4),
                "commanded_x": round(c_x, 4),
                "commanded_y": round(c_y, 4),
                "lateral_error_m": round(lateral_error, 4),
            }
        )

    return errors


def analyze_and_recommend(errors):
    """Analyze error patterns and recommend PID adjustments."""
    if not errors:
        print("No trajectory data found during autonomous.")
        return

    lateral_errors = [e["lateral_error_m"] for e in errors]
    max_error = max(lateral_errors)
    avg_error = sum(lateral_errors) / len(lateral_errors)
    rms_error = math.sqrt(sum(e**2 for e in lateral_errors) / len(lateral_errors))

    # Detect overshoot: error peaks followed by correction
    overshoots = []
    for i in range(1, len(lateral_errors) - 1):
        if (
            lateral_errors[i] > lateral_errors[i - 1]
            and lateral_errors[i] > lateral_errors[i + 1]
            and lateral_errors[i] > avg_error * 1.5
        ):
            overshoots.append(
                {"timestamp": errors[i]["timestamp"], "error": lateral_errors[i]}
            )

    # Detect steady-state error: persistent error in the last 20% of trajectory
    last_20_pct = lateral_errors[int(len(lateral_errors) * 0.8) :]
    steady_state_error = sum(last_20_pct) / len(last_20_pct) if last_20_pct else 0.0

    print("\n╔══════════════════════════════════════════════╗")
    print("║     THE ENGINE — Path Error Analysis         ║")
    print("╚══════════════════════════════════════════════╝\n")

    print(f"  Data points: {len(errors)}")
    print(f"  Max lateral error:    {max_error * 100:.1f} cm")
    print(f"  Average lateral error: {avg_error * 100:.1f} cm")
    print(f"  RMS error:            {rms_error * 100:.1f} cm")
    print(f"  Steady-state error:   {steady_state_error * 100:.1f} cm")
    print(f"  Overshoot events:     {len(overshoots)}")

    print("\n── PID Recommendations ──\n")

    if len(overshoots) > 2:
        print("  ⚠️  Multiple overshoots detected.")
        print("     → REDUCE Drive P gain by 10-15%")
        print("     → INCREASE Drive D gain (add damping)")
        print(
            f"     Largest overshoot: {max(o['error'] for o in overshoots) * 100:.1f} cm"
        )
    elif max_error > 0.10:
        print("  ⚠️  Large max error without overshoot.")
        print("     → INCREASE Drive P gain by 10-15%")
        print("     → Check if robot is slipping (carpet friction)")

    if steady_state_error > 0.05:
        print(f"\n  ⚠️  Steady-state error: {steady_state_error * 100:.1f} cm")
        print("     → Add or INCREASE Drive I gain (small value, e.g., 0.0001)")
        print("     → Or increase Drive feedforward (kV)")

    if avg_error < 0.03 and len(overshoots) == 0:
        print("  ✅ Path following looks good! No adjustments needed.")

    print("")


def write_error_csv(errors, output_path):
    """Write per-timestamp error data to CSV."""
    if not errors:
        return

    fieldnames = [
        "timestamp",
        "actual_x",
        "actual_y",
        "commanded_x",
        "commanded_y",
        "lateral_error_m",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(errors)

    print(f"Error data written to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/analyze_path_error.py <log_file.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    print(f"Parsing {input_path}...")

    entries = parse_log(input_path)
    actual, commanded = extract_trajectory_data(entries)
    errors = compute_errors(actual, commanded)

    analyze_and_recommend(errors)

    output_path = input_path.replace(".json", "_path_errors.csv")
    write_error_csv(errors, output_path)
