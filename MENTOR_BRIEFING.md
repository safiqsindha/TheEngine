# The Engine — Programming Mentor Briefing
# FRC Team 2950 — The Devastators — 2026 Season (REBUILT)

> **Purpose:** This document is a complete technical briefing for the programming
> mentor. It covers what the students originally built, what The Engine added on
> top of it, how the pieces fit together, and what still needs to happen on
> hardware before competition deployment.

---

## 1. What the Students Originally Built

The kids wrote a working swerve-drive robot codebase from scratch. Their
foundation was solid and hardware-verified:

**What they had:**
- YAGSL-based swerve drive (4 Thrifty Swerve modules, NEO motors, SPARK MAX controllers)
- ADIS16470 gyro on roboRIO SPI
- Teleop drive with field-relative control (Xbox controller)
- Basic subsystem classes for all mechanisms:
  - Flywheel (2x NEO Vortex + 2x feed wheels)
  - Intake (2x arm motors + 1x wheel motor)
  - Conveyor (belt + spindexer)
  - Climber
  - SideClaw
  - LEDs (60-LED strip)
- Manual teleop commands for each subsystem (trigger-scaled, POV presets)
- Limelight integration for AprilTag detection
- A `Helper.java` utility class for RPM lookups and Limelight helpers
- Hardware configs verified on the actual robot (CAN IDs, gear ratios, PID values)
- AdvantageKit logging scaffold (LoggedRobot base class)

**What they did NOT have:**
- No autonomous routines (no trajectory following, no path planning)
- No vision-aided pose estimation (Limelight was connected but not fusing into odometry)
- No game piece detection (no neural network, no YOLO)
- No automated scoring sequences
- No state machine coordinating mechanisms
- No unit tests
- No build quality gates (no formatter, no static analysis, no coverage)
- No simulation support beyond basic WPILib sim

---

## 2. What The Engine Added (11 Major Upgrades)

### Layer 1: Foundation Hardening

**Upgrade 1 — Build Quality Gates**
- Google Java Format via Spotless (auto-formats on every build)
- SpotBugs static analysis (medium confidence, catches null pointer risks)
- JaCoCo code coverage (80% minimum gate on `frc.lib` package)
- JUnit 5 test framework with 181 automated tests
- All tests run without HAL native libraries (pure Java, no robot hardware needed)

**Upgrade 2 — Vision Pose Estimation**
- Limelight MegaTag2 integration with WPI blue-origin coordinates
- 5-layer validation: tag count, latency, distance, field bounds, odometry delta
- Distance-based standard deviation scaling:
  - XY: `0.5 * dist^2 / sqrt(tagCount)` — quadratic penalty for far tags
  - Theta: `0.1` for 2+ tags, `0.5 * dist` for single tag
- Fused into YAGSL's Kalman filter with timestamp compensation

**Upgrade 3 — Brownout Protection**
- Battery voltage monitoring with two thresholds (warn at 12V, critical at 6.5V)
- Linear motor output scaling from 100% at 8V down to 50% at 6V
- Applied to all drive commands automatically
- CAN bus utilization logging

### Layer 2: Autonomous Intelligence

**Upgrade 4 — Superstructure State Machine**
- Coordinates intake/conveyor/flywheel/scoring pipeline
- States: IDLE, INTAKING, STAGING, SCORING, CLIMBING
- Commands query state rather than directly controlling motors
- Pure-function `computeNextState()` for unit testing without HAL

**Upgrade 5 — Pathfinding Stack**
- `NavigationGrid`: 164x82 cell occupancy grid (10cm resolution, loaded from JSON)
- `AStarPathfinder`: 8-directional A* search, <10ms on full grid
- `DynamicAvoidanceLayer`: Potential-field opponent repulsion (attractive gain 1.0, repulsive gain 1.5)
- `PathfindToGoalCommand`: Integrates A* with PathPlannerLib AD* for smooth trajectories
- Dynamic obstacle injection: opponent positions stamped as 1m obstacles each cycle

**Upgrade 6 — Decision Engine**
- `AutonomousStrategy`: Utility-based target ranking (SCORE, COLLECT, CLIMB)
- `GameState`: Immutable snapshot of robot pose, fuel held, time remaining, detections
- Time-aware: CLIMB priority escalates in last 15 seconds
- Distance-weighted: closer targets score higher
- Bot Aborter: cancels target if opponent will arrive 0.75s before robot

**Upgrade 7 — Full Autonomous Loop**
- `FullAutonomousCommand`: evaluate-pathfind-execute-repeat loop
- Re-evaluates every 0.5 seconds
- Retargets if a significantly better option appears (utility delta > 5.0)
- Integrates all three reactive layers (avoidance, aborter, dynamic obstacles)
- Graceful degradation: works with no vision, no fuel detection, no opponents

### Layer 3: Teleop Assist

**Upgrade 8 — Auto-Align**
- Hold right bumper: robot auto-rotates to face nearest AprilTag
- Driver retains full translation control
- P-gain heading correction (0.05)

**Upgrade 9 — Drive-to-Game-Piece**
- Hold left bumper: robot auto-translates toward nearest detected fuel
- Driver retains full rotation control
- Proportional approach with 0.5m arrival threshold

**Upgrade 10 — Auto-Score Sequence**
- Vision-gated: waits for 1-second continuous AprilTag lock before scoring
- Sequences superstructure through INTAKING -> STAGING -> SCORING
- 5-second timeout safety

### Layer 4: Detection & Tools

**Upgrade 11 — YOLO Fuel Detection Pipeline**
- Wave Robotics YOLOv11n model (2.59M params, single class: fuel ball)
- Exported to ONNX (10.1 MB, 640x640 input, opset 12)
- Limelight SnapScript with ONNX inference + HSV color fallback
- `FuelDetectionConsumer`: 80% confidence filter, 3-frame persistence, 8 max detections
- Field-relative coordinate projection from camera geometry + robot pose

**Competition Tools:**
- `pre_match_check.py`: NT4 health check (battery, CAN, vision, gyro, auto selection)
- `EncoderCalibrationCommand`: Copy-paste swerve encoder offsets for hardware_config.ini
- 5 analysis scripts for post-match log review (cycle times, path error, battery)

---

## 3. Architecture — How It Fits Together

```
                    ┌─────────────────────┐
                    │    RobotContainer    │  ← Button bindings, auto chooser
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
      ┌──────────────┐ ┌────────────┐ ┌──────────────────┐
      │ DriveCommand  │ │ AutoScore  │ │ FullAutonomous   │
      │ (teleop)      │ │ Command    │ │ Command          │
      └──────┬───────┘ └─────┬──────┘ └────────┬─────────┘
             │               │                  │
             ▼               ▼                  ▼
      ┌──────────────┐ ┌──────────┐  ┌──────────────────┐
      │ SwerveSubsys │ │   SSM    │  │ AutonomousStrategy│
      │ (YAGSL)      │ │ (states) │  │ (decision engine) │
      └──────┬───────┘ └──────────┘  └────────┬─────────┘
             │                                 │
             ▼                                 ▼
      ┌──────────────┐               ┌──────────────────┐
      │ VisionSubsys │               │  A* Pathfinder   │
      │ (Limelight)  │               │  + NavGrid       │
      └──────┬───────┘               │  + Avoidance     │
             │                        └──────────────────┘
             ▼
      ┌──────────────┐
      │ FuelDetection│
      │ Consumer     │
      └──────────────┘
```

**Key design rules:**
1. YAGSL owns all swerve math — no custom kinematics
2. REV SPARK MAX runs all PID loops onboard — no software PID on roboRIO
3. AdvantageKit logs everything — every subsystem publishes to NT4
4. All new code has unit tests — 181 tests, zero HAL dependencies
5. Spotless + SpotBugs + JaCoCo enforced on every `./gradlew check`

---

## 4. File Map — Where to Find Things

```
constructicon/
├── src/main/java/frc/
│   ├── robot/
│   │   ├── Robot.java                    ← Match phase logging, brownout monitoring
│   │   ├── RobotContainer.java           ← All button bindings + auto chooser (7 routines)
│   │   ├── Constants.java                ← All tuning constants (speeds, PIDs, CAN IDs)
│   │   ├── Helper.java                   ← RPM lookups, Limelight helpers
│   │   │
│   │   ├── subsystems/
│   │   │   ├── SwerveSubsystem.java      ← YAGSL wrapper + vision fusion + sim bypass
│   │   │   ├── VisionSubsystem.java      ← MegaTag2 + YOLO pipeline switching
│   │   │   ├── SuperstructureStateMachine.java  ← IDLE/INTAKING/STAGING/SCORING/CLIMBING
│   │   │   ├── FuelDetectionConsumer.java       ← llpython parser + persistence filter
│   │   │   ├── Flywheel.java, Intake.java, Conveyor.java, Climber.java, etc.
│   │   │   └── LEDs.java                 ← Priority-based LED animations
│   │   │
│   │   ├── commands/
│   │   │   ├── DriveCommand.java         ← Teleop drive + brownout scaling
│   │   │   ├── AutoAlignCommand.java     ← Right bumper: auto-rotate to AprilTag
│   │   │   ├── DriveToGamePieceCommand.java  ← Left bumper: drive toward fuel
│   │   │   ├── AutoScoreCommand.java     ← Vision-gated scoring sequence
│   │   │   ├── FullAutonomousCommand.java    ← Decision-driven auto loop
│   │   │   ├── PathfindToGoalCommand.java    ← A* + PathPlannerLib trajectory
│   │   │   ├── ChoreoAutoCommand.java    ← Choreography trajectory following
│   │   │   ├── EncoderCalibrationCommand.java ← Hardware bring-up tool
│   │   │   └── Flywheel*.java, IntakeControl.java, etc.  ← Mechanism commands
│   │   │
│   │   └── autos/
│   │       ├── AutonomousStrategy.java   ← Utility-based target ranking
│   │       ├── GameState.java            ← Immutable game snapshot
│   │       ├── ScoredTarget.java         ← (action, pose, utility) record
│   │       └── ActionType.java           ← SCORE, COLLECT, CLIMB enum
│   │
│   └── lib/pathfinding/
│       ├── NavigationGrid.java           ← 164x82 cell occupancy grid
│       ├── AStarPathfinder.java          ← 8-directional A* search
│       └── DynamicAvoidanceLayer.java    ← Potential-field opponent avoidance
│
├── src/test/java/frc/                    ← 17 test classes, 181 tests
│
├── tools/
│   ├── wave_fuel_detector.onnx           ← YOLOv11n model (10.1 MB)
│   ├── snapscript_fuel_detector.py       ← Limelight SnapScript (ONNX inference)
│   ├── pre_match_check.py                ← NT4 pre-match health check
│   ├── generate_configs.py               ← Regenerate YAGSL JSON from hardware_config.ini
│   └── analyze_*.py, extract_*.py        ← Post-match log analysis
│
├── hardware_config.ini                   ← Single source of truth for CAN IDs + offsets
├── CAN_ID_REFERENCE.md                   ← Human-readable CAN bus map
├── PROGRESS.md                           ← Phase-by-phase completion tracking
├── WHAT_WE_BUILT.md                      ← Student-facing summary
└── design-intelligence/
    ├── ARCHITECTURE.md                   ← Design decisions + package structure
    ├── YOLO_TRAINING_GUIDE.md            ← Neural network deployment guide
    └── AUTONOMOUS_DESIGN.md              ← Decision engine explanation
```

---

## 5. What Still Needs Hardware

These items CANNOT be completed in simulation. They require physical access to
the robot:

| Task | What to Do | Time |
|------|-----------|------|
| **Encoder calibration** | Point wheels forward, run `EncoderCalibrationCommand` in Test mode, copy offsets into `hardware_config.ini`, run `generate_configs.py`, redeploy | 15 min |
| **Flash SideClaw SPARK MAX** | REV Hardware Client: change CAN ID from 18 to 20 | 5 min |
| **Limelight model upload** | Upload `wave_fuel_detector.onnx` + `snapscript_fuel_detector.py` via Limelight web UI | 10 min |
| **Choreo trajectories** | Create `.traj` files in Choreo GUI using real field measurements | 1-2 hrs |
| **Vision std-dev tuning** | Drive at known positions, compare odometry vs vision pose in AdvantageScope | 30 min |
| **Autonomous weight tuning** | Run practice matches, review AdvantageKit logs, adjust `AutonomousStrategy` gains | Multiple sessions |

---

## 6. What's Safe to Deploy vs. What Needs Testing

### Safe to deploy immediately (no behavior change risk):
- Build quality gates (Spotless, SpotBugs, JaCoCo)
- AdvantageKit logging enhancements (battery, CAN, match phase)
- Brownout protection (only reduces motor output under voltage stress)
- Pre-match health check script
- LED priority system

### Needs on-robot testing before competition:
- Vision pose estimation (std-dev tuning is critical)
- Teleop assist commands (AutoAlign, DriveToGamePiece)
- Auto-score sequence (vision lock timing)
- Superstructure state machine (mechanism coordination)

### Needs significant practice time:
- Full autonomous loop (decision engine + pathfinding)
- YOLO fuel detection pipeline
- Choreo trajectory following

---

## 7. How to Read the Code (for the Mentor)

**Start here:**
1. `RobotContainer.java` — All button bindings and the auto chooser. This shows
   what the driver does and what autonomous options exist.
2. `Constants.java` — Every tuning value in one place. CAN IDs, speeds, PIDs,
   thresholds.
3. `SwerveSubsystem.java` — The YAGSL wrapper. The `drive()` method, vision
   fusion, and sim bypass are all here.

**Then follow the autonomous stack:**
4. `FullAutonomousCommand.java` — The top-level loop. Read `execute()` to see
   the evaluate-pathfind-execute cycle.
5. `AutonomousStrategy.java` — How targets are ranked. The utility functions
   are straightforward math.
6. `AStarPathfinder.java` — Standard A* with 8-directional movement. Well-tested.

**Test coverage proves behavior:**
- Every public method in the autonomous stack has unit tests
- Tests are pure Java (no HAL) — you can run them on any machine with:
  ```bash
  JAVA_HOME=~/wpilib/2026/jdk ./gradlew test
  ```

---

## 8. Questions the Mentor Will Probably Ask

**Q: Can I just deploy this as-is for competition?**
A: The teleop drive, brownout protection, logging, and build gates are safe.
The autonomous features need on-robot testing first. See Section 6.

**Q: Will this break the students' existing teleop?**
A: No. The teleop commands are the same as before, with two additions:
brownout scaling (invisible to the driver unless battery is dying) and two
assist commands on bumper buttons (optional — driver can ignore them).

**Q: How do I run the tests?**
A: `JAVA_HOME=~/wpilib/2026/jdk ./gradlew check` — runs all 181 tests plus
formatting, static analysis, and coverage. Takes about 7 seconds.

**Q: What if the YOLO model doesn't work at competition?**
A: The SnapScript has an automatic HSV color fallback. The autonomous loop
also works without any fuel detection — it just won't seek game pieces.

**Q: What's the simulation story?**
A: maple-sim 0.4.0-beta provides physics. There's a known issue where motor
forces don't integrate correctly in the physics engine — we added a kinematic
bypass that manually integrates pose from commanded speeds. It works for
basic driving in sim but isn't physics-accurate. The sim has 6 practice
scenarios selectable from SmartDashboard.
