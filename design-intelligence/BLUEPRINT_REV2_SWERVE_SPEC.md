# Blueprint Rev-2 Phase 2 — Swerve Frame Generator (B-MCP.3 Spec)
# 2026-04-13 | Team 2950 The Devastators

**Tier B output.** Concrete implementation spec for Phase 2 of the MCP pivot.
Mirrors the structure of `BLUEPRINT_REV2_COPY_PARAMETRIZE.md` (B-MCP.2 Phase 1 spec).
Inputs: `BLUEPRINT_REV2_DECISION.md` (fate table), Phase 1 elevator pattern (merged).

---

## 1. Scope

### What Phase 2 Delivers

Two new files — `blueprint/generators/swerve_rev2.py` and
`blueprint/cots_parts/swerve_parts.py` — plus hermetic and gated tests,
wired into `build_full_robot.py`.

The end-to-end path:

```
oracle.py  →  SwerveInputs → compute_swerve_physics() → build_swerve_assembly()
           →  onshape-mcp calls → Onshape doc URL
```

Output: printed Onshape document URL. Opening it shows a swerve drive frame
with 4 rail tubes, 4 cross-members, 4 corner gussets, and 4 swerve module
instances fastened at module-mount positions.

**Phase 2 structural scope: drive base frame only.** No bellypan cutouts,
no electrical layout, no bumper brackets. These are documented deferred items.

### What Phase 2 Explicitly Does Not Deliver

- Belly pan cutout geometry (complex notch patterns — Phase 3)
- Bumper mount brackets (structural bolting — Phase 3)
- Electrical / pneumatics layout
- Circular-pattern MCP shortcut (Phase 1 module placement is explicit loop — rationale in Section 7)
- Three-module or six-module configs (4-module canonical only)
- WCP Swerve X module (FRCDesignLib has SDS MK4i as the canonical swerve asm; see Section 5)

### Success Criterion

```
python3 blueprint/generators/swerve_rev2.py --dry-run
```

prints a valid `SwervePhysicsResult` JSON. Full run produces an Onshape URL
showing a frame assembly with 4 rail instances, 4 cross-members, 4 corner
gusset instances, and 4 module instances.

---

## 2. Inputs

Oracle keys consumed (all within `scorer` block, type must equal `"swerve"`):

```
oracle_output["scorer"]["type"]                → "swerve" (gate check)
oracle_output["scorer"]["wheelbase_in"]        → float, front-to-back wheel center distance
oracle_output["scorer"]["trackwidth_in"]       → float, left-to-right wheel center distance
oracle_output["scorer"]["module_type"]         → str ("wcp_swerve_x" | "sds_mk4i" | "rev_maxswerve")
oracle_output["scorer"]["module_count"]        → int, canonical 4 (other values: error)
oracle_output["weight_budget"]["scorer_lb"]    → float, weight allocated to drive base
```

The generator owns all geometry decisions downstream — the oracle provides
only the logical spec.

---

## 3. Physics Decisions

Pure function `compute_swerve_physics(inputs) -> SwervePhysicsResult`.
No I/O, no side effects. Drives MCP calls directly.

| Decision | Field | How Decided |
|---|---|---|
| Frame rail length (front/rear) | `rail_length_in` | `trackwidth_in` (left rail to right rail outer edge) |
| Frame rail length (left/right) | `rail_longside_in` | `wheelbase_in` (front to rear rail outer edge) |
| Rail cross-section | `rail_spec` | "2x1x0.0625" always (FRC standard, same as elevator) |
| Tube weight estimate | `frame_weight_lb` | rail count × length × 0.035 lb/in |
| Module mounting hole pattern | `module_mount_mm` | corner offsets from frame origin, one per module |
| Corner gusset count | `gusset_count` | 4 (always — one per corner) |
| Module type resolved | `module_part_key` | maps oracle `module_type` string to swerve_parts.py key |
| Layout positions (mm) | `layout_mm` | computed from wheelbase/trackwidth in millimetres |

### Frame Rail Sizing

Canonical FRC frame: 2x1 aluminium tube on a rectangular perimeter.
Generator creates 8 tube instances: 4 long-side (wheelbase) + 4 short-side (trackwidth).
Four corner gussets (WCP 90° gusset from FRCDesignLib) fasten perimeter corners.

### Module Offset Calculation

Each module sits at a corner offset from the frame centre by ±(trackwidth/2)
on X and ±(wheelbase/2) on Y. All four corners are computed and stored in
`layout_mm` as `MOD_FL`, `MOD_FR`, `MOD_RL`, `MOD_RR`.

### Weight Estimate

```
frame_weight_lb = (2 × rail_length_in + 2 × rail_longside_in) × 0.035   # perimeter tubes
                + 4 × 1.5                                                 # gussets (approx)
module_weight_lb = 4 × 4.2   # SDS MK4i ~4.2 lb per module (verified spec)
total_estimate_lb = frame_weight_lb + module_weight_lb
```

---

## 4. MCP Call Sequence

Same phase labels as elevator (A–F). Same `_add_and_capture()` pattern — 
`add_assembly_instance` always returns `instance_id="unknown"`, so we call
`get_assembly_positions` after each insert and take the last entry.

**Phase A — Document + assembly shell**
```
create_document (or use --doc-id)  → DOC_ID, WS_ID
create_assembly                    → ASM_ID
```

**Phase B — Part Studios for custom geometry**
```
create_part_studio   "Swerve Rail Tube {spec} {length}in"
  create_sketch_rectangle  corner1=[0,0], corner2=[2.0, 1.0]
  create_extrude           depth=length_in
→ LONGSIDE_ELEM_ID   (for wheelbase-length rails)

create_part_studio   "Swerve Cross-member Tube {spec} {length}in"
  create_sketch_rectangle  corner1=[0,0], corner2=[2.0, 1.0]
  create_extrude           depth=cross_length_in
→ SHORTSIDE_ELEM_ID  (for trackwidth-length rails)
```

**Phase B — Insert instances**
```
# Long-side rails: Front Left, Front Right, Rear Left, Rear Right
add_assembly_instance × 4  (LONGSIDE_ELEM_ID, is_asm=False) → RAIL_LS_{1..4}

# Short-side cross-members: two (front + rear)
add_assembly_instance × 2  (SHORTSIDE_ELEM_ID, is_asm=False) → RAIL_SS_{1..2}

# Corner gussets: 4 corners
add_assembly_instance × 4  (WCP 90° gusset, is_asm=False)   → GUSSET_{1..4}

# Swerve modules: 4 corners (FL, FR, RL, RR)
add_assembly_instance × 4  (module asm, is_asm=True)         → MOD_FL, MOD_FR, MOD_RL, MOD_RR
```

Total instances: 14 (4 + 2 + 4 + 4).

**Note on `create_circular_pattern`:** MCP has this tool but it requires a
face-based pattern axis. For 4 modules at asymmetric frame corners, explicit
transform_instance × 4 is cleaner and matches the elevator's explicit pattern.
`create_circular_pattern` is not used in Phase 2. Document for Phase 3 if needed.

**Phase C — Position instances**
```
transform_instance × 14  (from layout_mm dict)
```

**Phase D — Face IDs**
```
get_body_details (longside tube Part Studio)  → top/bottom face IDs
get_body_details (shortside tube Part Studio) → top/bottom face IDs
```

**Phase E — Mates**
```
# Gussets fastened at 4 corners
create_fastened_mate × 4  (gusset ↔ rail corner)

# Module fastened at module-mount positions
create_fastened_mate × 4  (module ↔ frame)
```

Total mates: 8 fastened (4 corner gussets + 4 module mounts).
No Slider or revolute mates — swerve frame is rigid.

**Phase F — Optional validation**
```
check_assembly_interference  (--check-interference flag)
export_assembly              (--export-step flag)
```

Total MCP calls (nominal): ~35–45. Faster than elevator (no springs, encoder,
slider mates).

---

## 5. FRCDesignLib Part Sourcing

**Swerve module:** `SDS MK4i Swerve Module` is in `frcdesignlib_parts.json`
(doc `698e922b5304f1d6a2b06339`, verified). This is the canonical module used
for Phase 2.

**WCP Swerve X and REV MaxSwerve** are not yet in `frcdesignlib_parts.json`.
For Phase 2: if oracle specifies `wcp_swerve_x` or `rev_maxswerve`, the
generator logs a warning to `missing_parts` and falls back to SDS MK4i.
These modules can be added in Phase 3 once their FRCDesignLib doc IDs are
verified via `search_documents`.

**Corner gussets:** `WCP 90° Gusset (2x1 to 2x1)` is in `frcdesignlib_parts.json`
(doc `b0e317da377b0565c96fc265`, part_id `JPD`, verified).

**Frame rails:** geometry-created (Part Studio extrude), same as elevator tube rails.
`is_asm = None` sentinel in `swerve_parts.py`.

---

## 6. Pre-flight Check

**New MCP tool exercised in Phase 2:** none beyond what Phase 1 verified.
`create_circular_pattern` was considered (see Section 4) and rejected in favour
of explicit loop. No pre-flight scratch run required.

All tools used (create_part_studio, create_sketch_rectangle, create_extrude,
add_assembly_instance, get_assembly_positions, transform_instance,
create_fastened_mate, check_assembly_interference, export_assembly) were
exercised in Phase 1 elevator and are confirmed working.

---

## 7. Pattern to Fold Back into Elevator

During Phase 2 authoring one pattern improvement was identified:

**Shared `_MCPModule` / `_get_mcp_module()` / `set_mcp_module()`** is
copy-pasted between `elevator_rev2.py` and `swerve_rev2.py`. In Phase 3,
extract to `blueprint/mcp_helpers.py` and import from both generators.
This reduces the wrapper from ~60 LOC in each generator to a single import.

**`_add_and_capture()` inner function** is also duplicated. The helper is
tightly coupled to the enclosing doc_id/ws_id/asm_id closure, making it
non-trivial to extract without a state object. Accept duplication for Phase 2;
refactor in Phase 3 if a third generator appears.

---

## 8. File Layout

**New files:**
```
blueprint/
  generators/
    swerve_rev2.py          (~250 LOC)
  cots_parts/
    swerve_parts.py         (~80 LOC)

tests/
  blueprint/
    test_swerve_rev2_hermetic.py   (~20 tests)
    test_swerve_rev2_gated.py      (~2 tests)

design-intelligence/
  BLUEPRINT_REV2_SWERVE_SPEC.md   (this file)
```

**Modified files:**
```
blueprint/build_full_robot.py
  — Add import of swerve_rev2.generate_swerve_assembly
  — Fill in the existing `scorer == "swerve"` hook (was NotImplementedError)
  — ~6 lines changed
```

---

## 9. Tests

**Hermetic tests (~20):**

Physics layer:
- rail lengths from standard wheelbase/trackwidth
- module offset calculation (4 corner positions)
- weight estimate formula
- module_type fallback to SDS MK4i for unknown types
- gusset count is always 4
- layout_mm has exactly 14 keys (RAIL_LS_1..4, RAIL_SS_1..2, GUSSET_1..4, MOD_FL/FR/RL/RR)

Part-ID mapping:
- all swerve_parts entries have required fields
- SDS MK4i imports from frcdesignlib_parts.json (no duplicate doc ID)
- gusset imports from frcdesignlib_parts.json
- resolve() raises KeyError for unknown key

Oracle parse:
- parse_oracle_output raises ValueError for scorer != "swerve"
- standard wheelbase/trackwidth fixture parses correctly

Dry-run:
- dry_run=True returns AssemblyResult with dry_run=True, document_url=""
- physics values for default fixture (28×28 frame) match expected rail lengths

**Gated tests (~2):**
- end-to-end creates assembly with instance_count > 0 and valid URL
- fastened_mate count >= 4 (4 module mounts at minimum)

---

## 10. Deviations from Phase 1 Elevator Pattern

| Item | Elevator | Swerve | Reason |
|---|---|---|---|
| Mate types | Slider + Fastened | Fastened only | Frame is rigid; no sliding joints |
| Geometry Parts Studios | tube + plate | tube long + tube short | Two tube sizes needed for perimeter |
| Springs/encoder | yes | no | Drive base has no elastic or sensing |
| Gearbox instance | WCP GreyT Telescope | none (in module asm) | Module asm contains gearbox |
| Stage count variable | yes (1 or 2) | no (always 4 modules) | No analog |
| Weight estimation | complex (motor+spring+plate) | simpler (frame tubes + modules) | |

---

## 11. Definition of Done

- [ ] `blueprint/generators/swerve_rev2.py` exists and passes `flake8`
- [ ] `blueprint/cots_parts/swerve_parts.py` exists with all entries populated
- [ ] `--dry-run` prints valid `SwervePhysicsResult` JSON
- [ ] All ~20 hermetic tests pass without network access
- [ ] Both gated tests pass with `ONSHAPE_ACCESS_KEY` set (run manually)
- [ ] `build_full_robot.py` scorer == "swerve" calls swerve_rev2 (not NotImplementedError)
- [ ] All 972 pre-existing tests still pass (no regressions)

---

*B-MCP.3 spec | Blueprint Rev-2 | Team 2950 The Devastators | 2026-04-13*
*Prev: B-MCP.2 elevator (merged). Next: Phase 3 belly pan + bumper mounts.*
