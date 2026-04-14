# Tomorrow's Work — Power Curve Attribution

**Saved 2026-04-13 for execution 2026-04-14+. Three linked items.**

---

## Item 1: Historical β tuning across all FRC games 2013-2025 (~4h)

Run the power curve attribution against every FRC game season from 2013 onward and empirically tune β per game. Deliverable:

- `blueprint/attribution_betas.py` — per-year `attribution_beta` config with tuned values
- `design-intelligence/ATTRIBUTION_BETA_TUNING.md` — methodology + results table with confidence intervals per year
- Validation: for each (year, β), measure attribution accuracy against a holdout of that year's match data

**Method per year:**
1. Pull all qual match data from Statbotics / TBA for that season
2. For each match, compute attributed credit under β ∈ [0.4, 1.0] step 0.05
3. Find β that maximizes fit between attributed credit and (next-year EPA correlation OR alliance-level win accuracy)
4. Report β* + uncertainty

**Prior expectations (to be validated):**
| Year | Game | Expected β | Reason |
|---|---|---|---|
| 2013 | Ultimate Ascent | ~0.70 | Frisbee alliance coupling |
| 2014 | Aerial Assist | ~0.60 | Ball passing = extreme coupling |
| 2015 | Recycle Rush | ~0.85 | Co-op + solo totes |
| 2016 | Stronghold | ~0.60 | Shooter + feeder + crosser roles |
| 2017 | Steamworks | ~0.70 | Gears coupled, fuel independent |
| 2018 | Power Up | ~0.75 | Vault + switch coupled |
| 2019 | Deep Space | ~0.85 cycle / 0.60 climb | Per-phase β |
| 2020-21 | Infinite Recharge | ~0.75 | Power cells cycling |
| 2022 | Rapid React | ~0.70 | Ball coupling strong |
| 2023 | Charged Up | ~0.80 | Grid scoring independent |
| 2024 | Crescendo | ~0.70 | Speaker carries dominant |
| 2025 | Reefscape | **0.70 (kl26436 verified)** | Algae staging effects |

---

## Item 2: Implementation port (~3h total)

### 2a: Core port (~2h)
- Add `power_normalize(contributions, beta)` helper in `scout/alliance_decomposition.py`
- Wire into existing `compute_alliance_decomposition()` — apply power transform to contribution_share before delta allocation
- Preserve linear behavior as the default (β=1.0) for back-compat

### 2b: Game-config plumbing (~1h)
- `blueprint/attribution_betas.py` exposes `get_attribution_beta(year, phase="overall")` — returns tuned β or 1.0 fallback
- `alliance_decomposition` reads the year from the match record and applies the correct β
- Document how to override β for per-phase attribution (2019-style: separate cycle β and climb β)

### 2c: Tests (~30 min included in 2a)
- ~8 tests covering: β=1 equals linear, β=0.7 on known Reefscape example, per-year config lookup, phase-override, β=0 gives uniform

---

## Item 3: Oracle Rule #18 feedback signal (~2h)

Use cross-season β values as a historical-fit signal for Oracle's Rule #18 (alliance complementarity).

**Insight:** games with low β (high coupling) reward specialist alliances where roles complement; games with high β (near-linear) reward alliances of independent generalists. Rule #18 should weight complementarity differently depending on the β of the current game.

**Deliverable:**
- `blueprint/oracle.py` — Rule #18 reads `attribution_beta` for the current season
- If β < 0.7: complementarity matters a lot — rank alliances by role coverage
- If β ≥ 0.85: complementarity matters less — rank alliances by raw EPA sum
- Add ~6 tests validating rule behavior under different β regimes

**Secondary:** `compute_alliance_complementarity()` helper already shipped in Oracle Phase 1 should consume the same β and weight phases accordingly (low β = weight balance heavily, high β = weight totals heavily).

---

## Item 4: Rulebook β prior (~4h)

Predict β from game manual language before any matches are played, so the system has a usable β at kickoff + 48h instead of waiting until week 1.

**Why:** tuning β empirically requires match data (week 1 minimum). The rulebook leaks coupling through consistent GDC vocabulary — handoff verbs, alliance-scoped vs robot-scoped scoring, named feeder zones, co-op RP triggers. Extract those signals, regress against Item 1's empirical β*, and we have a pre-season β we can post as a Bayesian prior and update as week 1 matches come in.

**Signals to extract per manual:**
- Handoff verb density ("pass", "hand off", "deliver to", "feed", "transfer") normalized by manual word count
- Ratio of "ALLIANCE"-scoped vs "ROBOT"-scoped scoring clauses
- Count of named field zones implying roles (LOADING STATION, HUMAN PLAYER STATION, SOURCE, FEEDER)
- Per-robot possession limits present/absent
- Co-op / shared RP triggers present/absent
- H-rule count (defense legality proxy)

**Method:**
1. Extract signals from 2013-2025 manual PDFs via Haiku structured-extraction prompt
2. Fit 3-feature regularized regression against empirical β* from Item 1 (13 labeled seasons)
3. Validate with leave-one-season-out — target β prediction within ±0.1 of empirical
4. Implement Bayesian update: prior variance shrinks as week-1 match count grows; by week 3 prior does almost no work

**Deliverable:**
- `blueprint/rulebook_beta_prior.py` — `extract_signals(manual_pdf)`, `predict_beta(signals) → (β_prior, confidence)`, `beta_posterior(β_prior, matches) → β_updated`
- `design-intelligence/RULEBOOK_BETA_METHODOLOGY.md` — feature list, regression coefficients, leave-one-out validation table
- ~6 tests covering signal extraction, prediction on held-out year, posterior convergence

**Sanity checks (the regression should learn these):**
- Aerial Assist 2014 → handoff-heavy manual → β ~0.60 ✓
- Recycle Rush 2015 → co-op RP + independent totes → β ~0.85 ✓
- Charged Up 2023 → independent grid slots → β ~0.80 ✓

---

## Execution order when tomorrow begins

1. **Item 2a first** (core port) — everything else depends on it existing
2. **Item 1** (historical tuning) — fills in the β config that Item 2b reads + provides labels for Item 4
3. **Item 2b** (game-config plumbing) — wires Item 1's results in
4. **Item 4** (rulebook prior) — requires Item 1's β* as training labels
5. **Item 3** (Oracle rule feedback) — adds the cross-system signal
6. **Item 2c validation tests** — catches regressions

**Total budget:** ~13h. Stretches a Saturday — Item 4 can slip to Sunday if needed.

---

## Not in scope

- Per-match β tuning (overfit risk — β should be per-season)
- Real-time β learning (adds complexity without payoff)
- UI changes to pick_board to show per-β confidence (only worth it after Item 1 validates the β values are meaningful)
