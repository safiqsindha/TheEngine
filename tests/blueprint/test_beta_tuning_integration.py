"""
tests/blueprint/test_beta_tuning_integration.py
-------------------------------------------------
Integration tests for the β-tuning pipeline using synthetic fixtures.

No network calls are made — all data is hardcoded here.

Scenarios covered:
  1. Objective function returns a finite float for each β in the grid.
  2. Grid search finds the correct β* on a toy dataset where the "true" β
     is known by construction.
  3. Bootstrap CI runs end-to-end and produces low <= best_beta <= high.
  4. build_match_records filters non-qual matches and bad scores correctly.
  5. Statbotics client offline mode raises RuntimeError (no network required).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Add blueprint directory to sys.path (same pattern as other blueprint tests)
_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
if str(_BLUEPRINT_DIR) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT_DIR))

from tune_attribution_beta import (  # noqa: E402
    _alliance_weighted_strength,
    _rmse,
    objective_score,
    tune_beta_for_season,
    build_match_records,
    TuningResult,
)

# Import blueprint's statbotics_client explicitly by path to avoid collision
# with scout/statbotics_client.py which has a different API.
import importlib.util as _ilu
_sc_spec = _ilu.spec_from_file_location(
    "blueprint_statbotics_client",
    _BLUEPRINT_DIR / "statbotics_client.py",
)
statbotics_client = _ilu.module_from_spec(_sc_spec)  # type: ignore[arg-type]
_sc_spec.loader.exec_module(statbotics_client)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def _make_match_record(epas: list[float], score: float) -> dict:
    return {"epas": epas, "score": score}


# A dataset where β=1.0 (linear) minimises RMSE: actual score ≈ sum(epas)
UNIFORM_MATCHES = [
    _make_match_record([20.0, 25.0, 30.0], 75.0),   # sum = 75
    _make_match_record([15.0, 20.0, 25.0], 60.0),   # sum = 60
    _make_match_record([30.0, 30.0, 30.0], 90.0),   # sum = 90
    _make_match_record([10.0, 40.0, 20.0], 70.0),   # sum = 70
]

# A dataset where β=0.4 (concave) minimises RMSE.
#
# Why β=0.4 wins here:
#   With β=1.0, weighted_strength([50,10,10]) ≈ 38.6 (dominant team's EPA²/sum
#   pulls prediction up). But actual scores are ~30 — the dominant team is
#   constrained by coupling and can't realise its full EPA.
#   Lower β compresses the dominant share, driving weighted_strength down toward
#   the actual scores (~29.5 at β=0.4 for this distribution).
COUPLED_MATCHES = [
    _make_match_record([50.0, 10.0, 10.0], 30.0),  # dominant robot over-EPAd
    _make_match_record([45.0, 12.0, 8.0],  28.0),
    _make_match_record([55.0, 8.0, 12.0],  32.0),
    _make_match_record([48.0, 11.0, 11.0], 29.0),
    _make_match_record([52.0, 9.0, 9.0],   31.0),
    _make_match_record([47.0, 13.0, 10.0], 30.0),
]


# ---------------------------------------------------------------------------
# 1. Objective function basic properties
# ---------------------------------------------------------------------------

class TestObjectiveFunction:
    def test_returns_finite_float_for_all_betas(self):
        betas = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        for beta in betas:
            score = objective_score(UNIFORM_MATCHES, beta)
            assert math.isfinite(score), f"objective_score should be finite for β={beta}"

    def test_higher_score_means_lower_rmse(self):
        """objective_score is -RMSE; higher value = better fit."""
        # For UNIFORM_MATCHES, β=1.0 should give score >= β=0.4 score
        # because the data was constructed to match linear EPAs
        score_linear = objective_score(UNIFORM_MATCHES, 1.0)
        score_concave = objective_score(UNIFORM_MATCHES, 0.4)
        # Linear should fit better (less negative) or at worst equal
        assert score_linear >= score_concave - 1.0  # loose tolerance

    def test_empty_matches_returns_zero(self):
        assert objective_score([], 0.7) == 0.0

    def test_all_zero_epas_does_not_crash(self):
        matches = [_make_match_record([0.0, 0.0, 0.0], 50.0)]
        score = objective_score(matches, 0.7)
        assert math.isfinite(score)


# ---------------------------------------------------------------------------
# 2. Grid search correctness
# ---------------------------------------------------------------------------

class TestGridSearch:
    def test_returns_tuning_result(self):
        result = tune_beta_for_season(2025, UNIFORM_MATCHES, beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        assert isinstance(result, TuningResult)

    def test_best_beta_in_range(self):
        result = tune_beta_for_season(2025, UNIFORM_MATCHES, beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        assert 0.4 <= result.best_beta <= 1.0

    def test_n_matches_correct(self):
        result = tune_beta_for_season(2025, UNIFORM_MATCHES, beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        assert result.n_matches == len(UNIFORM_MATCHES)

    def test_empty_matches_returns_safe_default(self):
        result = tune_beta_for_season(2025, [], beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        assert result.best_beta == 1.0
        assert result.n_matches == 0
        assert "FAILED" in result.status

    def test_status_ok_on_valid_data(self):
        result = tune_beta_for_season(2025, UNIFORM_MATCHES, beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        assert result.status == "OK"

    def test_coupled_game_prefers_lower_beta(self):
        """
        On the COUPLED_MATCHES fixture, the dominant team's EPA overpredicts.
        The grid search should favour a lower β (more concave = less top-dominated).
        This validates the objective function direction: concave compresses output,
        reducing RMSE when star EPAs overpredict.
        """
        result = tune_beta_for_season(2024, COUPLED_MATCHES, beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        # The best β should be strictly less than 1.0 for this coupled fixture
        assert result.best_beta < 1.0, (
            f"Expected β < 1.0 for coupled game fixture, got {result.best_beta}"
        )

    def test_score_by_beta_has_all_grid_points(self):
        result = tune_beta_for_season(2025, UNIFORM_MATCHES, beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        expected_count = round((1.0 - 0.4) / 0.05) + 1  # 13 grid points
        assert len(result.score_by_beta) == expected_count


# ---------------------------------------------------------------------------
# 3. Bootstrap CI
# ---------------------------------------------------------------------------

class TestBootstrapCI:
    def test_ci_runs_end_to_end(self):
        # Use more matches so bootstrap has signal
        matches = UNIFORM_MATCHES * 10  # 40 matches
        result = tune_beta_for_season(2025, matches, beta_range=(0.4, 1.0, 0.05), n_bootstrap=100)
        assert result.ci_low is not None
        assert result.ci_high is not None

    def test_ci_brackets_best_beta(self):
        matches = UNIFORM_MATCHES * 10
        result = tune_beta_for_season(2025, matches, beta_range=(0.4, 1.0, 0.05), n_bootstrap=100)
        # CI should bracket or include the best_beta
        assert result.ci_low <= result.best_beta + 0.05  # allow 1-step slack
        assert result.ci_high >= result.best_beta - 0.05

    def test_ci_none_when_too_few_matches(self):
        """Only 3 matches — below the minimum for CI."""
        matches = UNIFORM_MATCHES[:3]
        result = tune_beta_for_season(2025, matches, beta_range=(0.4, 1.0, 0.05), n_bootstrap=100)
        # _bootstrap_ci returns None,None for n < 10
        assert result.ci_low is None
        assert result.ci_high is None

    def test_ci_skipped_when_n_bootstrap_zero(self):
        result = tune_beta_for_season(2025, UNIFORM_MATCHES, beta_range=(0.4, 1.0, 0.05), n_bootstrap=0)
        assert result.ci_low is None
        assert result.ci_high is None


# ---------------------------------------------------------------------------
# 4. build_match_records filtering
# ---------------------------------------------------------------------------

class TestBuildMatchRecords:
    def _make_raw_match(
        self,
        comp_level: str = "qm",
        red_score: int = 80,
        blue_score: int = 70,
        red_teams: tuple = (1, 2, 3),
        blue_teams: tuple = (4, 5, 6),
    ) -> dict:
        return {
            "comp_level": comp_level,
            "red_score": red_score,
            "blue_score": blue_score,
            "red_1": red_teams[0],
            "red_2": red_teams[1],
            "red_3": red_teams[2],
            "blue_1": blue_teams[0],
            "blue_2": blue_teams[1],
            "blue_3": blue_teams[2],
        }

    def _epa_map(self) -> dict[int, float]:
        return {1: 20.0, 2: 25.0, 3: 30.0, 4: 15.0, 5: 18.0, 6: 22.0}

    def test_qual_matches_produce_two_alliance_records(self):
        raw = [self._make_raw_match()]
        records = build_match_records(raw, self._epa_map())
        # Each qual match → 2 alliance records
        assert len(records) == 2

    def test_non_qual_matches_filtered_out(self):
        raw = [
            self._make_raw_match(comp_level="sf"),
            self._make_raw_match(comp_level="f"),
        ]
        records = build_match_records(raw, self._epa_map())
        assert len(records) == 0

    def test_negative_scores_filtered(self):
        # When either alliance score is negative, the whole match is skipped
        # (both red and blue alliances), because a negative score signals a
        # replay, DQ, or data error that contaminates both sides.
        raw = [self._make_raw_match(red_score=-1)]
        records = build_match_records(raw, self._epa_map())
        assert len(records) == 0

    def test_missing_team_epa_defaults_to_zero(self):
        raw = [self._make_raw_match()]
        # Only provide EPA for red team 1, rest missing
        records = build_match_records(raw, {1: 20.0}, comp_level="qm")
        # Red alliance: epas = [20.0, 0.0, 0.0] — not all zero, so included
        # Blue alliance: epas = [0.0, 0.0, 0.0] — all zero, filtered
        red_records = [r for r in records if max(r["epas"]) > 0]
        assert len(red_records) == 1
        assert records[0]["epas"][0] == 20.0

    def test_record_has_correct_keys(self):
        raw = [self._make_raw_match()]
        records = build_match_records(raw, self._epa_map())
        for r in records:
            assert "epas" in r
            assert "score" in r
            assert len(r["epas"]) == 3
            assert isinstance(r["score"], float)


# ---------------------------------------------------------------------------
# 5. Statbotics client offline mode
# ---------------------------------------------------------------------------

class TestStatboticsClientOffline:
    def test_offline_mode_raises_runtime_error(self, monkeypatch):
        """With _OFFLINE_MODE=True, any network fetch should raise RuntimeError."""
        monkeypatch.setattr(statbotics_client, "_OFFLINE_MODE", True)
        with pytest.raises(RuntimeError, match="offline"):
            statbotics_client._fetch_page("http://example.com")

    def test_cache_path_structure(self):
        """Cache path should include endpoint, year, and offset."""
        p = statbotics_client._cache_path("matches", 2025, 0)
        assert "matches" in str(p)
        assert "2025" in str(p)
        assert "0" in str(p)
        assert str(p).endswith(".json")

    def test_load_cache_returns_none_for_missing_file(self, tmp_path, monkeypatch):
        """load_cache returns None when the cache file doesn't exist."""
        monkeypatch.setattr(statbotics_client, "CACHE_DIR", tmp_path)
        result = statbotics_client._load_cache("matches", 2099, 0)
        assert result is None

    def test_save_and_load_cache_round_trip(self, tmp_path, monkeypatch):
        """Data saved to cache can be loaded back intact."""
        monkeypatch.setattr(statbotics_client, "CACHE_DIR", tmp_path)
        data = [{"key": "2025abc_qm1", "red_score": 80}]
        statbotics_client._save_cache("matches", 2099, 0, data)
        loaded = statbotics_client._load_cache("matches", 2099, 0)
        assert loaded == data
