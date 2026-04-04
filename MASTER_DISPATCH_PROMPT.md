# THE ENGINE — Master Dispatch Prompt
# Copy this entire file content as your first prompt to Claude Code.
# Then close your laptop and check PROGRESS.md from your phone via Dispatch.

---

## CONTEXT

Read these files completely before writing any code:
1. ARCHITECTURE.md — class contracts, package structure, naming conventions
2. .cursorrules — locked decisions, agent roles, testing requirements
3. CURSOR_PROMPTS.md — sequential prompt chain for every phase

This project is called "The Engine" — an FRC robot software platform for Team 2950.
Hardware: Thrifty Swerve modules + NEO Brushless motors + SPARK MAX controllers +
Thrifty 10-Pin Magnetic Encoders + NEO built-in hall-effect relative encoders +
unknown gyro (use pigeon2 as placeholder). Motor control uses REVLib, NOT Phoenix 6.

## HARDWARE CONFIGURATION

The file hardware_config.ini is the single source of truth for all hardware parameters.
Values marked TODO will use simulation defaults until the team fills them in.

When hardware_config.ini is updated with real values, run:
    python tools/generate_configs.py

This regenerates ALL YAGSL JSON configs, CAN_ID_REFERENCE.md, and physical properties
from the single config file. Do NOT edit the generated JSON files directly.

For now, use these simulation defaults for any TODO values:
   - Drive gear ratio: 6.75
   - Steer gear ratio: 21.43
   - Wheel diameter: 4 inches
   - Module location: 10.865 inches from center (square chassis)
   - Gyro type: pigeon2, ID: 13
   - Encoder analog ports: 0, 1, 2, 3
   - CAN IDs: drive 1,3,5,7 — steer 2,4,6,8

## EXECUTION RULES

1. Execute every prompt in CURSOR_PROMPTS.md in sequential order, starting Phase 1 Block 1.
2. Run `./gradlew build` after every major file change. If it fails, read the error and fix it.
3. Run `./gradlew test` after implementing any test skeleton from src/test/java/.
4. If tests fail, fix them before moving to the next block.
5. Do NOT ask me questions — make reasonable decisions based on ARCHITECTURE.md.
6. Use the simulation defaults listed in HARDWARE CONFIGURATION above for any TODO values.
   Run `python tools/generate_configs.py` at the start to generate configs from defaults.
7. Commit to git after each completed block: `git add -A && git commit -m "[Phase.Block] description"`
8. After completing each block, append a status update to PROGRESS.md (see format below).

## COMPUTER USE INSTRUCTIONS

You have Computer Use enabled. Use it for visual verification steps:

### When to use Computer Use:
- **Phase 1 Block 4**: After building DriveIOSim, launch sim with `./gradlew simulateJava`.
  Open AdvantageScope (it should be installed — if not, download from GitHub releases).
  Connect AdvantageScope to the running sim via NetworkTables (localhost).
  Visually verify: open the 3D field view, confirm 4 swerve modules are visible.
  If a gamepad is connected, drive the robot and verify pure forward = no rotation.
  Take a screenshot and note the result in PROGRESS.md.

- **Phase 1 Block 5**: After creating ChoreoAutoCommand, run the sim in autonomous mode.
  Open AdvantageScope, watch the robot follow the trajectory.
  Verify: robot moves along the expected path, arrives at the endpoint.
  If the robot veers off course, check the odometry reset and trajectory loading code.

- **Phase 3A Week 2**: After implementing AStarPathfinder, run the tests AND open
  AdvantageScope to visualize the planned path. The path should be logged to
  AdvantageKit as a Pose2d array. Verify visually that the path avoids the HUB obstacle.

- **Phase 3D Week 6-7**: After implementing DynamicAvoidanceLayer, run the sim with
  a simulated opponent. Open AdvantageScope and verify the robot deflects around the
  opponent rather than driving through it. The force vectors should be logged as
  arrows in AdvantageScope.

- **Phase 3D Week 8 (Tuning)**: This is iterative. In AdvantageScope, watch the robot
  navigate around opponents. If it oscillates (bounces back and forth), increase the
  attractive gain or decrease the repulsive gain in Constants.java. If it clips the
  opponent (passes too close), increase the repulsive gain or influence radius.
  Iterate until the robot smoothly deflects. Run 10 autonomous cycles and verify
  zero collisions. Log the final tuning values in PROGRESS.md.

### When NOT to use Computer Use:
- Pure code generation — just write files directly
- Running ./gradlew build — use the terminal
- Reading error messages — use the terminal
- Running tests — use the terminal
- Git operations — use the terminal

## PROGRESS.MD FORMAT

After each block, append this to PROGRESS.md:

```
## [Phase X Block Y] - [Block Name]
- **Status**: PASS / FAIL / PARTIAL
- **Timestamp**: [current time]
- **Files created/modified**: [list]
- **Tests**: [X/Y passing]
- **Build**: CLEAN / [error summary if not clean]
- **Visual verification**: [what you saw in AdvantageScope, if applicable]
- **Issues**: [any problems encountered and how they were resolved]
- **Git commit**: [commit hash]
---
```

## PHASE EXECUTION ORDER

Follow CURSOR_PROMPTS.md exactly, but here is the high-level order for reference:

### Phase 1: The Engine (Swerve + Sim + Logging)
1. Block 1: Verify scaffold, clean build
2. Block 2: YAGSL config in sim (Thrifty encoders, TalonFX motors)
3. Block 3a: AdvantageKit logging + CAN bus monitoring
4. Block 3b: LED priority system tests
5. Block 4: DriveIOSim digital twin [USE COMPUTER USE FOR VISUAL VERIFICATION]
6. Block 5: Choreo trajectory following [USE COMPUTER USE FOR VISUAL VERIFICATION]

### Phase 2: Perception + Superstructure
7. 2A Week 1: VisionSubsystem (MegaTag2)
8. 2A Week 2: Dual pipeline switching + vision gating
9. 2B Week 1: SuperstructureStateMachine
10. 2B Week 3: AutoScoreCommand
11. 2B Week 4: Branching autonomous + SendableChooser

### Phase 3: Autonomous Intelligence
12. 3A Pre-Task: Evaluate Repulsor library (clone github.com/curtinfrc, review API,
    report findings in PROGRESS.md — recommend adopt or build custom)
13. 3A Week 1: NavigationGrid.java + tests [navgrid.json already exists in deploy/]
14. 3A Week 2: AStarPathfinder.java + tests [USE COMPUTER USE TO VISUALIZE PATH]
15. 3A Week 3: PathfindToGoalCommand + waypoint smoothing
16. 3B Week 3-4: AutonomousStrategy.java + Bot Aborter + tests
17. 3B Week 5-6: FullAutonomousCommand (decision engine loop)
18. 3C Week 4-5: FuelDetectionConsumer.java + tests
19. 3C Week 6: Wire vision into decision engine
20. 3D Week 6: DynamicAvoidanceLayer.java + tests [USE COMPUTER USE TO VISUALIZE]
21. 3D Week 7: Integration with drive command + decision engine
22. 3D Week 8: Tuning in simulation [USE COMPUTER USE — ITERATIVE]

### Phase 4: Competition Readiness
23. 4B: Teleop auto-align commands
24. 4C: Validate analysis scripts (tools/*.py) against a sim log
25. Final: Run ./gradlew test jacocoTestReport, log coverage percentages

## COMPLETION CRITERIA

The project is DONE when:
- [ ] ./gradlew build passes with zero errors
- [ ] ./gradlew test passes with all tests green
- [ ] JaCoCo shows 80%+ coverage on frc.lib package
- [ ] AdvantageScope shows a robot that can be driven with a gamepad
- [ ] A Choreo trajectory executes in simulation
- [ ] A* pathfinding routes around an obstacle (visible in AdvantageScope)
- [ ] Decision engine picks targets based on simulated game state
- [ ] DynamicAvoidanceLayer deflects around a simulated opponent
- [ ] All blocks are logged in PROGRESS.md with PASS status
- [ ] All work is committed to git

## BEGIN

Start now with Phase 1 Block 1. Read ARCHITECTURE.md first.
