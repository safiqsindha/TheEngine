# Session Summary — 2026-04-11 (Coffee Shop Block)

**Duration:** ~6 hours planned, autonomous execution requested.
**Box:** MacBook Pro, venue WiFi tethered to iPhone hotspot as fallback.
**Operator:** Safiq. No mid-session intervention required.

---

## What landed

### 1. `design-intelligence/VISION_PLAN_EVAL.md` + `COFFEE_SHOP_TASKS.md`

Honest re-grade of `VISION_2027_TRAINING_PLAN.md` against its own stated values. Headline: the architecture (pluggable registry + game-agnostic heuristics) is A, but the training plan wrapped around it scores a D on "dead simple" and a C- on "quickly manageable" because it assumed hand-labeling 20k frames + an overnight MLX job in 2026 when zero-shot detectors (YOLO-World, Grounding DINO 1.5, Florence-2, Moondream 2) and open-data harvesting (Roboflow Universe, Chief Delphi, HF Hub) make the whole thing a ~12-hour week instead of a 60-hour summer.

Rewrite: **harvest first, zero-shot second, fine-tune as a fallback**, all driven by a single-command training script that runs on the MacBook Pro. `PURCHASE_LIST.md` captures Mac Mini + Roboflow subscription as post-season items.

`COFFEE_SHOP_TASKS.md` was written as the narrow 3-hour vision-rewrite plan (YOLO-World adapter → harvest_vision scaffolding → docs), but after a second look **we pivoted the 6-hour plan entirely to the Discord refactor + runbook + infra close-out** because the subprocess-shelling bot was a real in-season blocker and the vision rewrite is off-season work. The coffee shop task doc is kept in the tree for the next session's pickup.

Commit: `ae96daf` (landed at the top of the session, before execution began).

### 2. `antenna/live_scout_commands.py` — pure-Python command layer

The core deliverable. New 731-line module under `antenna/`. Replaces every `subprocess.run(["python3", "pick_board.py", ...])` call in `bot.py` with a direct Python API call. Eleven `cmd_*` functions covering the full draft-day command surface:

| Command | What it does |
|---|---|
| `cmd_rec` | Top-10 pick recommendation + headline block |
| `cmd_pick` | Record a pick (with full argument validation before state mutation) |
| `cmd_board` | Project the pick board + current alliances |
| `cmd_undo` | Roll back the most recent pick |
| `cmd_dnp` | Toggle Do-Not-Pick / list current DNPs |
| `cmd_alliances` | Alliance summary with EPA totals |
| `cmd_sim` | Monte Carlo playoff simulation (defaults 5k sims, capped 50k) |
| `cmd_captains` | Predicted captain picks + final captain roster |
| `cmd_lookup` | Team EPA + season history from Statbotics |
| `cmd_brief` | Read the latest synthesis brief JSON (dry-run aware) |
| `cmd_preview` | Pre-event report excerpt for a team (with a live-state fallback) |

Design invariants baked into every command:

- Returns `str`, never raises into the bot loop.
- Re-loads state at the start of each call (multiple operators, stale cache = wrong answers).
- `_safe_load_state()` wrapper avoids `pick_board.load_state()`'s `sys.exit(1)` when the state file is missing — catastrophic for a long-running Discord bot.
- `_team_int()` accepts `"148"`, `"#148"`, `"frc148"` (case-insensitive), range 1-99999.
- `cmd_sim` uses `contextlib.redirect_stdout` to capture `pb.sim_playoffs()` output since the sim prints directly.
- `cmd_pick` pushes to `state["history"]` BEFORE mutating `state["picks"]` — matches pick_board.cmd_pick semantics so `cmd_undo` rolls back cleanly.
- Path bootstrap makes `scout/` importable regardless of working directory.

### 3. `antenna/bot.py` — subprocess cut-over + 7 new commands

Swapped the four subprocess-based handlers (`!rec`, `!pick`, `!board`, `!lookup`) for `await asyncio.to_thread(lsc.cmd_*)` calls. Added seven brand-new `@bot.command` handlers: `!undo`, `!dnp`, `!alliances`, `!sim`, `!captains`, `!brief`, `!preview`. Every new handler is a ~10-line async wrapper around the matching `live_scout_commands.cmd_*` function; errors return as formatted strings, never tracebacks.

Net effect: every pick_board feature is now exposed to Discord, no interpreter startup on every command (was ~300-500 ms subprocess overhead per call), and input validation happens before state mutation instead of inside a subprocess that dumps an unreadable traceback into the channel.

### 4. `tests/antenna/test_live_scout_commands.py` — 36 hermetic tests

New test file, new package (`tests/antenna/__init__.py`). Every test redirects `pick_board.STATE_FILE` + `STATE_DIR` at a pytest `tmp_path`, so:
- No real draft state is touched.
- No subprocess is ever spawned.
- `cmd_lookup` monkey-patches `statbotics_client` — no network.
- `cmd_brief` writes fake JSON files via the `_REPO_ROOT` monkey-patch.

Test breakdown:
- 5 for `_team_int` + `_safe_load_state` helpers
- 2 for `cmd_rec` (missing state, happy path)
- 6 for `cmd_pick` (missing args, bad alliance type, out-of-range alliance, unknown team, already-taken, happy-path persistence)
- 1 for `cmd_board`
- 2 for `cmd_undo` (empty history, rollback)
- 4 for `cmd_dnp` (empty list, toggle add/remove, unknown team, populated list render)
- 1 for `cmd_alliances`
- 2 for `cmd_sim` (small-n happy path, bad n)
- 1 for `cmd_captains`
- 3 for `cmd_lookup` (missing, bad, monkey-patched happy path)
- 4 for `cmd_brief` (no state+no key, file missing, dry-run, real brief)
- 4 for `cmd_preview` (missing team, no event, team not at event, fallback snapshot)

Total: **36 passing, 0 failing, 0 skipped**. Full repo suite: **492 passed, 2 skipped** (baseline was 456 + 36 = 492 ✓).

### 5. `design-intelligence/REGIONAL_RUNBOOK.md`

Day-by-day operational playbook for a single 2-day regional. Covers:
- Friday 8 AM → 6 PM setup (baseline, .env sanity, pre-event report, Discord warmup, pick_board initialization, optional synthesis + vision worker startup)
- Saturday 8 AM → 7 PM quals (minimal/extended operator loop per match, midday re-seed refresh)
- Saturday evening 7 PM → 10 PM pre-draft homework (three questions to answer on paper, simulate-top-3 sequence, DNP list, brief review)
- Sunday 8 AM → 10 AM alliance selection hour (pre-draft checklist, during-draft picking flow, R2 snake)
- Sunday 10 AM → 6 PM playoffs (pre-round `!sim` snapshot loop)
- Failure modes section covering bot unresponsive, `!rec` empty, brief missing, vision crashing, corrupt state file, lost laptop
- Printable 1-page Discord cheat sheet
- Appendices: file paths, one-off recovery commands

Length: ~400 lines. The three-question homework block ("who's the best non-captain / who fills our biggest hole / who's going to steal our top pick") is the highest-leverage piece of the whole document — it's the thing that turns the aggregator output into a defensible pick decision.

### 6. `design-intelligence/LIVE_SCOUT_PHASE2_REMAINING.md` §1 — T2 V5 closed out

Phase 5 of the plan was going to be "wire vision worker into Bicep + GHA" but an audit of the current files showed:

- `infra/bicep/main.bicep` already has a `visionJob` resource block with `MODEL_NAME=fake`, `visionGpuSku=""` default, `*/10 * * * *` cron, 30-min replica timeout, and correct `dependsOn` edges.
- `infra/bicep/parameters.dev.json` already sets `visionCronExpression` and `visionModelName`.
- `.github/workflows/mode-a-build.yml` already has a "Smoke test — start one Vision worker execution" step in the deploy job.

All three pieces landed in an earlier commit (`e82cd10` — "Live Scout Phase 2 infra: vision + synthesis + tba-uploader jobs"). The only outstanding item was the tracker doc still saying "pending." Fixed it by flipping §1 to "RESOLVED 2026-04-11" with the audit trail of what was verified where.

No new infra code was needed.

---

## Test suite delta

| Phase | Passing | Skipped | Δ |
|---|---|---|---|
| Session baseline | 456 | 2 | — |
| After Phase 3 (hermetic tests) | 492 | 2 | **+36** |
| After Phase 7 (final) | 492 | 2 | **+36** |

Zero regressions. Zero tests skipped that weren't already skipped. Zero flakes.

---

## What got deferred, and why

### Vision rewrite (YOLO-World adapter + harvest_vision scaffolding)

Originally planned as Phase 1/2 of the coffee-shop execution. Deferred because the Discord subprocess-shelling bug was a real in-season draft-day blocker and the vision rewrite was strictly off-season R&D. `COFFEE_SHOP_TASKS.md` stays in the tree as the pickup plan for the next session.

### Anthropic key provisioning + TBA Trusted registration

Both blocked on Safiq (need to mint the key / complete the multi-day registration). `!brief` handles the missing-key case gracefully (returns "no brief yet" or "DRY-RUN stub"), so the Discord bot ships without either. `scripts/provision_anthropic_key.sh` and `scripts/provision_tba_trusted.sh` are already in the tree from commit `e2809c0`.

### Azure deploy

Same reason — Safiq owns the `az login` + `az deployment group create` run. The GHA workflow will fire on the next push to main once the repo secrets are set (see `mode-a-build.yml` comment block).

### Zone map for `detect_defense_events`

Needs a real VOD + a UI to click polygons on. Not a coffee-shop task. Tracked in `VISION_PLAN_EVAL.md` §Risks.

---

## File inventory — everything added / touched this session

**New files:**
- `antenna/live_scout_commands.py` (731 lines)
- `tests/antenna/__init__.py` (empty marker)
- `tests/antenna/test_live_scout_commands.py` (448 lines, 36 tests)
- `design-intelligence/REGIONAL_RUNBOOK.md` (~400 lines)
- `design-intelligence/VISION_PLAN_EVAL.md` (from `ae96daf`)
- `design-intelligence/COFFEE_SHOP_TASKS.md` (from `ae96daf`)
- `design-intelligence/SESSION_2026-04-11_SUMMARY.md` (this file)

**Modified files:**
- `antenna/bot.py` — subprocess → Python-API cut-over, +7 new commands
- `design-intelligence/LIVE_SCOUT_PHASE2_REMAINING.md` — §1 flipped to RESOLVED

**Commit plan (Phase 6):**
1. `feat(antenna): live_scout_commands Python API + bot.py cut-over + 36 hermetic tests`
2. `docs(design-intel): regional runbook + session summary + close out T2 V5 tracker`

Pushed to `origin/main`.

---

## Pickup notes for next session

1. **The vision rewrite is still on the table.** `COFFEE_SHOP_TASKS.md` is the plan; nothing in it has been executed. First move: Phase 1 (YOLO-World prefix handler at `eye/vision_models/yolo_world.py` + tests). `ultralytics` pip install is the only external dep and the tests stub it anyway.
2. **PURCHASE_LIST.md still needs to be written.** `VISION_PLAN_EVAL.md §Phase 5` has the sketch; needs to be a real file before the post-season purchase window opens.
3. **Zone-map UI.** Smallest useful tool: a one-off matplotlib script that overlays a VOD frame and captures polygon clicks into a JSON file the defense heuristic can load. Off-season.
4. **`antenna/bot.py` could use a `!status` command.** Right now there's no way from Discord to see which workers are up, how many matches are logged, etc. — operator has to shell into the laptop. Add a `lsc.cmd_status()` that reads state file + worker logs + returns a compact table. Probably 30 minutes of work.
5. **The REGIONAL_RUNBOOK mentions a `--force` flag on `pick_board.py setup` that doesn't exist yet.** Small gap — either add the flag or remove the runbook reference. Force-overwrite should preserve picks/dnp/history; the runbook already describes the contract.

---

## Honest self-assessment

**What went well:**
- The pivot from vision rewrite to Discord refactor was the right call. Would have shipped ~0 user-facing value if we'd spent 6 hours on zero-shot detectors this weekend.
- Test-first worked: caught the `predict_captains` tuple-vs-list bug before it could hit Discord on draft day.
- Zero regressions, clean diff. Easy to review.

**What I'd do differently:**
- I should have audited the Bicep/GHA state BEFORE writing Phase 5 into the plan. The whole phase was 10 minutes of verification that nothing needed doing.
- The live_scout_commands.py file is big (~730 lines). Could have split `cmd_*` into one-file-per-command under `antenna/live_scout_commands/`. Not a blocker; just would be nicer.
- REGIONAL_RUNBOOK.md is speculative — it's written as if we've run regionals before with this system, but we haven't. The real runbook will get rewritten after Belton.
