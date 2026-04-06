# THE ENGINE — Scouting & Match Intelligence System
# Codename: "The Scout"
# Target: Ready before first 2027 competition event
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## The Problem

Traditional FRC scouting: 8 students walk to 60 pits with tablets.
They ask "what's your drivetrain?" to teams that answer however they
want. Data is inconsistent, subjective, full of gaps. Students who
know robotics ask good questions. Rookies check boxes. Half the data
is available publicly on TBA and Statbotics — the team just doesn't
know how to pull it.

At alliance selection, the drive coach picks based on "they looked
fast" and "I think they can climb." Meanwhile, the data that would
actually inform a winning pick — EPA breakdowns, scoring consistency,
auto reliability, defensive vulnerability — sits on public APIs
that nobody queried.

The Scout fixes this with three layers: automated pre-event intel
that replaces 80% of pit scouting, targeted pit visits for the 20%
that data can't capture, and structured stand scouting that records
qualitative observations the scoreboard doesn't show.

---

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1: AUTOMATED PRE-EVENT INTEL                  │
│  (runs night before event — no humans needed)        │
│                                                      │
│  TBA API ──→ Match history, scores, schedule         │
│  Statbotics API ──→ EPA breakdown (auto/teleop/end)  │
│  The Eye (if built) ──→ Heat maps, cycle times       │
│                                                      │
│  Output: One-page profile per team (PDF)             │
│  Printed: 30+ copies for drive coach and scouts      │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  LAYER 2: TARGETED PIT VISITS                        │
│  (10-15 teams, not 60 — experienced scouts only)     │
│                                                      │
│  Pre-event report flags teams to visit:              │
│  - Potential alliance picks (top 15 EPA at event)    │
│  - Teams with anomalies (EPA dropped, redesigns)     │
│  - Key opponents (high-seeded, likely to face)       │
│                                                      │
│  Each visit has SPECIFIC questions generated from     │
│  the pre-event data — not generic checklists          │
│                                                      │
│  Output: Updated team profiles with human intel      │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  LAYER 3: QUALITATIVE STAND SCOUTING                 │
│  (during qualification matches — structured obs)     │
│                                                      │
│  Scouts DO NOT count scoring events (TBA has this)   │
│  Scouts record ONLY what data cannot capture:        │
│  - Driver skill under pressure                       │
│  - Defense response (evade / slow / stuck)           │
│  - Mechanism reliability (jams, failures, recovery)  │
│  - Communication with alliance partners              │
│  - Field position tendencies (left vs right bias)    │
│                                                      │
│  Output: Qualitative tags per team per match         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  ALLIANCE SELECTION ADVISOR                          │
│  (runs before alliance selection ceremony)           │
│                                                      │
│  Combines: EPA data + pit intel + stand observations │
│  Produces: Ranked pick list with complementarity     │
│  analysis — "pick Team X, their scoring zones        │
│  complement ours and their climb is reliable"        │
│                                                      │
│  Optional: Monte Carlo match simulation              │
│  "With Team X, we win 78% of simulated playoffs"    │
└─────────────────────────────────────────────────────┘
```

---

## Layer 1: Pre-Event Report Generator

### Data Sources

| Source | API | Data Retrieved | Rate Limit |
|--------|-----|---------------|------------|
| The Blue Alliance | api.thebluealliance.com/v3 | Team list, match results, scores, rankings, OPRs | 100 req/min |
| Statbotics | api.statbotics.io/v3 | EPA (total, auto, teleop, endgame), win rate, consistency | Reasonable use |
| FRC Events | frc-events.firstinspires.org | Official results, playoff brackets | With API key |

### Team Profile (one page per team)

```
═══════════════════════════════════════════════════════
TEAM 4567 — The Thunderbolts
District: Ontario | Events: 2 (Windsor, Waterloo)
═══════════════════════════════════════════════════════

EPA BREAKDOWN
  Total:  45.2 (rank #23 at this event)
  Auto:   12.8 (27% of total — below average)
  Teleop: 24.1 (53% — average)
  Endgame: 8.3 (18% — above average climb)

MATCH HISTORY (last 2 events)
  Windsor:  7-5-0 (W-L-T), ranked 14th, eliminated QF
  Waterloo: 5-7-0, ranked 22nd, did not advance
  TREND: ↓ declining between events

SCORING CONSISTENCY
  Avg match score: 45.2 ± 18.7 (high variance — inconsistent)
  Best match: 82 pts | Worst match: 12 pts
  Auto scores in 75% of matches (misses 25%)

ENDGAME
  Climb attempts: 18/24 matches (75%)
  Climb success: 14/18 attempts (78%)
  Avg climb time: unknown (need stand scouting)

ANOMALY FLAGS
  ⚠️ EPA dropped 15% between events — possible redesign or issue
  ⚠️ High scoring variance — unreliable for playoffs

SCOUTING PRIORITY: MEDIUM
  Visit pit: YES (ask about EPA drop — redesign? Mechanism issue?)
  Stand scout: YES (watch climb reliability, note driver skill)
═══════════════════════════════════════════════════════
```

### Implementation

```python
# pre_event_report.py (extends tools/pull_statbotics.py)

import tbapy  # The Blue Alliance API client
import requests  # Statbotics API
from reportlab.platypus import SimpleDocTemplate  # PDF generation

def generate_event_report(event_key: str):
    """
    Input: TBA event key (e.g., "2027onto1")
    Output: PDF with one page per team at the event
    """
    # 1. Get team list from TBA
    teams = tba.event_teams(event_key)

    # 2. For each team, pull EPA from Statbotics
    for team in teams:
        epa = get_statbotics_epa(team.team_number)
        matches = tba.team_matches(team.team_number, year=2027)
        history = analyze_match_history(matches)

        # 3. Detect anomalies
        anomalies = detect_anomalies(epa, history)
        # EPA drops, high variance, missing endgame, etc.

        # 4. Assign scouting priority
        priority = assign_priority(epa, anomalies, event_ranking)
        # HIGH = potential pick, MEDIUM = watch, LOW = skip

        # 5. Generate specific pit visit questions
        questions = generate_pit_questions(anomalies, history)

        # 6. Build PDF page
        add_team_page(doc, team, epa, history, anomalies, questions)

    doc.build()
    # Output: event_report_2027onto1.pdf
```

### When to Run
- Night before the event (after TBA publishes team list)
- Update after Day 1 qualification matches (re-pull EPA with event data)
- Update before alliance selection (final pull with all qual data)

---

## Layer 2: Targeted Pit Visit System

### Who to Visit (auto-generated from Layer 1)

| Priority | Criteria | Typical Count | Who Visits |
|----------|----------|---------------|-----------|
| HIGH | Top 15 EPA at event (potential alliance picks) | 10-12 | Most experienced scouts |
| HIGH | Teams with anomaly flags (EPA drop, redesign) | 3-5 | Technical mentor or senior student |
| MEDIUM | Teams you're likely to face in quals | 5-8 | Experienced scouts |
| LOW | Everyone else | Skip | Data from Layer 1 is sufficient |

### Question Generator

Instead of generic "what's your drivetrain?" questions, the pre-event
report generates SPECIFIC questions based on each team's data:

| Anomaly Detected | Generated Question |
|-----------------|-------------------|
| EPA dropped 15% between events | "Your performance dropped since [event]. Did you change anything? Mechanism issue or strategy change?" |
| Auto scores in only 60% of matches | "Is your auto consistent? What causes it to miss?" |
| Climb success rate below 80% | "Is your climber reliable now? What was causing failures?" |
| First event for this team | "Is this your first event? What's your robot capable of?" |
| High EPA, potential alliance pick | "What's your preferred strategy? Where do you like to score from? What role do you play on an alliance?" |
| Recently rebuilt or redesigned | "What changed from your last event? Are you confident in the new design?" |

### Pit Visit Form (mobile-friendly)

```
Team #: [____]
Visited by: [____]
Date/Time: [auto]

Questions asked:
1. [Generated question]: [Response]
2. [Generated question]: [Response]
3. [Follow-up]: [Response]

Robot observations:
- Build quality: [excellent / good / average / concerning]
- Organization: [neat / average / messy]
- Students engaged: [yes / no]

Free notes:
[___________________________________]
```

---

## Layer 3: Qualitative Stand Scouting

### What Scouts Record (NOT quantitative)

Scouts DO NOT count:
- How many game pieces scored (TBA has this)
- Match score (TBA has this)
- Whether they climbed (TBA has this)

Scouts ONLY record what data cannot capture:

| Observation | Options | Why It Matters |
|-------------|---------|---------------|
| Driver skill | Precise / Adequate / Struggling | Predicts playoff performance under pressure |
| Defense response | Evades well / Slows down / Gets stuck | Tells you if defense works against them |
| Intake reliability | Consistent / Occasional jam / Frequent jam | Predicts match-to-match variance |
| Mechanism failure | None / Minor issue / Major failure | Reliability for playoffs |
| Recovery from failure | Quick (<5s) / Slow (5-15s) / Did not recover | How they handle adversity |
| Communication | Active with alliance / Minimal / None | Alliance coordination quality |
| Field preference | Left side / Right side / Center / No preference | Scoring zone complementarity |
| Defense played | Effective / Present but weak / None | Can they contribute defensively? |
| Speed impression | Fast cycles / Average / Slow | Subjective cycle speed confirmation |

### Implementation: Google Form

Simple Google Form with dropdowns for each observation.
One submission per team per match. Data flows into a Google Sheet.

Before alliance selection, filter the sheet:
- "Show me all teams where Driver skill = Precise AND
  Defense response = Evades well AND Intake reliability = Consistent"
- That's your pick list for playoff-ready partners.

---

## Alliance Selection Advisor

### Inputs
1. EPA data (Layer 1) — quantitative performance
2. Pit intel (Layer 2) — current robot status, strategy preferences
3. Stand scouting (Layer 3) — qualitative observations
4. Our team's profile — where we score, our strengths/weaknesses

### Complementarity Analysis

The advisor doesn't just rank teams by EPA. It finds teams that
COMPLEMENT your robot:

```
OUR TEAM (2950):
  Strengths: Strong auto (5-piece), good cycle time, reliable climb
  Weaknesses: Vulnerable to defense, score mostly from left side
  Need in a partner: Defense resistance OR right-side scoring

CANDIDATE: Team 8901 (EPA: 52.3)
  Strengths: Right-side scorer, fast cycles, good under defense
  Weaknesses: Weak auto (1-piece), inconsistent climb
  Complementarity score: 87/100
  Reasoning: "They cover our right side, we cover their auto deficit.
  Our consistent climb offsets their inconsistent one."

CANDIDATE: Team 2345 (EPA: 58.1 — higher raw EPA)
  Strengths: Left-side scorer, excellent auto
  Weaknesses: Same scoring zones as us, poor under defense
  Complementarity score: 41/100
  Reasoning: "Higher EPA but overlapping scoring zones. We'd compete
  for the same field positions. Poor defense resistance means
  opponents can slow both robots with one defender."
```

Pick Team 8901 (EPA 52) over Team 2345 (EPA 58) because
complementarity matters more than raw performance in playoffs.

### Optional: Monte Carlo Match Simulation

For the final pick list, simulate 1000 playoff matches:
- Our alliance (2950 + pick 1 + pick 2) vs likely opponents
- Model scoring as EPA ± historical variance
- Output: win probability percentage

"Alliance with Team 8901 + Team 3456: win 74% of simulated playoffs"
"Alliance with Team 2345 + Team 3456: win 61% of simulated playoffs"

This takes 30 seconds to run. The math is simple: draw from each
team's scoring distribution, sum alliance scores, compare.

---

## Data Flow — Complete Match Day

```
NIGHT BEFORE EVENT
  └── Run pre_event_report.py
      └── Output: 30-page PDF, one page per team
      └── Print copies for drive coach + scouts

FRIDAY (PIT SETUP + PRACTICE)
  └── Layer 2: Visit 10-15 flagged teams
      └── Update team profiles with pit intel
      └── Flag any teams that rebuilt or have issues

SATURDAY (QUALIFICATION MATCHES)
  └── Layer 3: Stand scouts record qualitative observations
      └── Google Form submissions per team per match
      └── Layer 1 auto-updates: re-pull EPA after each match block
      └── Updated report generated at lunch break

SATURDAY EVENING (ALLIANCE SELECTION PREP)
  └── Run alliance advisor
      └── Input: EPA (updated) + pit intel + stand scouting
      └── Output: ranked pick list with complementarity scores
      └── Optional: Monte Carlo simulation for top 5 candidates
      └── Drive coach reviews and makes final decisions

SUNDAY (PLAYOFFS)
  └── Pre-match strategy per opponent
      └── The Whisper has opponent data loaded
      └── Pit intel + stand scouting inform defense targets
      └── "Team 4567 scores from the left, jams on side pickups,
           climber fails when contested — defend left side,
           contest their climb in endgame"
```

---

## Integration with Other Engine Systems

| System | What It Provides to The Scout | What The Scout Provides |
|--------|------------------------------|----------------------|
| The Eye | Heat maps, cycle times, auto paths from video | Validation of stand scouting observations |
| The Whisper | Displays opponent weaknesses during matches | Opponent data for real-time recommendations |
| The Clock | Standup bot announces scouting assignments | Match schedule for scout rotation |
| Statbotics EPA | Quantitative baseline for every team | Context for EPA anomalies |
| Prediction Engine | What mechanisms should look like (cross-reference pit visits) | Mechanism validation data |
| D.4 Driver Analytics | Our team's performance metrics | Self-awareness for complementarity analysis |

---

## Student Roles at Events

| Role | Count | Responsibility | Skill Level |
|------|-------|---------------|-------------|
| Scout Lead | 1 | Runs pre-event report, manages scout assignments, runs alliance advisor | Senior, data-comfortable |
| Pit Scouts | 2 | Visit flagged teams, ask generated questions, fill pit visit forms | Experienced, good communicators |
| Stand Scouts | 3-4 | Watch assigned matches, fill Google Form per team per match | Any level, trained on what to observe |
| Data Analyst | 1 | Updates reports at lunch, runs Monte Carlo before alliance selection | Software student |

Total: 7-8 students dedicated to scouting (standard for competitive teams).
Rookie scouts start on stand scouting (Layer 3 — structured, hard to mess up).
Experienced scouts graduate to pit visits (Layer 2 — requires judgment).

---

## Development Roadmap

| Block | Task | Hours | Target |
|-------|------|-------|--------|
| S.1 | Pre-event report generator (TBA + Statbotics → PDF) | 16 | January 2027 |
| S.2 | Anomaly detection + pit question generator | 8 | January 2027 |
| S.3 | Stand scouting Google Form + data sheet | 4 | January 2027 |
| S.4 | Alliance selection advisor (complementarity scoring) | 12 | Before first event |
| S.5 | Monte Carlo match simulator (optional) | 8 | Before second event |
| S.6 | Integration with The Whisper (opponent data in match) | 6 | March 2027 |
| **Total** | | **54** | |

---

## What This Replaces vs What's New

| Traditional Scouting | The Scout |
|---------------------|-----------|
| 60 pit visits with generic questions | 10-15 targeted visits with data-driven questions |
| Students counting scoring events on tablets | TBA counts for you — students record qualitative only |
| "They looked fast" at alliance selection | EPA + complementarity + Monte Carlo simulation |
| No pre-event preparation | Full team profiles generated before arriving |
| Drive coach picks on gut feeling | Data-informed ranked pick list with reasoning |
| One scouting approach for every team | Priority-tiered: skip low-priority, deep-dive on picks |

---

*Architecture document — The Scout | THE ENGINE | Team 2950 The Devastators*
