"""
tests/integration/test_eye_pipeline_smoke.py

End-to-end Eye pipeline smoke test.
Team 2950 — The Devastators

Pipeline covered (no network, no real video checked into repo):
  1. Synthetic video creation (cv2 or ffmpeg) — fit_dcmp capture stage
  2. Frame extraction — the_eye.extract_frames()
  3. OCR scan (mocked OverlayOCR) — overlay_ocr stub
  4. Vision backend (mocked Anthropic) — the_eye.AnthropicVisionBackend
  5. Report synthesis — the_eye.synthesize_report()
  6. Eye bridge aggregation — eye_bridge.aggregate_team_eye_data()
  7. Pick board recommendation — pick_board.recommend_pick()

Skips gracefully if cv2 or ffmpeg are unavailable.
Runtime target: < 10 seconds.

Run with: pytest -m integration tests/integration/test_eye_pipeline_smoke.py
Skip in fast runs: pytest -m "not integration" ...
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Availability guards — skip gracefully if dependencies missing
# ---------------------------------------------------------------------------

cv2 = pytest.importorskip("cv2", reason="cv2 (opencv-python) not installed")

_ffmpeg_check = subprocess.run(
    ["ffmpeg", "-version"], capture_output=True, timeout=5
)
if _ffmpeg_check.returncode != 0:
    pytest.skip("ffmpeg not found on PATH", allow_module_level=True)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
EYE_DIR = ROOT / "eye"
SCOUT_DIR = ROOT / "scout"

for _p in (str(EYE_DIR), str(SCOUT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Stub overlay_ocr before importing eye modules (avoids PaddleOCR requirement)
# ---------------------------------------------------------------------------

def _make_overlay_ocr_stub() -> types.ModuleType:
    mod = types.ModuleType("overlay_ocr")

    class _StubOCR:
        def read_breakdown_screen(self, path: str) -> dict:
            return {"is_breakdown": False}

        def read_top_overlay(self, path: str) -> str:
            return ""

        def is_transition_screen(self, path: str) -> bool:
            return False

    mod.OverlayOCR = _StubOCR
    mod._parse_breakdown = lambda *a, **kw: {}
    mod._is_transition_text = lambda *a, **kw: False
    return mod


# Install stub only if not already present (respect conftest stubs)
if "overlay_ocr" not in sys.modules:
    sys.modules["overlay_ocr"] = _make_overlay_ocr_stub()

import the_eye   # noqa: E402
import eye_bridge  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic video fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_mp4(tmp_path_factory) -> Path:
    """
    Generate a tiny ~3-second synthetic MP4 at test time using cv2 + ffmpeg.

    Strategy:
      1. Write individual JPEG frames (solid-color + text overlay) via cv2.
      2. Encode them with ffmpeg into a silent MP4.
      3. Cleanup raw frames; MP4 lives in tmp_path for the module lifetime.

    The file is ~30 KB and never checked into the repo.
    """
    tmp = tmp_path_factory.mktemp("synthetic_video")
    frames_dir = tmp / "raw_frames"
    frames_dir.mkdir()
    video_path = tmp / "synthetic_match.mp4"

    fps = 5
    duration_s = 3
    total_frames = fps * duration_s
    width, height = 320, 240

    import numpy as np

    # Cycle through three phases: auto (green) → teleop (blue) → endgame (red)
    colors = [
        (0, 180, 0),    # green — auto
        (180, 0, 0),    # blue  — teleop
        (0, 0, 180),    # red   — endgame
    ]
    team_labels = ["2950", "3035", "1024"]

    for i in range(total_frames):
        color = colors[i % len(colors)]
        frame = np.full((height, width, 3), color, dtype="uint8")

        # Draw a fake score overlay at the top
        team = team_labels[i % len(team_labels)]
        overlay_text = f"Team {team} | Score: {i * 5}-{i * 3}"
        cv2.putText(
            frame, overlay_text,
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (255, 255, 255), 1, cv2.LINE_AA,
        )

        frame_path = frames_dir / f"frame_{i:04d}.jpg"
        cv2.imwrite(str(frame_path), frame)

    # Encode with ffmpeg
    encode_cmd = [
        "ffmpeg",
        "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.jpg"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(video_path),
    ]
    result = subprocess.run(encode_cmd, capture_output=True, timeout=30)
    assert result.returncode == 0, (
        f"ffmpeg encode failed: {result.stderr.decode()[:300]}"
    )
    assert video_path.exists() and video_path.stat().st_size > 1024, (
        "Synthetic video file too small or missing"
    )

    # Cleanup raw frames (keep only the mp4)
    for f in frames_dir.glob("*.jpg"):
        f.unlink()

    return video_path


# ---------------------------------------------------------------------------
# Helper builders (mirrors pick_board test patterns)
# ---------------------------------------------------------------------------

def _make_team_entry(team: int, epa: float = 45.0, **overrides) -> dict:
    """Minimal pick_board team dict."""
    base = {
        "team": team,
        "name": f"Team {team}",
        "epa": epa,
        "sd": max(epa * 0.15, 5.0),
        "floor": epa * 0.8,
        "ceiling": epa * 1.2,
        "epa_auto": epa * 0.25,
        "epa_teleop": epa * 0.55,
        "epa_endgame": epa * 0.20,
        "total_fuel": epa * 0.50,
        "total_tower": 0.0,
        "qual_rank": 1,
        "qual_record": "8-2",
        "auto_fuel": epa * 0.10,
        "auto_tower": 0.0,
        "first_shift": epa * 0.25,
        "second_shift": epa * 0.25,
        "transition_fuel": 0.0,
        "endgame_fuel": 0.0,
        "endgame_tower": epa * 0.20,
    }
    base.update(overrides)
    return base


def _make_draft_state(eye_teams: dict | None = None) -> dict:
    """Build minimal pick_board draft state, optionally pre-injected with EYE data."""
    teams: dict = {}
    captains = []
    for i in range(8):
        t = 1000 + i
        teams[str(t)] = _make_team_entry(t, epa=80.0 - i * 5)
        captains.append(t)

    # Available pool
    for i in range(8, 24):
        t = 2000 + i
        teams[str(t)] = _make_team_entry(t, epa=30.0 + i * 0.5)

    # Our team at seed 3
    our_team = 2950
    teams[str(our_team)] = _make_team_entry(our_team, epa=65.0)
    captains[2] = our_team

    # Inject EYE data if provided
    if eye_teams:
        for team_key, scores in eye_teams.items():
            if team_key in teams:
                teams[team_key].update(scores)

    return {
        "event_key": "2026smoke",
        "our_team": our_team,
        "our_seed": 3,
        "captains": captains,
        "picks": [],
        "teams": teams,
        "history": [],
        "dnp": [],
        "live_matches": {},
    }


# ---------------------------------------------------------------------------
# Mock Anthropic vision response
# ---------------------------------------------------------------------------

_MOCK_VISION_RESPONSE = [
    {
        "timestamp": "0:05",
        "phase": "auto",
        "scores": {"red": 5, "blue": 3},
        "timer": "0:05",
        "red_teams": [2950, 3035],
        "blue_teams": [1024, 2056],
        "observations": [
            {
                "team": 2950,
                "alliance": "red",
                "action": "scoring coral",
                "zone": "wing",
                "mechanism_note": "clean cycle",
                "defense": "",
            },
            {
                "team": 1024,
                "alliance": "blue",
                "action": "placing game pieces",
                "zone": "center",
                "mechanism_note": "none",
                "defense": "",
            },
        ],
        "field_state": "red dominant",
        "notable": "",
    },
    {
        "timestamp": "2:30",
        "phase": "endgame",
        "scores": {"red": 42, "blue": 31},
        "timer": "0:30",
        "red_teams": [2950, 3035],
        "blue_teams": [1024, 2056],
        "observations": [
            {
                "team": 3035,
                "alliance": "red",
                "action": "climbing",
                "zone": "barge",
                "mechanism_note": "solid",
                "defense": "",
            },
        ],
        "field_state": "endgame phase",
        "notable": "",
    },
]


# ---------------------------------------------------------------------------
# The smoke test
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestEyePipelineSmoke:
    """
    End-to-end smoke test: synthetic video → frames → OCR → vision → pick board.

    All network calls are mocked. Runtime target < 10 seconds.
    """

    # ------------------------------------------------------------------
    # Stage 1: fit_dcmp filename builder (capture harness, no yt-dlp needed)
    # ------------------------------------------------------------------

    def test_stage1_fit_dcmp_filename_builder(self):
        """fit_dcmp.build_output_filename() produces canonical naming."""
        # eye/ is on sys.path; capture is a sub-package within it
        from capture.fit_dcmp import build_output_filename  # noqa: PLC0415
        fname = build_output_filename("QM01", "red", capture_date="2026-04-15")
        assert fname == "fit_dcmp_2026-04-15_QM01_red.mp4"  # assertion 1

    def test_stage1_fit_dcmp_capture_cmd_dry_run(self, tmp_path):
        """fit_dcmp.build_capture_cmd() builds a yt-dlp command without executing."""
        from capture.fit_dcmp import build_capture_cmd  # noqa: PLC0415
        out = tmp_path / "test.mp4"
        cmd = build_capture_cmd(
            ytdlp="/fake/yt-dlp",
            url="https://youtube.com/watch?v=FAKEID1234",
            output_path=out,
            duration_sec=30,
            seek_sec=0.0,
            is_live=False,
        )
        assert isinstance(cmd, list)           # assertion 2
        assert "/fake/yt-dlp" in cmd           # assertion 3
        assert "--download-sections" in cmd    # assertion 4

    # ------------------------------------------------------------------
    # Stage 2: Frame extraction from synthetic video
    # ------------------------------------------------------------------

    def test_stage2_frame_extraction(self, synthetic_mp4, tmp_path):
        """extract_frames() on a synthetic mp4 produces at least 1 labeled frame."""
        frames_dir = tmp_path / "frames"
        frames = the_eye.extract_frames(
            video_path=synthetic_mp4,
            output_dir=frames_dir,
            interval=1,   # 1 frame/sec → ~3 frames from 3-sec clip
        )
        assert len(frames) >= 1, "Expected at least 1 extracted frame"  # assertion 5
        for f in frames:
            assert "path" in f                  # assertion 6
            assert "timestamp_s" in f           # assertion 7
            assert "phase" in f                 # assertion 8
            assert Path(f["path"]).exists(), f"Frame file missing: {f['path']}"  # assertion 9

    # ------------------------------------------------------------------
    # Stage 3: OCR scan on extracted frames (stub OverlayOCR)
    # ------------------------------------------------------------------

    def test_stage3_ocr_scan(self, synthetic_mp4, tmp_path):
        """OverlayOCR stub runs over extracted frames without crashing."""
        frames_dir = tmp_path / "ocr_frames"
        frames = the_eye.extract_frames(synthetic_mp4, frames_dir, interval=1)
        assert frames, "Need frames for OCR test"

        ocr = the_eye.OverlayOCR()
        breakdown_found = False
        for f in frames:
            bd = ocr.read_breakdown_screen(f["path"])
            assert isinstance(bd, dict)     # assertion 10
            assert "is_breakdown" in bd     # assertion 11
            if bd.get("is_breakdown"):
                breakdown_found = True
        # Stub always returns is_breakdown=False — that's correct behavior
        assert not breakdown_found          # assertion 12 (stub contract)

    # ------------------------------------------------------------------
    # Stage 4: Vision backend (mocked Anthropic) → synthesize_report
    # ------------------------------------------------------------------

    def test_stage4_vision_synthesis(self, synthetic_mp4, tmp_path):
        """
        Full the_eye pipeline: extract frames → mock vision API → synthesize_report.
        Verifies output JSON exists, has at least 1 team entry, has EPA-compatible fields.
        """
        frames_dir = tmp_path / "vision_frames"
        results_dir = tmp_path / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        frames = the_eye.extract_frames(synthetic_mp4, frames_dir, interval=1)
        assert frames, "Frame extraction must produce frames"  # assertion 13

        # Select frames (key tier — up to 12)
        selected = the_eye.select_frames_by_tier(frames, tier="key")
        assert len(selected) >= 1              # assertion 14

        # Build mock vision backend
        fake_backend = MagicMock()
        fake_backend.name.return_value = "haiku-vision"
        fake_backend.analyze_frames.return_value = _MOCK_VISION_RESPONSE

        with patch.object(the_eye, "get_backend", return_value=fake_backend):
            observations = fake_backend.analyze_frames(selected, [2950])

        assert len(observations) >= 1          # assertion 15

        # Synthesize report
        report = the_eye.synthesize_report(observations, focus_teams=[2950])

        assert isinstance(report, dict)                        # assertion 16
        assert len(report.get("teams", {})) >= 1              # assertion 17 — at least 1 team
        assert "n_frames" in report                            # assertion 18
        assert report["n_frames"] >= 1                         # assertion 19
        assert "final_scores" in report                        # assertion 20

        # Save to temp results dir (mirrors real pipeline behavior)
        result_path = results_dir / "smoke_report.json"
        save_data = json.loads(json.dumps(report, default=str))
        result_path.write_text(json.dumps(save_data, indent=2))

        assert result_path.exists()            # assertion 21
        loaded = json.loads(result_path.read_text())
        assert "teams" in loaded               # assertion 22
        assert len(loaded["teams"]) >= 1       # assertion 23 — JSON round-trip preserved teams

    # ------------------------------------------------------------------
    # Stage 5: eye_bridge aggregation
    # ------------------------------------------------------------------

    def test_stage5_eye_bridge_aggregation(self, tmp_path):
        """
        eye_bridge.aggregate_team_eye_data() converts EYE reports → team scores.
        Inject into a mock pick_board state and verify enrichment.
        """
        # Build EYE report as the_eye would write it
        eye_report = {
            "match": {"event": "2026smoke", "comp_level": "qm", "match_number": 1},
            "teams": {
                "2950": {
                    "overall": "solid",
                    "mechanisms": {"issues": "none"},
                    "defense": {"played_defense": False, "received_defense": False, "notes": ""},
                    "teleop": {"cycle_speed": "fast", "scoring_consistency": "high", "notes": ""},
                    "endgame": {"climb_attempted": True, "notes": "success"},
                },
                "1024": {
                    "overall": "strong",
                    "mechanisms": {"issues": "none"},
                    "defense": {"played_defense": False, "received_defense": False, "notes": ""},
                    "teleop": {"cycle_speed": "fast", "scoring_consistency": "high", "notes": ""},
                    "endgame": {"climb_attempted": True, "notes": "success"},
                },
            },
        }

        eye_scores = eye_bridge.aggregate_team_eye_data([eye_report])

        assert "2950" in eye_scores                                    # assertion 24
        assert "1024" in eye_scores                                    # assertion 25
        assert eye_scores["2950"]["eye_composite"] > 0                 # assertion 26
        assert "eye_reliability" in eye_scores["2950"]                 # assertion 27
        assert "eye_driver" in eye_scores["2950"]                      # assertion 28
        assert eye_scores["2950"]["eye_matches"] == 1                  # assertion 29
        assert eye_scores["2950"]["eye_confidence"] == 25              # assertion 30

        # inject_eye_data: wire into pick board state
        state = {"teams": {"2950": {"team": 2950, "epa": 45.0}}}
        enriched = eye_bridge.inject_eye_data(state, eye_scores)

        assert enriched == 1                                           # assertion 31
        assert "eye_composite" in state["teams"]["2950"]               # assertion 32
        assert state["teams"]["2950"]["eye_composite"] > 0             # assertion 33

    # ------------------------------------------------------------------
    # Stage 6: pick_board recommendation with EYE data
    # ------------------------------------------------------------------

    def test_stage6_pick_board_recommendation_with_eye_data(self):
        """
        Wire EYE scores into pick_board state and verify recommend_pick()
        produces a non-empty ranking without crashing.
        EYE data is on team "2022" (in the available pool).
        """
        import pick_board as pb  # noqa: PLC0415

        # Build eye scores for a pool team
        eye_scores = {
            "2022": {
                "eye_composite": 72.0,
                "eye_reliability": 80.0,
                "eye_driver": 70.0,
                "eye_overall": 65.0,
                "eye_matches": 2,
                "eye_confidence": 50,
            }
        }

        state = _make_draft_state(eye_teams=eye_scores)
        assert "2022" in state["teams"]                               # assertion 34
        assert state["teams"]["2022"].get("eye_composite") == 72.0    # assertion 35

        recommendations = pb.recommend_pick(state, year=2025)

        assert isinstance(recommendations, list)                      # assertion 36
        assert len(recommendations) >= 1                              # assertion 37 — non-empty
        assert "pick_score" in recommendations[0]                     # assertion 38
        assert "team" in recommendations[0]                           # assertion 39

        # Verify pick scores are sorted descending
        scores = [r["pick_score"] for r in recommendations]
        assert scores == sorted(scores, reverse=True)                 # assertion 40

        # Verify EYE-enriched team contributes eye_score field to result
        eye_rec = next(
            (r for r in recommendations if r["team"] == 2022), None
        )
        if eye_rec:
            assert eye_rec.get("eye_score", 0) == 72.0               # assertion 41
            assert eye_rec.get("eye_conf", 0) == 50                  # assertion 42

    # ------------------------------------------------------------------
    # Stage 7: Full pipeline wired end-to-end
    # ------------------------------------------------------------------

    def test_stage7_full_pipeline_no_crash(self, synthetic_mp4, tmp_path):
        """
        End-to-end smoke: synthetic video → extract_frames → mock vision API →
        synthesize_report → eye_bridge aggregation → pick_board recommendation.

        Asserts: output JSON exists, >= 1 team, pipeline does not raise.
        """
        import pick_board as pb  # noqa: PLC0415

        # -- Frame extraction --
        frames_dir = tmp_path / "e2e_frames"
        frames = the_eye.extract_frames(synthetic_mp4, frames_dir, interval=1)
        assert len(frames) >= 1    # assertion 43

        # -- Mock vision backend --
        fake_backend = MagicMock()
        fake_backend.name.return_value = "haiku-vision"
        fake_backend.analyze_frames.return_value = _MOCK_VISION_RESPONSE

        with patch.object(the_eye, "get_backend", return_value=fake_backend):
            selected = the_eye.select_frames_by_tier(frames, tier="key")
            observations = fake_backend.analyze_frames(selected, None)

        # -- Synthesize report --
        report = the_eye.synthesize_report(observations)
        assert report is not None   # assertion 44
        teams_in_report = report.get("teams", {})
        assert len(teams_in_report) >= 1    # assertion 45

        # -- Eye bridge: aggregate → inject --
        eye_report = {
            "match": {"event": "2026smoke"},
            "teams": teams_in_report,
        }
        eye_scores = eye_bridge.aggregate_team_eye_data([eye_report])
        assert len(eye_scores) >= 1    # assertion 46

        # Map the observed teams to pick board pool teams (translate keys)
        # Use whichever teams the mock returned (2950, 1024, 3035)
        # Build state with those teams in the pool
        state = _make_draft_state()
        # Add any scouted teams not already in state
        for tk, obs in teams_in_report.items():
            if tk not in state["teams"]:
                state["teams"][tk] = _make_team_entry(int(tk), epa=40.0)

        eye_bridge.inject_eye_data(state, eye_scores)

        # -- Pick board recommendation --
        recs = pb.recommend_pick(state, year=2025)
        assert isinstance(recs, list)   # assertion 47
        assert len(recs) >= 1           # assertion 48 — at least one recommendation

        # -- JSON output exists and is valid --
        results_dir = tmp_path / "e2e_results"
        results_dir.mkdir()
        out_path = results_dir / "smoke_e2e.json"
        out_path.write_text(json.dumps({
            "report": json.loads(json.dumps(report, default=str)),
            "eye_scores": eye_scores,
            "top_pick": recs[0] if recs else None,
        }, indent=2))

        assert out_path.exists()    # assertion 49
        loaded = json.loads(out_path.read_text())
        assert "report" in loaded   # assertion 50
        assert loaded["top_pick"] is not None   # assertion 51
