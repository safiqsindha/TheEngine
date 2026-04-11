# Plan — Oracle Prediction Engine Test Suite
**Budget:** ~1 hour autonomous (Sonnet 4.6)
**Branch tip:** `a16a39f` | **Today:** 2026-04-11

---

## The gap

`blueprint/oracle.py` is 810 lines of pure-logic prediction engine. It applies
R1–R19 rules from `CROSS_SEASON_PATTERNS.md` to a `GameRules` dataclass and
emits a structured prediction (drivetrain, intake, scorer, endgame, autonomous,
weight budget, build order).

**It has zero tests.**

This is The Engine's highest-leverage subsystem — at kickoff in Jan 2027,
the team will literally feed the new game's rules into this file and use the
output to start prototyping within 4 hours. A regression in any of the rules
ships silently to a build season decision. We have 9 months of off-season —
this is exactly when to lock in the prediction engine with regression tests.

The file is **stable** (only touched in the initial Engine commit `febb10d` —
no changes since), so test churn risk is low.

---

## What's in oracle.py

### Public surface
- `class GameRules` — input dataclass (game piece, scoring targets, endgame, field)
- `class RuleResult` — per-rule output (rule_id, applies, recommendation, confidence, reasoning)
- `apply_rules(game: GameRules) -> dict` — the main entry point. Returns:
  ```
  {drivetrain, intake, scorer, endgame, autonomous, weight_budget, build_order, rule_log}
  ```
- `predict_game(game)`, `predict_from_file(path)`, `run_full_pipeline(game)` — wrappers
- `validate_all() -> dict` — runs apply_rules against `HISTORICAL_GAMES` + `GROUND_TRUTH`

### Test fixtures already in the file
- `HISTORICAL_GAMES`: GameRules for 2022 Rapid React, 2023 Charged Up, 2024 Crescendo, 2025 Reefscape
- `GROUND_TRUTH`: What the best teams actually built each year (drivetrain, intake_width, scorer_method, turret, endgame)

### Rules visible in apply_rules (`grep "── R" blueprint/oracle.py`)
R1 (drivetrain), R2 (intake width), R3 (roller material), R4 (scorer method),
R5 (elevator stage count), R6 (turret), R7 (endgame), R8 (autonomous),
R10 (game piece detection), R18 (obstacle check), R19 (capped vs uncapped).

That's 11 of the documented 19 primary rules. Test what's implemented; don't
invent tests for rules that don't exist in the code.

---

## Goals

1. **One test per implemented rule** that pins down its happy path
2. **Boundary tests** for the rules with explicit thresholds (small field cutoff,
   frame perimeter cutoff, capped vs uncapped piece thresholds)
3. **Historical regression lock-in** — `validate_all()` must return ≥90% accuracy
   (the existing repo claim is ~98% per memory and PREDICTION_ENGINE_VALIDATION
    docs; pin to ≥90% so the test isn't fragile against minor rule tweaks)
4. **Predict-from-file path** — round-trip a GameRules through JSON and back
5. **End state:** `pytest tests/` collects ~840+ tests, all pass, zero warnings

---

## Ground rules

- **One file:** `tests/blueprint/test_oracle.py`. Pytest-style functions, not
  unittest.TestCase (the rest of the blueprint suite is a mix; pytest functions
  are simpler for new code).
- **No new imports outside stdlib + pytest + oracle itself.** No mocking
  libraries — oracle.py is pure logic.
- **Don't modify oracle.py.** If a test reveals a bug, document it in the test
  with `pytest.mark.xfail` and a clear comment, but don't change the source in
  this session. (Off-season — if there's a real bug, it gets a separate PR.)
- **sys.path fix uses the same pattern as the other moved blueprint tests:**
  ```python
  _BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
  sys.path.insert(0, str(_BLUEPRINT_DIR))
  ```
- **Run `pytest tests/blueprint/test_oracle.py -q` between batches.** Test
  count must grow monotonically.

---

## Phase 1 — Read + scaffold (10 min)

### 1.1 Read oracle.py end-to-end
- `apply_rules()` lines 97–401 (the entire rule pipeline)
- `_get_primary_target()` line 403
- `_run_scoring_analysis()` line 410
- `HISTORICAL_GAMES` line 445
- `GROUND_TRUTH` line 535
- `validate_all()` line 575

While reading, write a scratch comment in this plan listing every assertion you
intend to make. This is the "test plan" — get it down before writing test code
so the test file isn't a stream-of-consciousness mess.

### 1.2 Create the test file skeleton
```python
"""
Tests for blueprint/oracle.py — the prediction engine that applies
CROSS_SEASON_PATTERNS R1-R19 to a GameRules input.

Hermetic: pure logic, no I/O.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
sys.path.insert(0, str(_BLUEPRINT_DIR))

from oracle import (
    GameRules,
    RuleResult,
    apply_rules,
    predict_game,
    predict_from_file,
    validate_all,
    HISTORICAL_GAMES,
    GROUND_TRUTH,
)
```

Run `pytest tests/blueprint/test_oracle.py -q`. Should collect 0, exit 0
(empty file, no failures). Confirms imports work before you write any tests.

---

## Phase 2 — Per-rule happy-path tests (20 min)

Write one test per rule listed in §"Rules visible in apply_rules". Each test:
1. Constructs a minimal `GameRules` that triggers the rule
2. Calls `apply_rules(game)`
3. Asserts the relevant output field

Use small helper builders if it makes the tests shorter. Example pattern:

```python
def _minimal_game(**overrides):
    """Build a GameRules with minimal valid defaults; override what each test cares about."""
    base = dict(
        game_name="Test",
        year=2027,
        scoring_targets=[
            {"name": "T1", "height_in": 60, "distance_ft": 8, "auto_pts": 4,
             "teleop_pts": 2, "type": "ranged", "distributed": True,
             "cap_type": "uncapped", "max_alliance_pts": 999},
        ],
        endgame_type="climb",
        endgame_height_in=30,
        endgame_points=10,
    )
    base.update(overrides)
    return GameRules(**base)


def test_r1_drivetrain_always_swerve():
    pred = apply_rules(_minimal_game())
    assert pred["drivetrain"]["type"] == "swerve"
    assert pred["drivetrain"]["module"] == "sds_mk4i"


def test_r1_speed_small_field_gears_for_acceleration():
    pred = apply_rules(_minimal_game(field_is_small=True))
    assert pred["drivetrain"]["gear_for"] == "acceleration"
    assert pred["drivetrain"]["speed_fps"] == 14.0
```

**Target: ~15-20 tests** in this phase (one main happy path + one boundary case
for each of the 11 implemented rules). Run `pytest tests/blueprint/test_oracle.py -q`
after every 5 tests.

---

## Phase 3 — Historical regression lock-in (10 min)

This is the most important phase. It pins the prediction engine's accuracy.

```python
def test_validate_all_meets_accuracy_threshold():
    """Lock in oracle accuracy. If a rule change drops historical accuracy
    below 90%, this test fails and forces an explicit decision."""
    result = validate_all()
    assert result["accuracy_pct"] >= 90.0, (
        f"Oracle accuracy dropped to {result['accuracy_pct']}% — "
        f"a rule change broke historical validation. {result['correct']}/{result['total_checks']}"
    )


def test_validate_all_covers_all_historical_games():
    """If a new historical game is added, this test reminds you to add ground truth."""
    result = validate_all()
    assert set(result["results"].keys()) == set(HISTORICAL_GAMES.keys())
    assert set(HISTORICAL_GAMES.keys()) == set(GROUND_TRUTH.keys())


@pytest.mark.parametrize("year_str", sorted(HISTORICAL_GAMES.keys()))
def test_historical_game_predicts_correct_drivetrain(year_str):
    pred = apply_rules(HISTORICAL_GAMES[year_str])
    assert pred["drivetrain"]["type"] == GROUND_TRUTH[year_str]["drivetrain"]
```

**Note:** `validate_all()` prints to stdout. That's fine for tests — pytest
captures stdout by default. If it gets noisy, add `capsys` and discard.

**Add parametrize sweeps** for intake_width, scorer_method, endgame across all
4 historical games — that's 4 games × 3 fields = 12 cheap tests that catch any
regression in any rule across any year.

**Target: ~15 tests** in this phase.

---

## Phase 4 — Edge cases + JSON round-trip (10 min)

Things worth pinning that aren't covered by per-rule tests:

1. **Empty scoring_targets** — does apply_rules crash or default cleanly?
2. **Single scoring target** — does the scoring analysis handle it?
3. **Frame perimeter < 112"** — `frame_size = min(27.0, perimeter/4 - 1)`
4. **Capped vs uncapped game** (R19) — feed a strictly capped game and assert
   the scorer reasoning mentions R19
5. **Field has obstacles** — R18 path
6. **Game piece detection threshold** — R10 with high vs low contrast
7. **`predict_from_file`** — write a GameRules to JSON tempfile, load it back,
   assert prediction matches the in-memory call
8. **`build_order` non-empty** — every prediction should have a non-empty
   build_order list
9. **`rule_log` is populated** — every prediction should record the rules that
   fired

```python
def test_predict_from_file_round_trip(tmp_path):
    """A GameRules → JSON → predict_from_file → same prediction as in-memory."""
    from dataclasses import asdict
    game = HISTORICAL_GAMES["2024"]
    json_path = tmp_path / "game.json"
    json_path.write_text(json.dumps(asdict(game)))
    pred_from_file = predict_from_file(str(json_path))
    pred_in_memory = apply_rules(game)
    assert pred_from_file["drivetrain"] == pred_in_memory["drivetrain"]
```

**Target: ~10 tests** in this phase.

---

## Phase 5 — Run, count, commit (5 min)

```
python3 -m pytest tests/blueprint/test_oracle.py -v
python3 -m pytest tests/ -q
```

Expected: ~50 new tests. tests/ should be ~840+ passing. 0 warnings.

If any test fails:
- **First check the test, not the source.** Most likely: wrong fixture data or
  a misread of the rule.
- **If the source is genuinely buggy:** mark the test `@pytest.mark.xfail(reason="...")`
  with a clear comment. Do NOT modify oracle.py in this session — that's a
  separate decision.

Commit:
```
git add tests/blueprint/test_oracle.py
git commit -m "test(blueprint): add ~50 tests for oracle.py prediction engine

- Per-rule happy paths for R1-R8, R10, R18, R19
- Historical regression lock-in: validate_all() accuracy ≥90%
- Parametrize sweep across HISTORICAL_GAMES × {drivetrain, intake, scorer, endgame}
- Edge cases: empty scoring_targets, capped/uncapped, JSON round-trip
- predict_from_file round-trip verification

tests/: 796 → ~846, 0 warnings"
```

---

## Phase 6 — Push + INDEX update (5 min)

```
git push origin main
```

Update `design-intelligence/INDEX.md` line 7 to reflect the new test count
(currently says 796). Commit + push that as a separate one-liner commit.

---

## Abort conditions

- **More than 5 tests fail and the failures look like real bugs.** Stop, document
  in a follow-up scratch file, push what passes, hand back to the user.
- **`validate_all()` returns < 90% accuracy** — that means oracle has already
  regressed and this isn't the session to fix it. Lower the threshold to whatever
  it actually returns, mark the assertion with a `# TODO: investigate accuracy
  drop` comment, and surface this in the commit message.

---

## Out of scope

- **Mechanism generator tests** (plate_generator, turret_generator, cad_builder).
  Each is its own session; bundling them risks rushing oracle.
- **Modifying oracle.py.** Pure test addition this session. If a bug surfaces,
  document it; don't fix it inline.
- **Validating CROSS_SEASON_PATTERNS.md against the implementation.** That's a
  doc-vs-code reconciliation task, separate scope.
- **Adding new HISTORICAL_GAMES entries** (e.g., 2026 REBUILT). Separate task —
  needs ground truth research.

---

## Why this is the right next thing

**Highest leverage in the codebase:** Oracle is the single file that determines
"what does the team build at kickoff?". Every other Engine subsystem assists; this
one decides. Locking it down with tests means rule changes have to be intentional.

**Stable surface:** Hasn't been touched since the initial commit. Tests written
today won't churn next week.

**Hermetic + fast:** Pure logic, no I/O, no API calls. Tests run in <100ms,
fit cleanly into the existing CI which already runs `tests/` end-to-end.

**Off-season fit:** This is exactly the kind of "infrastructure investment that
pays off when 2027 kickoff hits" work. There is no in-season urgency; we have 9
months. Doing it now means by January the prediction engine has a regression
safety net.

**Closes the biggest test gap:** 810 LOC of zero-coverage logic in the most
important file. After this session, the only large untested blueprint files are
mechanism builders (plate, turret, cad_builder) which are mechanical and lower-leverage.
