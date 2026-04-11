# Regional Competition Runbook — Live Scout + Antenna

**Status:** operational playbook, 2026-04-11. Covers a single 2-day regional (Friday setup → Sunday playoffs). Assumes: Live Scout Phase-1 shipped, Antenna Discord bot live, pick_board.py 2.0 API wired through `antenna/live_scout_commands.py`, vision worker optional (runs in dry/fake mode if not provisioned yet).

**Owner at event:** Safiq + one student operator. Mentor has a MacBook Pro (M-series, ≥16 GB unified memory), iPhone hotspot, and a Discord channel provisioned under team ownership (`#engine-scout-live`).

**Scope:** everything the operator types, clicks, or watches between Friday 8 AM and Sunday 8 PM, plus the fall-back moves when each subsystem fails. Does NOT cover hardware pit operations, drive-team comms, or robot maintenance — separate docs own those.

---

## TL;DR — the minimum viable day

If every other section of this doc burns down, keep doing these three things and you still ship:

1. **Run `scout/pick_board.py setup 2026<event> --team 2950 --seed <best guess>`** before quals end so the state file exists.
2. **During each match, post the live score via `!pick` / `!board` in the Antenna channel** so there's a timestamped paper trail.
3. **Between quals and alliance selection, run `!rec` three times** (once at +0 min, +10 min, +20 min relative to the seeding refresh) and pick the team that shows up top-5 in at least 2 of the 3 runs.

Everything else is polish on top of those three moves.

---

## Friday — pre-event setup (8 AM → 6 PM)

### 8:00 — Laptop baseline

- Open the laptop, connect to the venue WiFi. If venue WiFi is flaky, tether to the iPhone hotspot. TBA + Statbotics are the only network-bound calls.
- `cd "/Users/safiqsindha/Desktop/The Engine/TheEngine"`
- `git pull --ff-only` — confirm you've got the latest `main`.
- `python3 -m pytest tests/ -q` — should be **492 passed, 2 skipped**. Red tests at the event are a rollback signal; if anything is red, stop, `git log -20`, and revert whatever landed last.

### 8:30 — Environment sanity

```bash
# .env file check — required keys
grep -E "ANTENNA_BOT_TOKEN|ANTENNA_CHANNEL_ID|TBA_READ_KEY|STATBOTICS" .env | wc -l
# Expected: 4 (or more — optional keys are fine to have)
```

- `ANTENNA_BOT_TOKEN` — required, Discord won't post without it.
- `ANTENNA_CHANNEL_ID` — required, digest goes nowhere without it.
- `TBA_READ_KEY` — required for pick_board setup (enrich).
- `ANTHROPIC_API_KEY` — optional. Synthesis worker runs in dry-run without it; `!brief` will say "DRY-RUN stub" until you add it.

### 9:00 — Pre-event report

One-shot: pre-compute every team's season EPA + event history so `!lookup` is instant during the chaos of quals.

```bash
python3 scout/pre_event_report.py --event 2026<event> --year 2025 > /tmp/pre_event_2026<event>.txt
# Scan the top-20 and bottom-5 manually while you have coffee.
```

Red flags to scan for:
- **Teams with zero qualifying matches this season** — the Monte Carlo sim treats them as 50 ± 20 EPA (prior-only), but you should eyeball their build-season Open Alliance threads (`!scan` + filter by team).
- **Teams whose 2025 EPA dropped more than 20 points from 2024** — that's a rebuild team; they may over/underperform by a lot.
- **Teams with an event history that's all regionals in one state** — they may have been sandbagging weaker competition; real strength unknown.

Jot a list of 5 "watch carefully" teams on a sticky note. These are the teams whose every match you'll re-confirm manually instead of trusting the aggregator blindly.

### 10:00 — Discord channel warm-up

In `#engine-scout-live`:

```
!scout
```

This should return some variant of "Scout online. 0 matches logged." If the bot is offline, `cd antenna && python3 bot.py &` and wait for the `Starting The Antenna Discord bot...` line. Then re-try `!scout`.

Test the four read-only commands:
```
!event 2026<event>
!matchnow 2026<event>
!eyescores 2026<event>
!scouted 2026<event>
```

If any one of them returns `Error: ...`, STOP. Read the error, fix the root cause (usually a missing .env key or a stale eye_bridge state file), and re-test. Pushing through a broken bot on draft day is the number-one way to ruin Sunday morning.

### 11:00 — pick_board initialization (dry run)

```bash
cd scout
python3 pick_board.py setup 2026<event> --team 2950 --seed 1
# Seed 1 is a placeholder — we don't know our real seed until quals end.
# The seed only affects recommend_pick output (it shifts which picks are
# considered ours); everything else is idempotent.
```

This pulls the event team list from TBA + Statbotics and populates `scout/.cache/draft/live_draft.json`. From Discord:

```
!board
```

Should show an 8-alliance scaffolding (captains are all "TBD until quals end") + a team list. If it returns `Error: No active draft`, the state file didn't land — check `ls scout/.cache/draft/`.

### 12:00 — Optional: start synthesis/vision workers

These are additive — the bot works without them, but running them means you get a real `!brief` output at the end of qualifying.

**Synthesis worker** (requires `ANTHROPIC_API_KEY` in .env):
```bash
cd workers
nohup python3 synthesis_worker.py --event 2026<event> > synthesis.log 2>&1 &
```

**Vision worker** (runs in fake mode without `MODEL_NAME` pointing at a real YOLO checkpoint):
```bash
cd workers
MODEL_NAME=fake nohup python3 vision_worker.py --event 2026<event> > vision.log 2>&1 &
```

Both workers hit the event's cached VODs and emit events into `eye_bridge.state`. The Discord `!eyescores` command reads from that.

---

## Saturday — qualifying rounds (8 AM → 7 PM)

### 8:00 — Restart-check

Laptops die overnight. Before quals start:

- `ps aux | grep bot.py` — Antenna bot still up?
- `ps aux | grep vision_worker` / `grep synthesis_worker` — workers still up?
- `!matchnow 2026<event>` in Discord — does the bot respond?

If any process has died, restart it. The workers are stateless (they write to files that survive a restart), so there's no data loss.

### During each qualification match

**Minimal operator loop — ~30 seconds per match:**

1. Watch the match on the venue feed OR on TBA live stream.
2. When the final score posts, run `!matchnow 2026<event>` to verify the bot picked it up. If not, wait 30-60s and re-run.
3. If you noticed anything unusual (robot broke, great defense play, surprise strategy), DM Safiq or drop a one-line note in `#engine-scout-live` tagged `OBS:` for later review.

**Recommended extended loop — ~2 minutes per match:**

After match N, look at the N+1 to N+3 preview:
```
!matchnow 2026<event>
!preview <top opponent we'll face>
```

This primes the cache and gives you time to notice issues (e.g., a team suddenly dropping in EPA, or a surprise partner).

### 12:00 noon — midday re-seed estimate

Halfway through quals:
```
!scouted 2026<event>        # how many matches did Live Scout log
!eyescores 2026<event>      # how many robots did the EYE detector find
```

These two should be roughly in the same ballpark (one human-logged scout per match + vision-detected robot events). If they're radically different (e.g., 30 human-scouted, 5 vision-detected), the vision worker is misfiring — check `vision.log`. This is not blocking; the draft doesn't depend on vision, but it does affect the quality of `!rec`.

At this point also run:
```bash
python3 scout/pick_board.py refresh 2026<event>
```

This re-pulls current Statbotics EPA and updates the teams table in `live_draft.json`. The `!board` output will shift as teams rise and fall.

### 6:00 PM — quals end

Once FIRST posts the final qual rankings:

```bash
# Update our_seed in the state file to match the posted ranking.
# If we finished 4th, for example:
python3 scout/pick_board.py setup 2026<event> --team 2950 --seed 4 --force
# --force overwrites the existing state but PRESERVES picks + dnp + history.
# Double-check --force is actually implemented before relying on it:
grep -n "force" scout/pick_board.py | head
# If not implemented, manually edit scout/.cache/draft/live_draft.json and
# bump our_seed. That file is JSON; don't break it.
```

---

## Saturday evening — pre-draft homework (7 PM → 10 PM)

This is the single most valuable block of the whole weekend. You have ~3 hours to stare at data before the draft starts.

### The three questions

Answer each of these in your own words on paper:

1. **Who's the best non-captain?** Run `!rec` and look at rank 1. Does that match your gut from watching quals? If not, WHY? Write down the gap.
2. **Who's the best defensive complement to our alliance?** Run `!preview` on the top 5 `!rec` results and compare their `total_tower` and `epa_endgame` numbers. Our alliance already has X; we want the partner that fills the biggest hole.
3. **Who's going to steal our top pick?** Run `!captains` to see the pick-prediction output. If Alliance 1 is predicted to take our top pick, we need a strong second choice ready.

### Simulate the top 3 alternatives

For each of your top 3 picks:
```
!pick 4 <candidate_team>
!sim 10000
!undo
```

This sequence:
1. Pretends to pick the candidate
2. Runs a 10k-sim playoff bracket with the hypothetical alliance
3. Rolls back so you can try the next candidate

Write down: **candidate / alliance EPA after pick / simulated QF win% / playoff win%**

The candidate that maximizes playoff win% (not just QF win%) is usually the right call, because QF is rarely the fight — it's the semis and finals where EPA margin becomes the deciding factor.

### DNP list

Anyone who's broken more than once during quals, or whose drive team looks unprepared:
```
!dnp <team>
```

DNP'd teams are filtered out of `!rec` entirely. They still show up in `!board` but with a marker. Be conservative — it's very bad to DNP a team that's actually fine just because they had one bad match. Only DNP if you have two concrete reasons.

### Brief (if synthesis is provisioned)

```
!brief
```

If this returns a `DRY-RUN stub` message, that's expected and fine — skip this step. If it returns a real brief, read it carefully. The LLM will often surface a pick consideration you missed (e.g., "2056 is climbing from a bot with a known endgame reliability issue — fallback to 148 if 2056 fails first climb").

---

## Sunday — alliance selection morning (8 AM → 10 AM)

### The alliance selection hour

Draft day has 8 alliances picking in strict seed order. You have ~15 seconds to call each pick when it's your turn. The whole thing is done in under 20 minutes and there is no time to debug the bot.

**Pre-draft checklist (08:30 → 09:00):**

- [ ] Bot is responding (`!scout` returns online)
- [ ] `!rec` returns your expected top pick (if not, something changed overnight)
- [ ] `!captains` matches the predicted pick order you wrote down last night
- [ ] Backup plan on paper — top 3 picks, DNP list, notes

**During the draft:**

As each alliance picks (including the ones before us), log it:
```
!pick <alliance#> <team>
```

This keeps the state file in sync with reality so `!rec` is always accurate when it's our turn. DO NOT skip this step even if you're tempted to "just do it in my head" — the recommendation engine needs the most recent state to give you a good answer.

When it's our turn:
```
!rec
```

Look at the top-3 results. If rank 1 matches your pre-draft homework, pick them. If rank 1 is a surprise team, pause, check why (look at their `!preview`), and decide in ≤30 seconds.

After making the pick IRL, record it:
```
!pick 4 <team>
```

### Round 2

In R2 the snake reverses (alliance 8 picks first). Your second pick matters less for EPA (the remaining pool is thinner) but MORE for complementarity. Re-run `!rec` — the complementarity score will have shifted significantly now that the pool has narrowed.

### If you mis-type a pick

```
!undo
```

Rolls back the most recent pick. History is preserved across multiple undo calls, so you can undo multiple picks in sequence if the whole last minute went sideways.

---

## Sunday — playoffs (10 AM → 6 PM)

Playoffs are less operator-driven. Main tasks:

### Before each playoff round

```
!matchnow 2026<event>
!sim 10000
```

The sim gives you a "what the bracket looks like from here" snapshot. Use it to:
- Estimate which alliance is the biggest threat in the opposite bracket
- Check if our finals probability just went up or down
- Decide whether to share a "we're feeling good / we're feeling nervous" update with drive team

### During each playoff match

Same minimal loop as quals — watch, verify TBA has the score, note any observations.

### Between playoff rounds

If you have 10+ minutes, run `!brief` again. The synthesis worker's prompt includes recent match context, so the brief in the semis will be different from the brief in QFs.

---

## Failure modes & recovery

### "Bot is not responding" in Discord

1. Is the bot process running? `ps aux | grep bot.py`
2. If not: `cd antenna && python3 bot.py &` and re-test.
3. If yes but no response: `tail -50 antenna/nohup.out` or stdout. Usually a Discord rate limit (wait 60s) or a missing key (fix .env, restart).
4. If still broken: fall back to the CLI directly — `python3 scout/pick_board.py rec` gives you the same data without Discord.

### `!rec` returns "no pick candidates"

Either the pool is empty (everyone's taken or DNP'd) or state is corrupt. Check:
```bash
python3 -c "import json; s=json.load(open('scout/.cache/draft/live_draft.json')); print(len(s['teams']), len(s['picks']), len(s['dnp']))"
```

If `teams` is 0, the setup step failed. Re-run `pick_board.py setup`. If `teams` is populated but every team is somehow taken, you mis-clicked `!pick` too many times — `!undo` repeatedly until the state reflects reality.

### `!brief` returns "no brief yet"

The synthesis worker either hasn't run yet or is dry-running. Not a blocker — skip it and rely on `!rec` + your pre-draft homework.

### The vision worker is crashing

Not a draft blocker. Kill it:
```bash
kill $(ps aux | grep vision_worker | grep -v grep | awk '{print $2}')
```

`!eyescores` will start showing older data. `!rec` falls back to EPA-only scoring (the `eye_score` component goes to 0, weights redistribute to EPA + Floor + Comp + MC).

### State file corrupts mid-event

Possible if the laptop crashes during a `save_state` call. The state file is JSON; open it in a text editor and fix it by hand (usually removing a trailing comma or a truncated closing brace). Worst case:
```bash
# Re-setup from scratch — LOSES picks/dnp/history.
python3 scout/pick_board.py setup 2026<event> --team 2950 --seed 4
```

Then manually re-enter every pick that had been made up to the crash via repeated `!pick` calls.

### Lost the laptop entirely

You have a backup plan. On the iPhone, open the GitHub repo in Safari, navigate to `scout/pick_board.py` comments, and manually copy the top-5 candidate teams from the pre-event report you printed Friday morning (see 9:00 step above — **actually print it this time, not just on the screen**). Make the pick by gut from that list.

---

## Discord command cheat sheet (printable, one page)

```
── LIVE SCOUT DRAFT COMMANDS ──

!rec                   Top 10 pick recommendations + top-pick summary
!pick <A#> <team>      Record a pick (alliance 1-8, team number)
!undo                  Roll back the most recent pick
!board                 Full pick board + current alliances
!alliances             Alliances summary with EPA totals
!dnp [team]            Toggle/list Do-Not-Pick teams
!sim [n]               Monte Carlo playoff simulation (default 5000)
!captains              Predicted captain pick order + backfill
!lookup <team>         Team EPA + season history (hits Statbotics)
!preview <team>        Pre-event report excerpt for a team
!brief [event]         Latest strategic brief (needs synthesis worker)

── READ-ONLY / STATUS ──

!scout                 Scout process status
!event <event_key>     Switch to a different event context
!matchnow <event>      Current / most recent match state
!scouted <event>       How many matches have been logged
!eyescores <event>     EYE vision detector counts
!loadscout             Reload scout state from disk
!strategy <match>      Per-match game plan (if pre-computed)
```

---

## Appendix A — file paths (for when shit breaks)

| What | Where |
|---|---|
| Antenna bot | `antenna/bot.py` |
| Live Scout command layer | `antenna/live_scout_commands.py` |
| Pick board engine | `scout/pick_board.py` |
| Draft state file | `scout/.cache/draft/live_draft.json` |
| Pre-event report | `scout/pre_event_report.py` |
| Statbotics client | `scout/statbotics_client.py` |
| Eye bridge state | `eye/.cache/eye_bridge.state.json` |
| Synthesis brief output | `workers/.state/briefs/brief_<event>.json` |
| Vision worker log | `workers/vision.log` (wherever nohup put it) |
| Antenna DB | `antenna/.antenna.db` (SQLite) |

---

## Appendix B — one-off commands you might need

```bash
# Re-enrich the team pool mid-event (after refresh or a team drops)
python3 scout/pick_board.py enrich

# Force-recompute team aggregates after adding new eye_bridge data
python3 -c "
import sys; sys.path.insert(0, 'scout')
import pick_board as pb
import json
s = pb.load_state()
pb.recompute_team_aggregates(s)
pb.save_state(s)
"

# Check synthesis brief freshness
ls -lt workers/.state/briefs/

# Tail-follow both workers at once
tail -f workers/vision.log workers/synthesis.log

# Dump the bot's in-memory state (command count, etc.)
# -- add this as a !scout subcommand later; for now just grep logs.
grep "command" antenna/nohup.out | tail -20
```

---

## Change log

- **2026-04-11** — initial runbook written alongside the pick_board → antenna refactor. Covers subprocess-free command wiring (`antenna/live_scout_commands.py`) and the 7 new draft-day commands (`!undo !dnp !alliances !sim !captains !brief !preview`). Vision worker treated as optional; brief worker treated as optional.
- _Next update after Belton regional debrief._
