"""Tests for blueprint/manual_parser.py — injects fake parse_fn (no real LLM)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from blueprint import manual_parser
from blueprint.manual_parser import (
    ConflictReport,
    ManualParse,
    consensus,
    finalize,
    parse_manual,
    render_diff_markdown,
    validate_parse_dict,
)


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

def _base_parse_dict() -> dict:
    return {
        "scoring": {
            "auto": [{"name": "Leave", "points": 3, "location": "start_line"}],
            "teleop": [{"name": "Coral L4", "points": 5, "location": "reef"}],
            "endgame": [{"name": "Deep Cage", "points": 12, "location": "barge"}],
        },
        "game_pieces": [{"name": "CORAL", "count_on_field": 22, "notes": "pipe"}],
        "field_zones": [{"name": "REEF", "alliance_scope": "alliance", "notes": ""}],
        "possession_limits": {"max_simultaneous": 1, "notes": "one at a time"},
        "ranking_points": [{"name": "Auto", "criterion": "all leave"}],
        "penalty_rules": [{"id": "G418", "severity": "MAJOR", "summary": "no contact"}],
        "critical_constraints": {
            "weight_lbs": 115.0,
            "max_height_in": 78.0,
            "frame_perimeter_in": 120.0,
            "starting_config": "inside perimeter",
        },
    }


def _make_parses(dicts: list) -> list:
    return [
        ManualParse(
            scoring=d["scoring"],
            game_pieces=d["game_pieces"],
            field_zones=d["field_zones"],
            possession_limits=d["possession_limits"],
            ranking_points=d["ranking_points"],
            penalty_rules=d["penalty_rules"],
            critical_constraints=d["critical_constraints"],
            raw_text="raw",
        )
        for d in dicts
    ]


# ---------------------------------------------------------------------------
# Consensus voting
# ---------------------------------------------------------------------------

def test_consensus_three_unanimous_locks_everything() -> None:
    d = _base_parse_dict()
    parses = _make_parses([d, json.loads(json.dumps(d)), json.loads(json.dumps(d))])
    merged, report = consensus(parses)
    assert report.ambiguous_fields == []
    assert report.tentative_fields == []
    assert len(report.locked_fields) >= 6  # 6 top-level + scoring paths
    assert merged.critical_constraints["weight_lbs"] == 115.0


def test_consensus_two_of_three_is_tentative() -> None:
    d1 = _base_parse_dict()
    d2 = json.loads(json.dumps(d1))
    d3 = json.loads(json.dumps(d1))
    # perturb one parse's possession_limits so 2 agree, 1 differs
    d3["possession_limits"] = {"max_simultaneous": 2, "notes": "differs"}
    parses = _make_parses([d1, d2, d3])
    merged, report = consensus(parses)
    paths = [e["path"] for e in report.tentative_fields]
    assert "possession_limits" in paths
    entry = next(e for e in report.tentative_fields if e["path"] == "possession_limits")
    assert entry["chosen"]["max_simultaneous"] == 1
    assert any(alt.get("max_simultaneous") == 2 for alt in entry["alternatives"])


def test_consensus_three_way_split_is_ambiguous() -> None:
    d1 = _base_parse_dict()
    d2 = json.loads(json.dumps(d1))
    d3 = json.loads(json.dumps(d1))
    d1["possession_limits"] = {"max_simultaneous": 1, "notes": "a"}
    d2["possession_limits"] = {"max_simultaneous": 2, "notes": "b"}
    d3["possession_limits"] = {"max_simultaneous": 3, "notes": "c"}
    parses = _make_parses([d1, d2, d3])
    _, report = consensus(parses)
    paths = [e["path"] for e in report.ambiguous_fields]
    assert "possession_limits" in paths


def test_consensus_scoring_array_matches_by_name() -> None:
    d1 = _base_parse_dict()
    d2 = json.loads(json.dumps(d1))
    d3 = json.loads(json.dumps(d1))
    # All three agree on "Leave" with same points/location -> locked
    # Perturb teleop Coral L4 points in one parse -> tentative
    d3["scoring"]["teleop"][0]["points"] = 6
    parses = _make_parses([d1, d2, d3])
    merged, report = consensus(parses)
    all_paths = report.locked_fields + [e["path"] for e in report.tentative_fields]
    assert "scoring.auto.leave.points" in report.locked_fields
    # Coral L4 has spread 5,5,6 → within 20% so ambiguous (>5% tolerance)
    tent_paths = [e["path"] for e in report.tentative_fields]
    amb_paths = [e["path"] for e in report.ambiguous_fields]
    assert "scoring.teleop.coral l4.points" in (tent_paths + amb_paths)


def test_integer_median_tolerance_locks_small_spread() -> None:
    # Use numeric consensus helper via a field with small spread
    from blueprint.manual_parser import _median_numeric
    status, winner, _ = _median_numeric([100, 100, 100])
    assert status == "locked" and winner == 100

    # Spread of (100, 101, 102) -> relative range 2/102 ≈ 2% -> tentative with median
    status, winner, alts = _median_numeric([100, 101, 102])
    assert status == "tentative"
    assert winner == 101

    # Spread 100/200 -> ambiguous
    status, winner, _ = _median_numeric([100, 150, 200])
    assert status == "ambiguous"


def test_validate_parse_dict_missing_fields_raises() -> None:
    with pytest.raises(ValueError, match="missing required fields"):
        validate_parse_dict({"scoring": {}})  # most keys missing


def test_validate_parse_dict_accepts_complete() -> None:
    validate_parse_dict(_base_parse_dict())  # no raise


# ---------------------------------------------------------------------------
# Rendering + finalize
# ---------------------------------------------------------------------------

def test_render_diff_markdown_contains_section_headers() -> None:
    d = _base_parse_dict()
    d2 = json.loads(json.dumps(d))
    d3 = json.loads(json.dumps(d))
    d3["possession_limits"] = {"max_simultaneous": 2, "notes": "differs"}
    parses = _make_parses([d, d2, d3])
    _, report = consensus(parses)
    md = render_diff_markdown(parses, report)
    assert "Manual Parse" in md
    assert "Tentative" in md
    assert "Locked" in md


def test_finalize_emits_valid_markdown_sections() -> None:
    d = _base_parse_dict()
    parses = _make_parses([d, json.loads(json.dumps(d)), json.loads(json.dumps(d))])
    merged, _ = consensus(parses)
    out = finalize(merged)
    assert out.startswith("# Kickoff Template")
    for section in ("Critical Constraints", "Scoring", "Game Pieces",
                    "Field Zones", "Ranking Points", "Possession Limits",
                    "Penalty Rules"):
        assert section in out
    assert "115.0" in out


def test_finalize_applies_resolutions() -> None:
    d = _base_parse_dict()
    parses = _make_parses([d, json.loads(json.dumps(d)), json.loads(json.dumps(d))])
    merged, _ = consensus(parses)
    out = finalize(
        merged,
        resolutions={"critical_constraints.weight_lbs": 125.0},
    )
    assert "125.0" in out


# ---------------------------------------------------------------------------
# parse_manual dependency-injection
# ---------------------------------------------------------------------------

def test_parse_manual_uses_injected_fake(tmp_path: Path) -> None:
    manual = tmp_path / "fake_manual.txt"
    manual.write_text("Reefscape 2025 rules text.")
    calls: list = []

    def fake(text: str, model: str) -> dict:
        calls.append((text, model))
        return _base_parse_dict()

    parses = parse_manual(str(manual), n_parses=3, parse_fn=fake)
    assert len(parses) == 3
    assert len(calls) == 3
    assert all(c[0] == "Reefscape 2025 rules text." for c in calls)


def test_parse_manual_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_manual(str(tmp_path / "nope.pdf"), n_parses=1, parse_fn=lambda t, m: _base_parse_dict())


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def test_cli_kickoff_parse_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import cli as engine_cli

    # Build a fake manual file
    manual = tmp_path / "manual_2025.txt"
    manual.write_text("reefscape manual text")

    # Monkey-patch parse_manual used inside CLI to use a fake
    fake_parses = _make_parses([_base_parse_dict() for _ in range(3)])

    def fake_parse_manual(path: str, n_parses: int = 3, model: str = "claude-haiku-4-5",
                         parse_fn=None) -> list:
        return fake_parses

    monkeypatch.setattr(manual_parser, "parse_manual", fake_parse_manual)

    runner = CliRunner()
    with runner.isolated_filesystem():
        # Copy manual into isolated fs
        local_manual = Path("manual_2025.txt")
        local_manual.write_text("reefscape manual text")
        result = runner.invoke(
            engine_cli.cli,
            ["kickoff-parse", str(local_manual), "--n-parses", "3", "--output", "reports"],
        )
        assert result.exit_code == 0, result.output
        assert "kickoff-parse" in result.output
        diff = Path("reports/kickoff_parse_2025.md")
        assert diff.exists()
        assert "Manual Parse" in diff.read_text()
