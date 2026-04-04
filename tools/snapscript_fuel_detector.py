"""
THE ENGINE — Limelight SnapScript: Wave Robotics YOLOv11n Fuel Detector
FRC Team 2950 | Deploy via Limelight web interface

Uses the Wave Robotics YOLOv11n ONNX model (trained on 2026 fuel balls).
The model is single-class: class 0 = fuel ball ("object").
Runs ONNX inference via onnxruntime, available on Limelight 4.

DEPLOYMENT:
  1. Upload wave_fuel_detector.onnx to Limelight via the web interface
     (Manage tab → File Upload, place in /home/limelight/)
  2. Upload this script as a SnapScript pipeline (Pipeline tab → Python)
  3. Set this pipeline as Pipeline Index 1 (keep AprilTag on Pipeline 0)

PROTOCOL:
  Robot → Limelight (llrobot array):
    [robotX, robotY, robotHeadingRad, zoneMinX, zoneMinY, zoneMaxX, zoneMaxY]

  Limelight → Robot (llpython array):
    [numFuel, fx1, fy1, fConf1, fx2, fy2, fConf2, ...]

  All coordinates are field-relative (meters).
  Confidence scores are 0.0-1.0.

NOTE: This model detects FUEL ONLY. Opponent detection must come from a
      separate source (e.g., Limelight AprilTag pose estimation to track
      opposing alliance robots by their AprilTag poses).

Model specs:
  Architecture : YOLOv11n
  Input        : 640×640 BGR (normalized to [0,1])
  Output       : (1, 5, 8400) — cx, cy, w, h, conf — single class
  Confidence   : 93–97% on training images (Wave Robotics, 2026)
"""

import cv2
import math
import numpy as np
import os

# ── Load ONNX model once at module load (not per frame) ─────────────────────
try:
    import onnxruntime as ort

    _MODEL_PATH = "/home/limelight/wave_fuel_detector.onnx"
    _SESS_OPTIONS = ort.SessionOptions()
    _SESS_OPTIONS.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    _SESSION = ort.InferenceSession(_MODEL_PATH, sess_options=_SESS_OPTIONS,
                                     providers=["CPUExecutionProvider"])
    _INPUT_NAME = _SESSION.get_inputs()[0].name
    _MODEL_LOADED = True
    print("[FuelDetector] YOLOv11n ONNX model loaded from", _MODEL_PATH)
except Exception as _e:
    _SESSION = None
    _MODEL_LOADED = False
    print("[FuelDetector] WARNING: ONNX model not loaded:", _e)
    print("[FuelDetector] Falling back to HSV color detection.")

# ── Tunable parameters ───────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.80     # Wave model is 93–97%; 0.80 is a safe floor
NMS_IOU_THRESHOLD    = 0.45     # Suppress overlapping boxes
MAX_FUEL_DETECTIONS  = 8

# Camera parameters — Limelight 4 default (update if using different mount)
CAMERA_FOV_H_DEG   = 63.3      # Horizontal FOV degrees
CAMERA_FOV_V_DEG   = 49.7      # Vertical FOV degrees
CAMERA_RES_X       = 640
CAMERA_RES_Y       = 480
CAMERA_HEIGHT_M    = 0.50      # Camera height above field carpet (meters)
CAMERA_PITCH_DEG   = -15.0     # Negative = tilted downward

# HSV fallback (only used if ONNX model fails to load)
_HSV_LOW  = (20, 100, 100)
_HSV_HIGH = (35, 255, 255)
_MIN_AREA = 300


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _pixel_to_field(cx_px, cy_px, robot_x, robot_y, robot_heading_rad):
    """
    Convert a bounding-box center pixel to field-relative (x, y) in meters.

    Uses the camera's pitch and the pixel's vertical position to estimate
    distance via flat-field geometry (assumes game pieces are on the carpet).
    Then rotates from robot-relative to field-relative using robot heading.

    Returns None if the projection produces an unreasonable result.
    """
    # Horizontal angle from camera optical axis (radians, + = right)
    angle_h = ((cx_px - CAMERA_RES_X / 2.0) / CAMERA_RES_X) \
              * math.radians(CAMERA_FOV_H_DEG)

    # Vertical angle from camera optical axis (radians, + = up)
    angle_v = ((CAMERA_RES_Y / 2.0 - cy_px) / CAMERA_RES_Y) \
              * math.radians(CAMERA_FOV_V_DEG)

    # Total depression angle below horizontal
    total_depression = -(math.radians(CAMERA_PITCH_DEG) + angle_v)

    if total_depression < 0.01:
        return None  # Object above horizon — can't project to floor

    # Distance to floor projection along the horizontal ground plane
    distance = CAMERA_HEIGHT_M / math.tan(total_depression)

    if distance < 0.2 or distance > 12.0:
        return None  # Outside plausible range

    # Robot-relative coordinates (forward = +x, left = +y)
    obj_x_robot = distance * math.cos(angle_h)
    obj_y_robot = distance * math.sin(angle_h)

    # Rotate to field-relative using robot heading
    cos_h = math.cos(robot_heading_rad)
    sin_h = math.sin(robot_heading_rad)
    field_x = robot_x + obj_x_robot * cos_h - obj_y_robot * sin_h
    field_y = robot_y + obj_x_robot * sin_h + obj_y_robot * cos_h

    return field_x, field_y


def _in_zone(x, y, zx0, zy0, zx1, zy1):
    return zx0 <= x <= zx1 and zy0 <= y <= zy1


# ── ONNX inference ───────────────────────────────────────────────────────────

def _run_yolo(image_bgr):
    """
    Run YOLOv11n inference on a BGR frame.

    Returns list of (cx_px, cy_px, conf) detections after NMS,
    sorted by confidence descending.

    YOLOv11n output tensor: (1, 5, 8400)
      Axis 1 rows: cx, cy, w, h, class0_confidence
      All coordinates are normalised to [0, 1] × input size (640×640).
    """
    # Preprocess: resize to 640×640, BGR→RGB, HWC→CHW, normalise
    img = cv2.resize(image_bgr, (640, 640))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))          # HWC → CHW
    img = np.expand_dims(img, axis=0)           # CHW → BCHW

    raw = _SESSION.run(None, {_INPUT_NAME: img})[0]  # (1, 5, 8400)
    preds = raw[0].T                                  # (8400, 5)

    cx_n, cy_n, w_n, h_n = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    conf = preds[:, 4]

    # Confidence filter
    mask = conf >= CONFIDENCE_THRESHOLD
    if not np.any(mask):
        return []

    cx_n, cy_n, w_n, h_n, conf = cx_n[mask], cy_n[mask], w_n[mask], h_n[mask], conf[mask]

    # De-normalise from 640-px input space back to original frame pixel space
    scale_x = image_bgr.shape[1] / 640.0
    scale_y = image_bgr.shape[0] / 640.0
    cx_px = cx_n * 640 * scale_x
    cy_px = cy_n * 640 * scale_y
    w_px  = w_n  * 640 * scale_x
    h_px  = h_n  * 640 * scale_y

    # Convert cx/cy/w/h → x1/y1/x2/y2 for NMS
    x1 = cx_px - w_px / 2
    y1 = cy_px - h_px / 2
    x2 = cx_px + w_px / 2
    y2 = cy_px + h_px / 2

    boxes  = np.stack([x1, y1, x2, y2], axis=1).astype(np.float32)
    scores = conf.astype(np.float32)

    # OpenCV NMS (returns surviving indices)
    indices = cv2.dnn.NMSBoxes(
        boxes.tolist(),
        scores.tolist(),
        CONFIDENCE_THRESHOLD,
        NMS_IOU_THRESHOLD
    )
    if len(indices) == 0:
        return []

    # Flatten in case OpenCV returns shape (N, 1)
    indices = indices.flatten()

    results = []
    for idx in indices:
        results.append((float(cx_px[idx]), float(cy_px[idx]), float(scores[idx])))

    results.sort(key=lambda d: d[2], reverse=True)
    return results[:MAX_FUEL_DETECTIONS]


# ── HSV fallback ─────────────────────────────────────────────────────────────

def _run_hsv(image_bgr):
    """
    Fallback detector using yellow HSV thresholding.
    Only used when the ONNX model failed to load.
    """
    hsv  = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _HSV_LOW, _HSV_HIGH)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < _MIN_AREA:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        peri = cv2.arcLength(c, True)
        circ = 4 * math.pi * area / (peri * peri) if peri > 0 else 0
        if circ < 0.5:
            continue
        conf = min(1.0, circ * (area / 2000.0))
        results.append((cx, cy, conf))

    results.sort(key=lambda d: d[2], reverse=True)
    return results[:MAX_FUEL_DETECTIONS]


# ── Main pipeline entry point ─────────────────────────────────────────────────

def runPipeline(image, llrobot):
    """
    Limelight SnapScript entry point. Called every camera frame.

    Args:
        image   : BGR uint8 image from the Limelight camera
        llrobot : double[] from the robot via NetworkTables

    Returns:
        (largestContour, annotatedImage, llpython)
        llpython = [numFuel, fx1, fy1, conf1, fx2, fy2, conf2, ...]
    """
    # ── Parse robot pose and detection zone from llrobot ──────────────────────
    robot_x       = llrobot[0] if len(llrobot) > 0 else 0.0
    robot_y       = llrobot[1] if len(llrobot) > 1 else 0.0
    robot_heading = llrobot[2] if len(llrobot) > 2 else 0.0   # radians
    zone_x0       = llrobot[3] if len(llrobot) > 3 else 0.0
    zone_y0       = llrobot[4] if len(llrobot) > 4 else 0.0
    zone_x1       = llrobot[5] if len(llrobot) > 5 else 16.46
    zone_y1       = llrobot[6] if len(llrobot) > 6 else 8.23

    # ── Detect fuel balls ─────────────────────────────────────────────────────
    raw_detections = _run_yolo(image) if _MODEL_LOADED else _run_hsv(image)

    # ── Project to field coordinates and zone-filter ──────────────────────────
    fuel_detections = []
    largest_contour = np.array([[]])

    for cx_px, cy_px, conf in raw_detections:
        proj = _pixel_to_field(cx_px, cy_px, robot_x, robot_y, robot_heading)
        if proj is None:
            continue
        fx, fy = proj
        if not _in_zone(fx, fy, zone_x0, zone_y0, zone_x1, zone_y1):
            continue
        fuel_detections.append((fx, fy, conf))

        # Annotate frame
        px, py = int(cx_px), int(cy_px)
        cv2.circle(image, (px, py), 12, (0, 255, 255), 2)
        cv2.putText(image, f"FUEL {conf:.0%}",
                    (px - 30, py - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    # ── Build llpython output ─────────────────────────────────────────────────
    # Format: [numFuel, fx1, fy1, conf1, fx2, fy2, conf2, ...]
    llpython = [float(len(fuel_detections))]
    for fx, fy, conf in fuel_detections:
        llpython.extend([fx, fy, conf])

    # Pad to fixed-width section (1 + MAX_FUEL * 3 elements) so the robot
    # parser always sees a predictable array length.
    fixed_len = 1 + MAX_FUEL_DETECTIONS * 3
    while len(llpython) < fixed_len:
        llpython.append(0.0)

    return largest_contour, image, llpython
