# THE ENGINE — Autonomous CAD Pipeline Architecture & Roadmap
# From game reveal to complete OnShape assembly in hours, not weeks
# April 2026 | Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

On kickoff day 2028, the prediction engine outputs mechanism recommendations.
The CAD Pipeline turns those recommendations into parametric OnShape assemblies
automatically. The human designs the game-specific end effector. The pipeline
handles everything that is the same every year.

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

## Technology Stack

| Component | Technology | Status |
|-----------|-----------|--------|
| CAD Platform | OnShape (free edu) | Available |
| CAD API | OnShape REST API (onshape-client) | Available |
| COTS Library | MKCad (OnShape plugin) | Available |
| Automation | Julia Schatz FeatureScripts | Available |
| Calculator | AMB Design Spreadsheet | Available |
| Orchestration | Python 3.11+ | Needs dev |
| Templates | 12 parametric OnShape assemblies | Needs dev |
| COTS Lookup | JSON: part name → OnShape ID | Needs dev |

## Subsystem Template Library (12 templates)

| Template | Parameters | Reference Robots |
|----------|-----------|-----------------|
| Elevator: Single Stage | Height, motors, tube, belt/chain | 254 (2022), Everybot |
| Elevator: Two Stage | Height, motors, tube, belt width | 254 (2025), 1323, 2056 |
| Elevator: Cascade | Height, motors, stages | 1690 (2025) |
| Intake: Over-Bumper | Width, rollers, deploy linkage | 254 (2025), 1323 |
| Intake: Under-Bumper | Width, roller diameter, compression | 254 (2024), 4414 |
| Intake: Fixed Full-Width | Width, roller type, funnel angle | 3847, Everybot |
| Wrist: Single Pivot | Rotation, motor, gear ratio | 254 (2025), 2056 |
| Wrist: Double Jointed | Shoulder + elbow, counterbalance | 254 (2023) |
| Climber: Hook + Winch | Height, rope, gearbox ratio | 254 (2025), 1323 |
| Climber: Telescope | Extension, latch type | Everybot style |
| Turret: Continuous | Gear ratio, bearing, encoder | 254 (2022, 2024) |
| Shooter: Dual Flywheel | Wheel size, spacing, hood range | 254 (2022, 2024, 2026) |

---

## Development Roadmap

### Phase 1: Foundation (Summer 2027, 62 hours)
| Block | Task | Hours |
|-------|------|-------|
| C.1 | OnShape API auth + Python client setup | 4 |
| C.2 | COTS Resolver: MKCad lookup table (200+ parts) | 12 |
| C.3 | Frame Generator: parametric drivebase | 20 |
| C.4 | Frame Generator: swerve module placement | 8 |
| C.5 | Frame Generator: bellypan + cross tubes | 8 |
| C.6 | Frame Generator: electronics layout | 6 |
| C.7 | Validation: 3 different frame sizes | 4 |

### Phase 2: Subsystem Templates (Fall 2027, 132 hours)
| Block | Task | Hours |
|-------|------|-------|
| C.8 | Study CAD Collection: catalog 20 elevators | 10 |
| C.9 | Elevator template: single stage | 16 |
| C.10 | Elevator template: two stage continuous | 20 |
| C.11 | Study CAD Collection: catalog 20 intakes | 10 |
| C.12 | Intake template: over-bumper deployable | 16 |
| C.13 | Intake template: under-bumper fixed | 12 |
| C.14 | Wrist template: single pivot | 12 |
| C.15 | Climber template: hook + winch | 12 |
| C.16 | Shooter template: dual flywheel | 12 |
| C.17 | Turret template: continuous rotation | 12 |

### Phase 3: Integration (December 2027, 56 hours)
| Block | Task | Hours |
|-------|------|-------|
| C.18 | Prediction Bridge: JSON spec generator | 8 |
| C.19 | Assembly Composer: subsystem placement (Rule 17) | 12 |
| C.20 | Assembly Composer: collision detection | 8 |
| C.21 | BOM Generator: parts list + vendor costs | 6 |
| C.22 | Export Pipeline: DXF + STL auto-export | 6 |
| C.23 | Dry run: generate REBUILT robot | 8 |
| C.24 | Dry run: generate Reefscape robot, compare to 254 | 8 |

### Phase 4: Live Deployment (January 2028 Kickoff, 8 hours)
Run the full pipeline live on kickoff day.

**Total: 25 blocks, 258 hours, 7 months**

---

## What Stays Human

1. End effector geometry (game piece changes every year)
2. Intake compliance and roller material (requires physical testing)
3. Packaging and wire routing (experienced intuition)
4. Weight optimization (pocketing, material selection)
5. Review and quality control (every assembly reviewed before manufacturing)
