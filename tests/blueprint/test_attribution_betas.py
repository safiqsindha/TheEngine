"""
tests/blueprint/test_attribution_betas.py
-------------------------------------------
Tests for blueprint.attribution_betas — config lookup, phase resolution, fallbacks.

No empirical β values are tested here (they are all None until the Item 1 data run).
Tests validate the lookup logic, not the numeric values themselves.
"""

import sys
from pathlib import Path

import pytest

_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
sys.path.insert(0, str(_BLUEPRINT_DIR))

from attribution_betas import (  # noqa: E402
    ATTRIBUTION_BETAS,
    get_attribution_beta,
)


# ---------------------------------------------------------------------------
# Every registered year should return a float
# ---------------------------------------------------------------------------

class TestAllYearsReturnFloat:
    """Config lookup for each registered year returns a float."""

    @pytest.mark.parametrize("year", sorted(ATTRIBUTION_BETAS.keys()))
    def test_year_returns_float(self, year: int):
        result = get_attribution_beta(year)
        assert isinstance(result, float), (
            f"get_attribution_beta({year}) returned {type(result).__name__}, expected float"
        )

    @pytest.mark.parametrize("year", sorted(ATTRIBUTION_BETAS.keys()))
    def test_year_in_valid_range(self, year: int):
        result = get_attribution_beta(year)
        assert 0.0 < result <= 1.0, (
            f"get_attribution_beta({year}) = {result} is outside (0, 1]"
        )

    @pytest.mark.parametrize("year", sorted(ATTRIBUTION_BETAS.keys()))
    def test_year_meets_minimum_floor(self, year: int):
        """No season β should fall below 0.4 (the tuning search floor)."""
        result = get_attribution_beta(year)
        assert result >= 0.4, (
            f"get_attribution_beta({year}) = {result} is below the search floor 0.4"
        )


# ---------------------------------------------------------------------------
# 2019 per-phase lookup
# ---------------------------------------------------------------------------

class Test2019PhaseResolution:
    """2019 Deep Space has per-phase β; phase lookup must work correctly."""

    def test_cycle_phase_returns_float(self):
        result = get_attribution_beta(2019, phase="cycle")
        assert isinstance(result, float)

    def test_climb_phase_returns_float(self):
        result = get_attribution_beta(2019, phase="climb")
        assert isinstance(result, float)

    def test_cycle_and_climb_differ(self):
        """Cycle and climb phases should have different β values per the prior."""
        cycle = get_attribution_beta(2019, phase="cycle")
        climb = get_attribution_beta(2019, phase="climb")
        assert cycle != climb, (
            "2019 cycle and climb β should differ (0.85 vs 0.60 prior); got same value"
        )

    def test_cycle_higher_than_climb(self):
        """Cycle (independent placement) should have higher β than climb (buddy assist)."""
        cycle = get_attribution_beta(2019, phase="cycle")
        climb = get_attribution_beta(2019, phase="climb")
        assert cycle > climb, (
            f"Expected cycle β ({cycle}) > climb β ({climb}) for Deep Space"
        )

    def test_unknown_phase_falls_back_to_float(self):
        """An unknown phase key should fall back gracefully — still returns a float."""
        result = get_attribution_beta(2019, phase="endgame")
        assert isinstance(result, float), (
            "Unknown phase for 2019 should return a float fallback, not raise"
        )

    def test_default_overall_phase_for_2019(self):
        """
        Calling get_attribution_beta(2019) without a phase arg should not crash.
        It returns one of the per-phase values (first available) as a proxy.
        """
        result = get_attribution_beta(2019)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Unknown year fallback
# ---------------------------------------------------------------------------

class TestUnknownYearFallback:
    """Unknown years should fall back to β=1.0 (linear attribution)."""

    @pytest.mark.parametrize("year", [1999, 2000, 2011, 2012, 2026, 9999])
    def test_unknown_year_returns_1_0(self, year: int):
        result = get_attribution_beta(year)
        assert result == 1.0, (
            f"get_attribution_beta({year}) should return 1.0 for unknown year, got {result}"
        )

    def test_unknown_year_with_phase_still_returns_1_0(self):
        result = get_attribution_beta(2000, phase="cycle")
        assert result == 1.0


# ---------------------------------------------------------------------------
# Registry structure sanity
# ---------------------------------------------------------------------------

class TestRegistryStructure:
    """Verify that the ATTRIBUTION_BETAS registry has the expected shape."""

    REQUIRED_KEYS = {
        "game_name",
        "prior_expected_beta",
        "prior_reason",
        "empirical_beta",
        "empirical_ci",
        "tuned_on_match_count",
    }

    @pytest.mark.parametrize("year", sorted(ATTRIBUTION_BETAS.keys()))
    def test_required_keys_present(self, year: int):
        entry = ATTRIBUTION_BETAS[year]
        missing = self.REQUIRED_KEYS - set(entry.keys())
        assert not missing, f"Year {year} missing keys: {missing}"

    @pytest.mark.parametrize("year", sorted(ATTRIBUTION_BETAS.keys()))
    def test_empirical_beta_is_none_until_data_run(self, year: int):
        """Empirical β should be None in this scaffold commit — no fabricated values."""
        assert ATTRIBUTION_BETAS[year]["empirical_beta"] is None, (
            f"Year {year} has a non-None empirical_beta. "
            "Empirical values must come from the Item 1 data run, not this scaffold."
        )

    @pytest.mark.parametrize("year", sorted(ATTRIBUTION_BETAS.keys()))
    def test_tuned_on_match_count_is_zero(self, year: int):
        assert ATTRIBUTION_BETAS[year]["tuned_on_match_count"] == 0, (
            f"Year {year} tuned_on_match_count should be 0 before the data run"
        )

    def test_2019_prior_is_dict(self):
        """2019 must have a per-phase prior dict, not a scalar."""
        prior = ATTRIBUTION_BETAS[2019]["prior_expected_beta"]
        assert isinstance(prior, dict), (
            f"2019 prior_expected_beta should be a dict, got {type(prior).__name__}"
        )
        assert "cycle" in prior and "climb" in prior
