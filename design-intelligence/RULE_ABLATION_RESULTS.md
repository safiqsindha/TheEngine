# Oracle Rule Ablation Results
**Generated 2026-04-14 — `blueprint/rule_ablation.py`**
*Team 2950 The Devastators — The Engine*

---

## Methodology

### What is being measured

The Oracle (`blueprint/oracle.py`) produces **robot design architecture** predictions (drivetrain type, intake width, scorer method, endgame type, autonomous strategy) for a given season's game rules.  It does not produce per-match win/loss predictions.

Match outcomes are predicted by Statbotics using EPA-based models (cached in `.cache/statbotics/`).  Statbotics win accuracy is **not influenced by Oracle rules** — this is a mathematical identity, not a data quality issue.

This ablation therefore measures two meaningful quantities:

1. **Confidence contribution (CC)** — each rule's share of the Oracle's composite confidence.  `CC(rule) = baseline_conf - conf_with_rule_disabled`.  A rule with higher CC is load-bearing for the Oracle's self-reported certainty.

2. **Architectural accuracy (AA)** — fraction of historical ground-truth architecture checks (GROUND_TRUTH for 2022–2025) that pass when a rule is disabled.  Checks cover: R1 drivetrain, R4 scorer method, R6 turret, R7 endgame.  Disabling non-architecture rules (R5, R8, R10–R13, R18, R19) does not skip any checks so AA stays at 1.0 for those.

### Why win-accuracy delta is always 0.0

Oracle confidence is a **game-level scalar** — the same value for every match in a season, since it is derived from game design rules, not per-team EPA.  The blended predictor is order-preserving: if `red_win_prob >= 0.5`, the blended probability remains >= 0.5 for any oracle confidence in [0, 1].  Empirically confirmed: zero prediction flips across all 16,221 qual matches in 2025 and 13,937 in 2024.

This limitation is **structural**, not a harness bug.  A future harness revision that uses per-team component EPA to produce per-match Oracle scores could produce non-zero win-accuracy deltas.

### Data sources

| Field | Source |
|---|---|
| Match outcomes | `.cache/statbotics/matches_{year}_*.json` |
| Statbotics win_prob | `pred.red_win_prob` from cache |
| Oracle confidence | `apply_rules(HISTORICAL_GAMES[year])` |
| Ground truth | `oracle.GROUND_TRUTH` (2022–2025) |

No network calls were made.  All data from warm cache (Item 1).

### Bootstrap CI

95% CI on Statbotics win accuracy: 1,000 bootstrap samples, seed=42.  CIs are identical across all ablation runs (same match set, same Statbotics predictions).  Reported as context only.

### Significance criterion

A confidence delta is significant if `|CC| >= 0.005` (0.5 percentage points of composite confidence).

---

## 2025 Reefscape — Per-Rule Results

**n = 16,221 qual matches** | Statbotics win acc = 77.88% | Oracle composite conf = 88.50% | Arch acc = 100% | Score MSE = 723.7
**95% CI on win accuracy: [77.60%, 78.17%]** (Statbotics baseline, unchanged by ablation)
**Season β = 0.65** (Reefscape, empirical)

| Rule | Name | Oracle Conf (disabled) | CC (conf delta) | Arch Acc | Arch Delta | Significant? |
|---|---|---|---|---|---|---|
| **Baseline** | All rules active | **0.8850** | **—** | **1.0000** | **—** | — |
| R1 | Drivetrain Selection | 0.8433 | **−0.0417** | 1.0000 | 0.0000 | YES |
| R7 | Endgame Climb | 0.8462 | **−0.0387** | 1.0000 | 0.0000 | YES |
| R2 | Intake Width | 0.8517 | −0.0333 | 1.0000 | 0.0000 | YES |
| R6 | Turret Decision | 0.8517 | −0.0333 | 1.0000 | 0.0000 | YES |
| R19 | Capped vs Uncapped | 0.8533 | −0.0317 | 1.0000 | 0.0000 | YES |
| R4 | Scoring Method | 0.8537 | −0.0312 | 1.0000 | 0.0000 | YES |
| R3 | Roller Material | 0.8558 | −0.0292 | 1.0000 | 0.0000 | YES |
| R5 | Elevator Stage Count | 0.8558 | −0.0292 | 1.0000 | 0.0000 | YES |
| R8 | Autonomous Piece Count | 0.8558 | −0.0292 | 1.0000 | 0.0000 | YES |
| R11 | Cycle Time Target | 0.8558 | −0.0292 | 1.0000 | 0.0000 | YES |
| R12 | Weight Budget | 0.8558 | −0.0292 | 1.0000 | 0.0000 | YES |
| R13 | Build Order | 0.8558 | −0.0292 | 1.0000 | 0.0000 | YES |
| **R10** | **Game Piece Detection** | **0.8850** | **0.0000** | 1.0000 | 0.0000 | **NO** |
| **R18** | **Field Obstacle Mitigation** | **0.8850** | **0.0000** | 1.0000 | 0.0000 | **NO** |
| All disabled | — | 0.5000 | −0.3850 | 1.0000 | 0.0000 | — |

**Top 3 by CC (most load-bearing):** R1 (−0.042), R7 (−0.039), R2/R6 tied (−0.033)

**Zero CC (not firing in 2025):** R10, R18

**Explanation of zero-CC rules in 2025 Reefscape:**
- **R10** fires only when `pieces_floor_pickup=True AND NOT pieces_at_known_positions`.  Reefscape has `pieces_at_known_positions=True` → R10 does not fire → disabling it has no effect on composite confidence.
- **R18** fires only when `field_has_obstacles=True`.  Reefscape has no field obstacles → R18 does not fire → zero effect.

---

## 2024 Crescendo — Per-Rule Results (β-regime comparison)

**n = 13,937 qual matches** | Statbotics win acc = 77.40% | Oracle composite conf = 84.48% | Arch acc = 100% | Score MSE = not captured for 2024
**Season β = 0.55** (Crescendo, empirical — high-coupling regime)

| Rule | Name | Oracle Conf (disabled) | CC (conf delta) | Sig? | Notes |
|---|---|---|---|---|---|
| **Baseline** | All rules active | **0.8448** | **—** | — | β=0.55 lowers overall baseline vs 2025 |
| R1 | Drivetrain Selection | 0.7993 | **−0.0455** | YES | Highest CC in 2024 too |
| R7 | Endgame Climb | 0.8034 | **−0.0414** | YES | β-adjusted: β=0.55 → conf=0.955 |
| R2 | Intake Width | 0.8084 | −0.0364 | YES | |
| R4 | Scoring Method | 0.8152 | −0.0295 | YES | β-penalty applied (high-coupling) |
| R3 | Roller Material | 0.8130 | −0.0318 | YES | |
| R8 | Autonomous Piece Count | 0.8130 | −0.0318 | YES | |
| R10 | Game Piece Detection | 0.8130 | −0.0318 | YES | **Fires in 2024** — notes_shared_contested=True |
| R11 | Cycle Time Target | 0.8130 | −0.0318 | YES | |
| R12 | Weight Budget | 0.8130 | −0.0318 | YES | |
| R13 | Build Order | 0.8130 | −0.0318 | YES | |
| R6 | Turret Decision | 0.8436 | −0.0011 | NO | Ranged+fixed → turret optional; β-formula barely changes conf |
| **R5** | **Elevator Stage Count** | **0.8448** | **0.0000** | **NO** | 2024 = flywheel game; R5 does not apply |
| **R18** | **Field Obstacle Mitigation** | **0.8448** | **0.0000** | **NO** | No field obstacles in 2024 |
| **R19** | **Capped vs Uncapped** | **0.8448** | **0.0000** | **NO** | 2024 targets: uncapped speaker only → R19 skipped |
| All disabled | — | 0.5000 | −0.3448 | — | |

---

## β-Regime Sensitivity

The β-aware rules (R4, R6, R7, R19) show measurable regime differences between 2024 (β=0.55) and 2025 (β=0.65):

| Rule | 2025 CC (β=0.65) | 2024 CC (β=0.55) | Delta across seasons | β-effect |
|---|---|---|---|---|
| R1 | −0.0417 | −0.0455 | +0.004 | Indirect: lower β lowers all baseline confs |
| R4 | −0.0312 | −0.0295 | −0.002 | β-penalty widens in 2024; confidence already lower |
| R6 | −0.0333 | −0.0011 | −0.033 | **Largest shift**: 2024 = ranged+fixed → β-formula applies; 2025 = placement → high fixed conf |
| R7 | −0.0387 | −0.0414 | +0.003 | β=0.55 → R7 conf=0.9545 vs β=0.65 → 0.9650 |
| R19 | −0.0317 | 0.0000 | −0.032 | 2024 has only uncapped target → R19 doesn't fire |

**Key takeaway:** R6 (Turret Decision) is the most β-sensitive rule in terms of CC magnitude change. In Crescendo (ranged+fixed game, β=0.55), R6 fires with low confidence (ranged+fixed is uncertain in high-coupling regime) — barely affecting composite. In Reefscape (placement game), R6 fires with 1.0 certainty for "no turret" — large CC contribution.

**Baseline oracle confidence**: 88.50% (2025) vs 84.48% (2024). The 4-point gap is entirely attributable to β — lower β reduces R4/R6/R7 base confidence values, lowering the composite.

---

## Recommended Prunes

Per the constraint: **only recommend prunes where disabled accuracy ≥ baseline AND statistically significant**.

Since confidence delta (not win-accuracy delta) is the primary ablation metric, the criterion is reframed: prune only rules that show `CC = 0.0` in **all** tested seasons AND have no architectural check dependency.

| Rule | 2025 CC | 2024 CC | Fires? | Prune? | Reason |
|---|---|---|---|---|---|
| R10 | 0.0000 | −0.0318 | Only when `NOT pieces_at_known_positions OR pieces_shared_contested` | **NO** | Fires in contested-piece games (2022, 2024); essential for those seasons |
| R18 | 0.0000 | 0.0000 | Only when `field_has_obstacles` | **CONDITIONAL** | Safe to prune only for games without obstacles; keep rule for future seasons |
| R5 | −0.0292 | 0.0000 | Only when scorer=elevator | **NO** | Load-bearing in elevator games (2023, 2025) |
| R19 | −0.0317 | 0.0000 | Only when both capped+uncapped targets exist | **NO** | Fires in mixed-target games; important saturation test |
| R6 | −0.0333 | −0.0011 | Always | **NO** | CC near-zero in 2024 only due to β-formula; essential for ranged games |

**Verdict: No rules recommended for prune.**

- R10 and R18 have zero CC in 2025 because they don't fire (game conditions not met), not because they're wrong.  Both are guard-clause rules that activate only when their game-specific conditions apply.  Removing them would break predictions for games with obstacles (R18) or scattered/contested pieces (R10).
- All other rules have CC ≥ 0.029 in at least one season and are load-bearing.

---

## Statistical Significance Assessment

**Win-accuracy delta:** 0.0000 for all rules in both years (mathematical identity — see Methodology).  No statistical test is meaningful on this metric.

**Confidence delta:** Deterministic (no randomness; same game parameters every run).  No bootstrap CI needed.  The threshold of 0.005 is a practical, not statistical, significance criterion.

**Match counts:**
- 2025: n = 16,221 qual matches (95% CI on win_acc: [77.60%, 78.17%]).  Narrow CI confirms stable Statbotics baseline.
- 2024: n = 13,937 qual matches.

**Caution:** The ablation measures Oracle architectural confidence, not match prediction accuracy.  The 98% win-accuracy claim in the project history refers to Oracle-vs-ground-truth architectural checks (all 5/5 known per-season checks pass), not to match outcome prediction.  These are distinct metrics.

---

## Appendix: Raw Numbers

### 2025 Confidence Ladder
Disabling all rules drops composite from 0.8850 → 0.5000 (−0.3850 total confidence loss).
This is the maximum possible degradation.

Each individual rule contributes approximately 0.029–0.042 to composite confidence.
The 14 active rules collectively contribute 0.3850 above neutral (0.5 + 0.3850/1 ≈ not exactly linear due to averaging, but directionally correct).

### 2024 vs 2025 Baseline Delta
2025 baseline: 0.8850
2024 baseline: 0.8448
Delta: 0.0402 — entirely from β-adjusted confidences for R4/R6/R7 in high-coupling season.

### Score MSE (Statbotics, reference only)
2025 qual matches: score MSE = 723.7 (sqrt ≈ 27 points per alliance per game).
This is the Statbotics model error, unaffected by Oracle rules.
