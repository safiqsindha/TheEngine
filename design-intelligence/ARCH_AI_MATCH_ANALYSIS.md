# THE ENGINE — AI Match Analysis System (Lite)
# Codename: "The Eye"
# Scoped: 60-80 hours (down from 260)
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

Every FRC match is live-streamed. The schedule is published with exact
team assignments and driver station positions. The field layout is
identical at every event. What if an AI watched every match at every
event and built a complete performance profile for every team — scoring
locations, cycle times, auto paths, climb reliability — automatically?

That is The Eye. It turns public video streams into competitive
intelligence at a scale no human scouting operation can match.

**Lite scope:** Batch processing overnight, not real-time. Single-event
analysis, not live streaming. Heat maps and cycle times, not defense
tracking or scoreboard OCR. This still gives you 90% of the value.

---

## What It Produces (Per Team, Per Match)

| Data Point | How It's Extracted |
|-----------|-------------------|
| Starting position (x, y) | Pre-match frame + TBA driver station assignment |
| Auto path | Frame-by-frame position tracking during first 20s |
| Teleop scoring locations | Heat map of where the robot scores from |
| Cycle times | Time between consecutive scoring zone entries |
| Climb attempt/success | Robot position on Tower at match end |
| Scoring consistency | Standard deviation of cycle times across matches |

### What's Cut (Full Version Only)
- ~~Defense interaction tracking~~ (Phase 2 of full version)
- ~~Scoreboard OCR~~ (TBA has scores — use that instead)
- ~~Live/near-live processing~~ (overnight batch is sufficient)
- ~~Drive coach tablet dashboard~~ (The Whisper covers this)
- ~~Custom robot identity model~~ (use alliance color + position)

---

## System Architecture (Lite)

```
┌─────────────────────────────────────────────────────┐
│                    DATA SOURCES                      │
│  TBA API: schedule, teams, driver stations, scores  │
│  YouTube: match video VODs (1080p)                  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              STREAM CAPTURE (Layer 1)                │
│  yt-dlp: download match VODs by event playlist      │
│  Frame extraction at 5 fps (sufficient for FRC)     │
│  Match segmentation using TBA schedule timestamps   │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│           FIELD CALIBRATION (Layer 2)                │
│  One-time per event venue/camera angle              │
│  4-point click → homography transform               │
│  Field is always 54ft × 27ft — geometry is known    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│        ROBOT DETECTION + TRACKING (Layer 3)          │
│                                                      │
│  Detection: YOLOv11-nano (fine-tuned or pretrained)  │
│    - 2 classes: red_bumper, blue_bumper              │
│    - Use existing Roboflow FRC datasets first        │
│                                                      │
│  Identity Assignment (frame 0, pre-match):           │
│    - TBA says Red1=254, Red2=1323, Red3=4567        │
│    - Leftmost red robot = Red1 = team 254            │
│                                                      │
│  Tracking: Supervision library (ByteTrack built-in)  │
│    - Alliance color separates red vs blue            │
│    - Within alliance: nearest-neighbor matching      │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│           SCORING ZONE DETECTION (Layer 4)           │
│                                                      │
│  Robot enters Hub scoring zone → cycle end           │
│  Auto vs Teleop: first 20s = auto, rest = teleop    │
│  Climb: robot position on Tower at match end         │
│  (No scoreboard OCR — use TBA match scores instead)  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│            OUTPUT (Layer 5)                           │
│                                                      │
│  Per team per match: SQLite database                 │
│    starting_position, auto_path, cycle_times,        │
│    scoring_heat_map, climb_success                   │
│                                                      │
│  Aggregated: scoring heat maps, cycle distributions, │
│    auto consistency, climb success rate               │
│                                                      │
│  Visualization: matplotlib field overlay plots       │
│  → Fed into The Scout pre-event reports              │
└─────────────────────────────────────────────────────┘
```

---

## Existing Libraries That Accelerate This

| Library | What It Replaces | Time Saved | Install |
|---------|-----------------|------------|---------|
| **[Roboflow Universe](https://universe.roboflow.com)** | Training data collection + labeling. Search "FRC robot detection" — multiple labeled datasets with 500+ images exist. Fine-tune on these instead of labeling from scratch. | ~30 hours | `pip install roboflow` |
| **[Supervision](https://github.com/roboflow/supervision)** | Custom tracking + visualization pipeline. Wraps detection → ByteTrack tracking → zone counting → heat map generation in ~50 lines of Python. This is the biggest accelerator. | ~25 hours | `pip install supervision` |
| **[ultralytics](https://github.com/ultralytics/ultralytics)** | Custom training pipeline. YOLOv11 train/export/inference in 5 lines: `yolo train data=frc.yaml model=yolo11n.pt epochs=100` | ~10 hours | `pip install ultralytics` |
| **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** | Video download. Downloads full event playlists in one command. | Already planned | `pip install yt-dlp` |
| **OpenCV homography** | Field calibration. 4-point click interface → pixel-to-meter transform. | ~5 hours | `pip install opencv-python` |

### The Key Insight

With Roboflow dataset + Supervision + ultralytics, your **actual custom code** is:
1. Field calibration (4-point click UI) — ~100 lines
2. Cycle time extraction logic (zone entry/exit timestamps) — ~150 lines
3. Output formatting for The Scout — ~200 lines
4. Orchestration (download → detect → track → analyze → output) — ~200 lines

**Total custom code: ~650 lines of Python.** Everything else is library calls.

---

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Video download | yt-dlp | Open source, handles YouTube playlists |
| Frame extraction | OpenCV (cv2.VideoCapture) | 5 fps sufficient |
| Field calibration | OpenCV (cv2.findHomography) | 4-point click tool |
| Robot detection | ultralytics YOLOv11-nano | Fine-tuned on Roboflow FRC data |
| Tracking + viz | Supervision (ByteTrack) | Detection → tracking → heat maps |
| Database | SQLite | Simple, local, no server |
| Heat maps | matplotlib | Field overlay visualization |
| Match schedule | TBA API v3 | Free, well-documented |
| Orchestration | Python 3.11+ | Ties everything together |

---

## Resolution Analysis

| Stream Quality | Robot Width (px) | Feasible? |
|---------------|------------------|-----------|
| 720p | ~59 px | Detection yes, tracking marginal |
| 1080p | ~88 px | Detection + tracking reliable |
| 4K | ~178 px | Ideal but unnecessary |

**Conclusion:** 1080p is the target. Most FRC streams are 1080p.

---

## Identity Assignment Strategy

The critical challenge: which blob of pixels is which team?

**Pre-match (high confidence):**
1. TBA API provides driver station assignments: Red1=254, Red2=1323, Red3=4567
2. Driver stations are ordered left to right (1, 2, 3)
3. In the pre-match frame, robots are stationary in known starting positions
4. Leftmost red robot = driver station 1 = team 254
5. Identity locked with tracking ID

**During match (tracking continuity):**
1. ByteTrack (via Supervision) maintains identity frame-to-frame
2. Alliance color (red/blue bumpers) prevents cross-alliance confusion
3. Within an alliance, only 3 robots to distinguish
4. Tracking loss recovery: use position history + proximity

---

## Development Phases (Lite)

### Phase E.1: Proof of Concept (20 hours)
- Download one match from YouTube (yt-dlp)
- Manual field calibration (click 4 corners → homography)
- Check Roboflow for existing FRC robot detection dataset
  - If good dataset exists: fine-tune YOLOv11-nano (~2 hours)
  - If not: label ~100 frames on Roboflow, then train (~8 hours)
- Supervision ByteTrack for full match tracking
- Output: 6 position traces overlaid on field diagram
- **If Roboflow dataset is strong, this phase drops to ~12 hours**

### Phase E.2: Event-Scale Batch Processing (30 hours)
- Download full event from YouTube (playlist URL → yt-dlp)
- TBA integration for match schedule + team assignments
- Auto-identity assignment from pre-match frame
- Define scoring zones, extract cycle times per team
- Batch: process 60-80 matches overnight
- Output: per-team database with cycle times + heat maps

### Phase E.3: Integration with The Scout (15 hours)
- Generate per-team heat map images (matplotlib on field diagram)
- Generate cycle time distributions (histogram per team)
- Auto-insert into pre-event report (The Scout S.1)
- One-command workflow: `python the_eye.py --event 2027onto2`

### Phase E.4: Dashboard Visualization (15 hours)
- Simple web viewer (Plotly or Streamlit)
- Team search → heat map + cycle chart + auto path overlay
- Compare two teams side-by-side (alliance selection tool)
- Export one-page PDF per team

### Total: 60-80 hours across 4 phases

---

## What This Enables for The Engine

| Engine Component | What The Eye Adds |
|-----------------|-------------------|
| The Scout | Heat maps and cycle times in pre-event reports |
| Alliance Selection | Complementary scoring zones, not just EPA numbers |
| Match Strategy | Where opponents score from → where to play defense |
| Driver Practice | "Your cycle from the right is 2s slower" with proof |
| Pattern Rules | Validate rules with VISUAL evidence across 100+ matches |

---

## Open Source Potential

This tool doesn't exist in FRC. If Team 2950 builds it and open-sources
it after their first season, the community impact would be enormous.
Every team could generate scouting reports from public video.

This is an Engineering Inspiration Award project.

---

## Future Expansion (Full Eye — Year 2+)

If The Eye Lite proves valuable, expand to the full version:
- Defense interaction tracking (proximity + velocity changes)
- Scoreboard OCR for real-time score attribution
- Live/near-live processing during events
- Custom robot identity model for mid-match re-ID
- Estimated additional: 120-180 hours

---

*Architecture document — The Eye (Lite) | THE ENGINE | Team 2950 The Devastators*
