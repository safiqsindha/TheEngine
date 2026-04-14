# Engine Full Audit — 2026-04-13
## Author: Engine audit session | Status: DECISION-READY

Off-season. Season is over for 2950. No events until January 2027 kickoff.
This audit answers one question: **what does a solo mentor actually use in the next
9 months, and what is dead weight?**

Bias: toward cutting. "Interesting intellectually" is not a deliverable.

---

## The 10 Systems — Honest Status Table

| # | System | Status | What's Actually Built | What It Delivers Off-Season | Recommendation |
|---|--------|--------|----------------------|----------------------------|----------------|
| **1** | **The Blueprint** (CAD Pipeline) | **DEAD-WEIGHT** | 12,713 LOC Python. `oracle.py` (823 LOC, 78 tests, 98% accuracy) is real. The generators (7,000+ LOC) produce 9 floating tubes. 0 gussets, 0 COTS modules, 0 buildable output. MCP pivot landed 4 phases before the COTS resolver and mates were built. | Oracle: game analysis on kickoff day. Generators: nothing. Students still CAD by hand. | **DOWNSCOPE** — keep oracle + physics, cut generators entirely. Reframe as design analysis + BOM estimator. |
| **2** | **The Antenna** (CD Watcher) | **SHIPPED** | 4,374 LOC, 64 tests. Scraper, scorer, digest, Discord webhook, SQLite store. Weekly digests posting live. AN.1–AN.6 fully implemented. | Compounding intelligence: every week through kickoff adds CD thread signal. 9 months of data by January 2027. Already running. | **KEEP** — zero additional work needed. Let it run. |
| **3** | **The Cockpit** (Driver Station) | **PLANNED** | 3 markdown specs in `design-intelligence/cockpit/`. 0 LOC of code. Controller mapping, dashboard layout, hardware standard — spec only. | Nothing until someone builds it. Elastic Dashboard (144 stars, FRC-specific) already exists and replaces 80% of the D.2 scope. | **DOWNSCOPE** — adopt Elastic Dashboard for D.2 (~2h config vs 19h build). Write D.1 final controller map (1 doc, no code). Skip D.4–D.5 (driver analytics, coach info system) until 2027 build season. |
| **4** | **The Scout** (Scouting System) | **SHIPPED** | 6,152 LOC, 450 tests. `alliance_advisor.py`, `pre_event_report.py`, `stand_scout.py`, `backtester.py`, `pick_board.py`, `the_scout.py`, 12 Discord commands via `live_scout_commands.py`. Monte Carlo sim, anomaly detection, TBA + Statbotics clients. | Pre-event reports. Alliance selection advisor. Live match tracking at competitions. Real competitive value. | **KEEP** — add 1678 algorithm ports (SPR, NormalDist, defense-adjusted EPA) in off-season. ~30h of targeted work. |
| **5** | **On-Robot Coprocessor** (Jetson + Whisper + Eye on-robot + logger + P.5) | **NOT STARTED** | Hardware not ordered. 0 LOC. Roadmap says order Jetson Orin Nano Super ($249) in July, bring up in August–September. CP.1–CP.14 are all spec. | Nothing until July at earliest. PhotonVision (406 stars) eliminates CP.1–CP.8 (pose estimation, camera bring-up) entirely. 254's AOS is the production reference. | **DEFER-TO-2027** — order hardware in July as planned, but reduce scope to: PhotonVision install + Whisper bridge only. Cut custom vision pipeline (CP.7–CP.12). ~20h of real work, not 66h. |
| **6** | **The Eye** (Offseason Video Pipeline) | **PARTIAL** | 3,966 LOC in `eye/`. `the_eye.py`, `hls_pull.py`, `match_boundary.py`, `overlay_ocr.py`, `stream_recorder.py`, `vision_yolo.py`, `eye_bridge.py`. Architecture is sound. E.1 (offseason batch POC) listed for August. | Offseason: validate video → YOLO pipeline against FIT DCMP footage (FIT DCMP is 4/15–4/18). Real data available now. Roboflow supervision (38K stars) replaces custom detection pipeline and saves ~5h. | **KEEP** — but scope to E.1 only (offseason batch POC, ~17h post-Roboflow savings). Don't build E.3–E.4 (Scout integration, dashboard) until Scout delivers E.1 data. |
| **7** | **The Pit Crew** (Pit Operations) | **PLANNED** | 1 markdown template (`ROBOT_REPORT_TEMPLATE.md`). 0 LOC of code. P.1–P.6 are all spec. PitFUSION (4 stars but FRC-specific) exists for P.1–P.4. | Nothing. P.1 (Robot Reports Discord channel) takes 10 minutes and no code — it was a Quick Win in the roadmap from April, still not done. | **DOWNSCOPE** — do P.1 (10 min, no code). Adopt PitFUSION + Foxglove for P.2–P.4 rather than building. P.6 (digital twin) is aspirational; defer. ~5h total instead of 44h. |
| **8** | **The Vault** (Parts Inventory) | **NOT STARTED** | 0 LOC. No shop audit. No Google Sheet. Binner (514 stars) is a self-hosted Docker app that replaces the planned custom inventory with barcode scanning, BOM cross-ref, and supplier lookup. | Nothing until someone installs Binner. The shop audit (12h walking and counting parts) is the real work here — the software is free. | **DOWNSCOPE** — adopt Binner ($0, ~2h config). Do the shop audit (12h human time) in September or October before build season. No custom code needed. |
| **9** | **The Grid** (Electrical + CAN-FD) | **NOT STARTED** | 0 LOC. Spec in `ARCH_ELECTRICAL_SYSTEMS.md`. No harnesses built. 254 AOS `frc/can_logger/` is the reference architecture. | Nothing until someone builds harnesses. The wiring standards card (`generate_grid_cards_v2.py`) is already runnable — that's the near-term output. | **DEFER-TO-2027** — harness builds need shop time with students in fall 2026. Put on the September calendar, don't touch in off-season coding sessions. |
| **10** | **The Clock** (Build Management) | **NOT STARTED** | 0 LOC. Spec in `ARCH_BUILD_MANAGEMENT.md`. GitHub MCP (28.8K stars) + Google Workspace MCP (2.1K stars) replace CL.1–CL.2 (task generator + standup bot) entirely. | Nothing. A standup bot is nice but not a solo-mentor priority when there are no students in the room. | **DEFER-TO-2027** — adopt GitHub MCP when build season starts and there are students to coordinate. Off-season coding sessions don't need a standup bot. |

---

## Cut List

### CUT NOW (Blueprint CAD generators)

**Blueprint generators + MCP infrastructure**
- `blueprint/generators/elevator_rev2.py` (1,005 LOC)
- `blueprint/generators/swerve_rev2.py` (900 LOC)
- `blueprint/cots_parts/elevator_parts.py` (272 LOC)
- `blueprint/cots_parts/swerve_parts.py` (202 LOC)
- `blueprint/build_full_robot.py` (171 LOC)
- `blueprint/demo_full_pipeline.py` (524 LOC)
- `blueprint/cad_builder.py` (~700 LOC — FeatureScript string builder)
- `blueprint/assembly_builder.py` (~724 LOC — hand-rolled assembly creation)
- `blueprint/part_resolver.py` (441 LOC — hardcoded part IDs, never resolved)
- `blueprint/fix_featurescript.py` (~100 LOC)
- `blueprint/apply_feature.py` (~80 LOC)
- `~/onshape-mcp/` install (external, no longer needed)
- `tests/blueprint/test_elevator_rev2_gated.py` (122 LOC)
- `tests/blueprint/test_elevator_rev2_hermetic.py` (260 LOC)
- `tests/blueprint/test_swerve_rev2_gated.py` (110 LOC)
- `tests/blueprint/test_swerve_rev2_hermetic.py` (302 LOC)
- `tests/blueprint/test_b3_generators.py` (646 LOC)
- `tests/blueprint/test_b4_b9_generators.py` (516 LOC)

**Savings: ~7,075 LOC deleted. Recovers ~200–400h of downstream work that was never going to produce buildable CAD.**

**Blueprint legacy generators (separate pass)**
The pre-MCP-pivot generators (`arm_generator.py`, `climber_generator.py`,
`conveyor_generator.py`, `elevator_generator.py`, `flywheel_generator.py`,
`frame_generator.py`, `intake_generator.py`) total ~4,897 LOC with 0 tests.
They emit FeatureScript text and were never integrated into the MCP pipeline.
Recommend: archive to `blueprint/_generators_legacy/` in one commit.
Additional ~4,897 LOC removed from active paths.

### CUT OR DEFER: Projects at Blueprint-level risk

**CodeScout (10h estimate)**
Spec only, no code. The landscape scan summary says "~11% of FRC teams have public
repos. Elite teams publish post-season only." For a solo mentor in off-season, this
is low ROI: scraping GitHub for auto paths works against mid-tier teams who post
after regionals, not against the teams you actually face at state. Defer to 2027
build season if alliance selection intelligence becomes a priority.
**Verdict: DEFER-TO-2027**

**CAD Geometry Tier 1 + Tier 2 (30h total, from Rev-4 additions)**
This is the "train a classifier on 253 Einstein robot CADs" concept. Zero code,
zero data collected. It requires pulling 200+ Onshape documents and running ML
classification. It is Blueprint-level ambitious and Blueprint-level speculative.
External tools (FRCDesignLib, 254 AOS mechanism library) already catalog this.
**Verdict: CUT — not tractable solo, not needed for 2027 kickoff**

**On-Robot Coprocessor CP.7–CP.14 (custom vision + YOLO training + logger + P.5)**
PhotonVision eliminates the entire pose estimation stack. The custom YOLO training
(CP.8, 10h) requires labeled FRC game piece data that doesn't exist for 2027's
game until kickoff day. Building it now trains on the wrong game. The AdvantageKit
NVMe logger (CP.10) and Pit Crew P.5 debug dashboard (CP.11) are real values but
they require the robot to be built first.
**Verdict: DEFER-TO-2027 — after kickoff, after game piece data exists**

**The Clock (CL.1–CL.3, 30h)**
No students in the room during off-season. A standup bot for one person is theater.
GitHub MCP handles milestone tracking if you need it. Build this in December 2026
at the earliest, when the 2027 build season is 4 weeks away and students need task
coordination.
**Verdict: DEFER-TO-2027**

**Eye E.3–E.4 (Scout integration + dashboard visualization, 30h)**
E.1 (offseason batch POC) hasn't run yet. Don't build the integration layer before
the first layer produces data. E.3–E.4 are downstream of real E.1 output.
**Verdict: DEFER — do E.1 first, re-evaluate in September**

**Pit Crew P.2–P.6 (40h)**
No robot to diagnose in off-season. P.2 (pre-match checklist), P.3 (post-match
diagnostics), and P.4 (wear tracking) all require match logs from a live competition.
P.6 (digital twin) requires AdvantageKit logs from the Jetson, which isn't built.
PitFUSION (4 stars but purpose-built) covers P.1–P.4 without custom code.
**Verdict: ADOPT PitFUSION for P.1–P.4, DEFER P.5–P.6 to build season**

**ARCH_SYSTEMCORE_MIGRATION.md**
Spec only, 0 code. Describes migrating from standard FRC robot libraries to NI
SystemCore. SystemCore is still new hardware, 2950 hasn't purchased it, and the
migration can't start until the 2027 robot design is locked. Pure speculation at
this stage.
**Verdict: DEFER — archive spec until SystemCore purchase decision is made**

### ADOPT INSTEAD OF BUILD (landscape scan findings to act on)

| What | Replace | Effort |
|------|---------|--------|
| Elastic Dashboard | Cockpit D.2 custom dashboard | ~2h config |
| Binner | The Vault custom inventory | ~2h config + 12h shop audit (human) |
| PhotonVision | Coprocessor CP.1–CP.8 (pose estimation) | ~4h setup |
| PitFUSION + Foxglove | Pit Crew P.2–P.4 | ~3h setup |
| roboflow/supervision | Eye custom detection pipeline | Already available as import |

### KEEP — Actively delivering value

| System | Why Keep |
|--------|---------|
| **Antenna** | Running, compounding, 0 maintenance burden. 9 months of CD intelligence by kickoff. |
| **Scout** | 450 tests, real competitive output. Add 1678 ports in off-season (~30h). |
| **Oracle** | 98% accuracy across 14 games. The whole prediction engine brain. |
| **Eye E.1** | FIT DCMP footage exists now. Validate the pipeline against real data. ~17h work. |

---

## Refocused Off-Season Roadmap (April 2026 → January 2027)

Given the cuts, the honest off-season is **4 workstreams + 2 hardware tasks + 1 season artifact.**

### Workstream 1: Scout Intelligence (May–August, ~30h)
The Scout is shipped but shallow. Add the 1678 algorithm ports:
- Scout Precision Rating (SPR) — validate human scouts
- NormalDist win probability — `P(RedWins) = NormalDist.cdf()`, replaces manual threshold
- Defense-adjusted EPA (predictobics) — separate "bad team" from "defended team"
- Alliance stat decomposition — attribute alliance performance to individuals
- Anomaly detection via z-score — flag outlier scouting entries

This is the highest-value off-season coding work. The Scout is already deployed and
these ports have documented source code. Real competitive advantage by 2027.

### Workstream 2: Eye Validation (May–June, ~17h)
FIT DCMP runs 4/15–4/18. Run the Eye pipeline against real footage using Roboflow
supervision as the detection backend. Document what works, what breaks. If E.1 POC
is solid by June, schedule E.3 Scout integration for October.

### Workstream 3: Oracle Phase 1 Data Foundation (June–July, ~11h)
Add EPA uncertainty bands (epa_sd + epa_skew from Statbotics API). Add component EPA
draft complementarity. Replace hardcoded 0.85/0.90 thresholds with Statbotics
norm-EPA-backed confidence. Small, targeted, completely within existing Oracle surface.

### Hardware task: Coprocessor setup (July, ~6h)
Order Jetson Orin Nano Super Dev Kit + NVMe (~$274). Flash JetPack. Install
PhotonVision. Confirm camera bring-up. That is the entire summer hardware task —
no YOLO training until game piece data exists post-kickoff.

### Operations task: Binner + Shop Audit (September, ~14h)
Configure Binner (2h). Walk the shop and enter inventory (12h). This is human time,
not model budget. The output feeds the 2027 BOM cross-reference.

### Workstream 4: Match Brief Generator (Scout Phase 3, October–November, ~12h)
Added 2026-04-13 after 1690 StrategyEngine evaluation. Between-match
strategy briefings, NOT live in-match use. Input: next match number +
current scouting database. Output: 30-second printable brief for the
drive coach — recommended focus, expected pressure points, priority
calls. Builds on Scout Phase 1 (NormalDist) + Phase 2 (defense-adjusted
EPA) + Oracle rules. Monte Carlo of the specific 3v3 matchup with
per-action choices (score vs defense, climb timing, scoring level
preference). ~10-15h build, closer to our existing surface than a full
per-action game sim clone.

**Why here and not earlier:** depends on defense-adjusted EPA (Phase 2,
August). Without it, anomaly and defense pressure can't be priced in
and the brief becomes "raw EPA times probabilities" which is what
we already have.

### Flex task: Game Analysis PDF workflow dry-run (~3h, whenever)
Build the agent-gated workflow before kickoff pressure hits. Pick a past
game (2024 Crescendo suggested — manual already read by team), run the
full G1–G6 gated flow with an agent, produce nothing publishable —
just validate the workflow, catch citation-discipline gaps, tune the
voice pass. Not tied to a month. Trigger when Safiq has a random
3-hour window and feels like building it.

**Why decoupled:** workflow iteration is exploratory; forcing it onto
a calendar slot burns it. Better as flex work done in one focused
session when the mood strikes.

**Output:** `design-intelligence/GAME_ANALYSIS_WORKFLOW.md` with the
gate definitions, prompt templates for G1–G6, and a 1-page retro
from the Crescendo dry-run.

### Season artifact: Game Analysis PDF (January 2027, ~4h human if dry-run done, ~6h if not)
Added 2026-04-13 after 1690 workflow evaluation. 1690's annual ~100-page
Game Analysis PDF is written by humans, not generated by StrategyEngine.
It's the artifact that makes elite teams *look* elite — scoring
economics, archetype analysis, cycle-time decomposition, strategy path
ranking. Published 2–3 weeks post-kickoff.

**2950 version:** 10–15 page PDF. Written by Safiq + senior students in
the first 2 weeks post-kickoff. Oracle + 18 rules do 50% of the work
for you (scoring economics, archetype identification); the rest is
writing. Target: publish on Chief Delphi within 3 weeks of kickoff.
Free credibility leverage — closes a meaningful chunk of the visible
capability gap vs elite teams for 4 hours of writing.

**Why this matters:** the PDF is *the* pre-season signaling artifact.
Recruited mentors, alumni donors, alliance partners all read published
strategy analyses. Shipping one puts 2950 in a ~30-team cohort
(Einstein-level teams + a few others who publish) instead of the
~3000-team cohort that doesn't.

### Total revised off-season: ~94h (~78h + 12h Scout Phase 3 + 4h Game Analysis PDF)

| Month | Focus | Hours |
|-------|-------|-------|
| April | Blueprint postmortem + cuts | ~4h model budget |
| May | Scout 1678 ports (Phase 1) + Eye E.1 setup | ~15h |
| June | Eye E.1 run + Scout SPR/anomaly | ~12h |
| July | Oracle Phase 1 data + Jetson hardware | ~17h |
| August | Scout Phase 2 defense-adjusted EPA | ~10h |
| September | Binner setup + shop audit | ~14h human |
| October | Eye E.3 Scout integration + Match Brief Phase 3a | ~16h |
| November | Match Brief Phase 3b finalize + Cockpit D.1 | ~10h |
| December | Full kickoff simulation dry run (past game) | ~6h |
| **January 2027** | **Kickoff + Game Analysis PDF** | **~4h writing** |

**This is ~9 hrs/week average for April–November, then 3–6h in Dec,
spike to ~10h/week for first 3 weeks of January 2027 kickoff.
Achievable solo. Every hour produces something usable or publishable.**

---

## Blueprint-Level Traps (Systems at Risk)

A "Blueprint-level trap" is: ambitious, speculative, downstream of real capability
we don't have, visible progress metrics (LOC, tests, phase numbers) but no buildable
output.

| System | Trap Indicators | Risk Level |
|--------|----------------|------------|
| **CAD Geometry Tier 1+2** | 253 robot CADs + ML classifier | HIGH — cut |
| **CodeScout** | 11% team repo coverage, post-season only | MEDIUM — defer |
| **Coprocessor CP.7–CP.14** | YOLO training for a game that doesn't exist yet | HIGH — defer |
| **The Clock** | Standup bot for a solo mentor | LOW — just don't build it yet |
| **Pit Crew P.2–P.6** | Requires robot + live matches to be useful | MEDIUM — adopt PitFUSION |
| **VISION_2027_TRAINING_PLAN.md / ROADMAP_2028.md** | Gemma + SAM3.1 for 2028 — 18 months out | LOW (planning docs are fine, just don't start building) |
| **ARCH_SYSTEMCORE_MIGRATION.md** | Hardware not purchased, robot not designed | LOW — archive spec |

None of the other traps are as advanced as Blueprint was (real LOC, real tests,
real API calls) so none will burn as many hours before detection.

---

## Summary

**Top 3 cuts:**
1. **Blueprint generators** — ~7,075 LOC of src + tests. 9 tubes is not a robot.
2. **CAD Geometry Tier 1+2** — 30h of ML work on robots for a game we don't know yet.
3. **Coprocessor CP.7–CP.14** — YOLO training and custom vision pipeline. PhotonVision exists.

**Top 3 keeps:**
1. **Antenna** — running, compounding, zero work needed.
2. **Scout + 1678 ports** — highest competitive ROI in the off-season.
3. **Oracle** — the brain of the whole system. Already validated at 98%.

**Other Blueprint-level traps found:** CodeScout (speculative pre-competition intel
against teams who mostly don't publish repos) and the full Coprocessor vision pipeline
(builds toward a game piece YOLO model for a game that won't be announced until
January 2027). Both have the same pattern as Blueprint: ambitious, tractable-looking,
but downstream of capability we don't have yet.

---

*Audit complete. No files deleted. Companion doc: `BLUEPRINT_REV2_POSTMORTEM.md`.*
*Refocused roadmap above replaces ENGINE_MASTER_ROADMAP.md Tier 2–4 scope.*
