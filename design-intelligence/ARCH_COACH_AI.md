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

1. The Jetson connects to the Operator Console via Ethernet cable (wired).
   Per the FRC manual, any device connected to the OPERATOR CONSOLE is
   considered part of the ROBOT. The Jetson IS part of the Operator Console.

2. The coach display connects to the Jetson via HDMI or USB-C cable (wired).
   Items held or worn by DRIVE TEAM members are allowed on the field.

3. No wireless communication. No external connections. No remote sensing.
   The system reads only NetworkTables data — the same data Shuffleboard reads.

4. The OPERATOR CONSOLE size limit is 60" × 16" × 78" high. The Jetson
   adds approximately 5" × 4" to the shelf footprint. Well within limits.

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
│  roboRIO                                             │
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
│  │  Driver Station       │  │  Jetson Orin Nano    │ │
│  │  Laptop               │  │  "The Whisper"       │ │
│  │                        │  │                      │ │
│  │  ONLY runs:            │  │  Runs:               │ │
│  │  - DS software         │  │  - Ollama            │ │
│  │  - FMS connection      │  │  - Llama 3.2 3B Q4   │ │
│  │                        │  │  - NT client         │ │
│  │  NO additional load    │  │  - FastAPI server    │ │
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

| Item | Purpose | Est. Cost | Source |
|------|---------|-----------|-------|
| NVIDIA Jetson Orin Nano 8GB Dev Kit | LLM inference + NT client | $249 | NVIDIA / Amazon |
| 7" HDMI IPS monitor (1024×600) | Coach display | $55 | Amazon |
| HDMI cable (3ft, thin) | Jetson → coach display | $8 | Amazon |
| Ethernet cable (3ft) | Jetson → DS Ethernet switch | $5 | Amazon |
| USB-C PD power bank (65W, 20000mAh) | Powers Jetson 6-10 hrs | $40 | Amazon |
| USB-C PD cable (1ft) | Power bank → Jetson | $8 | Amazon |
| 3D-printed enclosure | Protects Jetson on shelf | $5 | Print in-house |
| 8-port Ethernet switch (if not already owned) | Network hub on shelf | $20 | Amazon |
| **TOTAL** | | **~$390** | |

### Size Check (OPERATOR CONSOLE limits: 60" × 16")
| Component | Width | Depth |
|-----------|-------|-------|
| DS Laptop | ~15" | ~10" |
| Jetson in case | ~5" | ~4" |
| Ethernet switch | ~6" | ~3" |
| Power bank | ~6" | ~3" |
| **Total shelf footprint** | **~32"** | **~10"** |
| **Remaining** | **28"** | **6"** |

Plenty of room. The shelf is 69" wide and 12.25" deep.

---

## Software Stack

### Jetson Setup (one-time)
```
JetPack 6.0 (Ubuntu 22.04 + CUDA 12)
├── Ollama (LLM runtime)
│   └── llama3.2:3b-instruct-q4_K_M (2.0 GB model file)
├── Python 3.11
│   ├── pynetworktables (reads robot data from NT server)
│   ├── fastapi + uvicorn (serves coach dashboard)
│   └── strategy_bridge.py (orchestration script)
└── Chromium (kiosk mode on HDMI display)
    └── Coach dashboard (full-screen, auto-refreshing)
```

### strategy_bridge.py (core loop)
```python
# Pseudocode — the main orchestration script

import ntcore
import requests  # to Ollama local API
import time

# Connect to NetworkTables (robot publishes, we read)
nt = ntcore.NetworkTableInstance.getDefault()
nt.startClient4("whisper")
nt.setServer("10.29.50.2")  # roboRIO IP for team 2950

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

    # Generate recommendation via Ollama
    prompt = PROMPT_TEMPLATE.format(**state)
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "llama3.2:3b-instruct-q4_K_M",
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

| Metric | Requirement | Measured on Jetson Orin Nano |
|--------|-------------|---------------------------|
| Model | Llama 3.2 3B Instruct Q4_K_M | 2.0 GB model file |
| Inference latency | < 1 second | ~300ms for 50 tokens |
| Memory usage | < 4 GB | ~2.5 GB (model + runtime) |
| Power draw | < 15W | 7-15W depending on load |
| Update frequency | Every 2 seconds | Achievable with margin |
| Recommendation length | < 25 words | Enforced via num_predict |
| Temperature | 0.3 (low creativity, high consistency) | Deterministic enough for strategy |

### Model Selection Rationale
| Model | Params | Size (Q4) | Speed (Orin Nano) | Quality | Pick? |
|-------|--------|-----------|-------------------|---------|-------|
| Phi-3 Mini | 3.8B | 2.3 GB | ~350ms | Good | Backup |
| Llama 3.2 3B | 3.2B | 2.0 GB | ~300ms | Very good | PRIMARY |
| Llama 3.2 1B | 1.2B | 0.8 GB | ~150ms | Adequate | Fallback |
| Mistral 7B | 7.2B | 4.1 GB | ~800ms | Excellent | Too slow |
| Gemma 2 2B | 2.5B | 1.5 GB | ~250ms | Good | Alternative |

Llama 3.2 3B is the sweet spot — fast enough for real-time updates,
smart enough for nuanced recommendations, small enough for the Jetson's
8GB unified memory.

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

### Phase W.1: Hardware Setup (Week 1, 4 hours)
- Flash JetPack 6.0 on Jetson Orin Nano
- Install Ollama, pull Llama 3.2 3B Q4 model
- Verify inference speed: < 500ms for 50 tokens
- Connect HDMI monitor, verify display output

### Phase W.2: NetworkTables Bridge (Week 2, 8 hours)
- Install pynetworktables on Jetson
- Write strategy_bridge.py: reads NT → formats prompt → calls Ollama
- Add 4 new NT keys to robot code (HubStatus, HubTimer, scores)
- Test with simulated robot (maple-sim publishing to NT)

### Phase W.3: Coach Dashboard (Week 3, 8 hours)
- Build FastAPI web server serving HTML dashboard
- Color-coded recommendation display (48px action, 24px context)
- Auto-refreshing every 2 seconds via JavaScript fetch
- Chromium kiosk mode on Jetson HDMI output
- Test readability at arm's length (coach holding display)

### Phase W.4: Wiring & Packaging (Week 4, 2 hours)
- 3D print Jetson enclosure with ventilation
- Wire: Ethernet to switch, HDMI to coach display, USB-C to power bank
- Secure all cables with velcro and strain relief
- Verify everything fits within OPERATOR CONSOLE size limits
- Label all cables

### Phase W.5: Simulation Testing (Week 5, 8 hours)
- Run 20+ simulated matches via maple-sim
- Log every LLM recommendation + game state at time of recommendation
- Grade each recommendation: helpful / neutral / wrong
- Tune prompt template based on results
- Tune temperature and num_predict for consistency
- Test edge cases: what happens when NT disconnects? When hub status
  is unknown? When the match ends?

### Phase W.6: Prompt Refinement (Week 6, 4 hours)
- Identify the 5 most common game situations
- Verify recommendations are correct for each
- Add few-shot examples to prompt if needed
- Test with a student acting as drive coach — is the display
  readable and useful under simulated match stress?

### Phase W.7: Live Testing (Week 7, 4 hours)
- Deploy at practice event or scrimmage
- Drive coach uses the system for real matches
- Debrief after each match: "Was the recommendation helpful?
  Did you follow it? Would you have done something different?"
- Record: recommendations followed that helped, recommendations
  followed that hurt, recommendations ignored that would have helped

### Total: 38 hours across 7 weeks

---

## Fallback Modes

| Failure | Detection | Fallback |
|---------|-----------|----------|
| Jetson won't boot | No HDMI output | Coach operates without display (normal FRC) |
| Ollama crashes | Dashboard shows "LLM OFFLINE" | Dashboard still shows raw game state data |
| NetworkTables disconnects | No data for 5+ seconds | Dashboard shows "NO ROBOT DATA" + last known state |
| LLM generates gibberish | Recommendation > 30 words or contains non-strategy text | Display raw utility scores instead |
| Power bank dies | Jetson shuts down | Plug into field outlet if available, or operate without |
| HDMI cable disconnects | Coach display goes black | Coach looks at DS laptop dashboard (D.2) as backup |

The system is designed to degrade gracefully. Every failure mode
results in "operate like a normal FRC team" — which is still
competitive. The Whisper is a bonus, never a dependency.

---

## Future Enhancements

| Enhancement | Description | When |
|-------------|-------------|------|
| Pre-match strategy | Feed scouting data → LLM generates match plan → print on paper | After first event |
| Voice output | Text-to-speech through a bone conduction earpiece (rules TBD) | Evaluate rules first |
| Multi-match learning | Log recommendations + outcomes → fine-tune prompt between events | Second season |
| Alliance coordination | Share Whisper recommendations with alliance partners' coaches | Requires alliance agreement |
| Smart glasses | Replace handheld display with AR glasses (Vuzix, etc.) | When cost drops below $200 |

---

## What To Tell Judges

"Our Operator Console includes a dedicated AI processor — an NVIDIA Jetson
Orin Nano — hardwired to our driver station via Ethernet. It reads game state
data from our robot through NetworkTables, runs a local language model, and
displays real-time strategic recommendations to our drive coach on a wired
display. The entire system operates locally with no wireless communication
and no external connections. It's like having a data analyst on the drive
team who can process game state faster than any human."

This supports: Innovation in Control Award, Autonomous Award (autonomous
strategic intelligence extending into teleop), and Excellence in Engineering
Award (novel application of AI in competitive robotics).

---

*Architecture document — The Whisper | THE ENGINE | Team 2950 The Devastators*
