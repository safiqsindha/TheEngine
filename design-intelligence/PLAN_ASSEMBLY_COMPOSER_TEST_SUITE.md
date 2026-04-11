# Plan — Assembly Composer Test Suite (B.6 lock-down)
**Budget:** ~1 hour autonomous (Sonnet 4.6 — recalibrated, real budget)
**Branch tip:** `9477b7f` | **Today:** 2026-04-11
**Predecessor:** `PLAN_ORACLE_TEST_SUITE.md` (executed 2026-04-11, 78 tests added)

---

## The architectural gap

The Engine's blueprint pipeline is a **chain of trust**:

```
GameRules → oracle.apply_rules() → blueprint spec dict → assembly_composer.compose_robot() → RobotLayout → mechanism generators → CAD
                  ↑ LOCKED 2026-04-11             ↑ NEXT LINK — UNTESTED
```

Oracle is now pinned by 78 tests. The next link — `blueprint/assembly_composer.py`
(472 LOC) — is the **integration layer** that decides where each mechanism
physically mounts on the frame, computes the center of gravity, runs interference
checks, and emits the assembly order. **It has zero tests.**

This is the file that turns "logical robot design" into "physical robot
geometry." If `compose_robot()` returns wrong placements at kickoff 2027, the
team builds a robot with overlapping mechanisms and a CoG that won't pass
inspection. There is no second line of defense — the mechanism generators just
use whatever positions assembly_composer returns.

It's also **stable**: last touched 2026-04-09, no churn since. Same low-risk
profile as the oracle session.

---

## What's in assembly_composer.py

### Public surface
- `class MechanismPlacement` — output dataclass: `name`, `position_in [x,y,z]`,
  `position_mm`, `envelope_in/mm`, `weight_lb`, `mounting_face`, `notes`
- `class RobotLayout` — top-level output: `frame_length/width/height_in`,
  `placements: list`, `swerve_modules`, `electronics`, `total_height_in`,
  `center_of_gravity_in [x,y,z]`, `interference_warnings`, `assembly_order`,
  `notes`
- `compose_robot(spec: dict) -> RobotLayout` — the entry point. Reads
  `spec["frame"]`, `spec["intake"]`, `spec["flywheel"]`, `spec["elevator"]`,
  `spec["climber"]`, `spec["conveyor"]`, etc., and returns a fully-populated
  layout.
- `_check_overlap(p1, p2) -> bool` — internal AABB overlap test
- `display_layout(layout)` — pretty-printer (don't test, it's print-only)

### Placement zones (read these before writing tests)
Lines 41–80 of assembly_composer.py define `PLACEMENT_ZONES`: each mechanism
type has a `preferred` zone (front / back / center / etc.), a `z_base`
(frame_top / above_conveyor / etc.), and notes. Tests should assert each
mechanism lands in its preferred zone.

### Fixtures already on disk
`blueprint/2022_rapid_react_full_blueprint.json`,
`blueprint/2023_charged_up_full_blueprint.json`,
`blueprint/2024_crescendo_full_blueprint.json` —
real spec dicts produced by past pipeline runs. Top-level keys:
`game, year, frame, intake, flywheel/elevator, conveyor, climber, bom_rollup,
scoring_analysis, auto_strategy, build_order`. These are the "HISTORICAL_GAMES
of assembly_composer" — use them directly.

### Integration with oracle
Oracle's `apply_rules()` does NOT produce a full blueprint spec — it produces a
prediction dict with `drivetrain/intake/scorer/endgame/etc.`. The full
blueprint spec is built by downstream mechanism generators (frame_generator,
intake_generator, etc.) consuming oracle's prediction. So the contract under
test here is **mechanism specs → robot layout**, not oracle → layout directly.
Don't try to wire oracle output straight into compose_robot — it'll be missing
the per-mechanism geometry fields.

---

## Goals

1. **Per-mechanism placement tests** — intake lands at front, elevator at center
   back, climber where you'd expect, etc. One test per mechanism type listed in
   `PLACEMENT_ZONES`.
2. **Interference detection works** — fabricate two mechanisms with overlapping
   envelopes, assert a warning is emitted. Then a non-overlapping pair, assert
   no warning.
3. **Center of gravity sanity** — CoG stays inside the frame bounds for all 3
   historical specs. Tall mechanisms (elevator) raise the CoG above the frame
   height; short ones (intake) keep it low.
4. **Historical regression lock-in** — for each of 2022/2023/2024 full blueprint
   specs, assert (a) compose_robot doesn't crash, (b) returns a non-empty
   placements list, (c) has zero interference warnings (these were real shipping
   designs).
5. **Assembly order is non-empty and topologically sane** — frame mounts before
   anything else, electronics last.
6. **Unit conversion** — `_in_to_mm` round-trips correctly; placements have both
   `position_in` and `position_mm` populated and consistent.
7. **End state:** `pytest tests/` collects ~920+ tests, all pass, zero warnings.

---

## Ground rules

- **One file:** `tests/blueprint/test_assembly_composer.py`. Pytest functions,
  not unittest. Same style as `test_oracle.py`.
- **No new imports outside stdlib + pytest + assembly_composer itself.**
- **Don't modify assembly_composer.py.** If a test reveals a bug, mark it
  `pytest.mark.xfail(strict=True)` with a comment pointing to the line. Real
  bug fixes are a separate session — same rule as oracle.
- **sys.path fix uses the same pattern:**
  ```python
  _BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
  sys.path.insert(0, str(_BLUEPRINT_DIR))
  ```
- **Load historical fixtures from `_BLUEPRINT_DIR`** so tests find the JSON
  files regardless of where pytest is invoked from:
  ```python
  HISTORICAL_SPECS = {
      year: json.loads((_BLUEPRINT_DIR / f"{year}_{name}_full_blueprint.json").read_text())
      for year, name in (("2022", "rapid_react"), ("2023", "charged_up"), ("2024", "crescendo"))
  }
  ```
- **Run `pytest tests/blueprint/test_assembly_composer.py -q` between phases.**
  Test count must grow monotonically.
- **Run `pytest tests/ -q` at the end.** Final count: 874 → ~920+, zero
  warnings, all pass.

---

## Phase 1 — Read + scaffold (10 min)

### 1.1 Read assembly_composer.py end-to-end
- Lines 30–80 — `PLACEMENT_ZONES` constant (every test's source of truth)
- Lines 82–110 — `MechanismPlacement` and `RobotLayout` dataclasses
- Lines 118–391 — `compose_robot()` body (the entire placement pipeline)
- Lines 392–402 — `_check_overlap()`
- (Skip `display_layout()` and `main()` — print-only / CLI)

While reading, jot the actual key names each mechanism block uses
(`spec["intake"].get("...")`) — that's what the test fixtures need to provide.
The 3 historical full_blueprint.json files give you those keys for free; just
inspect them with `python3 -c "import json; print(list(json.load(open('blueprint/2022_rapid_react_full_blueprint.json'))['intake'].keys()))"`.

### 1.2 Create the test file skeleton
```python
"""
Tests for blueprint/assembly_composer.py — the integration layer that
decides where each mechanism mounts on the robot frame.

Hermetic: pure logic, no I/O beyond loading historical fixture JSONs from
the blueprint/ directory.
"""

import json
import sys
from pathlib import Path

import pytest

_BLUEPRINT_DIR = Path(__file__).resolve().parents[2] / "blueprint"
sys.path.insert(0, str(_BLUEPRINT_DIR))

from assembly_composer import (  # noqa: E402
    MechanismPlacement,
    RobotLayout,
    compose_robot,
    _check_overlap,
    _in_to_mm,
    PLACEMENT_ZONES,
)

HISTORICAL_SPECS = {
    year: json.loads((_BLUEPRINT_DIR / f"{year}_{name}_full_blueprint.json").read_text())
    for year, name in (
        ("2022", "rapid_react"),
        ("2023", "charged_up"),
        ("2024", "crescendo"),
    )
}
```

Run `pytest tests/blueprint/test_assembly_composer.py -q`. Should collect 0,
exit 0. Confirms imports + fixture loads work.

---

## Phase 2 — Unit helpers + per-mechanism placements (15 min)

Tests should be small and focused. Helper:

```python
def _minimal_spec(**mechanism_overrides):
    """Build a minimal blueprint spec dict — frame + whatever mechanisms the test needs."""
    spec = {
        "frame": {
            "frame_length_in": 27.0,
            "frame_width_in": 27.0,
            "frame_height_in": 1.0,
        }
    }
    spec.update(mechanism_overrides)
    return spec
```

### 2.1 Helper tests (~5 tests)
- `_in_to_mm(1.0) == 25.4`
- `_in_to_mm(0) == 0`
- `_in_to_mm` round-trip via 25.4 division stays within rounding tolerance
- `MechanismPlacement` defaults: position is `[0,0,0]`, envelope is `[0,0,0]`
- `RobotLayout` defaults: frame is 27x27x1, placements list empty

### 2.2 Frame-only baseline (~3 tests)
- `compose_robot({"frame": {...}})` returns a `RobotLayout` instance
- Layout has the frame dimensions echoed back
- `placements` may be empty when no mechanisms; `interference_warnings` empty;
  `assembly_order` non-empty (should at least include "frame")

### 2.3 Per-mechanism placement (~10 tests)
For each mechanism type listed in `PLACEMENT_ZONES`, build a minimal spec with
just that mechanism, call compose_robot, find the placement in `layout.placements`,
and assert it landed in its preferred zone.

**Don't guess at the mechanism field shapes — read what compose_robot actually
reads at lines 118-391.** For each `if "mechanism" in spec:` block, look at
which sub-fields it pulls (e.g. `spec["intake"].get("width_in")`,
`spec["elevator"].get("max_extension_in")`). Cross-reference with the
historical JSON fixtures for the right shape.

Example pattern:
```python
def test_intake_lands_at_front():
    intake_spec = HISTORICAL_SPECS["2022"]["intake"]  # known-good shape
    layout = compose_robot(_minimal_spec(intake=intake_spec))
    intake_placements = [p for p in layout.placements if "intake" in p.name.lower()]
    assert intake_placements, "intake should appear in placements"
    # Front of robot is +Y. Intake should have positive Y position.
    assert intake_placements[0].position_in[1] > 0
```

**Important:** if a mechanism block in compose_robot uses different field names
than the historical JSON, that's a real bug to flag (xfail). Don't fudge it.

---

## Phase 3 — Interference, CoG, assembly order (15 min)

### 3.1 _check_overlap (~5 tests)
- Two non-overlapping placements → False
- Two identical placements → True
- Overlap on X only (not Y/Z) → False (need overlap on all 3 axes)
- Overlap on all 3 axes → True
- Edge-touching placements (face-to-face) → False (touching is not overlapping)

### 3.2 Center of gravity (~4 tests)
For each historical spec, compose_robot, and assert:
- CoG x and y stay within ±half the frame (i.e. CoG inside the footprint)
- CoG z is positive (above bellypan)
- CoG z for elevator-heavy specs (2023, 2024) is higher than for flywheel-only
  specs (2022) — sanity check

### 3.3 Assembly order (~3 tests)
- Order is non-empty for each historical spec
- Frame appears before all mechanisms in the order
- Electronics, if present, appear after structural mounts

---

## Phase 4 — Historical regression lock-in (10 min)

This is the most important phase. It pins the layout engine for the 3 known-good
designs.

```python
@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_compose_does_not_crash(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert isinstance(layout, RobotLayout)


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_layout_has_placements(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert len(layout.placements) >= 2  # at least intake + scorer


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_no_interference(year):
    """The 3 historical designs were real shipping robots. They MUST be
    interference-free, otherwise the layout engine has a regression."""
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert layout.interference_warnings == [], (
        f"{year} layout has unexpected interference: {layout.interference_warnings}"
    )


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_cog_inside_frame(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    cog_x, cog_y, cog_z = layout.center_of_gravity_in
    half_l = layout.frame_length_in / 2
    half_w = layout.frame_width_in / 2
    assert -half_l <= cog_x <= half_l
    assert -half_w <= cog_y <= half_w
    assert cog_z >= 0


@pytest.mark.parametrize("year", sorted(HISTORICAL_SPECS.keys()))
def test_historical_total_height_positive(year):
    layout = compose_robot(HISTORICAL_SPECS[year])
    assert layout.total_height_in > 0
```

If `test_historical_no_interference` fails on any historical spec, that's a
**signal** — either compose_robot has a regression or the historical JSON file
on disk doesn't reflect a real shipping design. Don't fudge it; mark xfail with
a clear comment and surface in the commit message.

---

## Phase 5 — Edge cases (5 min)

A handful of small ones:

- Empty spec `{}` → either crashes cleanly (assert with `pytest.raises`) or
  returns a default layout (whichever it actually does — read the code)
- Spec with only frame → returns a RobotLayout with empty placements list
- Frame with non-default dimensions (e.g. 24x32) → layout echoes them
- Two mechanisms with deliberately overlapping envelopes injected at known
  positions → interference_warnings is non-empty

Don't write more than 5 here. Edge cases are infinite; pick the ones that
exercise distinct code paths.

---

## Phase 6 — Run, count, commit, push (5 min)

```
python3 -m pytest tests/blueprint/test_assembly_composer.py -v
python3 -m pytest tests/ -q
```

Expected: 874 → ~920+ tests passed, 2 skipped, 1 xfailed (the existing oracle
predict_from_file xfail), 0 warnings. ~5 second runtime.

If everything passes:
```
git add tests/blueprint/test_assembly_composer.py design-intelligence/PLAN_ASSEMBLY_COMPOSER_TEST_SUITE.md
git commit -m "test(blueprint): add ~50 tests for assembly_composer.py layout engine

- _in_to_mm + dataclass defaults
- Per-mechanism placement: intake/elevator/flywheel/climber/etc. land in zones
- _check_overlap AABB tests
- Historical regression lock-in: 2022/2023/2024 compose without interference
- Center of gravity stays inside frame for all historical specs
- Assembly order: frame first, electronics last

tests/: 874 -> ~920+, 0 warnings"
git push origin main
```

Then update `design-intelligence/INDEX.md` line 7 to reflect the new test
count and add this plan to the Session Snapshots table. Commit + push that as
a separate one-liner.

---

## Abort conditions

- **`test_historical_no_interference` fails on more than one year.** Stop.
  That means compose_robot has changed behavior since the historical JSONs were
  generated. Don't paper over it — surface in the commit message and hand back.
- **More than 5 placement tests fail because field names mismatch.** That means
  the historical JSONs and assembly_composer have drifted apart. Stop, document,
  hand back.
- **`pytest tests/` test count drops below 874.** Something you wrote broke an
  existing test (most likely a sys.path collision). Roll back, investigate.

---

## Out of scope

- **Modifying assembly_composer.py.** Pure test addition this session. Bugs get
  xfailed, not fixed.
- **plate_generator / turret_generator / cad_builder tests.** Each is its own
  session. Don't bundle.
- **Fixing the oracle predict_from_file xfail.** Different file, different
  bug, different session.
- **Wiring oracle.apply_rules() output directly into compose_robot().** They
  speak different schemas (oracle emits prediction; compose_robot consumes
  spec). The bridging happens in mechanism generators, which aren't in scope.
- **Re-generating the historical full_blueprint.json files.** Use them as-is.
  If the layout engine has drifted, the test failure tells us — that's the
  signal we want.

---

## Why this is the right next thing

**Next link in the chain of trust.** Oracle was locked down 2026-04-11 (78
tests). assembly_composer is the immediate downstream consumer in the blueprint
pipeline. Locking it now means rule changes in oracle propagate through a
verified layout engine. Without this lock, any future change to placement
zones, CoG math, or interference detection ships silently to a build season
decision.

**Highest-leverage architectural integration point.** Mechanism generators
(plate, turret, cad_builder) consume placements from compose_robot. If
compose_robot returns wrong positions, every downstream generator outputs
wrong CAD. This is the choke point.

**Stable, hermetic, fast.** Last touched 2026-04-09. Pure Python, no I/O
beyond loading 3 JSON fixtures from disk. Tests run in <100ms. Same risk
profile as the oracle session, which finished cleanly.

**Real-world fixtures already exist.** 4 historical full_blueprint.json files
on disk = free regression scaffolding. Don't write spec dicts by hand — use
the historical files like oracle uses HISTORICAL_GAMES.

**Off-season fit.** No in-season urgency. Doing it now means by 2027 kickoff
the full chain `GameRules → oracle → assembly_composer` is verified end-to-end,
with mechanism generators left for follow-up sessions.

**Recalibrated time budget.** The oracle session was budgeted at 1 hour and
took ~30 minutes for Sonnet. This plan is intentionally smaller (~50 tests vs
78) and should land well under 1 hour. If it does, the next step is to
immediately scope `plate_generator.py` as the follow-up.
