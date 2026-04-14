# Blueprint Rev-2 Phase 1 — Cascade Elevator Generator (MCP Implementation Spec)
# B-MCP.2 | 2026-04-13 | Team 2950 The Devastators

**Tier B output.** Concrete implementation spec for Phase 1 of the MCP pivot.
Inputs: `BLUEPRINT_REV2_DECISION.md` (the verdict), `BLUEPRINT_MCP_SMOKE_TEST.md`
(FRCDesign elevator anatomy), `ELEVATOR_DESIGN_SPEC.md` (physics reference).

---

## 1. Scope

### What Phase 1 Delivers

A single new file — `blueprint/generators/elevator_rev2.py` — that runs the
complete oracle → physics → MCP pipeline for a cascade elevator and produces a
**real Onshape assembly document** verifiable at `cad.onshape.com`.

The end-to-end path:

```
oracle.py  →  ElevatorPhysics (physics layer)  →  elevator_rev2.py  →  onshape-mcp  →  Onshape doc URL
```

Inputs from oracle: elevator type, carriage load, target stroke, game-piece
mass, motor preference, rigging type.
Output: printed Onshape document URL + assembly element ID. The user opens it
and sees an assembly with elevator tube instances, a carriage instance, at least
one Slider mate, and bearing block instances.

Game scope: **2026 REBUILT** only. The oracle already produces a cascade
elevator spec for that game. No other game is wired in Phase 1.

Phase 1 also ships:

- `blueprint/cots_parts/elevator_parts.py` — part-ID mapping for elevator COTS,
  replacing hardcoded lookups scattered in `insert_cots.py`
- ~20 tests: 18 hermetic + 2 Onshape-gated (gated tests run only when
  `ONSHAPE_ACCESS_KEY` is set)
- Wiring of `build_full_robot.py` to call `elevator_rev2` instead of the old
  `elevator_generator.py` when scorer is `"elevator"`

### What Phase 1 Explicitly Does Not Deliver

- Swerve frame generation (that is Phase 2 / B-MCP.3)
- Multi-mechanism full-robot assembly composition
- Cascade linear mate relation (see Section 7 — documented limitation, accepted
  for Phase 1)
- Three-stage elevator support (oracle R5 caps at 2 stages anyway)
- Variable Studio authoring (smoke test confirmed FRCDesign doesn't use them;
  we won't either)
- Modifications to `oracle.py`, `motor_model.py`, `bom_rollup.py`, or
  `assembly_composer.py` — those survive untouched

### Success Criterion

The user runs:

```
python3 blueprint/generators/elevator_rev2.py --game 2026_rebuilt
```

and within 90 seconds receives a printed Onshape URL. Opening that URL shows a
2-stage elevator assembly with rail tube instances, carriage plate, bearing
blocks, motor, and gearbox. At minimum 2 Slider mates are present.
No FeatureScript was hand-written. No `cad_builder.py` was called.

---

## 2. Inputs

The physics layer receives a dict extracted from `oracle.py`'s `OracleOutput`.
The relevant fields, by oracle key path:

```
oracle_output["scorer"]["type"]               → must equal "elevator" to enter
oracle_output["scorer"]["elevator_stages"]    → int (1 or 2, from R5)
oracle_output["scorer"]["target_height_in"]   → float (primary target height)
oracle_output["scorer"]["game_piece_mass_lb"] → float (from GameRules)
oracle_output["scorer"]["motor_preference"]   → str ("kraken_x60" | "neo")
oracle_output["scorer"]["rigging"]            → str ("continuous" | "cascade")
oracle_output["weight_budget"]["scorer_lb"]   → float (weight allotted to scorer)
oracle_output["endgame"]["type"]              → str (if "climb", elevator may
                                                double as climb — not handled in P1)
```

All of these fields are already emitted by `oracle.py`'s current scorer block.
No oracle changes are required.

The carriage load (`carriage_load_lb`) is derived from:

```
game_piece_mass_lb + estimated_end_effector_lb
```

where `estimated_end_effector_lb` defaults to 5.0 for Phase 1 (wrist + claw
placeholder). This default is a named constant in `elevator_rev2.py`, not a
magic number.

---

## 3. Physics Decisions

The physics layer runs before any MCP call and outputs a fully-resolved
`ElevatorPhysicsResult` dataclass. MCP calls consume this result directly —
no physics happens during or after the MCP sequence.

**Inputs to physics layer:**

| Field | Type | Source |
|---|---|---|
| `target_stroke_in` | float | oracle `target_height_in` |
| `carriage_load_lb` | float | derived (Section 2) |
| `game_piece_mass_lb` | float | oracle |
| `motor_pref` | str | oracle |
| `rigging` | str | oracle |
| `weight_budget_lb` | float | oracle |

**Outputs (ElevatorPhysicsResult fields):**

| Decision | Field | How Decided |
|---|---|---|
| Stage count | `stage_count` | R5 from oracle already set 1 or 2; physics confirms |
| Tube length per stage | `tube_length_in` | `stroke / 2 + bearing_block_height_in` |
| Tube cross-section | `tube_spec` | "2x1x0.0625" always (ELEVATOR_DESIGN_SPEC standard) |
| Carriage plate thickness | `carriage_plate_thickness_in` | `0.125` if load < 8 lb, `0.25` if >= 8 lb |
| Motor count | `motor_count` | 2 (always, per ELEVATOR_DESIGN_SPEC) |
| Motor type | `motor_type` | from `motor_pref` oracle field |
| Gear ratio | `gear_ratio` | light (<5 lb) → 5:1, medium (5–10 lb) → 7:1, heavy (>10 lb) → 10:1 |
| Belt/cable type | `belt_spec` | "9mm HTD3" always (ELEVATOR_DESIGN_SPEC standard) |
| Drive pulley | `pulley_teeth` | 18T HTD3 |
| Spring force | `spring_force_lb` | `carriage_load_lb` rounded to nearest WCP stock rating |
| Stage tube IDs | `stage_part_keys` | list of keys into `elevator_parts.py` |

**Physics equations:** see `ELEVATOR_DESIGN_SPEC.md`, sections "Drive System",
"Motors & Gearbox", and "Configurable Parameters." The physics layer does not
re-implement; it applies the lookup tables and formulas already documented
there. `motor_model.py` is imported for torque/speed checks, unchanged.

The physics layer is a pure function: `compute_elevator_physics(inputs) ->
ElevatorPhysicsResult`. No side effects, no I/O. This makes hermetic testing
trivial (Section 9).

---

## 4. The MCP Call Sequence

The sequence below is the complete ordered list of `mcp__onshape__*` tool calls
in `elevator_rev2.py`. Tools marked `[VERIFIED]` worked during the smoke test
(`BLUEPRINT_MCP_SMOKE_TEST.md`). Tools marked `[UNVERIFIED]` were not exercised
in the smoke test — they are part of the 45-tool inventory but have not been
called against a live Onshape document by this project.

**Phase A — Create document and assembly shell**

```
1. mcp__onshape__create_document
   args: name="2950 Cascade Elevator — {game} {date}"
   [UNVERIFIED — create_document not called in smoke test]
   → returns: documentId, defaultWorkspaceId
   store as: DOC_ID, WS_ID

2. mcp__onshape__create_assembly
   args: documentId=DOC_ID, workspaceId=WS_ID, name="Elevator Assembly"
   [UNVERIFIED]
   → returns: elementId
   store as: ASM_ID
```

**Phase B — Insert COTS instances**

One `add_assembly_instance` call per part. Part IDs come from
`elevator_parts.py` (Section 5). Instances are inserted at the origin; position
is corrected in Phase D.

```
3.  mcp__onshape__add_assembly_instance   [UNVERIFIED]
    part: stage1_left_rail_tube
    → instance_id: RAIL_S1_L

4.  mcp__onshape__add_assembly_instance
    part: stage1_right_rail_tube
    → instance_id: RAIL_S1_R

5.  mcp__onshape__add_assembly_instance   (if stage_count == 2)
    part: stage2_left_rail_tube
    → instance_id: RAIL_S2_L

6.  mcp__onshape__add_assembly_instance   (if stage_count == 2)
    part: stage2_right_rail_tube
    → instance_id: RAIL_S2_R

7.  mcp__onshape__add_assembly_instance
    part: carriage_plate         (configuration: carriage_plate_thickness_in)
    → instance_id: CARRIAGE

8.  mcp__onshape__add_assembly_instance   ×4
    part: thrifty_bearing_block  (4 blocks per moving stage)
    → instance_ids: BB_1..BB_4 (stage 1), BB_5..BB_8 (stage 2 if present)

9.  mcp__onshape__add_assembly_instance
    part: motor_{motor_type}     (e.g., kraken_x60 or neo)
    → instance_id: MOTOR_1

10. mcp__onshape__add_assembly_instance
    part: motor_{motor_type}
    → instance_id: MOTOR_2

11. mcp__onshape__add_assembly_instance
    part: wcp_single_reduction_gearbox  (ratio from physics)
    → instance_id: GEARBOX

12. mcp__onshape__add_assembly_instance
    part: through_bore_encoder
    → instance_id: ENCODER

13. mcp__onshape__add_assembly_instance ×2
    part: constant_force_spring_{spring_force_lb}lb
    → instance_ids: SPRING_L, SPRING_R
```

Total instances: 14–18 depending on stage count. All calls share the same
`documentId`, `workspaceId`, `assemblyId` from Phase A.

**Phase C — Place mate connectors**

Mate connectors define the reference frames that mates snap to. Placed at
geometric key points of each instance.

```
14. mcp__onshape__create_mate_connector   [UNVERIFIED]
    on: RAIL_S1_L, at: bottom_end_center
    → CONN_S1L_BOT

15. mcp__onshape__create_mate_connector
    on: RAIL_S1_L, at: top_end_center
    → CONN_S1L_TOP

(Repeat for RAIL_S1_R, RAIL_S2_L, RAIL_S2_R, CARRIAGE, GEARBOX)
```

Total mate connectors: approximately 10–14. This is the highest-risk phase
(see Section 10). If FRCDesignLib parts already carry named mate connectors,
these calls are skipped and replaced by referencing existing connector IDs
(see Section 6).

**Phase D — Position instances**

```
mcp__onshape__transform_instance   [UNVERIFIED]
    Move each instance to its computed (x, y, z) offset
    Coordinates come from ElevatorPhysicsResult.layout_mm dict
    One call per instance: ~15 calls
```

**Phase E — Add mates**

```
mcp__onshape__create_fastened_mate   [UNVERIFIED]
    For every rigid joint: motor→gearbox, gearbox→rail_s1, bearing_block→stage_tube
    Expected count: 8–12 fastened mates

mcp__onshape__create_slider_mate    [UNVERIFIED]
    slider_1: RAIL_S1_L/TOP ↔ RAIL_S2_L/BOT  (stage 2 slides on stage 1)
    slider_2: RAIL_S2_L/TOP ↔ CARRIAGE/BOT   (carriage slides on stage 2)
    Total: 2 slider mates
```

**Phase F — Validation (optional, gated by flag)**

```
mcp__onshape__check_assembly_interference   [UNVERIFIED]
    Run only when --check-interference flag is passed
    Expected: 0 interferences if transforms are correct

mcp__onshape__export_assembly               [UNVERIFIED]
    Run only when --export-step flag is passed
    Produces a STEP file snapshot for BOM rollup
```

**Total MCP round-trips (nominal path):** approximately 50–60 calls.
At ~0.5–1.5s per call (smoke test did not measure latency for write ops),
estimated wall time: 30–90 seconds. This is within the 90-second target.
The A3 risk note about serial MCP latency applies here — if write ops are
slower than reads, this could blow past 90 seconds. Measure on first run.

---

## 5. FRCDesignLib Part Sourcing

**Recommended path: hardcoded mapping in `elevator_parts.py`, WCP as primary vendor.**

Rationale: The smoke test showed FRCDesign parts have stable `doc/ver/elem/part_id`
tuples. The existing `frcdesignlib_parts.json` in `blueprint/` uses exactly this
format and it works (19 parts verified). Adding elevator parts follows the same
pattern. Querying Firestore or vendor Google Sheets at runtime adds network
dependency with zero benefit for a set of ~15 parts that changes once per season.

**File: `blueprint/cots_parts/elevator_parts.py`**

```python
# Format matches frcdesignlib_parts.json exactly — dict keyed by logical name.
# Each entry: doc (documentId), ver (versionId or None for workspace),
#             elem (elementId), is_asm (bool), part_id (str, empty if asm),
#             elem_name (str, for display)

ELEVATOR_PARTS = {
    "stage_rail_2x1_24in": { ... },   # 24" 2x1x0.0625" tube — stage 1 default
    "stage_rail_2x1_30in": { ... },   # 30" variant
    "stage_rail_2x1_36in": { ... },   # 36" variant
    "thrifty_bearing_block": { ... },  # Thrifty Elevator bearing block
    "carriage_plate_0125": { ... },    # 0.125" carriage plate
    "carriage_plate_0250": { ... },    # 0.25" carriage plate
    "wcp_greyt_gearbox_5to1": { ... }, # WCP GreyT single-stage 5:1
    "wcp_greyt_gearbox_7to1": { ... }, # WCP GreyT single-stage 7:1
    "wcp_greyt_gearbox_10to1": { ... },# WCP GreyT single-stage 10:1
    "kraken_x60": { ... },             # already in frcdesignlib_parts.json — import
    "neo_brushless": { ... },          # NI/REV — add if not present
    "through_bore_encoder": { ... },   # REV Through-Bore Encoder
    "constant_force_spring_8lb": { ... }, # WCP spring
    "constant_force_spring_12lb": { ... },# WCP spring
    "belt_9mm_htd3_kit": { ... },      # 9mm belt + 18T pulleys (kit form)
}

def resolve(key: str) -> dict:
    """Return part dict or raise KeyError with a helpful message."""
    ...
```

The `kraken_x60` entry is already in `frcdesignlib_parts.json`. `elevator_parts.py`
imports it rather than duplicating the doc ID.

**What to do if a part is not in FRCDesignLib:** see Section 10.

**Finding document IDs:** Use `mcp__onshape__search_documents` with "FRCDesignLib"
as the query, then `mcp__onshape__get_elements` to list element IDs, then
`mcp__onshape__get_parts` to enumerate part IDs within an element. Run this
once, paste results into `elevator_parts.py`. This lookup is a one-time
pre-flight, not part of the generator's runtime path.

---

## 6. Mate Connector Strategy

**Assumption for Phase 1:** FRCDesignLib elevator parts do NOT already have
pre-named mate connectors that we can reference by stable ID.

This assumption is based on the smoke test finding: the FRCDesign elevator
assembly has only 2 mate connectors total (for the whole 134-feature assembly),
placed on the assembly level, not on individual part instances. Parts inserted
from FRCDesignLib into a new assembly arrive without pre-baked connectors.

**Therefore Phase 1 creates mate connectors on-the-fly via MCP.**

The strategy:

1. After each `add_assembly_instance` call returns an instance ID, call
   `mcp__onshape__get_assembly_positions` to get the instance's current
   transform and bounding geometry.
2. Compute connector positions (bottom-end-center, top-end-center) from the
   bounding box + known tube orientation.
3. Call `mcp__onshape__create_mate_connector` with the computed position.

This is more work than referencing existing connectors (~2 extra MCP calls per
connector point) but is robust regardless of what's inside the FRCDesignLib part.

**Alternative (fast path):** If the FRCDesign elevator Part Studios are found to
already carry named connectors (check with `mcp__onshape__get_features` on the
part studio element), reference them by `featureId` in the mate call instead.
This halves the connector-creation round-trips. Check this before Phase 1
implementation starts — it takes 2 MCP calls to answer definitively.

---

## 7. The Cascade Coupling Problem

**The problem:** A cascade elevator requires stage 2 to extend at 2× the rate
of stage 1. In the FRCDesign reference assembly this is encoded as
`BTMMateRelation-1412` (a Linear mate relation), visible in the smoke test's
134-feature breakdown as "1 Linear mate relation."

**Does onshape-mcp expose a tool for mate relations?**

Scanning the 45-tool inventory from the smoke test:

- `create_fastened_mate` — rigid join
- `create_slider_mate` — 1-DOF translation
- `create_revolute_mate` — 1-DOF rotation
- `create_cylindrical_mate` — translation + rotation
- No `create_linear_mate_relation` or `create_mate_relation` tool exists.

**Confirmed limitation:** The 45-tool onshape-mcp inventory (as of 0.3.0) does
not include a mate relation tool. We cannot replicate the cascade coupling in
MCP alone.

**Phase 1 workaround — accept 1-DOF-per-stage, drive both from generator:**

Phase 1 creates 2 independent Slider mates (one per stage) and does not couple
them. The assembly is geometrically correct at any single commanded position.
The cascade 2:1 relationship is documented in the assembly's description and
must be enforced by the user or a future `eval_featurescript` call.

This is not a functional regression for the Phase 1 goal (produce a verifiable
Onshape assembly) because the cascade coupling is a control-time constraint,
not a structural constraint.

**Phase 2 fallback (document now, implement later):**

`mcp__onshape__eval_featurescript` accepts arbitrary FeatureScript. A Linear
mate relation can be created via FeatureScript. If Phase 2 (swerve frame) hits
a similar structural need, consider wrapping `eval_featurescript` with a thin
`create_mate_relation(type, ratio, slider_ids)` helper in a shared
`blueprint/mcp_helpers.py`. This is explicitly out of scope for Phase 1.

---

## 8. File Layout

Phase 1 creates exactly these files and modifies exactly one existing file.

**New files:**

```
blueprint/
  generators/
    __init__.py              (empty, marks generators as a package)
    elevator_rev2.py         (~200 LOC, the main generator)
  cots_parts/
    __init__.py              (empty)
    elevator_parts.py        (~80 LOC, part-ID mapping + resolve())

tests/
  test_elevator_rev2_hermetic.py    (~18 tests, no Onshape dependency)
  test_elevator_rev2_gated.py       (~2 tests, require ONSHAPE_ACCESS_KEY)
```

**Modified files:**

```
blueprint/build_full_robot.py
  — Add import of elevator_rev2.generate_elevator_assembly
  — In the main dispatch block, replace the call to elevator_generator.py
    with elevator_rev2 when scorer == "elevator"
  — Change: ~10 lines touched, no other logic altered
```

**Untouched files (explicitly — do not modify in Phase 1):**

```
blueprint/oracle.py
blueprint/motor_model.py
blueprint/assembly_composer.py
blueprint/bom_rollup.py
blueprint/elevator_generator.py   (kept, not wired — Phase 0 deletes cad_builder
                                   and assembly_builder, not elevator_generator)
blueprint/plate_generator.py       (shrink is a Phase 0 task, not Phase 1)
blueprint/turret_generator.py      (same)
blueprint/frcdesignlib_parts.json  (read-only reference in Phase 1)
```

**`elevator_rev2.py` internal structure:**

```
parse_oracle_output(oracle_json) -> ElevatorInputs
compute_elevator_physics(inputs) -> ElevatorPhysicsResult
build_elevator_assembly(physics, dry_run=False) -> AssemblyResult
  _create_doc_and_assembly(...)
  _insert_instances(...)
  _place_mate_connectors(...)
  _position_instances(...)
  _add_mates(...)
  _validate(...)
main() [CLI entry point with --game, --dry-run, --check-interference, --export-step]
```

The `--dry-run` flag runs parse + physics only, prints the resolved
`ElevatorPhysicsResult` as JSON, and exits without calling any MCP tool. This
is the fast feedback loop during development.

---

## 9. Tests

**Hermetic tests (`test_elevator_rev2_hermetic.py`) — ~18 tests:**

Physics layer correctness:

- `test_stage_count_1_for_stroke_under_40in` — stroke 36" → stage_count == 1
- `test_stage_count_2_for_stroke_40_to_55in` — stroke 48" → stage_count == 2
- `test_stage_count_2_for_stroke_over_55in` — stroke 60" → stage_count == 2
  (oracle R5 caps at 2)
- `test_tube_length_formula_24in_stroke` — tube_length = 24/2 + 4 = 16"
- `test_tube_length_formula_48in_stroke` — tube_length = 48/2 + 4 = 28"
- `test_carriage_plate_thin_under_8lb` — 5 lb load → 0.125" plate
- `test_carriage_plate_thick_at_8lb` — 8 lb load → 0.25" plate
- `test_gear_ratio_light_load` — 4 lb carriage → ratio == 5
- `test_gear_ratio_medium_load` — 7 lb carriage → ratio == 7
- `test_gear_ratio_heavy_load` — 12 lb carriage → ratio == 10
- `test_motor_preference_kraken_passthrough` — oracle pref "kraken_x60" preserved
- `test_motor_preference_neo_passthrough` — oracle pref "neo" preserved
- `test_spring_force_rounds_to_nearest_stock` — 9 lb load → 8 lb spring
  (nearest WCP stock below carriage weight)

Part-ID mapping:

- `test_resolve_stage_rail_key_returns_dict_with_required_fields`
- `test_resolve_unknown_key_raises_key_error`
- `test_all_elevator_parts_have_required_fields` — iterates ELEVATOR_PARTS,
  asserts each entry has doc, elem, is_asm, elem_name
- `test_kraken_x60_not_duplicated` — elevator_parts.py should import from
  frcdesignlib_parts.json, not re-define a different doc ID

MCP sequence shape (monkeypatching, no network):

- `test_dry_run_produces_physics_result_json` — run generator with --dry-run,
  assert output parses as valid JSON with expected keys

**Onshape-gated tests (`test_elevator_rev2_gated.py`) — 2 tests:**

Both are skipped automatically when `ONSHAPE_ACCESS_KEY` is not set, using a
`pytest.mark.skipif` decorator.

- `test_end_to_end_creates_assembly_with_instances` — runs full pipeline for
  a minimal 1-stage, kraken, 36" stroke spec; asserts the returned
  `AssemblyResult.instance_count > 0` and `AssemblyResult.document_url` is a
  valid `cad.onshape.com` URL
- `test_end_to_end_slider_mate_count_matches_stage_count` — same run; calls
  `mcp__onshape__get_assembly_features` on the resulting assembly; asserts
  slider mate count == stage_count

Test runner command:

```bash
pytest tests/test_elevator_rev2_hermetic.py -v          # always runs
pytest tests/test_elevator_rev2_gated.py -v             # skips without key
pytest tests/ -v -k "not gated"                         # safe CI subset
```

---

## 10. Risks

**R1 — Serial MCP latency (from A3 risk callout)**
Severity: medium. The smoke test measured read-op latency but not write ops.
`create_assembly`, `add_assembly_instance`, and `create_mate_connector` each
hit Onshape's CAD kernel and may be slower than `get_*` queries. If the 50–60
call sequence exceeds 5 minutes, the generator is unusable on kickoff day.
Mitigation: instrument every MCP call with a timestamp in Phase 1; log wall time
per phase. If Phase B (insert instances) is slow, batch into fewer calls using
`eval_featurescript` to insert multiple instances in one round-trip.

**R2 — FRCDesignLib part coverage**
Severity: high. If a part needed by the elevator (e.g., Thrifty bearing block,
WCP constant force spring) is not in the FRCDesignLib Onshape library, the
`add_assembly_instance` call will fail or produce an empty instance.
Mitigation: run `mcp__onshape__search_documents` + `get_elements` + `get_parts`
as a pre-flight check during `elevator_parts.py` authoring. For any missing
part: (a) use `eval_featurescript` to create a simple placeholder solid,
or (b) skip that part and note the gap in `AssemblyResult.missing_parts`.
Phase 1 does not need 100% COTS coverage — the success criterion requires only
rail tubes, carriage, and slider mates to be present.

**R3 — Mate connector absence on FRCDesignLib parts**
Severity: high. If FRCDesignLib parts arrive with no named mate connectors, the
Phase C connector-creation step requires computing exact 3D positions from
bounding boxes — any error in the coordinate math places connectors in the wrong
location, causing mate failures.
Mitigation: run `mcp__onshape__get_features` on the FRCDesignLib tube Part
Studio before writing a single line of Phase C code. If connectors are present,
use them. If not, the connector-placement step is the hardest engineering problem
in Phase 1 and warrants an extra 30–60 minutes of debugging budget.

**R4 — Cascade linear relation absent from MCP**
Severity: low for Phase 1. The accepted workaround (two independent Slider mates)
is documented in Section 7. The assembly is valid without cascade coupling — it
just cannot be animated with the correct kinematics in Onshape without a manual
mate relation added by the user. This is an acceptable Phase 1 limitation.

**R5 — Onshape API rate limiting**
Severity: low. Onshape's API has a rate limit (500 requests per minute for free
accounts). 50–60 calls is well within limits for a single generator run. Not a
concern unless the generator is called in a loop (e.g., batch robot generation).

---

## 11. Time Budget

A3 allocated ~3h Sonnet time for Phase 1. Breakdown:

| Task | Estimate | Risk multiplier |
|---|---|---|
| Read current generators + understand patterns | 30m | 1× — well-understood |
| Write `elevator_parts.py` + run search_documents pre-flight | 30m | 1.5× if parts are missing (R2) |
| Write physics layer (`compute_elevator_physics`) + hermetic tests | 45m | 1× — pure Python, trivial to test |
| Write MCP call sequence (Phases A–E) | 60m | 2× if mate connector placement is hard (R3) |
| Debug gated tests against live Onshape | 45m | 3× if write ops have unexpected errors |
| Wire `build_full_robot.py` | 15m | 1× |

**Nominal total: 3h 45m.** This is already above the A3 estimate of 3h.

**Risks that blow the budget:**

- R3 (mate connector absence): adds 1–2h if coordinate math for connector
  placement is nontrivial. This is the most likely time sink.
- R2 (part coverage): if 3+ elevator parts are missing from FRCDesignLib, the
  pre-flight authoring of `elevator_parts.py` could take an extra 30–60 minutes.
- Unexpected Onshape write-op errors (wrong required fields, API contract
  different from MCP docs): adds 30–60m debugging against live Onshape.

**Recommendation:** Run the mate connector pre-flight check (Section 6,
alternative fast path) before any other Phase 1 work. If parts have connectors,
the 3h budget is achievable. If not, budget 4–5h.

---

## 12. Definition of Done

- [ ] `blueprint/generators/elevator_rev2.py` exists and passes `flake8`
- [ ] `blueprint/cots_parts/elevator_parts.py` exists with all 15 part entries
      populated with verified Onshape doc/elem IDs
- [ ] `python3 blueprint/generators/elevator_rev2.py --game 2026_rebuilt --dry-run`
      prints a valid `ElevatorPhysicsResult` JSON for the REBUILT game's oracle output
- [ ] All 18 hermetic tests pass without network access
- [ ] Both gated tests pass with `ONSHAPE_ACCESS_KEY` set (run manually before
      closing the Phase 1 session)
- [ ] The gated test's produced Onshape URL opens in a browser and shows an
      assembly with at least 6 instances and 2 Slider mates
- [ ] `build_full_robot.py` calls `elevator_rev2` (not `elevator_generator`) for
      scorer == "elevator"
- [ ] `BLUEPRINT_REV2_DECISION.md` risk item "serial MCP latency" has measured
      data: total wall time for Phase 1 run is logged and recorded in a one-line
      note appended to this document
- [ ] No changes to `oracle.py`, `motor_model.py`, or any file marked KEEP in
      the A3 fate table

---

*B-MCP.2 spec | Blueprint Rev-2 | Team 2950 The Devastators | 2026-04-13*
*Next: Phase 2 swerve frame generator spec (B-MCP.3)*
