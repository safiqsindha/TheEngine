# THE ENGINE — Student Training Module 3: Understanding the Design Intelligence
# Block F.8 (Part 3 of 3) | Audience: Veterans + Rookies | Time: ~60 minutes

---

## What You'll Learn

By the end of this module, you will be able to:
1. Trace the full pipeline: Game Reveal → Pattern Rules → Kickoff Template → Code Configuration → Autonomous Decisions
2. Explain how every layer of The Engine connects
3. Walk through the FullAutonomousCommand execution loop
4. Use the Kickoff Template for a mock game reveal
5. Understand the A* pathfinder and navigation grid
6. Debug autonomous issues using telemetry and AdvantageScope

---

## Section 1: The Big Picture (10 min)

### The Design Intelligence Pipeline

The Engine isn't just robot code — it's a **decision-making pipeline** that starts before the robot is built and runs autonomously during matches.

```
┌─────────────────────────────────────────────────────────────┐
│                    DESIGN INTELLIGENCE                       │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │ PATTERN  │───▶│   KICKOFF    │───▶│ MECHANISM SPECS   │  │
│  │ DATABASE │    │  TEMPLATE    │    │ + BUILD PRIORITY  │  │
│  │ (7 teams │    │ (fill on     │    │ (what to build    │  │
│  │ 10 years)│    │  game day)   │    │  and in what      │  │
│  └──────────┘    └──────────────┘    │  order)           │  │
│       │                              └───────┬───────────┘  │
│       │                                      │              │
│  ┌────▼──────────────────────────────────────▼───────────┐  │
│  │              THE ENGINE CODEBASE                       │  │
│  │                                                       │  │
│  │  Constants.java ◄── Tuned per game                    │  │
│  │       │                                               │  │
│  │  GameState ──▶ AutonomousStrategy ──▶ ScoredTarget    │  │
│  │       │              │                     │          │  │
│  │  Vision +        Bot Aborter          Pick best       │  │
│  │  Odometry                                  │          │  │
│  │       │                                    ▼          │  │
│  │  NavigationGrid ──▶ A* Pathfinder ──▶ Path to target  │  │
│  │       │                                    │          │  │
│  │  Opponent         DynamicAvoidance     Dodge around    │  │
│  │  Positions            Layer            opponents       │  │
│  │       │                                    │          │  │
│  │       └────────────────────────────────────▼          │  │
│  │                                     DRIVE COMMAND      │  │
│  │                                     (every 20ms)       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### The Key Insight

Most FRC teams treat software as an afterthought — they build the robot first, then write code to drive it. The Engine **inverts this**: the software encodes decisions that were made *before* the robot was designed, based on patterns from the best teams in history.

---

## Section 2: Layer 1 — The Pattern Database (Review, 5 min)

You covered this in Module 1. Quick recap of the files:

| File | What It Contains | When It's Used |
|------|-----------------|----------------|
| `254_CROSS_SEASON_ANALYSIS.md` | 10 pattern categories from 8x world champs | Reference during design decisions |
| `MULTI_TEAM_ANALYSIS.md` | Patterns from 1678, 6328, 4414, 1690, 2910, 1323 | Cross-validate against 254's patterns |
| `TEAM_DATABASE.md` | Raw data: 50+ robots, mechanisms, motors, speeds | Look up specific historical robots |

**What patterns CANNOT do:** They can't tell you what to build for a completely novel game mechanic. That's where human creativity + the prediction engine come in.

---

## Section 3: Layer 2 — The Kickoff Template (10 min)

**File:** `design-intelligence/KICKOFF_TEMPLATE.md`

### How It Works

On game reveal day (January kickoff), the team:

1. Watches the game reveal video
2. Reads the game manual
3. Fills in the **Kickoff Template** (12 sections)
4. Feeds the template + pattern database to Claude
5. Claude produces: mechanism recommendations, specs, build priority, and Engine config changes

### The 12 Sections

| # | Section | Example (Reefscape 2025) |
|---|---------|-------------------------|
| 1 | Game Identity | "Reefscape", 2025 |
| 2 | Match Structure | 15s auto, 135s teleop |
| 3 | Game Pieces | Coral (PVC pipe), 12" long, ~0.5 lbs |
| 4 | Primary Scoring | Reef pipes at various heights |
| 5 | Secondary Scoring | Processor (low slot) |
| 6 | Endgame | Cage climb (deep/shallow) |
| 7 | Ranking Points | Coral RP, Cage RP |
| 8 | Field Layout | 54' × 27', reef in center |
| 9 | Robot Constraints | 125 lbs, 120" perimeter |
| 10 | Special Mechanics | Algae removal, barge scoring |
| 11 | Initial Observations | Short cycles, climbing critical for RP |
| 12 | Claude Prompt | Copy-paste for analysis |

### The Claude Prompt (Section 12)

The bottom of the template contains a pre-written prompt. After filling in sections 1-11, you copy everything and paste it to Claude along with the pattern database. Claude then produces:

1. **Scoring Meta Analysis** — Points per second for each action, optimal cycle structure
2. **Mechanism Recommendations** — Type, dimensions, motors, gear ratios, sensors, control approach
3. **Priority-Ranked Build Order** — What to prototype first
4. **Software Updates for The Engine** — What configs to change, new states needed

> **Rookie Checkpoint:** You don't need to be a programming expert to use the Kickoff Template. The template is designed so that anyone who read the game manual can fill it in. Claude does the analysis.

---

## Section 4: Layer 3 — The Engine Codebase (15 min)

### The Execution Loop

**File:** `src/main/java/frc/robot/commands/FullAutonomousCommand.java`

This is the top-level command that ties everything together. Here's what happens every 20 milliseconds during autonomous:

```
FullAutonomousCommand.execute()
│
├── 1. Update sensor data
│   ├── Get robot pose from odometry (swerve encoders + gyro)
│   ├── Get fuel positions from FuelDetectionConsumer (Limelight YOLO)
│   └── Get opponent positions (if available)
│
├── 2. Build GameState snapshot
│   └── new GameState().withRobotPose(...).withFuelHeld(...)...
│
├── 3. If active path command is running, keep executing it
│   └── activePathCommand.execute()
│
├── 4. Update dynamic obstacles on the navigation grid
│   └── Stamp opponent bounding boxes onto the grid
│
├── 5. Every 0.5 seconds, RE-EVALUATE:
│   ├── Run Bot Aborter — should we give up on current target?
│   ├── Run evaluateTargets() — is there a better option now?
│   │   └── If new best utility > current utility + 5.0 → RETARGET
│   └── If retargeting: plan new path, start new path command
│
└── 6. On arrival at target → back to step 1 for next target
```

### Key Design Decisions

**Why re-evaluate every 0.5 seconds, not every 20ms?**
Path planning is expensive. Re-evaluating every 20ms would waste CPU cycles when nothing has changed. 0.5 seconds is frequent enough to react to moving opponents but cheap enough computationally.

**Why does retargeting require utility > current + 5.0?**
To prevent "oscillation" — the robot switching between two targets that are almost equally good. The +5.0 hysteresis means the new target must be SIGNIFICANTLY better before the robot changes course.

**Why a fallback target at (8.23, 4.11)?**
If vision sees nothing, hub is inactive, and time is long, the robot still needs somewhere to go. The fallback is field center — a neutral position to wait for new information.

---

### The Pathfinding Stack

When the strategy picks a target, the robot needs to plan a path:

#### A* Pathfinder

**File:** `src/main/java/frc/lib/pathfinding/AStarPathfinder.java`

A* is a classic algorithm that finds the shortest path through a grid. Our version:

- **Grid:** 164 columns × 82 rows = 16.4m × 8.2m field at 10cm resolution
- **Movement:** 8 directions (N, NE, E, SE, S, SW, W, NW)
- **Cost:** Cardinal moves = 1.0, diagonal moves = 1.41 (√2)
- **Heuristic:** Euclidean distance to goal (straight-line distance)
- **Obstacles:** Field elements (static) + opponent robots (dynamic, updated each cycle)

```
START ──→ ──→ ──→ ──→ ──→
                    ┌─────────┐
              ──↘   │ OBSTACLE │  ──→
                 ↘  └─────────┘  ↗
                  ──→ ──→ ──→ ──↗  ──→ GOAL
```

The path avoids static obstacles (field walls, pillars) and dynamic obstacles (opponent robots).

#### Navigation Grid

**File:** `src/main/java/frc/lib/pathfinding/NavigationGrid.java`

The grid loads from `navgrid.json`:

```json
{
    "grid": [[0,1,0,...], ...],   // 0 = passable, 1 = blocked
    "cell_size_m": 0.1,          // each cell is 10cm × 10cm
    "columns": 164,              // 16.4 meters wide
    "rows": 82                   // 8.2 meters tall
}
```

**Static obstacles** are baked into the grid at deploy time (field walls, game elements).
**Dynamic obstacles** are stamped onto the grid each cycle from opponent vision data, then cleared and re-stamped.

#### Dynamic Avoidance Layer

**File:** `src/main/java/frc/lib/pathfinding/DynamicAvoidanceLayer.java`

You covered this in Module 2 — the potential field that smoothly curves around opponents. This runs ON TOP of the A* path, adjusting the velocity vector in real-time.

---

### The Vision Pipeline

**File:** `src/main/java/frc/robot/subsystems/FuelDetectionConsumer.java`

How fuel positions get from the camera to the strategy engine:

```
Limelight Camera
    │
    ▼ (ONNX inference on Limelight processor)
Wave YOLOv11n Model → detects "fuel" objects with bounding boxes
    │
    ▼ (SnapScript Python on Limelight)
Pixel → Field coordinate transform → [numFuel, x1, y1, conf1, x2, y2, conf2, ...]
    │
    ▼ (NetworkTables to roboRIO)
FuelDetectionConsumer.updateFromRawArray()
    │
    ├── Confidence filter: drop detections < 80%
    ├── Persistence filter: must see same fuel 3 frames in a row
    └── Output: List<Translation2d> confirmedFuelPositions
         │
         ▼
    GameState.withDetectedFuel(confirmedFuelPositions)
         │
         ▼
    AutonomousStrategy.evaluateTargets(state)
```

**Why 3-frame persistence?** Vision noise. A single frame might hallucinate a fuel cell. Three consecutive frames at the same position (within 0.5m tolerance) confirms it's real.

**Why 80% confidence?** The YOLOv11n model outputs a confidence score for each detection. Below 80%, too many false positives. Above 90%, we miss real fuel cells in poor lighting. 80% is the sweet spot.

---

## Section 5: The Cycle Tracker (5 min)

**File:** `src/main/java/frc/robot/autos/CycleTracker.java`

The cycle tracker measures how fast the robot completes the collect→carry→score loop:

```
IDLE ──startCycle()──▶ SEEKING ──markPickup()──▶ CARRYING ──markScore()──▶ SCORING ──▶ IDLE
                         │                         │                        │
                      (timer starts)           (intermediate)         (timer stops,
                                                                     cycle count++)
```

After each match, you can pull these metrics from AdvantageKit logs:
- **Cycle count** — how many complete collect→score cycles
- **Average cycle time** — seconds per cycle
- **Last cycle time** — most recent cycle duration

**Why this matters:** If your average cycle is 8 seconds and the championship average is 5, you know you need to optimize. The data tells you WHERE to improve — is it seeking time (path is slow), carrying time (driving is slow), or scoring time (mechanism is slow)?

---

## Section 6: How Everything Connects — Complete Data Flow

Here's the full chain from sensor to motor:

```
SENSORS                         PROCESSING                      ACTUATORS
────────                        ──────────                      ─────────
Swerve Encoders ──┐
                  ├──▶ Odometry ──▶ robotPose ──┐
Gyro (ADIS16470) ─┘                             │
                                                ├──▶ GameState
Limelight Camera ──▶ YOLO ──▶ FuelDetection ──┐│
                                    Consumer   ├┘
Match Timer ──────────────────────────────────┘
                                                │
                                                ▼
                                    AutonomousStrategy
                                    .evaluateTargets()
                                                │
                                     ┌──────────┴──────────┐
                                     │    ScoredTargets    │
                                     │  (sorted by utility)│
                                     └──────────┬──────────┘
                                                │
                                                ▼
                                     Best target selected
                                                │
                                                ▼
                              NavigationGrid + AStarPathfinder
                              → List<Translation2d> waypoints
                                                │
                                                ▼
                              DynamicAvoidanceLayer
                              → corrected velocity vector
                                                │
                                                ▼
                              SwerveSubsystem.driveRobotRelative()
                                                │
                                                ▼
                              Kraken X60 motors spin the wheels
```

---

## Section 7: Hands-On Exercises

### Exercise A: Mock Kickoff (All Levels, 20 min, In Groups)

Here's a fictional 2028 game. Fill in the Kickoff Template as a group.

> **GAME: "AVALANCHE" (2028)**
>
> Two alliances of 3 robots compete on a 54' × 27' field. Game pieces are 4-inch rubber balls (12 on field, 3 preloadable per alliance). Primary scoring: shoot balls into a "Summit" goal 8 feet high, located at each end of the field (3 pts auto, 2 pts teleop). Secondary scoring: place balls on a "Base Camp" shelf 18 inches high near alliance wall (1 pt each). Endgame: climb a "Glacier" bar 36 inches off the ground for 5 pts, or park in the "Glacier Zone" for 2 pts. RP1: "Avalanche RP" — alliance scores 20+ balls. RP2: "Summit RP" — all 3 robots climb. Match: 15s auto + 135s teleop. Max robot: 125 lbs, 120" perimeter, 48" tall.

**Task:** Fill in the Kickoff Template's first 9 sections. Then answer:

1. What pattern says about the intake design?
2. What pattern says about the scorer?
3. Build priority order?
4. What Engine constants would change?

**Expected Answers:**
1. Pattern 3: Full-width, under-bumper (4" balls fit under). Side funneling mecanum.
2. Pattern 4: Ball game + ranged scoring → flywheel shooter + turret + adjustable hood
3. Shooter first (highest point value), intake second (feeds shooter), climber last (Pattern 6)
4. `kClimbTimeThresholdSeconds` might change based on climb time, HUB_POSE coordinates for Summit location, `kFuelConfidenceThreshold` tuned for rubber balls vs PVC pipes

---

### Exercise B: Trace the Loop (Veterans, 15 min)

Open `src/main/java/frc/robot/commands/FullAutonomousCommand.java` in your editor.

Starting from the `execute()` method, trace these scenarios and write down what the robot does at each step:

**Scenario 1:** Robot starts at (1, 4), no fuel held, sees 2 fuel cells at (5, 3) and (7, 5), no opponents, 120 seconds remaining.

**Scenario 2:** Robot is driving to fuel at (5, 3), and an opponent appears at (4.5, 3.2) — 0.8m from the fuel. What happens at the next 0.5-second re-evaluation?

**Scenario 3:** Robot has collected 2 fuel, HUB is active, 14 seconds remaining. What does the strategy pick and why?

---

### Exercise C: Navigation Grid Drawing (Rookies, 10 min)

On a sheet of graph paper (or use the whiteboard):

1. Draw a 10×10 grid
2. Mark cell (2,2) as START and cell (8,8) as GOAL
3. Block out cells (4,3), (4,4), (4,5), (4,6) as an obstacle wall
4. Draw the shortest 8-directional path from START to GOAL that avoids the wall
5. Count the cost: cardinal moves = 1, diagonal moves = 1.41

This is exactly what our A* pathfinder does, but on a 164×82 grid at 10cm resolution.

---

### Exercise D: AdvantageScope Field Overlay (Veterans, 10 min)

If you have AdvantageScope installed:

1. Open a log file from the sim
2. Find the `AutonomousStrategy/` log group
3. Look for `BestTarget`, `AllTargets`, and `BotAborter` entries
4. Enable the field overlay to see detected fuel positions plotted on the field
5. Watch how the robot's target changes as fuel cells are collected

**Key thing to look for:** The moment the robot retargets. Does the utility jump make sense? Was the Bot Aborter correct to abort?

---

### Exercise E: Design a New Action Type (Discussion, All Levels)

The Engine currently has three action types: SCORE, COLLECT, CLIMB.

**Challenge:** Design a fourth action type for this scenario:

> In AVALANCHE 2028, there's a "Snow Plow" game mechanic: you can push loose balls into your alliance's scoring zone for 0.5 pts each. No mechanism required — just drive into them.

Questions to discuss:
1. What would you name the new ActionType?
2. What base utility would you give it?
3. Under what conditions should it activate?
4. How would you prevent it from conflicting with COLLECT (picking up balls)?
5. What new field would you add to GameState?

**Hint:** Think about when PLOW is better than COLLECT — maybe when the robot's intake is broken, or when there are many loose balls near the scoring zone and driving through them is faster than picking them up one at a time.

---

## Section 8: Quick Reference Card

Cut this out (or screenshot it) for your driver station binder:

```
┌────────────────────────────────────────────────────┐
│          THE ENGINE — QUICK REFERENCE               │
├────────────────────────────────────────────────────┤
│                                                    │
│  STRATEGY TIERS                                    │
│  ─────────────                                     │
│  CLIMB  = 100 - distance    (when time ≤ 15s)      │
│  SCORE  = 50 + fuel×5 - dist (when hub + fuel)     │
│  COLLECT = 20 - dist - penalty (per fuel cell)     │
│                                                    │
│  BOT ABORTER                                       │
│  ───────────                                       │
│  Abort if: (myETA - oppETA) ≥ 0.75s               │
│  ETA = distance / speed                            │
│                                                    │
│  KEY CONSTANTS                                     │
│  ─────────────                                     │
│  Opponent influence: 2.0 meters                    │
│  Repulsive gain: 1.5 (pushes away from opponents)  │
│  Confidence threshold: 80%                         │
│  Persistence: 3 frames to confirm detection        │
│  Re-evaluation: every 0.5 seconds                  │
│  Retarget hysteresis: +5.0 utility required        │
│  Max speed: 4.5 m/s                                │
│  Grid: 164×82 cells, 10cm each                     │
│                                                    │
│  PIPELINE                                          │
│  ────────                                          │
│  Camera → YOLO → Persistence → GameState           │
│  → Strategy → A* Path → Avoidance → Drive          │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## Section 9: Assessment Checklist

Check off each item when you can do it confidently:

**Rookies — You should be able to:**
- [ ] Name the 7 teams we studied and what each is known for
- [ ] Explain 3 pattern rules and give an example for each
- [ ] Fill in a Kickoff Template from a game manual
- [ ] Draw an A* path on a grid with obstacles
- [ ] Calculate utility scores for a simple game state
- [ ] Explain what the Bot Aborter does in plain English

**Veterans — You should also be able to:**
- [ ] Trace through FullAutonomousCommand.execute() step by step
- [ ] Explain the vision pipeline from camera to GameState
- [ ] Calculate opponent penalties and predict target selection
- [ ] Describe the re-evaluation loop and retarget hysteresis
- [ ] Read AdvantageScope telemetry and verify strategy decisions
- [ ] Propose a new ActionType with utility formula and activation conditions
- [ ] Explain why the avoidance layer uses potential fields instead of hard avoidance

---

## Congratulations

You've completed all three training modules for The Engine's Design Intelligence system.

**Module 1** taught you to read the pattern rules — the historical data from 7 championship teams that informs every design decision.

**Module 2** taught you the prediction engine — utility scoring, the Bot Aborter, and the avoidance layer that make autonomous decisions in real-time.

**Module 3** showed you how it all connects — from game reveal to kickoff template to running code that drives the robot.

**Next steps:**
- Practice the exercises with a partner
- Open the actual code files and trace through them
- At the next team meeting, try filling in the Kickoff Template for last year's game (Reefscape 2025) as practice
- When the 2028 game is revealed, you'll be ready to fill in the template on day one

---

*Module 3 of 3 | THE ENGINE Student Training | Team 2950 The Devastators*
