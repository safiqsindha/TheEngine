"""
pitcrew/dslog.py — Analysis layer on top of dslogparser.

Wraps LigerBots' dslogparser (MIT, https://github.com/ligerbots/dslogparser)
with drive-team-useful diagnostics: voltage, CAN, enabled/disabled timeline,
errors, and a trip-computer summary.
"""

from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

from dslogparser.dslogparser import DSEventParser, DSLogParser

# Each record is 20 ms apart (DSLOG_TIMESTEP = 0.020)
TIMESTEP_S = 0.020

# Voltage thresholds
BROWNOUT_VOLTAGE = 6.8        # RoboRIO brownout threshold (volts)
LOW_VOLTAGE_WARN = 11.0       # Yellow flag for drive team


@dataclass
class VoltageStats:
    minimum: float = 0.0
    maximum: float = 0.0
    average: float = 0.0
    brownout_count: int = 0
    low_voltage_count: int = 0  # records below LOW_VOLTAGE_WARN
    # (voltage, record_index) pairs for each brownout
    brownout_events: List[Tuple[float, int]] = field(default_factory=list)
    # Min voltage and the index at which it occurred
    min_voltage_idx: int = 0


@dataclass
class CANStats:
    average_utilization: float = 0.0
    max_utilization: float = 0.0
    # Fraction of records with packet_loss > 0
    packet_loss_fraction: float = 0.0
    # Number of records with packet_loss > 0
    packet_loss_count: int = 0
    # Approximate total seconds with packet loss
    packet_loss_seconds: float = 0.0


@dataclass
class EnabledTimeline:
    total_enabled_seconds: float = 0.0
    auto_seconds: float = 0.0
    teleop_seconds: float = 0.0
    disabled_seconds: float = 0.0
    estop_detected: bool = False
    # List of (start_index, end_index, mode) for each enabled segment
    segments: List[Tuple[int, int, str]] = field(default_factory=list)


@dataclass
class ErrorSummary:
    # List of (timestamp, message) for each event-log entry during enabled periods
    enabled_messages: List[Tuple[datetime.datetime, str]] = field(default_factory=list)
    # {message_text: count} after deduplication
    message_counts: dict[str, int] = field(default_factory=dict)
    # All messages (not filtered to enabled)
    all_messages: List[Tuple[datetime.datetime, str]] = field(default_factory=list)


@dataclass
class TripComputer:
    total_records: int = 0
    total_seconds: float = 0.0
    # Number of records where robot was disconnected from DS
    # (robot_disabled=True AND ds_disabled=False means DS sees robot but it is disabled;
    #  packet_loss >= 100% means DS cannot reach robot)
    disconnect_count: int = 0
    disconnect_seconds: float = 0.0
    # Contiguous disconnect segments as (start_idx, end_idx)
    disconnect_segments: List[Tuple[int, int]] = field(default_factory=list)
    max_round_trip_ms: float = 0.0
    avg_round_trip_ms: float = 0.0


@dataclass
class DSLogAnalysis:
    """Complete analysis result for a single DS log file."""

    source_path: str = ""
    match_info: Optional[dict[str, Any]] = None  # from find_match_info on paired .dsevents

    records: List[dict[str, Any]] = field(default_factory=list)  # raw records from dslogparser
    voltage: VoltageStats = field(default_factory=VoltageStats)
    can: CANStats = field(default_factory=CANStats)
    timeline: EnabledTimeline = field(default_factory=EnabledTimeline)
    errors: ErrorSummary = field(default_factory=ErrorSummary)
    trip: TripComputer = field(default_factory=TripComputer)


def _find_events_file(log_path: Path) -> Optional[Path]:
    """Given foo.dslog, look for a paired foo.dsevents in the same directory."""
    stem = log_path.stem
    candidates = [
        log_path.with_suffix(".dsevents"),
        log_path.parent / (stem + ".dsevents"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _load_event_messages(events_path: Path) -> List[Tuple[datetime.datetime, str]]:
    """Parse a .dsevents file and return [(timestamp, message), ...]."""
    parser = DSEventParser(str(events_path))
    msgs = []
    try:
        for rec in parser.read_records():
            msgs.append((rec["time"], rec["message"]))
    finally:
        parser.close()
    return msgs


def _analyze_voltage(records: List[dict[str, Any]]) -> VoltageStats:
    stats = VoltageStats()
    if not records:
        return stats

    voltages = [r["voltage"] for r in records]
    stats.minimum = min(voltages)
    stats.maximum = max(voltages)
    stats.average = sum(voltages) / len(voltages)
    stats.min_voltage_idx = voltages.index(stats.minimum)

    for idx, (r, v) in enumerate(zip(records, voltages)):
        if r.get("brownout", False):
            stats.brownout_count += 1
            stats.brownout_events.append((v, idx))
        if v < LOW_VOLTAGE_WARN:
            stats.low_voltage_count += 1

    return stats


def _analyze_can(records: List[dict[str, Any]]) -> CANStats:
    stats = CANStats()
    if not records:
        return stats

    usages = [r.get("can_usage", 0.0) for r in records]
    losses = [r.get("packet_loss", 0.0) for r in records]

    stats.average_utilization = sum(usages) / len(usages)
    stats.max_utilization = max(usages)
    stats.packet_loss_count = sum(1 for pl in losses if pl > 0)
    stats.packet_loss_fraction = stats.packet_loss_count / len(records)
    stats.packet_loss_seconds = stats.packet_loss_count * TIMESTEP_S

    return stats


def _analyze_timeline(records: List[dict[str, Any]]) -> EnabledTimeline:
    tl = EnabledTimeline()
    if not records:
        return tl

    for r in records:
        auto = r.get("robot_auto", False)
        tele = r.get("robot_tele", False)
        disabled = r.get("robot_disabled", True)
        watchdog = r.get("watchdog", False)

        if watchdog:
            tl.estop_detected = True

        if auto:
            tl.auto_seconds += TIMESTEP_S
            tl.total_enabled_seconds += TIMESTEP_S
        elif tele:
            tl.teleop_seconds += TIMESTEP_S
            tl.total_enabled_seconds += TIMESTEP_S
        else:
            tl.disabled_seconds += TIMESTEP_S

    # Build enabled segments
    segments = []
    in_segment = False
    seg_start = 0
    seg_mode = "disabled"
    for idx, r in enumerate(records):
        if r.get("robot_auto", False):
            mode = "auto"
        elif r.get("robot_tele", False):
            mode = "teleop"
        else:
            mode = "disabled"

        if mode != "disabled" and not in_segment:
            in_segment = True
            seg_start = idx
            seg_mode = mode
        elif mode == "disabled" and in_segment:
            segments.append((seg_start, idx - 1, seg_mode))
            in_segment = False
        elif mode != "disabled" and in_segment and mode != seg_mode:
            # mode transition within enabled
            segments.append((seg_start, idx - 1, seg_mode))
            seg_start = idx
            seg_mode = mode

    if in_segment:
        segments.append((seg_start, len(records) - 1, seg_mode))

    tl.segments = segments
    return tl


def _analyze_errors(
    records: List[dict[str, Any]],
    all_messages: List[Tuple[datetime.datetime, str]],
    timeline: EnabledTimeline,
) -> ErrorSummary:
    summary = ErrorSummary()
    summary.all_messages = all_messages

    if not records:
        return summary

    # Build set of timestamps covering enabled periods
    enabled_times: set[datetime.datetime] = set()
    for seg_start, seg_end, _ in timeline.segments:
        for idx in range(seg_start, seg_end + 1):
            t = records[idx].get("time")
            if t:
                # Round to nearest 5-second window to allow fuzzy matching with event log
                enabled_times.add(t.replace(second=t.second // 5 * 5, microsecond=0))

    # Filter event messages to those that occurred during enabled periods
    # (using a generous ±2-second window since clock skew can exist)
    for ts, msg in all_messages:
        ts_rounded = ts.replace(second=ts.second // 5 * 5, microsecond=0)
        if ts_rounded in enabled_times:
            summary.enabled_messages.append((ts, msg))

    # If no enabled messages found, include all (better than empty)
    if not summary.enabled_messages:
        summary.enabled_messages = list(all_messages)

    # Deduplicate and count
    counts: dict[str, int] = {}
    for _, msg in summary.enabled_messages:
        # Normalize: strip timestamps and memory addresses
        normalized = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", msg).strip()
        counts[normalized] = counts.get(normalized, 0) + 1

    summary.message_counts = dict(
        sorted(counts.items(), key=lambda x: x[1], reverse=True)
    )
    return summary


def _analyze_trip(records: List[dict[str, Any]]) -> TripComputer:
    trip = TripComputer()
    if not records:
        return trip

    trip.total_records = len(records)
    trip.total_seconds = len(records) * TIMESTEP_S

    rtt_vals = [r.get("round_trip_time", 0.0) for r in records]
    trip.max_round_trip_ms = max(rtt_vals) * 1000
    trip.avg_round_trip_ms = (sum(rtt_vals) / len(rtt_vals)) * 1000

    # Detect disconnect events: packet_loss == 100% (value 1.0 after scaling)
    # dslogparser scales packet_loss as 0.04 * raw, max raw=255 → ~10.2
    # A full disconnect shows up as 100% = value 4.0 per dslogparser scaling
    # In practice, packet_loss > 0 means some loss; > 2.0 is severe
    in_disconnect = False
    seg_start = 0
    for idx, r in enumerate(records):
        pl = r.get("packet_loss", 0.0)
        is_disconnected = pl >= 4.0  # ~100% loss

        if is_disconnected and not in_disconnect:
            in_disconnect = True
            seg_start = idx
        elif not is_disconnected and in_disconnect:
            trip.disconnect_segments.append((seg_start, idx - 1))
            in_disconnect = False

    if in_disconnect:
        trip.disconnect_segments.append((seg_start, len(records) - 1))

    trip.disconnect_count = sum(e - s + 1 for s, e in trip.disconnect_segments)
    trip.disconnect_seconds = trip.disconnect_count * TIMESTEP_S

    return trip


def analyze(log_path: str | Path) -> DSLogAnalysis:
    """
    Parse a .dslog file and return a DSLogAnalysis with all diagnostics.

    Automatically looks for a paired .dsevents file in the same directory.
    """
    log_path = Path(log_path)
    if not log_path.exists():
        raise FileNotFoundError(f"DS log file not found: {log_path}")

    analysis = DSLogAnalysis(source_path=str(log_path))

    # Parse the binary log
    parser = DSLogParser(str(log_path))
    try:
        analysis.records = list(parser.read_records())
    finally:
        parser.close()

    # Look for paired events file
    events_path = _find_events_file(log_path)
    all_messages: List[Tuple[datetime.datetime, str]] = []
    if events_path:
        all_messages = _load_event_messages(events_path)
        analysis.match_info = DSEventParser.find_match_info(str(events_path))

    # Run all analyses
    analysis.voltage = _analyze_voltage(analysis.records)
    analysis.can = _analyze_can(analysis.records)
    analysis.timeline = _analyze_timeline(analysis.records)
    analysis.errors = _analyze_errors(analysis.records, all_messages, analysis.timeline)
    analysis.trip = _analyze_trip(analysis.records)

    return analysis


def batch_analyze(directory: str | Path) -> List[DSLogAnalysis]:
    """
    Analyze all .dslog files in a directory.
    Returns a list of DSLogAnalysis objects sorted by filename.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    log_files = sorted(directory.glob("*.dslog"))
    results = []
    for lf in log_files:
        try:
            results.append(analyze(lf))
        except Exception as exc:  # noqa: BLE001 — binary DSLog format; any struct/IO error is valid
            # Don't let one bad file kill the batch — surface as partial result
            a = DSLogAnalysis(source_path=str(lf))
            a.errors.all_messages = [(datetime.datetime.now(), f"PARSE ERROR: {exc}")]
            results.append(a)
    return results
