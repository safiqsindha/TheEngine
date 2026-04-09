# The Engine

**FRC Team 2950 — The Devastators**

The Engine is an AI-powered competition intelligence system for FRC Team 2950. It covers the full lifecycle — from predicting what robot to build before kickoff, to telling students who to pick in alliance selection, to generating match-by-match game plans during playoffs.

62 Python files across 6 subsystems, plus a full Java robot codebase with 246 tests. **120 of 160 blocks complete.**

Robot code lives in a separate repo: [2950-robot](https://github.com/safiqsindha/2950-robot)

---

## What We Built

### The Robot Code (Java)

The foundation. We took the students' robot code and layered on:

- **AdvantageKit logging** everywhere — every subsystem records state for replay
- **maple-sim simulation** — full physics sim so students can practice without a robot
- **Autonomous intelligence** — custom A* pathfinding on a 164x82 navigation grid, dynamic obstacle avoidance, fuel detection via YOLO on a Limelight 4, and a strategy engine that chains goals (score, pickup, score) with fallback chains if anything fails
- **Competition hardening** — stall detection, odometry divergence detection, subsystem self-tests, a 10-step pit crew diagnostic that actuates every mechanism, and pre-match health checks via NetworkTables
- **Driver experience** — controller rumble patterns, precision/full speed toggle, one-button score command, dashboard path visualization

51 of 55 blocks done. The remaining 4 need a physical robot to tune.

---

### The Antenna (Intelligence Gathering)

A Discord bot that scrapes Chief Delphi automatically, scores every post by relevance to our team, and posts weekly intelligence digests to our Discord server. Students react with emojis to triage.

It runs 24/7 — daily scans, weekly digests, critical alerts DM'd to the lead mentor. 60 tests passing, fully deployed.

```bash
cd antenna
pip install -r requirements.txt
cp .env.example .env     # Fill in bot token + channel ID
python3 bot.py           # Start the Discord bot
```

---

### The Oracle + Blueprint (Game Prediction to CAD)

We analyzed technical binders from elite teams (254, 1678, etc) and historical Statbotics data to build an 18-rule prediction engine. Given a game manual's scoring rules, it predicts the optimal robot architecture — what mechanisms to build, what to prioritize, what to skip.

**98% accuracy** against historical games (tested 2016-2025).

The Oracle's output feeds into Blueprint, which has parametric generators for every common FRC mechanism — elevator, intake, flywheel, arm, conveyor, climber, turret. Each generator takes specs (travel height, game piece size, target RPM) and outputs a complete mechanical specification with motor selection, gear ratios, weight, current draw, and a bill of materials.

The pipeline goes all the way to OnShape — it can create a CAD document with a swerve chassis frame, insert 19+ COTS parts, and position them. The gap is mechanism geometry (currently bounding boxes, not real shapes) and generalization beyond the 2022 game we demoed on.

---

### The Scout (Scouting & Alliance Selection)

The core competition-day tool. Pulls EPA data from Statbotics and match data from The Blue Alliance, then layers analysis on top:

- **Pre-event reports** — team profiles with anomaly detection (EPA drops, high variance, no endgame) and generated pit scouting questions
- **Alliance pick recommendations** — 4-factor scoring: raw EPA (30%), floor reliability (10%), scoring zone complementarity (25%), and Monte Carlo playoff simulation (25%). Complementarity matters because you don't want three fuel-only robots — you want someone who covers your tower gap or endgame weakness
- **Live draft board** — real-time state tracking during alliance selection. Students call out picks, the system records them, updates projections, and gives instant recommendations when it's our turn. Supports undo for misheard picks
- **Captain prediction with decline modeling** — predicts which captains will decline invitations from higher seeds
- **District point projections** — full-bracket Monte Carlo (QF to SF to Finals) projecting how many district ranking points each alliance earns from playoffs
- **EPA trajectories** — tracks teams across multiple events to catch who's improving vs peaking early vs declining
- **Historical backtester** — replayed against every alliance selection in the 2026 FIT district (12 events, 96 picks). Results: 54% exact match, 81% in the top 3, 91% in the top 5

```bash
cd scout
python3 the_scout.py report 2026txbel --team 2950    # Pre-event report
python3 pick_board.py setup 2026txbel --team 2950 --seed 3  # Init draft
python3 pick_board.py rec                              # Get recommendation
python3 trajectory.py team 2950 2026                   # EPA trajectory
python3 backtester.py 2026fit                          # Backtest district
```

---

### The EYE (Vision Match Scouting)

Automated scouting from video. Downloads match videos, extracts frames, and runs them through a vision model (Haiku by default, supports Sonnet/Opus) to extract qualitative data that Statbotics and TBA can't provide:

- Mechanism reliability (jams, breakdowns, recovery time)
- Defense effectiveness (both playing and receiving)
- Scoring droughts (invisible in the final score)
- Field control (game piece distribution)
- Individual team attribution (who actually scored vs who got carried)

Uses EasyOCR on post-match breakdown screens for match boundary detection, and has a stream recorder that can watch a live stream, detect when matches end, and auto-cut individual match clips.

Cost to scout every match at every FIT district event (1,200 matches): **$10.50/season** on the key frame tier with Haiku.

```bash
cd eye
python3 the_eye.py analyze <youtube_url> --focus 2950 --tier key --backend haiku
python3 the_eye.py ocr .cache/WpzeaX1vgeQ/frames/    # Free OCR-only
python3 stream_recorder.py record <stream_url>         # Live recording
python3 eye_bridge.py load                             # Load into pick board
```

---

### Stand Scouting (Human-in-the-Loop)

Students in the stands record observations during matches using quick-tap shorthand in Discord:

```
!scout 2950 auto:scored fast fuel climbed elite
!scout 7521 moderate tower barge played-defense
!scout 3035 slow no-endgame intake-jam note:"dropped 3 corals"
```

22 tags across 7 categories. Designed for phone input in a loud venue. Stored in the same JSON format as EYE reports — both human and vision observations flow through the same scoring pipeline.

When both sources exist for a team, stand scout data is weighted 1.5x per observation (human deliberately tracked one robot) while EYE provides broader coverage (every match on stream).

---

### Match Strategy

Pre-match game plans that synthesize everything — EPA data, EYE observations, stand scout reports, opponent analysis:

- **Auto coordination** — who's the primary auto scorer, do we have an advantage
- **Teleop assignments** — role classification and task allocation
- **Defense decisions** — cost-benefit analysis: if our weakest robot's scoring EPA is less than 40% of their best robot's EPA, defense creates more value
- **Endgame sequencing** — who climbs first based on EPA and observed reliability
- **Risk flags** — mechanism issues from EYE, cold streaks, high variance warnings
- **Win probability** — Monte Carlo simulation with visual progress bar

```bash
cd scout
python3 match_strategy.py next 2026txbel --team 2950
python3 match_strategy.py opponent 2026txbel --teams 4364,9311,10032
python3 match_strategy.py synergy 2026txbel --alliance 2950,7521,3035
```

---

### The Discord Bot (Competition-Day UI)

Everything above is accessible through Discord. 25+ commands:

| Category | Commands |
|----------|----------|
| **Scouting** | `!event`, `!matchnow`, `!scout`, `!scouted`, `!eyescores`, `!loadscout` |
| **Draft** | `!rec`, `!pick`, `!board`, `!lookup` |
| **Strategy** | `!strategy`, `!strategy opponent <teams>`, `!strategy synergy <teams>` |
| **Intelligence** | `!scan`, `!digest`, `!search`, `!alerts`, `!watch` |

**Competition-day flow:**
1. Set the event once: `!event 2026txbel`
2. During quals, students scout from the stands: `!scout 7521 fast fuel climbed solid`
3. EYE processes the stream video in parallel
4. Before alliance selection: `!loadscout` then `!rec` for scouting-enriched picks
5. During the draft: `!pick 1 148` then `!rec` in real-time
6. Before each playoff match: `!strategy` for the game plan

---

### The Engine Advisor

The orchestrator. Uses Anthropic's advisor pattern — Haiku handles routine operations and escalates to Opus for strategic decisions. Keeps costs low while getting expert-level analysis when it matters.

```bash
python3 engine_advisor.py                              # Interactive chat
python3 engine_advisor.py "Who should 2950 pick at 2026txbel?"  # Single query
python3 engine_advisor.py --executor sonnet "Run pre-event report"  # Use Sonnet
```

---

## Architecture

```
TBA + Statbotics ──> Scout (EPA, rankings, records)
                          |
Stand scouts (Discord) --> stand_scout.py --> eye_bridge.py --> pick_board.py
EYE (video streams) -----> the_eye.py ---/        |              |
                                            match_strategy.py   recommend_pick()
                                                    |
                                            engine_advisor.py (Haiku + Opus)
                                                    |
                                            Discord bot (antenna/bot.py)
```

## Repo Structure

```
TheEngine/
  engine_advisor.py          # AI orchestrator (Haiku + Opus)
  antenna/                   # Chief Delphi scraper + Discord bot
  scout/                     # Scouting, draft, strategy, backtester, trajectories
  eye/                       # Vision scouting, stream recorder, bridge
  blueprint/                 # Oracle prediction + mechanism generators + CAD
  tools/                     # Match analysis, configs, pre-match checks
  scripts/                   # Wiki updater
  design-intelligence/       # Cross-season patterns, architecture specs
  training/                  # Student onboarding, 6 training modules
```

## What's Left

| Category | Blocks | When |
|----------|--------|------|
| Robot hardware tuning | 4 | Next robot access |
| Local vision models (Gemma, Qwen-VL on Jetson) | 2 | When hardware available |
| Blueprint mechanism geometry + generalization | 3 | Offseason |
| Design intelligence (remaining team binders) | 7 | Oct-Dec 2026 |
| 2028 features (mid-match strategy, alliance UDP) | 8 | Summer 2027 |
| Modular robot library (physical mechanisms) | 16 | Summer 2027 |

See [PROGRESS.md](PROGRESS.md) for the full block-by-block status.

## Environment

```bash
# Required
export ANTHROPIC_API_KEY=<key>       # For EYE vision + Engine Advisor
# or put in TheEngine/.anthropic_key

# Scout
# Put TBA API key in scout/.tba_key

# Antenna Discord bot
export ANTENNA_BOT_TOKEN=<token>
export ANTENNA_CHANNEL_ID=<id>
```

## Claude Skills

Six FRC-specific skills for Claude Code in `.claude/skills/`:
`frc-game-analyzer`, `frc-kickoff-assistant`, `frc-elevator-designer`, `frc-scouting-setup`, `frc-pre-event-report`, `frc-alliance-advisor`

---

*The Engine | Team 2950 The Devastators | 120/160 blocks complete*
