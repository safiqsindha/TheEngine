"""Tests for scout/pre_event_report.py — Season Attribution β + Rule #18 regime.

Covers:
  - Report includes "Season Attribution β" section when year=2025
  - Regime text matches β value (2014 → "low-coupling", 2024 → "high-coupling")
  - year=None falls through gracefully (no β section)
  - Missing β data year → graceful fallback message
  - format_beta_section_text + format_beta_section_markdown both render valid output
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SCOUT_DIR = ROOT / "scout"
_BLUEPRINT_DIR = ROOT / "blueprint"

# Insert scout/ first so scout/statbotics_client.py takes priority over blueprint/
if str(_SCOUT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCOUT_DIR))
# Append blueprint/ so attribution_betas is importable without shadowing scout modules
if str(_BLUEPRINT_DIR) not in sys.path:
    sys.path.append(str(_BLUEPRINT_DIR))

from pre_event_report import (
    classify_beta_regime,
    get_season_beta_info,
    format_beta_section_text,
    format_beta_section_markdown,
    display_report,
    TeamProfile,
    Anomaly,
)


# ─── fixtures ────────────────────────────────────────────────────────────────

def _make_profiles(n: int = 3) -> list[TeamProfile]:
    profiles = []
    for i in range(n):
        p = TeamProfile(
            team=1000 + i,
            name=f"Team {1000 + i}",
            epa_total=50.0 - i * 5,
            epa_auto=10.0,
            epa_teleop=30.0,
            epa_endgame=10.0,
            epa_rank_at_event=i + 1,
            trend="stable",
            epa_change_pct=0.0,
            events_this_season=3,
            priority="MEDIUM",
            priority_reason="test",
        )
        profiles.append(p)
    return profiles


# ─── classify_beta_regime ────────────────────────────────────────────────────

class TestClassifyBetaRegime:
    def test_below_threshold_is_high_coupling(self):
        assert classify_beta_regime(0.55) == "high-coupling"

    def test_exactly_0_7_is_moderate(self):
        # 0.7 is the boundary: < 0.7 → high-coupling, so 0.7 itself is moderate
        assert classify_beta_regime(0.70) == "moderate"

    def test_mid_range_is_moderate(self):
        assert classify_beta_regime(0.78) == "moderate"

    def test_at_0_85_is_low_coupling(self):
        assert classify_beta_regime(0.85) == "low-coupling"

    def test_above_threshold_is_low_coupling(self):
        assert classify_beta_regime(1.0) == "low-coupling"


# ─── get_season_beta_info ────────────────────────────────────────────────────

class TestGetSeasonBetaInfo:
    def test_year_none_returns_none(self):
        result = get_season_beta_info(None)
        assert result is None

    def test_year_2025_returns_dict(self):
        result = get_season_beta_info(2025)
        assert result is not None
        assert result["year"] == 2025
        assert result["game_name"] == "Reefscape"
        assert "beta" in result
        assert "regime" in result

    def test_2025_empirical_beta_used(self):
        # 2025 empirical_beta=0.65 → high-coupling
        result = get_season_beta_info(2025)
        assert result is not None
        assert result["beta"] == pytest.approx(0.65, abs=1e-9)
        assert result["regime"] == "high-coupling"

    def test_2014_regime_is_low_coupling(self):
        # 2014 empirical_beta=0.95 → low-coupling
        result = get_season_beta_info(2014)
        assert result is not None
        assert result["regime"] == "low-coupling"

    def test_2024_regime_is_high_coupling(self):
        # 2024 empirical_beta=0.55 → high-coupling
        result = get_season_beta_info(2024)
        assert result is not None
        assert result["regime"] == "high-coupling"

    def test_unknown_year_returns_none(self):
        # Year not in registry → None
        result = get_season_beta_info(1999)
        assert result is None


# ─── format_beta_section_text ────────────────────────────────────────────────

class TestFormatBetaSectionText:
    def test_none_returns_empty_string(self):
        assert format_beta_section_text(None) == ""

    def test_2025_section_contains_header(self):
        info = get_season_beta_info(2025)
        text = format_beta_section_text(info)
        assert "ATTRIBUTION" in text.upper()
        assert "Rule #18" in text

    def test_2025_section_contains_regime(self):
        info = get_season_beta_info(2025)
        text = format_beta_section_text(info)
        assert "HIGH-COUPLING" in text

    def test_2025_section_contains_game_name(self):
        info = get_season_beta_info(2025)
        text = format_beta_section_text(info)
        assert "Reefscape" in text

    def test_2025_section_contains_beta_value(self):
        info = get_season_beta_info(2025)
        text = format_beta_section_text(info)
        assert "0.65" in text

    def test_2014_section_contains_low_coupling(self):
        info = get_season_beta_info(2014)
        text = format_beta_section_text(info)
        assert "LOW-COUPLING" in text


# ─── format_beta_section_markdown ────────────────────────────────────────────

class TestFormatBetaSectionMarkdown:
    def test_none_returns_empty_string(self):
        assert format_beta_section_markdown(None) == ""

    def test_markdown_has_h2_header(self):
        info = get_season_beta_info(2025)
        md = format_beta_section_markdown(info)
        assert md.startswith("## Season Attribution")

    def test_markdown_contains_bold_regime(self):
        info = get_season_beta_info(2025)
        md = format_beta_section_markdown(info)
        assert "**Regime:**" in md

    def test_markdown_contains_game_name(self):
        info = get_season_beta_info(2025)
        md = format_beta_section_markdown(info)
        assert "Reefscape" in md

    def test_markdown_has_closing_hr(self):
        info = get_season_beta_info(2025)
        md = format_beta_section_markdown(info)
        assert "---" in md

    def test_markdown_2014_low_coupling(self):
        info = get_season_beta_info(2014)
        md = format_beta_section_markdown(info)
        assert "LOW-COUPLING" in md


# ─── display_report integration ──────────────────────────────────────────────

class TestDisplayReportBetaSection:
    def _capture(self, profiles, event_key, year):
        buf = StringIO()
        with patch("sys.stdout", buf):
            display_report(profiles, event_key, year=year)
        return buf.getvalue()

    def test_year_2025_includes_beta_section(self):
        profiles = _make_profiles(3)
        out = self._capture(profiles, "2025txhou", 2025)
        assert "ATTRIBUTION" in out.upper()
        assert "Rule #18" in out

    def test_year_none_has_no_beta_section(self):
        profiles = _make_profiles(3)
        out = self._capture(profiles, "2025txhou", None)
        assert "Season Attribution" not in out

    def test_year_2014_shows_low_coupling(self):
        profiles = _make_profiles(3)
        out = self._capture(profiles, "2014txhou", 2014)
        assert "LOW-COUPLING" in out

    def test_year_2024_shows_high_coupling(self):
        profiles = _make_profiles(3)
        out = self._capture(profiles, "2024txhou", 2024)
        assert "HIGH-COUPLING" in out

    def test_unknown_year_no_beta_section(self):
        # year=1999 not in registry → no beta section
        profiles = _make_profiles(3)
        out = self._capture(profiles, "1999txhou", 1999)
        assert "Season Attribution" not in out

    def test_existing_sections_preserved(self):
        profiles = _make_profiles(3)
        out = self._capture(profiles, "2025txhou", 2025)
        # Header always present
        assert "PRE-EVENT INTELLIGENCE REPORT" in out
        # Notable teams section always present
        assert "NOTABLE TEAMS" in out
        # Scouting priorities section always present
        assert "SCOUTING PRIORITIES" in out


# ─── graceful fallback — missing empirical β ─────────────────────────────────

class TestMissingEmpiricalBeta:
    def test_prior_used_when_empirical_none(self):
        # 2015 has empirical_beta=None; should fall back to prior=0.85
        result = get_season_beta_info(2015)
        assert result is not None
        # prior_expected_beta=0.85 → low-coupling
        assert result["beta"] == pytest.approx(0.85, abs=1e-9)
        assert result["regime"] == "low-coupling"
        assert result["beta_source"] == "prior"

    def test_ci_string_says_prior_when_empirical_none(self):
        result = get_season_beta_info(2015)
        assert result is not None
        assert "prior" in result["ci_str"]

    def test_ci_string_has_interval_when_empirical_present(self):
        # 2025 has empirical_beta and empirical_ci
        result = get_season_beta_info(2025)
        assert result is not None
        assert "CI" in result["ci_str"]

    def test_format_text_does_not_raise_when_prior(self):
        info = get_season_beta_info(2015)
        text = format_beta_section_text(info)
        assert "Recycle Rush" in text


# ─── per-team β-credit in build_report_for_team ──────────────────────────────

class TestBuildReportForTeamBetaSection:
    """Test that build_report_for_team includes the β info block."""

    def test_beta_info_present_in_team_report_when_year_known(self):
        from pre_event_report import build_report_for_team

        mock_profiles = _make_profiles(5)
        # Patch build_profiles so no network calls
        with patch("pre_event_report.build_profiles", return_value=mock_profiles):
            result = build_report_for_team("2025txhou", 1000, year=2025)

        # Should include β info (no carry_delta_ema → fallback message)
        assert "Season β" in result or "β-adj credit" in result or "0.65" in result

    def test_beta_section_absent_when_year_unknown(self):
        from pre_event_report import build_report_for_team

        mock_profiles = _make_profiles(5)
        # year=1999 not in registry → beta_info is None
        with patch("pre_event_report.build_profiles", return_value=mock_profiles):
            result = build_report_for_team("1999txhou", 1000, year=1999)

        assert "Season β" not in result
        assert "β-adj credit" not in result
