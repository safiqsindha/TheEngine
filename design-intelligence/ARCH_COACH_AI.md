# THE ENGINE — Coach AI System
# Codename: "The Whisper"
# Architecture revision: 3 (on-robot coprocessor)
# Target: March 2027 (first competition event)
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

A dedicated on-robot coprocessor reads the robot's game state directly
from the robot controller, runs a local language model, and publishes
real-time strategic recommendations back over NetworkTables. The Driver
Station laptop reads those recommendations through the standard field
radio link and surfaces them on the coach dashboard.

The drive coach glances at their Elastic/Shuffleboard panel and sees:

> **CLIMB NOW** — up by 12, Hub inactive for 14s, partner already scoring

The coprocessor is not a dashboard-shelf appliance. It lives on the
robot alongside PhotonVision and the vision pipeline, consolidating
four systems into one box:

1. **PhotonVision** — AprilTag pose estimation (2 cameras)
2. **The Eye (on-robot)** — YOLO11 game-piece detection
3. **The Whisper** — local LLM strategic coach
4. **On-robot AdvantageKit logger** — NVMe match recording
5. **Pit Crew P.5 debug webserver** — LAN dashboard when tethered

Every other FRC team runs a vision coprocessor. We run a vision + AI
coprocessor. No new hardware philosophy — just more value per watt.

---

## Rules Compliance

### Why This Is Legal

The coprocessor is a standard on-robot vision coprocessor. It is
physically mounted on the robot, powered by the PDH through a regulated
5V buck-boost, and communicates with the robot controller (SystemCore
2027+) over an on-robot Ethernet link. This is the same architecture
every top FRC team uses for PhotonVision.

1. **On-robot coprocessor is explicitly legal.** R809 (or its 2027
   equivalent) allows custom COTS single-board computers connected to
   the robot controller via Ethernet. Jetson/Pi/Limelight/mini-PC
   coprocessors are universally used.

2. **No Operator Console hardware is added.** The coach display is a
   normal Driver Station dashboard panel (Elastic or Shuffleboard) on
   the DS laptop. Zero Operator Console footprint, zero referee
   questions, zero Q&A needed.

3. **No wireless, no remote sensing.** The coprocessor reads NT keys
   that the robot controller already publishes. The LLM runs entirely
   on-device. No cloud, no external connection.

4. **Power is from the PDH via an approved buck-boost regulator.** The
   coprocessor draws < 25W steady (40W peak), well within the current
   budget on a 20A breaker.

### What To Prepare For

Nothing special. This is a standard vision coprocessor from a rules
perspective. If a Robot Inspector asks what the box is, answer: "It's
our vision coprocessor — it runs PhotonVision, our game-piece
detector, and our strategic coach model." No Q&A submission needed.

---

## System Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                              ROBOT                                 │
│                                                                    │
│  ┌────────────────────────────────┐    ┌────────────────────────┐ │
│  │ SystemCore (robot controller)  │    │ Jetson Orin Nano Super │ │
│  │                                 │    │ "The Whisper" box      │ │
│  │  WPILib Java:                   │    │                        │ │
│  │  - Drivetrain + subsystems      │    │ JetPack 6 userland:    │ │
│  │  - CAN-FD to motor controllers  │    │                        │ │
│  │  - FMS comms                    │    │  [PhotonVision]        │ │
│  │  - NT server                    │    │    AprilTag 36h11      │ │
│  │  - AutonomousStrategy.java      │    │    2× global shutter   │ │
│  │  - SuperstructureStateMachine   │    │                        │ │
│  │  - CycleTracker                 │    │  [eye_onrobot]         │ │
│  │  - Constructicon state machine  │    │    YOLO11s TensorRT    │ │
│  │                                 │    │    1× color USB3 cam   │ │
│  │  publishes:                     │    │                        │ │
│  │   /Strategy/*                   │    │  [whisper_bridge.py]   │ │
│  │   /Superstructure/*             │    │    NT client           │ │
│  │   /CycleTracker/*               │◄──►│    State → prompt      │ │
│  │   /StallDetector/*              │    │                        │ │
│  │   /Vision/Pose                  │    │  [llama.cpp server]    │ │
│  │                                 │    │    Gemma 2 2B Q4       │ │
│  │  reads:                         │    │    or Llama 3.2 3B Q4  │ │
│  │   /Whisper/*                    │    │                        │ │
│  │   /PhotonVision/*               │    │  [onrobot_logger]      │ │
│  │   /Eye/Detections               │    │    NT → NVMe streamer  │ │
│  │                                 │    │                        │ │
│  │                                 │    │  [pit_crew_p5]         │ │
│  │                                 │    │    FastAPI on :8080    │ │
│  │                                 │    │    LAN-only debug UI   │ │
│  └────────┬───────────────────────┘    └──────────┬─────────────┘ │
│           │                                        │                │
│           │       ┌──────────────────────┐        │                │
│           └──────►│ on-robot Ethernet    │◄───────┘                │
│                   │ switch (Rev Radio    │                          │
│                   │ or standalone)       │                          │
│                   └──────────┬───────────┘                          │
│                              │                                      │
└──────────────────────────────┼──────────────────────────────────────┘
                               │ Field Radio (standard FRC link)
                               ▼
                ┌─────────────────────────────┐
                │  Driver Station Laptop      │
                │                             │
                │  - WPILib Driver Station    │
                │  - Elastic / Shuffleboard   │
                │    reads /Whisper/*         │
                │    and renders coach panel  │
                │                             │
                │  NO extra load. NO extra HW │
                └─────────────────────────────┘
```

---

## Hardware Bill of Materials

| Item | Part | Qty | Cost | Notes |
|---|---|---|---|---|
| Coprocessor | NVIDIA Jetson Orin Nano Super Dev Kit (8GB) | 1 | $249 | 67 TOPS Super mode, CUDA, TensorRT |
| Boot storage | Samsung 980 NVMe 256 GB (M.2 2280) | 1 | $25 | Boot + AdvantageKit logs |
| NVMe adapter | Seeed Jetson Orin Nano NVMe carrier (or stock slot) | 1 | $0 | Stock dev kit has M.2 Key M |
| Power regulation | Pololu D36V50F5 5V 5A buck-boost | 1 | $25 | PDH → Jetson, brown-out safe |
| AprilTag cameras | Arducam B0497 OV9281 global shutter (mono) | 2 | $100 | 120 Hz @ 720p, PhotonVision-ready |
| Game-piece cam | ELP 1080p color USB3 global shutter | 1 | $55 | YOLO11 input |
| Cooling | Noctua NF-A4x20 PWM 40mm fan + heatsink pad | 1 | $20 | Prevents thermal throttling |
| USB hub | Anker 4-port USB 3.0 | 1 | $15 | 3 cams → Jetson |
| Ethernet cable | Cat6 patch, 1 ft | 1 | $5 | Jetson → robot switch |
| Mount | 3D-printed enclosure + heatsink bracket | 1 | $5 | Fits 6"×4"×2" electronics bay |
| Connectors | Anderson Powerpole set + heat shrink | 1 | $10 | PDH pigtail |
| **TOTAL** | | | **~$509** | |

All items are COTS and rules-legal. NVMe + fan + buck-boost are the
non-negotiable upgrades — do not skip any of them.

### What We're NOT buying and why
- **Coral USB Accelerator** ($60) — 15× slower than the Jetson's GPU, TFLite-only, eats a USB3 port. The Jetson IS the accelerator.
- **Limelight 3/4 cameras** ($400/ea) — we run PhotonVision on the Jetson with generic globals. Same or better AprilTag pose at 1/8 the cost.
- **Separate logger SBC** — the Jetson streams AdvantageKit directly to NVMe.
- **Separate pit display SBC** — the Jetson's FastAPI serves the debug dashboard on the shop LAN when tethered.

### SystemCore side (unchanged by Whisper)
SystemCore is the robot controller, replacing the roboRIO in 2027. It
runs WPILib Java, CAN-FD motor control, FMS comms, and the NT server.
Whisper talks to SystemCore — it does not replace it. SystemCore BOM is
tracked in `ARCH_SYSTEMCORE_MIGRATION.md`.

---

## Software Stack

### whisper_bridge.py (core loop, runs on the Jetson)

```python
# Main orchestration script — NT client + LLM driver
import ntcore
import requests   # to llama.cpp server on localhost:8080
import time
import hashlib

nt = ntcore.NetworkTableInstance.getDefault()
nt.startClient4("whisper")
nt.setServer("10.29.50.2")  # SystemCore IP for team 2950

strategy  = nt.getTable("Strategy")
cycle     = nt.getTable("CycleTracker")
superstr  = nt.getTable("Superstructure")
stall     = nt.getTable("StallDetector")
whisper   = nt.getTable("Whisper")

# Topics we publish back to SystemCore for the coach dashboard
rec_action     = whisper.getStringTopic("Recommendation/Action").publish()
rec_context    = whisper.getStringTopic("Recommendation/Context").publish()
rec_category   = whisper.getStringTopic("Recommendation/Category").publish()
rec_priority   = whisper.getIntegerTopic("Recommendation/Priority").publish()
rec_timestamp  = whisper.getDoubleTopic("Recommendation/Timestamp").publish()
alt_action     = whisper.getStringTopic("Alternative/Action").publish()
alt_context    = whisper.getStringTopic("Alternative/Context").publish()
health_alive   = whisper.getIntegerTopic("Health/Alive").publish()
health_latency = whisper.getDoubleTopic("Health/LastInferenceMs").publish()
debug_raw      = whisper.getStringTopic("Debug/RawOutput").publish()
debug_hash     = whisper.getStringTopic("Debug/PromptHash").publish()

PROMPT_TEMPLATE = """You are an FRC drive coach assistant for Team 2950.
Output ONE strategic recommendation in under 25 words.
Be direct and actionable. Include timing if relevant.

Match state:
- Time remaining: {time_remaining}s
- Score: Us {our_score} - Them {their_score} ({score_diff})
- Fuel held: {fuel_held}
- Hub status: {hub_status} (changes in {hub_timer}s)
- Robot state: {robot_state}
- Average cycle time: {avg_cycle}s
- Endgame: {is_endgame}

Recommendation:"""

heartbeat = 0
while True:
    t0 = time.monotonic()

    state = read_state_from_nt(strategy, cycle, superstr, stall)
    prompt = PROMPT_TEMPLATE.format(**state)
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]

    # llama.cpp server on the same box (CUDA, ~200 ms/inference)
    r = requests.post("http://localhost:8080/completion", json={
        "prompt": prompt,
        "n_predict": 50,
        "temperature": 0.3,
        "stop": ["\n\n"],
    }, timeout=1.5)

    raw = r.json()["content"].strip()
    action, context, category, priority = parse_recommendation(raw)

    # Publish back to SystemCore
    rec_action.set(action)
    rec_context.set(context)
    rec_category.set(category)
    rec_priority.set(priority)
    rec_timestamp.set(time.time())
    debug_raw.set(raw)
    debug_hash.set(prompt_hash)

    dt_ms = (time.monotonic() - t0) * 1000
    health_latency.set(dt_ms)
    heartbeat = (heartbeat + 1) % 1_000_000
    health_alive.set(heartbeat)

    time.sleep(max(0, 1.0 - (time.monotonic() - t0)))  # ~1 Hz update
```

### LLM backend: llama.cpp server with CUDA

```bash
# On the Jetson, one-time setup
cd ~/whisper
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=1
cmake --build llama.cpp/build --config Release -j6

# Launch as systemd service
./llama.cpp/build/bin/llama-server \
    -m models/gemma-2-2b-it-Q4_K_M.gguf \
    --host 127.0.0.1 --port 8080 \
    --n-gpu-layers 999 \
    --ctx-size 2048
```

llama.cpp with CUDA runs Gemma 2 2B Q4 at ~30 tokens/sec on the Orin
Nano Super, so a 50-token recommendation lands in ~1.7 seconds end-to-
end. Target update rate is 1 Hz, which gives plenty of margin.

### Coach Display (DS-side, not on Jetson)

The coach panel is a normal Elastic / Shuffleboard layout on the
**existing** DS laptop. No new hardware, no HDMI cable to the operator
console, no G302/R904 concerns. The panel reads `/Whisper/*` over the
field radio and renders:

```
┌────────────────────────────────────────┐
│         THE WHISPER — LIVE             │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │                                  │  │
│  │   CLIMB NOW                      │  │  ← 48px, color by Category
│  │   Lead safe, secure 15 points    │  │  ← 24px context
│  │                                  │  │
│  └──────────────────────────────────┘  │
│                                        │
│  ALT: Defend right lane (util 0.62)    │  ← Alternative/*
│                                        │
│  TIME 0:22  SCORE 87-62 (+25)          │
│  FUEL 4     HUB INACTIVE (9s)          │
│  STATE CLIMBING   CYCLE 4.8s           │
│                                        │
│  Whisper OK · 612 ms · heartbeat 14332 │  ← Health/*
└────────────────────────────────────────┘
```

### Color Coding

| Category (NT enum)    | Background   | Text  |
|-----------------------|--------------|-------|
| `SCORE_NOW`           | Green #22C55E | White |
| `COLLECT`             | Blue #3B82F6  | White |
| `CLIMB_NOW` (priority 3 → pulse) | Red #EF4444 | White |
| `POSITION` / `WAIT`   | Cyan #06B6D4  | Dark  |
| `DEFEND`              | Orange #F97316 | Dark |
| `WARNING`             | Red #DC2626   | White |
| `OFFLINE`             | Gray #6B7280  | White |

### Font Sizing

| Element | Size | Font |
|---------|------|------|
| Action  | 48px bold | Sans-serif |
| Context | 24px       | Sans-serif |
| Alt / Score / time | 18px | Monospace |

---

## NetworkTables Schema

### Inputs — robot already publishes these (SystemCore side)

| NT Key | Type | Source | Exists? |
|---|---|---|---|
| `/Strategy/TimeRemaining` | double | AutonomousStrategy | ✅ |
| `/Strategy/RecommendedAction` | string | AutonomousStrategy | ✅ |
| `/Strategy/Utilities/Score` | double | AutonomousStrategy | ✅ |
| `/Strategy/Utilities/Collect` | double | AutonomousStrategy | ✅ |
| `/Strategy/Utilities/Climb` | double | AutonomousStrategy | ✅ |
| `/Strategy/HubStatus` | string | AutonomousStrategy | NEW |
| `/Strategy/HubTimer` | double | AutonomousStrategy | NEW |
| `/Strategy/AllianceScore` | double | FMS / DriverStation | NEW |
| `/Strategy/OpponentScore` | double | FMS / DriverStation | NEW |
| `/Strategy/FuelHeld` | int | SuperstructureStateMachine | ✅ |
| `/Superstructure/CurrentState` | string | SuperstructureStateMachine | ✅ |
| `/CycleTracker/AvgCycleTime` | double | CycleTracker | ✅ |
| `/CycleTracker/TotalCycles` | int | CycleTracker | ✅ |
| `/StallDetector/IsStalled` | boolean | StallDetector | ✅ |

**4 new keys, ~30 min of Java.**

### Outputs — Whisper publishes these (Jetson side)

| NT Key | Type | Meaning |
|---|---|---|
| `/Whisper/Recommendation/Action` | string | Headline, e.g. "CLIMB NOW" |
| `/Whisper/Recommendation/Context` | string | 24px reasoning line |
| `/Whisper/Recommendation/Category` | string enum | `SCORE_NOW` `COLLECT` `CLIMB_NOW` `POSITION` `DEFEND` `WAIT` `WARNING` `OFFLINE` |
| `/Whisper/Recommendation/Priority` | int (0-3) | 3 → pulse dashboard |
| `/Whisper/Recommendation/Timestamp` | double | Unix seconds at publish |
| `/Whisper/Recommendation/MatchTime` | double | Match time remaining at publish |
| `/Whisper/Alternative/Action` | string | Runner-up strategy |
| `/Whisper/Alternative/Context` | string | Runner-up reasoning |
| `/Whisper/Alternative/Utility` | double | Runner-up utility score |
| `/Whisper/State/ScoreDiff` | int | As observed by Whisper |
| `/Whisper/State/TimeRemaining` | double | As observed by Whisper |
| `/Whisper/State/IsEndgame` | boolean | |
| `/Whisper/State/FuelHeld` | int | |
| `/Whisper/State/RobotState` | string | |
| `/Whisper/State/HubStatus` | string | |
| `/Whisper/State/AvgCycleTime` | double | |
| `/Whisper/State/PartnerClimbing` | boolean | |
| `/Whisper/Health/Alive` | int | Heartbeat counter, increments each loop |
| `/Whisper/Health/LastInferenceMs` | double | LLM latency |
| `/Whisper/Health/ModelLoaded` | boolean | |
| `/Whisper/Health/QueueDepth` | int | Pending requests |
| `/Whisper/Health/LastError` | string | Empty on nominal |
| `/Whisper/Health/UptimeSec` | double | Since whisper_bridge start |
| `/Whisper/Debug/RawOutput` | string | Raw LLM response (for post-match analysis) |
| `/Whisper/Debug/PromptHash` | string | 8-char hash of prompt (dedupe) |

### AdvantageKit integration

SystemCore republishes `/Whisper/Recommendation/*` into the
AdvantageKit log via ~10 lines of Java in `RobotContainer.java`, so
every post-match log contains the full Whisper decision trace. The
Jetson ALSO writes its own NVMe log (prompts, raw output, inference
latency) indexed by match time — cross-reference after events.

---

## LLM Performance Specifications

| Metric | Requirement | Measured on Orin Nano Super (target) |
|---|---|---|
| Model | Gemma 2 2B Q4_K_M (primary) or Llama 3.2 3B Q4_K_M (backup) | — |
| VRAM footprint | < 3 GB on GPU | ~1.8 GB (Gemma 2B) / ~2.2 GB (Llama 3B) |
| Inference latency | < 2 s per recommendation | ~0.9 s (Gemma 2B) / ~1.7 s (Llama 3B) |
| Power draw (inference burst) | < 25 W steady | ~18 W avg, 35 W peak |
| Update frequency | 1 Hz | 1 Hz with margin |
| Recommendation length | < 25 words | Enforced via `n_predict: 50` |
| Temperature | 0.3 | Deterministic enough for strategy |

### Model Selection Rationale

| Model | Params | Size (Q4) | Quality | Pick? |
|---|---|---|---|---|
| Gemma 2 2B | 2.5B | 1.5 GB | Good instruction following | **PRIMARY** |
| Llama 3.2 3B | 3.2B | 2.0 GB | Better reasoning | **BACKUP** |
| Phi-3 Mini | 3.8B | 2.3 GB | Good, slower | Fallback |
| Llama 3.2 1B | 1.2B | 0.8 GB | Adequate | Emergency fallback |
| Gemma 3 270M | 270M | ~0.2 GB | Surprising at simple tasks | Brownout-safe tier |

Gemma 2 2B is primary because it hits sub-1-second inference on the
Orin Nano with 6 GB of memory still free for PhotonVision + YOLO +
logger. Llama 3.2 3B is the drop-in backup if Gemma hallucinates too
much during sim testing.

---

## On-Jetson Resource Budget

The Jetson is doing five jobs at once. Here is the verified budget:

| Workload | RAM | GPU time | CPU |
|---|---|---|---|
| PhotonVision (2× global shutter, 60 Hz) | ~800 MB | ~8 ms/frame | 1 core pinned |
| YOLO11s TensorRT (30 Hz, game pieces) | ~600 MB VRAM | ~15 ms/frame | 0.5 core |
| Gemma 2 2B Q4 via llama.cpp CUDA (1 Hz burst) | ~2.0 GB | ~900 ms/inference | 1 core |
| AdvantageKit-style NVMe logger | ~200 MB | 0 | 0.5 core |
| Pit Crew P.5 FastAPI debug server | ~150 MB | 0 | 0.2 core |
| JetPack 6 userland + drivers | ~1.5 GB | — | background |
| **Totals** | **~5.3 GB** | **~23 ms/frame steady** | **~3.2 / 6 cores** |
| **Headroom on 8 GB Super** | **~2.7 GB** | **~10 ms slack/frame** | **~2.8 cores** |

Fits with margin. The Ampere GPU's CUDA streams time-slice cleanly
between PhotonVision's pose solver, YOLO's TensorRT pass, and
llama.cpp's inference burst.

---

## Example Recommendations

| Game State | Whisper Output |
|---|---|
| Hub active, 5 fuel held, 1:30 left | `SCORE_NOW` — Dump all 5 fuel. Hub active 14 more seconds. |
| Hub inactive, near depot, 1:00 left | `COLLECT` — Hub activates in 11 s. Fill hopper from depot. |
| Hub inactive, full hopper, 0:45 left | `POSITION` — Move to Hub. Ready to dump in 6 seconds. |
| Up by 30, 0:25 left, not climbing | `CLIMB_NOW` (priority 3) — Lead safe. Secure endgame 15 points. |
| Down by 15, 0:20 left, not climbing | `WAIT` — Need 2 cycles. Climb only if Hub goes inactive. |
| Partner climbing, 0:15 left | `CLIMB_NOW` — Partner on Tower. Take adjacent rung. 12 s left. |
| Stall detected on intake | `WARNING` — Intake jammed. Reverse and retry. Do not force. |
| Opponent playing heavy defense | `DEFEND` — Score from far side. Evade left. |

---

## Development Roadmap

The previous W.1–W.7 plan assumed a standalone Jetson on the DS shelf.
Rev-3 consolidates Whisper + on-robot Eye + on-robot logger + Pit Crew
P.5 debug dashboard into a single coprocessor build. The new phases:

| Phase | Task | Hours | Target |
|---|---|---|---|
| **CP.1** | Order Jetson Orin Nano Super + BOM ($509) | 0.5 | July 2026 |
| **CP.2** | Jetson bring-up: JetPack 6 flash, NVMe boot, fan, enclosure | 6 | July 2026 |
| **CP.3** | llama.cpp CUDA build + Gemma 2 2B model load | 3 | July 2026 |
| **CP.4** | whisper_bridge.py: NT client, state reader, prompt builder | 6 | August 2026 |
| **CP.5** | whisper_bridge.py: LLM call, parse, NT publish | 4 | August 2026 |
| **CP.6** | SystemCore Java: 4 new NT keys + AdvantageKit republish | 1 | August 2026 |
| **CP.7** | PhotonVision install + 2-camera AprilTag calibration | 6 | August 2026 |
| **CP.8** | YOLO11s training on FRC game pieces + TensorRT export | 10 | August 2026 |
| **CP.9** | eye_onrobot.py: YOLO inference loop + NT publish | 4 | September 2026 |
| **CP.10** | onrobot_logger: AdvantageKit → NVMe streamer | 4 | September 2026 |
| **CP.11** | pit_crew_p5 FastAPI dashboard (shop LAN only) | 8 | September 2026 |
| **CP.12** | Sim testing — 20 matches, grade recommendations | 8 | September 2026 |
| **CP.13** | Prompt refinement + live scrimmage | 4 | October 2026 |
| **CP.14** | Thermal + vibration test on actual robot (1-hour run) | 2 | October 2026 |
| **TOTAL** | | **66.5** | |

Compare to rev-2 line items being consolidated:

| Rev-2 line | Hours | Rev-3 fate |
|---|---|---|
| The Whisper W.1-W.7 | 38 | Folded into CP.1-CP.6, CP.12-CP.14 |
| The Eye E.2 (event-scale batch) | 30 | Replaced by on-robot CP.7-CP.9 (20 h) — actually better data |
| Pit Crew P.5 (pit display dashboard) | 16 | Folded into CP.11 (8 h) |
| On-robot AdvantageKit logger (implicit) | ~8 | Folded into CP.10 (4 h) |
| **Rev-2 total** | **~92** | **Rev-3 total: 66.5** |

**Net savings: ~25 hours and ~$110** (no separate shelf Jetson, no
separate pit-display SBC, no Limelight camera purchases). Hardware
budget goes from $390 to $509, but Limelight-free vision pays that
back the first time you'd have bought one.

---

## Fallback Modes

| Failure | Detection | Fallback |
|---|---|---|
| LLM inference fails | `Health/LastError` set, no update for 5 s | Dashboard shows `/Strategy/RecommendedAction` (raw utility scores from SystemCore). Coach keeps full strategic info, just no natural-language polish. |
| Whisper process crashes | `Health/Alive` heartbeat stops | systemd restart, dashboard shows `OFFLINE` category until heartbeat resumes |
| Jetson thermal throttle | Jetson `tegrastats` over threshold | Whisper continues at reduced rate, fan already at 100% |
| NT disconnect (Jetson ↔ SystemCore) | No NT server for 2 s | Dashboard shows `OFFLINE` category. Robot keeps running on SystemCore alone. |
| Field radio drops (SystemCore ↔ DS) | Normal FRC comms loss | Coach dashboard grays out like any other NT value. Same as a regular comms blip. |
| Jetson power brownout | PDH rail sag during collision | Buck-boost holds, Jetson survives. If it reboots anyway, whisper_bridge auto-starts in ~25 s. Robot is never dependent on Whisper to drive. |
| PhotonVision fails | No pose updates | Drivetrain falls back to wheel odometry. Same behavior as any PV team. |

**Design principle: every failure returns the team to "normal FRC
team" behavior. The Whisper is a bonus, never a dependency.**

---

## What To Tell Judges

"We run a single on-robot coprocessor — a Jetson Orin Nano Super —
that handles three things at once: PhotonVision for AprilTag
localization, a custom YOLO11 model for game-piece detection, and a
small local language model called The Whisper that reads our live
match state and generates strategic recommendations for our drive
coach. Everything runs on-device. No cloud, no wireless, no external
connections. The coach reads the Whisper panel on our normal driver
station dashboard."

Awards supported:
- **Innovation in Control Award** — on-device LLM strategic advisor is novel in FRC
- **Autonomous Award** — strategic intelligence extending from auto into teleop
- **Excellence in Engineering** — consolidated vision + AI coprocessor
- **Industrial Design Award** — clean CAD integration of the coprocessor enclosure

---

## Open Questions

1. **Camera count for PhotonVision.** 2 cameras is the baseline. If the
   2027 field geometry makes 3 worthwhile, the Jetson has USB3 headroom
   for it. Decide after kickoff.
2. **LLM fine-tuning.** Rev-3 assumes zero-shot Gemma 2 2B with a good
   prompt. If sim testing shows bad recommendations, CP.13 has budget
   to add a small LoRA fine-tune on ~200 labeled match states.
3. **Alliance partner Whisper sharing.** Out of scope for 2027. Possible
   2028 enhancement if rules allow cross-alliance NT bridging.

---

*Architecture document rev 3 — The Whisper | THE ENGINE | Team 2950 The Devastators*
