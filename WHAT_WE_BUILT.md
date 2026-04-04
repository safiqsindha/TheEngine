# What We Built: From Swerve-Test to Constructicon

## For the Students and Mentors of FRC Team 2950 (The Devastators)

This document explains what your original robot code does, what was added on top of it, and why. Think of it as the "before and after" guide to understanding how Constructicon works.

---

## Part 1: What You Built (The Foundation)

Everything in your swerve-test branch was the starting point. This code was written and tested on real hardware by team members, and it forms the foundation everything else sits on top of.

### Your Hardware Configuration

You picked the hardware, wired it, and verified every CAN ID on the real robot:

| What | Your Choice |
|------|-------------|
| Swerve modules | Thrifty Swerve (4 modules) |
| Drive motors | NEO Brushless via SPARK MAX |
| Steer motors | NEO Brushless via SPARK MAX |
| Encoders | Thrifty 10-pin magnetic (attached to SPARK MAX data port) |
| Gyroscope | ADIS16470 on roboRIO SPI |
| Flywheel | 2x NEO Vortex (SPARK Flex) + 2x NEO feed wheels |
| Intake | 2x NEO arms (independent PID) + 1x NEO wheel |
| Conveyor | 1x brushed belt motor + 1x NEO spindexer |
| Climber | 1x NEO with position PID |
| Side claw | 1x NEO with position PID |
| Vision | Limelight 3 |

Your gear ratios (6.23 drive, 25 steer), wheel diameter (4"), module spacing (11" from center), and PID tuning values (P=0.0020645) all came from real-world testing.

### Your Subsystem Code

These files contain the motor control logic you wrote. They tell each mechanism how to move:

| File | What It Does |
|------|-------------|
| `Flywheel.java` | Spins the shooter wheels to a target RPM using onboard PID. Two Vortex motors for the main wheels, two NEO motors for the lower feed wheels. |
| `Intake.java` | Raises/lowers the intake arms and spins the intake wheel. Two independent arm PIDs because the mechanical linkage has some play. |
| `Conveyor.java` | Runs the belt and spindexer that move game pieces from intake to flywheel. |
| `Climber.java` | Extends and retracts the climbing mechanism to a target position. |
| `SideClaw.java` | Extends and retracts the side claw to a target position. |
| `Helper.java` | Your Limelight distance/aim filters, RPM-from-distance lookup table, and hub-shift logic. Migrated directly from swerve-test. |

### Your Teleop Commands

These are the button bindings that let the driver control each mechanism:

| Command | What It Does |
|---------|-------------|
| `DriveCommand` | Left stick = drive, right stick = rotate. Field-relative. |
| `FlywheelDynamic` | Left trigger scales flywheel speed up. |
| `FlywheelStatic` | POV buttons fire at preset RPMs (2400, 2500, 3000, 3500). |
| `IntakeControl` | Right trigger scales arm angle and wheel speed together. |
| `ConveyorControl` | Holds conveyor stopped by default; overridden during scoring. |
| `ClimberControl` | Sets climber to a target height. |
| `ClawControl` | Sets claw to a target position. |

### Your YAGSL Swerve Library

The entire `swervelib/` directory (130 Java files) is the YAGSL library that handles swerve drive math, motor control, odometry, and simulation. Your team configured it with the correct module JSONs, CAN IDs, and tuning values.

---

## Part 2: What Was Added (The Upgrades)

Everything below was built on top of your foundation. None of it changes how your motors spin or how the driver controls the robot in basic teleop. It adds layers of intelligence, safety, and automation.

### Upgrade 1: AdvantageKit Logging

**What it is:** A recording system that logs everything the robot does, every 20ms, to a file.

**Why it matters:** When something goes wrong at competition, you can replay the entire match in AdvantageScope and see exactly what happened. No more "I think the robot did something weird" -- you can prove it.

**What gets logged:**
- Robot pose (where the robot thinks it is)
- Gyro angle, wheel velocities, motor outputs
- Vision measurements (accepted and rejected)
- Battery voltage, CAN bus utilization
- Every state machine transition
- Every autonomous decision

**Files:** Changes in `Robot.java` (LoggedRobot), `Logger.recordOutput()` calls throughout subsystems.

### Upgrade 2: LED Priority System

**What it is:** The LED strip shows different patterns based on what the robot is doing, with a priority system so important signals override less important ones.

| Priority | When | Pattern |
|----------|------|---------|
| 0 (lowest) | Idle | Slow pulse |
| 1 | Driving normally | Solid color |
| 2 | Auto-aligning to target | Blinking |
| 3 (highest) | Error or scoring | Fast flash |

**File:** `LEDs.java` (191 lines)

### Upgrade 3: Vision Pose Estimation

**What it is:** The Limelight reads AprilTags and tells the robot exactly where it is on the field. This fuses with wheel odometry so even if wheels slip, the robot still knows its position.

**How it works:**
1. Limelight sees AprilTags, publishes `botpose_orb_wpiblue` (MegaTag2)
2. VisionSubsystem reads it, checks quality (tag count, latency, distance)
3. Rejects measurements more than 1m from where the robot thinks it is (prevents jumps from misidentified tags)
4. Feeds accepted measurements into the YAGSL Kalman filter with distance-based confidence weighting: close tags get trusted more, far tags get trusted less

**Files:** `VisionSubsystem.java` (225 lines)

### Upgrade 4: Superstructure State Machine

**What it is:** A coordinator that tracks what the robot is doing and prevents conflicting actions. Instead of manually sequencing "intake, then convey, then shoot," the state machine handles it automatically.

**The 5 states:**
```
IDLE  -->  INTAKING  -->  STAGING  -->  SCORING
                                          |
IDLE  <--  CLIMBING  <------------------+
```

- **IDLE:** Nothing happening. Ready for commands.
- **INTAKING:** Intake deployed, wheels spinning. Waiting for game piece.
- **STAGING:** Game piece detected (current spike on intake motor > 15A). Game piece is being positioned.
- **SCORING:** Flywheel spinning, feeding game piece. Stays here until scoring command calls `requestIdle()`.
- **CLIMBING:** Climber active. Everything else stops.

**File:** `SuperstructureStateMachine.java` (192 lines)

### Upgrade 5: Auto-Align and Drive-to-Game-Piece

**What they are:** Two teleop assist commands that help the driver without taking away control.

| Button | What Happens | Driver Keeps |
|--------|-------------|-------------|
| Right bumper | Robot auto-rotates to face nearest AprilTag | Full translation (WASD movement) |
| Left bumper | Robot drives toward nearest detected game piece | Full rotation (turning) |

These are "hold to use" -- release the bumper and you're back to full manual control.

**Files:** `AutoAlignCommand.java` (86 lines), `DriveToGamePieceCommand.java` (97 lines)

### Upgrade 6: Choreo Trajectory Following

**What it is:** Pre-planned autonomous paths created in the Choreo app. The robot follows these paths precisely using its pose estimation.

**Available autos:**
| Name | What It Does |
|------|-------------|
| Leave Only | Follow a Choreo trajectory to leave the community zone |
| Leave Only (Raw) | Drive forward 2m using raw motor commands (sim testing) |
| Score + Leave | Shoot preloaded game piece, then leave |
| 2 Coral | Score, drive to station, pickup, score again |
| 3 Coral | Three scoring cycles with station pickups |
| Safe Mode (No Vision) | Emergency fallback: timed forward drive + blind shot at 2800 RPM |

**Files:** `ChoreoAutoCommand.java` (281 lines)

### Upgrade 7: Full Autonomous Intelligence

This is the big one. A complete decision-making system that lets the robot play autonomously without pre-planned paths.

#### How It Works (The Decision Loop)

Every 0.5 seconds during autonomous, the robot:

1. **Evaluates all possible targets** on the field
2. **Scores each target** by utility (how valuable is it?)
3. **Pathfinds** to the best target using A* search
4. **Avoids opponents** using potential fields (like magnets pushing the robot away)
5. **Executes the action** (score, collect fuel, or climb)
6. **Re-evaluates** -- if a better opportunity appears, switches targets

#### The Priority System

| Priority | Action | When |
|----------|--------|------|
| Highest | CLIMB | Less than 15 seconds remaining |
| Medium | SCORE | Hub is active AND robot has fuel |
| Lowest | COLLECT | Fuel detected on field |

#### The Pathfinding Stack

| Layer | What It Does | File |
|-------|-------------|------|
| Navigation Grid | 164x82 cell occupancy map of the field (10cm per cell) | `NavigationGrid.java` |
| A* Pathfinder | Finds shortest path around obstacles in under 10ms | `AStarPathfinder.java` |
| Dynamic Avoidance | Pushes the robot away from opponents (2m influence radius) | `DynamicAvoidanceLayer.java` |
| Bot Aborter | Cancels a target if an opponent will beat us there by 0.75+ seconds | `AutonomousStrategy.java` |

#### Fuel Detection

The Limelight runs a neural network that detects game pieces on the field. `FuelDetectionConsumer.java` filters these detections:
- Must be above 80% confidence
- Must persist for 3 consecutive frames (prevents false positives)
- Opponents are detected immediately (they're hazards, not targets)

**Files:** `FullAutonomousCommand.java` (296 lines), `AutonomousStrategy.java` (118 lines), `GameState.java` (105 lines), `NavigationGrid.java` (199 lines), `AStarPathfinder.java` (178 lines), `DynamicAvoidanceLayer.java` (89 lines), `FuelDetectionConsumer.java` (214 lines)

### Upgrade 8: Brownout Protection

**What it is:** When the battery voltage drops below 8.0V (heavy motor use), the robot automatically reduces drive speed to prevent a full brownout (which would reboot the roboRIO).

- 8.0V and above: 100% speed
- 8.0V to 6.0V: linearly scales down to 50% speed
- Below 6.5V: logs a critical warning to AdvantageKit

**Files:** `Robot.java` (getBrownoutScale), `DriveCommand.java` (applies scale)

### Upgrade 9: Driver Practice Mode

**What it is:** 6 pre-built simulation scenarios for practicing without the real robot.

| Scenario | Alliance | Start Position | Mode |
|----------|----------|---------------|------|
| Full Auto Blue | Blue 1 | Blue community | Auto |
| Full Auto Red | Red 1 | Red community (mirrored) | Auto |
| Teleop Blue Center | Blue 1 | Field center | Teleop |
| Teleop Red Center | Red 1 | Field center (mirrored) | Teleop |
| Teleop Blue Near Hub | Blue 2 | Near blue hub | Teleop |
| Stress Test | Blue 3 | Corner, 45-degree angle | Teleop |

Select a scenario from the SmartDashboard "Practice Scenario" chooser. Press Start to reset to the starting position.

**File:** `DriverPracticeMode.java` (127 lines)

### Upgrade 10: Build Quality Gates

These run automatically every time you build the code:

| Tool | What It Checks | Consequence |
|------|---------------|-------------|
| **Spotless** | Code formatting (Google Java style) | Auto-fixes formatting |
| **SpotBugs** | Common bug patterns (null pointers, resource leaks) | Build fails on bugs |
| **JaCoCo** | Test coverage (80% minimum on library code) | Build fails if under 80% |
| **JUnit 5** | 181 automated tests across 17 test classes | Build fails on any test failure |

### Upgrade 11: Analysis Scripts

Python tools in `tools/` for post-match analysis:

| Script | What It Does |
|--------|-------------|
| `extract_cycles.py` | Parses AdvantageKit logs to find scoring cycle times |
| `analyze_path_error.py` | Compares planned path vs actual path driven |
| `battery_analysis.py` | Correlates voltage drops with motor usage |
| `generate_configs.py` | Regenerates YAGSL JSON from hardware_config.ini |
| `generate_navgrid.py` | Creates the field occupancy grid for pathfinding |

---

## Part 3: The Numbers

| Metric | Value |
|--------|-------|
| Your original Java files | ~15 (subsystems + commands + helper) |
| Total Java files now | 40 main + 17 test = 57 |
| Total lines of production Java | ~4,200 |
| Automated tests | 181 across 17 test classes |
| Library test coverage (frc.lib) | 98% |
| Autonomous options | 7 (from Leave Only to Full Autonomous + Safe Mode) |
| Python analysis tools | 7 |
| Build quality gates | 4 (Spotless, SpotBugs, JaCoCo, JUnit) |

---

## Part 4: What Still Needs You (Hardware-Only Tasks)

These cannot be done in code -- they need the real robot:

| Task | What To Do | Why |
|------|-----------|-----|
| **Encoder offsets** | Point all modules forward, read encoder values, update hardware_config.ini | Swerve won't drive straight without this |
| **Flash SideClaw to CAN ID 20** | Use REV Hardware Client to change CAN ID from 18 to 20 | Was conflicting with the spindexer motor |
| **Verify intake current threshold** | Run intake with and without a game piece, check if 15A is the right spike threshold | Too low = false triggers, too high = missed pickups |
| **Choreo trajectories** | Open Choreo app, design match-ready paths, export .traj files | We have the follower code but need the actual paths |
| **Vision std-dev validation** | Test AprilTag detection at various distances, tune trust weights if needed | Close tags should be trusted more than far ones |

---

## How to Read the Code

If you want to understand how a specific feature works, here's where to start:

**"How does the robot drive?"**
`DriveCommand.java` -> `SwerveSubsystem.java` -> YAGSL `SwerveDrive`

**"How does autonomous work?"**
`FullAutonomousCommand.java` -> `AutonomousStrategy.java` -> `AStarPathfinder.java`

**"How does the robot detect game pieces?"**
`VisionSubsystem.java` -> `FuelDetectionConsumer.java` -> Limelight llpython array

**"How does the state machine work?"**
`SuperstructureStateMachine.java` -- read the `computeNextState()` method, it's a single switch statement

**"How do I add a new autonomous routine?"**
Look at `configureAutonomous()` in `RobotContainer.java` -- add a new `autoChooser.addOption()` call

**"How do I run the tests?"**
```bash
./gradlew test        # Run all 181 tests
./gradlew check       # Run tests + formatting + bug checks + coverage
```

**"How do I run the simulator?"**
```bash
./gradlew simulateJava
```
Then open AdvantageScope and connect to `localhost`.
