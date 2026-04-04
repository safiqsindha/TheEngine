# The Engine — FRC Team 2950 (The Devastators)
## 2026 Season Robot Code

---

## Quick Start

```bash
# Build and verify everything passes
./gradlew check

# Deploy to robot (connected via USB or ethernet)
./gradlew deploy

# Run simulation
./gradlew simulateJava
```

> Requires the WPILib JDK at `~/wpilib/2026/jdk/`. If the system Java is not found, prefix commands with `JAVA_HOME=~/wpilib/2026/jdk`.

---

## Game: 2026 REBUILT

Robots score **FUEL** (game pieces) into the **HUB** when it's active, and climb the **TOWER** at end game. The HUB alternates between active and inactive states — only score when active.

---

## Hardware

| Component | Part |
|-----------|------|
| Drivetrain | Thrifty Swerve (4 modules) |
| Drive/Steer motors | NEO Brushless via SPARK MAX |
| Gyro | ADIS16470 |
| Absolute encoders | Thrifty 10-pin (SPARK MAX data port) |
| Camera | Limelight 3 (AprilTag + neural detector) |
| Shooter | Dual NEO Vortex flywheel |
| Intake | 2-arm independent position PID + roller wheel |
| Conveyor | Belt + spindexer |
| Climber | Single NEO telescoping arm |

CAN IDs: see `CAN_ID_REFERENCE.md`
All hardware values: see `hardware_config.ini`

---

## Teleop Controls (Driver — Port 0)

| Button | Action |
|--------|--------|
| Left stick | Drive (field-relative) |
| Right stick X | Rotate |
| A | Zero gyro (robot facing away from driver) |
| Right bumper (hold) | Auto-align rotation to nearest AprilTag target |
| Left bumper (hold) | Auto-drive toward nearest detected game piece |
| Left trigger > 0.5 (hold) | Flywheel aim + auto-feed |
| X | Automated score sequence (vision-gated) |
| Y (hold) | Lock wheels in X pattern |
| POV Right/Down/Left/Up | Flywheel static shots (2400/2500/3000/3500 RPM) |
| Start | Reset to scenario start pose (simulation only) |
| B (hold) | LED diagnostic — blinks if vision has target |

---

## Autonomous Options

Select from the **Auto Chooser** on SmartDashboard before enable:

| Option | Description |
|--------|-------------|
| Leave Only *(default)* | Drive off the line via Choreo trajectory |
| Leave Only (Raw) | Direct motor command, no Choreo — tests swerve sim |
| Shoot Only | Spin up flywheel and feed for 19 seconds |
| Score + Leave | Shoot preloaded fuel, then drive off line |
| 2 Coral | Shoot, collect one game piece, return and shoot again |
| 3 Coral | Full two-cycle collection with three shots total |
| Full Autonomous | Strategy-driven loop: vision detects fuel → pathfind → score → repeat |

---

## Simulation

1. Run `./gradlew simulateJava`
2. The WPILib Sim GUI and AdvantageScope-compatible NT4 server start automatically
3. Select a **Practice Scenario** from SmartDashboard before enabling:
   - Full Auto – Blue / Red
   - Teleop – Blue Center / Red Center
   - Teleop – Blue Near Hub
   - Stress Test – Full Field
4. Press **Start button** on driver controller to teleport back to the start pose mid-session

---

## Code Structure

```
src/main/java/frc/
  robot/
    Robot.java              — Entry point, AdvantageKit init, mode hooks
    RobotContainer.java     — All subsystem + command wiring, button bindings
    Constants.java          — Every tuning constant, organized by subsystem
    DriverPracticeMode.java — Simulation scenario selector
    Helper.java             — Limelight IIR filters, RPM-from-distance lookup
    commands/
      DriveCommand.java             — Default field-relative teleop drive
      AutoAlignCommand.java         — AprilTag rotation assist (right bumper)
      DriveToGamePieceCommand.java  — Game piece seek (left bumper)
      AutoScoreCommand.java         — Full vision-gated scoring sequence
      PathfindToGoalCommand.java    — Autonomous pathfinding wrapper
      FullAutonomousCommand.java    — Strategy loop for Full Autonomous mode
      ChoreoAutoCommand.java        — Trajectory-following routines
    subsystems/
      SwerveSubsystem.java          — YAGSL swerve wrapper
      VisionSubsystem.java          — Limelight MegaTag2 + neural detector
      FuelDetectionConsumer.java    — llpython array parser (80% confidence, 3-frame)
      SuperstructureStateMachine.java — IDLE/INTAKING/STAGING/SCORING/CLIMBING
      Flywheel / Intake / Conveyor / Climber / SideClaw / LEDs
    autos/
      AutonomousStrategy.java  — Utility scorer (CLIMB > SCORE > COLLECT)
      GameState.java           — Immutable snapshot fed to strategy each cycle
      ActionType.java / ScoredTarget.java
  lib/
    AllianceFlip.java        — Mirror poses blue↔red
    pathfinding/
      NavigationGrid.java    — 164×82 navgrid.json occupancy grid
      AStarPathfinder.java   — 8-directional A*, <10ms on full grid
      DynamicAvoidanceLayer.java — Potential field obstacle avoidance
```

---

## Testing

```bash
# Run all 56 unit tests
./gradlew test

# Run tests + generate coverage report
./gradlew test jacocoTestReport
# Report: build/reports/jacoco/test/html/index.html

# Full check (format + static analysis + tests + coverage gate)
./gradlew check
```

**Coverage requirement:** `frc.lib.*` must stay above 80% line coverage. The build fails otherwise.

Every new feature needs tests in `src/test/java/frc/`. Name test classes `ClassUnderTestTest` and test methods `testMethod_scenario_expectedResult`.

---

## Adding a Feature

1. Read `ARCHITECTURE.md` — locked decisions are non-negotiable
2. Write the feature code in `src/main/java/frc/robot/`
3. Write tests in `src/test/java/frc/`
4. Run `./gradlew check` — must pass before any commit
5. Update `PROGRESS.md` with what you built

---

## Analysis Tools

After a sim run, export the WPILOG from AdvantageScope and run:

```bash
python3 tools/extract_cycles.py     <log.json>   # Scoring cycle timing
python3 tools/analyze_path_error.py <log.json>   # Path deviation vs commanded
python3 tools/battery_analysis.py   <log.json>   # Voltage sag correlation
```

---

## Key References

- `ARCHITECTURE.md` — architectural decisions, class contracts, naming conventions
- `PROGRESS.md` — what's built and what's pending
- `CAN_ID_REFERENCE.md` — full hardware CAN map
- `hardware_config.ini` — all verified hardware values (gear ratios, PID, CAN IDs)
- `VENDORDEP_URLS.md` — library download URLs
