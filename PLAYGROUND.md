# The Engine — Playground

Welcome to The Engine. This is the codebase that runs Team 2950's competition intelligence. It is one repo with **fifteen subsystems** at three different stages of completion:

### Built — runnable code (the missions cover all of these)
| Subsystem | What it does | Lives in |
|---|---|---|
| **Scout** | Pre-event reports, alliance pick board, match strategy briefs, stand scouting | `scout/` |
| **EYE** | Vision scouting from YouTube — pulls frames, sends to Claude vision, writes a report | `eye/` |
| **Antenna** | Watches Chief Delphi for posts about teams and mechanisms we care about | `antenna/` |
| **Blueprint / Oracle** | Reads game rules, predicts the right robot architecture (R1–R19 rules) | `blueprint/` |
| **Constructicon** | The actual robot Java code (swerve, vision, autonomous, state machine) | `src/`, `swervelib/` |
| **Engine Advisor** | Haiku executor + Opus advisor — the LLM brain on top of all of the above | `engine_advisor.py` |
| **Design Intelligence** | The wiki the Oracle reads from — patterns, training modules, cross-season analysis | `design-intelligence/` |
| **Tools** | Pre-match check, post-match log analysis, navgrid generator | `tools/` |

### Specs and templates — read these, no code to run
| Subsystem | What's there | Lives in |
|---|---|---|
| **Cockpit** | Driver console standards: controller mapping, dashboard layout, hardware spec | `cockpit/` |
| **Pit Crew** | Robot report template used between matches | `pit-crew/` |
| **Training** | 6 training modules + worksheet PDF + deck PPTX + a React training app | `training/` |

### Reserved subsystem slots — planned but not built yet (see `design-intelligence/ENGINE_MASTER_ROADMAP.md`)
| Subsystem | What it will be | Planned for |
|---|---|---|
| **The Whisper** | Coach AI on Jetson — NT bridge + LLM inference for live in-match coaching | Aug–Sept 2026 |
| **The Vault** | Parts inventory — feeds the Blueprint BOM cross-reference | Sept 2026 |
| **The Grid** | Electrical standards — wiring cards, CAN topology, pre-built swerve harnesses | Sept–Oct 2026 |
| **The Clock** | Build management — task generator + standup bot + parts tracker | Oct–Nov 2026 |

The 10 missions below cover the **Built** tier hands-on. The **Specs** tier shows up in Mission 1 and Mission 9 as required reading. The **Reserved** tier is at the bottom under "What's coming next" — that's where you go if you want to help build something that doesn't exist yet.

You have a **$0.50 daily** and **$5.00 lifetime** API budget. Run `python3 engine_budget.py` any time to see how much you have left. Haiku is cheap (~$0.005 per advisor query), one mistake won't sink the whole budget.

> **Default model is Haiku.** Don't switch to Opus unless a mission explicitly says to. One Opus query costs as much as fifteen Haiku queries.

## Before you start

```bash
python3 engine_budget.py     # see your budget
python3 engine_advisor.py    # interactive Engine chat (Haiku)
```

If `engine_budget.py` shows your numbers, you're connected to the proxy and ready. If it errors out, ping your mentor — the proxy is probably down.

The 10 missions below are designed to walk you through the **entire** Engine, one subsystem at a time. Do them in order — each one builds on the last. Total cost across all 10 missions is about **$0.18** if you don't loop anything.

---

## Mission 1 — Orientation (no API cost)

Before you touch anything, read these so you know what you're looking at:

- `MENTOR_BRIEFING.md` — what The Engine is and why it exists
- `WHAT_WE_BUILT.md` — every subsystem listed with file pointers
- `ARCHITECTURE.md` — how the pieces talk to each other
- `design-intelligence/ENGINE_MASTER_ROADMAP.md` — every subsystem (built, in-progress, and planned) on a single timeline. This is the only place that explains where The Whisper, Vault, Grid, and Clock fit.

If you want the textbook version of any of this, the `training/` directory has six training modules covering pattern rules, the prediction engine, design intelligence, pathfinding, vision/YOLO, and simulation. Modules 1–3 pair well with Missions 3, 4, and 8 below.

Then take the Engine Advisor for a free spin. Interactive mode runs Haiku and stays well under a penny per question:

```bash
python3 engine_advisor.py
> what subsystems does the engine have?
> show me how the pick board scores teams
> exit
```

**Deliverable:** Post in `#sandbox`: *"I read the briefing. The Engine has these subsystems: ___"*. List at least six.

**API cost:** ~$0.01 (a couple of free-form Haiku questions)

---

## Mission 2 — The Scout: pull real event data

The Scout talks to The Blue Alliance and Statbotics for free public data. No Anthropic spend — these are open APIs.

```bash
python3 scout/the_scout.py lookup 254              # team profile
python3 scout/the_scout.py lookup 2950
python3 scout/the_scout.py report 2024txhou        # full pre-event report
python3 scout/the_scout.py compare 2024txhou --teams 254,2950,1678
```

Pick any past event from any team you've heard of. Pull team data. Notice what's there (EPA, OPR, ranking, win rate) and what isn't.

**Question:** What was Team 254's auto EPA at their last 2024 event? Post the answer in `#sandbox`.

**API cost:** $0

---

## Mission 3 — The Pick Board: tune the algorithm

The pick algorithm lives in `scout/pick_board.py`. It scores every available team during alliance selection using five factors:

| Factor | Weight (with EYE) | Weight (no EYE) | What it measures |
|---|---|---|---|
| EPA | 30% | 35% | Raw scoring contribution from Statbotics |
| Floor | 10% | 15% | Worst-case (10th percentile) match |
| Complementarity | 25% | 25% | Fills gaps in our alliance |
| Monte Carlo | 25% | 25% | Simulated quarterfinal win rate |
| EYE | 10% | — | Stand-scout + vision observations |

Look at `recommend_pick()` in `scout/pick_board.py` (around line 377) to see the math. Then run the backtester — it replays past events and shows how the algorithm would have picked vs. what actually happened:

```bash
python3 scout/backtester.py --event 2025txdal
python3 scout/backtester.py 2026fit         # whole district
```

**Experiment:** Change EPA from 0.35 to 0.50 (and proportionally lower another factor so weights still sum to 1.0). Re-run the backtester on the same event.

Did your changes make picks better or worse? Post a 2-line summary in `#sandbox` with the before/after accuracy.

**API cost:** $0 — pure stats, no LLM calls.

---

## Mission 4 — Pre-Event Report (Haiku exec summary)

Pre-event reports take a Statbotics dump and produce a tier list, threat assessment, and pick suggestions for an upcoming event. The whole report is rule-based except the very last step, where the Engine Advisor (Haiku) writes a one-paragraph executive summary.

```bash
python3 scout/pre_event_report.py 2026txbel
```

Watch your budget — should cost about $0.005.

Read the output. Find one team it ranks high that surprises you. Look up that team manually on TBA and figure out *why* the report likes them. Post your finding.

**API cost:** ~$0.01

---

## Mission 5 — Stand Scout + Match Strategy

This is the full match-prep workflow: stand scouts type observations from the stands, then match strategy combines those with EPA and EYE data into a pre-match game plan.

### Step 1 — Stand-scout a real match

You're acting as a stand scout. Pick any past 2024 or 2025 match on YouTube.

```bash
# The 22 valid tags are listed at the top of stand_scout.py
python3 scout/stand_scout.py add --event 2024txhou --match qm15 --team 254 \
  --tags "fast,tower,climb,reliable" --note "Strong cycles, no jams"

python3 scout/stand_scout.py add --event 2024txhou --match qm15 --team 2056 \
  --tags "consistent,defense,climb" --note "Played defense most of match"
```

Scout 3 teams from the same match. Then summarize:

```bash
python3 scout/stand_scout.py summary --event 2024txhou
```

At competition, real stand scouts do this from a Discord bot on their phone — same backend.

### Step 2 — Generate the match strategy brief

```bash
python3 scout/match_strategy.py match 2024txhou qm15 --team 254
```

This calls Haiku at the end to write the human-readable brief.

**Experiment:** Open `scout/match_strategy.py`, find `_defense_decision()` around line 478. The function decides whether to play defense based on a points-prevented multiplier (currently `0.4`). Bump it to `0.6` and re-run.

Did the recommendation flip from "score" to "defend"? Why? Post your finding.

**API cost:** ~$0.01

---

## Mission 6 — The EYE: vision scout from a YouTube clip

EYE pulls a video from YouTube, extracts frames, runs them through Claude vision, and writes a structured scouting report. Pick any past FRC match from YouTube.

```bash
python3 eye/the_eye.py analyze "https://www.youtube.com/watch?v=..." \
  --tier key --backend haiku --focus 254
```

- `--tier key` only sends 12 frames per match (cheapest)
- `--backend haiku` uses the cheapest vision model
- `--focus 254` tells EYE which team to pay attention to

**Do not** pass `--tier all` or `--backend opus` — both will burn budget fast.

EYE saves a JSON report at `eye/.cache/results/`. Read it. Compare to the actual scores from TBA. Where did EYE get fooled? (Hint: defense, occlusion, robots that look similar.)

**API cost:** ~$0.05

---

## Mission 7 — The Antenna: watch Chief Delphi

The Antenna is a free-running scraper that watches Chief Delphi for posts about teams and mechanisms we care about. It scores each post by relevance and dumps a weekly digest you can ship to Discord.

```bash
python3 antenna/antenna.py scan 5      # scrape the latest 5 pages of CD
python3 antenna/antenna.py top 10      # top 10 scored posts
python3 antenna/antenna.py stats       # database stats
python3 antenna/antenna.py digest      # generate a weekly digest (don't --send it)
```

Open `antenna/scorer.py` and look at how a post is scored. The keywords for tracked teams and mechanisms live in `antenna/config.py` — find `MECHANISM_KEYWORDS` and add one new keyword that matters to your team. Re-run `scan` and see if anything changes.

**Deliverable:** Post the title of the highest-scored post in your scan to `#sandbox`.

**API cost:** $0 — pure scraping, no LLM.

---

## Mission 8 — The Oracle: predict the right robot

This is one of the most important pieces in the whole repo and almost nobody on the team knows what it does. The Oracle is a 19-rule prediction engine: you feed it the rules of an FRC game, it tells you what the optimal robot architecture looks like (drivetrain, mechanisms, power budget, scoring strategy). It's pure rules — **no LLM at all** — and it's been validated against 4 historical seasons at ~98% accuracy.

```bash
python3 blueprint/oracle.py predict --example-2024     # Crescendo
python3 blueprint/oracle.py predict --example-2025     # Reefscape
python3 blueprint/oracle.py validate                   # run all historical games
```

Read the prediction output carefully. The "rules" the Oracle uses are derived from `design-intelligence/CROSS_SEASON_PATTERNS.md`. Open that file — this is the **brain** of the entire prediction engine and is where every R1–R19 rule comes from.

**Deliverable:** Find which Oracle rule fired most often in the 2025 prediction and post it to `#sandbox`.

**API cost:** $0

---

## Mission 9 — Constructicon: inside the robot code

The Engine isn't just Python tooling — it also includes the **actual robot Java code** that runs on the roboRIO. Built on YAGSL swerve, AdvantageKit logging, MegaTag2 vision, and a full A* pathfinding stack. Take a guided tour:

| Read this file | What it shows |
|---|---|
| `src/main/java/frc/robot/RobotContainer.java` | All button bindings + the auto chooser (7 routines) |
| `src/main/java/frc/robot/subsystems/SwerveSubsystem.java` | YAGSL wrapper + vision fusion |
| `src/main/java/frc/robot/subsystems/SuperstructureStateMachine.java` | IDLE → INTAKING → STAGING → SCORING → CLIMBING |
| `src/main/java/frc/robot/commands/FullAutonomousCommand.java` | The autonomous decision loop (evaluate → pathfind → execute → repeat) |
| `src/main/java/frc/robot/autos/AutonomousStrategy.java` | Utility-based target ranking (SCORE / COLLECT / CLIMB) |
| `src/main/java/frc/lib/pathfinding/AStarPathfinder.java` | 8-directional A* search on a 164×82 nav grid |

You can't run the simulator from a Codespace (it needs WPILib desktop), but you can read every test file in `src/test/java/frc/` to see exactly what each piece is supposed to do — there are 181 unit tests and they're all HAL-free (pure Java, no robot hardware needed).

While you're in this mission, also read the two operations docs that pair with the robot code:

- `cockpit/D1_CONTROLLER_MAPPING.md` — exactly which button does what on the driver and operator controllers
- `cockpit/D2_DASHBOARD_LAYOUT.md` — what every widget on the driver-station dashboard means
- `cockpit/D3_CONSOLE_HARDWARE_STANDARD.md` — the physical driver console build spec
- `pit-crew/ROBOT_REPORT_TEMPLATE.md` — the template the pit crew fills out between matches

These don't have code yet — they're the contracts the Cockpit and Pit Crew subsystems will eventually be built against.

**Deliverable:** In 2 sentences, explain the decision loop in `FullAutonomousCommand.execute()` to your `#sandbox`. What does the robot do every 0.5 seconds?

**API cost:** $0

---

## Mission 10 — The Engine Advisor + ship a contribution

Two parts. The first part costs money. The second part is free but takes longer.

### Part A — Watch the Advisor escalate (the only Opus mission)

The Engine Advisor uses a Haiku **executor** for routine work and escalates to an Opus **advisor** for strategic decisions. You've been using it in Haiku-only mode the whole time. This time we let it call Opus.

```bash
python3 engine_advisor.py "Who should team 2950 pick at 2026txbel and why?"
```

Watch the output. You'll see the executor work for a while, then escalate to the advisor. Note how the advisor's reasoning is qualitatively different from anything Haiku produced in Missions 1, 4, or 5.

**Cost warning:** This call may use $0.05–$0.10 on its own. Run it **once**. Don't loop it.

### Part B — Build something that doesn't exist yet

Now ship something. Pick something tiny that the Engine doesn't do today. Some ideas, ranked by difficulty:

1. A `python3 scout/the_scout.py compare 254 2950 --year 2024` shortcut that prints both teams' EPA side-by-side without needing an event key
2. A new tag in `stand_scout.py` for "good driver awareness"
3. A new column in the pick board that shows each team's win rate at their last event
4. A new mechanism keyword in `antenna/config.py` and a check that it actually matches recent posts
5. A new Oracle rule in `blueprint/oracle.py` derived from a pattern you found in `CROSS_SEASON_PATTERNS.md`
6. A `python3 scout/match_strategy.py worst_case 2024txhou qm15 --team 2950` that simulates the worst plausible outcome
7. A scheduled cron that runs the Antenna every Sunday and posts the digest to Discord

Open a PR. Explain your change in the description. **This is how you graduate from Playground to actually contributing.**

**API cost:** ~$0.05–$0.10 for Part A. Part B depends on what you build.

---

## What's coming next — the four reserved subsystems

Everything in the 10 missions above is **runnable today**. But the directory tree has four more slots that are empty on purpose. They're real planned subsystems with hours, costs, and target months in `design-intelligence/ENGINE_MASTER_ROADMAP.md`. If you want to do something nobody else on the team has done before, this is where you go.

### The Whisper — Coach AI on a Jetson (Aug–Sept 2026, ~38h, ~$390 hardware)
Lives in `whisper/`. Plan: order a Jetson Orin Nano, build a NetworkTables bridge, run a small LLM on-device that watches live match state and feeds the human drive coach prompts like "switch to defense, opponent 1 has a stuck conveyor." Spec lives at `design-intelligence/ARCH_COACH_AI.md`.

### The Vault — Parts inventory (Sept 2026, ~12h)
Lives in `vault/`. Plan: full shop audit, parts spreadsheet, and an API the Blueprint can call to cross-reference every part in a generated BOM against what's actually on the shelf. Spec at `design-intelligence/ARCH_PARTS_INVENTORY.md`.

### The Grid — Electrical standards (Sept–Oct 2026, ~18h)
Lives in `grid/`. Plan: wiring standards card, CAN topology map, pre-built swerve harnesses that swap in during competition, brownout-recovery kit, inspection checklist. Spec at `design-intelligence/ARCH_ELECTRICAL_SYSTEMS.md`.

### The Clock — Build management (Oct–Nov 2026, ~30h, depends on Vault + Blueprint)
Lives in `clock/`. Plan: task generator that consumes Blueprint output, a standup bot that pings Discord for daily progress, a parts tracker that checks Vault inventory, and BOM import. Spec at `design-intelligence/ARCH_BUILD_MANAGEMENT.md`.

If one of those sounds interesting, ping your mentor and ask which one is unblocked. They depend on each other in a specific order — that's the whole point of the master roadmap.

---

## Rules of the playground

1. **Don't push to `main`.** Always work in a branch and open a PR.
2. **Don't share your `ANTHROPIC_API_KEY`.** It contains your username; if a friend uses it, your budget gets charged.
3. **Default to Haiku.** Use Opus only when a mission explicitly tells you to (Mission 10 Part A).
4. **If you break something, ask.** Don't `git push --force`. Don't `rm -rf` anything you didn't make. Ask in `#sandbox` first.
5. **Check your budget.** Run `python3 engine_budget.py` before starting a session. If you see the lifetime bar getting close to full, slow down.

When you finish all 10 missions, you've earned a Codespace permanently and you understand every major subsystem in The Engine. Welcome to the team.

---

## Cheat sheet

```bash
# Budget + advisor
python3 engine_budget.py
python3 engine_advisor.py                  # interactive (Haiku)
python3 engine_advisor.py "your question"  # one-shot (may escalate to Opus)

# Scout (free, no LLM)
python3 scout/the_scout.py lookup 254
python3 scout/the_scout.py report 2024txhou
python3 scout/the_scout.py compare 2024txhou --teams 254,2950,1678
python3 scout/backtester.py --event 2025txdal
python3 scout/pick_board.py                # interactive draft

# Stand scout (free)
python3 scout/stand_scout.py add --event ... --match ... --team ... --tags "..."
python3 scout/stand_scout.py summary --event ...

# Pre-event report (~$0.01, Haiku exec summary)
python3 scout/pre_event_report.py 2026txbel

# Match strategy (~$0.01, Haiku brief)
python3 scout/match_strategy.py match 2024txhou qm15 --team 254

# EYE vision (~$0.05 with --tier key --backend haiku)
python3 eye/the_eye.py analyze "<youtube_url>" --tier key --backend haiku --focus 254

# Antenna (free, no LLM)
python3 antenna/antenna.py scan 5
python3 antenna/antenna.py top 10
python3 antenna/antenna.py digest

# Oracle (free, pure rules)
python3 blueprint/oracle.py predict --example-2025
python3 blueprint/oracle.py validate
```
