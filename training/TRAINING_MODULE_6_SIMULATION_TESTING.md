# THE ENGINE — Student Training Module 6: Simulation & Testing
# Block F.8 (Part 6 of 6) | Audience: Veterans + Rookies | Time: ~55 minutes

---

## What You'll Learn

By the end of this module, you will be able to:
1. Explain why simulation and testing exist and what they catch
2. Run the robot in simulation mode and observe behavior in AdvantageScope
3. Read and write a JUnit 5 test for Engine components
4. Understand the 4 build quality gates (Spotless, SpotBugs, JaCoCo, JUnit)
5. Know the HAL-free testing pattern and why it matters
6. Use the build system to catch bugs before they reach the robot

---

## Section 1: Why Test? Why Simulate? (5 min)

### The Competition Reality

At competition, you get **5-10 minutes between matches** to fix bugs. If your code crashes on the field, you lose that match — and maybe your tournament.

Testing and simulation let you find bugs **before** you get to the field:

| When Bug Is Found | Cost to Fix |
|-------------------|------------|
| In a unit test | 30 seconds — fix and re-run |
| In simulation | 5 minutes — observe, fix, re-simulate |
| In the pit | 10-30 minutes — rush, stress, maybe miss next match |
| During a match | **Cannot fix** — you lose the match |

### What Each Layer Catches

```
┌───────────────────────────────────────────────────┐
│  Layer 4: COMPETITION        Catches: Nothing new │
│  (This should be BORING —    (Everything was      │
│   no surprises!)              caught earlier)      │
├───────────────────────────────────────────────────┤
│  Layer 3: SIMULATION         Catches: Integration │
│  (Full robot, fake physics)  issues, state machine│
│                              transitions, timing  │
├───────────────────────────────────────────────────┤
│  Layer 2: UNIT TESTS         Catches: Logic bugs, │
│  (Individual components)     math errors, edge    │
│                              cases, regressions   │
├───────────────────────────────────────────────────┤
│  Layer 1: QUALITY GATES      Catches: Format,     │
│  (Automatic code checks)     style, null bugs,    │
│                              missing coverage     │
└───────────────────────────────────────────────────┘
```

---

## Section 2: The 4 Build Quality Gates (15 min)

Every time you run `./gradlew build`, four automatic checks run. If ANY of them fails, the build fails and you must fix it before deploying.

### Gate 1: Spotless (Code Formatting)

**What it does:** Automatically formats all Java code to Google Java Format.

**Why it matters:** Consistent formatting means anyone can read anyone's code. No arguments about tabs vs spaces, brace placement, or import ordering.

```bash
# Format all code:
./gradlew spotlessApply

# Check formatting without fixing:
./gradlew spotlessCheck
```

**Config in build.gradle:**
```groovy
spotless {
    java {
        target "src/**/*.java"
        googleJavaFormat("1.25.2")
        removeUnusedImports()
        trimTrailingWhitespace()
        endWithNewline()
    }
}
```

**Example:** Before Spotless:
```java
public void doThing( ){
    int x=5;
    if(x>3){
    System.out.println("hi");
    }}
```

After Spotless:
```java
public void doThing() {
    int x = 5;
    if (x > 3) {
        System.out.println("hi");
    }
}
```

> **Rookie Tip:** You don't need to worry about formatting while writing code. Just run `./gradlew spotlessApply` and it fixes everything automatically.

---

### Gate 2: SpotBugs (Static Analysis)

**What it does:** Scans compiled code for common bug patterns WITHOUT running it.

**Why it matters:** Catches bugs that are easy to write but hard to spot in review:

| Bug Pattern | Example | Why It's Bad |
|------------|---------|-------------|
| Null dereference | `obj.method()` when obj might be null | Crashes at runtime |
| Unused return value | `list.add(x)` but not checking result | Might silently fail |
| Wrong comparison | `str == "hello"` instead of `.equals()` | Always false in Java |
| Resource leak | Opening a file without closing it | Memory leak |
| Dead store | `x = 5; x = 10;` (first value never used) | Wasted computation |

```bash
# Run SpotBugs:
./gradlew spotbugsMain

# View report:
open build/reports/spotbugs/main.html
```

**Config:**
```groovy
spotbugs {
    reportLevel = "MEDIUM"    // Catches real bugs, low noise
    ignoreFailures = false    // Build FAILS if bugs found
    toolVersion = "4.8.6"
}
```

**Real example from our code:** SpotBugs caught `vision.hasTarget()` being called but the return value was ignored. The fix was storing the result and logging it:
```java
// BAD (SpotBugs flags this):
vision.hasTarget();

// GOOD:
boolean hasTarget = vision.hasTarget();
Logger.recordOutput("SelfTest/VisionHasTarget", hasTarget);
```

---

### Gate 3: JaCoCo (Test Coverage)

**What it does:** Measures what percentage of your code is exercised by tests.

**Why it matters:** Code that isn't tested might have bugs you don't know about.

**Our thresholds:**
| Package | Required Coverage | Why |
|---------|------------------|-----|
| `frc.lib.*` | **80% line coverage** | Pure math — no excuses, fully testable |
| `frc.robot.*` | 50% target (not enforced) | Hardware-coupled, harder to test |

```bash
# Run tests + generate coverage report:
./gradlew test jacocoTestReport

# View report:
open build/reports/jacoco/test/html/index.html
```

The coverage report shows which lines are green (tested) and red (not tested):

```
Green:  if (speed > MAX_SPEED) {      ← test covers this
Green:      speed = MAX_SPEED;        ← test covers this
Red:    } else if (speed < -MAX_SPEED) { ← NO test reaches this!
Red:        speed = -MAX_SPEED;
        }
```

> **Key Insight:** 80% coverage on `frc.lib` is a **hard gate** — the build FAILS if it drops below. This forces you to write tests when you add new library code.

---

### Gate 4: JUnit 5 (Unit Tests)

**What it does:** Runs all 246+ automated tests. Any failure blocks the build.

```bash
# Run all tests:
./gradlew test

# Run a specific test class:
./gradlew test --tests "frc.robot.autos.AutonomousStrategyTest"
```

We'll cover writing tests in detail in Section 3.

---

### Running All 4 Gates At Once

```bash
./gradlew build
```

This runs: `spotlessApply` → compile → `spotbugsMain` → `test` → `jacocoTestReport` → `jacocoTestCoverageVerification`

If the output ends with `BUILD SUCCESSFUL`, all 4 gates passed. Deploy with confidence.

---

## Section 3: Writing Unit Tests (15 min)

### Test Structure: Arrange-Act-Assert

Every test follows the same pattern:

```java
@Test
void testDescriptiveName() {
    // ARRANGE — set up the inputs
    GameState state = new GameState()
        .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
        .withFuelHeld(3)
        .withHubActive(true)
        .withTimeRemaining(60.0);

    // ACT — call the method under test
    List<ScoredTarget> targets = strategy.evaluateTargets(state);

    // ASSERT — verify the result
    assertEquals(ActionType.SCORE, targets.get(0).actionType(),
        "Should prefer scoring when HUB is active and holding FUEL");
}
```

### Common Assertions

```java
// Value equality
assertEquals(expected, actual, "message if wrong");

// Boolean checks
assertTrue(condition, "message");
assertFalse(condition, "message");

// Null checks
assertNotNull(object, "message");

// Exception expected
assertThrows(IllegalArgumentException.class, () -> {
    dangerousMethod(-1);
});

// Floating-point comparison (with tolerance)
assertEquals(3.14, result, 0.01, "Pi should be approximately 3.14");
```

### The HAL-Free Testing Pattern

**THE MOST IMPORTANT TESTING RULE:**

> **Never import `frc.robot.Constants` in test files.**

Why? `Constants` imports WPILib classes, which trigger HAL JNI native library loading. This crashes in a plain JUnit environment (no robot, no roboRIO).

**BAD — crashes:**
```java
import frc.robot.Constants;

@Test
void test() {
    double threshold = Constants.Pathfinding.kFuelConfidenceThreshold; // CRASH!
}
```

**GOOD — hardcode the value:**
```java
@Test
void test() {
    double threshold = 0.80; // Same as Constants.Pathfinding.kFuelConfidenceThreshold
}
```

This is why our testable classes use **dependency injection** — they take values as constructor/method parameters instead of reading from Constants:

```java
// Testable: accepts clock as parameter
public class CycleTracker {
    private final DoubleSupplier clock;
    public CycleTracker(DoubleSupplier clock) {
        this.clock = clock;
    }
}

// In production: real clock
new CycleTracker(Timer::getFPGATimestamp);

// In tests: fake clock you control
double[] time = {0.0};
CycleTracker tracker = new CycleTracker(() -> time[0]);
time[0] = 5.0; // "advance" time to 5 seconds
```

### Testing Patterns Used in The Engine

#### Pattern 1: Fluent GameState Construction

```java
GameState state = new GameState()
    .withRobotPose(new Pose2d(4.0, 4.0, new Rotation2d()))
    .withFuelHeld(2)
    .withHubActive(true)
    .withTimeRemaining(60.0)
    .withDetectedFuel(List.of(new Translation2d(6.0, 4.0)));
```

#### Pattern 2: Injectable Clock for Time-Based Logic

```java
double[] time = {0.0};
StallDetector detector = new StallDetector(
    0.5,          // threshold duration
    40.0,         // current threshold amps
    () -> time[0], // injectable clock
    () -> 50.0     // injectable current (over threshold)
);

time[0] = 0.6; // advance past threshold
detector.update();
assertTrue(detector.isStalled());
```

#### Pattern 3: Direct Grid Construction for Pathfinding Tests

```java
int[][] grid = {
    {0, 0, 0, 0, 0},
    {0, 0, 1, 0, 0},  // 1 = obstacle in center
    {0, 0, 1, 0, 0},
    {0, 0, 0, 0, 0},
    {0, 0, 0, 0, 0}
};
NavigationGrid navGrid = new NavigationGrid(grid, 0.1);
```

#### Pattern 4: Static Method Testing (No Hardware Needed)

```java
@Test
void testBotAborter_opponentArriveFirst_aborts() {
    assertTrue(AutonomousStrategy.shouldAbortTarget(
        3.0, 2.0,   // robot: 3m away, 2 m/s
        1.0, 3.0    // opponent: 1m away, 3 m/s
    ));
}
```

---

## Section 4: Simulation (10 min)

### What Is Simulation?

Simulation runs the FULL robot code on your laptop, with fake physics replacing real motors and sensors. The robot "drives" in a virtual field.

**Stack:**
- **maple-sim 0.4.0-beta** — Physics engine (dyn4j) simulating swerve drive, collisions, inertia
- **WPILib HALSim** — Fake hardware abstraction layer
- **AdvantageScope** — Visualization tool showing the robot on a field

### Running the Simulation

```bash
# Start the sim:
./gradlew simulateJava

# This opens:
# 1. A WPILib sim GUI (driver station)
# 2. WebSocket server on port 3300 (for AdvantageScope)
```

Then open AdvantageScope and connect to `localhost:3300`.

### What You Can Test in Simulation

| Feature | How to Test | What to Look For |
|---------|-------------|-----------------|
| Swerve drive | Enable teleop, use virtual joystick | Robot moves smoothly, no drift |
| Autonomous | Enable auto, select routine | Robot follows path, scores targets |
| State machine | Trigger transitions via SmartDashboard | Correct state sequence, no illegal transitions |
| Odometry | Drive a known path | Odometry matches expected position |
| LED patterns | Trigger different states | LED log shows correct colors |

### What You CANNOT Test in Simulation

| Feature | Why Not |
|---------|---------|
| Real CAN bus | No physical CAN devices |
| Actual motor current | Physics approximate only |
| Vision with real camera | No physical camera in sim |
| Exact match timing | Sim clock may not match real-time |
| Mechanical failures | Can't simulate broken gears |

### AdvantageScope Field Overlay

AdvantageScope can show the robot on a field map in real-time:

1. Connect to the sim
2. Open a **Field** tab
3. Drag `RobotPose` from the log tree onto the field
4. Drag `AutonomousStrategy/BestTarget` to see where the robot is heading
5. Drag `FuelDetections` to see detected game pieces

This is how you visually verify that the strategy engine is making good decisions.

---

## Section 5: The Testing Pyramid (5 min)

Our 246+ tests are organized in a pyramid:

```
                    ╱╲
                   ╱  ╲
                  ╱ 10 ╲         Integration tests
                 ╱      ╲        (AutonomousIntegrationTest,
                ╱────────╲        FaultInjectionTest)
               ╱          ╲
              ╱    ~50      ╲     Component tests
             ╱              ╲    (AutonomousStrategy, NavigationGrid,
            ╱────────────────╲    CycleTracker, StallDetector, etc.)
           ╱                  ╲
          ╱      ~186          ╲  Unit tests
         ╱                      ╲ (Math functions, state machines,
        ╱────────────────────────╲ parsers, converters, etc.)
```

**Unit tests (bottom):** Test one method in isolation. Fast (< 1ms each). Example: "Does `shouldAbortTarget()` return true when opponent arrives 0.75s first?"

**Component tests (middle):** Test one class with its real dependencies. Example: "Does `CycleTracker` correctly measure cycle time across 3 phases?"

**Integration tests (top):** Test multiple systems together. Example: "Does the full autonomous loop collect fuel and score when GameState changes?"

**Why a pyramid?** Unit tests are cheap and fast. Integration tests are expensive and slow. You want MANY cheap tests and FEW expensive tests.

---

## Section 6: Hands-On Exercises

### Exercise A: Run the Build (All Levels, 5 min)

Open a terminal in the constructicon directory and run:

```bash
./gradlew build
```

**Questions:**
1. Did it pass? What was the last line?
2. How many tests ran? (Look for "X tests completed")
3. How long did the build take?

If it failed, read the error message. Which gate failed? What does the error say?

---

### Exercise B: Write Your First Test (All Levels, 10 min)

Let's write a test for the Bot Aborter. Create a mental model first:

**Scenario:** Robot is 2m away going 3 m/s. Opponent is 4m away going 1 m/s.
- Robot ETA: 2/3 = 0.667s
- Opponent ETA: 4/1 = 4.0s
- Difference: 0.667 - 4.0 = -3.33s (robot arrives WAY first)
- Should abort? NO

Now write the test:

```java
@Test
void testBotAborter_robotArrivesMuchFirst_continues() {
    // ARRANGE: robot close+fast, opponent far+slow
    double robotDist = 2.0;
    double robotSpeed = 3.0;
    double opponentDist = 4.0;
    double opponentSpeed = 1.0;

    // ACT
    boolean shouldAbort = AutonomousStrategy.shouldAbortTarget(
        robotDist, robotSpeed, opponentDist, opponentSpeed);

    // ASSERT
    assertFalse(shouldAbort,
        "Robot arrives 3.3s before opponent — should NOT abort");
}
```

**Your turn:** Write tests for these scenarios:
1. Robot stopped (speed = 0) → should abort
2. Opponent stopped (speed = 0) → should NOT abort
3. Dead heat (both arrive at nearly the same time, diff < 0.75s) → should NOT abort

---

### Exercise C: Break the Build (Veterans, 10 min)

Intentionally break each quality gate and observe the error:

**Gate 1 — Spotless:**
```java
// Add terrible formatting to any .java file:
public void ugly(   ){int x=5;if(x>3){}}
```
Run `./gradlew spotlessCheck` (not `spotlessApply`). See the error. Then run `spotlessApply` to fix.

**Gate 2 — SpotBugs:**
```java
// Add an unused return value:
public void buggy() {
    List<String> items = new ArrayList<>();
    items.add("test"); // SpotBugs may flag this depending on context
    String s = null;
    s.length(); // Definite null dereference — SpotBugs will catch this
}
```
Run `./gradlew spotbugsMain`. Read the report.

**Gate 3 — JaCoCo:**
Add a new method to a `frc.lib` class without writing a test. Run `./gradlew build`. If coverage drops below 80%, the build fails.

**Gate 4 — JUnit:**
Change an assertion to something wrong:
```java
assertEquals(ActionType.CLIMB, targets.get(0).actionType()); // Wrong on purpose
```
Run `./gradlew test`. Read the failure message.

**After each experiment, revert your changes** (`git checkout -- .`).

---

### Exercise D: Read a Coverage Report (All Levels, 5 min)

```bash
./gradlew test jacocoTestReport
open build/reports/jacoco/test/html/index.html
```

1. Find the `frc.lib.pathfinding` package. What's its line coverage percentage?
2. Click into `AStarPathfinder`. Which lines are green? Which are red?
3. Find `DynamicAvoidanceLayer`. Is the repulsive force calculation fully covered?

---

### Exercise E: Simulation Walkthrough (Veterans, 10 min)

```bash
./gradlew simulateJava
```

1. Open AdvantageScope, connect to `localhost:3300`
2. Enable autonomous mode in the sim GUI
3. Watch the robot drive. Open the log tree and find:
   - `SwerveSubsystem/Odometry` → robot position
   - `AutonomousStrategy/BestTarget` → where it's heading
   - `CycleTracker/Phase` → current cycle phase
4. Does the robot complete a full collect → score cycle?
5. Change to teleop mode. Use the virtual joystick. Does field-relative driving work?

---

### Exercise F: Design a Test (Discussion, All Levels)

You're adding a new feature: the robot should blink its LEDs red when the conveyor jams (current > 40A for > 0.5 seconds).

**Design questions:**
1. What class would you test? (Hint: we already have `StallDetector`)
2. What would you inject? (clock, current supplier)
3. Write 3 test scenarios in English:
   - Test 1: Current stays below 40A → no stall detected
   - Test 2: Current exceeds 40A for 0.3s → not long enough, no stall
   - Test 3: Current exceeds 40A for 0.6s → stall detected!

4. Why don't you need to test actual LEDs in the unit test?
   - Because the unit test verifies `isStalled()` returns true. The LED logic is a separate concern — it reads `isStalled()` and sets LED color. You'd test that separately.

---

## Key Vocabulary

| Term | Definition |
|------|-----------|
| **Unit Test** | Tests one method/function in isolation |
| **Integration Test** | Tests multiple components working together |
| **Quality Gate** | Automatic check that blocks deployment if it fails |
| **Spotless** | Code formatter — enforces consistent style |
| **SpotBugs** | Static analyzer — finds bug patterns without running code |
| **JaCoCo** | Coverage tool — measures what % of code is tested |
| **JUnit 5** | Java testing framework (uses `@Test`, assertions) |
| **HAL** | Hardware Abstraction Layer — WPILib's interface to robot hardware |
| **HAL-free** | Testing pattern that avoids loading native robot libraries |
| **Dependency Injection** | Passing dependencies (clock, sensors) as parameters instead of hardcoding |
| **Arrange-Act-Assert** | Test structure: set up inputs, call method, verify output |
| **maple-sim** | Physics simulation engine for FRC swerve robots |
| **AdvantageScope** | Log visualization tool — shows robot on field, plots data |

---

## Section 7: Quick Reference — Common Commands

```bash
# ── Build & Test ───────────────────────────────
./gradlew build              # All 4 gates + compile
./gradlew test               # JUnit tests only
./gradlew spotlessApply      # Auto-format code
./gradlew spotbugsMain       # Static analysis
./gradlew jacocoTestReport   # Coverage report

# ── Simulation ─────────────────────────────────
./gradlew simulateJava       # Launch sim + GUI

# ── Specific Tests ─────────────────────────────
./gradlew test --tests "frc.robot.autos.*"           # All auto tests
./gradlew test --tests "*.AutonomousStrategyTest"    # One class
./gradlew test --tests "*.CycleTrackerTest.testSingleCycle"  # One method

# ── Reports ────────────────────────────────────
open build/reports/tests/test/index.html             # Test results
open build/reports/jacoco/test/html/index.html       # Coverage
open build/reports/spotbugs/main.html                # Bug report
```

---

## Congratulations — You've Completed All 6 Modules!

Here's what you now know:

| Module | Topic | Key Skill |
|--------|-------|-----------|
| **1** | Pattern Rules | Read historical data, predict mechanism choices |
| **2** | Prediction Engine | Calculate utility scores, trace strategy decisions |
| **3** | Design Intelligence | Full pipeline from game reveal to running code |
| **4** | Pathfinding | A* algorithm, navigation grids, dynamic obstacles |
| **5** | Vision & YOLO | Camera → neural network → field coordinates |
| **6** | Simulation & Testing | Quality gates, unit tests, simulation, HAL-free pattern |

**You are now equipped to:**
- Contribute code to The Engine with confidence
- Debug autonomous decisions using telemetry data
- Write tests that catch bugs before competition
- Fill in the Kickoff Template on game reveal day
- Use pattern rules to make design recommendations

**Welcome to the team.**

---

*Module 6 of 6 | THE ENGINE Student Training | Team 2950 The Devastators*
