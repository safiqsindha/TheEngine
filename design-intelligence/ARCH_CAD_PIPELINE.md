# THE ENGINE — CAD Pipeline (Lite)
# Codename: "The Blueprint"
# Scoped: 55-70 hours (down from 258)
# From game reveal to parametric OnShape assembly in hours, not weeks
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

On kickoff day, the prediction engine outputs mechanism recommendations.
The CAD Pipeline turns those recommendations into parametric OnShape
assemblies. The human designs the game-specific end effector. The
pipeline handles everything that is the same every year.

**The goal is not to replace CAD designers. It is to give them a 3-day head start.**

**Lite scope:** 3 templates (swerve frame, elevator, over-bumper intake)
instead of 12. These cover 80%+ of FRC robots. Add more templates in
Year 2 if the first 3 prove useful.

---

## Three-Layer Architecture (Lite)

| Layer | Name | Input | Output |
|-------|------|-------|--------|
| 3 | Subsystem Generator | Template ID + parameters | Elevator or intake assembly |
| 2 | Frame Generator | Dimensions + module type | Drivebase (frame + swerve + electronics) |
| 1 | Prediction Bridge | KICKOFF_TEMPLATE output | Architecture spec (JSON) |

### What's Cut (Full Version Only)
- ~~Assembly Composer~~ (auto-merge subsystems onto frame — do manually)
- ~~COTS Resolver~~ (auto-lookup OnShape IDs — use MKCad manually)
- ~~Collision detection~~ (human review catches this)
- ~~9 additional templates~~ (turret, wrist, cascade elevator, under-bumper intake, etc.)
- ~~DXF/STL auto-export~~ (OnShape does this natively)

---

## Existing Libraries That Accelerate This

| Resource | What It Replaces | Time Saved | Notes |
|----------|-----------------|------------|-------|
| **[OnShape REST API](https://onshape-public.github.io/docs/)** + **[onshape-client](https://pypi.org/project/onshape-client/)** | Raw HTTP auth + part studio manipulation. Official Python SDK handles auth, configurations, assemblies, feature calls. | ~8 hours | `pip install onshape-client` |
| **[MKCad](https://www.chiefdelphi.com/t/mkcad-2024-season-updates/447692)** | Modeling COTS parts from scratch. SPARK MAX, NEO, Thrifty Swerve, gussets, bearings, etc. all exist as OnShape documents. Insert by reference. | ~30 hours of part modeling | OnShape plugin (free) |
| **[Julia Schatz FeatureScripts](https://www.juliaschatz.com/featurescripts)** | Writing custom tube generation, gusset patterns, bearing hole patterns from scratch. These are parametric building blocks that already exist. | ~20 hours | OnShape FeatureScripts (free) |
| **[ReCalc](https://www.reca.lc/)** | Manual physics validation. Validates elevator/arm/drivetrain specs before generating CAD. Feed prediction engine output through ReCalc first. | Prevents rework (significant) | Web tool (free) |
| **Existing parametric swerve templates** | Building a swerve base from zero. Multiple teams publish parametric swerve bases on OnShape. Fork one, configure for your module. | ~12 hours | Search OnShape public docs |

### The Key Insight

MKCad parts + Julia Schatz FeatureScripts + an existing swerve template
means the Frame Generator (B.2) is mostly **configuration, not creation**.
Your custom code is the glue: Prediction Engine JSON → OnShape API calls →
configured assembly → BOM JSON.

**If you find a parametric swerve base on OnShape that's close enough to fork,
B.2 drops from 20 hours to ~8 hours. Total drops to ~55 hours.**

---

## Technology Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| CAD Platform | OnShape (free edu license) | Available |
| CAD API | OnShape REST API (onshape-client Python SDK) | Available |
| COTS Library | MKCad (OnShape plugin) | Available |
| FeatureScripts | Julia Schatz tube/gusset/bearing generators | Available |
| Physics Validation | ReCalc (web tool) | Available |
| Orchestration | Python 3.11+ | Needs dev |
| Templates | 3 parametric OnShape assemblies | Needs dev |

---

## Template Library (Lite — 3 Templates)

| Template | Parameters | Reference Robots | Why This One |
|----------|-----------|-----------------|-------------|
| **Swerve Frame** | Wheelbase, track width, bellypan, cross tubes, electronics layout | Every swerve robot | Every robot needs a frame. Build once, reuse forever. |
| **Elevator (1-stage + 2-stage)** | Height, motors, tube size, belt/chain, stages | 254 (2022, 2025), 1323, 2056, Everybot | Most common scoring mechanism in FRC history. |
| **Intake: Over-Bumper** | Width, roller count, deploy linkage, compression | 254 (2025), 1323, 3847 | Most common intake style since 2019. |

### What's Deferred to Year 2
| Template | When to Add |
|----------|------------|
| Intake: Under-Bumper | If a game rewards low intake |
| Wrist: Single Pivot | If the game needs an articulating end effector |
| Climber: Hook + Winch | After Year 1 climber is well understood |
| Turret: Continuous | If a game rewards 360° shooting |
| Shooter: Dual Flywheel | If a game has projectile scoring |

---

## Development Roadmap (Lite)

### Phase B.1: API + COTS Setup (6 hours)
| Block | Task | Hours |
|-------|------|-------|
| B.1.1 | OnShape API auth + onshape-client Python setup | 3 |
| B.1.2 | Catalog MKCad parts we use (SPARK MAX, NEO, Thrifty Swerve, bearings, gussets) | 2 |
| B.1.3 | Test: create empty assembly via API, insert one MKCad part | 1 |

### Phase B.2: Swerve Frame Generator (20 hours)
| Block | Task | Hours |
|-------|------|-------|
| B.2.1 | Find and fork best existing parametric swerve base on OnShape | 4 |
| B.2.2 | Add Julia Schatz tube generator for cross members | 4 |
| B.2.3 | Parametric bellypan (adjust to wheelbase/track width) | 4 |
| B.2.4 | Electronics layout (roboRIO, PDH, radio — standard positions) | 4 |
| B.2.5 | Validate: generate 3 different frame sizes, verify fits | 4 |

**If existing swerve template is forkable with minimal changes, B.2 drops to ~8 hours.**

### Phase B.3: Elevator Template (24 hours)
| Block | Task | Hours |
|-------|------|-------|
| B.3.1 | Study 5 reference elevators from CAD Collection (254, 1323, Everybot) | 4 |
| B.3.2 | Single-stage elevator: parametric tubes + bearing blocks + belt | 8 |
| B.3.3 | Two-stage extension: second stage with cascade or continuous rigging | 8 |
| B.3.4 | Validate: generate 3 heights (30", 48", 60"), check interference | 4 |

### Phase B.4: Over-Bumper Intake Template (12 hours)
| Block | Task | Hours |
|-------|------|-------|
| B.4.1 | Study 3 reference OB intakes (254, 1323, 3847) | 2 |
| B.4.2 | Parametric roller bar + side plates + deploy pivot | 6 |
| B.4.3 | Compression adjustment (gap between rollers and bumper) | 2 |
| B.4.4 | Validate: generate 2 widths, check bumper clearance | 2 |

### Phase B.5: BOM Export + Vault Integration (8 hours)
| Block | Task | Hours |
|-------|------|-------|
| B.5.1 | Extract part list from OnShape assembly via API | 3 |
| B.5.2 | Format as JSON: part name, quantity, vendor, est. cost | 2 |
| B.5.3 | Cross-reference with The Vault inventory (Google Sheet CSV) | 2 |
| B.5.4 | Output: order list (BOM minus inventory) | 1 |

### Total: 13 blocks, 55-70 hours, 2-3 months

---

## What Stays Human

1. **End effector geometry** — game piece changes every year
2. **Intake compliance** — roller material and compression require physical testing
3. **Packaging and wire routing** — experienced intuition
4. **Weight optimization** — pocketing, material selection
5. **Assembly review** — every generated assembly reviewed by a human before manufacturing
6. **Subsystem placement on frame** — done manually in OnShape (Assembly Composer is Year 2)

---

## Kickoff Day Workflow

```
Hour 0:00 — Watch game reveal
Hour 0:30 — Fill in KICKOFF_TEMPLATE.md
Hour 1:00 — Run prediction engine (17 rules)
Hour 1:30 — Search CAD Collection for reference robots
Hour 2:00 — Run Blueprint: frame generator (set wheelbase, track width)
Hour 2:30 — Run Blueprint: elevator template (set height from prediction)
Hour 3:00 — Run Blueprint: intake template (set width from prediction)
Hour 3:30 — Run BOM export → cross-reference The Vault → order parts
Hour 4:00 — Teams receive: parametric CAD assemblies + task plan + parts ordered
```

CAD team starts with complete subsystem assemblies, not blank canvases.
They focus on end effector design (the game-specific part) from hour 4.

---

## Future Expansion (Full Blueprint — Year 2+)

If the first 3 templates prove useful, expand:
- COTS Resolver (auto-lookup OnShape element IDs from part names)
- Assembly Composer (auto-place subsystems on frame with collision detection)
- Additional templates: under-bumper intake, wrist, climber, turret, shooter
- DXF/STL auto-export for CNC and 3D printing
- Estimated additional: ~180 hours across Year 2

---

*Architecture document — The Blueprint (Lite) | THE ENGINE | Team 2950 The Devastators*
