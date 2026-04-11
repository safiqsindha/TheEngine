# design-intelligence/ — Document Index

Entry point for all design, prediction, and operational docs.
**Start here** when onboarding a new agent or planning a session.

*Last updated: 2026-04-11. 53 docs across 4 buckets + 2 subfolders.*
*Test suite: **936 tests** in tests/ (503 scout + 64 antenna + 371 blueprint + 2 skip + 4 xfail). Oracle + assembly_composer suites added 2026-04-11.*

---

## System of Record (SOR)

Actively referenced by code or other SOR docs. Do not modify without operator review.

| File | One-line description |
|---|---|
| `CROSS_SEASON_PATTERNS.md` | **THE BRAIN** — 18 FRC prediction rules + 12 meta-rules. Core of everything. |
| `COMPETITIVE_BENCHMARKS.md` | EPA targets by competition level (district / regional / championship) |
| `ELEVATOR_DESIGN_SPEC.md` | Elevator arm spec from 254's championship architecture (Blueprint upstream) |
| `ENGINE_MASTER_ROADMAP.md` | Full system roadmap with phases and timeline |
| `KICKOFF_TEMPLATE.md` | Reusable game-analysis template run at every kickoff |
| `LIVE_SCOUT_ARCHITECTURE.md` | Architecture doc for the Scout + EYE + Antenna scout layer |
| `LIVE_SCOUT_PHASE1_BUILD.md` | Phase 1 build spec — referenced by workers/mode_a.py, hls_pull.py |
| `REGIONAL_RUNBOOK.md` | Day-by-day playbook for operating at a regional (Friday–Sunday) |
| `STUDENT_ONBOARDING_GUIDE.md` | Student onboarding doc — links to all training modules |
| `V0a_MODEL_SELECTION.md` | Vision model selection decision record (referenced by eye/vision_yolo.py) |
| `V0b_GPU_SELECTION.md` | GPU SKU selection for Azure vision worker |
| `WIKI_INDEX.md` | Karpathy LLM wiki index — auto-updated incremental design notes |

---

## Validation & Analysis

Data-backed validation of predictions and system performance.

| File | One-line description |
|---|---|
| `254_CROSS_SEASON_ANALYSIS.md` | Cross-season analysis of FRC Team 254's design patterns |
| `MULTI_TEAM_ANALYSIS.md` | Multi-team EPA and design pattern analysis |
| `OPEN_ALLIANCE_TRACKER.md` | Open Alliance team tracking and cross-pollination notes |
| `PREDICTION_ENGINE_2026_SEASON_VALIDATION.md` | 2026 TX season: A1 wins 92%, EPA alignment, txfor upset dissected |
| `PREDICTION_ENGINE_VALIDATION_14GAME.md` | 18-rule validation across 14 games (2012–2026): 98% accuracy |
| `REBUILT_VALIDATION.md` | 2026 REBUILT game-specific rule validation |
| `STATBOTICS_EPA_2026.md` | Statbotics EPA data analysis for the 2026 season |
| `SUBSYSTEM_LEVERAGE_AUDIT.md` | Audit of AdvantageScope / digital-twin leverage vs custom build |
| `TEAM_DATABASE.md` | Team database with EPA, mechanism tags, alliance history |
| `TOOLS_AUDIT_2026-04-11.md` | tools/ script audit: active vs stale, recommended actions |

---

## Active Specs & Plans

In-progress or forward-looking specs. Some may be partially complete.

| File | One-line description |
|---|---|
| `LIVE_SCOUT_PHASE2_REMAINING.md` | Remaining T2/T3 live scout work items (T2-V5 resolved 2026-04-11) |
| `PURCHASE_LIST.md` | Off-season purchase decisions gated on first off-season scrimmage / 2027 prep milestones |
| `ROADMAP_2028.md` | 2028 off-season vision data engine (Gemma + SAM3.1) |
| `SIMULATION_EXERCISES.md` | Maple Sim training exercises for students |
| `VISION_2027_TRAINING_PLAN.md` | 2027 vision model training pipeline plan |
| `VISION_PLAN_EVAL.md` | Holistic vision plan evaluation: model tiers, compute, dataset |
| `YOLO_TRAINING_GUIDE.md` | Step-by-step YOLO model training guide for custom FRC datasets |

---

## Architecture Specs (ARCH_*)

One file per potential subsystem. Some built, some planned, some archived.

| File | Status | One-line description |
|---|---|---|
| `ARCH_AI_MATCH_ANALYSIS.md` | Spec | AI-powered post-match analysis pipeline |
| `ARCH_BUILD_MANAGEMENT.md` | Spec | Build management and milestone tracking system |
| `ARCH_CAD_PIPELINE.md` | **Built** | CAD pipeline spec — implemented as `blueprint/` |
| `ARCH_CD_WATCHER.md` | **Built** | Chief Delphi watcher — implemented as `antenna/` |
| `ARCH_COACH_AI.md` | Spec | In-match AI coaching assistant (Whisper) |
| `ARCH_DRIVER_STATION.md` | Spec | Driver station cockpit hardware and software spec |
| `ARCH_ELECTRICAL_SYSTEMS.md` | Spec | Electrical system standards and PDH slot allocation |
| `ARCH_PARTS_INVENTORY.md` | Spec | COTS parts inventory and BOM management |
| `ARCH_PIT_SYSTEMS.md` | Spec | Pit organization, tools, and workflow |
| `ARCH_SCOUTING_SYSTEM.md` | **Built** | Scouting system spec — implemented as `scout/` + `eye/` |
| `ARCH_SYSTEMCORE_MIGRATION.md` | Spec | Migration plan from FRC robot libs to SystemCore |

---

## Training Modules

Student training curriculum — 6 modules mapped to The Engine subsystems.

| File | One-line description |
|---|---|
| `TRAINING_MODULE_1_PATTERN_RULES.md` | Module 1 — Reading and applying the 18 prediction rules |
| `TRAINING_MODULE_2_PREDICTION_ENGINE.md` | Module 2 — Running the prediction engine on a new game |
| `TRAINING_MODULE_3_DESIGN_INTELLIGENCE.md` | Module 3 — Using design-intelligence/ docs in a design review |
| `TRAINING_MODULE_4_PATHFINDING.md` | Module 4 — Pathfinding and navgrid for autonomous |
| `TRAINING_MODULE_5_VISION_YOLO.md` | Module 5 — Training and deploying a YOLO vision model |
| `TRAINING_MODULE_6_SIMULATION_TESTING.md` | Module 6 — Maple Sim testing and AdvantageScope replay |

---

## Session Snapshots

Dated session summaries and one-shot planning docs. Preserved for audit trail.

| File | Date | What happened |
|---|---|---|
| `CLEANUP_PLAN_2026-04-11.md` | 2026-04-11 | This cleanup session's execution plan |
| `PLAN_ORACLE_TEST_SUITE.md` | 2026-04-11 | Plan for oracle.py test suite (executed: 78 tests added) |
| `PLAN_ASSEMBLY_COMPOSER_TEST_SUITE.md` | 2026-04-11 | Plan for assembly_composer.py test suite (executed: 62 tests, 3 xfail AABB bug surfaced) |
| `COFFEE_SHOP_TASKS.md` | 2026-04 | Coffee shop session task breakdown |
| `GATE_2_HANDOFF.md` | 2026-04 | Gate 2 design handoff milestone document |
| `SESSION_2026-04-11_EVENING_SUMMARY.md` | 2026-04-11 | Evening session: !status, --force, 2026 validation |
| `SESSION_2026-04-11_SUMMARY.md` | 2026-04-11 | Morning/afternoon session: Live Scout command layer |

---

## Subfolders

| Folder | Contents |
|---|---|
| `_archived/` | 3 archived architecture specs (ARCH_F13, ARCH_F18, ARCH_F21) |
| `cockpit/` | Driver console specs: controller mapping, dashboard layout, hardware standard |
| `pit-crew/` | Robot report template used between matches at competition |
