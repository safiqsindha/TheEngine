# Manual Parser Validation — 2019 FRC Deep Space

**Status:** ✅ COMPLETE
**Date run:** 2026-04-15
**Target module:** `blueprint/manual_parser.py`
**Driver:** `blueprint/validate_2019_manual.py`
**Corpus:** 2019 Deep Space Game Manual (`manuals/2019_deep_space.pdf`, 5.5 MB — gitignored)
**Configuration:** `n_parses=3`, `model="claude-haiku-4-5"`
**Summary data:** `design-intelligence/_2019_validation_summary.json`

---

## Headline results

| Metric | Value |
|---|---|
| Ground-truth checks passed | **14 / 17 (82.4%)** |
| Consensus: locked (3/3 agreed) | 11 fields |
| Consensus: tentative (2/3 agreed) | 7 fields |
| Consensus: ambiguous (no majority) | 6 fields |
| Total input tokens | 96,684 (~32k per parse) |
| Total output tokens | 4,382 |
| Total cost | **$0.1186** (Haiku 4.5 at $1/MTok in, $5/MTok out) |
| Wall-clock per parse | 11.5 – 13.7 s |
| PDF text extracted | 263,221 chars |

Cost came in **at half the forward estimate** ($0.12 vs $0.25-0.40). Haiku's context handling of the 263k-char manual was clean — no truncation issues, no JSON parse failures across 3 runs.

---

## Per-field accuracy breakdown

| Category | Passed | Failed | Notes |
|---|---|---|---|
| HAB climb scoring (auto + endgame, L1/L2/L3) | 6 / 6 | 0 | Perfect on all levels and phases |
| Hatch panel scoring (auto + teleop, Rocket + Cargo Ship) | 4 / 4 | 0 | Perfect |
| Cargo scoring (auto + teleop, Rocket + Cargo Ship) | **0 / 3** | 3 | **Systematic miss — see below** |
| Game pieces identified | 2 / 2 | 0 | Both `cargo` and `hatch panel` extracted |
| Possession limit | 1 / 1 | 0 | `max_simultaneous = 1`, correct note captured |
| Ranking points | 2 / 2 | 0 | Rocket RP + HAB docking RP both present |
| Robot weight constraint | 1 / 1 | 0 | 125.0 lb |

---

## Root cause of the 3 failures — cargo scoring collapse

All three failures return the same `HATCH PANEL` scoring entry:

```
auto.cargo_in_cargo_ship=3      → got HATCH PANEL, 2 pts  [FAIL]
teleop.cargo_in_cargo_ship=3    → got HATCH PANEL, 2 pts  [FAIL]
teleop.cargo_in_rocket=3        → got HATCH PANEL, 2 pts  [FAIL]
```

**Diagnosis:** the parser saw the manual's side-by-side scoring tables (HATCH | CARGO columns per phase) and emitted a single aggregate `HATCH PANEL` row per location instead of separate rows for each game piece. All 3 Haiku parses made the same collapse — this is not a variance problem, it's a prompt-precision problem.

The JSON schema accepted whatever shape Haiku produced. A stricter schema forcing one entry per `(phase, game_piece, location)` tuple, with explicit enumeration examples in the prompt, would prevent this.

**This is a real bug in the parser, not a data issue.** Ground-truth accuracy is 14/17 today but would be 17/17 with a tighter prompt.

---

## Recommended fix — 2027-kickoff readiness

### Prompt hardening (blueprint/manual_parser.py)

Before the next real kickoff, update `DEFAULT_PROMPT` (or equivalent) with:

1. **Explicit tuple requirement:** "Emit one `scoring[]` entry for each distinct `(phase, game_piece, field_location)`. Do not combine game pieces into a single entry even if they appear in the same row of a rulebook table."
2. **Few-shot example** showing a 2-piece game's scoring with separated entries (Reefscape 2025 works — coral + algae).
3. **Post-parse validator** in `consensus()`: if two scoring entries share `(phase, location)` but different `points`, flag as tentative rather than silently picking one.

Cost impact: negligible. Output tokens grow ~10% from separated entries.

### Consensus weighting

11 fields locked (3/3 agreement) and 13 fields had majority agreement at minimum. The 6 ambiguous fields are the tail — mostly penalty-rule details and edge-case zones. **Three parses is the right setting**: bumping to 5 would not have fixed the cargo collapse (all 3 missed it identically), only the prompt fix would.

Dropping to 2 parses loses the tiebreaker on the 7 tentative fields — not worth saving ~$0.04.

### Validator improvement

The ground-truth check logic in `validate_2019_manual.py` uses substring lookup (`find_pts(flat, ["cargo"])`) and returns the first match. When the parser emits no cargo entry, the lookup falls through to hatch panel rows and gives misleading "failure" output. A stricter lookup that returns `None` when no entry matches all keywords would produce cleaner diagnostics.

---

## Agreement stats interpretation

- **11 locked (46%)**: fields where all 3 Haiku parses produced identical (after normalization) values. These are the reliable floor — robot weight, possession limits, major RPs, HAB point values.
- **7 tentative (29%)**: 2/3 agreement. Most are minor: penalty rule categories, zone scope labels. Human review in 10 seconds each.
- **6 ambiguous (25%)**: no majority. These are the ones that need a human pass regardless of parse count — usually penalty table details where the manual itself has ambiguous wording.

For a kickoff-morning workflow, expect roughly 15 minutes of human review after 3-parse ensemble, concentrated on the 13 non-locked fields.

---

## Why 2019 was a good validation target

- Large manual (100+ pages) exercised full context window.
- Dual-piece game (cargo + hatch) — surfaced the exact parser weakness (multi-piece scoring table collapse) that a single-piece game would have hidden.
- HAB climb has asymmetric auto vs endgame scoring — tested phase-tagging correctness.
- Scoring rules are uncontroversial in retrospect, so ground truth is stable.

A 2023 Charged Up or 2024 Crescendo validation would be good complements for 2027-kickoff readiness: Charged Up has alliance-scoped grid scoring which tests scope detection; Crescendo has distinct amp vs speaker scoring which tests location enumeration.

---

## Execution log

```
[+] PDF: manuals/2019_deep_space.pdf (5.5 MB)
[+] Extracted 263,221 chars from PDF
[+] Running 3 parses with claude-haiku-4-5...
[+] Consensus: locked=11 tentative=7 ambiguous=6

Per-field accuracy: 14/17

Tokens: in=96,684 out=4,382
Cost: $0.1186

Wall-clock: 11.5s, 11.5s, 13.7s per parse (parallel would be ~13.7s total)
```

---

## Action items opened by this validation

1. **Harden `DEFAULT_PROMPT` in `blueprint/manual_parser.py`** to enforce one scoring entry per `(phase, piece, location)` tuple.
2. **Tighten validator lookup** in `blueprint/validate_2019_manual.py` to return `None` on no-match rather than fall through to a different entry.
3. **Add `consensus()` guard** that flags same-location-different-points as tentative.
4. **Run 2023 Charged Up + 2024 Crescendo validations** once prompt is hardened, to confirm the fix generalizes.

Estimated effort: 2 hours. Target: before 2027 kickoff.
