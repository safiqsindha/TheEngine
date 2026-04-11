# THE ENGINE — Live Scout Phase 1 Build Scope
# Concrete deliverables, integration spec, dependency graph
# Team 2950 — The Devastators
# Authored: 2026-04-10
# ═══════════════════════════════════════════════════════════════════

## How to read this doc

This is the **implementation companion** to
[LIVE_SCOUT_ARCHITECTURE.md](LIVE_SCOUT_ARCHITECTURE.md). The architecture
doc says *what* we're building and *why*. This doc says *how*, in what
order, what each piece must accept and produce, and where it plugs in.

Phase 1 ships through six gates. Each gate is independently shippable
and demonstrably useful — we don't have an "all or nothing" big-bang
deploy at the end. If we run out of time mid-gate, the system at the
last completed gate is still doing real work for us.

---

## Findings from the pre-build audit

Before scoping deliverables, here's what the audit found in existing
code that constrains the design.

### `scout/pick_board.py` (1387 lines) — the consumer

| Question | Answer |
|---|---|
| Input shape | Reads event-level EPA from `statbotics` (line 564) + per-match TBA data via `cmd_enrich` (line 1016). **No live match feed exists yet.** |
| State store | `.cache/draft/live_draft.json` via `save_state()` (line 131). Single dict, full rewrite on each call. |
| Identifier scheme | TBA-style: team_key `frc2950`, event_key `2026txbel`, match_key `2026txbel_qm32`. |
| Update pattern | Direct dict mutation: `state["teams"][str(team_num)][field] = value` then `save_state(state)`. |
| Existing TBA client | Yes — `scout/tba_client.py` (249 lines). 1-hour cache by default; override `ttl=0` for live mode. |
| Reusable function for Live Scout | **No.** We add `append_live_match(state, match_dict)` next to `cmd_enrich`. |

**Integration spec for F4** (locked in here so we don't relitigate):

```python
# scout/pick_board.py — new function alongside cmd_enrich

def append_live_match(state: dict, match: LiveMatch) -> None:
    """Idempotent insert of a Live Scout match record into draft state.

    Mutates state in place. Caller is responsible for save_state().
    Safe to call multiple times for the same match_key — later calls
    overwrite earlier ones (matches finalize as more frames are processed).
    """
    state.setdefault("live_matches", {})[match.match_key] = match.to_dict()
    # Roll up per-team aggregates so the existing pick_board UI sees them
    for team_num in match.red_teams + match.blue_teams:
        team_entry = state["teams"].setdefault(str(team_num), {})
        team_entry.setdefault("live_match_keys", []).append(match.match_key)
        team_entry["live_match_keys"] = sorted(set(team_entry["live_match_keys"]))
        # rolling aggregates updated by recompute_team_aggregates()
    recompute_team_aggregates(state, team_nums=match.red_teams + match.blue_teams)
```

The state file gets a new top-level key `live_matches` keyed by match_key.
Existing pick_board code is untouched except for `recompute_team_aggregates`
which is also new (computes rolling avg score, real_sd, streak from the
`live_matches` dict instead of from TBA).

### `eye/the_eye.py` + `eye/stream_recorder.py` — what we reuse, what we rewrite

**Reusable, lift-and-shift to a shared module:**
- `OverlayOCR.read_breakdown_screen()` — `the_eye.py:245-294`
- `OverlayOCR.is_transition_screen()` — `the_eye.py:296-308`
- `OverlayOCR.detect_match_boundaries()` — `the_eye.py:310-321`
- `select_key_frames()` — `the_eye.py:135-159`
- `synthesize_report()` — `the_eye.py:546-628`
- yt-dlp HLS extraction loop — `stream_recorder.py:87-98`
- `MatchDetector.scan_segment()` — `stream_recorder.py:203`

**Code duplication to fix:** `_read_breakdown` and `_is_transition` exist
in BOTH `the_eye.py:245+` AND `stream_recorder.py:268+`. Phase 1 F1
consolidates both into `eye/overlay_ocr.py` and updates both callers.

**Not reusable, rewrite from scratch:**
- `download_video()` — `the_eye.py:67` — pytubefix-based, replaced by HLS pull
- `cmd_analyze()` — `the_eye.py:708` — orchestrator that doesn't fit cloud worker shape

**No existing canonical match-state class.** We define `LiveMatch` in
`scout/live_match.py` as part of F2 — see schema in F2 below.

---

## The dependency graph

```
F1 OCR consolidation ──┐
F2 LiveMatch shape ────┼──> W1 discovery-cron
F3 HLS puller ─────────┤
F4 pick_board append() ┘            │
                                    ▼
                              W2 mode-a-worker ──┐
                                    │            │
                                    ▼            │
                              W3 mode-b-worker   │
                                    │            │
                                    ▼            │
                              W4 mode-c-anomaly  │
                              W5 mode-c-event-end│
                                    │            │
                                    ▼            │
                              W6 backfill        │
                                    │            │
                                    ▼            │
            I1 Azure deploy ◀───────┘            │
            I2 Local dev rig ◀──────────────────-┘
            I3 Test fixtures ◀──────────────────-┘
            D1 Discord push ◀── (deferred until Gate 4)
```

T2 vision and T3 synthesis are **Phase 2** — see the bottom of this
doc. They depend on Phase 1 having `LiveMatch` records flowing through
the pipeline first.

F1-F4 are the foundation and have no dependencies on each other — they
can be done in parallel by different humans. After F4 is in, W1 unlocks.
W1 is a small warmup. W2 is the bulk of the work. Everything from W3
down is "mostly free" because it reuses W2's processing pipeline.

---

## Gate 0 — Foundation (no cloud yet)

**Goal:** refactor existing code so Live Scout has clean primitives to
build on. Nothing runs in cloud. The eye/ rewrite is a valuable PR on
its own even if Phase 1 stops here.

| Item | Description | Effort | Acceptance |
|---|---|---|---|
| **F1** | Move `OverlayOCR` to `eye/overlay_ocr.py`, swap easyocr → PaddleOCR (per SUBSYSTEM_LEVERAGE_AUDIT.md), update both `the_eye.py` and `stream_recorder.py` to import from the new module | 4 h | `pytest eye/tests/test_overlay_ocr.py` passes against cached frames in `eye/.cache/frames/`; both old callers still work |
| **F2** | Define `scout/live_match.py` with `LiveMatch` dataclass + `to_dict()` / `from_dict()` / TBA-key validators | 2 h | Round-trip JSON serialization test passes; rejects malformed match_keys |
| **F3** | Extract HLS pull into `eye/hls_pull.py` with one function: `pull_hls_segment(youtube_url, duration_sec) -> Path` returning a temp mp4 file | 2 h | Pulls 60 sec from a known-good FIT VOD; cleans up temp file on context exit |
| **F4** | Add `append_live_match()` + `recompute_team_aggregates()` to `pick_board.py`; extend the state schema with `live_matches` top-level key | 3 h | Unit test: insert 3 fake matches, verify per-team rollups update correctly; existing `cmd_setup` and `cmd_enrich` unchanged |

**Gate 0 effort: ~11 h**

`LiveMatch` schema (locked in F2):

```python
@dataclass
class LiveMatch:
    event_key: str          # "2026txbel"
    match_key: str          # "2026txbel_qm32"
    match_num: int          # 32
    comp_level: str         # "qm" | "qf" | "sf" | "f"
    red_teams: list[int]    # [2950, 1234, 5678]
    blue_teams: list[int]
    red_score: int | None   # None until match ends
    blue_score: int | None
    red_breakdown: dict     # OCR breakdown subscores
    blue_breakdown: dict
    winning_alliance: str | None  # "red" | "blue" | "tie" | None
    timer_state: str        # "auto" | "teleop" | "endgame" | "post"
    processed_at: int       # unix epoch
    source_video_id: str    # YouTube video ID
    source_tier: str        # "live" | "vod" | "backfill"
    confidence: float       # 0..1, OCR cross-frame consensus score
```

---

## Gate 1 — Mode A end-to-end, locally

**Goal:** Mode A runs from your laptop against a real (or recorded) FIT
event and writes one fully-processed match into pick_board state. This
is the first time anyone sees Live Scout actually do its job.

| Item | Description | Effort | Acceptance |
|---|---|---|---|
| **W1** | `workers/discovery.py`: poll YouTube Data API v3 for active streams on `@FIRSTinTexas`; cross-reference TBA for active FIT events; identify "our event" by matching against `frc2950`; write dispatcher state to a local JSON file (Azure Storage Table later) | 3 h | `python -m workers.discovery --dry-run` outputs `{our_event: "2026txbel", active_streams: [...]}` |
| **W2** | `workers/mode_a.py`: read dispatcher state, fetch upcoming opponent set from TBA, pull 5 min HLS, run OCR pipeline, build `LiveMatch`, call `append_live_match()`, save_state | 8 h | `python -m workers.mode_a --event 2026txbel --debug` against a recorded VOD writes one valid `LiveMatch` into a test pick_board state file; team set matches TBA truth set; scores match TBA truth set |
| **I3** | `tests/live_scout/`: pytest fixtures using cached frames in `eye/.cache/frames/`; integration test that runs Mode A end-to-end against the cached frames and asserts the output `LiveMatch` matches a hand-validated golden record | 4 h | `pytest tests/live_scout/` green, takes < 30 sec |

**Gate 1 effort: ~15 h**

**Gate 1 demo:** point Mode A at a recorded FIT VOD on a Saturday
afternoon, watch it produce the same per-match data the stand scouts
will produce in person. Verify it's correct before trusting it live.

---

## Gate 2 — Mode A in Azure

**Goal:** the same Mode A runs on cron in Azure Container Apps Jobs,
no laptop required. End of Gate 2, the system is doing real work for
us at our next FIT event.

| Item | Description | Effort | Acceptance |
|---|---|---|---|
| **I1** | Dockerfile (multi-stage, PaddleOCR baked in), Bicep template for Container Apps Environment + Jobs + Storage Table + Storage Blob, GitHub Action to build/push image, secrets via Container Apps secrets (TBA key, Anthropic key) | 5 h | `az containerapp job execution start --name mode-a-worker` succeeds; logs visible in Azure portal |
| **I2** | Local dev rig: `scripts/run_worker_local.sh` that runs any worker with the same env as Azure but pointed at local state files. Used for debugging without paying Azure round-trip cost | 1 h | `scripts/run_worker_local.sh mode_a --event 2026txbel` works without an Azure connection |
| **migration** | Replace local file dispatcher state with Azure Storage Table writes; replace local pick_board state file with a state shim that can read/write to either local or Azure Blob | 2 h | Same Mode A code path runs locally and in Azure; pick_board reads same shape from either |

**Gate 2 effort: ~8 h**

**Gate 2 demo:** the cron fires every minute during a real FIT event
weekend; pick_board state on disk gets fresh `live_matches` entries
within 5 min of each broadcast match. We're now scouting an event with
zero human input.

---

## Gate 3 — Pick board fully fed

**Goal:** end of qual day, pick_board has *every* match at our event,
not just the ones involving upcoming opponents. Alliance selection has
the complete picture.

| Item | Description | Effort | Acceptance |
|---|---|---|---|
| **W3** | `workers/mode_b.py`: at end of qual day cron, walk every match at our event from TBA, skip ones already in `live_matches`, process the rest from VOD (not live) using Mode A's processing pipeline. Idempotent | 3 h | After Mode B runs, `len(state["live_matches"])` equals total qual matches at our event for that day |

**Gate 3 effort: ~3 h** (mostly free — reuses W2 pipeline)

**Gate 3 demo:** Saturday morning before alliance selection, open
pick_board, see every team has a full match history with cycle counts
and breakdown subscores. No gaps.

---

## Gate 4 — Other-event awareness + Discord

**Goal:** we get notified when something interesting happens at an event
we're not at, plus an end-of-event digest for every other FIT event.

| Item | Description | Effort | Acceptance |
|---|---|---|---|
| **W4** | `workers/mode_c_anomaly.py`: every 5 min, poll TBA for newly-completed matches at non-our FIT events, run anomaly detector (stats only, no OCR), enqueue any anomaly hits for full processing | 4 h | Replay against a known anomalous historical match (e.g., a 2025 FIT event with a record score) — anomaly fires correctly |
| **W5** | `workers/mode_c_event_end.py`: triggered by event status flip in TBA, pulls VOD via yt-dlp, runs T1 + T2 over every match in the event, writes digest blob | 4 h | Replay against a completed 2025 FIT event — digest blob contains correct top-3 ranking, sample alliance briefs |
| **D1** | `workers/discord_push.py`: thin wrapper over Discord webhook API; called by Mode A (heads-up alerts), Mode C anomaly, and Mode C event-end; rate-limited; idempotent (doesn't double-post on cron retries) | 3 h | Test webhook fires for each of the 3 message types; idempotency check (run twice, only one message lands) |

**Gate 4 effort: ~11 h**

**Gate 4 demo:** during a real Saturday with 3+ FIT events live, our
Discord channel gets:
- "Heads up — your Q47 partner team 1234 just lost their elevator at our event"
- "🚨 Team 5678 just scored 200 at the Houston event (record)"
- "📊 Houston event complete — top 3: 1234, 5678, 9012"

---

## Gate 5 — Backfill the corpus

**Goal:** the moat. Run the backfill worker over 2023+ FIT VODs, build
the multi-season Texas FRC corpus that nothing else in the world has.

| Item | Description | Effort | Acceptance |
|---|---|---|---|
| **W6** | `workers/backfill.py`: iterates `@FIRSTinTexas` VOD list (or `@texasFRC` per-match cuts) for a given season, runs the same Mode B pipeline, writes to a separate `backfill/` blob namespace so it doesn't pollute live state | 3 h | Test run against one historical FIT event (e.g., 2025 FIT District Dripping Springs) — output matches Mode B against the same VOD |

**Gate 5 effort: ~3 h** (mostly free — reuses W3 pipeline)

**Gate 5 demo:** kick off the backfill on a Friday evening. Saturday
morning, 4 seasons of Texas FIT data are sitting in blob storage,
ready for the prediction engine to ingest.

---

## Total Phase 1 effort

| Gate | Effort | Cumulative | Shippable as |
|---|---|---|---|
| Gate 0 — Foundation | 11 h | 11 h | OCR refactor PR (independent value) |
| Gate 1 — Mode A locally | 15 h | 26 h | Local scouting from a laptop |
| Gate 2 — Azure | 8 h | 34 h | Cloud-hosted Mode A |
| Gate 3 — Mode B fill | 3 h | 37 h | Complete pick_board feed |
| Gate 4 — Mode C + Discord | 11 h | 48 h | Cross-event awareness |
| Gate 5 — Backfill | 3 h | 51 h | Multi-season corpus |

**Phase 1 total: ~51 h.** T3 synthesis (was Gate 5 in an earlier draft,
~4 h) is now Phase 2 along with T2 vision. Phase 1 is **score truth +
backfill only** — the cleanest possible MVP that demonstrates value at
a real FIT event without committing to vision model integration or the
Opus advisor at the same time.

The architecture doc's Phase 1 effort table sums to ~33 h because it
counts only the worker code itself; this doc's ~51 h is honest about
also including the F1-F4 foundation refactor, local dev rig, test
fixtures, and the local→Azure state shim.

Spread across 3-4 weekends if focused. Spread across the 2026
offseason if not under FIT competition pressure.

**Critical path**: F1 → F2 → F4 → W2 → I1. Everything else is
parallelizable or "mostly free."

---

## Phase 2 — Vision + Synthesis + TBA video uploader

Phase 2 layers the heavier capabilities onto the Phase 1 foundation as
a single offseason capability push. Three pieces, ~22 h total.

| Piece | What | Effort | Cron | Latency |
|---|---|---|---|---|
| **T2 Vision** | Roboflow Universe FRC YOLO model integration; cycle counts, climb success, defense events. New `vision-worker` Container Apps Job. Reads matches with T1 OCR complete but T2 not yet run; pulls cached frames from Storage Blob; updates `LiveMatch` records with vision breakdown | 10 h | every 10 min | 5 min post-match |
| **T3 Synthesis** | `synthesis-worker` Container Apps Job. Reads all `live_matches` for our event, calls Opus with the same prompt structure as the existing prediction engine, pushes brief to Discord war-room channel + updates `pick_board` with end-of-day rankings | 6 h | 11 PM CT on qual days | end of qual day |
| **TBA video uploader** | Cut + upload per-match videos to TBA, faster than `@texasFRC`. Match boundary state machine (2 h) + timestamp validation against TBA schedule (1 h) + TBA write API client + retries (2 h) + tests against a real cached event (1 h) | 6 h | per-match (post-VOD) | next morning |
| **Total Phase 2** | | **~22 h** | | |

Full architecture detail in
[LIVE_SCOUT_ARCHITECTURE.md](LIVE_SCOUT_ARCHITECTURE.md) §"Phase 2".

### Why these three were grouped into Phase 2

- **T3 needs T2.** A "strategic synthesis" that knows scores but
  doesn't know cycle counts is half-blind. We don't ship the Opus
  advisor until it can read cycle data, so T3 follows T2.
- **T2 + T3 are an offseason job.** Vision model selection and prompt
  iteration both want a quiet week to bake against backfill data, not
  a Saturday morning before a real alliance selection.
- **TBA uploader piggybacks on the same offseason build window.**
  Same build cycle, same Azure runtime, same test methodology
  (replay against cached events). Bundling them avoids two
  separate "deploy + verify" rounds.

### Phase 2 build starts when **all four** of these are true

1. **Phase 1 Gate 5 is shipped and stable** — at least 1 full FIT
   event has been scouted live by Phase 1 with no major errors. We
   have a known-good baseline before adding new responsibilities.
2. **The 2026 FIT season is over** — Houston worlds wraps (typically
   late April / early May). No live scouting demands competing for
   build time.
3. **`@texasFRC` is still operating** — verify before starting Phase 2
   that the existing competitor hasn't shut down. If they HAVE shut
   down, the TBA uploader piece of Phase 2 jumps the queue mid-2026
   because TBA losing its video uploader is a community problem
   worth solving fast.
4. **TBA Trusted User application has been submitted** — apply ~30
   days before targeted Phase 2 start so approval clears the queue.
   Application is free; Safiq submits. Required only for the TBA
   uploader piece — T2 vision and T3 synthesis don't need it.

**Target Phase 2 start: June 2026** (post-Houston, pre-2027 kickoff).
Build vision + synthesis + uploader against cached events from
Phase 1's backfill so we can iterate model choice, advisor prompts,
and the boundary state machine offline. Validated against ≥3
historical FIT events before any 2027 production use.

**Reactive trigger:** if `@texasFRC` pauses for >7 days during a FIT
event we're at, the TBA video uploader piece of Phase 2 jumps to
immediate priority and ships in parallel with Phase 1's later gates.
T2 vision and T3 synthesis stay in offseason regardless.

---

## Out of scope for Phase 1 (call them out so we don't drift)

These are tempting to fold in but explicitly NOT Phase 1:

**Deferred to Phase 2** (offseason build, see Phase 2 section above):
- **Roboflow Universe FRC YOLO model integration (T2 vision).** Mode A
  and Mode B use OCR only in Phase 1. Vision is stubbed in W2 with a
  hook so Phase 2 can drop in without re-architecture. Reasoning: OCR
  alone gives us 70% of the strategic value at 5% of the integration
  risk. Add vision after we trust the OCR layer.
- **T3 strategic synthesis (Opus advisor brief).** Depends on T2
  having cycle data. Ships in the same Phase 2 push as vision.
- **TBA video uploader.** Bundled into the Phase 2 push for the same
  offseason build cycle.

**Deferred indefinitely / lives elsewhere:**
- **moondream2 belt-and-suspenders qualitative VLM.** A second
  validation layer on top of T2 vision. Can layer in post-Phase-2 if
  we observe T2 false positives that need a sanity check.
- **AdvantageScope log overlay for our own robot.** That's a
  different data path (WPILOG via `tools/post_match_analyzer.py`)
  and lives in a different doc.
- **Whisper coach integration.** Whisper consumes Live Scout data via
  pick_board, but the on-robot Whisper itself is its own arch
  ([ARCH_COACH_AI.md](ARCH_COACH_AI.md)) and ships independently.
- **A web dashboard for live state viewing.** We have pick_board
  (CLI) and Discord (alerts). No third UI surface.
- **Multi-team licensing / open-source release.** We focus on
  scouting Team 2950 first. Sharing this with other FRC teams is a
  post-2026-season decision once the system has proven itself.

---

## References

- [LIVE_SCOUT_ARCHITECTURE.md](LIVE_SCOUT_ARCHITECTURE.md) — what + why
- [SUBSYSTEM_LEVERAGE_AUDIT.md](SUBSYSTEM_LEVERAGE_AUDIT.md) — PaddleOCR validation that F1 is built on
- [ARCH_SCOUTING_SYSTEM.md](ARCH_SCOUTING_SYSTEM.md) — pick_board.py architecture doc
- [ARCH_COACH_AI.md](ARCH_COACH_AI.md) — Whisper, downstream consumer
- [CROSS_SEASON_PATTERNS.md](CROSS_SEASON_PATTERNS.md) — prediction engine that ingests the backfill corpus

---

*Live Scout Phase 1 Build Scope | THE ENGINE | Team 2950 The Devastators | 2026-04-10*
