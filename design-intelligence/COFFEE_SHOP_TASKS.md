# Coffee Shop Session — 3-Hour Vision Rewrite Execution

**Status:** execution plan, 2026-04-11. Scoped for a single 3-hour coffee-shop block on the MacBook Pro. Companion to `VISION_PLAN_EVAL.md`.

**Rules:**
- Total wall-clock budget: **180 minutes** from the moment the first keystroke lands.
- Hard cut at 180 minutes regardless of state. Partial work is fine — commit what's done, leave a stub PR for the rest.
- No network downloads larger than 500 MB. No training runs longer than 5 minutes. Everything that can be a fake/stub during this session IS a fake/stub.
- Ordered highest-leverage first. If we run long, drop from the bottom.
- Tests pass at the end of every phase before moving on. A red suite at hand-off is worse than less work shipped.

---

## Phase 0 — Setup (5 min, 0:00 → 0:05)

- [ ] `git pull --ff-only` on `main`
- [ ] `python3 -m pytest tests/live_scout/ -q` — confirm baseline is still **456 passed, 2 skipped**
- [ ] Open `design-intelligence/VISION_PLAN_EVAL.md` in a side pane for reference
- [ ] Start a fresh git branch? No — work on `main`. Commit in small chunks.

**Exit criteria:** baseline green, branch clean, docs open.

---

## Phase 1 — YOLO-World prefix handler + tests (45 min, 0:05 → 0:50)

**Why first:** highest-leverage single piece of code in the rewrite. Turns the pluggable registry into something that actually runs zero-shot detection the instant a real `ultralytics` install lands. Also the cheapest and most testable of the four rewrite phases — pure code, no network, no training, hermetic tests.

### Step 1 — module (20 min)

Create `eye/vision_models/__init__.py` (empty, marks the package).

Create `eye/vision_models/yolo_world.py`:
- `_load_yolo_world(model_name: str) -> VisionModel` — parses `"yolo-world:<comma-separated-prompts>"`, lazy-imports `ultralytics.YOLOWorld`, constructs and returns a `_YoloWorldAdapter`.
- `_YoloWorldAdapter` class — `.infer(frame_path) -> list[VisionEvent]`. Translates YOLO-World detection output into `VisionEvent` records. Per-prompt → event_type mapping is env-driven (`YOLO_WORLD_EVENT_TYPE_MAP`, JSON string, default `{"robot": "defense"}` as a placeholder until heuristic layer consumes raw detections).
- `register_model_prefix("yolo-world:", _load_yolo_world)` at module bottom.
- **Lazy-import `ultralytics`** so the module imports without the SDK installed. Tests monkeypatch the import path.

**Key design decision to lock in now:** YOLO-World produces raw robot/piece detections, not `VisionEvent`s with `event_type="cycle"` etc. For Phase 1 we emit a single `event_type="defense"` as a placeholder and rely on the caller (next rewrite phase, not this session) to wire the real pipeline through `eye/vision_heuristics.py`. The adapter's ONLY job is: "text prompts in, VisionEvents out." Semantic interpretation is downstream.

### Step 2 — registry hookup (5 min)

Import `eye.vision_models.yolo_world` from `eye/vision_yolo.py` at the bottom of the file (after the registry definitions, guarded by a try/except so a missing submodule doesn't break imports). This ensures the prefix handler registers at import time whenever anything touches `vision_yolo`.

### Step 3 — tests (15 min)

New file `tests/live_scout/test_vision_models_yolo_world.py`:
- `test_yolo_world_prefix_parses_prompts` — `MODEL_NAME="yolo-world:robot,orange ball"` resolves via the registry with prompts `["robot", "orange ball"]`.
- `test_yolo_world_adapter_emits_vision_events` — monkeypatch a fake `YOLOWorld` class that returns scripted detections, verify the adapter produces matching `VisionEvent` records.
- `test_yolo_world_replaces_existing_prefix_registration` — idempotent re-registration sanity check.
- `test_yolo_world_handles_empty_prompts_gracefully` — `"yolo-world:"` raises a clear ValueError rather than exploding.

### Step 4 — run suite (5 min)

- [ ] `python3 -m pytest tests/live_scout/test_vision_models_yolo_world.py tests/live_scout/test_vision_yolo.py -q`
- [ ] Expected: all green. If not, fix before moving on.

**Exit criteria:** registry resolves `yolo-world:` prefix, 4 new tests green, full `test_vision_yolo.py` suite still green, nothing committed yet (commit at the next checkpoint).

---

## Phase 2 — `tools/harvest_vision/` scaffolding + Roboflow source (60 min, 0:50 → 1:50)

**Why second:** delivers the "harvest first" half of the rewrite in a form we can iterate on later. Complete Roboflow pull today; HuggingFace + GitHub + Chief Delphi scrapers deferred to a later session. The Roboflow source alone gives us enough candidate models to ensemble.

### Step 1 — package layout (10 min)

```
tools/
  __init__.py                  # (may already exist; noop if so)
  harvest_vision/
    __init__.py
    __main__.py                # makes `python -m tools.harvest_vision` work
    cli.py                     # argparse CLI
    manifest.py                # harvest manifest dataclass + JSON persist
    sources/
      __init__.py
      base.py                  # abstract VisionSource Protocol
      roboflow.py              # Roboflow Universe API client (THIS SESSION)
      # huggingface.py         # NEXT SESSION (stub file with TODO)
      # github.py              # NEXT SESSION (stub file with TODO)
      # chiefdelphi.py         # NEXT SESSION (stub file with TODO)
```

### Step 2 — manifest schema (10 min)

`manifest.py`:
```python
@dataclass
class HarvestedModel:
    source: str                 # "roboflow" | "huggingface" | ...
    source_id: str              # "workspace/project/version"
    target_class: str           # "robot" | "game_piece" | "apriltag"
    license: str | None         # SPDX id or free-text
    url: str
    weights_path: Path | None   # None until downloaded
    sha256: str | None          # filled after download
    pulled_at: int              # unix
```
`HarvestManifest` wraps `list[HarvestedModel]` with JSON `to_dict` / `from_dict` / `save` / `load`. Written to `tools/harvest_vision/.cache/manifest.json`.

### Step 3 — Roboflow source (25 min)

`sources/base.py`:
```python
class VisionSource(Protocol):
    name: str
    def search(self, *, target: str, limit: int) -> list[HarvestedModel]: ...
    def download(self, model: HarvestedModel, dest_dir: Path) -> HarvestedModel: ...
```

`sources/roboflow.py`:
- `RoboflowSource` class implementing `VisionSource`
- `search(target, limit)` — queries Roboflow Universe for models matching `f"frc {target}"`. Lazy-imports `requests`. Returns `HarvestedModel` stubs with `weights_path=None`.
- `download(model, dest_dir)` — stubbed with a clear `NotImplementedError("need ROBOFLOW_API_KEY to pull weights, and license must be OSS")`. We don't actually pull during the coffee-shop session — Roboflow requires API key + license audit + non-trivial download volume. Shipping the search half is enough to validate the design.
- Built-in fallback: if `ROBOFLOW_API_KEY` is not set, `search()` returns a **baked-in** list of 3 known FRC models (the ones already identified in `V0a_MODEL_SELECTION.md`) so the tool is still testable offline.

### Step 4 — CLI entrypoint (10 min)

`cli.py`:
```bash
python -m tools.harvest_vision search --target robot --source roboflow
python -m tools.harvest_vision list   # dump the manifest
```

`search` prints a table of candidate models + their licenses, appends to the manifest, does NOT download. This makes the coffee-shop deliverable: "a working search command that tells us what we'd pull."

### Step 5 — tests (5 min)

`tests/tools/test_harvest_roboflow.py`:
- `test_roboflow_search_offline_fallback` — without `ROBOFLOW_API_KEY`, search returns the baked-in list of 3 models.
- `test_manifest_roundtrip` — `HarvestManifest` serializes to JSON and back identically.

**Exit criteria:** `python -m tools.harvest_vision search --target robot` prints 3 candidate models with licenses, manifest persists, 2 new tests green.

---

## Phase 3 — Commit checkpoint (10 min, 1:50 → 2:00)

- [ ] `python3 -m pytest tests/ -q` — full suite green
- [ ] `git status` — review changed/new files
- [ ] Commit 1: `feat(vision): add yolo-world prefix handler with fake-YOLOWorld tests`
- [ ] Commit 2: `feat(tools): add harvest_vision scaffolding + Roboflow search source`
- [ ] Push to `origin/main`

**Exit criteria:** two clean commits on `main`, remote is in sync, full suite green.

---

## Phase 4 — Update `VISION_2027_TRAINING_PLAN.md` + create `PURCHASE_LIST.md` (50 min, 2:00 → 2:50)

**Why fourth:** paper changes with no test failures, safest slot for the back half of the session. Docs-only so context switches are cheap.

### Step 1 — `VISION_2027_TRAINING_PLAN.md` edits (30 min)

- [ ] Add a banner at the top: `Superseded in part by VISION_PLAN_EVAL.md. The harvest-first rewrite is canonical; Phase 1 below is archived.`
- [ ] Replace the "Phase 1 — Summer 2026: Build the robot detector" section with a `## Phase 1 (archived)` + `## Phase 1 (current) — Harvest-first, this week` pair. The archived version stays for context.
- [ ] New Phase 1 (current) points at `tools/harvest_vision/` and the YOLO-World prefix handler, not at the MLX auto-label pipeline.
- [ ] Milestone table: compress the 2026-06-01 → 2026-07-15 range into 2026-04-14 → 2026-04-21 (this week + next).
- [ ] MacBook Pro called out explicitly as the dev box through competition.

### Step 2 — `PURCHASE_LIST.md` (20 min)

New file. Captures hardware + services we've been tracking for post-season purchase:

```markdown
# The Engine — Post-Season Purchase List

Hardware, services, and tooling we should buy / subscribe to AFTER the 2026 season ends, not during. In-season money is budgeted for competition logistics, not R&D infrastructure.

## Mac Mini — local ML + LLM box
- M4 Mac Mini 16 GB, $599
- Use cases: ...

## Other entries as they come up
```

List at least: Mac Mini, possibly a Roboflow hobbyist subscription (for API rate limits if we end up harvesting at scale), YOLO-World fine-tune compute credits (if we move training off the MacBook Pro), TBA Trusted production keys once approved.

Link from `design-intelligence/README.md` if that file exists; otherwise just drop it alongside the other docs.

**Exit criteria:** both docs committed and pushed.

---

## Phase 5 — Buffer + final polish (30 min, 2:50 → 3:20)

**Built-in overrun budget.** If Phase 1-4 took the full 2:50 (likely), this is where the wheels don't come off.

Use this slot for any of:
- Fixing a test that went red between phases
- Writing the second commit message more carefully
- One more pass on the eval doc for typos
- Reading through the committed diff before push
- Running `python3 -m pytest tests/ -q` one last time

If everything above is green and there's real spare time: start sketching `tools/harvest_vision/sources/huggingface.py` as a stub with TODO comments, to make the next session trivial to pick up.

**Hard cut at 3:00.** Close the laptop. Do not commit anything between 2:50 and 3:00 that hasn't been tested.

---

## What we explicitly do NOT do in this session

These are tempting but out-of-scope:

- **Actually downloading Roboflow model weights.** Requires API key, license audit, network time. Next session.
- **YOLO-World accuracy evaluation against cached VODs.** Requires YOLO-World to actually be installed and cached VODs to be in a known state. Next session.
- **Writing `scripts/train_vision_kickoff.sh`.** Phase 3 of the rewrite, ~2 hours, doesn't fit.
- **Fine-tuning ANY model.** Zero training runs in this session.
- **Drawing a zone map.** Needs a real VOD + a UI to click on. Not happening at a coffee shop.
- **Pulling Chief Delphi datasets.** Requires HTML scraping + manual license checks. Next session.
- **Composite vision model wiring.** That's the Phase 4 of the rewrite, needs the harvest tool and YOLO-World both working first.

---

## Deliverables checklist (what "done" looks like)

By 3:00 we should have, on `origin/main`:

- [ ] `eye/vision_models/__init__.py` — new package
- [ ] `eye/vision_models/yolo_world.py` — YOLO-World adapter, registered at import
- [ ] `tests/live_scout/test_vision_models_yolo_world.py` — 4 tests green
- [ ] `tools/harvest_vision/` — scaffolding, manifest, Roboflow source (search only)
- [ ] `tools/harvest_vision/cli.py` — working `search` command
- [ ] `tests/tools/test_harvest_roboflow.py` — 2 tests green
- [ ] `design-intelligence/VISION_2027_TRAINING_PLAN.md` — updated with harvest-first Phase 1
- [ ] `design-intelligence/PURCHASE_LIST.md` — new, Mac Mini entry present
- [ ] Full test suite: **462 passed, 2 skipped** (+6 from today's baseline of 456)
- [ ] Two (or three) atomic commits, pushed to `main`

If any of these are missing at 3:00, they roll into the next session's plan. **No heroics.**

---

## Time budget summary

| Phase | Activity | Budget | Cumulative |
|---|---|---|---|
| 0 | Setup | 5 min | 0:05 |
| 1 | YOLO-World adapter + tests | 45 min | 0:50 |
| 2 | harvest_vision scaffolding + Roboflow | 60 min | 1:50 |
| 3 | Commit + push | 10 min | 2:00 |
| 4 | Doc updates + PURCHASE_LIST | 50 min | 2:50 |
| 5 | Buffer + final polish | 10 min | **3:00 hard cut** |

**Total: 180 minutes. Zero slack beyond Phase 5's buffer.** If Phase 1 runs 60 min instead of 45, Phase 4 drops the `PURCHASE_LIST.md` step and keeps `VISION_2027_TRAINING_PLAN.md` updates only.
