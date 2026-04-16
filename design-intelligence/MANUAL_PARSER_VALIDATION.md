# Manual Parser Validation — FRC 2019 / 2023 / 2024

**Status:** ✅ HAIKU + SONNET MATRIX COMPLETE
**Date run:** 2026-04-15
**Target module:** `blueprint/manual_parser.py`
**Driver:** `blueprint/validate_manual.py` (year-agnostic, per-year ground truth)
**Corpora:** `manuals/2019_deep_space.pdf`, `manuals/2023_charged_up.pdf`, `manuals/2024_crescendo.pdf` (all gitignored)
**Configuration:** `n_parses=3`, hardened `PROMPT_TEMPLATE`, models compared: `claude-haiku-4-5` vs `claude-sonnet-4-5`
**Summary data:** `design-intelligence/_{2019,2023,2024}_validation_summary.json` (Sonnet overwrites — Haiku numbers preserved in this doc)

---

## Headline matrix — Sonnet vs Haiku head-to-head

| Year | Game | Haiku 4.5 | Sonnet 4.5 | Δ |
|---|---|---|---|---|
| 2019 | Deep Space | 14 / 17 (82.4%) | **15 / 17 (88.2%)** | +1 |
| 2023 | Charged Up | 10 / 16 (62.5%) | 10 / 16 (62.5%) | 0 |
| 2024 | Crescendo | 8 / 14 (57.1%) | **10 / 14 (71.4%)** | +2 |
| **Totals** | — | 32 / 47 (68.1%) | **35 / 47 (74.5%)** | **+3 (+6.4%)** |
| **Cost** | — | **$0.4081** | **$1.1021** | 2.7× |

### Per-year detail (Haiku | Sonnet)

| Year | Cost (H/S) | In tok | Out tok (H/S) | Locked (H/S) |
|---|---|---|---|---|
| 2019 | $0.12 / $0.36 | 97,803 | 4,759 / 4,144 | 0 / 0 |
| 2023 | $0.15 / $0.36 | 98,658 | 10,516 / 4,274 | 0 / 4 |
| 2024 | $0.14 / $0.39 | 95,331 | 7,995 / 6,695 | 6 / 4 |

### Where Sonnet specifically wins

- **2019**: correctly separated `CARGO in ROCKET (teleop) = 3` (Haiku dropped it into the HATCH PANEL aggregate)
- **2024**: correctly enumerated `PARK = 1` and `ONSTAGE = 3` (Haiku emitted neither)
- **Consistency**: Sonnet's scoring-entry names vary less parse-to-parse → locked rate jumped from 0 to 4 on 2023

### Where Sonnet does NOT help

- **2019**: both `cargo_in_cargo_ship` entries still missing (auto + teleop) — parser split Rocket cleanly but kept the Cargo Ship cells merged
- **2023**: hybrid and high grid nodes completely missing across both phases; engage=10 still collapses to dock=6; weight still `None`
- **2024**: spotlit=1 missed (merged with ONSTAGE); teleop amplified speaker=5 missed (merged with non-amp teleop=2); weight still `None`

### Verdict

Sonnet helps modestly at 2.7× cost. $1.10 for a once-a-year kickoff run is trivial. But **the core failure mode is unchanged**: multi-cell table collapse. Upgrading the model chips at the edges, it doesn't fix the root cause.

- No truncation issues across any of the three 263k–313k-char manuals. JSON parse succeeded on all 18 calls (9 Haiku + 9 Sonnet).
- Wall-clock: Haiku 11–15 s/parse, Sonnet 25–45 s/parse. Sequential runs required — 50k input-tokens/min rate limit caps parallel launches at this corpus size.

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

---

## The real fix — stop flattening tables before the LLM sees them

The Haiku→Sonnet bump closed 6% of the gap. Prompt hardening closed none of the cargo-collapse gap. Every remaining failure is the same root cause: **`pypdf` destroys the 2D table structure of scoring rules before we hand the text to the LLM.** We're asking Haiku/Sonnet to reconstruct "hybrid / mid / high × cone / cube" from linear text with whitespace collapsed, and they can't.

### Two candidate inputs that preserve table structure

**Option A — HTML scrape from frcmanual.com**
- Community-maintained HTML mirror of the manual
- Tables are native `<table><tr><td>` — BeautifulSoup parses them in one line
- Input token drop: 97k → ~35k (strip nav/css), cost ~60% lower
- Risk: hosted by third party, may not have historical back-fill, need PDF as source-of-truth cross-check

**Option B — MinerU (PDF + vision layout detection)**
- opendatalab/MinerU emits markdown with proper `| col | col |` table syntax from PDF
- Works offline, no third-party dependency, authoritative PDF as input
- Tradeoff: 2–3 GB model download, 30–90 s inference per manual, AGPL-3.0 license

**Lighter alternative — Docling (IBM, MIT license)**
- Similar capability to MinerU, smaller footprint, permissive license
- Best candidate if we want PDF-native without AGPL baggage

### Right architecture

- **Primary:** HTML scrape from frcmanual.com when the year is hosted (trivial + cheap)
- **Fallback:** Docling (or MinerU) on the PDF when HTML isn't available
- **Source of truth:** PDF always wins on disagreement — HTML is a structural hint, not an authority

### Next spike

Pick one year (2024 or 2025) and swap `extract_pdf_text()` for an HTML-scrape adapter. Re-run validation. Success criterion: `teleop.amplified_speaker=5` and `endgame.spotlit=1` pass. If they do, the multi-tier failures across 2019/2023/2024 all go with them.

---

## HTML spike — shipped 2026-04-15

**Outcome:** 35/36 (97.2%) on the two HTML-available years, Sonnet 4.5. Every multi-tier table collapse that dogged PDF parsing went away.

| Year | Input | Accuracy | Cost | Notes |
|---|---|---|---|---|
| 2024 Crescendo | FIRST HTML blob | **14 / 14 (100%)** | $0.47 | All prior PDF failures pass — teleop.speaker=2, amplified=5, spotlit=4, weight=125.5 |
| 2025 Reefscape | FIRST HTML blob | **21 / 22 (95.5%)** | $0.43 | Weight was mis-set in GT (expected 125, actual R103 = 115); parser correct, GT patched |
| 2026 REBUILT | FIRST HTML + DOCX cross-check | Structural parity | — | Both sources encode the same 13×5 scoring table byte-for-byte (modulo em-dash encoding) |

### What changed in `blueprint/manual_parser.py`

1. **`extract_html_text(source)`** — accepts a file path or `http(s)://` URL. BeautifulSoup + cp1252 encoding fallback for FIRST's Windows-1252 output. Walks the DOM top-down and emits tables as markdown pipe-tables, paragraphs and headings inline. Crucially, `_table_to_markdown()` does proper rowspan/colspan grid expansion so a category label with `rowspan=3` appears in every row it spans — this is the fix that made ONSTAGE/SPOTLIT split cleanly on 2024.
2. **`build_parse_window()`** — 115k-char head + 10k-char targeted robot-rules excerpt. Keeps Sonnet input under the 30k tokens/min starter-tier cap while still including R103 (weight rule sits ~130k chars into modern manuals, past a naive head cut).
3. **`_call_with_rate_limit_retry()`** — exponential backoff on `RateLimitError`. Paired with a `inter_parse_delay_s=30.0` default in `parse_manual()`, three parses take ~90 s and stay inside the per-minute input-token budget.
4. **URL dispatch** — `parse_manual()` now sniffs scheme; `http(s)://` routes to HTML extractor, `.htm/.html` reads as HTML, `.pdf` stays on pypdf.

### What changed in `blueprint/validate_manual.py`

1. **`--source html`** flag + `first_html_url(year)` helper. Defaults to the FIRST blob URL when no local path given.
2. **`find_pts(..., exclude=[...])`** — disambiguates substring matches like `AMPLIFIED` vs `not AMPLIFIED` and `SPOTLIT` vs `not SPOTLIT`. Was silently picking the wrong entry pre-fix.
3. **2025 Reefscape GT** — 22 scoring checks covering coral L1-L4 (auto+teleop), algae processor + net, leave, park/shallow/deep cage, 3 RPs, weight=115 (post-correction).
4. **2024 GT corrections** — weight=125.5lb (was 125.0), spotlit=4 (was delta +1).

### Why this works where pypdf didn't

pypdf flattens a 4-column scoring table into a single linear run of whitespace-collapsed text. The LLM can't tell that "3" belongs to the ONSTAGE row's point column vs being a stray page number. HTML preserves the 2D structure, which after rowspan/colspan expansion gives each cell a unique `(row, col)` coordinate. The LLM reads a clean pipe-table and never has to reconstruct geometry.

### FIRST blob URL coverage

`firstfrc.blob.core.windows.net/frc{year}/Manual/HTML/{year}GameManual.htm` — confirmed live for **2024, 2025, 2026**. 2019/2020/2022/2023 return 404. For historical-year validation we still need a PDF-native structured extractor (Docling / Marker) — that's the next spike.

### Cost delta vs PDF+Haiku

| | PDF + Haiku | HTML + Sonnet | Δ |
|---|---|---|---|
| 2024 accuracy | 8/14 (57%) | 14/14 (100%) | +43 pts |
| Per-year cost | $0.14 | $0.45 | +$0.31 |
| Mean accuracy (HTML years) | 68% | **97%** | +29 pts |

$0.90 for a 2-year kickoff-morning audit is a rounding error. The win here isn't cost efficiency — it's accuracy that's now usable without a 30-minute human reconciliation pass.

### Remaining work

1. **Historical PDF spike** — evaluate `marker-pdf` and `markitdown` on 2019/2023 to see if we can recover structured tables from PDF-only years. Same ground-truth harness, just swap the extractor.
2. **2026 live-kickoff dry run** — run validation against 2026 HTML once we write the 2026 ground-truth dict (REBUILT scoring table from Table 6-2: FUEL 1/1, TOWER L1 15/10, L2 0/20, L3 0/30, RPs ENERGIZED/SUPERCHARGED/TRAVERSAL).
3. **Rate-limit tier** — $3 input × 30k tok/min = tight. Moving to the Build tier ($5/MTok, 50k/min) eliminates the need for pacing and lets us run 5 parses instead of 3 for marginal lift. Decide before Jan 2027.
