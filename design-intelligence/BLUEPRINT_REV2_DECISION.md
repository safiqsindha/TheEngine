# Blueprint Rev-2 Architecture Decision — 2026-04-13

**Tier A3 output.** One-page verdict on the MCP pivot, with fate of every existing Blueprint module specified.

**Inputs:** `BLUEPRINT_MCP_SMOKE_TEST.md` (A2 output, elevator + shooter both have no Variable Studios), `BLUEPRINT_NEXT_6_PHASES.md` (pre-pivot plan).

---

## The verdict

**Pivot to MCP — but NOT to the "copy + parametrize via Variable Studio" flow originally sketched on Saturday.**

Saturday's hypothesis assumed FRCDesign reference docs expose named parametric variables (`stage_count`, `extension_in`, etc.). The smoke test refuted this: 2 of 2 FRCDesign docs sampled have empty Variable Studios. The elevator's 134 assembly features are hardcoded mates with 2 Slider DOFs — assembly-parametric, not geometry-parametric.

So the pivot is not `copy doc → set variables → fetch back`. The pivot is:

> **Blueprint becomes a mate-connector + COTS-instance composer driven by onshape-mcp, using FRCDesign parts as inserted instances and our own parametric logic to decide positions and configurations.**

The 45-tool MCP stays central. What changes is what we copy.

---

## Fate of every existing Blueprint module

Read this left-to-right: one line per file, one verb, one reason.

| Module | Fate | Reason |
|---|---|---|
| `oracle.py` (810 LOC, 78 tests) | **KEEP UNCHANGED** | Operates on rules → spec. Geometry-agnostic. 944 tests safe. |
| `bom_rollup.py` | **KEEP UNCHANGED** | Rolls up BOM from whatever generator produces. Output format stable. |
| `motor_model.py` | **KEEP UNCHANGED** | Physics. No Onshape dependency. |
| `oracle_pipeline.py` / `prediction_bridge.py` | **KEEP UNCHANGED** | Upstream of CAD. |
| `assembly_composer.py` (472 LOC, 62 tests) | **SHRINK** | Keep CoG + mass rollup; delete AABB overlap checking (replaced by `check_assembly_interference` MCP tool). Drop 3 AABB xfails by deleting the buggy code, not fixing it. |
| `plate_generator.py` (567 LOC, 0 tests) | **SHRINK** | Keep sizing/load physics (plate thickness given load). Delete FeatureScript generation — replaced by `create_extrude` + `create_fillet` MCP calls. |
| `turret_generator.py` (515 LOC, 0 tests) | **SHRINK** | Keep physics model (turret inertia, gear ratio, speed). Delete geometry emission — replaced by MCP feature composition. |
| `cad_builder.py` (700 LOC, 0 tests) | **DELETE** | 85% is FeatureScript string concatenation. Every one of those primitives has a 1-to-1 MCP tool replacement. Hand-rolled FeatureScript was the dead end. |
| `assembly_builder.py` (724 LOC, 0 tests) | **DELETE** | Hand-rolled assembly creation via `onshape-client`. Full replacement: MCP `create_assembly` + `add_assembly_instance` + `create_fastened_mate` et al. |
| `part_resolver.py` (433 LOC, 0 tests) | **REPLACE** | Hardcoded part IDs. Rewrite against FRCDesignLib Firestore-seeded catalog (the vendor data work from 2026-04-12 scan). Much smaller module. |
| `insert_cots.py` (533 LOC, 0 tests) | **DELETE** | Replaced by MCP `add_assembly_instance` directly. |
| `build_full_robot.py` (229 LOC) | **REWRITE** | Orchestrator was wired to `cad_builder` + `assembly_builder`. New orchestrator drives MCP tools + shrunken generators. Stays small (~150 LOC). |
| `onshape_api.py` (blueprint local wrapper) | **KEEP FOR NOW** | Still used by `onshape_api_test.py` and a few direct calls. Fold into MCP gradually; deprecate over Q3. |
| `cots_parts/` (19 working part files) | **MIGRATE** | Re-key to new FRCDesignLib-backed resolver. Content is fine, indexing changes. |

**Net change:** ~3,000 LOC of hand-rolled CAD generation deleted or shrunken. Oracle + physics + BOM untouched (~1,500 LOC + 940 tests survive).

---

## Why shrink physics rather than delete

MCP gives us geometry primitives, not physics. It can extrude a plate to thickness X, but it can't tell us X=0.125in is correct for 40-lb carriage load at 8in span. That math lives in `plate_generator.py` and `turret_generator.py` and has to survive. What dies is the FeatureScript emission layer that turned the physics answer into text — MCP `create_extrude` takes the answer as a direct argument.

## Why the new work is tractable

The 6-phase plan in `BLUEPRINT_NEXT_6_PHASES.md` assumed we had to build:
- Hermetic test suite for `cad_builder.py` (Phase 5)
- Full Onshape gating for `assembly_builder.py` (Phase 4)
- `part_resolver` correctness harness (Phase 3)
- AABB bug fix (Phase 1)

All four items disappear under this decision:
- No `cad_builder.py` to test — it's deleted
- No hand-rolled `assembly_builder.py` to gate — MCP is the assembly layer
- No custom `part_resolver` surface — thin FRCDesignLib wrapper, ~50 LOC test
- No AABB bug to fix — code is deleted, MCP does interference checks

Phase 1-5 of the old plan collapse into **Phase 0: delete + shrink** (~1 Sonnet session) and **Phase 1: prove the new flow on one mechanism** (B-MCP.2 below).

## What we do NOT try to do

- **No Variable Studio authoring.** Smoke test showed FRCDesign doesn't use them. We won't either — complexity without payoff.
- **No copy-and-modify of FRCDesign docs as templates.** They're reference demonstrations, not templates. Inserting their parts into our own assemblies is the right primitive.
- **No port of `cad_builder` FeatureScript to MCP equivalents one-to-one.** We regenerate the geometry decisions from physics, not translate the old strings.

## The open risk

MCP feature composition is serial (one HTTP call per feature). A full robot has hundreds of features. If generation time blows past acceptable (say, > 60s for a full robot), we'll have to either batch via `eval_featurescript` (one big FS script composed locally, one MCP round-trip) or accept local FeatureScript generation for hot paths. Decide after B-MCP.2 measures actual latency.

---

## What this changes about April calendar

Original April plan (from `MONDAY_KICKOFF_2026-04-13.md`):
- B.1: API + COTS setup (6h) — partly done
- B.2: swerve frame generator (24h) — was going to use `cad_builder`

Revised:
- **Phase 0** (Sonnet, ~2h): Delete `cad_builder.py`, `assembly_builder.py`, `insert_cots.py`. Shrink `plate_generator`, `turret_generator`, `assembly_composer` per table above. Move deleted tests out. Land a single commit titled "Blueprint Rev-2: MCP pivot cuts."
- **Phase 1 / B-MCP.2** (Sonnet, ~3h): Rewrite cascade elevator generator on MCP. Oracle says "elevator"; generator picks stage count + extension from physics; MCP adds FRCDesignLib elevator parts + mates + slider DOF. End-to-end test.
- **Phase 2** (Sonnet, ~2h): Same pattern for swerve frame (replaces old B.2).

Total revised April model budget: ~7h. Replaces ~30h of the old plan. Remainder of weekly cap goes to Tier C items from the kickoff doc.

---

## Supersession

This doc **supersedes** `BLUEPRINT_NEXT_6_PHASES.md`. That plan is preserved for history but its Phase 1-5 are no longer the plan of record. New plan of record is the 3-phase sequence above.

Next doc: `BLUEPRINT_REV2_COPY_PARAMETRIZE.md` (B-MCP.1) — the concrete spec for Phase 1's elevator rewrite, with the MCP call sequence.
