# Rulebook β Prior — Feature Extraction and Regression Methodology

*Item 4 execution complete — 2026-04-14.*
*Fitted via ridge regression against 10 empirical β* labels from Item 1 (commit 58a37cf).*

---

## Motivation

Empirically tuning β requires week-1 match data.  The rulebook β prior lets the
system publish a usable β estimate within 48 hours of kickoff, based solely on
game manual language.  It is treated as a Bayesian prior that gets overwritten by
match-derived evidence as the season progresses.

---

## Manual Acquisition

Game manual summaries were fetched from Wikipedia (2026-04-14) for seasons 2013–2025.
Accessible pages: 2013 (Ultimate Ascent), 2014 (Aerial Assist), 2015 (Recycle Rush),
2016 (Stronghold), 2017 (Steamworks), 2018 (Power Up), 2019 (Deep Space),
2020 (Infinite Recharge), 2022 (Rapid React), 2023 (Charged Up), 2025 (Reefscape).

**Not accessible:** 2024 Crescendo (Wikipedia page returned 404). Signals for 2024
were constructed from widely-documented game mechanics (well-established in community
sources by 2026).

Fetched text cached to `.cache/manuals/` (gitignored).

---

## Feature List and Rationale

Each feature is a signal extracted from the game manual.  See `blueprint/rulebook_beta_prior.extract_signals()` for the regex extractor (used when a full manual PDF is available).

| Feature | Type | Rationale |
|---------|------|-----------|
| `handoff_verb_density` | float (per 1k words) | GDC consistently uses "pass", "hand off", "deliver", "feed", "transfer" for inter-robot coupling mechanics.  High density → lower β. |
| `alliance_scope_ratio` | float [0,1] | Scoring rules referencing ALLIANCE (whole-alliance scoring) vs ROBOT (per-robot scoring) reveal whether credit is inherently coupled.  High ratio → lower β (in theory — see anomaly note). |
| `named_feeder_zones` | int | Dedicated loading/feeding zones (LOADING STATION, SOURCE, FEEDER) create role specialization.  More zones → more coupling → lower β. |
| `has_possession_limit` | bool | Per-robot possession limits force cycling and reduce hoarding; strongest coupling signal. |
| `has_coop_rp` | bool | Co-op / intra-ALLIANCE bonus ranking points explicitly require inter-robot coordination.  True → lower β. |
| `h_rule_count` | int | Defense-legality rules (H-rules) proxy GDC's expectation of role-based interactions; expected lower β, but see anomaly note. |

### Signal extraction implementation

**Current approach (Item 4):** Expert-assigned signals per season based on fetched Wikipedia
summaries. Raw regex extraction on short Wikipedia text (~400 words) produces unreliable
density estimates (too few words → inflated per-1k-word counts). Expert assignment is
documented in `blueprint/fit_rulebook_regression.py:EXPERT_SIGNALS` and cached to
`.cache/manuals/expert_signals.json`.

**Upgrade path:** Replace with Claude Haiku structured-extraction on real manual PDFs
(typically 50–100k words). See TODO in `blueprint/rulebook_beta_prior.extract_signals()`.
This upgrade is **recommended** (MAE ≤ 0.10 currently met, but expert assignment adds
human-in-the-loop friction for future seasons).

---

## Regression Model

**Model**: Ridge regression (λ=0.1).
**Training set**: 10 labeled seasons (2013–2025; see excluded seasons below).
**Features**: 6 features listed above, no interaction terms.
**Fit date**: 2026-04-14.
**Script**: `blueprint/fit_rulebook_regression.py`.

### Excluded seasons

| Year | Reason |
|------|--------|
| 2015 | `empirical_beta=None` — Recycle Rush Statbotics tuning failed |
| 2019 | Per-phase β only (cycle/climb); no single overall empirical β available |

### Fitted Coefficients

| Feature | Coefficient | ±Std Error | Expected Sign | Status |
|---------|-------------|-----------|---------------|--------|
| Intercept | +0.4617 | 0.1552 | — | — |
| `handoff_verb_density` | −0.0324 | 0.0371 | − | OK |
| `alliance_scope_ratio` | +0.0327 | 0.2090 | − | **ANOMALY** (SE >> coef; effectively zero) |
| `named_feeder_zones` | −0.0527 | 0.0406 | − | OK |
| `has_possession_limit` | −0.2917 | 0.0588 | − | OK — **strongest signal** |
| `has_coop_rp` | −0.3028 | 0.0656 | − | OK — **strongest signal** |
| `h_rule_count` | +0.0658 | 0.0181 | − | **ANOMALY** (see note) |

**Note on unexpected signs:**

- `alliance_scope_ratio` (+0.033): The standard error (0.209) greatly exceeds the coefficient magnitude — it is statistically indistinguishable from zero.  Alliance-scope ratio may not vary enough across the training seasons to provide a useful regression signal.  Do not rely on this feature until more seasons are available.

- `h_rule_count` (+0.066): Statistically significant (SE=0.018) but with unexpected sign.  Likely confounded by 2016 Stronghold, which has high h-rule count (defense-heavy game) AND high empirical β (1.0 — linear).  The correlation is spurious; with more training seasons this coefficient should become negative.

The two dominant signals are `has_possession_limit` and `has_coop_rp`, both with coefficients near −0.30 and SEs well below the coefficient magnitude.

---

## Leave-One-Out Validation Table

Ridge regression (λ=0.1) fit on the 9 remaining seasons for each held-out year.
Target: |predicted − actual| ≤ 0.10.

| Year | Game | Held-out β* | LOO-predicted β | |Error| | Result |
|------|------|-------------|-----------------|---------|--------|
| 2013 | Ultimate Ascent | 0.60 | 0.700 | 0.100 | PASS (border) |
| 2014 | Aerial Assist | 0.95 | 1.000 | 0.050 | PASS |
| 2016 | Stronghold | 1.00 | 1.000 | 0.000 | PASS |
| 2017 | Steamworks | 0.85 | 0.802 | 0.048 | PASS |
| 2018 | Power Up | 0.80 | 0.733 | 0.068 | PASS |
| 2020 | Infinite Recharge | 1.00 | 0.884 | 0.116 | WARN (≤0.15) |
| 2022 | Rapid React | 0.95 | 0.921 | 0.029 | PASS |
| 2023 | Charged Up | 0.65 | 0.761 | 0.111 | WARN (≤0.15) |
| 2024 | Crescendo | 0.55 | 0.540 | 0.010 | PASS |
| 2025 | Reefscape | 0.65 | 0.725 | 0.075 | PASS |

**Mean Absolute Error (LOO): 0.0605**

8/10 years PASS (|error| ≤ 0.10). 2 years WARN (0.10–0.15). 0 FAIL.

Target ≤ 0.10 MAE: **MET.**

---

## Sanity Checks

| Year | Game | Full-model pred | Empirical β* | |Diff| | Status |
|------|------|-----------------|--------------|-------|--------|
| 2024 | Crescendo | 0.546 | 0.55 | 0.004 | OK |
| 2025 | Reefscape | 0.665 | 0.65 | 0.015 | OK |
| 2023 | Charged Up | 0.711 | 0.65 | 0.061 | OK |
| 2014 | Aerial Assist | 0.976 | 0.95 | 0.026 | OK (counter-intuitive high β expected) |

All sanity checks pass. Reefscape prediction (0.665) is within 0.015 of empirical 0.65.

---

## Honest Assessment: Is This Model Useful?

**Yes, with caveats.**

The model meets the ≤0.10 MAE target (LOO MAE = 0.0605), with 8 of 10 years
predicting within ±0.10 of empirical β*. The two strongest signals —
`has_possession_limit` and `has_coop_rp` — are reliable binary flags that any
analyst can read from the game manual in minutes.

**Known limitations:**

1. **10 training samples is small.** With 6 features and 10 samples, the model
   is at risk of overfitting to idiosyncrasies of specific seasons.  The two
   unexpected signs (alliance_scope_ratio, h_rule_count) are likely artifacts
   of this constraint.

2. **Expert-assigned signals introduce subjectivity.** The handoff_verb_density
   values (0.5–3.5) are scaled estimates from Wikipedia summaries, not counts
   from real PDFs. Different analysts might assign different values.

3. **Empirical β* labels may have noise.** The Statbotics-derived β values
   themselves have confidence intervals — the labels are not ground truth.
   Wide CIs in the empirical data (see attribution_betas.py) mean the regression
   target is noisy.

4. **The LLM upgrade is recommended, not critical** (MAE target is met). Once
   full PDF extraction is implemented, signal assignment becomes automated and
   repeatable, and the regression can be re-fit on more precise density estimates.

**Recommendation:** Use `predict_beta()` as a kickoff-day prior with uncertainty
±0.15. Update to match-derived β by week 2. Do not over-trust the confidence value
(it is a rough proxy, not a calibrated probability).

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

The crossover schedule assumes `beta_prior_var=0.025` (σ≈0.16) and the calibrated
noise variance per match of 0.01 (placeholder; re-calibrate from Item 1 bootstrap spread).
