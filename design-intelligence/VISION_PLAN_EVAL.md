# Vision Plan — Honest Evaluation and Rewrite

**Status:** evaluation doc, 2026-04-11. Grades `VISION_2027_TRAINING_PLAN.md` against its own stated values and proposes a rewrite that cuts total work from ~60 hours to ~12 hours while making the pipeline strictly more future-proof.

**Owner:** Safiq (decision) + Claude (critique).

**Depends on:** `VISION_2027_TRAINING_PLAN.md` (the thing being graded), `V0a_MODEL_SELECTION.md`, `V0b_GPU_SELECTION.md`, `eye/vision_yolo.py` (pluggable registry), `eye/vision_heuristics.py` (game-agnostic climb + defense).

---

## TL;DR

The architecture (pluggable registry + game-agnostic heuristics) is the right foundation and stays. The training plan wrapped around it was written as if it were 2022 — it assumed we had to hand-label 20k frames of archived broadcasts and babysit a 72-hour MLX inference job. That's wrong by 2026 standards.

The rewrite in one sentence: **harvest first, zero-shot second, fine-tune only as a fallback**, with the whole thing driven by a single-command training script that runs on the mentor's MacBook Pro.

**Grade:**
- Original plan: **B+** (right architecture, overbuilt training plan, missed zero-shot and open-data harvesting)
- Rewritten plan: **A** (harvest → zero-shot → fine-tune, ~12 hours total, single command, MacBook Pro runnable)

---

## The grading rubric

The plan should be graded against its own stated values from `VISION_2027_TRAINING_PLAN.md`:

| # | Stated value | What it means in practice |
|---|---|---|
| V1 | Future-proof | New models (released monthly) absorb into the pipeline with zero core edits |
| V2 | Dead simple | One command, one human, no multi-day babysitting |
| V3 | Quickly manageable | Time-to-first-working-model is short, not seasonal |
| V4 | Game-agnostic | A new FRC game does not require a core architecture change |
| V5 | Locally runnable | Everything works on developer-class Apple Silicon hardware |
| V6 | Owned corpus | No vendor lock-in, no surprise EOL of external models |

Each value gets a letter grade below.

---

## Value-by-value grade

### V1 — Future-proof → **A**

The pluggable registry (`eye/vision_yolo.py::MODEL_REGISTRY` + `MODEL_PREFIX_REGISTRY`) is genuinely good. Adding a new model is one `register_model_prefix("thing:", factory)` call at import time. No core edits. Every model released in the last 18 months — YOLO-World, Grounding DINO 1.5, Florence-2, Moondream 2, RT-DETR, YOLOv11, YOLO26 — drops in the same way. This is the piece that carries the whole plan, and it already shipped in commit `16aac8f`.

**No change needed here.** Already A.

### V2 — Dead simple → **D**

This is the biggest failure mode of the current plan. The Week 0 workflow as written is:

1. Pull kickoff assets (30 min)
2. Run Gemma+SAM auto-labeling on MLX (~7 hours wall-clock, unattended)
3. Fine-tune YOLOv11n (~30 min)
4. Wire the composite model (~30 min)
5. QA smoke test (~30 min)
6. Bicep deploy (~30 min)

That's 6 discrete manual steps spread across an overnight inference job. On a chaotic kickoff weekend (when the team is simultaneously reading the game manual, running a prototype build, and arguing about strategy) that's unrealistic.

**Dead simple would be one command:**

```bash
./scripts/train_vision_kickoff.sh \
    --video https://youtube.com/watch?v=FRC_2027_KICKOFF \
    --piece-name "orange orb" \
    --output models/piece_2027.pt
```

60 seconds of human time. Come back later. Commit the result.

**Grade hit: plan is too many manual steps. Fix in Phase 3 of the rewrite.**

### V3 — Quickly manageable → **C-**

60 hours of summer prep work is not "quick." More damningly, "quick" should mean **time-to-first-working-model**, which the current plan pegs at ~6 weeks of background labor between June and August 2026. The team doesn't get a working robot detector until mid-July.

But there are already **working robot detectors published by other FRC teams right now**. We could have one in the registry this week.

The current plan wildly under-exploits the fact that FRC is the most publicly shared niche in robotics ML:

- **Roboflow Universe** — public API, ~7 current 2026-season FRC models (Wiredcat fuel detector at 2784 images, AutoNav robot detector, JohnSpace AprilTag detector at 90.0 mAP)
- **HuggingFace Hub** — FRC datasets + pretrained weights, growing fast
- **GitHub** — Team 6907 Game Piece Detection, PhotonVision labeled calibration data, Limelight public datasets
- **Chief Delphi "Vision" category** — teams post labeled datasets weekly, often CC-BY
- **TBA match videos** — unlabeled but free corpus, matched to scheduled matches

**The plan should harvest before it trains.** Estimated harvest cost: ~6 hours of code + ~1 hour of network-bound pulling. Deliverable: a working ensemble robot detector **this week, not August**.

**Grade hit: 60 hours → 6 hours + 1 hour, most of it this week.**

### V4 — Game-agnostic → **A-**

The `eye/vision_heuristics.py` layer handles climb and defense without any game-specific knowledge. That's real. Cycle detection is still game-specific, but that's fine — cycles need a game-piece detector, and the rewrite handles that via zero-shot prompting (which is *also* game-agnostic, see V1).

Minor ding: the heuristics module was shipped without a real-world zone map ever being drawn or tested against a real VOD. That's a "when we get first VOD footage" check, not a plan flaw, but worth noting.

**Grade holds at A-.**

### V5 — Locally runnable → **B+**

The plan says "M-series inference" without specifying hardware. For a team that's deciding what box to buy, that matters. For our immediate situation (MacBook Pro through competition, Mac Mini deferred to post-season purchase planning), it matters less, but the plan still has a hole here.

MacBook Pro M-series runs YOLO-World + SAM 2.1 + YOLOv11n training comfortably under 12 GB of unified memory. All the zero-shot detectors have MLX ports or Apple Metal accelerated paths. The 20k-frame auto-label job the original plan called for would have been ~3 days of wall-clock time on an M4 Max — doable but awkward on a personal laptop. The **harvest-first rewrite eliminates that pain point entirely** because the harvest step is network-bound, not compute-bound.

**Grade hit: plan was underspecified. Fix by adding a PURCHASE_LIST.md entry (post-season) and documenting the MacBook Pro as the canonical dev box for in-season work.**

### V6 — Owned corpus → **A**

This is the one place the original plan was maybe *too* conservative. It rejects community models on the grounds that they disappear when their authors graduate. True but not fatal — we can fork them into our own repo the day we pull them. The harvest tool should do exactly that: pull every candidate model **and its weights**, checksum them, and commit a manifest.

**Grade: A, because "harvest and fork" is strictly better than either "train from scratch" (slow) or "hosted inference" (vendor lock-in).**

---

## What the original plan missed

This section is the most important part of the eval. The original plan missed these because I wrote it in one pass without stepping back to ask "what has the world shipped since 2024?"

### 1. Zero-shot open-vocabulary detectors (biggest miss)

In the last 18 months, a family of detectors has appeared that takes **text prompts** and detects objects zero-shot. No training. No labels. Type in `"robot"` or `"orange ball"` and get bboxes.

| Model | Strengths | Weaknesses | Our fit |
|---|---|---|---|
| **YOLO-World** (Tencent, 2024) | Fast (real-time on CPU), in `ultralytics`, text-prompted YOLO architecture | Slightly lower accuracy than Grounding DINO | **Primary pick.** Drop-in `ultralytics` means one-line adapter. |
| **Grounding DINO 1.5** | Highest zero-shot accuracy in its class | Slower, larger model | **Secondary fallback** for high-precision work (e.g. kickoff footage labeling). |
| **OWL-ViT v2** | Google's contribution, stable, reliable | Slower than YOLO-World | Backup. |
| **Florence-2** (Microsoft, 2024) | Unified detect + segment + caption in one 230M model | Heavier integration | Interesting for summer 2026 experimentation. |
| **Moondream 2** | 2B-param VLM, runs on iPhone, detects via prompt | Lower accuracy, slower than YOLO-World | Fallback for embedded/edge use cases. |

**For our pipeline**, YOLO-World is the primary pick. It means we can do this:

```python
# MODEL_NAME=yolo-world:robot,orange ball,climb cage
```

and the pipeline just works — for every future FRC game — with no training, no labels, no data engine, nothing. The only question is whether accuracy is high enough for the signals we care about (cycles), and the answer we'll only find out by trying it on cached VODs.

**If zero-shot works, the entire training pipeline becomes a fallback that most seasons we never touch.**

### 2. Open-data harvesting (second biggest miss)

FRC teams publish labeled vision data publicly and continuously. The original plan said "train once on 2016-2026 broadcasts" as if that corpus didn't already exist in someone's Roboflow workspace. It does.

**What a 6-hour harvest tool delivers, versus a 60-hour training effort:**

| Source | What we get | Effort to pull |
|---|---|---|
| Roboflow Universe API | ~7 current FRC models + weights + labels | 1 hour (API exists, rate-limited but fine) |
| HuggingFace Hub API | FRC datasets, pretrained weights | 1 hour (API exists) |
| GitHub public repos | Team 6907, PhotonVision, Limelight data | 2 hours (git clone loop) |
| Chief Delphi scraper | CC-BY datasets linked from Vision threads | 2 hours (BeautifulSoup + respect robots.txt) |

Total: **~6 hours of code, ~1 hour of unattended network pull.** Deliverable: a cached library of ~10-15 candidate robot detectors + ~20 candidate game-piece detectors, all ready for accuracy evaluation against our cached `2026txbel` VODs.

**Simple-ensemble-by-voting** (not a neural re-training, just weighted box fusion) then gives us a shipping detector in under a day of work.

### 3. Single-command training script

The "dead simple" ask needs a single entrypoint. The rewrite delivers:

```bash
./scripts/train_vision_kickoff.sh \
    --video <youtube-url> \
    --piece-name "<prompt>" \
    --output models/piece_2027.pt
```

Under the hood:
1. `yt-dlp` download
2. `ffmpeg` 1 fps decimation
3. YOLO-World zero-shot pre-label (most frames done here, fast)
4. SAM 2.1 refinement on low-confidence YOLO-World boxes
5. `ultralytics` fine-tune YOLOv11n from the harvested robot checkpoint
6. Auto-write `eye/vision_models/piece_2027.py` with `register_model(...)` call
7. Smoke test against held-out frames
8. Print `git add` suggestion

**Runtime on M-series MacBook Pro: ~45 minutes end-to-end.** Human time: 60 seconds of typing + coming back later.

### 4. Mac Mini hardware sizing → **deferred to PURCHASE_LIST.md**

Not needed in-season. MacBook Pro handles everything until competition. Post-season we revisit with a clear "buy X for Y use case" table.

---

## The rewritten plan

### Phase 1 — `tools/harvest_vision/` (~6 hours, this week)

New top-level tool. Not part of the cron worker fleet. Runs on the MacBook Pro.

**Layout:**
```
tools/harvest_vision/
  __init__.py
  roboflow_source.py      # Roboflow Universe API client
  huggingface_source.py   # HF Hub API client
  github_source.py        # git clone + manifest parser
  chiefdelphi_source.py   # HTML scraper for the Vision category
  harvest.py              # orchestrator
  evaluate.py             # accuracy check against cached VODs
  ensemble.py             # weighted box fusion
  cli.py                  # CLI entrypoint
```

**CLI:**
```bash
python -m tools.harvest_vision.cli pull --target robot
python -m tools.harvest_vision.cli evaluate --target robot --against eye/.cache/2026txbel/
python -m tools.harvest_vision.cli ensemble --target robot --top 3 --out models/robot_harvest_v1.pt
```

**Deliverable:** `models/robot_harvest_v1.pt` — a robot detector, harvested + ensembled from public sources, with a manifest of its provenance, ready to register via the `robot:harvest-v1` prefix.

### Phase 2 — YOLO-World prefix handler (~3 hours)

New module `eye/vision_models/yolo_world.py`:
```python
from eye.vision_yolo import register_model_prefix, VisionEvent

def _load_yolo_world(model_name: str):
    from ultralytics import YOLOWorld
    prompts_spec = model_name.split(":", 1)[1]    # "robot,orange ball,climb cage"
    prompts = [p.strip() for p in prompts_spec.split(",") if p.strip()]
    yolo = YOLOWorld("yolov8s-world.pt")
    yolo.set_classes(prompts)
    return _YoloWorldAdapter(yolo, prompts)

register_model_prefix("yolo-world:", _load_yolo_world)
```

Plus `_YoloWorldAdapter` class that translates YOLO-World's detection output into `VisionEvent` records and maps class names back onto our taxonomy (with a per-class -> event_type mapping that the caller provides).

Tests: fake `YOLOWorld` (lazy-imported, so tests can monkeypatch it) returning scripted detections, verify `VisionYolo(model_name="yolo-world:robot,ball")` wires through the registry to the adapter and emits the right events.

### Phase 3 — `scripts/train_vision_kickoff.sh` (~2 hours)

The dead-simple entrypoint. Delegates heavy lifting to `tools/kickoff_finetune/` (new Python package) so the bash script is ~20 lines of arg parsing + one `python -m` call.

### Phase 4 — Update `VISION_2027_TRAINING_PLAN.md` (~1 hour)

Replace the "60-hour summer corpus build" section with a "harvest-first-zero-shot-second-fine-tune-last" section. Keep the milestone schedule but compress Phase 1 from 4 weeks to 1 week.

### Phase 5 — `design-intelligence/PURCHASE_LIST.md` (~30 min)

New doc. Mac Mini sizing table, deferred to post-season. Also captures any other hardware we've been noting offhand.

### Total rewrite cost: ~12.5 hours.

Of which: **~4 hours is code we can ship in one coffee shop session.**

---

## Coffee-shop execution plan (3 hours, tightly scoped)

Given a 3-hour block at a coffee shop with the MacBook Pro, here's the subset that fits and delivers real value. Ordered for highest-leverage-first so if something runs long we cut from the bottom, not the top.

See `COFFEE_SHOP_TASKS.md` for the timeboxed checklist.

---

## Risks and open questions

1. **YOLO-World accuracy on broadcast footage is unknown.** It's possible the frame quality of TBA-archived VODs is low enough that zero-shot accuracy is unacceptable. Fallback: harvest ensemble + fine-tune from the harvest checkpoint. We'll know after the first evaluation run in Phase 1.

2. **Roboflow Universe API rate limits.** Public API has a soft rate limit; harvester needs exponential backoff. Not a blocker, just code hygiene.

3. **License auditing.** Community models come with varying licenses. Harvest tool must capture the license field from each source and refuse to commit non-commercial-licensed weights to our repo. We're not redistributing — we're pulling for evaluation and then either forking (if license allows) or linking (if not).

4. **Evaluation data.** We need held-out test frames to grade harvested models. Today we have cached VODs from `2026txbel` but no labeled test set. First run of the harvest tool will also produce the evaluation dataset (via YOLO-World zero-shot pseudo-labels, validated manually on ~50 frames).

5. **Zone maps.** The defense heuristic needs hand-drawn scoring-zone polygons per broadcast camera angle. We have zero of these drawn right now. First-VOD task, not part of this rewrite.

---

## Final disposition

The original `VISION_2027_TRAINING_PLAN.md` stays in the repo — the architecture description and the milestones are still useful context. It gets a header update saying "superseded in part by `VISION_PLAN_EVAL.md`; see that doc for the harvest-first rewrite" and a pointer to the rewritten Phase 1.

Everything else rolls forward via the coffee-shop tasks and then the remaining Phase 3-5 work as time allows between now and regionals.

---

## Sources

- `VISION_2027_TRAINING_PLAN.md` — the thing being graded
- `V0a_MODEL_SELECTION.md`, `V0b_GPU_SELECTION.md` — context
- `eye/vision_yolo.py`, `eye/vision_heuristics.py` — the foundation the rewrite builds on
- [YOLO-World: Real-Time Open-Vocabulary Object Detection (Tencent, 2024)](https://arxiv.org/abs/2401.17270)
- [Grounding DINO 1.5 (IDEA Research)](https://arxiv.org/abs/2405.10300)
- [Florence-2 (Microsoft, 2024)](https://arxiv.org/abs/2311.06242)
- [Moondream 2](https://github.com/vikhyat/moondream)
- [Roboflow Universe API docs](https://docs.roboflow.com/api-reference)
- [HuggingFace Hub API](https://huggingface.co/docs/hub/api)
- [Chief Delphi Vision category](https://www.chiefdelphi.com/c/technical/programming/vision)
- [Team 6907 FRC Game Piece Detection](https://github.com/Team-6907/FRC-Game-Piece-Detection)
