# THE ENGINE — Architecture Reference
## FRC Team 2950 | 2026 Season

> **Purpose:** This document is the single source of truth for any AI agent (Cursor,
> Claude, etc.) generating code for this project. Read this BEFORE writing any code.

---

## 1. Project Identity

- **Project name:** The Engine
- **Team:** FRC 2950 (The Devastators)
- **Game:** 2026 REBUILT (FUEL scoring, HUB active/inactive shifts, TOWER climbing)
- **Language:** Java 17
- **Framework:** WPILib 2026, Command-Based
- **Build:** Gradle + GradleRIO 2026.2.1 (canonical version in `build.gradle`)

## 2. Hardware Configuration

| Component | Part | Interface |
|-----------|------|-----------|
| Swerve module | Thrifty Swerve | All steel gear, no belts |
| Drive motor (x4) | NEO Brushless (REV) | SPARK MAX via CAN bus |
| Steer motor (x4) | NEO Brushless (REV) | SPARK MAX via CAN bus |
| Motor controller (x8) | SPARK MAX (REV) | CAN bus |
| Absolute encoder (x4) | Thrifty 10-Pin Magnetic Encoder | SPARK MAX data port OR roboRIO analog input (TBD) |
| Relative encoder (x8) | NEO built-in hall-effect | Integrated in SPARK MAX |
| Gyroscope | **TBD** (see hardware_config.ini) | TBD |
| Drive gear ratio | **TBD** (6 options available) | — |
| Steer gear ratio | **TBD** | — |
| Wheel diameter | **TBD** (likely 4 inches) | — |

**CRITICAL:** This robot uses REV hardware (NEO + SPARK MAX), NOT CTRE (Kraken/TalonFX).
Motor control uses REVLib SparkPIDController (onboard SPARK MAX PID), NOT Phoenix 6.
YAGSL motor type is `"sparkmax_brushless"`, NOT `"talonfx"`.
The Thrifty encoder can connect to the SPARK MAX data port (type `"attached"`) or to
the roboRIO analog input (type `"thrifty"`). Check hardware_config.ini encoder_connection.

## 3. Locked Architectural Decisions

These are non-negotiable. Do not deviate.

1. **YAGSL** is the swerve engine. Do NOT write custom swerve kinematics.
2. **Choreo** is the sole trajectory pipeline. Do NOT use PathPlannerLib.
3. **No software-side PID loops.** Motor-level control uses SPARK MAX onboard PID
   (via REVLib SparkPIDController). State-space/LQR at subsystem coordination level only.
   The principle is the same as Phoenix 6 firmware PID — PID runs on the motor controller
   hardware, not on the roboRIO — but the API is REVLib, not CTRE.
4. **AdvantageKit** is a telemetry CONSUMER of YAGSL. Do NOT create DriveIO interfaces
   that wrap YAGSL internals. Log what YAGSL publishes to NT4.
5. **Spotless** (Google Java Format) + **SpotBugs** (medium confidence) + **JaCoCo**
   (80% on frc.lib) enforced on every build.
6. **JUnit tests are mandatory** with every feature. Generate tests in the same
   response as the feature code.

## 4. Package Structure

```
frc.robot              — Robot-specific code (tied to this robot's hardware)
  ├── Robot.java           — TimedRobot entry point, AdvantageKit init
  ├── RobotContainer.java  — Command bindings, subsystem instantiation
  ├── Constants.java       — All constants, organized by subsystem inner class
  ├── BuildConstants.java  — Git metadata (auto-generated)
  ├── Main.java            — WPILib entry point (do not modify)
  ├── DriverPracticeMode.java      — [Phase 4] Sim scenario chooser + pose reset
  ├── commands/
  │   ├── DriveCommand.java        — Default swerve teleop command
  │   ├── ChoreoAutoCommand.java   — [Phase 1] Trajectory following
  │   ├── AutoScoreCommand.java    — [Phase 2] Vision-gated scoring
  │   ├── AutoAlignCommand.java    — [Phase 4] Right-bumper AprilTag rotation assist
  │   ├── DriveToGamePieceCommand.java — [Phase 4] Left-bumper game piece seek
  │   ├── PathfindToGoalCommand.java — [Phase 3] A* path following
  │   └── FullAutonomousCommand.java — [Phase 3] Decision engine loop
  ├── subsystems/
  │   ├── SwerveSubsystem.java     — YAGSL wrapper, AK logging, gyro zero
  │   ├── LEDs.java                — Priority animation system
  │   ├── VisionSubsystem.java     — [Phase 2] Limelight MegaTag2 + [Phase 3] llpython
  │   └── FuelDetectionConsumer.java — [Phase 3] SnapScript data parser
  └── autos/
      ├── ActionType.java          — SCORE / COLLECT / CLIMB enum
      ├── GameState.java           — Immutable game state snapshot (builder)
      ├── ScoredTarget.java        — record: actionType, targetPose, utility
      └── AutonomousStrategy.java  — [Phase 3] Utility-based target selector

frc.lib                — Reusable utilities (game-agnostic, season-portable)
  ├── AllianceFlip.java            — Mirror poses blue↔red
  ├── pathfinding/
  │   ├── NavigationGrid.java      — Load/query navgrid.json
  │   ├── AStarPathfinder.java     — A* search on NavigationGrid
  │   └── DynamicAvoidanceLayer.java — Potential field obstacle avoidance
  └── util/
      └── BatteryCompensation.java — Feedforward voltage correction
```

## 5. YAGSL JSON Configuration Schema

All configs live in `src/main/deploy/swerve/`.

### swervedrive.json
```json
{
  "imu": {
    "type": "PLACEHOLDER_GYRO_TYPE",
    "id": PLACEHOLDER_GYRO_ID,
    "canbus": ""
  },
  "invertedIMU": false,
  "modules": [
    "modules/frontleft.json",
    "modules/frontright.json",
    "modules/backleft.json",
    "modules/backright.json"
  ]
}
```

### Module files (e.g., frontleft.json)
```json
{
  "drive": { "type": "sparkmax", "id": PLACEHOLDER_CAN_ID, "canbus": "" },
  "angle": { "type": "sparkmax", "id": PLACEHOLDER_CAN_ID, "canbus": "" },
  "encoder": { "type": "attached", "id": 0, "canbus": "" },
  "inverted": { "drive": false, "angle": false },
  "absoluteEncoderInverted": false,
  "absoluteEncoderOffset": 0.0,
  "location": { "front": PLACEHOLDER_INCHES, "left": PLACEHOLDER_INCHES }
}
```

**Note:** For Thrifty 10-pin encoders plugged into the SPARK MAX data port, the
encoder type is `"attached"` and the `"id"` field is ignored (encoder reads through
the SPARK MAX automatically). If the encoder is plugged into the roboRIO analog input
instead, change the type to `"thrifty"` and set `"id"` to the analog port number (0-3).

### physicalproperties.json
```json
{
  "conversionFactor": {
    "drive": { "gearRatio": PLACEHOLDER_DRIVE_RATIO, "diameter": PLACEHOLDER_WHEEL_DIA, "factor": 0 },
    "angle": { "gearRatio": PLACEHOLDER_STEER_RATIO, "factor": 0 }
  },
  "currentLimit": { "drive": 40, "angle": 20 },
  "rampRate": { "drive": 0.25, "angle": 0.25 },
  "wheelGripCoefficientOfFriction": 1.19,
  "optimalVoltage": 12
}
```

## 6. Key Class Contracts

### SwerveSubsystem.java
- Constructor: `new SwerveSubsystem(File swerveJsonDir)` loads YAGSL config
- **IMPORTANT:** Call `swerveDrive.pushOffsetsToEncoders()` in constructor if using
  attached absolute encoders (Thrifty 10-pin on SPARK MAX data port). This sets the
  SPARK MAX onboard PID sensor to the attached encoder for best performance.
- `drive(Translation2d translation, double rotation, boolean fieldRelative)` — primary control
- `lock()` — X-formation wheel lock
- `zeroGyro()` — reset heading
- `getPose()` → `Pose2d` — current estimated pose
- `addVisionMeasurement(Pose2d pose, double timestamp)` — for Phase 2
- Periodic: logs pose, gyro, module states to AdvantageKit

### LEDs.java
- `setAnimation(Animation anim, int priority)` — set animation at priority level
- `clearAnimation(int priority)` — clear specific priority
- Higher priority number overrides lower
- Priority 0 = idle, 1 = driving, 2 = aligning, 3 = alert/error

### NavigationGrid.java (Phase 3)
- Constructor: `new NavigationGrid(String jsonPath)` loads navgrid.json
- `isPassable(int col, int row)` → boolean
- `toGridCoords(Translation2d fieldPos)` → int[] {col, row}
- `toFieldCoords(int col, int row)` → Translation2d
- `setDynamicObstacle(Translation2d min, Translation2d max)` — mark rect as blocked
- `clearDynamicObstacles()` — reset to static grid

### AStarPathfinder.java (Phase 3)
- `findPath(Translation2d start, Translation2d goal, NavigationGrid grid)` → `List<Translation2d>`
- 8-connected neighbors, Euclidean heuristic
- Returns empty list if no path exists

### DynamicAvoidanceLayer.java (Phase 3)
- `computeCorrectedVelocity(Pose2d robotPose, Translation2d nextWaypoint, List<Translation2d> opponents)` → `Translation2d`
- Attractive force toward waypoint + repulsive forces from opponents
- Configurable: influence radius (default 2.0m), repulsive gain, attractive gain

### AutonomousStrategy.java (Phase 3)
- `evaluateTargets(Pose2d robotPose, GameState state)` → `List<ScoredTarget>`
- `ScoredTarget` contains: target pose, action type, utility score
- GameState contains: FUEL held, HUB active status, time remaining, detected FUEL positions, detected opponents

### FuelDetectionConsumer.java (Phase 3)
- Reads `llpython` NetworkTables double array every cycle
- `getDetectedFuelPositions()` → `List<Translation2d>` (filtered by confidence > 80%, 3-frame persistence)
- `getDetectedOpponents()` → `List<Translation2d>` (from extended SnapScript)

### AutoAlignCommand.java (Phase 4)
- Bound to driver right bumper (`whileTrue`)
- Driver retains full translation (left stick); rotation auto-aims via `Helper.getAprilTagAim()` (kP=0.05)
- Calls `vision.setAprilTagPipeline()` on initialize, `Helper.resetFilters()` for clean IIR state

### DriveToGamePieceCommand.java (Phase 4)
- Bound to driver left bumper (`whileTrue`)
- Driver retains rotation (right stick); translation drives toward nearest `FuelDetectionConsumer` position
- Proportional approach: `speed = min(dist * 0.4, 1.0)`, stops at 0.5m arrival threshold
- Calls `vision.setNeuralPipeline()` on initialize

### DriverPracticeMode.java (Phase 4)
- `Scenario` enum: FULL_AUTO_BLUE/RED, TELEOP_BLUE_CENTER/RED_CENTER, TELEOP_BLUE_NEAR_HUB, STRESS_TEST
- `apply()`: called from `Robot.simulationInit()` — sets alliance station, auto/teleop mode, resets start pose
- `resetToStart()`: bound to driver Start button — teleports robot to scenario start pose without restarting sim
- SmartDashboard chooser: "Practice Scenario"

## 7. Naming Conventions

- Constants: `kCamelCase` (e.g., `kMaxSpeedMetersPerSec`)
- Subsystem methods: `verbNoun()` (e.g., `drive()`, `zeroGyro()`, `getPose()`)
- Commands: `VerbNounCommand` (e.g., `DriveCommand`, `AutoScoreCommand`)
- Test classes: `ClassUnderTestTest` (e.g., `AStarPathfinderTest`)
- Test methods: `testMethodName_scenario_expectedResult()` (e.g., `testFindPath_obstacleBlocking_pathAvoidsObstacle()`)
- Commit messages: `[Role] Brief description` (e.g., `[Drive] Fix YAGSL config for Thrifty encoders`)

## 8. Dependencies (Vendordeps)

| Library | Vendordep JSON URL |
|---------|-------------------|
| YAGSL | `https://broncbotz3481.github.io/YAGSL-Lib/yagsl/yagsl.json` |
| REVLib (SPARK MAX) | `https://software-metadata.revrobotics.com/REVLib-2026.json` |
| Phoenix 6 (CTRE) | `https://maven.ctr-electronics.com/release/com/ctre/phoenix6/latest/Phoenix6-frc2026-latest.json` |
| AdvantageKit | `https://github.com/Mechanical-Advantage/AdvantageKit/releases/latest/download/AdvantageKit.json` |
| Choreo | `https://sleipnirgroup.github.io/ChoreoLib/dep/ChoreoLib.json` |

**Note:** Phoenix 6 is included because the gyro may be a Pigeon 2.0 (CTRE device).
If the gyro is a NavX (Kauai Labs), Phoenix 6 may not be needed — but YAGSL includes
it as a transitive dependency anyway. REVLib is REQUIRED for SPARK MAX motor control.

## 9. File Locations

| Purpose | Path |
|---------|------|
| YAGSL JSON configs | `src/main/deploy/swerve/` |
| Navigation grid | `src/main/deploy/navgrid.json` |
| Choreo trajectories | `src/main/deploy/choreo/` |
| Java source | `src/main/java/frc/` |
| JUnit tests | `src/test/java/frc/` |
| SpotBugs exclusions | `config/spotbugs-exclude.xml` |
| Navgrid generator | `tools/generate_navgrid.py` |
| Analysis scripts | `tools/` |

## 10. Testing Requirements

- **frc.lib.***: 80%+ line coverage (enforced by build gate). Pure math — every function tested.
- **frc.robot.***: 50%+ line coverage. Use WPILib sim hooks + fake NT data.
- Run: `./gradlew test` (must pass before every commit)
- Coverage: `./gradlew test jacocoTestReport` (report at build/reports/jacoco/)
- Every Cursor-generated feature MUST include tests in the same response.

## 11. Simulation

- All code runs in WPILib simulation without hardware
- YAGSL provides built-in simulation for swerve modules
- DriveIOSim provides a parallel WPILib DCMotorSim path for AdvantageScope
- maple-sim provides physics simulation (game piece interaction, field collisions)
- Test with: `./gradlew simulateJava` then open AdvantageScope

## 12. SnapScript Integration (Phase 3)

The Limelight SnapScript system provides a bidirectional data bridge:

**Robot → Limelight** (via `llrobot` NetworkTables double array):
```
[robotX, robotY, robotHeading, zoneMinX, zoneMinY, zoneMaxX, zoneMaxY, hubActive]
```

**Limelight → Robot** (via `llpython` NetworkTables double array):
```
[numFuel, fx1, fy1, fConf1, fx2, fy2, fConf2, ..., numOpponents, ox1, oy1, oConf1, ...]
```

All coordinates are field-relative (meters). Confidence scores are 0.0–1.0.
