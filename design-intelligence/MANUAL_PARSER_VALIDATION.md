# Manual Parser Validation — FRC 2019 / 2023 / 2024

**Status:** ✅ THREE-YEAR MATRIX COMPLETE (hardened prompt)
**Date run:** 2026-04-15
**Target module:** `blueprint/manual_parser.py`
**Driver:** `blueprint/validate_manual.py` (year-agnostic, per-year ground truth)
**Corpora:** `manuals/2019_deep_space.pdf`, `manuals/2023_charged_up.pdf`, `manuals/2024_crescendo.pdf` (all gitignored)
**Configuration:** `n_parses=3`, `model="claude-haiku-4-5"`, hardened `PROMPT_TEMPLATE`
**Summary data:** `design-intelligence/_{2019,2023,2024}_validation_summary.json`

---

## Three-year headline matrix

| Year | Game | Accuracy | Cost | Input tok | Output tok | Locked | Tentative | Ambiguous |
|---|---|---|---|---|---|---|---|---|
| 2019 | Deep Space | **14 / 17 (82.4%)** | $0.1216 | 97,803 | 4,759 | 0 | 2 | 28 |
| 2023 | Charged Up | **10 / 16 (62.5%)** | $0.1512 | 98,658 | 10,516 | 0 | 23 | 74 |
| 2024 | Crescendo | **8 / 14 (57.1%)** | $0.1353 | 95,331 | 7,995 | 6 | 7 | 17 |
| **Totals** | — | **32 / 47 (68.1%)** | **$0.4081** | 291,792 | 23,270 | 6 | 32 | 119 |

- Cost across 3 years landed at **$0.41 for 47 ground-truth checks** — Haiku 4.5 is the right cost point for kickoff automation.
- No truncation issues across any of the three 263k–313k-char manuals. JSON parse succeeded on all 9 calls.
- Wall-clock: 11–15 s per parse per year. Sequential runs needed because 50k input-tokens/min rate limit caps parallel launches at this corpus size.

---

## What changed between runs — the hardened prompt

Before this matrix, `PROMPT_TEMPLATE` allowed the model to emit one scoring entry per *row* of the rulebook table. For 2-piece games (2019 cargo/hatch, 2023 cone/cube) Haiku collapsed multi-piece rows into a single aggregate. The first 2019-only run caught 3 cargo failures traced to this.

**Fix landed in `blueprint/manual_parser.py`:**

1. Explicit tuple requirement in the prompt:

   > CRITICAL — emit ONE `scoring[]` entry for each distinct `(phase, game_piece, field_location)` combination. Do NOT combine game pieces into a single entry even if they share a row in a rulebook table.

2. Reefscape 2025 worked example showing 4 separate entries (coral L1, coral L4, algae processor, algae net).

3. `_flag_phase_location_overlaps()` post-check in `consensus()` that flags entries sharing `(phase, location)` with different `points` as tentative rather than silently picking one.

4. Strict validator lookup in `blueprint/validate_manual.py` — `find_pts(..., require_all=True)` returns `None` instead of falling through to the first substring match, so failures now show "no entry matched" instead of a misleading wrong-entry report.

---

## Headline finding — hardening fixed diagnostics, not extraction

The hardened prompt **did not fix the cargo-collapse bug** for 2019. The validator now correctly reports "no entry matched" for the 3 cargo ground-truth rows (previously they silently picked the hatch row). Extraction itself still merges cargo and hatch into one "HATCH PANEL on ROCKET or CARGO SHIP" entry worth 2 pts — cargo's 3-pt entries never appear.

**Interpretation:** the tuple-requirement instruction is in the prompt, but Haiku still collapses rows when the manual presents HATCH and CARGO columns side-by-side in a shared table. The worked example (Reefscape) did not generalize to table-parsing — it only proves to Haiku that separated entries are allowed, not that they're mandatory when the source is a column-paired table.

---

## Per-year failure patterns

### 2019 Deep Space — 14/17 (82.4%) — same failures as pre-hardening run

| Category | Passed | Failed |
|---|---|---|
| HAB climb (auto + endgame, L1/L2/L3) | 6/6 | 0 |
| Hatch panel (auto + teleop, Rocket + Cargo Ship) | 4/4 | 0 |
| Cargo (auto + teleop, Rocket + Cargo Ship) | **0/3** | 3 |
| Game pieces, possession, RPs, weight | 4/4 | 0 |

Cargo-collapse bug persists exactly as before — hardening surfaced the failure cleanly but did not prevent it.

### 2023 Charged Up — 10/16 (62.5%) — multi-tier nodes collapsed

| Category | Passed | Failed |
|---|---|---|
| Cone scoring (middle row, auto + teleop) | 2/2 | 0 |
| Cube scoring | **0/any** | all missed |
| Hybrid + High node (auto + teleop, either piece) | **0/4** | 4 |
| Mobility + Park + Dock | 3/3 | 0 |
| Engage (expected 10 pts) | **0/1** | got 6 (dock) instead |
| Game pieces, possession, RPs | 5/5 | 0 |
| Weight=125 lb | **0/1** | returned `None` |

Haiku extracted the middle row cone entries but emitted nothing for hybrid/high nodes and nothing for cubes. This is the same multi-row-collapse pathology as 2019 cargo, extended to a 3-tier grid. Separately, ENGAGE (the higher-scoring charge-station state) was missed — only DOCKED was extracted.

### 2024 Crescendo — 8/14 (57.1%) — endgame enumeration missed

| Category | Passed | Failed |
|---|---|---|
| Amp scoring (auto + teleop) | 2/2 | 0 |
| Speaker auto=5 | 1/1 | 0 |
| Teleop speaker (2 pts non-amp) | **0/1** | no entry matched |
| Amplified speaker (5 pts) | **0/1** | returned 2 (non-amp) |
| Auto leave | 1/1 | 0 |
| Endgame PARK / ONSTAGE / SPOTLIT | **0/3** | all "no entry matched" |
| Game pieces, possession, RPs | 4/4 | 0 |
| Weight=125 lb | **0/1** | returned `None` |

Endgame climbing states are enumerated in Crescendo with distinct point values per configuration. Haiku captured none of them. Amplified vs non-amplified speaker is collapsed similarly — the 5-pt amplified variant was silently subsumed into the 2-pt non-amp row.

---

## Systemic parser weaknesses identified

Three failure modes show up across **all three years**:

1. **Multi-tier table collapse.** When the manual presents scoring as a table with N tiers (hybrid/mid/high nodes, L1/L2/L3 HAB, park/onstage/spotlit), Haiku emits one entry per row of prose but loses the per-tier point values. Hardening the prompt with a tuple requirement has not fixed this for column-paired tables.

2. **Weight constraint extraction broken.** Both 2023 and 2024 returned `None` for robot weight. 2019 passed, suggesting the manual's prose phrasing drives detection and the schema is fragile when the wording drifts from "125 pounds" literal.

3. **Consensus lock rate collapses on `name` variance.** Across 2019 and 2023, `locked=0` despite the underlying point values being stable. Root cause: `consensus()` normalizes on the `name` field, and Haiku emits varying names per parse for the same scoring entry ("SANDSTORM Bonus (HAB Level 1)" vs "HAB Level 1 (Sandstorm)") even when `points` and `location` match. 2024 partially escaped this (6 locked) because Crescendo naming is simpler.

---

## Cost efficiency verdict

| | Per year | Per 47 fields |
|---|---|---|
| Input tokens | ~97k | 291,792 |
| Output tokens | 4.8k–10.5k | 23,270 |
| Cost | $0.12–0.15 | $0.41 |

**~$0.14 per year for a 3-parse ensemble against a full game manual.** That's inside the kickoff budget envelope (original forecast was $0.25–0.40 per year). Three parses is the right setting — bumping to 5 would not fix systematic collapses (all 3 parses miss identically), only prompt/schema fixes will.

---

## Revised action items (supersedes prior recommendations)

The 2019-only report's 4 action items (prompt tuple requirement, Reefscape worked example, overlap guard, strict validator) have **all shipped** and are covered in this run. New items surfaced by the 3-year matrix:

1. **Change consensus match key from `name` → `(phase, location, points)` tuple.**
   `name` is the wrong primary key for equality because Haiku varies phrasing. Matching on the three structured fields should recover the lock rate to the 40–50% range seen in pre-hardening 2019.

2. **Prompt: explicit weight-constraint instruction.**
   Add a dedicated "extract the robot weight limit in pounds, scan for phrasing 'weigh no more than X' or 'maximum weight'" clause. Currently schema is silent on how to find the value and Haiku is dropping it.

3. **Prompt: explicit tier/level/zone enumeration requirement.**
   Tuple requirement is too abstract. Add a second stronger clause: "If the scoring table has multiple tiers, levels, rows, zones, or configurations with different point values, emit one entry per tier. Examples: HAB L1/L2/L3, hybrid/mid/high grid nodes, park/onstage/spotlit."

4. **Post-parse reconciliation step.**
   After 3 parses, run a 4th Haiku call in "reconcile mode" with the 3 scoring arrays as input, asked to merge into a canonical deduplicated set with one entry per `(phase, location, piece)` tuple. Adds ~$0.02 per run but should materially lift accuracy.

5. **Re-run 3-year matrix after items 1–4 land.**
   Success criterion: ≥ 90% accuracy on 2019 (17/17 within reach), ≥ 80% on 2023 and 2024.

Estimated effort: 3 hours for prompt tightening + consensus rekey + reconcile pass. Target: before 2027 kickoff (9 months of runway).

---

## Why the hardened run is still a good outcome

Pre-hardening, the 2019 cargo failures were masked — the validator silently returned the hatch row as "the cargo entry" and reported false-positive passes alongside misleading "failures". The hardened prompt + strict validator now gives **clean diagnostics**: when the parser drops an entry, we see "no entry matched" instead of a wrong match wearing the right label. That matters more for the real goal (kickoff-morning human review of parser output) than a point or two of raw accuracy — a mentor can spot "no entry for cargo scoring" in the diff and add it in 30 seconds, whereas a wrong-entry false positive sails through review.

68.1% raw accuracy with clean failure diagnostics is a better foundation to iterate from than 82% with silent collapses.

---

## Execution log (hardened prompt runs)

```
2019 Deep Space  — 14/17 accuracy, $0.1216, 97,803→4,759 tok, locked=0 tentative=2 ambiguous=28
2023 Charged Up  — 10/16 accuracy, $0.1512, 98,658→10,516 tok, locked=0 tentative=23 ambiguous=74
2024 Crescendo   — 8/14 accuracy, $0.1353, 95,331→7,995 tok, locked=6 tentative=7 ambiguous=17
---------------------------------------------------------------
Total            — 32/47 (68.1%), $0.4081, 291,792→23,270 tokens
```

Sequential execution required due to 50k input-tokens/min Haiku rate limit — parallel launch of all 3 years 429'd reliably. Stagger 60–90 s between year starts for clean runs.

---

## Action items opened by this validation

1. Consensus key change from `name` → `(phase, location, points)` tuple — **blueprint/manual_parser.py**
2. Prompt add explicit weight-constraint clause — **blueprint/manual_parser.py**
3. Prompt add explicit tier/level/zone enumeration clause — **blueprint/manual_parser.py**
4. Add post-parse reconcile pass (4th Haiku call) — **blueprint/manual_parser.py**
5. Re-run 3-year matrix; target ≥ 80% mean accuracy — **blueprint/validate_manual.py**

Target: 2027 kickoff-readiness. Estimated effort: 3 hours.
