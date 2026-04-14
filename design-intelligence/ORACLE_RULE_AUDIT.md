# Oracle 18-Rule Audit
**For Tier C work: C2 confidence scores, C3 ablation study, C4 β-awareness sweep**
*Generated 2026-04-14 — read-only audit of `blueprint/oracle.py`*

Word count target: 1500-2500 words

---

## How to Read This Document

`apply_rules()` (oracle.py:394) processes a `GameRules` dataclass through rules R1-R19 in sequence, accumulating results into a `pred` dict. Rules contribute to five subsystem keys (`drivetrain`, `intake`, `scorer`, `endgame`, `autonomous`) plus `weight_budget`, `build_order`, `rule_log`, and `confidence`. The overall confidence is the arithmetic mean of `.confidence` from all rules where `.applies is True` (oracle.py:688).

Rules R9, R14-R17 are not present in `apply_rules()`. The Oracle currently implements: R1, R2, R3, R4, R5, R6, R7, R8, R10, R11 (inline), R12, R13, R18, R19. That is 14 numbered rules plus Rule #18 (the `rank_alliances_r18` / complementarity system added in commit 2144106). This audit catalogs all 14 in-engine rules plus the complementarity helper as the "Rule #18 Alliance System", matching the product framing.

---

## Rule Catalog

### R1 — Drivetrain Selection
**Purpose:** Always recommend swerve drive; set speed and frame geometry based on field size and perimeter constraint.

**Input signals:**
- `game.field_is_small` (bool)
- `game.max_frame_perimeter_in` (float)

**Constants / magic numbers:**
- `speed = 16.0` fps (large field) — MAGIC NUMBER (oracle.py:421)
- `speed = 14.0` fps (small field) — MAGIC NUMBER (oracle.py:423)
- `frame_size = 27.0` default inches — MAGIC NUMBER (oracle.py:427)
- Perimeter threshold `< 112` inches — MAGIC NUMBER (oracle.py:428)
- Frame calculation `perimeter / 4 - 1` — derived formula, not policy constant

**Output:** `pred["drivetrain"]` — type, module (hardcoded `sds_mk4i`), speed_fps, gear_for, frame_length, frame_width.

**Confidence:** Hardcoded `1.0` (oracle.py:414). Uses `CONFIDENCE_POLICY["certain"]` semantically but the literal is written inline.

**Test coverage:** `test_r1_drivetrain_always_swerve`, `test_r1_large_field_gears_for_speed`, `test_r1_small_field_gears_for_acceleration`, `test_r1_default_frame_size_is_27`, `test_r1_small_perimeter_shrinks_frame`, `test_r1_perimeter_boundary_112_uses_default`. Also exercised by all 4 historical parametrized tests. Well covered.

**β-awareness:** No. R1 does not read `attribution_beta`. Module selection (`sds_mk4i`) is hardcoded — it does not vary by season coupling. Speed and frame targets could theoretically be β-influenced (e.g. high-coupling years may favor tighter, acceleration-optimized bots) but this is a stretch. **Verdict: β not needed here.**

**C2 confidence score candidate:** No — R1 is unconditional; confidence is rightly 1.0. EPA data does not help.

**C3 ablation candidate:** No — R1 is structural (drivetrain type feeds into all other outputs). Disabling it would corrupt the entire prediction graph.

---

### R2 — Intake Width
**Purpose:** Recommend full-width bumper-to-bumper intake whenever floor pickup exists.

**Input signals:**
- `game.pieces_floor_pickup` (bool)

**Constants / magic numbers:** None — "full" and `motors = 2` are categorical, not thresholds. Motor count `2` is a magic number (oracle.py:479).

**Output:** `pred["intake"]["width"]`, `pred["intake"]["motors"]`, `pred["intake"]["deploy"]`.

**Confidence:** `CONFIDENCE_POLICY["high"]` = 0.90 (oracle.py:443).

**Test coverage:** `test_r2_intake_full_width`, `test_r2_intake_deploys_when_floor_pickup`. Covered. No test for `pieces_floor_pickup=False` path (intake without deploy).

**β-awareness:** No. Floor-pickup universality is a structural rule independent of season coupling. **Verdict: β not needed.**

**C2 candidate:** Yes — `epa_win_confidence` could be used to weight R2 down if a game's EPA data shows little variance from floor intake (suggesting intake matters less). Low-priority.

**C3 ablation candidate:** Yes, with care. Disabling R2 changes intake width to a default but does not crash other rules. Safe to stub out.

---

### R3 — Roller Material
**Purpose:** Select intake roller material from game piece geometry.

**Input signals:**
- `game.game_piece_shape` (string, keyword-matched)
- `game.game_piece_diameter_in` (float, for over/under bumper decision)

**Constants / magic numbers:**
- Diameter threshold `< 3.0` inches → under-bumper intake (oracle.py:470) — MAGIC NUMBER

**Output:** `pred["intake"]["roller_material"]`, `pred["intake"]["type"]` (over/under bumper).

**Confidence:** `CONFIDENCE_POLICY["medium"]` = 0.85 (oracle.py:465).

**Test coverage:** `test_r3_spherical_uses_compliant_wheels`, `test_r3_flat_disc_uses_mecanum_funnel`, `test_r3_cylindrical_uses_flex_wheels`, `test_r3_irregular_uses_flex_wheels`, `test_r3_unknown_shape_defaults_to_flex`, `test_r3_under_bumper_when_piece_small`, `test_r3_over_bumper_when_piece_large`. Full branch coverage.

**β-awareness:** No. Material selection is a physics / geometry rule. Season coupling does not change what roller works on a sphere. **Verdict: β not needed.**

**C2 candidate:** No — this is deterministic geometry, not a probabilistic judgment.

**C3 ablation candidate:** Yes. R3 only affects `roller_material` and `intake.type`; disabling it does not cascade. Safe to ablate.

---

### R4 — Scoring Method
**Purpose:** Identify the primary scoring target and assign a mechanism type (flywheel, elevator, gravity drop).

**Input signals:**
- `game.scoring_targets` list (selects max by `teleop_pts` via `_get_primary_target`)
- `primary_target["type"]` — `"ranged"`, `"placement"`, or `"ground"`

**Constants / magic numbers:** None at the threshold level; all branches are categorical. Default fallback `target_type = "placement"`, `target_height = 48` when no targets exist (oracle.py:492-493) — magic number 48.

**Output:** `pred["scorer"]["method"]` — the most influential single output key in the system.

**Confidence:** `CONFIDENCE_POLICY["high"]` = 0.90 for ranged and placement; `CONFIDENCE_POLICY["medium"]` for ground; `CONFIDENCE_POLICY["low"]` = 0.75 for unknown (oracle.py:497-511).

**Test coverage:** `test_r4_ranged_target_uses_flywheel`, `test_r4_placement_target_uses_elevator`, `test_r4_ground_target_uses_gravity_drop`, `test_r4_no_targets_defaults_to_elevator`. All branches tested. Historical parametrized tests also verify scorer_method against ground truth for 2022-2025.

**β-awareness:** No. Scoring mechanism choice is driven by target geometry, not inter-team independence. **Verdict: β not needed directly, but a future β-weighted confidence could be useful — in high-coupling seasons, the "wrong" scorer choice is more costly.**

**C2 candidate:** Yes — strong candidate. `epa_win_confidence` on scorer EPAs (auto + teleop component) could replace the hardcoded 0.90/0.85/0.75 with a data-derived probability.

**C3 ablation candidate:** No — R4 is load-bearing. R5, R6, and build-order all branch on `scorer_method`. Disabling R4 requires stubbing those downstream rules too.

---

### R5 — Elevator Stage Count
**Purpose:** Size the elevator by target height in inches.

**Input signals:**
- `scorer_method` (from R4)
- `target_height` (from primary scoring target)

**Constants / magic numbers:**
- `<= 24"` → 0 stages (oracle.py:517) — MAGIC NUMBER
- `<= 40"` → 1 stage (oracle.py:519) — MAGIC NUMBER
- `<= 55"` → 2 stages (oracle.py:521) — MAGIC NUMBER
- `> 55"` → 2 stages (3-stage capped, oracle.py:523) — MAGIC NUMBER and policy comment

**Output:** `pred["scorer"]["stages"]`.

**Confidence:** `CONFIDENCE_POLICY["medium"]` = 0.85 (oracle.py:533).

**Test coverage:** `test_r5_low_target_no_elevator`, `test_r5_mid_target_single_stage`, `test_r5_high_target_two_stage`, `test_r5_extreme_height_caps_at_two_stage`. Full branch coverage.

**β-awareness:** No. Stage count is mechanical geometry. **Verdict: β not needed.**

**C2 candidate:** No — deterministic height bins. EPA uncertainty does not inform this.

**C3 ablation candidate:** Yes. R5 writes only `scorer.stages`; disabling it defaults stages to 0 and doesn't affect other rules. Safe.

---

### R6 — Turret Decision
**Purpose:** Four-quadrant matrix: ranged×distributed → build turret; all other combos → skip.

**Input signals:**
- `target_type` (from R4)
- `target_distributed` (from primary scoring target)

**Constants / magic numbers:**
- `0.65` hardcoded confidence for ranged+fixed (oracle.py:545) — MAGIC NUMBER; intentionally below-policy, noted in comment as "ambiguous decision"

**Output:** `pred["scorer"]["turret"]` — `"continuous"` or `"none"`.

**Confidence:** `CONFIDENCE_POLICY["high"]` for ranged+distributed; hardcoded `0.65` for ranged+fixed; `CONFIDENCE_POLICY["high"]` for placement+distributed; `CONFIDENCE_POLICY["certain"]` for placement+fixed.

**Test coverage:** `test_r6_ranged_distributed_builds_continuous_turret`, `test_r6_ranged_fixed_skips_turret`, `test_r6_placement_distributed_skips_turret`, `test_r6_placement_fixed_skips_turret`. All four quadrants tested. Historical turret check in `validate_all` adds regression coverage.

**β-awareness:** No, but this is the best candidate for β-weighting among structural rules. In high-coupling seasons (β < 0.70), coordinated turret-plus-target systems yield higher scoring variance than in independent seasons. The 0.65 magic number for ranged+fixed is the one constant most likely to be improved by β-parameterization. **Verdict: strong C4 candidate.**

**C2 candidate:** Yes — the 0.65 ambiguous branch is an ideal target. Historical turret data by β regime could replace the magic number with an EPA-derived confidence.

**C3 ablation candidate:** Yes. Turret choice feeds only into `scorer.turret` and reasoning text. The downstream BOM cost changes, but `predict_game` output structure is unaffected. Safe to ablate.

---

### R7 — Endgame Climb
**Purpose:** Determine whether and how to climb based on endgame point fraction.

**Input signals:**
- `game.endgame_pct_of_winning_score` (float)
- `game.endgame_type` (string — `"climb"`, `"balance"`, `"park"`, `"none"`)
- `game.endgame_height_in` (float)

**Constants / magic numbers:**
- `>= 0.15` → climb_must (oracle.py:579) — MAGIC NUMBER
- `>= 0.05` → climb_should (oracle.py:580) — MAGIC NUMBER
- `> 40"` → telescope mechanism (oracle.py:593) — MAGIC NUMBER
- `> 30"` → 2 endgame motors; else 1 motor (oracle.py:597) — MAGIC NUMBER

**Output:** `pred["endgame"]` — type, height_in, motors.

**Confidence:** `CONFIDENCE_POLICY["certain"]` = 1.00 (oracle.py:583). Highest confidence rule.

**Test coverage:** `test_r7_high_value_climb_required`, `test_r7_telescope_for_tall_climbs`, `test_r7_hook_winch_for_short_climbs`, `test_r7_balance_endgame`, `test_r7_park_only_endgame`, `test_r7_15_percent_threshold_must_climb`. All branches covered. Historical endgame check adds regression.

**β-awareness:** No. Point fraction thresholds are game-rule constants, not coupling-dependent. **Verdict: β not needed.**

**C2 candidate:** Yes — endgame is the highest-confidence rule but the 0.15/0.05 thresholds are mechanical. If endgame component EPA from Statbotics shows that climb success rate varies below 0.15, the `certain` confidence is inflated.

**C3 ablation candidate:** No — endgame weight feeds `weight_budget.endgame_lb` and the build order. Disabling R7 would produce an underweight, incorrectly ordered prediction.

---

### R8 — Autonomous Piece Count
**Purpose:** Estimate how many game pieces an elite robot can score in auto.

**Input signals:**
- `game.auto_duration_s` (int)
- `game.pieces_at_known_positions` (bool)
- `game.field_is_small` (bool)

**Constants / magic numbers:**
- Baseline `auto_pieces = 3` (oracle.py:613) — MAGIC NUMBER
- `+1` piece for small field, capped at 5 (oracle.py:617) — MAGIC NUMBER

**Output:** `pred["autonomous"]["estimated_pieces"]`, `pred["autonomous"]["priority_actions"]`.

**Confidence:** `CONFIDENCE_POLICY["medium"]` = 0.85 (oracle.py:619).

**Test coverage:** `test_r8_baseline_three_piece_auto`, `test_r8_small_field_bumps_auto_pieces`, `test_r8_cycle_time_normal_field`, `test_r8_cycle_time_small_field`. Covered. No test for `pieces_at_known_positions=False` path (which currently does not change the piece count — a potential logic gap).

**β-awareness:** No. Piece counts are field geometry. **Verdict: β not needed for piece count; however, auto EPA from Statbotics would be more actionable than fixed baselines.**

**C2 candidate:** Yes — auto component EPA from Statbotics directly informs what elite auto routines achieve. This is the most concrete C2 upgrade target in the autonomous block.

**C3 ablation candidate:** Yes. R8 only writes `autonomous.estimated_pieces`; the rest of the pipeline uses `endgame`, `scorer`, `drivetrain`. Safe to ablate.

---

### R10 — Game Piece Detection
**Purpose:** Choose vision detection strategy based on piece predictability and contrast.

**Input signals:**
- `game.pieces_floor_pickup` (bool)
- `game.pieces_at_known_positions` (bool)
- `game.piece_high_contrast` (bool)
- `game.pieces_shared_contested` (bool)

**Constants / magic numbers:** None — all categorical branches.

**Output:** Appended to `pred["rule_log"]` (not a top-level subsystem key). Detection method: `"none"`, `"hsv_color"`, or `"yolo_neural"`.

**Confidence:** `CONFIDENCE_POLICY["medium"]` = 0.85 (oracle.py:636).

**Test coverage:** `test_r10_no_detection_when_known_positions`, `test_r10_hsv_for_high_contrast_scattered`, `test_r10_yolo_for_low_contrast_scattered`, `test_r10_yolo_for_contested_pieces`. All branches covered.

**β-awareness:** No. Vision strategy is independent of scoring coupling. **Verdict: β not needed.**

**C2 candidate:** No — categorical rule with no probabilistic gradient.

**C3 ablation candidate:** Yes — R10 only appends to rule_log and does not set any top-level subsystem output. Safest rule to ablate; zero downstream effect.

---

### R11 — Cycle Time Target (Inline)
**Purpose:** Set the teleop cycle time target used in auto planning.

**Input signals:**
- `game.field_is_small` (bool)

**Constants / magic numbers:**
- `5.0` seconds (large field) — MAGIC NUMBER (oracle.py:642)
- `4.0` seconds (small field) — MAGIC NUMBER (oracle.py:644)

**Output:** `pred["autonomous"]["cycle_time_s"]` (oracle.py:648).

**Confidence:** Not independently tracked — R11 is inline within the R8 block and shares R8's confidence in the log. **Coverage gap: R11 has no independent RuleResult entry.**

**Test coverage:** `test_r8_cycle_time_normal_field`, `test_r8_cycle_time_small_field` test the output, but attribute it to R8 not R11.

**β-awareness:** No. Cycle time is field geometry. **Verdict: β not needed.**

**C2 candidate:** Yes — teleop EPA variance from Statbotics can predict realistic cycle times better than a hardcoded 4/5 second constant. High-value candidate for C2.

**C3 ablation candidate:** Yes — cycle_time_s is informational only (used in reasoning string, not in any downstream branch). Safe.

---

### R12 — Weight Budget
**Purpose:** Produce a static weight allocation across subsystems.

**Input signals:**
- `scorer_method` (from R4)
- `climb_required` (from R7)

**Constants / magic numbers:**
- `drivetrain_lb = 42` — MAGIC NUMBER (oracle.py:671)
- `intake_lb = 10` — MAGIC NUMBER
- `scorer_lb = 22` (elevator) or `15` (flywheel) — MAGIC NUMBERS
- `endgame_lb = 8` (climb) or `2` — MAGIC NUMBERS
- `electronics_lb = 15` — MAGIC NUMBER
- `bumpers_lb = 10` — MAGIC NUMBER
- `margin_lb = 18` — MAGIC NUMBER
- `total_limit_lb = 125` — MAGIC NUMBER (FRC rule, should be policy constant)

**Output:** `pred["weight_budget"]` — component breakdowns.

**Confidence:** Not tracked — R12 has no RuleResult entry. **Coverage gap: no rule_log entry for R12.**

**Test coverage:** `test_weight_budget_sums_under_limit` verifies the arithmetic constraint. No test for the scorer-dependent or endgame-dependent branches.

**β-awareness:** No. Weight is an FRC rule constraint. **Verdict: β not needed.**

**C2 candidate:** No — weight is a hard physical constraint, not a probabilistic judgment.

**C3 ablation candidate:** Yes — weight_budget is an informational output block. Disabling R12 leaves the key empty but nothing else branches on it. Safe.

---

### R13 — Build Order
**Purpose:** Sequence subsystem builds; elevator-heavy games prioritize scorer over intake.

**Input signals:**
- `scorer_method` (from R4)
- `target_height` (from primary target)

**Constants / magic numbers:**
- `target_height > 40` triggers scorer-first order (oracle.py:683) — MAGIC NUMBER (shared with R5 boundary)

**Output:** `pred["build_order"]` — list of subsystem names in build sequence.

**Confidence:** Not tracked — R13 has no RuleResult entry. **Coverage gap: no rule_log entry for R13.**

**Test coverage:** `test_build_order_non_empty`, `test_build_order_elevator_first_for_tall_targets`. Covered.

**β-awareness:** No. **Verdict: β not needed.**

**C2 candidate:** No — order is categorical.

**C3 ablation candidate:** Yes — build order is advisory output, not consumed by any downstream rule. Safe.

---

### R18 (Obstacle Check, in-engine) — Field Obstacle Mitigation
**Purpose:** Flag bellypan raise requirement when field obstacles exceed ground clearance.

**Input signals:**
- `game.field_has_obstacles` (bool)
- `game.field_obstacle_height_in` (float)

**Constants / magic numbers:**
- Bellypan target `"2-3\""` embedded in reasoning string — not a queryable constant

**Output:** Appended to `pred["rule_log"]` only when `field_has_obstacles=True`. No top-level subsystem key updated.

**Confidence:** `CONFIDENCE_POLICY["medium"]` = 0.85 (oracle.py:657).

**Test coverage:** `test_r18_obstacle_check_fires`, `test_r18_no_obstacle_no_rule`. Two tests, minimal. The height-dependent reasoning string is not tested.

**β-awareness:** No. Obstacle geometry is independent of scoring coupling. **Verdict: β not needed.**

**C2 candidate:** No — binary trigger.

**C3 ablation candidate:** Yes — this R18 variant only appends to rule_log. No downstream effect. Safe.

---

### R18 (Alliance System) — Alliance Complementarity Ranking
**Purpose:** Rank candidate alliances by role coverage vs. raw EPA total, weighted by attribution β.

**Input signals:**
- `alliances` — list of per-team component-EPA dicts (`auto`, `teleop`, `endgame`)
- `year` — optional; triggers β lookup from `attribution_betas.get_attribution_beta(year)`
- `attribution_beta` — float in [0, 1]; read from `attribution_betas` module (commit 2144106)

**Constants / magic numbers:**
- `_BETA_HIGH_COUPLING = 0.70` — regime boundary (oracle.py:231)
- `_BETA_INDEPENDENT = 0.85` — regime boundary (oracle.py:232)
- `raw_total_score` normalization cap `150.0` pts (oracle.py:228) — MAGIC NUMBER
- Fallback β = `1.0` when `attribution_betas` import fails (oracle.py:68) — policy default

**Output:** `rank_alliances_r18()` returns sorted `(index, score)` list. Not part of `apply_rules()` pipeline; called separately by alliance advisor.

**Confidence:** Not tracked via RuleResult — operates outside the `apply_rules` confidence averaging.

**Test coverage:** `test_r18_year_2024_beta_055_favors_complementarity`, `test_r18_year_2023_beta_065_moderate_weight`, `test_r18_year_2014_beta_095_favors_raw_totals`. Three β-regime tests. Also: `test_complementarity_*` suite (8 tests). Well covered for the logic. No test for `year=None` legacy path in `rank_alliances_r18` directly (covered indirectly via complementarity tests).

**β-awareness:** YES — the only rule that currently reads `attribution_beta`. Serves as the template for C4 upgrades to other rules.

**C2 candidate:** Yes — the complementarity score itself is a confidence proxy. An alliance with score < 0.3 indicates structural weakness; this threshold could be surfaced as a C2 warning.

**C3 ablation candidate:** Yes — `rank_alliances_r18` is a standalone helper not wired into `apply_rules`. Can be disabled with zero effect on the main prediction pipeline.

---

### R19 — Capped vs. Uncapped Scoring Analysis
**Purpose:** Determine whether capped scoring methods will saturate, identifying the uncapped method as the scoring differentiator.

**Input signals:**
- `game.scoring_targets` — split by `cap_type` (`"capped"` vs `"uncapped"`)
- `game.teleop_duration_s` (read but not used in saturation formula — dead variable)

**Constants / magic numbers:**
- `3 * 10 * capped_pts_per_cycle` — alliance cycle estimate: 3 robots × 10 cycles (oracle.py:723) — MAGIC NUMBERS
- `0.8` saturation threshold: `estimated_alliance_capped > capped_max * 0.8` (oracle.py:725) — MAGIC NUMBER
- `0.88` hardcoded confidence in both branches (oracle.py:728, 734) — MAGIC NUMBER; not referenced from CONFIDENCE_POLICY

**Output:** Conditional `RuleResult("R19", ...)` appended to results. If `uncapped_priority`, also appends to `pred["scorer"]["reasoning"]`.

**Confidence:** `0.88` hardcoded — not from `CONFIDENCE_POLICY`. **Flag: inconsistent with policy dict.**

**Test coverage:** `test_r19_only_uncapped_no_rule`, `test_r19_mixed_targets_fires`, `test_r19_saturating_capped_recommends_uncapped`, `test_r19_non_saturating_capped_remains_priority`. All branches covered.

**β-awareness:** No, but this is a prime C4 target. In high-coupling seasons (β < 0.70), coordinated alliances more reliably saturate capped targets, making the 0.80 saturation threshold systematically too conservative. **Verdict: strong C4 candidate.**

**C2 candidate:** Yes — the `0.88` magic confidence and `0.8` saturation threshold are both candidates for EPA-derived calibration.

**C3 ablation candidate:** Yes. R19 only fires conditionally (requires both capped and uncapped targets). When disabled, scorer method from R4 remains authoritative. Safe to ablate.

---

## Summary Sections

### Rules That Use Hardcoded Magic Numbers
*Targets for CONFIDENCE_POLICY consolidation:*

| Rule | Magic Numbers |
|------|--------------|
| R1 | `16.0`, `14.0` fps; `27.0"` frame; `112"` perimeter; `sds_mk4i` hardcoded |
| R2 | `2` motors |
| R3 | `3.0"` diameter threshold |
| R4 | `48"` default height fallback |
| R5 | `24"`, `40"`, `55"` height bins |
| R6 | `0.65` confidence (intentional but undocumented in policy dict) |
| R7 | `0.15`, `0.05` pct thresholds; `40"`, `30"` height breakpoints |
| R8 | `3` baseline pieces; `5` cap; `+1` small field bump |
| R11 | `5.0`, `4.0` seconds cycle time |
| R12 | All 7 weight values + `125 lb` FRC limit |
| R13 | `40"` height threshold |
| R18 (Alliance) | `0.70`, `0.85` β thresholds; `150.0` normalization cap |
| R19 | `3`, `10` cycle estimate; `0.8` saturation threshold; `0.88` confidence (not in policy dict) |

**Highest priority for consolidation:** R19's `0.88` confidence (breaks CONFIDENCE_POLICY consistency) and R12's weight constants (should be a separate WEIGHT_POLICY dict or CONSTANTS block).

---

### Rules NOT Covered by Tests
*Coverage gaps:*

- **R11 (Cycle Time)** — no independent RuleResult in rule_log; not directly assertable by rule ID. Tests exist for the output value but are attributed to R8.
- **R12 (Weight Budget)** — no RuleResult in rule_log; `test_weight_budget_sums_under_limit` only checks arithmetic, not the scorer-method and endgame branch variations (e.g. `scorer_lb = 15` for flywheel is not independently tested).
- **R13 (Build Order)** — no RuleResult in rule_log; the non-elevator-first path (default order) is not explicitly asserted against a specific target height < 40.
- **R2 (Intake)** — `pieces_floor_pickup=False` path not tested (no test asserts `deploy=False`).
- **R8 (Autonomous)** — `pieces_at_known_positions=False` does not change piece count in the code but is not tested to confirm this is intentional.

---

### Rules That Should Read β But Don't Yet
*Tier C4 work list (priority order):*

1. **R19 — Capped vs. Uncapped Analysis.** The 0.80 saturation threshold and 10-cycle assumption are both β-sensitive. High-coupling years (β < 0.70) see tighter alliance coordination → higher saturation rates. This constant should scale with β.

2. **R6 — Turret Decision.** The `0.65` ambiguous confidence for ranged+fixed targets is the most obviously β-sensitive confidence value. In high-coupling years, a turret provides differentiated value even for fixed targets; in independent years it matters less.

3. **R4 — Scoring Method Confidence.** The 0.90/0.85/0.75 CONFIDENCE_POLICY values used here are universal. In high-coupling seasons, choosing the wrong scorer type is more consequential; β could modulate confidence down to force wider uncertainty bands.

4. **R7 — Endgame Climb.** The 0.15 must-climb threshold is currently certain (1.0 confidence). In seasons where endgame contributes less to scoring variance (β-observable through endgame EPA component), this should have lower confidence.

---

### Rules Safe to Disable for Ablation
*Tier C3 input list:*

Safe = disabling produces no crash and does not corrupt other rule outputs.

| Rule | Safety Notes |
|------|-------------|
| R3 — Roller Material | Only writes `intake.roller_material` and `intake.type`. No downstream branches read these. |
| R5 — Elevator Stages | Only writes `scorer.stages`. R6, R13 do not branch on stage count. |
| R6 — Turret | Only writes `scorer.turret`. No downstream rule reads turret. |
| R8 — Auto Pieces | Only writes `autonomous.estimated_pieces` and `priority_actions`. |
| R10 — Detection | Only appends to `rule_log`. Zero downstream effect. |
| R11 — Cycle Time | Only writes `autonomous.cycle_time_s`. No downstream branch. |
| R12 — Weight Budget | Only writes `weight_budget`. No downstream branch. |
| R13 — Build Order | Only writes `build_order`. No downstream branch. |
| R18 (Obstacle) | Only appends to `rule_log` conditionally. Zero downstream effect. |
| R18 (Alliance System) | Standalone function, not called by `apply_rules`. Zero effect on main pipeline. |
| R19 — Capped Analysis | Only fires conditionally; adds reasoning text to `scorer`. R4 result stands when R19 is off. |
| R2 — Intake Width | Affects `intake.width`, `intake.motors`, `intake.deploy`. No other rule reads these fields. |

**Not safe to ablate (load-bearing):**
- R1 — all other rules assume swerve + frame geometry
- R4 — R5, R6, R13 branch on `scorer_method`
- R7 — R12 branches on `climb_required`

---

### Top 3 Rules Most Influential on Final Prediction

**1. R4 — Scoring Method** is the single highest-leverage rule. Its output (`scorer_method`) directly determines R5 (elevator stages), R6 (turret), R13 (build order), R12 (scorer weight), and through those, the complete mechanism specification. A wrong R4 call propagates to 4 downstream rules and invalidates the BOM. Historical accuracy on scorer_method across 2022-2025 is 4/4 — this rule is correct precisely because it is the most carefully designed.

**2. R7 — Endgame Climb** carries `CONFIDENCE_POLICY["certain"]` (1.00) and gates the entire endgame weight allocation in R12 and the build order. Endgame points have been 15-25% of winning scores for every game in the historical corpus. The 0.15 threshold captures all four historical games correctly. Weight in the confidence average: highest per-rule contribution because it is always applied and always 1.0.

**3. R1 — Drivetrain (Swerve)** is structurally foundational. Although it is trivially always correct (post-2022 Einstein consensus is unanimous), it sets the frame geometry that constrains intake and scorer sizing. Its `1.0` confidence raises the overall `pred["confidence"]` average the most of any single rule. An incorrect R1 call would invalidate physical feasibility for all mechanism dimensions.

**Honorable mention — R19** has the highest potential influence when it fires (overrides scorer reasoning) but only triggers when both capped and uncapped targets coexist. Its `0.88` magic confidence is the one inconsistency most likely to skew the aggregate confidence score incorrectly.

---

*Audit complete. File: `TheEngine/blueprint/oracle.py`. Test file: `TheEngine/tests/blueprint/test_oracle.py`. Commit reference for Rule #18 β upgrade: 2144106.*
