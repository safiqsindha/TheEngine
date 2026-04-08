---
name: frc-kickoff-assistant
description: Complete FRC kickoff day assistant that takes a game manual and generates a full robot design package within hours. Use this skill when someone mentions FRC kickoff day, kickoff planning, first-day game analysis, "what to do on kickoff," starting the FRC build season, or needs a complete plan for an FRC game including mechanism selection, build timeline, BOM, weight budget, and competitive targets. Combines the prediction engine (98% accuracy) with COTS vendor recommendations, build scheduling, and competitive benchmarking.
---

# FRC Kickoff Day Assistant

Generate a complete kickoff day robot design package from a game manual.

## Input Required

- FRC game manual (PDF or description)
- Team's current resources (optional): swerve type, available motors, CNC access, team size
- Team's competitive goal (optional): district qualifier, district championship, worlds

## Process

1. Read `references/CROSS_SEASON_PATTERNS.md` — apply all 18 prediction rules
2. Read `references/KICKOFF_TEMPLATE.md` — fill it in from the game manual
3. Read `references/COMPETITIVE_BENCHMARKS.md` — set EPA targets for the team's goal
4. Generate the complete package below

## Output: The Kickoff Day Package

### Section 1: Game Analysis (first 30 minutes)
- Game type classification (shooting vs placement vs hybrid)
- Game piece analysis (type, size, material, handling requirements)
- Scoring structure (point values at each location, multipliers)
- Endgame analysis (point value, percentage of winning score, climb type)
- Autonomous opportunity analysis

### Section 2: Mechanism Predictions (next 30 minutes)
- Apply all 18 rules with confidence scores
- Recommended robot architecture (1-paragraph summary)
- Architecture diagram (text-based, showing subsystem layout)
- Key design decisions with reasoning

### Section 3: Build Timeline (R13)
- Day 1-2: Drivetrain (if COTS swerve, this is assembly only)
- Day 1-3: Intake prototyping (cardboard + PVC)
- Day 2-7: Primary scoring mechanism design and build
- Day 7-14: Endgame mechanism
- Day 14-21: Integration and first drive
- Day 21-42: Iteration, driver practice, autonomous development
- Key milestones with dates

### Section 4: Weight Budget (R12)
- Subsystem-by-subsystem weight allocation
- Total target weight (125 lbs)
- CG estimation

### Section 5: COTS Shopping List
Recommend specific parts from:
- Thrifty Bot (budget-friendly, elevator kits, swerve)
- WCP / West Coast Products (GreyT assemblies, Kraken motors)
- REV Robotics (SPARK MAX/Flex, NEO motors, MAXTube)
- AndyMark (SDS swerve, wheels, structural)

Reference `references/VENDOR_REFERENCE.md` for vendor details.

### Section 6: Competitive Targets
Based on the team's goal level, provide:
- Target EPA
- Target cycle time
- Target autonomous pieces
- Target endgame success rate

### Section 7: Risks and Mitigations
- What could go wrong with this architecture
- Fallback plans if primary mechanism doesn't work
- Timeline risks (what gets cut if you fall behind)

## Important Notes

- The first 4 hours of kickoff day determine the entire season
- Prioritize DECISIONS over DETAILS — decide what to build, not how to build it
- Prototyping starts immediately after this package is complete
- Never recommend building from scratch what COTS can provide
- Never recommend a telescoping arm. Always recommend an elevator for vertical reach.
- Reference the WCP Competitive Concept and REV Starter Bot as starting points
