# THE ENGINE — Cursor Prompt Chain
## Execute these prompts in order. Each builds on the previous.

> **Before starting:** Tell Cursor to read ARCHITECTURE.md first.
> Prompt: "Read ARCHITECTURE.md and .cursorrules. Confirm you understand the project structure, locked decisions, and naming conventions."

---

## PHASE 1: THE ENGINE (Swerve + Sim + Logging)

### Block 1: Verify Scaffold
```
As Validation & Safety, run ./gradlew build and confirm zero errors. Check the SpotBugs report at build/reports/spotbugs/. List any findings. If there are vendordep issues, check vendordeps/ directory.
```
**Expected:** Clean build with 0 errors. SpotBugs report clean or with minor informational findings.
**If it fails:** Check that all vendordep JSON files are in vendordeps/. Run `./gradlew --refresh-dependencies`.

### Block 2: YAGSL Config Verification
```
As the Drive Engineer, examine the YAGSL JSON configuration in src/main/deploy/swerve/. These files use Thrifty Absolute Magnetic Encoders (type "thrifty", connected to roboRIO analog inputs 0-3), NOT CANcoders. The physical properties have PLACEHOLDER values that will be filled in later — for now use: drive gear ratio 6.75, steer gear ratio 21.43, wheel diameter 4 inches, module location 10.865 inches from center. Update the placeholder values for simulation, run the simulation, and confirm the swerve modules initialize without errors.
```
**Expected:** Simulation launches, 4 swerve modules appear in AdvantageScope, no exceptions.
**If modules spin uncontrollably:** Invert the angle motor in the module JSON. Thrifty encoders may need `absoluteEncoderInverted: true`.

### Block 3a: AdvantageKit Logging
```
As Validation & Safety, verify that AdvantageKit is logging all YAGSL telemetry. Open the AK log in AdvantageScope and confirm module velocities and positions are present for all four modules. Also add CAN bus utilization logging: log RobotController.getCANStatus().percentBusUtilization to AdvantageKit every loop cycle in SwerveSubsystem.periodic().
```

### Block 3b: LED Priority System
```
As Interface & Docs, test the LED priority system. Write a simple test in Robot.java's testPeriodic that cycles through animations at different priorities to verify override behavior. Then uncomment and implement the test methods in LEDsTest.java.
```

### Block 4: Digital Twin Simulation
```
As the Drive Engineer, create DriveIOSim.java in frc.robot.subsystems. Build a parallel simulation path using WPILib DCMotorSim for each of the four swerve modules. Use the gear ratios and wheel diameter from Constants.java. Do NOT try to wrap YAGSL's internal simulation — build an independent sim that mirrors the same physics. Wire it into RobotContainer's simulation path with a Robot.isSimulation() check. Then run the JUnit kinematic tests in SwerveKinematicsTest.java and confirm all 5 pass.
```
**Expected:** Gamepad drives digital twin in AdvantageScope. Pure forward = no rotation. All 5 kinematic tests pass.

### Block 5: Choreo Integration
```
As the Systems Architect, create ChoreoAutoCommand.java in frc.robot.commands. This command loads a Choreo trajectory from deploy/choreo/ and follows it using the swerve subsystem. Reset odometry to the trajectory's starting pose before following. Wire a test trajectory into the autonomous selector using SendableChooser in RobotContainer. Create a simple test trajectory JSON file for simulation testing (straight line 2m forward).
```

---

## PHASE 2: PERCEPTION + SUPERSTRUCTURE

### 2A Week 1: Vision Subsystem
```
As the Perception Engineer, create VisionSubsystem.java in frc.robot.subsystems. Integrate Limelight MegaTag2 pose estimation using LimelightHelpers (from the Limelight vendordep or copied from Limelight docs). Feed poses to the swerve drive pose estimator via SwerveSubsystem.addVisionMeasurement(). Filter out poses that are more than 1.0m from current odometry estimate. Log all accepted and rejected measurements to AdvantageKit.
```

### 2A Week 2: Dual Pipeline Switching
```
As the Perception Engineer, implement dual Limelight pipeline switching in VisionSubsystem. During autonomous, use the neural detector pipeline (index 1) for game piece detection. During teleop, switch to AprilTag pipeline (index 0) for pose estimation. Pipeline switching is fire-and-forget via LimelightHelpers.setPipelineIndex(). Also implement vision-gated scoring: a method isTargetValid() that returns true only if an AprilTag has been continuously detected for at least 250ms.
```

### 2B Week 1: Superstructure State Machine
```
As the Systems Architect, create SuperstructureStateMachine.java in frc.robot.subsystems. Define states: IDLE, INTAKING, STAGING, SCORING, CLIMBING. Each state has entry/exit actions and transition conditions. Gate all transitions by sensor confirmation (use simulated sensors for now). Log every state transition to AdvantageKit with timestamp and trigger reason.
```

### 2B Week 3: Auto-Score Command
```
As the Systems Architect, create AutoScoreCommand.java in frc.robot.commands. This is a SequentialCommandGroup that: (1) drives to scoring position using vision alignment, (2) waits for AprilTag confirmation via VisionSubsystem.isTargetValid(), (3) executes scoring action, (4) retracts. Include a 5-second total timeout. If vision gate fails within 250ms, abort and flash error LED at priority 3.
```

### 2B Week 4: Branching Autonomous
```
As the Systems Architect, create branching autonomous routines. Add 3-5 autonomous options to the SendableChooser in RobotContainer. Each option is a SequentialCommandGroup that chains Choreo segments with scoring commands. Use ConditionalCommand to branch: if FUEL was successfully acquired, drive to score; otherwise, skip to next pickup. Log branch decisions to AdvantageKit.
```

---

## PHASE 3: AUTONOMOUS INTELLIGENCE

### 3A Pre-Task: Evaluate Repulsor
```
As the Systems Architect, evaluate the Repulsor library (Team 4788, github.com/curtinfrc). Clone their 2026-Rebuilt repo and examine the pathfinding/avoidance API. Determine: (1) Does it support our YAGSL swerve integration? (2) Does it load navgrid.json or use its own field representation? (3) Is the API surface compatible with our AutonomousStrategy? Report findings and recommend: adopt Repulsor, adopt Oxplorer (Team 3044), or build custom A*.
```

### 3A Week 1: NavigationGrid
```
As the Systems Architect, create NavigationGrid.java in frc.lib.pathfinding. This class loads the 2D occupancy grid from deploy/navgrid.json (already generated — 164x82 cells at 10cm resolution). Implement: isPassable(col, row), toGridCoords(Translation2d), toFieldCoords(col, row), setDynamicObstacle(min, max), clearDynamicObstacles(). Then uncomment and implement all test methods in NavigationGridTest.java. All tests must pass.
```

### 3A Week 2: A* Pathfinder
```
As the Systems Architect, create AStarPathfinder.java in frc.lib.pathfinding. Implement A* search with 8-connected neighbors and Euclidean heuristic. Input: start Translation2d, goal Translation2d, NavigationGrid. Output: List<Translation2d> waypoints. Return empty list if no path exists. Then uncomment and implement all test methods in AStarPathfinderTest.java. All tests must pass, including the performance test (<10ms).
```

### 3A Week 3: Path Following Command
```
As the Systems Architect, create PathfindToGoalCommand.java in frc.robot.commands. This command: (1) runs AStarPathfinder to get waypoints, (2) smooths them with cubic spline interpolation, (3) follows the path by driving toward each waypoint sequentially, (4) re-plans if robot deviates >30cm from expected position. Log the planned path to AdvantageKit for visualization in AdvantageScope.
```

### 3B Week 3-4: Decision Engine
```
As the Systems Architect, create AutonomousStrategy.java in frc.robot.autos. Implement a utility function that evaluates available targets and returns a ranked list. Inputs: robot pose, FUEL held count, HUB active/inactive status, time remaining, detected FUEL positions, detected opponent positions. Outputs: List<ScoredTarget> sorted by utility score. Include Bot Aborter logic: shouldAbortTarget() returns true if opponent arrives at target >=0.75s before robot. Then uncomment and implement all tests in AutonomousStrategyTest.java.
```

### 3B Week 5-6: Full Autonomous Command
```
As the Systems Architect, create FullAutonomousCommand.java in frc.robot.commands. This command loops: (1) query AutonomousStrategy for best target, (2) pathfind to target via AStarPathfinder, (3) execute action (intake/score/climb), (4) repeat until match ends. Log every decision to AdvantageKit: target selected, utility score, path planned, action taken, time elapsed. Wire into the autonomous selector as "Adaptive Auto".
```

### 3C Week 4: FuelDetectionConsumer
```
As the Perception Engineer, create FuelDetectionConsumer.java in frc.robot.subsystems. This subsystem reads the llpython NetworkTables double array from the Limelight every cycle. Parse format: [numFuel, x1, y1, conf1, x2, y2, conf2, ...]. Provide getDetectedFuelPositions() that returns only detections above 80% confidence that have persisted for at least 3 consecutive frames. Log all detections to AdvantageKit. Then uncomment and implement all tests in FuelDetectionConsumerTest.java.
```

### 3C Week 5: Wire Vision into Decision Engine
```
As the Systems Architect, wire FuelDetectionConsumer into AutonomousStrategy. The decision engine should now evaluate real-time FUEL detections alongside static targets (DEPOT, HUB, TOWER). If a high-confidence FUEL detection is closer than the nearest DEPOT, prefer it. Log the decision rationale to AdvantageKit.
```

### 3D Week 6: Dynamic Avoidance Layer
```
As the Systems Architect, create DynamicAvoidanceLayer.java in frc.lib.pathfinding. Implement artificial potential fields: attractive force toward next A* waypoint (magnitude proportional to distance), repulsive forces away from opponent positions within 2.0m influence radius (magnitude inversely proportional to distance squared). Output a corrected velocity vector normalized to max robot speed. Store tunable parameters in Constants.java. Log all force vectors to AdvantageKit. Then uncomment and implement all tests in DynamicAvoidanceLayerTest.java.
```

### 3D Week 7: Integration
```
As the Systems Architect, integrate DynamicAvoidanceLayer into the autonomous drive command. When following A* waypoints, apply the potential field correction every loop cycle. Add opponent proximity penalty to AutonomousStrategy utility function. Implement Bot Aborter integration: if FuelDetectionConsumer reports an opponent racing toward the same target, trigger shouldAbortTarget() and re-target if needed.
```

---

## PHASE 4: COMPETITION READINESS

### 4B: Teleop Enhancement
```
As the Drive Engineer, create auto-align teleop commands. When the driver holds the right bumper, the robot automatically aligns to the nearest HUB scoring position using VisionSubsystem AprilTag data. When the driver holds the left bumper, the robot drives toward the nearest detected FUEL using FuelDetectionConsumer data. Release the button to return to manual control.
```

### 4C: Analysis Scripts
```
As Validation & Safety, the Python analysis scripts are already pre-built in tools/. Review extract_cycles.py, analyze_path_error.py, and battery_analysis.py. Run them against a sample WPILOG file (generate one from a simulation session) and verify the output CSV and reports are correct.
```
