# THE ENGINE — YOLO Game Piece Detection Guide
# FRC Team 2950 — The Devastators
# ═══════════════════════════════════════════════════════════════════════════════

## Quick Start (2026 Season — Wave Robotics Model Already Integrated)

The Wave Robotics YOLOv11n model is already wired into The Engine. You do NOT
need to train a new model for the 2026 season unless you want to improve it.

**To deploy:**
1. `tools/wave_fuel_detector.onnx` is already in the repo (10.1 MB, opset 12).
2. Upload it to the Limelight via the web UI (Manage tab → File Upload → `/home/limelight/`).
3. Upload `tools/snapscript_fuel_detector.py` as Pipeline 1.
4. Done. The robot will use it automatically during autonomous.

---

## Wave Robotics YOLOv11n Model — Technical Details

Sourced from [Chief Delphi post by Wave Robotics (Team 2826)](https://www.chiefdelphi.com/t/introducing-wave-robotics-yolov11-model-for-rebuilt/512701).
Trained on 60 labeled images of 2026 game fuel balls.

| Property           | Value                                  |
|--------------------|----------------------------------------|
| Architecture       | YOLOv11-nano                          |
| Input size         | 640 × 640 px                          |
| Parameters         | 2.59 M (2,582,347)                    |
| GFLOPs             | 6.4                                   |
| Layers (fused)     | 101                                   |
| Classes            | 1 — `object` (fuel ball)              |
| Confidence range   | 93–97% on training images             |
| PyTorch file       | `~/Downloads/PyTorch_model.pt` (5.2 MB)|
| ONNX file (repo)   | `tools/wave_fuel_detector.onnx` (10.1 MB, opset 12) |
| Dataset            | 60 images, YOLO label format, Label Studio annotations |
| Label class        | `Fuel?` (class 0), normalized bounding boxes |

**Important:** The model detects fuel balls ONLY. There is no opponent robot class.
Opponent avoidance uses a different data source (see `FullAutonomousCommand.java`).

### ONNX export command (already done, for reference)
```python
from ultralytics import YOLO
model = YOLO("PyTorch_model.pt")
model.export(format="onnx", imgsz=640, simplify=True, opset=12, dynamic=False, batch=1)
```

---

## How Detection Works (Pipeline Overview)

```
Camera frame (640×480 BGR)
        │
        ▼
snapscript_fuel_detector.py   ← runs on Limelight hardware
  • YOLOv11n ONNX inference (640×640 input, normalized)
  • NMS with IoU threshold 0.45
  • Confidence filter ≥ 0.80
  • Pixel → field-relative projection (camera geometry + robot pose)
  • Zone filter (robot-reported detection zone)
        │
        ▼
llpython NT4 array: [numFuel, fx1, fy1, conf1, ...]   ← field meters
        │
        ▼
FuelDetectionConsumer.java   ← runs on roboRIO at 50 Hz
  • 80% confidence gate (secondary)
  • 3-frame persistence (prevents phantom detections)
  • Nearest-neighbor tracking across frames
        │
        ▼
VisionSubsystem.getFuelPositions()   ← confirmed fuel positions
        │
        ├── DriveToGamePieceCommand (teleop assist)
        └── FullAutonomousCommand (autonomous loop)
```

---

## Confidence Thresholds

| Threshold       | Where Set                              | Value  |
|-----------------|----------------------------------------|--------|
| SnapScript NMS  | `snapscript_fuel_detector.py`          | 0.80   |
| Java consumer   | `Constants.Pathfinding.kFuelConfidenceThreshold` | 0.80 |
| Persistence     | `Constants.Pathfinding.kFuelPersistenceFrames`   | 3     |
| Max detections  | `Constants.Pathfinding.kMaxFuelDetections`       | 8     |

If you see too many false positives at competition: raise SnapScript threshold to 0.85.
If you're missing real fuel: lower to 0.75 (but watch for field element false positives).

---

## What to Do if the Model Misses Fuel at Competition

The SnapScript has a built-in HSV color fallback that activates automatically if the
ONNX model fails to load. You can also manually switch to this fallback:

1. Open the Limelight web UI during a practice match.
2. Go to the SnapScript pipeline settings.
3. Temporarily set `CONFIDENCE_THRESHOLD = 0.70` and redeploy.

For a real fix: capture 20–30 images under the venue's lighting and fine-tune or
retrain (see **Retraining** section below).

---

## Opponent Detection — Status

**The Wave model does not detect opponents.** The avoidance system in
`FullAutonomousCommand` uses a supplier that returns opponent positions. In the
current build, this supplier returns an empty list. Options for the future:

1. **AprilTag-based opponent tracking** — read the opponent alliance AprilTag IDs
   from the FMS and use their known field positions as opponent locations.
2. **Fine-tune the Wave model** with a second class (`robot`) using labeled images
   of robots. ~50 images is enough for YOLOv11n.
3. **Separate Limelight** — dedicate one camera to fuel (this model) and another
   to opponent detection via a different model.

---

## Retraining or Fine-Tuning (Optional, Offseason)

### When to retrain
- Game piece changes shape, color, or size for a new season.
- Detection accuracy drops below 85% at competition lighting.
- You want to add an opponent robot class.

### Dataset
The Wave Robotics dataset is available in `~/Downloads/Dataset for ball training/`:
- 60 labeled images in YOLO format (`class_id cx cy w h`, normalized [0,1])
- Class 0 = `Fuel?`
- Annotations created with Label Studio

### Fine-tune from Wave checkpoint
```bash
pip install ultralytics
yolo train model=PyTorch_model.pt data=your_dataset.yaml epochs=50 imgsz=640
```
This continues training from the Wave model weights — you need far fewer images
than training from scratch.

### Export after training
```bash
yolo export model=runs/detect/train/weights/best.pt format=onnx imgsz=640 simplify=True opset=12
```
Then replace `tools/wave_fuel_detector.onnx` in the repo and redeploy.

### Labeling new images
1. Use [Label Studio](https://labelstud.io/) (free, self-hosted) or Roboflow (free tier).
2. Draw bounding boxes. Class name: `fuel` (or `Fuel?` to match existing dataset).
3. Export in YOLO format.
4. Mix with existing 60 images for fine-tuning.

---

## Model Performance Reference

| Model          | Params | FLOPs | Limelight 4 Speed | Notes                          |
|----------------|--------|-------|-------------------|--------------------------------|
| YOLOv11-nano   | 2.6M   | 6.4G  | 30+ fps           | **Current (Wave model)**       |
| YOLOv8-nano    | 3.2M   | 8.7G  | 25+ fps           | Previous recommendation        |
| YOLOv11-small  | 9.4M   | 21.5G | 15+ fps           | Use only if nano accuracy poor |

YOLOv11-nano is the correct choice for FRC. One or two classes don't need a larger model.

---

## Offseason Training Exercise (for students)

This is an excellent fall training module:
1. Give students 10 random objects (balls, cups, boxes).
2. Each student captures 20 images of their assigned object.
3. Label in Label Studio or Roboflow (teaches bounding box annotation).
4. Fine-tune from the Wave YOLOv11n checkpoint (teaches transfer learning).
5. Export ONNX, deploy to Limelight (teaches embedded AI deployment).
6. Competition: which student's model detects most accurately?

Total time: 2–3 hours. Students learn the complete ML deployment pipeline
with zero math prerequisites. They'll be ready to fine-tune game-specific
models on kickoff day.
