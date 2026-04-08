# The Engine

**FRC Team 2950 — The Devastators**

The Engine is a competitive robotics intelligence platform. It persists across seasons, compounding knowledge and tooling so that every year the team starts stronger than the last.

## The 10 Systems

| # | System | Status | Description |
|---|--------|--------|-------------|
| 1 | **The Blueprint** | Planned | Parametric CAD pipeline — OnShape templates for swerve frames, elevators, intakes, shooters, and more |
| 2 | **The Antenna** | Live | Chief Delphi intelligence watcher — scrapes, scores, and delivers weekly digests via Discord bot |
| 3 | **The Cockpit** | Planned | Driver station standards — controller mapping, dashboard layout, practice analytics |
| 4 | **The Scout** | Planned | Scouting system — pre-event reports, pit scouting, alliance selection advisor, Monte Carlo sim |
| 5 | **The Whisper** | Planned | Coach AI — real-time strategy recommendations via Jetson Orin Nano |
| 6 | **The Eye** | Planned | AI match analysis — YOLO object detection on match footage |
| 7 | **The Pit Crew** | Planned | Pit operations — checklists, diagnostics, wear tracking, pit display |
| 8 | **The Vault** | Planned | Parts inventory — shop audit, BOM cross-referencing, auto-order lists |
| 9 | **The Grid** | Planned | Electrical standards — wiring cards, CAN maps, pre-built harnesses |
| 10 | **The Clock** | Planned | Build season management — task generator, standup bot, parts tracker |

## Repo Structure

```
TheEngine/
├── .claude/skills/          ← 6 FRC Claude Skills
├── design-intelligence/     ← Cross-season patterns, benchmarks, architecture specs
├── antenna/                 ← CD scraper + Discord bot (live)
├── scout/                   ← Scouting system (future)
├── whisper/                 ← Coach AI (future)
├── grid/                    ← Electrical standards (future)
├── vault/                   ← Parts inventory (future)
├── clock/                   ← Build management (future)
├── tools/                   ← Statbotics scripts, utilities
└── training/                ← Student onboarding, training modules
```

Robot code lives in a separate repo: [2950-robot](https://github.com/safiqsindha/2950-robot)

## The Antenna (Live)

The Antenna monitors Chief Delphi and delivers scored intelligence to Discord.

```bash
cd antenna
pip install -r requirements.txt
cp .env.example .env     # Fill in bot token + channel ID
python3 bot.py           # Start the Discord bot
```

**Discord commands:** `!scan`, `!digest`, `!search`, `!alerts`, `!top`, `!pulled`, `!watch`, `!watchlist`, `!unwatch`, `!stats`, `!commands`

**Test suite:** `python3 test_antenna.py` (60 tests)

## Claude Skills

Six FRC-specific skills for Claude Code, located in `.claude/skills/`:

| Skill | What it does |
|-------|-------------|
| `frc-game-analyzer` | Analyze any FRC game using cross-season pattern rules |
| `frc-kickoff-assistant` | Run the full kickoff workflow with prediction engine |
| `frc-elevator-designer` | Design parametric elevators with motor/ratio calculations |
| `frc-scouting-setup` | Set up scouting infrastructure for an event |
| `frc-pre-event-report` | Generate pre-event intelligence from TBA/Statbotics |
| `frc-alliance-advisor` | Alliance selection recommendations with complementarity scoring |

### Installing Skills

To use these skills in Claude Code, the repo must be your working directory (or a parent). Claude Code automatically discovers skills in `.claude/skills/`.

```bash
cd TheEngine
claude   # Skills are available automatically
```

## Roadmap

See [ENGINE_MASTER_ROADMAP.md](design-intelligence/ENGINE_MASTER_ROADMAP.md) for the full prioritized execution plan through December 2026.

---

*The Engine | Team 2950 The Devastators*
