"""
tests/eye/test_roboflow_config.py — Roboflow API wiring tests.

All tests run fully offline via unittest.mock — no real network calls.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eye" / "pipeline"))
sys.path.insert(0, str(ROOT / "eye"))

import roboflow_config as rc
from roboflow_config import Detection, batch_predict, load_model, predict, probe_api


# ---------------------------------------------------------------------------
# Helpers — fake Roboflow objects
# ---------------------------------------------------------------------------

def _make_fake_prediction(class_name: str, confidence: float, x: float, y: float, w: float, h: float):
    """Build a minimal fake Prediction object matching the roboflow SDK shape."""
    pred = MagicMock()
    pred.json_prediction = {
        "class": class_name,
        "confidence": confidence,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "image_path": "/fake/image.jpg",
        "prediction_type": "object-detection",
    }
    return pred


def _make_fake_prediction_group(predictions):
    """Build a fake PredictionGroup-like object."""
    pg = MagicMock()
    pg.predictions = predictions
    return pg


def _make_fake_model(prediction_group=None):
    """Build a fake ObjectDetectionModel."""
    model = MagicMock()
    pg = prediction_group if prediction_group is not None else _make_fake_prediction_group([])
    model.predict.return_value = pg
    return model


# ---------------------------------------------------------------------------
# 1. Missing API key → clear ValueError
# ---------------------------------------------------------------------------

def test_missing_api_key_raises_value_error_no_env(monkeypatch):
    """No key passed and env var not set → ValueError with helpful message."""
    monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ROBOFLOW_API_KEY"):
        rc._resolve_api_key(None)


def test_missing_api_key_empty_string_raises(monkeypatch):
    """Empty string key is treated as missing."""
    monkeypatch.setenv("ROBOFLOW_API_KEY", "")
    with pytest.raises(ValueError, match="API key is required"):
        rc._resolve_api_key(None)


def test_explicit_api_key_bypasses_env(monkeypatch):
    """Explicit api_key= parameter wins even if env var is missing."""
    monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)
    key = rc._resolve_api_key("explicit-key-abc123")
    assert key == "explicit-key-abc123"


def test_env_api_key_is_used_when_no_explicit_key(monkeypatch):
    """ROBOFLOW_API_KEY env var is used when no key is passed explicitly."""
    monkeypatch.setenv("ROBOFLOW_API_KEY", "env-key-xyz")
    key = rc._resolve_api_key(None)
    assert key == "env-key-xyz"


# ---------------------------------------------------------------------------
# 2. load_model — mocked Roboflow client
# ---------------------------------------------------------------------------

def test_load_model_calls_roboflow_chain(monkeypatch):
    """load_model authenticates and traverses workspace→project→version→model."""
    monkeypatch.setenv("ROBOFLOW_API_KEY", "test-key")

    fake_model = MagicMock()
    fake_version = MagicMock()
    fake_version.model = fake_model
    fake_project = MagicMock()
    fake_project.version.return_value = fake_version
    fake_workspace = MagicMock()
    fake_workspace.project.return_value = fake_project
    fake_rf = MagicMock()
    fake_rf.workspace.return_value = fake_workspace

    with patch("roboflow_config.Roboflow", return_value=fake_rf) as mock_rf_cls:
        model = load_model(project="frc-robots", version=1)

    mock_rf_cls.assert_called_once_with(api_key="test-key")
    fake_rf.workspace.assert_called_once()
    fake_workspace.project.assert_called_once_with("frc-robots")
    fake_project.version.assert_called_once_with(1)
    assert model is fake_model


def test_load_model_raises_value_error_without_key(monkeypatch):
    """load_model raises ValueError before touching Roboflow if no key."""
    monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ROBOFLOW_API_KEY"):
        load_model(project="frc-robots", version=1)


# ---------------------------------------------------------------------------
# 3. predict — returns Detection objects
# ---------------------------------------------------------------------------

def test_predict_returns_detections(tmp_path, monkeypatch):
    """predict() converts PredictionGroup into Detection objects."""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff")  # minimal JPEG header

    fake_preds = [
        _make_fake_prediction("robot", 0.92, cx := 100.0, cy := 200.0, w := 60.0, h := 80.0),
    ]
    pg = _make_fake_prediction_group(fake_preds)
    model = _make_fake_model(pg)

    detections = predict(model, img)

    assert len(detections) == 1
    d = detections[0]
    assert isinstance(d, Detection)
    assert d.class_name == "robot"
    assert abs(d.confidence - 0.92) < 1e-6
    # Center (100,200) w=60 h=80 → x1=70, y1=160, x2=130, y2=240
    assert d.bbox == (70.0, 160.0, 130.0, 240.0)


def test_predict_empty_detections(tmp_path):
    """predict() returns empty list when model finds nothing."""
    img = tmp_path / "empty.jpg"
    img.write_bytes(b"\xff\xd8\xff")

    model = _make_fake_model(_make_fake_prediction_group([]))
    detections = predict(model, img)
    assert detections == []


def test_predict_missing_image_raises(tmp_path):
    """predict() raises FileNotFoundError for a nonexistent image path."""
    model = _make_fake_model()
    with pytest.raises(FileNotFoundError, match="not found"):
        predict(model, tmp_path / "nonexistent.jpg")


def test_predict_multiple_detections(tmp_path):
    """predict() handles multiple detections in one image."""
    img = tmp_path / "multi.jpg"
    img.write_bytes(b"\xff\xd8\xff")

    fake_preds = [
        _make_fake_prediction("robot", 0.85, 50.0, 50.0, 40.0, 40.0),
        _make_fake_prediction("game_piece", 0.70, 300.0, 200.0, 20.0, 20.0),
        _make_fake_prediction("robot", 0.91, 600.0, 400.0, 80.0, 60.0),
    ]
    pg = _make_fake_prediction_group(fake_preds)
    model = _make_fake_model(pg)

    detections = predict(model, img)
    assert len(detections) == 3
    assert detections[0].class_name == "robot"
    assert detections[1].class_name == "game_piece"
    assert detections[2].confidence == 0.91


# ---------------------------------------------------------------------------
# 4. batch_predict
# ---------------------------------------------------------------------------

def test_batch_predict_empty_list():
    """batch_predict([]) returns [] without touching the model."""
    model = _make_fake_model()
    result = batch_predict(model, [])
    assert result == []
    model.predict.assert_not_called()


def test_batch_predict_multiple_images(tmp_path):
    """batch_predict returns one list per image."""
    imgs = []
    for i in range(3):
        p = tmp_path / f"img_{i}.jpg"
        p.write_bytes(b"\xff\xd8\xff")
        imgs.append(p)

    # Each call to model.predict returns 1 detection
    call_count = 0

    def side_effect(path):
        nonlocal call_count
        call_count += 1
        return _make_fake_prediction_group([
            _make_fake_prediction("robot", 0.8, 100.0, 100.0, 40.0, 40.0)
        ])

    model = MagicMock()
    model.predict.side_effect = side_effect

    results = batch_predict(model, imgs)
    assert len(results) == 3
    assert call_count == 3
    for det_list in results:
        assert len(det_list) == 1
        assert det_list[0].class_name == "robot"


# ---------------------------------------------------------------------------
# 5. probe_api
# ---------------------------------------------------------------------------

def test_probe_api_success(monkeypatch):
    """probe_api returns ok=True with workspace info on a 200 response."""
    monkeypatch.setenv("ROBOFLOW_API_KEY", "probe-key")

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "workspace": "team-2950",
        "projects": [{"id": "frc-robots"}, {"id": "field-zones"}],
    }
    fake_response.raise_for_status = MagicMock()

    with patch("roboflow_config.requests.get", return_value=fake_response) as mock_get:
        result = probe_api()

    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "probe-key" in call_url
    assert result["ok"] is True
    assert result["workspace"] == "team-2950"
    assert result["project_count"] == 2


def test_probe_api_bad_key_raises(monkeypatch):
    """probe_api propagates HTTPError when the key is rejected."""
    import requests as req_lib

    monkeypatch.setenv("ROBOFLOW_API_KEY", "bad-key")

    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = req_lib.HTTPError("401 Unauthorized")

    with patch("roboflow_config.requests.get", return_value=fake_response):
        with pytest.raises(req_lib.HTTPError):
            probe_api()


def test_probe_api_no_key_raises(monkeypatch):
    """probe_api raises ValueError before making any network call if key is missing."""
    monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)
    with patch("roboflow_config.requests.get") as mock_get:
        with pytest.raises(ValueError, match="ROBOFLOW_API_KEY"):
            probe_api()
    mock_get.assert_not_called()
