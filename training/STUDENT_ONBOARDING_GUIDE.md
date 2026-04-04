# THE ENGINE — Student Onboarding Guide
# Block F.10 | Your first day on Team 2950's programming subteam

---

## Welcome to The Engine

You're joining the programming subteam of **Team 2950 — The Devastators**. This
guide will get you from "I just cloned the repo" to "I'm running the robot in
simulation" in about 2 hours.

No prior robotics experience required. If you can open a terminal, you can do this.

---

## Step 1: Set Up Your Laptop (30 min)

### Install These (If You Don't Have Them Already)

| Tool | What It Does | Install Link |
|------|-------------|-------------|
| **WPILib 2026** | FRC development environment (includes Java 17, VS Code, Gradle) | wpilib.org → Getting Started |
| **Git** | Version control | git-scm.com (Mac: already installed via Xcode tools) |
| **AdvantageScope** | Robot log viewer and field visualizer | github.com/Mechanical-Advantage/AdvantageScope/releases |

### Clone the Repository

```bash
cd ~/Desktop
git clone <your-team-repo-url> constructicon
cd constructicon
```

### Verify Your Setup

```bash
./gradlew build
```

This downloads dependencies (first run takes 3-5 minutes), compiles the code, runs
all tests, and checks code quality. If it ends with **BUILD SUCCESSFUL**, you're
ready.

If it fails:
- "Java not found" → Install WPILib (it includes Java 17)
- "Could not resolve dependencies" → Check internet connection
- Test failure → Ask a veteran, the code might have a known issue

---

## Step 2: Understand the Project Structure (15 min)

Open the `constructicon` folder in VS Code (or your editor). Here's what matters:

```
constructicon/
├── src/
│   ├── main/java/frc/
│   │   ├── robot/              ← ROBOT CODE (the main stuff)
│   │   │   ├── Robot.java          Entry point
│   │   │   ├── RobotContainer.java Button bindings, subsystem creation
│   │   │   ├── Constants.java      All tunable numbers
│   │   │   ├── subsystems/         Hardware interfaces (swerve, flywheel, etc.)
│   │   │   ├── commands/           Actions the robot performs
│   │   │   └── autos/             Autonomous decision-making
│   │   └── lib/                ← REUSABLE LIBRARIES
│   │       └── pathfinding/        A* pathfinder, navigation grid, avoidance
│   └── test/java/frc/         ← TESTS (mirrors main structure)
│       ├── robot/
│       └── lib/
├── design-intelligence/        ← TRAINING MODULES & PATTERN DATABASE
│   ├── TRAINING_MODULE_1_PATTERN_RULES.md
│   ├── TRAINING_MODULE_2_PREDICTION_ENGINE.md
│   ├── ... (6 modules total)
│   ├── SIMULATION_EXERCISES.md
│   ├── 254_CROSS_SEASON_ANALYSIS.md
│   ├── MULTI_TEAM_ANALYSIS.md
│   └── KICKOFF_TEMPLATE.md
├── tools/                      ← VISION SCRIPTS & MODELS
│   ├── wave_fuel_detector.onnx     YOLO model for game piece detection
│   └── snapscript_fuel_detector.py Limelight Python script
├── PROGRESS.md                 ← What's done, what's next
├── ARCHITECTURE.md             ← System design overview
└── build.gradle                ← Build configuration (quality gates live here)
```

### The 3 Most Important Files to Read First

1. **`PROGRESS.md`** — Shows every feature and its status. Start here to understand scope.
2. **`ARCHITECTURE.md`** — Diagrams of how subsystems connect.
3. **`Constants.java`** — Every tunable number in one place.

---

## Step 3: Run the Robot in Simulation (15 min)

You don't need a physical robot. The simulation runs everything on your laptop.

### Launch Simulation

```bash
./gradlew simulateJava
```

This opens a WPILib simulation GUI (a fake driver station).

### Connect AdvantageScope

1. Open AdvantageScope
2. Click **File → Connect to Simulator**  (or enter `localhost:3300`)
3. Open a **Field** tab
4. Drag `RobotPose` from the log tree onto the field

### Try These Things

**Teleop (driver control):**
1. In the sim GUI, click **Teleop**
2. Open the **System Joysticks** panel
3. Use a connected gamepad or keyboard to drive
4. Watch the robot move on the AdvantageScope field

**Autonomous:**
1. In the sim GUI, click **Autonomous**
2. Watch the robot drive itself
3. In AdvantageScope, look for `AutonomousStrategy/BestTarget` in the log tree

**Disabled:**
1. Click **Disabled** to stop the robot
2. Nothing should move — this is normal and correct

### What You Just Did

You ran the full robot software — swerve drive physics, autonomous strategy, state
machine, logging — all on your laptop. Every change you make to the code can be
tested this way before touching the real robot.

---

## Step 4: Run the Tests (10 min)

```bash
./gradlew test
```

You should see something like:
```
> Task :test
246 tests completed, 0 failed
BUILD SUCCESSFUL
```

### Read a Test

Open `src/test/java/frc/robot/autos/AutonomousStrategyTest.java`. Notice the
pattern:

```java
@Test
void testHubActive_prefersScoring() {
    // ARRANGE — set up the scenario
    GameState state = new GameState()
        .withFuelHeld(3)
        .withHubActive(true)
        .withTimeRemaining(60.0);

    // ACT — run the code
    List<ScoredTarget> targets = strategy.evaluateTargets(state);

    // ASSERT — check the result
    assertEquals(ActionType.SCORE, targets.get(0).actionType());
}
```

Every test follows **Arrange-Act-Assert**. Once you learn this pattern, you can
read (and write) any test in the codebase.

---

## Step 5: Make Your First Change (15 min)

Let's make a small, safe change to prove you can modify the code and verify it works.

### The Task

Open `src/main/java/frc/robot/autos/CycleTracker.java`. Find the `CyclePhase` enum:

```java
enum CyclePhase {
    IDLE,
    SEEKING,
    CARRYING,
    SCORING
}
```

We're going to add a log message. In the `startCycle()` method, find where the
phase changes and add a print:

```java
System.out.println("[CycleTracker] Cycle started — transitioning to SEEKING");
```

### Verify Your Change

```bash
./gradlew build
```

If it says **BUILD SUCCESSFUL**, your change is clean. The formatting was auto-fixed
by Spotless, SpotBugs found no bugs, and all tests still pass.

### Revert Your Change

This was just practice. Revert it:

```bash
git checkout -- src/main/java/frc/robot/autos/CycleTracker.java
```

---

## Step 6: Start the Training Modules (ongoing)

The `design-intelligence/` folder contains 6 training modules plus simulation
exercises. Here's the recommended order and pace:

### Week 1 (Orientation)

| Day | Module | Time | Focus |
|-----|--------|------|-------|
| Day 1 | This onboarding guide | 2 hrs | Setup, sim, first change |
| Day 2 | Module 1: Pattern Rules | 45 min | How top teams design robots |
| Day 3 | Module 2: Prediction Engine | 60 min | Utility scoring, Bot Aborter |

### Week 2 (Deep Dive)

| Day | Module | Time | Focus |
|-----|--------|------|-------|
| Day 1 | Module 3: Design Intelligence | 60 min | Full pipeline, kickoff template |
| Day 2 | Module 4: Pathfinding | 50 min | A* algorithm, navigation grids |
| Day 3 | Module 5: Vision & YOLO | 55 min | Camera to field coordinates |

### Week 3 (Practice)

| Day | Module | Time | Focus |
|-----|--------|------|-------|
| Day 1 | Module 6: Simulation & Testing | 55 min | Quality gates, writing tests |
| Day 2 | Simulation Exercises Sets 1-3 | 60 min | Hands-on practice |
| Day 3 | Simulation Exercises Sets 4-6 | 60 min | Build + sim challenges |

**Veterans:** You can skip Modules 1-2 and start at Module 3 if you already
understand utility functions and pattern matching.

---

## Step 7: Know Your Resources

### In the Repo

| File | What It's For |
|------|--------------|
| `PROGRESS.md` | What's done, what's blocked, what's next |
| `ARCHITECTURE.md` | System design diagrams |
| `MENTOR_BRIEFING.md` | Technical overview for programming mentors |
| `HOW_TO_PACKAGE.md` | How to share the code with others |
| `COMPETITION_DATA_CHECKLIST.md` | What data to collect at events |

### Key Commands

```bash
# ── Everyday Commands ──────────────────────────
./gradlew build               # Compile + all 4 quality gates
./gradlew test                # Run tests only
./gradlew simulateJava        # Launch simulation
./gradlew spotlessApply       # Auto-format your code

# ── When You Want Details ──────────────────────
./gradlew test --tests "*.ClassName"   # Run one test class
./gradlew test jacocoTestReport        # Generate coverage report
./gradlew spotbugsMain                 # Run static analysis

# ── Git Basics ─────────────────────────────────
git status                    # What files did I change?
git diff                      # What exactly did I change?
git add <file>                # Stage a file for commit
git commit -m "message"       # Save your changes
git pull                      # Get latest from team
git push                      # Share your changes
```

### When You're Stuck

1. **Read the error message.** 90% of the time it tells you exactly what's wrong.
2. **Run `./gradlew build`** to see if the code compiles and tests pass.
3. **Search the codebase.** Use `grep -r "keyword" src/` or your IDE's search.
4. **Ask a veteran.** No question is too basic.
5. **Check the training modules.** The answer might be in Modules 1-6.

---

## Quick Glossary

Terms you'll hear at meetings that might be confusing at first:

| Term | What It Means |
|------|--------------|
| **Swerve** | Drivetrain where each wheel rotates independently — can drive in any direction |
| **Subsystem** | A hardware group (drivetrain, flywheel, intake, etc.) managed by one Java class |
| **Command** | An action the robot performs (drive, score, climb) — tied to subsystems |
| **Autonomous / Auto** | The 15-second period where the robot drives itself with no human input |
| **Teleop** | The 135-second period where drivers control the robot |
| **Deploy** | Sending code from your laptop to the robot's roboRIO computer |
| **roboRIO** | The small computer inside the robot that runs our Java code |
| **CAN bus** | The wire network connecting the roboRIO to all motors and sensors |
| **Limelight** | A camera + processor that runs vision pipelines (AprilTag + YOLO) |
| **AdvantageKit** | Logging framework — records everything the robot does for replay |
| **AdvantageScope** | Desktop app to visualize robot logs (field view, graphs, 3D) |
| **NetworkTables** | WPILib's data-sharing system between robot, dashboard, and camera |
| **YOLO** | Neural network that detects game pieces in camera images |
| **Utility score** | A number rating how "good" an action is — higher = better |
| **Bot Aborter** | Logic that gives up on a target if an opponent will get there first |
| **Spotless** | Auto-formatter that enforces consistent code style |
| **SpotBugs** | Static analyzer that finds bug patterns without running the code |
| **JaCoCo** | Coverage tool measuring what % of code is tested |
| **HAL** | Hardware Abstraction Layer — WPILib's interface to robot hardware |
| **maple-sim** | Physics simulation that fakes swerve drive, collisions, inertia |

---

## Your First Week Checklist

Check off each item as you complete it:

- [ ] Cloned the repo and ran `./gradlew build` successfully
- [ ] Launched simulation with `./gradlew simulateJava`
- [ ] Connected AdvantageScope and saw the robot on the field
- [ ] Drove the robot in teleop simulation
- [ ] Watched the robot run autonomous
- [ ] Ran `./gradlew test` and saw all tests pass
- [ ] Read `PROGRESS.md` to understand the project scope
- [ ] Opened `Constants.java` and found 3 tunable values
- [ ] Made a test change, verified the build, and reverted it
- [ ] Completed Module 1 (Pattern Rules)
- [ ] Completed Module 2 (Prediction Engine)
- [ ] Calculated a utility score by hand

If you can check all 12 boxes, you're off to a great start. Welcome to the team.

---

*F.10 Student Onboarding Guide | THE ENGINE | Team 2950 The Devastators*
