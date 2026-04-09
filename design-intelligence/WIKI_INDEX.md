# The Engine — Design Intelligence Wiki Index

> Persistent, compounding knowledge base for FRC Team 2950 — The Devastators.
> Maintained by The Engine's LLM Wiki agent. Each file is a wiki page.
> New sources get integrated, cross-referenced, contradictions flagged.

Last updated: 2026-04-08

---

## How This Wiki Works

This folder follows the **LLM Wiki pattern**: instead of re-processing raw documents every query, the LLM builds and maintains structured markdown files that compound knowledge over time. Every new source (CD post, team binder, game manual, EPA data) gets integrated into the relevant pages, cross-references updated, contradictions flagged.

**Human role:** Curate sources, direct analysis, review diffs.
**LLM role:** Summarize, cross-reference, maintain consistency, flag contradictions.

Update script: `../scripts/wiki_update.py`

---

## File Catalog

### Core Intelligence (5 files)
The foundation — patterns extracted from elite teams that power the prediction engine.

| File | Purpose | Key Entities |
|------|---------|-------------|
| [CROSS_SEASON_PATTERNS.md](CROSS_SEASON_PATTERNS.md) | **The brain.** 18 rules + 12 meta-rules from 50+ robots across 10 seasons | R1-R18, confidence scores, game conditions |
| [254_CROSS_SEASON_ANALYSIS.md](254_CROSS_SEASON_ANALYSIS.md) | Deep patterns from Team 254 (2019-2025) | Drivetrains, intakes, scorers, climbers, frame sizes |
| [MULTI_TEAM_ANALYSIS.md](MULTI_TEAM_ANALYSIS.md) | Cross-team comparison: 1678, 6328, 4414, 1323, 2910 | Design philosophies, mechanism patterns, cycle times |
| [TEAM_DATABASE.md](TEAM_DATABASE.md) | Historical inventory of 13 elite teams with resource types | CAD releases, code repos, binders per season |
| [OPEN_ALLIANCE_TRACKER.md](OPEN_ALLIANCE_TRACKER.md) | Living index of teams whose public resources feed The Engine | Tier 1/2 teams, GitHub repos, EPA rankings |

### Validation & Benchmarks (4 files)
Tests the prediction engine against real competition data.

| File | Purpose | Key Entities |
|------|---------|-------------|
| [PREDICTION_ENGINE_VALIDATION_14GAME.md](PREDICTION_ENGINE_VALIDATION_14GAME.md) | v2 engine tested against 14 historical games (2012-2026) | 215 rule applications, accuracy per rule |
| [REBUILT_VALIDATION.md](REBUILT_VALIDATION.md) | 2026 REBUILT game live validation | 254 (331.7 EPA), 1323 (313.5 EPA), mechanism predictions |
| [COMPETITIVE_BENCHMARKS.md](COMPETITIVE_BENCHMARKS.md) | Winning alliance score targets (2022-2026) | Avg scores by comp level, target EPA per robot |
| [STATBOTICS_EPA_2026.md](STATBOTICS_EPA_2026.md) | Real-time EPA data from 2026 REBUILT season | Total/Auto/Teleop/Endgame EPA, worldwide rankings |

### Architecture — The 10 Systems (11 files)
Each ARCH_* file specifies one of The Engine's subsystems.

| File | Codename | Purpose | Hours |
|------|----------|---------|-------|
| [ARCH_CAD_PIPELINE.md](ARCH_CAD_PIPELINE.md) | The Blueprint | Autonomous CAD generation from predictions | 120-150h |
| [ARCH_BUILD_MANAGEMENT.md](ARCH_BUILD_MANAGEMENT.md) | The Clock | 6-week build season project management | — |
| [ARCH_CD_WATCHER.md](ARCH_CD_WATCHER.md) | The Antenna | Daily Chief Delphi scraper for technical intelligence | 32h |
| [ARCH_SCOUTING_SYSTEM.md](ARCH_SCOUTING_SYSTEM.md) | The Scout | 3-layer scouting (automated + pit + stand) | 54h |
| [ARCH_AI_MATCH_ANALYSIS.md](ARCH_AI_MATCH_ANALYSIS.md) | The Eye | AI video analysis of every match | 60-80h |
| [ARCH_COACH_AI.md](ARCH_COACH_AI.md) | The Whisper | Real-time strategy on drive coach display | 38h |
| [ARCH_DRIVER_STATION.md](ARCH_DRIVER_STATION.md) | The Cockpit | Controller mapping, dashboard, console hardware | 39h |
| [ARCH_ELECTRICAL_SYSTEMS.md](ARCH_ELECTRICAL_SYSTEMS.md) | The Grid | Wiring standards, CAN topology, inspection checklists | 18h |
| [ARCH_PIT_SYSTEMS.md](ARCH_PIT_SYSTEMS.md) | The Pit Crew | Robot reports, pre-match checklist, failure log | 60h |
| [ARCH_PARTS_INVENTORY.md](ARCH_PARTS_INVENTORY.md) | The Vault | Parts inventory vs CAD BOM | 12h |
| [ELEVATOR_DESIGN_SPEC.md](ELEVATOR_DESIGN_SPEC.md) | — | 254-caliber elevator parametric spec | — |

### Roadmaps & Planning (3 files)

| File | Purpose |
|------|---------|
| [ENGINE_MASTER_ROADMAP.md](ENGINE_MASTER_ROADMAP.md) | Prioritized execution plan for all 10 systems by Dec 2026 (463-513h) |
| [ROADMAP_2028.md](ROADMAP_2028.md) | 2028 enhancements: on-robot LLM, pre/post-match briefings |
| [KICKOFF_TEMPLATE.md](KICKOFF_TEMPLATE.md) | Fill-in form combined with CROSS_SEASON_PATTERNS on kickoff day |

### Training & Education (9 files)
Student pathway from setup to full system understanding.

| File | Purpose | Duration |
|------|---------|----------|
| [STUDENT_ONBOARDING_GUIDE.md](STUDENT_ONBOARDING_GUIDE.md) | Day 1 setup (WPILib, Git, AdvantageScope) | ~2h |
| [TRAINING_MODULE_1_PATTERN_RULES.md](TRAINING_MODULE_1_PATTERN_RULES.md) | Why we study other teams' patterns | ~45min |
| [TRAINING_MODULE_2_PREDICTION_ENGINE.md](TRAINING_MODULE_2_PREDICTION_ENGINE.md) | How the prediction engine works | ~60min |
| [TRAINING_MODULE_3_DESIGN_INTELLIGENCE.md](TRAINING_MODULE_3_DESIGN_INTELLIGENCE.md) | Full pipeline trace: game reveal to autonomous | ~60min |
| [TRAINING_MODULE_4_PATHFINDING.md](TRAINING_MODULE_4_PATHFINDING.md) | A* pathfinding and navigation grid | ~50min |
| [TRAINING_MODULE_5_VISION_YOLO.md](TRAINING_MODULE_5_VISION_YOLO.md) | YOLO vision pipeline and Limelight | ~55min |
| [TRAINING_MODULE_6_SIMULATION_TESTING.md](TRAINING_MODULE_6_SIMULATION_TESTING.md) | Simulation, testing, quality gates | ~55min |
| [SIMULATION_EXERCISES.md](SIMULATION_EXERCISES.md) | Hands-on exercises for all 6 modules | — |
| [YOLO_TRAINING_GUIDE.md](YOLO_TRAINING_GUIDE.md) | Step-by-step: image capture to Limelight deploy | 4-6h |

### Archived / Future (3 files in `_archived/`)

| File | Status |
|------|--------|
| ARCH_F13_PREMATCH_STRATEGIST.md | Architecture only — build when Jetson available |
| ARCH_F18_ALLIANCE_UDP.md | Architecture only — deploy at Worlds playoffs |
| ARCH_F21_SCOUTING_PIPELINE.md | Architecture only — students build scouting app |

---

## Dependency Graph

```
                    Raw Sources (CD, binders, game manuals, EPA data)
                                      |
                                      v
    +------------------+    +-------------------+    +--------------------+
    | TEAM_DATABASE    |    | OPEN_ALLIANCE_    |    | 254_CROSS_SEASON_  |
    | (13 elite teams) |    | TRACKER (tiers)   |    | ANALYSIS (deep)    |
    +--------+---------+    +--------+----------+    +---------+----------+
             |                       |                         |
             +----------+------------+-------------------------+
                        |
                        v
          +-----------------------------+
          | CROSS_SEASON_PATTERNS       |  <-- The Brain
          | 18 rules + 12 meta-rules    |
          +------+----------+-----------+
                 |          |
        +--------+    +----+--------+
        v              v             v
  KICKOFF_       PREDICTION_    REBUILT_
  TEMPLATE       ENGINE_        VALIDATION
  (game input)   VALIDATION     (live 2026)
        |        _14GAME             |
        v             |              v
  (Predictions)       |        STATBOTICS_
        |             |        EPA_2026
        +------+------+
               |
     +---------+---------+
     v                   v
  ARCH_CAD_          ARCH_BUILD_
  PIPELINE           MANAGEMENT
  (BOM output)       (task schedule)
     |
     v
  ARCH_PARTS_
  INVENTORY

  ARCH_CD_WATCHER ──feeds──> CROSS_SEASON_PATTERNS
                             TEAM_DATABASE
                             OPEN_ALLIANCE_TRACKER

  ARCH_SCOUTING_SYSTEM <── ARCH_AI_MATCH_ANALYSIS
                       <── OPEN_ALLIANCE_TRACKER
                       ──> ARCH_COACH_AI

  COMPETITIVE_BENCHMARKS ──validates──> Prediction accuracy
  ELEVATOR_DESIGN_SPEC   ──template──> ARCH_CAD_PIPELINE
  ENGINE_MASTER_ROADMAP  ──orchestrates──> all ARCH_* files
```

---

## Entity Cross-Reference

### Teams
| Team | Primary File | Also Referenced In |
|------|-------------|-------------------|
| 254 | 254_CROSS_SEASON_ANALYSIS | CROSS_SEASON_PATTERNS, TEAM_DATABASE, OPEN_ALLIANCE_TRACKER, REBUILT_VALIDATION, MULTI_TEAM_ANALYSIS, TRAINING_MODULE_1 |
| 1678 | MULTI_TEAM_ANALYSIS | TEAM_DATABASE, OPEN_ALLIANCE_TRACKER, TRAINING_MODULE_1 |
| 6328 | MULTI_TEAM_ANALYSIS | TEAM_DATABASE, OPEN_ALLIANCE_TRACKER, TRAINING_MODULE_1 |
| 4414 | MULTI_TEAM_ANALYSIS | TEAM_DATABASE |
| 1323 | MULTI_TEAM_ANALYSIS | TEAM_DATABASE, REBUILT_VALIDATION |
| 2910 | MULTI_TEAM_ANALYSIS | TEAM_DATABASE, TRAINING_MODULE_1 |
| 118 | TEAM_DATABASE | OPEN_ALLIANCE_TRACKER, REBUILT_VALIDATION |
| 3847 | TEAM_DATABASE | OPEN_ALLIANCE_TRACKER, ARCH_ELECTRICAL_SYSTEMS, TRAINING_MODULE_1 |
| 1690 | OPEN_ALLIANCE_TRACKER | TRAINING_MODULE_1 |
| 1114 | TEAM_DATABASE | OPEN_ALLIANCE_TRACKER |
| 973 | TEAM_DATABASE | OPEN_ALLIANCE_TRACKER |
| 2056 | TEAM_DATABASE | OPEN_ALLIANCE_TRACKER |
| 2826 | TEAM_DATABASE | TRAINING_MODULE_5 |

### Prediction Rules
| Rule | Domain | Defined In | Validated In |
|------|--------|-----------|-------------|
| R1 | Drivetrain (swerve) | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME, REBUILT_VALIDATION |
| R2 | Intake width | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME |
| R3 | Roller material | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME |
| R4 | Scoring method | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME, REBUILT_VALIDATION |
| R5 | Elevator vs arm | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME |
| R6 | Turret decision | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME |
| R7 | Climb strategy | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME, REBUILT_VALIDATION |
| R8-R18 | Various | CROSS_SEASON_PATTERNS | PREDICTION_ENGINE_VALIDATION_14GAME |
| R19 | Scoring analysis | CROSS_SEASON_PATTERNS | REBUILT_VALIDATION |

### Games
| Game | Year | Analyzed In |
|------|------|------------|
| Rapid React | 2022 | COMPETITIVE_BENCHMARKS, PREDICTION_ENGINE_VALIDATION_14GAME |
| Charged Up | 2023 | COMPETITIVE_BENCHMARKS, PREDICTION_ENGINE_VALIDATION_14GAME |
| Crescendo | 2024 | COMPETITIVE_BENCHMARKS, PREDICTION_ENGINE_VALIDATION_14GAME |
| Reefscape | 2025 | COMPETITIVE_BENCHMARKS, PREDICTION_ENGINE_VALIDATION_14GAME |
| REBUILT | 2026 | REBUILT_VALIDATION, STATBOTICS_EPA_2026, COMPETITIVE_BENCHMARKS |

---

## Update Protocol

When new information arrives, the wiki update script (`../scripts/wiki_update.py`) follows this loop:

1. **Ingest** — Read the new source, extract key facts
2. **Match** — Identify which wiki pages are affected (using this index)
3. **Diff** — Generate proposed updates for each affected page
4. **Flag** — If new data contradicts an existing rule or claim, flag it
5. **Output** — Print all diffs for human review (no auto-commit)

### What triggers updates:
- New CD post from a tracked team → TEAM_DATABASE, OPEN_ALLIANCE_TRACKER, possibly 254_CROSS_SEASON_ANALYSIS
- New EPA data → STATBOTICS_EPA_2026, COMPETITIVE_BENCHMARKS, REBUILT_VALIDATION
- New game manual → KICKOFF_TEMPLATE, CROSS_SEASON_PATTERNS (new predictions)
- New team binder/CAD release → TEAM_DATABASE, relevant MULTI_TEAM_ANALYSIS sections
- Rule contradiction discovered → CROSS_SEASON_PATTERNS (flag for review)
