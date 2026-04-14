"""
Tests for blueprint/monte_carlo.py — Monte Carlo alliance simulation.

Covers:
  1.  simulate_alliance_score returns array of n_sims scores
  2.  simulate_match probabilities sum to ~1.0
  3.  Deterministic output with fixed seed
  4.  Equal alliances → ~50/50 win probability
  5.  Dropout raises variance and lowers expected score
  6.  Empty robots list → raises ValueError
  7.  n_sims=1 edge case works
  8.  Matches analytic result within 2% for well-behaved Gaussian case
  9.  sigma=0 edge case (near-deterministic scores)
  10. predict_alliance_with_uncertainty wrapper returns correct structure
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup — import blueprint.monte_carlo directly
# ---------------------------------------------------------------------------
_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
_SCOUT_DIR = Path(__file__).resolve().parents[2] / "scout"
sys.path.insert(0, str(_BLUEPRINT_DIR))
sys.path.insert(0, str(_SCOUT_DIR))

from monte_carlo import (  # noqa: E402
    RobotDistribution,
    simulate_alliance_score,
    simulate_match,
    predict_alliance_with_uncertainty,
    DEFAULT_SIGMA_FRACTION,
    MIN_SIGMA,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_robot(mu: float = 50.0, sigma: float = 8.0, **kw) -> RobotDistribution:
    return RobotDistribution(mu=mu, sigma=sigma, **kw)


def _equal_alliances(mu: float = 50.0, sigma: float = 8.0):
    robots = [_make_robot(mu=mu, sigma=sigma) for _ in range(3)]
    return robots, robots


# ---------------------------------------------------------------------------
# Test 1: simulate_alliance_score returns array of n_sims scores
# ---------------------------------------------------------------------------

class TestSimulateAllianceScore:
    def test_returns_ndarray_of_correct_length(self):
        robots = [_make_robot()]
        scores = simulate_alliance_score(robots, n_sims=500)
        assert isinstance(scores, np.ndarray)
        assert len(scores) == 500

    def test_three_robots_n1000(self):
        robots = [_make_robot(mu=50.0), _make_robot(mu=40.0), _make_robot(mu=30.0)]
        scores = simulate_alliance_score(robots, n_sims=1000)
        assert scores.shape == (1000,)

    def test_mean_near_sum_of_mus(self):
        """With many sims the sample mean converges to sum(mu_i)."""
        robots = [_make_robot(mu=60.0, sigma=5.0),
                  _make_robot(mu=45.0, sigma=4.0),
                  _make_robot(mu=35.0, sigma=3.0)]
        expected_mu = 60.0 + 45.0 + 35.0
        rng = np.random.default_rng(0)
        scores = simulate_alliance_score(robots, n_sims=10_000, rng=rng)
        assert abs(scores.mean() - expected_mu) < 2.0  # within 2 pts

    # ----- edge case: n_sims=1 -----
    def test_n_sims_1(self):
        robots = [_make_robot()]
        scores = simulate_alliance_score(robots, n_sims=1)
        assert scores.shape == (1,)

    # ----- edge case: sigma=0 (deterministic) -----
    def test_sigma_zero_deterministic(self):
        """sigma=0 → every sim returns exactly mu."""
        robots = [RobotDistribution(mu=100.0, sigma=0.0)]
        rng = np.random.default_rng(99)
        scores = simulate_alliance_score(robots, n_sims=200, rng=rng)
        # sigma is floored to MIN_SIGMA so scores will be extremely close to mu
        assert np.allclose(scores, 100.0, atol=1e-3)

    # ----- edge case: empty robots -----
    def test_empty_robots_raises_value_error(self):
        with pytest.raises(ValueError, match="non-empty"):
            simulate_alliance_score([], n_sims=100)

    def test_n_sims_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="n_sims"):
            simulate_alliance_score([_make_robot()], n_sims=0)


# ---------------------------------------------------------------------------
# Test 2: simulate_match probabilities sum to 1.0
# ---------------------------------------------------------------------------

class TestSimulateMatch:
    def test_probs_sum_to_one(self):
        red = [_make_robot(mu=55.0), _make_robot(mu=50.0), _make_robot(mu=40.0)]
        blue = [_make_robot(mu=45.0), _make_robot(mu=45.0), _make_robot(mu=45.0)]
        result = simulate_match(red, blue, n_sims=2000, rng=np.random.default_rng(1))
        total = result["red_win_prob"] + result["blue_win_prob"] + result["tie_prob"]
        assert abs(total - 1.0) < 1e-6

    def test_result_keys(self):
        red = [_make_robot()]
        blue = [_make_robot()]
        result = simulate_match(red, blue, n_sims=100)
        expected_keys = {
            "red_win_prob", "blue_win_prob", "tie_prob",
            "score_diff_mean", "score_diff_ci_90",
            "red_scores", "blue_scores",
        }
        assert set(result.keys()) == expected_keys

    def test_ci_90_is_ordered_tuple(self):
        red = [_make_robot()]
        blue = [_make_robot()]
        result = simulate_match(red, blue, n_sims=500, rng=np.random.default_rng(7))
        lo, hi = result["score_diff_ci_90"]
        assert lo <= hi

    def test_score_arrays_length(self):
        red = [_make_robot()]
        blue = [_make_robot()]
        result = simulate_match(red, blue, n_sims=300)
        assert len(result["red_scores"]) == 300
        assert len(result["blue_scores"]) == 300

    def test_favored_alliance_wins_more(self):
        strong_red = [_make_robot(mu=80.0), _make_robot(mu=70.0), _make_robot(mu=60.0)]
        weak_blue = [_make_robot(mu=30.0), _make_robot(mu=25.0), _make_robot(mu=20.0)]
        result = simulate_match(strong_red, weak_blue, n_sims=3000,
                                rng=np.random.default_rng(42))
        assert result["red_win_prob"] > 0.90


# ---------------------------------------------------------------------------
# Test 3: Deterministic output with fixed seed
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_seed_same_scores(self):
        robots = [_make_robot(mu=60.0, sigma=10.0), _make_robot(mu=40.0, sigma=6.0)]
        s1 = simulate_alliance_score(robots, n_sims=500, rng=np.random.default_rng(42))
        s2 = simulate_alliance_score(robots, n_sims=500, rng=np.random.default_rng(42))
        np.testing.assert_array_equal(s1, s2)

    def test_different_seed_different_scores(self):
        robots = [_make_robot()]
        s1 = simulate_alliance_score(robots, n_sims=200, rng=np.random.default_rng(1))
        s2 = simulate_alliance_score(robots, n_sims=200, rng=np.random.default_rng(2))
        assert not np.array_equal(s1, s2)

    def test_simulate_match_deterministic(self):
        red = [_make_robot(mu=55.0)]
        blue = [_make_robot(mu=50.0)]
        r1 = simulate_match(red, blue, n_sims=400, rng=np.random.default_rng(77))
        r2 = simulate_match(red, blue, n_sims=400, rng=np.random.default_rng(77))
        assert r1["red_win_prob"] == r2["red_win_prob"]
        np.testing.assert_array_equal(r1["red_scores"], r2["red_scores"])


# ---------------------------------------------------------------------------
# Test 4: Equal alliances → ~50/50 win probability
# ---------------------------------------------------------------------------

class TestEqualAlliances:
    def test_near_fifty_fifty(self):
        """10k sims; equal alliances should land within ±3% of 50%."""
        red, blue = _equal_alliances(mu=60.0, sigma=10.0)
        result = simulate_match(red, blue, n_sims=10_000,
                                rng=np.random.default_rng(123))
        # Red and Blue should each be close to 50% (ties are rare)
        assert abs(result["red_win_prob"] - 0.50) < 0.03
        assert abs(result["blue_win_prob"] - 0.50) < 0.03


# ---------------------------------------------------------------------------
# Test 5: Dropout raises variance and lowers expected score
# ---------------------------------------------------------------------------

class TestDropout:
    def test_dropout_lowers_expected_score(self):
        no_dropout = [RobotDistribution(mu=50.0, sigma=5.0, dropout_prob=0.0)]
        with_dropout = [RobotDistribution(mu=50.0, sigma=5.0, dropout_prob=0.5,
                                         dropout_penalty=0.0)]
        rng1 = np.random.default_rng(8)
        rng2 = np.random.default_rng(8)
        s_no = simulate_alliance_score(no_dropout, n_sims=5000, rng=rng1)
        s_drop = simulate_alliance_score(with_dropout, n_sims=5000, rng=rng2)
        # 50% dropout with 0 penalty → expected score ≈ 0.5 * mu
        assert s_drop.mean() < s_no.mean() - 10.0

    def test_dropout_raises_variance(self):
        no_dropout = [RobotDistribution(mu=50.0, sigma=3.0, dropout_prob=0.0)]
        with_dropout = [RobotDistribution(mu=50.0, sigma=3.0, dropout_prob=0.3,
                                         dropout_penalty=0.0)]
        rng1 = np.random.default_rng(9)
        rng2 = np.random.default_rng(9)
        s_no = simulate_alliance_score(no_dropout, n_sims=5000, rng=rng1)
        s_drop = simulate_alliance_score(with_dropout, n_sims=5000, rng=rng2)
        assert s_drop.std() > s_no.std()

    def test_dropout_penalty_applied(self):
        """If a robot always drops out and penalty=−10, mean score ≈ −10."""
        robot = RobotDistribution(mu=50.0, sigma=5.0,
                                  dropout_prob=1.0, dropout_penalty=-10.0)
        rng = np.random.default_rng(11)
        scores = simulate_alliance_score([robot], n_sims=1000, rng=rng)
        assert abs(scores.mean() - (-10.0)) < 0.5


# ---------------------------------------------------------------------------
# Test 6: Empty robots raises ValueError (covered above; explicit class)
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_red_alliance_raises(self):
        blue = [_make_robot()]
        with pytest.raises(ValueError):
            simulate_match([], blue, n_sims=100)

    def test_empty_blue_alliance_raises(self):
        red = [_make_robot()]
        with pytest.raises(ValueError):
            simulate_match(red, [], n_sims=100)

    def test_invalid_dropout_prob_raises(self):
        with pytest.raises(ValueError):
            RobotDistribution(mu=50.0, dropout_prob=1.5)

    def test_negative_dropout_prob_raises(self):
        with pytest.raises(ValueError):
            RobotDistribution(mu=50.0, dropout_prob=-0.1)


# ---------------------------------------------------------------------------
# Test 8: Matches analytic result within 2% for Gaussian case
# ---------------------------------------------------------------------------

class TestAnalyticComparison:
    def test_matches_analytic_win_prob(self):
        """
        For a well-behaved Gaussian case the MC win probability should be
        within 2 percentage points of the NormalDist analytic answer.
        """
        from win_probability import alliance_win_prob

        mu_r, sigma_r = 142.0, 18.0
        mu_b, sigma_b = 131.0, 15.0

        analytic = alliance_win_prob(mu_r, sigma_r, mu_b, sigma_b)

        # Build alliances where each robot contributes 1/3 of alliance mu/sigma
        # The combined alliance sigma_r = sqrt(3 * (sigma_r/sqrt(3))^2) = sigma_r
        per_r = sigma_r / math.sqrt(3)
        per_b = sigma_b / math.sqrt(3)
        red = [RobotDistribution(mu=mu_r / 3, sigma=per_r) for _ in range(3)]
        blue = [RobotDistribution(mu=mu_b / 3, sigma=per_b) for _ in range(3)]

        result = simulate_match(red, blue, n_sims=20_000,
                                rng=np.random.default_rng(2024))
        mc = result["red_win_prob"]
        assert abs(mc - analytic) < 0.02, (
            f"MC={mc:.4f} analytic={analytic:.4f}, diff={abs(mc - analytic):.4f}"
        )


# ---------------------------------------------------------------------------
# Test 10: predict_alliance_with_uncertainty wrapper
# ---------------------------------------------------------------------------

class TestPredictAllianceWithUncertainty:
    def test_returns_required_keys(self):
        teams = [1, 2, 3]
        epa = {1: 50.0, 2: 45.0, 3: 35.0}
        sigma = {1: 8.0, 2: 7.0, 3: 5.0}
        result = predict_alliance_with_uncertainty(
            teams, epa, sigma, n_sims=500, rng=np.random.default_rng(0)
        )
        for key in ("scores", "mean", "std", "ci_90", "robots"):
            assert key in result, f"Missing key: {key}"

    def test_scores_length(self):
        teams = [254, 971, 1678]
        epa = {254: 80.0, 971: 75.0, 1678: 70.0}
        sigma = {}
        result = predict_alliance_with_uncertainty(
            teams, epa, sigma, n_sims=250, rng=np.random.default_rng(5)
        )
        assert len(result["scores"]) == 250

    def test_missing_team_defaults_to_zero_epa(self):
        result = predict_alliance_with_uncertainty(
            [9999], {}, {}, n_sims=100, rng=np.random.default_rng(3)
        )
        # mu=0 → scores should be near 0
        assert abs(result["mean"]) < 1.0

    def test_default_sigma_fraction_applied(self):
        """When sigma is absent, fallback = DEFAULT_SIGMA_FRACTION * mu."""
        teams = [1]
        epa = {1: 100.0}
        result = predict_alliance_with_uncertainty(
            teams, epa, {}, n_sims=200, rng=np.random.default_rng(6)
        )
        robot: RobotDistribution = result["robots"][0]
        assert abs(robot.sigma - DEFAULT_SIGMA_FRACTION * 100.0) < 1e-9

    def test_ci_90_bounds(self):
        teams = [1, 2, 3]
        epa = {1: 60.0, 2: 50.0, 3: 40.0}
        sigma = {1: 8.0, 2: 7.0, 3: 6.0}
        result = predict_alliance_with_uncertainty(
            teams, epa, sigma, n_sims=2000, rng=np.random.default_rng(42)
        )
        lo, hi = result["ci_90"]
        assert lo < result["mean"] < hi


# ---------------------------------------------------------------------------
# Test for predict_win_probability_mc in scout/win_probability.py
# ---------------------------------------------------------------------------

class TestMCWrapperInWinProbability:
    def test_predict_win_probability_mc_keys(self):
        from win_probability import predict_win_probability_mc

        red = [{"epa": 50.0, "sd": 8.0}, {"epa": 45.0, "sd": 7.0},
               {"epa": 35.0, "sd": 5.0}]
        blue = [{"epa": 40.0, "sd": 6.0}, {"epa": 40.0, "sd": 6.0},
                {"epa": 40.0, "sd": 6.0}]
        result = predict_win_probability_mc(
            red, blue, n_sims=500, rng=np.random.default_rng(10)
        )
        assert "red_win_prob" in result
        assert "blue_win_prob" in result
        total = result["red_win_prob"] + result["blue_win_prob"] + result["tie_prob"]
        assert abs(total - 1.0) < 1e-6
