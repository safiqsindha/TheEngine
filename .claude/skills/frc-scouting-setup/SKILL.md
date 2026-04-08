---
name: frc-scouting-setup
description: Recommend and configure an FRC scouting system based on team resources. Use this skill when someone asks about FRC scouting apps, which scouting system to use, how to set up scouting for FRC, scouting with no WiFi, alliance selection tools, FRC data analysis, Statbotics, The Blue Alliance data, comparing scouting platforms, or building an FRC scouting workflow. Covers 15+ community scouting tools evaluated for different team sizes and resource levels, from Google Sheets (simplest) to AI-powered analysis (most advanced).
---

# FRC Scouting Setup

Recommend the right scouting stack based on your team's resources.

## Input Required

- Team size (how many students available for scouting?)
- Devices available (phones, tablets, laptops?)
- Internet at events (reliable, spotty, or none?)
- Scouting experience (first time, some experience, veteran?)
- Competitive goal (district qualifier, district championship, worlds?)

## Scouting Tool Landscape

Read `references/SCOUTING_TOOLS.md` for the complete tool directory.

### Tier 1: Zero Development (Use Immediately)

| Tool | What It Does | Requirements | Best For |
|------|-------------|-------------|---------|
| **ArcBotics** | Chrome extension overlaying Statbotics EPA on TBA pages | Chrome browser | Pre-event research, anyone |
| **Quick Pick** | Statbotics-based alliance pick list generator | Web browser | Alliance selection, any team |
| **SPAMalytics** | Google Sheets scouting (the "Everybot of scouting") | Google Sheets + printed forms | Teams new to scouting |
| **Statbotics** | EPA ratings, match predictions, team comparison | Web browser or Python API | Data analysis, any team |
| **The Blue Alliance** | Match results, schedules, team info | Web browser or API | Everyone, always |

### Tier 2: Minimal Setup (1-2 Hours)

| Tool | What It Does | Requirements | Best For |
|------|-------------|-------------|---------|
| **Maneuver** | Offline-first scouting suite with match strategy | Web browser, works offline | 6+ scouts, any device |
| **ScoutingPASS** | JSON-configurable QR code scouting | Web browser, QR scanner | Teams wanting customizable forms |
| **Lovat** | Full scouting + shared database platform | Web browser, account | Teams wanting shared data |
| **SPOT** | Modular scouting with no-code configuration | Web browser, server (Render) | Teams wanting analysis built-in |
| **Open Scouting** | Web-based scouting with TBA integration | Web browser, server | Teams wanting API access to data |

### Tier 3: Advanced (Custom Development)

| Tool | What It Does | Requirements | Best For |
|------|-------------|-------------|---------|
| **Blue Banner Engine** | AI-powered scouting analysis | Python, API access | Teams wanting AI insights |
| **The P.A.C.K.** | Robot tracking from match video | Python, GPU recommended | Teams wanting video analysis |
| **Orpheus** | Advanced scouting data analysis | Data export from any scouting tool | Teams wanting deep analytics |
| **FRC Score Optimizer** | Identifies highest-impact scoring improvements | Match data | Post-event analysis |

## Recommendation Logic

### If team has never scouted before:
→ SPAMalytics (Google Sheets) + ArcBotics + Quick Pick
→ Total setup: 30 minutes
→ Covers: basic data collection + EPA overlay + alliance selection

### If team has 6+ scouts with phones, no WiFi:
→ Maneuver (offline-first) + Quick Pick + ArcBotics
→ Total setup: 1 hour
→ Covers: detailed match scouting + alliance selection + EPA data

### If team wants customizable scouting:
→ ScoutingPASS (edit JSON config) + Statbotics Python API
→ Total setup: 2 hours
→ Covers: custom data fields + quantitative analysis

### If team wants maximum competitive intelligence:
→ Maneuver (collection) + Blue Banner Engine (AI analysis) + Quick Pick (alliance) + ArcBotics (EPA overlay)
→ Plus custom: anomaly detection + complementarity scoring + Monte Carlo simulation
→ Total setup: 4 hours + custom development
→ Covers: everything

## The Intelligence Layer (What No Community Tool Provides)

Community tools solve data COLLECTION. No tool solves data INTELLIGENCE:
- Anomaly detection (flagging EPA drops, redesigns, trends)
- Complementarity scoring (which partner covers your weaknesses)
- Monte Carlo match simulation (win probability per alliance)
- Auto-generated pit visit questions from data anomalies
- Real-time opponent data fed to drive coach during match

This is where custom development adds unique competitive value.

## Important Notes

- Start simple. A team using SPAMalytics well beats a team with a broken custom app.
- The most important scouting activity is WATCHING MATCHES, not clicking buttons.
- Qualitative notes ("this team's intake jams every 3rd cycle") are often more valuable than quantitative data.
- Alliance selection is the moment all scouting pays off. Quick Pick is the minimum tool for this.
- Install ArcBotics on every team laptop. It's free and adds EPA to every TBA page.
