# THE ENGINE — Student Training Module 2: Using the Prediction Engine
# Block F.8 (Part 2 of 3) | Audience: Veterans + Rookies | Time: ~60 minutes

---

## What You'll Learn

By the end of this module, you will be able to:
1. Explain what "utility scoring" means and why it's better than if/else chains
2. Read `AutonomousStrategy.java` and predict what the robot will do in any game state
3. Trace through a `GameState` snapshot and calculate utility scores by hand
4. Understand the Bot Aborter and when the robot gives up on a target
5. Explain how the avoidance layer keeps the robot safe from opponents

---

## Section 1: What Is a Prediction Engine? (10 min)

### The Problem

During autonomous mode, the robot has 15 seconds to score as many points as possible with **zero human input**. It needs to answer three questions every 20 milliseconds:

1. **What** should I do? (Score, collect fuel, or climb?)
2. **Where** should I go? (Which fuel cell? Which scoring location?)
3. **Should I give up?** (Is an opponent going to beat me there?)

### The Bad Way: Giant If/Else Chain

```java
// DON'T DO THIS — fragile, impossible to test, breaks when conditions overlap
if (timeLeft < 15 && !hasClimbed) {
    driveToClimb();
} else if (hasFuel && canSeeHub) {
    driveToHub();
} else if (canSeeFuel) {
    driveToFuel();
} else {
    driveToCenter();
}
```

Problems: What if time is 16 seconds and we're right next to the climb? What if there are 3 fuel cells — which one? What if an opponent is blocking the closest one?

### The Engine Way: Utility Scoring

Instead of picking ONE action, we **score ALL possible actions** and pick the best one.

```
CLIMB  → utility = 100.0 - distance_to_climb
SCORE  → utility =  50.0 + (fuel_held × 5.0) - distance_to_hub
COLLECT fuel_1 → utility = 20.0 - distance - opponent_penalty
COLLECT fuel_2 → utility = 20.0 - distance - opponent_penalty
COLLECT fuel_3 → utility = 20.0 - distance - opponent_penalty
```

Sort by utility. Pick the highest. Drive there.

**This is the same technique used in video game AI, self-driving cars, and warehouse robots.** It's called a "utility function" and it's one of the most important concepts in robotics.

---

## Section 2: The Building Blocks (15 min)

### Block A: GameState — The Snapshot

**File:** `src/main/java/frc/robot/autos/GameState.java`

GameState is an **immutable snapshot** of everything the robot knows right now:

```java
public final class GameState {
    Pose2d  robotPose;          // Where am I on the field? (x, y, angle)
    int     fuelHeld;           // How many game pieces am I carrying?
    boolean hubActive;          // Is the scoring target available?
    double  timeRemaining;      // Seconds left in the match
    List<Translation2d> detectedFuel;      // Where did vision see fuel?
    List<Translation2d> detectedOpponents; // Where are opponents?
}
```

**Key concept: Immutable means you can't change it after creation.** You build a new one each cycle:

```java
GameState state = new GameState()
    .withRobotPose(swerve.getPose())
    .withFuelHeld(conveyor.getBallCount())
    .withHubActive(true)
    .withTimeRemaining(timer.get())
    .withDetectedFuel(vision.getFuelPositions());
```

> **Rookie Checkpoint:** Why immutable? Because if two pieces of code share the same GameState, neither can corrupt the other's data. It's a safety net.

---

### Block B: ActionType — What Can the Robot Do?

**File:** `src/main/java/frc/robot/autos/ActionType.java`

```java
public enum ActionType {
    SCORE,    // Drive to HUB and shoot fuel
    COLLECT,  // Drive to a fuel cell and pick it up
    CLIMB     // Drive to climb location and engage climber
}
```

Only three options. Simple on purpose. The intelligence is in **when** to pick each one.

---

### Block C: ScoredTarget — A Rated Option

**File:** `src/main/java/frc/robot/autos/ScoredTarget.java`

```java
public record ScoredTarget(
    ActionType actionType,   // SCORE, COLLECT, or CLIMB
    Pose2d targetPose,       // field position to drive to
    double utility           // how good is this option? (higher = better)
) {}
```

The strategy engine produces a **list** of these, sorted by utility. The robot drives to the first one.

---

## Section 3: The Strategy Engine — Line by Line (20 min)

**File:** `src/main/java/frc/robot/autos/AutonomousStrategy.java`

### The Three Priority Tiers

The `evaluateTargets()` method builds a list of every possible action, scores each one, then sorts. Here's how each tier works:

#### Tier 1: CLIMB (Highest Base Utility)

```java
if (state.getTimeRemaining() <= 15.0) {    // kClimbTimeThresholdSeconds
    double dist = robotPos.getDistance(CLIMB_POSE);
    double utility = 100.0 - dist;
    targets.add(new ScoredTarget(ActionType.CLIMB, CLIMB_POSE, utility));
}
```

**Translation:** When 15 seconds or less remain, add CLIMB as an option with base utility 100. Subtract the distance so "closer to climb = higher score."

**Why 100?** Because SCORE starts at 50 and COLLECT starts at 20. Even the farthest possible CLIMB (~16 meters across the field = utility 84) still beats the best possible SCORE (utility ~60). **This guarantees the robot climbs when time is short.**

> **Exercise 1:** The robot is 3 meters from the climb point, 12 seconds remaining, holding 2 fuel, HUB is active. What's the CLIMB utility?
>
> **Answer:** 100.0 - 3.0 = **97.0**

---

#### Tier 2: SCORE

```java
if (state.isHubActive() && state.getFuelHeld() > 0) {
    double dist = robotPos.getDistance(HUB_POSE);
    double utility = 50.0 + state.getFuelHeld() * 5.0 - dist;
    targets.add(new ScoredTarget(ActionType.SCORE, HUB_POSE, utility));
}
```

**Translation:** If the HUB is active AND we're carrying fuel, score = 50 + (5 per fuel held) - distance.

**Why the fuel bonus?** Carrying 3 fuel is more valuable than carrying 1 — you score more points per trip. The `× 5.0` bonus incentivizes scoring when loaded up.

> **Exercise 2:** Robot holds 2 fuel, HUB active, 5 meters from HUB. What's the SCORE utility?
>
> **Answer:** 50.0 + (2 × 5.0) - 5.0 = **55.0**

> **Exercise 3:** Same situation but with 12 seconds remaining. CLIMB utility from 8 meters away? Which wins?
>
> **Answer:** CLIMB = 100 - 8 = 92.0. SCORE = 55.0. **CLIMB wins** — the robot drives to climb instead of scoring. This is correct behavior: climbing is worth more than 2 fuel when time is short.

---

#### Tier 3: COLLECT

```java
for (Translation2d fuelPos : state.getDetectedFuel()) {
    double dist = robotPos.getDistance(fuelPos);
    double utility = 20.0 - dist - opponentPenalty(fuelPos, opponents);
    targets.add(new ScoredTarget(ActionType.COLLECT, collectPose, utility));
}
```

**Translation:** For EACH fuel cell the camera sees, score = 20 - distance - opponent penalty.

**The opponent penalty** is the key innovation. If an opponent is near a fuel cell, that fuel cell's utility drops:

```java
private static double opponentPenalty(Translation2d target, List<Translation2d> opponents) {
    for (Translation2d opp : opponents) {
        double dist = target.getDistance(opp);
        if (dist < 2.0) {  // kOpponentInfluenceRadiusMeters
            penalty += (2.0 - dist) * 1.5;  // kRepulsiveGain
        }
    }
    return penalty;
}
```

**Translation:** Any opponent within 2 meters of a fuel cell adds a penalty. The closer the opponent, the bigger the penalty. This makes the robot prefer fuel cells that opponents aren't near.

> **Exercise 4:** Two fuel cells detected. Fuel A is 2m away with no opponents. Fuel B is 1m away but an opponent is 0.5m from it. Which has higher utility?
>
> **Fuel A:** 20.0 - 2.0 - 0 = **18.0**
> **Fuel B:** 20.0 - 1.0 - ((2.0 - 0.5) × 1.5) = 20.0 - 1.0 - 2.25 = **16.75**
> **Fuel A wins** even though it's farther away, because the opponent penalty on B pushed it down.

---

### The Sort and Pick

```java
targets.sort(Comparator.comparingDouble(ScoredTarget::utility).reversed());
return targets;
```

Highest utility first. The caller drives to `targets.get(0)`.

---

## Section 4: The Bot Aborter (10 min)

What if the robot is driving to a fuel cell and an opponent starts heading for the same one? The **Bot Aborter** decides whether to give up.

```java
public static boolean shouldAbortTarget(
    double robotDist, double robotSpeed,
    double opponentDist, double opponentSpeed) {

    if (robotSpeed <= 0) return true;     // we're stopped — can't win
    if (opponentSpeed <= 0) return false;  // they're stopped — free fuel

    double robotEta = robotDist / robotSpeed;
    double opponentEta = opponentDist / opponentSpeed;
    return (robotEta - opponentEta) >= 0.75;  // kAbortTimeThresholdSeconds
}
```

**Translation:** Calculate who arrives first. If the opponent arrives 0.75 seconds or more before us, **abort** — we'll lose the race. Re-evaluate and pick the next best target.

> **Exercise 5:** Robot is 3m away going 2 m/s. Opponent is 2m away going 3 m/s. Should we abort?
>
> Robot ETA: 3/2 = 1.5s
> Opponent ETA: 2/3 = 0.667s
> Difference: 1.5 - 0.667 = 0.833s
> 0.833 >= 0.75? **Yes — ABORT.** The opponent beats us by nearly a full second.

> **Exercise 6:** Robot is 2m away going 4 m/s. Opponent is 3m away going 2 m/s. Abort?
>
> Robot ETA: 2/4 = 0.5s
> Opponent ETA: 3/2 = 1.5s
> Difference: 0.5 - 1.5 = -1.0s
> -1.0 >= 0.75? **No — KEEP GOING.** We arrive a full second before them.

---

## Section 5: The Avoidance Layer (10 min)

Even after the strategy picks a target, the robot needs to **dodge opponents on the way there**. That's the Dynamic Avoidance Layer.

**File:** `src/main/java/frc/lib/pathfinding/DynamicAvoidanceLayer.java`

### How It Works: Vector Math

Imagine two invisible forces acting on the robot every 20ms:

```
ATTRACTIVE FORCE ──────────────► (pulls toward the waypoint)
     ▲
     │
     │  REPULSIVE FORCE (pushes away from opponents)
     │
   [OPPONENT]
```

The robot's actual velocity is the **sum** of these forces:

```java
// Attractive: point toward waypoint at max speed
attractiveForce = direction_to_waypoint × maxSpeed × 1.0

// Repulsive: push away from each nearby opponent
for each opponent within 2.0 meters:
    repulsiveForce += direction_away_from_opponent × strength
    // strength = 1.5 × (2.0 - distance) / 2.0 × maxSpeed

// Sum and cap at max speed (4.5 m/s)
finalVelocity = attractive + repulsive
if |finalVelocity| > 4.5:
    finalVelocity = normalize(finalVelocity) × 4.5
```

### Visual Example

```
                    [WAYPOINT]
                        ↑
                     attract
                        ↑
   [OPP] ← repel ← [ROBOT] → result path curves around opponent
                        ↑
                     attract
                        ↑
```

The robot smoothly curves around opponents instead of driving straight through them.

### The Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `kAttractiveGain` | 1.0 | How strongly the waypoint pulls |
| `kRepulsiveGain` | 1.5 | How strongly opponents push (1.5× stronger than attraction) |
| `kOpponentInfluenceRadiusMeters` | 2.0 | Opponents beyond 2m are ignored |
| `kMaxRobotSpeedMps` | 4.5 | Output velocity capped here |

> **Why is repulsive gain higher than attractive?** Safety. We'd rather arrive late than collide with an opponent. A collision can disable both robots.

---

## Section 6: Putting It All Together — Full Match Walkthrough

Let's trace through a hypothetical autonomous period:

### T = 0.0s (Match Start)

```
GameState: robotPose=(1.0, 4.0), fuelHeld=1, hubActive=true, timeRemaining=15.0
Detected fuel: [(5.0, 3.0), (8.0, 5.0)]
No opponents detected
```

Evaluation:
- CLIMB: time = 15.0 ≤ 15.0 → utility = 100 - 8.6 = **91.4** (8.6m to climb)
- SCORE: hub active, holding fuel → utility = 50 + 5 - 2.4 = **52.6** (2.4m to hub)
- COLLECT fuel_1: 20 - 4.1 = **15.9**
- COLLECT fuel_2: 20 - 7.1 = **12.9**

**Winner: CLIMB (91.4)** — With exactly 15 seconds left, the robot goes straight to climb.

### What if timeRemaining = 60.0 instead?

- CLIMB: time > 15 → **not generated**
- SCORE: 50 + 5 - 2.4 = **52.6**
- COLLECT fuel_1: 20 - 4.1 = **15.9**
- COLLECT fuel_2: 20 - 7.1 = **12.9**

**Winner: SCORE (52.6)** — With plenty of time, the robot scores its fuel first, then collects more.

---

## Section 7: Hands-On Exercises

### Exercise A: Manual Utility Calculation (All Levels)

Given this game state, calculate ALL utilities and determine the winner:

```
robotPose = (4.0, 4.0)
fuelHeld = 0
hubActive = true
timeRemaining = 45.0
detectedFuel = [(6.0, 4.0), (4.0, 6.0), (2.0, 2.0)]
detectedOpponents = [(5.5, 4.0)]    ← opponent near fuel_1!
HUB is at (3.39, 4.11)
CLIMB is at (8.23, 4.11)
```

Fill in:

| Target | Base | Distance | Penalty | Utility |
|--------|------|----------|---------|---------|
| CLIMB | — | — | — | _(not generated, time > 15)_ |
| SCORE | — | — | — | _(not generated, fuelHeld = 0)_ |
| COLLECT fuel_1 at (6,4) | 20 | ? | ? | ? |
| COLLECT fuel_2 at (4,6) | 20 | ? | 0 | ? |
| COLLECT fuel_3 at (2,2) | 20 | ? | 0 | ? |

**Answer Key:**

- fuel_1: dist = 2.0m, opponent at (5.5, 4.0) is 0.5m from fuel → penalty = (2.0-0.5)×1.5 = 2.25 → utility = 20 - 2.0 - 2.25 = **15.75**
- fuel_2: dist = 2.0m, no nearby opponent → utility = 20 - 2.0 = **18.0**
- fuel_3: dist = 2.83m, no nearby opponent → utility = 20 - 2.83 = **17.17**

**Winner: fuel_2 (18.0)** — The robot goes for the fuel without an opponent nearby, even though fuel_1 is the same distance. The opponent penalty works!

---

### Exercise B: Bot Aborter Drill (All Levels)

For each scenario, calculate ETAs and decide: ABORT or KEEP GOING?

| # | Robot Dist | Robot Speed | Opp Dist | Opp Speed | Abort? |
|---|-----------|-------------|----------|-----------|--------|
| 1 | 4.0m | 4.0 m/s | 2.0m | 4.0 m/s | ? |
| 2 | 2.0m | 3.0 m/s | 5.0m | 2.0 m/s | ? |
| 3 | 3.0m | 2.0 m/s | 1.0m | 0.0 m/s | ? |
| 4 | 1.0m | 0.0 m/s | 5.0m | 1.0 m/s | ? |

**Answers:**
1. Robot ETA=1.0, Opp ETA=0.5, diff=0.5 → 0.5 < 0.75 → **KEEP GOING** (close race, we might win)
2. Robot ETA=0.67, Opp ETA=2.5, diff=-1.83 → **KEEP GOING** (we arrive way first)
3. Opp speed=0 → **KEEP GOING** (opponent is stationary, no threat)
4. Robot speed=0 → **ABORT** (we're not moving, can't reach anything)

---

### Exercise C: Read the Code (Veterans)

Open `src/main/java/frc/robot/autos/AutonomousStrategy.java` and answer:

1. What happens if the strategy finds NO valid targets? (Look at the `if (targets.isEmpty())` block)
2. Where are `HUB_POSE` and `CLIMB_POSE` defined? What are their coordinates?
3. The opponent penalty uses `kRepulsiveGain = 1.5`. If you changed it to 3.0, what would happen?

**Answers:**
1. A fallback COLLECT target at (8.23, 4.11) with utility 0.0 is added — the robot always has somewhere to go
2. Top of class: HUB at (3.39, 4.11), CLIMB at (8.23, 4.11) — blue alliance coordinates
3. Opponent penalties would double. The robot would avoid contested fuel cells much more aggressively, possibly driving to far-away fuel instead of competing for closer ones

---

### Exercise D: What Would You Change? (Discussion, All Levels)

These are real design questions with no single right answer. Discuss with your group:

1. **CLIMB base utility is 100, SCORE is 50.** Could there ever be a game where scoring should beat climbing when time is low? What would you change?

2. **The opponent penalty only applies to COLLECT, not SCORE.** Should we penalize SCORE if an opponent is near the HUB? What are the tradeoffs?

3. **Bot Aborter threshold is 0.75 seconds.** Too aggressive (gives up too easily) or too conservative (wastes time on lost races)? What data would you need to tune it?

---

## Key Vocabulary

| Term | Definition |
|------|-----------|
| **Utility** | A number representing how "good" an option is. Higher = better. |
| **GameState** | An immutable snapshot of everything the robot knows right now |
| **Immutable** | Can't be changed after creation. Safe to share between threads. |
| **Bot Aborter** | Logic that gives up on a target if an opponent will get there first |
| **ETA** | Estimated Time of Arrival = distance / speed |
| **Potential Field** | Physics-based technique: attractive forces pull toward goals, repulsive forces push away from obstacles |
| **Fluent API** | Builder pattern where you chain `.withX()` calls: `new GameState().withFuelHeld(2).withHubActive(true)` |

---

## What's Next

**Module 3** shows how the pattern rules (Module 1) and prediction engine (Module 2) connect into the **full Design Intelligence pipeline** — from game day kickoff all the way to autonomous code running on the robot.

---

*Module 2 of 3 | THE ENGINE Student Training | Team 2950 The Devastators*
