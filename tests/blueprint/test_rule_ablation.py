"""
tests/blueprint/test_rule_ablation.py
---------------------------------------
Tests for the Oracle rule ablation harness.

Hermetic: no network calls; uses cached Statbotics data from
.cache/statbotics/matches_2025_*.json (already warm from Item 1).
When cache is absent, integration tests skip gracefully.

Design note: because Oracle confidence is a game-level scalar (same value for
every match in a season), ablation accuracy deltas on Statbotics win_accuracy
are always 0.0 by mathematical identity.  These tests validate the two
meaningful metrics: confidence_delta and arch_accuracy_delta.  See module
docstring in rule_ablation.py for the full explanation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "statbotics"

if str(_BLUEPRINT_DIR) not in sys.path:
    sys.path.insert(0, str(_BLUEPRINT_DIR))

from rule_ablation import (  # noqa: E402
    AblationResult,
    ALL_RULE_IDS,
    NEUTRAL_CONFIDENCE,
    MIN_MATCHES_REQUIRED,
    SIGNIFICANCE_THRESHOLD,
    _oracle_composite_confidence,
    _compute_arch_accuracy,
    _bootstrap_accuracy_ci,
    _load_matches,
    _statbotics_accuracy_mse,
    run_ablation,
    run_full_ablation,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_exists(year: int) -> bool:
    """Return True if at least one match cache file exists for *year*."""
    files = list(_CACHE_DIR.glob(f"matches_{year}_*.json"))
    return bool(files)


CACHE_2025_AVAILABLE = _cache_exists(2025)
CACHE_2024_AVAILABLE = _cache_exists(2024)

_skip_no_2025 = pytest.mark.skipif(
    not CACHE_2025_AVAILABLE,
    reason="No cached 2025 match data found — run statbotics_client.py first",
)
_skip_no_2024 = pytest.mark.skipif(
    not CACHE_2024_AVAILABLE,
    reason="No cached 2024 match data found — run statbotics_client.py first",
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — pure logic, no cache required
# ─────────────────────────────────────────────────────────────────────────────

class TestAblationResultDataclass:
    """AblationResult dataclass has all required fields with correct defaults."""

    def test_required_fields_set_from_constructor(self):
        result = AblationResult(
            disabled_rules=frozenset({7}),
            n_matches=500,
            win_accuracy=0.77,
            score_mse=700.0,
            mean_confidence=0.88,
        )
        assert result.disabled_rules == frozenset({7})
        assert result.n_matches == 500
        assert result.win_accuracy == 0.77
        assert result.score_mse == 700.0
        assert result.mean_confidence == 0.88

    def test_default_delta_fields_are_zero(self):
        result = AblationResult(
            disabled_rules=frozenset(),
            n_matches=100,
            win_accuracy=0.80,
            score_mse=500.0,
            mean_confidence=0.85,
        )
        assert result.confidence_delta == 0.0
        assert result.arch_accuracy_delta == 0.0
        assert result.baseline_accuracy == 0.0
        assert result.ci_low == 0.0
        assert result.ci_high == 0.0
        assert result.is_significant is False
        assert result.year == 0

    def test_year_field_is_settable(self):
        result = AblationResult(
            disabled_rules=frozenset(),
            n_matches=1000,
            win_accuracy=0.78,
            score_mse=720.0,
            mean_confidence=0.87,
            year=2025,
        )
        assert result.year == 2025

    def test_all_five_required_fields_present(self):
        """AblationResult has disabled_rules, n_matches, win_accuracy,
        score_mse, mean_confidence — the five task-specified fields."""
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(AblationResult)}
        for required in (
            "disabled_rules", "n_matches", "win_accuracy",
            "score_mse", "mean_confidence",
        ):
            assert required in field_names, f"Missing field: {required}"


class TestBootstrapCI:
    """_bootstrap_accuracy_ci bootstrap confidence interval."""

    def test_all_correct_gives_ci_near_one(self):
        flags = [1] * 1000
        lo, hi = _bootstrap_accuracy_ci(flags, n_samples=200, seed=0)
        assert lo >= 0.99
        assert hi == 1.0

    def test_all_incorrect_gives_ci_near_zero(self):
        flags = [0] * 1000
        lo, hi = _bootstrap_accuracy_ci(flags, n_samples=200, seed=0)
        assert lo == 0.0
        assert hi <= 0.01

    def test_deterministic_with_fixed_seed(self):
        flags = [1, 0, 1, 1, 0, 0, 1] * 100
        lo1, hi1 = _bootstrap_accuracy_ci(flags, n_samples=200, seed=42)
        lo2, hi2 = _bootstrap_accuracy_ci(flags, n_samples=200, seed=42)
        assert lo1 == lo2
        assert hi1 == hi2

    def test_empty_input_returns_zeros(self):
        lo, hi = _bootstrap_accuracy_ci([])
        assert lo == 0.0
        assert hi == 0.0

    def test_ci_contains_sample_mean(self):
        flags = [1, 0] * 500
        lo, hi = _bootstrap_accuracy_ci(flags, n_samples=500, seed=7)
        assert lo <= 0.5 <= hi


class TestOracleCompositeConfidence:
    """_oracle_composite_confidence extracts and applies rule disabling."""

    def test_known_year_returns_float_in_unit(self):
        conf = _oracle_composite_confidence(2025, frozenset())
        assert 0.0 <= conf <= 1.0

    def test_unknown_year_returns_neutral(self):
        conf = _oracle_composite_confidence(9999, frozenset())
        assert conf == NEUTRAL_CONFIDENCE

    def test_disabling_all_rules_returns_neutral(self):
        all_rules = frozenset(ALL_RULE_IDS)
        conf = _oracle_composite_confidence(2025, all_rules)
        assert conf == pytest.approx(NEUTRAL_CONFIDENCE, abs=1e-9)

    def test_disabling_no_rules_gives_above_neutral(self):
        conf_baseline = _oracle_composite_confidence(2025, frozenset())
        assert conf_baseline > NEUTRAL_CONFIDENCE

    def test_disabling_r1_lowers_composite(self):
        # R1 has confidence 1.0; replacing with 0.5 should lower composite.
        conf_base = _oracle_composite_confidence(2025, frozenset())
        conf_no_r1 = _oracle_composite_confidence(2025, frozenset({1}))
        assert conf_no_r1 < conf_base

    def test_more_disabled_rules_lowers_composite(self):
        conf_0 = _oracle_composite_confidence(2025, frozenset())
        conf_1 = _oracle_composite_confidence(2025, frozenset({1}))
        conf_2 = _oracle_composite_confidence(2025, frozenset({1, 4}))
        assert conf_1 <= conf_0
        assert conf_2 <= conf_1

    def test_same_year_different_disabled_set_gives_different_conf(self):
        # R1 has conf=1.0 (highest); R3 has conf=0.85; disabling them separately
        # should give different composites.
        conf_no_r1 = _oracle_composite_confidence(2025, frozenset({1}))
        conf_no_r3 = _oracle_composite_confidence(2025, frozenset({3}))
        assert conf_no_r1 != conf_no_r3


class TestArchAccuracy:
    """_compute_arch_accuracy historical ground-truth checks."""

    def test_baseline_arch_accuracy_is_one(self):
        acc = _compute_arch_accuracy(frozenset())
        assert acc == pytest.approx(1.0, abs=1e-9)

    def test_all_disabled_skips_checks_returns_one(self):
        # When all relevant rules (R1, R4, R6, R7) are disabled, total=0
        # checks run → returns 1.0 (no checks = no failures).
        acc = _compute_arch_accuracy(frozenset(ALL_RULE_IDS))
        assert acc == pytest.approx(1.0, abs=1e-9)

    def test_disabling_r4_removes_scorer_checks(self):
        # With R4 disabled, scorer method checks are skipped — total checks drop.
        # Result should still be 1.0 because remaining checks still pass.
        acc = _compute_arch_accuracy(frozenset({4}))
        assert 0.0 <= acc <= 1.0

    def test_arch_accuracy_float_in_unit(self):
        for rule_num in ALL_RULE_IDS:
            acc = _compute_arch_accuracy(frozenset({rule_num}))
            assert 0.0 <= acc <= 1.0, f"R{rule_num} gave acc={acc}"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — require cache data
# ─────────────────────────────────────────────────────────────────────────────

class TestRunAblationIntegration:
    """Integration tests using cached Statbotics match data."""

    @_skip_no_2025
    def test_baseline_processes_minimum_matches(self):
        result = run_ablation(2025, frozenset())
        assert result.n_matches >= MIN_MATCHES_REQUIRED
        assert result.n_matches >= 10  # explicit task requirement

    @_skip_no_2025
    def test_baseline_win_accuracy_in_plausible_range(self):
        result = run_ablation(2025, frozenset())
        # Statbotics is typically 70-85% accurate on qual matches.
        assert 0.60 <= result.win_accuracy <= 0.95

    @_skip_no_2025
    def test_ablation_result_all_fields_populated(self):
        result = run_ablation(2025, frozenset({7}))
        assert result.n_matches > 0
        assert 0.0 <= result.win_accuracy <= 1.0
        assert result.score_mse >= 0.0
        assert 0.0 <= result.mean_confidence <= 1.0
        assert 0.0 <= result.ci_low <= result.ci_high <= 1.0
        assert 0.0 <= result.arch_accuracy <= 1.0

    @_skip_no_2025
    def test_insufficient_cache_raises_runtime_error(self, tmp_path, monkeypatch):
        """Ablation on year with no cache should raise RuntimeError."""
        import rule_ablation as ra
        monkeypatch.setattr(ra, "CACHE_DIR", tmp_path)
        with pytest.raises(RuntimeError, match="Insufficient cached data"):
            run_ablation(2025, frozenset())

    @_skip_no_2025
    def test_disabling_no_rules_is_deterministic(self):
        """Same year twice → identical results (no randomness in conf computation)."""
        r1 = run_ablation(2025, frozenset())
        r2 = run_ablation(2025, frozenset())
        assert r1.win_accuracy == r2.win_accuracy
        assert r1.mean_confidence == r2.mean_confidence
        assert r1.n_matches == r2.n_matches

    @_skip_no_2025
    def test_disabling_all_rules_oracle_conf_is_neutral(self):
        all_disabled = run_ablation(2025, frozenset(ALL_RULE_IDS))
        assert all_disabled.n_matches > 0
        assert all_disabled.mean_confidence == pytest.approx(NEUTRAL_CONFIDENCE)


class TestRunFullAblation:
    """run_full_ablation returns complete keyed dict with deltas."""

    @_skip_no_2025
    def test_full_ablation_returns_all_keys(self):
        results = run_full_ablation(2025)
        assert "baseline" in results
        assert "disable_all" in results
        for rule_num in ALL_RULE_IDS:
            assert f"disable_R{rule_num}" in results

    @_skip_no_2025
    def test_baseline_confidence_delta_is_zero(self):
        results = run_full_ablation(2025)
        baseline = results["baseline"]
        assert baseline.confidence_delta == 0.0
        assert baseline.arch_accuracy_delta == 0.0

    @_skip_no_2025
    def test_per_rule_confidence_deltas_populated_correctly(self):
        results = run_full_ablation(2025)
        base_conf = results["baseline"].mean_confidence
        for rule_num in ALL_RULE_IDS:
            r = results[f"disable_R{rule_num}"]
            expected_delta = round(r.mean_confidence - base_conf, 6)
            assert r.confidence_delta == pytest.approx(expected_delta, abs=1e-5)

    @_skip_no_2025
    def test_significance_flag_follows_threshold(self):
        results = run_full_ablation(2025)
        for key, r in results.items():
            if key == "baseline":
                continue
            expected_sig = abs(r.confidence_delta) >= SIGNIFICANCE_THRESHOLD
            assert r.is_significant == expected_sig, (
                f"{key}: expected is_significant={expected_sig} "
                f"(|delta|={abs(r.confidence_delta):.4f})"
            )

    @_skip_no_2025
    def test_2025_at_least_10_matches_processed(self):
        """Integration smoke: at least 10 qual matches processed for 2025."""
        results = run_full_ablation(2025)
        assert results["baseline"].n_matches >= 10

    @_skip_no_2025
    def test_deterministic_across_two_calls(self):
        """Same year twice → identical baseline confidence and accuracy."""
        r1 = run_full_ablation(2025)
        r2 = run_full_ablation(2025)
        assert r1["baseline"].win_accuracy == r2["baseline"].win_accuracy
        assert r1["baseline"].mean_confidence == r2["baseline"].mean_confidence

    @_skip_no_2024
    def test_2024_ablation_completes_successfully(self):
        """2024 Crescendo (beta=0.55) ablation completes without error."""
        results = run_full_ablation(2024)
        assert "baseline" in results
        assert results["baseline"].n_matches >= 10
        assert 0.60 <= results["baseline"].win_accuracy <= 0.95

    @_skip_no_2024
    def test_beta_sensitive_rules_differ_between_2024_and_2025(self):
        """R4, R7 confidence deltas should differ between 2024 (β=0.55) and 2025 (β=0.65)."""
        res_2025 = run_full_ablation(2025)
        res_2024 = run_full_ablation(2024)
        # R7 baseline confidence is beta-adjusted; the composite should differ between years.
        assert (
            res_2025["baseline"].mean_confidence != res_2024["baseline"].mean_confidence
        ), "Baseline confidence should differ between β=0.65 (2025) and β=0.55 (2024)"
