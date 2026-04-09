# Blueprint CAD Evolution — Real COTS Assembly Pipeline

## Core Insight

FRC robot design is COTS-first. Teams select modules, motors, bearings, and
structural components from vendors, drop them into a frame, and design only the
connecting plates/brackets. The CAD system should mirror this workflow:

**Pick parts → Place parts → Output assembly**

Almost everything on an FRC robot is COTS — including the connecting geometry.
Gussets, brackets, bearing blocks, motor mounts, extrusion connectors are all
off-the-shelf from REV, WCP, TTB, and others. The only truly custom parts are
typically 2-3 simple plates per mechanism (elevator carriage, intake side plate).

---

## Architecture: Two-Layer CAD

```
Layer 1: COTS Parts (from FRCDesignLib via API)
  Everything — swerve modules, motors, gearboxes, bearings, sensors,
  electronics, wheels, pulleys, sprockets, tube stock,
  AND gussets, brackets, bearing blocks, motor mounts, extrusion connectors

Layer 2: Parametric Frame + Minimal Custom Plates (generated FeatureScript)
  Tube extrusions with real wall thickness, bellypan with mounting holes,
  cross members, module cutouts. Plus the 2-3 simple plates per mechanism
  that don't exist as COTS (elevator carriage plate, intake side plate).
```

The key realization: Layer 3 (connecting geometry) from the original scope is
almost entirely COTS too. Gussets, motor mount plates, bearing blocks — these
are all purchasable. The system should SELECT the right connector, not GENERATE it.

---

## Phase 1: COTS Part Resolution + Assembly Creation

### 1a. FRCDesignLib Part Resolver

The problem: FRCDesignApp stores parts in Firestore, not at static OnShape
document IDs. We need a resolver that maps catalog names to insertable parts.

**Approach — OnShape Document Search API:**
```
catalog entry: "SDS MK4i"
  → search OnShape public documents for "FRCDesignLib" + "MK4i"
  → find document_id, element_id, part_id
  → cache the mapping locally (parts don't change often)
```

**Implementation:**
- `part_resolver.py` — resolves catalog search terms to OnShape document/element/part IDs
- `part_cache.json` — local cache of resolved IDs (keyed by catalog name + version)
- Cache invalidation: check document microversion, re-resolve if changed
- Fallback: if resolution fails, use bounding box (current behavior)

### 1b. Assembly Document Builder

Currently `cad_builder.py` creates a Part Studio with FeatureScript geometry.
Real robots are OnShape **Assemblies** with inserted parts.

**New workflow:**
```
1. Create OnShape document
2. Create Part Studio → generate frame + custom parts via FeatureScript
3. Create Assembly
4. Insert frame from Part Studio
5. Resolve + insert each COTS part (swerve modules, motors, etc.)
6. Apply mate connectors to position parts
7. Return assembly URL
```

**New API methods needed in `onshape_api.py`:**
- `create_assembly(document_id, workspace_id, name)` — create assembly tab
- `add_mate_connector(...)` — define mate points on parts
- `add_mate(assembly_id, mate_type, connector1, connector2)` — fasten/revolute/slider
- `set_part_transform(assembly_id, instance_id, transform_matrix)` — position part
- `create_part_studio_feature(document_id, workspace_id, element_id, featurescript)` — push FS

### 1c. Positioning Strategy

The assembly composer already outputs positions in inches from frame center.
Convert these to OnShape transform matrices:

```python
def placement_to_transform(placement, frame_spec):
    """Convert assembly composer placement to 4x4 transform matrix."""
    # Translate from center-origin inches to mm
    tx = placement.position_in[0] * 25.4
    ty = placement.position_in[1] * 25.4
    tz = placement.position_in[2] * 25.4
    return [
        1, 0, 0, tx,
        0, 1, 0, ty,
        0, 0, 1, tz,
        0, 0, 0, 1
    ]
```

---

## Phase 2: Real Tube Frame

Replace fCuboid frame tubes with proper extrusions.

### 2a. Tube Profiles

```
2x1 tube: rectangular profile, 2" x 1" with 0.100" wall (WCP pattern)
1x1 tube: square profile, 1" x 1" with 0.063" wall
1x2 L-channel: L-profile for some cross members
```

**FeatureScript approach:**
```featurescript
// Instead of fCuboid for a rail:
skSolid("front_rail", {
    "sketch": skRectangle(2*inch, 1*inch, 0.100*inch),  // hollow rectangle
    "extrude": length_mm
});
```

### 2b. Frame Features

- **Module cutouts**: 3.75" square holes at each module location (from COTS mounting spec)
- **Bolt holes**: at module mounting pattern, cross member junctions, bellypan
- **Gusset plates**: triangular plates at rail-to-rail joints
- **Bellypan**: 1/8" polycarb sheet with mounting holes on ~3" grid

### 2c. Tube Stock from COTS

Frame tubes themselves are COTS (WCP, TTB, Vex versaframe). The resolver should
pull real tube stock profiles from FRCDesignLib when available.

---

## Phase 3: COTS Connector Selection + Minimal Custom Plates

Almost all connecting geometry in FRC is itself COTS. The system should SELECT
the right off-the-shelf connector rather than generate custom brackets.

### 3a. COTS Connector Catalog

Expand the COTS catalog with connecting hardware:
```
Gussets:
  - WCP 90° gusset (2x1 to 2x1)
  - WCP 90° gusset (1x1 to 2x1)
  - WCP T-gusset
  - REV 90° bracket (15mm extrusion)
  - TTB gusset plates (various angles)
  - Andymark churro gussets

Motor Mounts:
  - WCP motor mount plate (Falcon/Kraken pattern)
  - REV MAXPlanetary mount plate
  - VersaPlanetary mount plate (Vex)
  - TTB motor mount

Bearing Blocks:
  - Thrifty bearing block (1/2" hex)
  - WCP bearing block (1/2" hex, 3/8" hex)
  - REV bearing pillow block
  - Vex VersaBlock

Shaft Retainers:
  - WCP shaft collar
  - REV shaft spacers
  - Snap rings + grooves

Extrusion Connectors (REV 15mm ecosystem):
  - Inside corner connector
  - T-connector
  - Pivot bracket
  - Hinge
  - End cap
```

### 3b. Connector Selection Logic

Given a joint type, the system picks the right COTS part:
```python
def select_connector(joint_type, tube_size_a, tube_size_b, angle_deg):
    """Select COTS gusset/bracket for a frame joint."""
    if angle_deg == 90 and tube_size_a == "2x1" and tube_size_b == "2x1":
        return "WCP 90° Gusset (2x1)"
    elif joint_type == "T":
        return "WCP T-Gusset"
    # etc.
```

### 3c. Minimal Custom Plates (the only generated geometry)

The 2-3 plates per robot that genuinely don't exist as COTS:
- **Elevator carriage plate** — bearing block pattern + end effector mount
- **Intake side plate** — pivot bore + roller bearing pattern
- **Shooter backplate** — flywheel bearing pattern + hood shape

These are simple rectangular plates with bolt holes. Generated as FeatureScript
with holes derived from the COTS parts they connect to.

---

## Phase 4: Mechanism-Specific COTS Assemblies

Each mechanism type maps to a known set of COTS parts. The blueprint generators
already know what parts are needed — extend them to output COTS part lists with
positions. Almost everything is a drop-in.

### 4a. Swerve Drivetrain
```
COTS: 4x swerve module, 4x drive motor, 4x steer motor,
      frame tubes (WCP/TTB), bellypan (polycarb sheet),
      gussets at every joint, tube plugs
Custom: module cutouts in rails (just holes in the tube extrusions)
```

### 4b. Intake
```
COTS: rollers (flex wheels/compliant wheels on hex shaft),
      bearings + bearing blocks (Thrifty/WCP),
      deploy motor + VersaPlanetary/MAXPlanetary,
      pivot shaft + bearings, gussets for frame mount
Custom: 2x side plates (rectangular with bearing bores + pivot bore)
```

### 4c. Flywheel Shooter
```
COTS: flywheel wheels (Colson/Stealth), motors, belt + pulleys,
      bearings + bearing blocks, shaft
Custom: 2x side plates, 1x backplate/hood
```

### 4d. Elevator
```
COTS: tube stock (inner/outer stages), bearing blocks (Thrifty),
      motors + gearbox, spool/pulley, rigging (dyneema),
      limit switches, hard stops
Custom: 1x carriage plate (bearing block bolt pattern + end effector mount)
```

### 4e. Climber
```
COTS: motors + gearbox, spool, strap/rope, shaft + bearings,
      bearing blocks, gussets for frame mount
Custom: hook (often 3D printed — could include STL template)
```

### 4f. Arm/Wrist
```
COTS: motors + planetary gearbox (VersaPlanetary/MAXPlanetary),
      hex shaft, bearings + bearing blocks, encoder,
      gas spring (optional), gussets
Custom: 1x arm tube (COTS tube stock cut to length), 1x pivot plate
```

**Pattern**: each mechanism is 80-90% COTS by part count. The custom parts are
almost always simple rectangular plates with a few bolt holes — trivial to
generate parametrically.

---

## Implementation Priority

```
Priority  Block                    Effort   Impact
──────────────────────────────────────────────────────
  P0      Part resolver             Medium   Unlocks all COTS insertion
  P0      Assembly builder          Medium   Creates real OnShape assemblies
  P1      Real tube frame           Low      Huge visual + functional upgrade
  P1      Swerve assembly           Low      4 modules + motors, most visible
  P1      COTS connector catalog    Low      Gussets, brackets, bearing blocks
  P2      Elevator assembly         Medium   Most complex mechanism
  P2      Intake assembly           Medium   Second most common mechanism
  P3      Shooter/climber/arm       Medium   Remaining mechanisms
  P3      Minimal custom plates     Low      The 2-3 generated plates per mech
```

**P0 is the foundation** — without part resolution and assembly creation, nothing
else works. Once P0 is done, each mechanism is just adding COTS parts to the
catalog and writing placement logic. The connecting geometry problem largely
disappears because gussets, brackets, and bearing blocks are COTS too.

---

## File Structure (Planned)

```
blueprint/
  cad_builder.py          ← extend with assembly mode
  part_resolver.py        ← NEW: FRCDesignLib → OnShape document IDs
  part_cache.json         ← NEW: cached resolutions
  assembly_builder.py     ← NEW: OnShape assembly API orchestration
  cots_catalog.json       ← extend with connectors + mate locations
```

No `bracket_templates.py` needed — the connecting geometry is COTS.
The only generated geometry is the frame tubes (FeatureScript extrusions)
and 2-3 simple plates per mechanism (FeatureScript rectangles with holes).

---

## COTS Catalog Extensions Needed

Each catalog entry needs:
```json
{
  "mate_connectors": [
    {
      "name": "frame_mount",
      "type": "planar",
      "origin_mm": [0, 0, 0],
      "normal": [0, 0, 1],
      "bolt_pattern": "4x #10-32 on 95.25mm square"
    },
    {
      "name": "output_shaft",
      "type": "cylindrical",
      "origin_mm": [0, 0, -82.55],
      "axis": [0, 0, 1],
      "diameter_mm": 50.8
    }
  ]
}
```

This tells the assembly builder where and how each COTS part connects to
adjacent parts — the critical data for automated mating.

---

## Success Criteria

When this evolution is complete, the pipeline should:

1. **Output a real OnShape assembly** with named subassemblies per mechanism
2. **Use actual FRCDesignLib parts** — swerve modules, motors, bearings look real
3. **Generate only the custom parts** — plates and brackets, not COTS geometry
4. **Support part swaps** — change "SDS MK4i" to "Thrifty Swerve" and the
   frame cutouts, bolt patterns, and positions all update automatically
5. **Export a real BOM** from the OnShape assembly that matches the Blueprint BOM
6. **Be usable on day 1 of build season** — team opens the link and has a
   starting-point assembly they can immediately refine

The goal is not to replace CAD designers — it's to give them a 2-hour head start
instead of starting from an empty document.
