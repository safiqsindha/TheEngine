---
name: frc-game-analyzer
description: Analyze any FRC (FIRST Robotics Competition) game manual and predict the optimal robot mechanisms, architecture, and strategy. Use this skill whenever someone asks about FRC game analysis, robot design predictions, mechanism selection, FRC kickoff strategy, what robot to build for an FRC game, FRC game manual analysis, or predicting what champions will build. Also trigger when someone pastes an FRC game manual or describes an FRC game and asks for design recommendations. This skill applies 18 validated prediction rules (98% accuracy across 14 FRC games from 2012-2026) to generate specific mechanism recommendations with confidence scores.
---

# FRC Game Analyzer

Analyze an FRC game and predict the optimal robot architecture using 18 validated prediction rules.

## Input Required

The user provides ONE of:
- An FRC game manual (PDF or text)
- A description of an FRC game (scoring methods, game pieces, field layout, endgame)
- A year (e.g., "2025") — look up the game details

## Process

1. Read the full rules from `references/CROSS_SEASON_PATTERNS.md`
2. Extract these key properties from the game description:
   - Scoring method (throw/shoot OR place/stack)
   - Game piece type(s), shape, size, material
   - Scoring target locations (fixed vs distributed, height)
   - Endgame challenge and point value
   - Autonomous scoring opportunities
   - Defense rules
   - Number of game piece types
3. Apply each of the 18 rules to the game properties
4. Generate output in the format below

## Output Format

For each applicable rule, provide:
- Rule name and number
- Prediction (what to build)
- Confidence percentage
- Brief reasoning (1-2 sentences)

Then provide a summary:
- Recommended robot architecture (1 paragraph)
- Priority build order (R13 timing)
- Weight budget estimate (R12)
- Competitive tier targets (reference `references/COMPETITIVE_BENCHMARKS.md`)
- Key risks and what could go wrong

## Critical Rules

The 18 rules are in `references/CROSS_SEASON_PATTERNS.md`. Always read this file before generating predictions. Never guess at rule content from memory.

Key rules that drive the architecture:
- R4 (Scoring Method) determines 80% of the robot — throw→flywheel, place→elevator
- R5 (Elevator Stages) determines vertical reach requirements
- R6 (Turret Decision) uses a 4-quadrant matrix — always apply it correctly
- R10 (Game Piece Detection) uses a conditional decision tree — don't default to "use YOLO"
- R11 (Cycle Speed) is king — every recommendation should optimize for speed
- R16 (Dual Game Piece) — if two pieces, ONE mechanism, optimize for higher value
- R18 (Obstacle Traversal) is dormant unless the game has terrain

## Validation

This engine has been validated across 14 FRC games (2012-2026):
- 202 rule applications
- 198 correct, 4 partial, 0 incorrect
- 98% accuracy
- 15 of 18 rules score 100%

See `references/PREDICTION_ENGINE_VALIDATION_14GAME.md` for full validation data.

## Important Notes

- Always state confidence levels honestly — some predictions are 95%, some are 65%
- If the game has a novel element not covered by any rule, say so explicitly
- The rules are calibrated for modern FRC (2022+). Pre-2022 games may have lower accuracy on R1 (drivetrain)
- Never recommend a telescoping arm for scoring. Always recommend an elevator for vertical reach.
- The meta-rules (M1-M12) in the patterns file provide additional design philosophy guidance
