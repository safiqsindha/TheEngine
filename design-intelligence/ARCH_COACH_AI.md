# THE ENGINE — Coach AI System
# Codename: "The Whisper"
# Target: March 2027 (first competition event)
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

A dedicated AI processing unit on the driver station shelf reads
the robot's game state via NetworkTables, runs a local language model,
and displays real-time strategic recommendations on a wired display
held by the drive coach. The Driver Station laptop is completely
untouched — zero additional CPU load.

The drive coach glances at their display and sees:
"CLIMB NOW — up by 12, Hub inactive for 14s, partner already scoring"

No other FRC team has this. It's legal, it's practical, and it turns
The Engine's autonomous intelligence into a teleop strategic advisor.

---

## Rules Compliance

### Why This Is Legal

1. The coprocessor connects to the Operator Console via Ethernet cable (wired).
   Per the FRC manual, any device connected to the OPERATOR CONSOLE is
   considered part of the ROBOT. The coprocessor IS part of the Operator Console.

2. The coach display connects to the coprocessor via HDMI or USB-C cable (wired).
   Items held or worn by DRIVE TEAM members are allowed on the field.

3. No wireless communication. No external connections. No remote sensing.
   The system reads only NetworkTables data — the same data Shuffleboard reads.

4. The OPERATOR CONSOLE size limit is 60" × 16" × 78" high. The coprocessor
   footprint is well within limits (exact size check TBD per target hardware).

5. Items may be used to "plan or track strategy for the purposes of
   communication of that strategy to other ALLIANCE members."

### What To Prepare For

Referees may ask about the setup. Have a one-sentence explanation ready:
"It's a second computer hardwired to our Operator Console that displays
game state information for our drive coach — same data as our dashboard,
just on a separate screen." If pressed, show the wired connections.

Consider submitting a Q&A before your first event: "Is a secondary
computing device, hardwired to the OPERATOR CONSOLE via Ethernet, that
reads NetworkTables data and displays strategy information to the DRIVE
COACH, compliant with G302 and R904?" This pre-clears any referee concerns.

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   ON THE ROBOT                       │
│                                                      │
│  Robot controller (SystemCore 2027+)                 │
│  ├── AutonomousStrategy.java                        │
│  │   └── publishes: /Strategy/Utilities/*           │
│  │       /Strategy/RecommendedAction                │
│  │       /Strategy/HubStatus                        │
│  ├── CycleTracker.java                              │
│  │   └── publishes: /CycleTracker/AvgCycleTime     │
│  ├── SuperstructureStateMachine.java                │
│  │   └── publishes: /Superstructure/CurrentState    │
│  └── FuelDetectionConsumer.java                     │
│      └── publishes: /Vision/FuelCount               │
│                                                      │
└──────────────────┬──────────────────────────────────┘
                   │ field WiFi (standard FRC comms)
                   ▼
┌─────────────────────────────────────────────────────┐
│              DRIVER STATION SHELF                    │
│                                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐ │
│  │  Driver Station       │  │  "The Whisper"       │ │
│  │  Laptop               │  │  (coprocessor TBD)   │ │
│  │                        │  │                      │ │
│  │  ONLY runs:            │  │  Runs:               │ │
│  │  - DS software         │  │  - Local LLM runtime │ │
│  │  - FMS connection      │  │  - Small instruct    │ │
│  │                        │  │    model (~3B Q4)    │ │
│  │  NO additional load    │  │  - NT client         │ │
│  │                        │  │  - Strategy bridge   │ │
│  └──────────┬─────────────┘  └──────┬───────────────┘ │
│             │                       │                  │
│             └───── Ethernet ────────┘                  │
│                    Switch                              │
│                                                        │
└────────────────────────────┬───────────────────────────┘
                             │ HDMI or USB-C (wired)
                             ▼
                   ┌──────────────────┐
                   │  Coach Display   │
                   │  (7" monitor     │
                   │   or tablet)     │
                   │                  │
                   │  Held by drive   │
                   │  coach           │
                   └──────────────────┘
```

---

## Hardware Bill of Materials

> **TBD — target hardware under evaluation (SystemCore-native vs Coral TPU vs Android tablet). This section will be rewritten once the decision is made.**

---

## Software Stack

### strategy_bridge.py (core loop)
```python
# Pseudocode — the main orchestration script

import ntcore
import requests  # to local LLM runtime (llama.cpp server, LiteRT, Ollama, etc.)
import time

# Connect to NetworkTables (robot publishes, we read)
nt = ntcore.NetworkTableInstance.getDefault()
nt.startClient4("whisper")
nt.setServer("10.29.50.2")  # Robot controller IP for team 2950

strategy_table = nt.getTable("Strategy")
cycle_table = nt.getTable("CycleTracker")
super_table = nt.getTable("Superstructure")

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
- Climb available: {climb_available}

Recommendation:"""

while True:
    # Read game state from NetworkTables
    state = {
        "time_remaining": strategy_table.getNumber("TimeRemaining", 0),
        "our_score": strategy_table.getNumber("AllianceScore", 0),
        "their_score": strategy_table.getNumber("OpponentScore", 0),
        "fuel_held": strategy_table.getNumber("FuelHeld", 0),
        "hub_status": strategy_table.getString("HubStatus", "UNKNOWN"),
        "hub_timer": strategy_table.getNumber("HubTimer", 0),
        "robot_state": super_table.getString("CurrentState", "IDLE"),
        "avg_cycle": cycle_table.getNumber("AvgCycleTime", 0),
        "is_endgame": state["time_remaining"] <= 30,
        "climb_available": state["time_remaining"] <= 30,
    }
    state["score_diff"] = f"+{state['our_score'] - state['their_score']}"
                          if state["our_score"] >= state["their_score"]
                          else str(state["our_score"] - state["their_score"])

    # Generate recommendation via local LLM runtime
    # (endpoint depends on backend — Ollama, llama.cpp server, LiteRT, etc.)
    prompt = PROMPT_TEMPLATE.format(**state)
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "whisper-coach-3b-q4",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 50}
    })
    recommendation = response.json()["response"].strip()

    # Publish to local web dashboard
    update_dashboard(state, recommendation)

    time.sleep(2.0)  # Update every 2 seconds
```

### Coach Dashboard (HTML served by FastAPI)
```
┌───────────────────────────────────────┐
│         THE WHISPER — LIVE            │
│                                       │
│  ┌─────────────────────────────────┐  │
│  │                                 │  │
│  │   COLLECT FUEL — HUB INACTIVE   │  │  ← Large text, color-coded
│  │   Hub activates in 9 seconds    │  │  ← Context line
│  │   Position near Hub for dump    │  │  ← LLM natural language
│  │                                 │  │
│  └─────────────────────────────────┘  │
│                                       │
│  TIME: 1:22    SCORE: 87-62 (+25)    │  ← Always visible
│  FUEL: 4       HUB: INACTIVE (9s)    │
│  STATE: COLLECTING    CYCLE: 4.8s    │
│                                       │
└───────────────────────────────────────┘
```

### Color Coding
| Recommendation Type | Background Color | Text Color |
|-------------------|-----------------|------------|
| SCORE NOW | Green (#22C55E) | White |
| COLLECT | Blue (#3B82F6) | White |
| CLIMB NOW | Red pulsing (#EF4444) | White |
| POSITION / WAIT | Cyan (#06B6D4) | Dark |
| DEFEND | Orange (#F97316) | Dark |
| WARNING / ERROR | Red solid (#DC2626) | White |

### Font Sizing (readability at arm's length)
| Element | Size | Font |
|---------|------|------|
| Recommendation action | 48px bold | Sans-serif |
| Context / LLM advice | 24px | Sans-serif |
| Score / time / state | 18px | Monospace |

---

## LLM Performance Specifications

| Metric | Requirement | Notes |
|--------|-------------|-------|
| Model | Small instruct LLM (~3B class) | ~2 GB Q4 model file |
| Inference latency | < 1 second per recommendation | Target-dependent, TBD |
| Memory usage | < 4 GB | Model + runtime |
| Power draw | < 15W | Target-dependent |
| Update frequency | Every 2 seconds | |
| Recommendation length | < 25 words | Enforced via num_predict |
| Temperature | 0.3 (low creativity, high consistency) | Deterministic enough for strategy |

### Model Selection Rationale
| Model | Params | Size (Q4) | Quality | Pick? |
|-------|--------|-----------|---------|-------|
| Phi-3 Mini | 3.8B | 2.3 GB | Good | Backup |
| Llama 3.2 3B | 3.2B | 2.0 GB | Very good | PRIMARY candidate |
| Llama 3.2 1B | 1.2B | 0.8 GB | Adequate | Fallback |
| Gemma 2 2B | 2.5B | 1.5 GB | Good | Alternative |
| Gemma 3 270M | 270M | ~0.2 GB | Surprising | Ultra-low-end fallback |

The 3B class is the sweet spot — fast enough for real-time updates,
smart enough for nuanced recommendations, small enough to fit in 4 GB
RAM alongside the runtime. Final model choice depends on target
hardware's inference backend (llama.cpp, LiteRT, Coral TFLite, etc.).

---

## Example Recommendations by Game State

| Game State | LLM Output |
|-----------|-----------|
| Hub active, holding 5 fuel, 1:30 left | "SCORE NOW. Dump all 5 fuel. Hub active for 14 more seconds." |
| Hub inactive, near depot, 1:00 left | "COLLECT. Hub activates in 11 seconds. Fill hopper from depot." |
| Hub inactive, full hopper, 0:45 left | "POSITION. Move to Hub scoring zone. Ready to dump in 6 seconds." |
| Up by 30, 0:25 left, not climbing | "CLIMB NOW. Lead is safe. Secure endgame points immediately." |
| Down by 15, 0:20 left, not climbing | "KEEP SCORING. Need 2 more cycles. Climb only if Hub goes inactive." |
| Alliance partner climbing, 0:15 left | "CLIMB. Partner is on Tower. Take adjacent rung. 12 seconds left." |
| Stall detected on intake | "INTAKE JAM. Reverse intake. Eject and retry. Don't force it." |
| Opponent playing heavy defense | "EVADE LEFT. Opponent targeting you. Score from the far side." |

---

## NetworkTables Keys Required

The robot code must publish these keys for The Whisper to read.
Most already exist in The Engine codebase. New keys marked with *.

| NT Key | Type | Source | Exists? |
|--------|------|--------|---------|
| /Strategy/TimeRemaining | double | AutonomousStrategy | ✅ |
| /Strategy/RecommendedAction | string | AutonomousStrategy | ✅ |
| /Strategy/HubStatus | string | AutonomousStrategy | * NEW |
| /Strategy/HubTimer | double | AutonomousStrategy | * NEW |
| /Strategy/AllianceScore | double | FMS / DriverStation | * NEW |
| /Strategy/OpponentScore | double | FMS / DriverStation | * NEW |
| /Strategy/FuelHeld | int | SuperstructureStateMachine | ✅ |
| /Strategy/Utilities/Score | double | AutonomousStrategy | ✅ |
| /Strategy/Utilities/Collect | double | AutonomousStrategy | ✅ |
| /Strategy/Utilities/Climb | double | AutonomousStrategy | ✅ |
| /Superstructure/CurrentState | string | SuperstructureStateMachine | ✅ |
| /CycleTracker/AvgCycleTime | double | CycleTracker | ✅ |
| /CycleTracker/TotalCycles | int | CycleTracker | ✅ |
| /StallDetector/IsStalled | boolean | StallDetector | ✅ |

4 new NT keys needed. Approximately 30 minutes of code to add.

---

## Development Roadmap

> **Development Roadmap and "What To Tell Judges" are below in the rev-2 section — those are the current authoritative versions pending SystemCore rewrite.**

---

### Color Coding

| Recommendation Type | Background | Meaning |
|-------------------|-----------|---------|
| SCORE NOW | Green #22C55E | Hub active, dump fuel |
| COLLECT | Blue #3B82F6 | Gather fuel, Hub inactive |
| CLIMB NOW | Red pulse #EF4444 | Endgame, secure points |
| POSITION / WAIT | Cyan #06B6D4 | Move to scoring position |
| DEFEND | Orange #F97316 | Block opponent |
| WARNING | Red solid #DC2626 | Stall, jam, or error |

---

## NetworkTables Keys Required

Most already exist in The Engine codebase. Keys marked NEW need 30 min of code.

| NT Key | Type | Source | Exists? |
|--------|------|--------|---------|
| /Strategy/TimeRemaining | double | AutonomousStrategy | Yes |
| /Strategy/RecommendedAction | string | AutonomousStrategy | Yes |
| /Strategy/HubStatus | string | AutonomousStrategy | NEW |
| /Strategy/HubTimer | double | AutonomousStrategy | NEW |
| /Strategy/AllianceScore | double | FMS / DriverStation | NEW |
| /Strategy/OpponentScore | double | FMS / DriverStation | NEW |
| /Strategy/FuelHeld | int | SuperstructureStateMachine | Yes |
| /Strategy/Utilities/Score | double | AutonomousStrategy | Yes |
| /Strategy/Utilities/Collect | double | AutonomousStrategy | Yes |
| /Strategy/Utilities/Climb | double | AutonomousStrategy | Yes |
| /Superstructure/CurrentState | string | SuperstructureStateMachine | Yes |
| /CycleTracker/AvgCycleTime | double | CycleTracker | Yes |
| /StallDetector/IsStalled | boolean | StallDetector | Yes |

---

## Example Recommendations

| Game State | Whisper Output |
|-----------|---------------|
| Hub active, 5 fuel held, 1:30 left | SCORE NOW. Dump all 5 fuel. Hub active for 14 more seconds. |
| Hub inactive, near depot, 1:00 left | COLLECT. Hub activates in 11s. Fill hopper from depot. |
| Hub inactive, full hopper, 0:45 left | POSITION. Move to Hub. Ready to dump in 6 seconds. |
| Up by 30, 0:25 left, not climbing | CLIMB NOW. Lead is safe. Secure endgame points. |
| Down by 15, 0:20 left, not climbing | KEEP SCORING. Need 2 more cycles. Climb only if Hub inactive. |
| Intake stalled | INTAKE JAM. Reverse intake. Eject and retry. |

---

## Development Roadmap

| Block | Task | Hours | Target |
|-------|------|-------|--------|
| W.1 | Install AI Edge Gallery on tablet, test Gemma 4 E2B inference | 2 | Oct 2026 |
| W.2 | Build Android app: NetworkTables client over Ethernet | 8 | Oct 2026 |
| W.3 | Build Android app: Gemma inference via LiteRT-LM | 8 | Oct 2026 |
| W.4 | Build Android app: Coach display UI (full-screen, color-coded) | 6 | Oct 2026 |
| W.5 | Wire USB-C Ethernet adapter, test on DS Ethernet switch | 2 | Nov 2026 |
| W.6 | Simulation testing (20+ sim matches, grade recommendations) | 8 | Nov 2026 |
| W.7 | Prompt refinement + live scrimmage test | 4 | Dec 2026 |
| **Total** | | **38** | |

---

## Fallback Modes

| Failure | Detection | Fallback |
|---------|-----------|----------|
| Gemma inference fails | No output for 5+ seconds | Display raw utility scores (no LLM needed) |
| NetworkTables disconnects | No data update for 5s | Show NO ROBOT DATA + last known state |
| Tablet battery low | Android low battery warning | Plug into field outlet USB, or coach operates without |
| Ethernet adapter disconnects | Network unreachable | Show DISCONNECTED, coach operates normally |
| App crashes | Android ANR detection | Restart app (< 10 seconds, Gemma reloads from cache) |

Every failure = operate like a normal FRC team. The Whisper is a bonus, never a dependency.

---

## Future Enhancements

| Enhancement | Description | When |
|-------------|-------------|------|
| Pre-match strategy | Feed scouting data to Gemma, generate printed match plan | After first event |
| Gemma 4 E4B upgrade | If tablet has 6GB+ RAM, upgrade for better reasoning | When E4B LiteRT-LM optimized |
| Voice output | Gemma generates text, Android TTS speaks it to coach via earbud | Evaluate rules first |
| Multimodal input | Point tablet camera at field, Gemma interprets what it sees | Rules concern (remote sensing) |
| Alliance partner display | Share Whisper data with alliance partners coach tablets | Requires alliance agreement |

---

## What To Tell Judges

Your Operator Console includes an Android tablet hardwired via USB-C
Ethernet to our driver station network. It runs a Google Gemma 4 AI
model completely locally on the tablet hardware. It reads game state
from our robot through NetworkTables and displays real-time strategic
recommendations to our drive coach. No cloud, no wireless, no external
connections. The entire system runs on a single tablet the coach holds.

Awards supported: Innovation in Control Award, Autonomous Award
(strategic intelligence extending into teleop), Excellence in
Engineering Award (novel application of on-device AI in robotics).

---

*Architecture document - The Whisper | THE ENGINE | Team 2950 The Devastators*
