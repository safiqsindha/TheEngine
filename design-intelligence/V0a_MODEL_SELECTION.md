# V0a — Vision Worker Model Selection

**Status:** decision doc, 2026-04-11. Resolves the "pick a Roboflow Universe FRC YOLO model" prereq from `LIVE_SCOUT_PHASE2_REMAINING.md §5`.

**Owner:** Safiq (decision) + Claude (implementation once decision lands).

---

## The core problem

The Phase 2 vision worker schema (`eye/vision_yolo.py::VisionEvent`) commits to **five** event types, each with a `team_num`:

```
cycle | climb_attempt | climb_success | climb_failure | defense
```

**No single Roboflow Universe FRC model emits this taxonomy.** Every public FRC 2026 model found detects one of:

- A game piece (Fuel), or
- AprilTags, or
- Robots (only a 2023-era model from AutoNav, generic class "robot")

None of them emit `cycle`, none of them emit `climb_*`, none of them emit `defense`, and none of them assign detections to a **team number** (at best you get "red robot" / "blue robot" via bumper color heuristics).

So "pick a model" is not really a single-dropdown decision. It's a **pipeline architecture** decision with three viable paths.

---

## The candidate models (for context)

These are the 2026-season FRC YOLO models I found on Roboflow Universe. None of them solve the full taxonomy problem alone — they're parts of a compound pipeline at best.

| Project | Workspace | Detects | Images | Last updated | Notes |
|---|---|---|---|---|---|
| 2026 FRC Rebuilt Fuel Detection | `2026-wiredcat-fuel-detection/2026-frc-rebuilt-fuel-detection` | Fuel (4 classes) | **2784** | ~2026-03 | **Largest** 2026 fuel dataset. Almost certainly red/blue/goal/stacked splits. |
| FRC 2026 Fuel | `frcroboraiders/frc-2026-fuel-sbrdk` | Fuel | 706 | 2026 | YOLOv11 |
| FRC 2026 ReBuilt Fuel Detection | `myworkspace-mliyg/frc-2026-rebuilt-fuel-detection` | Fuel | ? | 2026-01 | YOLOv11 |
| FRC 2026 Fuel | `-wrw23/frc-2026-fuel` | Fuel | 464 | 2026-01 | |
| FRC 2026 Fuel Detection | `robotics-mncog/frc-2026-fuel-detection-et8lw` | Fuel | 162 | 2026 | Smallest |
| 2026 FRC AprilTags | `johnspace-ivyq6/2026-frc-apriltags` | AprilTag IDs | 4000 | 2026-02-21 | mAP 90.0 / P 86.7 / R 84.3 — **best-published metrics** |
| FRC Robot Detection | `autonav/frc-robot-detection` | cone, cube, robot | ? | 2023 | 2023-era (Charged Up); "robot" class still valid, cone/cube are dead |

**Observation:** the only pre-trained model with a published mAP is the AprilTag detector, and AprilTags tell us nothing about cycles or climbs. The biggest and best-maintained "real game" detector is the 2026 Wiredcat fuel detector.

---

## The three paths

### 🛣️ Path A — Compound pipeline (best quality, most work)

**Architecture:** wire two models behind a fused `VisionYolo` that emits our taxonomy.

```
frame → [robot detector]  → robot bboxes
      → [fuel detector]   → fuel bboxes
      → bumper-color classifier (red/blue)
      → Mode-A team-set cross-reference (we know the 6 teams in the match)
      → spatial heuristics:
          * fuel bbox near low-goal / high-goal zone
            AND within radius of an alliance-matching robot → cycle event
          * robot bbox on chain hook / cage zone during endgame timer
            → climb_attempt
          * robot bbox remains on cage at match-end frame
            → climb_success
          * non-scoring robot stays in opposing scoring zone > N frames
            → defense
```

**Components we'd actually use:**
- **Robot detector:** `autonav/frc-robot-detection` (filter to "robot" class only; ignore the dead cone/cube classes from 2023)
- **Fuel detector:** `2026-wiredcat-fuel-detection/2026-frc-rebuilt-fuel-detection` (biggest, freshest)

**Effort:**
- ~6 hours to write the compound wrapper in `_load_real_model` + the bumper-color classifier (OpenCV HSV mask on the lower third of each robot bbox) + the spatial heuristics
- ~4 hours of tuning on cached VODs from 2026txbel to get the zone definitions right
- **Gated on:** a GPU SKU decision (Path A is painful on CPU) — see `V0b_GPU_SELECTION.md`

**Team-number attribution is still heuristic.** We know the 3 red + 3 blue teams per match from TBA. We know bumper color from the detector. We don't know *which* red robot is team 2950 vs team 148 vs team 1678 from the YOLO output alone — we'd have to track spatial position across frames and do a second disambiguation pass (OCR on bumper numbers, or simply attribute "red team cycle" without pinning it to one specific driver station, which is what the stand scouts are for anyway).

**Quality ceiling:** roughly as good as a human scout watching the stream. Not as good as a human scout watching the actual field.

### 🛣️ Path B — Fuel-only proxy pipeline (fastest to ship, lossy)

**Architecture:** single model, no robot correlation.

```
frame → [fuel detector] → count fuel bboxes in "scoring zone" region
                        → emit cycle events WITHOUT team_num
      → no climb detection at all (leave climb_results empty)
      → no defense detection at all
```

**Components:**
- Just `2026-wiredcat-fuel-detection/2026-frc-rebuilt-fuel-detection`

**Effort:**
- ~2 hours to write the zone-based cycle counter in `_load_real_model`
- Can run on CPU at `*/10 * * * *` cadence with acceptable latency

**What you lose:**
- No per-team cycle attribution (counts are aggregate-per-alliance, which we already get from OCR scores anyway)
- No climb tracking (climb_results stays empty → endgame analysis is OCR-only)
- No defense tagging (we lose the one vision-exclusive signal)

**Honestly: Path B is barely better than `FakeYOLOModel`.** The OCR pipeline already gives us alliance scores and alliance breakdowns for free. Adding a fuel detector that only tells us "red alliance scored ~12 fuel this match" doesn't add information on top of the breakdown screen OCR. The vision pipeline's whole value is the **per-team** breakdown that OCR can't give, and Path B doesn't deliver that.

### 🛣️ Path C — Stay fake, ship the auto-label data engine (off-season)

**Architecture:** `MODEL_NAME=fake` stays in prod through the 2026 season. The vision worker is deployed, wired, cron-scheduled, and emits empty `vision_events` / `cycle_counts` / `climb_results`. LiveMatch records still carry OCR data, which is what the pick board actually reads anyway.

During summer 2026, execute the **Gemma+SAM3.1 auto-labeling data engine** from `LIVE_SCOUT_PHASE2_REMAINING.md §6 (off-season backlog)`:

1. Pull archived VODs from 2026 events (all of them, not just 2950's)
2. Gemma 4 picks open-vocabulary prompts per frame
3. SAM3.1 returns masks
4. Masks → YOLO bounding boxes in our own 5-class taxonomy
5. Train a local YOLOv8n/v11n on the auto-labels
6. Ship the trained weights into `_load_real_model`
7. 2027 season ships with a vision model trained on **our** taxonomy with **our** class names

**Effort this season:** zero. Everything Phase 2 infra is already deployed; vision worker already runs `MODEL_NAME=fake` with no errors.

**Effort off-season:** 80-120 hours of M-series inference time + ~20 hours of plumbing code. All batch work, none of it urgent.

**Quality ceiling:** a proper FRC vision model trained specifically on our taxonomy. Better than Path A by a lot, because the classes are **our** classes instead of heuristic translations from generic robot/fuel detections.

---

## Recommendation

**Path C for the 2026 season. Path A is the long-term destination via the off-season data engine.**

### Why not Path A now?

1. **Zero-sum with the rest of the season.** Path A is ~10 hours of work before we tune it against real VODs, and we're already inside the competition window (today is 2026-04-11 — regionals are either imminent or underway). Any hour spent on vision worker tuning is an hour not spent on pick board, Scout live draft, or the pre-event report pipeline.

2. **The quality ceiling is low and the work is throwaway.** Everything we build in Path A — the compound wrapper, the bumper-color classifier, the spatial heuristics — gets **deleted** when Path C's auto-label pipeline ships for 2027. We're not building foundation; we're building a bridge we'll burn.

3. **We already have the data we'd have extracted.** Mode A's OCR gives us alliance scores + breakdowns. Mode B's replay gives us match outcomes. The stand scout gives us per-team subjective notes. The pick board's `real_avg_score` aggregate is already computed from OCR'd scores. Vision adds per-team *physical* metrics (cycle cadence, defense time, climb outcome) — which are exactly the things Path A can't reliably attribute to a specific team without bumper-number OCR, which we don't have.

4. **The team never depended on the vision worker shipping real inference for 2026.** The Phase 2 architecture explicitly declared `FakeYOLOModel` as a valid production deployment. Gate 2 shipped without anyone noticing the vision worker was fake.

### Why not Path B?

Because it adds a moving part with zero information gain. The OCR pipeline already gives us alliance-aggregate fuel counts via the breakdown screen. A fuel detector that confirms "yes, red alliance scored a lot of fuel" is noise — we already know the red score.

### What Path C actually means in code

1. **Leave `visionModelName=fake` in `parameters.dev.json`.** No Bicep change.
2. **Leave `_load_real_model` as `NotImplementedError`.** It fires loud if anyone accidentally sets `MODEL_NAME` to a non-fake value in prod — which is what we want.
3. **Close out V0a as "resolved: Path C"** in this doc.
4. **Keep V0b deferred.** No GPU decision needed while `MODEL_NAME=fake`; the default empty `visionGpuSku` is correct.
5. **Open a 2026-off-season ticket** pointing at `LIVE_SCOUT_PHASE2_REMAINING.md §6 auto-label data engine`. That's the real V0a successor.

### What Path A would actually look like, if you overrule me

If you decide Path A is worth the 10 hours, the implementation outline is:

```python
# eye/vision_yolo.py::_load_real_model
def _load_real_model(model_name: str) -> Any:
    if model_name == "compound_v1":
        return _CompoundFRC2026Model(
            robot_model_id="autonav/frc-robot-detection/1",
            fuel_model_id="2026-wiredcat-fuel-detection/2026-frc-rebuilt-fuel-detection/1",
            confidence=0.5,
        )
    raise NotImplementedError(...)
```

`_CompoundFRC2026Model`:
- `__init__`: lazy-imports `roboflow`, pulls both hosted inference APIs OR downloads weights via `roboflow.Roboflow(api_key=...).project(...).version(...).download("yolov8")` for offline inference
- `infer(frame_path)`:
  1. Run robot detector → list of robot bboxes
  2. Run fuel detector → list of fuel bboxes
  3. Classify each robot bbox as red/blue via HSV mask on lower-third bumper region
  4. For each fuel bbox, find the nearest alliance-matching robot (or drop if no match)
  5. Emit `VisionEvent(event_type="cycle", team_num=None, ...)` per fuel-in-scoring-zone event
  6. Map robot positions against a zone map (low goal / high goal / cage / opponent scoring zone) to emit `climb_attempt`, `climb_success`, `defense`
  7. Team number: left as `None` until we have bumper-number OCR

New dep in `workers/requirements.txt`: `inference>=0.20,<1.0` (the Roboflow Inference SDK) OR `ultralytics>=8.3` if we download weights and run locally.

New Bicep param: `visionModelName=compound_v1` + `visionGpuSku=Consumption-GPU-NC8as-T4` (see `V0b_GPU_SELECTION.md`).

Estimated cost: ~$25/month GPU + ~$3/month Roboflow hosted inference (if used) vs. ~$0/month in Path C.

---

## Decision needed from Safiq

Pick one:

- **[ ] Path C** (recommended) — stay fake, resolve in off-season via data engine
- **[ ] Path B** — ship a fuel-only cycle counter in the next 2 hours
- **[ ] Path A** — compound pipeline, ~10 hours of work, needs V0b decided first
- **[ ] Other** — e.g. "just run the Wiredcat fuel model and see what it does in dry-run to gather intuition before committing"

Once a path is chosen, I'll execute it end-to-end and close out V0a.

---

## Sources

- [YOLO26: YOLO Model for Real-Time Vision AI 2026](https://blog.roboflow.com/yolo26/)
- [2026 FRC Rebuilt Fuel Detection (Wiredcat)](https://universe.roboflow.com/2026-wiredcat-fuel-detection/2026-frc-rebuilt-fuel-detection)
- [FRC 2026 Fuel (frcroboraiders)](https://universe.roboflow.com/frcroboraiders/frc-2026-fuel-sbrdk)
- [FRC 2026 ReBuilt Fuel Detection (Joshua Pankratz)](https://universe.roboflow.com/myworkspace-mliyg/frc-2026-rebuilt-fuel-detection)
- [FRC 2026 Fuel (-wrw23)](https://universe.roboflow.com/-wrw23/frc-2026-fuel)
- [FRC 2026 Fuel Detection (robotics-mncog)](https://universe.roboflow.com/robotics-mncog/frc-2026-fuel-detection-et8lw)
- [2026 FRC AprilTags (JohnSpace)](https://universe.roboflow.com/johnspace-ivyq6/2026-frc-apriltags)
- [FRC Robot Detection (AutoNav, 2023-era)](https://universe.roboflow.com/autonav/frc-robot-detection)
- [Team 6907 FRC Game Piece Detection (2024-era GitHub)](https://github.com/Team-6907/FRC-Game-Piece-Detection)
