"""
tests/eye/test_eye_bridge.py — Tests for eye/eye_bridge.py

Covers: aggregate_team_eye_data, _score_team, aggregate_blended,
        load_eye_reports, load_stand_scout_reports, inject_eye_data.

No real filesystem access to production directories.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
EYE_DIR = ROOT / "eye"
sys.path.insert(0, str(EYE_DIR))

import eye_bridge  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(teams_dict: dict, event: str = "2026txcmp") -> dict:
    """Build a minimal EYE report dict."""
    return {
        "match": {"event": event, "comp_level": "qm", "match_number": 1},
        "teams": teams_dict,
    }


def _simple_obs(overall: str = "solid", mechanism_issues: str = "none") -> dict:
    """Minimal observation dict that eye_bridge._score_team can consume."""
    return {
        "overall": overall,
        "mechanisms": {"issues": mechanism_issues},
        "defense": {"played_defense": False, "received_defense": False, "notes": ""},
        "teleop": {"cycle_speed": "fast", "scoring_consistency": "high", "notes": ""},
        "endgame": {"climb_attempted": True, "notes": "success"},
    }


# ===========================================================================
# 1. _score_team
# ===========================================================================

class TestScoreTeam:
    def test_empty_observations_returns_zeros(self):
        result = eye_bridge._score_team("2950", [])
        assert result["eye_composite"] == 0
        assert result["eye_matches"] == 0
        assert result["eye_confidence"] == 0

    def test_single_solid_observation(self):
        obs = [_simple_obs("solid")]
        result = eye_bridge._score_team("2950", obs)
        assert result["eye_composite"] > 0
        assert result["eye_matches"] == 1
        assert result["eye_confidence"] == 25

    def test_four_matches_gives_100_percent_confidence(self):
        obs = [_simple_obs("solid")] * 4
        result = eye_bridge._score_team("2950", obs)
        assert result["eye_confidence"] == 100

    def test_breakdown_reduces_reliability(self):
        good = [_simple_obs("elite", mechanism_issues="none")]
        bad  = [_simple_obs("elite", mechanism_issues="jam")]
        r_good = eye_bridge._score_team("1", good)
        r_bad  = eye_bridge._score_team("2", bad)
        assert r_good["eye_reliability"] > r_bad["eye_reliability"]

    def test_elite_team_scores_higher_than_weak(self):
        elite = [_simple_obs("elite")]
        weak  = [_simple_obs("weak")]
        r_elite = eye_bridge._score_team("1", elite)
        r_weak  = eye_bridge._score_team("2", weak)
        assert r_elite["eye_composite"] > r_weak["eye_composite"]

    def test_result_keys_present(self):
        obs = [_simple_obs()]
        result = eye_bridge._score_team("2950", obs)
        for key in ("eye_composite", "eye_reliability", "eye_driver",
                    "eye_overall", "eye_matches", "eye_confidence"):
            assert key in result, f"Missing key: {key}"


# ===========================================================================
# 2. aggregate_team_eye_data
# ===========================================================================

class TestAggregateTeamEyeData:
    def test_empty_reports_returns_empty_dict(self):
        assert eye_bridge.aggregate_team_eye_data([]) == {}

    def test_single_report_produces_team_entry(self):
        report = _make_report({"2950": _simple_obs()})
        result = eye_bridge.aggregate_team_eye_data([report])
        assert "2950" in result
        assert result["2950"]["eye_matches"] == 1

    def test_multiple_reports_accumulate_matches(self):
        r1 = _make_report({"2950": _simple_obs()})
        r2 = _make_report({"2950": _simple_obs()})
        result = eye_bridge.aggregate_team_eye_data([r1, r2])
        assert result["2950"]["eye_matches"] == 2


# ===========================================================================
# 3. aggregate_blended
# ===========================================================================

class TestAggregateBlended:
    def test_eye_only_returns_eye_scores(self):
        eye = [_make_report({"2950": _simple_obs()})]
        result = eye_bridge.aggregate_blended(eye, [])
        assert "2950" in result

    def test_stand_only_bumps_confidence(self):
        stand = [_make_report({"2950": _simple_obs()})]
        result = eye_bridge.aggregate_blended([], stand)
        assert result["2950"]["eye_confidence"] >= 30  # stand bumps per match

    def test_blended_both_sources_includes_all_teams(self):
        eye   = [_make_report({"2950": _simple_obs()})]
        stand = [_make_report({"3035": _simple_obs()})]
        result = eye_bridge.aggregate_blended(eye, stand)
        assert "2950" in result
        assert "3035" in result

    def test_blended_same_team_both_sources(self):
        eye   = [_make_report({"2950": _simple_obs("solid")})]
        stand = [_make_report({"2950": _simple_obs("elite")})]
        result = eye_bridge.aggregate_blended(eye, stand)
        assert "2950" in result
        assert "eye_sources" in result["2950"]
        assert result["2950"]["eye_sources"]["eye"] == 1
        assert result["2950"]["eye_sources"]["stand"] == 1


# ===========================================================================
# 4. load_eye_reports / load_stand_scout_reports
# ===========================================================================

class TestLoadReports:
    def test_load_eye_reports_nonexistent_dir_returns_empty(self, tmp_path):
        with patch.object(eye_bridge, "EYE_RESULTS_DIR", tmp_path / "missing"):
            result = eye_bridge.load_eye_reports()
        assert result == []

    def test_load_eye_reports_reads_json_files(self, tmp_path):
        fake_report = {"teams": {"2950": {"overall": "solid"}}}
        (tmp_path / "qm1_report.json").write_text(json.dumps(fake_report))
        with patch.object(eye_bridge, "EYE_RESULTS_DIR", tmp_path):
            result = eye_bridge.load_eye_reports()
        assert len(result) == 1
        assert "teams" in result[0]

    def test_load_eye_reports_skips_corrupt_json(self, tmp_path):
        (tmp_path / "bad_report.json").write_text("{not valid json")
        with patch.object(eye_bridge, "EYE_RESULTS_DIR", tmp_path):
            result = eye_bridge.load_eye_reports()
        assert result == []

    def test_load_stand_scout_reports_empty_dir(self, tmp_path):
        stand_dir = tmp_path / "stand_scout"
        stand_dir.mkdir()
        with patch.object(eye_bridge, "STAND_SCOUT_DIR", stand_dir):
            result = eye_bridge.load_stand_scout_reports()
        assert result == []

    def test_load_stand_scout_event_filter(self, tmp_path):
        stand_dir = tmp_path / "stand_scout"
        stand_dir.mkdir()
        r1 = {"match": {"event": "2026txcmp"}, "teams": {"1": {}}}
        r2 = {"match": {"event": "2026txhou"}, "teams": {"2": {}}}
        (stand_dir / "scout_0001.json").write_text(json.dumps(r1))
        (stand_dir / "scout_0002.json").write_text(json.dumps(r2))
        with patch.object(eye_bridge, "STAND_SCOUT_DIR", stand_dir):
            result = eye_bridge.load_stand_scout_reports(event_key="2026txcmp")
        assert len(result) == 1


# ===========================================================================
# 5. inject_eye_data
# ===========================================================================

class TestInjectEyeData:
    def test_inject_adds_scores_to_known_team(self):
        state = {"teams": {"2950": {"team": 2950, "epa": 45.0}}}
        scores = {"2950": {"eye_composite": 72.0, "eye_confidence": 50}}
        enriched = eye_bridge.inject_eye_data(state, scores)
        assert enriched == 1
        assert state["teams"]["2950"]["eye_composite"] == 72.0

    def test_inject_skips_unknown_teams(self):
        state = {"teams": {"2950": {"team": 2950}}}
        scores = {"9999": {"eye_composite": 80.0}}
        enriched = eye_bridge.inject_eye_data(state, scores)
        assert enriched == 0

    def test_inject_empty_scores(self):
        state = {"teams": {"2950": {"team": 2950}}}
        enriched = eye_bridge.inject_eye_data(state, {})
        assert enriched == 0
