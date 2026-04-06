# THE ENGINE — Master Roadmap
# Prioritized Execution Plan
# Updated: April 2026
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Guiding Principle

Build what compounds first. Every system that feeds other systems gets
built before systems that stand alone. Every system that can be tested
in simulation gets built before systems that need hardware or events.

---

## The 10 Engine Systems

| # | Codename | System | Hours | Hardware Cost |
|---|----------|--------|-------|---------------|
| 1 | The Vault | Parts Inventory | 12h | $0 |
| 2 | The Grid | Electrical Standards | 18h | $0 |
| 3 | The Antenna | Chief Delphi Watcher | 32h | $0 |
| 4 | The Clock | Build Management | 30h | $0 |
| 5 | The Cockpit | Driver Station | 39h | $0 |
| 6 | The Scout | Scouting System | 54h | $0 |
| 7 | The Pit Crew | Pit Operations | 60h | $0 |
| 8 | The Whisper | Coach AI | 38h | ~$390 |
| 9 | The Eye | AI Match Analysis (Lite) | 60-80h | $0 |
| 10 | The Blueprint | CAD Pipeline (Lite) | 55-70h | $0 |
| | | **TOTAL** | **398-433h** | **~$390** |

---

## Priority Tiers

### TIER 1: Build Before Kickoff (Summer-December 2026)
*These create the foundation everything else depends on.*

| Priority | System | Why First | Blocks | Target |
|----------|--------|-----------|--------|--------|
| **1** | **The Vault** (12h) | Every other system references inventory. The Clock needs it for parts tracking. The Blueprint needs it for BOM cross-referencing. Without it, kickoff day ordering is guesswork. | V.1-V.3 | **Summer 2026** |
| **2** | **The Grid** (18h) | Pre-built wiring harnesses save 20+ hours during build season. Must be done before you need them. Inspection checklist prevents competition failures. | E.1-E.6 | **Summer 2026** |
| **3** | **The Antenna** (32h) | Starts feeding intelligence into The Engine immediately. By kickoff, you'll have 6 months of Chief Delphi intelligence accumulated. The longer it runs, the more valuable it gets. | AN.1-AN.7 | **Summer 2026** |
| **4** | **The Clock** (30h) | Auto-generates the 6-week build plan on kickoff day. If this isn't ready, the plan is manual. Needs The Vault for parts cross-referencing. | CL.1-CL.3 | **December 2026** |
| **5** | **The Cockpit D.1-D.3** (11h) | Controller mapping, dashboard layout, and console hardware standard. Documentation + physical setup — no code. Must be locked before driver practice starts. | D.1-D.3 | **December 2026** |

**Tier 1 total: 103 hours, $0 cost**
**Result: On kickoff day, you have inventory, wiring harnesses, 6 months of CD intelligence, auto-generated build plan, and standardized driver station.**

---

### TIER 2: Build During Early Build Season (January-February 2027)
*These make the team faster during build season.*

| Priority | System | Why Now | Blocks | Target |
|----------|--------|---------|--------|--------|
| **6** | **The Scout S.1-S.3** (28h) | Pre-event report generator + pit question generator + stand scouting form. Must be ready before first event. Layer 1 (automated) is the highest ROI — replaces 80% of pit scouting. | S.1-S.3 | **January 2027** |
| **7** | **The Cockpit D.4** (12h) | Driver practice analytics. The earlier this runs, the more practice data you accumulate. Every session from week 2 onward is tracked. | D.4 | **January 2027** |
| **8** | **The Pit Crew P.1-P.3** (12.2h) | Robot Reports channel (10 min), pre-match checklist (4h), post-match diagnostics (8h). P.1 is literally 10 minutes. Start it immediately. P.2-P.3 needed before first event. | P.1-P.3 | **February 2027** |
| **9** | **The Blueprint B.1-B.2** (26h) | API setup + swerve frame generator. The swerve frame is the same every year — build this template once and reuse forever. Run it on kickoff day 2027 even if B.3-B.5 aren't ready. | B.1-B.2 | **February 2027** |

**Tier 2 total: 78 hours, $0 cost**
**Result: Scouting operational, driver improving with data, pit crew running diagnostics, swerve CAD auto-generating.**

---

### TIER 3: Build Before First Competition (March 2027)
*These give you a competitive edge at events.*

| Priority | System | Why Now | Blocks | Target |
|----------|--------|---------|--------|--------|
| **10** | **The Scout S.4-S.6** (26h) | Alliance selection advisor + Monte Carlo sim + Whisper integration. The alliance pick is the single highest-leverage decision at an event. Data-informed picks win championships. | S.4-S.6 | **Before first event** |
| **11** | **The Whisper** (38h) | Coach AI on driver station. Needs Jetson Orin Nano ($249) + monitor ($55). Order hardware in January, build in February, test in March. Nobody in FRC has this. | W.1-W.7 | **March 2027** |
| **12** | **The Cockpit D.5** (16h) | Drive coach information system. If The Whisper isn't ready, this is the fallback — phone/tablet showing strategy recommendations from existing AutonomousStrategy code. | D.5 | **March 2027** |
| **13** | **The Pit Crew P.4** (12h) | Wear tracking. By your first event, you want to be counting mechanism cycles. The data compounds — by event 3, you have real failure predictions. | P.4 | **March 2027** |

**Tier 3 total: 92 hours, ~$390 cost**
**Result: Data-driven alliance selection, AI coach on driver station, wear tracking active, full pit diagnostics.**

---

### TIER 4: Build During/After Competition Season (April-September 2027)
*These refine your competitive edge and prepare for next year.*

| Priority | System | Why Now | Blocks | Target |
|----------|--------|---------|--------|--------|
| **14** | **The Eye E.1-E.2** (50h) | Proof of concept + event-scale processing. Process your own events first. If Roboflow has a good FRC dataset, E.1 drops to ~12 hours. | E.1-E.2 | **April-May 2027** |
| **15** | **The Pit Crew P.5-P.6** (36h) | Pit display dashboard + digital twin. Judge wow factor. Build after first event when you know what data matters. | P.5-P.6 | **Before second event** |
| **16** | **The Blueprint B.3-B.5** (44h) | Elevator + intake templates + BOM export. Build during offseason when there's time to iterate. Ready for kickoff 2028. | B.3-B.5 | **Summer 2027** |
| **17** | **The Eye E.3-E.4** (30h) | Scout integration + dashboard. Process opponents' previous events before your later events. | E.3-E.4 | **Summer 2027** |

**Tier 4 total: 160 hours, $0 cost**
**Result: Full system operational. AI video analysis, complete CAD pipeline, pit display with digital twin.**

---

## Execution Calendar

```
═══════════════════════════════════════════════════════════════════

SUMMER 2026 (June-August)                    TARGET: 62 hours
├── The Vault: full shop audit + inventory sheet (V.1-V.3)
├── The Grid: wiring standards + harnesses + checklist (E.1-E.6)
└── The Antenna: CD scraper + scoring + Discord digest (AN.1-AN.6)

FALL 2026 (September-December)               TARGET: 41 hours
├── The Antenna: LLM summarization (AN.7)
├── The Clock: task generator + standup bot + parts tracker (CL.1-CL.3)
└── The Cockpit: controller mapping + dashboard + console (D.1-D.3)

KICKOFF DAY (January 2027)                   ← YOU ARE HERE
│   Run prediction engine → Run The Clock → Run The Vault cross-ref
│   → Order parts → Teams assigned by hour 4
│
├── The Scout: pre-event report + pit questions + forms (S.1-S.3)
├── The Cockpit: driver practice analytics (D.4)
├── The Pit Crew: Robot Reports + checklist + diagnostics (P.1-P.3)
└── The Blueprint: API setup + swerve frame generator (B.1-B.2)

FEBRUARY 2027                                TARGET: 78 hours
├── The Scout: alliance advisor + Monte Carlo (S.4-S.5)
├── The Whisper: hardware + software + testing (W.1-W.7)
└── The Pit Crew: wear tracking (P.4)

MARCH 2027 (FIRST EVENT)                     TARGET: 54 hours
├── The Scout: Whisper integration (S.6)
├── The Cockpit: coach info system (D.5)
└── Deploy everything. Compete.

APRIL-MAY 2027                               TARGET: 86 hours
├── The Eye: proof of concept + event processing (E.1-E.2)
├── The Pit Crew: pit display + digital twin (P.5-P.6)
└── Process your own event data through The Eye

SUMMER 2027                                  TARGET: 74 hours
├── The Blueprint: elevator + intake templates + BOM (B.3-B.5)
├── The Eye: Scout integration + dashboard (E.3-E.4)
└── Everything ready for kickoff 2028

═══════════════════════════════════════════════════════════════════
```

---

## Dependency Map

```
                    ┌─────────────┐
                    │  Prediction  │
                    │   Engine     │
                    │  (EXISTS)    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
      ┌──────────┐ ┌──────────┐ ┌──────────┐
      │The Clock │ │  The     │ │  The     │
      │(tasks)   │ │Blueprint │ │ Cockpit  │
      └────┬─────┘ │(CAD)     │ │(driver)  │
           │       └────┬─────┘ └────┬─────┘
           │            │            │
           ▼            ▼            │
      ┌──────────┐ ┌──────────┐     │
      │The Vault │ │BOM Export │     │
      │(parts)   │◄┤          │     │
      └──────────┘ └──────────┘     │
                                    │
      ┌──────────┐                  │
      │The Grid  │                  │
      │(wiring)  │──────────────────┘
      └──────────┘        (harnesses ready for build)

      ┌──────────┐     ┌──────────┐     ┌──────────┐
      │The       │────►│The Scout │────►│The       │
      │Antenna   │     │(scouting)│     │Whisper   │
      │(CD intel)│     └────┬─────┘     │(coach AI)│
      └──────────┘          │           └──────────┘
                            │
                    ┌───────▼──────┐
                    │   The Eye    │
                    │(video intel) │
                    └──────────────┘

      ┌──────────┐
      │The Pit   │  (standalone — reads AdvantageKit logs)
      │Crew      │
      └──────────┘
```

---

## What Compounds

These systems get better over time. Starting them early is critical:

| System | Compound Effect |
|--------|----------------|
| **The Antenna** | 6 months of CD intelligence by kickoff. 12 months by first event. Every week adds to the knowledge base. |
| **The Vault** | Consumption data from one season predicts next season's orders. |
| **The Pit Crew P.1** | Robot Reports from one event inform pre-inspection at the next. After 3 events, you have a real reliability database. |
| **The Eye** | More events processed = more accurate team profiles. By playoffs, you've analyzed 200+ matches. |
| **D.4 Practice Analytics** | 30 practice sessions of data shows exactly where the driver improved and what still needs work. |
| **The Blueprint** | Templates improve annually. Year 2 kickoff is even faster than Year 1. |

---

## Quick Wins (Do This Week)

These take less than 2 hours each and create immediate value:

| # | Action | Time | Impact |
|---|--------|------|--------|
| 1 | Create #robot-reports channel on Discord/Slack (P.1) | 10 min | Starts reliability database |
| 2 | Print wiring standards card (E.1) — laminate, post in shop | 30 min | Every student wires correctly |
| 3 | Set up The Vault Google Sheet with 6 inventory tabs | 1 hour | Ready for shop audit |
| 4 | Print controller mapping card (D.1) — tape to driver station | 30 min | Driver never looks down |
| 5 | Order Jetson Orin Nano Dev Kit ($249) — lead time matters | 10 min | Hardware arrives when you need it |

---

## Budget

| Item | Cost | When to Buy |
|------|------|-------------|
| Jetson Orin Nano 8GB Dev Kit | $249 | January 2027 (lead time) |
| 7" HDMI IPS monitor | $55 | January 2027 |
| HDMI cable (3ft) | $8 | January 2027 |
| Ethernet cable (3ft) | $5 | January 2027 |
| USB-C PD power bank (65W) | $40 | January 2027 |
| USB-C PD cable (1ft) | $8 | January 2027 |
| 3D-printed Jetson enclosure | $5 | February 2027 |
| 8-port Ethernet switch | $20 | If not already owned |
| **TOTAL** | **~$390** | |

Everything else is free: OnShape edu license, Roboflow free tier,
open source libraries, Google Sheets, Discord webhooks.

---

## Success Metrics

### By Kickoff 2027
- [ ] Full shop inventory completed (The Vault)
- [ ] 4 swerve wiring harnesses pre-built (The Grid)
- [ ] 6 months of CD intelligence accumulated (The Antenna)
- [ ] Build plan auto-generated within 30 minutes of game reveal (The Clock)
- [ ] Parts ordered within 4 hours of kickoff (The Vault + The Clock)

### By First Event 2027
- [ ] Pre-event scouting report generated for all teams (The Scout)
- [ ] Driver practice analytics showing improvement curves (The Cockpit)
- [ ] Pre-match checklist operational (The Pit Crew)
- [ ] Post-match diagnostic reports auto-generated (The Pit Crew)

### By End of Season 2027
- [ ] AI coach deployed on driver station (The Whisper)
- [ ] Data-informed alliance selection at every event (The Scout)
- [ ] Video analysis of at least one full event (The Eye)
- [ ] Parametric swerve frame + elevator + intake templates ready (The Blueprint)
- [ ] All 10 systems operational for kickoff 2028

---

*Master Roadmap | THE ENGINE | Team 2950 The Devastators*
