# THE ENGINE — Statbotics EPA Data (2026 REBUILT Season)
# Pulled: April 2, 2026 from statbotics.io
# ═══════════════════════════════════════════════════════════════════

## 2026 REBUILT — EPA Rankings (Tracked Teams)

| Rank | Team | Name | Record | Total EPA | Auto EPA | Teleop EPA | Endgame EPA | Worldwide |
|------|------|------|--------|-----------|----------|------------|-------------|-----------|
| 1 | 254 | Cheesy Poofs | 32-2-0 | 331.7 | 59.7 | 191.9 | 80.1 | #3 |
| 2 | 1323 | MadTown Robotics | 34-0-0 | 313.5 | 53.1 | 192.2 | 68.2 | #4 |
| 3 | 118 | Robonauts | 63-5-0 | 158.3 | 27.9 | 94.5 | 35.9 | #107 |

Note: 1678, 6328, 4414, 2910, 1690, 3847, 2056, 1114, 973, 2826 not yet pulled — 
run python3 script locally for full dataset across all years.

## Analysis

### REBUILT Game Characteristics (from EPA distribution)
- **High-scoring game:** Top teams scoring 300+ total EPA suggests many scoring opportunities
- **Teleop-dominant:** Teleop is ~58% of total score for top teams (191/331 for 254)
- **Endgame matters:** 80 EPA for endgame (254) = ~24% of total, confirms Rule 7 (climb mandatory)
- **Auto is significant:** 60 EPA for auto (254) = ~18% of total, confirms Rule 8 (3+ piece auto)

### Key Comparisons
- **254 vs 1323 teleop:** 191.9 vs 192.2 — virtually identical scoring rates
- **254 vs 1323 endgame:** 80.1 vs 68.2 — 254's climb is worth ~12 more points
- **254 vs 1323 auto:** 59.7 vs 53.1 — 254 scores ~1 more game piece in auto
- **254 vs 118 teleop:** 191.9 vs 94.5 — 2x gap suggests fundamentally different mechanism capability
- **1323 undefeated:** 34-0 despite lower total EPA than 254 — consistency > peak performance

### Pattern Rule Validation
- Rule 1 (Swerve): All top teams use swerve ✅
- Rule 3 (Roller material): Fuel = foam balls → foam/silicone rollers predicted ✅
- Rule 4 (Scoring method): Fuel = throwable → flywheel shooter predicted ✅
- Rule 7 (Climb): Endgame ~24% of score → climb mandatory ✅
- Rule 8 (Auto): ~18% of score → strong auto critical ✅
- Rule 11 (Cycle speed): 1323 and 254 tied in teleop → fastest cyclers dominate ✅
- Rule 12 (Weight): 254 at 115 lbs (under max) → REBUILT may reward agility over mass

### FRC2026sim.com Reference
Community-built match simulator for REBUILT strategy analysis:
- Full match simulation with configurable robot roles (cycler, passer, shooter, stealer)
- Ball and ownership flow visualization
- Customizable: intake rate, shooting rate, accuracy, capacity, climb timing
- Config sharing for strategy comparison
- URL: https://frc2026sim.com
- CD Thread: https://www.chiefdelphi.com/t/introducing-frc2026sim-com/511260

### Future Scouting Bot Architecture
Combine Statbotics EPA + FRC2026sim + TBA live data for:
1. Pre-event: Monte Carlo simulation of all matches → predicted rankings + brackets
2. Live event: Update EPA after each match → re-predict remaining matches
3. Alliance selection: Simulate all possible alliance combos → pick recommendations
4. Match strategy: Simulate offense vs defense variations → optimal strategy per match
