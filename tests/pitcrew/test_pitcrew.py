"""
tests/pitcrew/test_pitcrew.py

Synthetic-fixture tests for pitcrew.dslog, pitcrew.report, and pitcrew.cli.
All fixtures are in-memory dicts matching the record shape produced by
dslogparser.dslogparser.DSLogParser.read_record_v3 — no real .dslog file required.

Record fields used by pitcrew:
  time           datetime  timestamp
  voltage        float     battery voltage (V)
  brownout       bool      RoboRIO brownout flag
  packet_loss    float     DS packet-loss (0.04 * raw; 4.0 ≈ 100%)
  can_usage      float     CAN bus utilisation fraction (0.0–1.0)
  round_trip_time float    DS round-trip time (seconds)
  robot_auto     bool      robot in autonomous mode
  robot_tele     bool      robot in teleop mode
  robot_disabled bool      robot is disabled
  watchdog       bool      watchdog/e-stop fired
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parents[2]))

from pitcrew.dslog import (
    DSLogAnalysis,
    VoltageStats,
    CANStats,
    EnabledTimeline,
    ErrorSummary,
    TripComputer,
    _analyze_voltage,
    _analyze_can,
    _analyze_timeline,
    _analyze_errors,
    _analyze_trip,
    BROWNOUT_VOLTAGE,
    LOW_VOLTAGE_WARN,
    TIMESTEP_S,
)
from pitcrew.report import generate, generate_batch_table
from pitcrew.cli import main


# ---------------------------------------------------------------------------
# Helpers: synthetic record factories
# ---------------------------------------------------------------------------

_BASE_TIME = datetime.datetime(2026, 4, 12, 10, 0, 0, tzinfo=datetime.timezone.utc)


def _make_record(
    idx: int = 0,
    voltage: float = 12.5,
    brownout: bool = False,
    packet_loss: float = 0.0,
    can_usage: float = 0.3,
    round_trip_time: float = 0.02,
    robot_auto: bool = False,
    robot_tele: bool = False,
    robot_disabled: bool = True,
    watchdog: bool = False,
) -> dict:
    return {
        "time": _BASE_TIME + datetime.timedelta(seconds=idx * TIMESTEP_S),
        "voltage": voltage,
        "brownout": brownout,
        "packet_loss": packet_loss,
        "can_usage": can_usage,
        "round_trip_time": round_trip_time,
        "robot_auto": robot_auto,
        "robot_tele": robot_tele,
        "robot_disabled": robot_disabled,
        "watchdog": watchdog,
    }


def _make_match_records() -> list[dict]:
    """
    150 records (~3 s) simulating:
      - 0..49   disabled (startup)
      - 50..99  autonomous
      - 100..149 teleop
    Voltage sawtooth: starts 12.5, dips to 10.8 at idx=75, recovers.
    One brownout at idx=90 (6.5 V).
    """
    records = []
    for i in range(150):
        auto = 50 <= i < 100
        tele = 100 <= i < 150
        disabled = not (auto or tele)

        # Voltage profile
        if i == 90:
            v = 6.5  # brownout
        elif 70 <= i <= 100:
            v = 10.8  # low but not brownout
        else:
            v = 12.5

        records.append(
            _make_record(
                idx=i,
                voltage=v,
                brownout=(i == 90),
                can_usage=0.5 if auto else 0.3,
                round_trip_time=0.01 if tele else 0.02,
                robot_auto=auto,
                robot_tele=tele,
                robot_disabled=disabled,
            )
        )
    return records


def _make_full_analysis(records=None) -> DSLogAnalysis:
    if records is None:
        records = _make_match_records()
    a = DSLogAnalysis(source_path="/fake/2026-04-12_10-00-00.dslog")
    a.records = records
    a.voltage = _analyze_voltage(records)
    a.can = _analyze_can(records)
    a.timeline = _analyze_timeline(records)
    a.errors = _analyze_errors(records, [], a.timeline)
    a.trip = _analyze_trip(records)
    return a


# ---------------------------------------------------------------------------
# 1. Voltage stats: min, max, mean
# ---------------------------------------------------------------------------

class TestAnalyzeVoltage:
    def test_basic_stats(self):
        records = [_make_record(idx=i, voltage=v) for i, v in enumerate([12.0, 11.0, 10.0])]
        stats = _analyze_voltage(records)
        assert stats.minimum == pytest.approx(10.0)
        assert stats.maximum == pytest.approx(12.0)
        assert stats.average == pytest.approx(11.0)

    def test_brownout_count(self):
        records = [
            _make_record(idx=0, voltage=6.5, brownout=True),
            _make_record(idx=1, voltage=6.3, brownout=True),
            _make_record(idx=2, voltage=12.0, brownout=False),
        ]
        stats = _analyze_voltage(records)
        assert stats.brownout_count == 2
        assert len(stats.brownout_events) == 2

    def test_low_voltage_count(self):
        # LOW_VOLTAGE_WARN = 11.0
        records = [
            _make_record(idx=0, voltage=10.5),  # below warn
            _make_record(idx=1, voltage=11.5),  # above warn
            _make_record(idx=2, voltage=10.9),  # below warn
        ]
        stats = _analyze_voltage(records)
        assert stats.low_voltage_count == 2

    def test_min_voltage_idx(self):
        records = [_make_record(idx=i, voltage=v) for i, v in enumerate([12.0, 9.0, 11.0])]
        stats = _analyze_voltage(records)
        assert stats.min_voltage_idx == 1

    def test_empty_records(self):
        stats = _analyze_voltage([])
        assert stats.minimum == 0.0
        assert stats.brownout_count == 0


# ---------------------------------------------------------------------------
# 2. CAN error counting
# ---------------------------------------------------------------------------

class TestAnalyzeCAN:
    def test_average_utilization(self):
        records = [_make_record(idx=i, can_usage=u) for i, u in enumerate([0.2, 0.4, 0.6])]
        stats = _analyze_can(records)
        assert stats.average_utilization == pytest.approx(0.4)

    def test_max_utilization(self):
        records = [_make_record(idx=i, can_usage=u) for i, u in enumerate([0.2, 0.9, 0.5])]
        stats = _analyze_can(records)
        assert stats.max_utilization == pytest.approx(0.9)

    def test_packet_loss_count(self):
        records = [
            _make_record(idx=0, packet_loss=0.0),
            _make_record(idx=1, packet_loss=0.5),
            _make_record(idx=2, packet_loss=1.2),
            _make_record(idx=3, packet_loss=0.0),
        ]
        stats = _analyze_can(records)
        assert stats.packet_loss_count == 2
        assert stats.packet_loss_fraction == pytest.approx(0.5)

    def test_packet_loss_seconds(self):
        records = [_make_record(idx=i, packet_loss=1.0 if i < 5 else 0.0) for i in range(10)]
        stats = _analyze_can(records)
        assert stats.packet_loss_seconds == pytest.approx(5 * TIMESTEP_S)

    def test_empty_records(self):
        stats = _analyze_can([])
        assert stats.average_utilization == 0.0


# ---------------------------------------------------------------------------
# 3. Timeline bucketing
# ---------------------------------------------------------------------------

class TestAnalyzeTimeline:
    def test_auto_teleop_disabled_seconds(self):
        records = _make_match_records()
        tl = _analyze_timeline(records)
        # 50 auto records * 0.020 s = 1.0 s
        assert tl.auto_seconds == pytest.approx(50 * TIMESTEP_S, abs=1e-9)
        # 50 teleop records * 0.020 s = 1.0 s
        assert tl.teleop_seconds == pytest.approx(50 * TIMESTEP_S, abs=1e-9)
        # 50 disabled records
        assert tl.disabled_seconds == pytest.approx(50 * TIMESTEP_S, abs=1e-9)

    def test_enabled_segments_detected(self):
        records = _make_match_records()
        tl = _analyze_timeline(records)
        # Should have 2 segments: auto(50-99) and teleop(100-149)
        assert len(tl.segments) == 2
        assert tl.segments[0][2] == "auto"
        assert tl.segments[1][2] == "teleop"

    def test_estop_detected(self):
        records = [_make_record(idx=i, watchdog=(i == 5)) for i in range(10)]
        tl = _analyze_timeline(records)
        assert tl.estop_detected is True

    def test_no_estop_when_watchdog_false(self):
        records = [_make_record(idx=i) for i in range(10)]
        tl = _analyze_timeline(records)
        assert tl.estop_detected is False

    def test_total_enabled_seconds(self):
        records = _make_match_records()
        tl = _analyze_timeline(records)
        assert tl.total_enabled_seconds == pytest.approx(100 * TIMESTEP_S, abs=1e-9)


# ---------------------------------------------------------------------------
# 4. Error analysis / top-failure-mode extraction
# ---------------------------------------------------------------------------

class TestAnalyzeErrors:
    def _make_timeline_with_auto(self, n=10):
        records = [
            _make_record(idx=i, robot_auto=True, robot_disabled=False) for i in range(n)
        ]
        return records, _analyze_timeline(records)

    def test_message_counts_deduplication(self):
        records, tl = self._make_timeline_with_auto()
        # Both addresses are valid hex — regex normalizes them both to 0xADDR
        msgs = [
            (_BASE_TIME + datetime.timedelta(seconds=0.0), "CAN Error: 0xBEEF timeout"),
            (_BASE_TIME + datetime.timedelta(seconds=0.0), "CAN Error: 0xCAFE timeout"),
            (_BASE_TIME + datetime.timedelta(seconds=0.0), "Low battery"),
        ]
        summary = _analyze_errors(records, msgs, tl)
        # Both CAN addresses normalize to the same pattern
        assert "CAN Error: 0xADDR timeout" in summary.message_counts
        assert summary.message_counts["CAN Error: 0xADDR timeout"] == 2

    def test_all_messages_stored(self):
        records, tl = self._make_timeline_with_auto()
        msgs = [(_BASE_TIME, f"msg{i}") for i in range(5)]
        summary = _analyze_errors(records, msgs, tl)
        assert len(summary.all_messages) == 5

    def test_empty_records(self):
        tl = _analyze_timeline([])
        summary = _analyze_errors([], [], tl)
        assert summary.message_counts == {}
        assert summary.all_messages == []


# ---------------------------------------------------------------------------
# 5. Trip computer / disconnect detection
# ---------------------------------------------------------------------------

class TestAnalyzeTrip:
    def test_total_records_and_seconds(self):
        records = [_make_record(idx=i) for i in range(50)]
        trip = _analyze_trip(records)
        assert trip.total_records == 50
        assert trip.total_seconds == pytest.approx(50 * TIMESTEP_S)

    def test_disconnect_detected_above_threshold(self):
        # packet_loss >= 4.0 is a full disconnect in pitcrew's model
        records = [
            _make_record(idx=i, packet_loss=4.0 if 5 <= i <= 9 else 0.0)
            for i in range(20)
        ]
        trip = _analyze_trip(records)
        assert trip.disconnect_count == 5
        assert trip.disconnect_seconds == pytest.approx(5 * TIMESTEP_S)
        assert len(trip.disconnect_segments) == 1

    def test_round_trip_stats(self):
        records = [_make_record(idx=i, round_trip_time=rtt)
                   for i, rtt in enumerate([0.01, 0.02, 0.03])]
        trip = _analyze_trip(records)
        assert trip.avg_round_trip_ms == pytest.approx(20.0)
        assert trip.max_round_trip_ms == pytest.approx(30.0)

    def test_empty_records(self):
        trip = _analyze_trip([])
        assert trip.total_records == 0
        assert trip.disconnect_count == 0


# ---------------------------------------------------------------------------
# 6. Markdown report generation
# ---------------------------------------------------------------------------

class TestReportGenerate:
    def test_report_contains_team_header(self):
        a = _make_full_analysis()
        report = generate(a, team="2950")
        assert "Team 2950" in report

    def test_report_contains_voltage_info(self):
        a = _make_full_analysis()
        report = generate(a, team="2950")
        assert "Battery:" in report
        assert "V" in report

    def test_brownout_warning_shown(self):
        records = [_make_record(idx=i, voltage=6.5, brownout=True) for i in range(5)]
        a = _make_full_analysis(records)
        report = generate(a, team="2950")
        assert "SWAP BATTERY" in report

    def test_no_brownout_no_warning(self):
        records = [_make_record(idx=i, voltage=12.5) for i in range(10)]
        a = _make_full_analysis(records)
        report = generate(a, team="2950")
        assert "SWAP BATTERY" not in report

    def test_can_section_present(self):
        a = _make_full_analysis()
        report = generate(a)
        assert "CAN:" in report

    def test_top_errors_shown(self):
        records = [_make_record(idx=i, robot_tele=True, robot_disabled=False) for i in range(10)]
        a = DSLogAnalysis(source_path="/fake/test.dslog")
        a.records = records
        a.voltage = _analyze_voltage(records)
        a.can = _analyze_can(records)
        a.timeline = _analyze_timeline(records)
        msgs = [(_BASE_TIME, "CAN Error") for _ in range(3)]
        a.errors = _analyze_errors(records, msgs, a.timeline)
        a.trip = _analyze_trip(records)
        report = generate(a)
        assert "CAN Error" in report

    def test_batch_table_structure(self):
        analyses = [_make_full_analysis() for _ in range(2)]
        table = generate_batch_table(analyses, team="2950")
        assert "| File" in table
        assert "Brownouts" in table
        assert len(table.splitlines()) > 4  # header + separator + rows

    def test_batch_table_empty(self):
        result = generate_batch_table([], team="2950")
        assert "No logs" in result


# ---------------------------------------------------------------------------
# 7. CLI smoke test (argparse-based, no real file needed)
# ---------------------------------------------------------------------------

class TestCLI:
    def test_cli_missing_file_returns_nonzero(self):
        ret = main(["analyze", "/nonexistent/path/fake.dslog"])
        assert ret != 0

    def test_cli_analyze_with_mocked_analysis(self, tmp_path):
        # Create a fake dslog file (content doesn't matter; we mock analyze())
        fake_log = tmp_path / "match.dslog"
        fake_log.write_bytes(b"\x00" * 100)

        analysis = _make_full_analysis()
        analysis.source_path = str(fake_log)

        with patch("pitcrew.cli.analyze", return_value=analysis):
            ret = main(["analyze", str(fake_log)])
        assert ret == 0

    def test_cli_analyze_writes_to_file(self, tmp_path):
        fake_log = tmp_path / "match.dslog"
        fake_log.write_bytes(b"\x00" * 100)
        out_file = tmp_path / "report.md"

        analysis = _make_full_analysis()
        analysis.source_path = str(fake_log)

        with patch("pitcrew.cli.analyze", return_value=analysis):
            ret = main(["analyze", str(fake_log), "--out", str(out_file)])
        assert ret == 0
        assert out_file.exists()
        assert "DS Log Report" in out_file.read_text()
