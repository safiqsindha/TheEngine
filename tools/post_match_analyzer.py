#!/usr/bin/env python3
"""
THE ENGINE — Post-Match Analyzer (F.14)
tools/post_match_analyzer.py

Unified post-match debrief: combines cycle extraction, path error analysis,
battery analysis, and autonomous decision review into a single plain-text report.

Usage:
    python tools/post_match_analyzer.py path/to/match.json

    Convert WPILOG to JSON first using AdvantageScope File → Export Data.

Output:
    Plain-text match debrief to stdout
    Optional CSV files (--csv flag)
"""

import sys
import json
import math
from pathlib import Path


# ── Thresholds ──────────────────────────────────────────────────────────────

NOMINAL_VOLTAGE = 12.5
WARNING_VOLTAGE = 11.5
CRITICAL_VOLTAGE = 11.0
PATH_ERROR_WARN_CM = 5.0
PATH_ERROR_CRIT_CM = 10.0
CYCLE_DEGRADATION_THRESHOLD = 0.15  # 15% slower in second half


# ── Log Parsing ─────────────────────────────────────────────────────────────

def load_log(filepath):
    """Load AdvantageKit JSON export."""
    with open(filepath) as f:
        return json.load(f)


def extract_keyed_series(entries, target_keys):
    """
    Extract time series for a set of keys.
    Returns dict of key → [(timestamp, value), ...]
    """
    series = {k: [] for k in target_keys}
    for entry in entries:
        key = entry.get("key", "")
        if key in series:
            series[key].append((entry.get("timestamp", 0.0), entry.get("value")))
    return series


# ── Section 1: Cycle Extraction ─────────────────────────────────────────────

def extract_cycles(entries):
    """Extract scoring cycles from superstructure state transitions."""
    cycles = []
    current_cycle = None
    cycle_num = 0

    last_x, last_y = 0.0, 0.0

    for entry in entries:
        ts = entry.get("timestamp", 0.0)
        key = entry.get("key", "")
        value = entry.get("value", "")

        if key == "Drive/Pose/x":
            last_x = float(value)
        elif key == "Drive/Pose/y":
            last_y = float(value)

        if key != "Superstructure/State":
            continue

        state = str(value)

        if state == "INTAKING" and current_cycle is None:
            cycle_num += 1
            current_cycle = {
                "num": cycle_num,
                "start": ts,
                "sx": last_x,
                "sy": last_y,
            }
        elif state == "IDLE" and current_cycle is not None:
            dx = last_x - current_cycle["sx"]
            dy = last_y - current_cycle["sy"]
            dist = math.sqrt(dx * dx + dy * dy)
            duration = ts - current_cycle["start"]
            cycles.append({
                "num": current_cycle["num"],
                "start": round(current_cycle["start"], 2),
                "end": round(ts, 2),
                "duration_s": round(duration, 2),
                "distance_m": round(dist, 2),
            })
            current_cycle = None

    return cycles


def format_cycles(cycles):
    """Format cycle data into report lines."""
    lines = []
    lines.append("SCORING CYCLES")
    lines.append("─" * 50)

    if not cycles:
        lines.append("  No completed cycles found.")
        return lines

    lines.append(f"  Total cycles: {len(cycles)}")
    durations = [c["duration_s"] for c in cycles]
    avg = sum(durations) / len(durations)
    lines.append(f"  Average cycle time: {avg:.1f}s")
    lines.append(f"  Fastest: {min(durations):.1f}s  Slowest: {max(durations):.1f}s")

    lines.append("")
    lines.append(f"  {'#':>3}  {'Start':>6}  {'End':>6}  {'Time':>5}  {'Dist':>5}")
    for c in cycles:
        lines.append(
            f"  {c['num']:>3}  {c['start']:>6.1f}  {c['end']:>6.1f}  "
            f"{c['duration_s']:>5.1f}  {c['distance_m']:>5.1f}m"
        )

    # Degradation check
    if len(cycles) >= 4:
        mid = len(durations) // 2
        first_half = sum(durations[:mid]) / mid
        second_half = sum(durations[mid:]) / (len(durations) - mid)
        change = (second_half - first_half) / first_half
        if change > CYCLE_DEGRADATION_THRESHOLD:
            lines.append("")
            lines.append(
                f"  WARNING: Cycle time degraded {change * 100:.0f}% in second half "
                f"({first_half:.1f}s -> {second_half:.1f}s)"
            )
            lines.append("  → Check battery health, mechanism wear, or thermal throttling")

    return lines


# ── Section 2: Autonomous Decision Review ───────────────────────────────────

def extract_auto_decisions(entries):
    """Extract autonomous decision log from FullAuto keys."""
    decisions = []
    current = {}

    for entry in entries:
        ts = entry.get("timestamp", 0.0)
        key = entry.get("key", "")
        value = entry.get("value", "")

        if key == "FullAuto/Status":
            status = str(value)
            if status in ("STARTING", "RETARGETING"):
                current = {"time": round(ts, 2), "status": status}
            elif status == "ARRIVED":
                current["result"] = "ARRIVED"
                current["end_time"] = round(ts, 2)
                decisions.append(current)
                current = {}
            elif status == "ABORT":
                current["result"] = "ABORTED"
                current["end_time"] = round(ts, 2)
                decisions.append(current)
                current = {}
            elif status == "NO_TARGETS":
                decisions.append({"time": round(ts, 2), "status": "NO_TARGETS", "result": "IDLE"})
            elif status in ("DONE", "INTERRUPTED"):
                if current:
                    current["result"] = status
                    current["end_time"] = round(ts, 2)
                    decisions.append(current)
                    current = {}

        elif key == "FullAuto/CurrentAction" and current:
            current["action"] = str(value)
        elif key == "FullAuto/CurrentUtility" and current:
            current["utility"] = round(float(value), 1)
        elif key == "FullAuto/AbortReason" and current:
            current["abort_reason"] = str(value)

    return decisions


def extract_fallback_events(entries):
    """Extract autonomous fallback tier changes."""
    events = []
    for entry in entries:
        key = entry.get("key", "")
        if key == "Auto/FallbackTier":
            events.append({
                "time": round(entry.get("timestamp", 0.0), 2),
                "tier": str(entry.get("value", "")),
            })
        elif key == "Auto/FallbackReason":
            events.append({
                "time": round(entry.get("timestamp", 0.0), 2),
                "reason": str(entry.get("value", "")),
            })
    return events


def format_auto_decisions(decisions, fallbacks):
    """Format autonomous decision review."""
    lines = []
    lines.append("AUTONOMOUS DECISIONS")
    lines.append("─" * 50)

    if not decisions:
        lines.append("  No autonomous decision data found.")
        return lines

    arrived = sum(1 for d in decisions if d.get("result") == "ARRIVED")
    aborted = sum(1 for d in decisions if d.get("result") == "ABORTED")
    total = len(decisions)

    lines.append(f"  Targets attempted: {total}")
    lines.append(f"  Arrived: {arrived}  Aborted: {aborted}")
    if total > 0:
        lines.append(f"  Success rate: {arrived / total * 100:.0f}%")

    lines.append("")
    for d in decisions:
        action = d.get("action", "?")
        utility = d.get("utility", "?")
        result = d.get("result", "?")
        t = d.get("time", 0)
        marker = "OK" if result == "ARRIVED" else "XX"
        line = f"  [{marker}] t={t:>5.1f}s  {action:<12} utility={utility}  → {result}"
        if "abort_reason" in d:
            line += f"\n       Reason: {d['abort_reason']}"
        lines.append(line)

    if aborted > 0:
        lines.append("")
        lines.append(f"  NOTE: {aborted} aborted target(s). Review opponent detection accuracy.")
        lines.append("  If false aborts, consider raising the abort distance threshold.")

    if fallbacks:
        lines.append("")
        lines.append("  Fallback events:")
        for f in fallbacks:
            if "tier" in f:
                lines.append(f"    t={f['time']:.1f}s  Tier → {f['tier']}")
            elif "reason" in f:
                lines.append(f"    t={f['time']:.1f}s  Reason: {f['reason']}")

    return lines


# ── Section 3: Path Error ───────────────────────────────────────────────────

def extract_path_error(entries):
    """Extract commanded vs actual pose during auto."""
    actual_poses = []
    cmd_poses = []
    auto_active = False
    ax, ay, cx, cy = 0.0, 0.0, 0.0, 0.0

    for entry in entries:
        ts = entry.get("timestamp", 0.0)
        key = entry.get("key", "")
        value = entry.get("value", 0.0)

        if key == "Robot/Phase":
            auto_active = str(value) == "AUTONOMOUS"

        if not auto_active:
            continue

        if key == "Drive/Pose/x":
            ax = float(value)
        elif key == "Drive/Pose/y":
            ay = float(value)
            actual_poses.append((ts, ax, ay))
        elif key == "Auto/CommandedPose/x":
            cx = float(value)
        elif key == "Auto/CommandedPose/y":
            cy = float(value)
            cmd_poses.append((ts, cx, cy))

    # Compute lateral errors
    errors = []
    for a_ts, a_x, a_y in actual_poses:
        closest = min(cmd_poses, key=lambda c: abs(c[0] - a_ts), default=None)
        if closest is None:
            continue
        c_ts, c_x, c_y = closest
        if abs(a_ts - c_ts) > 0.1:
            continue
        err = math.sqrt((a_x - c_x) ** 2 + (a_y - c_y) ** 2)
        errors.append((a_ts, err))

    return errors


def format_path_error(errors):
    """Format path error analysis."""
    lines = []
    lines.append("PATH FOLLOWING")
    lines.append("─" * 50)

    if not errors:
        lines.append("  No commanded vs actual pose data found during auto.")
        lines.append("  Ensure Auto/CommandedPose/x,y are logged.")
        return lines

    err_vals = [e for _, e in errors]
    max_err = max(err_vals)
    avg_err = sum(err_vals) / len(err_vals)
    rms_err = math.sqrt(sum(e ** 2 for e in err_vals) / len(err_vals))

    # Steady-state error (last 20%)
    tail = err_vals[int(len(err_vals) * 0.8):]
    ss_err = sum(tail) / len(tail) if tail else 0.0

    lines.append(f"  Data points: {len(errors)}")
    lines.append(f"  Max error:          {max_err * 100:.1f} cm")
    lines.append(f"  Average error:      {avg_err * 100:.1f} cm")
    lines.append(f"  RMS error:          {rms_err * 100:.1f} cm")
    lines.append(f"  Steady-state error: {ss_err * 100:.1f} cm")

    # Overshoot detection
    overshoots = 0
    for i in range(1, len(err_vals) - 1):
        if (err_vals[i] > err_vals[i - 1]
                and err_vals[i] > err_vals[i + 1]
                and err_vals[i] > avg_err * 1.5):
            overshoots += 1

    if overshoots > 2:
        lines.append(f"\n  WARNING: {overshoots} overshoot events detected")
        lines.append("  → Reduce Drive P gain by 10-15%, increase D gain")
    elif max_err > 0.10:
        lines.append(f"\n  WARNING: Max error {max_err * 100:.1f}cm without overshoot")
        lines.append("  → Increase Drive P gain by 10-15% or check carpet slip")

    if ss_err > 0.05:
        lines.append(f"\n  WARNING: Steady-state error {ss_err * 100:.1f}cm")
        lines.append("  → Add/increase Drive I gain or feedforward (kV)")

    if avg_err < 0.03 and overshoots == 0:
        lines.append("\n  Path following looks good. No adjustments needed.")

    return lines


# ── Section 4: Battery ──────────────────────────────────────────────────────

def extract_battery(entries):
    """Extract battery voltage time series."""
    voltage_keys = {
        "Robot/BatteryVoltage",
        "SystemStats/BatteryVoltage",
        "RoboRIO/BatteryVoltage",
        "PowerDistribution/Voltage",
    }
    data = []
    for entry in entries:
        if entry.get("key", "") in voltage_keys:
            data.append((entry.get("timestamp", 0.0), float(entry.get("value", 0.0))))
    return data


def format_battery(voltage_data):
    """Format battery analysis."""
    lines = []
    lines.append("BATTERY")
    lines.append("─" * 50)

    if not voltage_data:
        lines.append("  No battery voltage data found.")
        return lines

    voltages = [v for _, v in voltage_data]
    timestamps = [t for t, _ in voltage_data]
    min_v = min(voltages)
    max_v = max(voltages)
    avg_v = sum(voltages) / len(voltages)

    lines.append(f"  Range: {min_v:.2f}V – {max_v:.2f}V  (avg {avg_v:.2f}V)")

    # First/last 30s comparison
    t0 = timestamps[0]
    tf = timestamps[-1]
    first_30 = [v for t, v in voltage_data if t - t0 < 30]
    last_30 = [v for t, v in voltage_data if tf - t < 30]
    avg_first = sum(first_30) / len(first_30) if first_30 else avg_v
    avg_last = sum(last_30) / len(last_30) if last_30 else avg_v
    drop = avg_first - avg_last

    lines.append(f"  First 30s avg: {avg_first:.2f}V  Last 30s avg: {avg_last:.2f}V")
    lines.append(f"  Drop over match: {drop:.2f}V")

    # Sag events
    sag_count = 0
    critical_sags = 0
    in_sag = False
    sag_min = NOMINAL_VOLTAGE

    for _, v in voltage_data:
        if v < WARNING_VOLTAGE and not in_sag:
            in_sag = True
            sag_min = v
        elif v < WARNING_VOLTAGE and in_sag:
            sag_min = min(sag_min, v)
        elif v >= WARNING_VOLTAGE and in_sag:
            sag_count += 1
            if sag_min < CRITICAL_VOLTAGE:
                critical_sags += 1
            in_sag = False

    if sag_count > 0:
        lines.append(f"\n  WARNING: {sag_count} voltage sag(s) below {WARNING_VOLTAGE}V")
        if critical_sags > 0:
            lines.append(f"  CRITICAL: {critical_sags} sag(s) below {CRITICAL_VOLTAGE}V")

    if drop > 1.0:
        lines.append(f"\n  REPLACE THIS BATTERY — {drop:.1f}V drop indicates aging cells")
    elif drop > 0.5:
        lines.append(f"\n  Monitor battery — moderate {drop:.1f}V drop")
    else:
        lines.append("\n  Battery health: Good")

    return lines


# ── Section 5: Match Summary ────────────────────────────────────────────────

def extract_match_meta(entries):
    """Extract match phase timing and high-level info."""
    phases = []
    brownout = False
    match_time = None

    for entry in entries:
        key = entry.get("key", "")
        ts = entry.get("timestamp", 0.0)
        value = entry.get("value", "")

        if key == "Robot/PhaseTransitionTo":
            phases.append((ts, str(value)))
        elif key == "Robot/BrownoutActive" and bool(value):
            brownout = True
        elif key == "Robot/MatchTimeRemaining":
            match_time = float(value)

    return {"phases": phases, "brownout_occurred": brownout}


def format_match_header(meta, match_name):
    """Format the match header."""
    lines = []
    lines.append("=" * 56)
    lines.append("  THE ENGINE — Post-Match Debrief")
    lines.append(f"  Match: {match_name}")
    lines.append("=" * 56)
    lines.append("")

    if meta["phases"]:
        lines.append("MATCH TIMELINE")
        lines.append("─" * 50)
        for ts, phase in meta["phases"]:
            lines.append(f"  t={ts:>6.1f}s  → {phase}")
        if meta["brownout_occurred"]:
            lines.append("  !! BROWNOUT detected during match !!")
        lines.append("")

    return lines


# ── Section 6: Vision ───────────────────────────────────────────────────────

def extract_vision_stats(entries):
    """Extract vision subsystem performance."""
    tag_counts = []
    latencies = []
    rejections = 0

    for entry in entries:
        key = entry.get("key", "")
        value = entry.get("value", 0)

        if key == "Vision/TagCount":
            tag_counts.append(int(value))
        elif key == "Vision/LatencyMs":
            latencies.append(float(value))
        elif key == "Vision/RejectedDistM":
            rejections += 1

    return {"tag_counts": tag_counts, "latencies": latencies, "rejections": rejections}


def format_vision(stats):
    """Format vision stats."""
    lines = []
    lines.append("VISION")
    lines.append("─" * 50)

    if not stats["tag_counts"] and not stats["latencies"]:
        lines.append("  No vision data found.")
        return lines

    if stats["tag_counts"]:
        total_updates = len(stats["tag_counts"])
        multi = sum(1 for c in stats["tag_counts"] if c >= 2)
        lines.append(f"  Pose updates: {total_updates}")
        lines.append(f"  Multi-tag updates: {multi} ({multi / total_updates * 100:.0f}%)")

    if stats["latencies"]:
        avg_lat = sum(stats["latencies"]) / len(stats["latencies"])
        max_lat = max(stats["latencies"])
        lines.append(f"  Avg latency: {avg_lat:.0f}ms  Max: {max_lat:.0f}ms")

    if stats["rejections"] > 0:
        lines.append(f"  Rejected updates: {stats['rejections']} (too far from odometry)")

    return lines


# ── Recommendations ─────────────────────────────────────────────────────────

def generate_recommendations(cycles, decisions, path_errors, voltage_data):
    """Generate actionable recommendations from all analyses."""
    recs = []

    # Cycle-based recommendations
    if cycles:
        durations = [c["duration_s"] for c in cycles]
        if len(cycles) >= 4:
            mid = len(durations) // 2
            first_avg = sum(durations[:mid]) / mid
            second_avg = sum(durations[mid:]) / (len(durations) - mid)
            if (second_avg - first_avg) / first_avg > CYCLE_DEGRADATION_THRESHOLD:
                recs.append("Cycle times degraded in second half — check battery and thermal management")

    # Auto decision recommendations
    if decisions:
        aborted = sum(1 for d in decisions if d.get("result") == "ABORTED")
        total = len(decisions)
        if total > 0 and aborted / total > 0.3:
            recs.append(f"High abort rate ({aborted}/{total}) — review opponent detection thresholds")

    # Path error recommendations
    if path_errors:
        err_vals = [e for _, e in path_errors]
        rms = math.sqrt(sum(e ** 2 for e in err_vals) / len(err_vals))
        if rms * 100 > PATH_ERROR_CRIT_CM:
            recs.append(f"Path RMS error {rms * 100:.1f}cm — tune drive PID before next match")
        elif rms * 100 > PATH_ERROR_WARN_CM:
            recs.append(f"Path RMS error {rms * 100:.1f}cm — consider PID adjustment")

    # Battery recommendations
    if voltage_data:
        voltages = [v for _, v in voltage_data]
        if min(voltages) < CRITICAL_VOLTAGE:
            recs.append("Battery hit critical voltage — swap battery immediately")
        elif min(voltages) < WARNING_VOLTAGE:
            recs.append("Battery sagged below warning threshold — consider swapping")

    return recs


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/post_match_analyzer.py <match_log.json>")
        print("  Convert WPILOG to JSON first using AdvantageScope File → Export Data")
        sys.exit(1)

    input_path = sys.argv[1]
    match_name = Path(input_path).stem

    print(f"Loading {input_path}...", file=sys.stderr)
    entries = load_log(input_path)
    print(f"Loaded {len(entries)} log entries.", file=sys.stderr)

    # Extract everything
    meta = extract_match_meta(entries)
    cycles = extract_cycles(entries)
    decisions = extract_auto_decisions(entries)
    fallbacks = extract_fallback_events(entries)
    path_errors = extract_path_error(entries)
    voltage_data = extract_battery(entries)
    vision = extract_vision_stats(entries)

    # Build report
    report = []
    report.extend(format_match_header(meta, match_name))
    report.extend(format_cycles(cycles))
    report.append("")
    report.extend(format_auto_decisions(decisions, fallbacks))
    report.append("")
    report.extend(format_path_error(path_errors))
    report.append("")
    report.extend(format_battery(voltage_data))
    report.append("")
    report.extend(format_vision(vision))

    # Recommendations
    recs = generate_recommendations(cycles, decisions, path_errors, voltage_data)
    if recs:
        report.append("")
        report.append("ACTION ITEMS")
        report.append("─" * 50)
        for i, rec in enumerate(recs, 1):
            report.append(f"  {i}. {rec}")

    report.append("")
    report.append("─" * 56)
    report.append("  Generated by The Engine — post_match_analyzer.py")
    report.append("─" * 56)

    print("\n".join(report))


if __name__ == "__main__":
    main()
