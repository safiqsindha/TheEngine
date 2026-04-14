# Blueprint — Next 6 Phases of Architecture Work
**Author:** Opus (planning) | **Executor:** Sonnet 4.6
**Branch tip:** `6bc49bb` | **Today:** 2026-04-11
**Predecessors:** `PLAN_ORACLE_TEST_SUITE.md`, `PLAN_ASSEMBLY_COMPOSER_TEST_SUITE.md`

---

> **⚠ SUPERSEDED 2026-04-13** by `BLUEPRINT_REV2_DECISION.md`.
>
> The A2 smoke test showed FRCDesign reference docs have no Variable Studios (2/2 sampled). Phases 1-5 below are no longer the plan of record:
> - Phase 1 (AABB bug fix): cancelled — `assembly_composer._check_overlap` is deleted, not fixed
> - Phase 4 (`cad_builder` hermetic tests): cancelled — `cad_builder.py` is deleted
> - Phase 5 (Onshape gating): replaced by MCP tool calls
>
> This doc is preserved for audit trail. Read `BLUEPRINT_REV2_DECISION.md` for the current plan.

---

---

## Where we are

The blueprint pipeline is a chain that turns game rules into a buildable robot:

```
GameRules → oracle → mechanism specs → assembly_composer → cad_builder → BOM
              ✅                              ✅                ❌
        78 tests, 1 xfail              62 tests, 3 xfail
```

**Locked down (936 tests as of 6bc49bb):**
- `oracle.py` (810 LOC) — 78 tests, R1-R8/R10/R18/R19 + historical regression
- `assembly_composer.py` (472 LOC) — 62 tests, placement + CoG + interference
- 156 tests already exist for `intake/frame/elevator/flywheel/climber/conveyor/arm` generators (test_b3 + test_b4_b9_generators)
- `bom_rollup`, `motor_model`, `oracle_pipeline`, `prediction_bridge` — already tested

**Untested hermetic files:**
- `plate_generator.py` (567 LOC) — pure logic, FeatureScript generation
- `turret_generator.py` (515 LOC) — pure logic, physics model

**Untested but Onshape-coupled (need gating like test_blueprint.TestOnShapeSmoke):**
- `cad_builder.py` (700 LOC) — large, mostly pure FeatureScript gen + small Onshape send
- `assembly_builder.py` (724 LOC) — Onshape assembly creation
- `part_resolver.py` (433 LOC) — Onshape COTS lookup
- `insert_cots.py` (533 LOC) — Onshape parts insertion
- `build_full_robot.py` (229 LOC) — orchestrator script

**Known bugs (currently xfail):**
1. **AABB over-conservatism in `assembly_composer._check_overlap`** — 3 xfails in `test_historical_no_mechanism_interference`. Intake AABB extends backward into the robot center because the bounding box assumes "intake = 14" piece + 4" structure deep in all directions". Real intakes only deploy forward.
2. **`oracle.predict_from_file` drops list fields** — 1 xfail in `test_predict_from_file_full_round_trip`. Uses `hasattr(GameRules, k)` which returns False for dataclass fields with `default_factory` (like `scoring_targets`).

---

## The 6 phases

Ordered by dependency. Bugs first (cleans up xfails), then test lock-in for the
two remaining hermetic generators, then integration. Each phase is a
standalone Sonnet session — Opus writes the full plan doc when you're ready
to execute.

### Phase 1 — Fix AABB over-conservatism in assembly_composer
**Type:** Bug fix + architectural improvement
**Target:** `blueprint/assembly_composer.py` (lines ~175–195 intake placement, ~392–402 `_check_overlap`)
**Removes:** 3 xfails (`test_historical_no_mechanism_interference[2022/2023/2024]`)
**Adds:** ~10 new tests for the deployed/stowed envelope model
**Time budget:** 60 min for Sonnet

**Why:** The previous session surfaced a real geometry bug. The interference
detector flags the 3 historical shipping designs as overlapping because the
intake AABB assumes a single bounding box that extends backward into the
robot center. Real intakes only deploy forward — when stowed, they're flush
with the bumper. This is wrong now, and it'll silently fail kickoff 2027 if
left unfixed.

**Architecture move:** Add a `stowed_envelope_in` field to `MechanismPlacement`
alongside the existing `envelope_in` (which becomes "deployed"). Update
`_check_overlap` to use `stowed_envelope_in` for interference detection
(stowed is what matters when other mechanisms are running). Keep the deployed
envelope for clearance/range-of-motion analysis.

**Scope:**
- Add `stowed_envelope_in` and `stowed_envelope_mm` fields to `MechanismPlacement`
- For the intake block in `compose_robot`, compute a smaller stowed envelope
  (no piece-diameter expansion in -Y, smaller depth)
- Update `_check_overlap` to use stowed envelopes
- Update existing tests that check `envelope_in` to also verify `stowed_envelope_in`
- Remove the 3 xfails and verify all 3 historical specs now pass with zero
  interference warnings
- Add new tests: stowed vs deployed envelope shapes, stowed-stowed overlap,
  deployed envelope still tracked for range analysis

**Out of scope:** Other mechanism types (climber telescoping, arm sweeping)
get the same treatment in a follow-up. Focus on intake first because that's
what's causing the xfails.

**Success criteria:**
- All 3 `test_historical_no_mechanism_interference` xfails removed and passing
- `pytest tests/` reports 936 → ~946+, 0 warnings, only 1 xfail remaining (the oracle one)

---

### Phase 2 — Fix oracle.predict_from_file + GameRules I/O hardening
**Type:** Bug fix + architectural improvement
**Target:** `blueprint/oracle.py` (lines ~32–82 `GameRules`, ~704–709 `predict_from_file`)
**Removes:** 1 xfail (`test_predict_from_file_full_round_trip`)
**Adds:** ~15 new tests for `from_dict` / `to_dict` / round-trip
**Time budget:** 45-60 min for Sonnet

**Why:** Real serialization bug surfaced by the oracle session. Any field with
`default_factory` (most importantly `scoring_targets`) gets silently dropped
on JSON load, so kickoff workflows that author GameRules in JSON will produce
wrong predictions with no error. This is the contract between the kickoff
template and the prediction engine.

**Architecture move:** Add `GameRules.from_dict(cls, data: dict)` and
`GameRules.to_dict(self) -> dict` classmethods that use `dataclasses.fields()`
instead of `hasattr`. `predict_from_file` calls `from_dict` instead of the
current janky filter. Optionally add a `from_json_file(cls, path)` constructor.

**Scope:**
- Add `GameRules.from_dict(cls, data)` using `dataclasses.fields(cls)` to
  enumerate fields explicitly
- Add `GameRules.to_dict(self)` (can wrap `dataclasses.asdict`)
- Update `predict_from_file` to use `GameRules.from_dict`
- Remove the `hasattr` filter (or replace with dataclass introspection)
- Add validation: warn (don't crash) on unknown keys, raise on missing
  required fields with clear messages
- Tests: full round-trip for all 4 HISTORICAL_GAMES, missing-field handling,
  unknown-key handling, type-coercion behavior (int vs float)
- Remove the xfail from `test_predict_from_file_full_round_trip`

**Out of scope:**
- JSON schema generation (separate session if it becomes needed)
- Pydantic migration (overkill for a 30-line dataclass)
- Validating value ranges (R5 height bands, etc.)

**Success criteria:**
- The xfail is removed and passing
- All 4 HISTORICAL_GAMES round-trip cleanly through JSON
- `pytest tests/` reports ~946 → ~961+, 0 warnings, 0 xfails (assuming Phase 1 done)

---

### Phase 3 — Lock down plate_generator.py
**Type:** Test lock-in (proven oracle/assembly_composer pattern)
**Target:** `blueprint/plate_generator.py` (567 LOC)
**Adds:** ~50 tests in `tests/blueprint/test_plate_generator.py`
**Time budget:** 60 min for Sonnet

**Why:** Custom aluminum plates are the most-manufactured parts on the robot
(2-3 per mechanism). Their bolt-hole positions, lightening pockets, and
edge clearances all come out of `plate_generator.py`. A geometry bug here
means every laser-cut plate needs rework — exactly the kind of regression
that off-season test investment prevents.

**Scope:**
- Survey: read `plate_generator.py` end-to-end to find the public surface
  (`generate_mechanism_plates(spec)` is the documented entry point per the
  module docstring)
- Build minimal mechanism spec fixtures (bolt patterns, plate dimensions)
- Tests for each plate type generated (mounting plate, side plate, gusset, etc.)
- Tests for bolt hole positioning math
- Tests for lightening pocket placement (if implemented)
- Tests for the FeatureScript output structure (string contains expected
  feature names — don't try to execute the FS, just verify output shape)
- Historical regression: feed in real mechanism specs from
  `blueprint/2022_*.json` and `blueprint/2023_*.json` and assert plate
  generation doesn't crash

**Out of scope:**
- Executing FeatureScript against Onshape (network)
- Validating that generated plates manufacture correctly (physical world)
- Modifying `plate_generator.py` (xfail any bugs found, fix in separate session)

**Success criteria:**
- ~50 new tests, all pass
- `pytest tests/` reports ~961 → ~1011+, 0 warnings
- Same pattern as `test_oracle.py` and `test_assembly_composer.py`

---

### Phase 4 — Lock down turret_generator.py
**Type:** Test lock-in (proven pattern)
**Target:** `blueprint/turret_generator.py` (515 LOC)
**Adds:** ~40 tests in `tests/blueprint/test_turret_generator.py`
**Time budget:** 60 min for Sonnet

**Why:** Turrets are the highest-leverage mechanism for ranged-distributed
games (per oracle R6). The 254/1678/2056 architectures encoded in this file
are the team's best shot at a championship-grade turret in 2027. Physics
math (motor torque vs payload inertia, Euler-integrated slew time) needs
regression tests so future tweaks don't silently break the simulation.

**Scope:**
- Survey: read `turret_generator.py` end-to-end. Look for `generate(...)`,
  `presets`, `simulate_slew`, and any motion-profile functions.
- Tests for preset loading: every documented preset (e.g. `shooter_turret`)
  must produce a valid spec dict
- Tests for the physics simulation: feed known inputs (motor type, payload
  weight, target angle), assert slew time is in a sensible range (don't
  pin to exact values — physics simulations drift; pin to ranges)
- Tests for motor selection logic: under-powered config produces warning,
  over-powered produces sensible torque margin
- Tests for the turret spec output schema (required fields present)
- Edge cases: zero payload, infinite payload, zero target angle

**Out of scope:**
- Modifying `turret_generator.py` (xfail bugs, fix separately)
- Onshape integration (turret cad goes through `cad_builder.py`)

**Success criteria:**
- ~40 new tests, all pass
- `pytest tests/` reports ~1011 → ~1051+, 0 warnings

---

### Phase 5 — Hermetic test suite for cad_builder.py
**Type:** Test lock-in with network gating (test_blueprint pattern)
**Target:** `blueprint/cad_builder.py` (700 LOC)
**Adds:** ~30-40 tests in `tests/blueprint/test_cad_builder.py`
**Time budget:** 60-75 min for Sonnet (slightly larger due to network gating)

**Why:** `cad_builder.py` is the link between mechanism specs and physical
3D geometry in Onshape. It's mostly pure-logic FeatureScript generation
with a small slice that pushes to the Onshape API. The pure-logic slice
is large and untested. Bugs here mean every kickoff CAD push produces
wrong geometry — no second line of defense before students start
prototyping.

**Architecture move:** Separate the FeatureScript-generating functions
(pure logic, hermetic) from the API-pushing functions (network). Test
the former directly; gate the latter behind `@unittest.skipUnless` like
`test_blueprint.TestOnShapeSmoke`.

**Scope:**
- Survey: read `cad_builder.py` and identify each `build_*` function
  (`build_frame`, `build_intake`, `build_flywheel`, etc.)
- For each, test that it returns a non-empty FeatureScript string
- Test that the FeatureScript references the expected feature names
  (`opExtrude`, `opBoolean`, etc.)
- Test that swapping spec fields (e.g. frame_width 27 → 30) changes
  the FeatureScript output
- Historical regression: feed full_blueprint.json files from
  `blueprint/2022_*` etc. and assert each `build_*` doesn't crash
- Gate any actual Onshape API calls behind `@pytest.mark.skipif(not
  os.getenv("ONSHAPE_ACCESS_KEY"))`
- Don't try to validate FeatureScript syntactically — that requires Onshape

**Out of scope:**
- Modifying `cad_builder.py` (xfail bugs, fix separately)
- Testing `assembly_builder.py`, `part_resolver.py`, `insert_cots.py`
  (each is a separate Onshape-coupled session)

**Success criteria:**
- ~30-40 new tests, all pass without ONSHAPE_ACCESS_KEY set
- Network-gated tests (if any) skip cleanly when key absent
- `pytest tests/` reports ~1051 → ~1081+, 0 warnings

---

### Phase 6 — End-to-end pipeline integration test
**Type:** Cross-subsystem integration test (architecture validation)
**Target:** New file `tests/blueprint/test_pipeline_e2e.py`
**Adds:** ~15-20 tests covering the full chain
**Time budget:** 60 min for Sonnet

**Why:** Phases 1-5 lock down each subsystem in isolation. None of them
verify that the chain `GameRules → oracle → prediction_bridge →
mechanism specs → assembly_composer → CAD specs` actually composes
end-to-end. This is the kickoff-day workflow — if any link breaks the
contract with the next, the team finds out at 11am on the morning of
kickoff.

**Architecture move:** Use `oracle.HISTORICAL_GAMES` as the input set
(4 known-good games), run the full pipeline, and assert each stage's
output validates as input for the next. This becomes a regression
test for any architectural change anywhere in the pipeline.

**Scope:**
- For each of the 4 HISTORICAL_GAMES, run:
  ```python
  game = oracle.HISTORICAL_GAMES["2024"]
  prediction = oracle.apply_rules(game)
  oracle_output = prediction_bridge.parse_oracle_output(prediction)
  # ... feed into per-mechanism generators if needed
  spec = build_full_blueprint_spec(oracle_output)  # may need a helper
  layout = assembly_composer.compose_robot(spec)
  ```
  And assert at each stage:
  - Output is non-empty
  - Output has required keys for the next stage
  - No exceptions
- Pin specific known-good values from the historical pipeline JSONs:
  - 2024 Crescendo prediction → flywheel scorer (R4)
  - 2024 layout → climber at back (-Y)
  - etc.
- Diff the live pipeline output against the on-disk
  `2024_crescendo_pipeline.json` to detect drift (with a "drift threshold"
  — minor numerical changes are OK, structural changes are not)
- Add a "smoke" test that runs `oracle_pipeline.run_pipeline` end-to-end
  if a fixture mode exists (no Onshape, dry-run only)

**Out of scope:**
- Onshape API calls (smoke-only, gated)
- Modifying any source files (read-only test layer)
- Adding new pipeline stages — this is regression-locking, not feature work

**Success criteria:**
- ~15-20 new tests, all pass
- The chain `oracle → bridge → compose_robot` works for all 4 historical games
- `pytest tests/` reports ~1081 → ~1101+, 0 warnings
- A baseline diff exists for each historical game so future drift is detectable

---

## Summary table

| # | Phase | Type | Target | Tests | Time | Removes xfails |
|---|-------|------|--------|-------|------|----------------|
| 1 | Fix AABB bug | Bug + arch | assembly_composer.py | +10 | 60 min | 3 |
| 2 | Fix predict_from_file | Bug + arch | oracle.py | +15 | 45-60 min | 1 |
| 3 | plate_generator | Test lock-in | plate_generator.py | +50 | 60 min | 0 |
| 4 | turret_generator | Test lock-in | turret_generator.py | +40 | 60 min | 0 |
| 5 | cad_builder | Test lock-in (gated) | cad_builder.py | +35 | 60-75 min | 0 |
| 6 | E2E pipeline | Integration | new test_pipeline_e2e.py | +18 | 60 min | 0 |

**Total budget:** ~6 hours of Sonnet sessions (likely ~3 actual hours given recalibration)
**Total tests added:** ~168 (936 → ~1104)
**Bugs fixed:** 2 (both xfails removed)
**End state:** Full blueprint pipeline tested end-to-end, zero xfails, ready for 2027 kickoff

---

## Sequencing notes

- **Phases 1 and 2 are independent.** Either can come first. Phase 1 has
  more xfails to clean up, Phase 2 is smaller. Sonnet's call.
- **Phases 3 and 4 are independent of each other** but both should come
  after Phases 1-2 so the test count base is clean.
- **Phase 5 should come after Phases 3-4** because cad_builder consumes
  the same mechanism specs that plate/turret produce — testing those first
  gives us confidence in the input shapes.
- **Phase 6 should come last.** It validates the chain end-to-end and
  benefits from every previous phase being stable.

## What this leaves unfinished

After all 6 phases, the blueprint subsystem is essentially feature-complete
and regression-locked. Remaining gaps:

- **Onshape-coupled files** (`assembly_builder`, `part_resolver`,
  `insert_cots`, `build_full_robot`) — need either Onshape mocks or a
  hermetic FeatureScript-only test layer. Separate decision.
- **Adding new HISTORICAL_GAMES entries** (e.g. 2026 REBUILT) — needs
  ground truth research, separate task.
- **Implementing oracle rules R9, R11, R12, R13, R14, R15, R16, R17** —
  documented in `CROSS_SEASON_PATTERNS.md` but not in `oracle.py`. Each
  rule is its own design decision.
- **Eye + scout subsystems** — not blueprint scope, but
  `eye/eye_bridge.py` is the next biggest untested file outside blueprint.

When Phase 6 lands, the natural next conversation is "blueprint is locked,
where next?" — at that point the eye/scout/antenna subsystems are the
remaining frontier.

---

## When ready to execute

Tell Sonnet which phase to run. Opus will write the full PLAN doc for that
specific phase (modeled on `PLAN_ORACLE_TEST_SUITE.md` /
`PLAN_ASSEMBLY_COMPOSER_TEST_SUITE.md`), then Sonnet executes.

Default order: 1 → 2 → 3 → 4 → 5 → 6.
