# THE ENGINE — Master Roadmap
# Prioritized Execution Plan
# Deadline: Everything complete by December 2026
# Updated: April 2026 (rev-3 with SystemCore + on-robot coprocessor)
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Guiding Principle

The Blueprint is the backbone — a parametric CAD pipeline that gives
the team a complete robot assembly on kickoff day. Build it first,
build it fully, and build everything else around it.

**Hard deadline: all 10 systems operational by December 2026.**

> **Rev-3 note (April 2026):** Whisper, Eye E.2, Pit Crew P.5, and the
> on-robot AdvantageKit logger have been consolidated into a single
> **On-Robot Coprocessor** line item (CP.1-CP.14) built around a Jetson
> Orin Nano Super that mounts on the robot itself. See
> [ARCH_COACH_AI.md](ARCH_COACH_AI.md) and
> [ARCH_SYSTEMCORE_MIGRATION.md](ARCH_SYSTEMCORE_MIGRATION.md).
> Net effect: ~25 hours saved, hardware budget ~$509 (up from $390
> but Limelight cameras are eliminated in exchange).

---

## The 10 Engine Systems

| # | Codename | System | Hours | Hardware Cost |
|---|----------|--------|-------|---------------|
| 1 | The Blueprint | CAD Pipeline (Full) | 120-150h | $0 |
| 2 | The Antenna | Chief Delphi Watcher | 32h | $0 |
| 3 | The Cockpit | Driver Station | 39h | $0 |
| 4 | The Scout | Scouting System | 54h | $0 |
| 5 | **On-Robot Coprocessor** (Whisper + Eye on-robot + logger + P.5) | Jetson Orin Nano Super, CP.1-CP.14 | 66.5h | ~$509 |
| 6 | The Eye (offseason batch, S.6 integration) | Scouting laptop pipeline | ~30h | $0 |
| 7 | The Pit Crew (P.1-P.4, P.6) | Pit Operations | ~44h | $0 |
| 8 | The Vault | Parts Inventory | 12h | $0 |
| 9 | The Grid | Electrical Standards (CAN-FD + SystemCore rewire) | 18h | $0 |
| 10 | The Clock | Build Management | 30h | $0 |
| | | **TOTAL** | **~450-500h** | **~$509** |

---

## Priority Tiers

### TIER 1: The Foundation (April-July 2026)
*The Blueprint is the centerpiece. The Antenna starts compounding immediately.*

| Priority | System | Why First | Target |
|----------|--------|-----------|--------|
| **1** | **The Blueprint B.1-B.3** (56h) | API foundation + frame generator + Priority A templates (swerve frame, elevator, OB intake). These 3 templates cover 80%+ of FRC robots. Must be rock-solid before anything else layers on top. | **April-July 2026** |
| **2** | **The Antenna** (32h) | Starts feeding intelligence into The Engine immediately. Every week it runs, the knowledge base grows. By December you'll have 8 months of community intelligence. Start it in parallel with Blueprint work. | **April-June 2026** |
| **3** | **The Cockpit D.1-D.3** (11h) | Controller mapping, dashboard layout, console hardware standard. Documentation + physical setup — no code. Lock these early so driver practice is standardized from day one. | **May-June 2026** |

**Tier 1 total: ~99 hours, $0 cost**
**Result: Core CAD templates generating, CD intelligence accumulating, driver station standardized.**

---

### TIER 2: Full CAD + Intelligence (July-September 2026)
*Complete all 12 Blueprint templates. Build the scouting and coaching systems.*

| Priority | System | Why Now | Target |
|----------|--------|---------|--------|
| **4** | **The Blueprint B.4-B.5** (62h) | Priority B templates (under-bumper intake, full-width intake, hook climber, wrist) + Priority C templates (telescope climber, shooter, turret, cascade elevator). Complete the full template library so any game architecture can be generated. | **July-September 2026** |
| **5** | **The Scout** (54h) | Full scouting system: pre-event reports, targeted pit visits, stand scouting forms, alliance selection advisor, Monte Carlo simulation. Ready to deploy at any offseason event for testing. | **July-September 2026** |
| **6** | **On-Robot Coprocessor CP.1-CP.12** (60.5h) | Order Jetson Orin Nano Super + BOM ($509). Bring up JetPack, llama.cpp, Gemma 2B. Build `whisper_bridge.py` NT client. Install PhotonVision, train YOLO11s on FRC game pieces, wire Eye-on-robot. Build AdvantageKit NVMe logger and the Pit Crew P.5 FastAPI debug dashboard. Sim-test 20 matches. **One box, five jobs.** See [ARCH_COACH_AI.md](ARCH_COACH_AI.md) rev-3 for full phase breakdown. | **July-September 2026** |
| **7** | **The Eye E.1** (offseason batch proof-of-concept) (12-20h) | Scouting-laptop pipeline for processing offseason event footage. Validates that offline video analysis complements the on-robot YOLO detections (E.2 batch is replaced by on-robot CP.7-CP.9). | **August-September 2026** |

**Tier 2 total: ~180 hours, ~$509 cost**
**Result: Full 12-template CAD pipeline, scouting system tested, on-robot coprocessor bringing Whisper + PhotonVision + Eye + logger + P.5 dashboard online in a single box, offseason video pipeline validated.**

---

### TIER 3: Operations + Integration (September-November 2026)
*Build the team operations infrastructure. Wire everything together.*

| Priority | System | Why Now | Target |
|----------|--------|---------|--------|
| **8** | **The Blueprint B.6-B.7** (32h) | Assembly Composer + BOM generator + dry runs. This is the integration layer — subsystems snap onto the frame, BOM exports, and the full kickoff workflow is validated end-to-end. | **September-October 2026** |
| **9** | **The Vault** (12h) | Full shop audit + inventory Google Sheet. Needs to be done before The Blueprint's BOM cross-referencing works. 12 hours of walking the shop and counting parts. | **September 2026** |
| **10** | **The Grid** (18h) | Wiring standards card, **CAN-FD topology map for SystemCore's 5 buses** (see [ARCH_SYSTEMCORE_MIGRATION.md](ARCH_SYSTEMCORE_MIGRATION.md)), pre-built swerve harnesses, inspection checklist, brownout kit, Jetson power rail (Pololu D36V50F5 buck-boost off PDH). Build harnesses during fall meetings when the shop is available. | **September-October 2026** |
| **11** | **The Clock** (30h) | Task generator + standup bot + parts tracker. Needs The Vault for inventory cross-referencing. Needs The Blueprint for BOM import. Both are now ready. | **October-November 2026** |
| **12** | **The Pit Crew P.1-P.4** (24.2h) | Robot Reports channel, pre-match checklist, post-match diagnostics, wear tracking. P.1 takes 10 minutes — do it immediately. P.2-P.4 are software that can be tested against AdvantageKit logs from the current robot. *(P.5 debug dashboard is folded into CP.11 on the Jetson.)* | **October-November 2026** |
| **13** | **The Cockpit D.4-D.5** (28h) | Driver practice analytics + coach information system. D.5 is The Whisper's lightweight fallback — build both and the coach always has strategic data regardless of which system is running. | **October-November 2026** |

**Tier 3 total: ~144 hours, $0 cost**
**Result: Complete CAD pipeline validated end-to-end, inventory done, harnesses built, build management ready, pit operations running, driver analytics live.**

---

### TIER 4: Polish + Future-Proofing (November-December 2026)
*Final integration, testing, and preparation for kickoff.*

| Priority | System | Why Now | Target |
|----------|--------|---------|--------|
| **14** | **The Eye E.3-E.4** (30h) | Scout integration + dashboard visualization. Wire The Eye's heat maps and cycle times (from on-robot YOLO + offseason batch) into The Scout's pre-event reports. Build the team comparison dashboard for alliance selection. | **November 2026** |
| **15** | **The Pit Crew P.6** (20h) | Digital twin — replays AdvantageKit logs from the Jetson NVMe with 3D visualization for post-match debug. *(P.5 debug dashboard already live on the Jetson from CP.11.)* | **November-December 2026** |
| **15b** | **On-Robot Coprocessor CP.13-CP.14** (6h) | Prompt refinement + live scrimmage test + 1-hour thermal/vibration test on the actual robot. Lock down the Whisper configuration for 2027 kickoff. | **October-November 2026** |
| **16** | **Full system dry run** (0h) | Run the entire kickoff workflow end-to-end using a past game (REBUILT or Reefscape). Prediction engine → Blueprint → Clock → Vault cross-ref → Scout pre-event. Fix any integration gaps. | **December 2026** |

**Tier 4 total: ~66 hours, $0 cost**
**Result: All 10 systems operational, tested, and ready for January 2027 kickoff.**

---

## Execution Calendar

```
═══════════════════════════════════════════════════════════════════

APRIL 2026                                   TARGET: 38 hours
├── The Blueprint B.1: API + COTS setup (6h)
├── The Blueprint B.2: swerve frame generator (24h)
└── The Antenna AN.1-AN.3: scraper + scoring + database (16h)

MAY 2026                                     TARGET: 42 hours
├── The Blueprint B.3: Priority A templates — elevator + intake (26h)
├── The Antenna AN.4-AN.6: digest + Discord + recommendations (11h)
└── The Cockpit D.1-D.3: mapping + dashboard + console (11h)
    *** Antenna weekly digests begin posting ***

JUNE 2026                                    TARGET: 35 hours
├── The Blueprint B.4: Priority B templates — intake, climber, wrist (30h)
└── The Antenna AN.7: LLM summarization (5h)

JULY 2026                                    TARGET: 65.5 hours
├── The Blueprint B.5: Priority C templates — shooter, turret, cascade (32h)
├── The Scout S.1-S.2: pre-event report + anomaly detection (24h)
├── Order Jetson Orin Nano Super + coprocessor BOM ($509)
└── Coprocessor CP.1-CP.3: JetPack flash + NVMe + fan + llama.cpp CUDA (9.5h)

AUGUST 2026                                  TARGET: 63 hours
├── The Scout S.3-S.4: stand scouting + alliance advisor (16h)
├── Coprocessor CP.4-CP.6: whisper_bridge + LLM call + 4 new NT keys (11h)
├── Coprocessor CP.7: PhotonVision install + 2-camera calibration (6h)
├── Coprocessor CP.8: YOLO11s training + TensorRT export (10h)
└── The Eye E.1: offseason batch proof of concept (12-20h)

SEPTEMBER 2026                               TARGET: 75 hours
├── The Blueprint B.6: assembly composer + BOM (20h)
├── Coprocessor CP.9: eye_onrobot YOLO inference loop (4h)
├── Coprocessor CP.10: AdvantageKit NVMe logger (4h)
├── Coprocessor CP.11: Pit Crew P.5 FastAPI debug dashboard on Jetson (8h)
├── Coprocessor CP.12: sim testing — 20 matches (8h)
├── The Scout S.5-S.6: Monte Carlo + Whisper integration (14h)
├── The Vault V.1-V.3: inventory template + audit + cross-ref (12h)
└── The Grid E.1-E.2: wiring card + SystemCore CAN-FD map (5h)

OCTOBER 2026                                 TARGET: 57 hours
├── The Blueprint B.7: validation + dry runs (12h)
├── Coprocessor CP.13-CP.14: prompt refinement + live scrimmage + thermal test (6h)
├── The Grid E.3-E.6: harnesses + PDH + Jetson power rail + checklist + kit (13h)
├── The Clock CL.1-CL.2: task generator + standup bot (18h)
├── The Pit Crew P.1-P.2: Robot Reports + checklist (4.2h)
└── The Cockpit D.4: driver practice analytics (12h)

NOVEMBER 2026                                TARGET: 61 hours
├── The Clock CL.3: parts tracker + BOM import + Vault link (10h)  *** Note: CL.2c (2h) already done in Oct ***
├── The Pit Crew P.3-P.4: diagnostics + wear tracking (20h)
├── The Cockpit D.5: coach info system (16h)
└── The Eye E.3: Scout integration (15h)

DECEMBER 2026                                TARGET: 35 hours
├── The Eye E.4: dashboard visualization (15h)
├── The Pit Crew P.6: digital twin — replays Jetson NVMe logs (20h)
├── Full system dry run: kickoff simulation with past game
└── Fix integration gaps, document everything

═══════════════════════════════════════════════════════════════════
JANUARY 2027 — KICKOFF DAY
│
│   Run prediction engine → Run The Blueprint → Run The Clock
│   → Run The Vault cross-ref → Order parts → Teams assigned
│   → The Scout generates pre-event reports
│   → The Whisper running on the on-robot Jetson coprocessor
│   → The Antenna has 9 months of intelligence
│   → The Grid harnesses installed in hours, not days
│
│   YOU ARE THE MOST PREPARED TEAM AT YOUR EVENT.
═══════════════════════════════════════════════════════════════════
```

---

## Monthly Hour Commitment

| Month | Hours | Pace (hrs/week) |
|-------|-------|-----------------|
| April | 38 | ~10 |
| May | 42 | ~10 |
| June | 35 | ~9 |
| July | 65.5 | ~16 |
| August | 63 | ~16 |
| September | 75 | ~19 |
| October | 57 | ~14 |
| November | 61 | ~15 |
| December | 35 | ~9 |
| **TOTAL** | **~471** | **avg ~13 hrs/week** |

This is roughly 12 hours/week across 9 months. Peaks in August-September
and November when multiple systems are building in parallel. Achievable
with 2-3 dedicated students + mentor working evenings and weekends.

---

## Dependency Map

```
                    ┌─────────────┐
                    │  Prediction  │
                    │   Engine     │
                    │  (EXISTS)    │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
 ┌──────────────┐  ┌──────────┐      ┌──────────┐
 │ The Blueprint│  │The Clock │      │ The      │
 │ (CAD) ★ T1   │  │(tasks)T3 │      │ Cockpit  │
 │ 12 templates │  └────┬─────┘      │(driver)  │
 └──────┬───────┘       │            └──────────┘
        │                │
        ▼                ▼
 ┌──────────┐     ┌──────────┐
 │BOM Export │────►│The Vault │
 │          │     │(parts)T3 │
 └──────────┘     └──────────┘

 ┌──────────┐     ┌──────────┐     ┌──────────────────────────┐
 │The       │────►│The Scout │────►│ On-Robot Coprocessor     │
 │Antenna   │     │(scouting)│     │ (Jetson Orin Nano Super) │
 │★ T1      │     │T2        │     │   - Whisper (coach LLM)  │
 └──────────┘     └────┬─────┘     │   - Eye on-robot (YOLO)  │
                       │           │   - PhotonVision         │
                       │           │   - AdvantageKit logger  │
                       │           │   - Pit Crew P.5 debug   │
                       │           │   T2 · CP.1-CP.14        │
                       │           └───────────┬──────────────┘
                       │                       │
                       ▼                       ▼
               ┌──────────────┐       ┌────────────────┐
               │  The Eye     │       │  SystemCore    │
               │  (offseason  │       │  robot ctrl    │
               │  batch) T2/T4│       │  (2027+)       │
               └──────────────┘       └────────────────┘

 ┌──────────┐     ┌──────────┐
 │The Grid  │     │The Pit   │
 │(wiring)T3│     │Crew T3/T4│
 └──────────┘     └──────────┘
```

★ = Tier 1 priority

---

## What Compounds

Start these early — they get better over time:

| System | Compound Effect |
|--------|----------------|
| **The Antenna** | 9 months of CD intelligence by kickoff. Every week adds to the knowledge base. |
| **The Blueprint** | Templates improve with each dry run. Year 2 kickoff is even faster. |
| **The Eye** | More events processed = more accurate team profiles. |
| **The Pit Crew P.1** | Robot Reports build a reliability database over time. |
| **D.4 Practice Analytics** | More sessions tracked = better drill recommendations. |

---

## Quick Wins (Do This Week)

| # | Action | Time | Impact |
|---|--------|------|--------|
| 1 | Set up OnShape API key + test onshape-client | 1 hour | Blueprint B.1 started |
| 2 | Start The Antenna scraper (AN.1) | 3 hours | Intelligence starts accumulating |
| 3 | Create #robot-reports Discord channel (P.1) | 10 min | Reliability database begins |
| 4 | Order Jetson Orin Nano Super Dev Kit ($249) + NVMe + buck-boost | 10 min | Lead time — arrives when needed |
| 5 | Catalog MKCad parts for Blueprint (B.1.2) | 2 hours | Foundation for all templates |

---

## Budget

On-robot coprocessor BOM (rev-3, replaces the rev-2 shelf plan):

| Item | Cost | When to Buy |
|------|------|-------------|
| Jetson Orin Nano Super 8GB Dev Kit | $249 | July 2026 |
| Samsung 980 NVMe 256 GB (M.2 2280) | $25 | July 2026 |
| Pololu D36V50F5 5V 5A buck-boost | $25 | July 2026 |
| Arducam B0497 OV9281 global shutter mono (×2) | $100 | July 2026 |
| ELP 1080p color USB3 global shutter | $55 | July 2026 |
| Noctua NF-A4x20 PWM fan + heatsink pad | $20 | July 2026 |
| Anker 4-port USB 3.0 hub | $15 | July 2026 |
| Cat6 patch cable, 1 ft | $5 | July 2026 |
| 3D-printed enclosure + heatsink bracket | $5 | August 2026 |
| Anderson Powerpole set + heat shrink | $10 | July 2026 |
| **TOTAL** | **~$509** | |

Eliminated from rev-2 plan (no longer needed):
- 7" HDMI IPS monitor — coach panel is on the existing DS laptop
- USB-C PD power bank — Jetson powered from PDH
- Driver-station-shelf Ethernet switch — already on the robot

Limelight 3/4 cameras ($400+ each) are NOT purchased — PhotonVision
on the Jetson with the Arducam globals replaces them entirely.

Everything else is free: OnShape edu license, Roboflow free tier,
open source libraries, Google Sheets, Discord webhooks.

---

## Success Metrics

### By July 2026
- [ ] Blueprint generating swerve frames + elevators + OB intakes (Priority A)
- [ ] Antenna posting weekly CD digests to Discord
- [ ] Driver station mapping and dashboard locked

### By September 2026
- [ ] All 12 Blueprint templates generating correctly
- [ ] Scout pre-event reports generating from TBA/Statbotics
- [ ] Whisper showing recommendations from simulated matches
- [ ] Eye processing at least one full offseason event

### By December 2026
- [ ] Full kickoff workflow validated end-to-end (past game dry run)
- [ ] All 10 systems operational
- [ ] 8+ months of Antenna intelligence accumulated
- [ ] Pit display + digital twin running
- [ ] Team ready for January 2027 kickoff

---

*Master Roadmap | THE ENGINE | Team 2950 The Devastators*
