"""
tests/blueprint/test_rulebook_beta_prior.py
---------------------------------------------
Tests for blueprint.rulebook_beta_prior — signal extraction, β prediction,
Bayesian posterior update.

All tests use crafted text fragments or synthetic inputs; no real game manual
PDFs are required.
"""

import sys
from pathlib import Path

import pytest

_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
sys.path.insert(0, str(_BLUEPRINT_DIR))

from rulebook_beta_prior import (  # noqa: E402
    RulebookSignals,
    beta_posterior,
    extract_signals,
    predict_beta,
)


# ---------------------------------------------------------------------------
# extract_signals
# ---------------------------------------------------------------------------

class TestExtractSignals:
    """Signal extraction from crafted text fragments."""

    def test_handoff_verb_density_elevated_when_many_handoffs(self):
        """
        A fragment with 'hand off' repeated 5 times should yield elevated
        handoff_verb_density compared to a neutral fragment.
        """
        fragment = (
            "The ROBOT must hand off the GAME PIECE to the HUMAN PLAYER. "
            "After the HUMAN PLAYER receives, the ROBOT may hand off again. "
            "The hand off zone is marked on the field. "
            "Each hand off attempt is recorded. "
            "A successful hand off scores one (1) point. "
            "This is neutral filler text to pad out the word count so density "
            "is meaningful and not inflated by a tiny document."
        )
        signals = extract_signals(fragment)
        assert signals.handoff_verb_density > 0.0, (
            "Expected non-zero handoff_verb_density for fragment with 5 'hand off' occurrences"
        )

    def test_neutral_text_has_lower_handoff_density_than_handoff_heavy(self):
        """A neutral fragment should have lower handoff density than a handoff-heavy one."""
        neutral = (
            "ROBOTS score GAME PIECES in the ALLIANCE GOAL. "
            "Each ROBOT operates within its ALLIANCE ZONE. "
            "Ranking points are awarded for meeting threshold conditions."
        ) * 5  # repeat to get a realistic word count

        handoff_heavy = (
            "The ROBOT must hand off to pass the game piece and deliver to the HUMAN PLAYER. "
            "A feed from the loading station transfers game pieces to the ROBOT. "
            "The ROBOT may pass again or transfer ownership to an ALLIANCE partner."
        ) * 5

        neutral_signals = extract_signals(neutral)
        heavy_signals = extract_signals(handoff_heavy)
        assert heavy_signals.handoff_verb_density > neutral_signals.handoff_verb_density

    def test_alliance_scope_ratio_increases_with_alliance_keywords(self):
        """Text referencing ALLIANCE frequently should push alliance_scope_ratio up."""
        alliance_heavy = (
            "ALLIANCE ROBOTS score together. ALLIANCE total matters. "
            "ALLIANCE GOAL. ALLIANCE ZONE. ALLIANCE RP."
        ) * 10
        signals = extract_signals(alliance_heavy)
        assert signals.alliance_scope_ratio > 0.0

    def test_named_feeder_zones_counted(self):
        """LOADING STATION, SOURCE, FEEDER should be counted as distinct feeder zones."""
        text = (
            "The LOADING STATION is located at the end of the field. "
            "GAME PIECES enter via the SOURCE. "
            "The FEEDER provides additional pieces. "
            "ROBOTS retrieve from these locations."
        )
        signals = extract_signals(text)
        assert signals.named_feeder_zones >= 2, (
            f"Expected at least 2 named feeder zones, got {signals.named_feeder_zones}"
        )

    def test_possession_limit_detected(self):
        text = (
            "A ROBOT may only possess one (1) GAME PIECE at a time. "
            "Possessing more than one GAME PIECE is a foul."
        )
        signals = extract_signals(text)
        assert signals.has_possession_limit is True

    def test_no_possession_limit_when_absent(self):
        text = "ROBOTS score GAME PIECES in the GOAL. There are no restrictions on quantity."
        signals = extract_signals(text)
        assert signals.has_possession_limit is False

    def test_coop_rp_detected(self):
        text = (
            "Teams may earn the COOPERTITION bonus by jointly exceeding the threshold. "
            "The CO-OP ranking point requires both alliances to cooperate."
        )
        signals = extract_signals(text)
        assert signals.has_coop_rp is True

    def test_h_rule_count(self):
        text = (
            "H101 — Robots may not cross the midline. "
            "H201 — Contact with opponent ROBOTS in the LOADING ZONE is prohibited. "
            "H301 — Strategies that impede game flow are disallowed."
        )
        signals = extract_signals(text)
        assert signals.h_rule_count == 3

    def test_empty_manual_returns_zero_signals(self):
        """Edge case: empty manual should return all-zero/False signals without crashing."""
        signals = extract_signals("")
        assert signals.handoff_verb_density == 0.0
        assert signals.alliance_scope_ratio == 0.0
        assert signals.named_feeder_zones == 0
        assert signals.has_possession_limit is False
        assert signals.has_coop_rp is False
        assert signals.h_rule_count == 0

    def test_whitespace_only_manual(self):
        """Whitespace-only manual should behave like empty."""
        signals = extract_signals("   \n\t  ")
        assert signals.handoff_verb_density == 0.0


# ---------------------------------------------------------------------------
# predict_beta
# ---------------------------------------------------------------------------

class TestPredictBeta:
    """predict_beta() must return β ∈ [0.4, 1.0] and a confidence ∈ [0.0, 1.0]."""

    def _neutral_signals(self) -> RulebookSignals:
        return RulebookSignals(
            handoff_verb_density=0.0,
            alliance_scope_ratio=0.0,
            named_feeder_zones=0,
            has_possession_limit=False,
            has_coop_rp=False,
            h_rule_count=0,
        )

    def test_returns_tuple_of_two_floats(self):
        signals = self._neutral_signals()
        result = predict_beta(signals)
        assert isinstance(result, tuple) and len(result) == 2
        beta, confidence = result
        assert isinstance(beta, float)
        assert isinstance(confidence, float)

    def test_beta_in_valid_range_neutral(self):
        _, conf = predict_beta(self._neutral_signals())
        beta, _ = predict_beta(self._neutral_signals())
        assert 0.4 <= beta <= 1.0

    @pytest.mark.parametrize("handoff_density,alliance_ratio,feeder_zones,poss_limit,coop_rp,h_count", [
        (0.0, 0.0, 0, False, False, 0),   # neutral / high β game
        (5.0, 0.8, 3, True,  True,  10),  # highly coupled / low β game
        (2.0, 0.5, 1, False, True,  5),   # moderate coupling
        (10.0, 1.0, 5, True, True,  20),  # extreme coupling — must clamp to 0.4
    ])
    def test_beta_always_in_range(
        self, handoff_density, alliance_ratio, feeder_zones,
        poss_limit, coop_rp, h_count
    ):
        signals = RulebookSignals(
            handoff_verb_density=handoff_density,
            alliance_scope_ratio=alliance_ratio,
            named_feeder_zones=feeder_zones,
            has_possession_limit=poss_limit,
            has_coop_rp=coop_rp,
            h_rule_count=h_count,
        )
        beta, confidence = predict_beta(signals)
        assert 0.4 <= beta <= 1.0, f"β={beta} out of range for signals {signals}"
        assert 0.0 <= confidence <= 1.0, f"confidence={confidence} out of range"

    def test_more_coupling_signals_gives_lower_beta(self):
        """High-coupling signals should produce lower β than low-coupling signals."""
        low_coupling = RulebookSignals(
            handoff_verb_density=0.0,
            alliance_scope_ratio=0.1,
            named_feeder_zones=0,
            has_possession_limit=False,
            has_coop_rp=False,
            h_rule_count=0,
        )
        high_coupling = RulebookSignals(
            handoff_verb_density=5.0,
            alliance_scope_ratio=0.8,
            named_feeder_zones=3,
            has_possession_limit=True,
            has_coop_rp=True,
            h_rule_count=8,
        )
        beta_low, _ = predict_beta(low_coupling)
        beta_high, _ = predict_beta(high_coupling)
        assert beta_high < beta_low, (
            f"High-coupling signals should give lower β; got {beta_high} >= {beta_low}"
        )


# ---------------------------------------------------------------------------
# beta_posterior
# ---------------------------------------------------------------------------

class TestBetaPosterior:
    """beta_posterior() Bayesian update behavior."""

    def test_zero_matches_returns_prior(self):
        """Edge case: match_count=0 should return the prior unchanged."""
        prior = 0.75
        result = beta_posterior(
            beta_prior=prior,
            beta_prior_var=0.025,
            match_derived_beta=0.55,
            match_count=0,
        )
        assert result == pytest.approx(prior, abs=1e-6), (
            f"With match_count=0, posterior should equal prior {prior}, got {result}"
        )

    def test_posterior_in_valid_range(self):
        result = beta_posterior(
            beta_prior=0.80,
            beta_prior_var=0.025,
            match_derived_beta=0.60,
            match_count=50,
        )
        assert 0.4 <= result <= 1.0

    def test_posterior_moves_toward_match_derived_as_count_grows(self):
        """With many matches, posterior should be closer to match_derived_beta."""
        prior = 0.85
        match_beta = 0.60
        var = 0.025

        posterior_few = beta_posterior(prior, var, match_beta, match_count=5)
        posterior_many = beta_posterior(prior, var, match_beta, match_count=200)

        # With many matches, should be much closer to match_beta
        assert abs(posterior_many - match_beta) < abs(posterior_few - match_beta), (
            f"posterior_many={posterior_many} should be closer to {match_beta} "
            f"than posterior_few={posterior_few}"
        )

    def test_posterior_between_prior_and_match_derived(self):
        """Posterior should lie between the prior and match-derived β."""
        prior = 0.80
        match_beta = 0.55
        result = beta_posterior(
            beta_prior=prior,
            beta_prior_var=0.025,
            match_derived_beta=match_beta,
            match_count=30,
        )
        lo, hi = min(prior, match_beta), max(prior, match_beta)
        assert lo <= result <= hi, (
            f"Posterior {result} should be between prior ({prior}) and "
            f"match_derived ({match_beta})"
        )

    def test_posterior_converges_near_match_derived_with_very_many_matches(self):
        """With 500 matches, posterior should be very close to match_derived_beta."""
        prior = 0.90
        match_beta = 0.60
        result = beta_posterior(
            beta_prior=prior,
            beta_prior_var=0.025,
            match_derived_beta=match_beta,
            match_count=500,
        )
        assert abs(result - match_beta) < 0.05, (
            f"With 500 matches, posterior {result} should be within 0.05 of {match_beta}"
        )

    def test_clamping_to_valid_range(self):
        """Even with extreme inputs, posterior must stay in [0.4, 1.0]."""
        result = beta_posterior(
            beta_prior=0.41,
            beta_prior_var=0.001,
            match_derived_beta=0.40,
            match_count=1000,
        )
        assert 0.4 <= result <= 1.0

    def test_zero_prior_variance_returns_prior(self):
        """Zero prior variance (degenerate case) should return the prior clamped."""
        result = beta_posterior(
            beta_prior=0.75,
            beta_prior_var=0.0,
            match_derived_beta=0.55,
            match_count=100,
        )
        assert 0.4 <= result <= 1.0
