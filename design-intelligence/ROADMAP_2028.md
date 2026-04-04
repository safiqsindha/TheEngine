# THE ENGINE — 2028 Season Roadmap
# Building on everything from 2026-2027
# ═══════════════════════════════════════════════════════════════════════════════

## Where You Are After 2027

By the end of the 2027 competition season, The Engine gives you:
- Proven swerve platform with NEO + SPARK MAX (2 seasons of competition data)
- 8 modular mechanism modules (intake, indexer, elevator, wrist, turret, flywheel,
  climber with rotation, drivetrain)
- Vision pipeline with Limelight YOLO + AprilTag dual pipeline
- Autonomous intelligence stack (A*, decision engine, dynamic avoidance)
- Historical design database (50+ robots, cross-season patterns, prediction engine)
- 1-2 seasons of Statbotics performance data on YOUR OWN ROBOT
- Student team trained on the entire stack

## What Changes for 2028

### 1. On-Robot LLM Strategist

**Hardware:** Add a Jetson Orin Nano ($250) as a coprocessor mounted inside the
robot frame. Connected to roboRIO via NetworkTables over Ethernet.

**Model:** Gemma 3 1B or Phi-4 mini, quantized to 4-bit (with TurboQuant-style
KV cache compression if available). Fits in 2-3GB RAM, leaving headroom for
context. Runs entirely on-device — no internet needed, FRC legal.

**Pre-Match Strategy (deploy first):**
During the ~60 second setup period before a match, the Jetson runs the LLM with:
- Scouting data for all 6 robots on the field (pulled from your scouting app)
- Your robot's capabilities (from hardware_config.ini and performance logs)
- Alliance partner capabilities and weaknesses
- Opponent tendencies and weak spots

The LLM generates:
- A natural language strategy briefing displayed on the driver station
- An auto-routine recommendation (which of your 5-10 pre-built autos to run)
- Target priority order (which scoring locations to prefer based on opponent defense)
- A defensive counter-strategy if you're likely to be defended

The driver reads the briefing, confirms or overrides the auto selection, and the
match starts. Time from data input to strategy output: 5-10 seconds on Jetson.

**Post-Match Analysis (deploy second):**
After each match, the Jetson reads the AdvantageKit WPILOG and generates:
- Natural language match debrief ("Cycle 4 was 3.2s — intake jammed at 45.3s.
  Auto scored 2 of 3 targets. Climber engaged in 1.8s, 0.3s slower than average.")
- PID adjustment recommendations based on path-following error analysis
- Strategy adjustments for the next match
- Comparison to scouting predictions ("Opponent 3847 scored 15% less than expected,
  their intake may be broken — consider targeting their weak side")

The pit crew reviews this between matches instead of manually scrubbing through
AdvantageScope. It saves 5-10 minutes per match cycle.

**Mid-Match Strategic Layer (deploy last, experimental):**
Every 3-5 seconds during the match, the LLM evaluates:
- Current score differential
- Time remaining
- Game piece positions from vision
- Opponent positions from vision
- Current robot state (holding game piece? elevator position? health?)

It outputs a single strategic directive to the decision engine:
- "PRIORITIZE_SCORING" (we're behind, cycle faster)
- "PLAY_DEFENSE" (we're ahead, slow opponents down)
- "CLIMB_NOW" (time is short, secure endgame points)
- "SWITCH_TARGET" (current target is contested, go elsewhere)

The decision engine still makes the moment-to-moment control decisions
(which specific target, which path). The LLM provides the 30,000-foot view.

This is the Google DeepMind architecture: Gemini Robotics-ER (slow, strategic)
tells Gemini Robotics (fast, action) what to focus on.

### 2. Sim-to-Real Transfer with maple-sim

254 used maple-sim for the first time in 2025. By 2028 it will be more mature.

**What to build:**
- Import your actual robot CAD (with correct masses, moments of inertia, gear
  ratios) into maple-sim
- Run every autonomous routine in simulation before running on hardware
- Use AdvantageKit replay to compare sim predictions vs real match results
- Identify discrepancies between sim and real → fix the sim model → iterate

**The competitive advantage:**
When you swap modules for a new game (e.g., attach the elevator module for 2028),
you can test autonomous routines in simulation BEFORE the mechanism is fully built.
Software development doesn't wait for hardware. Drivers can practice in sim while
the pit crew assembles.

Teams that used sim in 2025 (254, 6328) iterated 3-5x faster on auto routines
than teams that required physical hardware for every test.

### 3. Advanced Vision: Multi-Camera Fusion

**Hardware:** Add a third camera — a global shutter USB camera (Arducam OV9281,
~$30) mounted low on the robot pointing at the ground/intake area.

**Why:** The Limelights face outward for AprilTags and game pieces at distance.
But they can't see what's happening inside your intake. A downward-facing camera
watches the game piece enter the intake, confirms successful acquisition, detects
jams, and triggers state transitions more reliably than beam break sensors.

**Implementation:**
Run a tiny YOLOv8-nano model on the roboRIO 2's coprocessor mode or on the
Jetson. It detects: game piece entering intake (trigger INTAKING → STAGING),
game piece jammed (trigger auto-reverse), game piece fully seated in end effector
(trigger ready-to-score). This replaces beam break sensors with a more reliable,
software-defined sensor that works with any game piece shape.

### 4. Alliance Communication Protocol

**What:** A simple UDP protocol that shares robot pose, intended target, and
current state between the 3 alliance robots during a match. FRC allows
robot-to-robot communication via the field network.

**Why:** Without communication, two alliance robots often drive to the same
game piece, wasting a cycle. With communication:
- Robot A broadcasts "I'm going to game piece at (5.2, 3.1)"
- Robot B sees this and diverts to (7.8, 2.4) instead
- Robot C knows it should play defense because A and B are scoring

254 implies they have this ("feeder strategy selection for coordinated alliance
play" in their 2022 binder). No team has published the protocol.

**Implementation:**
NetworkTables supports cross-robot communication via the FMS network. Each
robot publishes a small struct: {pose_x, pose_y, heading, intended_target_x,
intended_target_y, current_state, held_game_piece_count}. The decision engine
reads all three robots' published states and incorporates them into target
scoring. "Target already claimed by alliance partner" → penalty in utility
function → robot picks a different target.

This is a 1-2 day software project that potentially saves 2-3 wasted cycles
per match. At 4-6 points per cycle, that's 8-18 extra points per match.

### 5. Predictive Opponent Modeling

**What:** Track opponent robot behavior across multiple matches at an event
and predict their next actions during a match.

**How:** Your scouting data + vision-based opponent tracking gives you:
- Opponent A always scores on the left side
- Opponent B plays defense after 90 seconds
- Opponent C never climbs

Feed this to the LLM strategist pre-match. It generates counter-strategies:
- "Opponent A goes left — we go right to avoid contention"
- "Opponent B defends late — score aggressively in first 90 seconds"
- "Opponent C won't climb — if we're ahead, we don't need to rush our climb"

During the match, the vision system tracks opponent positions and the decision
engine adjusts based on where opponents actually are vs where they were predicted
to be. If an opponent breaks from their usual pattern, the system adapts.

### 6. Continuous Learning Between Events

**What:** After each event, feed all match logs, scouting data, and strategy
outcomes into the LLM. It generates a "lessons learned" document and updates
the decision engine's utility function weights.

**Example:**
After Event 1: "We won 80% of matches where we scored 3+ game pieces in auto.
We lost 70% of matches where we were defended in the first 30 seconds. Auto
scoring should be weighted 25% higher. Anti-defense maneuvering should trigger
earlier (at 0.5m opponent proximity instead of 1.0m)."

These adjustments are applied to The Engine's Constants.java between events.
By Event 3 or 4, the robot's strategy has self-tuned based on empirical
competition data.

### 7. Hardware Upgrade Path

By 2028, consider:
- **REV SPARK Flex** (if available) — faster CAN frame rates than SPARK MAX
- **NavX3** or **Pigeon 3** — improved gyro drift performance
- **Limelight 5** (if released) — faster Hailo accelerator, better camera
- **WCP X2i or X3 swerve** — 254 switched from SDS to WCP in 2025, likely
  because WCP offered wider grippier wheels and gear-based azimuth (no belt)
- **NEO Vortex** — REV's next-gen motor if it outperforms NEO on power density

The modular design means hardware upgrades are isolated changes. Swap a motor,
update hardware_config.ini, regenerate configs, done.

## 2028 Season Timeline

| Month | Activity | Deliverable |
|-------|----------|-------------|
| Apr 2027 | Competition season ends, collect data | Event performance logs |
| May-Jun 2027 | Post-season analysis, LLM strategist research | Architecture document |
| Jul-Aug 2027 | Build Jetson coprocessor module + LLM integration | Pre-match strategist working |
| Sep 2027 | Post-match analyzer deployed, sim-to-real pipeline | Full LLM pipeline |
| Oct-Nov 2027 | Alliance communication protocol | Cross-robot coordination |
| Dec 2027 | Validate prediction engine against 2027 game | Prediction engine V2 |
| Jan 2028 | Kickoff — prediction engine + LLM strategist + modular hardware | Competition-ready in 48 hours |
| Feb-Mar 2028 | Competition season with mid-match LLM + alliance comms | Most advanced software in FRC |

## The 2028 Vision

Your robot walks onto the Einstein field with:
- A proven swerve platform entering its third season (no drivetrain risk)
- Modular mechanisms swapped in 48 hours after kickoff
- A YOLO neural detector that identifies game pieces in any lighting
- An LLM strategist that generates match strategy from scouting data
- A post-match analyzer that recommends PID and strategy adjustments
- Alliance communication that prevents wasted cycles
- Sim-to-real transfer that lets software development outpace hardware
- A decision engine whose weights were self-tuned across 2 seasons of data
- A prediction engine that correctly predicted the optimal 2028 mechanism
  architecture before any other team finished brainstorming

This is 1690-level software sophistication combined with 1323-level cycle speed,
on 4414-level simple/rigid hardware, with 6328-level transparency. That's the
combination that wins championships.
