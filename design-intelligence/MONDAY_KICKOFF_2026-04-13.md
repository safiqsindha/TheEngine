# Monday Kickoff — 2026-04-13

**Author:** Opus (written 2026-04-11, Saturday)
**For:** Sonnet + Opus, first session after weekly rate limit reset (Monday 10:00 AM)
**Budget context:** Last week ended at 92% of weekly cap. This week is a full reset.
**Repo state at write-time:** main @ `415308d`, **944 passed / 2 skipped / 3 xfailed**

This is a single-shot kickoff doc. Read it top-to-bottom Monday morning before
touching any code. It exists because we burned last week on test scaffolding
instead of advancing the architecture, and we need this week's first hour to
not repeat that mistake.

---

## Section 1 — Where The Engine actually is (full arch review)

Roadmap target (from `ENGINE_MASTER_ROADMAP.md`): **10 systems, ~471 hours, all
operational by December 2026**. Off-season runs through January 2027 kickoff.

### Status of the 10 systems

| # | System | Roadmap Status | Reality on disk (2026-04-11) |
|---|---|---|---|
| 1 | **The Blueprint** (CAD pipeline) | Tier 1, 120-150h | **Partially built.** `blueprint/` is 80 files. `oracle.py`, `assembly_composer.py`, `plate_generator.py`, `turret_generator.py`, `cad_builder.py` exist. Oracle has 944 tests + 0 known bugs. Assembly composer has 62 tests + 1 known AABB bug (3 xfails). Plate / turret / cad_builder are **untested and unaudited**. `onshape_api.py` exists with working `onshape-client` integration + API keys in `blueprint/.env`. **The hard question is whether any of this should survive the MCP pivot — see Section 2.** |
| 2 | **The Antenna** (CD watcher) | Tier 1, 32h | **DONE.** 64 tests. Live in production. `antenna/` is 14 files. Posts weekly digests, scrapes CD threads, scores them. Compounding intelligence as designed. |
| 3 | **The Cockpit** (driver station) | Tier 1, 39h | **Spec only.** `design-intelligence/cockpit/` has the 3 reference docs (controller mapping, dashboard layout, hardware standard). No code. Scheduled May-June. |
| 4 | **The Scout** (scouting system) | Tier 2, 54h | **DONE.** 503 tests. `scout/` is the full system: pre-event reports, anomaly detection, stand scouting, alliance advisor, Monte Carlo sim, Synthesis worker. 12 Discord commands wired through `live_scout_commands.py`. |
| 5 | **On-Robot Coprocessor** (Jetson + Whisper + Eye on-robot + logger + P.5) | Tier 2, 66.5h | **Not started.** Hardware not ordered. Roadmap says order in July, bring up August-September. |
| 6 | **The Eye** (offseason batch + S.6 integration) | Tier 2, ~30h | **Partially built.** `eye/` exists (vision_yolo.py + bridge to scout). E.1 (offseason batch POC) listed for August-September. Currently structured around YOLOv8. |
| 7 | **The Pit Crew** (P.1-P.4, P.6) | Tier 3, ~44h | **Spec only.** `design-intelligence/pit-crew/` has the robot report template. No P.1 channel, no P.2-P.4 software. |
| 8 | **The Vault** (parts inventory) | Tier 3, 12h | **Not started.** No code, no shop audit. |
| 9 | **The Grid** (electrical + CAN-FD topology) | Tier 3, 18h | **Not started.** Spec in `ARCH_ELECTRICAL_SYSTEMS.md`. No harnesses, no CAN-FD map. |
| 10 | **The Clock** (build management) | Tier 3, 30h | **Not started.** Spec in `ARCH_BUILD_MANAGEMENT.md`. No code. |

### What the calendar says about April

> APRIL 2026 — TARGET: 38 hours
> - Blueprint B.1: API + COTS setup (6h)
> - Blueprint B.2: swerve frame generator (24h)
> - Antenna AN.1-AN.3: scraper + scoring + database (16h)

**Reality check:**
- Antenna AN.1-AN.3 are already done (Antenna is fully shipped). The 16 hours
  budgeted there are recoverable.
- Blueprint B.1 (API + COTS setup) is partially done — `onshape_api.py` works,
  `blueprint/.env` has keys, `cots_parts/` has 19 working part files. The
  remaining work is the *parametric* part, not the API plumbing.
- Blueprint B.2 (swerve frame generator) is **not** done. There's `swerve_frame_generator.py`
  but it generates raw geometry, not a parametrized FRCDesign reference. This
  is exactly the work the MCP pivot is about.

**Net:** the April roadmap was written before we knew about FRCDesign-as-references
or the hedless/onshape-mcp project. The hours are roughly right; the *approach*
inside those hours needs to change.

### What we burned last week (2026-04-04 → 2026-04-11)

Pulled from `git log --since='2026-04-04'`:

- Test infrastructure recovery (relocated 231 blueprint tests + 64 antenna tests
  into `tests/`, fixed CI testpaths, recovered orphaned tests)
- Oracle test suite (78 tests, locked in 18 prediction rules)
- Assembly composer test suite (62 tests, surfaced 3 AABB xfails)
- GameRules I/O fix (predict_from_file bug, +8 tests, removed 1 xfail)
- Cleanup work (junk file removal, doc reorganization, INDEX.md creation)
- 2026 season validation (42 games, 92% A1 win rate, runbook validation)

**What this week did NOT do:** advance any of the 10 systems toward their roadmap
targets. Test scaffolding hardens existing code; it doesn't move the system count.
That's the meta-problem the user named on Saturday and the reason this kickoff
doc exists.

### The MCP pivot (Saturday's user research)

User found `hedless/onshape-mcp` — a 49★ Python MCP server with 45 Onshape tools,
explicitly designed for Claude Code as the consumer, with mate connector builders.
Plus `Rhoban/onshape-to-robot` (523★, battle-tested URDF exporter) and the
broader CAD ecosystem (KittyCAD, CadQuery, build123d, partcad).

User's proposed architecture: stop hand-rolling CAD and treat Onshape as the
geometry source of truth. Generators become "copy reference doc → parametrize
Variable Studio → fetch back" instead of "compute XYZ transforms in Python."

Phases that DIE if we adopt this:
- `cad_builder.py` hermetic test suite (was Phase 5 of `BLUEPRINT_NEXT_6_PHASES.md`)
- Most of `assembly_composer.py` (raw AABB collision becomes irrelevant if mates
  are mate connectors)
- All future hand-rolled mechanism geometry generators

Phases that SURVIVE:
- Oracle (operates on rules, not geometry — the 944 tests are safe)
- `plate_generator.py` / `turret_generator.py` *physics* (sizing, CoG, load) but
  not their *geometry* output
- The roadmap above the Blueprint line (Antenna, Scout, Eye, Coprocessor, etc.)
- The Engine's higher-level orchestration

Pivot is **un-confirmed** until the Saturday spike + MCP install lands. This
kickoff doc treats it as the most likely path but plans for both branches.

---

## Section 2 — What this week (Mon 4/13 → Sun 4/19) can actually finish

### Budget assumption

Full weekly cap reset Monday 10:00 AM. If last week we did ~30% of cap on the
final-day Phase 2 sprint (Sonnet agent + Opus chat + research + this doc), then
a sustainable pace is **roughly 1 substantive workstream per day across both
models**. Call it 6-8 substantive workstreams over the week, with buffer.

Each "substantive workstream" = ~1 hour Sonnet agent OR ~2-3 Opus chat rounds
with planning + code review.

### Tier A — Must do this week (the unblock)

These three are gates. Without them every other week is more wasted scaffolding.

**A1. FRCDesign elevator spike** (user runs, no model budget)
- Fork one FRCDesign elevator reference doc in Onshape
- Open the Variable Studio (if any)
- Report back 3 things: (a) does it have named variables like `stage_count` /
  `extension_in`, (b) are the mates between stages parametric on those variables
  or fixed, (c) roughly how many variables exposed
- Time: ~30 min user time, $0 budget
- **Without this we cannot pick a Blueprint architecture for the rest of the year.**

**A2. hedless/onshape-mcp install + smoke test** (Sonnet, ~1 hour)
- Read `hedless/onshape-mcp` README + tool list
- Install the MCP server, configure it to read keys from `blueprint/.env`
  (`ONSHAPE_ACCESS_KEY` / `ONSHAPE_SECRET_KEY`)
- Smoke-test 3 calls: `list_documents`, `get_features` on a known FRCDesign doc,
  `get_variables` on a Variable Studio (if A1 confirmed Variable Studios exist)
- Report which of the 45 tools work end-to-end and which fail
- Pre-req: A1 done, or A1 confirmed unavailable
- **Output:** new doc `BLUEPRINT_MCP_SMOKE_TEST.md` with the tool inventory + verdict

**A3. Architecture decision doc** (Opus, ~1 chat round)
- Read A1 + A2 outputs
- Write `BLUEPRINT_REV2_DECISION.md` — the one-page verdict on whether we
  pivot to MCP-driven copy-and-parametrize or stay with hand-rolled generators
- Decide the fate of `assembly_composer.py`, `cad_builder.py`, `plate_generator.py`,
  `turret_generator.py` explicitly (keep / shrink / delete / replace)
- Update `BLUEPRINT_NEXT_6_PHASES.md` to reflect the decision (or supersede it)

**Tier A total:** ~2 hours user time + ~1.5 hours model time. Should land Monday + Tuesday.

### Tier B — Should do this week (real architecture work, post-decision)

These depend on Tier A's outcome. Pick the matching branch.

**Branch B-MCP** (if A3 says pivot)
- **B-MCP.1** Write `BLUEPRINT_REV2_COPY_PARAMETRIZE.md` — the new spec for the
  generator pipeline. (Opus, 1 round)
- **B-MCP.2** First real generator rewrite: cascade elevator using the MCP +
  one FRCDesign reference doc. End-to-end: oracle says "elevator", spec says
  "2-stage cascade, 24in extension", we copy the FRCDesign doc, set the variables,
  fetch the result. (Sonnet, ~2 hours)
- **B-MCP.3** Demo: run the full pipeline against 2024 Crescendo and 2025 REBUILT
  GameRules. Verify a real Onshape doc shows up at the end. (Sonnet, ~1 hour)

**Branch B-LOCAL** (if A3 says stay with hand-rolled)
- **B-LOCAL.1** Fix AABB bug in `assembly_composer.py` (Phase 1 of the original
  6-phase plan, removes 3 xfails). (Sonnet, ~1 hour)
- **B-LOCAL.2** Lock down `plate_generator.py` with tests + audit. (Sonnet, ~1 hour)
- **B-LOCAL.3** Lock down `turret_generator.py` with tests + audit. (Sonnet, ~1 hour)

**Tier B total:** ~3-4 hours model time. Should land Wed + Thu.

### Tier C — Nice to have if budget remains (compounding work)

These are the "compounding" systems from the roadmap. Each is small and standalone
and would have shipped weeks ago in a healthier roadmap pace.

**C1. Pit Crew P.1** — create #robot-reports Discord channel + post the template
from `design-intelligence/pit-crew/`. Time: 10 min user, no model budget. From
the roadmap "Quick Wins" list, never executed.

**C2. Vault V.1** — create the inventory Google Sheet template. Time: 30 min user,
no model budget. From the roadmap "Quick Wins" list, never executed.

**C3. Cockpit D.1** — controller mapping doc finalization. There are 3 reference
docs in `design-intelligence/cockpit/` already. Read them, write a single
canonical `D1_CONTROLLER_MAPPING_FINAL.md` that the build season can lock to.
(Opus, ~1 round)

**C4. Eye smoke test debrief follow-up** — IF the FIT CMP weekend test
(`EYE_RUNBOOK_FIT_CMP_2026-04-11.md`) ran successfully and produced a debrief
doc, this Monday workstream reads the debrief, identifies the top 1-2 concrete
improvements, and either schedules them or files them as backlog. If the
weekend test surfaced something exciting, Eye E.1 (offseason batch POC) may
need to move up the roadmap from August to May. (Opus, ~1 round)

**Tier C total:** ~1-2 rounds of model time + ~40 min user time. Friday filler if
Tier B finished early.

### Tier C parallel — FIT DCMP test runs Wed 4/15 → Sat 4/18 (NOT this weekend)

**Date correction (2026-04-11 PM):** FIT DCMP is 2026-04-15 → 2026-04-18, not
this weekend. Worlds is 2026-04-29 → 2026-05-02. Updated event window memory
reflects this.

**FIT_DCMP.1** — Run `EYE_RUNBOOK_FIT_DCMP_2026-04-15.md` (renamed from
2026-04-11) against FIT DCMP local-only. 5-10 matches, Mode A (post-match VOD),
Haiku backend OR (if Path A wire-up lands by Wed) the local compound model.
Costs Anthropic API credits (~$1-2 if Haiku) or zero (if local model). Zero
Claude Code conversation budget either way. **This is the dress rehearsal for
Worlds.**

This is **not blocked by Monday** and does **not** require Tier A to land first.
User runs it autonomously Wed-Sat and writes a 1-page debrief.

### Tier D — DO NOT do this week

Listed explicitly so we don't drift back into it.

- ❌ More test scaffolding on `cad_builder.py` (Phase 5 of old plan — DEAD)
- ❌ More test scaffolding on `plate_generator.py` / `turret_generator.py` *unless*
  the architecture decision says they survive (i.e. wait for Tier A)
- ❌ Any roadmap item past July 2026 (Coprocessor, Vault audit, Grid harnesses,
  Clock, Pit Crew P.2-P.6, Eye E.3-E.4) — these have hardware dependencies or
  ordering windows that don't open until summer
- ❌ "Cleanup" / "audit" / "doc reorg" sessions — we did the cleanup last week,
  don't do it again
- ❌ Anything that doesn't move at least one of the 10 systems forward
- ❌ **Azure deploy of the Eye / vision worker.** Worlds is the Azure deploy test
  window, not this week. FIT CMP is local-only. Do not flip `MODEL_NAME=fake` →
  real in Bicep until after the FIT CMP debrief AND a Worlds-prep go decision.

### Realistic week ceiling

**REVISED 2026-04-11 PM:** User explicitly authorized burning up to ~50% of
weekly cap on Blueprint MCP work this week. That changes the math from "tier
gating" to "execute hard on the architecture pivot, leave headroom for Eye
runbook polish + buffer."

If everything goes well:
- Tier A lands fully Mon-Tue (3 items, ~10-15% of cap)
- Tier B-MCP lands fully Tue-Thu (3 items, ~30-35% of cap) — first real generator
  rewritten against the MCP pipeline, demoed against 2024+2025 GameRules
- Eye runbook polish for FIT DCMP lands by Wed (~3-5% of cap)
- Tier C lands 1-2 compounding items Friday

**Total advance: ~50% cap consumed, MCP architecture in production for at
least the cascade elevator generator, FIT DCMP test runbook ready for
weekend, ~50% cap held in reserve for Worlds prep next week.**

If things go poorly (spike says "FRCDesign refs aren't parametric", MCP install
hits auth issues, etc.):
- Tier A lands partially (A1 + A2, A3 deferred)
- Tier B falls back to B-LOCAL (AABB fix + plate/turret lockdown)
- ~25-30% cap consumed instead of 50%
- More headroom for Worlds prep next week

**Floor: ~3-4 workstreams, MCP question answered definitively, week not wasted
even on the bad path.**

---

## Section 2.5 — Week 2 (Mon 4/20 → Sun 4/26): Worlds prep

**Headline goal:** wire a fully-local vision model into `vision_yolo.py` so that
during Worlds week (4/29 → 5/2) we can demonstrate "5 consecutive live matches
processed end-to-end with no API dependency."

### V0a is RE-OPENED

`design-intelligence/V0a_MODEL_SELECTION.md` was resolved earlier today
(2026-04-11 morning) as **Path C** ("stay fake, defer to off-season data engine").
The reasoning was sound at the time: 2026 season was assumed active, Path A
work would be "zero-sum with the rest of the season" and "throwaway."

**Both premises are now invalid:**
1. 2950's 2026 season is over (no more team competition this year)
2. Path A is no longer throwaway — it IS the Worlds demo. The off-season auto-label
   data engine still ships in summer, but we need a working model BEFORE that
   for the FIT DCMP rehearsal + Worlds demo.

**Decision:** re-open V0a as **Path A** (compound pipeline). Estimated effort
from V0a doc: ~6h wrapper + ~4h tuning = ~10 hours. That's a single Sonnet
workstream over 2-3 sessions.

### Week 2 task list

**W2.1 — Re-open V0a, write the new decision in `V0a_MODEL_SELECTION_REV2.md`**
(or amend V0a in place). Records the constraint change and locks in Path A.
(Opus, ~1 round)

**W2.2 — Wire `_CompoundFRC2026Model` into `eye/vision_yolo.py`** via the
existing `register_model()` interface. Components:
- Robot detector: `autonav/frc-robot-detection` (filter to "robot" class)
- Fuel detector: `2026-wiredcat-fuel-detection/2026-frc-rebuilt-fuel-detection`
- Bumper-color HSV classifier (lower-third of robot bbox)
- Spatial heuristics for cycle / climb / defense (per V0a §A)
- Output: emit `VisionEvent` records matching the existing schema
(Sonnet, ~3-4 hours)

**W2.3 — Smoke test against cached FIT DCMP VODs.** By the time W2 starts,
FIT DCMP weekend will have produced ~5-10 cached VOD files in `eye/.cache/`.
Run the new compound model against them, compare to the Haiku-based reports
from the FIT DCMP weekend test, gather a delta report.
(Sonnet, ~1-2 hours)

**W2.4 — Tune the spatial zones for the 2026 REBUILT field geometry.** The
zone definitions in V0a §A (low goal / high goal / cage / scoring zone) are
heuristic. Eyeball-tune them against the cached FIT DCMP frames until the
cycle counts roughly match the OCR'd score breakdowns.
(Sonnet, ~2 hours)

**W2.5 — End-to-end live test.** Pick one cached FIT DCMP VOD, run the full
pipeline (`hls_pull` segment-style → `match_boundary` autocut → `vision_yolo`
local inference → `LiveMatch` aggregation), confirm one match end-to-end with
no API calls. This is the dress rehearsal for the dress rehearsal.
(Sonnet, ~1 hour)

**W2.6 — Worlds runbook.** Write `EYE_RUNBOOK_WORLDS_2026-04-29.md` — the
operator's manual for the Wed 4/29 → Sat 5/2 demo. Covers: how to find the
Worlds livestream URL, how to start the local pipeline, how to confirm 5
consecutive matches landed, what to do when something fails mid-match.
(Opus, ~1 round)

### Week 2 budget

**Estimated:** ~30-40% of week-2 cap. Bulk of it on W2.2 + W2.3 + W2.4 (the
actual model wire-up + tuning).

**Reserve:** ~30% of week-2 cap held back for Worlds week itself in case
something goes wrong live.

---

## Section 2.6 — Worlds week (Wed 4/29 → Sat 5/2): the binary demo

**Success criterion (locked):** **5 consecutive Worlds qualification matches
processed live, end-to-end, with the fully-local compound vision model. Zero
API dependency. Output matches in `LiveMatch` format with cycle counts, climb
outcomes, and (if heuristics fire) defense tags.**

We do NOT need to process the entire Worlds. We do not need to compete with
real scouts. We need 5 matches in a row to land cleanly. That's it.

### What "live" means in this context

- Match starts → vision worker pulls a ~2-min HLS segment from the livestream
- Segment goes through `match_boundary` autocut to find the boundary frames
- Frames go through the compound local model
- Aggregator emits a LiveMatch record per match
- No human intervention between matches

If 5 in a row land cleanly: **demo successful. Engine is provably operational
on a live broadcast with no API.**

If 1 fails (any reason): debug, fix, retry, count from zero. We have ~80
qualification matches over 4 days. Plenty of attempts.

### What this UNLOCKS

A successful 5-match demo at Worlds is the proof point that the entire vision
pipeline (Phase 2 of Live Scout) works end-to-end without paid APIs. That
unlocks:
- The Path C off-season data engine becomes a quality upgrade, not a critical
  path item
- The Coprocessor (system #5) gets a clear performance baseline to beat
- The 2027 season ships with a battle-tested vision pipeline instead of an
  untested one

### What this does NOT do

- Does not deploy to Azure (Worlds is local-only on Safiq's machine)
- Does not handle every Worlds match (5 is the bar)
- Does not prove production reliability (5 matches is a smoke test, not SLA)
- Does not commit Azure infra spend (V0b GPU SKU stays deferred)

---

## Section 2.7 — Off-season MCP architecture (June → December 2026)

**Saturday 2026-04-12 landscape scan uncovered an MCP ecosystem play.** Not
critical path for Worlds, but reshapes the off-season roadmap.

### Adopted MCP servers (install when needed)

| MCP Server | Stars | Engine System | What it does for us |
|---|---|---|---|
| `hedles/onshape-mcp` | 49 | Blueprint (#1) | Claude-driven CAD: create/parametrize Onshape docs |
| `github/github-mcp-server` | 28,800 | Clock (#10) | Track Engine milestones, issues, PRs via Claude |
| `taylorwilsdon/google_workspace_mcp` | 2,100 | Clock (#10) | Team OS: Calendar (build schedule), Sheets (BOM), Drive (docs), Gmail (notifications) |
| `anaisbetts/mcp-youtube` | 514 | Eye (#6) | Match video metadata + transcripts for batch processing |
| `DugboTek/FRCDocsMCP` | 0 | All systems | WPILib + CTRE + AdvantageScope docs in Claude context |

### The FRC MCP vision (fastmcp, off-season build)

Use `PrefectHQ/fastmcp` (24.5K★) to wrap each Engine subsystem as an MCP
server. Claude becomes the universal interface — replaces CLI for students.

**Example queries that become possible:**
- "What's 254's average cycle time this season?" → Scout MCP
- "Show me 2950's last match Eye report" → Eye MCP
- "Any CD threads about swerve this week?" → Antenna MCP
- "Generate a 2-stage elevator for REBUILT" → Blueprint MCP (via onshape-mcp)
- "What tasks are left for the drivetrain?" → Clock MCP (via GitHub MCP)
- "Add a build session for Thursday 6pm" → Google Workspace MCP

**Token budget concern (user-flagged):** 10+ MCP servers = 10-20K tokens of
tool definitions. Mitigations: session-scoped connections (scouting ≠ CAD),
fastmcp lazy loading, composite servers (Scout+Eye = one server). Real concern,
solvable at implementation time.

**First-mover opportunity:** No "FRC MCP" results on GitHub. 5000+ FRC teams,
zero MCP solutions. If we open-source The Engine's MCP servers, we're first.

### New Blueprint stack (supersedes `onshape_api.py`)

| Layer | Tool | What it does |
|---|---|---|
| Python SDK | `onshape-robotics-toolkit` (297★) | Variable Studio editing, URDF export, assembly graph, mesh handling. `pip install onshape-robotics-toolkit`. Replaces our deprecated `onshape_client` dep. |
| MCP layer | `hedles/onshape-mcp` (49★) | 45 Onshape tools for Claude. Interactive CAD sessions. |
| Both coexist | No conflict | Toolkit for batch/programmatic ops, MCP for agent-driven sessions. |

---

## Section 2.8 — Oracle Intelligence Upgrade (off-season, 33h)

**Saturday 2026-04-12 deep dives into statbotics source + predictobics + 
frc-livescore revealed 9 concrete improvements to the Oracle + Scout.**

### Phase 1: Data foundation (May-June, ~11h)
| # | Task | Hours | Source |
|---|---|---|---|
| 1 | Add 10 missing historical games to `HISTORICAL_GAMES` + `GROUND_TRUTH` (2012-2021) | 4h | `PREDICTION_ENGINE_VALIDATION_14GAME.md` — already analyzed, just needs coding |
| 2 | Pull `epa_sd` + `epa_skew` into Scout predictions (uncertainty bands) | 2h | Statbotics API fields we're currently ignoring |
| 3 | Use component EPAs (`auto_epa`, `teleop_epa`, `endgame_epa`) for draft complementarity | 3h | Statbotics API |
| 4 | Replace hardcoded rule confidence (0.85, 0.90) with Norm EPA-backed values | 2h | Statbotics cross-season Norm EPA |

### Phase 2: Scout intelligence (July-August, ~11h)
| # | Task | Hours | Source |
|---|---|---|---|
| 5 | Port defense-adjusted EPA into Scout alliance ranking | 4h | predictobics: `defense_adj = epa_total + 0.18*(sos - global_avg) - 0.45*defense_impact` |
| 6 | Port synergy scoring (pair-level residuals) into draft advisor | 4h | predictobics: alliance "chemistry" detection |
| 7 | Port SkewNormal EWMA locally (~200 lines numpy/scipy) | 3h | Statbotics source: real-time what-if sims during alliance selection, zero API latency |

### Phase 2.5: 1678 Algorithm Ports (July-August, ~12h)
| # | Task | Hours | Source |
|---|---|---|---|
| 5b | Port Scout Precision Rating (SPR) — scout accuracy validation | 3h | frc1678 `sim_precision.py`: isolate individual scout reliability via 3-scout combos |
| 5c | Port NormalDist win probability | 2h | frc1678 `predicted_aim.py`: `P(R-B > 0)` via `NormalDist.cdf()` |
| 5d | Port auto-path compatibility scoring for draft | 3h | frc1678 `pickability.py`: ensure 2nd-pick auto doesn't conflict with 1st-pick |
| 5e | Port anomaly/outlier detection for scouting data | 1h | frc1678 `data_validation.py`: z-score flagging |
| 5f | Port TrueSkill Bayesian ratings | 3h | frc1678 `ratings.py`: mu/sigma complement to EPA |

### Phase 3: LLM augmentation (September-October, ~11h)
| # | Task | Hours | Source |
|---|---|---|---|
| 8 | Add Claude as Oracle reviewer layer (catches novel mechanics rules don't cover) | 3h | anthropic SDK + CROSS_SEASON_PATTERNS.md as system prompt |
| 9 | Game manual → GameRules auto-extraction (Claude reads PDF → structured JSON) | 8h | FRCDocsMCP + anthropic SDK. Eliminates manual KICKOFF_TEMPLATE.md filling for 2027. |

### New data sources to integrate

| Source | Provides | System |
|---|---|---|
| Statbotics EPA internals (SkewNormal EWMA) | Real confidence scores, uncertainty, component-level predictions | Oracle + Scout |
| predictobics defense model | Defense effectiveness vs low-EPA differentiation | Scout (3rd pick strategy) |
| predictobics synergy scoring | Pair-level alliance composition effects | Scout (draft advisor) |
| frc-livescore template matching | Auto-score extraction from broadcast video | Eye → Scout pipeline |
| JSim physics engine (Python bindings) | Validate generator physics with real simulation | Blueprint + Motor Model |
| 2910 2025 robot code | Ground truth validation for Oracle 2025 predictions | Oracle |
| **1678 SPR** | Scout accuracy validation — rank individual scout reliability | Scout |
| **1678 NormalDist win chance** | Probabilistic win prediction complement to EPA | Scout + Oracle |
| **1678 auto-path compatibility** | 2nd-pick draft scoring — non-conflicting autonomous paths | Scout (draft) |
| **1678 TrueSkill** | Bayesian team ratings (mu/sigma) complement to EPA | Scout |
| **ReCalc math** | Cross-validate elevator/arm/flywheel ODE solvers vs our motor_model.py | Blueprint |
| **frc-shooter-calculator** | Projectile trajectory with Magnus lift — bolt onto flywheel_generator.py | Blueprint |
| **Spectrum Mechanism pattern** | Config-driven PID/MotionMagic/current-limit template for code generation | Blueprint |

### New system adoptions (batch 6)

| Adoption | System | Hours Saved | Notes |
|---|---|---|---|
| **PhotonVision** (406★) | Coprocessor | **-30h** | Flash-and-go AprilTag + pose. Eliminates CP.1-CP.8. |
| **Elastic Dashboard** (144★) | Cockpit | **-19h** | Fork + add strategy/checklist widgets. |
| **1678 algorithms** (5 ports) | Scout | **-12h** | SPR, NormalDist, auto-path, anomaly, TrueSkill |

---

## Section 2.10 — CAD Geometry Intelligence (Einstein-scoped, off-season)

**Saturday evening discovery:** Spectrum3847's FRC CAD Collection spreadsheet contains **847 robot CAD entries** from 2007-2026. Cross-referenced with Einstein teams: **56 Einstein teams have CAD in the collection** — **253 total entries** (112 Onshape with mates, 131 STEP/IGES, 10 other).

**Key insight:** STEP files have no mates, but they DO have exact geometry. With known game rules per year, we can extract mechanism dimensions, count motors, detect mechanism types, and correlate with match performance. Einstein-only scoping keeps it tractable (~253 CAD entries) and the signal is pure (top teams only).

**Data source:** `FRC CAD Collection - Spectrum3847.xlsx` + Onshape link for FRCDesign elevator (confirmed: has parametric mates + Variable Studio variables).

**Top Einstein teams by CAD depth:**
- 148 Robowranglers: 26 entries (2008-2020) — longest CAD history of any team
- 118 Robonauts: 24 entries (2007-2025) — full career span in CAD
- 971 Spartan: 24 entries (2007-2023) — 12 Onshape + 12 STEP
- 1678 Citrus Circuits: 17 entries (2015-2024) — 14 Onshape (richest mate data)
- 3847 Spectrum: 9 entries (2012-2024) — curators of the collection itself
- 2910 Jack in the Bot: 6 entries (2018-2025)
- 6328 Mechanical Advantage: 5 entries (2019-2024)

### Tier 1: Metadata Extraction (~12h, June-July)

**Scope:** 253 Einstein CAD entries. Import each, extract geometry metadata, cross-reference with TBA.

| # | Task | Hours | Tool |
|---|------|-------|------|
| 1 | Build STEP/Onshape import pipeline (batch) | 3h | onshape-robotics-toolkit + cadquery/OCP for STEP |
| 2 | Extract per-robot: bounding box, mass, CG height, wheel count, motor count | 3h | Geometry queries |
| 3 | Cross-reference with TBA API: team EPA, event wins, auto scores, endgame | 2h | statbotics + TBA |
| 4 | Build `EINSTEIN_GEOMETRY_DATABASE.csv` — 253 rows × 25+ columns | 2h | pandas |
| 5 | Correlate: CG height vs climb success, envelope vs scoring, motor count vs EPA | 2h | Analysis |

**Output:** Data-backed validation of CROSS_SEASON_PATTERNS rules. "R5 says 2-stage elevator is optimal — here's the geometric proof across 56 Einstein teams."

### Tier 2: Mechanism Classification (~18h, July-August)

**Scope:** Same 253 entries. Train classifier on the 112 Onshape robots (where mates reveal mechanism type), apply to 131 STEP robots.

| # | Task | Hours | Approach |
|---|------|-------|----------|
| 1 | Label 112 Onshape robots by mechanism type (elevator/arm/turret/intake/climber) using mate analysis | 4h | onshape-robotics-toolkit assembly graph |
| 2 | Extract geometry features: vertical rail patterns, pivot points, extension envelope, structural tube layout | 4h | Shape analysis |
| 3 | COTS part matching: identify motors (Falcon/NEO/Kraken body shapes), gearboxes (MaxPlanetary/VP shells), wheels (known diameters) | 4h | Template matching against COTS catalog |
| 4 | Train mechanism classifier on Onshape-labeled data, apply to STEP robots | 3h | scikit-learn / simple CNN on voxelized geometry |
| 5 | Correlate classified mechanisms with game rules + match performance per year | 3h | Analysis + new Oracle rules |

**Output:** Mechanism-level Oracle rules derived from geometry, not intuition:
- "In high-scoring-height games, cascade elevators on Einstein teams extend to avg X inches"
- "Einstein teams use avg Y motors per primary mechanism vs Z for non-Einstein"
- "Intake width / game piece width ratio clusters around A for scoring >B points/match"
- New CROSS_SEASON_PATTERNS rules backed by CAD data from 56 Einstein teams

### Combined: 30h, fits into July-August alongside Scout Phase 2

**Roadmap addition:**
| Work Item | Hours | When |
|-----------|-------|------|
| CAD Geometry Tier 1 (metadata extraction) | 12h | June-July |
| CAD Geometry Tier 2 (mechanism classification) | 18h | July-August |
| **Total** | **30h** | Parallel with Oracle/Scout work |

**Revised grand total: 310h + 30h = 340h (still 28% below original 471h)**

---

## Section 3 — Monday morning checklist (in order)

**Read these first, in this order, before anything else:**
1. This doc (you're doing it)
2. `MEMORY.md` (auto-loaded but skim it)
3. `design-intelligence/INDEX.md`
4. `design-intelligence/BLUEPRINT_NEXT_6_PHASES.md` (the now-obsolete plan,
   read as historical context for the pivot)

**Then check:**
- [ ] Did the user run the Saturday FRCDesign spike? (look in chat history or
      ask). If yes → start A2 immediately. If no → ask once, politely, then
      start A2 anyway because the install doesn't depend on the spike.
- [ ] `git log -5` to confirm we're still at `415308d` and nothing weird
      happened over the weekend.
- [ ] `pytest tests/blueprint/test_oracle.py tests/blueprint/test_assembly_composer.py`
      smoke test (~10 sec) to confirm Phase 2's fix is still green.

**Then execute Tier A:**
- A2 (MCP install, Sonnet background agent — write the prompt as Opus, launch
  as background task, do NOT block on it)
- While A2 runs: A3 partial work — draft the decision doc skeleton, leave
  branches blank for spike + smoke test results
- When A2 returns: fill in A3, post to user, get sign-off before Tier B

**Hard rules carried over from last week's lessons:**
1. Sonnet runs the code. Opus plans, reviews, decides.
2. No test scaffolding without an architecture decision behind it.
3. Search GitHub before scoping any external integration.
4. If something can't be locally verified, ask the user before assuming.
5. Test count is monotonic — if a phase drops it, abort that phase.
6. Don't write docs to feel productive. Docs serve decisions or onboarding.

---

## Section 4 — Things Opus needs to remember

(These exist in memory already but reinforced here for the post-reset session.)

- **Today's date is 2026-04-11.** Monday is 2026-04-13.
- **Off-season.** No competition pressure. Long-bet bias is correct.
- **Sonnet executes, Opus plans.** Do not do code work as Opus.
- **The Engine ≠ FRC robot code.** The Engine is the *meta-system* that helps
  the team build the robot. The actual 2027 robot code lives elsewhere in the
  same repo (`src/main/java/...`) but is not what we work on here.
- **Onshape keys exist** in `blueprint/.env`. Don't ask for them, don't print
  them, don't paste them in chat.
- **Test count baseline at start of week:** 944 passed, 2 skipped, 3 xfailed.
  That number is the floor — drop it and abort whatever caused the drop.
- **The 3 xfails are all AABB-related** in `tests/blueprint/test_assembly_composer.py`.
  They are documentation, not failures. Don't fix them until A3 says
  `assembly_composer.py` survives.

---

## Section 2.9 — Einstein Finalist Audit + CodeScout Concept (Batch 7, added Saturday PM)

**Saturday afternoon:** Exhaustive audit of all 40+ unique teams that appeared on Einstein finalist/winner alliances 2019-2025. Checked GitHub presence for every team. Found 27 of 30+ teams have GitHub orgs. Full findings in `LANDSCAPE_SCAN_254_BINNER_2026-04-12.md` Batch 7.

**New adopt-to-study items (12):** Raven ecosystem (1310, 3-tier scouting), FalconScout (4099, config-driven QR scouting), StrategyEngine-2026 (1690, game sim + AI), SCREAMLib (4522, WPILib vendor lib with IK solver), deadeye/wallEYE (2767, multi-camera vision), and 7 more. All reference architectures — no direct hour savings but inform design decisions for Scout, Blueprint, and Coprocessor.

**CodeScout — new Scout feature concept (~10h, off-season):**
Pre-competition GitHub scanning of opponent teams. Parse Choreo .traj / PathPlanner .path files to visualize auto paths on field map. Extract mechanism constants, auto mode selectors, subsystem inventories. ~11% of FRC teams have public repos. Critical limitation: elite teams publish post-season only. Best use: off-season learning from "-Public" repos, supplementary pre-regional intel for mid-tier opponents. Ethical: public code is fair game, but automated surveillance feels gray. Build as study tool first.

**Updated final numbers (all 7 batches):**
- 120+ repos directly evaluated, 417 org repos scanned, 40+ Einstein teams checked
- 18 adopt, 30 adopt-to-study, 16 algorithm ports
- Dev: 471h → 248h (47% reduction, -223h)
- New work: +52h Oracle/Scout intelligence + 10h CodeScout = +62h
- **Grand total: 471h → 310h net (34% reduction)**

---

## Section 5 — The one paragraph version

> Last week we burned context on test scaffolding (944 tests, +236 from start of
> week, +2 real bug fixes) instead of advancing any of the 10 Engine systems
> toward their December 2026 roadmap. Saturday the user surfaced
> hedless/onshape-mcp (49★, 45 Onshape tools designed for Claude Code) which
> probably makes most of `blueprint/`'s hand-rolled CAD code redundant. This
> week's first job is to confirm or kill that pivot in 2 hours of work
> (FRCDesign spike + MCP smoke test + decision doc), then either rewrite the
> first generator against the MCP or fall back to fixing AABB and locking
> plate/turret. Compounding work (Pit Crew P.1, Vault V.1) fills any leftover
> budget. Hard floor: end the week with a recorded architecture decision and
> the Blueprint materially advanced. Hard ceiling: ~7 substantive workstreams,
> don't try to do more.

---

*Written by Opus 2026-04-11. Read this Monday before touching anything.*
