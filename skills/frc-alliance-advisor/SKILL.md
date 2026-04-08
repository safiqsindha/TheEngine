---
name: frc-alliance-advisor
description: FRC alliance selection advisor that uses EPA data, complementarity scoring, and Monte Carlo simulation to recommend optimal alliance picks. Use this skill when someone asks about FRC alliance selection, who to pick, pick list strategy, alliance strategy, complementarity analysis, playoff predictions, how to pick in FRC, or optimizing their alliance for FRC playoffs. Also use when someone provides a list of available teams and asks who to pick. Combines Statbotics EPA analysis with strategic complementarity scoring to go beyond simple EPA ranking.
---

# FRC Alliance Advisor

Generate optimized alliance pick recommendations using data + strategy.

## Input Required

- Event code OR list of available teams with EPA data
- Your team number and EPA (auto/teleop/endgame breakdown)
- Your seed position (or expected seed)
- Competition model: regional (optimize for win) or district (optimize for points)
- Your robot's capabilities (what you're good at, what you're weak at)

## Process

1. Get EPA data for all available teams (from Statbotics or user-provided)
2. Calculate complementarity scores (not just raw EPA)
3. Run simplified Monte Carlo simulation for top alliance options
4. Generate ranked pick list with reasoning

## Complementarity Scoring

Raw EPA ranking is what Quick Pick does. This skill goes further.

### Step 1: Identify Your Gaps

```
If your auto EPA is below event median → you need an auto-strong partner
If your teleop EPA is below event median → you need a teleop-strong partner
If your endgame EPA is below event median → you need an endgame-reliable partner
If you only score one game piece type → you need a partner who handles the other
```

### Step 2: Score Each Potential Partner

```
For each available team:
  auto_complement = partner_auto_EPA × (1 if your auto is weak, 0.5 if average, 0.3 if strong)
  teleop_complement = partner_teleop_EPA × (1 if your teleop is weak, 0.5 if avg, 0.3 if strong)
  endgame_complement = partner_endgame_EPA × reliability_multiplier
  
  reliability_multiplier:
    100% endgame success rate = 1.2
    80-99% = 1.0
    50-79% = 0.7
    <50% = 0.3

  complementarity_score = auto_complement + teleop_complement + endgame_complement
```

### Step 3: Alliance Strength Estimation

```
For each potential alliance (your team + partner + likely 3rd pick):
  alliance_EPA = your_EPA + partner_EPA + estimated_3rd_pick_EPA
  estimated_3rd_pick_EPA = median EPA of teams likely available in round 2
```

### Step 4: Simplified Monte Carlo

```
For each potential alliance:
  Simulate 100 playoff matches against each likely opposing alliance
  Win rate = matches won / total matches simulated
  
  For each simulated match:
    your_score = sum(each_team_EPA × random_normal(mean=1, std=0.15))
    opp_score = sum(each_opp_EPA × random_normal(mean=1, std=0.15))
    # The 0.15 std represents match-to-match variance
```

## Output Format

### The Pick List (Ranked)

For each recommended team (top 10-15):

| Rank | Team | Total EPA | Complementarity | Why Pick Them |
|------|------|----------|----------------|---------------|
| 1 | 254 | 65.2 | 92 | Covers your weak auto, consistent endgame |
| 2 | 1323 | 61.8 | 88 | Fastest teleop cycles at this event |
| ... | | | | |

### Alliance Scenarios

"If you pick Team X, your alliance looks like this..."
- Predicted alliance EPA
- Predicted playoff win rate
- Key risk (what could go wrong)
- Counter-strategy (what opponents will try against you)

### The "Do Not Pick" List

Teams to avoid despite high EPA:
- Teams with >20% endgame failure rate (unreliable in playoffs)
- Teams with declining EPA trend (getting worse, not better)
- Teams that duplicate your strengths instead of covering weaknesses
- Teams with known mechanical reliability issues (from pit scouting)

### Decision Framework for the 45-Second Pick Clock

When you're on the clock during alliance selection:
1. Check if your #1 pick is available → pick them
2. If not, go down the complementarity list, not the raw EPA list
3. If all top picks are gone, pick the most RELIABLE team available
4. In playoffs, reliability beats capability. A 40 EPA team that works every match beats a 50 EPA team that breaks in eliminations.

## Important Notes

- This is a TOOL, not a replacement for human judgment
- Scouting data from the event should override pre-event EPA for teams you've watched
- Talk to teams before picking them. Chemistry and communication matter in playoffs.
- The best pick is sometimes the team that makes YOUR robot better, not the team with the highest EPA
- In districts, consider district point optimization (sometimes a semifinal finish earns more points than a risky finals run)
- Quick Pick (quick-pick-psi.vercel.app) is the free baseline tool. This skill adds complementarity and Monte Carlo on top.
