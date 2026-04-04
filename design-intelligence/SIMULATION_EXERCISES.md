# THE ENGINE — Simulation Exercises
# Block F.9 | Companion to Training Modules 1-6 | Audience: Veterans + Rookies

Each module from F.8 has a matching simulation exercise below. These are designed
to be run on a laptop with no physical robot — just the codebase, a terminal, and
optionally AdvantageScope.

**Prerequisites:**
- Java 17+ installed
- The constructicon repo cloned
- `./gradlew build` passes (run this first to confirm your setup)
- AdvantageScope installed (optional but recommended — download from GitHub)

---

## Exercise Set 1: Pattern Rules (Module 1 Companion)

### Sim Exercise 1.1 — Constants Treasure Hunt

The pattern rules from Module 1 are encoded as constants in the codebase. Find each
one and record its value. This teaches you where design decisions live in code.

**Instructions:** Use `grep` or your IDE's search to find each constant. Record the
file, line number, and value.

| Pattern Rule | What to Search For | File | Value |
|--------------|--------------------|------|-------|
| Climb time threshold | `kClimbTimeThresholdSeconds` | ? | ? |
| Opponent avoidance radius | `kOpponentInfluenceRadiusMeters` | ? | ? |
| Max robot speed | `kMaxRobotSpeedMps` | ? | ? |
| Vision confidence gate | `kFuelConfidenceThreshold` | ? | ? |
| Persistence frames | `kFuelPersistenceFrames` | ? | ? |
| Bot aborter threshold | `kAbortTimeThresholdSeconds` | ? | ? |
| Repulsive gain | `kRepulsiveGain` | ? | ? |
| Attractive gain | `kAttractiveGain` | ? | ? |
| Grid cell size | `kNavGridCellSizeMeters` | ? | ? |
| Replan threshold | `kReplanThresholdMeters` | ? | ? |

**Verification:** All values should be in `src/main/java/frc/robot/Constants.java`
under the `Pathfinding` inner class.

### Sim Exercise 1.2 — Pattern Debate Prep (No Computer Needed)

Pick one of these statements. Prepare a 2-minute argument FOR and AGAINST using
pattern rules as evidence. Present to a partner or the group.

1. "We should always gear our drivetrain for maximum speed."
2. "The climber should be the first mechanism we prototype."
3. "A turret is always worth the complexity."
4. "We should copy 254's design exactly every year."

**Scoring:** 1 point for each pattern rule cited with correct evidence. Bonus point
for citing a team other than 254.

---

## Exercise Set 2: Prediction Engine (Module 2 Companion)

### Sim Exercise 2.1 — Run the Strategy Tests and Read the Output

```bash
./gradlew test --tests "frc.robot.autos.AutonomousStrategyTest" --info
```

**Tasks:**
1. How many tests ran? How many passed?
2. Read the test names. For each one, predict what it tests BEFORE reading the code.
3. Open `src/test/java/frc/robot/autos/AutonomousStrategyTest.java`. Were your
   predictions correct?

### Sim Exercise 2.2 — Utility Scoring Calculator

Create a spreadsheet (or paper table) with these columns:

```
| Target | ActionType | Base Utility | Distance | Fuel Bonus | Opp Penalty | TOTAL |
```

Now calculate for this game state:
```
Robot at (2.0, 4.0), fuelHeld = 2, hubActive = true, timeRemaining = 30.0
Detected fuel: [(6.0, 3.0), (10.0, 5.0), (3.0, 7.0)]
Detected opponents: [(5.5, 3.2)]
HUB at (3.39, 4.11), CLIMB at (8.23, 4.11)
```

Fill in ALL rows (CLIMB, SCORE, and each COLLECT). Sort by total utility. Which
target does the robot choose?

**Check your work:** CLIMB should be generated (time ≤ 30 > 15? No — 30 > 15 so
CLIMB is NOT generated). Wait — is 30 ≤ 15? No. So no CLIMB. Re-read the condition:
`timeRemaining <= kClimbTimeThresholdSeconds (15.0)`. At 30s, CLIMB is not an option.

### Sim Exercise 2.3 — Bot Aborter Speed Drill

Time yourself. Calculate abort/continue for 10 scenarios as fast as you can.
Formula: abort if `(robotDist/robotSpeed) - (oppDist/oppSpeed) >= 0.75`

| # | rDist | rSpd | oDist | oSpd | rETA | oETA | Diff | Abort? |
|---|-------|------|-------|------|------|------|------|--------|
| 1 | 3.0 | 3.0 | 1.0 | 2.0 | | | | |
| 2 | 1.0 | 4.0 | 3.0 | 1.0 | | | | |
| 3 | 5.0 | 2.5 | 2.0 | 4.0 | | | | |
| 4 | 2.0 | 2.0 | 2.0 | 2.0 | | | | |
| 5 | 4.0 | 1.0 | 1.0 | 1.0 | | | | |
| 6 | 1.5 | 4.5 | 3.0 | 2.0 | | | | |
| 7 | 6.0 | 3.0 | 1.0 | 3.0 | | | | |
| 8 | 2.0 | 0.0 | 5.0 | 2.0 | | | | |
| 9 | 3.0 | 2.0 | 8.0 | 0.0 | | | | |
| 10| 0.5 | 4.0 | 0.6 | 4.0 | | | | |

**Answer Key:**
1. 1.0 - 0.5 = 0.5 → NO
2. 0.25 - 3.0 = -2.75 → NO
3. 2.0 - 0.5 = 1.5 → YES
4. 1.0 - 1.0 = 0.0 → NO
5. 4.0 - 1.0 = 3.0 → YES
6. 0.33 - 1.5 = -1.17 → NO
7. 2.0 - 0.33 = 1.67 → YES
8. rSpd=0 → YES (special case: robot not moving)
9. oSpd=0 → NO (special case: opponent stationary)
10. 0.125 - 0.15 = -0.025 → NO

**Target time:** Under 3 minutes for all 10.

---

## Exercise Set 3: Design Intelligence (Module 3 Companion)

### Sim Exercise 3.1 — Kickoff Dry Run

Open `design-intelligence/KICKOFF_TEMPLATE.md`. Fill it in for the 2025 game
**Reefscape** as practice (use the game manual or your memory from the season).

Then answer these questions using ONLY pattern rules:
1. What intake type do patterns suggest for coral (PVC pipes)?
2. What scorer type for placement at fixed positions?
3. Should we use a turret?
4. What's the build priority order?

**Compare your answers to what 254 actually built in 2025** (see
`254_CROSS_SEASON_ANALYSIS.md`). How close were your pattern-based predictions?

### Sim Exercise 3.2 — Trace the Autonomous Loop on Paper

Draw the FullAutonomousCommand flowchart from memory (don't look at the code).
Include:
- Where GameState is built
- Where evaluateTargets() is called
- Where A* runs
- Where the avoidance layer runs
- The 0.5s re-evaluation cycle
- Bot Aborter check
- Retarget hysteresis (+5.0)

Then open `FullAutonomousCommand.java` and check your diagram. Mark anything you
got wrong in red.

---

## Exercise Set 4: Pathfinding (Module 4 Companion)

### Sim Exercise 4.1 — Run the Pathfinder Tests

```bash
./gradlew test --tests "frc.lib.pathfinding.*" --info
```

**Tasks:**
1. How many pathfinding tests ran total?
2. Find the performance test. What's the time threshold?
3. What does the "unreachable" test verify?

### Sim Exercise 4.2 — Build Your Own Grid

Write a Java test that creates a custom grid and pathfinds through it.

```java
@Test
void myCustomPathTest() {
    // Build a 10×10 grid with a wall
    int[][] grid = new int[10][10];
    // Add a vertical wall at column 5, rows 0-7 (leaving a gap at row 8-9)
    for (int r = 0; r < 8; r++) {
        grid[r][5] = 1;
    }

    NavigationGrid navGrid = new NavigationGrid(grid, 1.0); // 1m cells for easy math
    AStarPathfinder pathfinder = new AStarPathfinder();

    // Find path from (0,0) to (9,9)
    List<Translation2d> path = pathfinder.findPath(
        new Translation2d(0.5, 0.5),   // center of cell (0,0)
        new Translation2d(9.5, 9.5),   // center of cell (9,9)
        navGrid
    );

    // YOUR ASSERTIONS HERE:
    // 1. Path should not be empty
    // 2. Path should have more than 2 waypoints (can't go straight)
    // 3. No waypoint should be in column 5, rows 0-7 (the wall)
}
```

**Challenge:** Add a dynamic obstacle and verify the path routes around it too.

### Sim Exercise 4.3 — Grid Visualization (Paper)

On graph paper, draw a 20×20 grid. Mark these obstacles:

```
Static wall: columns 8-9, rows 0-14
Static wall: columns 8-9, rows 16-19
Gap at: columns 8-9, row 15

Dynamic opponent 1: center (5, 10), size 0.8m (cells 4-5, rows 9-10)
Dynamic opponent 2: center (14, 8), size 0.8m (cells 13-14, rows 7-8)
```

Now draw the A* path from (0, 0) to (19, 19). Use different colors for:
- Blue: the path
- Red: cells explored but not on the final path
- Gray: obstacle cells

---

## Exercise Set 5: Vision & YOLO (Module 5 Companion)

### Sim Exercise 5.1 — Array Parser Challenge

Write or modify a test that constructs `llpython` arrays and feeds them to
`FuelDetectionConsumer`. Verify the output.

```bash
./gradlew test --tests "frc.robot.subsystems.FuelDetectionConsumerTest" --info
```

**Tasks:**
1. Run the existing tests. How many pass?
2. Read the test code. Identify which test covers:
   - The 80% confidence filter
   - The 3-frame persistence requirement
   - Empty/null array handling

### Sim Exercise 5.2 — Pixel-to-Field Calculator

Build a quick calculator (spreadsheet, Python, or on paper) that implements
`_pixel_to_field()`. Test it with these inputs:

| cx_px | cy_px | robot_x | robot_y | heading_rad | Expected distance | Expected field_x | Expected field_y |
|-------|-------|---------|---------|-------------|-------------------|-------------------|-------------------|
| 320 | 400 | 0.0 | 0.0 | 0.0 | ~0.68m | ~0.68 | ~0.0 |
| 320 | 240 | 0.0 | 0.0 | 0.0 | — | None (at horizon) | None |
| 480 | 350 | 5.0 | 3.0 | 1.57 | ~1.0m | ~5.0 | ~4.0 |

Camera: height=0.50m, pitch=-15°, FOV_H=63.3°, FOV_V=49.7°

**Note:** Row 2 should return None — the pixel is at the camera's optical center,
and with -15° pitch the total depression is exactly 15°, which gives a finite
distance. Adjust: try cy_px = 100 (above horizon) to get None.

### Sim Exercise 5.3 — Persistence State Machine

Draw the persistence filter as a state machine diagram:

```
States: NO_CANDIDATE, COUNT_1, COUNT_2, CONFIRMED
Transitions:
  - Detection appears (within 0.5m of existing position)
  - Detection disappears (no match this frame)
  - Detection appears at a new position (> 0.5m from any candidate)
```

For each transition, label what happens to the candidate's count and position.

---

## Exercise Set 6: Simulation & Testing (Module 6 Companion)

### Sim Exercise 6.1 — Full Build Audit

Run the complete build and record the results:

```bash
./gradlew clean build 2>&1 | tee build_output.txt
```

**Fill in this report card:**

| Gate | Passed? | Details |
|------|---------|---------|
| Spotless | ? | Any files reformatted? |
| SpotBugs | ? | Any findings? |
| JUnit | ? | Tests run / passed / failed / skipped |
| JaCoCo | ? | frc.lib coverage % |
| Overall | ? | BUILD SUCCESSFUL or FAILED? |

### Sim Exercise 6.2 — Write 3 New Tests

Pick ANY class from the list below and write 3 new tests that don't already exist.
Each test must follow Arrange-Act-Assert.

**Suggested classes:**
- `CycleTracker` — test edge cases (what if markPickup() is called twice?)
- `StallDetector` — test boundary conditions (exactly at threshold duration)
- `SpeedModeManager` — test rapid toggling
- `MovingShotCompensation` — test extreme velocities
- `RumbleManager` — test pattern completion

```bash
# Run your new tests:
./gradlew test --tests "your.test.ClassName"
```

**Requirements:**
- All 3 tests must pass
- Build must still pass after adding them (`./gradlew build`)
- Tests must be HAL-free (no Constants imports)

### Sim Exercise 6.3 — Coverage Improvement Challenge

```bash
./gradlew test jacocoTestReport
open build/reports/jacoco/test/html/index.html
```

1. Find the class with the LOWEST coverage in `frc.lib`
2. Identify 3 uncovered lines (red in the report)
3. Write tests that cover those lines
4. Re-run coverage. Did it go up?

**Goal:** Improve `frc.lib` coverage by at least 2 percentage points.

### Sim Exercise 6.4 — Simulation Observation Log

```bash
./gradlew simulateJava
```

Connect AdvantageScope to `localhost:3300`. Run autonomous mode for 15 seconds.
Fill in this observation log:

| Timestamp | Robot Pose (x, y) | Current Target | Action Type | Utility | Notes |
|-----------|-------------------|----------------|-------------|---------|-------|
| 0.0s | | | | | Match start |
| 2.0s | | | | | |
| 5.0s | | | | | |
| 10.0s | | | | | |
| 14.0s | | | | | Near endgame |

**Questions:**
1. Did the robot switch targets during the run? At what time and why?
2. Did the Bot Aborter trigger? How can you tell from the logs?
3. What was the average cycle time (if any cycles completed)?

### Sim Exercise 6.5 — Break It and Fix It

Intentionally introduce each of these bugs (one at a time). Run the build. Record
what catches it. Then fix it.

| Bug | What to Do | Gate That Catches It |
|-----|-----------|---------------------|
| 1 | Remove a semicolon from any .java file | ? |
| 2 | Add `String s = null; s.length();` to any method | ? |
| 3 | Change an assertion's expected value to something wrong | ? |
| 4 | Delete a test for a `frc.lib` class | ? |
| 5 | Add `int x=5;if(x>3){}` with bad formatting | ? |

**Answer Key:**
1. Compiler (not even a quality gate — Java won't compile)
2. SpotBugs (null dereference)
3. JUnit (assertion failure)
4. JaCoCo (coverage drops below 80%)
5. Spotless (reformats automatically, so it "catches" by fixing it)

**Important:** Revert all changes after each experiment: `git checkout -- .`

---

## Scoring & Completion

Each exercise set is worth 10 points. Track your team's progress:

| Exercise Set | Max Points | Student Score | Date Completed |
|-------------|-----------|---------------|----------------|
| Set 1: Pattern Rules | 10 | | |
| Set 2: Prediction Engine | 10 | | |
| Set 3: Design Intelligence | 10 | | |
| Set 4: Pathfinding | 10 | | |
| Set 5: Vision & YOLO | 10 | | |
| Set 6: Sim & Testing | 10 | | |
| **TOTAL** | **60** | | |

**Scoring guide:**
- Completed exercise with correct answers: full points
- Completed exercise with minor errors: -1 per error
- Attempted but incomplete: half points
- Not attempted: 0

**Badges:**
- 50-60 points: **Engine Master** — ready to lead a subsystem
- 35-49 points: **Engine Operator** — can contribute code independently
- 20-34 points: **Engine Apprentice** — can contribute with mentor guidance
- 0-19 points: **Engine Observer** — keep learning, you'll get there

---

*F.9 Simulation Exercises | THE ENGINE Student Training | Team 2950 The Devastators*
