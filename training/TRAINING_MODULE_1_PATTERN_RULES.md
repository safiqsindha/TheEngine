# THE ENGINE — Student Training Module 1: Reading the Pattern Rules
# Block F.8 (Part 1 of 3) | Audience: Veterans + Rookies | Time: ~45 minutes

---

## What You'll Learn

By the end of this module, you will be able to:
1. Explain why we study other teams' robots
2. Read a pattern rule and predict what mechanism a top team would build
3. Apply pattern rules to a new game to generate your own mechanism ideas
4. Know where to find pattern data in our codebase

---

## Section 1: Why Patterns Matter (10 min)

### The Core Idea

The best FRC teams don't start from scratch every year. They apply **design patterns** — proven approaches that worked across multiple seasons, multiple games, and multiple teams.

We studied **7 championship-winning teams across 10 seasons** (2016-2025) and extracted the rules they follow. These live in our `design-intelligence/` folder.

### The Teams We Studied

| Team | Nickname | What They're Known For |
|------|----------|----------------------|
| **254** | The Cheesy Poofs | 8x World Champions — the gold standard |
| **1678** | Citrus Circuits | Best documentation + scouting data |
| **6328** | Mechanical Advantage | Created AdvantageKit/AdvantageScope |
| **4414** | HighTide | "Simple and rigid beats complex" |
| **1690** | Orbit | Israeli powerhouse |
| **2910** | Jack in the Bot | PNW swerve pioneers |
| **1323** | MadTown | 2025 World Champions |

### Where to Find the Data

```
constructicon/
  design-intelligence/
    254_CROSS_SEASON_ANALYSIS.md    <-- 10 pattern categories from 254
    MULTI_TEAM_ANALYSIS.md          <-- patterns from 6 other top teams
    TEAM_DATABASE.md                <-- raw data from 50+ robots
    KICKOFF_TEMPLATE.md             <-- how to USE these patterns
```

---

## Section 2: The 10 Pattern Categories (15 min)

Read each rule below. For each one, we've included the **evidence** (what top teams actually did) and a **quick check** question.

### Pattern 1: Game Analysis Structure

**Rule:** Split into groups. Read the manual line-by-line. Build a must-have / nice-to-have / explore matrix. Optimize for Ranking Points, not raw score.

**Evidence:** 254 does this identically every year. They explicitly state: "Win the championship" is the design goal, not "do our best."

> **Quick Check:** Your alliance partner says "let's build whatever scores the most points." What's wrong with that thinking?
>
> **Answer:** Ranking Points determine your rank. A mechanism that reliably earns an RP every match is more valuable than one that scores 5 extra points. Top teams optimize for RPs first.

---

### Pattern 2: Drivetrain Selection

**Rule:** Swerve drive. Every top team runs swerve (2022+). Optimize speed for the game — faster isn't always better.

**Evidence:**
- 254 ran 18 ft/s in 2024 (Crescendo — long-field cycles)
- 254 ran 13.2 ft/s in 2025 (Reefscape — short cycles where acceleration > top speed)

> **Quick Check:** A game has scoring locations 3 feet from the starting position. Should you gear for max speed?
>
> **Answer:** No. Short distances mean you spend most of your time accelerating and decelerating. Gear for torque/acceleration instead. 254 made exactly this call in 2025.

---

### Pattern 3: Intake Design

**Rule:** ALWAYS full-width. "Touch it, own it." Side funneling (mecanum or angled wheels) for pieces arriving at angles. Under-bumper preferred; over-bumper if the game piece requires it.

**Evidence:**
| Year | Piece | Intake Style | Why |
|------|-------|-------------|-----|
| 2022 | Balls | Over-bumper | Ball size required it |
| 2024 | Notes | Under-bumper | Flat disc fits under |
| 2025 | Coral (PVC) | Over-bumper 4-bar | Pipe shape required it |

> **Quick Check:** The 2028 game piece is a 6-inch foam cube. Over-bumper or under-bumper?
>
> **Answer:** Could go either way at 6 inches, but under-bumper is preferred (better impact protection). The cube shape doesn't force over-bumper. You'd prototype both and test.

---

### Pattern 4: Scorer Selection

**Rule:**
- Ball game (shooting) → Flywheel + turret + adjustable hood
- Placement game → Elevator + wrist end effector
- Turret if scoring locations vary; skip turret if scoring is always at fixed positions

**Evidence:** 254 used a turret every year from 2019-2024, then dropped it in 2025 because Reefscape scoring was always at the same Reef pipes.

> **Quick Check:** The 2028 game requires placing cubes on shelves at 3 different heights, and the shelves are at random field positions. Turret or no turret?
>
> **Answer:** Turret — because the scoring locations are at random positions, the turret decouples scoring direction from driving direction.

---

### Pattern 5: Elevator Sizing

**Rule:**
- Height < 24 inches → single-stage
- Height > 24 inches → two-stage
- Speed target: ALWAYS under 1 second full travel
- Belt-driven (moved from chain in recent years)

**Evidence:** 254 in 2025 built a 52-inch two-stage elevator that travels full range in 0.3 seconds using 2x Kraken X60 motors.

> **Quick Check:** You need 30 inches of travel. How many stages? How many motors?
>
> **Answer:** Two-stage (>24"). Likely 2 motors for a two-stage (heavier carriage + longer belt run needs more torque).

---

### Pattern 6: Climber Design

**Rule:** Design LAST (after scoring is locked). Target < 2 seconds engagement. Use Dyneema rope, gas springs, ratchet/pawl retention. 1-2 motors max through a high-reduction gearbox.

**Evidence:** Every 254 climber since 2019 follows this — and they explicitly state the climber is the last thing they prototype.

> **Quick Check:** Your team wants to design the climber first because "it's the coolest part." What do you tell them?
>
> **Answer:** Climber points are capped (you climb once per match), but scoring points scale with cycles. Scoring mechanisms should be designed first because they have the highest impact on match outcome. Every top team does it this way.

---

### Pattern 7: Vision

**Rule:** Limelight on every championship robot (2019-2025). 2x Limelights standard since 2024. 3+ game piece auto is the championship baseline. 90%+ auto success rate required.

> **Quick Check:** Your autonomous routine scores 2 game pieces with 95% reliability. Is that competitive at championships?
>
> **Answer:** No. 3+ pieces is the baseline. You need to add at least one more scoring action to your auto.

---

### Pattern 8: Sensors

**Rule:** Beam break at every handoff point. Absolute encoder on every rotary joint. Hall effect for elevator zeroing. Current monitoring for stall detection.

> **Quick Check:** Your intake feeds into a conveyor, which feeds into a shooter. How many beam breaks minimum?
>
> **Answer:** Two — one at the intake-to-conveyor handoff, one at the conveyor-to-shooter handoff. Each transition needs confirmation.

---

### Pattern 9: Weight and CG

**Rule:** Battery centered or opposite the heaviest mechanism. Bellypan at 0.5-0.625" from ground. Frame square or near-square. Heavier robots can push opponents effectively.

**Evidence:** 4414 (HighTide) specifically maximizes weight low in the frame. 254 referenced them: "max weight robots like 4414 were just pushing people out of the way."

---

### Pattern 10: The 4414 Rule — Simplicity Wins

**Rule:** A simple mechanism executed perfectly beats a complex mechanism executed okay.

**Evidence:** 4414's design philosophy is "simple and rigid." They consistently reach eliminations with fewer mechanisms than 254 — but the mechanisms they have are bulletproof.

> **Quick Check:** You have 2 weeks left in build season. You can either (A) add a second scoring mechanism or (B) make your existing scorer 50% faster and 100% reliable. Which do you choose?
>
> **Answer:** B. Every time. Reliability and speed on one mechanism beats having two mechanisms that are both shaky.

---

## Section 3: Cross-Team Trends (5 min)

These are things that changed ACROSS all top teams between 2022 and 2025:

| Trend | Old | New | Why |
|-------|-----|-----|-----|
| Drive motors | Falcon 500 | Kraken X60 | Better FOC control, more torque |
| Low-power motors | Falcon 500 | Kraken X44 | Right-sized for intakes/wrists |
| Simulation | None | maple-sim + AdvantageScope | Test before you build |
| Elevator speed | <1 second | 0.3 seconds | Faster cycles = more points |
| Frame size | 27" square | 29.5" square | Stability with heavier mechanisms |
| Intake rollers | Hard rubber | Silicone on foam | Better grip, less damage |

---

## Section 4: Hands-On Exercise (15 min)

### Exercise 1: Pattern Matching (All Levels)

Read the following game description, then answer the questions below.

> **IMAGINARY GAME — "AVALANCHE" (2028)**
> - Game piece: 4-inch diameter rubber balls (12 on field)
> - Primary scoring: Shoot balls into a goal 8 feet off the ground from anywhere on the field
> - Secondary scoring: Place balls on a low shelf (18 inches high) near your alliance wall
> - Endgame: Robot climbs a bar that's 36 inches off the ground
> - Match: 15s auto + 135s teleop
> - Key RP: Score 20+ balls as an alliance

**Questions:**

1. What type of scorer does Pattern 4 suggest? Why?
2. What type of intake does Pattern 3 suggest?
3. How many elevator stages (Pattern 5) for the low shelf? For the climber?
4. Using Pattern 7, what should your auto target?
5. Using Pattern 6, when do you design the climber?

**Answers:**

1. Flywheel shooter + turret + adjustable hood — it's a ball game with ranged scoring
2. Full-width, likely under-bumper (4-inch balls fit under bumpers), with side funneling
3. Low shelf: single-stage (18" < 24"). Climber: two-stage or hook arms (36" > 24")
4. 3+ balls scored in auto (championship baseline from Pattern 7)
5. Last — after the shooter and intake are locked (Pattern 6)

---

### Exercise 2: Find It In The Code (Veterans)

Open a terminal and find these files. For each one, write down what pattern category it relates to:

```bash
# 1. Find the file that contains 254's intake patterns
#    Hint: grep -l "Touch it, own it" design-intelligence/

# 2. Find where we store multi-team patterns
#    Hint: ls design-intelligence/MULTI_TEAM_ANALYSIS.md

# 3. Find the kickoff template that USES these patterns
#    Hint: cat design-intelligence/KICKOFF_TEMPLATE.md | head -15
```

---

### Exercise 3: Debate (All Levels, In Pairs)

Pick a partner. One person argues FOR the statement, one argues AGAINST. Use pattern rules as evidence.

**Statement:** "Team 2950 should always build the most complex robot possible to maximize scoring."

After 3 minutes, switch sides. The pattern data should make the answer clear — but being able to argue both sides builds understanding.

---

## What's Next

**Module 2** covers the **Prediction Engine** — the Java code that actually makes decisions using these patterns. You'll learn how `AutonomousStrategy.java` turns game state into action.

**Module 3** covers the **full Design Intelligence system** — how kickoff templates, pattern rules, and the prediction engine connect into one pipeline that goes from game reveal to working robot code.

---

*Module 1 of 3 | THE ENGINE Student Training | Team 2950 The Devastators*
