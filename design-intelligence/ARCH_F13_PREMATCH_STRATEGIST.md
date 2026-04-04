# F.13 Architecture: Pre-Match Strategist
# Status: Architecture only — build when Jetson hardware is available

## What It Does

During the ~60 seconds before a match, generates a natural language strategy
briefing and auto-routine recommendation from scouting data + opponent history.

## When to Build

After F.11 (Jetson Orin Nano) and F.12 (LLM evaluation) are complete. The prompt
template below can be tested today using Claude or any LLM via laptop — the Jetson
just makes it run without internet at competition.

---

## Input Schema

The strategist takes a single JSON blob assembled by the driver station app:

```json
{
  "match": {
    "event": "2028cmptx",
    "match_number": 42,
    "match_type": "playoff",
    "time_remaining_before_start_s": 55
  },
  "our_robot": {
    "team": 2950,
    "auto_routines": ["3-piece-left", "3-piece-right", "2-piece-center", "safe-mode"],
    "avg_cycle_time_s": 6.2,
    "avg_auto_score": 12.5,
    "climb_success_rate": 0.92,
    "intake_reliability": 0.97,
    "known_issues": ["elevator slow above 40in"]
  },
  "alliance_partners": [
    {
      "team": 254,
      "avg_cycle_time_s": 4.1,
      "preferred_scoring_side": "left",
      "climb_success_rate": 0.99,
      "plays_defense": false,
      "notes": "Best auto in the event, always scores 3+ in auto"
    },
    {
      "team": 1678,
      "avg_cycle_time_s": 5.0,
      "preferred_scoring_side": "right",
      "climb_success_rate": 0.95,
      "plays_defense": true,
      "notes": "Strong defender, switches to offense last 30s"
    }
  ],
  "opponents": [
    {
      "team": 1323,
      "avg_cycle_time_s": 4.5,
      "preferred_scoring_side": "center",
      "climb_success_rate": 0.88,
      "weakness": "Intake jams on off-angle pickups",
      "threat_level": "high"
    },
    {
      "team": 6328,
      "avg_cycle_time_s": 5.2,
      "preferred_scoring_side": "left",
      "climb_success_rate": 0.90,
      "weakness": "Slow climber, starts at 20s remaining",
      "threat_level": "high"
    },
    {
      "team": 4414,
      "avg_cycle_time_s": 5.8,
      "preferred_scoring_side": "any",
      "climb_success_rate": 0.70,
      "weakness": "Inconsistent auto",
      "threat_level": "medium"
    }
  ]
}
```

## Output Schema

The LLM returns structured JSON (parsed by the DS app) plus a human-readable brief:

```json
{
  "recommended_auto": "3-piece-left",
  "auto_reasoning": "254 runs right-side auto. We take left to avoid contention.",
  "strategy_brief": "Score left side. 1678 defends their 1323 first 90s then scores right. We cycle left uncontested. All 3 climb — don't rush, we have time.",
  "target_priority": ["left_high", "left_mid", "center_high"],
  "defensive_note": "If defended, switch to center — 4414 is weakest center scorer.",
  "climb_timing": "Start climb at 18s — our 1.8s avg gives margin.",
  "confidence": 0.85
}
```

## Prompt Template

```
You are a FIRST Robotics Competition match strategist for Team {our_team}.

Given the scouting data below, produce a match strategy in JSON format.

Rules:
- Recommend an auto routine that avoids contention with alliance partners
- Identify which scoring locations our robot should target
- Identify which opponent is the biggest threat and how to counter them
- Determine climb timing based on our success rate and average climb time
- Keep the strategy_brief under 50 words — drivers read it in 10 seconds

Scouting data:
{input_json}

Respond with ONLY valid JSON matching the output schema.
```

## Display

The driver station dashboard shows:
- **Auto**: `3-piece-left` (large, green text)
- **Brief**: 1-2 sentence strategy (medium text)
- **Climb at**: `18s` (yellow, bottom corner)

Driver confirms or overrides via a single SmartDashboard dropdown.

## Implementation Phases

| Phase | What | Depends On |
|-------|------|-----------|
| 1. Prompt template | This document — done | Nothing |
| 2. Laptop prototype | Run the prompt via Claude API on a pit laptop | API key |
| 3. Jetson deployment | Run on-device with quantized Gemma/Phi | F.11, F.12 |
| 4. DS integration | Auto-populate input from scouting DB, display output | F.21 |

## What You Can Test Today

Copy the prompt template and input JSON into Claude (chat). See if the output
is useful. Iterate on the prompt until it reliably produces good strategies.
The prompt is the hard part — the Jetson deployment is mechanical.
