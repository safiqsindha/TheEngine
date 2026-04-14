"""
blueprint/rulebook_beta_prior.py
----------------------------------
Predict the power-curve β from game manual language before any matches are played.

This module implements the Item 4 framework from TOMORROW_POWER_CURVE_WORK.md.
It contains:
  - RulebookSignals dataclass (the feature vector)
  - extract_signals()  — regex/keyword extractor from raw manual text
  - predict_beta()     — weighted-sum prior; coefficients are placeholders
  - beta_posterior()   — Bayesian conjugate update as match data arrives

IMPORTANT: All regression coefficients in predict_beta() are placeholder priors,
NOT fitted values.  They encode directional expectations (e.g. more handoff verbs
→ lower β) but have NOT been calibrated against empirical β* from Item 1.

TODO(Item 4 execution — unblocked by Item 1 empirical β* values):
  - Fit coefficients in predict_beta() via regularized linear regression on the
    13 labeled (signals, β*) pairs from Item 1.
  - Replace keyword counting in extract_signals() with a Haiku structured-extraction
    call (see TODO comment in that function) for better precision on ambiguous clauses.
  - Validate with leave-one-season-out cross-validation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Feature dataclass
# ---------------------------------------------------------------------------

@dataclass
class RulebookSignals:
    """
    Signal vector extracted from a game manual.

    Attributes
    ----------
    handoff_verb_density   : float
        Count of handoff/pass/transfer verbs in the manual, normalized by
        total manual word count × 1000 (so units = occurrences per 1k words).
    alliance_scope_ratio   : float
        Ratio of "ALLIANCE"-scoped scoring clauses to total scoring clauses.
        Range [0, 1]; higher means more alliance-level coupling.
    named_feeder_zones     : int
        Count of distinctly named feeder/loading zones implying dedicated human-
        player or robot-to-robot transfer roles.
    has_possession_limit   : bool
        True if the manual specifies a per-robot game-piece possession limit,
        indicating that robots must cycle quickly rather than hoard.
    has_coop_rp            : bool
        True if the manual includes a co-op / shared ranking point that requires
        inter-robot coordination.
    h_rule_count           : int
        Number of H-rules (defense legality rules) as a proxy for the degree to
        which the GDC expected blocking/interference interactions.
    """
    handoff_verb_density: float   # occurrences per 1k words
    alliance_scope_ratio: float   # [0, 1]
    named_feeder_zones: int
    has_possession_limit: bool
    has_coop_rp: bool
    h_rule_count: int


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

# Handoff/transfer verbs the GDC consistently uses for inter-robot coupling
_HANDOFF_VERBS = [
    r"pass(?:es|ed|ing)?",
    r"hand[\s-]off",
    r"handoff",
    r"deliver(?:s|ed|ing)?(?:\s+to)?",
    r"feed(?:s|ing|er)?",
    r"transfer(?:s|red|ring)?",
    r"load(?:s|ed|ing)?(?:\s+(?:from|to|into))?",
    r"toss(?:es|ed|ing)?",
]
_HANDOFF_PATTERN = re.compile(
    r"|".join(_HANDOFF_VERBS),
    re.IGNORECASE,
)

# Alliance-scoped scoring clause indicators
_ALLIANCE_SCOPE_PATTERN = re.compile(r"\bALLIANCE\b", re.IGNORECASE)

# Robot-scoped scoring clause indicators
_ROBOT_SCOPE_PATTERN = re.compile(r"\bROBOT\b", re.IGNORECASE)

# Named feeder/loading zones
_FEEDER_ZONE_PATTERN = re.compile(
    r"\b(?:LOADING\s+STATION|HUMAN\s+PLAYER\s+STATION|SOURCE|FEEDER|SINGULATION)\b",
    re.IGNORECASE,
)

# Possession limit indicators
_POSSESSION_LIMIT_PATTERN = re.compile(
    r"\b(?:may\s+only\s+possess|possess\s+no\s+more\s+than|maximum\s+of\s+\d+\s+(?:GAME\s+)?PIECE|"
    r"limit\s+of\s+\d+|hold\s+no\s+more\s+than|may\s+not\s+possess\s+more)\b",
    re.IGNORECASE,
)

# Co-op / shared RP triggers
_COOP_RP_PATTERN = re.compile(
    r"\b(?:CO-?OP|COOPERTITION|shared\s+ranking\s+point|alliance\s+ranking\s+point|"
    r"MELODY|ENSEMBLE|LINK|SUSTAINABILITY)\b",
    re.IGNORECASE,
)

# H-rules: lines that start with "H" followed by digits (H101, H201, etc.)
_H_RULE_PATTERN = re.compile(r"\bH\d{2,4}\b")


def extract_signals(manual_text: str) -> RulebookSignals:
    """
    Extract RulebookSignals from raw game manual text.

    This implementation uses regex/keyword counting.  It is intentionally
    conservative: it counts occurrences of well-known GDC vocabulary rather
    than attempting semantic understanding.

    TODO(Item 4 execution — upgrade path):
      Replace or augment this with a Haiku structured-extraction call:
        from anthropic import Anthropic
        client = Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5",
            messages=[{
                "role": "user",
                "content": SIGNAL_EXTRACTION_PROMPT.format(text=manual_text[:50_000]),
            }],
            ...
        )
      A Haiku call would handle paraphrases, negations, and context more reliably
      than pure regex — especially for alliance_scope_ratio which requires clause
      boundary detection.  Unblocked by: Anthropic API key in environment.

    Parameters
    ----------
    manual_text : str — raw text extracted from the game manual PDF.

    Returns
    -------
    RulebookSignals
    """
    if not manual_text or not manual_text.strip():
        # Empty manual: return all-zero/False signals
        return RulebookSignals(
            handoff_verb_density=0.0,
            alliance_scope_ratio=0.0,
            named_feeder_zones=0,
            has_possession_limit=False,
            has_coop_rp=False,
            h_rule_count=0,
        )

    word_count = max(len(manual_text.split()), 1)

    # Handoff verb density (per 1k words)
    handoff_count = len(_HANDOFF_PATTERN.findall(manual_text))
    handoff_verb_density = (handoff_count / word_count) * 1000.0

    # Alliance-scope ratio
    alliance_count = len(_ALLIANCE_SCOPE_PATTERN.findall(manual_text))
    robot_count = len(_ROBOT_SCOPE_PATTERN.findall(manual_text))
    total_scope = alliance_count + robot_count
    alliance_scope_ratio = (alliance_count / total_scope) if total_scope > 0 else 0.0

    # Named feeder zones (distinct matches, not raw count)
    feeder_matches = set(
        m.group(0).upper().replace(" ", "_")
        for m in _FEEDER_ZONE_PATTERN.finditer(manual_text)
    )
    named_feeder_zones = len(feeder_matches)

    # Possession limit
    has_possession_limit = bool(_POSSESSION_LIMIT_PATTERN.search(manual_text))

    # Co-op RP
    has_coop_rp = bool(_COOP_RP_PATTERN.search(manual_text))

    # H-rule count (distinct H-rule identifiers)
    h_rules = set(_H_RULE_PATTERN.findall(manual_text))
    h_rule_count = len(h_rules)

    return RulebookSignals(
        handoff_verb_density=handoff_verb_density,
        alliance_scope_ratio=alliance_scope_ratio,
        named_feeder_zones=named_feeder_zones,
        has_possession_limit=has_possession_limit,
        has_coop_rp=has_coop_rp,
        h_rule_count=h_rule_count,
    )


# ---------------------------------------------------------------------------
# β prediction
# ---------------------------------------------------------------------------

# Placeholder coefficients for the weighted-sum β predictor.
#
# Directional expectations (which will be verified / replaced by regression):
#   - Higher handoff_verb_density  → lower β  (more coupling)
#   - Higher alliance_scope_ratio  → lower β  (alliance-level scoring = coupling)
#   - More named_feeder_zones      → lower β  (specialized roles = coupling)
#   - has_possession_limit=True    → slightly lower β  (forces cycling)
#   - has_coop_rp=True             → lower β  (explicit cross-robot coordination)
#   - More h_rules                 → slightly lower β  (defense = role specialization)
#
# TODO(Item 4 execution — unblocked by Item 1 empirical β* values):
#   Fit these coefficients via ridge regression on 13 labeled seasons.
#   Expected after regression: intercept ~0.95, coefficients tighter than current placeholders.

_INTERCEPT = 0.95       # β starts near linear and is pulled down by coupling signals
_W_HANDOFF = -0.04      # TODO: fit via regression — per-unit-density penalty
_W_ALLIANCE = -0.30     # TODO: fit via regression — alliance scope pulls β toward 0.60
_W_FEEDER = -0.02       # TODO: fit via regression — per-zone penalty
_W_POSSESSION = -0.05   # TODO: fit via regression — possession limit effect
_W_COOP_RP = -0.08      # TODO: fit via regression — co-op RP effect
_W_HRULE = -0.003       # TODO: fit via regression — per-h-rule effect

_BETA_MIN = 0.4
_BETA_MAX = 1.0


def predict_beta(signals: RulebookSignals) -> tuple[float, float]:
    """
    Predict (β_prior, confidence) from RulebookSignals.

    The confidence value is a rough proxy based on signal strength; it is NOT
    a calibrated probability.  After Item 4 regression it should be replaced
    with a model-fit–derived interval.

    TODO(Item 4 execution): replace weighted sum with fitted regression coefficients.
    TODO(Item 4 execution): replace confidence formula with regression R² or
                            leave-one-out prediction interval width.

    Parameters
    ----------
    signals : RulebookSignals extracted from the game manual.

    Returns
    -------
    (β_prior, confidence) where β_prior ∈ [0.4, 1.0] and confidence ∈ [0.0, 1.0].
    """
    raw = (
        _INTERCEPT
        + _W_HANDOFF * signals.handoff_verb_density
        + _W_ALLIANCE * signals.alliance_scope_ratio
        + _W_FEEDER * signals.named_feeder_zones
        + _W_POSSESSION * (1.0 if signals.has_possession_limit else 0.0)
        + _W_COOP_RP * (1.0 if signals.has_coop_rp else 0.0)
        + _W_HRULE * signals.h_rule_count
    )

    beta_prior = float(max(_BETA_MIN, min(_BETA_MAX, raw)))

    # Confidence: stronger signal deviation from neutral → higher confidence.
    # Placeholder formula; will be replaced by regression-derived interval.
    # TODO(Item 4 execution): replace with proper confidence from fitted model.
    signal_strength = abs(raw - _INTERCEPT) / ((_INTERCEPT - _BETA_MIN) + 1e-9)
    confidence = float(max(0.0, min(1.0, signal_strength * 0.8)))

    return beta_prior, confidence


# ---------------------------------------------------------------------------
# Bayesian posterior update
# ---------------------------------------------------------------------------

def beta_posterior(
    beta_prior: float,
    beta_prior_var: float,
    match_derived_beta: float,
    match_count: int,
) -> float:
    """
    Bayesian conjugate Gaussian update: combine rulebook prior with match-derived β.

    As match_count grows, the posterior shrinks toward match_derived_beta and
    the prior does less work.  By ~week 3 (≥30 matches) the prior contributes
    negligibly.

    Standard conjugate-Gaussian form:
        posterior_mean = (prior_mean / prior_var + data_mean * n / noise_var)
                         / (1/prior_var + n/noise_var)

    We treat each match as contributing information with variance = noise_var/match_count.
    A fixed noise_var of 0.01 (σ≈0.1 per match) is a placeholder.

    TODO(Item 4 execution — unblocked by Item 1 data):
      Calibrate noise_var from the empirical spread of β across bootstrap samples.

    Parameters
    ----------
    beta_prior        : float — prior β from predict_beta()
    beta_prior_var    : float — prior variance (uncertainty).  Typical value: 0.025
                        (σ≈0.16, spanning most of the [0.4,1.0] range).
    match_derived_beta: float — β estimated from observed matches (from tune_beta_for_season)
    match_count       : int   — number of matches used to derive match_derived_beta.
                        0 → return prior unchanged.

    Returns
    -------
    float — posterior β estimate, clamped to [0.4, 1.0].
    """
    if match_count <= 0 or beta_prior_var <= 0:
        return float(max(_BETA_MIN, min(_BETA_MAX, beta_prior)))

    # Noise variance per match (placeholder; TODO: calibrate from Item 1 bootstrap spread)
    _NOISE_VAR_PER_MATCH = 0.01  # TODO(Item 4 execution): replace with calibrated value

    # Precision-weighted update
    prior_precision = 1.0 / beta_prior_var
    likelihood_precision = match_count / _NOISE_VAR_PER_MATCH

    posterior_mean = (
        prior_precision * beta_prior + likelihood_precision * match_derived_beta
    ) / (prior_precision + likelihood_precision)

    return float(max(_BETA_MIN, min(_BETA_MAX, posterior_mean)))
