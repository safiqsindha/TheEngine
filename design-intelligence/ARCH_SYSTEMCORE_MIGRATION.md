# THE ENGINE — SystemCore Migration
# Umbrella architectural decision doc
# Target: 2027 kickoff
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Why this doc exists

FIRST is replacing the NI roboRIO with the Limelight **SystemCore**
as the official FRC robot controller starting in the 2027 season. This
doc is the single source of truth for how The Engine adapts: which
subsystems change, which don't, the coprocessor strategy that rides on
top of SystemCore, and the CAN-FD topology we commit to.

Every subsystem-level architecture doc (`ARCH_COACH_AI.md`,
`ARCH_ELECTRICAL_SYSTEMS.md`, `ARCH_DRIVER_STATION.md`,
`ARCH_CAD_PIPELINE.md`) should link back here for the hardware
baseline.

---

## The SystemCore in one paragraph

SystemCore is a Raspberry Pi CM5-based robot controller with a
realtime RP2350 I/O subsystem bolted on. Quad Cortex-A76 @ 2.4 GHz
running Linux 6.6 PREEMPT-RT with 4 GB LPDDR4X, 16 GB eMMC, VideoCore
VII GPU. The RP2350 coprocessor (dual Cortex-M33 @ 150 MHz, 520 KB
SRAM) owns the deterministic I/O layer. It has **5× CAN-FD @ 8 Mbps**,
4× USB 3.0, Gigabit Ethernet, a PCIe 2.0 M.2 A+E 2230 slot, a built-in
IMU (400 Hz quaternion + 3-axis accel + gyro), 6 reconfigurable Smart
I/O ports (DIO/PWM/Analog/LED/Quadrature), and an OLED 128×64 status
display. Power input is 5-26 V with a buck-boost, ~6 W idle / 40 W
peak, with a configurable brownout threshold at 6.3 V.

Relevant for us:
- **CAN-FD at 8 Mbps** — 8× the bandwidth of the roboRIO CAN bus
- **Built-in IMU** — Pigeon 2.0 becomes optional, not mandatory
- **M.2 A+E slot** — open for a Coral / AI HAT / Wi-Fi card if ever needed
- **Linux userland** — we can run supporting Python scripts directly on SystemCore for non-realtime jobs

---

## Core principle: two boxes, two roles

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│ SystemCore (robot controller) │◄──NT──►│ Jetson Orin Nano Super        │
│                               │  GigE  │ (on-robot coprocessor)        │
│  - WPILib Java                │        │  - PhotonVision               │
│  - Drivetrain + subsystems    │        │  - YOLO11 (Eye on-robot)      │
│  - CAN-FD motor controllers   │        │  - Whisper LLM coach          │
│  - FMS comms                  │        │  - AdvantageKit NVMe logger   │
│  - NT server                  │        │  - Pit Crew P.5 debug server  │
│  - Constructicon state mach.  │        │                               │
│  - 50 Hz control loop         │        │  Non-realtime, GPU-heavy      │
│  - RP2350 realtime I/O        │        │  You own the whole stack      │
│                               │        │                               │
│  Safety-critical.             │        │  Intelligence-critical.       │
│  WPILib / FMS certified.      │        │  Not on the FMS allowlist.    │
└──────────────────────────────┘         └──────────────────────────────┘
```

**SystemCore is the spine. The Jetson is the brain stem.** They talk
NT4 over a single on-robot Cat6 cable. Lose the Jetson mid-match and
SystemCore keeps driving on manual — the robot becomes dumber but
doesn't die. Lose SystemCore and the whole robot is e-stopped, as it
should be.

We do NOT run Whisper, vision, or heavy inference on SystemCore
itself. During a season where we're legitimately competitive, we
refuse to share CPU between control code and inference. The coprocessor
is the offload target for everything that isn't realtime control.

---

## Subsystem impact matrix

| Subsystem | Impact | Effort | Who owns | Status |
|---|---|---|---|---|
| **Constructicon (robot code)** | Full port: roboRIO → SystemCore. Build system, vendor deps, WPILib version, deploy workflow. | ~20 h | Software lead + mentor | Pending 2027 WPILib drop |
| **The Whisper** | Full rearchitecture — moved from DS shelf to on-robot Jetson coprocessor (see `ARCH_COACH_AI.md` rev-3). | 66.5 h | Software lead | Rev-3 locked |
| **The Grid (electrical)** | Rewire: new CAN-FD topology, SystemCore power pigtail, remove Pigeon wiring (SystemCore has built-in IMU), add Jetson power rail from PDH. | ~12 h | Electrical lead | Doc update pending |
| **The Blueprint (CAD)** | Minor: update electronics panel template to reflect SystemCore + Jetson footprint + enclosures. MKCad/FRCDesignLib parts to source. | ~3 h | CAD lead | Backlog |
| **The Eye (match analysis)** | Split into two halves: (a) on-robot real-time YOLO runs on the Jetson coprocessor (replaces offboard E.2), (b) offseason batch processing on scouting laptops unchanged. | Already folded into CP.7-CP.9 | Software lead | Rev-3 locked |
| **Pit Crew P.5 (debug dashboard)** | Repointed: FastAPI serves from the on-robot Jetson on LAN when tethered in the pit. | Already folded into CP.11 | Software lead | Rev-3 locked |
| **The Cockpit (driver station)** | Adds Whisper coach panel to Elastic/Shuffleboard layout. Reads `/Whisper/*` over field radio. No new hardware. | ~2 h | Driver lead | Backlog |
| **The Antenna** | No change. | 0 | — | ✅ |
| **The Scout** | No change. | 0 | — | ✅ |
| **The Vault** | Inventory spreadsheet gains SystemCore + Jetson parts. | ~1 h | Mentor | Backlog |
| **The Clock (build mgmt)** | No change beyond ingesting updated BOMs. | 0 | — | ✅ |
| **Engine Advisor** | No change. | 0 | — | ✅ |
| **Design Intelligence** | This doc + ARCH_COACH_AI rev-3 + roadmap update. In progress. | 4 h | Mentor | In progress |
| **Prediction Engine** | No change. | 0 | — | ✅ |
| **Oracle** | No change. | 0 | — | ✅ |

---

## CAN-FD topology

SystemCore gives us 5 CAN-FD buses @ 8 Mbps each. On a swerve + intake
+ elevator + shooter + climber robot we'll use 3 for motor groups and
keep 2 in reserve for future subsystems or bus fault isolation.

```
                ┌─────────────────────────────┐
                │         SystemCore           │
                │                              │
                │  CAN-FD 0  CAN-FD 1  CAN-FD 2 CAN-FD 3  CAN-FD 4 │
                └──┬───────────┬──────────┬──────┬─────────┬──────┘
                   │           │          │      │         │
         ┌─────────▼───┐  ┌────▼────┐  ┌──▼──┐  ▼        ▼
         │ DRIVETRAIN  │  │ SUPER-  │  │ PDH │  SPARE   SPARE
         │ 4× Kraken   │  │ STRUCT  │  │ 1×  │  (reserved for bus
         │ 4× Kraken   │  │ 4× NEO  │  │     │  fault isolation
         │ 4× CANcoder │  │ 2× NEO  │  │     │  and future expansion)
         │ (swerve)    │  │ 2× Thru │  │     │
         └─────────────┘  └─────────┘  └─────┘
```

Why split this way:
- **Drivetrain on its own bus** so swerve latency is deterministic and
  never shares bandwidth with superstructure motion.
- **Superstructure on a second bus** so intake/elevator/shooter retries
  don't stutter the drivetrain.
- **PDH alone on a third bus** so current monitoring survives motor
  bus failures (needed for brownout diagnosis).
- **Two spare buses** so a mid-match bus fault can be hot-swapped by
  re-IDing devices onto a spare bus via the OLED front panel.

8 Mbps CAN-FD means even the busy drivetrain bus runs at <20% load.
We're nowhere near saturating any single bus.

---

## Pigeon 2.0 decision

SystemCore has a built-in IMU (400 Hz quaternion + 3-axis accel + gyro
via the RP2350 with PREEMPT-RT timing). On paper, this eliminates the
need for a Pigeon 2.0 on the swerve drivetrain.

**Decision: keep Pigeon 2.0 as primary, SystemCore IMU as secondary
reference + fallback.**

Reasoning:
1. Pigeon 2.0 is a known quantity — 2 years of tuned swerve odometry
   behavior we don't want to re-validate during a championship season.
2. Pigeon 2.0 mounts near the center of rotation. SystemCore mounts
   wherever the electronics panel puts it, which may not be center.
3. The built-in IMU is a great cross-check for Pigeon drift and a
   free brownout-safe fallback if CAN bus 1 drops.
4. Cost is ~$150 for a part we already own.

Constructicon reads both, logs both via AdvantageKit, trusts Pigeon
for pose estimation, and raises an alarm if the two disagree by >5°.

---

## Power rail changes

The Jetson Orin Nano Super draws 6 W idle / 40 W peak, which the PDH
handles easily, but it needs a **regulated 5 V** rail that survives
motor brownout transients. A Pololu D36V50F5 5 V 5 A buck-boost
regulator off a 20 A PDH breaker covers this.

New power topology:

```
 Battery 12 V ──► PDH ──┬──► SystemCore (12 V direct, internal buck-boost)
                       │
                       ├──► 20 A breaker ──► Pololu D36V50F5 ──► Jetson (5 V @ 5 A)
                       │
                       ├──► Motor controllers (CAN-FD group)
                       ├──► VRM (radio + 5 V logic) ──► Radio / Ethernet switch
                       └──► Pigeon 2.0 (VRM 5 V)
```

Brownout behavior:
- SystemCore brownout configurable at 6.3 V (defaults there).
- Jetson buck-boost holds input down to ~4.5 V so it survives any
  brownout SystemCore does.
- If Jetson reboots anyway, whisper_bridge auto-starts in ~25 s. Robot
  keeps driving on SystemCore alone the whole time.

---

## Deploy + development workflow changes

SystemCore runs Linux 6.6 PREEMPT-RT with WPILib Java installed as a
normal userland process under a systemd unit. Deploy flow:

| Step | roboRIO (old) | SystemCore (new) |
|---|---|---|
| Build | `./gradlew build` | `./gradlew build` (same) |
| Deploy | `./gradlew deploy` → FTP to roboRIO | `./gradlew deploy` → ssh+scp to SystemCore |
| Riolog | `./gradlew riolog` | `./gradlew riolog` (WPILib 2027 renames but same) |
| Shell access | ssh `admin@roborio-2950-frc.local` | ssh `pi@systemcore-2950-frc.local` (default) |
| Logs | roboRIO console | `journalctl -u frc-user -f` |
| CAN trace | Phoenix Tuner / REV HW Client | Phoenix Tuner / REV HW Client (unchanged) |

Key difference: on SystemCore, we can ssh in and run standard Linux
tools (`htop`, `tcpdump`, `networktables-cli`) without going through
WPILib's opaque layer. This is a **huge** debug upgrade.

---

## Risks + unknowns

| Risk | Severity | Mitigation |
|---|---|---|
| 2027 WPILib release slips | High | Start porting Constructicon against beta releases as soon as they drop. Do NOT wait for GA. |
| Vendor deps (CTRE Phoenix, REV, PathPlanner, AdvantageKit, Choreo) lag | High | Pin versions that have 2027 SystemCore builds. Keep a 2026 roboRIO branch for offseason events until vendors catch up. |
| SystemCore + Jetson network quirks | Medium | Dry-run NT4 over on-robot Ethernet for 1 full hour before any event. Thermal + vibration test. |
| SystemCore brownout behavior differs from roboRIO | Medium | Characterize on the bench with a current ramp. Log voltage vs state transitions in AdvantageKit. |
| PREEMPT-RT userland process gets descheduled | Low | WPILib 2027 is expected to set SCHED_FIFO on the control loop. Verify before first event. |
| CAN-FD device firmware incompatibility | Low | Update all motor controllers + PDH + CANcoders to latest firmware before first practice day. |
| Jetson thermal throttle in robot enclosure | Low | Active Noctua fan + heatsink. Run 1 h thermal test at CP.14. |

---

## Timeline

| When | Milestone |
|---|---|
| **April 2026** | This doc published. ARCH_COACH_AI rev-3 published. Roadmap folded. |
| **July 2026** | Jetson + BOM ordered ($509). CP.1-CP.3 complete (bring-up + llama.cpp). |
| **August 2026** | CP.4-CP.8 complete (whisper_bridge, PhotonVision, YOLO training). |
| **September 2026** | CP.9-CP.12 complete (Eye on-robot, logger, P.5 dashboard, sim testing). |
| **October 2026** | CP.13-CP.14 complete (prompt refinement, thermal test). |
| **November 2026** | WPILib 2027 beta lands. Start Constructicon port on a branch. |
| **December 2026** | SystemCore port of Constructicon functional on bench robot. Integration dry run with Jetson coprocessor. |
| **January 2027** | Kickoff. 2027 WPILib GA. Final deploy to competition robot. |
| **March 2027** | First competition event. |

---

## References

- [ARCH_COACH_AI.md](ARCH_COACH_AI.md) — Whisper coprocessor rev-3 (authoritative for Jetson workloads)
- [ARCH_ELECTRICAL_SYSTEMS.md](ARCH_ELECTRICAL_SYSTEMS.md) — Needs update for new CAN-FD topology + Jetson power rail
- [ARCH_DRIVER_STATION.md](ARCH_DRIVER_STATION.md) — Needs update for Whisper coach panel
- [ARCH_CAD_PIPELINE.md](ARCH_CAD_PIPELINE.md) — Needs update for SystemCore + Jetson electronics panel
- [ENGINE_MASTER_ROADMAP.md](ENGINE_MASTER_ROADMAP.md) — Consolidated CP.1-CP.14 line items
- [SystemCore spec sheet (Limelight, June 15 2025 alpha)](https://downloads.limelightvision.io/documents/systemcore_specifications_june15_2025_alpha.pdf)

---

*Architecture umbrella doc — SystemCore Migration | THE ENGINE | Team 2950 The Devastators*
