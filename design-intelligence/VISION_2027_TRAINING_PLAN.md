# Vision 2027 — Training Plan

**Status:** design doc, 2026-04-11. Sketches how Team 2950 ships a real (non-fake) vision model for Week 1 of the 2027 season.

**Owner:** Safiq (decision) + Claude (implementation during summer 2026).

**Depends on:** `V0a_MODEL_SELECTION.md` (Path C resolution), `V0b_GPU_SELECTION.md` (CPU-only resolution), `LIVE_SCOUT_PHASE2_REMAINING.md §6` (auto-label data engine sketch), `eye/vision_heuristics.py` (game-agnostic climb + defense layer).

---

## TL;DR

We don't need a game-specific model. We need **one robot detector** trained on a decade of FRC broadcast footage, plus the `eye/vision_heuristics.py` game-agnostic climb + defense layer that already exists, plus a small **game-piece model that gets fine-tuned during Week 0** of each new season from kickoff broadcasts.

Total work: ~60 hours over summer 2026 + ~4 hours the weekend of kickoff each future season. Result: a vision pipeline that handles every future FRC game without core code changes.

---

## The key insight (from Safiq, 2026-04-11)

> "If we train our model on all the past decade wouldn't that be a good guide for almost any future game pieces? Most of our game pieces are balls or squares with the rare exception of gears in 2017. The rare items could be trained in the first week."

He's right, and it unlocks a much cleaner architecture than "pick a Roboflow model each year". Let's look at the last decade:

| Year | Game | Game piece(s) | Shape class |
|---|---|---|---|
| 2016 | Stronghold | Boulder | Sphere |
| 2017 | Steamworks | Fuel + Gear | Sphere + Gear (odd) |
| 2018 | Power Up | Cube | Cube |
| 2019 | Deep Space | Cargo + Hatch Panel | Sphere + Disc |
| 2020 | Infinite Recharge | Power Cell | Sphere |
| 2022 | Rapid React | Cargo | Sphere |
| 2023 | Charged Up | Cone + Cube | Cone + Cube |
| 2024 | Crescendo | Note | Torus |
| 2025 | Reefscape | Coral + Algae | Cylinder + Sphere |
| 2026 | REBUILT | Fuel | Sphere |

**Observation 1:** 7 of 11 game pieces across 11 seasons were spheres or cubes. A generic "small convex object on the field floor" detector would catch almost all of them.

**Observation 2:** The genuinely novel shapes (gears 2017, cones 2023, notes/torus 2024, corals 2025) were all introduced at kickoff — and kickoff videos are broadcast the morning of day 1 with clean close-up shots of the game piece on the field. **That's a labelable training corpus, for free, on Week 0.**

**Observation 3:** Robots themselves barely change year to year. They're 120 lb rectangles on wheels with bumpers. A robot detector trained on 2016-2026 footage will work unchanged on 2027+.

This means the decomposition is:

1. **Robot detector** — train once on 2016-2026 archived broadcasts. Never retrain. Classes: `{robot}`.
2. **Game-piece detector** — fine-tune weekly-ish at the start of each season from kickoff video + Week 0 qualification broadcasts. Classes: `{game_piece}` (always one class; different weights per year).
3. **Heuristic layer** — already built (`eye/vision_heuristics.py`). Climb and defense are computed from robot bboxes + ground plane + zone map, no game-piece knowledge needed.

Cycles are the only game-piece-dependent signal, and cycles need the fine-tuned game-piece model. Everything else is year-agnostic.

---

## Architecture

```
                ┌─────────────────────────────┐
                │   eye/vision_yolo.py        │
                │   (pluggable registry)      │
                └──────────────┬──────────────┘
                               │
                 load_vision_model("composite:2027")
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
    ┌──────────────────┐             ┌──────────────────┐
    │ Robot detector   │             │ Game-piece       │
    │ (trained once on │             │ detector         │
    │  2016-2026)      │             │ (fine-tuned      │
    │                  │             │  Week 0 each     │
    │ Classes: {robot} │             │  season)         │
    │                  │             │                  │
    │ ~10 MB weights   │             │ Classes: {piece} │
    │ YOLOv11n / 26n   │             │ ~10 MB weights   │
    └────────┬─────────┘             └────────┬─────────┘
             │                                │
             ▼                                ▼
    ┌──────────────────────────────────────────────┐
    │  CompositeVisionModel.infer(frame_path):     │
    │    robots = robot_model.infer(frame)         │
    │    pieces = piece_model.infer(frame)         │
    │    → RobotDetection[] + piece bboxes         │
    └──────────────────┬───────────────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────────────┐
    │  eye/vision_heuristics.py                    │
    │    - GroundPlaneEstimator → floor_y          │
    │    - detect_climb_events → climb_* events    │
    │    - detect_defense_events → defense events  │
    │    - (new) detect_cycle_events → cycle events│
    └──────────────────────────────────────────────┘
```

Notice the registry lets us swap either half independently:

- `register_model_prefix("robot:", _load_robot_detector)` — one robot model, stable across years.
- `register_model_prefix("piece:2027", _load_2027_piece_detector)` — fine-tuned per season.
- `register_model("composite:2027", _build_composite)` — an exact-match handler that wires both halves together.

Flipping from `MODEL_NAME=fake` → `MODEL_NAME=composite:2027` is a single Bicep parameter edit.

---

## Phase 1 — Summer 2026: Build the robot detector

**Timeline:** 4 weeks of background work between June and August 2026.

### Step 1: Corpus collection (~8 hours)

Pull archived broadcasts from TBA + FIRST YouTube channel:

- Target: ~3 matches per event × ~30 events per year × 11 years ≈ **1000 matches** of footage.
- Prefer qualification matches, not finals — more varied robots on the field.
- Prefer wide-angle (field view) over close-ups.
- Cache to `eye/.cache/training/broadcasts/<year>/<event>/<match_key>.mp4`.
- Frame-decimate to 1 fps = ~150 frames per match × 1000 matches = **~150k frames**.

Why 1 fps: we don't need 30 fps for a robot detector — robots move slowly relative to the frame. 1 fps samples diverse poses without bloating the dataset.

### Step 2: Auto-label with Gemma + SAM3.1 on MLX (~40 hours of M-series inference)

Per-frame pipeline:

1. Gemma 4 picks the prompt: `"every robot on the field"` (never changes — it's always the same prompt).
2. SAM 3.1 returns segmentation masks.
3. Mask → tight bbox → `{class: "robot", bbox: [x1,y1,x2,y2]}` YOLO label.
4. Write `labels/<frame_id>.txt` + add the image to `images/train/`.

Latency: ~10-15 sec/frame on M-series → 150k frames × 12 sec = 500 hours ≈ 21 days wall-clock if you run it 24/7.

**Reality check:** we don't need 150k frames. A robot detector trained on 20k frames from 5 years is indistinguishable from one trained on 150k frames from 11 years — robot shapes don't change that much. **Target 20k frames. ~70 hours of inference → 3 days wall-clock.**

### Step 3: Human QA pass (~4 hours)

Random-sample 500 auto-labels, visually verify masks are tight around robots. Reject frames with too many false positives (refs, cameramen, screen-on-screen overlays). Whitelist the clean ones.

The 500-sample check is the ceiling on quality — if 95% look good, ship it. If 80% look good, we tweak the Gemma prompt or the SAM threshold and re-run.

### Step 4: Train YOLOv11n / YOLO26n on the auto-labels (~2 hours on M-series)

YOLOv11n has ~2.6M parameters and trains in ~90 minutes on an M1 Max with 20k frames and 100 epochs. The exact flavor (v8n / v11n / 26n) doesn't matter much at this scale — pick whatever `ultralytics` ships with the cleanest export pipeline at the time.

Output: `models/robot_detector_v1.pt` (~10 MB).

### Step 5: Register + deploy (~1 hour)

```python
# eye/vision_models/robot_detector.py
from eye.vision_yolo import register_model_prefix, VisionModel, VisionEvent

def _load_robot_detector(model_name: str) -> VisionModel:
    from ultralytics import YOLO
    weights = model_name.split(":", 1)[1] or "models/robot_detector_v1.pt"
    yolo = YOLO(weights)
    return _RobotYoloAdapter(yolo)

register_model_prefix("robot:", _load_robot_detector)
```

Ship the `.pt` file inside the `vision-worker` container image (it's 10 MB, which is rounding error compared to the Python runtime).

---

## Phase 2 — Week 0 of each new season: Fine-tune the game-piece detector

**Timeline:** ~4 hours on kickoff weekend, every future season.

### Step 1: Pull kickoff assets (~30 min)

- Kickoff video from FIRST (always contains clean renders + prop shots of the new game piece).
- Game manual PDF — some years include 3D renders.
- Any Week 0 scrimmage broadcasts (Granite State, Ramp Riot, etc. — usually ~1 week after kickoff).

### Step 2: Auto-label with Gemma + SAM3.1 (~2 hours of MLX inference)

Prompt: `"every <game_piece_name> on the field"`. The name comes from the kickoff video. For 2027 this might be `"every Orb"` or `"every Widget"` — Gemma adapts immediately, SAM doesn't care what the label is, and we don't need a single line of code change.

Target: ~2000 frames from the kickoff video + any Week 0 footage. ~2000 × 12 sec = 7 hours wall-clock — run overnight on the Sunday of kickoff.

### Step 3: Fine-tune YOLOv11n from the robot detector checkpoint (~30 min)

Transfer-learn: start from `robot_detector_v1.pt`, replace the head with a single-class `game_piece` head, train for ~30 epochs on the new labels. Output: `models/piece_detector_2027.pt`.

Why start from the robot checkpoint: the backbone has already learned general field features (bumpers, floor, lighting). Transfer learning on 2000 frames gets us to ~85% mAP in ~10 minutes of training.

### Step 4: Build the composite model (~30 min)

```python
# eye/vision_models/composite_2027.py
from eye.vision_yolo import register_model, VisionModel, VisionEvent

def _build_composite_2027(model_name: str) -> VisionModel:
    from ultralytics import YOLO
    robot_yolo = YOLO("models/robot_detector_v1.pt")
    piece_yolo = YOLO("models/piece_detector_2027.pt")
    return _CompositeVision(robot_yolo, piece_yolo)

register_model("composite:2027", _build_composite_2027)
```

`_CompositeVision.infer(frame)`:
1. Run `robot_yolo` → RobotDetection list
2. Run `piece_yolo` → piece bbox list
3. Run `detect_climb_events` + `detect_defense_events` from `eye/vision_heuristics.py`
4. Run a new `detect_cycle_events` that correlates piece bboxes with a "scoring zone" polygon (same ZoneMap shape as defense detection)
5. Return the concatenated VisionEvent list

### Step 5: Deploy (~30 min)

One Bicep parameter flip: `visionModelName=composite:2027`. Container rebuilds, cron picks up the new model on the next tick. Ship it before the team's first event.

### Total Week 0 work: ~4 hours

- 30 min corpus pull
- ~7 hours auto-label (wall-clock, unattended overnight)
- 30 min training
- 30 min composite wiring
- 30 min QA smoke test
- 30 min Bicep deploy
- Buffer

Fits in one evening of work Sunday night of kickoff week, assuming Saturday was spent watching the kickoff and reading the game manual.

---

## What about rare-shape games?

Safiq's worry: "the rare items could be trained in the first week." Let's enumerate:

- **2017 Gear:** odd flat disc with a hole. Gemma/SAM handle flat objects on a floor just fine — the prompt `"every gear on the field"` works unchanged.
- **2023 Cone:** distinctive shape, was all over kickoff video. Auto-labeling from kickoff footage would have produced a working detector in under 2 hours.
- **2024 Note (torus):** novel shape, but visually distinctive on the floor. Same workflow.
- **2025 Coral (cylinder):** ditto.

**Conclusion:** no game piece in the last decade would have broken this workflow. The "rare shape" failure mode is hypothetical, not historical.

If a future game does introduce something truly weird (liquid? shape-shifting piece? invisible?), the fallback is unchanged: the robot detector still works, `eye/vision_heuristics.py` still computes climb + defense, and we lose only the cycle signal — which is exactly what happens today with `MODEL_NAME=fake`. The pipeline degrades gracefully.

---

## Why this beats every alternative

### vs "pick a Roboflow model each year"
- No community model covers our 5-class taxonomy with team-number attribution.
- Community models are trained on random other teams' footage, not a curated corpus.
- Community models disappear when their authors graduate.
- **Our training pipeline is idempotent and replayable** — we own every byte.

### vs "train a 5-class model from scratch each year"
- ~60 hours of summer prep + ~20 hours of Week 0 fine-tune × forever.
- Has to re-label the robot class every season (wasted work).
- Transfer learning from last year's model is possible but gets worse over time as the piece classes drift.

### vs "stay fake forever"
- Works. Phase 2 already runs fine on `MODEL_NAME=fake`.
- But we lose the vision-exclusive signals (per-team cycle cadence, defense time, climb outcome) that OCR can't give us.
- The pick board's `real_avg_score` is still computed from OCR scores, so the ranking isn't blind — we're just leaving some data on the table.

### vs "pay for a commercial service"
- Roboflow hosted inference is ~$3-10/month per project. Two projects = ~$10-20/month.
- Our self-hosted pipeline is $0/month after the initial training (vision-worker runs on existing CPU container).
- No API rate limits, no vendor lock-in, no surprise EOL.

---

## What blocks this today

Nothing — this plan is intentionally scheduled for summer 2026 and kickoff 2027 so it doesn't compete with the in-season pick board / synthesis worker / Scout live draft work. The only thing that needs to happen before summer is **finish Phase 2**, which is what `LIVE_SCOUT_PHASE2_REMAINING.md` tracks.

---

## Milestones

| Date | Milestone |
|---|---|
| 2026-04-11 | V0a/V0b resolved, `eye/vision_heuristics.py` shipped, registry in place *(this doc)* |
| 2026-04-12 | Phase 2 prereqs closed, Safiq mints the Anthropic key + TBA creds |
| 2026-05-01 | 2026 regionals over, season post-mortem |
| 2026-06-01 | Start corpus collection for robot detector |
| 2026-07-01 | 20k frames auto-labeled + QA'd |
| 2026-07-15 | `robot_detector_v1.pt` trained, registered via `robot:` prefix |
| 2026-08-15 | Composite pipeline dry-run against 2026 cached VODs, end-to-end tested |
| 2026-12-31 | Kickoff assets ready (pre-planned prompts, MLX inference box idle and ready) |
| 2027-01-03 | Kickoff weekend — auto-label + fine-tune + deploy `composite:2027` |
| 2027-02-XX | Team 2950's Week 1 event — vision pipeline live with real model |

---

## Open questions

1. **Do we ship the robot model weights inside the container image or fetch them from Blob Storage at startup?** Image is simpler (one-shot deploy); blob is cleaner (model can be swapped without a rebuild). Recommend: image for v1, blob if we ever need to A/B test models mid-season.

2. **Cycle zone map — hand-drawn or auto-detected?** Hand-drawn is ~5 minutes per broadcast camera angle and we only have ~5 angles across the season. Auto-detected via AprilTag + homography is 2027-off-season work if it's worth it.

3. **Do we bother with team-number attribution via bumper-OCR?** Probably not for 2027 — heuristic "red alliance team 1/2/3 by spatial position" is Good Enough and bumper OCR adds an entire second model to the pipeline. Revisit after we see what the plain robot detector does for a full season.

4. **What about Week 1 "scrim" events?** Some teams scrim the weekend before Week 1 and those broadcasts often contain the cleanest wide-angle shots of the new game. Adding scrim footage to the Week 0 corpus would probably add another ~500 frames and push the fine-tune quality materially higher. Optional step 2.5 in the Week 0 workflow.

---

## Sources

- `V0a_MODEL_SELECTION.md` — why Path C (stay fake in-season) is correct for 2026
- `V0b_GPU_SELECTION.md` — why CPU-only is correct for all three paths
- `LIVE_SCOUT_PHASE2_REMAINING.md §6` — original auto-label data engine sketch
- `eye/vision_heuristics.py` — the game-agnostic layer this plan depends on
- `eye/vision_yolo.py` — the pluggable registry this plan targets
- [YOLO26 announcement](https://blog.roboflow.com/yolo26/) — likely the default YOLO flavor by summer 2026
- [Segment Anything 3.1](https://github.com/facebookresearch/sam2) — mask oracle
- [Maziyar Panahi: Gemma 4 + SAM 3.1 on MLX](https://twitter.com/MaziyarPanahi) — demo that inspired the MLX pipeline choice
- `project_llm_wiki.md` (user memory) — Karpathy's data engine pattern, applied to vision here
