# THE ENGINE — Build Season Project Management
# Codename: "The Clock"
# Target: Ready before January 2027 kickoff
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## The Problem

Six weeks. That's all you get. And here's how most teams spend them:

Week 1: Brainstorming and arguing about robot design.
Week 2: Still brainstorming. Someone starts CAD. Nobody's prototyping.
Week 3: CAD is halfway done. Parts aren't ordered. Prototypes are cardboard.
Week 4: Parts arrive. Manufacturing starts. First real mechanism built.
Week 5: Integration hell. Nothing fits together. Wiring is a mess.
Week 6: Frantic assembly. Untested autonomous. 2 hours of driver practice.

The Engine already solves week 1 — the prediction engine gives you a
validated robot architecture within 4 hours of kickoff. The CAD Pipeline
gives you parametric assemblies by end of day 1. But without project
management, weeks 2-6 still collapse into chaos.

The Clock fixes this. It takes the prediction engine output and auto-
generates a task breakdown with dependencies, assignments, and deadlines.
It tracks progress daily. It flags blockers before they become crises.

---

## Three Components

### CL.1: Kickoff Day Task Generator (8 hours to build)

**Input:** Prediction engine output (mechanism list + build order from Rule 13)
**Output:** Complete 6-week task breakdown with dependencies

The generator knows FRC build season patterns:
- Drivetrain is always first (days 1-3)
- Intake and scorer prototype in parallel (days 1-7)
- Integration starts when drivetrain is rolling (day 5-7)
- Climber is always last (starts week 2-3)
- Software runs continuously in parallel
- Driver practice starts the moment anything drives

#### Auto-Generated Task Template

On kickoff day, the prediction engine says: "swerve drivetrain,
2-stage elevator, over-bumper intake, hook climber." The Clock
generates:

```
═══════════════════════════════════════════════════════
THE CLOCK — Build Season Task Plan
Game: [2027 Game Name]
Generated: Kickoff Day, January XX, 2027
Architecture: Swerve + 2-Stage Elevator + OB Intake + Hook Climber
═══════════════════════════════════════════════════════

WEEK 1: PROTOTYPE & PROVE (Days 1-7)
─────────────────────────────────────
DRIVETRAIN (Team A: 3-4 students, Lead: _______)
  □ Day 1: Assemble swerve modules on frame
  □ Day 2: Wire drivetrain (use pre-built harnesses from The Grid)
  □ Day 3: Flash motor controllers, load swerve config
  □ Day 3: First drive test (forward, strafe, rotate)
  □ Day 4: Autonomous framework loaded, basic auto test
  □ Day 5: MILESTONE — Drivetrain driving and turning over to integration
  BLOCKER CHECK: Are all 4 swerve modules in inventory?

INTAKE (Team B: 2-3 students, Lead: _______)
  □ Day 1: Study 3 reference robots from CAD Collection
  □ Day 1: Cardboard/PVC prototype of intake geometry
  □ Day 2: Test prototype with actual game pieces
  □ Day 3: Iterate roller spacing and compression
  □ Day 4: Begin CAD of V1 intake (or load Blueprint template)
  □ Day 5: Order any non-stock parts
  □ Day 7: MILESTONE — Intake geometry proven, CAD complete
  BLOCKER CHECK: Do we have game pieces to test with?

ELEVATOR (Team C: 2-3 students, Lead: _______)
  □ Day 1: Study 3 reference elevators from CAD Collection
  □ Day 2: Prototype elevator with plywood and drawer slides
  □ Day 3: Test height range and speed with real motors
  □ Day 4: Begin CAD (or load Blueprint template, set height param)
  □ Day 5: Order bearing blocks if not in stock
  □ Day 7: MILESTONE — Elevator concept proven, CAD complete
  BLOCKER CHECK: Bearing blocks and belt in inventory?

SOFTWARE (Team D: 2 students, Lead: _______)
  □ Day 1: Fork The Engine, update Constants for new game
  □ Day 2: Update navgrid.json for new field layout
  □ Day 3: Adapt AutonomousStrategy utility weights for new game
  □ Day 4: Test auto in simulation with new field
  □ Day 5: Load code on drivetrain, test basic teleop
  □ Day 7: MILESTONE — Teleop driving, auto paths running in sim
  BLOCKER CHECK: Game field CAD available for navgrid?

WEEK 2: BUILD V1 (Days 8-14)
─────────────────────────────
INTEGRATION (Teams A+B merge, Lead: _______)
  □ Day 8: Mount intake on drivetrain frame
  □ Day 9: Wire intake motor, test intake + drive together
  □ Day 10: Test intake with game pieces while driving
  □ Day 12: MILESTONE — Robot intakes game pieces while driving
  BLOCKER CHECK: Intake mounting points match frame?

ELEVATOR BUILD (Team C continues, Lead: _______)
  □ Day 8: Cut tubes, drill bearing block holes
  □ Day 9: Assemble elevator stages
  □ Day 10: Install belt/chain, test travel
  □ Day 12: Mount on frame (or test standalone)
  □ Day 14: MILESTONE — Elevator moves full range on robot
  BLOCKER CHECK: Parts from Day 5 order arrived?

CLIMBER START (2 students, Lead: _______)
  □ Day 10: Study reference climbers from CAD Collection
  □ Day 11: Prototype hook/latch mechanism
  □ Day 12: Test with practice field element
  □ Day 14: Begin CAD
  BLOCKER CHECK: Practice field element available?

SOFTWARE (Team D continues)
  □ Day 8: Integrate intake commands with state machine
  □ Day 10: Vision pipeline adapted for new game piece
  □ Day 12: Auto routines running on real drivetrain
  □ Day 14: MILESTONE — 2-piece auto working on real robot
  BLOCKER CHECK: Limelights mounted and calibrated?

DRIVER PRACTICE STARTS (Day 10+)
  □ Day 10: First teleop driving with intake
  □ Day 12: Practice cycling (intake → score)
  □ Day 14: Log first practice session in D.4 analytics

WEEK 3: INTEGRATE & ITERATE (Days 15-21)
────────────────────────────────────────
  □ Day 15: Full robot assembled (drivetrain + intake + elevator)
  □ Day 16: End effector/scorer mounted and wired
  □ Day 17: Full scoring cycle tested (intake → convey → score)
  □ Day 18: Climber V1 mounted
  □ Day 19: MILESTONE — Robot can intake, score, and climb
  □ Day 20: Begin reliability testing (run 50 cycles)
  □ Day 21: Fix anything that broke during reliability testing
  BLOCKER CHECK: Weight check — are we under 125 lbs?

WEEK 4: HARDEN (Days 22-28)
───────────────────────────
  □ Day 22: Electrical inspection (E.5 checklist)
  □ Day 23: Pre-match checklist (P.2) dry run
  □ Day 24: 3-piece auto reliable (90%+ success rate)
  □ Day 25: Driver practice — target 20 cycles in a session
  □ Day 26: Pit crew diagnostic (P.1 PitCrewDiagnosticCommand)
  □ Day 27: MILESTONE — Robot passes all quality checks
  □ Day 28: Bag day prep / final adjustments

WEEK 5-6: PRACTICE & COMPETE
─────────────────────────────
  □ Driver practice daily (D.4 analytics tracking)
  □ 4-piece auto target
  □ The Whisper tested in practice matches
  □ Scouting system pre-event report generated
  □ Spare parts packed per The Vault inventory
  □ EVENT WEEK — execute per event timeline
```

#### How It Works Technically

The generator is a Python script that takes a JSON config (from the
prediction engine's Prediction Bridge) and outputs a Markdown task plan.
Teams can customize it — add students' names, adjust timelines, add
team-specific tasks. The structure comes from the script; the details
come from the team.

```python
# Pseudocode
def generate_build_plan(architecture_spec):
    plan = BuildPlan()

    # Always the same
    plan.add_week1_drivetrain(architecture_spec["swerve"])

    # From prediction engine
    for subsystem in architecture_spec["subsystems"]:
        if subsystem["type"] == "elevator":
            plan.add_elevator_tasks(subsystem["stages"], subsystem["height"])
        elif subsystem["type"] == "intake":
            plan.add_intake_tasks(subsystem["style"], subsystem["width"])
        elif subsystem["type"] == "climber":
            plan.add_climber_tasks(subsystem["rungs"], subsystem["height"])
        elif subsystem["type"] == "shooter":
            plan.add_shooter_tasks(subsystem["wheel_size"])
        elif subsystem["type"] == "turret":
            plan.add_turret_tasks(subsystem["rotation"])

    # Always the same
    plan.add_software_tasks()
    plan.add_integration_milestones()
    plan.add_driver_practice_schedule()
    plan.add_quality_checkpoints()

    return plan.to_markdown()
```

---

### CL.2: Daily Standup Bot (12 hours to build)

A Slack or Discord bot that automates daily progress tracking.

#### How It Works

Every meeting day at a configured time (e.g., 6:00 PM when the
meeting starts), the bot posts in each mechanism channel:

```
🤖 STANDUP — Elevator Team (Day 12 of 42)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Please reply with:
1. What did your team complete since last standup?
2. What are you working on next?
3. Is anything blocking you?

Current milestone: "Elevator moves full range" (due Day 14)
Days until milestone: 2
```

Team leads reply in-thread. The bot collects responses.

#### Weekly Summary (auto-generated every Sunday)

```
═══════════════════════════════════════════
THE CLOCK — Week 2 Summary
Days elapsed: 14 of 42 | Days remaining: 28
═══════════════════════════════════════════

DRIVETRAIN ✅ On Track
  Milestones hit: 5/5
  Status: Integrated with intake, auto paths running
  No blockers

INTAKE ✅ On Track
  Milestones hit: 7/7
  Status: V1 mounted on drivetrain, cycling game pieces
  No blockers

ELEVATOR ⚠️ At Risk
  Milestones hit: 4/7
  Status: Tubes cut, bearing blocks not yet arrived
  BLOCKER: Bearing blocks ordered Day 5, not delivered
  Action needed: Check order status, source locally if needed

CLIMBER ✅ On Track
  Milestones hit: 2/4
  Status: Prototype hook tested, CAD started
  No blockers

SOFTWARE ✅ On Track
  Milestones hit: 6/7
  Status: Teleop working, 2-piece auto in sim
  Minor: Vision pipeline needs game piece training data

OVERALL: 24/30 milestones complete (80%)
RISK: Elevator bearing blocks — escalate to mentor
═══════════════════════════════════════════
```

#### Implementation

- Discord bot (discord.py) or Slack bot (slack-bolt)
- Task data stored in a JSON file (tasks.json)
- Standup responses logged with timestamps
- Weekly summary auto-posted to #build-season channel
- Mentor gets a DM if any team is flagged "At Risk"

---

### CL.3: Parts Order Tracker (10 hours to build)

Tracks every part from "needed" to "ordered" to "arrived" to "installed."

#### Integration with The Blueprint CAD Pipeline

When the CAD Pipeline generates a BOM, it automatically creates entries
in the parts tracker:

```
═══════════════════════════════════════════
THE CLOCK — Parts Tracker
═══════════════════════════════════════════

NEEDED (not yet ordered)
  [ ] 2x SDS Elevator Bearing Blocks — $45 each — source: SDS
  [ ] 8ft 2x1x0.0625 aluminum tube — $22 — source: McMaster
  [ ] 15mm HTD belt, 1200mm — $18 — source: WCP

ORDERED (waiting for delivery)
  [→] 2x Kraken X60 — ordered Jan 14 — expected Jan 18 — AndyMark
  [→] 4x 4" flex wheels — ordered Jan 14 — expected Jan 17 — WCP

ARRIVED (in inventory, not yet used)
  [✓] 1x Kraken X44 — arrived Jan 16 — in parts bin #3
  [✓] 10x 10-32 Nylock nuts (bag of 100) — arrived Jan 15

INSTALLED (on the robot)
  [★] 4x Thrifty Swerve modules — installed Day 1
  [★] 8x SPARK MAX — installed Day 2

BLOCKER ALERTS
  ⚠️ Elevator Bearing Blocks — NEEDED, not ordered
      Elevator team blocked starting Day 8
      → Order TODAY from SDS, or source from local team
```

#### How It Works

- Google Sheet or simple web app (React + localStorage)
- BOM import from CAD Pipeline (CSV)
- Cross-references The Vault inventory (what we already own)
- Flags items on the critical path that haven't been ordered
- Integrates with standup bot — blocked items show in standup prompts

#### The Cross-Reference

```
CAD Pipeline BOM says: "Need 4x SDS Elevator Bearing Blocks"
The Vault says: "Team owns 2x SDS Elevator Bearing Blocks"
Parts Tracker outputs: "Order 2 more SDS Elevator Bearing Blocks"
```

This eliminates both over-ordering (wasting budget) and under-ordering
(blocking the build).

---

## How The Clock Fits Into Kickoff Day

```
Hour 0:00 — Watch game reveal
Hour 0:30 — Fill in KICKOFF_TEMPLATE.md
Hour 1:00 — Run prediction engine (17 rules)
Hour 1:30 — Search CAD Collection for reference robots
Hour 2:00 — Run CAD Pipeline (The Blueprint)
Hour 2:30 — Run The Clock task generator ← NEW
             Output: 6-week build plan with tasks + assignments
Hour 3:00 — Run The Vault inventory cross-reference ← NEW
             Output: parts to order list (BOM minus inventory)
Hour 3:30 — Order parts (from parts tracker output)
Hour 4:00 — Teams assigned, prototyping begins
             Standup bot activated in Discord/Slack
```

By hour 4, you have: a validated robot architecture, parametric CAD,
adapted software, a 6-week task plan with assignments, and parts
ordered. No other team at your level is doing this.

---

## Development Roadmap

| Block | Task | Hours | Target |
|-------|------|-------|--------|
| CL.1 | Task generator script (Python → Markdown) | 8 | December 2026 |
| CL.2a | Standup bot — Discord/Slack integration | 6 | December 2026 |
| CL.2b | Standup bot — weekly summary generator | 4 | December 2026 |
| CL.2c | Standup bot — blocker detection + mentor alert | 2 | December 2026 |
| CL.3a | Parts tracker — web app or Google Sheet template | 6 | December 2026 |
| CL.3b | Parts tracker — BOM import from CAD Pipeline | 2 | December 2026 |
| CL.3c | Parts tracker — Vault inventory cross-reference | 2 | December 2026 |
| **Total** | | **30** | |

---

## Integration with Other Engine Systems

```
Prediction Engine ──→ CL.1 Task Generator (mechanism list → tasks)
CAD Pipeline BOM ───→ CL.3 Parts Tracker (what to order)
The Vault ──────────→ CL.3 Parts Tracker (what we already have)
CL.2 Standup Bot ───→ CL.3 Parts Tracker (blocker alerts in standups)
CL.1 Task Plan ────→ CL.2 Standup Bot (milestone tracking)
D.4 Practice Log ──→ CL.2 Standup Bot (driver practice hours in summary)
P.1 Robot Reports ─→ CL.2 Standup Bot (failure events flagged)
```

---

*Architecture document — The Clock | THE ENGINE | Team 2950 The Devastators*
