# Manual Parser — JSON Schema

The ensemble manual parser (`blueprint/manual_parser.py`) prompts each LLM
call to emit a single JSON object matching the schema below. Tests and
CI validate structure via `validate_parse_dict`.

## Top-level shape

```json
{
  "scoring": {
    "auto":    [{"name": "string", "points": 0, "location": "string"}],
    "teleop":  [{"name": "string", "points": 0, "location": "string"}],
    "endgame": [{"name": "string", "points": 0, "location": "string"}]
  },
  "game_pieces": [
    {"name": "string", "count_on_field": 0, "notes": "string"}
  ],
  "field_zones": [
    {"name": "string", "alliance_scope": "string", "notes": "string"}
  ],
  "possession_limits": {"max_simultaneous": 0, "notes": "string"},
  "ranking_points": [
    {"name": "string", "criterion": "string"}
  ],
  "penalty_rules": [
    {"id": "string", "severity": "string", "summary": "string"}
  ],
  "critical_constraints": {
    "weight_lbs": 0.0,
    "max_height_in": 0.0,
    "frame_perimeter_in": 0.0,
    "starting_config": "string"
  }
}
```

## Field reference

| Field | Type | Notes |
|---|---|---|
| `scoring.{auto,teleop,endgame}` | list | Action name, point value, field location. |
| `game_pieces` | list | Physical pieces (CORAL, ALGAE, NOTE, etc.). |
| `field_zones` | list | Named zones / scoring areas. |
| `possession_limits` | dict | Max simultaneous game pieces + rule notes. |
| `ranking_points` | list | RP name + qualifying criterion. |
| `penalty_rules` | list | G/H-rule ID, severity (MINOR/MAJOR/TECH), summary. |
| `critical_constraints` | dict | Robot envelope: weight, height, perimeter, start config. |

All numeric fields must be numbers (not strings). Use `null` for unknown
numerics; use `[]` / `{}` for unknown collections. Do not paraphrase
official action or zone names.

## Consensus rules

- **Exact-match** voting after normalization (lowercase/strip for strings,
  recursive sort for lists/dicts).
- **Numeric tolerance**: median is accepted as tentative if the spread
  is within 5% relative; otherwise ambiguous.
- **Scoring arrays**: matched by normalized `name`; consensus is applied
  per-entry on `points` and `location`.
- Paths in the conflict report are dotted (e.g. `scoring.auto.leave.points`).

## Worked example — 2025 Reefscape (abbreviated)

```json
{
  "scoring": {
    "auto": [
      {"name": "Leave", "points": 3, "location": "starting_line"},
      {"name": "Coral L1", "points": 3, "location": "reef_trough"},
      {"name": "Coral L2", "points": 4, "location": "reef"},
      {"name": "Coral L3", "points": 6, "location": "reef"},
      {"name": "Coral L4", "points": 7, "location": "reef"}
    ],
    "teleop": [
      {"name": "Coral L1", "points": 2, "location": "reef_trough"},
      {"name": "Coral L4", "points": 5, "location": "reef"},
      {"name": "Processor", "points": 6, "location": "processor"},
      {"name": "Net", "points": 4, "location": "barge_net"}
    ],
    "endgame": [
      {"name": "Park", "points": 2, "location": "barge_zone"},
      {"name": "Shallow Cage", "points": 6, "location": "barge"},
      {"name": "Deep Cage", "points": 12, "location": "barge"}
    ]
  },
  "game_pieces": [
    {"name": "CORAL", "count_on_field": 22, "notes": "PVC pipe segment"},
    {"name": "ALGAE", "count_on_field": 14, "notes": "Foam ball"}
  ],
  "field_zones": [
    {"name": "REEF", "alliance_scope": "alliance", "notes": "4-level scoring structure"},
    {"name": "PROCESSOR", "alliance_scope": "alliance", "notes": "Algae intake for opponent"},
    {"name": "BARGE", "alliance_scope": "shared", "notes": "Endgame + net scoring"}
  ],
  "possession_limits": {"max_simultaneous": 1, "notes": "One CORAL or one ALGAE at a time"},
  "ranking_points": [
    {"name": "Coopertition", "criterion": "Both alliances score ≥2 ALGAE in opponent PROCESSOR"},
    {"name": "Auto", "criterion": "All robots leave + ≥1 CORAL scored in auto"},
    {"name": "Coral", "criterion": "≥5 CORAL on 3 levels (4 with coop)"},
    {"name": "Barge", "criterion": "≥14 barge points in endgame"}
  ],
  "penalty_rules": [
    {"id": "G418", "severity": "MAJOR", "summary": "No contact inside opponent REEF zone"},
    {"id": "G410", "severity": "MINOR", "summary": "Pinning > 5 seconds"}
  ],
  "critical_constraints": {
    "weight_lbs": 115.0,
    "max_height_in": 78.0,
    "frame_perimeter_in": 120.0,
    "starting_config": "Fit inside 120\" frame perimeter; extensions allowed in teleop"
  }
}
```
