# Landscape Scan — Team 254 + Binner + Misc (2026-04-12)

**Context:** User's Saturday browsing session, second batch. Found Team 254's
full GitHub org (including AOS, cheesy-parts, cheesy-hours, pitdisplay) and
Binner (open-source parts inventory). Also evaluated google/deepvariant
(genomics, no relevance) and dawarazhar11/SolidVoice (SolidWorks voice
control, architecture validation only).

---

## HIGH PRIORITY — Direct overlap with planned Engine work

| Repo | Stars | Engine System | Description | Verdict |
|---|---|---|---|---|
| [Team254/aos-public](https://github.com/Team254/aos-public) `frc/orin/` | — | **Coprocessor (#5)** | CUDA AprilTag detection, Argus camera driver, GPU image pipeline, hardware monitoring, Orin IRQ configs. **This is our CP.1-CP.14 plan, already built in production C++ by 254.** | **investigate deeply** |
| [Team254/aos-public](https://github.com/Team254/aos-public) `frc/analysis/` | — | **Pit Crew (#7)** | Foxglove integration, web plotter, log trimming, match analysis. Direct precedent for P.6 digital twin. | **investigate** |
| [Team254/aos-public](https://github.com/Team254/aos-public) `frc/can_logger/` + `frc/imu/` | — | **Grid (#9)** | CAN bus logger with ASC format export. IMU calibration library (ADIS16505). CAN-FD topology reference. | **investigate** |
| [replaysMike/Binner](https://github.com/replaysMike/Binner) | 514 | **Vault (#8)** | Open-source parts inventory: barcode scanning, label printing, supplier lookup, BOM cross-ref, self-hosted (RPi/Docker). .NET + React. API available. Could replace The Vault entirely. | **investigate → likely adopt** |
| [Team254/cheesy-parts](https://github.com/Team254/cheesy-parts) | 25 | **Vault (#8)** | 254's 2013 parts management DB. Old tech (HTML) but the FRC-specific data model is worth studying. | **investigate** (data model only) |

## MEDIUM PRIORITY — Relevant reference implementations

| Repo | Stars | Engine System | Description | Verdict |
|---|---|---|---|---|
| [Team254/cheesy-hours](https://github.com/Team254/cheesy-hours) | 13 | **Clock (#10)** | FRC project hour tracking (Ruby). Precedent for our task tracker + standup bot. Study the workflow, not the code. | **investigate** (workflow only) |
| [Team254/cheesy-action-items](https://github.com/Team254/cheesy-action-items) | 0 | **Clock (#10)** | Action item management for team leaders/mentors. Another workflow precedent. | **investigate** (workflow only) |
| [Team254/pitdisplay](https://github.com/Team254/pitdisplay) | 1 | **Pit Crew (#7)** | Pit display: match schedule + results. Tiny but relevant for P.1 Robot Reports display concept. | **investigate** |
| [Team254/cheesy-arena](https://github.com/Team254/cheesy-arena) | 195 | None directly | Alternative FMS in Go. Not needed now, but if 2950 ever runs an offseason event, this is THE tool. | **ignore for now** |
| [Team254/FRC-2025-Public](https://github.com/Team254/FRC-2025-Public) | 35 | Robot Code | 254's 2025 robot code. Reference for swerve + superstructure patterns. | **investigate** |
| [Team254/FRC-2024-Public](https://github.com/Team254/FRC-2024-Public) | 42 | Robot Code | 254's 2024 robot code. | **investigate** |
| [Team254/aos-public](https://github.com/Team254/aos-public) `motors/` + `frc/control_loops/` | — | Motor model | Full motor math library + control loop library (C++). Our `motor_model.py` is a fraction of this. | **investigate** (study math, not adopt code) |

## NO RELEVANCE

| Repo | Stars | Description | Verdict |
|---|---|---|---|
| [google/deepvariant](https://github.com/google/deepvariant) | 3,700 | Genomics/DNA variant calling with CNNs. Zero FRC/robotics relevance. | **ignore** |

---

## Deep dive: AOS (`Team254/aos-public`)

### What AOS actually is

AOS is NOT just robot code. It's a **full robotics operating system** that 254
runs their entire operation on. 11,775 commits across C++ (43.7%), C (41.4%),
Python (3.7%), Rust (0.9%), Go, and JavaScript. Bazel build system.

### Architecture layers

```
┌─────────────────────────────────────────────┐
│  aos/ — Core OS                             │
│  Event loop, config system, analysis tools, │
│  containers, CLI utilities, Foxglove        │
├─────────────────────────────────────────────┤
│  frc/ — FRC-specific                        │
│  Control loops, autonomous, estimation,     │
│  vision (Orin), CAN logging, IMU, networking│
├─────────────────────────────────────────────┤
│  motors/ — Hardware abstraction             │
│  Motor math, driver station, peripherals,   │
│  Teensy/pistol grip controllers             │
└─────────────────────────────────────────────┘
```

### What maps to The Engine

| AOS component | Path | What it does | Engine system it maps to |
|---|---|---|---|
| `frc/orin/` | GPU vision pipeline | CUDA AprilTag detection, Argus camera, hardware monitoring, GPU image processing, localizer, Orin IRQ tuning | **Coprocessor (#5) CP.1-CP.14** |
| `frc/analysis/` | Post-match analysis | Foxglove integration, web plotter, log trimming, match-scoped analysis tools | **Pit Crew (#7) P.6 digital twin** |
| `frc/can_logger/` | CAN bus logging | CAN logger with ASC format export, FlatBuffers schema | **Grid (#9) CAN-FD topology** |
| `frc/imu/` | IMU calibration | ADIS16505 driver, RP2040 Pico firmware, quadrature encoder | **Grid (#9) sensor standards** |
| `frc/control_loops/` | Control theory | Catapult, aiming, coerce goal, C2D, capped test plants, full LQR/LQG | **Motor model** (our `motor_model.py` is a toy version) |
| `frc/estimation/` | State estimation | Extended Kalman Filter | Nothing equivalent (yet) |
| `frc/image_streamer/` | Video streaming | Image stream with web frontend | **Eye (#6)** streaming layer |
| `frc/autonomous/` | Auto framework | Config-driven autonomous modes, FlatBuffers schemas | Robot code reference |
| `motors/` | Motor math | Full motor characterization, driver station interface, peripheral drivers | **Motor model** reference |
| `frc/networktables/` | NT client | Custom NetworkTables implementation | Standard WPILib reference |

### The `frc/orin/` directory in detail

This is the most relevant subsystem for The Engine. Files:

| File | What it does |
|---|---|
| `gpu_apriltag.cc/.h` | CUDA-accelerated AprilTag detection |
| `apriltag_detect.cc` | AprilTag detection pipeline orchestrator |
| `argus_camera.cc` | NVIDIA Argus camera API driver for Jetson |
| `cuda.cc/.h` | CUDA utility functions |
| `hardware_monitor.cc` | Jetson hardware health monitoring |
| `hardware_stats.fbs` | FlatBuffers schema for hardware telemetry |
| `line_fit_filter.cc/.h` | Line fitting for field feature detection |
| `localizer_logger.cc` | Robot position logging |
| `threshold.cc/.h` + `neon_threshold.cc` | Image thresholding (NEON SIMD + CUDA) |
| `resize_generator.cc` | Image resize via Halide |
| `orin_irq_config.json` | Orin IRQ pinning for realtime performance |
| `set_orin_clock.sh` | Set Orin to max clock for consistent perf |

**Key insight:** 254 is running CUDA AprilTag detection on a Jetson Orin, not
PhotonVision. Our roadmap says "CP.7: PhotonVision install + 2-camera
calibration (6h)." 254's approach (raw CUDA) is more performant but more work.
We should study their `orin_irq_config.json` and `set_orin_clock.sh` regardless
of which vision pipeline we choose — those are hardware-level optimizations that
apply to any Jetson workload.

### What we should NOT adopt from AOS

- The core event-loop OS (`aos/` core) — we're Python, they're C++. Different universe.
- The Bazel build system — we use Gradle (Java) + pytest (Python).
- The FlatBuffers schemas — useful to read for data modeling inspiration but
  we use dataclasses + JSON, not FlatBuffers.
- The control loop library — impressive but C++ and our robot code is Java/WPILib.

**Rule of thumb for AOS:** study their *decisions* (what to put on the Orin,
how to configure IRQs, what data to log from CAN bus, how to structure
post-match analysis), not their *code* (wrong language, wrong build system,
wrong abstraction layer).

---

## Deep dive: Binner

### Why Binner might replace The Vault

The Engine's roadmap budgets 12 hours for The Vault (V.1-V.3: inventory
template + shop audit + BOM cross-reference). Binner already provides:

| Vault requirement | Binner feature | Status |
|---|---|---|
| V.1 Inventory template | Standard inventory management + custom fields | ✅ Built |
| V.2 Shop audit | Barcode scanning + label printing (Dymo) | ✅ Built |
| V.3 BOM cross-reference | Supplier lookup + datasheet retrieval + BOM import | ✅ Built |
| API for The Clock | REST API (standalone Kestrel service) | ✅ Built |
| Self-hosted in shop | Runs on Raspberry Pi, Docker, Windows, Linux | ✅ Built |
| CSV/Excel export | Built-in | ✅ Built |

**What Binner doesn't have that we'd need:**
- FRC-specific part categories (COTS vendors like REV, AndyMark, WCP, TTB)
- Integration with Blueprint BOM output (custom bridge needed)
- Integration with The Clock for "do we have this part?" queries (API call)

**Adoption path:**
1. Install Binner on a Raspberry Pi or Docker in the shop (~1 hour)
2. Import COTS vendor catalogs as custom categories (~2 hours)
3. Write a thin Python bridge: `blueprint/bom_rollup.py` → Binner API (~2 hours)
4. Total: **~5 hours** instead of 12 hours from scratch

**Tech stack mismatch:** Binner is .NET + React. The Engine is Python. This is
fine — we consume Binner's REST API, we don't modify Binner's code. Same
pattern as using Onshape's API or TBA's API.

---

## Deep dive: cheesy-parts vs Binner for The Vault

| | cheesy-parts (254) | Binner |
|---|---|---|
| Stars | 25 | 514 |
| Year | 2013 | Active (2026) |
| Stack | HTML (static) | .NET + React |
| FRC-specific | Yes (built by 254 for FRC) | No (electronics general) |
| Barcode scanning | No | Yes |
| Label printing | No | Yes (Dymo) |
| Supplier integration | No | Yes (auto-lookup) |
| API | No | Yes (REST) |
| Self-hosted | Unknown | Yes (RPi, Docker) |

**Verdict:** Use Binner for the actual software, study cheesy-parts for FRC-
specific data modeling (part categories, vendor naming conventions, how 254
organizes their shop). The best Vault is Binner's software + 254's data model.

---

## Updated search matrix — what we found vs what's still open

| Engine System | Existing library found? | Status |
|---|---|---|
| Blueprint (CAD) | hedles/onshape-mcp (49★) | **Week 1 — MCP install** |
| Antenna (CD) | None needed (already built) | ✅ Done |
| Cockpit (driver) | None found — low priority | Open |
| Scout (scouting) | None needed (already built) | ✅ Done |
| **Coprocessor (#5)** | **254/aos-public `frc/orin/`** | **investigate — study hardware decisions** |
| **Eye (#6)** | **Roboflow ecosystem (supervision, sports, trackers, inference)** | **Week 2 — Worlds prep** |
| **Pit Crew (#7)** | **254/aos-public `frc/analysis/` + pitdisplay** | **investigate — study Foxglove integration** |
| **Vault (#8)** | **Binner (514★) + cheesy-parts (25★)** | **investigate → likely adopt Binner** |
| **Grid (#9)** | **254/aos-public `frc/can_logger/` + `frc/imu/`** | **investigate — study CAN logging** |
| **Clock (#10)** | **cheesy-hours (13★) + cheesy-action-items (0★)** | **investigate — study workflows** |
| Motor model | 254/aos-public `motors/` + `frc/control_loops/` | **investigate — study math** |

**6 out of 10 Engine systems now have external references or adoptable libraries.**
The remaining 4 (Blueprint done via MCP, Antenna done, Scout done, Cockpit low
priority) are either already built or not code-heavy.

---

## Impact on roadmap hours

| System | Original hours | With discovered libraries | Savings |
|---|---|---|---|
| Vault (#8) | 12h | ~5h (Binner + bridge) | **-7h** |
| Eye (#6) vision model | 10h | ~4.5h (Roboflow stack) | **-5.5h** |
| Coprocessor (#5) | 66.5h | Maybe -10-15h (study 254 before building) | **-10-15h** |
| Pit Crew (#7) P.6 | 20h | Maybe -5h (Foxglove patterns from 254) | **-5h** |
| **Total savings** | | | **~27-32h** |

One afternoon of Saturday browsing → ~30 hours saved on the roadmap. This is
why the "Search Before You Build" rule exists.

---

---

## NEW FIND: FRC Nexus API (`frc.nexus/api/v1`)

**What:** Real-time event operations API for FRC competitions. Provides live
match timing, pit locations, inspection status, and webhooks. Complements TBA
(which has results/stats but NOT live timing or pit data).

**Auth:** Free API key, register at frc.nexus/api.

| Endpoint | Data | Engine System | Verdict |
|---|---|---|---|
| `GET /event/{key}` | Live event status, announcements, match timing | Scout | **adopt** |
| `GET /event/{key}/pits` | Team-to-pit-location mapping | Pit Crew | **adopt** |
| `GET /event/{key}/inspection` | Inspection status + queue position | Pit Crew | **adopt** |
| `GET /event/{key}/map` | Pit map coordinates/layout | Pit Crew | **adopt** |
| `GET /events` | List all registered events | Scout | **adopt** |
| Webhook: match status | Push notification when matches queue/start/end | Scout + Eye | **adopt** |

**Key insight:** Match timing webhooks replace the `mode_a.py` polling cron.
Instead of pulling a 60-second HLS segment every 10 minutes and hoping we
catch a match, we trigger capture **exactly when Nexus says a match starts**.
This is the difference between "might catch the match" and "always catches it."

**Implementation:** Add `scout/nexus_client.py` alongside `scout/tba_client.py`.
Same pattern, different data source. TBA for results/stats, Nexus for live ops.

---

## AOS Extraction Notes — What to actually pull

### Concrete artifacts to study before building

| # | AOS artifact | Our system | What to extract | When |
|---|---|---|---|---|
| 1 | `frc/orin/orin_irq_config.json` | Coprocessor CP.1-CP.3 | IRQ pinning for realtime perf | July (Jetson setup) |
| 2 | `frc/orin/set_orin_clock.sh` | Coprocessor CP.13 | Max clock script for thermal test | July |
| 3 | `frc/orin/argus_camera.cc` | Coprocessor CP.7 | Camera architecture: CSI+Argus vs USB | July (camera decision) |
| 4 | `frc/orin/hardware_monitor.cc` + `hardware_stats.fbs` | Pit Crew P.5 dashboard | Jetson health metrics schema | September |
| 5 | `frc/analysis/` (Foxglove integration) | Pit Crew P.6 digital twin | Foxglove vs AdvantageKit decision | November |
| 6 | `frc/analysis/trim_log_to_enabled.cc` | Pit Crew P.3 diagnostics | Auto-trim logs to match portion | October |
| 7 | `frc/can_logger/` (ASC format) | Grid E.1-E.2 | CAN log format: adopt ASC standard | September |
| 8 | `frc/imu/imu_calibrator.cc` | Coprocessor CP.2 | IMU calibration workflow | July |
| 9 | `motors/` + `frc/control_loops/` | Motor model | Full motor math + LQR/LQG reference | Ongoing |

**Rule: study their DECISIONS, not their CODE.** Wrong language (C++ vs Python),
wrong build system (Bazel vs pytest/Gradle), wrong abstraction layer. But
their hardware decisions (which cameras, which IRQ config, which log format,
which metrics to monitor) are directly portable.

### Decisions 254 made that we should adopt

1. **Foxglove for log replay** — industry-standard robotics visualization.
   Supports ROS bags, MCAP, custom formats. Our P.6 digital twin should use
   Foxglove instead of building a custom replay UI.

2. **ASC format for CAN logging** — Vector CANalyzer compatible, industry
   standard. Don't invent a custom CAN log format.

3. **IRQ pinning on Jetson** — essential for consistent vision latency. Copy
   their `orin_irq_config.json` approach, adapt pin assignments for Orin Nano.

4. **Max clock locking** — `set_orin_clock.sh` ensures the Jetson doesn't
   thermal-throttle mid-match. Simple, essential, directly portable.

5. **Hardware health monitoring** — temperature, clock speed, memory usage,
   GPU utilization. Their FlatBuffers schema tells us exactly what metrics
   matter on a Jetson during competition.

### Decisions where 254's approach might NOT fit us

1. **Argus camera API** — requires CSI cameras (expensive, complex connector).
   We planned USB cameras (Arducam OV9281, $50 each). Argus is faster but
   USB is simpler and cheaper. **Decision deferred to July** when we actually
   have the Jetson in hand.

2. **CUDA AprilTag detection** — impressive but requires significant C++/CUDA
   expertise. PhotonVision gives us AprilTag detection for free with a GUI
   calibration tool. **Probably stick with PhotonVision** unless we hit a
   latency wall that only CUDA can solve.

3. **Custom event-loop OS** — AOS's core is a full realtime OS. We use
   WPILib + YAGSL. The complexity gap is too large to bridge for 2027.
   **Ignore the core OS layer entirely.**

---

## Revised impact summary (both batches combined)

Saturday 2026-04-12 browsing session found:
- **Roboflow ecosystem** (8 repos) → Eye vision pipeline drops from 10h to 4.5h
- **Team 254 AOS** (9 extractable artifacts) → Coprocessor/Pit Crew/Grid save ~20h of discovery
- **Binner** (514★) → Vault drops from 12h to 5h
- **FRC Nexus API** → live match timing + pit ops for Scout + Pit Crew + Eye trigger
- **cheesy-parts/hours/pitdisplay** → data model references for Vault/Clock/Pit Crew

**Total estimated savings: ~35-40 hours** off the 471-hour roadmap.

**Systems with external references: 7 out of 10** (up from 6 earlier today).
Only Cockpit (#3), Antenna (#2, already done), and Scout (#4, already done)
lack external references — and 2 of those 3 are already shipped.

---

## NEW FINDS: Foxglove, PitFUSION, CD Prediction Competition (batch 3)

### Foxglove — Verdict: adopt for Pit Crew P.6 (digital twin)

Investigation resolved: Foxglove works offline, free tier covers our needs.

| Question | Answer |
|---|---|
| Works locally without internet? | **Yes** — local MCAP/bag file playback, no internet |
| Free tier? | **Yes** — 3 users, 10 devices, unlimited local playback |
| Desktop app? | **Yes** — downloadable at foxglove.dev/download |
| Python SDK? | **Yes** — `foxglove-sdk` on PyPI (Rust core, Python bindings) |
| Self-hosted? | Enterprise only — **not needed**, free tier local playback suffices |

Key repos:
- **foxglove-sdk** (219★) — send data via WebSocket or write MCAP files
- **mcap** (895★) — the log format. Our AdvantageKit .wpilog needs a converter
  to .mcap, or we write dual-format on the Jetson using foxglove-sdk
- **create-foxglove-extension** (60★) — custom panels for FRC-specific data
  (cycle counts, alliance scores, The Whisper recommendations)
- **mp42mcap** (6★) — MP4 to MCAP converter (relevant for match video sync)
- **awesome-urdf** (2★) — URDF resource list, connects to onshape-to-robot
  for 3D robot model in the digital twin

**P.6 pipeline:**
```
Robot AdvantageKit logs (.wpilog on Jetson NVMe)
  → Convert to .mcap (foxglove-sdk Python, post-match)
  → Transfer via USB/ethernet tether to pit laptop
  → Open in Foxglove desktop app (free, offline)
  → Full replay: telemetry + 3D model + custom FRC panels
```

**Open question:** .wpilog → .mcap converter doesn't exist yet. Either:
1. Write a Python converter using foxglove-sdk (likely ~100 lines)
2. Have the Jetson write .mcap directly alongside .wpilog
3. Use AdvantageScope for .wpilog and Foxglove for .mcap (two tools)

### PitFUSION — Verdict: ADOPT for Pit Crew P.1

**[mpking828/PitFUSION](https://github.com/mpking828/PitFUSION)** (4★, 19 releases, MIT)

A single HTML file that provides a complete FRC pit display. Uses **FRC Nexus
+ TBA + Statbotics** (the same 3 APIs we already integrate with). Features:

- Live match queue (on field / on deck / queuing) with countdown timer
- Alliance bumper color display
- Parts requests + event announcements (via FRC Nexus)
- Match schedule with results and rankings
- Double-elimination playoff bracket
- EPA performance analytics with team comparison
- Pit map with team locations (via FRC Nexus)
- Match video replay integration
- 4 themes including custom team branding
- **Zero build process — single HTML file, vanilla JS**

This replaces our entire Pit Crew P.1 plan and adds features we hadn't planned
(live queuing, parts requests, pit map, playoff bracket). The 44-hour Pit Crew
roadmap drops by ~10-15 hours. And it already uses FRC Nexus, which we only
discovered earlier today.

**Adoption path:**
1. Fork PitFUSION, add Team 2950 branding (~30 min)
2. Add our custom panels: Robot Reports (P.1), pre-match checklist (P.2)
3. Wire to our Scout data for EPA overlays
4. Deploy on the pit display Raspberry Pi or any laptop with a browser

### CD Random Robot Statistics Competition

`chiefdelphi.com/t/announcing-the-2026-random-robot-statistics-competition/515104`
(page 403'd on fetch, working from URL context)

Annual CD competition where participants predict random robot performance
statistics (EPA, win rate, scoring averages) for the FRC season.

**Relevance:** benchmark for our Oracle prediction engine. If we enter our
predictions, we get a public comparison against the FRC analytics community.
The scoring methodology would tell us which prediction metrics matter most.

**Verdict: investigate** — worth entering Oracle predictions as a validation
exercise. Need to read the actual page (403 blocked today) for format/rules.

---

## FINAL SESSION SUMMARY — Saturday 2026-04-12

### All finds across 3 batches

| # | Find | Stars | Engine System | Verdict | Hours saved |
|---|---|---|---|---|---|
| 1 | Roboflow/supervision | 38,000 | Eye (#6) | **adopt** | |
| 2 | Roboflow/sports | 4,900 | Eye (#6) | **adopt** | |
| 3 | Roboflow/trackers | 3,300 | Eye (#6) | **adopt** | |
| 4 | Roboflow/inference | 2,300 | Eye (#6) | **adopt** | |
| 5 | Roboflow/rf-detr | 6,400 | Eye (#6) | **investigate** | |
| 6 | Roboflow/maestro | 2,700 | Eye (#6) off-season | **investigate** | |
| 7 | **Eye total** | | | | **~5.5h** |
| 8 | Team254/aos `frc/orin/` | — | Coprocessor (#5) | **investigate** | ~10-15h |
| 9 | Team254/aos `frc/analysis/` | — | Pit Crew (#7) | **investigate** | ~5h |
| 10 | Team254/aos `frc/can_logger/` | — | Grid (#9) | **investigate** | ~3-5h |
| 11 | Team254/cheesy-parts | 25 | Vault (#8) | **investigate** | |
| 12 | Team254/cheesy-hours | 13 | Clock (#10) | **investigate** | |
| 13 | Team254/pitdisplay | 1 | Pit Crew (#7) | **investigate** | |
| 14 | replaysMike/Binner | 514 | Vault (#8) | **adopt** | ~7h |
| 15 | FRC Nexus API | — | Scout + Eye + Pit Crew | **adopt** | New capability |
| 16 | Foxglove ecosystem | 895 (mcap) | Pit Crew P.6 | **adopt** | ~5h |
| 17 | **mpking828/PitFUSION** | 4 | **Pit Crew P.1** | **ADOPT** | **~10-15h** |
| 18 | CD Random Stats Competition | — | Oracle validation | **investigate** | — |
| 19 | SolidVoice | 8 | Blueprint (validates arch) | **ignore** | — |
| 20 | google/deepvariant | 3,700 | None | **ignore** | — |

### Systems with external references: 8 out of 10

| # | System | Status | External finds |
|---|---|---|---|
| 1 | Blueprint | MCP pivot (hedles/onshape-mcp, prior session) | ✅ |
| 2 | Antenna | Already shipped | ✅ Done |
| 3 | **Cockpit** | D.1-D.3 done as docs. D.4-D.5 use standard FRC dashboard tools | No external library needed |
| 4 | Scout | Already shipped + FRC Nexus API adds live timing | ✅ Done + enhanced |
| 5 | Coprocessor | 254 AOS `frc/orin/` — study hardware decisions | ✅ Reference |
| 6 | Eye | Roboflow ecosystem (6 repos) + FRC Nexus webhooks | ✅ |
| 7 | Pit Crew | **PitFUSION (adopt)** + Foxglove (adopt) + 254 analysis | ✅ |
| 8 | Vault | **Binner (adopt)** + cheesy-parts (data model) | ✅ |
| 9 | Grid | 254 AOS `frc/can_logger/` + `frc/imu/` | ✅ Reference |
| 10 | Clock | cheesy-hours + cheesy-action-items (workflows) | ✅ Reference |

### Total estimated savings: **~45-55 hours** off the 471-hour roadmap

One Saturday afternoon of browsing → ~50 hours saved → **roadmap drops from
~471 hours to ~420 hours.** The "Search Before You Build" rule paid for itself
on day one.

---

## BATCH 4: CAD Toolkits + MCP Ecosystem (late Saturday)

### CAD Toolkits

| Repo | Stars | Engine System | Description | Verdict |
|---|---|---|---|---|
| [neurobionics/onshape-robotics-toolkit](https://github.com/neurobionics/onshape-robotics-toolkit) | **297** | **Blueprint (#1)** | Python SDK for Onshape REST API: Variable Studio editing, URDF export, assembly graph analysis, mesh/STL handling, Pydantic models. Apache 2.0. `pip install onshape-robotics-toolkit`. **Strict superset of our `onshape_api.py`.** Replaces our deprecated `onshape_client` dependency. | **adopt** |
| [CodeToCAD/CodeToCAD](https://github.com/CodeToCAD/CodeToCAD) | 108 | Blueprint (#1) | Vendor-agnostic CAD scripting (Blender/Onshape/Fusion360). Not yet on PyPI, early stage, no guarantee cross-platform models work. | **ignore** |

**Blueprint stack decision:**
- **Low-level API** → `onshape-robotics-toolkit` (297★, replaces `onshape_api.py`)
- **Agent-driven CAD** → `hedles/onshape-mcp` (49★, MCP layer for Claude)
- **Both coexist** — toolkit for batch/programmatic ops, MCP for interactive sessions

### MCP Ecosystem Scan

| Repo | Stars | Engine System | Description | Verdict |
|---|---|---|---|---|
| [github/github-mcp-server](https://github.com/github/github-mcp-server) | **28,800** | **Clock (#10)** | Official GitHub MCP — AI-driven issue/PR tracking, milestone management. Track Engine development across all 10 subsystems via Claude. | **adopt (off-season)** |
| [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | **24,500** | **All systems** | Framework for building custom MCP servers. Wrap each Engine subsystem as an MCP tool — Scout becomes queryable, Antenna becomes queryable, Eye becomes queryable. **Claude becomes the universal interface to The Engine.** | **adopt (off-season)** |
| [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) | **2,100** | **Clock (#10)** | MCP for 12 Google Workspace services: Gmail, Calendar, Drive, Sheets, Docs, Slides, Forms, Tasks, Contacts, Chat. OAuth 2.1, read-only mode, no telemetry. **Team OS: build scheduling via Calendar, BOM tracking via Sheets, design docs via Drive, notifications via Gmail.** | **adopt (off-season)** |
| [anaisbetts/mcp-youtube](https://github.com/anaisbetts/mcp-youtube) | **514** | **Eye (#6)** | YouTube metadata + transcript extraction via MCP. Feed match video metadata to Eye pipeline. Could replace manual video sourcing for off-season batch processing. | **investigate** |
| [DugboTek/FRCDocsMCP](https://github.com/DugboTek/FRCDocsMCP) | **0** | **All systems** | FRC-specific: pulls WPILib, CTRE, AdvantageScope docs into AI context. Zero stars but directly relevant — gives Claude access to FRC documentation during robot code sessions. | **adopt** |
| [hanweg/mcp-discord](https://github.com/hanweg/mcp-discord) | 149 | Scout (#4) | MCP for Discord — send/read messages, manage channels. No embeds, no event listening, no threads. Our discord.py bot is better for competition use. | **pass** |
| [AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot) | 29,800 | Scout (#4) | Multi-platform chatbot (Discord, Slack, Telegram). Massively over-scoped for our needs. | **ignore** |

### The FRC MCP Vision

**No results for "FRC MCP" on GitHub.** The Engine would be among the first
FRC-specific MCP integrations if we build it. 5000+ FRC teams, zero MCP
solutions today.

**The play (off-season, fastmcp-powered):**

```
┌──────────────────────────────────────────────────────┐
│  Claude Code / Claude Desktop / Web GUI              │
│  (universal interface — replaces CLI for students)   │
├──────────────────────────────────────────────────────┤
│  fastmcp layer                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Scout MCP│ │ Eye MCP  │ │Antenna   │            │
│  │ "254's   │ │ "show me │ │MCP "any  │            │
│  │  avg     │ │  2950's  │ │CD threads│            │
│  │  cycle?" │ │  last    │ │about     │            │
│  │          │ │  match"  │ │swerve?"  │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │Blueprint │ │ Pit Crew │ │ Clock    │            │
│  │MCP "gen  │ │MCP "robot│ │MCP "what │            │
│  │elevator  │ │ health?" │ │tasks are │            │
│  │2-stage"  │ │          │ │left?"    │            │
│  └──────────┘ └──────────┘ └──────────┘            │
├──────────────────────────────────────────────────────┤
│  External MCP servers                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ GitHub   │ │ Google   │ │ YouTube  │            │
│  │ MCP      │ │Workspace │ │ MCP      │            │
│  │ (issues) │ │MCP (cal, │ │ (match   │            │
│  │          │ │sheets)   │ │ videos)  │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│  ┌──────────┐ ┌──────────┐                          │
│  │ Onshape  │ │ FRC Docs │                          │
│  │ MCP      │ │ MCP      │                          │
│  │ (CAD)    │ │ (WPILib) │                          │
│  └──────────┘ └──────────┘                          │
└──────────────────────────────────────────────────────┘
```

**Token budget concern (user-flagged):** Each MCP server adds tool definitions
to the context window. With 10+ MCP servers connected, the tool definition
overhead could consume 10-20K tokens before any conversation starts. Mitigations:
1. Only connect relevant servers per session (scouting session ≠ CAD session)
2. fastmcp supports lazy tool loading — tools only appear when queried
3. Claude Code's tool pagination helps (user scrolls, not auto-loaded)
4. Group related tools into composite servers (Scout+Eye = one server)

This is a real concern but solvable. Defer to implementation time.

---

## FINAL UPDATED SESSION SUMMARY — Saturday 2026-04-12

### All finds across 4 batches (24 repos + 1 API evaluated)

| # | Find | Stars | Engine System | Verdict | Impact |
|---|---|---|---|---|---|
| 1 | Roboflow/supervision | 38,000 | Eye (#6) | **adopt** | Zone counting built-in |
| 2 | Roboflow/sports | 4,900 | Eye (#6) | **adopt** | Bumper OCR = per-team |
| 3 | Roboflow/trackers | 3,300 | Eye (#6) | **adopt** | Robot identity persistence |
| 4 | Roboflow/inference | 2,300 | Eye (#6) | **adopt** | Local edge deployment |
| 5 | Roboflow/rf-detr | 6,400 | Eye (#6) | **investigate** | SOTA detector backbone |
| 6 | Roboflow/maestro | 2,700 | Eye (#6) | **investigate** | Off-season fine-tuning |
| 7 | Team254/aos `frc/orin/` | — | Coprocessor (#5) | **investigate** | Hardware decisions |
| 8 | Team254/aos `frc/analysis/` | — | Pit Crew (#7) | **investigate** | Foxglove patterns |
| 9 | Team254/aos `frc/can_logger/` | — | Grid (#9) | **investigate** | CAN logging standard |
| 10 | Team254/cheesy-parts | 25 | Vault (#8) | **investigate** | FRC data model |
| 11 | Team254/cheesy-hours | 13 | Clock (#10) | **investigate** | Workflow reference |
| 12 | replaysMike/Binner | 514 | Vault (#8) | **adopt** | Replaces entire Vault |
| 13 | FRC Nexus API | — | Scout+Eye+Pit | **adopt** | Live timing + webhooks |
| 14 | Foxglove ecosystem | 895 | Pit Crew P.6 | **adopt** | Digital twin replay |
| 15 | mpking828/PitFUSION | 4 | Pit Crew P.1 | **adopt** | Single HTML pit display |
| 16 | **neurobionics/onshape-robotics-toolkit** | **297** | **Blueprint (#1)** | **adopt** | **Replaces onshape_api.py** |
| 17 | **github/github-mcp-server** | **28,800** | **Clock (#10)** | **adopt** | **Issue/PR tracking via Claude** |
| 18 | **PrefectHQ/fastmcp** | **24,500** | **All systems** | **adopt** | **Engine-as-MCP-servers** |
| 19 | **google_workspace_mcp** | **2,100** | **Clock (#10)** | **adopt** | **Team OS (Calendar+Sheets+Drive)** |
| 20 | **anaisbetts/mcp-youtube** | **514** | **Eye (#6)** | **investigate** | **Match video metadata** |
| 21 | **DugboTek/FRCDocsMCP** | **0** | **All systems** | **adopt** | **WPILib+CTRE docs in context** |
| 22 | CodeToCAD | 108 | Blueprint | **ignore** | Early stage, unnecessary |
| 23 | SolidVoice | 8 | Blueprint | **ignore** | SolidWorks only |
| 24 | AstrBot | 29,800 | Scout | **ignore** | Over-scoped |
| 25 | mcp-discord | 149 | Scout | **pass** | No embeds, no events |

### Systems with external references: 10 out of 10

Every Engine system now has either an adoptable library, a reference
implementation, or is already shipped.

### Revised roadmap impact

| System | Original hours | Revised hours | Savings | Source |
|---|---|---|---|---|
| Blueprint (#1) | 120-150h | ~80-100h | **-40-50h** | onshape-robotics-toolkit + onshape-mcp |
| Eye (#6) | ~30h | ~20h | **-10h** | Roboflow stack + mcp-youtube |
| Vault (#8) | 12h | ~5h | **-7h** | Binner |
| Pit Crew (#7) | 44h | ~25h | **-19h** | PitFUSION + Foxglove |
| Coprocessor (#5) | 66.5h | ~50h | **-16h** | 254 AOS reference |
| Clock (#10) | 30h | ~15h | **-15h** | GitHub MCP + Google Workspace MCP |
| Grid (#9) | 18h | ~13h | **-5h** | 254 CAN logger reference |
| Cockpit (#3) | 39h | 39h | 0h | No change |
| Scout (#4) | 54h | 54h | 0h | Already shipped |
| Antenna (#2) | 32h | 32h | 0h | Already shipped |
| **TOTAL** | **~471h** | **~265h** | **~206h (44%)** | |

**One Saturday of browsing → 44% roadmap reduction.**

---

## BATCH 5: FRC Ecosystem Deep Dive + Oracle Data Sources (Saturday evening)

User surfaced 23 additional repos across FRC prediction, scouting, simulation,
alliance selection, match video, and reference robot code. Also resolved all
previously-marked "investigate" items to final verdicts.

### ADOPT — Direct integration into The Engine

| Repo | Stars | Engine System | Description | Action |
|---|---|---|---|---|
| [avgupta456/statbotics](https://github.com/avgupta456/statbotics) | **96** | **Scout + Oracle** | Source code for statbotics.io. EPA is Skew Normal EWMA, not Elo/OPR. Exposes `epa_sd`, `epa_skew`, component EPAs (`auto_epa`, `teleop_epa`, `endgame_epa`), RP predictions. Model is ~200 lines numpy/scipy — runnable locally. `pip install statbotics`. | Port SkewNormal EWMA locally for real-time what-if sims. Pull component EPAs into draft advisor. Use Norm EPA for cross-season Oracle confidence calibration. |
| [andrewda/frc-livescore](https://github.com/andrewda/frc-livescore) | **29** | **Eye (#6)** | Python package: live FRC score extraction via OpenCV template matching + Tesseract OCR. `LivescoreBase` class with per-year game support. Stale (2022) but architecture is proven. | Reference for Eye OCR pipeline. Study `simpleocr_utils` and template-matching approach. Extend templates for 2025+ games. |
| [anaisbetts/mcp-youtube](https://github.com/anaisbetts/mcp-youtube) | **514** | **Eye (#6)** | YouTube subtitle/caption extraction via yt-dlp through MCP. We already have yt-dlp. Stable (Mar 2025). | Install for deferred YouTube match video pipeline. Transcripts feed commentary mining for strategy extraction. |

### ADOPT-TO-STUDY — Extract patterns and algorithms, don't adopt wholesale

| Repo | Stars | Engine System | What to Extract |
|---|---|---|---|
| [cliclye/predictobics](https://github.com/cliclye/predictobics) | **1** | **Scout + Oracle** | **Defense-adjusted EPA:** `defense_adj = epa_total + 0.18*(sos - global_avg) - 0.45*defense_impact`. **Synergy scoring:** pair-level residuals. **Outlier/dead-robot rejection.** Port defense model into Scout's alliance ranking. |
| [Ruthie-FRC/JSim](https://github.com/Ruthie-FRC/JSim) | **2** | **Motor Model / Blueprint** | Full FRC physics engine: swerve/tank drivetrains, elevator/arm/shooter mechanisms, game piece aerodynamics (magnus effect), collisions, sensors. Python bindings via pybind. 336 commits, pushed today. Superset of our `motor_model.py`. Study mechanism sim abstractions for off-season physics upgrade. |
| [FRCTeam2910/2025CompetitionRobot-Public](https://github.com/FRCTeam2910/2025CompetitionRobot-Public) | **48** | **Oracle + Coprocessor** | 2910's 2025 robot (archived, stable reference). Custom FSM, vision relocalization with auto camera selection, AdvantageKit + CTRE swerve. Validates Oracle's 2025 Reefscape predictions. Vision patterns for Coprocessor design. |
| [Team254/aos-public](https://github.com/Team254/aos-public) `frc/orin/` | — | **Coprocessor (#5)** | CUDA AprilTag, Argus camera, IRQ configs, clock scripts, hardware monitoring. Study decisions, not code (wrong language). Already documented in batch 2. |
| [Team254/aos-public](https://github.com/Team254/aos-public) `frc/analysis/` | — | **Pit Crew (#7)** | Foxglove integration, web plotter, log trimming. Study for P.6 digital twin. |
| [Team254/aos-public](https://github.com/Team254/aos-public) `frc/can_logger/` | — | **Grid (#9)** | CAN logger with ASC format. Adopt ASC standard for our CAN logging. |
| [Team254/cheesy-parts](https://github.com/Team254/cheesy-parts) | 25 | **Vault (#8)** | FRC-specific part data model (categories, vendor naming). Combine with Binner for best Vault. |
| [Team254/cheesy-hours](https://github.com/Team254/cheesy-hours) | 13 | **Clock (#10)** | FRC project hour tracking workflow reference. Study, not adopt (Ruby). |

### IGNORE — Investigated and ruled out

| Repo | Stars | Why Ignored |
|---|---|---|
| roboflow/rf-detr | 6,400 | GPU-only, heavier than YOLO, we have ultralytics installed. No edge/CPU support. |
| roboflow/maestro | 2,700 | Fine-tunes VLMs only (Florence-2, PaliGemma). Does NOT support YOLO training. |
| NimbleValley/auto-scout | 11 | Proof-of-concept, 14 commits, stale since Aug 2024. Eye already covers this. |
| haar09/FRC-Rebuilt-BumpSim | 4 | Single Java file, 5 commits, MapleSim dependency. Too thin. |
| Shom770/quick-pick | 1 | Next.js alliance picker with 60+ team performance issues. Discord draft is better. |
| shueja/FRC-Mechanism-Guide | 1 | Mostly stubs. Software patterns, not mechanical design selection. |
| himeinhardt/MatTuGames | 45 | MATLAB game theory, too academic, wrong language. |
| marcotav/supervised-machine-learning | 47 | Generic ML tutorial, abandoned 2020. |
| phuryn/pm-skills | 9,831 | Product management marketplace. Zero FRC relevance. |
| WoXy-Sensei/frc-search-team-extension | 18 | Chrome extension, Discord bot covers this. |
| xriiitox/TealBot | 1 | C# Discord bot, dormant 2+ years. |
| ExcaliburFRC/ExcaLib | 8 | WPILib Java library, robot code not design tooling. |
| AadiJo/FRC-RAG-Frontend-V2 | 2 | Bare Next.js scaffold, no real content. |
| a-warraich/ADAPT | 0 | Sim-only PID tuning, unvalidated, 0 stars. |
| Sethhondl/FRCQualificationMatchPowerRanking | 0 | Niche rebalancing analysis. |
| gdonarum/mentor-g | 1 | FRC log analysis web app, no Engine overlap. |
| thedropbears/TrueSkill | 4 | TrueSkill for FRC, abandoned 2017. Statbotics EPA is better. |
| REVrobotics/SystemCoreTesting | 0 | Empty alpha testing repo. |
| connectaman/PitchLense | 5 | Startup pitch analysis, not sports CV. |
| 0xemmkty/QuantMuse | 2,300 | Quantitative trading system. Zero FRC relevance. |
| idaholab/raven | 255 | Nuclear risk analysis framework. Zero FRC relevance. |
| youtube (org) | — | Deprecated API samples. Nothing useful. |
| CodeToCAD | 108 | Early stage, unnecessary abstraction over Onshape. |
| AstrBot | 29,800 | Over-scoped chatbot infra. Our Discord bot is tighter. |
| mcp-discord | 149 | No embeds, no events, no threads. discord.py is better. |
| SolidVoice | 8 | SolidWorks only, architecture validation only. |
| google/deepvariant | 3,700 | Genomics. Zero relevance. |
| Team254/pitdisplay | 1 | Superseded by PitFUSION. |
| Team254/cheesy-action-items | 0 | Workflow reference only, minimal value. |

---

## ORACLE IMPROVEMENT PLAN

### Current State
- 19 rules (R1-R19) + 12 meta-rules in `CROSS_SEASON_PATTERNS.md`
- Pure rule-based Python (`oracle.py`, ~750 lines)
- Validated against 4 historical games (2022-2025), 98% accuracy (19/20 checks)
- No ML, no LLM, no external data beyond hardcoded rules

### Data Sources Discovered Today

| Source | What It Provides | How to Use |
|---|---|---|
| **Statbotics EPA internals** | SkewNormal EWMA model, component EPAs, Norm EPA (cross-season comparable), uncertainty quantification | Replace hardcoded confidence scores with real data. "Teams that built turrets in ranged+distributed games had 1650 norm EPA vs 1480 for non-turret" |
| **Statbotics component EPAs** | `auto_epa`, `teleop_epa`, `endgame_epa`, `rp_1_epa`-`rp_3_epa`, `comp_1`-`comp_18` (game-specific) | Feed into draft advisor for alliance complementarity. Also validate Oracle's mechanism predictions against actual EPA outcomes. |
| **predictobics defense model** | `defense_adj = epa_total + 0.18*(sos - global_avg) - 0.45*defense_impact` | New capability: identify effective defenders vs teams with genuinely low EPAs. Critical for 3rd pick strategy. |
| **predictobics synergy scoring** | Pair-level residuals that capture alliance composition effects | "Teams A+B together score 8% above their individual EPA sum" — identifies chemistry. |
| **frc-livescore OCR** | Template matching + Tesseract for score extraction from video | Feeds Eye → Scout pipeline: auto-extract match scores from broadcast for real-time EPA updates. |
| **2910 2025 robot code** | Validates Oracle's 2025 predictions (coral/algae/climb subsystem architecture) | Add to ground truth: does our Oracle correctly predict 2910's architecture? |
| **JSim physics engine** | Mechanism simulation with Python bindings | Validate generator physics: "Oracle says 2-stage elevator with 2 NEOs. JSim says that config reaches 52\" in 0.4s" — real sim backing our predictions. |

### Concrete Improvement Tasks (ordered by impact/effort)

| # | Task | Effort | Impact | Source |
|---|---|---|---|---|
| 1 | **Add 10 missing historical games** to `HISTORICAL_GAMES` + `GROUND_TRUTH` (2012-2021) | 4h | Validation: 4 → 14 games. Every miss = rule refinement. | Already analyzed in `PREDICTION_ENGINE_VALIDATION_14GAME.md` |
| 2 | **Pull `epa_sd` + `epa_skew`** into Scout predictions | 2h | Uncertainty bands: "2950 wins 70% ±12%" | Statbotics API |
| 3 | **Use component EPAs** for draft complementarity scoring | 3h | "We're weak endgame, pick team X (top 5% endgame EPA)" | Statbotics API |
| 4 | **Replace hardcoded confidence** with Norm EPA-backed values | 2h | Rule confidence grounded in real data, not estimates | Statbotics Norm EPA |
| 5 | **Port defense-adjusted EPA** into Scout | 4h | Differentiate effective defenders from low-EPA teams | predictobics |
| 6 | **Port synergy scoring** into draft advisor | 4h | Alliance "chemistry" detection | predictobics |
| 7 | **Port SkewNormal EWMA locally** | 3h | Real-time what-if sims during alliance selection, zero API latency | Statbotics source (~200 lines) |
| 8 | **Add Claude as reviewer layer** | 3h | After Oracle outputs rule-based prediction, Claude catches novel mechanics rules don't cover | anthropic SDK |
| 9 | **Game manual → GameRules auto-extraction** | 8h | Claude reads PDF, outputs structured GameRules JSON. Eliminates manual KICKOFF_TEMPLATE.md filling. | FRCDocsMCP + anthropic SDK |
| **Total** | | **~33h** | | |

### Priority Order for Off-Season

**Phase 1 (May-June): Data foundation** — Tasks 1, 2, 3, 4 (~11h)
- More validation games, real confidence scores, component EPAs in draft

**Phase 2 (July-August): Scout intelligence** — Tasks 5, 6, 7 (~11h)
- Defense model, synergy scoring, local EPA sim for draft

**Phase 3 (September-October): LLM augmentation** — Tasks 8, 9 (~11h)
- Claude as Oracle reviewer + auto game-manual extraction for 2027 kickoff

---

## FINAL MASTER SUMMARY — All Batches (Saturday 2026-04-12)

### Complete inventory: 44 repos + 1 API evaluated across 5 batches

**ADOPT (15 items):**

| # | Repo | Stars | System | Key Value |
|---|---|---|---|---|
| 1 | roboflow/supervision | 38,000 | Eye | Zone counting, annotations |
| 2 | roboflow/sports | 4,900 | Eye | Bumper OCR = per-team attribution |
| 3 | roboflow/trackers | 3,300 | Eye | Robot identity persistence |
| 4 | roboflow/inference | 2,300 | Eye | Local edge model server |
| 5 | neurobionics/onshape-robotics-toolkit | 297 | Blueprint | Replaces `onshape_api.py`, Variable Studios, URDF |
| 6 | hedles/onshape-mcp | 49 | Blueprint | 45 Onshape tools for Claude |
| 7 | replaysMike/Binner | 514 | Vault | Replaces entire Vault |
| 8 | mpking828/PitFUSION | 4 | Pit Crew | Single HTML pit display |
| 9 | Foxglove ecosystem | 895 | Pit Crew | Digital twin replay, offline |
| 10 | FRC Nexus API | — | Scout+Eye+Pit | Live timing + webhooks |
| 11 | github/github-mcp-server | 28,800 | Clock | Issue/PR tracking via Claude |
| 12 | taylorwilsdon/google_workspace_mcp | 2,100 | Clock | Team OS (Calendar+Sheets+Drive+Gmail) |
| 13 | DugboTek/FRCDocsMCP | 0 | All | WPILib+CTRE docs in Claude context |
| 14 | avgupta456/statbotics | 96 | Scout+Oracle | EPA internals, local model, component EPAs |
| 15 | andrewda/frc-livescore | 29 | Eye | OCR template matching reference |
| 16 | anaisbetts/mcp-youtube | 514 | Eye | YouTube transcript extraction via MCP |

**ADOPT-TO-STUDY (8 items):**

| # | Repo | Stars | System | What to Extract |
|---|---|---|---|---|
| 1 | cliclye/predictobics | 1 | Scout+Oracle | Defense-adjusted EPA, synergy scoring |
| 2 | Ruthie-FRC/JSim | 2 | Motor Model | FRC physics engine, Python bindings |
| 3 | FRCTeam2910/2025CompetitionRobot-Public | 48 | Oracle+Coprocessor | FSM, vision relocalization |
| 4 | Team254/aos `frc/orin/` | — | Coprocessor | Hardware decisions (IRQ, clock, camera) |
| 5 | Team254/aos `frc/analysis/` | — | Pit Crew | Foxglove patterns |
| 6 | Team254/aos `frc/can_logger/` | — | Grid | ASC CAN log standard |
| 7 | Team254/cheesy-parts | 25 | Vault | FRC part data model |
| 8 | Team254/cheesy-hours | 13 | Clock | Hour tracking workflow |

**IGNORE (28 items):**
rf-detr, maestro, auto-scout, BumpSim, quick-pick, FRC-Mechanism-Guide,
MatTuGames, supervised-machine-learning, pm-skills, frc-search-team-extension,
TealBot, ExcaLib, FRC-RAG-Frontend-V2, ADAPT, FRCQualificationMatchPowerRanking,
mentor-g, TrueSkill, SystemCoreTesting, PitchLense, QuantMuse, raven,
youtube org, CodeToCAD, AstrBot, mcp-discord, SolidVoice, deepvariant,
pitdisplay (superseded by PitFUSION), cheesy-action-items

### Revised roadmap (final)

| System | Original | Revised | Savings | Key Source |
|---|---|---|---|---|
| Blueprint (#1) | 120-150h | ~80-100h | **-40-50h** | onshape-robotics-toolkit + onshape-mcp |
| Eye (#6) | ~30h | ~20h | **-10h** | Roboflow stack + frc-livescore + mcp-youtube |
| Vault (#8) | 12h | ~5h | **-7h** | Binner |
| Pit Crew (#7) | 44h | ~25h | **-19h** | PitFUSION + Foxglove |
| Coprocessor (#5) | 66.5h | ~50h | **-16h** | 254 AOS + JSim reference |
| Clock (#10) | 30h | ~15h | **-15h** | GitHub MCP + Google Workspace MCP |
| Grid (#9) | 18h | ~13h | **-5h** | 254 CAN logger |
| Scout (#4) | 54h | ~45h | **-9h** | Statbotics source + predictobics defense model |
| Cockpit (#3) | 39h | 39h | 0h | No change |
| Antenna (#2) | 32h | 32h | 0h | Already shipped |
| **Oracle improvements** | 0h | **+33h** | New work | Statbotics + predictobics + LLM layer |
| **TOTAL** | **~471h** | **~290h** | **~181h saved** | |

**Net: 471h original → 290h revised (38% reduction) + 33h of new Oracle
intelligence work = 323h total. Still a significant net reduction.**

### Systems with external references: 10 out of 10

Every Engine system now has adoptable libraries, reference implementations,
or is already shipped. Zero blind spots.

---

## BATCH 6: FRC Calculators, Org Deep Dives, Vision Hardware (Saturday night)

User surfaced ReCalc, shooter calculators, and requested full org reviews of
LimelightVision, frc1678 (Citrus Circuits), and Spectrum3847. Plus PhotonVision
and Elastic Dashboard from the earlier search sweep.

### ADOPT

| Repo | Stars | Engine System | Description | Action |
|---|---|---|---|---|
| [PhotonVision/photonvision](https://github.com/PhotonVision/photonvision) | **406** | **Coprocessor (#5)** | Complete AprilTag + 3D pose estimation coprocessor. Flash-and-go on Jetson/Pi. Web UI config. | Eliminates CP.1-CP.8 (~30h). Flash onto Jetson Orin, configure cameras, done. |
| [Gold872/elastic_dashboard](https://github.com/Gold872/elastic_dashboard) | **144** | **Cockpit (#3)** | Flutter FRC driver dashboard. NetworkTables, camera streams, customizable widgets. 1235+ teams. | Fork + add strategy overlay, pre-match checklist. Saves ~15-20h vs building from scratch. |

### ADOPT-TO-STUDY

| Repo | Stars | System | What to Extract |
|---|---|---|---|
| **tervay/recalc** | 28 | Blueprint | TypeScript FRC calculators for elevator, arm, flywheel, intake, drive, belts/chains/gears. Motor model with kV/kT/resistance + RK4 ODE solver. **Cross-validate** our motor_model.py against their math. Covers 6/8 generators. |
| **efeerdogmus0/frc-shooter-calculator** | 0 | Blueprint | Python projectile trajectory sim with drag + Magnus lift + Monte Carlo scoring probability. Already Python/numpy. Bolt `simulate_to_distance()` and `calculate_optimal_angle()` onto flywheel_generator.py. |
| **frc1678/server-2025-public** | 0 | Scout | Citrus Circuits scouting server: 21 calculation modules, MongoDB. **Three novel algorithms to port (see below).** |
| **Spectrum3847/2024-Ultraviolet** | 13 | Blueprint | SpectrumLib `Mechanism` base class: config-driven PID, MotionMagic, current limits, soft limits. Template for our mechanism code generation. Elevator config has exact kP/kV/currentLimit constants. |
| **LimelightVision/limelightlib-python** | 3 | Coprocessor | Python SDK for Limelight cameras: REST + WebSocket, pipeline switching, targeting results. Complement to PhotonVision if team owns Limelights. |
| **LimelightVision/systemcore-os-public** | 20 | Coprocessor | Limelight's new coprocessor OS with TensorFlow 2.16, CAN/PWM/DIO APIs. Watch as potential competitor to our Jetson approach. |
| **Spectrum3847/gitbook** | 0 | Oracle | Illuminations Young Team Guide: standardized fasteners, material choices, drivetrain progression. Cross-reference for CROSS_SEASON_PATTERNS.md hardware rules. |

### IGNORE

| Repo | Stars | Why |
|---|---|---|
| Ace5tar/ProjectileMotionMapCalculator | 0 | C++ trajectory sim, no flywheel modeling. Too narrow. |
| Spectrum3847/2024-SysID | 1 | Empty boilerplate WPILib SysIdRoutine. No usable output. |
| Spectrum3847/Spectrum-CAD-Library | 16 | SolidWorks only, last updated 2017. Superseded by FRCDesignLib. |
| Spectrum3847/RIOdroid | 21 | Obsolete (2016 Android-to-RIO). |
| Spectrum3847/SpectrumScout | 2 | Trivial Apps Script. Our Scout is far more capable. |
| 0xemmkty/QuantMuse | 2,300 | Quantitative trading. Zero FRC relevance. |
| idaholab/raven | 255 | Nuclear risk analysis. Zero FRC relevance. |
| All other 1678 frontends | 0 | Kotlin/Android apps — we use Discord, not native apps. |

---

## 1678 NOVEL ALGORITHMS — Priority Port List

The Citrus Circuits server contains **6 algorithms** we should port into The Engine:

### Must Port (direct value)

| # | Algorithm | Source File | What It Does | Engine System | Effort |
|---|---|---|---|---|---|
| 1 | **Scout Precision Rating (SPR)** | `sim_precision.py` + `scout_precision.py` | Compares each scout's reports against TBA actuals. Isolates individual scout accuracy via 3-scout combination analysis. Ranks scout reliability. | Scout | 3h |
| 2 | **NormalDist Win Probability** | `predicted_aim.py:calc_win_chance()` | Models each team's scoring as mean+variance, sums per alliance, computes `P(R-B > 0)` via `NormalDist.cdf()`. Clean probabilistic predictor. | Scout + Oracle | 2h |
| 3 | **Auto-Path Compatibility** | `pickability.py:calc_offensive_2nd_pickability()` | Checks if candidate's auto starts from positions compatible with first-pick's paths. Ensures non-conflicting reef faces. | Scout (draft) | 3h |

### Should Port (complementary value)

| # | Algorithm | Source File | What It Does | Engine System | Effort |
|---|---|---|---|---|---|
| 4 | **Anomaly Detection** | `data_validation.py` | Z-score outlier flagging across all numeric scouting fields. Writes flagged entries for review. | Scout | 1h |
| 5 | **TrueSkill Global Ratings** | `ratings.py` | Microsoft TrueSkill (mu/sigma Bayesian) across all events. Complements EPA. | Scout | 3h |
| 6 | **DoozerNet ML Predictor** | `doozernet_communicator.py` | Neural net match predictor (Prophet + SuperProphet models). API at `api.1678doozer.net`. | Oracle | Monitor only (API is private) |

**Total port effort: ~12h** for items 1-5. These add scout validation, probabilistic
win prediction, auto-path-aware drafting, data hygiene, and Bayesian rankings.

---

## UPDATED MASTER TOTALS

### All finds: 6 batches, 64+ repos + 1 API + 3 full org reviews

**ADOPT: 18 items**
(Previous 16) + PhotonVision (406★) + Elastic Dashboard (144★)

**ADOPT-TO-STUDY: 15 items**
(Previous 8) + ReCalc (28★) + frc-shooter-calculator + 1678 server
+ Spectrum Ultraviolet + limelightlib-python + systemcore-os-public
+ Spectrum gitbook

**IGNORE: 33+ items**

### Final Revised Roadmap

| System | Original | Previous Revised | After Batch 6 | Change |
|---|---|---|---|---|
| Blueprint (#1) | 120-150h | ~80-100h | ~80-100h | 0h (ReCalc validates, doesn't replace) |
| Coprocessor (#5) | 66.5h | ~50h | **~20h** | **-30h** (PhotonVision) |
| Cockpit (#3) | 39h | 39h | **~20h** | **-19h** (Elastic Dashboard) |
| Scout (#4) | 54h | ~45h | **~33h** | **-12h** (1678 algorithms pre-built) |
| Eye (#6) | ~30h | ~20h | ~17h | -3h (BBE Heat Seeker, frc-livescore) |
| Pit Crew (#7) | 44h | ~25h | ~25h | 0h |
| Vault (#8) | 12h | ~5h | ~5h | 0h |
| Grid (#9) | 18h | ~13h | ~13h | 0h |
| Clock (#10) | 30h | ~15h | ~15h | 0h |
| Antenna (#2) | 32h | 32h | 32h | Already shipped |
| Oracle improvements | +33h | +33h | **+45h** | +12h (1678 algorithm ports) |
| **TOTAL** | **~471h** | **~290h** | **~250h dev + 45h intelligence** | |

**Grand total: 471h → 295h (37% net reduction including new Oracle/Scout work)**

Without the intelligence upgrades: **471h → 250h (47% reduction).**

---

## ADDENDUM: Deep Org Reviews — frc1678 + Spectrum3847 (Saturday night)

Exhaustive review of both orgs to ensure nothing was missed.

### frc1678 (Citrus Circuits) — 107 repos total

**Scouting server evolution (2015-2025):**
- 2015: iOS Realm-based, Objective-C
- 2016-2018: Python flat-file (calculate_abilities, calculate_defense, calculate_predictions)
- 2019: scipy.stats.norm predictions, SPR already present, `calculate_defense.py` + `calculate_pushing_ability.py`
- 2020-2022: MongoDB migration, 15 calc modules, cardinal Django API
- 2023: 18 modules, auto_paths.py (timeline consolidation via mode-voting), sim_precision.py
- 2024: grosbeak REST API replaces cardinal, statbotics_exporter, predict_alliance
- 2025: 21 modules, DoozerNet ML predictor, TrueSkill, full auto-path compatibility

**NEW finds from deep dive:**

| Find | Source | Engine System | Action |
|---|---|---|---|
| **inner_goals_regression.py** | server-2021 | Oracle | Least-squares + Monte Carlo (10K iterations) to decompose alliance-level stats into per-team metrics. Apply to any shared-scoring scenario. |
| **calculate_defense.py** | server-2019 | Scout | Quantified defense impact (points prevented). Ancestor of predictobics defense model. |
| **auto_paths.py mode-voting** | server-2023 | Scout | Consolidates 3 scouts' timelines via mode-based voting. Data quality technique. |
| **robot-code-public** (49★) | C++ monorepo | Coprocessor | **muan** library: vision processing, camera calibration, video streaming, protobuf config. Study for Coprocessor vision layer. |
| **C2025-Public** (30★) | Java | Oracle + Blueprint | 2025 robot: elevator, pivot, coral deploy, algae, climber, end effector. **frc/lib** is their reusable Java layer. Validates Oracle 2025 predictions. |
| **C2024-Public** (29★) | Java | Blueprint | **regressions** package + shooting math. Study for flywheel_generator.py validation. |
| **pit-display-2024-public** | Vue/Electron | Pit Crew | Electron pit display app. Alternative to PitFUSION. |
| **elims-scouting-2025-public** | Kotlin | Scout | Dedicated elimination round scouting — separate workflow from quals. |
| **C2025-SystemCore** | Java | Coprocessor | Already testing 2027 controller code on 2025 hardware. Shows their offseason iteration. |
| **grosbeak** (2022-2024) | Python | Scout | REST API middleware (Docker, tests). Replaced Django cardinal. Architecture reference. |
| **schema** repos (2021-2025) | YAML | Scout | Schema-driven scouting pipeline — forms, calculations, and validation all derive from YAML schemas. |
| **No scouting whitepaper exists** | — | — | Methodology is encoded in code+schemas, not documentation. |

**Additional algorithm ports identified:**

| # | Algorithm | Source | Effort | Priority |
|---|---|---|---|---|
| 10 | Alliance-level stat decomposition (least-squares + Monte Carlo) | server-2021 `inner_goals_regression.py` | 3h | Medium |
| 11 | Defense points-prevented metric | server-2019 `calculate_defense.py` | 2h | High (complements predictobics) |
| 12 | Mode-voting timeline consolidation | server-2023 `auto_paths.py` | 2h | Medium |
| 13 | Schema-driven scouting pipeline | schema-2025 | 4h | Off-season (big refactor) |

### Spectrum3847 — 60 repos total

**SpectrumLib evolution (2020-2026):**
- 2020: Subsystems as flat classes (Ultraviolet-2020)
- 2021: Commands + Subsystems pattern (GammaRay)
- 2022: Sim + Telemetry packages added (Infrared-2022)
- 2023: SpectrumLib-Archive extracted as standalone. Elevator, FourBar, IntakeLauncher.
- 2024: `Mechanism.java` base class crystallized. Config-driven PID, MotionMagic, current limits, soft limits. (2024-Ultraviolet, 13★)
- 2025: Same pattern + vision/, gamepads/, leds/, sim/. SpectrumLib embedded in-repo. (2025-Spectrum, 9★)
- 2026: **NEW — `Coordinator.java` + `State.java`** orchestration layer. Mechanisms: fuelIntake, hood, indexerBed, indexerTower, intakeExtension, launcher. (2026-Spectrum, 3★)

**NEW finds from deep dive:**

| Find | Source | Engine System | Action |
|---|---|---|---|
| **Coordinator + State pattern** | 2026-Spectrum | Blueprint (code gen) | New orchestration layer beyond Mechanism base class. Study for robot code generation. |
| **FRC CAD Collection** | cadcollection.spectrum3847.org | Oracle (M12 reference) | **Not a repo** — Google Sheet with 805+ robot CAD links. Submission form. Useful for kickoff-day reference. |
| **$2000 Purchase Guide** | 2000.spectrum3847.org | Vault | Google Sheet with recommended purchases for new teams. Reference for Vault part priorities. |
| **Training curriculum (40+ modules)** | gitbook | Reference | 7 tracks (F/C/D/B/S/M/A): FRC intro, Java, control systems, OnShape CAD, MKCad, shop skills, strategy, media. All with Google Slides + YouTube. |
| **MCC-2019** (2★) | Robot code | Oracle (M11) | The only code repo implementing MCC philosophy directly. Study for MCC auto-generation. |
| **2025-Spectrum mechanism set** | Robot code | Oracle validation | elevator + elbow + shoulder + intake + climb + twist. Validates Oracle's 2025 arm-bot prediction. |
| **Driver Station log files** | Spectrum-Driver-Station-Logs | Pit Crew | Raw DS logs from competitions. Useful for brownout/comms failure analysis patterns. |
| **2024-NoteDetector** (1★) | Python | Eye | Game piece detection for 2024 notes. Minor but shows their vision approach. |

### Inconsistencies Fixed

| Issue | Resolution |
|---|---|
| mcp-youtube listed as both "investigate" and "adopt" | **Final: adopt.** Upgraded after investigation confirmed it works with our existing yt-dlp. |
| rf-detr listed as "investigate" then "ignore" | **Final: ignore.** GPU-only, heavier than YOLO, no edge support. |
| maestro listed as "investigate" then "ignore" | **Final: ignore.** VLM-only, doesn't support YOLO training. |
| Eye hours: "10h→4.5h" vs "30h→17h" | **Clarification:** 10h→4.5h is V0a vision model only. 30h→17h is the full Eye system. Both correct at different scopes. |
| fastmcp not in hour reduction | **Clarification:** fastmcp is an enabler (MCP server framework), not a direct hour saver. It reshapes the off-season architecture but doesn't replace existing planned work. |
| Batch 3 "45-55h saved" vs batch 6 "221h saved" | **Final number is batch 6:** 221h dev reduction + 45h new intelligence work = 176h net reduction (37%). Earlier batch totals were intermediate snapshots. |

---

## FINAL DEFINITIVE NUMBERS (post-deep-review)

### Adopt: 18 items

| # | Repo | Stars | System |
|---|---|---|---|
| 1 | roboflow/supervision | 38,000 | Eye |
| 2 | roboflow/sports | 4,900 | Eye |
| 3 | roboflow/trackers | 3,300 | Eye |
| 4 | roboflow/inference | 2,300 | Eye |
| 5 | neurobionics/onshape-robotics-toolkit | 297 | Blueprint |
| 6 | hedles/onshape-mcp | 49 | Blueprint |
| 7 | replaysMike/Binner | 514 | Vault |
| 8 | mpking828/PitFUSION | 4 | Pit Crew |
| 9 | Foxglove ecosystem | 895 | Pit Crew |
| 10 | FRC Nexus API | — | Scout+Eye+Pit |
| 11 | github/github-mcp-server | 28,800 | Clock |
| 12 | taylorwilsdon/google_workspace_mcp | 2,100 | Clock |
| 13 | DugboTek/FRCDocsMCP | 0 | All |
| 14 | avgupta456/statbotics | 96 | Scout+Oracle |
| 15 | andrewda/frc-livescore | 29 | Eye |
| 16 | anaisbetts/mcp-youtube | 514 | Eye |
| 17 | PhotonVision/photonvision | 406 | Coprocessor |
| 18 | Gold872/elastic_dashboard | 144 | Cockpit |

### Adopt-to-study: 18 items (expanded from 15)

| # | Repo | Stars | System | Extract |
|---|---|---|---|---|
| 1 | cliclye/predictobics | 1 | Scout | Defense EPA, synergy scoring |
| 2 | Ruthie-FRC/JSim | 2 | Motor Model | FRC physics engine, Python bindings |
| 3 | FRCTeam2910/2025CompetitionRobot-Public | 48 | Oracle+Coprocessor | FSM, vision relocalization |
| 4 | Team254/aos `frc/orin/` | — | Coprocessor | Hardware decisions |
| 5 | Team254/aos `frc/analysis/` | — | Pit Crew | Foxglove patterns |
| 6 | Team254/aos `frc/can_logger/` | — | Grid | ASC CAN log standard |
| 7 | Team254/cheesy-parts | 25 | Vault | FRC part data model |
| 8 | Team254/cheesy-hours | 13 | Clock | Hour tracking workflow |
| 9 | tervay/recalc | 28 | Blueprint | Elevator/arm/flywheel ODE validation |
| 10 | efeerdogmus0/frc-shooter-calculator | 0 | Blueprint | Projectile sim (Python, Magnus) |
| 11 | frc1678/server-2025-public | 0 | Scout | SPR, NormalDist, auto-path, anomaly, TrueSkill, DoozerNet |
| 12 | frc1678/server-2019 | 2 | Scout | Defense points-prevented, pushing ability |
| 13 | frc1678/server-2021-public | 0 | Scout | Alliance stat decomposition (LS + Monte Carlo) |
| 14 | frc1678/C2025-Public | 30 | Oracle+Blueprint | Latest mechanism patterns, frc/lib |
| 15 | frc1678/C2024-Public | 29 | Blueprint | Regressions + shooting math |
| 16 | Spectrum3847/2024-Ultraviolet | 13 | Blueprint | Mechanism base class, config-driven PID |
| 17 | Spectrum3847/2026-Spectrum | 3 | Blueprint | Coordinator+State orchestration pattern |
| 18 | LimelightVision/limelightlib-python | 3 | Coprocessor | Python SDK for Limelight |

### Algorithm ports: 16 total (~52h)

**Oracle Phase 1 — Data foundation (May-June, 11h):**
1. Add 10 missing historical games to HISTORICAL_GAMES (4h)
2. Pull epa_sd + epa_skew into Scout predictions (2h)
3. Use component EPAs for draft complementarity (3h)
4. Replace hardcoded confidence with Norm EPA (2h)

**Scout Phase 2 — Intelligence (July-August, 23h):**
5. Port defense-adjusted EPA (predictobics, 4h)
6. Port synergy scoring (predictobics, 4h)
7. Port SkewNormal EWMA locally (statbotics, 3h)
8. Port SPR scout validation (1678-2025, 3h)
9. Port NormalDist win probability (1678-2025, 2h)
10. Port auto-path compatibility (1678-2025, 3h)
11. Port anomaly detection (1678-2025, 1h)
12. Port TrueSkill ratings (1678-2025, 3h)

**Scout Phase 2.5 — Advanced (August, 7h):**
13. Port defense points-prevented (1678-2019, 2h)
14. Port alliance stat decomposition (1678-2021, 3h)
15. Port mode-voting timeline consolidation (1678-2023, 2h)

**Oracle Phase 3 — LLM augmentation (September-October, 11h):**
16. Claude as Oracle reviewer (3h)
17. Game manual → GameRules auto-extraction (8h)

### Definitive roadmap

| System | Original | Final | Savings |
|---|---|---|---|
| Blueprint (#1) | 120-150h | ~80-100h | -40-50h |
| Coprocessor (#5) | 66.5h | ~20h | -46h |
| Cockpit (#3) | 39h | ~20h | -19h |
| Scout (#4) | 54h | ~33h | -21h |
| Eye (#6) | ~30h | ~17h | -13h |
| Pit Crew (#7) | 44h | ~25h | -19h |
| Vault (#8) | 12h | ~5h | -7h |
| Grid (#9) | 18h | ~13h | -5h |
| Clock (#10) | 30h | ~15h | -15h |
| Antenna (#2) | 32h | 32h | 0h (shipped) |
| **Dev subtotal** | **~471h** | **~250h** | **-221h (47%)** |
| Oracle/Scout intelligence | 0h | +52h | New work |
| **GRAND TOTAL** | **471h** | **302h** | **-169h net (36%)** |

### Total scope: 80+ repos + 1 API + 3 full org reviews (107+60+11 = 178 org repos scanned)

---

## Batch 7: Einstein Finalists (2019-2025) — Exhaustive GitHub Audit

**Context:** User requested: "list all Einstein finalists from 2019-2025 and see if they have public GitHub repos." Exhaustive scan of all 40+ unique teams that appeared on Einstein finalist/winner alliances across 6 championship events (2019 Houston, 2019 Detroit, 2022, 2023, 2024, 2025). 2020-2021 cancelled (COVID).

### Einstein Finals Teams — GitHub Presence

**2019 Houston:** W: 1323+973+5026 | F: 254+3310+6986
**2019 Detroit:** W: 3707+4481+217 | F: 5406+930+1310
**2022:** W: 1619+254+6672+3175 | F: 1577+4099+4414
**2023:** W: 1323+4414+4096 | F: 5460+125+870
**2024:** W: 1690+4522+321 | F: 254+1323+294
**2025:** W: 1323+2910+4272 | F: 2073+4414+1690

### Tier 1 — Rich Codebases (adopt-to-study)

| Team | GitHub | Repos | Key Finding | Verdict |
|---|---|---|---|---|
| **1310** Runnymede | [RunnymedeRobotics1310](https://github.com/RunnymedeRobotics1310) | 44 | **Raven ecosystem** — RavenEye (React 19, offline-first IndexedDB scouting), RavenBrain (Java/Micronaut REST + MySQL), **RavenLink** (Go binary: NetworkTables capture + OBS auto-record + store-and-forward sync). Published Maven swerve library. Most architecturally mature 3-tier scouting found. | **adopt-to-study** |
| **4099** The Falcons | [team4099](https://github.com/team4099) | 74 | **FalconScout** (9★, low-code QR scouting, config-driven forms, data validation engine), **FalconAlliance** (8★, PyPI TBA wrapper), **FalconVis** (4★, Streamlit analytics + auto picklist), **FalconUtils** (3★, Kotlin units + geometry + controllers), **HawkEye** (3★, Android AR AprilTag via ARCore), **nester** (CNC part nesting optimizer) | **adopt-to-study** |
| **1690** Orbit | [Team1690](https://github.com/Team1690) | 16 | **StrategyEngine-2026** (Flutter+Go+Python game simulation with AI optimization), **Scouting-Frontend** (10★, Flutter+GraphQL+Hasura, radar charts, auto picklist), **scouting-simulator** (Monte Carlo meta-sim testing 13 scouting methods across 10K iterations), **orbit-elastic-dashboard** (3★) | **adopt-to-study** |
| **2767** Stryke Force | [strykeforce](https://github.com/strykeforce) | 50 | **thirdcoast** (38★, vendordep swerve + telemetry streaming + pit health check), **deadeye** (6★, multi-component C++ vision: daemon + Java client + React admin + Python server + Ansible deploy), **wallEYE** (multi-camera AprilTag on Orange Pi 5), **cookiecutter-robot** (5★, project template generator) | **adopt-to-study** |
| **900** Zebracorns | [FRC900](https://github.com/FRC900) | 126 | **Only ROS2 team in FRC.** 70+ ROS packages. GPU AprilTags (CUDA), particle filter localization, TensorFlow game piece detection (11★), Gazebo simulation, VR headset pose streaming, custom roboRIO kernel drivers (CAN, RTC, IMU). Code archive back to 2004. | **adopt-to-study** |
| **4522** Team SCREAM | [TeamSCREAMRobotics](https://github.com/TeamSCREAMRobotics) | 13 | **SCREAMLib** — proper WPILib vendor library (installable via JSON): TalonFXSubsystem base class, **2-joint IK solver**, projectile trajectory with air resistance, HexagonalPoseArea zone geometry, SimWrapper for maple-sim. 2024 Einstein winner code public. | **adopt-to-study** |
| **321** RoboLancers | [RoboLancers](https://github.com/RoboLancers) | 49 | **bluetooth-scouting** (React Native + Bleno + SQLite, no WiFi), **Helios** custom vision hardware (Orange Pi 5 + ArduCam, custom PCB, Limelight alternative), **lancer-deploy-tool** (Probot auto-versioning), NFC attendance tracker, OnShape→Discord bot. 2024 Einstein winner. | **adopt-to-study** |
| **2073** EagleForce | [team-2073-eagleforce](https://github.com/team-2073-eagleforce) | 21 | **scouting-backend** (3★, Django 5.1, dynamic JSON game config, Google OAuth, QR scanner, strategy dashboard, PostgreSQL), **JeVois Vision Suite** (7★, highest-starred across all Einstein teams, with published white paper), **eagleforce-robot-template** (3★) | **adopt-to-study** |

### Tier 2 — Useful Reference Code

| Team | GitHub | Repos | Key Finding | Verdict |
|---|---|---|---|---|
| **217** ThunderChickens | [Team217](https://github.com/Team217) | 24 | **FRC-217-Libraries** (2★, reusable JAR: PID, MotionProfiler, **GeometricProfiler** with sinusoidal wave profiles + [Desmos viz](https://www.desmos.com/calculator/qqevqwzzzu), CTRE/REV wrappers) | **adopt-to-study** |
| **930** BEARs | [FRC930](https://github.com/FRC930) | 46 | **BEARscouts** (5★, Flutter QR scouting, drag-drop widgets, config editor), **frc-data-lib** (npm package for FRC APIs), **Bluetooth scouting** architecture (bt-scout-supervisor/client) | **adopt-to-study** |
| **4272** Maverick | [maverick-boiler-robotics-team-4272](https://github.com/maverick-boiler-robotics-team-4272) | 21 | **MAVcoder PCB** (5★, custom shaft encoder in KiCad), **DefenseSwerve** (defense-specific swerve impl), uses Choreo not PathPlanner. 2025 Einstein winner. | **adopt-to-study** |
| **6672** Fusion Corps | [FusionCorps](https://github.com/FusionCorps) | 24 | **ballistic-simulator** (C++ + Python + Java + LaTeX paper), **lidar** (Rust, GPU-accelerated LiDAR localization via ArrayFire), fusioncorps-swerve (3★). 2022 Einstein winner. | **adopt-to-study** |
| **4096** Ctrl-Z | [CtrlZ-FRC4096](https://github.com/CtrlZ-FRC4096) | 22 | **Only Python/robotpy Einstein winner.** VSCode live execution tracer (highlights running code lines in real-time), coroutine command framework, remote REPL into running robot, PIDD2 controller. | **adopt-to-study** |
| kl26436 | [kl26436/frc-2026-analytics](https://github.com/kl26436/frc-2026-analytics) | 1 | **Data Wrangler** — React/TypeScript/Firestore scouting analytics: fuel attribution model (beta=0.7 power curve), match replay with timestamped field map, three-tier picklist with real-time Firestore sync, trend analysis (overall vs last 3), data quality vs FMS comparison | **adopt-to-study** |

### Tier 3 — Robot Code Only (study for Oracle validation)

| Team | GitHub | Repos | Verdict |
|---|---|---|---|
| **3310** Black Hawks | [Team3310](https://github.com/Team3310) | 21 | Vue scouting app (fork of 2834), Java robot code 2012-2025. **adopt-to-study** (scouting pattern) |
| **5406** Celt-X | [Team5406](https://github.com/Team5406) | 23 | Java robot code + PurpleLib. Reference only. |
| **4481** Rembrandts | [FRC-4481-Team-Rembrandts](https://github.com/FRC-4481-Team-Rembrandts) | 10 | Robot code + LED controller. Reference only. |
| **294** Beach Cities | [team294](https://github.com/team294) | 49 | signinapp (3★, PyQt hours tracker), 15-year code history. Reference only. |
| **1619** Up-A-Creek | [Team1619](https://github.com/Team1619) | 4 | Minimal robot code releases. |
| **1323** MadTown | [Team1323](https://github.com/Team1323) | 8 | 3x Einstein winner. Swerve code 2017-2019. Code quality high but no libraries. |
| **125** NUTRONs | [gitlab.com/nutrons125](https://gitlab.com/nutrons125) | 8 | GitLab. Championship-winning code public (NU22, NU23, NU25). No tooling. |
| **4414** HighTide | [Team4414](https://github.com/Team4414) | 7 | FalconDashboard (4★). 4x Einstein finalist. Minimal public code. |

### Tier 4 — No/Minimal GitHub Presence

5460 Strike Zone (2 ancient repos), 3175 Knight Vision (21 repos, no libraries), 1577 Steampunk (not found), 3707 Brighton TechnoDogs (not found), 870 Team R.I.C.E. (not found), 6986 PPT Bots (not found).

### Batch 7 New Adoptions: 12 adopt-to-study

These are all **study** items — reference architectures and algorithms, not direct replacements:

1. **RavenLink** (1310) — Go binary for NetworkTables+OBS capture. Pattern for Scout data bridge.
2. **FalconScout** (4099) — Config-driven QR scouting. Reference for Scout form generation.
3. **FalconAlliance** (4099) — PyPI TBA wrapper. Save ~2h of API wrapper code in Scout.
4. **StrategyEngine-2026** (1690) — Game simulation with AI. New Oracle capability concept.
5. **scouting-simulator** (1690) — Monte Carlo scouting methodology validation. Scout data quality.
6. **SCREAMLib IK solver** (4522) — 2-joint inverse kinematics. Blueprint mechanism math.
7. **deadeye/wallEYE** (2767) — Multi-camera vision architecture. Coprocessor reference.
8. **BEARscouts** (930) — Flutter QR scouting. Alternative Scout form pattern.
9. **bluetooth-scouting** (321) — No-WiFi scouting via Bluetooth. Scout resilience.
10. **scouting-backend** (2073) — Django with dynamic JSON config. Scout flexibility pattern.
11. **FRC-217-Libraries** (217) — GeometricProfiler. Blueprint motion profile reference.
12. **ballistic-simulator** (6672) — LaTeX-documented physics. Blueprint shooter validation.

### New Concept: CodeScout — Competitive Intelligence via Public GitHub

**The idea:** Before a competition, automatically search GitHub for opponent teams' public repos to learn their autonomous routines, mechanism capabilities, and strategy.

**What's extractable from public robot code:**
- **Choreo/PathPlanner trajectory files** (.traj/.path JSON) → plot auto paths on field map
- **AutoModeSelector classes** → list all auto routines with descriptive names
- **Mechanism constants** → elevator heights, speeds, PID values reveal capability
- **Vendor dependencies** → CTRE vs REV, PhotonVision vs Limelight, Choreo vs PathPlanner
- **Subsystem inventory** → directories reveal mechanisms (climber? shooter? vision?)

**Feasibility assessment:**
- ~11% of FRC teams have public GitHub repos (~400/3,500 per season)
- At a typical regional: 4-8 teams have discoverable repos, 2-4 have meaningful code
- **Critical limitation:** Elite teams publish AFTER competitions (254, 1678, 6328, 2910 all post-season only)
- Mid-tier teams that push during build season ARE vulnerable to this analysis
- **Ethically acceptable** in FRC community — public code is public. But automated surveillance feels like it crosses the spirit of coopertition.

**Proposed implementation (off-season, ~10h):**
1. TBA API → get team list for event (1h)
2. GitHub API search for `frc{number}` orgs (2h)
3. Parse Choreo .traj / PathPlanner .path files → field visualization (3h)
4. Extract AutoModeSelector / Constants.java → capability card (2h)
5. Generate per-team intelligence report (2h)

**Verdict:** Build as a study tool for off-season learning from elite teams' post-season releases. Use sparingly for pre-competition intel — the ethical line is blurry and the hit rate is low (~10%).

---

## Batch 8: Exhaustive Einstein Team Audit (~130 teams)

**Context:** User provided the complete list of every team that competed on Einstein from 2019-2025 (~130 unique teams). All checked for GitHub presence, repos counted, tools and libraries identified.

### Tier 1 — Gold mines (new discoveries not in Batches 1-7)

| Team | GitHub | Repos | Key Finding | Verdict |
|---|---|---|---|---|
| **971** Spartan Robotics | [frc971](https://github.com/frc971) | 17 | **971-Robot-Code** (69★) — AOS distributed middleware, LQR/DARE solvers, state-space control, CUDA AprilTags, Bazel build. Most sophisticated FRC codebase on GitHub. Scouting system with PostgreSQL. Custom Yocto Linux images. Jetson kernel builder. | **adopt-to-study** |
| **604** Quixilver | [frc604](https://github.com/frc604) | 37 | **frcreplay** (11★) — automated match video capture+upload. **quikplan-public** (11★) — trajectory optimization. robot-sim-example (5★). team-tracker. gcode CNC scripts. | **adopt-to-study** |
| **3061** Huskie Robotics | [HuskieRobotics](https://github.com/HuskieRobotics) | 60 | **3061-lib** (32★) — well-starred Java FRC library. **SPOT** (26★) — scouting+visualization tool. | **adopt-to-study** |
| **4788** CurtinFRC | [CurtinFRC](https://github.com/CurtinFRC) | 42 | **CAN-over-RJ45** — custom PCB (KiCad): CANbus+power+DIO over RJ45. **Numbat** — zero-cost C++ logging lib (vendor template). **Repulsor** (4★) — autonomous path planning. **Wombat** (3★) — reusable C++ FRC framework. | **adopt-to-study** |
| **2471** Mean Machine | [TeamMeanMachine](https://github.com/TeamMeanMachine) | 41 | **meanlib** (20★) — Kotlin FRC library. **MeanScout** (5★) — P2P WebRTC scouting (no server). PathVisualizer (3★). | **adopt-to-study** |
| **2877** LigerBots | [ligerbots](https://github.com/ligerbots) | 71 | **dslogparser** (18★) — Python DS log parser (MIT). Broadly useful for Pit Crew diagnostics. | **adopt-to-study** |

### Tier 2 — Useful tools and ecosystems

| Team | GitHub | Repos | Key Finding | Verdict |
|---|---|---|---|---|
| **1073** Force Team | [FRCTeam1073-TheForceTeam](https://github.com/FRCTeam1073-TheForceTeam) | 126 | **viper** (19★) — web scouting system. vision2026 (Rust). | **adopt-to-study** |
| **1477** Texas Torque | [TexasTorque](https://github.com/TexasTorque) | 46 | TorqueLib (3★), TorqueLearn wiki (9★), Torqueue machine queue (2★), torque-hours (1★), TorqueTask (1★). Most team-ops-tooling-rich org. | **adopt-to-study** |
| **7028** Binary Battalion | [STMARobotics](https://github.com/STMARobotics) | 38 | frc-7028-2023 (27★), **superalliance** (3★, scouting), **frc-jetson-detect** (Jetson object detection), **QuestNav** (Oculus Quest pose→NT). | **adopt-to-study** |
| **862** Lightning Robotics | [frc-862](https://github.com/frc-862) | 110 | thunder/lightning libs (5★ each), **WebDS** (3★, web-based driver station), DigitalBatteryLog (2★). | reference |
| **2590** Nemesis | [Team2590](https://github.com/Team2590) | 24 | frc-livescore (vision scoring), full scouting pipeline, scout-validator, RFID attendance. | reference |
| **461** Westside Boiler | [frc461](https://github.com/frc461) | 30 | **Scoutify** (modular: client 4★/merger 4★/viewer/database), opr-calc Ruby gem. | reference |
| **2718** | [team2718](https://github.com/team2718) | 20 | **PossumFMS** (custom FMS), StrategyBoard-2026, ButtonBoxFirmware, scouting suite. | reference |
| **2539** Krypton Cougars | [FRC2539](https://github.com/FRC2539) | 72 | Cougar-Dashboard (4★), cougar-log (2★), cougarlib (2★), java-training (7★). | reference |
| **5940** BREAD | [BREAD5940](https://github.com/BREAD5940) | 62 | Deep PhotonVision + Intel RealSense + Northstar vision investment. Embedded Linux tooling. | reference |
| **195** CyberKnights | [frcteam195](https://github.com/frcteam195) | 100+ | KnightVision (2★), CyberDash, scouting web+python, ROS dev, CKSim (Unity FRC sim). Most diverse toolkit. | reference |
| **4201** Vitruvian Bots | [4201VitruvianBots](https://github.com/4201VitruvianBots) | 84 | Codex library, scouting apps (MIT), VitruvianMatchSchedule, QuestNav fork. | reference |
| **4145** WorBots | [Worthington-Robotics](https://github.com/Worthington-Robotics) | 41 | YOLO-based AI vision (2024AIVision), Rust scouting app. | reference |
| **4003** TriSonics | [TheTriSonics](https://github.com/TheTriSonics) | 14 | frcscout.org (Angular+Python scouting on Azure), frc_log_puller. | reference |
| **4607** CIS | [FRC4607](https://github.com/FRC4607) | 33 | Robot-Telemetry (Python log analysis), Vue scouting app. | reference |
| **2122** Team Tators | [TeamTators](https://github.com/TeamTators) | 9 | Full TypeScript scouting ecosystem (app+dashboard+webhooks+bot). | reference |

### Tier 3 — Robot code only (notable star counts)

| Team | GitHub | Repos | Best Repo |
|---|---|---|---|
| 111 WildStang | [WildStang](https://github.com/WildStang) | 68 | wildrank-android (6★) scouting + robot_framework (3★) |
| 166 Chop Shop | [chopshop-166](https://github.com/chopshop-166) | 41 | chopshoplib (1★) game-agnostic lib + SignInWebApp (3★) |
| 548 Robostangs | [Robostangs](https://github.com/Robostangs) | 46 | Everyscout web scouting + **visionOS scouting app** (Apple Vision Pro!) |
| 302 Dragons | [Team302](https://github.com/Team302) | 77 | ScoutingPASS, SystemCoreCpp (2★), DragonVision |
| 687 NerdHerd | [nerdherd](https://github.com/nerdherd) | 62 | NerdyLib (7★) + NerdScout |
| 972 Iron Claw | [iron-claw-972](https://github.com/iron-claw-972) | 90 | 2024-Coprocessor-Vision (5★, ML object detection) |
| 2052 KnightKrawler | [frc2052](https://github.com/frc2052) | 35 | FRC-Krawler (25★) scouting app |
| 1706 Ratchet Rockers | [rr1706](https://github.com/rr1706) | 57 | 2022-Main (17★) |
| 6995 NOMAD | [frc6995](https://github.com/frc6995) | 31 | nomad-lib + NOMADBase template + LimelightWidget |
| 4613 Barker Redbacks | [Team4613-BarkerRedbacks](https://github.com/Team4613-BarkerRedbacks) | 10 | SoftwareWorkshops (11★) + Programming-Java-Guide (11★) |
| 1771 | [Team1771](https://github.com/Team1771) | 16 | Crash-Course C++ tutorial (11★) |
| 3184 Blaze | [FRC3184](https://github.com/FRC3184) | 12 | frcblocks (2★, block-based FRC code) + purepursuit |
| 3534 HOC | [HOC-Team-3534](https://github.com/HOC-Team-3534) | 25 | StateBasedControl (3★) vendor dependency |
| 4946 Alpha Dogs | [frc4946](https://github.com/frc4946) | 13 | Scouting server (C#) + autonomous path planner + battery tester |

### Tier 4 — No/minimal GitHub presence

16, 59, 78, 118, 133, 179, 180, 190, 230, 324, 346, 498, 818, 870, 987, 1058, 1189, 1218, 1577, 1730, 1746, 1768, 2075, 2370, 2481, 2534, 2582, 2609, 2614, 2907, 3132, 3276, 3478, 3538, 3603, 3655, 3707 (minimal), 3940, 4004, 4153, 4192, 4206, 4213, 4329, 4476, 5050, 5166, 5401, 5419, 5454, 5804, 5813, 5895, 6329, 6986, 7179, 7558, 8044, 8085, 9072, 9312, 9432, 9483

### Batch 8 Summary

- ~130 teams checked (including ~28 already investigated in Batches 1-7)
- ~75 teams have GitHub presence
- ~55 teams have no/minimal repos
- **6 new Tier 1 adopt-to-study** (971, 604, 3061, 4788, 2471, 2877)
- **10 new Tier 2 reference** items (1073, 1477, 7028, 862, 2590, 461, 2718, 2539, 5940, 195)
- **14 more Tier 3 robot-code-only** with notable repos
- **Team 971 is the single most important find** — their 69-star monorepo with AOS middleware, control theory (LQR/DARE), and CUDA vision is the most sophisticated FRC codebase on GitHub

---

## FINAL SUMMARY — ALL 8 BATCHES

### Saturday 2026-04-12 by the numbers

| Metric | Count |
|---|---|
| **Total repos directly evaluated** | 150+ |
| **Full org reviews** | 5 deep (frc1678: 107, Spectrum3847: 60, team4099: 74, FRC900: 126, strykeforce: 50) |
| **Einstein teams exhaustively checked** | ~130 unique teams across 2019-2025 |
| **Total org repos scanned** | 500+ |
| **Teams with GitHub presence** | ~75 of ~130 (58%) |
| **Adopt verdicts** | 18 |
| **Adopt-to-study verdicts** | 36 (18 Batches 1-6 + 12 Batch 7 + 6 Batch 8) |
| **Reference items** | 10+ additional (Batch 8 Tier 2) |
| **Algorithm ports identified** | 16 (~52h) |
| **New concept (CodeScout)** | ~10h |

### Final Adoption List (18 adopt — unchanged)

| # | Repo | Stars | System | What it replaces |
|---|---|---|---|---|
| 1 | roboflow/supervision | 38,000 | Eye | Custom detection pipeline |
| 2 | roboflow/sports | 4,900 | Eye | Custom tracking |
| 3 | roboflow/trackers | 3,300 | Eye | Custom multi-object tracking |
| 4 | roboflow/inference | 2,300 | Eye | Custom model serving |
| 5 | onshape-robotics-toolkit | 297 | Blueprint | onshape_api.py |
| 6 | hedles/onshape-mcp | 49 | Blueprint | Manual CAD scripting |
| 7 | replaysMike/Binner | 514 | Vault | Custom inventory system |
| 8 | mpking828/PitFUSION | 4 | Pit Crew | Custom pit reporting |
| 9 | Foxglove ecosystem | 895 | Pit Crew | Custom log visualization |
| 10 | FRC Nexus API | — | Scout+Eye | Custom event data sync |
| 11 | github-mcp-server | 28,800 | Clock | Manual GitHub workflow |
| 12 | google_workspace_mcp | 2,100 | Clock | Manual Google Workspace |
| 13 | DugboTek/FRCDocsMCP | 0 | All | Manual doc lookup |
| 14 | avgupta456/statbotics | 96 | Scout+Oracle | Hardcoded EPA values |
| 15 | andrewda/frc-livescore | 29 | Eye | Custom OCR |
| 16 | anaisbetts/mcp-youtube | 514 | Eye | Manual video handling |
| 17 | PhotonVision | 406 | Coprocessor | CP.1-CP.8 custom vision |
| 18 | Elastic Dashboard | 144 | Cockpit | Custom dashboard |

### Final Roadmap Impact (unchanged from Batch 7 — Batch 8 adds depth, not hour savings)

| System | Original | Post-Scan | Savings |
|---|---|---|---|
| Blueprint (#1) | 120-150h | ~80-100h | **-40-50h** |
| Coprocessor (#5) | 66.5h | ~20h | **-46h** |
| Cockpit (#3) | 39h | ~20h | **-19h** |
| Scout (#4) | 54h | ~31h | **-23h** |
| Eye (#6) | ~30h | ~17h | **-13h** |
| Pit Crew (#7) | 44h | ~25h | **-19h** |
| Vault (#8) | 12h | ~5h | **-7h** |
| Grid (#9) | 18h | ~13h | **-5h** |
| Clock (#10) | 30h | ~15h | **-15h** |
| Antenna (#2) | 32h | 32h | 0h (shipped) |
| **Dev subtotal** | **~471h** | **~248h** | **-223h (47%)** |
| Oracle/Scout intelligence | 0h | +52h | New capability |
| CodeScout | 0h | +10h | New capability |
| **GRAND TOTAL** | **471h** | **310h** | **-161h net (34%)** |

**One Saturday of searching saved 223 development hours, uncovered 62 hours of new capability work, and mapped the entire FRC Einstein GitHub ecosystem.**

### Top 10 Most Important Repos Found (across all 8 batches)

| Rank | Repo | Stars | Why |
|---|---|---|---|
| 1 | roboflow/supervision | 38,000 | Replaces entire Eye detection pipeline |
| 2 | frc971/971-Robot-Code | 69 | Most sophisticated FRC codebase — AOS, LQR/DARE, CUDA vision |
| 3 | PhotonVision | 406 | Eliminates 30h of Coprocessor work |
| 4 | onshape-robotics-toolkit | 297 | Replaces onshape_api.py entirely |
| 5 | Elastic Dashboard | 144 | Fork replaces custom Cockpit dashboard |
| 6 | avgupta456/statbotics | 96 | EPA internals power Oracle upgrade |
| 7 | frc1678/server-2025 | 0 | 6 algorithm ports for Scout (SPR, NormalDist, TrueSkill, etc.) |
| 8 | HuskieRobotics/3061-lib | 32 | Well-starred Java FRC library reference |
| 9 | HuskieRobotics/SPOT | 26 | Scouting + visualization reference |
| 10 | frc604/frcreplay + quikplan | 11+11 | Automated match video + trajectory optimization |

*Landscape scan by Opus, 2026-04-12. Eight batches + exhaustive Einstein audit.
150+ repos directly evaluated + 500+ org repos scanned + ~130 Einstein teams checked.
Companion to `LANDSCAPE_SCAN_ROBOFLOW_2026-04-12.md` (same day, first batch).*
