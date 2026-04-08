# THE ENGINE — Kickoff Day Prompt Template
# Phase 5D: Fill this in during the game reveal, feed to Claude with the pattern database
#
# Instructions:
#   1. Watch the game reveal video
#   2. Fill in every section below from the game manual
#   3. Feed this file + design-intelligence/TEAM_DATABASE.md + 
#      design-intelligence/CROSS_SEASON_PATTERNS.md to Claude
#   4. Claude produces: mechanism recommendations, specs, and build priority
# ═══════════════════════════════════════════════════════════════════════════════

## Game Identity
- Game name: 
- Season year: 
- Presented by: 

## Match Structure
- Autonomous duration (seconds): 
- Teleop duration (seconds): 
- Endgame duration (seconds): 
- Total match time: 
- Does auto performance affect teleop? (describe): 

## Game Pieces
- Name: 
- Shape: 
- Dimensions (inches): 
- Weight (lbs): 
- How many on field at start: 
- How many pre-loadable: 
- Where are they located on field: 
- Can human players introduce them: 

## Scoring Locations
### Primary Scoring Target
- Name: 
- Height from ground (inches): 
- Distance from nearest starting position (feet): 
- Points in auto: 
- Points in teleop: 
- Any multiplier or bonus: 

### Secondary Scoring Target (if applicable)
- Name: 
- Height from ground (inches): 
- Distance: 
- Points in auto: 
- Points in teleop: 

### Endgame Scoring
- Name (climb/park/other): 
- Height levels and points per level: 
- Max robots that can score endgame simultaneously: 
- Points as percentage of typical winning score: 

## Ranking Points
### RP 1
- Name: 
- Threshold/requirement: 
- Estimated difficulty (easy/medium/hard): 

### RP 2
- Name: 
- Threshold/requirement: 
- Estimated difficulty: 

### RP 3 (if applicable)
- Name: 
- Threshold/requirement: 
- Estimated difficulty: 

## Field Layout
- Field dimensions: 
- Key obstacles (name, dimensions, location): 
- Zones or restricted areas: 
- Is field symmetric or asymmetric: 

## Robot Constraints
- Max height (inches): 
- Max frame perimeter (inches): 
- Max weight with bumpers (lbs): 
- Extension limits: 

## Special Mechanics
- Describe anything unique about this game that doesn't fit above:
- (e.g., HUB shift system in REBUILT, defense rules, game piece interactions)

## Initial Observations
- What actions score the most points per second?
- What's the hardest ranking point to achieve?
- Does this game favor offense or defense?
- Is cycling (repeated scoring) or precision (fewer high-value scores) more important?

# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT TO CLAUDE (copy everything below and paste with this filled template):
# ═══════════════════════════════════════════════════════════════════════════════
#
# I've attached the filled-in game template for the [YEAR] FRC game "[NAME]",
# along with our historical team database (TEAM_DATABASE.md) and cross-season
# pattern analysis (CROSS_SEASON_PATTERNS.md).
#
# Based on the game rules and historical patterns from the top 50 robots across
# 10 seasons, produce:
#
# 1. SCORING META ANALYSIS
#    - Points per second for each scoring action
#    - Optimal cycle structure (what order to do things)
#    - Ranking point feasibility (which RPs to target, which to ignore)
#    - Estimated winning score range
#
# 2. MECHANISM RECOMMENDATIONS
#    For each mechanism (intake, scorer, endgame, drivetrain):
#    - Recommended type (with historical justification)
#    - Dimensions and travel requirements
#    - Motor selection and count
#    - Gear ratio range
#    - Required sensors
#    - Control approach (position PID, velocity PID, voltage)
#    - Estimated cycle time contribution
#
# 3. PRIORITY-RANKED BUILD ORDER
#    - What to prototype first (highest scoring impact)
#    - What can be added later
#    - What to skip if time is short
#
# 4. SOFTWARE UPDATES FOR THE ENGINE
#    - What game-specific configs need to change
#    - New state machine states needed
#    - New autonomous strategies
#    - SnapScript detection target changes
