#!/usr/bin/env python3
"""
THE ENGINE — Battery Voltage Analysis
tools/battery_analysis.py

Extracts battery voltage from hoot logs (converted to JSON/WPILOG), correlates
voltage sag events with path-following error spikes, and flags matches where
voltage dropped below critical thresholds.

Usage:
    python tools/battery_analysis.py path/to/match.json

Output:
    Console report with battery health assessment
    CSV with voltage-error correlation data
"""

import sys
import json
import csv
import math
from pathlib import Path


# Thresholds
NOMINAL_VOLTAGE = 12.5
WARNING_VOLTAGE = 11.5
CRITICAL_VOLTAGE = 11.0
SAG_CORRELATION_WINDOW_S = 0.5  # Correlate voltage sag with error within this window


def parse_log(filepath):
    """Load log exported as JSON."""
    with open(filepath) as f:
        return json.load(f)


def extract_voltage_and_error(entries):
    """
    Extract battery voltage and path-following error over time.

    Looks for:
      SystemStats/BatteryVoltage or RoboRIO/BatteryVoltage
      Drive/PathError or custom lateral error log
    """
    voltage_data = []  # (timestamp, voltage)
    error_data = []  # (timestamp, error_m)

    voltage_keys = [
        "SystemStats/BatteryVoltage",
        "RoboRIO/BatteryVoltage",
        "DS/BatteryVoltage",
        "PowerDistribution/Voltage",
    ]
    error_keys = [
        "Drive/PathError",
        "Auto/LateralError",
    ]

    for entry in entries:
        ts = entry.get("timestamp", 0.0)
        key = entry.get("key", "")
        value = entry.get("value", 0.0)

        if key in voltage_keys:
            voltage_data.append((ts, float(value)))
        elif key in error_keys:
            error_data.append((ts, float(value)))

    return voltage_data, error_data


def analyze_voltage(voltage_data):
    """Analyze voltage patterns throughout the match."""
    if not voltage_data:
        print("No voltage data found in log.")
        print("Ensure battery voltage is being logged via AdvantageKit or SignalLogger.")
        return None

    voltages = [v for _, v in voltage_data]
    timestamps = [t for t, _ in voltage_data]

    min_v = min(voltages)
    max_v = max(voltages)
    avg_v = sum(voltages) / len(voltages)
    match_duration = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0

    # Find sag events (drops below warning threshold)
    sag_events = []
    in_sag = False
    sag_start = 0.0
    sag_min = NOMINAL_VOLTAGE

    for ts, v in voltage_data:
        if v < WARNING_VOLTAGE and not in_sag:
            in_sag = True
            sag_start = ts
            sag_min = v
        elif v < WARNING_VOLTAGE and in_sag:
            sag_min = min(sag_min, v)
        elif v >= WARNING_VOLTAGE and in_sag:
            sag_events.append(
                {
                    "start": round(sag_start, 2),
                    "end": round(ts, 2),
                    "duration_s": round(ts - sag_start, 2),
                    "min_voltage": round(sag_min, 2),
                }
            )
            in_sag = False

    # Voltage trend: compare first 30s average vs last 30s average
    first_30 = [v for t, v in voltage_data if t - timestamps[0] < 30]
    last_30 = [v for t, v in voltage_data if timestamps[-1] - t < 30]
    avg_first = sum(first_30) / len(first_30) if first_30 else avg_v
    avg_last = sum(last_30) / len(last_30) if last_30 else avg_v
    voltage_drop = avg_first - avg_last

    return {
        "min": round(min_v, 2),
        "max": round(max_v, 2),
        "average": round(avg_v, 2),
        "match_duration": round(match_duration, 1),
        "sag_events": sag_events,
        "voltage_drop_over_match": round(voltage_drop, 2),
        "avg_first_30s": round(avg_first, 2),
        "avg_last_30s": round(avg_last, 2),
    }


def correlate_sag_with_error(voltage_data, error_data):
    """
    Find correlation between voltage sag events and path-following error spikes.
    """
    correlations = []

    for v_ts, voltage in voltage_data:
        if voltage >= WARNING_VOLTAGE:
            continue

        # Find error data within the correlation window
        nearby_errors = [
            e
            for e_ts, e in error_data
            if abs(e_ts - v_ts) < SAG_CORRELATION_WINDOW_S
        ]

        if nearby_errors:
            max_error = max(nearby_errors)
            correlations.append(
                {
                    "timestamp": round(v_ts, 3),
                    "voltage": round(voltage, 2),
                    "max_nearby_error_m": round(max_error, 4),
                    "feedforward_compensation": round(NOMINAL_VOLTAGE / voltage, 4),
                }
            )

    return correlations


def print_report(analysis, correlations, match_name):
    """Print battery health report."""
    print("\n╔══════════════════════════════════════════════╗")
    print("║     THE ENGINE — Battery Analysis            ║")
    print("╚══════════════════════════════════════════════╝\n")
    print(f"  Match: {match_name}")
    print(f"  Duration: {analysis['match_duration']}s")
    print(f"  Voltage: {analysis['min']:.2f}V – {analysis['max']:.2f}V (avg {analysis['average']:.2f}V)")
    print(f"  Drop over match: {analysis['voltage_drop_over_match']:.2f}V")
    print(f"  First 30s avg: {analysis['avg_first_30s']:.2f}V")
    print(f"  Last 30s avg:  {analysis['avg_last_30s']:.2f}V")

    if analysis["sag_events"]:
        print(f"\n  ⚠️  {len(analysis['sag_events'])} voltage sag events below {WARNING_VOLTAGE}V:")
        for sag in analysis["sag_events"]:
            severity = "🔴 CRITICAL" if sag["min_voltage"] < CRITICAL_VOLTAGE else "🟡 WARNING"
            print(
                f"    {severity} t={sag['start']:.1f}s–{sag['end']:.1f}s "
                f"({sag['duration_s']:.1f}s) min={sag['min_voltage']:.2f}V"
            )
    else:
        print(f"\n  ✅ No voltage sags below {WARNING_VOLTAGE}V")

    if correlations:
        print(f"\n  Voltage-Error Correlations ({len(correlations)} events):")
        high_corr = [c for c in correlations if c["max_nearby_error_m"] > 0.05]
        if high_corr:
            print(f"    {len(high_corr)} sag events correlated with >5cm path error")
            avg_comp = sum(c["feedforward_compensation"] for c in high_corr) / len(high_corr)
            print(f"    → Recommended feedforward multiplier: {avg_comp:.3f}x")
            print(f"      (Add to DriveCommand: ff *= {NOMINAL_VOLTAGE} / currentVoltage)")

    if analysis["voltage_drop_over_match"] > 1.0:
        print("\n  🔋 Battery recommendation: REPLACE THIS BATTERY")
        print(f"     {analysis['voltage_drop_over_match']:.1f}V drop indicates aging cells")
    elif analysis["voltage_drop_over_match"] > 0.5:
        print("\n  🔋 Battery recommendation: Monitor — moderate voltage drop")
    else:
        print("\n  🔋 Battery health: Good")

    print("")


def write_correlation_csv(correlations, output_path):
    """Write voltage-error correlation data."""
    if not correlations:
        return

    fieldnames = [
        "timestamp",
        "voltage",
        "max_nearby_error_m",
        "feedforward_compensation",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(correlations)

    print(f"Correlation data written to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/battery_analysis.py <log_file.json>")
        sys.exit(1)

    input_path = sys.argv[1]
    match_name = Path(input_path).stem

    print(f"Parsing {input_path}...")
    entries = parse_log(input_path)
    voltage_data, error_data = extract_voltage_and_error(entries)
    analysis = analyze_voltage(voltage_data)

    if analysis:
        correlations = correlate_sag_with_error(voltage_data, error_data)
        print_report(analysis, correlations, match_name)

        output_path = input_path.replace(".json", "_battery.csv")
        write_correlation_csv(correlations, output_path)
