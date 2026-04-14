"""
eye/pipeline/roboflow_config.py — Roboflow API wiring
Team 2950 The Devastators | Eye E.1

Provides:
  - Detection dataclass
  - RoboflowModel type alias
  - load_model()      — authenticate + fetch model from Roboflow Universe
  - predict()         — run inference on one image → list[Detection]
  - batch_predict()   — run inference on multiple images → list[list[Detection]]
  - probe_api()       — verify API key works (no model download needed)

Environment:
  ROBOFLOW_API_KEY — set this; never hardcode.

Original stub context preserved below as module docstring addendum:
  Week 2 task order (from ENGINE_AUDIT_2026-04-13.md Workstream 2):
    W2.2a  Install libraries:  pip install supervision trackers inference
                               pip install git+https://github.com/roboflow/sports.git
    W2.2b  Wire pipeline (the ~200 lines of glue described in landscape scan)
    W2.2c  Define 2026 REBUILT field zone polygons via polygonzone tool
    W2.2d  Smoke test against cached FIT DCMP VODs
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests  # noqa: F401  (imported here so tests can patch roboflow_config.requests)

try:
    from roboflow import Roboflow  # noqa: F401  (imported here so tests can patch roboflow_config.Roboflow)
except ImportError:  # pragma: no cover
    Roboflow = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    """A single object detection result from Roboflow inference.

    bbox is in (x1, y1, x2, y2) absolute-pixel format.
    The raw Roboflow response uses center (x, y, width, height);
    predict() converts to corner format automatically.
    """
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2


# Type alias — the underlying object is a roboflow ObjectDetectionModel,
# but we keep it opaque so callers only depend on this module's API.
RoboflowModel = Any


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _resolve_api_key(api_key: Optional[str]) -> str:
    """Return api_key if provided, else read ROBOFLOW_API_KEY from env.

    Raises ValueError with a clear message if neither is available.
    """
    key = api_key or os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Roboflow API key is required. "
            "Pass api_key= explicitly or set the ROBOFLOW_API_KEY environment variable. "
            "Get your key at https://app.roboflow.com/settings/api"
        )
    return key


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_model(
    project: str,
    version: int,
    api_key: Optional[str] = None,
) -> RoboflowModel:
    """Authenticate with Roboflow and return a model ready for inference.

    Args:
        project:  Roboflow project slug, e.g. "frc-robots" (workspace/project
                  or bare project name — Roboflow resolves via default workspace).
        version:  Version number to load, e.g. 1.
        api_key:  Optional explicit API key. Falls back to ROBOFLOW_API_KEY env var.

    Returns:
        An ObjectDetectionModel (or equivalent) from the roboflow package.

    Raises:
        ValueError: if no API key is available.
        roboflow.exceptions.AuthenticationError: if the key is invalid.
        requests.HTTPError: on any other HTTP failure from the Roboflow API.
    """
    if Roboflow is None:  # pragma: no cover
        raise ImportError("roboflow package is not installed. Run: pip install roboflow")

    key = _resolve_api_key(api_key)
    rf = Roboflow(api_key=key)
    proj_obj = rf.workspace().project(project)
    model = proj_obj.version(version).model
    return model


def predict(model: RoboflowModel, image_path: str | Path) -> list[Detection]:
    """Run inference on a single image and return Detection objects.

    Args:
        model:       A model object returned by load_model().
        image_path:  Path to the local image file.

    Returns:
        List of Detection objects, one per detected object.
        Empty list if no objects are detected.

    Raises:
        FileNotFoundError: if image_path does not exist.
        requests.HTTPError: on Roboflow API failure.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    prediction_group = model.predict(str(image_path))
    return _parse_prediction_group(prediction_group)


def batch_predict(
    model: RoboflowModel,
    image_paths: list[str | Path],
) -> list[list[Detection]]:
    """Run inference on multiple images.

    Args:
        model:        A model object returned by load_model().
        image_paths:  List of local image paths.

    Returns:
        List of detection lists, one inner list per input image.
        Empty outer list if image_paths is empty.
    """
    if not image_paths:
        return []
    return [predict(model, p) for p in image_paths]


def probe_api(api_key: Optional[str] = None) -> dict:
    """Verify that the API key works by listing the default workspace.

    Makes a lightweight authenticated GET to the Roboflow API —
    no model download or inference is performed.

    Args:
        api_key:  Optional explicit API key. Falls back to ROBOFLOW_API_KEY.

    Returns:
        dict with keys:
          - "ok": True
          - "workspace": workspace slug string
          - "project_count": number of projects in the workspace

    Raises:
        ValueError: if no API key is available.
        requests.HTTPError: if the API key is invalid or the request fails.
    """
    key = _resolve_api_key(api_key)
    url = f"https://api.roboflow.com/?api_key={key}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    workspace_slug = data.get("workspace", "")
    # The top-level response contains a workspace entry with project list
    projects = data.get("projects", [])
    return {
        "ok": True,
        "workspace": workspace_slug,
        "project_count": len(projects),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_prediction_group(prediction_group) -> list[Detection]:
    """Convert a Roboflow PredictionGroup into a list of Detection objects.

    Roboflow returns center-based bboxes (x, y, width, height).
    We convert to corner-based (x1, y1, x2, y2).
    """
    detections: list[Detection] = []
    for pred in prediction_group.predictions:
        jp = pred.json_prediction
        cx = float(jp["x"])
        cy = float(jp["y"])
        w = float(jp["width"])
        h = float(jp["height"])
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2
        detections.append(
            Detection(
                class_name=str(jp.get("class", "")),
                confidence=float(jp.get("confidence", 0.0)),
                bbox=(x1, y1, x2, y2),
            )
        )
    return detections


# ---------------------------------------------------------------------------
# Preserved config dataclasses from original stub
# (used by other pipeline modules — do not remove)
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    """Config for a single detection model."""
    model_id: str
    source: str             # "roboflow_universe" | "local_weights" | "ultralytics"
    backbone: str           # "rf-detr" | "yolov8" | "yolo11"
    description: str
    weights_path: Optional[Path] = None
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.5
    notes: str = ""


UNIVERSE_FRC_MODEL = ModelConfig(
    model_id="frc-robots/1",
    source="roboflow_universe",
    backbone="yolov8",
    description=(
        "Community FRC robot detector from Roboflow Universe. "
        "Zero custom training needed. Detects robot bounding boxes."
    ),
    confidence_threshold=0.45,
    notes=(
        "PLACEHOLDER model_id. Replace with real workspace/project/version string "
        "from https://universe.roboflow.com/search?q=FRC+robots"
    ),
)

RF_DETR_MODEL = ModelConfig(
    model_id="rfdetr-base",
    source="ultralytics",
    backbone="rf-detr",
    description="RF-DETR base (ICLR 2026 SOTA real-time detector).",
    confidence_threshold=0.40,
    notes="Not installed yet. Week 2 investigation task.",
)

ACTIVE_MODEL = UNIVERSE_FRC_MODEL

INFERENCE_SERVER_URL = "http://localhost:9001"


@dataclass
class TrackerConfig:
    algorithm: str = "bytetrack"
    track_activation_threshold: float = 0.25
    lost_track_buffer: int = 30
    minimum_matching_threshold: float = 0.8
    frame_rate: int = 30


TRACKER = TrackerConfig()


@dataclass
class ZoneConfig:
    name: str
    polygon_points: list[list[int]]
    zone_type: str
    description: str


FIELD_ZONES_2026_REBUILT: list[ZoneConfig] = [
    ZoneConfig(
        name="red_scoring_zone",
        polygon_points=[[0, 0], [200, 0], [200, 200], [0, 200]],
        zone_type="scoring",
        description="PLACEHOLDER — Red alliance scoring zone (REBUILT 2026).",
    ),
    ZoneConfig(
        name="blue_scoring_zone",
        polygon_points=[[1080, 0], [1280, 0], [1280, 200], [1080, 200]],
        zone_type="scoring",
        description="PLACEHOLDER — Blue alliance scoring zone (REBUILT 2026).",
    ),
    ZoneConfig(
        name="red_climb_zone",
        polygon_points=[[0, 520], [200, 520], [200, 720], [0, 720]],
        zone_type="climb",
        description="PLACEHOLDER — Red alliance climb/endgame zone.",
    ),
    ZoneConfig(
        name="blue_climb_zone",
        polygon_points=[[1080, 520], [1280, 520], [1280, 720], [1080, 720]],
        zone_type="climb",
        description="PLACEHOLDER — Blue alliance climb/endgame zone.",
    ),
]


@dataclass
class BumperOCRConfig:
    crop_top_fraction: float = 0.6
    crop_bottom_fraction: float = 1.0
    min_confidence: float = 0.7
    cache_frames: int = 30


BUMPER_OCR = BumperOCRConfig()
