"""
tests/scout/test_game_analysis.py
----------------------------------
Tests for scout/game_analysis.py — Game Analysis PDF Generator (D3).

All tests run offline (cache-only, no network).
Oracle ablation is mocked in unit tests to avoid the ~170s ablation run.
The `integration` mark runs the real ablation; skip with -m "not integration".
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scout/ and blueprint/ are importable
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scout"))
sys.path.insert(0, str(_REPO_ROOT / "blueprint"))

import scout.game_analysis as ga
from scout.game_analysis import (
    GameAnalysisReport,
    OracleSection,
    OracleRuleRow,
    generate_game_analysis,
    render_markdown,
    render_pdf,
    _build_beta_section,
    _build_top_teams,
    _build_regional_insights,
    _build_strategic_takeaways,
    _load_team_years,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_team_records(n: int = 20, year: int = 2025) -> list[dict]:
    """Synthetic team records shaped like Statbotics cache entries."""
    records = []
    for i in range(n):
        team_num = 1000 + i
        epa_val = 80.0 - i * 2.5
        records.append({
            "team": team_num,
            "year": year,
            "name": f"Team {team_num}",
            "country": "USA",
            "state": "TX" if i % 2 == 0 else "MI",
            "district": "fit" if i < n // 2 else "fim",
            "rookie_year": 2010,
            "epa": {
                "total_points": {"mean": epa_val, "sd": 4.0},
                "breakdown": {
                    "total_points": epa_val,
                    "auto_points": round(epa_val * 0.20, 2),
                    "teleop_points": round(epa_val * 0.65, 2),
                    "endgame_points": round(epa_val * 0.15, 2),
                },
            },
            "record": {"wins": 8 - i % 4, "losses": 2 + i % 4},
            "season": {"count": 3},
        })
    return records


def _mock_oracle_section(year: int = 2025) -> OracleSection:
    """Return a lightweight mock OracleSection (no actual ablation run)."""
    rules = [
        OracleRuleRow("R4", 0.88, 0.012, 0.75, 0.02, True, "Placement rule"),
        OracleRuleRow("R1", 0.87, 0.010, 0.74, 0.01, True, "Swerve rule"),
        OracleRuleRow("R6", 0.86, 0.005, 0.73, 0.00, False, "Turret rule"),
    ]
    return OracleSection(
        year=year,
        baseline_win_accuracy=0.671,
        baseline_confidence=0.885,
        n_matches=16221,
        rules=rules,
        ci_low=0.663,
        ci_high=0.679,
        data_available=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: generate_game_analysis for year=2025 populates all sections
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_2025_all_sections_populated():
    """Sections must be populated when 2025 cache exists. Oracle mocked for speed."""
    records = _minimal_team_records(50)
    with patch.object(ga, "_build_oracle_section", return_value=_mock_oracle_section(2025)), \
         patch.object(ga, "_load_team_years", return_value=records):
        report = generate_game_analysis(2025)

    assert isinstance(report, GameAnalysisReport)
    assert report.year == 2025
    assert report.game_name, "game_name should be non-empty"
    assert report.overview, "overview should be non-empty"
    assert report.scoring_model, "scoring_model should be non-empty"
    assert report.beta.year == 2025
    assert report.top_teams_sample_size == 50
    assert len(report.top_teams) > 0
    assert len(report.strategic_takeaways) >= 1
    assert "T" in report.generated_at and "Z" in report.generated_at


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Missing β data → fallback text (unmapped year)
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_beta_fallback():
    """An unmapped year (2099) must degrade gracefully with fallback text."""
    with patch.object(ga, "_build_oracle_section", return_value=OracleSection(
        year=2099, baseline_win_accuracy=0.0, baseline_confidence=0.0,
        n_matches=0, rules=[], ci_low=0.0, ci_high=0.0,
        data_available=False, note="No cache"
    )):
        report = generate_game_analysis(2099)

    assert report.beta.data_available is False
    assert report.beta.empirical_beta is None
    assert report.beta.interpretation  # non-empty explanation
    assert isinstance(report, GameAnalysisReport)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Markdown renders non-empty and contains expected headers
# ─────────────────────────────────────────────────────────────────────────────

def test_render_markdown_non_empty():
    """render_markdown must return a non-empty string with all required headers."""
    records = _minimal_team_records(20)
    with patch.object(ga, "_build_oracle_section", return_value=_mock_oracle_section(2025)), \
         patch.object(ga, "_load_team_years", return_value=records):
        report = generate_game_analysis(2025)

    md = render_markdown(report)

    assert isinstance(md, str)
    assert len(md) > 200, "Markdown output is suspiciously short"

    required_headers = [
        "# FRC 2025",
        "## 1. Game Overview",
        "## 2. Attribution β",
        "## 3. Top Teams Analysis",
        "## 4. Oracle Rule Performance",
        "## 5. Regional / District Insights",
        "## 6. Strategic Takeaways",
        "Data Sources",
    ]
    for header in required_headers:
        assert header in md, f"Missing expected header: {header!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: PDF renders or skips gracefully (no unexpected crash)
# ─────────────────────────────────────────────────────────────────────────────

def test_render_pdf_or_skip_gracefully():
    """render_pdf must produce a PDF file OR raise RuntimeError. No other exceptions."""
    records = _minimal_team_records(10)
    with patch.object(ga, "_build_oracle_section", return_value=_mock_oracle_section(2025)), \
         patch.object(ga, "_load_team_years", return_value=records):
        report = generate_game_analysis(2025)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "test_report.pdf"
        try:
            render_pdf(report, out)
            assert out.exists(), "render_pdf returned without error but file missing"
            assert out.stat().st_size > 500, "PDF is suspiciously small"
        except RuntimeError as exc:
            # Acceptable: matplotlib not available
            assert "matplotlib" in str(exc).lower() or "written" in str(exc).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: CLI smoke test (--md-only)
# ─────────────────────────────────────────────────────────────────────────────

def test_cli_smoke(tmp_path):
    """CLI --md-only must exit without error and produce a .md file."""
    records = _minimal_team_records(10)
    out_pdf = tmp_path / "report.pdf"
    sys.argv = [
        "game_analysis",
        "--year", "2025",
        "--output", str(out_pdf),
        "--md-only",
    ]
    with patch.object(ga, "_build_oracle_section", return_value=_mock_oracle_section(2025)), \
         patch.object(ga, "_load_team_years", return_value=records):
        from scout.game_analysis import _cli
        _cli()

    md_path = out_pdf.with_suffix(".md")
    assert md_path.exists(), "CLI --md-only did not produce .md file"
    content = md_path.read_text()
    assert "FRC 2025" in content


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: year=2015 (empirical_beta=None) → graceful degradation
# ─────────────────────────────────────────────────────────────────────────────

def test_year_2015_graceful_degradation():
    """2015 has empirical_beta=None — must not raise; interpretation must exist."""
    with patch.object(ga, "_build_oracle_section", return_value=OracleSection(
        year=2015, baseline_win_accuracy=0.0, baseline_confidence=0.0,
        n_matches=0, rules=[], ci_low=0.0, ci_high=0.0,
        data_available=False, note="No 2015 cache"
    )):
        report = generate_game_analysis(2015)

    assert isinstance(report, GameAnalysisReport)
    assert report.year == 2015
    # β: 2015 is in ATTRIBUTION_BETAS but empirical_beta is None
    assert report.beta.interpretation  # must have text
    # Markdown should render without crash
    md = render_markdown(report)
    assert "2015" in md


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Determinism — same injected data → identical results
# ─────────────────────────────────────────────────────────────────────────────

def test_determinism_with_fixed_input():
    """Two calls with same injected data must produce identical top-team rankings."""
    records = _minimal_team_records(30, year=2025)
    oracle_mock = _mock_oracle_section(2025)

    with patch.object(ga, "_build_oracle_section", return_value=oracle_mock), \
         patch.object(ga, "_load_team_years", return_value=records):
        report_a = generate_game_analysis(2025, data_sources={"team_records": records})

    with patch.object(ga, "_build_oracle_section", return_value=oracle_mock), \
         patch.object(ga, "_load_team_years", return_value=records):
        report_b = generate_game_analysis(2025, data_sources={"team_records": records})

    assert len(report_a.top_teams) == len(report_b.top_teams)
    for ta, tb in zip(report_a.top_teams, report_b.top_teams):
        assert ta.team == tb.team
        assert math.isclose(ta.epa_total, tb.epa_total, rel_tol=1e-9)
    assert report_a.beta.empirical_beta == report_b.beta.empirical_beta


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: _build_top_teams with injected synthetic records
# ─────────────────────────────────────────────────────────────────────────────

def test_build_top_teams_with_synthetic_records():
    """Verify top-teams builder ranks correctly, flags [ELITE], computes elite_threshold."""
    records = _minimal_team_records(50, year=2025)

    with patch.object(ga, "_load_team_years", return_value=records):
        entries, sample_size, source, elite_threshold = _build_top_teams(2025, top_n=10)

    assert sample_size == 50
    assert len(entries) == 10
    # Sorted descending by EPA
    for i in range(len(entries) - 1):
        assert entries[i].epa_total >= entries[i + 1].epa_total
    assert elite_threshold > 0
    assert any(e.is_elite for e in entries)
    assert source  # non-empty


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Regional insights aggregation from synthetic records
# ─────────────────────────────────────────────────────────────────────────────

def test_regional_insights_aggregation():
    """Regional builder groups by district and computes mean/median correctly."""
    records = _minimal_team_records(20, year=2025)
    insights, source = _build_regional_insights(2025, records)

    assert isinstance(insights, list)
    district_names = {ri.name for ri in insights}
    assert "fit" in district_names
    assert "fim" in district_names

    for ri in insights:
        assert ri.team_count > 0
        assert ri.mean_epa > 0
        assert ri.top_team > 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration test: real 2025 report with actual ablation (~170s)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_integration_real_2025_oracle():
    """Real ablation run — verifies oracle section has meaningful data. SLOW (~170s)."""
    report = generate_game_analysis(2025)

    assert report.oracle.data_available is True
    assert report.oracle.n_matches > 10000
    assert report.oracle.baseline_confidence > 0.5
    assert len(report.oracle.rules) > 0
    # At least one rule should have significant confidence contribution
    assert any(r.is_significant for r in report.oracle.rules)
