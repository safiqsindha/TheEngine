# Live Scout Phase 2 — Remaining Work

**Status as of 2026-04-11:** T2 V1 + V3 + V4 + V5 shipped. T2 fully in-infra.
Test suite: **492 passing, 2 skipped** (+165 vs the 2026-04-10 baseline,
includes the Antenna Live Scout command layer tests from
`tests/antenna/test_live_scout_commands.py`).

What's still on the list, ordered by what to grab first.

---

## 1. ~~T2 V5 — Bicep + GHA wiring~~ **RESOLVED 2026-04-11**

Vision worker is fully wired into the infra. Audit trail:

- `infra/bicep/main.bicep` — `visionJob` resource block (lines ~368-455):
  - `cronExpression: visionCronExpression` (default `*/10 * * * *`)
  - Env: `MODEL_NAME=fake` (from `visionModelName` param), `STATE_BACKEND=azure`,
    `AZURE_STORAGE_CONNECTION_STRING` from inline secret, `VISION_GPU_SKU`
    (from `visionGpuSku` param, default `""`)
  - `replicaTimeout: 1800` (30 min ceiling per tick)
  - `dependsOn: [dispatcherTable, pickBoardContainer]`
  - Output: `visionJobName`
- `infra/bicep/parameters.dev.json` — `visionCronExpression` + `visionModelName`
  set to their production defaults (`*/10 * * * *` + `fake`)
- `.github/workflows/mode-a-build.yml` — the `deploy` job has a
  "Smoke test — start one Vision worker execution" step (lines ~142-148)
  that fires the job after every manual deploy
- `MODEL_NAME=fake` is enforced in prod per V0a decision below — when real
  models ship, flip the param, don't touch the template

**No new Dockerfile needed** — `workers/vision_worker.py` is packaged inside
the same image the mode-a job uses, so the single existing build target covers
both jobs.

**Done when:** `python3 -m pytest tests/` green (**492 passing, 2 skipped** as of 2026-04-11) and
`az bicep build --file infra/bicep/main.bicep` parses clean. Pytest confirmed green 2026-04-11;
the Bicep template hasn't changed in this session so the last successful parse (commit that
introduced the `visionJob` block) is still authoritative.

---

## 2. T3 — Synthesis worker (medium, ~2-3 hours)

Opus-powered end-of-day strategic brief. Cron fires once per night, calls Anthropic, writes a
`BriefDocument` blob the Discord bot picks up.

### S0c — pick_board audit (already done, no work)
There is no existing end-of-day rankings function. `recompute_team_aggregates` (pick_board.py:218)
gives us per-team `real_avg_score` / `real_sd` / `streak`. The synthesis worker computes its own
ranking from `state["teams"]` aggregates — no shared helper needed.

### S1 — `scout/synthesis_prompt.py`
- `SynthesisInputs` dataclass:
  - `event_key: str`
  - `our_team: int`
  - `top_teams: list[dict]` — top-N from `state["teams"]` ranked by `real_avg_score`
  - `recent_matches: list[dict]` — last ~10 LiveMatches sorted by `match_num`
  - `next_opponent_matches: list[dict]` — schedule entries with our team's upcoming matches
- `collect_synthesis_inputs(state, event_key, our_team, *, top_n=24, recent_n=10) -> SynthesisInputs`
- `build_synthesis_prompt(inputs: SynthesisInputs) -> tuple[str, str]`
  - Returns `(system_prompt, user_prompt)` ready for `client.messages.create`
  - System prompt: "You are a strategic scout for FRC Team 2950. Output a brief with sections..."
  - User prompt: stringified inputs in a format Opus can chew on
- Tests: `test_synthesis_prompt.py` — happy path, empty state, missing our_team, top_n cap

### S2 — `workers/synthesis_worker.py`
Mirror `mode_a.py` shape:
- `BriefDocument` dataclass: `event_key, generated_at, top_picks: list[int], pick_rationale: dict[int, str], summary: str, raw_response: str`
- `SynthesisWorkerResult` dataclass: `processed: bool, brief: Optional[BriefDocument], errors: list[str]`
- `call_anthropic(system, user, *, client, model="claude-opus-4-6") -> str`
  - Lazy import of `anthropic` so the module imports clean without the SDK
  - Inject `client` for tests (`FakeAnthropicClient` returning a scripted response)
- `parse_brief_response(text: str) -> BriefDocument` — tolerate malformed output, never raise
- `run_synthesis_worker(*, event_key, our_team, state, brief_backend, client=None) -> SynthesisWorkerResult`
- CLI: `--event 2026txbel --our-team 2950 [--debug]`

### S2 helper — `get_brief_backend` factory
Add to `workers/state_backend.py`, mirror `get_digest_backend`:
- Local: `workers/.state/briefs/brief_<event_key>.json`
- Azure: `AZURE_STATE_BLOB_CONTAINER` / `brief_<event_key>.json` (default)
- Add `_DEFAULT_BRIEF_LOCAL_DIR` constant alongside the other defaults
- Add `AZURE_BRIEF_BLOB` env var doc to the module docstring

### S2 deps — `workers/requirements.txt`
- Add `anthropic>=0.40,<1.0`

### S3 — Tests
- `test_synthesis_prompt.py` — collect_synthesis_inputs filtering, build_synthesis_prompt shape
- `test_synthesis_worker.py` — FakeAnthropicClient, parse happy + malformed, run end-to-end with hermetic state
- `test_state_backend.py` — extend with `get_brief_backend` local + azure path tests

### S4 — Bicep + GHA wiring
- `infra/bicep/main.bicep` — `synthesis-worker` Container App Job
  - Cron: `0 4 * * *` UTC (= 8pm PT — runs after qual day ends)
  - New params: `synthesisAnthropicModel` (default `"claude-opus-4-6"`)
  - Secrets: `ANTHROPIC_API_KEY` from Key Vault
- `.github/workflows/mode-a-build.yml` — synthesis-worker build target

**Done when:** Synthesis worker tests pass, Discord bot can read `brief_<event>.json` blob and post the digest.

---

## 3. U — TBA video uploader (medium-large, ~3-4 hours)

Auto-publish post-match video links to TBA so other teams (and our Mode B backfill on the next event) get them for free.

### U1 — `eye/match_boundary.py`
- `MatchBoundary` dataclass: `match_key, comp_level, match_num, start_frame_idx, end_frame_idx, start_unix, end_unix`
- `MatchBoundaryDetector` state machine — walks frames, detects auto countdown → end-of-match transition
- `detect_boundaries_from_frames(frames, ocr) -> list[MatchBoundary]`
- `validate_against_tba_schedule(boundaries, tba_matches) -> list[MatchBoundary]` — drop boundaries that don't line up with a TBA scheduled match
- Tests: scripted OCR results, schedule alignment edge cases

### U2 — `scout/tba_writer.py`
- `TbaWriter` class
  - HMAC-MD5 signing per [TBA Trusted v1 spec](https://www.thebluealliance.com/apidocs/trusted/v1)
    - `sign = md5(auth_secret + url_path + body_json).hexdigest()`
    - Headers: `X-TBA-Auth-Id`, `X-TBA-Auth-Sig`
  - `add_match_video(event_key, match_key, video_key) -> None`
  - Lazy `requests` import
  - Retries with exponential backoff on 5xx, idempotent on 400 "already exists"
- Tests with `requests-mock` (already in dev deps? — check; if not, use a manual transport injection like the Anthropic client pattern)

### U3 — `workers/tba_uploader.py`
- `TbaUploadResult` dataclass: `processed: list[str], skipped_already_uploaded: list[str], skipped_no_video: list[str], errors: list[tuple[str, str]]`
- `find_pending_uploads(state) -> list[dict]` — LiveMatches with `source_video_id` set but no `tba_uploaded` flag
- `upload_one_match(record, *, writer) -> str` — returns status string
- `run_tba_uploader(*, state, writer) -> TbaUploadResult`
- CLI: `--event ... [--dry-run] [--debug]`
- Mark records with `record["tba_uploaded"] = True` after success (new field, schema bump candidate)
- Tests with FakeTbaWriter

### U4 — Bicep + GHA wiring
- `infra/bicep/main.bicep` — `tba-uploader` Container App Job
  - Cron: `*/15 * * * *`
  - Secrets: `TBA_TRUSTED_AUTH_ID`, `TBA_TRUSTED_AUTH_SECRET` from Key Vault
- `.github/workflows/mode-a-build.yml` — tba-uploader build target

### U4 — Handoff doc
- `design-intelligence/GATE_2_HANDOFF.md` — append "Phase 2: TBA Trusted User registration"
  - Steps to register the team account at TBA, request trusted access, store creds in Key Vault

**Done when:** A LiveMatch with a `source_video_id` triggers an HTTP POST to TBA on the next cron tick (in dry-run during dev).

---

## 4. Cleanup

- Delete `worktree-agent-a81ad389` worktree (T2 V1 file is salvaged into main):
  ```
  git worktree remove .claude/worktrees/agent-a81ad389
  git branch -D worktree-agent-a81ad389
  ```
- Final `python3 -m pytest tests/live_scout/` and push.

---

## 5. Human-blocked prerequisites (can't be coded — Safiq needs to do)

These don't block writing the code (everything above stubs them), but they have to be resolved before Phase 2 actually runs in prod:

- ~~**V0a** — Pick a Roboflow Universe FRC YOLO model.~~ **RESOLVED 2026-04-11 → Path C** (see `V0a_MODEL_SELECTION.md`). No single Roboflow model emits our 5-class taxonomy with team_num, and every compound pipeline we'd wire up in-season gets thrown away when the 2027 Gemma+SAM3.1 data engine ships. Decision: **stay `MODEL_NAME=fake` through the 2026 season**; replace during summer 2026 via the off-season data engine (§6) trained on **our** taxonomy. `_load_real_model` stays as `NotImplementedError` so prod never silently falls back to fake. Follow-up: refactor `eye/vision_yolo.py` to a pluggable model registry so new 2026-era and 2027-era models can be swapped in with a one-line `register_model(...)` call — no core code changes.
- ~~**V0b** — Pick an Azure GPU SKU for the vision worker.~~ **RESOLVED 2026-04-11 → CPU only** (see `V0b_GPU_SELECTION.md`). YOLOv8n/v11n CPU inference fits comfortably in the 10-minute cron budget for all three V0a paths; the T4 SKU saves ~15 seconds per invocation for ~$7/month extra, which nearly triples the infrastructure line item for near-zero operational benefit. Decision: `visionGpuSku=""` (already the default) in both dev + prod parameter files. Revisit only if Mode A cadence moves to `* * * * *` or a >25M-param custom model ships.
- ~~**T3 prereq** — Get an Anthropic API key into Key Vault.~~ **Tooling ready** — `scripts/provision_anthropic_key.sh` stores + verifies + runs a live smoke test of the synthesis worker against the key. Just needs Safiq to mint the key at console.anthropic.com, export it, and run the script. See `GATE_2_HANDOFF.md §8`.
- ~~**U prereq** — Register the team's TBA Trusted account, get creds into Key Vault.~~ **Tooling ready** — `scripts/provision_tba_trusted.sh` stores both secrets and runs `workers.tba_uploader --dry-run` to validate the HMAC-MD5 signing path. Just needs Safiq to complete the TBA Trusted registration (1–3 day approval) and run the script. See `GATE_2_HANDOFF.md §7`.

---

## Order of operations tomorrow

Recommended grab order to minimize merge friction (everything goes onto `main` directly — no parallel agents this time, since the previous round all hit token limits):

1. **T2 V5** (30 min) — closes T2 entirely
2. **U** end-to-end (3-4h) — bigger but self-contained
3. **T3** end-to-end (2-3h) — depends on T2 vision data being in state, so do it last so live test data is realistic
4. **Cleanup + final push**

Total estimated remaining work: **~6-8 focused hours**.

---

## Off-season backlog (post-Phase 2)

### Auto-labeling data engine — Gemma + SAM3.1 on MLX

**The play:** Use a small reasoning LLM (Gemma 4) orchestrating SAM3.1 on Apple Silicon
(MLX, no GPU) as a label oracle against archived FRC broadcasts. Output: FRC-specific
YOLO training data for the T2 vision worker.

**Why it matters:** T2 V0a is currently blocked on "pick a Roboflow Universe FRC YOLO
model." Whatever we pick is trained on someone else's footage, someone else's game year,
and someone else's class taxonomy. The data-engine play unblocks V0a permanently —
we ship a model trained on Devastators-relevant footage with classes we control.

**Sketch:**
1. `tools/auto_label/` — new top-level tool, not part of the cron worker fleet
2. Input: archived match VODs from `eye/.cache/` or YouTube backfill
3. Pipeline: extract frames → Gemma 4 picks open-vocabulary prompts per frame
   ("segment robot 2950 attempting a climb", "segment any robot scoring") → SAM3.1
   returns masks → convert masks to YOLO bounding boxes → write `data.yaml` +
   `labels/*.txt` in YOLO training format
4. Train a small YOLOv8/v11 model on the auto-labels
5. Ship the trained weights into the vision-worker job, flip `MODEL_NAME` from
   `"fake"` to the local model id

**Why this fits the pattern we already use:**
- Same shape as `project_llm_wiki.md` — Karpathy's data engine, but for vision instead
  of code/docs
- Same shape as `reference_advisor_strategy.md` — small executor + reasoner pair, here
  the reasoner is Gemma 4 and the executor is SAM3.1
- Runs on a MacBook — no Azure GPU procurement (V0b also unblocked)

**Latency reality:** ~10-15 sec/frame on M-series. A 4-hour broadcast at 0.5s frame
interval is ~28k frames → 80-120 hours of single-machine inference. **This is fine** —
it's an off-season batch job, not a cron tick. Run it on archived footage during summer.

**Status:** Idea only. Not started. Revisit after Phase 2 ships and after the 2026
season ends so we have a full year of Devastators footage to chew on.

**Sources:** sam3-angle (https://github.com/Radar105/sam3-angle), Maziyar Panahi tweet
2026-04 demoing Gemma 4 + SAM 3.1 on MLX.
