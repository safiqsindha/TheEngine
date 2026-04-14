# Rulebook β Prior — Feature Extraction and Regression Methodology

*Framework document for Item 4 of the Power Curve Attribution work.*
*Created 2026-04-14.  Regression coefficients and validation: TBD — requires
empirical β* from Item 1 data run.*

---

## Motivation

Empirically tuning β requires week-1 match data.  The rulebook β prior lets the
system publish a usable β estimate within 48 hours of kickoff, based solely on
game manual language.  It is treated as a Bayesian prior that gets overwritten by
match-derived evidence as the season progresses.

---

## Feature List and Rationale

Each feature is extracted by `blueprint/rulebook_beta_prior.extract_signals()`.

| Feature | Type | Rationale |
|---------|------|-----------|
| `handoff_verb_density` | float (per 1k words) | GDC consistently uses "pass", "hand off", "deliver", "feed", "transfer" for inter-robot coupling mechanics.  High density → low β. |
| `alliance_scope_ratio` | float [0,1] | Scoring rules referencing ALLIANCE (whole-alliance scoring) vs ROBOT (per-robot scoring) reveal whether credit is inherently coupled.  High ratio → low β. |
| `named_feeder_zones` | int | Dedicated loading/feeding zones (LOADING STATION, SOURCE, FEEDER) create role specialization.  More zones → more coupling → lower β. |
| `has_possession_limit` | bool | Per-robot possession limits force cycling and reduce hoarding; moderate coupling effect. |
| `has_coop_rp` | bool | Co-op / COOPERTITION ranking points explicitly require inter-robot coordination.  True → lower β. |
| `h_rule_count` | int | Defense-legality rules (H-rules) proxy the GDC's expectation of role-based interactions; more rules → lower β (weak signal). |

### Signal extraction implementation

Current implementation: regex/keyword counting in `extract_signals()`.

Upgrade path: replace with a Claude Haiku structured-extraction call for better
handling of paraphrases, negation, and clause boundary detection.
See TODO comment in `blueprint/rulebook_beta_prior.py:extract_signals()`.

---

## Regression Model

Goal: fit a function f(signals) → β* that predicts the empirical β* from Item 1.

**Model**: regularized linear regression (Ridge, α to be chosen via cross-validation).

**Training set**: 13 labeled (signals, β*) pairs — one per season 2013–2025.

**Features used in regression**: the 6 features above, plus interactions to be
determined after seeing the Item 1 results.

**Status**: TBD — requires labeled β* from Item 1 data run.

Placeholder coefficients currently in `predict_beta()`:
- Intercept: 0.95
- handoff_verb_density: −0.04 per unit
- alliance_scope_ratio: −0.30
- named_feeder_zones: −0.02 per zone
- has_possession_limit: −0.05
- has_coop_rp: −0.08
- h_rule_count: −0.003 per rule

These encode directional expectations and will be replaced after regression.

---

## Leave-One-Out Validation Table

Target: β prediction within ±0.10 of empirical β* for each held-out season.

All values TBD — requires empirical β* from Item 1 and fitted regression from Item 4.

| Year    | Game              | Held-out β* | LOO-predicted β | Residual | Pass (|resid|≤0.10)? |
|---------|-------------------|-------------|-----------------|----------|----------------------|
| 2013    | Ultimate Ascent   | TBD         | TBD             | TBD      | TBD                  |
| 2014    | Aerial Assist     | TBD         | TBD             | TBD      | TBD                  |
| 2015    | Recycle Rush      | TBD         | TBD             | TBD      | TBD                  |
| 2016    | Stronghold        | TBD         | TBD             | TBD      | TBD                  |
| 2017    | Steamworks        | TBD         | TBD             | TBD      | TBD                  |
| 2018    | Power Up          | TBD         | TBD             | TBD      | TBD                  |
| 2019    | Deep Space        | TBD (cycle) | TBD             | TBD      | TBD                  |
| 2019    | Deep Space        | TBD (climb) | TBD             | TBD      | TBD                  |
| 2020-21 | Infinite Recharge | TBD         | TBD             | TBD      | TBD                  |
| 2022    | Rapid React       | TBD         | TBD             | TBD      | TBD                  |
| 2023    | Charged Up        | TBD         | TBD             | TBD      | TBD                  |
| 2024    | Crescendo         | TBD         | TBD             | TBD      | TBD                  |
| 2025    | Reefscape         | TBD         | TBD             | TBD      | TBD                  |

---

## Bayesian Update Schedule

The prior from `predict_beta()` serves as β₀.  As match data arrives, the
posterior from `beta_posterior()` replaces it:

| Data available | Expected posterior weight on prior |
|---|---|
| Kickoff + 48h (manual only) | 100% prior |
| Week 1 (≈30 matches) | ~25% prior, ~75% match-derived |
| Week 2 (≈100 matches) | ~8% prior, ~92% match-derived |
| Week 3+ (≈200+ matches) | prior negligible |

The crossover schedule depends on `beta_prior_var` and the calibrated noise
variance per match — both TBD pending Item 1 data.

---

## Sanity Checks (Regression Should Learn These)

These are documented expectations from the prior table, NOT regression outputs:

- **Aerial Assist 2014**: handoff-heavy manual → β* ~0.60 ✓
- **Recycle Rush 2015**: co-op RP + independent totes → β* ~0.85 ✓
- **Charged Up 2023**: independent grid slots → β* ~0.80 ✓

If the regression produces β estimates that contradict these expectations by more
than ±0.10, review the feature extraction and coefficient priors before accepting
the fitted model.

---

## Next Steps

1. Complete Item 1 data run → obtain empirical β* for all 13 seasons.
2. Extract signals from 2013–2025 manual PDFs (PDFs stored in `design-intelligence/manuals/` — TBD).
3. Fit Ridge regression on (signals, β*) pairs.
4. Run leave-one-out validation; verify ±0.10 target is met.
5. Update coefficient values in `predict_beta()` and confidence formula.
6. Calibrate `_NOISE_VAR_PER_MATCH` in `beta_posterior()` from Item 1 bootstrap spread.
