# Landscape Scan — Roboflow Ecosystem (2026-04-12)

**Context:** Discovered during casual browsing on 2026-04-12. The Roboflow GitHub
org contains 8 repos that collectively cover almost everything V0a Path A was
going to hand-write. This scan reshapes the Eye's architecture for Week 2
(Worlds prep) and beyond.

**Also found:** [dawarazhar11/SolidVoice](https://github.com/dawarazhar11/SolidVoice-Voice-Enabled-Parametric-Modelling-in-SolidWorks)
(8★) — Whisper → Claude → SolidWorks COM API for voice-controlled parametric
modeling. Validates our Blueprint architecture direction (Whisper → Claude →
Onshape MCP) but targets SolidWorks/Windows, not transferable directly.

---

## HIGH PRIORITY — Direct overlap with planned Engine work

| Repo | Stars | Last Updated | Description | Relevance | Verdict |
|---|---|---|---|---|---|
| [roboflow/supervision](https://github.com/roboflow/supervision) | 38,000 | Active | Reusable CV tools: zone counting, line crossing, heatmaps, annotation | Replaces custom spatial heuristics in V0a Path A. Zone-based scoring event detection is built-in. | **adopt** |
| [roboflow/sports](https://github.com/roboflow/sports) | 4,900 | Active | Sports CV: player tracking, ball tracking, jersey number OCR, camera calibration | **Critical find.** Jersey OCR → bumper number OCR solves per-team attribution (V0a said impossible). Player tracking = robot tracking. Ball tracking = game piece tracking. | **adopt** |
| [roboflow/rf-detr](https://github.com/roboflow/rf-detr) | 6,400 | Active | ICLR 2026 SOTA real-time detector, designed for fine-tuning | Potential replacement for YOLO as the detector backbone. SOTA on COCO, better fine-tuning story. | **investigate** |
| [roboflow/trackers](https://github.com/roboflow/trackers) | 3,300 | Active | Multi-object tracking (DeepSORT, ByteTrack, etc.) | Robot identity persistence across frames. Required for per-team cycle counting. | **adopt** |
| [roboflow/inference](https://github.com/roboflow/inference) | 2,300 | Active | Local edge inference server, any computer → CV command center | Local model runner for the Worlds 5-match demo. Replaces raw ultralytics inference loop. | **adopt** |
| [roboflow/maestro](https://github.com/roboflow/maestro) | 2,700 | Active | Fine-tuning framework for multimodal models (PaliGemma 2, etc.) | Off-season data engine (Path C): fine-tune on auto-labeled FRC data using our 5-class taxonomy. | **investigate** |

## LOWER PRIORITY — Useful but not critical path

| Repo | Stars | Last Updated | Description | Relevance | Verdict |
|---|---|---|---|---|---|
| [roboflow/polygonzone](https://github.com/roboflow/polygonzone) | 84 | Active | Web tool for drawing polygon zones on images | Draw scoring zones on the FRC field image for supervision zone counting. Nice UX for field calibration. | **investigate** |
| [roboflow/sam3](https://github.com/roboflow/sam3) | 15 | Active | SAM 3 inference code + checkpoints | Off-season auto-label data engine: Gemma picks prompts → SAM3 returns masks → YOLO bboxes. | **investigate** |
| [roboflow/zero-shot-object-tracking](https://github.com/roboflow/zero-shot-object-tracking) | 382 | Active | Object tracking using CLIP + DeepSort | Zero-shot robot tracking without FRC-specific training. Fallback if fine-tuned tracker isn't ready for Worlds. | **investigate** |
| [roboflow/notebooks](https://github.com/roboflow/notebooks) | 9,300 | Active | Tutorial collection covering YOLO, SAM, RF-DETR, etc. | Reference material for wiring the pipeline. Not a dependency. | **ignore** |

## OTHER FIND — Not Roboflow

| Repo | Stars | Description | Relevance | Verdict |
|---|---|---|---|---|
| [dawarazhar11/SolidVoice](https://github.com/dawarazhar11/SolidVoice-Voice-Enabled-Parametric-Modelling-in-SolidWorks) | 8 | Whisper → Claude → SolidWorks parametric modeling | Validates Whisper+LLM+CAD architecture but SolidWorks/Windows only. Not transferable. | **ignore** |

---

## Impact on V0a Path A

### Before this scan (original V0a Path A estimate: ~10 hours)

All custom code:
- Custom bumper-color HSV classifier
- Custom spatial zone heuristics (cycle/climb/defense)
- Custom frame-to-frame robot tracking
- No per-team attribution (alliance-level only)
- Raw ultralytics for inference

### After this scan (revised estimate: ~3-4 hours)

Compose existing Roboflow libraries:
- `supervision` for zone counting + heatmaps + annotation
- `trackers` for robot identity across frames
- `sports` OCR for bumper numbers → **per-team attribution** (was "impossible")
- `inference` for local edge deployment (Worlds demo)
- `rf-detr` OR YOLO as detector backbone (investigate which is better for FRC)
- Custom code reduced to: field zone definitions + VisionEvent emission glue

### What this changes about the Worlds demo

**Old success criterion:** 5 consecutive matches, fully local, alliance-level
cycle counts only. Per-team attribution explicitly out of scope.

**New potential:** 5 consecutive matches, fully local, **per-team** cycle counts
+ climb outcomes + defense tags. Bumper OCR makes per-team the default, not
the stretch goal.

---

## New Eye Architecture — Roboflow-Native Pipeline

### The old pipeline (pre-scan)

```
frame
  → YOLO (robot + fuel detection, raw ultralytics)
  → hand-coded bumper-color HSV classifier
  → hand-coded spatial zone heuristics
  → NO robot tracking across frames
  → VisionEvent(team_num=None)  # alliance-level only
```

### The new pipeline (Roboflow-native)

```
                    ┌─────────────────────────────┐
                    │  inference (local server)    │
                    │  Runs rf-detr or YOLO        │
                    │  on every frame              │
                    └──────────┬──────────────────┘
                               │
                    ┌──────────▼──────────────────┐
                    │  trackers (ByteTrack)        │
                    │  Assigns persistent IDs to   │
                    │  each detected robot across  │
                    │  frames                      │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼────────┐ ┌────▼──────┐ ┌───────▼────────┐
    │ sports OCR        │ │supervision│ │ supervision     │
    │ Bumper number     │ │ PolygonZone│ │ LineZone       │
    │ → team_num        │ │ Scoring   │ │ Game piece     │
    │ (per robot bbox)  │ │ zones     │ │ crossing into  │
    │                   │ │ (cage,    │ │ scoring zone   │
    │                   │ │  goals,   │ │ = cycle event  │
    │                   │ │  etc.)    │ │                │
    └─────────┬────────┘ └────┬──────┘ └───────┬────────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
                    ┌──────────▼──────────────────┐
                    │  Event Aggregator            │
                    │  Fuse: tracker_id + team_num │
                    │  + zone_events + line_events │
                    │  → VisionEvent(              │
                    │      event_type="cycle",     │
                    │      team_num=2950,           │
                    │      confidence=0.85)         │
                    └──────────┬──────────────────┘
                               │
                    ┌──────────▼──────────────────┐
                    │  LiveMatch aggregation       │
                    │  Per-team cycle counts       │
                    │  Per-team climb outcomes     │
                    │  Per-team defense tags       │
                    │  (existing schema, now with  │
                    │   real team_num populated)   │
                    └─────────────────────────────┘
```

### Layer breakdown

| Layer | Library | What it does | Custom code needed |
|---|---|---|---|
| **Detection** | `inference` + `rf-detr` or `YOLO` | Detect robots + game pieces per frame | ~0. Config only. |
| **Tracking** | `trackers` (ByteTrack) | Persistent robot IDs across frames | ~0. Plug tracker into detection output. |
| **Team ID** | `sports` (jersey/bumper OCR) | Read bumper numbers → map tracker_id to team_num | ~30 lines. Crop robot bbox lower-third, run OCR, cache result per tracker_id. |
| **Zone events** | `supervision` (PolygonZone, LineZone) | Count game pieces entering scoring zones, robots entering cage zone | ~50 lines. Define zone polygons for the 2026 REBUILT field. Use `polygonzone` web tool to draw them on a field image. |
| **Aggregation** | Custom (existing `vision_yolo.py` schema) | Fuse tracker_id + team_num + zone events → VisionEvent records | ~100 lines. The glue layer. Maps supervision events to our existing VisionEvent taxonomy (cycle, climb_attempt, climb_success, defense). |
| **Match scoping** | Existing `match_boundary.py` + `overlay_ocr.py` | Detect match start/end boundaries from broadcast overlay | Already built. No changes. |
| **Inference server** | `inference` | Run the whole pipeline locally, no API | ~20 lines config. Point inference at downloaded weights, start local server. |

**Total custom code: ~200 lines of glue.** Down from the original V0a Path A
estimate of ~600+ lines of custom spatial heuristics, HSV classifiers, and
manual tracking.

### What we need to install

```bash
pip install supervision          # zone counting, annotation, line crossing
pip install trackers             # multi-object tracking
pip install git+https://github.com/roboflow/sports.git  # jersey/bumper OCR
pip install inference            # local inference server
# rf-detr weights downloaded via inference or ultralytics (already installed)
```

`ultralytics` 8.4.33 is already installed locally. `inference` may pull it as
a dependency anyway.

### What we still need to figure out (Week 2 tasks)

1. **Which detector backbone?** rf-detr vs YOLO11 vs YOLOv8. Need to benchmark
   on FRC footage. rf-detr is SOTA on COCO but FRC footage is different (fast
   motion, overhead angle, specific game pieces). Run both on cached FIT DCMP
   VODs and compare.

2. **Bumper OCR accuracy on FRC footage.** The sports repo's jersey OCR is
   trained on basketball/soccer. FRC bumper numbers are bigger and higher
   contrast but at different angles and distances. Need to test on real FIT
   DCMP frames.

3. **Zone polygon definitions for 2026 REBUILT field.** Use `polygonzone` to
   draw the scoring zones on a field image. These are game-specific — new
   zones every January at kickoff. Should be a config file, not hardcoded.

4. **Tracking persistence through occlusion.** FRC robots routinely block
   each other. ByteTrack handles this for people — need to verify it works
   for boxy FRC robots with similar shapes.

5. **`inference` local server vs raw ultralytics.** The `inference` server adds
   overhead but gives us a cleaner deployment story. For the Worlds 5-match
   demo (local only), either works. For the eventual Coprocessor (Jetson Orin
   Nano), `inference` is designed for exactly that edge deployment.

### Week 2 revised task list (supersedes MONDAY_KICKOFF §2.5 W2.2-W2.4)

| Task | Hours | Description |
|---|---|---|
| W2.2a | 0.5 | Install supervision + trackers + sports + inference locally |
| W2.2b | 1.0 | Wire detection → tracking → OCR → zone counting pipeline as a single `RoboflowFRCModel` registered in `vision_yolo.py` |
| W2.2c | 0.5 | Define 2026 REBUILT field zone polygons (use polygonzone tool on a field image) |
| W2.2d | 0.5 | Write the ~200 lines of aggregation glue (VisionEvent emission) |
| W2.3 | 1.0 | Smoke test against cached FIT DCMP VODs. Compare to Haiku reports. |
| W2.4 | 0.5 | Tune: which detector (rf-detr vs YOLO), OCR confidence threshold, zone boundaries |
| W2.5 | 0.5 | End-to-end live test: one cached VOD, full pipeline, no API calls, LiveMatch output |
| **Total** | **4.5** | Down from original 10h estimate |

---

## Summary

The Roboflow ecosystem (supervision, sports, trackers, inference, rf-detr)
provides battle-tested implementations of almost everything V0a Path A was
going to build from scratch. The critical find is `roboflow/sports` — its
jersey number OCR directly maps to FRC bumper number reading, solving the
per-team attribution problem that V0a declared heuristic-only. Combined with
`supervision` for zone counting and `trackers` for robot identity, the custom
code drops from ~600 lines to ~200 lines of glue, the timeline drops from
~10 hours to ~4.5 hours, and the quality ceiling rises from alliance-level
to per-team-level cycle counts. The Worlds demo (5 consecutive matches, fully
local, zero API) is now significantly more achievable and significantly more
impressive.

---

*Landscape scan by Opus, 2026-04-12. Triggered by user's casual browsing,
not a scheduled scan. This is exactly the kind of discovery the "Search Before
You Build" workflow rule exists to systematize.*
