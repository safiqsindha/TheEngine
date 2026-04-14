"""
eye/pipeline/roboflow_config.py — Roboflow supervision backend config stub
Team 2950 The Devastators | Eye E.1 FIT DCMP 2026

This file documents which Roboflow/supervision models we plan to use
(from LANDSCAPE_SCAN_ROBOFLOW_2026-04-12.md) and provides the config
structure for wiring them in Week 2 (post-FIT DCMP, pre-Worlds).

STATUS: STUB — do not run inference against real footage yet.
        Fill in ROBOFLOW_API_KEY from https://app.roboflow.com/settings/api
        before attempting any online inference.

Week 2 task order (from ENGINE_AUDIT_2026-04-13.md Workstream 2):
  W2.2a  Install libraries:  pip install supervision trackers inference
                             pip install git+https://github.com/roboflow/sports.git
  W2.2b  Wire pipeline (the ~200 lines of glue described in landscape scan)
  W2.2c  Define 2026 REBUILT field zone polygons via polygonzone tool
  W2.2d  Smoke test against cached FIT DCMP VODs

Do NOT run the inference server or download model weights during
FIT DCMP weekend (4/15–4/18). Capture footage first; wire pipeline in Week 2.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Roboflow Inference — Local server config
# ---------------------------------------------------------------------------
# Repo: https://github.com/roboflow/inference  (2,300 stars, active)
# Role: Local edge inference server. Runs rf-detr or YOLO without cloud calls.
#       For the Worlds 5-match demo (local, no API), this is the runtime.
# Install: pip install inference
# Start:   from inference import get_model   (no separate server process needed
#          for the Python SDK; the server is optional for REST access)

INFERENCE_SERVER_URL = "http://localhost:9001"  # if running as a standalone server
INFERENCE_API_KEY = os.environ.get("ROBOFLOW_API_KEY", "")  # set in env, never hardcode


# ---------------------------------------------------------------------------
# Model selection — two paths (see landscape scan for rationale)
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    """Config for a single detection model."""
    model_id: str           # Roboflow Universe model ID, e.g. "frc-robots/1"
    source: str             # "roboflow_universe" | "local_weights" | "ultralytics"
    backbone: str           # "rf-detr" | "yolov8" | "yolo11"
    description: str
    weights_path: Optional[Path] = None  # for local weights only
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.5
    notes: str = ""


# Path A: Roboflow Universe FRC model (zero training, works now)
# Find current best FRC robot detection model at:
#   https://universe.roboflow.com/search?q=FRC+robot
# The LIVE_SCOUT_ARCHITECTURE.md references "Roboflow Universe FRC YOLO model"
# as the Phase 2 T2 vision backend.
UNIVERSE_FRC_MODEL = ModelConfig(
    model_id="frc-robots/1",            # PLACEHOLDER — find real ID on universe.roboflow.com
    source="roboflow_universe",
    backbone="yolov8",
    description=(
        "Community FRC robot detector from Roboflow Universe. "
        "Zero custom training needed. Detects robot bounding boxes. "
        "Alliance color (red/blue) inferred from bumper HSV, not the model."
    ),
    confidence_threshold=0.45,
    notes=(
        "PLACEHOLDER model_id. Before Week 2 wire-up:\n"
        "  1. Go to https://universe.roboflow.com/search?q=FRC+robots\n"
        "  2. Find the highest-mAP model with recent FRC footage\n"
        "  3. Replace model_id with the real workspace/project/version string\n"
        "  4. Set ROBOFLOW_API_KEY in env"
    ),
)

# Path B: rf-detr — SOTA detector, may outperform YOLO on FRC footage
# Repo: https://github.com/roboflow/rf-detr  (6,400 stars, ICLR 2026)
# Advantage: better on small/occluded objects, better fine-tuning story
# Disadvantage: heavier than YOLO, needs GPU for real-time
# Verdict: INVESTIGATE after FIT DCMP VOD smoke test (W2.3)
RF_DETR_MODEL = ModelConfig(
    model_id="rfdetr-base",             # from `pip install rf-detr`
    source="ultralytics",               # loaded via rf-detr Python API
    backbone="rf-detr",
    description=(
        "RF-DETR base (ICLR 2026 SOTA real-time detector). "
        "Better fine-tuning story than YOLO. Investigate for Worlds demo."
    ),
    confidence_threshold=0.40,
    notes=(
        "Not installed yet. Week 2 investigation task:\n"
        "  pip install rf-detr\n"
        "  Run both UNIVERSE_FRC_MODEL and RF_DETR_MODEL against 3 cached\n"
        "  FIT DCMP VODs. Compare robot detection precision. Keep the winner."
    ),
)

# Active config — switch between Path A and Path B here
ACTIVE_MODEL = UNIVERSE_FRC_MODEL


# ---------------------------------------------------------------------------
# Tracking config (roboflow/trackers — ByteTrack)
# ---------------------------------------------------------------------------
# Repo: https://github.com/roboflow/trackers  (3,300 stars)
# Role: Robot identity persistence across frames (same robot = same ID)
# Required for per-team cycle counting (can't count cycles without stable IDs)
# Install: pip install trackers

@dataclass
class TrackerConfig:
    algorithm: str = "bytetrack"       # ByteTrack is the default; also: botsort, deepocsort
    track_activation_threshold: float = 0.25
    lost_track_buffer: int = 30        # frames to hold a lost track (1 sec at 30fps)
    minimum_matching_threshold: float = 0.8
    frame_rate: int = 30


TRACKER = TrackerConfig()


# ---------------------------------------------------------------------------
# Zone config (roboflow/supervision — PolygonZone)
# ---------------------------------------------------------------------------
# Repo: https://github.com/roboflow/supervision  (38,000 stars)
# Role: Define scoring zones as polygons; count robots/game pieces entering
# Tool: https://app.roboflow.com/polygonzone — draw zones on a field image
#
# These polygon coordinates are PLACEHOLDERS for the 2026 REBUILT game.
# Week 2.2c task: use the polygonzone web tool on a 2026 field image
# (find at https://firstroboticsbc.org/frc/game-season-info/) to define
# the actual coordinates. Coordinates are in pixel space relative to the
# broadcast frame at 1280x720.
#
# Zone naming convention: match the 2026 game manual section names exactly
# so zone events are traceable to manual rules.

@dataclass
class ZoneConfig:
    name: str
    polygon_points: list[list[int]]    # [[x,y], ...] pixel coords at 1280x720
    zone_type: str                     # "scoring" | "climb" | "starting" | "field"
    description: str


FIELD_ZONES_2026_REBUILT: list[ZoneConfig] = [
    # PLACEHOLDERS — replace with real coordinates from polygonzone tool
    # Week 2.2c: open https://app.roboflow.com/polygonzone
    # Upload a frame from a FIT DCMP VOD, draw the zones, export JSON
    ZoneConfig(
        name="red_scoring_zone",
        polygon_points=[[0, 0], [200, 0], [200, 200], [0, 200]],  # PLACEHOLDER
        zone_type="scoring",
        description="PLACEHOLDER — Red alliance scoring zone (REBUILT 2026). "
                    "Replace with real coords from polygonzone tool on a FIT DCMP frame.",
    ),
    ZoneConfig(
        name="blue_scoring_zone",
        polygon_points=[[1080, 0], [1280, 0], [1280, 200], [1080, 200]],  # PLACEHOLDER
        zone_type="scoring",
        description="PLACEHOLDER — Blue alliance scoring zone (REBUILT 2026).",
    ),
    ZoneConfig(
        name="red_climb_zone",
        polygon_points=[[0, 520], [200, 520], [200, 720], [0, 720]],  # PLACEHOLDER
        zone_type="climb",
        description="PLACEHOLDER — Red alliance climb/endgame zone.",
    ),
    ZoneConfig(
        name="blue_climb_zone",
        polygon_points=[[1080, 520], [1280, 520], [1280, 720], [1080, 720]],  # PLACEHOLDER
        zone_type="climb",
        description="PLACEHOLDER — Blue alliance climb/endgame zone.",
    ),
]


# ---------------------------------------------------------------------------
# Bumper OCR config (roboflow/sports)
# ---------------------------------------------------------------------------
# Repo: https://github.com/roboflow/sports  (4,900 stars)
# Role: Jersey/number OCR — maps to FRC bumper number reading
# Key finding from landscape scan: per-team attribution was "impossible"
#   with V0a. sports OCR makes it default, not stretch.
# Install: pip install git+https://github.com/roboflow/sports.git

@dataclass
class BumperOCRConfig:
    # Crop fraction of robot bounding box to read — lower third has bumper number
    crop_top_fraction: float = 0.6     # start at 60% from top of robot bbox
    crop_bottom_fraction: float = 1.0  # to bottom of robot bbox
    min_confidence: float = 0.7        # OCR confidence threshold
    cache_frames: int = 30             # re-use OCR result for this many frames
    # After cache_frames, re-read. This handles robots that rotate to show
    # different bumper faces.
    notes: str = (
        "sports OCR is trained on basketball/soccer jersey numbers. "
        "FRC bumper numbers are bigger + higher contrast but at different "
        "angles. Expected accuracy: ~80% on frontal bumper views, "
        "~50% on angled views. Validate against FIT DCMP frames in W2.3."
    )


BUMPER_OCR = BumperOCRConfig()


# ---------------------------------------------------------------------------
# Pipeline summary (for human reference)
# ---------------------------------------------------------------------------

PIPELINE_SUMMARY = """
Roboflow-Native Detection Pipeline (Eye E.1 Week 2 target)
===========================================================

Frame
  → inference (local server)         # detection: rf-detr or YOLO
      └→ trackers (ByteTrack)        # robot identity across frames
          ├→ sports OCR              # bumper number → team_num
          ├→ supervision PolygonZone # robot/game piece in scoring zone
          └→ supervision LineZone    # game piece crossing scoring line
              └→ VisionEvent aggregator   # fuse tracker_id + team_num + zones
                  └→ LiveMatch record     # per-team cycles, climbs, defense

Custom code needed: ~200 lines of glue (aggregator + field zone definitions)
Libraries: supervision, trackers, sports, inference  (all pip-installable)

Week 2 install command:
  pip install supervision trackers inference
  pip install git+https://github.com/roboflow/sports.git

Do NOT install during FIT DCMP weekend — focus on capture, not pipeline build.
"""


def print_pipeline_summary():
    print(PIPELINE_SUMMARY)
    print("Active model:", ACTIVE_MODEL.model_id)
    print("Tracker:", TRACKER.algorithm)
    print("Zones defined:", len(FIELD_ZONES_2026_REBUILT),
          "(WARNING: all are PLACEHOLDER coordinates)")
    print()
    print("Next steps:")
    print("  1. Set ROBOFLOW_API_KEY in env")
    print("  2. Replace UNIVERSE_FRC_MODEL.model_id with real Roboflow Universe model")
    print("  3. Run polygonzone tool to define real field zone coords")
    print("  4. Wire pipeline in eye/pipeline/roboflow_pipeline.py (W2.2b)")


if __name__ == "__main__":
    print_pipeline_summary()
