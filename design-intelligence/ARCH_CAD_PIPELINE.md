# THE ENGINE — Autonomous CAD Pipeline
# Codename: "The Blueprint"
# Full Scope: 120-150 hours (with library acceleration)
# From game reveal to complete OnShape assembly in hours, not weeks
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

On kickoff day, the prediction engine outputs mechanism recommendations.
The CAD Pipeline turns those recommendations into parametric OnShape
assemblies automatically. The human designs the game-specific end
effector. The pipeline handles everything that is the same every year.

**The goal is not to replace CAD designers. It is to give them a 3-day head start.**

---

## Five-Layer Architecture

| Layer | Name | Input | Output |
|-------|------|-------|--------|
| 5 | Assembly Composer | Subsystem assemblies + frame | Complete robot assembly with BOM |
| 4 | Subsystem Generator | Template ID + parameters | Elevator, intake, climber assemblies |
| 3 | Frame Generator | Dimensions + module type | Drivebase (frame + swerve + electronics) |
| 2 | COTS Resolver | Part name + spec | OnShape element ID from MKCad |
| 1 | Prediction Bridge | KICKOFF_TEMPLATE output | Architecture spec (JSON) |

---

## Existing Libraries That Accelerate This

The original estimate was 258 hours. These libraries cut it roughly in half:

| Resource | What It Replaces | Time Saved | Notes |
|----------|-----------------|------------|-------|
| **[OnShape REST API](https://onshape-public.github.io/docs/)** + **[onshape-client](https://pypi.org/project/onshape-client/)** | Raw HTTP auth + part studio manipulation. Official Python SDK handles auth, configurations, assemblies, feature calls. | ~8h | `pip install onshape-client` |
| **[MKCad](https://www.chiefdelphi.com/t/mkcad-2024-season-updates/447692)** | Modeling COTS parts from scratch. SPARK MAX, NEO, Thrifty Swerve, gussets, bearings, etc. all exist as OnShape documents. Insert by reference instead of modeling. | ~30h | OnShape plugin (free) |
| **[Julia Schatz FeatureScripts](https://www.juliaschatz.com/featurescripts)** | Writing custom tube generation, gusset patterns, bearing hole patterns. These are parametric building blocks that already exist and are widely used by top FRC teams. | ~20h | OnShape FeatureScripts (free) |
| **[ReCalc](https://www.reca.lc/)** | Manual physics validation. Validates elevator/arm/drivetrain specs before generating CAD. Feed prediction engine output through ReCalc first, then generate geometry from validated specs. | Prevents rework | Web tool (free) |
| **Existing parametric swerve templates** | Building a swerve base from zero. Multiple teams publish parametric swerve bases on OnShape. Fork the best one, configure for your module type. | ~12h | Search OnShape public docs |
| **[AMB Design Spreadsheet](https://ambcalc.com/)** | Manual gear ratio and motor calculations. Validates mechanism specs before CAD generation. | ~5h | Free spreadsheet |

**Net estimate with libraries: 120-150 hours** (down from 258).

---

## Technology Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| CAD Platform | OnShape (free edu license) | Available |
| CAD API | OnShape REST API (onshape-client Python SDK) | Available |
| COTS Library | MKCad (OnShape plugin) | Available |
| Automation | Julia Schatz FeatureScripts | Available |
| Calculator | ReCalc + AMB Design Spreadsheet | Available |
| Orchestration | Python 3.11+ | Needs dev |
| Templates | 12 parametric OnShape assemblies | Needs dev |
| COTS Lookup | JSON: part name → OnShape element ID | Needs dev |

---

## Subsystem Template Library (12 Templates)

### Priority A — Build First (cover 80%+ of FRC robots)

| Template | Parameters | Reference Robots | Hours (w/ libraries) |
|----------|-----------|-----------------|---------------------|
| **Swerve Frame** | Wheelbase, track width, bellypan, cross tubes, electronics | Every swerve robot | 12-20h |
| **Elevator: Single Stage** | Height, motors, tube, belt/chain | 254 (2022), Everybot | 8h |
| **Elevator: Two Stage** | Height, motors, tube, belt width | 254 (2025), 1323, 2056 | 10h |
| **Intake: Over-Bumper** | Width, rollers, deploy linkage | 254 (2025), 1323, 3847 | 8h |

### Priority B — Build Second (common mechanisms)

| Template | Parameters | Reference Robots | Hours (w/ libraries) |
|----------|-----------|-----------------|---------------------|
| **Intake: Under-Bumper** | Width, roller diameter, compression | 254 (2024), 4414 | 8h |
| **Intake: Fixed Full-Width** | Width, roller type, funnel angle | 3847, Everybot | 6h |
| **Climber: Hook + Winch** | Height, rope, gearbox ratio | 254 (2025), 1323 | 8h |
| **Wrist: Single Pivot** | Rotation, motor, gear ratio | 254 (2025), 2056 | 8h |

### Priority C — Build Third (specialized)

| Template | Parameters | Reference Robots | Hours (w/ libraries) |
|----------|-----------|-----------------|---------------------|
| **Climber: Telescope** | Extension, latch type | Everybot style | 6h |
| **Shooter: Dual Flywheel** | Wheel size, spacing, hood range | 254 (2022, 2024, 2026) | 8h |
| **Turret: Continuous** | Gear ratio, bearing, encoder | 254 (2022, 2024) | 8h |
| **Elevator: Cascade** | Height, motors, stages | 1690 (2025) | 10h |

---

## Development Roadmap

### Phase B.1: Foundation (6 hours) — April 2026
| Block | Task | Hours |
|-------|------|-------|
| B.1.1 | OnShape API auth + onshape-client Python setup | 3 |
| B.1.2 | Catalog MKCad parts we use (200+ parts lookup table) | 2 |
| B.1.3 | Test: create empty assembly via API, insert one MKCad part | 1 |

### Phase B.2: COTS Resolver + Frame Generator (24 hours) — May-June 2026
| Block | Task | Hours |
|-------|------|-------|
| B.2.1 | COTS Resolver: JSON mapping part name → OnShape element ID | 4 |
| B.2.2 | Find and fork best parametric swerve base on OnShape | 4 |
| B.2.3 | Julia Schatz tube generator for cross members | 4 |
| B.2.4 | Parametric bellypan (adjust to wheelbase/track width) | 4 |
| B.2.5 | Electronics layout (roboRIO, PDH, radio — standard positions) | 4 |
| B.2.6 | Validate: generate 3 different frame sizes | 4 |

**If existing swerve template is forkable with minimal changes, B.2 drops by ~8 hours.**

### Phase B.3: Priority A Templates (26 hours) — June-July 2026
| Block | Task | Hours |
|-------|------|-------|
| B.3.1 | Study 5 reference elevators (254, 1323, 2056, Everybot) | 4 |
| B.3.2 | Single-stage elevator: parametric tubes + bearing blocks + belt | 8 |
| B.3.3 | Two-stage elevator: second stage with continuous rigging | 10 |
| B.3.4 | Study 3 reference OB intakes (254, 1323, 3847) | 2 |
| B.3.5 | Over-bumper intake: roller bar + side plates + deploy pivot | 8 |
| B.3.6 | Validate all Priority A: generate 3 configs each | 4 |

*Note: B.3.1 and B.3.4 study hours are reduced because reference robots are already cataloged in design-intelligence docs.*

### Phase B.4: Priority B Templates (30 hours) — July-August 2026
| Block | Task | Hours |
|-------|------|-------|
| B.4.1 | Under-bumper intake: fixed rollers + compression adjustment | 8 |
| B.4.2 | Fixed full-width intake: funnel geometry + roller spacing | 6 |
| B.4.3 | Hook + winch climber: hook geometry + spool + gearbox | 8 |
| B.4.4 | Single pivot wrist: rotation limits + counterbalance | 8 |

### Phase B.5: Priority C Templates (32 hours) — August-September 2026
| Block | Task | Hours |
|-------|------|-------|
| B.5.1 | Telescope climber: stages + latch mechanism | 6 |
| B.5.2 | Dual flywheel shooter: wheel spacing + hood range | 8 |
| B.5.3 | Continuous turret: bearing + encoder + slip ring routing | 8 |
| B.5.4 | Cascade elevator: multi-stage rigging + pulley routing | 10 |

### Phase B.6: Assembly Composer + BOM (20 hours) — October-November 2026
| Block | Task | Hours |
|-------|------|-------|
| B.6.1 | Prediction Bridge: JSON spec from KICKOFF_TEMPLATE output | 4 |
| B.6.2 | Assembly Composer: place subsystems on frame (Rule 17 spacing) | 8 |
| B.6.3 | BOM Generator: extract parts list via API, format JSON | 4 |
| B.6.4 | BOM cross-reference with The Vault inventory | 2 |
| B.6.5 | Dry run: generate full REBUILT robot from prediction spec | 2 |

### Phase B.7: Validation + Polish (12 hours) — November-December 2026
| Block | Task | Hours |
|-------|------|-------|
| B.7.1 | Dry run: generate Reefscape-style robot, compare to 254 | 4 |
| B.7.2 | Dry run: generate elevator-heavy robot, check fit | 4 |
| B.7.3 | Document: usage guide for kickoff day workflow | 2 |
| B.7.4 | Edge case testing: unusual combinations, constraints | 2 |

### Total: ~150 hours across 7 phases (April-December 2026)
### With strong library acceleration: ~120 hours

---

## What Stays Human

1. **End effector geometry** — game piece changes every year
2. **Intake compliance and roller material** — requires physical testing
3. **Packaging and wire routing** — experienced intuition
4. **Weight optimization** — pocketing, material selection
5. **Review and quality control** — every assembly reviewed before manufacturing
6. **Final adjustments** — assembly composer gets you 90%, human fine-tunes the last 10%

---

## Kickoff Day Workflow

```
Hour 0:00 — Watch game reveal
Hour 0:30 — Fill in KICKOFF_TEMPLATE.md
Hour 1:00 — Run prediction engine (17 rules)
Hour 1:30 — Search CAD Collection for reference robots
Hour 2:00 — Run Blueprint: prediction bridge → architecture JSON
Hour 2:15 — Run Blueprint: frame generator (wheelbase, track width)
Hour 2:30 — Run Blueprint: subsystem templates (elevator height, intake width, etc.)
Hour 3:00 — Run Blueprint: assembly composer (place subsystems on frame)
Hour 3:15 — Run Blueprint: BOM export → cross-reference The Vault → order list
Hour 3:30 — Order parts
Hour 4:00 — Teams receive: complete parametric CAD + task plan + parts ordered
```

CAD team starts with a complete robot assembly, not blank canvases.
They focus on end effector design (the game-specific part) from hour 4.
No other team at your level operates this way.

---

*Architecture document — The Blueprint | THE ENGINE | Team 2950 The Devastators*
