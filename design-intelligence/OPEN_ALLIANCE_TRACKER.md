# THE ENGINE — Open Alliance & Team Intelligence Tracker
# Last updated: April 2, 2026
# Source: Chief Delphi Open Alliance Directory, team websites, GitHub, TBA
# ═══════════════════════════════════════════════════════════════════

## How to Use This Document

This is a living index of every team whose public resources feed into
The Engine's prediction engine and design intelligence. Update it after
each competition season with new releases.

On kickoff day: scan the Open Alliance directory for new 2027 entries,
pull the highest-engagement build threads, and feed mechanism choices
into CROSS_SEASON_PATTERNS.md validation.

---

## Tier 1: Permanent Tracked Teams (always monitor)

### Team 254 — Cheesy Poofs (San Jose, CA)
**Why:** The benchmark. Technical binders are the most detailed public FRC documentation.
**2026:** Robot "Overload" — 32-2-0, #3 in CA district. 115 lbs. Scoring Fuel + Tower climb.
**2025:** Robot "Undertow" — Full binder extracted. WCP X2i swerve (13.2 ft/s), 2-stage elevator (52" in 0.3s), roller claw climber (1:224 gearbox), "Flying V" end effector, first year using maple-sim, A*/AD* pathfinding, centralized state machine, 18 motors, 2× Limelight 4.
**Resources:**
- Binders: 2025, 2024, 2023, 2022, 2019, 2018 (all on team254.com + CD threads)
- Code: github.com/Team254 (FRC-2025-Public, FRC-2024-Public, FRC-2022-Public, FRC-2020-Public, FRC-2019-Public, FRC-2018-Public)
- 2022 Strategy Presentation (unique — match strategy methodology)
- Forked maple-sim on GitHub (Feb 2026) — confirms continued sim usage
**Key patterns:** Full-width intake always, swerve since 2022, turret when aiming required, elevator when placing required, climber designed last, AlphaBot for early learning

### Team 118 — Robonauts (Houston, TX)
**Why:** NASA-backed, publishes CAD + code + binders + PCB files. Also runs Everybot (10118) — gives TWO data points per game (top robot + minimum competitive robot).
**2026:** Robot "Artemis" — 63-5-0, won 3 of 4 events.
**2025:** Robot "Firefly" — Code, off-season code, custom PCB files, CAD, Technical Binder all published. Championship Division Winner.
**Resources:**
- Binders: 2025, 2023 (on 118robonauts.org/robots)
- Code: Published for 2025, 2024, 2019, 2018, 2017
- CAD: STEP files + GrabCAD for every year since 2013
- Custom PCB/Avionics files: 2025, 2023 (unique resource — no other top team publishes this)
- Everybot: 118everybot.org (complete build guide for $1500 competitive robot)
**Key patterns:** Everybot delta shows exactly how much complexity buys in performance

### Team 1678 — Citrus Circuits (Davis, CA)
**Why:** Pioneered quantitative scouting. Publishes strategy docs, scouting whitepapers, and 7+ scouting software repos.
**2025:** Robot "Sublime" — CAD, Code, Ghost Coral Intake, Rembrandts Climber, Scouting Whitepaper, Strategy resources all published.
**2024:** Robot "Nik" — CAD, Code, Scouting Whitepaper, Strategy resources published.
**Resources:**
- Release page: citruscircuits.org/cad-code-release
- Scouting repos: Server, Viewer, Kestrel/Grosbeak, Match Collection, Pit Collection, Stand Strategist, Playoffs Scouting
- Strategic Design Workshop PDF (covers pre-season prep through competition strategy)
- Golden Rule #1: "Keep It Simple Silly"
- Robot History: citruscircuits.org (2009-2023 archives)
**Key patterns:** Data-driven scouting, simple mechanism philosophy despite high capability

### Team 6328 — Mechanical Advantage
**Why:** Created AdvantageKit + AdvantageScope. Open Alliance build thread is the transparency standard.
**2026:** Active Open Alliance build thread (listed in directory)
**2025:** World-class build thread, daily code pushes, maple-sim integration
**Resources:**
- Build threads on CD (yearly, detailed weekly updates)
- Code: Published daily during season
- AdvantageKit template projects (Spark Swerve, Talon Swerve)
- Conference presentations on logging, simulation, replay
**Key patterns:** Simulation-first development, replay-based debugging, transparency as competitive strategy

### Team 3847 — Spectrum (Houston, TX)
**Why:** Most detailed build blog in FRC. Publishes complete design guidelines, "Don't Do" list, and 4-phase build process.
**2026:** Active build blog (73.5k views, 3.3k likes). Robot plan: AM → XM → PM → FM (4 phases).
**Resources:**
- Build blog: CD thread (yearly since 2012)
- Design guidelines: Complete materials, fasteners, electronics, swerve, power transmission standards
- "Don't Do" list: 15+ learned mistakes codified as rules
- Conference presentations: Maximizing Week 1, Robot Architecture, Prototyping
- CAD Collection: ~850 links to FRC CAD models across all teams
- Swerve Guide, Cart Guide, Tool Guide
**Key patterns:** "No pneumatics" (2026), MK5n swerve, 4-phase build with designed-in redesign time, "Don't chase magic numbers"

### Team 2056 — OP Robotics (Stoney Creek, Ontario, Canada)
**Why:** Engineering drawing-quality technical binders. Full CAD drawing packages with revision history. Detailed Q&A on manufacturing techniques.
**2025:** Robot "Lightning" — Binder + full drawing package. Arm + elevator reaching 80" in 0.5s. Gas shocks in over-center toggle.
**2024:** Robot "Low-Key" — Binder + drawing package. Zero-backlash gearbox with Loctite 609.
**2023:** Robot "Uppercut" — Binder + STL swerve covers. Phoenix Pro time-sync for odometry.
**Resources:**
- Binders: 2025, 2024, 2023 (PDFs on 2056.ca)
- CAD drawing packages with revision designations (R1, R2, etc.)
- CD Q&A threads with detailed manufacturing and assembly techniques
**Key patterns:** Loctite 609 for zero-backlash fits, custom-broached sprockets, reinforcement plates at pivot stress points, timed-based (not command-based) programming

### Team 1323 — MadTown Robotics (Madera, CA)
**Why:** 2025 World Champions. Tech binder has 53.9k views and 2.5k likes.
**2025:** World Champions (with 2910). Tech binder published. Credited 3847 Spectrum for intake design, 2910 for climbing mechanism.
**Resources:**
- 2025 Tech Binder (PDF linked from CD thread)
- CD reveal thread with detailed Q&A
**Key patterns:** Passive coral centering intake, dual-purpose mechanisms (algae intake repurposed as climb latch), weight-critical design (4-5 lbs per mechanism), students solve problems independently, X2T swerve modules

### Team 4414 — HighTide
**Why:** Defined the "small, fast, rigid" robot archetype. Referenced by 254 as a benchmark.
**Key patterns:** Maximize weight for traction, simple mechanisms at highest execution level, acceleration > top speed, score at highest-VALUE level fastest (not highest physical level)

### Team 2910 — Jack in the Bot
**Why:** Swerve pioneers, strong competitive results, collaborated with 1323 on 2025 climbing mechanism.
**2025:** Robot "Spectre" — Started with SDS MK4i, upgraded to MK5 mid-season. Dual-purpose end effector.
**Key patterns:** Mid-season hardware upgrades, swerve module evolution (MK4i → MK5)

### Team 1690 — Orbit (Binyamina, Israel)
**Why:** Most sophisticated software automation in FRC. 2024 World Champions. Proves software ceiling.
**2025:** Robot "Whisper" — Custom swerve, 3-stage differential elevator with carbon fiber arm, vacuum end effector with separate Coral/Algae sealing elements.
**Key patterns:** Lost 2025 Einstein to simpler/faster 1323+2910. Proves execution speed > software sophistication. Vacuum end effectors viable for precision placement.

### Team 1114 — Simbotics (Ontario, Canada)
**Why:** Legendary team with public code releases spanning 2015-2025. Published Simbot-Base template and scouting platform.
**Resources:**
- Code: github.com/simbotics (14 repos, 2015-2025)
- Simbot-Base: Template robot with utilities (equivalent to a starter scaffold)
- Scouting-Platform-Mobile (Dart)
- 2025 code: Suzuki (in-season), CMD-Public (offseason), Drive-Template-Public
**Key patterns:** Consistent naming convention, template-based approach, scouting app ecosystem

### Team 973 — Greybots (Atascadero, CA)
**Why:** Published subsystem-examples repo (reusable generic subsystem code). Switched C++ → Java in 2023.
**Resources:**
- Code: github.com/team973 (19 repos, 2010-2025)
- subsystem-examples: Generic reusable subsystem code
- greyscout: Vue.js scouting app
**Key patterns:** C++ to Java migration mirrors community trend, subsystem abstraction

### Team 2826 — Wave Robotics
**Why:** Published the YOLOv11n fuel detection model The Engine uses. Active Open Alliance participant.
**2026:** Active Open Alliance build thread
**Resources:**
- YOLO model: wave_fuel_detector.onnx (2.59M params, single class, 10.1 MB)
- GitHub: github.com/WaveRobotics (published during season)
**Key patterns:** Neural network models published for community use, SnapScript integration

---

## Tier 2: 2026 Open Alliance — High-Value Threads to Monitor

These teams are publishing detailed build threads for the 2026 REBUILT season.
Monitor weekly during build season for mechanism choices and design rationale.

| Team | Name | Build Thread | Notable Resources |
|------|------|-------------|-------------------|
| 157 | Aztechs | CD thread | OnShape CAD |
| 525 | Swartdogs | CD thread | GitHub, YouTube |
| 900 | Zebracorns | CD thread | Long-running OA participant |
| 1540 | Flaming Chickens | CD thread | GitHub, maintains frc-software-releases list |
| 3061 | Huskie Robotics | CD thread | GitHub, published AdvantageKit swerve template |
| 3284 | LASER | CD thread | GitHub, YouTube |
| 4481 | Team Rembrandts | CD thread | GrabCAD, GitHub (Netherlands) |
| 4590 | GreenBlitz | CD thread | GitHub (Israel, strong software) |
| 5987 | Galaxia | CD thread | GitHub (Israel, strong software) |
| 7407 | Wired Boars | CD thread | GitHub |
| 7461 | Sushi Squad | CD thread | OnShape, GitHub, team website |

Full directory: 60+ teams listed at
https://www.chiefdelphi.com/t/2026-frc-open-alliance-information-and-directory/508112/2

---

## Resource Index — Direct Links

### Technical Binders (PDF)
- 254 2025 Undertow: CD thread (PDF linked in first post)
- 254 2024 Vortex: CD thread
- 254 2023 Breakdown: CD thread
- 254 2022 Sideways: CD thread + Strategy Presentation
- 2056 2025 Lightning: https://2056.ca/wp-content/uploads/2025/05/OPR25-2056-Technical-Binder.pdf
- 2056 2024 Low-Key: https://2056.ca/wp-content/uploads/2024/05/OPR24-2056-Technical-Binder.pdf
- 1323 2025: CD thread (PDF linked)
- 118 2025 Firefly: 118robonauts.org/robots
- 118 2023 Echo: 118robonauts.org/robots

### Code Releases (GitHub)
- 254: github.com/Team254 (2018-2025)
- 118: Published per-season on robonauts website
- 1678: github.com/frc1678 (scouting + robot code)
- 6328: Published daily during season
- 1114: github.com/simbotics (2015-2025)
- 973: github.com/team973 (2010-2025)
- 2826: github.com/WaveRobotics

### Strategy & Process Documents
- 1678 Strategic Design Workshop: citruscircuits.org/uploads strategic_design_2022.pdf
- 1678 Scouting Whitepapers: citruscircuits.org/cad-code-release
- 3847 Design Guidelines: 2026 build blog first post
- 3847 "Don't Do" List: 2026 build blog first post
- 3847 Conference Presentations: Maximizing Week 1, Robot Architecture, Prototyping
- 254 2022 Strategy Presentation: CD thread

### CAD Collections
- 3847 FRC CAD Collection: ~850 links (spectrum3847.org)
- 118 GrabCAD: All robots since 2013
- 2056 Drawing Packages: Engineering drawings with revision history

---

## Update Schedule

| Period | Action |
|--------|--------|
| Kickoff day | Scan Open Alliance directory for new entries, pull mechanism choices from top threads |
| Weekly during build season | Check top 10 OA threads for design updates, rejected designs, pivots |
| After each competition week | Pull match results from TBA for tracked teams, note any mid-season redesigns |
| Post-season (May-June) | Collect binder releases, code releases, CD Q&A threads |
| Offseason (July-September) | Pull Chezy Champs and other offseason event data, update pattern rules |
| Pre-kickoff (December) | Verify all tracked team resources are current, prepare KICKOFF_TEMPLATE.md |

---

## Intelligence Quality Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Permanently tracked teams | 13 | 15-20 |
| Teams with full binder extraction | 4 (254, 118, 1690, 3847) | 8+ |
| Teams with code analysis | 3 (254, 1114, 973) | 6+ |
| Cross-season patterns formalized | 15 rules + 5 meta-rules | 20+ rules |
| Open Alliance threads monitored | 60+ (2026) | All active |
| Statbotics EPA data pulled | Not yet | All tracked teams, 8 seasons |
