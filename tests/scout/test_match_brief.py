"""
Tests for scout/match_brief.py — Match Brief Generator.

Covers:
  1.  Mock all data sources, verify MatchBrief structure populated
  2.  Markdown renders non-empty and contains expected sections
  3.  PDF renders to file (or skipped if no deps)
  4.  our_team_number not in match → not_participating flag
  5.  Anomaly flag surfaces correctly in TeamBrief
  6.  β=0.55 regime → "specialists" language in markdown
  7.  β=0.95 → "raw EPA" language in markdown
  8.  Missing eye data → falls back gracefully (no crash)
  9.  Empty alliance → raises ValueError
  10. CLI smoke test with CliRunner equivalent (argparse)
  11. Deterministic output with fixed inputs
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root and scout/ dir are importable
ROOT = Path(__file__).resolve().parents[2]
SCOUT_DIR = ROOT / "scout"
for _p in (str(ROOT), str(SCOUT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from match_brief import (  # noqa: E402
    AllianceBrief,
    MatchBrief,
    TeamBrief,
    _beta_regime,
    generate_match_brief,
    render_markdown,
    render_pdf,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

TEAMS_DB = {
    "1": {"epa": 50.0, "sd": 10.0},
    "2": {"epa": 55.0, "sd": 12.0},
    "3": {"epa": 45.0, "sd": 9.0},
    "4": {"epa": 40.0, "sd": 8.0},
    "5": {"epa": 35.0, "sd": 7.0},
    "6": {"epa": 30.0, "sd": 6.0},
    "2950": {"epa": 48.0, "sd": 11.0},
}

RED_TEAMS = [1, 2, 2950]
BLUE_TEAMS = [4, 5, 6]

BASE_KWARGS = dict(
    event_key="2025wor",
    match_key="qm1",
    year=2025,
    our_team_number=2950,
    teams_db=TEAMS_DB,
    red_teams=RED_TEAMS,
    blue_teams=BLUE_TEAMS,
)


# ─── Test 1: Brief structure populated ────────────────────────────────────────

def test_brief_structure_populated():
    brief = generate_match_brief(**BASE_KWARGS)

    assert isinstance(brief, MatchBrief)
    assert brief.event_key == "2025wor"
    assert brief.match_key == "qm1"
    assert brief.year == 2025
    assert brief.our_team_number == 2950
    assert not brief.not_participating

    # Alliances
    assert isinstance(brief.red_alliance, AllianceBrief)
    assert isinstance(brief.blue_alliance, AllianceBrief)
    assert len(brief.red_alliance.teams) == 3
    assert len(brief.blue_alliance.teams) == 3

    # Each TeamBrief has required fields
    for tb in brief.red_alliance.teams + brief.blue_alliance.teams:
        assert isinstance(tb, TeamBrief)
        assert tb.team_number > 0
        assert isinstance(tb.epa, float)
        assert 0.0 <= tb.attributed_credit <= 1.0

    # Outcome
    assert "red_win_prob" in brief.predicted_outcome
    assert "blue_win_prob" in brief.predicted_outcome
    assert 0.0 <= brief.predicted_outcome["red_win_prob"] <= 1.0

    # β
    assert isinstance(brief.attribution_beta, float)
    assert brief.beta_regime in ("raw EPA", "moderate coupling", "role specialists", "specialists")

    # Recommendations
    assert isinstance(brief.recommendations, list)
    assert len(brief.recommendations) >= 1

    # Key matchups
    assert isinstance(brief.key_matchups, list)
    assert len(brief.key_matchups) <= 3


# ─── Test 2: Markdown renders non-empty with sections ────────────────────────

def test_markdown_contains_expected_sections():
    brief = generate_match_brief(**BASE_KWARGS)
    md = render_markdown(brief)

    assert isinstance(md, str)
    assert len(md) > 100

    assert "Match Brief" in md
    assert "Predicted Outcome" in md
    assert "Attribution" in md
    assert "Red Alliance" in md
    assert "Blue Alliance" in md
    assert "Key Matchups" in md
    assert "Coaching Recommendations" in md
    assert "2025wor" in md
    assert "qm1" in md


# ─── Test 3: PDF renders to file or skipped gracefully ───────────────────────

def test_pdf_renders_or_skips(tmp_path):
    brief = generate_match_brief(**BASE_KWARGS)
    output = tmp_path / "brief.pdf"

    # Try to detect PDF backend
    has_reportlab = False
    has_weasyprint = False
    try:
        import reportlab  # noqa: F401
        has_reportlab = True
    except ImportError:
        pass
    try:
        import weasyprint  # noqa: F401
        has_weasyprint = True
    except ImportError:
        pass

    if has_reportlab or has_weasyprint:
        render_pdf(brief, output)
        assert output.exists()
        assert output.stat().st_size > 0
    else:
        # Should warn and not raise
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            render_pdf(brief, output)
        assert any("PDF" in str(warning.message) for warning in w)
        assert not output.exists()


# ─── Test 4: not_participating flag ──────────────────────────────────────────

def test_not_participating_flag():
    brief = generate_match_brief(
        event_key="2025wor",
        match_key="qm1",
        year=2025,
        our_team_number=9999,  # not in this match
        teams_db=TEAMS_DB,
        red_teams=RED_TEAMS,
        blue_teams=BLUE_TEAMS,
    )
    assert brief.not_participating is True
    assert len(brief.recommendations) >= 1
    assert any("NOT" in r or "not" in r.lower() for r in brief.recommendations)


# ─── Test 5: Anomaly flag surfaces correctly ─────────────────────────────────

def test_anomaly_flags_surface():
    # Build observations with a clear outlier on match_contribution for team 2950
    obs_normal = [
        {"team": 2950, "match_contribution": 50.0, "_meta": {"match_key": f"qm{i}", "scout": "alice"}}
        for i in range(1, 8)
    ]
    obs_outlier = {"team": 2950, "match_contribution": 200.0, "_meta": {"match_key": "qm8", "scout": "alice"}}
    all_obs = obs_normal + [obs_outlier]

    brief = generate_match_brief(
        **{**BASE_KWARGS, "all_observations": all_obs}
    )

    # Find team 2950 in red alliance
    our_brief = next((t for t in brief.red_alliance.teams if t.team_number == 2950), None)
    assert our_brief is not None
    # Anomaly flags should be populated
    assert isinstance(our_brief.anomaly_flags, list)
    # With the big outlier (200 vs mean~50), robust MAD should flag it
    assert len(our_brief.anomaly_flags) >= 1


# ─── Test 6: β=0.55 → "specialists" language ─────────────────────────────────

def test_beta_055_specialists_regime():
    assert _beta_regime(0.55) == "specialists"

    with patch("match_brief._load_blueprint_attribution_beta", return_value=0.55):
        brief = generate_match_brief(**BASE_KWARGS)

    assert brief.beta_regime == "specialists"
    md = render_markdown(brief)
    assert "specialists" in md.lower()


# ─── Test 7: β=0.95 → "raw EPA" language ─────────────────────────────────────

def test_beta_095_raw_epa_regime():
    assert _beta_regime(0.95) == "raw EPA"

    with patch("match_brief._load_blueprint_attribution_beta", return_value=0.95):
        brief = generate_match_brief(**BASE_KWARGS)

    assert brief.beta_regime == "raw EPA"
    md = render_markdown(brief)
    assert "raw EPA" in md or "raw epa" in md.lower()


# ─── Test 8: Missing eye data → falls back to stand_scout only ───────────────

def test_missing_eye_data_falls_back():
    """Without event_matches and all_observations, EPA-only path triggers gracefully."""
    brief = generate_match_brief(
        event_key="2025wor",
        match_key="qm1",
        year=2025,
        our_team_number=2950,
        teams_db=TEAMS_DB,
        red_teams=RED_TEAMS,
        blue_teams=BLUE_TEAMS,
        all_observations=None,
        event_matches=None,
    )
    # Should not raise; partial fallback path — teams_db is available
    assert isinstance(brief, MatchBrief)
    # No stand_scout or event_matches data — only teams_db used
    assert "stand_scout" not in brief.data_sources_used
    assert "event_matches" not in brief.data_sources_used
    # Brief is still fully rendered
    md = render_markdown(brief)
    assert len(md) > 50
    assert "Predicted Outcome" in md


# ─── Test 9: Empty alliance → raises ValueError ───────────────────────────────

def test_empty_alliance_raises():
    with pytest.raises(ValueError, match="No alliance data"):
        generate_match_brief(
            event_key="2025wor",
            match_key="qm1",
            year=2025,
            our_team_number=2950,
            teams_db=TEAMS_DB,
            red_teams=[],
            blue_teams=[],
        )


# ─── Test 10: CLI smoke test ──────────────────────────────────────────────────

def test_cli_smoke(capsys):
    """Simulate CLI args and verify no crash + output produced."""
    import argparse

    # Directly call the internal CLI parse path by patching sys.argv
    test_argv = [
        "match_brief",
        "--event", "2025wor",
        "--match", "qm1",
        "--team", "2950",
        "--red", "1", "2", "2950",
        "--blue", "4", "5", "6",
    ]
    with patch("sys.argv", test_argv):
        # Import and call _cli but catch SystemExit(0)
        import match_brief as mb_module
        try:
            mb_module._cli()
        except SystemExit as e:
            assert e.code == 0 or e.code is None

    captured = capsys.readouterr()
    # _cli prints the markdown to stdout
    assert "Match Brief" in captured.out or len(captured.out) > 0


# ─── Test 11: Deterministic output with fixed inputs ─────────────────────────

def test_deterministic_output():
    """Same inputs → identical output, twice."""
    brief_1 = generate_match_brief(**BASE_KWARGS)
    brief_2 = generate_match_brief(**BASE_KWARGS)

    md_1 = render_markdown(brief_1)
    md_2 = render_markdown(brief_2)

    assert md_1 == md_2
    assert brief_1.attribution_beta == brief_2.attribution_beta
    assert brief_1.predicted_outcome == brief_2.predicted_outcome
    assert brief_1.beta_regime == brief_2.beta_regime


# ─── Test: Event key prefix normalisation ────────────────────────────────────

def test_match_key_prefix_stripped():
    """Full TBA key '2025wor_qm1' should be normalised to 'qm1' in the brief."""
    brief = generate_match_brief(
        event_key="2025wor",
        match_key="2025wor_qm1",
        year=2025,
        our_team_number=2950,
        teams_db=TEAMS_DB,
        red_teams=RED_TEAMS,
        blue_teams=BLUE_TEAMS,
    )
    assert brief.match_key == "qm1"


# ─── Test: Win probability present and coherent ───────────────────────────────

def test_win_probability_sums_to_one():
    brief = generate_match_brief(**BASE_KWARGS)
    po = brief.predicted_outcome
    total = po.get("red_win_prob", 0) + po.get("blue_win_prob", 0)
    assert abs(total - 1.0) < 1e-6
