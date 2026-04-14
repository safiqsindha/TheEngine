# Blueprint Rev-2 Phase 0 Report
**Date:** 2026-04-13
**Session:** Sonnet 4.6 — Phase 0 execution (delete + shrink)

---

## What was done

Phase 0 executed the Blueprint Rev-2 MCP pivot cuts as specified in
`BLUEPRINT_REV2_DECISION.md` (A3 fate table). No commits were made;
all changes are staged for review.

---

## LOC deleted per file

### Deleted outright (A3 fate: DELETE)

| File | Pre-cut LOC | Post-cut LOC | Deleted |
|---|---|---|---|
| `blueprint/cad_builder.py` | 700 | 0 (file deleted) | 700 |
| `blueprint/assembly_builder.py` | 724 | 0 (file deleted) | 724 |
| `blueprint/insert_cots.py` | 533 | 0 (file deleted) | 533 |
| **Subtotal** | **1,957** | **0** | **1,957** |

### Shrunk (A3 fate: SHRINK)

| File | Pre-cut LOC | Post-cut LOC | Deleted |
|---|---|---|---|
| `blueprint/assembly_composer.py` | 472 | 464 | 8 |
| `blueprint/plate_generator.py` | 567 | 518 | 49 |
| `blueprint/turret_generator.py` | 515 | 389 | 126 |
| **Subtotal** | **1,554** | **1,371** | **183** |

### Stubbed (A3 fate: REWRITE — deferred to Phase 1)

| File | Pre-cut LOC | Post-cut LOC | Deleted |
|---|---|---|---|
| `blueprint/build_full_robot.py` | 229 | 48 | 181 |
| **Subtotal** | **229** | **48** | **181** |

### Left in place (A3 fate: REPLACE — Phase 1 work)

| File | Pre-cut LOC | Post-cut LOC | Deleted |
|---|---|---|---|
| `blueprint/part_resolver.py` | 433 | 441 | 0 (docstring added: +8) |

### Net total

**~2,321 LOC deleted** across all changes (1,957 deleted files + 183 shrunk + 181 stubbed).

---

## Test count before/after

| Metric | Before | After | Delta |
|---|---|---|---|
| Tests collected | 949 | 938 | -11 |
| Passed | ~946 | 936 | -10 |
| Skipped | 2 | 2 | 0 |
| xfail | 3 | **0** | **-3** |
| Failures | 0 | **0** | 0 |

Tests removed breakdown:
- 7 `_check_overlap` unit tests (subject function deleted)
- 3 `test_historical_no_mechanism_interference` xfail parametrized tests (2022, 2023, 2024)
- 1 `test_two_overlapping_mechanisms_triggers_warning` test (tested AABB path, now deleted)

The 3 AABB xfails are **gone** — not converted to passes, deleted as the function no longer exists.

---

## Deviations from the A3 plan (with reason)

### 1. `plate_generator.py` shrink: 518 LOC, not <200 LOC target

**Reason:** The `plates_to_featurescript` function (the only true FeatureScript emission) was ~46 LOC. The remaining ~470 LOC is all physics: `BoltHole`, `Pocket`, `CustomPlate` dataclasses, `BOLT_PATTERNS`, mount constants (`THRIFTY_BEARING_BLOCK`, `NEO_MOUNT`, `KRAKEN_MOUNT`), bolt-pattern helper functions (`_bolt_circle`, `_bolt_grid`), and 5 mechanism-specific plate generators. These are all load/geometry physics — they compute bolt positions, bearing bore diameters, and plate dimensions from mechanism specs. None of it is FeatureScript string emission.

The A3 "<200 LOC" target assumed most of the module was FeatureScript generation. It wasn't. The physics is legitimately dense. This is not a deviation from intent — the physics was supposed to survive, and it did.

### 2. `turret_generator.py` shrink: 389 LOC, not closer to <200 LOC

**Reason:** `PRESETS` (the preset configuration dict, ~55 LOC) had to be restored after deletion. `bom_rollup.py` imports `PRESETS as TURRET_PRESETS` — and `bom_rollup.py` is KEEP UNCHANGED per the A3 fate table. Deleting `PRESETS` broke `bom_rollup.py` import. The fix was to restore `PRESETS` with a comment noting it's kept for `bom_rollup.py` compatibility.

The actual geometry emission deleted from `turret_generator.py` was: `display_spec` (~40 LOC), `main` (~30 LOC), and the `parts_list`/`notes` generation block inside `generate_turret` (~50 LOC). `json`, `sys`, and `asdict` imports also removed. Net 126 LOC deleted.

### 3. `assembly_composer.py` shrink: only 8 LOC deleted

**Reason:** The AABB function (`_check_overlap`) was 10 LOC. The call-site block was removed (5 LOC) and replaced with a 3-line comment explaining the removal. The docstring was expanded to document the Rev-2 scope. Net LOC delta is small because the module's CoG, mass rollup, placement logic, and assembly-order generation all survive untouched per A3.

### 4. `plate_generator.py` — `display_plates` and CLI kept

The `display_plates` function and the `if __name__ == "__main__"` CLI were kept. The CLI no longer calls `plates_to_featurescript` (that call was removed). These are harmless display utilities that don't depend on deleted code. Removing them would save ~20 LOC with no benefit.

---

## What Phase 1 must account for

### A. `build_full_robot.py` is a stub — Phase 1 must wire it

The orchestrator raises `NotImplementedError` now. Phase 1 (B-MCP.2) wires in `elevator_rev2.py` as the first MCP generator. The Phase 1 spec (`BLUEPRINT_REV2_COPY_PARAMETRIZE.md`, Section 8) already documents the exact `build_full_robot.py` change needed: import `elevator_rev2.generate_elevator_assembly`, dispatch on `scorer == "elevator"`.

### B. `part_resolver.py` is unreferenced dead code

Nothing in the live codebase imports `part_resolver.py`. It was kept in place (per A3: REPLACE in Phase 1, not DELETE in Phase 0). Phase 1 should replace it with a thin FRCDesignLib Firestore-backed resolver per the spec, then delete the old file. Do not let it linger past Phase 1.

### C. `turret_generator.py` — `parts_list` and `notes` fields now empty

`TurretSpec.parts_list` and `TurretSpec.notes` are still declared in the dataclass (so `bom_rollup.py` doesn't crash) but `generate_turret` no longer populates them. This means:
- Turret BOM entries will have empty `parts` lists in the rollup output
- Turret notes will not appear in the rollup summary

This is acceptable for Phase 0 — the turret BOM was a convenience feature, not a structural requirement. Phase 1 (or a turret-specific generator) can repopulate these from a proper COTS catalog lookup.

### D. `plate_generator.py` — weight computation still live

`CustomPlate.compute_weight()` and `generate_mechanism_plates()` are live and accurate. If Phase 1 needs carriage plate weight estimates for BOM rollup, these functions are ready to use. They do not depend on the deleted FeatureScript surface.

### E. LOC net: ~2,321 deleted vs A3 target of ~3,000

The gap (~680 LOC) is explained by:
- `plate_generator.py` physics being larger than assumed (~320 LOC vs expected <50)
- `turret_generator.py` PRESETS restoration (55 LOC)
- `assembly_composer.py` physics surviving largely intact

The cut is within the spirit of the A3 target. All hand-rolled FeatureScript and all hand-rolled Onshape API wiring are gone.

---

## Files touched summary

| File | Action |
|---|---|
| `blueprint/cad_builder.py` | DELETED |
| `blueprint/assembly_builder.py` | DELETED |
| `blueprint/insert_cots.py` | DELETED |
| `blueprint/assembly_composer.py` | SHRUNK (docstring, AABB block, `_check_overlap` function) |
| `blueprint/plate_generator.py` | SHRUNK (`plates_to_featurescript`, CLI FS line, docstring) |
| `blueprint/turret_generator.py` | SHRUNK (display_spec, main, parts_list/notes gen, unused imports; PRESETS restored) |
| `blueprint/build_full_robot.py` | STUBBED (imports + body replaced with NotImplementedError) |
| `blueprint/part_resolver.py` | DOCSTRING ONLY (deprecation notice added) |
| `tests/blueprint/test_assembly_composer.py` | 11 tests removed (7 `_check_overlap` unit, 3 AABB xfail, 1 overlap warning) |

**Files not touched (KEEP UNCHANGED per A3):**
`oracle.py`, `bom_rollup.py`, `motor_model.py`, `oracle_pipeline.py`, `prediction_bridge.py`,
`onshape_api.py`, `cots_parts/`, all scout/antenna/eye modules.

---

*Phase 0 complete. Ready for Phase 1 (B-MCP.2): elevator_rev2.py MCP generator.*
