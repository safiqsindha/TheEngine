# THE ENGINE — Live Scout Architecture
# Cloud-hosted cross-event scouting cluster for FIT (FIRST In Texas)
# Team 2950 — The Devastators
# Authored: 2026-04-10
# ═══════════════════════════════════════════════════════════════════

## Why this doc exists

The Engine has every layer of scouting EXCEPT a continuous cross-event
quantitative feed. We can scout the event we're at via stand scouts +
the_eye + pick_board, but we go blind to the other 11 FIT events
running on the same weekend. By the time TBA catches up Sunday night,
the strategic value is gone and we're just looking at history.

This doc commits the architecture for a cloud-hosted worker that
watches every FIT event live (and every FIT event ever, retroactively),
filters aggressively to what we actually care about, and feeds the
result into pick_board and Discord.

The biggest single insight we landed on while scoping this:

> **Live scout is the quantitative SPINE of strategic intelligence.
> It's necessary but not sufficient. Stand scouts cover the human
> observation layer. The Whisper coach consumes both at game time.
> Don't pretend the cloud can replace humans walking the pit.**

---

## The strategic picture (and where live scout fits in it)

Live scout covers ~70% of the strategic data layer. Here's the honest
audit of what's covered and what's NOT.

### Covered by live scout

| Strategic question | How |
|---|---|
| Match scores across the season for any FIT team | T1 OCR |
| RP earned per alliance | T1 OCR |
| Cycle counts per team per match | T2 vision |
| Climb success rate | T2 vision |
| Defense events and effectiveness | T2 vision |
| Auto path tendencies | T2 vision (key frames) |
| Cross-event normalized strength rankings | T3 synthesis |
| Trend lines (improving / regressing teams) | T1 over time |
| Strategic alliance brief end-of-day | T3 Opus advisor |
| Pick board recommendations | feeds pick_board.py |

### NOT covered by live scout (still requires humans)

| Strategic question | Source |
|---|---|
| Pit observations — what they're fixing, what mechanism they're running | Stand scouts walking pits |
| Driver personality — aggressive, panics, tilts under pressure | Human observation |
| Practice match performance | Stand scouts (not streamed) |
| Inter-team picking politics | Mentor diplomacy |
| Off-camera failures (brownouts, jams) | Stand scouts |
| Driver station behavior — queue speed, recovery | Stand scouts |
| Same-day morale / hot streaks / mentor disputes | Pure human read |
| Robot construction details | `design-intelligence/pit-crew/` photos + human notes |

### How the layers fit together

```
                       ┌────────────────────────────────┐
                       │ Opus advisor (T3, end of day)   │
                       └───────────────┬────────────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │                               │                               │
┌──────▼──────────┐         ┌──────────▼─────────┐         ┌──────────▼──────────┐
│ LIVE SCOUT      │         │ STAND SCOUTS       │         │ PREDICTION ENGINE   │
│ (cloud — this   │         │ (humans @ event)   │         │ (cross-season brain)│
│  doc)           │         │                    │         │                     │
│ Quantitative    │         │ Qualitative        │         │ Pattern recognition │
│ ~70% of spine   │         │ ~30% of picture    │         │ Meta layer          │
└──────┬──────────┘         └──────────┬─────────┘         └──────────┬──────────┘
       │                               │                               │
       └───────────────────────────────┼───────────────────────────────┘
                                       │
                             ┌─────────▼─────────┐
                             │ pick_board.py     │
                             └─────────┬─────────┘
                                       │
                             ┌─────────▼─────────┐
                             │ THE WHISPER       │
                             │ (on-robot Jetson) │
                             └───────────────────┘
```

You need ALL of these. The live scout fills one specific gap: the
cross-event quantitative feed that nothing else can fill. Don't ship
this and disband your stand scouts.

---

## The three modes

Live scout does NOT process every frame of every FIT stream. That's
wasteful and we don't need it. It runs three discrete modes, each
with a different scope and trigger.

### Mode A — Opponent prep (the hot path)

**Trigger:** cron every 1 minute during our event hours
**Scope:** matches at our event involving teams in our next 1-3 upcoming matches
**Why:** tactical prep for who we're about to play

Algorithm:
```
upcoming_opponents = teams_in(our_next_3_matches) - {2950}
process_queue = matches_at_our_event_recent
                  .involving(upcoming_opponents)
                  .not_already_processed()

for match in process_queue:
    extract_state(match)  # T1 OCR + T2 vision
    push_to_pick_board(match)
    push_discord_heads_up(match, our_upcoming_team_set)
```

In a typical district event we play ~12 matches over 2 days. With 5
unique teams per upcoming match × 3 upcoming matches = ~12-15 distinct
teams to track. Each has played 0-3 recent matches we care about. Net:
**5-15 matches to fully process per day at our event.**

This is dramatically less than "every frame of every Austin match."

### Mode B — Pick board fill (the safety net)

**Trigger:** once at end of qualification day at our event
**Scope:** every match at our event we haven't already processed in Mode A
**Why:** Saturday alliance selection needs the complete picture

Just a final batch sweep that catches anything Mode A missed (because
the team wasn't in our upcoming opponents list). Runs against the
auto-VOD, not the live stream, so it's cheap and idempotent.

### Mode C — Other-event watch + digest

**Trigger:** cron every 5 minutes globally + event-end batch
**Scope:** all OTHER FIT events (not the one we're at)
**Why:** we don't care play-by-play, but we want to know if something
crazy happens, and we want the digest when their event ends

Mode C has TWO sub-paths:

**C.1 Anomaly detection (cheap, frequent):**
- Cron every 5 min
- Polls TBA for newly-completed matches at non-our events
- Runs the anomaly stat comparison (no OCR needed — TBA gives us final scores)
- If anomaly fires → trigger full match processing for that one match → push Discord alert

**C.2 Event-end digest (heavy, one-shot per event):**
- Triggered when an event status flips to complete
- Runs T1 + T2 over every match in the event (mostly via the auto-VOD)
- T3 generates a summary brief
- Pushes digest to Discord
- Updates the cross-season pattern brain

### Anomaly definitions (concrete, not vibes)

| Anomaly | Threshold | Why we care |
|---|---|---|
| Final score record | Match score > 95th pct of season-to-date for this game | Someone unlocked something |
| Personal best | Team scores > 120% of their prior personal best this season | Strong improvement signal |
| Top-ranked upset | A team ranked top-8 in TX EPA loses to a team ranked >24 | Vulnerability detected |
| Texas team milestone | Climb success rate change > 20%, or new RP rate jump | Direct competitive intel |
| Match anomaly | E-stop, red card, replay called | Reliability priors update |

Anomaly detection itself uses **zero OCR** — it's pure TBA stat
comparison. OCR only fires when an anomaly triggers and we want the
visual context (which usually we don't even need).

---

## The tiers (T1 + backfill = Phase 1, T2 + T3 = Phase 2)

Once a match is in the process queue (via Mode A or B or C.2), it
runs through tiers in sequence. None of them are sub-second because
the cloud is strategic, not tactical.

| Tier | Latency target | Trigger | Build effort | Phase |
|---|---|---|---|---|
| **T1** Score truth | 5 min (1 min at our event) | Azure cron every 5 min | ~12 h | **Phase 1** |
| **T2** Vision/cycle counting | 5 min post-match | Azure cron every 10 min | ~10 h | **Phase 2** |
| **T3** Strategic synthesis | End of qualification day | Azure cron at 11pm CT | ~6 h | **Phase 2** |
| **Backfill** | Whenever | Manual + one-time bulk | ~3 h (mostly free from T1+T2) | **Phase 1** |
| | | | **Total ~31 h** | |

**Why 5 min is fine for T1+T2:** strategic data at 5-min latency is
strategic. We don't drive the robot from cloud data. Drive team
decisions are tactical — they come from drivers' eyes + the on-robot
Whisper coach reading on-robot scout state. If you're at the Austin
event, a 5-second-fresh Houston score is exactly as useful as a
5-minute-fresh one. None.

The one edge case: between-match opponent intel for our NEXT match.
At our event we run Mode A at 1-min cadence so back-to-back match
prep stays tight.

---

## Cloud architecture (Azure)

Stateless, cron-driven, scale-to-zero. No always-on workers. Each
invocation pulls what it needs, processes, writes state, exits.

```
Azure Container Apps Environment "engine-live-scout"
│
├── discovery-cron (Container Apps Job, every 5 min)
│   ├── YouTube Data API v3: list active streams on @FIRSTinTexas
│   ├── TBA: list active FIT events
│   ├── Identifies which event we're at (matches our team key)
│   └── Updates job dispatcher state in Azure Storage Table
│
├── mode-a-worker (Container Apps Job, every 1 min during our event)
│   ├── Reads our event + upcoming match schedule from TBA
│   ├── Builds the upcoming-opponent team set
│   ├── Pulls last 5 min of HLS from our event's stream via yt-dlp
│   ├── Filters frames to matches involving upcoming opponents
│   ├── Runs T1 OCR (PaddleOCR, score-box ROIs only)
│   ├── Runs T2 vision (VLM key frames) on relevant matches
│   ├── Validates against TBA team set + invariants
│   └── Writes match state → Storage + pushes to pick_board, Discord
│
├── mode-b-worker (Container Apps Job, end of qual day @ our event)
│   ├── Walks every match at our event
│   ├── Skips any already processed by Mode A
│   ├── Same pipeline as Mode A but runs from VOD, not live stream
│   └── Writes final state for pick_board
│
├── mode-c-anomaly-cron (Container Apps Job, every 5 min)
│   ├── Polls TBA for newly-completed matches at non-our FIT events
│   ├── Runs anomaly detector (stats only, zero OCR)
│   ├── On trigger → enqueues full match for processing
│   └── Pushes Discord alert with the anomaly summary
│
├── mode-c-event-end-batch (Container Apps Job, on event-status flip)
│   ├── Triggered when a non-our event completes
│   ├── Pulls VOD via yt-dlp from @FIRSTinTexas
│   ├── Runs T1 + T2 over every match in the event
│   ├── T3 generates digest
│   └── Pushes digest to Discord
│
├── synthesis-worker (Container Apps Job, 11 PM CT @ our event days) [PHASE 2]
│   ├── Reads everything in Storage for our event
│   ├── Runs Opus advisor for alliance brief (depends on T2 cycle data)
│   ├── Pushes brief to Discord war-room channel
│   └── Updates pick_board with end-of-day rankings
│
├── vision-worker (Container Apps Job, every 10 min) [PHASE 2]
│   ├── Reads matches with T1 OCR complete but T2 not yet run
│   ├── Pulls cached frames from Storage Blob
│   ├── Runs Roboflow Universe FRC YOLO model
│   ├── Extracts cycle counts, climb success, defense events
│   └── Updates LiveMatch records with vision breakdown
│
└── backfill-worker (Container Apps Job, manual / one-time)
    ├── Iterates @FIRSTinTexas VOD list (2023-present)
    ├── Same pipeline as event-end batch
    └── Builds the multi-season Texas FRC corpus
```

State stores:
- **Azure Storage Table** for match state cache + dispatcher state
- **Azure Storage Blob** for any debug frame archives (tiny — no full video)
- **Azure Cache for Redis** OPTIONAL — only if pick_board needs sub-second reads. Skip for v1.

Discovery: YouTube Data API v3 `liveBroadcasts.list` against
`@FIRSTinTexas` channel ID. If quota becomes an issue, fall back to
HTML scraping the `/streams` page. Both are free.

---

## Source: YouTube Live + auto-VOD

FIT broadcasts every event on `youtube.com/@FIRSTinTexas/streams`.
This is the single best possible source because:

1. **Single channel discovery** — one channel ID lists every active stream
2. **yt-dlp is rock solid for YouTube live** (much more stable than pytubefix ever was)
3. **Auto-archives to VOD** — every live stream becomes a permanent VOD on the same channel within ~30 sec of stream end. We never need to host video ourselves.
4. **Multiple concurrent streams** from the same channel work natively (one per field at peak Saturdays)
5. **Multi-season retrospective backfill** — every FIT stream from 2023+ is already on YouTube. Two parallel sources: `@FIRSTinTexas` retains full-day livestream auto-VODs, and `@texasFRC` publishes per-match cuts. Either feeds the same `yt-dlp` puller. Backfill is just point-and-shoot over historical URLs.

Latency cost: YouTube Live broadcast delay is **15-30 seconds**.
Our state is therefore live-minus-30s at best. Already accounted for
in the latency budget — strategic, not tactical.

---

## Consumers (only two)

### 1. pick_board live feed

- Mode A pushes incremental match state during the event
- Mode B writes final state at end of quals
- Mode C pushes only when an anomaly triggers a relevant team
- pick_board reads from Azure Storage Table or via REST endpoint

### 2. Discord #engine-alerts channel

- Mode A: "Heads up — your Q47 partner team 1234 just lost their elevator at our event"
- Mode C anomaly: "🚨 Team 5678 just scored 200 at the Houston event (record)"
- Mode C event-end: "📊 Houston event complete — top 3: 1234, 5678, 9012. Full digest: [link]"
- T3 synthesis: "📋 End-of-quals brief: pick recommendations and strategic narrative for tomorrow"

**No "war room browsing channel."** We don't care about other events
play-by-play, only on anomaly or end-of-event.

---

## Cost model

**Assumes Microsoft FIRST sponsorship Azure credits are available
(typical $150/mo for FRC teams). Mentor will apply if not yet active.**

| Line item | Without credits | With credits |
|---|---|---|
| Azure Container Apps compute (consumption) | ~$20-40/season | $0 |
| Azure Storage (Table + Blob) | ~$1/mo | $0 |
| Azure Cache for Redis (OPTIONAL, skip for v1) | ~$16/mo if used | $0 |
| YouTube Data API v3 | $0 (free tier) | $0 |
| Anthropic API (T3 Opus advisor calls) | ~$30/season | ~$30/season |
| Discord webhook bandwidth | $0 | $0 |
| **Total operational** | **~$60/season** | **~$30/season** |

The biggest line item with credits is the Anthropic API for T3
synthesis briefs. Everything else fits inside the credit envelope
trivially.

For comparison: a single Roboflow inference plan is $250/month and
gets you fewer requests than this would do in an hour.

---

## Build effort

**Phase 1 = T1 (score truth) + Backfill.** Vision and synthesis come
later in Phase 2. The full per-tier breakdown is in the table at the
top of §"The tiers" above. The detailed gate-by-gate Phase 1 plan
lives in [LIVE_SCOUT_PHASE1_BUILD.md](LIVE_SCOUT_PHASE1_BUILD.md).

| Component | Effort |
|---|---|
| Discovery cron (YouTube + TBA) | 3 h |
| Mode A worker (filtered cron + match processor) | 8 h |
| Mode B end-of-quals fill | 3 h |
| Mode C anomaly detector | 4 h |
| Mode C event-end batch | 4 h |
| Discord #engine-alerts push | 3 h |
| pick_board live feed integration | 3 h |
| Azure deploy + tests | 5 h |
| **Total Phase 1** | **~33 h** |

Spread across 2-3 weekends if focused.

Backfill worker: ~3 h (mostly free since it shares Mode B + Event-End code).

Note: T2 vision (~10 h) and T3 synthesis (~6 h) are now Phase 2.
Earlier drafts of this doc folded them into Phase 1; the cleaner
split is to ship pure score-truth first and add the heavier vision
+ synthesis layer as a single offseason capability push.

---

## Phase 2: Vision + Synthesis + TBA video uploader

Phase 2 layers the heavier capabilities onto the Phase 1 foundation as
a single offseason capability push. Three pieces:

1. **T2 Vision/cycle counting** — Roboflow Universe FRC YOLO + the
   on-robot vision pipeline running over cached frames. Produces
   cycle counts, climb success, defense events. Adds the ~30% of
   strategic data that OCR alone can't capture.
2. **T3 Strategic synthesis** — the Opus advisor that reads everything
   in state at end of qualification day and writes the alliance
   selection brief. Requires T2 to be working so the brief has
   per-team cycle data, not just scores.
3. **TBA video uploader** — cut + upload per-match videos to TBA,
   faster than `@texasFRC`. Gated on TBA Trusted User approval.

### Phase 2 effort

| Piece | Detail | Effort |
|---|---|---|
| **T2 Vision** | Roboflow Universe FRC YOLO model integration into Mode A/B match processing; cycle counting + climb detection + defense event tagging; runs as a separate cron 10 min cadence after T1 completes | 10 h |
| **T3 Synthesis** | `synthesis-worker` Container Apps Job at 11 PM CT cron; reads all `live_matches` for our event, calls Opus with the same prompt structure as the existing prediction engine, pushes brief to Discord war-room channel + updates `pick_board` with end-of-day rankings | 6 h |
| **TBA video uploader** | Match boundary state machine (2 h), timestamp validation against TBA schedule (1 h), TBA write API client + retries (2 h), tests against a real cached event (1 h) | 6 h |
| **Total Phase 2** | | **~22 h** |

### T2 Vision prerequisites

- Phase 1 shipped (Mode A/B writing `LiveMatch` records reliably)
- Pick a Roboflow Universe FRC model (validate against backfill corpus first)
- GPU-backed Container Apps revision OR Azure Container Instance with a small GPU SKU — vision is the only piece that benefits from GPU; everything else is CPU-bound

### T3 Synthesis prerequisites

- Phase 1 + T2 both shipped (synthesis depends on cycle counts)
- Anthropic API key already provisioned in Phase 1 secrets
- `pick_board` end-of-day rankings function exists (auditing this when we wire Mode A in Phase 1 — see [LIVE_SCOUT_PHASE1_BUILD.md](LIVE_SCOUT_PHASE1_BUILD.md) §F4)

### TBA video uploader prerequisites

- **Mentor applies for TBA Trusted User status** — apply ~30 days before targeted Phase 2 start so approval clears the queue. Free, takes a few days.
- TBA write API key once approved
- Confirm `@texasFRC` is still operating (so we don't duplicate effort needlessly — we want to be FASTER, not the only ones)

### Phase 2 schedule

Defer until Phase 1 is shipped and stable. Target post-2026 season as
an offseason capability build, when there are no live events to scout
and we can iterate vision models + synthesis prompts + boundary
detector against the Phase 1 backfill corpus.

If `@texasFRC` stops operating mid-2026, the TBA video uploader piece
of Phase 2 jumps the queue (vision + synthesis stay in offseason).

---

## Backfill (free side effect of Phase 1)

**Source confirmed (2026-04-10):** every past FIT competition is
already on YouTube — `@texasFRC` holds the per-match archive going
back multiple seasons, and `@FIRSTinTexas` retains the full-day
livestream auto-VODs. Either source feeds the same `yt-dlp` puller.
No video hosting cost on our side, no scraping fragility, no
"will the source still exist" risk. Backfill is unblocked.

Once T1 + T2 are working, **the backfill worker is essentially free
to run**. It uses the exact same code path as Mode B, just pointed at
historical VOD URLs instead of current-event VOD URLs.

What backfill unlocks:

1. **4-season Texas-only FRC corpus** — every FIT event from 2023 to
   present, fully OCR'd, with cycle counts and climb data. Deeper than
   any single team has ever assembled. Can run as a long batch over
   one or two weekends.
2. **Prediction engine training data** — the cross-season pattern
   brain gets a massive in-domain dataset to validate against.
3. **The Whisper training corpus** — match narration, opponent
   tendencies, strategic patterns. All extractable from the backfill.
4. **Cross-event normalization baseline** — same model, same
   preprocessing, same OCR pipeline → all data is comparable across
   events and seasons. No artifacts from different scoreboard
   renderings.

**The backfill worker is the most valuable code in this entire plan
and it doesn't even run live.** Treat the live capability as the
headline feature; treat the backfill as the moat.

---

## Open questions to resolve before build starts

1. ~~**Microsoft FIRST Azure credits**~~ — **RESOLVED 2026-04-10.**
   Safiq is applying for FIRST Azure credits. Worst case, fall back to
   personal billing — the cost ceiling is low enough (~$30/season
   Anthropic API + Azure scale-to-zero) that this isn't a blocker.
2. ~~**TBA Trusted User application**~~ — **DEFERRED 2026-04-10.**
   Not needed for Phase 1 because `@texasFRC` is already cutting and
   uploading per-match videos to TBA. Reopen this question only if/when
   Phase 2 (be faster than `@texasFRC`) becomes a priority.
3. **pick_board live feed shape** — does pick_board.py read from a
   REST endpoint, a file, or a database? **Audit deferred until we
   start Mode A** — confirm before that worker ships so the integration
   doesn't surprise us, but it does not block design-doc sign-off.
4. ~~**Discord #engine-alerts channel**~~ — **DEFERRED 2026-04-10.**
   Hold the channel + alert push layer until Phase 1 is fully built.
   No reason to create the channel before there's anything to send to
   it; avoids student confusion about a dead alerts channel.
5. ~~**Backfill scope**~~ — **RESOLVED 2026-04-10.** Go straight to
   2023+. Source is already on YouTube (`@texasFRC` per-match archive
   + `@FIRSTinTexas` full-day livestream VODs), so there is no
   acquisition cost and no risk of the source vanishing. Run the
   backfill worker over a weekend per season. Earliest practical
   season is 2023 because that's when the current scoreboard
   rendering stabilized; older seasons would need their own ROI
   tuning and aren't worth the engineering for the prediction-engine
   use case.

---

## What this is NOT

To prevent scope creep, here's what live scout explicitly does NOT do:

- **Doesn't replace stand scouts.** Pit observations, driver
  personality, practice matches, off-camera failures — all still
  human-only.
- **Doesn't drive robot decisions in real-time.** That's drivers + the
  on-robot Whisper. The cloud feed has 30+ sec broadcast delay
  baseline; can't be tactical.
- **Doesn't extract our own robot's performance metrics.** That's
  AdvantageKit logs + `tools/post_match_analyzer.py` reading WPILOG.
  Different data source.
- **Doesn't do video hosting.** YouTube hosts the video. We just
  process it.
- **Doesn't generate match video uploads to TBA in Phase 1.** That's
  Phase 2.
- **Doesn't try to be a war room dashboard.** We have a single Discord
  alerts channel; we don't need a 12-tile monitoring grid we'll never
  look at.

---

## References

- [SUBSYSTEM_LEVERAGE_AUDIT.md](SUBSYSTEM_LEVERAGE_AUDIT.md) — §4 The Eye section: PaddleOCR validation that this whole architecture rides on
- [ARCH_AI_MATCH_ANALYSIS.md](ARCH_AI_MATCH_ANALYSIS.md) — The Eye base architecture this extends
- [ARCH_SCOUTING_SYSTEM.md](ARCH_SCOUTING_SYSTEM.md) — pick_board.py, the consumer
- [ARCH_COACH_AI.md](ARCH_COACH_AI.md) — The Whisper, downstream consumer at game time
- [CROSS_SEASON_PATTERNS.md](CROSS_SEASON_PATTERNS.md) — Prediction engine brain that lives off this data
- [ENGINE_MASTER_ROADMAP.md](ENGINE_MASTER_ROADMAP.md) — Add Live Scout as a new tier 4 capability with the build effort above

External:
- [@FIRSTinTexas YouTube channel](https://www.youtube.com/@FIRSTinTexas/streams) — primary source
- [@texasFRC YouTube](https://www.youtube.com/@texasFRC/videos) — existing TBA video uploader (Phase 2 competitor)
- [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — OCR engine (validated 2026-04-10)
- [TBA Read API v3](https://www.thebluealliance.com/apidocs/v3) — schedule + final score truth
- [TBA Write API + Trusted User docs](https://www.thebluealliance.com/add-data) — Phase 2 dependency
- [Azure Container Apps Jobs](https://learn.microsoft.com/azure/container-apps/jobs) — runtime primitive

---

*Live Scout Architecture | THE ENGINE | Team 2950 The Devastators | 2026-04-10*
