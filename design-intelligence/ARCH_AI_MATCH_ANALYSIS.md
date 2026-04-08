# THE ENGINE — AI Match Analysis System
# Codename: "The Eye"
# Architecture & Roadmap
# Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════

## Vision

Every FRC match is live-streamed. The schedule is published with exact
team assignments and driver station positions. The field layout is
identical at every event. What if an AI watched every match at every
event and built a complete performance profile for every team — scoring
locations, cycle times, auto paths, climb reliability, defensive
tendencies — automatically?

That is The Eye. It turns public video streams into competitive
intelligence at a scale no human scouting operation can match.

---

## What It Produces (Per Team, Per Match)

| Data Point | How It's Extracted |
|-----------|-------------------|
| Starting position (x, y) | Pre-match frame + TBA driver station assignment |
| Auto path | Frame-by-frame position tracking during first 20s |
| Auto scoring events | Position + timestamp when robot enters scoring zone |
| Teleop scoring locations | Heat map of where the robot scores from |
| Cycle times | Time between consecutive scoring events |
| Climb attempt/success/level | Robot position on Tower + time to complete |
| Defense interactions | Proximity + velocity change between opponent robots |
| Scoring consistency | Standard deviation of cycle times across matches |

## Competitive Advantage

| Without The Eye | With The Eye |
|----------------|-------------|
| Manual scouting — subjective, inconsistent | AI scouting — objective, complete |
| Only matches you physically attend | Every match at every event all season |
| "They're pretty fast" | "4.2s average cycle, 0.6s slower from the right side" |
| "Their climber is okay" | "Climber succeeds 80%, fails when contested" |
| Alliance picks based on EPA + gut feeling | Alliance picks based on complementary scoring zones |
| Defense strategy based on reputation | Defense targeting their weakest field positions |

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    DATA SOURCES                      │
│  TBA API: schedule, teams, driver stations, scores  │
│  YouTube/Twitch: match video streams (1080p)        │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              STREAM CAPTURE (Layer 1)                │
│  YouTube-dl / yt-dlp: download match VODs           │
│  Frame extraction at 5 fps (sufficient for FRC)     │
│  Match segmentation using TBA schedule timestamps   │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│           FIELD CALIBRATION (Layer 2)                │
│  One-time per event venue/camera angle              │
│  Map pixel coords → field coords (meters)           │
│  Known landmarks: Hub (47"x47"), Tower, Bumps,      │
│    Trenches, field corners, Alliance Walls           │
│  Homography transform (4+ point correspondence)     │
│  Field is always 54ft × 27ft — geometry is known    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│        ROBOT DETECTION + TRACKING (Layer 3)          │
│                                                      │
│  Detection: YOLOv11 trained on FRC robots            │
│    - 2 classes: red_bumper, blue_bumper              │
│    - ~200 labeled training frames needed             │
│    - 1080p gives ~88px per robot (sufficient)        │
│                                                      │
│  Identity Assignment (frame 0, pre-match):           │
│    - Robots are stationary in starting positions     │
│    - TBA says Red1=254, Red2=1323, Red3=4567        │
│    - Leftmost red robot = Red1 = team 254            │
│    - Identity locked for match duration              │
│                                                      │
│  Tracking (frames 1-N):                              │
│    - ByteTrack or DeepSORT multi-object tracker     │
│    - Maintains identity through motion continuity    │
│    - Alliance color separates red vs blue            │
│    - Within alliance: nearest-neighbor matching      │
│    - Re-ID on tracking loss via position history     │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│           EVENT DETECTION (Layer 4)                   │
│                                                      │
│  Scoring Events:                                     │
│    - Robot enters Hub scoring zone → cycle end       │
│    - Scoreboard OCR confirms point change            │
│    - Score delta attributed to nearest robot          │
│                                                      │
│  Climb Events:                                       │
│    - Robot position on Tower structure               │
│    - Height estimation from pixel position           │
│    - Success = robot elevated at match end            │
│                                                      │
│  Defense Events:                                     │
│    - Two opponent-colored robots within 1m           │
│    - Velocity change (deceleration = being blocked)  │
│    - Duration of contact event                       │
│                                                      │
│  Auto vs Teleop:                                     │
│    - TBA provides match period timestamps            │
│    - First 20s = auto, remaining = teleop            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│            OUTPUT DATABASE (Layer 5)                  │
│                                                      │
│  Per team per match:                                 │
│    team_number: int                                  │
│    event_key: string                                 │
│    match_key: string                                 │
│    starting_position: {x, y}                         │
│    auto_path: [{time, x, y}, ...]                   │
│    auto_scores: [{time, x, y, points}, ...]         │
│    teleop_scores: [{time, x, y, points}, ...]       │
│    cycle_times: [float, ...]                         │
│    avg_cycle_time: float                             │
│    climb: {attempted, level, success, duration}      │
│    defense_given: [{time, target, x, y, dur}, ...]  │
│    defense_received: [{time, source, x, y, dur}]    │
│                                                      │
│  Aggregated across matches:                          │
│    scoring_heat_map: 2D frequency grid               │
│    auto_consistency: std_dev of auto paths           │
│    cycle_time_trend: improving or degrading          │
│    climb_success_rate: float                         │
│    preferred_scoring_side: left/right/center         │
│    defense_vulnerability_zones: [(x,y), ...]         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│           VISUALIZATION (Layer 6)                    │
│                                                      │
│  Heat Maps: where does each team score from?         │
│  Auto Overlay: 10 matches of the same team's auto   │
│  Cycle Distribution: histogram per team              │
│  Weakness Map: where they get defended successfully  │
│  Scouting Report: one-page per team for drive coach  │
│  Alliance Simulator: complementary zone analysis     │
└─────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Video download | yt-dlp | Open source, handles YouTube + Twitch |
| Frame extraction | OpenCV (cv2.VideoCapture) | 5 fps sufficient |
| Field calibration | OpenCV (cv2.findHomography) | 4-point perspective transform |
| Robot detection | YOLOv11-nano or YOLOv11-small | ~200 labeled frames to train |
| Multi-object tracking | ByteTrack | State-of-the-art, open source |
| Scoreboard OCR | Tesseract or PaddleOCR | Fixed position, high contrast text |
| Database | SQLite or PostgreSQL | Simple for local, Postgres for shared |
| Heat maps | matplotlib or Plotly | Field overlay visualization |
| Match schedule + teams | TBA API v3 | Free, well-documented |
| Orchestration | Python 3.11+ | Ties everything together |

---

## Resolution Analysis

| Stream Quality | Field Width (px) | Robot Width (px) | Bumper Number (px) | Feasible? |
|---------------|-----------------|------------------|-------------------|-----------|
| 720p | 1280 | ~59 | ~15 | Detection yes, number OCR no |
| 1080p | 1920 | ~88 | ~22 | Detection yes, number OCR borderline |
| 4K | 3840 | ~178 | ~44 | Detection yes, number OCR yes |

Conclusion: 1080p is sufficient for detection + tracking. 4K enables
mid-match re-identification via bumper number OCR but is not required
if tracking is maintained from starting positions.

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
1. ByteTrack maintains identity frame-to-frame via motion prediction
2. Alliance color (red/blue bumpers) prevents cross-alliance confusion
3. Within an alliance, only 3 robots to distinguish
4. Tracking loss recovery: use position history + velocity to re-match

**Failure modes:**
- Two same-alliance robots collide and overlap → track both through collision
  using velocity prediction, re-assign on separation
- Robot fully occluded by field element → maintain last-known position,
  re-acquire when visible, match by proximity to predicted position
- Camera angle change → re-calibrate homography (rare during match)

---

## Development Phases

### Phase 1: Proof of Concept
- Process a single recorded match (downloaded MP4)
- Manual field calibration (click 4 corners)
- YOLOv11 detection of robots (red vs blue bumpers)
- ByteTrack tracking for full match
- Output: 6 position traces overlaid on field diagram
- Estimated effort: 40 hours

### Phase 2: Event Detection
- Add scoring zone detection (robot enters Hub area)
- Add scoreboard OCR to confirm score changes
- Add climb detection (robot on Tower at match end)
- Process 10 matches from one event
- Output: per-team scoring events + cycle times
- Estimated effort: 60 hours

### Phase 3: Automation & Scale
- Auto-calibration using detected field landmarks
- TBA integration for match schedule + team assignments
- Batch processing: download + analyze full event (60-80 matches)
- Auto-generate heat maps and scouting reports
- Output: complete event database + visualizations
- Estimated effort: 80 hours

### Phase 4: Competitive Tool
- Live/near-live processing during events
- Pre-event reports from analyzing opponents' previous events
- Drive coach dashboard (tablet-friendly)
- Alliance selection advisor using zone complementarity
- Integration with The Engine's scouting bot architecture
- Estimated effort: 80 hours

### Total: ~260 hours across 4 phases
### Timeline: TBD — leave open based on team capacity and priorities

---

## Training Data Requirements

| Model | Training Images | Source | Annotation |
|-------|----------------|--------|-----------|
| Robot detector (red/blue) | ~200 frames | FRC match VODs from YouTube | Bounding boxes, 2 classes |
| Scoreboard OCR | ~50 frames | Various stream overlays | Text regions |
| Field landmark detector | ~30 frames | Different event venues | Keypoints |

Training data can be collected from freely available match VODs on YouTube.
Label with Roboflow (free tier) or Label Studio (self-hosted).

---

## What This Enables for The Engine

| Engine Component | What The Eye Adds |
|-----------------|-------------------|
| Prediction Engine | Validate rules with VISUAL evidence, not just EPA |
| Scouting Bot | Ground truth data instead of manual observations |
| Match Strategy | Heat maps showing exactly where to play defense |
| Alliance Selection | Complementary scoring zones, not just EPA numbers |
| Driver Practice | "Your cycle from the left is 2s slower" with proof |
| Post-Match Debrief | Visual replay with annotated scoring events |
| Pattern Rules | New rules discovered from watching 1000+ matches |

---

## Open Source Potential

This tool doesn't exist in FRC. If Team 2950 builds it and open-sources
it after their first season using it, the community impact would be
enormous. Every team could generate scouting reports from public video.
Manual scouting (students watching matches and writing on tablets)
would be supplemented by AI analysis covering every match they can't
physically watch.

This is an Engineering Inspiration Award project. It advances the entire
FRC community's access to competition intelligence.

---

*Architecture document — The Eye | THE ENGINE | Team 2950 The Devastators*
