"""Tests for scout/trueskill_ratings.py — TrueSkill Bayesian ratings."""

import math
import pytest

from scout.trueskill_ratings import (
    TeamRating,
    conservative_skill,
    from_match_history,
    predict_match_win_prob,
    update_alliance_match,
    DRAW_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh(num: int) -> TeamRating:
    return TeamRating(team_number=num)


def _alliance(nums):
    return [_fresh(n) for n in nums]


# ---------------------------------------------------------------------------
# 1. Fresh team defaults
# ---------------------------------------------------------------------------

class TestFreshDefaults:
    def test_mu_is_25(self):
        r = _fresh(2950)
        assert r.mu == pytest.approx(25.0)

    def test_sigma_is_25_over_3(self):
        r = _fresh(2950)
        assert r.sigma == pytest.approx(25.0 / 3.0, rel=1e-6)

    def test_matches_played_zero(self):
        r = _fresh(2950)
        assert r.matches_played == 0


# ---------------------------------------------------------------------------
# 2. Win raises mu, shrinks sigma
# ---------------------------------------------------------------------------

class TestWinEffect:
    def setup_method(self):
        self.red = _alliance([1, 2, 3])
        self.blue = _alliance([4, 5, 6])
        self.new_red, self.new_blue = update_alliance_match(
            self.red, self.blue, red_score=100, blue_score=50
        )

    def test_winner_mu_increases(self):
        for orig, updated in zip(self.red, self.new_red):
            assert updated.mu > orig.mu

    def test_winner_sigma_shrinks(self):
        for orig, updated in zip(self.red, self.new_red):
            assert updated.sigma < orig.sigma

    def test_loser_mu_decreases(self):
        for orig, updated in zip(self.blue, self.new_blue):
            assert updated.mu < orig.mu

    def test_matches_played_incremented(self):
        for r in self.new_red:
            assert r.matches_played == 1
        for b in self.new_blue:
            assert b.matches_played == 1


# ---------------------------------------------------------------------------
# 3. Loss lowers mu
# ---------------------------------------------------------------------------

class TestLossEffect:
    def test_loser_mu_lower_than_winner(self):
        red = _alliance([10, 11, 12])
        blue = _alliance([13, 14, 15])
        new_red, new_blue = update_alliance_match(
            red, blue, red_score=30, blue_score=90
        )
        for r, nr in zip(red, new_red):
            assert nr.mu < r.mu
        for b, nb in zip(blue, new_blue):
            assert nb.mu > b.mu


# ---------------------------------------------------------------------------
# 4. conservative_skill = mu - 3*sigma
# ---------------------------------------------------------------------------

class TestConservativeSkill:
    def test_fresh_team(self):
        r = _fresh(9999)
        expected = r.mu - 3.0 * r.sigma
        assert conservative_skill(r) == pytest.approx(expected)

    def test_after_wins(self):
        red = _alliance([20, 21, 22])
        blue = _alliance([23, 24, 25])
        new_red, _ = update_alliance_match(red, blue, 120, 40)
        for r in new_red:
            assert conservative_skill(r) == pytest.approx(r.mu - 3.0 * r.sigma)

    def test_negative_for_fresh_team(self):
        # 25 - 3*(25/3) = 25 - 25 = 0 exactly for fresh defaults
        r = _fresh(1)
        assert conservative_skill(r) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 5. predict_match_win_prob in [0, 1]
# ---------------------------------------------------------------------------

class TestPredictWinProb:
    def test_evenly_matched_near_half(self):
        red = _alliance([30, 31, 32])
        blue = _alliance([33, 34, 35])
        p = predict_match_win_prob(red, blue)
        assert 0.0 <= p <= 1.0
        assert p == pytest.approx(0.5, abs=0.05)

    def test_strong_red_above_half(self):
        strong = [TeamRating(team_number=i, mu=40, sigma=2) for i in [1, 2, 3]]
        weak = [TeamRating(team_number=i, mu=10, sigma=2) for i in [4, 5, 6]]
        p = predict_match_win_prob(strong, weak)
        assert p > 0.9

    def test_strong_blue_below_half(self):
        weak = [TeamRating(team_number=i, mu=10, sigma=2) for i in [1, 2, 3]]
        strong = [TeamRating(team_number=i, mu=40, sigma=2) for i in [4, 5, 6]]
        p = predict_match_win_prob(weak, strong)
        assert p < 0.1

    def test_empty_red_returns_half(self):
        blue = _alliance([4, 5, 6])
        p = predict_match_win_prob([], blue)
        assert p == 0.5

    def test_empty_blue_returns_half(self):
        red = _alliance([1, 2, 3])
        p = predict_match_win_prob(red, [])
        assert p == 0.5


# ---------------------------------------------------------------------------
# 6. Batch seed from match history converges sigma downward
# ---------------------------------------------------------------------------

class TestFromMatchHistory:
    def _make_history(self, n_matches: int = 10) -> list[dict]:
        matches = []
        for i in range(n_matches):
            matches.append({
                "red_alliance": [1, 2, 3],
                "blue_alliance": [4, 5, 6],
                "red_score": 80 + i,
                "blue_score": 60,
            })
        return matches

    def test_sigma_decreases_after_matches(self):
        fresh_sigma = 25.0 / 3.0
        ratings = from_match_history(self._make_history(10))
        for team_num in [1, 2, 3, 4, 5, 6]:
            assert ratings[team_num].sigma < fresh_sigma

    def test_teams_present_in_result(self):
        ratings = from_match_history(self._make_history(5))
        assert set(ratings.keys()) == {1, 2, 3, 4, 5, 6}

    def test_matches_played_count(self):
        ratings = from_match_history(self._make_history(10))
        for team_num in [1, 2, 3, 4, 5, 6]:
            assert ratings[team_num].matches_played == 10

    def test_empty_history_returns_empty(self):
        ratings = from_match_history([])
        assert ratings == {}


# ---------------------------------------------------------------------------
# 7. Tie handling
# ---------------------------------------------------------------------------

class TestTieHandling:
    def test_exact_tie_is_draw(self):
        red = _alliance([40, 41, 42])
        blue = _alliance([43, 44, 45])
        new_red, new_blue = update_alliance_match(red, blue, 75, 75)
        # In a draw both sides should converge toward each other (sigma shrinks)
        for r in new_red:
            assert r.sigma < 25.0 / 3.0
        for b in new_blue:
            assert b.sigma < 25.0 / 3.0

    def test_within_threshold_treated_as_draw(self):
        """Scores within DRAW_THRESHOLD should produce symmetric updates."""
        red = _alliance([50, 51, 52])
        blue = _alliance([53, 54, 55])
        new_red, new_blue = update_alliance_match(
            red, blue, red_score=75, blue_score=75 + DRAW_THRESHOLD
        )
        # Both should shrink sigma similarly (draw result)
        red_mu_delta = new_red[0].mu - red[0].mu
        blue_mu_delta = new_blue[0].mu - blue[0].mu
        # In a draw the mu deltas should be small and symmetric
        assert abs(red_mu_delta) < 1.0
        assert abs(blue_mu_delta) < 1.0
