# The Engine — Playground

Welcome. You don't need to know how to code to do these missions. You just need to follow the steps. Each mission walks you through one piece of The Engine — the system Team 2950 uses to scout, predict, and run robots.

There are **10 missions** in this guide. Each one takes about 30 minutes. Doing all 10 costs about **18 cents** of API budget — well under the $0.50/day and $5.00/lifetime caps your account has.

When you finish each mission you post a short reply in the matching GitHub Discussion thread. That's how a mentor knows you finished. Links are at the bottom of every mission.

---

## What is The Engine?

The Engine is one big GitHub repo with **fifteen subsystems** at three different stages:

### Built — these have working code (the missions cover all of these)
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

### Reserved subsystem slots — planned but not built yet
| Subsystem | What it will be | Planned for |
|---|---|---|
| **The Whisper** | Coach AI on Jetson — NT bridge + LLM inference for live in-match coaching | Aug–Sept 2026 |
| **The Vault** | Parts inventory — feeds the Blueprint BOM cross-reference | Sept 2026 |
| **The Grid** | Electrical standards — wiring cards, CAN topology, pre-built swerve harnesses | Sept–Oct 2026 |
| **The Clock** | Build management — task generator + standup bot + parts tracker | Oct–Nov 2026 |

The 10 missions only cover the **Built** tier. The **Specs** tier comes up in Mission 1 and Mission 9 as required reading. The **Reserved** tier is at the bottom of this guide if you want to help build something brand new.

---

## How this Codespace works (read this once)

You're using a **GitHub Codespace** — a full Linux computer running in the cloud, inside your browser. You don't have to install anything. Here's how to find the parts you'll use:

### The terminal (where you type commands)

Look at the **bottom of your screen**. There's a black panel with a `$` prompt waiting for you. That's the **terminal**. Every command in this guide is something you type into the terminal and press **Enter**.

If you don't see the terminal at the bottom:
- Press **Ctrl + `** (the backtick key, top-left of your keyboard, just below the Esc key), OR
- Click the **View** menu at the top of the screen → **Terminal**

### The file explorer (where you see the files)

Look at the **left side of your screen**. There's a list of folders and files — that's the **file explorer**. When this guide says "open `scout/pick_board.py`", you do this:

1. Click the `scout` folder in the left sidebar to expand it
2. Click `pick_board.py` inside the folder
3. The file opens in the middle of your screen — that's the **editor**

### The editor (where you read and change code)

The big area in the middle of your screen is the **editor**. When this guide says "edit a file", you click in the editor and type. To save your changes:
- **Mac**: press **Cmd + S**
- **Windows / Linux / Chromebook**: press **Ctrl + S**

VS Code will show a little white dot next to the file name when you have unsaved changes. The dot disappears once you save.

### Your budget (how much money you have left)

You have **$0.50 per day** and **$5.00 total** to spend on Anthropic API calls. Most missions cost less than a cent. To check your budget any time, type this in the terminal:

```bash
python3 engine_budget.py
```

You'll see two bars — today's spend and lifetime spend.

> **Important: default model is Haiku (cheap).** Don't switch to Opus unless a mission tells you to. One Opus query costs as much as fifteen Haiku queries.

### When something goes wrong

If a command errors out, **copy the whole error message** (click and drag to highlight, then Cmd+C / Ctrl+C) and paste it into the matching mission's discussion thread. Don't try to fix it yourself unless the guide tells you to. A mentor will help.

---

## Mission 1 — Orientation

**What this mission is about:** Before you touch anything, you need to know what The Engine actually is. This mission is mostly reading.

**What you'll do:** Read four files. Then talk to the Engine Advisor for the first time.

### Step 1 — Read the briefing files

In the file explorer on the **left side of your screen**, click each of these files to open them. Read each one (you don't have to memorize anything, just get the gist):

- `MENTOR_BRIEFING.md` — what The Engine is and why it exists
- `WHAT_WE_BUILT.md` — every subsystem listed with file pointers
- `ARCHITECTURE.md` — how the pieces talk to each other
- `design-intelligence/ENGINE_MASTER_ROADMAP.md` — the timeline showing every subsystem (built, in-progress, planned)

These are markdown files. They look like nicely-formatted documents — VS Code shows them in a readable view by default. If yours opens as raw text instead, right-click the tab at the top of the editor and pick "Open Preview".

### Step 2 — Talk to the Engine Advisor

Now go to the **terminal at the bottom of your screen** and type this exact command, then press **Enter**:

```bash
python3 engine_advisor.py
```

After a second or two you'll see a `>` prompt. The Engine Advisor is now waiting for you. Type a question and press Enter. Try:

```
what subsystems does the engine have?
```

Wait for the answer. It'll take a few seconds because it's calling Claude Haiku in the background. Then try one or two more questions:

```
show me how the pick board scores teams
```

```
what does the oracle do?
```

When you're done, type `exit` and press Enter to leave the Advisor.

### Step 3 — Check your budget

Run this in the terminal:

```bash
python3 engine_budget.py
```

You should see your "Today" bar move slightly — maybe a penny or two. That's the cost of the questions you asked.

### What success looks like

- You read all four files.
- You asked the Advisor at least one question and got a real answer.
- Your budget bar moved.

### Deliverable

Reply to **[Mission 1 Discussion](https://github.com/safiqsindha/TheEngine/discussions/1)** with:

> *I read the briefing. The Engine has these subsystems: ___*

List at least six subsystems. Pick any six from the table at the top of this file.

**API cost:** ~$0.01

---

## Mission 2 — The Scout: pull real event data

**What this mission is about:** The Scout is the part of The Engine that pulls free data from The Blue Alliance and Statbotics. No Anthropic API spend at all.

**What you'll do:** Run three commands that pull real team and event data, then answer one question.

### Step 1 — Look up a team

In the **terminal at the bottom of your screen**, type this command and press **Enter** (you can replace `254` with any FRC team number you're curious about):

```bash
python3 scout/the_scout.py lookup 254
```

You'll see a profile of Team 254 — their EPA, OPR, win rate, and recent events.

### Step 2 — Look up your own team

```bash
python3 scout/the_scout.py lookup 2950
```

That's Team 2950 — us. Compare what you see to Team 254.

### Step 3 — Pull a full event report

Pick a past event you want to learn about. The format is `<year><district><event-code>`. Some real ones to try:

- `2024txhou` — Houston Championship 2024
- `2024txdal` — Dallas District 2024
- `2025txbel` — Belton District 2025

Pick one and type:

```bash
python3 scout/the_scout.py report 2024txhou
```

The output is long. Scroll up in the terminal to read the whole thing. You'll see every team that played, ranked by predicted strength, with notes on each one.

### Step 4 — Compare three teams head-to-head

```bash
python3 scout/the_scout.py compare 2024txhou --teams 254,2950,1678
```

This puts three teams side-by-side. Notice what's there (EPA, OPR, ranking, win rate) and what isn't.

### What success looks like

- You ran four commands and got real data back from each one.
- You scrolled through the full event report and saw it has 30+ teams listed.

### Deliverable

Reply to **[Mission 2 Discussion](https://github.com/safiqsindha/TheEngine/discussions/2)** with:

> What was Team 254's auto EPA at their last 2024 event?

(Look in the team lookup output. "Auto EPA" is one of the columns.)

**API cost:** $0

---

## Mission 3 — The Pick Board: tune the algorithm

**What this mission is about:** The pick board is what we use during alliance selection at competition. It scores every available team using five different factors and tells us who to pick. In this mission you change the math and see what happens.

**What you'll do:** Read the algorithm, run a backtest against past events, change one number, run the backtest again, and compare.

### Step 1 — Read the algorithm

In the **left sidebar**, click `scout/` to expand it, then click `pick_board.py`. Scroll down to **line 377** — there's a function called `recommend_pick()`. Read the docstring (the lines in triple quotes at the top of the function). It tells you exactly how a team gets scored:

| Factor | Weight (with EYE data) | Weight (without EYE) | What it measures |
|---|---|---|---|
| EPA | 30% | 35% | Raw scoring contribution from Statbotics |
| Floor | 10% | 15% | Worst-case (10th percentile) match |
| Complementarity | 25% | 25% | Fills gaps in our alliance |
| Monte Carlo | 25% | 25% | Simulated quarterfinal win rate |
| EYE | 10% | — | Stand scout + vision observations |

### Step 2 — Run the backtester

The backtester takes the algorithm and runs it against past events that already happened, then compares the algorithm's picks to who the winning alliance actually picked. In the terminal:

```bash
python3 scout/backtester.py --event 2025txdal
```

It'll print accuracy numbers. **Write the accuracy number down** somewhere — you'll compare it in Step 4.

### Step 3 — Change a weight

Go back to `pick_board.py` in the editor. Find the line in `recommend_pick()` that looks like this (around line 448):

```python
pick_score = (epa_norm * 0.35 + floor_norm * 0.15 +
              comp_norm * 0.25 + mc_norm * 0.25)
```

Change the `0.35` to `0.50` and the `0.15` to `0.00`. The numbers still need to add up to 1.0. Save the file (**Cmd+S** on Mac, **Ctrl+S** on Windows).

### Step 4 — Run the backtester again

Same command:

```bash
python3 scout/backtester.py --event 2025txdal
```

Compare the new accuracy number to the one from Step 2.

### What success looks like

- The backtester printed two different accuracy numbers (one before, one after).
- You can tell whether your change made it better or worse.

### Deliverable

Reply to **[Mission 3 Discussion](https://github.com/safiqsindha/TheEngine/discussions/3)** with:

> A 2-line summary of the before/after pick accuracy. Did your tweak make it better or worse?

**API cost:** $0 (no LLM used)

---

## Mission 4 — Pre-Event Report

**What this mission is about:** Before a competition, we generate a pre-event report that ranks every team that's playing and writes a one-paragraph executive summary. The summary is the only part that uses Claude — everything else is pure stats.

**What you'll do:** Run the report against an upcoming event and read the AI-written summary.

### Step 1 — Generate the report

In the terminal:

```bash
python3 scout/pre_event_report.py 2026txbel
```

(`2026txbel` = Belton District 2026. You can try other event keys too.)

It'll take 10–20 seconds. You'll see it pulling data, computing tiers, then at the end it calls Haiku to write the executive summary.

### Step 2 — Read the output

Scroll up in the terminal and read the whole report. Pay attention to:

- **The tier list** — teams are grouped into tiers based on EPA + consistency
- **The threats** — opponents the algorithm thinks we should worry about
- **The pick suggestions** — who the algorithm thinks we should target during alliance selection
- **The executive summary at the end** — the AI-written paragraph

### Step 3 — Pick a surprising team

Find a team in the top tier that you've never heard of. Then look that team up manually:

```bash
python3 scout/the_scout.py lookup <team-number>
```

…replacing `<team-number>` with the team you picked. Look at their floor score and consistency, not just their EPA. That'll usually tell you why the algorithm likes them.

### Step 4 — Check your budget

```bash
python3 engine_budget.py
```

The Today bar should have moved by about half a cent.

### What success looks like

- You read the full report including the AI-written summary at the end.
- You picked one team that surprised you and figured out *why* the algorithm ranks it high.

### Deliverable

Reply to **[Mission 4 Discussion](https://github.com/safiqsindha/TheEngine/discussions/4)** with:

> A team the report ranks high that surprised you, and your guess at *why* the algorithm likes them.

**API cost:** ~$0.01

---

## Mission 5 — Stand Scout + Match Strategy

**What this mission is about:** Real stand scouts at competition watch matches and type observations into a Discord bot. Then before each match, we generate a strategy brief that combines those observations with EPA data. You're going to do both halves manually.

**What you'll do:** Pretend to scout three teams from a YouTube match, then generate a match strategy brief, then change one number and see what happens.

### Step 1 — Find a match on YouTube

Open a new browser tab. Search YouTube for `2024 Houston Championship match qm15` (or pick any past FRC match). You don't need to watch the whole thing — just enough to make up reasonable observations about three robots.

### Step 2 — Type your observations

Come back to the Codespace terminal. The format is:

```bash
python3 scout/stand_scout.py add --event 2024txhou --match qm15 --team 254 --tags "fast,tower,climb,reliable" --note "Strong cycles, no jams"
```

**You can copy that whole command and just change three things:**
- The team number (`254` → whichever team you picked)
- The tags (pick 3–5 from the list — they're at the top of `scout/stand_scout.py`)
- The note (whatever you observed)

Run that command three times, once per team, all in the same match. Scout three different teams.

### Step 3 — Look at your scouting summary

```bash
python3 scout/stand_scout.py summary --event 2024txhou
```

You should see your three teams listed with their tags.

### Step 4 — Generate the match strategy brief

```bash
python3 scout/match_strategy.py match 2024txhou qm15 --team 254
```

This calls Haiku at the end to write the brief. Read the recommendation — does it say "score" or "play defense"?

### Step 5 — Change the defense decision and re-run

Open `scout/match_strategy.py` in the editor. Press **Cmd+F** (Mac) or **Ctrl+F** (Windows) to open Find. Type `_defense_decision` and press Enter — it'll jump to the function definition (around line 478).

A few lines down, find this line:

```python
defense_value = best_opp_epa * 0.4  # estimated points prevented
```

Change `0.4` to `0.6`. Save the file. Re-run the strategy:

```bash
python3 scout/match_strategy.py match 2024txhou qm15 --team 254
```

Did the recommendation flip from "score" to "defend" or vice versa?

### What success looks like

- You scouted three teams with stand_scout.
- You ran the match strategy brief twice and noticed (or didn't notice) a difference.

### Deliverable

Reply to **[Mission 5 Discussion](https://github.com/safiqsindha/TheEngine/discussions/5)** with:

> Did the recommendation flip from "score" to "defend"? What does that tell you about how the model values defense?

**API cost:** ~$0.01

---

## Mission 6 — The EYE: vision scout from a YouTube clip

**What this mission is about:** EYE is the part of The Engine that watches FRC matches on YouTube and writes a scouting report automatically. It downloads the video, pulls out some frames, sends them to Claude vision, and summarizes what it saw. This is the most expensive mission — about a nickel.

**What you'll do:** Pick a YouTube match, run EYE against it, and look at the report.

### Step 1 — Find a YouTube URL

Open YouTube in a new browser tab. Find any past FRC match (search for `2024 frc qm15` or similar). Copy the URL from the browser bar — it'll look like `https://www.youtube.com/watch?v=ABCDEFG`.

### Step 2 — Run EYE

Back in the Codespace terminal, run this command (paste your URL where it says `<your-url>`):

```bash
python3 eye/the_eye.py analyze "<your-url>" --tier key --backend haiku --focus 254
```

A few notes on what those flags do:
- `--tier key` — only sends 12 frames (cheapest)
- `--backend haiku` — uses the cheapest vision model
- `--focus 254` — tells EYE to pay extra attention to Team 254 (change to whichever team is in your match)

> **Do not** change `--tier key` to `--tier all` or `--backend haiku` to `--backend opus`. Both will burn your budget fast.

EYE will download the video (slow — 30 seconds or so), extract frames, then call Haiku vision on each frame. The whole thing takes 1–2 minutes.

### Step 3 — Find the report

When it's done, look in the **left sidebar** for a folder called `eye/.cache/results/`. Inside you'll find a JSON file named after the video ID. Click it to open it in the editor.

(JSON files are just text with structure. You're looking for the team observations, the match summary, and any errors.)

### Step 4 — Compare to reality

Look up the actual match scores on The Blue Alliance website (search "tba 2024 qm15" or whatever match you used). Compare what really happened to what EYE wrote down.

### Step 5 — Check your budget

```bash
python3 engine_budget.py
```

The Today bar should have moved by about a nickel.

### What success looks like

- EYE ran without errors and produced a JSON report.
- You compared at least one of EYE's observations to what actually happened.

### Deliverable

Reply to **[Mission 6 Discussion](https://github.com/safiqsindha/TheEngine/discussions/6)** with:

> Where did EYE get something wrong? Defense? Occlusion? Two robots that look similar? Paste a snippet from the JSON if you can find one.

**API cost:** ~$0.05

---

## Mission 7 — The Antenna: watch Chief Delphi

**What this mission is about:** Chief Delphi is the FRC community forum where teams post about their robots, mechanisms, and strategies. The Antenna is a scraper that reads CD every day, scores each post by relevance to our team, and pulls out the most important ones. Free — no LLM at all.

**What you'll do:** Run the scraper, look at the top posts, and add a new keyword that matters to your team.

### Step 1 — Scrape Chief Delphi

In the terminal:

```bash
python3 antenna/antenna.py scan 5
```

That'll scrape the latest 5 pages of CD (about 100 posts). It takes 10–20 seconds. Each post gets scored based on whether it mentions teams or mechanisms we track.

### Step 2 — See the top posts

```bash
python3 antenna/antenna.py top 10
```

That shows the 10 highest-scored posts. **Write down the title of #1** — you'll need it for the deliverable.

### Step 3 — Look at the database stats

```bash
python3 antenna/antenna.py stats
```

You'll see how many posts are in the database, how many are tracked, when the last scrape ran, etc.

### Step 4 — Look at how posts get scored

In the **left sidebar**, expand `antenna/`, click `scorer.py`. Read the function `score_topic()`. You don't need to understand every line — just notice that it adds points for tracked teams, tracked mechanisms, and certain keywords.

### Step 5 — Add a new keyword

In the **left sidebar**, click `antenna/config.py`. Find the section called `MECHANISM_KEYWORDS`. It's a Python dictionary listing things like `"elevator"`, `"swerve"`, `"intake"`. Add one new keyword that matters to your team. For example, if your team is building a turret, add `"turret"`. Save the file.

### Step 6 — Re-scan with your new keyword

```bash
python3 antenna/antenna.py scan 5
python3 antenna/antenna.py top 10
```

Does the top-10 list look any different now? It might or might not — depends on whether anyone on CD posted about your keyword recently.

### What success looks like

- You scraped CD and saw real posts in the top-10 list.
- You added a new keyword to `config.py` and saved it.

### Deliverable

Reply to **[Mission 7 Discussion](https://github.com/safiqsindha/TheEngine/discussions/7)** with:

> The title of the highest-scored post in your scan, plus the new keyword you added and *why* it matters to our team.

**API cost:** $0

---

## Mission 8 — The Oracle: predict the right robot

**What this mission is about:** This is one of the most important pieces in the whole repo and almost nobody on the team knows it exists. The Oracle is a 19-rule prediction engine: you feed it the rules of an FRC game, it tells you what the optimal robot architecture looks like (drivetrain, mechanisms, power budget, scoring strategy). It's pure rules — **no LLM at all** — and it's been validated against four historical seasons at ~98% accuracy.

**What you'll do:** Run the Oracle on a past FRC game, then read the document the rules came from.

### Step 1 — Predict 2024 (Crescendo)

In the terminal:

```bash
python3 blueprint/oracle.py predict --example-2024
```

You'll see a long output describing the robot architecture the Oracle would have suggested for the 2024 Crescendo game. Compare it mentally to what real top teams (like 254, 2056, or your own team) actually built that year.

### Step 2 — Predict 2025 (Reefscape)

```bash
python3 blueprint/oracle.py predict --example-2025
```

Same thing for 2025 Reefscape. The output is structured — pay attention to the "rules fired" section. Each rule is named R1 through R19.

### Step 3 — Run the validation

```bash
python3 blueprint/oracle.py validate
```

This runs the Oracle against every historical game in the database and prints accuracy. You should see ~98%.

### Step 4 — Read the brain

The rules the Oracle uses come from one document. In the **left sidebar**, expand `design-intelligence/`, click `CROSS_SEASON_PATTERNS.md`. **This is the source of every R1–R19 rule.** It's the most important markdown file in the entire repo.

Read at least the first 200 lines. You don't have to memorize the rules — just understand that this document is where the Oracle's intelligence comes from.

### Step 5 — Find which rule fired most

Go back to the 2025 prediction output (scroll up in the terminal, or re-run `python3 blueprint/oracle.py predict --example-2025`). Look at the list of rules that fired. Note which rule appears most often.

### What success looks like

- You ran predict for 2024 and 2025 and saw two different robot architectures suggested.
- You read at least the first section of CROSS_SEASON_PATTERNS.md.
- You identified which rule fired most often in the 2025 prediction.

### Deliverable

Reply to **[Mission 8 Discussion](https://github.com/safiqsindha/TheEngine/discussions/8)** with:

> Which Oracle rule (R1–R19) fired most often in the 2025 Reefscape prediction? Quote the rule text from CROSS_SEASON_PATTERNS.md.

**API cost:** $0

---

## Mission 9 — Constructicon: inside the robot code

**What this mission is about:** The Engine isn't just Python tooling — it also includes the **actual robot Java code** that runs on the roboRIO during a match. Built on YAGSL swerve, AdvantageKit logging, MegaTag2 vision, and a full A* pathfinding stack. You're not going to compile or run any of it — Codespaces don't have the WPILib desktop installed — but you're going to read it.

**What you'll do:** Read six specific files. Then read four operations specs. Then explain the autonomous loop in two sentences.

### Step 1 — Read these six files (in this order)

In the **left sidebar**, expand each folder and click each file. You don't have to understand every line — focus on the comments and method names.

| Click this file | What to look for |
|---|---|
| `src/main/java/frc/robot/RobotContainer.java` | All the button bindings + the auto chooser at the bottom (lists 7 autonomous routines) |
| `src/main/java/frc/robot/subsystems/SwerveSubsystem.java` | The `drive()` method and the vision fusion code |
| `src/main/java/frc/robot/subsystems/SuperstructureStateMachine.java` | The 5-state machine: IDLE → INTAKING → STAGING → SCORING → CLIMBING |
| `src/main/java/frc/robot/commands/FullAutonomousCommand.java` | **The most important file.** Read the `execute()` method top to bottom |
| `src/main/java/frc/robot/autos/AutonomousStrategy.java` | How the robot scores potential targets (SCORE / COLLECT / CLIMB) |
| `src/main/java/frc/lib/pathfinding/AStarPathfinder.java` | A* search on a 164×82 grid |

### Step 2 — Read the operations specs

These are the contracts the Cockpit and Pit Crew subsystems will eventually be built against. Click each one in the left sidebar:

- `cockpit/D1_CONTROLLER_MAPPING.md` — exactly which button does what on the driver and operator controllers
- `cockpit/D2_DASHBOARD_LAYOUT.md` — what every widget on the driver-station dashboard means
- `cockpit/D3_CONSOLE_HARDWARE_STANDARD.md` — the physical driver console build spec
- `pit-crew/ROBOT_REPORT_TEMPLATE.md` — the template the pit crew fills out between matches

### Step 3 — Bonus: read the unit tests

The unit tests live in `src/test/java/frc/`. There are 181 of them. They're all pure Java (no robot hardware needed). Click into a few — they're the cleanest possible explanation of what each piece is supposed to do.

### What success looks like

- You opened all six Java files and the four spec docs.
- You can explain in plain English what `FullAutonomousCommand.execute()` does.

### Deliverable

Reply to **[Mission 9 Discussion](https://github.com/safiqsindha/TheEngine/discussions/9)** with:

> In 2 sentences, explain what the robot does every 0.5 seconds during full autonomous mode.

(Hint: read the `execute()` method in `FullAutonomousCommand.java`. There's a comment block at the top of the method that basically tells you the answer.)

**API cost:** $0

---

## Mission 10 — The Engine Advisor + ship a contribution

**What this mission is about:** The final mission. Two parts. Part A is the only mission where you use Opus instead of Haiku — you'll see why. Part B is where you actually contribute to The Engine.

**What you'll do:** Run one expensive Advisor query, watch it escalate from Haiku to Opus, then open a real pull request with a small contribution.

### Part A — Watch the Advisor escalate

In the terminal:

```bash
python3 engine_advisor.py "Who should team 2950 pick at 2026txbel and why?"
```

> **Cost warning:** This single query may use **$0.05–$0.10** of your budget — about ten times more than any other mission so far. **Run this exactly once. Do not loop it.**

Watch the output carefully. You'll see:

1. The Haiku **executor** start working — pulling team data, computing pick scores
2. At some point, the executor calls `advisor()` — that's the **escalation**
3. Opus takes over, reads the entire conversation so far, and writes a strategic recommendation that looks qualitatively different from anything Haiku wrote in earlier missions

Read both halves. You're looking at the same architecture pattern Anthropic uses internally — a cheap fast model handling routine work, escalating to a smart slow model for the hard decisions.

### Part B — Ship a contribution

Now you're going to open a real pull request. Pick **one** of these, ranked easiest to hardest:

1. **Easy: Add a new tag to `stand_scout.py`** for "good driver awareness" or any other useful trait. The list of valid tags is at the top of the file.
2. **Easy: Add a new mechanism keyword** to `antenna/config.py` that matters to your team. Make sure it's not already in the list.
3. **Medium: Add a new column** to the pick board output that shows each team's win rate at their last event.
4. **Medium: Write a `compare` shortcut** in `the_scout.py` that doesn't need an event key — just two team numbers and a year.
5. **Hard: Write a new Oracle rule** in `blueprint/oracle.py` based on a pattern you found in `CROSS_SEASON_PATTERNS.md`.
6. **Hard: Write a new auto** for `match_strategy.py` called `worst_case` that simulates the worst plausible outcome of a match.

To open a PR:

1. In the terminal: `git checkout -b <your-name>-<short-description>` (e.g. `alex-add-driver-tag`)
2. Make your edits in the editor. Save with **Cmd+S** / **Ctrl+S**.
3. In the terminal: `git add .` then `git commit -m "Your description"` then `git push -u origin HEAD`
4. The terminal will print a link to open a PR. Click it. Fill in the PR description explaining what you changed and why.

**Don't worry if it's small.** A two-line PR is still a real contribution. The goal is the experience of opening one, not the size of the change.

### What success looks like

- You ran Part A exactly once and saw the Opus advisor reasoning.
- You opened a pull request on the TheEngine repo.

### Deliverable

Reply to **[Mission 10 Discussion](https://github.com/safiqsindha/TheEngine/discussions/10)** with:

> A link to your PR and one sentence about what your change does. Bonus: paste a snippet of the Opus advisor's reasoning that surprised you.

**When your PR is merged, you've graduated from Playground to Engine contributor.**

**API cost:** ~$0.05–$0.10 for Part A. Part B depends on what you build (usually $0).

---

## What's coming next — the four reserved subsystems

Everything in the 10 missions above is **runnable today**. But the directory tree has four more slots that are empty on purpose. They're real planned subsystems with hours, costs, and target months in `design-intelligence/ENGINE_MASTER_ROADMAP.md`. If you finish all 10 missions and want to do something nobody else on the team has done before, this is where you go.

### The Whisper — Coach AI on a Jetson (Aug–Sept 2026, ~38h, ~$390 hardware)
Lives in `whisper/`. Plan: order a Jetson Orin Nano, build a NetworkTables bridge, run a small LLM on-device that watches live match state and feeds the human drive coach prompts like "switch to defense, opponent 1 has a stuck conveyor." Spec lives at `design-intelligence/ARCH_COACH_AI.md`.

### The Vault — Parts inventory (Sept 2026, ~12h)
Lives in `vault/`. Plan: full shop audit, parts spreadsheet, and an API the Blueprint can call to cross-reference every part in a generated BOM against what's actually on the shelf. Spec at `design-intelligence/ARCH_PARTS_INVENTORY.md`.

### The Grid — Electrical standards (Sept–Oct 2026, ~18h)
Lives in `grid/`. Plan: wiring standards card, CAN topology map, pre-built swerve harnesses that swap in during competition, brownout-recovery kit, inspection checklist. Spec at `design-intelligence/ARCH_ELECTRICAL_SYSTEMS.md`.

### The Clock — Build management (Oct–Nov 2026, ~30h, depends on Vault + Blueprint)
Lives in `clock/`. Plan: task generator that consumes Blueprint output, a standup bot that pings Discord for daily progress, a parts tracker that checks Vault inventory, and BOM import. Spec at `design-intelligence/ARCH_BUILD_MANAGEMENT.md`.

If one of those sounds interesting, talk to your mentor and ask which one is unblocked. They depend on each other in a specific order — that's the whole point of the master roadmap.

---

## Rules of the playground

1. **Don't push directly to `main`.** Always work in a branch and open a pull request. Mission 10 walks you through this.
2. **Don't share your `ANTHROPIC_API_KEY`.** It contains your username; if a friend uses it, your budget gets charged.
3. **Default to Haiku.** Use Opus only when a mission explicitly tells you to (Mission 10 Part A).
4. **If you break something, ask.** Don't `git push --force`. Don't delete files you didn't create. Post in the matching mission discussion thread first.
5. **Check your budget.** Run `python3 engine_budget.py` before starting a session. If your lifetime bar is getting close to full, slow down and tell your mentor.

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
python3 antenna/antenna.py stats

# Oracle (free, pure rules)
python3 blueprint/oracle.py predict --example-2025
python3 blueprint/oracle.py validate
```

## Mission discussion threads

Post your deliverable for each mission here:

| Mission | Discussion |
|---|---|
| Mission 1 — Orientation | https://github.com/safiqsindha/TheEngine/discussions/1 |
| Mission 2 — The Scout | https://github.com/safiqsindha/TheEngine/discussions/2 |
| Mission 3 — Pick Board | https://github.com/safiqsindha/TheEngine/discussions/3 |
| Mission 4 — Pre-Event Report | https://github.com/safiqsindha/TheEngine/discussions/4 |
| Mission 5 — Stand Scout + Match Strategy | https://github.com/safiqsindha/TheEngine/discussions/5 |
| Mission 6 — The EYE | https://github.com/safiqsindha/TheEngine/discussions/6 |
| Mission 7 — The Antenna | https://github.com/safiqsindha/TheEngine/discussions/7 |
| Mission 8 — The Oracle | https://github.com/safiqsindha/TheEngine/discussions/8 |
| Mission 9 — Constructicon | https://github.com/safiqsindha/TheEngine/discussions/9 |
| Mission 10 — Engine Advisor + ship a contribution | https://github.com/safiqsindha/TheEngine/discussions/10 |
