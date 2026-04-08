---
name: frc-pre-event-report
description: Generate a pre-event scouting report for any FRC competition event. Use this skill when someone asks for a pre-event report, event analysis, team profiles for an upcoming FRC event, who to scout at an event, pre-scouting, opponent analysis, or preparing for an FRC competition. Takes an event code and generates team profiles, EPA analysis, anomaly detection, suggested pit visit questions, and alliance selection strategy. Requires access to The Blue Alliance and Statbotics data.
---

# FRC Pre-Event Report Generator

Generate a comprehensive pre-event intelligence report for an FRC competition.

## Input Required

- Event code (e.g., "2025miket" for Michigan Kettering District) OR event name + year
- Your team number (to highlight your matches and potential partners)
- Your team's estimated EPA (optional, for alliance strategy)

## Data Sources

This skill needs data from:
1. **The Blue Alliance API** (thebluealliance.com/api/v3) — team list, schedule, past event results
2. **Statbotics API** (api.statbotics.io) — EPA ratings, auto/teleop/endgame breakdowns
3. If APIs aren't available, the user can paste team lists and manually provide EPA data

## Output: Pre-Event Report

### Section 1: Event Overview
- Event name, location, dates
- Number of teams competing
- Average EPA of the event (is this a strong or weak event?)
- Notable teams attending (EPA > event mean + 1 standard deviation)

### Section 2: Top 10 Teams by EPA
For each:
- Team number and name
- Total EPA with auto/teleop/endgame breakdown
- EPA trend (improving, declining, or stable across recent events)
- Strengths and weaknesses based on component EPA
- Known robot capabilities (if available from public sources)

### Section 3: Anomaly Detection
Flag teams where:
- EPA dropped >15% from their previous event (possible redesign, breakdown, or driver change)
- EPA improved >15% from their previous event (possible upgrade worth investigating)
- Auto EPA is disproportionately high or low compared to teleop (unusual strategy)
- Endgame EPA is zero or near-zero (can't climb? chose not to? broken climber?)

For each flagged team, generate a specific pit visit question:
- "Team 1234: EPA dropped 20% since your last event. What changed on your robot?"
- "Team 5678: Your auto EPA is top 5 but teleop is bottom half. Are you prioritizing auto over teleop?"

### Section 4: Your Match Preview (if schedule is available)
For each qualification match your team is in:
- Alliance partners and their EPA
- Opponent alliance and their EPA
- Predicted score and win probability
- Key matchup notes (who's the threat, who needs support)

### Section 5: Alliance Selection Strategy
Based on your team's EPA and the field:
- Likely seed position after quals
- If you're a captain: recommended pick list (top 8 partners by complementarity)
- If you're picked: which captains would benefit most from picking you
- Complementarity notes: which teams cover different scoring areas than you

### Section 6: Key Pit Visit Targets
Prioritized list of teams to visit in the pits, with specific questions for each based on their data profile.

## Complementarity Scoring

When ranking potential alliance partners, don't just sort by total EPA. Score complementarity:

```
complementarity = partner_auto_EPA × (1 - correlation_with_your_auto) +
                  partner_teleop_EPA × (1 - correlation_with_your_teleop) +
                  partner_endgame_EPA × endgame_reliability_bonus

Higher complementarity = partner is strong where you're weak
```

A partner with 40 EPA who covers your weak areas is better than a partner with 45 EPA who duplicates your strengths.

## Important Notes

- EPA is a starting point, not gospel. Scouting data from matches supplements EPA.
- Pre-event reports are most useful for the first day. By day 2, live scouting data is more current.
- Print a 1-page summary per team for the drive coach to reference between matches.
- Share the report with alliance partners during playoffs.
