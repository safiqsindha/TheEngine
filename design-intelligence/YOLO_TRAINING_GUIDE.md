# THE ENGINE — YOLO Game Piece Detection Guide
# Train and deploy a custom neural network on Limelight 4 Hailo accelerator
# ═══════════════════════════════════════════════════════════════════════════════

## Overview

This guide replaces HSV color thresholding (SnapScript) with a trained YOLOv8-nano
neural network for game piece detection. The YOLO model runs on the Limelight 4's
Hailo-8 accelerator at 30+ fps and is robust to lighting changes that break color
thresholding at competition.

**Time from zero to deployed model: 4-6 hours.**
**Images needed: 50-200 (with augmentation → 500+).**
**Cost: $0 (Roboflow free tier handles everything).**

## Step 1: Capture Training Images (1 hour)

### What you need
- Limelight 4 (or any webcam — the images don't have to come from the Limelight)
- 5-10 actual game pieces
- Access to a practice field or large room

### Image capture checklist
- [ ] Game piece on field carpet, straight-on view, 3 distances (2ft, 5ft, 10ft)
- [ ] Game piece partially behind a field element (partial occlusion)
- [ ] Game piece near a wall or scoring target
- [ ] Game piece in shadow
- [ ] Game piece under bright overhead lights
- [ ] Game piece with another robot in frame
- [ ] Multiple game pieces in one frame (2-3 pieces)
- [ ] Game piece rolling or at odd angles
- [ ] Wide shot with game piece small in frame
- [ ] Close shot with game piece filling frame

### Tips
- Vary the background. Don't take all photos from the same spot.
- Include "negative" variety — frames with robots, field elements, and people
  but NO game pieces. This teaches the model what is NOT a game piece.
- 50 good images with variety > 500 images from one angle.
- Save as JPEG, any resolution. Roboflow handles resizing.

## Step 2: Label with Roboflow (1 hour)

### Setup
1. Go to roboflow.com — create a free account
2. Create a new project: Object Detection, name it "FRC-[YEAR]-[GAMEPIECE]"
3. Upload all your images

### Labeling
1. For each image, draw a bounding box around every game piece
2. Label each box with the class name (e.g., "fuel", "coral", "note", "algae")
3. If you're also detecting opponents, add a second class: "robot"
4. Skip labeling anything else — keep it to 1-2 classes maximum

### Augmentation (automatic)
Roboflow's free tier auto-generates augmented versions:
- Horizontal flip
- ±15° rotation
- ±20% brightness adjustment
- ±15% contrast
- Random crop
- Mosaic (combines 4 images into 1)

This turns 100 labeled images into 500+ training samples.

### Check for existing FRC datasets
Before labeling everything yourself, search Roboflow Universe:
- roboflow.com/search → "FRC [game piece name] [year]"
- Many FRC teams upload labeled datasets each season
- Download an existing dataset, add your own images to it, retrain

## Step 3: Train the Model (30-60 minutes, hands-off)

### In Roboflow
1. Click "Generate" → Create a new version of your dataset
2. Set preprocessing: Resize to 640x640, Auto-Orient
3. Set augmentation: Use the defaults (flip, rotation, brightness)
4. Click "Generate"
5. Click "Train" → Select YOLOv8-nano (fastest, smallest)
6. Training runs in the cloud. Takes 30-60 minutes for 500 images.
7. You'll get an email when it's done.

### Alternative: Train locally (for more control)
```bash
pip install ultralytics
yolo train model=yolov8n.pt data=your_dataset.yaml epochs=50 imgsz=640
```
This uses your GPU if available, CPU if not (slower). Output: best.pt model file.

### What to expect
- mAP (mean Average Precision) above 0.85 = good for FRC
- mAP above 0.90 = excellent
- If mAP is below 0.80, add more training images with more variety

## Step 4: Export for Limelight (15 minutes)

### Export from Roboflow
1. Click "Deploy" → Select "Hailo" or "ONNX" format
2. Download the model file

### If training locally
```bash
yolo export model=best.pt format=onnx imgsz=640
```

### Deploy to Limelight
1. Open the Limelight web interface (http://limelight.local:5801)
2. Go to the "Neural Network" tab
3. Upload your .onnx or Hailo-compiled model
4. Assign it to Pipeline Index 1 (keep AprilTag on Pipeline Index 0)
5. Set confidence threshold to 0.7 (adjust based on testing)
6. Set the detector input size to 640x640

## Step 5: Wire into The Engine (30 minutes)

The FuelDetectionConsumer.java subsystem already reads detections from
NetworkTables. The Limelight outputs neural network detections in the same
format regardless of whether it's running SnapScript or YOLO.

### Pipeline switching in VisionSubsystem.java
```java
// During autonomous: switch to YOLO neural detector (pipeline 1)
LimelightHelpers.setPipelineIndex("limelight", 1);

// During teleop: switch to AprilTag (pipeline 0)
LimelightHelpers.setPipelineIndex("limelight", 0);

// Or run both simultaneously if using dual Limelights:
// limelight-front: always AprilTag (pose estimation)
// limelight-back: always YOLO (game piece detection)
```

### Reading YOLO detections
The Limelight outputs detected objects as a JSON array in NetworkTables.
Each detection includes: class ID, confidence, bounding box (x, y, w, h),
and tx/ty angles from camera center. FuelDetectionConsumer.java parses
these the same way it parses SnapScript llpython output.

## Step 6: Competition Day Workflow

### Pre-event (night before)
1. Set up Limelight in the practice area
2. Capture 20-30 images under the venue's actual lighting
3. Add to your existing Roboflow dataset
4. Retrain (30 min cloud training while you do other setup)
5. Deploy updated model to Limelight

### Between matches
- If detection is missing game pieces: lower confidence threshold
- If detection has false positives: raise confidence threshold
- If lighting changed dramatically: capture 10 more images, quick retrain

### Fallback
If the YOLO model fails for any reason, switch to Pipeline 2 (SnapScript
color thresholding). The software doesn't care which pipeline is active —
FuelDetectionConsumer reads the same data format either way.

## Model Performance Reference

| Model | Size | Hailo-8 Speed | Training Images | Good For |
|-------|------|--------------|-----------------|----------|
| YOLOv8-nano | 6MB | 30+ fps | 50-100 | 1-2 classes, FRC standard |
| YOLOv8-small | 22MB | 20+ fps | 100-200 | 3-4 classes |
| YOLOv11-nano | 5MB | 35+ fps | 50-100 | Latest architecture, fastest |

YOLOv8-nano or YOLOv11-nano are recommended for FRC. One or two object
classes (game piece + optionally opponent robot) don't need a larger model.

## Offseason Training Exercise (for students)

This is an excellent fall training module:
1. Give students 10 random objects (balls, cups, boxes)
2. Each student captures 20 images of their assigned object
3. Label in Roboflow (teaches bounding box annotation)
4. Train a model (teaches ML pipeline concepts)
5. Deploy to Limelight (teaches embedded AI deployment)
6. Competition: which student's model detects most accurately?

Total time: 2-3 hours. Students learn the entire ML deployment pipeline
with zero math prerequisites. They'll be ready to train game-specific
models on kickoff day.
