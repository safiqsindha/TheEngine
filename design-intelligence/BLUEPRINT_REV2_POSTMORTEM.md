# Blueprint Rev-2 Postmortem
## Date: 2026-04-13 | Author: Engine audit session
## Status: DEAD — reframe as design analysis / BOM estimator only

---

## What We Tried

### The original plan (before Rev-2)
Blueprint started as a parametric CAD generator: feed a game's scoring rules into
`oracle.py`, get a FeatureScript assembly out the other end. We built 12,713 LOC
of Python across `oracle.py`, `cad_builder.py`, `assembly_builder.py`,
`frame_generator.py`, `elevator_generator.py`, `intake_generator.py`,
`flywheel_generator.py`, `arm_generator.py`, `climber_generator.py`,
`conveyor_generator.py`, `plate_generator.py`, and `turret_generator.py`.

The generators emitted FeatureScript text strings. `cad_builder.py` and
`assembly_builder.py` submitted those strings to Onshape via `onshape-client`.
`part_resolver.py` looked up hardcoded COTS part IDs. `bom_rollup.py` aggregated
the result.

### The Rev-2 MCP pivot (2026-04-12 → 2026-04-13)
Landscape scan surfaced `hedless/onshape-mcp` (49 stars, 45 tools, subprocess-free,
designed for Claude Code). Saturday hypothesis: instead of emitting FeatureScript
text, call MCP tools directly. The "copy FRCDesign reference doc + parametrize via
Variable Studio" architecture was proposed as the core flow.

Smoke test (A2) refuted the Variable Studio hypothesis immediately: 2/2 sampled
FRCDesign docs have empty Variable Studios. Mates are hardcoded, not parametric.

Pivot adjusted to: "emit geometry primitives via MCP calls instead of FeatureScript
strings, use FRCDesignLib parts as instances." Two new generator files were written:
`generators/elevator_rev2.py` (1,005 LOC) and `generators/swerve_rev2.py` (900 LOC).
Two COTS files: `cots_parts/elevator_parts.py` (272 LOC) and `swerve_parts.py` (202 LOC).
`build_full_robot.py` (171 LOC) and `demo_full_pipeline.py` (524 LOC) were written
or rewritten as orchestrators.

### What was built across all phases
- **Phase 0 (architecture decision):** `BLUEPRINT_REV2_DECISION.md` — correct analysis,
  sound verdict. ~0 LOC produced.
- **Phase 1 (onshape-mcp install + smoke test):** `BLUEPRINT_MCP_SMOKE_TEST.md` —
  tools work, Variable Studio hypothesis refuted. `~/onshape-mcp/` installed.
  `.mcp.json` configured.
- **Phase 2 (first generators):** `elevator_rev2.py`, `swerve_rev2.py`,
  `elevator_parts.py`, `swerve_parts.py` — 2,379 LOC of MCP-call generators.
  2 test suites: `test_elevator_rev2_hermetic.py` (260 LOC), `test_swerve_rev2_hermetic.py`
  (302 LOC), `test_elevator_rev2_gated.py` (122 LOC), `test_swerve_rev2_gated.py`
  (110 LOC). Plus `test_b3_generators.py` (646 LOC) and `test_b4_b9_generators.py`
  (516 LOC) for the full generator family — 1,956 LOC total of generator test code.
- **Live run (B-MCP.4):** `BLUEPRINT_REV2_DEMO_REPORT.md` — the 57-call live run
  that triggered this postmortem.

---

## What We Got

The live run produced: **9 rectangular tubes + 4 mates** in a real Onshape document.

Specifically:
- 6 swerve frame rails (all identical 27" 2×1 extrusions, no gussets, no corner
  plates, no bellypan cutout, no module pockets)
- 2 elevator stage rails (28" 2×1 extrusions)
- 1 elevator carriage plate (10×8×0.25" solid block)
- 2 fastened mates between cross-members and long rails
- 1 fastened mate attaching elevator to swerve frame
- 1 slider mate for the carriage

That is the entire output. Viewing the document confirms: no swerve module instances
(SDS MK4i, REV Max Swerve), no bumper mounts, no bellypan, no gussets, no
electronics mounting, no battery tray, no COTS hardware of any kind, no
game-specific mechanism beyond a floating elevator carriage with a slider DOF.

The report called this "production-ready for Rev-2." It is not production-ready.
It is a stick-figure robot with 9 primitives.

The 57-call live run took 4–5 wall-clock minutes. A robot with hundreds of real
features would take hours at this call rate. The `instance_id="unknown"` MCP bug
required a 9-call workaround just for the 9 instances — that workaround scales
linearly with part count.

---

## Why It Failed

### The diagnosis in one sentence
We solved geometry emission (~15% of the actual CAD problem) and spent 100% of
Blueprint's April budget on it, because it was the visible, tractable, shippable
layer.

### The layers we did not touch
**Layer 1: COTS insertion.** A real swerve frame needs 4 SDS MK4i or REV Max Swerve
modules. Each module is a multi-body subassembly with mate connectors and document
references. `FRCDesignLib` resolves these from Firestore, but the resolver
(`part_resolver.py`, 441 LOC) is a hardcoded-ID stub. The MCP `add_assembly_instance`
call requires a `document_id`, `element_id`, and `part_id` for every COTS part.
We have none of those for the module catalog. FRCDesignLib integration was labeled
"deferred to Phase 3" in the live run report. Phase 3 never happened.

**Layer 2: Real mates.** A real swerve frame has 30–50 fastened mates just for the
frame structure (gussets, corner plates, cross-members, bellypan studs). Our 2
fastened mates don't make the frame rigid — the two side rails are connected but
the 4 long rails are floating in space, positioned only by `transform_instance`
coordinate offsets. There is no structural closure.

**Layer 3: Feature count vs. API latency.** The `instance_id="unknown"` bug requires
a `get_assembly_positions` round-trip after every `add_assembly_instance` call.
At 9 instances that added 9 extra API calls. A complete single-mechanism assembly
in FRCDesign has 50–200+ instances. At 57 calls for 9 instances, a real assembly
would require 300–1,000+ calls and 30–100+ minutes of wall time. The MCP approach
does not scale to production robot assemblies without batching via `eval_featurescript` —
which is back to hand-rolled FeatureScript, the thing the pivot was meant to escape.

**Layer 4: What a student can build from.** The output students need is: correct
tube lengths, correct hole patterns for gussets and modules, a bellypan with
cutouts for wheel pockets and electronics, and a BOM they can click-order on
WCP/REV/AM. None of those exist. The assembly has no hole features, no gussets,
no bellypan geometry. It cannot be handed to a student as a build reference.

### The architectural trap
The MCP pivot solved the right problem at the wrong layer. FeatureScript
emission via string concatenation was genuinely bad — brittle, untestable, prone
to syntax errors. MCP calls are better primitives. But the insight "use better
primitives" does not get us to "produce CAD a student can build from." The gap
between those two things is:
- FRCDesignLib COTS resolver (Firestore-backed part catalog, hundreds of entries)
- Structural mates (30–50 per mechanism, not 4)
- Gussets and hardware (dozens of instances per mechanism)
- Electronics layout (bellypan, PDH, RIO, pneumatics if any)
- Hole patterns for rivet/bolt connections

None of those were in Phase 1 or Phase 2. All of them were "Phase 3+."

The decision doc (`BLUEPRINT_REV2_DECISION.md`) named the right modules to cut
and keep. What it underestimated was the total surface area of the remaining
problem: even after the MCP pivot, the gap between "9 primitives" and "build-ready
assembly" is 200–400 additional hours of work (not 7–30h as April budget implied).

---

## What We Keep — The Honest Salvage

These modules survive and have clear off-season value as-is:

| Module | LOC | Tests | Why Keep |
|--------|-----|-------|----------|
| `oracle.py` | 823 | 78 | 18-rule prediction engine, 98% accuracy across 14 games. Game-agnostic. Runs in <1s. Real kickoff day value. |
| `motor_model.py` | 366 | ~12 (via oracle suite) | Physics: gear ratios, free speed, stall torque, current draw. No Onshape dependency. Input to sizing decisions. |
| `bom_rollup.py` | 534 | ~8 | Aggregates BOM from any generator output. Format-stable. Useful for a manual BOM estimator. |
| `plate_generator.py` (physics layer only) | ~150 of 518 | 0 | Plate thickness → load calculation is correct physics. Delete the FeatureScript emission half. |
| `turret_generator.py` (physics layer only) | ~100 of 389 | 0 | Turret inertia, gear ratio, speed math. Same: keep physics, delete geometry emission. |
| `oracle_pipeline.py` | 426 | ~0 | Wires oracle to downstream. Small and correct. |
| `prediction_bridge.py` | 544 | ~0 | Upstream of CAD. Geometry-agnostic. |
| `CROSS_SEASON_PATTERNS.md` | — | — | The brain. 18 rules + 12 meta-rules. Validated. |

**Reframing Blueprint:** Blueprint is a *design analysis and BOM estimation tool*,
not a CAD generator. Oracle analyzes the game and recommends mechanism types. Motor
model sizes the drivetrain and scoring mechanism motors. BOM rollup produces a parts
list. Students take that output and CAD by hand in Onshape, which is where they
actually learn mechanical design. The Engine assists the thinking; it does not
replace the drafting.

This framing is more honest and more useful than "generate a robot in 4 minutes."

---

## What We Cut

Do not delete yet. This is the approved cut list pending operator sign-off.

### Code to delete

| File | LOC | Reason |
|------|-----|--------|
| `blueprint/generators/elevator_rev2.py` | 1,005 | Produces unfixable primitive output. 1,000 LOC to make 3 tubes. |
| `blueprint/generators/swerve_rev2.py` | 900 | Same. 6 tubes, no modules, no gussets. |
| `blueprint/cots_parts/elevator_parts.py` | 272 | COTS IDs for a generator that's being deleted. |
| `blueprint/cots_parts/swerve_parts.py` | 202 | Same. |
| `blueprint/build_full_robot.py` | 171 | Orchestrator for deleted generators. |
| `blueprint/demo_full_pipeline.py` | 524 | Demo script for a pipeline that doesn't produce usable CAD. |
| `blueprint/cad_builder.py` | ~700 (est from audit) | FeatureScript string concatenation. Superseded. |
| `blueprint/assembly_builder.py` | ~724 (est from audit) | Hand-rolled assembly creation. Superseded. |
| `blueprint/part_resolver.py` | 441 | Hardcoded part IDs. Was to be replaced; replacement never built. |
| `blueprint/fix_featurescript.py` | est ~100 | FeatureScript post-processing. Moot. |
| `blueprint/apply_feature.py` | est ~80 | FeatureScript application. Moot. |
| **Subtotal (src)** | **~5,119** | |

### Tests to delete

| File | LOC | Reason |
|------|-----|--------|
| `tests/blueprint/test_elevator_rev2_gated.py` | 122 | Tests deleted generator. |
| `tests/blueprint/test_elevator_rev2_hermetic.py` | 260 | Same. |
| `tests/blueprint/test_swerve_rev2_gated.py` | 110 | Same. |
| `tests/blueprint/test_swerve_rev2_hermetic.py` | 302 | Same. |
| `tests/blueprint/test_b3_generators.py` | 646 | Tests legacy generators (arm, climber, conveyor, elevator, flywheel, frame, intake) that were never wired to MCP. All dead-weight. |
| `tests/blueprint/test_b4_b9_generators.py` | 516 | Same family. |
| **Subtotal (tests)** | **~1,956** | |

### External infrastructure to remove

| Item | Why |
|------|-----|
| `~/onshape-mcp/` install | Only needed if we're running MCP-driven CAD generation, which we're cutting. |
| `.mcp.json` onshape server config | Same reason. If no CAD generation, no MCP server needed. |

### Legacy generator files (audit separately)
The legacy generators (`arm_generator.py`, `climber_generator.py`, `conveyor_generator.py`,
`elevator_generator.py`, `flywheel_generator.py`, `frame_generator.py`,
`intake_generator.py` — ~4,897 LOC combined) were never part of the MCP pivot.
They were never cleaned up post-pivot. They have 0 tests and emit FeatureScript.
Recommend archive or delete in a separate pass after this cut.

### JSON artifact files to clean up
`blueprint/` contains ~30 JSON and FS artifact files (oracle outputs, BOM CSVs,
FeatureScript files, assembly manifests). These can be archived to `blueprint/_artifacts/`
rather than deleted — they are historical record of pipeline runs, not active code.

---

## LOC Delta Estimate

| Category | Before | After cut | Deleted |
|----------|--------|-----------|---------|
| Blueprint src (Python) | 12,713 | ~7,594* | **~5,119** |
| Blueprint tests | 3,680 | ~1,724** | **~1,956** |
| **Total** | **~16,393** | **~9,318** | **~7,075** |

*Retains: oracle, motor_model, bom_rollup, plate_generator, turret_generator,
assembly_composer (shrunk), oracle_pipeline, prediction_bridge, onshape_api.
**Retains: test_oracle.py (674), test_blueprint.py (660), test_assembly_composer.py (390).

The estimate of "~1,500 LOC deleted" in the original scope was too low.
Actual conservative estimate is **~7,000 LOC deleted** across src + tests.
This does not include the legacy generator files (another ~5,000 LOC), which
are a separate decision.

---

## What This Recovers

**Time budget:**
- ~30h of April model budget already spent on Blueprint MCP pivot is sunk cost.
- Cutting Blueprint CAD generation now recovers the remaining April + all of
  May-June Blueprint budget (originally ~88h across B.3-B.7 phases).
- Stopping here prevents ~200–400h of downstream work that would have been needed
  to reach "build-ready assembly" output.

**Attention budget:**
- Removes ~12 open architecture questions from active working memory
  (FRCDesignLib integration, MCP call batching, gusset catalog, bellypan layout,
  COTS resolver, mate connector authoring, etc.)
- Removes the need to track `~/onshape-mcp/` updates and API breaking changes.
- Removes the MCP server as a required dependency at competition.

**What those hours free up (priority order):**
1. Scout intelligence (1678 algorithm ports, SPR, NormalDist, defense-adjusted EPA)
2. Eye E.1 (offseason batch video pipeline — Roboflow supervision reduces this to
   ~17h from ~30h)
3. Oracle Phase 1 (data foundation: EPA uncertainty bands, component EPA, confidence)
4. Cockpit D.1–D.3 (Elastic Dashboard fork — ~20h, mostly config)
5. Vault V.1 (Binner adoption — ~5h to configure, not build)

---

## Lessons

**1. Geometry emission was ~15% of the actual CAD problem.** We spent 100% of
Blueprint's budget there because it was visible, measurable, and tractable. Every
week produced a green test count and a passing pipeline call. "Pipeline runs
end-to-end" is not the same as "output is useful."

**2. The definition of done was never stated in buildable terms.** If we had written
"a student can order parts from the BOM and build this robot" as the acceptance
criterion on day one, we would have caught the COTS-resolver and gusset gaps
in Phase 0, not Phase 4.

**3. Pivots that solve the wrong layer look like progress.** The MCP pivot replaced
FeatureScript string concatenation with MCP tool calls. Both produce the same
output: 9 primitives. The pivot was architecturally correct but strategically
irrelevant if the output was never going to be build-ready.

**4. Test counts are not a signal of shipping.** 1,011 tests passing. Blueprint
produced 9 tubes. The oracle and scout suites are real value. The generator test
suites (1,956 LOC of hermetic + gated tests) were testing geometry math that
serves no one.

**5. Off-season is not the time to build a CAD generator solo.** A production
FRC CAD pipeline (reference: 971's open-alliance work, FRCDesignLib) requires
a team of mechanical engineers with Onshape expertise iterating over months.
A solo software mentor building this at night after work cannot close that gap
before January 2027 kickoff. Students CAD by hand — that is where they learn
mechanism design. The Engine should feed them better data and analysis, not
try to replace the drafting.

---

*Postmortem complete. No files deleted. Awaiting operator approval of cut plan.*
*Companion doc: `ENGINE_AUDIT_2026-04-13.md` — full system audit and refocused roadmap.*
