# Live Scout Phase 2 — Remaining Work

**Status as of 2026-04-10 night:** T2 V1 + V3 + V4 shipped (commits `0beabe0` + `ba9be9a`).
Test suite: **327 passing, 2 skipped** (+43 vs Phase 1 baseline).

What's still on the list, ordered by what to grab first.

---

## 1. T2 V5 — Bicep + GHA wiring (smallest, ~30 min)

Close out the vision worker by wiring it into infra.

- **`infra/bicep/main.bicep`** — add `vision-worker` Container App Job
  - Cron: `*/10 * * * *`
  - Env: `MODEL_NAME` (default `"fake"` until V0a lands), `STATE_BACKEND=azure`,
    `AZURE_STORAGE_CONNECTION_STRING` from Key Vault
  - New param: `visionGpuSku` (string, default `""` so CPU is the fallback)
  - Image tag follows the same `${acrLoginServer}/vision-worker:${imageTag}` pattern as mode-a
- **`.github/workflows/mode-a-build.yml`** — add `vision-worker` build target
  - Same matrix entry shape as mode-a/mode-b/backfill — point Dockerfile build context at
    `workers/` and tag with the new image name
- **No new Dockerfile needed** — vision_worker.py imports from the same `workers/` package
  the existing image already builds

**Done when:** `python3 -m pytest tests/live_scout/` still green and `terraform plan`/`bicep build`
runs clean against the updated template.

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

- **V0a** — Pick a Roboflow Universe FRC YOLO model. Need: model ID, class map, confidence threshold. Wire into `eye/vision_yolo.py::_load_real_model`, then flip `MODEL_NAME` env from `"fake"` to the real ID in the vision-worker job.
- **V0b** — Pick an Azure GPU SKU for the vision worker (or accept CPU latency). Set `visionGpuSku` Bicep param.
- **T3 prereq** — Get an Anthropic API key into the Azure Key Vault entry the synthesis-worker job pulls from.
- **U prereq** — Register the team's TBA Trusted User account, get `auth_id` + `auth_secret` into Key Vault.

---

## Order of operations tomorrow

Recommended grab order to minimize merge friction (everything goes onto `main` directly — no parallel agents this time, since the previous round all hit token limits):

1. **T2 V5** (30 min) — closes T2 entirely
2. **U** end-to-end (3-4h) — bigger but self-contained
3. **T3** end-to-end (2-3h) — depends on T2 vision data being in state, so do it last so live test data is realistic
4. **Cleanup + final push**

Total estimated remaining work: **~6-8 focused hours**.
