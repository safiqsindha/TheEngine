# FalconAlliance Migration Evaluation
Team 2950 — The Engine
Date: 2026-04-14

## Summary

**Verdict: SKIP** — The existing `scout/tba_client.py` is superior for this codebase's needs.
No code changes. Rationale below.

---

## Step 1: Audit

### Call sites (11 total)

| File | Line | Functions imported |
|------|------|-------------------|
| `scout/backtester.py` | 28 | `event_alliances`, `event_rankings`, `district_events` |
| `scout/match_strategy.py` | 49 | `event_matches`, `event_rankings`, `team_event_matches`, `team_key` |
| `scout/pick_board.py` | 47 | `event_matches`, `event_alliances` |
| `scout/pre_event_report.py` | 29 | `event_teams`, `event_info`, `event_matches`, `event_rankings`, `team_key`, `team_number`, `team_record_at_event` |
| `scout/the_scout.py` | 188 | `clear_cache` |
| `scout/trajectory.py` | 33 | `district_rankings`, `district_events`, `event_team_keys`, `team_events` |
| `workers/backfill.py` | 139 | `district_events` |
| `workers/discovery.py` | 276 | `team_events`, `team_key` |
| `workers/mode_a.py` | 317 | `event_matches` |
| `workers/mode_c_anomaly.py` | 186 | `event_matches` |
| `workers/mode_c_event_end.py` | 163 | `event_matches` |

### Endpoints used (19 distinct)

**Event-level:**
- `/event/{key}` → `event_info`
- `/event/{key}/teams` → `event_teams`
- `/event/{key}/teams/keys` → `event_team_keys`
- `/event/{key}/matches` → `event_matches`
- `/event/{key}/rankings` → `event_rankings`
- `/event/{key}/oprs` → `event_oprs`
- `/event/{key}/alliances` → `event_alliances`
- `/event/{key}/coprs` → `event_coprs`
- `/event/{key}/predictions` → `event_predictions`
- `/event/{key}/playoff_advancement` → `event_playoff_advancement`
- `/event/{key}/insights` → `event_insights`
- `/event/{key}/district_points` → `event_district_points`

**Match-level:**
- `/match/{key}` → `match_detail`

**District-level:**
- `/district/{key}/rankings` → `district_rankings`
- `/district/{key}/events` → `district_events`

**Team-level:**
- `/team/{key}` → `team_info`
- `/team/{key}/events/{year}` → `team_events`
- `/team/{key}/event/{key}/matches` → `team_event_matches`
- `/team/{key}/event/{key}/status` → `team_event_status`

### FalconAlliance coverage check (v1.0.1)

| Endpoint | FA covers? | Notes |
|----------|-----------|-------|
| `event_matches` | Yes (`Event.matches()`) | Returns `Match` objects, not dicts |
| `event_rankings` | Yes (`Event.rankings()`) | Returns `Dict[str, Event.Ranking]`, not TBA dict |
| `event_alliances` | Yes (`Event.alliances()`) | Returns `List[Event.Alliance]` objects |
| `event_teams` | Yes (`Event.teams()`) | Returns `Team` objects |
| `event_info` | Yes (`ApiClient.event()`) | Returns `Event` object |
| `event_oprs` | Yes (`Event.oprs()`) | Returns `Event.OPRs` object |
| `event_team_keys` | Partial (`Event.teams(keys=True)`) | Returns list of str keys |
| `district_events` | Yes (`District.events()`) | Returns `Event` objects |
| `district_rankings` | Yes (`District.rankings()`) | Returns ranked objects |
| `team_events` | Yes (`Team.events()`) | Returns `Event` objects |
| `team_event_matches` | Yes (`Team.event(...).matches()`) | Two-call chain |
| `match_detail` | Yes (`ApiClient.match()`) | Returns `Match` object |
| `event_coprs` | No | Not in FA schema |
| `event_playoff_advancement` | No | Not in FA schema |
| `clear_cache` | No | FA has no local caching |

---

## Step 2: Decision

### Verdict: SKIP

**Reasons:**

1. **Return-type mismatch (critical).** FalconAlliance returns typed schema objects (`Match`, `Event.Ranking`, `Event.Alliance`, etc.). Every single call site in this codebase — workers, scout modules, backtester — operates on plain `dict`s. A migration would require either (a) converting every FA object to a dict at the boundary, or (b) refactoring 11 call sites to use object attribute access. Neither is zero-risk.

2. **No caching.** `tba_client.py` has a 1-hour file-based JSON cache (`scout/.cache/tba/`). This is essential for live-event use where the same endpoint is hit dozens of times across workers, Discord commands, and pick board refreshes. FalconAlliance v1.0.1 has no caching layer — every call is a network round-trip.

3. **Missing endpoints.** `event_coprs` and `event_playoff_advancement` have no FA equivalent. At least two callers use these.

4. **Heavy transitive deps.** FA pulls in `aiohttp`, `matplotlib`, `scipy`, `python-dotenv` — adding ~35 MB to the scout runtime for zero gain. Workers already keep deps lean for container cold-start time.

5. **Existing wrapper is fine.** `scout/tba_client.py` is 244 lines, has zero external deps beyond `requests` (already a dep), covers all endpoints, has caching, reads `TBA_API_KEY` from env/file, and has been battle-tested through a full season. There is no bug to fix and no missing feature that FA provides.

6. **Low call-site count relative to scope.** 11 call sites across 11 files — a full migration would touch most of the scout/workers layer with no user-visible benefit.

### Conditions that would change this verdict

- If FA gains built-in caching and a `to_dict()` / raw-response mode
- If the codebase migrated to object-oriented TBA access patterns (FA's schema layer is well designed)
- If `tba_client.py` had an actual bug or maintenance burden

---

## Step 3: No code changes

Per the skip verdict, no code changes are made. `scout/tba_client.py` remains the canonical TBA wrapper.

`falcon-alliance` was NOT added to any requirements file.
