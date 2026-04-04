# THE ENGINE — Student Training Module 5: Vision & YOLO Pipeline
# Block F.8 (Part 5 of 6) | Audience: Veterans + Rookies | Time: ~55 minutes

---

## What You'll Learn

By the end of this module, you will be able to:
1. Explain what YOLO is and why it's better than color-based detection
2. Trace a camera frame through the full vision pipeline (image → field coordinates)
3. Understand pixel-to-field projection geometry
4. Read the SnapScript Python code and the Java FuelDetectionConsumer
5. Explain confidence filtering and persistence filtering (why both exist)
6. Know how to deploy and update the vision model on a Limelight

---

## Section 1: Why Vision Matters (5 min)

### The Core Problem

The robot needs to know WHERE game pieces are on the field. Without vision, the robot is blind — it can only drive pre-programmed paths and hope game pieces are still where they were at the start of the match.

**With vision:** The robot sees fuel balls in real-time, updates its strategy, and drives to the nearest one. This is what separates a good autonomous from a great one.

### Two Approaches

| Approach | How It Works | Pros | Cons |
|----------|-------------|------|------|
| **HSV Color** | Filter image by color range | Simple, fast, no training needed | Breaks with lighting changes, false positives from same-colored objects |
| **YOLO Neural Network** | Trained model recognizes objects by shape + color + context | Robust to lighting, very few false positives, learns from examples | Needs training data, heavier computation |

**The Engine uses YOLO as primary, HSV as fallback.** If the YOLO model fails to load on the Limelight, the system automatically falls back to HSV color detection.

---

## Section 2: What Is YOLO? (10 min)

### YOLO = "You Only Look Once"

YOLO is a family of neural networks designed for real-time object detection. The name means the network processes the entire image in **one pass** (unlike older methods that scanned the image in patches).

### Our Model: Wave Robotics YOLOv11n

| Spec | Value |
|------|-------|
| Architecture | YOLOv11n (the "n" = nano, smallest/fastest variant) |
| Parameters | 2.59 million |
| Compute | 6.4 GFLOPs |
| Input | 640 × 640 pixels, BGR color |
| Output | Up to 8,400 candidate detections |
| Classes | 1 ("object" = fuel ball) |
| Training accuracy | 93-97% on Wave Robotics dataset |
| File size | ~10 MB (ONNX format) |
| File | `tools/wave_fuel_detector.onnx` |

### How YOLO Works (Simplified)

```
INPUT IMAGE (640×640)
        │
        ▼
┌──────────────────┐
│  NEURAL NETWORK  │   Millions of tiny math operations
│  (101 layers)    │   learned from training images
└──────────────────┘
        │
        ▼
OUTPUT: 8,400 candidate boxes
Each box = [center_x, center_y, width, height, confidence]

        │
        ▼
CONFIDENCE FILTER (keep only > 80%)
        │
        ▼
NMS (Non-Max Suppression)
Remove overlapping boxes — keep the best one
        │
        ▼
FINAL: 0-8 confirmed fuel detections
```

### Non-Max Suppression (NMS)

When YOLO sees a fuel ball, it often produces 5-10 overlapping boxes for the same ball. NMS fixes this:

```
Before NMS:                    After NMS:
┌───────┐                     ┌───────┐
│ ┌───┐ │  conf=0.95          │       │  conf=0.95 (kept!)
│ │   │ │  conf=0.88          │       │
│ └───┘ │  conf=0.82          └───────┘
└───────┘

Three boxes for one ball  →   One box for one ball
```

The algorithm: if two boxes overlap by more than 45% (our `NMS_IOU_THRESHOLD`), keep the higher-confidence one and discard the other.

> **Rookie Checkpoint:** IOU stands for "Intersection Over Union" — the percentage of overlap between two boxes. If IOU > 0.45, they're probably detecting the same object.

---

## Section 3: The Full Vision Pipeline (15 min)

### Overview

```
Limelight Camera                         roboRIO (Java)
──────────────────                       ─────────────────

1. Capture frame (640×480 BGR)
        │
2. SnapScript Python runs:
   ├── Resize to 640×640
   ├── YOLO inference (ONNX)
   ├── NMS filter
   ├── Pixel → field projection
   └── Build llpython array
        │
3. Publish to NetworkTables
   llpython = [numFuel, x1,y1,c1, ...]
                        │
                        ▼
                    4. FuelDetectionConsumer
                       ├── Confidence filter (≥80%)
                       ├── Persistence filter (3 frames)
                       └── Output: List<Translation2d>
                                │
                                ▼
                    5. GameState → Strategy → Drive
```

### Step 1: Camera Capture

The Limelight 4 camera captures 640×480 pixel frames at up to 90 FPS. Each pixel has 3 color channels (Blue, Green, Red = BGR).

### Step 2: SnapScript Processing

**File:** `tools/snapscript_fuel_detector.py`

The SnapScript is Python code that runs ON the Limelight processor (not on the roboRIO). The entry point is:

```python
def runPipeline(image, llrobot):
    """
    Called every camera frame by the Limelight.

    image  : BGR uint8 image (640×480)
    llrobot: double[] sent FROM the robot via NetworkTables
             [robotX, robotY, robotHeadingRad, zoneMinX, zoneMinY, zoneMaxX, zoneMaxY]

    Returns: (largestContour, annotatedImage, llpython)
    """
```

**The robot tells the Limelight where it is** via `llrobot`. This is critical — the Limelight needs the robot's position and heading to convert pixel detections to field coordinates.

#### YOLO Inference

```python
def _run_yolo(image_bgr):
    # 1. Preprocess
    img = cv2.resize(image_bgr, (640, 640))     # Resize to model input
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)   # BGR → RGB
    img = img.astype(np.float32) / 255.0         # Normalize 0-255 → 0.0-1.0
    img = np.transpose(img, (2, 0, 1))           # HWC → CHW (channels first)
    img = np.expand_dims(img, axis=0)            # Add batch dimension

    # 2. Run model
    raw = _SESSION.run(None, {_INPUT_NAME: img})[0]  # Shape: (1, 5, 8400)
    preds = raw[0].T                                  # Shape: (8400, 5)

    # 3. Filter by confidence
    # 4. NMS to remove duplicates
    # 5. Return [(cx_px, cy_px, conf), ...]
```

> **Veteran Note:** The model input is 640×640 but the camera frame is 640×480. The resize stretches the image slightly. This is standard practice — YOLO is trained to handle this.

#### Pixel-to-Field Projection

This is the most interesting part. How do you convert "pixel (320, 400) in the image" to "field position (5.2, 3.1) meters"?

**File:** `tools/snapscript_fuel_detector.py`, function `_pixel_to_field()`

The geometry uses the camera's known position and angle:

```
Side view:
                                    Camera
                                   /  │ (angle down)
                                  /   │
                                 /    │  height = 0.50m
                                /     │
    ───────────────────────────●──────┴──── Field carpet
                               ↑
                          Game piece here
                          (distance = height / tan(depression_angle))
```

**Step by step:**

```python
# 1. How far left/right is the object from camera center?
angle_h = ((cx_px - 320) / 640) * FOV_horizontal   # radians

# 2. How far up/down is the object from camera center?
angle_v = ((240 - cy_px) / 480) * FOV_vertical      # radians

# 3. Total angle looking down at the object
total_depression = -(camera_pitch + angle_v)

# 4. Distance along the ground (trigonometry!)
distance = camera_height / tan(total_depression)

# 5. Robot-relative position (forward = +x, left = +y)
obj_x_robot = distance * cos(angle_h)
obj_y_robot = distance * sin(angle_h)

# 6. Rotate to field-relative using robot heading
field_x = robot_x + obj_x_robot * cos(heading) - obj_y_robot * sin(heading)
field_y = robot_y + obj_x_robot * sin(heading) + obj_y_robot * cos(heading)
```

**Camera parameters (Limelight 4 defaults):**

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `CAMERA_FOV_H_DEG` | 63.3° | How wide the camera sees |
| `CAMERA_FOV_V_DEG` | 49.7° | How tall the camera sees |
| `CAMERA_HEIGHT_M` | 0.50m | Camera height above carpet |
| `CAMERA_PITCH_DEG` | -15.0° | Tilted 15° downward |

**Safety checks:** The function returns `None` if:
- Object is above the horizon (can't project to floor)
- Projected distance < 0.2m or > 12.0m (unreasonable range)

#### Zone Filtering

After projection, detections outside the valid zone are discarded:

```python
if not _in_zone(fx, fy, zone_x0, zone_y0, zone_x1, zone_y1):
    continue
```

The robot sends the zone boundaries in `llrobot[3:7]`. Default is the entire field (0,0) to (16.46, 8.23).

#### Building the Output Array

```python
# Format: [numFuel, fx1, fy1, conf1, fx2, fy2, conf2, ...]
llpython = [float(len(fuel_detections))]
for fx, fy, conf in fuel_detections:
    llpython.extend([fx, fy, conf])

# Pad to fixed width: 1 + 8 * 3 = 25 elements
while len(llpython) < 25:
    llpython.append(0.0)
```

**Why fixed width?** NetworkTables arrays must have predictable sizes. Zero-padding means the Java parser always sees exactly 25 elements, whether there are 0 or 8 detections.

### Step 3: NetworkTables Transport

The `llpython` array is automatically published by the Limelight to NetworkTables. The roboRIO reads it every robot loop cycle (20ms).

### Step 4: FuelDetectionConsumer (Java Side)

**File:** `src/main/java/frc/robot/subsystems/FuelDetectionConsumer.java`

The Java side applies TWO additional filters:

#### Filter 1: Confidence Gate (≥ 80%)

```java
if (conf >= Constants.Pathfinding.kFuelConfidenceThreshold) {  // 0.80
    result.add(new Translation2d(x, y));
}
```

Wait — didn't we already filter at 80% in Python? Yes! But the Python filter runs on raw model output. By the time data crosses NetworkTables, we filter again to be safe.

#### Filter 2: Persistence (3 Consecutive Frames)

This is the critical innovation. A single detection might be noise. **Three consecutive frames at the same position confirms it's real.**

```
Frame 1: Fuel detected at (5.2, 3.1) → Candidate created, count = 1
Frame 2: Fuel detected at (5.18, 3.08) → Matches candidate (within 0.5m), count = 2
Frame 3: Fuel detected at (5.21, 3.12) → Matches candidate, count = 3 → CONFIRMED!
Frame 4: No detection near (5.2, 3.1) → Candidate DROPPED (reset)
```

**The matching logic:**

```java
for (Candidate candidate : candidates) {
    // Find the closest new detection within 0.5m tolerance
    for (int i = 0; i < newDetections.size(); i++) {
        double dist = candidate.position.getDistance(newDetections.get(i));
        if (dist < 0.5 && dist < bestDist) {  // MATCH_TOLERANCE_M = 0.5
            bestIdx = i;
            bestDist = dist;
        }
    }
    if (matched) {
        candidate.position = newDetections.get(bestIdx);  // Update position
        candidate.consecutiveFrames++;                     // Increment counter
    }
    // Unmatched candidates are DROPPED (not carried forward)
}
```

> **Why 0.5m tolerance?** The robot is moving, and vision has some jitter. The same fuel ball might project to slightly different positions across frames. 0.5m is wide enough to track a real ball but narrow enough to not confuse two separate balls.

### Step 5: Output to Strategy

```java
List<Translation2d> confirmed = consumer.getDetectedFuelPositions();
// Only returns detections with consecutiveFrames >= 3
// Capped at 8 detections maximum

GameState state = new GameState()
    .withDetectedFuel(confirmed);

strategy.evaluateTargets(state);  // → picks the best fuel to collect
```

---

## Section 4: The HSV Fallback (5 min)

If the ONNX model fails to load (file missing, onnxruntime not installed, etc.), the SnapScript falls back to HSV color thresholding:

```python
def _run_hsv(image_bgr):
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (20, 100, 100), (35, 255, 255))  # Yellow range
    # Erode + dilate to remove noise
    # Find contours
    # Filter by area (> 300 px) and circularity (> 0.5)
    # Return [(cx, cy, conf), ...]
```

**HSV means Hue-Saturation-Value** — a color space where hue = color, saturation = intensity, value = brightness. Yellow fuel balls have hue 20-35 in the HSV space.

**Why it's a fallback, not primary:**
- Changes with arena lighting (competition fields have spotlights)
- Yellow sponsor logos, yellow shirts, and yellow tape trigger false positives
- Can't distinguish a fuel ball from a yellow water bottle

**Why we keep it:** Because having SOME detection is better than NO detection. If someone forgets to upload the ONNX model, the robot still works (just less reliably).

---

## Section 5: Deployment Guide (5 min)

### How to Deploy the Vision Pipeline to a Limelight

**Step 1:** Connect to the Limelight web interface
```
http://10.29.50.11:5801    (for team 2950)
```

**Step 2:** Upload the ONNX model
- Go to **Manage** tab → **File Upload**
- Upload `tools/wave_fuel_detector.onnx`
- It goes to `/home/limelight/wave_fuel_detector.onnx`

**Step 3:** Upload the SnapScript
- Go to **Pipeline** tab
- Select Pipeline 1 (keep Pipeline 0 for AprilTags)
- Paste the contents of `tools/snapscript_fuel_detector.py`
- Save

**Step 4:** Verify
- Point the camera at a fuel ball
- The annotated image should show yellow circles with "FUEL 95%" labels
- Check NetworkTables for the `llpython` array

### Pipeline Switching

The robot code switches between AprilTag (Pipeline 0) and YOLO (Pipeline 1):

```java
// In VisionSubsystem:
vision.setAprilTagPipeline();   // Pipeline 0 — for pose estimation
vision.setNeuralPipeline();      // Pipeline 1 — for fuel detection
```

Typically: AprilTag runs during most of the match (for odometry), and neural pipeline is activated when actively searching for game pieces.

---

## Section 6: Hands-On Exercises

### Exercise A: Trace the Pipeline (All Levels, 10 min)

Given this scenario, trace through each step:

```
Robot position: (3.0, 4.0), heading: 0.0 radians (facing +X)
Camera sees a fuel ball at pixel (400, 350) with confidence 0.92
Camera height: 0.50m, pitch: -15°, FOV_H: 63.3°, FOV_V: 49.7°
```

**Step 1:** Calculate horizontal angle from center
```
angle_h = ((400 - 320) / 640) × 63.3° = ?
```

**Step 2:** Calculate vertical angle from center
```
angle_v = ((240 - 350) / 480) × 49.7° = ?
```

**Step 3:** Calculate total depression angle
```
total_depression = -((-15°) + angle_v) = ?
```

**Step 4:** Calculate ground distance
```
distance = 0.50 / tan(total_depression) = ?
```

**Step 5:** Calculate robot-relative position
```
obj_x = distance × cos(angle_h) = ?
obj_y = distance × sin(angle_h) = ?
```

**Step 6:** Rotate to field-relative (heading = 0, so cos=1, sin=0)
```
field_x = 3.0 + obj_x = ?
field_y = 4.0 + obj_y = ?
```

**Answers:**
1. angle_h = (80/640) × 63.3° = 7.91° = 0.138 rad
2. angle_v = (-110/480) × 49.7° = -11.39° = -0.199 rad
3. total_depression = -((-0.262) + (-0.199)) = 0.461 rad = 26.4°
4. distance = 0.50 / tan(26.4°) = 0.50 / 0.497 = **1.006m**
5. obj_x = 1.006 × cos(0.138) = 0.996m, obj_y = 1.006 × sin(0.138) = 0.139m
6. field_x = 3.0 + 0.996 = **3.996m**, field_y = 4.0 + 0.139 = **4.139m**

The fuel ball is about 1 meter ahead and slightly to the right of the robot.

---

### Exercise B: Array Parsing (All Levels, 5 min)

The roboRIO receives this `llpython` array from NetworkTables:

```
[3.0, 5.2, 3.1, 0.95, 8.1, 2.0, 0.72, 4.5, 4.5, 0.88, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
```

Parse it:
1. How many fuel detections? (index 0)
2. List each detection's (x, y, confidence)
3. Which detections pass the 80% confidence filter?
4. After 3 frames of seeing detections 1 and 3 (but not 2), which become confirmed?

**Answers:**
1. **3** fuel detections
2. Fuel 1: (5.2, 3.1, 0.95), Fuel 2: (8.1, 2.0, 0.72), Fuel 3: (4.5, 4.5, 0.88)
3. Fuel 1 (0.95 ≥ 0.80) and Fuel 3 (0.88 ≥ 0.80) pass. **Fuel 2 (0.72) is dropped.**
4. Fuel 1 and Fuel 3 become confirmed (3 consecutive frames). Fuel 2 was never a candidate (failed confidence).

---

### Exercise C: Persistence Scenarios (All Levels, 5 min)

For each frame sequence, determine which fuel cells are confirmed after frame 4:

**Scenario 1: Steady detection**
```
Frame 1: Fuel at (5.0, 3.0) conf=0.90
Frame 2: Fuel at (5.05, 2.98) conf=0.91
Frame 3: Fuel at (4.98, 3.02) conf=0.89
Frame 4: Fuel at (5.01, 3.01) conf=0.92
```

**Scenario 2: Flickering detection**
```
Frame 1: Fuel at (5.0, 3.0) conf=0.90
Frame 2: Nothing detected
Frame 3: Fuel at (5.0, 3.0) conf=0.88
Frame 4: Fuel at (5.02, 2.99) conf=0.91
```

**Scenario 3: Two fuel cells, one moves**
```
Frame 1: Fuel A at (5.0, 3.0), Fuel B at (8.0, 5.0)
Frame 2: Fuel A at (5.0, 3.0), Fuel B at (8.6, 5.0)  ← B moved 0.6m
Frame 3: Fuel A at (5.0, 3.0), Fuel B at (9.2, 5.0)  ← B moved another 0.6m
Frame 4: Fuel A at (5.0, 3.0), Fuel B at (9.8, 5.0)
```

**Answers:**
1. **Confirmed.** All positions within 0.5m of each other. Count reaches 4 by frame 4.
2. **Not confirmed.** Frame 2 breaks the streak. Frame 3 starts a new candidate (count=1). Frame 4 matches (count=2). Only 2 consecutive — needs one more frame.
3. **Fuel A: Confirmed** (steady). **Fuel B: NOT confirmed** — each frame B moves 0.6m, which exceeds the 0.5m match tolerance. Each frame starts a NEW candidate for B.

---

### Exercise D: Camera Geometry Drawing (Rookies, 5 min)

On paper, draw the side-view diagram:

1. Draw a horizontal line (the field carpet)
2. Draw a vertical line 0.50m tall (the camera mount)
3. Draw the camera at the top, angled 15° downward
4. Draw a fuel ball on the carpet 1.5m ahead of the robot
5. Draw the line from the camera through the ball to the carpet
6. Label the depression angle

**Key insight:** Objects farther away appear HIGHER in the image (closer to the horizon). Objects close to the robot appear LOW in the image (near the bottom). This is why `cy_px` matters — the vertical pixel position tells you how far away the object is.

---

### Exercise E: What Would Break? (Discussion, All Levels)

1. **The camera gets bumped and is now at -25° pitch instead of -15°.** What happens to distance calculations?
   - All distances would be underestimated (the camera thinks objects are closer than they are). Fuel positions would be projected too close to the robot.

2. **Someone puts a yellow traffic cone on the field.** How does each detector handle it?
   - HSV: Detects it as fuel (it's yellow and circular-ish). False positive!
   - YOLO: Probably ignores it — trained on fuel balls specifically, not cones. But might detect if the cone looks similar enough. This is where the 3-frame persistence helps.

3. **The robot's odometry drifts by 0.5m.** How does this affect vision?
   - The `llrobot` array sends the wrong position. All pixel-to-field projections are offset by ~0.5m. The fuel positions reported to the strategy engine are wrong by 0.5m. This is why accurate odometry matters!

---

## Key Vocabulary

| Term | Definition |
|------|-----------|
| **YOLO** | "You Only Look Once" — neural network for real-time object detection |
| **ONNX** | Open Neural Network Exchange — standard model format that runs on any hardware |
| **Inference** | Running data through a trained model to get predictions |
| **Confidence** | Model's certainty that a detection is real (0.0 to 1.0) |
| **NMS** | Non-Max Suppression — removes duplicate detections of the same object |
| **IOU** | Intersection Over Union — measures how much two boxes overlap |
| **HSV** | Hue-Saturation-Value — a color space useful for color filtering |
| **Persistence** | Requiring multiple consecutive frames to confirm a detection |
| **SnapScript** | Python code that runs on the Limelight's onboard processor |
| **llpython** | The NetworkTables array the Limelight sends to the roboRIO |
| **llrobot** | The NetworkTables array the roboRIO sends to the Limelight |
| **Pipeline** | A Limelight configuration. Pipeline 0 = AprilTag, Pipeline 1 = YOLO |

---

## What's Next

**Module 6** covers **Simulation & Testing** — how to test all of this without a physical robot, and how our build quality gates catch bugs before they reach the competition field.

---

*Module 5 of 6 | THE ENGINE Student Training | Team 2950 The Devastators*
