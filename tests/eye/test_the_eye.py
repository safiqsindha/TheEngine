"""
tests/eye/test_the_eye.py — Tests for eye/the_eye.py

Covers: synthesize_report, cmd_analyze, select_key_frames,
        select_frames_by_tier, parse_common_args, get_backend.

All external calls (Anthropic API, ffmpeg, pytubefix, OverlayOCR) mocked.
No real network calls, no real video files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Path setup — inject eye/ directory so `from overlay_ocr import OverlayOCR`
# works without a real PaddleOCR installation.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
EYE_DIR = ROOT / "eye"

# overlay_ocr stub is installed by tests/eye/conftest.py before any test runs.
# We only need to ensure eye/ is on sys.path so the_eye can be imported.
sys.path.insert(0, str(EYE_DIR))

import the_eye  # noqa: E402  (must come after path setup)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_frames(n: int, interval: int = 5) -> list:
    """Build synthetic frame dicts (no actual files)."""
    frames = []
    for i in range(n):
        ts = i * interval
        if ts < 18:
            phase = "auto"
        elif ts < 150:
            phase = "teleop"
        else:
            phase = "endgame"
        frames.append({
            "path": f"/fake/frames/frame_{i:03d}.jpg",
            "filename": f"frame_{i:03d}.jpg",
            "timestamp_s": ts,
            "phase": phase,
        })
    return frames


def _make_obs(team: int, alliance: str, phase: str,
              action: str = "scoring", zone: str = "wing",
              defense: str = "", mechanism_note: str = "") -> dict:
    """Minimal observation dict matching the shape the_eye produces."""
    return {
        "team": team,
        "alliance": alliance,
        "action": action,
        "zone": zone,
        "defense": defense,
        "mechanism_note": mechanism_note,
    }


def _make_vision_obs(teams=(2950, 3035), red_score=30, blue_score=25,
                     phase="teleop") -> dict:
    """Minimal vision-layer observation dict."""
    return {
        "timestamp": "1:30",
        "phase": phase,
        "scores": {"red": red_score, "blue": blue_score},
        "timer": "1:30",
        "red_teams": [teams[0]],
        "blue_teams": [teams[1]],
        "observations": [
            _make_obs(teams[0], "red", phase, action="scoring coral"),
            _make_obs(teams[1], "blue", phase, action="defending"),
        ],
        "field_state": "red dominant",
        "notable": "",
    }


# ===========================================================================
# 1. synthesize_report
# ===========================================================================

class TestSynthesizeReport:
    """Tests for the_eye.synthesize_report()"""

    def test_empty_observations_returns_empty_report(self):
        report = the_eye.synthesize_report([])
        assert report["n_frames"] == 0
        assert report["teams"] == {}
        assert report["final_scores"] == {}

    def test_single_observation_extracts_team(self):
        obs = _make_vision_obs(teams=(2950, 3035))
        report = the_eye.synthesize_report([obs])
        assert "2950" in report["teams"]
        assert "3035" in report["teams"]

    def test_score_progression_built_correctly(self):
        obs = [
            _make_vision_obs(red_score=10, blue_score=5, phase="auto"),
            _make_vision_obs(red_score=30, blue_score=25, phase="teleop"),
        ]
        report = the_eye.synthesize_report(obs)
        assert len(report["score_progression"]) == 2
        assert report["score_progression"][0]["red"] == 10
        assert report["score_progression"][-1]["blue"] == 25

    def test_final_scores_taken_from_last_observation(self):
        obs = [
            _make_vision_obs(red_score=5, blue_score=0, phase="auto"),
            _make_vision_obs(red_score=50, blue_score=40, phase="teleop"),
            _make_vision_obs(red_score=72, blue_score=61, phase="endgame"),
        ]
        report = the_eye.synthesize_report(obs)
        assert report["final_scores"]["red"] == 72
        assert report["final_scores"]["blue"] == 61

    def test_parse_error_observations_skipped(self):
        obs = [
            {"parse_error": True, "raw": "bad json"},
            _make_vision_obs(),
        ]
        report = the_eye.synthesize_report(obs)
        # Should still process the valid observation
        assert len(report["teams"]) > 0

    def test_focus_teams_added_to_report(self):
        obs = [_make_vision_obs(teams=(2950, 3035))]
        report = the_eye.synthesize_report(obs, focus_teams=[2950])
        assert "2950" in report["focus_teams"]

    def test_focus_team_not_observed_returns_no_data(self):
        obs = [_make_vision_obs(teams=(1, 2))]
        report = the_eye.synthesize_report(obs, focus_teams=[9999])
        assert report["focus_teams"]["9999"].get("no_data") is True

    def test_actions_bucketed_by_phase(self):
        auto_obs = _make_vision_obs(phase="auto")
        tele_obs = _make_vision_obs(phase="teleop")
        end_obs = _make_vision_obs(phase="endgame")
        report = the_eye.synthesize_report([auto_obs, tele_obs, end_obs])
        td = report["teams"]["2950"]
        assert len(td["auto"]) >= 1
        assert len(td["teleop"]) >= 1
        assert len(td["endgame"]) >= 1

    def test_ocr_breakdown_merged_into_report(self):
        obs = [_make_vision_obs()]
        ocr_data = {"is_breakdown": True, "teams": {"red": [2950], "blue": [3035]}}
        report = the_eye.synthesize_report(obs, ocr_data=ocr_data)
        assert report["breakdown"].get("is_breakdown") is True

    def test_unknown_team_skipped(self):
        obs_with_unknown = {
            "phase": "teleop",
            "scores": {"red": 10, "blue": 5},
            "observations": [
                {"team": "unknown", "alliance": "red", "action": "driving",
                 "zone": "center", "defense": "", "mechanism_note": ""},
            ],
        }
        report = the_eye.synthesize_report([obs_with_unknown])
        assert "unknown" not in report["teams"]


# ===========================================================================
# 2. select_key_frames / select_frames_by_tier
# ===========================================================================

class TestFrameSelection:
    """Tests for frame-selection helpers."""

    def test_select_key_frames_returns_at_most_max_frames(self):
        frames = _make_frames(60)
        result = the_eye.select_key_frames(frames, max_frames=12)
        assert len(result) <= 12

    def test_select_key_frames_includes_first_frame(self):
        """First frame is always included in the key frames selection."""
        frames = _make_frames(40)
        result = the_eye.select_key_frames(frames, max_frames=12)
        # First frame (index 0) must always be present
        assert result[0] is frames[0]
        # Result must never exceed max_frames
        assert len(result) <= 12

    def test_select_key_frames_short_list_unchanged(self):
        frames = _make_frames(5)
        result = the_eye.select_key_frames(frames, max_frames=12)
        assert result == frames

    def test_select_frames_by_tier_all_returns_all(self):
        frames = _make_frames(20)
        result = the_eye.select_frames_by_tier(frames, tier="all")
        assert result is frames

    def test_select_frames_by_tier_key_limits(self):
        frames = _make_frames(60)
        result = the_eye.select_frames_by_tier(frames, tier="key")
        assert len(result) <= 12

    def test_select_frames_by_tier_scored_falls_back_to_even_without_ocr(self):
        frames = _make_frames(100)
        result = the_eye.select_frames_by_tier(frames, tier="scored", ocr=None)
        assert len(result) <= 50

    def test_select_key_frames_last_frame_always_included(self):
        """Regression: last frame must survive the [:max_frames] trim even when
        many endgame frames appear before it and push it out of the slice."""
        # Build a frame list where endgame starts early so there are many
        # endgame frames — enough to fill max_frames before the last index.
        # 40 frames at 5 s each → frames 30-39 are endgame (ts 150-195).
        frames = _make_frames(40, interval=5)
        max_frames = 12
        result = the_eye.select_key_frames(frames, max_frames=max_frames)

        assert len(result) <= max_frames, "must not exceed max_frames"
        assert result[-1] is frames[-1], (
            "last frame must always be present regardless of endgame frame count"
        )


# ===========================================================================
# 3. parse_common_args
# ===========================================================================

class TestParseCommonArgs:
    def test_defaults_returned_with_empty_args(self):
        opts = the_eye.parse_common_args([])
        assert opts["backend_name"] == "haiku"
        assert opts["tier"] == "key"
        assert opts["fps"] == 5
        assert opts["focus_teams"] is None

    def test_focus_parsed_correctly(self):
        opts = the_eye.parse_common_args(["--focus", "2950,3035"])
        assert opts["focus_teams"] == [2950, 3035]

    def test_backend_parsed_correctly(self):
        opts = the_eye.parse_common_args(["--backend", "sonnet"])
        assert opts["backend_name"] == "sonnet"

    def test_invalid_tier_returns_none(self):
        result = the_eye.parse_common_args(["--tier", "invalid"], start=0)
        assert result is None

    def test_fps_parsed_correctly(self):
        opts = the_eye.parse_common_args(["--fps", "2"])
        assert opts["fps"] == 2


# ===========================================================================
# 4. get_backend
# ===========================================================================

class TestGetBackend:
    def test_invalid_backend_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            the_eye.get_backend("nonexistent_backend")

    def test_local_backend_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            the_eye.get_backend("gemma")

    def test_yolo_backend_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            the_eye.get_backend("yolo")

    def test_anthropic_backend_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Mock anthropic module
        fake_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            # Patch key lookup to return empty
            with patch.object(Path, "exists", return_value=False):
                with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                    the_eye.AnthropicVisionBackend(model_key="haiku")


# ===========================================================================
# 5. cmd_analyze — full pipeline mocked
# ===========================================================================

class TestCmdAnalyze:
    def test_no_args_returns_early(self, capsys):
        the_eye.cmd_analyze([])
        captured = capsys.readouterr()
        assert "Usage" in captured.out

    def test_full_pipeline_calls_backend_and_returns_report(self, tmp_path, monkeypatch):
        """cmd_analyze with mocked download, extract, OCR, and vision backend."""
        url = "https://youtube.com/watch?v=ABC12345678"

        fake_frames = _make_frames(10)
        fake_obs = [_make_vision_obs()]

        fake_backend = MagicMock()
        fake_backend.name.return_value = "haiku-vision"
        fake_backend.analyze_frames.return_value = fake_obs

        monkeypatch.setattr(the_eye, "CACHE_DIR", tmp_path / ".cache")
        monkeypatch.setattr(the_eye, "RESULTS_DIR", tmp_path / ".cache" / "results")

        with patch.object(the_eye, "download_video",
                          return_value=tmp_path / "match.mp4") as mock_dl, \
             patch.object(the_eye, "extract_frames",
                          return_value=fake_frames) as mock_frames, \
             patch.object(the_eye, "get_backend",
                          return_value=fake_backend) as mock_backend, \
             patch("the_eye.OverlayOCR") as mock_ocr_cls:

            mock_ocr = MagicMock()
            mock_ocr.read_breakdown_screen.return_value = {"is_breakdown": False}
            mock_ocr_cls.return_value = mock_ocr

            report = the_eye.cmd_analyze([url])

        assert report is not None
        assert "teams" in report
        assert "n_frames" in report
        mock_dl.assert_called_once()
        mock_frames.assert_called_once()
        fake_backend.analyze_frames.assert_called_once()

    def test_cmd_analyze_stops_if_download_fails(self, tmp_path, monkeypatch):
        url = "https://youtube.com/watch?v=BAD00000000"
        monkeypatch.setattr(the_eye, "CACHE_DIR", tmp_path / ".cache")
        monkeypatch.setattr(the_eye, "RESULTS_DIR", tmp_path / ".cache" / "results")

        with patch.object(the_eye, "download_video", return_value=None):
            result = the_eye.cmd_analyze([url])

        assert result is None

    def test_cmd_analyze_stops_if_no_frames(self, tmp_path, monkeypatch):
        url = "https://youtube.com/watch?v=NOFRAMES1234"
        monkeypatch.setattr(the_eye, "CACHE_DIR", tmp_path / ".cache")
        monkeypatch.setattr(the_eye, "RESULTS_DIR", tmp_path / ".cache" / "results")

        with patch.object(the_eye, "download_video",
                          return_value=tmp_path / "match.mp4"), \
             patch.object(the_eye, "extract_frames", return_value=[]):
            result = the_eye.cmd_analyze([url])

        assert result is None
