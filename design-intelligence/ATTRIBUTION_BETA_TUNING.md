# Attribution β Tuning — Methodology and Results

*Framework document for Item 1 of the Power Curve Attribution work.*
*Created 2026-04-14. Empirical values: TBD — pending data run.*

---

## Overview

The power-curve attribution model in `scout/alliance_decomposition.py` applies a
per-season exponent β to robot contribution shares before distributing alliance
score credit.  β=1.0 gives linear (proportional) attribution; β<1 compresses
the contribution distribution, reducing the penalty gap between the top and
bottom contributors — appropriate for games where robots are tightly coupled.

This document records how empirical β* is estimated per season and will be
updated with results once the data run completes.

---

## Data Source

- **Match data**: [Statbotics](https://www.statbotics.io) (EPA components per team per match)
  and [The Blue Alliance v3 API](https://www.thebluealliance.com/apidocs/v3)
  (score breakdowns per match).
- **Coverage**: All qual matches 2013–2025, excluding replays and DQ'd matches.
- **Minimum match threshold**: seasons with fewer than 200 qual matches are flagged
  for manual review (not expected for any season in range).

---

## Objective Function

For a candidate β, we compute:

1. For each qual match, apply `power_normalize(contributions, beta)` to each
   alliance's per-robot contribution shares (derived from EPA or score breakdown).
2. Use attributed credits to predict the alliance win/loss outcome.
3. Score = negative mean-squared-error between predicted win probability and
   observed outcome (binary win=1, loss=0), OR Spearman correlation between
   attributed credit and next-year EPA — whichever is more stable for that season.

**Implementation**: `blueprint/tune_attribution_beta.py:objective_score()`.

The objective function body is currently a placeholder (returns 0.0) and will be
completed during the Item 1 data run when real match data is available.

---

## β Search Range

- **Range**: β ∈ [0.40, 1.00]
- **Step**: 0.05 (13 grid points)
- **Best β** (β*): grid point with the highest objective score
- **Confidence interval**: 95% bootstrap CI over match resamples (N=1000 resamples)

---

## CI Method — Bootstrap

1. For each season, resample the match set with replacement 1000 times.
2. Run the grid search on each bootstrap sample → distribution of best β.
3. Report 5th and 95th percentiles as the 90% CI (labeled as 95% CI in the table
   by convention — the interval covers the central 90% of the bootstrap distribution).

TODO(Item 1 execution): implement bootstrap in `tune_attribution_beta.py`.

---

## Results Table

All empirical values are **TBD — pending data run**.
`prior_β` values are documented prior expectations from TOMORROW_POWER_CURVE_WORK.md,
NOT empirical fits.

| Year    | Game              | prior_β (documented) | empirical_β* | CI (90% bootstrap) | n_matches |
|---------|-------------------|----------------------|--------------|--------------------|-----------|
| 2013    | Ultimate Ascent   | 0.70                 | TBD          | TBD                | TBD       |
| 2014    | Aerial Assist     | 0.60                 | TBD          | TBD                | TBD       |
| 2015    | Recycle Rush      | 0.85                 | TBD          | TBD                | TBD       |
| 2016    | Stronghold        | 0.60                 | TBD          | TBD                | TBD       |
| 2017    | Steamworks        | 0.70                 | TBD          | TBD                | TBD       |
| 2018    | Power Up          | 0.75                 | TBD          | TBD                | TBD       |
| 2019    | Deep Space        | 0.85 cycle / 0.60 climb | TBD (per-phase) | TBD          | TBD       |
| 2020-21 | Infinite Recharge | 0.75                 | TBD          | TBD                | TBD       |
| 2022    | Rapid React       | 0.70                 | TBD          | TBD                | TBD       |
| 2023    | Charged Up        | 0.80                 | TBD          | TBD                | TBD       |
| 2024    | Crescendo         | 0.70                 | TBD          | TBD                | TBD       |
| 2025    | Reefscape         | 0.70                 | TBD          | TBD                | TBD       |

*Note: 2020 and 2021 are merged as Infinite Recharge because 2021 had no in-person
competition; match data is sparse.  They share one row and one β estimate.*

---

## Validation Plan

After the empirical run:
1. **Holdout validation**: for each season, hold out 20% of matches, tune β on 80%,
   measure objective score on holdout.
2. **Sanity check**: β* should be lower (more coupling) for Aerial Assist 2014 and
   Stronghold 2016 than for Charged Up 2023 and Recycle Rush 2015.
3. **Year-over-year stability**: adjacent seasons with similar game structures should
   have β* within ±0.10 of each other.

---

## Next Steps

1. Implement `objective_score()` in `tune_attribution_beta.py` (Statbotics API fetch required).
2. Run `run_all_seasons()` for 2013–2025.
3. Populate `empirical_beta` and `empirical_ci` in `blueprint/attribution_betas.py`.
4. Update this table with real values.
5. Feed empirical β* into Item 4 (rulebook prior regression).
