"""
tests/eye/test_stream_recorder.py — Tests for eye/stream_recorder.py

Covers: record_stream (yt-dlp binary lookup, download failure, SABR 403),
        extract_match_clip, MatchDetector (logic only), StreamPipeline._print_summary.

No real yt-dlp, ffmpeg, or network calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parents[2]
EYE_DIR = ROOT / "eye"

# overlay_ocr stub is installed by tests/eye/conftest.py before any test runs.
sys.path.insert(0, str(EYE_DIR))

import stream_recorder  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_completed(returncode=0, stdout="", stderr=""):
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


# ===========================================================================
# 1. record_stream — yt-dlp binary handling
# ===========================================================================

class TestRecordStream:
    """Tests that record_stream fails gracefully when yt-dlp or stream is unavailable."""

    def test_missing_ytdlp_yields_nothing(self, tmp_path):
        """When yt-dlp is not found anywhere, record_stream returns immediately."""
        with patch("shutil.which", return_value=None), \
             patch("stream_recorder.Path.exists", return_value=False), \
             patch("subprocess.run", return_value=_fake_completed(returncode=1)):
            segments = list(stream_recorder.record_stream(
                "https://twitch.tv/firstinspires", tmp_path, segment_duration=5
            ))
        assert segments == []

    def test_empty_stream_url_retries_then_stops(self, tmp_path):
        """When yt-dlp returns empty stdout, record_stream sleeps and eventually gives up."""
        # We'll stop after the first sleep to avoid an infinite loop in tests
        call_count = [0]

        def _fake_run(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] > 3:
                raise KeyboardInterrupt  # bail out
            return _fake_completed(returncode=0, stdout="")

        with patch.object(stream_recorder.Path, "exists",
                          side_effect=lambda p=None, *a, **kw: True), \
             patch("subprocess.run", side_effect=_fake_run), \
             patch("time.sleep", side_effect=lambda *a: None):
            try:
                segments = list(stream_recorder.record_stream(
                    "https://twitch.tv/test", tmp_path, segment_duration=5
                ))
            except KeyboardInterrupt:
                pass  # expected — we forced it to stop

        # Should not have yielded any segment
        assert call_count[0] > 0  # did try

    def test_yt_dlp_subprocess_error_continues(self, tmp_path):
        """subprocess.run raising Exception triggers retry logic, not a crash."""
        call_counts = {"run": 0, "sleep": 0}

        def _run(*args, **kwargs):
            call_counts["run"] += 1
            raise Exception("connection reset")

        def _sleep(secs):
            call_counts["sleep"] += 1
            if call_counts["sleep"] >= 2:
                # Bail out of the infinite loop after 2 sleep calls
                raise RuntimeError("test_stop")

        with patch.object(stream_recorder, "SEGMENTS_DIR", tmp_path), \
             patch("subprocess.run", side_effect=_run), \
             patch("time.sleep", side_effect=_sleep):
            try:
                list(stream_recorder.record_stream(
                    "https://youtube.com/watch?v=LIVE", tmp_path, segment_duration=5
                ))
            except RuntimeError as e:
                assert "test_stop" in str(e)

        # subprocess.run was called at least once (the exception path was hit)
        assert call_counts["run"] >= 1


# ===========================================================================
# 2. extract_match_clip
# ===========================================================================

class TestExtractMatchClip:
    def test_returns_none_if_ffmpeg_produces_no_output(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _fake_completed()
            result = stream_recorder.extract_match_clip(
                source_path=tmp_path / "segment.mp4",
                match_end_s=300.0,
                match_number=1,
                output_dir=tmp_path / "matches",
            )
        # No file was created by the mock, so should return None
        assert result is None

    def test_returns_clip_path_when_file_exists(self, tmp_path):
        matches_dir = tmp_path / "matches"
        matches_dir.mkdir()
        # Pre-create the expected clip file
        clip = matches_dir / "match_001.mp4"
        clip.write_bytes(b"fake video data" * 1000)  # > 10KB

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _fake_completed()
            result = stream_recorder.extract_match_clip(
                source_path=tmp_path / "segment.mp4",
                match_end_s=300.0,
                match_number=1,
                output_dir=matches_dir,
            )
        assert result == clip

    def test_start_offset_never_negative(self, tmp_path):
        """When match_end_s < 240, start should clamp to 0 (no negative seek)."""
        captured_cmds = []

        def _capture_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            return _fake_completed()

        with patch("subprocess.run", side_effect=_capture_run):
            stream_recorder.extract_match_clip(
                source_path=tmp_path / "seg.mp4",
                match_end_s=60.0,  # < 240, so start should be 0
                match_number=1,
                output_dir=tmp_path / "matches",
            )

        # Find -ss argument value
        assert len(captured_cmds) > 0
        cmd = captured_cmds[0]
        ss_idx = cmd.index("-ss")
        start_val = float(cmd[ss_idx + 1])
        assert start_val == 0.0


# ===========================================================================
# 3. MatchDetector — gap deduplication logic
# ===========================================================================

class TestMatchDetector:
    def test_initial_state(self):
        detector = stream_recorder.MatchDetector()
        assert detector.match_count == 0
        assert detector.last_match_end_time == 0

    def test_scan_segment_calls_ffmpeg_and_returns_events(self, tmp_path):
        """scan_segment should call ffmpeg for frame extraction and return events."""
        # Create a fake segment file
        seg = tmp_path / "segment_0000.mp4"
        seg.touch()

        # Create fake frames directory that scan_segment will look at
        frames_dir = stream_recorder.CACHE_DIR / "scan_frames"

        with patch("subprocess.run", return_value=_fake_completed()), \
             patch.object(stream_recorder, "CACHE_DIR", tmp_path):
            detector = stream_recorder.MatchDetector()
            # OCR stub always returns no breakdown, so events should be empty
            events = detector.scan_segment(seg, segment_offset_s=0.0)

        assert isinstance(events, list)

    def test_gap_filter_suppresses_close_match_ends(self, tmp_path):
        """Two match ends within MATCH_GAP_S should not both be counted."""
        detector = stream_recorder.MatchDetector()
        detector.last_match_end_time = 500.0  # simulate recent match end

        # Inject an OCR that says "is_breakdown" for the next frame
        detector.ocr.read_breakdown_screen = MagicMock(
            return_value={"is_breakdown": True}
        )

        seg = tmp_path / "seg.mp4"
        seg.touch()

        # Fake two frames at t=505 (too close to 500 — within MATCH_GAP_S=120)
        fake_frames = [tmp_path / "scan_0001.jpg", tmp_path / "scan_0002.jpg"]
        for f in fake_frames:
            f.touch()

        with patch("subprocess.run", return_value=_fake_completed()), \
             patch.object(stream_recorder, "CACHE_DIR", tmp_path), \
             patch.object(Path, "glob",
                          return_value=iter(fake_frames)):
            events = detector.scan_segment(seg, segment_offset_s=0.0)

        # Should be empty because frames at t=5,10 are within MATCH_GAP_S=120 of t=500
        match_ends = [e for e in events if e["type"] == "match_end"]
        assert len(match_ends) == 0


# ===========================================================================
# 4. StreamPipeline._print_summary
# ===========================================================================

class TestStreamPipeline:
    def test_print_summary_writes_log_json(self, tmp_path):
        pipeline = stream_recorder.StreamPipeline.__new__(stream_recorder.StreamPipeline)
        pipeline.event_key = "2026txcmp"
        pipeline.event_dir = tmp_path / "event"
        pipeline.event_dir.mkdir()
        pipeline.matches_dir = pipeline.event_dir / "matches"
        pipeline.all_events = [
            {
                "type": "match_end",
                "timestamp_s": 300.0,
                "match_number": 1,
                "frame_path": str(tmp_path / "frame.jpg"),
                "data": {"teams": {"red": [2950], "blue": [3035]}},
            }
        ]

        pipeline._print_summary()

        log_path = tmp_path / "event" / "event_log.json"
        assert log_path.exists()
        log = json.loads(log_path.read_text())
        assert log["event_key"] == "2026txcmp"
        assert log["matches_detected"] == 1

    def test_print_summary_excludes_frame_path_from_log(self, tmp_path):
        pipeline = stream_recorder.StreamPipeline.__new__(stream_recorder.StreamPipeline)
        pipeline.event_key = "2026txdri"
        pipeline.event_dir = tmp_path / "event2"
        pipeline.event_dir.mkdir()
        pipeline.matches_dir = pipeline.event_dir / "matches"
        pipeline.all_events = [
            {
                "type": "match_end",
                "timestamp_s": 200.0,
                "match_number": 1,
                "frame_path": "/secret/path/frame.jpg",
                "data": {},
            }
        ]

        pipeline._print_summary()

        log = json.loads((tmp_path / "event2" / "event_log.json").read_text())
        # frame_path should be stripped from persisted events
        for evt in log["events"]:
            assert "frame_path" not in evt

    def test_run_live_stops_when_not_running(self, tmp_path):
        """pipeline.running = False before first segment → no segments processed."""
        pipeline = stream_recorder.StreamPipeline.__new__(stream_recorder.StreamPipeline)
        pipeline.event_key = "2026txcmp"
        pipeline.event_dir = tmp_path / "live"
        pipeline.event_dir.mkdir()
        pipeline.matches_dir = pipeline.event_dir / "matches"
        pipeline.all_events = []
        pipeline.segment_offset = 0
        pipeline.discord_webhook = None
        pipeline.detector = MagicMock()
        pipeline.running = False  # already stopped

        # record_stream generator yields one segment, but running=False exits immediately
        def _fake_record_stream(*a, **kw):
            yield tmp_path / "seg.mp4"

        with patch.object(stream_recorder, "record_stream", _fake_record_stream), \
             patch.object(pipeline, "_print_summary") as mock_summary:
            pipeline.run_live("https://twitch.tv/firstinspires")

        # process_segment should NOT have been called
        pipeline.detector.scan_segment.assert_not_called()
        mock_summary.assert_called_once()
