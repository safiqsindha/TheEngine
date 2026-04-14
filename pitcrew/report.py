"""
pitcrew/report.py — Generate a human-readable match report from a DSLogAnalysis.

Output is Markdown text a pit crew member can read in 30 seconds.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pitcrew.dslog import DSLogAnalysis, LOW_VOLTAGE_WARN, BROWNOUT_VOLTAGE


def _match_label(analysis: DSLogAnalysis) -> str:
    """Return a best-effort match label (e.g. 'QM01 — 2950')."""
    if analysis.match_info and analysis.match_info.get("match_name"):
        return analysis.match_info["match_name"]
    return Path(analysis.source_path).stem


def _voltage_section(analysis: DSLogAnalysis) -> str:
    v = analysis.voltage
    tl = analysis.timeline
    records = analysis.records

    if not records:
        return "Battery: no data\n"

    start_v = records[0].get("voltage", 0.0)
    end_v = records[-1].get("voltage", 0.0)

    # Find peak-low during autonomous
    auto_voltages = []
    for seg_start, seg_end, mode in tl.segments:
        if mode == "auto":
            for r in records[seg_start : seg_end + 1]:
                auto_voltages.append(r.get("voltage", 99.0))

    auto_min_str = ""
    if auto_voltages:
        auto_min = min(auto_voltages)
        auto_min_str = f", auto low {auto_min:.1f}V"

    # Determine worst voltage cycle label
    cycle_note = ""
    if v.min_voltage_idx > 0:
        # Estimate cycle by finding which enabled segment we're in
        seg_num = 0
        for i, (seg_start, seg_end, _) in enumerate(tl.segments):
            if seg_start <= v.min_voltage_idx <= seg_end:
                seg_num = i + 1
                break
        if seg_num:
            cycle_note = f" during cycle {seg_num}"

    line = (
        f"Battery: {start_v:.1f}V → {end_v:.1f}V "
        f"(peaked low at {v.minimum:.1f}V{cycle_note}{auto_min_str})"
    )
    return line


def _brownout_section(analysis: DSLogAnalysis) -> str:
    count = analysis.voltage.brownout_count
    if count == 0:
        return "Brownouts: 0"
    return f"Brownouts: {count}  *** ATTENTION — SWAP BATTERY IMMEDIATELY ***"


def _can_section(analysis: DSLogAnalysis) -> str:
    c = analysis.can
    util_pct = c.average_utilization * 100
    max_pct = c.max_utilization * 100
    loss_pct = c.packet_loss_fraction * 100

    warnings = 0
    critical = 0
    # CAN utilization > 90% = warning; packet_loss > 10% = critical
    if max_pct > 90:
        critical += 1
    elif max_pct > 70:
        warnings += 1

    if loss_pct > 10:
        critical += 1
    elif loss_pct > 0:
        warnings += 1

    detail = f"avg {util_pct:.0f}% util, max {max_pct:.0f}%"
    if c.packet_loss_count > 0:
        detail += f", {loss_pct:.1f}% packet loss"

    return f"CAN: {warnings} warning(s), {critical} critical — {detail}"


def _timeline_section(analysis: DSLogAnalysis) -> str:
    tl = analysis.timeline
    lines = []

    auto_s = tl.auto_seconds
    tele_s = tl.teleop_seconds
    disabled_s = tl.disabled_seconds

    if auto_s > 0:
        lines.append(f"Auto: {auto_s:.1f}s")
    if tele_s > 0:
        lines.append(f"Teleop: {tele_s:.1f}s")

    # Flag unexpected disabled gaps (> 0.5s during what should be match time)
    total_match = auto_s + tele_s
    if total_match > 10 and disabled_s > 0.5:
        lines.append(f"Disabled gaps: {disabled_s:.1f}s (unexpected — check comms)")

    if tl.estop_detected:
        lines.append("E-STOP detected!")

    return "Timeline: " + " | ".join(lines) if lines else "Timeline: no enabled time recorded"


def _disconnect_section(analysis: DSLogAnalysis) -> str:
    trip = analysis.trip
    if trip.disconnect_seconds > 0:
        return f"DS Disconnects: {trip.disconnect_seconds:.1f}s total ({len(trip.disconnect_segments)} segment(s))"
    return "DS Disconnects: none"


def _errors_section(analysis: DSLogAnalysis) -> str:
    counts = analysis.errors.message_counts
    if not counts:
        return "Errors/Warnings: none logged"

    top = list(counts.items())[:5]  # Show top 5
    parts = [f"{msg[:60]} ({cnt})" for msg, cnt in top]
    return "Top errors:\n" + "\n".join(f"  - {p}" for p in parts)


def generate(analysis: DSLogAnalysis, team: str = "2950") -> str:
    """
    Generate a markdown match report from a DSLogAnalysis.

    Returns a string suitable for stdout or writing to a .md file.
    """
    label = _match_label(analysis)

    # Estimate final score from match info if available (placeholder)
    score_label = ""
    if analysis.match_info:
        score_label = f"  |  Match: {label}"
    else:
        score_label = f"  |  File: {Path(analysis.source_path).name}"

    lines = [
        f"# DS Log Report — Team {team}{score_label}",
        "",
        _voltage_section(analysis),
        _brownout_section(analysis),
        _can_section(analysis),
        _timeline_section(analysis),
        _disconnect_section(analysis),
        "",
        _errors_section(analysis),
    ]

    rtt = analysis.trip.avg_round_trip_ms
    if rtt > 0:
        lines.append(f"\nRound-trip latency: avg {rtt:.1f}ms, max {analysis.trip.max_round_trip_ms:.1f}ms")

    lines.append(f"\nRecords: {analysis.trip.total_records} ({analysis.trip.total_seconds:.0f}s log duration)")

    return "\n".join(lines)


def generate_batch_table(analyses: list[DSLogAnalysis], team: str = "2950") -> str:
    """
    Generate a comparison table for multiple logs (batch mode).
    """
    if not analyses:
        return "No logs to display."

    header = (
        "| File | Volt Min | Brownouts | CAN Avg% | Auto(s) | Tele(s) | Disconnects | Top Error |\n"
        "|------|----------|-----------|----------|---------|---------|-------------|-----------|"
    )
    rows = [header]

    for a in analyses:
        fname = Path(a.source_path).name
        v = a.voltage
        c = a.can
        tl = a.timeline
        trip = a.trip

        top_err = ""
        if a.errors.message_counts:
            first_msg = next(iter(a.errors.message_counts))
            top_err = first_msg[:30] + ("..." if len(first_msg) > 30 else "")

        rows.append(
            f"| {fname} "
            f"| {v.minimum:.2f}V "
            f"| {v.brownout_count} "
            f"| {c.average_utilization * 100:.0f}% "
            f"| {tl.auto_seconds:.1f} "
            f"| {tl.teleop_seconds:.1f} "
            f"| {trip.disconnect_seconds:.1f}s "
            f"| {top_err} |"
        )

    return f"# Batch DS Log Report — Team {team}\n\n" + "\n".join(rows)
