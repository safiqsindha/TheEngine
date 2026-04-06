# THE ENGINE — Pit Systems Architecture
# Codename: "The Pit Crew"
# Target: Ready before 2027 season
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Overview

Six systems that transform pit operations from reactive ("something broke,
what do we do?") to proactive ("the data says inspect the elevator belt
before it fails"). Ordered by priority — the first three can be deployed
at your next event.

---

## P.1: Robot Reports Channel
**Effort:** 10 minutes | **Impact:** Transforms pit culture
**Target:** Immediately

Create a dedicated Slack or Discord channel called #robot-reports.
Any time something breaks, malfunctions, or behaves unexpectedly,
someone posts:
- What broke
- When (which match or practice session)
- What was happening when it broke
- How it was fixed

Example post:
> Match 12: Left front swerve module grinding noise after hard
> collision. Inspected — azimuth belt jumped one tooth.
> Re-tensioned and verified. Total downtime: 8 minutes.

Before each event, read every report from previous events and
pre-inspect every documented failure point. Over time this channel
becomes your reliability database.

Source: Team 3847 Spectrum uses this exact system. They call it
"Robot Reports Channel to document things that break and need to
be repaired."

---

## P.2: Pre-Match Checklist App
**Effort:** 4 hours | **Impact:** Prevents avoidable failures
**Target:** Before first 2027 event

Convert the existing `tools/pre_match_check.py` into a mobile-friendly
web page with large green/yellow/red indicators.

Checklist items:
1. Battery swapped (voltage > 12.5V) — GREEN/RED
2. Battery connector zip-tied — GREEN/RED
3. Bumpers secure (all fasteners checked) — GREEN/RED
4. Limelight booted and connected — GREEN/RED (auto-detect via NT)
5. Autonomous mode selected on dashboard — GREEN/RED
6. Driver station assignment confirmed — GREEN/RED
7. Radio LED solid — GREEN/RED
8. Intake deploys freely (manual check) — GREEN/RED
9. Elevator moves full range (manual check) — GREEN/RED
10. Driver controller connected — GREEN/RED (auto-detect)

Implementation: React app or simple HTML served from the roboRIO
or driver station laptop. Reads NetworkTables for automated checks
(battery, Limelight, radio, controller). Manual items require
tap-to-confirm.

Rule: If ANY item is RED, the robot does not go to the field.

---

## P.3: Post-Match Diagnostic Report
**Effort:** 8 hours | **Impact:** Targeted repairs, no guessing
**Target:** Before first 2027 event

After each match, the AdvantageKit log file is copied from the
roboRIO USB stick. A Python script parses it and generates a
one-page diagnostic report.

Report contents:
- Match number, alliance, result (W/L), score
- Auto performance: targets attempted vs scored, paths followed
- Teleop cycle times: each cycle with timestamps
- Mechanism health: any stall detections (motor, timestamp, duration)
- Odometry drift: max divergence between vision and wheel odometry
- Climber: engagement time, success/failure
- Warnings: anything outside normal operating ranges
- Comparison to team averages (is this match better or worse?)

Output format: Terminal printout (immediate) + saved HTML report
(for later review). Drive coach gets the printout before the next
match. Mentor reviews the HTML during lunch.

Implementation: Extend `tools/post_match_analyzer.py` (already exists)
to parse AdvantageKit WPILOG files. Key data channels:
- /RealOutputs/SwerveSubsystem/ModuleStates
- /RealOutputs/AutonomousStrategy/BestTarget
- /RealOutputs/CycleTracker/*
- /RealOutputs/StallDetector/*
- /RealOutputs/OdometryDivergenceDetector/*

---

## P.4: Wear Tracking System
**Effort:** 12 hours | **Impact:** Prevents mid-event failures
**Target:** Before first 2027 event

Every mechanism has a fatigue life. Track total actuations per
mechanism across the entire season.

Tracked mechanisms:
| Mechanism | Counter Source | Inspect At | Replace At |
|-----------|---------------|-----------|------------|
| Elevator cycles | Hall effect trigger count | 500 cycles | 1000 cycles |
| Intake deploys | Deploy motor command count | 200 cycles | 500 cycles |
| Climber engagements | Climber command count | 20 cycles | 50 cycles |
| Swerve module rotation | Steer encoder total revolutions | Every event | Seasonal |
| Drive belt/chain | Drive encoder total distance (km) | 10 km | 25 km |
| Shooter wheel | Shooter motor total revolutions | 5000 rev | 10000 rev |

Implementation: Add a PersistentCounter class that saves counts to
a JSON file on the roboRIO. Increments in the subsystem periodic()
methods. Display on SmartDashboard/Shuffleboard. The pre-match
checklist (P.2) reads these counters and warns when approaching
inspection thresholds.

Thresholds are initial estimates — update based on actual failure
data from Robot Reports (P.1). After one season, you'll have real
numbers for your specific hardware.

---

## P.5: Pit Display Dashboard
**Effort:** 16 hours | **Impact:** Professionalism + judge impression
**Target:** Before first 2027 event

A monitor or tablet at the pit showing real-time robot status.

Dashboard sections:
1. **Robot Health** — Battery voltage (current + trend across matches),
   motor temperatures (if available via CAN), CAN bus device count,
   total match count on each mechanism (from P.4 wear tracking)
2. **Match Performance** — Last match cycle times, auto score,
   teleop score, climb result. Trend line across all matches.
3. **Next Match** — Time until next match (from TBA API), opponent
   teams, any known scouting data on opponents
4. **Maintenance Status** — Wear counters with color-coded thresholds
   (green/yellow/red), last inspection timestamps

Implementation: React app or Shuffleboard custom layout. Data
sources: NetworkTables (live robot data), AdvantageKit logs
(historical), TBA API (schedule + opponents).

Judge benefit: When judges visit the pit, they see a team that
monitors their robot with real-time telemetry. This directly
supports Quality Award and Excellence in Engineering Award
submissions.

---

## P.6: Digital Twin Pit Display
**Effort:** 20 hours | **Impact:** Debugging + judge wow factor
**Target:** Before second 2027 event (iterate after first event)

The robot's 3D model in AdvantageScope, updating in real-time
from the pit or from match replay.

Requirements:
- Import robot 3D model (STEP → GLB/GLTF for AdvantageScope)
- Map joint positions to logged encoder values:
  - Elevator height → elevator encoder
  - Intake deploy angle → deploy encoder
  - Wrist angle → wrist encoder
  - Climber position → climber encoder
- Configure in AdvantageScope's 3D view config

Use cases:
1. **Live debugging:** "The elevator is binding at 42 inches" —
   see it in 3D, correlate with motor current graph
2. **Post-match replay:** Replay the full match in 3D to
   understand what happened at specific timestamps
3. **Judge demo:** Show judges a synchronized 3D model moving
   with the real robot. No other team at your event will have this.

Implementation: AdvantageScope already supports custom 3D models
with articulating joints. The main work is creating the model
mapping config file and ensuring all joint positions are logged
via AdvantageKit.

---

## Integration Map

```
P.1 Robot Reports ──→ feeds failure data into ──→ P.4 Wear Tracking
        │                                              │
        ▼                                              ▼
P.3 Post-Match Report ──→ auto-generates ──→ P.5 Pit Dashboard
        │                                              │
        ▼                                              ▼
P.2 Pre-Match Checklist ←── reads wear ←── P.4 Wear Tracking
                                                       │
                                                       ▼
                                               P.6 Digital Twin
                                         (uses same logged data)
```

All six systems share the same data backbone: AdvantageKit logs +
NetworkTables + the Robot Reports channel. Building P.1-P.3 first
creates the data foundation that P.4-P.6 build on.

---

## Total Investment

| System | Hours | Dependencies |
|--------|-------|-------------|
| P.1 Robot Reports Channel | 0.2 | None (Slack/Discord) |
| P.2 Pre-Match Checklist App | 4 | NetworkTables connection |
| P.3 Post-Match Diagnostic Report | 8 | AdvantageKit log parsing |
| P.4 Wear Tracking System | 12 | P.1 for threshold calibration |
| P.5 Pit Display Dashboard | 16 | P.3 + P.4 for data |
| P.6 Digital Twin Pit Display | 20 | AdvantageScope + 3D model |
| **TOTAL** | **60.2** | |

---

*Architecture document — The Pit Crew | THE ENGINE | Team 2950 The Devastators*
