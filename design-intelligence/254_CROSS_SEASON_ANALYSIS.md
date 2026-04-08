# THE ENGINE — Phase 5: Team 254 Cross-Season Analysis
# Extracted from Technical Binders: 2019, 2022, 2024, 2025
# (2018, 2020, 2023 binders are image-based PDFs — need manual extraction)

## 254's Consistent Design Patterns

### 1. Game Analysis Structure (Every Year)
- Split into groups to brainstorm strategies post-kickoff
- Review game manual line by line
- Create must-have / nice-to-have / explore priority matrix
- Ranking point optimization drives all design decisions
- "Win the championship" is the explicit design goal, not "do our best"

### 2. Drivetrain Evolution
| Year | Game | Drive Type | Modules | Motors | Speed | Frame |
|------|------|-----------|---------|--------|-------|-------|
| 2019 | Deep Space | West Coast 6-wheel | Custom 2-speed | 4x NEO | 8.3/13.5 ft/s | 28"x27.5" |
| 2022 | Rapid React | Swerve (FIRST TIME) | SDS MK4i L3 | Falcon 500 | 18 ft/s | 27"x27" |
| 2024 | Crescendo | Swerve | SDS MK4i L3 | Kraken X60 FOC | 18 ft/s | 27"x27" |
| 2025 | Reefscape | Swerve | WCP X2i | Kraken X60 | 13.2 ft/s | 29.5"x29.5" |

**Pattern:** 254 switched to swerve in 2022 and never went back. They optimized speed
down in 2025 (13.2 ft/s vs 18 ft/s) because Reefscape had short cycles where
acceleration matters more than top speed. Frame size increased in 2025 for stability.

### 3. Intake Patterns
| Year | Game Piece | Intake Type | Width | Deploy | Key Feature |
|------|-----------|-------------|-------|--------|-------------|
| 2019 | Hatch + Cargo | Arm-mounted jaws + roller | Robot width | Arm positions | Flex wheels for hatch centering |
| 2022 | Balls | Dual over-bumper | Full width | Pneumatic 4-bar | Mecanum + funneling wheels |
| 2024 | Notes (frisbee) | Under-bumper | Full width | Always deployed | Mecanum side funneling |
| 2025 | Coral (PVC pipes) | Over-bumper with 4-bar | Full width | Kraken deploy <0.15s | Silicone on foam rollers, floating front roller |

**Pattern:** ALWAYS full-width intake. "Touch it, own it" is a recurring phrase in every
binder. Side funneling (mecanum or angled wheels) appears in 2022+ to handle pieces
arriving at angles. Under-bumper preferred for impact protection (2024), over-bumper
when game piece geometry requires it (2022, 2025).

### 4. Scorer/Shooter Patterns
| Year | Scoring Method | Key Mechanism | Motor Count | Speed/Range |
|------|---------------|---------------|-------------|-------------|
| 2019 | Placement | 4-DOF arm (turret+elevator+shoulder+wrist) | 5x 775pro | N/A (placement) |
| 2022 | Flywheel shooter | Turret + adjustable hood | 2x Falcon + 1x Falcon hood | 15ft range, shoot-on-move |
| 2024 | Flywheel shooter | Turret + adjustable hood | 2x Kraken + 1x Kraken hood | Variable range, trap scoring |
| 2025 | Placement | Elevator + wrist end effector | 2x Kraken elevator, 1x Kraken wrist | <0.3s full travel |

**Pattern:** When game requires ranged scoring (balls) → turret + flywheel with adjustable
hood. When game requires precise placement (hatches, coral) → elevator + wrist.
Turret appears in ALL years 2019-2024 — 254 loves turrets because they decouple
scoring direction from driving direction. 2025 dropped turret because Reefscape scoring
was always at the same field positions (Reef pipes).

### 5. Elevator Patterns
| Year | Stages | Travel | Motors | Speed | Drive |
|------|--------|--------|--------|-------|-------|
| 2019 | 1-stage | ~24" | 3x 775pro | 5.47 ft/s | #25 chain |
| 2022 | 1-stage | 17" | 1x Falcon | <1s | #25 chain |
| 2024 | 1-stage | 17" | 1x Kraken | <1s | Belt |
| 2025 | 2-stage continuous | 52" | 2x Kraken X60 | 0.3s full travel | 9mm HTD belt inside tubes |

**Pattern:** Single-stage when height requirement is <24". Two-stage when >24".
Belt-driven in later years (moved from chain). Speed target: ALWAYS under 1 second
for full travel. 2025 used 2x Kraken for the heavier 2-stage lift. Aluminum tube
construction (2x1x1/16") is universal.

### 6. Climber Patterns
| Year | Type | Travel | Speed | Key Feature |
|------|------|--------|-------|-------------|
| 2019 | Suction pad + vacuum pump | N/A | <3s | Hangs off edge of platform, leaves room for partners |
| 2022 | Elevator + stinger + reaction arm | Traversal bar | <10s | Inventive 3-phase climb sequence |
| 2024 | Hook arms + gas spring + winch | 16" lift | <2s | Dyneema rope, single Kraken |
| 2025 | Roller claw + latch + winch | Deep cage | <2s | Flex wheel claw grabs pipe, 1:224 gearbox |

**Pattern:** Climber is always the LAST thing designed. They don't prototype the climber
until the scoring mechanisms are locked. Climber target: <2 seconds engagement.
Dyneema rope and gas springs are recurring components. Ratchet/pawl mechanisms
hold the robot up after match ends (passive retention).

### 7. Software Patterns (Consistent Across All Years)
- **Centralized state machine** controlling all subsystem interactions
- **Vision-assisted auto-alignment** for scoring (Limelight in every year)
- **Goal tracking** — robot remembers target position even when camera can't see it
- **Feedforward-dominant control** for shooters and turrets
- **Field-relative control** for driving
- **Pre-generated paths** for autonomous (quintic splines in 2019, trajectory optimization in 2022+)
- **Motion planning** for multi-DOF superstructure to prevent collisions (2019 explicitly)
- **Simulation** appeared in 2025 for the first time (maple-sim + AdvantageScope)

### 8. Sensor Patterns (Consistent)
- **Beam break sensors** at every handoff point (intake→indexer, indexer→scorer)
- **Absolute encoders** on all rotary joints (turret, wrist, climber claw)
- **Hall effect sensors** for elevator zeroing and soft stops
- **Limelight cameras** (1 in 2019, 1 in 2022, 2 in 2024-2025)
- **Current monitoring** implied but rarely discussed in binders
- **CANrange sensors** new in 2025 (mounted on swerve modules)

### 9. Weight and Size Patterns
| Year | Frame | Weight Target | Actual | CG Strategy |
|------|-------|--------------|--------|-------------|
| 2019 | 28"x27.5" | 90-110 lbs | Not stated | Low, square for scoring all sides |
| 2022 | 27"x27" | Low CG priority | Not stated | Battery centered, low bellypan |
| 2024 | 27"x27" | Low CG, wide base | Not stated | Battery opposite intake for balance |
| 2025 | 29.5"x29.5" | Maximize for traction | Not stated | Battery centered, bellypan at 5/8" |

**Pattern:** CG management is discussed in EVERY binder. Battery placement is always
strategic — centered or opposite the heaviest mechanism. Bellypan lowered as close
to ground as possible (0.5-0.625"). Frame is always square or near-square.

### 10. Design Process Patterns
- **AlphaBot / prototype robot** built in 2025 (1 week) using previous year's drivetrain
  to learn gameplay before competition robot is designed
- **Multiple design revisions** during season (2019 had V1 and V2 of arm and intake)
- **Subsystem prototyping** is extensive (2025 shows 4+ prototypes photographed)
- **"Former Designs" section** in 2019 documents what was tried and rejected

## Key Quantitative Benchmarks (From Binder Data)

| Metric | 2019 | 2022 | 2024 | 2025 |
|--------|------|------|------|------|
| Intake deploy time | Arm-based | Pneumatic | Always deployed | <0.15s |
| Elevator full travel | 5.47 ft/s | <1s | <1s | 0.3s for 52" |
| Shooter spin-up | N/A | Not stated | Not stated | N/A |
| Climber engage time | <3s suction | <10s full sequence | <2s | <1s engage + <1s winch |
| Auto scoring | 2 hatches | 5+ cargo | Not stated | 3+ coral |
| Swerve modules | N/A | SDS MK4i | SDS MK4i | WCP X2i |
| Motor count | ~12 | ~15 | 19 | 18 |
| Limelight count | 2 | 1 | 2 | 2 |

## Emerging Trends (2022 → 2025)

1. **Swerve is universal** — no going back to tank/WCD
2. **Kraken X60 replacing Falcon 500** — happened between 2022 and 2024
3. **Kraken X44 appearing** for low-power mechanisms (intake deploy, indexer, wrist)
4. **Simulation becoming standard** — 2025 is the first year 254 mentions maple-sim
5. **Scoring speed increasing** — elevator travel times dropped from <1s to 0.3s
6. **Intake complexity increasing** — from simple rollers to floating rollers on foam
7. **Frame size increasing** — from 27" to 29.5" for stability with heavier mechanisms
8. **2 Limelights becoming standard** — dual camera for better tag visibility

## 2025 Undertow Binder — Detailed Extraction (Full 27-Page Binder)

### Motor Census (18 total)
| Subsystem | Motor | Qty | Notes |
|-----------|-------|-----|-------|
| Drive | Kraken X60 (in WCP X2i) | 4 | 10T X1 reduction, ~13.2 ft/s |
| Steer | (in WCP X2i) | 4 | Gear-based azimuth (not belt) |
| Intake rollers | Kraken X44 | 1 | ~15 ft/s surface speed |
| Intake deploy | Kraken X44 | 1 | 10:36→14:42→14:56, ~0.15s |
| Indexer | Kraken X44 | 1 | 8:48T, ~30 ft/s surface speed |
| Elevator | Kraken X60 | 2 | 11:50T, 52" in 0.3s |
| Wrist | Kraken X44 | 1 | 210° in 0.2s, sector gear |
| End effector (coral+algae) | Kraken X44 | 1 | Shared motor, ~13 ft/s |
| Climber claw | Kraken X44 | 1 | 10:30T→15:28T |
| Climber winch | Kraken X60 | 1 | 1:224 gearbox |

### Sensor Census
- 2× Limelight 4 (with heatsinks and fans)
- CANrange sensors on swerve modules
- 2× Banner beam break (indexer front/rear)
- 2× Banner beam break (end effector)
- CANcoder on wrist pivot (1:1 absolute)
- CANcoder on climber claw
- Hall effect on elevator (zeroing)
- PDP 2.0

### Key Design Decisions (from Architecture page)
Three architectures were considered and REJECTED:
1. Wrist Dunk + Funnel + Passthrough
2. Dual Intakes flip-up to Laterator
3. Side Elevator with Intake, Funnel, Climber, and Wrist

The chosen architecture places intake on one end, elevator on the other,
with indexer and funnel feeding into the end effector from both sides.

### AlphaBot Lessons (built in 1 week using 2023 drivebase)
1. End effector without auto-align compliance misses coral
2. Pivoting arm + coordinated elevator/arm motion is SLOWER than driving into reef
3. Small roller claw too narrow for coral station intaking
4. Limelight cameras must be set back from corners to see tags near the reef
5. Electronics need shielding from dropped coral

### Software Architecture (confirmed from binder)
- A* and AD* pathfinding with real-time collision avoidance
- Pre-computed paths cached at robot init, merged with on-the-fly paths
- Simple mirror for red vs blue alliance
- Centralized state machine (3 modes: Coral, Algae/Climb, Coral Manual)
- MegaTag 1 (not MegaTag 2) for localization using both cameras
- Validation on tag count, area, ambiguity
- Falls back to swerve odometry when far from tags
- Heading controller with snap for auto-alignment
- Slew rate, velocity, and acceleration constraints
- maple-sim + AdvantageScope with imported 3D model, masses, MOI, gear ratios
- PhotonVision sim for AprilTag detection

### 2026 Robot "Overload" (REBUILT)
- Weight: 115 lbs (10 under max — lighter than 2025, suggests speed/agility game)
- Record: 32-2-0, #3 in CA district, won Silicon Valley + Central Valley events
- Sponsors include NVIDIA, Apple, Boeing, Google, SDS, WCP, Fabworks
- maple-sim fork updated Feb 2026 — confirmed continued simulation usage
- Tech binder expected September 2026 after Chezy Champs
