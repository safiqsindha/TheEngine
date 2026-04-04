# THE ENGINE — Complete Phase & Block Reference (Reconciled)
## Verified April 3, 2026 — 52 production files, 27 test files, 246 tests, 3 architecture docs

**Legend:** ✅ Done | ⏳ Needs hardware | 🔧 Partial | ⬜ Not started

## Verified Numbers
| Metric | Count |
|--------|-------|
| Production Java files | 52 |
| Test files | 27 |
| Tests passing | 246 |
| Python tools + ONNX model | 9 |
| Documentation files | 26 |
| Build quality gates | 4 (Spotless, SpotBugs, JaCoCo, JUnit) |

---

## Phase 0: Merge & Refactor ✅ COMPLETE (6/6)
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 0.1 | Clone & analyze team repo | Claude Code | Sonnet | ✅ Done | All 22 student files present |
| 0.2 | Rename classes to Java conventions | Claude Code | Sonnet | ✅ Done | Climber.java, SwerveSubsystem.java, SideClaw.java |
| 0.3 | AdvantageKit vendordep + logging | Claude Code | Sonnet | ✅ Done | LoggedRobot, Logger.recordOutput throughout |
| 0.4 | Spotless + SpotBugs + JaCoCo | Claude Code | Sonnet | ✅ Done | build.gradle enforces all 4 gates |
| 0.5 | LEDs, AllianceFlip, hardware_config | Claude Code | Sonnet | ✅ Done | LEDs.java, AllianceFlip.java, hardware_config.ini |
| 0.6 | ARCHITECTURE.md, PROGRESS.md, build passes | Claude Code | Sonnet | ✅ Done | Both docs exist, BUILD SUCCESSFUL |

## Phase 1: Simulation & Testing ✅ COMPLETE (5/5)
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 1.1 | DriveIOSim with team gear ratios | Claude Code | Sonnet | ✅ Done | maple-sim 0.4.0-beta + YAGSL SwerveDriveSimulation |
| 1.2 | Choreo vendordep + ChoreoAutoCommand | Claude Code | Sonnet | ✅ Done | ChoreoAutoCommand.java (4 routines) |
| 1.3 | Test skeleton files (47+ methods) | Claude Code | Sonnet | ✅ Done | 27 test files, 246 tests |
| 1.4 | FlywheelIOSim | Claude Code | Sonnet | ✅ Done | SPARK MAX sim layer |
| 1.5 | Visual sim verification | Claude Code | Opus | ✅ Done | 6 practice scenarios |

## Phase 2: Perception & State Machine ✅ COMPLETE (5/5)
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 2.1 | VisionSubsystem with MegaTag2 | Claude Code | Sonnet | ✅ Done | 5-layer validation, std-dev tuning |
| 2.2 | Dual pipeline switching + vision-gated | Claude Code | Sonnet | ✅ Done | setAprilTagPipeline(), setNeuralPipeline() |
| 2.3 | SuperstructureStateMachine | Claude Code | Sonnet | ✅ Done | 5 states, logged transitions |
| 2.4 | AutoScoreCommand | Claude Code | Sonnet | ✅ Done | Vision-gated, 5s timeout, error LED |
| 2.5 | Branching autonomous chooser | Claude Code | Sonnet | ✅ Done | 7 options including Safe Mode |

## Phase 3: Autonomous Intelligence ✅ COMPLETE (10/11, 1 needs hardware)
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 3.1 | Evaluate Repulsor library | Claude Code | **Opus** | ✅ Done | Decision: custom A* + potential fields |
| 3.2 | NavigationGrid (164x82) | Claude Code | Sonnet | ✅ Done | + 8 tests |
| 3.3 | AStarPathfinder | Claude Code | Sonnet | ✅ Done | + 7 tests |
| 3.4 | PathfindToGoalCommand | Claude Code | Sonnet | ✅ Done | PPLib AD* integration |
| 3.5 | AutonomousStrategy + Bot Aborter | Claude Code | **Opus** | ✅ Done | + 8 tests |
| 3.6 | FullAutonomousCommand | Claude Code | **Opus** | ✅ Done | Evaluate-pathfind-execute loop |
| 3.7 | FuelDetectionConsumer | Claude Code | Sonnet | ✅ Done | + 9 tests |
| 3.8 | Wire fuel into strategy | Claude Code | Sonnet | ✅ Done | fuelSupplier + opponentSupplier |
| 3.9 | DynamicAvoidanceLayer | Claude Code | Sonnet | ✅ Done | + 7 tests |
| 3.10 | Integration + Bot Aborter wiring | Claude Code | **Opus** | ✅ Done | All wired |
| 3.11 | Tuning via AdvantageScope | Claude Code | **Opus** | ⏳ Hardware | Gains set, needs real validation |

## Phase 4: Competition Readiness ✅ COMPLETE (7/7)
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 4.1 | AutoAlignCommand (right bumper) | Claude Code | Sonnet | ✅ Done | Wired in RobotContainer |
| 4.2 | DriveToGamePieceCommand (left bumper) | Claude Code | Sonnet | ✅ Done | Wired in RobotContainer |
| 4.3 | Validate analysis scripts | Claude Code | Sonnet | ✅ Done | All 3 scripts working |
| 4.4 | Test coverage 80% gate | Claude Code | Sonnet | ✅ Done | frc.lib at 98% |
| 4.5 | Driver practice sim mode | Claude Code | Sonnet | ✅ Done | 6 scenarios, SmartDashboard chooser |
| 4.6 | Final polish & handoff | Claude Code | Sonnet | ✅ Done | All docs, BUILD SUCCESSFUL |
| 4.7 | Pit crew diagnostic (10-step actuating) | Claude Code | Sonnet | ✅ Done | PitCrewDiagnosticCommand.java — 10 steps, actuates all mechanisms, LED feedback |

## Phase 5*: Competition Hardening ✅ MOSTLY COMPLETE (5/8)
*Claude Code bonus phase*
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 5*.1 | Sim controller validation | Claude Code | Sonnet | ⏳ Controller | Needs Switch 2 Pro |
| 5*.2 | EncoderCalibrationCommand | Claude Code | Sonnet | ⏳ Hardware | Code exists, needs robot |
| 5*.3 | Match phase logging | Claude Code | Sonnet | ✅ Done | MatchPhase enum, logPhaseTransition() |
| 5*.4 | Edge case hardening | Claude Code | Sonnet | ✅ Done | Null guards everywhere |
| 5*.5 | Pre-match health check | Claude Code | Sonnet | ✅ Done | pre_match_check.py PASS/WARN/FAIL |
| 5*.6 | Trajectory scaffolding | Claude Code | Sonnet | ⏳ Hardware | Needs Choreo GUI for .traj files |
| 5*.7 | Autonomous tuning | Claude Code | Sonnet | ⏳ Hardware | Needs real match logs |
| 5*.8 | YOLO pipeline deployment | Claude Code | Sonnet | ✅ Done | Wave YOLOv11n ONNX + snapscript |

## Phase 6*: Reliability & Match Intelligence ✅ COMPLETE (6/6)
*Claude Code bonus phase — 26 new tests*
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 6*.1 | Autonomous Fallback Chain | Claude Code | **Opus** | ✅ Done | FULL_AUTO → SAFE_MODE → STOPPED |
| 6*.2 | Subsystem Self-Test | Claude Code | **Opus** | ✅ Done | Swerve, gyro, vision checks |
| 6*.3 | Odometry Divergence Detector | Claude Code | **Opus** | ✅ Done | + 6 tests |
| 6*.4 | Stall Detection | Claude Code | **Opus** | ✅ Done | + 6 tests |
| 6*.5 | Cycle Timer & Scoring Tracker | Claude Code | **Opus** | ✅ Done | + 8 tests |
| 6*.6 | Moving Shot Compensation | Claude Code | **Opus** | ✅ Done | + 6 tests |

## Phase 7*: Driver Experience ✅ COMPLETE (4/4)
*Claude Code bonus phase — 15 new tests*
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 7*.1 | Controller Rumble Feedback | Claude Code | **Opus** | ✅ Done | 6 patterns + 6 tests |
| 7*.2 | Speed Mode Toggle | Claude Code | **Opus** | ✅ Done | FULL/PRECISION + 4 tests |
| 7*.3 | One-Button Score Command | Claude Code | **Opus** | ✅ Done | 6-phase, 6s timeout |
| 7*.4 | Dashboard Path Visualizer | Claude Code | **Opus** | ✅ Done | 6 AScope channels + 5 tests |

## Phase 8*: Testing Depth ✅ COMPLETE (3/3)
*Claude Code bonus phase — 23 new tests*
| Block | Task | Tool | Model | Status | Evidence |
|-------|------|------|-------|--------|----------|
| 8*.1 | Autonomous Integration Tests | Claude Code | **Opus** | ✅ Done | 10 scenarios |
| 8*.2 | Fault Injection Tests | Claude Code | **Opus** | ✅ Done | 10 adversarial inputs |
| 8*.3 | CAN ID Conflict Regression | Claude Code | **Opus** | ✅ Done | 3 tests (parses Constants.java as text) |

---

## FUTURE: Design Intelligence (Oct-Dec 2026)
| Block | Task | Tool | Model | Status |
|-------|------|------|-------|--------|
| F.1 | Remaining 254 binders (2018, 2020, 2023) | Chat | Opus | ⬜ |
| F.2 | 1678 strategy documents | Chat | Opus | ⬜ |
| F.3 | 1323 MadTown 2025 tech binder (World Champions) | Chat | Opus | ⬜ |
| F.4 | 6328 build thread highlights | Chat | Opus | ⬜ |
| F.5 | Statbotics EPA data pull | You + Chat | Opus | ⬜ |
| F.6 | CROSS_SEASON_PATTERNS.md (15-20 rules) | Chat | Opus | ⬜ |
| F.7 | Validate prediction engine against REBUILT | Chat | Opus | ⬜ |
| F.8 | 6 student training modules | Claude Code | **Opus** | ✅ 6/6 done (Patterns, Prediction Engine, Design Intelligence, Pathfinding, Vision/YOLO, Sim & Testing) |
| F.9 | Simulation exercises per module | Claude Code | **Opus** | ✅ 6 exercise sets with answer keys, scoring system, badges |
| F.10 | Student onboarding guide | Claude Code | **Opus** | ✅ 7-step guide: setup → sim → first change → training path → glossary |

## FUTURE: 2028 Advanced Features (Summer 2027)
| Block | Task | Tool | Model | Status |
|-------|------|------|-------|--------|
| F.11 | Jetson Orin Nano setup + NT bridge | Team + Code | Sonnet | ⬜ |
| F.12 | LLM evaluation + quantization | Code + you | **Opus** | ⬜ |
| F.13 | Pre-match strategist | Chat + Code | **Opus** | ✅ Architecture doc (ARCH_F13_PREMATCH_STRATEGIST.md) |
| F.14 | Post-match analyzer | Claude Code | **Opus** | ✅ Unified debrief script (tools/post_match_analyzer.py) |
| F.15 | Mid-match strategic layer | Claude Code | **Opus** | ⬜ |
| F.16 | CAD to maple-sim validation | Students + Code | Sonnet | ⬜ |
| F.17 | CI pipeline (sim on push) | Claude Code | **Opus** | ✅ .github/workflows/build.yml — all 4 gates |
| F.18 | Alliance UDP protocol | Claude Code | **Opus** | ✅ Architecture doc (ARCH_F18_ALLIANCE_UDP.md) — build at Worlds |
| F.19 | Decision engine alliance integration | Claude Code | Sonnet | ⬜ |
| F.20 | Publish protocol on Chief Delphi | Chat + students | Opus | ⬜ |
| F.21 | Scouting data pipeline | Claude Code | **Opus** | ✅ Architecture doc (ARCH_F21_SCOUTING_PIPELINE.md) |
| F.22 | LLM opponent pattern extraction | Chat + Code | **Opus** | ⬜ |
| F.23 | Counter-strategy generation | Claude Code | **Opus** | ⬜ |
| F.24 | Performance tracker (cross-event) | Claude Code | Sonnet | ⬜ |
| F.25 | LLM weight self-tuning | Chat + Code | **Opus** | ⬜ |
| F.26 | Chief Delphi Watcher (weekly digest) | Claude Code | Sonnet | ⬜ |

## FUTURE: Modular Robot Library (Summer 2027)
| Block | Task | Tool | Model | Status |
|-------|------|------|-------|--------|
| F.27 | Drivetrain module (The Engine swerve) | N/A | N/A | ✅ Done |
| F.28-F.29 | Intake frame + 3 roller sets | Team (fab) | N/A | ⬜ |
| F.30 | IntakeSubsystem.java | Claude Code | Sonnet | ⬜ |
| F.31 | Conveyor build | Team (fab) | N/A | ⬜ |
| F.32 | IndexerSubsystem.java | Claude Code | Sonnet | ⬜ |
| F.33 | Elevator build | Team (fab) | N/A | ⬜ |
| F.34 | ElevatorSubsystem.java | Claude Code | Sonnet | ⬜ |
| F.35 | Wrist pivot + 2 jaw sets | Team (fab) | N/A | ⬜ |
| F.36 | WristSubsystem.java | Claude Code | Sonnet | ⬜ |
| F.37 | Turret build | Team (fab) | N/A | ⬜ |
| F.38 | TurretSubsystem.java | Claude Code | **Opus** | ⬜ |
| F.39 | FlywheelSubsystem.java refactor | Claude Code | Sonnet | ⬜ |
| F.40-F.42 | Climber hardware (turntable, arm, hooks) | Team (fab) | N/A | ⬜ |
| F.43 | ClimberSubsystem.java | Claude Code | **Opus** | ⬜ |

---

## Grand Totals

| Phase | Source | Blocks | ✅ | ⏳ | 🔧 | ⬜ |
|-------|--------|--------|-----|-----|-----|-----|
| Phase 0 | Chat plan | 6 | 6 | 0 | 0 | 0 |
| Phase 1 | Chat plan | 5 | 5 | 0 | 0 | 0 |
| Phase 2 | Chat plan | 5 | 5 | 0 | 0 | 0 |
| Phase 3 | Chat plan | 11 | 10 | 1 | 0 | 0 |
| Phase 4 | Chat plan | 7 | 7 | 0 | 0 | 0 |
| Phase 5* | Code bonus | 8 | 5 | 3 | 0 | 0 |
| Phase 6* | Code bonus | 6 | 6 | 0 | 0 | 0 |
| Phase 7* | Code bonus | 4 | 4 | 0 | 0 | 0 |
| Phase 8* | Code bonus | 3 | 3 | 0 | 0 | 0 |
| Design Intel | Future | 10 | 3 | 0 | 0 | 7 |
| 2028 Features | Future | 16 | 4 | 0 | 0 | 12 |
| Modular Library | Future | 17 | 1 | 0 | 0 | 16 |
| **TOTAL** | | **98** | **59** | **4** | **0** | **35** |

### Progress: 60% complete (59/98 done, 4 hardware-pending, 35 future)

## What's Left by Category
| Category | Blocks | When |
|----------|--------|------|
| Hardware-only (encoder, CAN, Choreo, tuning) | 4 | Next robot access |
| Design Intelligence (remaining: binders, data, patterns) | 7 | Oct-Dec 2026 |
| 2028 Features | 12 | Summer 2027 |
| Modular Library | 16 | Summer 2027 |
| **Total remaining** | **39** | |

## Calendar View
| Period | Status |
|--------|--------|
| Week 1: Phase 0-2 | ✅ DONE |
| Week 2: Phase 3 | ✅ DONE |
| Week 2-3: Phase 4 | ✅ DONE |
| Week 3: Phase 5*-8* (Code bonus) | ✅ DONE |
| Week 3: F.8-F.10 (Training modules + onboarding) | ✅ DONE |
| Week 3: F.13,F.14,F.17,F.18,F.21 (Arch docs + CI + analyzer) | ✅ DONE |
| **NOW: Hardware tasks + team demo** | **← YOU ARE HERE** |
| Week after competition: DEMO TO TEAM | ⬜ |
| May-Sep: Competition season | ⬜ |
| Oct-Dec: Design Intelligence (F.1-F.7 remaining) | ⬜ |
| Summer 2027: 2028 Features + Modular Library | ⬜ |
| Jan 2028: Kickoff | ⬜ |
