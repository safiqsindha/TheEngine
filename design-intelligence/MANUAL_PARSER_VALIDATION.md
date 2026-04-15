# Manual Parser Validation — 2019 FRC Deep Space

**Status:** BLOCKED — awaiting `ANTHROPIC_API_KEY` to run live ensemble.
**Date prepared:** 2026-04-14
**Target module:** `blueprint/manual_parser.py`
**Driver:** `blueprint/validate_2019_manual.py`
**Corpus:** 2019 Deep Space Game Manual
(`manuals/2019_deep_space.pdf`, 5.2 MB — gitignored)
**Configuration:** `n_parses=3`, `model="claude-haiku-4-5"`

---

## Run status

The live ensemble run is **not yet executed**. Guardrail logic in
`validate_2019_manual.py` refused to run because `ANTHROPIC_API_KEY`
was unset in the shell invoking this validation. The PDF was fetched
successfully from the FIRST primary mirror
(`firstfrc.blob.core.windows.net/frc2019/Manual/2019FRCGameSeasonManual.pdf`)
and is cached locally under `manuals/` (excluded from git).

Per the task guardrails, **no accuracy numbers, token counts, or costs
are reported here** — fabricating those would defeat the purpose of a
historical validation. Rerun once the key is exported.

### To execute the validation

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python blueprint/validate_2019_manual.py
```

Outputs:
- Console: pass/fail per ground-truth check, consensus counts, total
  input/output tokens, and estimated USD cost.
- `design-intelligence/_2019_validation_summary.json`: machine-readable
  summary for the next editor pass on this doc.

---

## Ground-truth checks encoded in the driver

The driver tests 16 Deep Space rules against the consensus output:

| Category | Check | Expected |
|---|---|---|
| Auto | Cargo in Cargo Ship | 3 pts |
| Auto | Hatch on Cargo Ship | 2 pts |
| Auto | HAB cross L1 | 3 pts |
| Auto | HAB cross L2 | 6 pts |
| Teleop | Cargo in Cargo Ship | 3 pts |
| Teleop | Cargo in Rocket | 3 pts |
| Teleop | Hatch on Rocket | 2 pts |
| Teleop | Hatch on Cargo Ship | 2 pts |
| Endgame | HAB climb L1 | 3 pts |
| Endgame | HAB climb L2 | 6 pts |
| Endgame | HAB climb L3 | 12 pts |
| Pieces | Cargo identified | present |
| Pieces | Hatch panel identified | present |
| Possession | `max_simultaneous` | 1 |
| RPs | Rocket RP | present |
| RPs | HAB/climb RP | present |
| Constraint | `weight_lbs` | 125 |

The driver also logs per-parse token usage through an instrumented
`parse_fn` that wraps the default Anthropic client, so cost is measured
against real `response.usage` — not estimated from character counts.

---

## Pending sections (fill after live run)

- [ ] Agreement stats: % locked / tentative / ambiguous across 3 parses
- [ ] Per-field accuracy vs ground truth (X/16 passing)
- [ ] Systematic errors — any rule all 3 parses missed the same way
- [ ] Cost: total tokens × Haiku 4.5 pricing
  ($1.00/MTok in, $5.00/MTok out at the time of this doc)
- [ ] Recommendation: stay at 3 parses, bump to 5, or drop to 2

---

## Why 2019 is the validation target

- Long enough (100+ pages) to stress token/context handling.
- Scoring rules are unambiguous and well-documented in retrospectives,
  so ground truth is not in dispute.
- Rules diverge from modern games (HAB platforms, sandstorm, hatch/cargo
  dual-piece possession) — a good OOD test vs. the parser's 2022–2025
  exposure in existing blueprints.

## Cost envelope (forward estimate only)

Haiku 4.5 on a full game manual is expected to consume roughly
80–120k input tokens per parse and a few hundred output tokens.
Three parses → ~$0.25–$0.40 total, well inside the per-run budget.
Replace this section with real numbers after the first run.
