# THE ENGINE — Driver Station Systems
# Codename: "The Cockpit"
# Target: Ready before 2027 season
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Overview

The driver station is where The Engine meets the human. Five systems
that transform it from "laptop on a shelf with a controller plugged in"
to a fighter jet cockpit where every piece of information is placed
deliberately, the controls minimize hand movement, and the driver
never has to look away from the field.

254 runs a single driver with 3 modes on one controller. Their binder
documents every button mapping. 3847 Spectrum recommends a fisheye
camera feed showing the intake. Both teams treat the driver station
as an engineered system, not an afterthought.

Total investment: 39 hours.

---

## D.1: Controller Mapping Optimization (3 hours)
**Target:** Pre-season, finalized before first practice session

### Principles
- Most frequent actions on triggers/bumpers (fingers already resting there)
- Mode switches on D-pad (deliberate, hard to hit accidentally)
- Emergency functions on face buttons requiring intentional press
- Left stick = translation, right stick = rotation (universal FRC standard)
- Never put a destructive action next to a common action

### Recommended Layout (Single Driver, Xbox-style)

**Triggers & Bumpers (high frequency — every cycle):**
| Button | Action | Why Here |
|--------|--------|----------|
| Right Trigger | Intake / collect game piece | Most frequent action |
| Left Trigger | Score / eject game piece | Second most frequent |
| Right Bumper | Auto-align to scoring target | Used every scoring cycle |
| Left Bumper | Auto-align to game piece | Used every collection cycle |

**D-Pad (mode switches — a few times per match):**
| Button | Action | Why Here |
|--------|--------|----------|
| D-Pad Up | Scoring height: HIGH | Deliberate selection |
| D-Pad Right | Scoring height: MID | Deliberate selection |
| D-Pad Down | Scoring height: LOW | Deliberate selection |
| D-Pad Left | Toggle speed mode (full/precision) | Situational |

**Face Buttons (less frequent + endgame):**
| Button | Action | Why Here |
|--------|--------|----------|
| A | Stage / confirm score | Confirm action |
| B | Stow all mechanisms | Safety reset |
| X | Deploy climber | Endgame only |
| Y | Climb / winch | Endgame only |

**Sticks:**
| Stick | Action |
|-------|--------|
| Left stick | Field-relative translation (X/Y) |
| Right stick X | Field-relative rotation |
| Right stick press | Reset gyro heading |
| Left stick press | Toggle robot-relative drive |

**Back Buttons (if controller has them):**
| Button | Action |
|--------|--------|
| Start | Exhaust / reverse intake |
| Back | Manual override mode |

### Documentation
Print the mapping as a card. Tape it to the driver station shelf.
During the first 5 practice matches, the driver memorizes it.
The card remains for pit crew reference and backup drivers.

### Validation
During practice sessions, count how many times the driver looks
down at the controller. Target: zero after 5 sessions. If the
driver is still looking down, the mapping needs adjustment — the
most-used actions aren't on intuitive buttons.

---

## D.2: Dashboard Layout Design (6 hours)
**Target:** Pre-season, iterate after first event

### Core Principle
The driver should NEVER read text during a match. Everything mid-match
is communicated through color, position, and size. Text is for pre-match
setup and pit crew diagnostics only.

### Layout Zones (Shuffleboard or custom HTML dashboard)

```
┌─────────────────────────────────────────────────────────┐
│ MATCH TIME  │  ROBOT STATE (color)  │  BATTERY │ SCORE  │ ← Top Strip
│   1:47      │  ■■■ SCORING ■■■      │  12.4V   │ 87-62  │   (always visible)
├─────────────────────────────────────────────────────────┤
│                                                         │
│              DRIVER CAMERA FEED                         │ ← Main Area
│              (fisheye showing intake)                   │   (80% of screen)
│                                                         │
│   ┌──────┐                                              │
│   │ AUTO │  (pre-match only: auto mode selector)        │
│   │SELECT│                                              │
│   └──────┘                                              │
├─────────────────────────────────────────────────────────┤
│ CAN: 14/14 │ Cycles: 7 │ Avg: 4.8s │ Hub: ACTIVE      │ ← Bottom Strip
│            │           │           │ (12s remaining)    │   (pit crew info)
└─────────────────────────────────────────────────────────┘
```

### State Colors (driver reads these peripherally)
| State | Color | Meaning |
|-------|-------|---------|
| IDLE | Gray | No game piece, not moving toward target |
| INTAKING | Blue pulse | Intake deployed, seeking game piece |
| HOLDING | Solid green | Game piece acquired and secured |
| SCORING | Yellow pulse | Actively ejecting game piece |
| CLIMBING | Purple pulse | Climber engaged |
| ERROR | Red flash | Stall detected or mechanism fault |
| ENDGAME | Orange pulse | <30 seconds remaining |

### Camera Feed
One Limelight or USB camera configured as a fisheye driver camera.
Mount position: looking down at the intake from the robot's frame.
The driver uses this to confirm game piece acquisition without
turning their head away from the field.

3847 Spectrum specifically recommends: "Fisheye for the driver
camera should be able to see the intake."

### Pre-Match vs Match Mode
Dashboard switches layout when match starts:
- Pre-match: auto selector visible, detailed telemetry shown
- Match active: auto selector hidden, camera feed maximized,
  only color-coded status indicators visible
- Post-match: cycle summary shown automatically

---

## D.3: Operator Console Hardware Standard (2 hours)
**Target:** Pre-season, photo-document and laminate

### Physical Setup Specification
| Item | Position | Secured By |
|------|----------|-----------|
| Laptop | Center of shelf | Velcro strip (loop on shelf, hook on laptop) |
| Primary controller | Right side of laptop | USB cable routed OVER laptop, not under |
| Backup controller | In driver station tote (under shelf) | Zip-tied cable, ready to swap |
| Ethernet cable | Left side of laptop | Plugged into correct port (label the port) |
| Power cable | Field outlet → laptop | Routed behind laptop, not across shelf |

### Photo Guide
Take 6 photos of the correct setup:
1. Full driver station from driver's perspective
2. Cable routing (Ethernet, USB, power)
3. Velcro placement on shelf and laptop bottom
4. Controller position and cable routing
5. Backup controller location in tote
6. View from behind (what the drive coach sees)

Print these photos on a single sheet. Laminate it. Store it in the
driver station tote lid. Any student can set up the driver station
identically at every event in under 3 minutes.

### Failure Prevention
| Problem | Prevention |
|---------|-----------|
| Laptop slides during hard defense | Velcro strip (mandatory) |
| Ethernet pulled during match | Route behind laptop, leave 6" slack loop |
| Controller disconnects | USB extension cable zip-tied to shelf |
| Wrong Ethernet port | Label the correct port with tape |
| Laptop dies mid-match | Always plugged into field power outlet |
| Controller drift | Calibrate in Driver Station before first match |

---

## D.4: Driver Practice Analytics (12 hours)
**Target:** Pre-season, runs during all practice sessions

### What It Tracks
Extends the existing CycleTracker (Phase 6*.5) and StallDetector
(Phase 6*.4) to build a driver improvement database.

Per practice session:
| Metric | Source | How Measured |
|--------|--------|-------------|
| Total cycles completed | CycleTracker | Pickup → score count |
| Average cycle time | CycleTracker | Mean of all cycles |
| Fastest cycle | CycleTracker | Min cycle time |
| Cycle time by field position | CycleTracker + odometry | Group by starting zone |
| Intake success rate | Beam break + intake motor | Attempts vs acquisitions |
| Scoring accuracy | AutoScoreCommand | Attempts vs confirmed scores |
| Climb time | Climber command logs | Engage → confirmed climb |
| Climb success rate | Climber command logs | Attempts vs successes |
| Defense evasion (if practiced) | Velocity drops during contact | Deceleration events |

### Session Report (auto-generated after each practice)
```
═══════════════════════════════════════════════
DRIVER PRACTICE REPORT — Session 14
Date: 2027-02-15 | Duration: 45 min | Cycles: 52
═══════════════════════════════════════════════

CYCLE TIMES
  Average:  4.6s (↓ from 4.9s last session)
  Fastest:  3.7s
  Slowest:  7.2s (intake jam at T+12:34)
  Std Dev:  0.8s

BY FIELD POSITION
  Left approach:   4.2s avg (strong)
  Center approach:  4.5s avg (good)
  Right approach:   5.4s avg (needs work ← DRILL TARGET)

INTAKE
  Success rate: 96% (48/50 attempts)
  Jam events: 2 (both on side pickups)

SCORING
  Accuracy: 94% (49/52 cycles)
  Misses: 3 (2 at HIGH, 1 at MID)

CLIMB
  Attempts: 5 | Successes: 5 | Avg time: 1.9s

TREND (last 5 sessions)
  Avg cycle: 5.8 → 5.4 → 5.1 → 4.9 → 4.6 ✓ improving

RECOMMENDED DRILLS
  1. Right-side approach (10 reps) — 1.2s slower than left
  2. HIGH scoring accuracy (10 reps) — 2 of 3 misses at HIGH
═══════════════════════════════════════════════
```

### Implementation
- Python script reads AdvantageKit logs from practice sessions
- Stores historical data in a JSON file (session_history.json)
- Generates trend charts (matplotlib) showing improvement curves
- Identifies weakest area and recommends specific drills

### Improvement Targets
| Metric | Rookie | Competitive | Elite |
|--------|--------|------------|-------|
| Avg cycle time | <7.0s | <5.0s | <4.0s |
| Intake success | >80% | >90% | >97% |
| Scoring accuracy | >75% | >90% | >95% |
| Climb time | <5.0s | <2.5s | <1.5s |
| Practice hours (season) | 20+ | 50+ | 80+ |

Rule M3: "The team that drives more wins." This system proves it
with data.

---

## D.5: Drive Coach Information System (16 hours)
**Target:** Pre-season, the teleop copilot

### The Concept
The Engine's autonomous strategy runs during teleop too — but instead
of controlling the robot, it displays recommendations to the drive
coach. The coach glances at their phone/tablet, calls out the
recommendation, and the driver executes.

This is where The Engine becomes a real-time strategic advisor.

### Hardware
- Phone or tablet (any Android/iOS device)
- Connected to robot via NetworkTables (same WiFi network)
- Web dashboard served from the driver station laptop
- OR: Shuffleboard on a second monitor if available

### Display Layout
```
┌───────────────────────────────┐
│     RECOMMENDED ACTION        │
│                               │
│   ███ COLLECT FUEL ███        │  ← Large, color-coded
│   Hub inactive: 8s remaining  │  ← Context
│                               │
├───────────────────────────────┤
│ Score: RED 87 — BLUE 62       │  ← Match awareness
│ Time: 1:22 remaining          │
│ Fuel held: 3                  │
├───────────────────────────────┤
│ Hub status: INACTIVE (8s)     │  ← Game-specific
│ Next active: 0:74 on clock    │
├───────────────────────────────┤
│ Alliance partner 1: SCORING   │  ← Coordination
│ Alliance partner 2: CLIMBING  │
└───────────────────────────────┘
```

### Recommendation Logic
Uses the same utility scoring from AutonomousStrategy.java but
outputs human-readable recommendations:

| Game State | Recommendation | Color |
|-----------|---------------|-------|
| Hub active + fuel held | "SCORE NOW" | Green |
| Hub active + no fuel | "COLLECT FAST — Hub active" | Yellow |
| Hub inactive + near fuel | "COLLECT — Hub back in Xs" | Blue |
| Hub inactive + full hopper | "POSITION FOR HUB — Xs" | Cyan |
| <30s + not climbing | "CLIMB NOW" | Red pulse |
| <30s + already climbing | "CLIMBING — hold steady" | Purple |
| Opponent blocking score path | "SCORE FROM OTHER SIDE" | Orange |

### What Makes This Different
Most FRC drive coaches rely on experience and instinct. This system
gives them the same data-driven recommendations that the autonomous
mode uses — but presented as suggestions, not commands. The coach
always has the final say. The system just makes sure they never miss
a Hub transition, forget about endgame timing, or lose track of the
score differential.

### Implementation
1. AutonomousStrategy.java already calculates utility scores every 0.5s
2. Add a NetworkTables publisher: /CoachDisplay/RecommendedAction,
   /CoachDisplay/HubStatus, /CoachDisplay/TimeRemaining, etc.
3. Build a simple web dashboard (HTML + JS reading NT via pynetworktables
   websocket) or use Shuffleboard
4. Phone connects to robot WiFi and opens the dashboard URL

### Privacy Note
This system only reads data the robot already publishes to
NetworkTables. It does not violate any FRC rules about communication
during matches — the drive coach is allowed to see any data on the
robot's dashboard.

---

## Integration with Existing Engine Systems

```
Phase 6*.5 CycleTracker ────→ D.4 Practice Analytics
Phase 6*.6 MovingShotComp ──→ D.2 Dashboard (shot readiness indicator)
Phase 7*.1 RumbleManager ──→ D.1 Controller (haptic feedback layer)
Phase 7*.2 SpeedModeManager → D.1 Controller (D-pad toggle)
Phase 7*.3 OneButtonScore ──→ D.1 Controller (trigger mapping)
Phase 3.5 AutonomousStrategy → D.5 Coach System (utility recommendations)
AdvantageKit logging ────────→ D.4 Practice Analytics (data source)
VisionSubsystem ─────────────→ D.2 Dashboard (camera feed)
```

Every driver station system builds on code that already exists in
The Engine. D.4 and D.5 are the main new development. D.1-D.3 are
documentation and physical setup — no code required.

---

## Total Investment

| System | Hours | Type | Dependencies |
|--------|-------|------|-------------|
| D.1 Controller Mapping | 3 | Documentation + testing | Existing Phase 7 code |
| D.2 Dashboard Layout | 6 | Shuffleboard/HTML config | VisionSubsystem for camera |
| D.3 Console Hardware Standard | 2 | Photo documentation | None |
| D.4 Practice Analytics | 12 | Python script | CycleTracker logs |
| D.5 Coach Information System | 16 | Web dashboard + NT publisher | AutonomousStrategy.java |
| **TOTAL** | **39** | | |

---

*Architecture document — The Cockpit | THE ENGINE | Team 2950 The Devastators*
