# THE ENGINE — Subsystem Leverage Audit
# Where we are hand-rolling something a mature open-source project already solves
# Team 2950 — The Devastators
# Authored: 2026-04-10
# ═══════════════════════════════════════════════════════════════════

## Why this doc exists

The Engine has grown to ~14 subsystems and ~40k lines of Python/Java
across mentor + student contributions. Before we burn another season's
worth of hours on subsystems still on the roadmap, we audited every
one against what's already on GitHub. The question for each row:

> *Is the IP here actually The Engine, or are we re-implementing
> something the FRC + open-source community has already shipped?*

If the answer is the latter, we should swap to the upstream project
and spend our hours on the parts that ARE our IP (Prediction Engine,
The Whisper, pick_board scoring, the cross-season pattern brain).

This doc is the source of truth for those swaps. It is paired with
`ENGINE_MASTER_ROADMAP.md` — anything marked **SWAP** here should
deduct hours from the roadmap line items it replaces.

---

## TL;DR savings

| Subsystem | Swap target | Hours saved | Risk | Priority |
|---|---|---|---|---|
| Pit Crew P.3 + P.6 | Mechanical-Advantage/AdvantageScope | ~36 h | Low | **1** |
| The Vault | inventree/InvenTree | ~20 h | Low | **2** |
| Scout TBA + Statbotics clients | tbapy + avgupta456/statbotics | ~8 h | Low | **3** |
| The Eye (CP.6-CP.8) | yt-dlp + PaddleOCR + Roboflow Universe + moondream2 | ~30 h | Medium | **4** |
| The Clock CL.1-CL.3 | GitHub Projects + Discord standup bot | ~30 h | Low | **5** |
| Blueprint B.3-B.6 | hedless/onshape-mcp + FRCDesign.org | ~75 h | Medium | **6** |
| **Total** | | **~199 h** | | |

For context: the entire rev-3 SystemCore + Whisper coprocessor plan
we just locked in is 66.5 h. This audit, fully executed, gives us
back roughly **3× that effort** to spend elsewhere.

---

## 1. Pit Crew P.3 + P.6 → AdvantageScope ⭐ TOP WIN

**What we were going to build (P.3 + P.6 in `ARCH_PIT_SYSTEMS.md`):**
- Custom WPILOG / Hoot replay viewer
- Digital twin debugger with field overlay
- Joystick playback for replicating bug reports
- Mechanism2D + swerve viz
- Timeline scrubber with NT4 live mode

**What already exists:** **Mechanical-Advantage/AdvantageScope**
- All of the above, polished, actively maintained by 6328
- Already ingests AdvantageKit logs (which we already produce)
- 3D field viewer with FRC field models pre-loaded
- Tab-based workflow, CSV export, video sync

**Why swap is safe:**
- We already committed to AdvantageKit in the rev-3 architecture
- AdvantageScope is the canonical viewer for AdvantageKit logs
- Swapping costs nothing — the logs are already in the right format

**What we keep custom:**
- Pit Crew P.5 (FastAPI debug dashboard for Whisper internals) — different job, lives on the Jetson
- Pit Crew P.1 + P.2 (the actual pit checklist + match log workflow)

**Action:**
- Delete P.3 and P.6 from the roadmap
- Add a one-line note: *"Log replay + digital twin handled by AdvantageScope. Document the field model + log paths in `design-intelligence/pit-crew/ADVANTAGESCOPE_SETUP.md`."*
- ~36 h reclaimed

**Status:** Ready to execute. No blockers.

---

## 2. The Vault → InvenTree ⭐ TOP WIN

**What we were going to build (`ARCH_PARTS_INVENTORY.md`):**
- Spreadsheet-backed parts database
- BOM tracking against The Blueprint
- Low-stock alerts
- Supplier links
- Build-season consumable tracking

**What already exists:** **inventree/InvenTree**
- Open-source, self-hostable, Django + Vue
- Python REST API
- Barcode scanning (matters for pit organization)
- BOM management with parametric matching
- Stock locations (matters for our tool chest layout)
- Supplier tracking with WCP / AndyMark / REV / CTRE built-in part import
- Low-stock alerts via email + webhook (Discord-able)

**Why swap is safe:**
- We have ZERO Vault code yet — `vault/` directory is empty
- Self-hosted means no SaaS lock-in or recurring cost
- Python API means The Clock can still pull data programmatically

**What we keep custom:**
- The Engine-specific webhook glue: `vault/inventree_bridge.py` to push low-stock alerts into our Discord build channel
- Roadmap-aware BOM verification (does the Blueprint robot have parts in stock?) — ~4 h of glue code

**Action:**
- Stand up InvenTree in the team Synology / Codespace
- Import existing inventory CSV
- Write the ~4 h glue script for Discord alerts
- ~20 h reclaimed

**Status:** Ready to execute. Need a host to run it on.

---

## 3. Scout client swap ⭐ EASY WIN

**What exists in `scout/`:**
- `tba_client.py` — 244 lines, custom HTTP wrapper around TBA v3 with handrolled JSON cache
- `statbotics_client.py` — 244 lines, same pattern against the Statbotics REST API

**What already exists:**
- **frc1418/tbapy** — canonical TBA client, used by hundreds of FRC tools
- **avgupta456/statbotics** — official Python lib written by the Statbotics maintainer himself

**Why swap is safe:**
- Both libs have stable APIs and active maintenance
- Our 488 lines are mostly cache-management boilerplate, not IP
- pick_board.py and match_strategy.py (the actual scoring brain) consume cache dicts that we can produce from either lib's return values with a thin adapter

**Risk:** Low. The Scout pick_board is tested against 2026txbel — keep that test suite as the regression check during the swap.

**What we keep custom:**
- `scout/pick_board.py` (1387 lines — this IS The Scout's IP)
- `scout/match_strategy.py` (932 lines — same)
- A ~30 line `scout/cache_adapter.py` that wraps both libs to preserve the dict shape pick_board expects

**Action:**
- `pip install statbotics tbapy`
- Write `scout/cache_adapter.py`
- Delete `tba_client.py` + `statbotics_client.py`
- Re-run the 36-test pick_board suite
- ~8 h reclaimed

**Status:** Ready to execute. The 36-test regression suite is the safety net.

---

## 4. The Eye → yt-dlp + Roboflow Universe + moondream2

**What exists in `eye/`:**
- `the_eye.py` (911 lines) — Layer 0: pytubefix + ffmpeg, Layer 1: EasyOCR, Layer 2: Vision LLM (swappable), Layer 3: Opus advisor
- `stream_recorder.py` (618 lines)
- `eye_bridge.py` (602 lines) — already shipped, lives between Eye and pick_board

**Pain points today:**
- pytubefix breaks on every YouTube algo change — we've patched it twice this season
- EasyOCR is heavyweight and CPU-bound; it's also redundant with a vision LLM that can read text natively
- We were going to train a custom YOLO11 model from scratch in CP.6-CP.8

**Swap targets:**

| Layer | Current | Swap | Why |
|---|---|---|---|
| 0 (download) | pytubefix | **yt-dlp** | Gold standard, never broken for long, handles age-gated and live |
| 1a (deterministic OCR) | EasyOCR | **PaddleOCR (PP-OCRv5)** | Validated against real FRC scoreboard frame — see test below |
| 1b (qualitative VLM) | LocalVisionBackend stub | **moondream2** (1.6B on Jetson) | Scene understanding, runs alongside Whisper |
| Vision (object detection) | YOLO stub raising NotImplementedError | **Roboflow Universe FRC models** | Pre-trained models for game pieces, robots, field elements already exist |
| LLM (strategic) | Anthropic SDK | Keep | Frontier model for synthesis; not swap-worthy |

**Belt-and-suspenders OCR strategy:**
- PaddleOCR for **deterministic** field extraction (scores, timer, team numbers, RP) — never hallucinates digits
- moondream2 for **qualitative** scene reads ("which alliance is on offense", "is anyone climbing")
- VLM occasionally hallucinates digits, OCR doesn't — use the right tool for each layer

**Roboflow Universe specifically has:**
- Multiple FRC game piece detectors per season
- Robot bumper detection models
- Field element detectors
- All free, all licensable for our use

**What we keep custom:**
- `eye_bridge.py` (already done — the wiring INTO pick_board is the IP)
- Layer 3 Opus advisor (the strategic interpretation is the IP, not the vision)
- Our prompt set + the cross-season pattern lookups feeding the advisor

### PaddleOCR validation test (2026-04-10)

Tested PaddleOCR 3.4.0 (`PP-OCRv5_server_det` + `en_PP-OCRv5_mobile_rec`) against `eye/.cache/frames/frame_020.jpg` — a real cached FRC qualification match scoreboard from FIT District Dripping Springs.

**17 detections, all match-critical fields captured:**

| Field | PaddleOCR result | Confidence |
|---|---|---|
| All 6 team numbers (4364, 9311, 10032, 2950, 3035, 7752) | exact | 0.96-1.00 |
| RED score `27`, BLUE score `70` | exact | 1.00 |
| RED RP `27 / 100`, BLUE RP `65 / 100` | exact | 0.90-0.93 |
| Match timer `1:09` | exact | 1.00 |
| Auto/teleop phase `4/6` `:14` | exact | 1.00 |
| Alliance labels `RED` / `BLUE` | exact | 1.00 |

**Missed (acceptable losses):**
- "Qualification 32 of 62" header — stylized "Q" decoration; can pull match number from TBA via Scout instead
- "FIT District Dripping Springs Event" footer — known from event context
- Stylized sponsor logos — irrelevant for scouting

**Performance (M-series Mac CPU, no GPU):**
- Cold model load: 25.9 s (one-time, downloads ~45 MB from HuggingFace)
- Warm load: ~3 s
- Inference: **3.8 s per frame**
- Per-match cost (12 key frames in `analyze` mode): ~46 s
- For live `stream_recorder` use, switch to `PP-OCRv5_mobile` det model OR run on Jetson with CUDA

**Test artifact:** `/tmp/paddleocr_test.py` (10 lines, can be promoted into `eye/tests/test_paddleocr_smoke.py` if we want it as a regression check)

**Conclusion:** PaddleOCR is the right swap. EasyOCR comes out, PaddleOCR goes in.

**Action:**
- Swap pytubefix → yt-dlp in `the_eye.py:70` (~1 h)
- Swap easyocr → paddleocr in `the_eye.py:239` and `stream_recorder.py:195` (~3 h, including class rewrite for the new Paddle API which is `predict()` returning page dicts)
- Promote `/tmp/paddleocr_test.py` to `eye/tests/test_paddleocr_smoke.py` (~30 min)
- Survey Roboflow Universe for the best 2026 game piece model, license it (~2 h)
- Stand up moondream2 on the Jetson alongside Whisper (~4 h, fits in CP.6)
- Replace CP.7-CP.8 custom training plan with Roboflow model fine-tune (~4-6 h vs 30 h)
- ~30 h reclaimed across CP.6-CP.8

**Risk:** Low for OCR swap (validated). Medium for Roboflow (need to verify a 2026 game piece model is good enough; if not, we still fall back to custom training but with a proven baseline).

**Status:** PaddleOCR swap validated and ready to execute. yt-dlp swap can happen this week and pays for itself the next time pytubefix breaks.

---

## 5. The Clock CL.1-CL.3 → GitHub Projects + Discord standup bot

**What CL.1-CL.3 was going to build (`ARCH_BUILD_MANAGEMENT.md`):**
- CL.1: Task generator that scans CAD/code commits and proposes follow-ups
- CL.2: Standup bot that pings students for status, posts to Discord
- CL.3: Burn-down tracker tied to the season calendar

**What already exists:**
- **GitHub Projects** (free for public repos, free for our team) — covers issue tracking, kanban, milestone burn-down, automation rules
- **Geekbot / standup-bot OSS** — multiple Discord bots that do async standups; the Geekbot Discord bot is mature and has a free tier
- **GitHub Actions** can post commit summaries to Discord webhooks natively

**What we keep custom:**
- The Engine-specific glue: a ~50 line script that maps GitHub Project items to Roadmap CP line items, so when CP.7 closes, the roadmap updates automatically
- Anything that touches our cross-season pattern brain (none of CL.1-CL.3 actually does)

**Action:**
- Stand up GitHub Projects board mirrored from `ENGINE_MASTER_ROADMAP.md`
- Pick a standup bot, install it in our Discord
- Write the ~50 line roadmap-sync script
- Delete CL.1-CL.3 from the roadmap, replace with "Clock = GitHub Projects + standup bot + 50 LOC glue"
- ~30 h reclaimed

**Status:** Ready to execute. Lowest-risk swap on the list.

---

## 6. Blueprint B.3-B.6 → hedless/onshape-mcp + FRCDesign.org

**Status:** Already documented in the prior conversation turn. Full plan deferred until user picks the entry path. Re-summarized here for completeness.

**Pain root cause:** `blueprint/assembly_builder.py` builds Onshape assemblies with raw XYZ transform matrices and hard-coded mm offsets:
```python
position_mm=[mx, my, 76.2]              # arbitrary "above frame"
position_mm=[mx + 30, my, 76.2]         # arbitrary 30mm offset
position_mm=[px + i * 50, py, pz + 40]  # arbitrary wheel spacing
```
This is why placement is fragile — every part is pinned to absolute coordinates instead of mate connectors.

**Swap targets:**
- **hedless/onshape-mcp** (49★, has CLAUDE.md, 45 tools including `create_mate` for FASTENED/REVOLUTE/SLIDER/CYLINDRICAL, `MateConnectorBuilder`, Variable Tables, FeatureScript eval, interference checking) — drop-in replacement for our raw API calls
- **FRCDesign.org** (curated catalog of public Onshape reference documents per mechanism class) — fork-and-parametrize source instead of synthesizing geometry from scratch
- **Rhoban/onshape-to-robot** (523★, master-class `assembly.py` with 933+ lines on mate handling, occurrence transforms, DOF detection) — reference implementation for the mate-graph code we'd write

**Strategy shift:**
- Stop generating geometry from primitives
- Start forking proven FRCDesign.org documents and parametrizing via Variable Studios
- Use mate connectors as the placement primitive, not XYZ matrices

**Action plan (deferred — awaiting user signal on entry path):**
1. Manual spike: fork one FRCDesign.org elevator and verify Variable Studios fork works
2. Install hedless/onshape-mcp into the Codespace devcontainer
3. Write `BLUEPRINT_REV2_COPY_PARAMETRIZE.md` documenting the new philosophy
4. Rewrite the first generator (probably elevator since it's the simplest mechanism with a good FRCDesign.org reference)

**Hours saved:** ~75 h on B.3-B.6.

**Status:** Plan ready. Awaiting go signal.

---

## Smaller wins / worth checking

### Antenna scoring — embedding store
- `antenna/scraper.py` (the Discourse client) is fine, leave it
- The relevance scorer is rule-based; could use **chromadb** or **txtai** for semantic ranking
- Better recall on queries like "find Chief Delphi threads about swerve odometry drift"
- ~1 day rewrite, no blocker
- **Defer** until we have a concrete pain query that today's scorer misses

### Engine proxy → BerriAI/litellm
- Our custom proxy is intentionally minimal so this is a wash
- LiteLLM gives free budget tracking, model fallback, OpenAI-compatible endpoints
- Adds a dependency for marginal gain
- **Defer** unless we add a third model provider

### `tools/extract_cycles.py` + `tools/post_match_analyzer.py`
- Both look like log-trawling scripts
- AdvantageScope's tab system + CSV export probably covers them
- **Verify before deleting** — check if either has analysis logic that ISN'T just log filtering

### `tools/snapscript_fuel_detector.py`
- One-off image classifier
- **PhotonVision** has built-in object detection on coprocessors now
- Drop into the Jetson PhotonVision pipeline → SnapScript for free
- Folds into CP.5 (PhotonVision setup on the Jetson)

### `tools/pull_statbotics.py`
- One-liner script
- Replaces itself in the same swap as #3

---

## Already maxed out (no action)

These subsystems are using the right libraries already. Listed so we
don't accidentally re-audit them.

| Subsystem | Why it's maxed |
|---|---|
| **Constructicon** (robot code) | WPILib + AdvantageKit + PathPlanner + Choreo + Phoenix6. Nothing left to swap. |
| **Prediction Engine** | The 18-rule brain IS the IP. CROSS_SEASON_PATTERNS.md is the source of truth. Don't touch. |
| **The Antenna** (ingest pipeline) | Tested, 60-test suite passing. Discourse API is stable. Leave alone unless we re-do scoring. |
| **The Whisper CP.1-CP.12** | Already uses llama.cpp + Whisper.cpp + PhotonVision — that IS the leverage. |
| **The Cockpit** | Elastic / Shuffleboard already cover the dashboard. We just configure layouts. |
| **eye_bridge.py** | Already shipped. The wiring INTO pick_board is custom IP, can't be replaced. |
| **scout/pick_board.py + match_strategy.py** | The scoring algorithm IS our scouting IP. Tested vs 2026txbel. |
| **Engine Advisor** | Just routes between models. Trivial, no swap target. |

---

## Execution order

Priority is "easiest × highest impact first":

1. **Scout client swap** — 8 h saved, low risk, can ship this week. Knock out first as proof the audit pattern works.
2. **Pit Crew P.3 + P.6 → AdvantageScope** — 36 h saved. Just deletion + a setup doc.
3. **Vault → InvenTree** — 20 h saved. Need a host. Stand up in parallel with #2.
4. **Clock CL.1-CL.3** — 30 h saved. GitHub Projects board + bot install.
5. **Eye yt-dlp swap** (Layer 0 only, 1 h) — Pay for itself the next time pytubefix breaks.
6. **Eye full swap (CP.6-CP.8)** — 30 h saved. Folds into the Jetson bring-up window (July-September 2026).
7. **Blueprint rev-2** — 75 h saved. Largest bet, deferred until user picks entry path.

---

## Open questions

1. **InvenTree host** — Synology, Codespace, or rent a $5/mo VPS? Need to decide before #3 can start.
2. **Roboflow Universe licensing** — Free for educational use, but we should confirm the FRC-specific models we want are CC-licensed before betting CP.7 on them.
3. **Are there any P.3/P.6 features AdvantageScope DOESN'T cover** that we actually need? E.g. did we plan anything custom for tracking The Whisper's recommendation cadence vs match state? If yes, that piece stays as a small custom tab in P.5, not a P.3 rebuild.
4. **GitHub Projects vs Linear** — both work for #4. Linear is nicer but costs money for >10 users. GitHub Projects is free and integrates with our commits. Probably GitHub Projects, but worth a 5 min discussion.

---

## References

- [ENGINE_MASTER_ROADMAP.md](ENGINE_MASTER_ROADMAP.md) — Hours and CP line items this audit deducts from
- [ARCH_PIT_SYSTEMS.md](ARCH_PIT_SYSTEMS.md) — Source for P.3 + P.6 (will need rev-2 after AdvantageScope swap)
- [ARCH_PARTS_INVENTORY.md](ARCH_PARTS_INVENTORY.md) — Source for The Vault (will need rev-2 after InvenTree swap)
- [ARCH_BUILD_MANAGEMENT.md](ARCH_BUILD_MANAGEMENT.md) — Source for The Clock CL.1-CL.3 (will need rev-2)
- [ARCH_AI_MATCH_ANALYSIS.md](ARCH_AI_MATCH_ANALYSIS.md) — Source for The Eye (CP.6-CP.8 will need rev-2)
- [ARCH_CAD_PIPELINE.md](ARCH_CAD_PIPELINE.md) — Source for Blueprint B.3-B.6 (rev-2 plan pending)
- [ARCH_SCOUTING_SYSTEM.md](ARCH_SCOUTING_SYSTEM.md) — Source for The Scout (only client swap, no architecture change)

External:
- Mechanical-Advantage/AdvantageScope — github.com/Mechanical-Advantage/AdvantageScope
- inventree/InvenTree — github.com/inventree/InvenTree
- frc1418/tbapy — github.com/frc1418/tbapy
- avgupta456/statbotics — github.com/avgupta456/statbotics
- yt-dlp/yt-dlp — github.com/yt-dlp/yt-dlp
- Roboflow Universe — universe.roboflow.com
- vikhyat/moondream — github.com/vikhyat/moondream
- hedless/onshape-mcp — github.com/hedless/onshape-mcp
- frcdesign/FRCDesign.org — github.com/frcdesign/FRCDesign.org
- Rhoban/onshape-to-robot — github.com/Rhoban/onshape-to-robot

---

*Subsystem Leverage Audit | THE ENGINE | Team 2950 The Devastators | 2026-04-10*
