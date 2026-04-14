"""
tests/eye/test_fit_dcmp.py — Tests for eye/capture/fit_dcmp.py

Covers: build_output_filename, build_capture_cmd, find_ytdlp/find_ffmpeg,
        capture() (dry-run, live, VOD, timeout, missing output).

No real yt-dlp, ffmpeg, or network calls.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parents[2]
EYE_DIR = ROOT / "eye"
sys.path.insert(0, str(EYE_DIR / "capture"))
sys.path.insert(0, str(EYE_DIR))

import fit_dcmp  # noqa: E402


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
# 1. build_output_filename
# ===========================================================================

class TestBuildOutputFilename:
    def test_basic_filename_format(self):
        fn = fit_dcmp.build_output_filename("QM01", "red", "2026-04-15")
        assert fn == "fit_dcmp_2026-04-15_QM01_red.mp4"

    def test_uppercase_match_label(self):
        fn = fit_dcmp.build_output_filename("qm01", "Red", "2026-04-15")
        assert "QM01" in fn
        assert "red" in fn  # field normalized to lowercase

    def test_semifinal_label(self):
        fn = fit_dcmp.build_output_filename("SF1M1", "blue", "2026-04-16")
        assert "SF1M1" in fn
        assert "blue" in fn
        assert "2026-04-16" in fn

    def test_default_date_is_today(self):
        from datetime import date
        fn = fit_dcmp.build_output_filename("QM12", "field2")
        today = date.today().isoformat()
        assert today in fn

    def test_spaces_in_label_stripped(self):
        fn = fit_dcmp.build_output_filename("QM 01", "red", "2026-04-15")
        assert " " not in fn

    def test_spaces_in_field_stripped(self):
        fn = fit_dcmp.build_output_filename("QM01", "field 1", "2026-04-15")
        assert " " not in fn


# ===========================================================================
# 2. build_capture_cmd
# ===========================================================================

class TestBuildCaptureCmd:
    def test_live_stream_includes_downloader_ffmpeg(self, tmp_path):
        cmd = fit_dcmp.build_capture_cmd(
            ytdlp="yt-dlp",
            url="https://youtube.com/watch?v=LIVE",
            output_path=tmp_path / "out.mp4",
            duration_sec=150,
            seek_sec=0.0,
            is_live=True,
        )
        assert "--downloader" in cmd
        assert "ffmpeg" in cmd

    def test_vod_with_duration_uses_download_sections(self, tmp_path):
        cmd = fit_dcmp.build_capture_cmd(
            ytdlp="yt-dlp",
            url="https://youtube.com/watch?v=VOD",
            output_path=tmp_path / "out.mp4",
            duration_sec=150,
            seek_sec=30.0,
            is_live=False,
        )
        assert "--download-sections" in cmd
        # Section string should contain start and end times
        section_idx = cmd.index("--download-sections")
        section_str = cmd[section_idx + 1]
        assert "30.000" in section_str
        assert "180.000" in section_str

    def test_no_duration_means_full_vod(self, tmp_path):
        cmd = fit_dcmp.build_capture_cmd(
            ytdlp="yt-dlp",
            url="https://youtube.com/watch?v=VOD",
            output_path=tmp_path / "out.mp4",
            duration_sec=None,
            seek_sec=0.0,
            is_live=False,
        )
        assert "--download-sections" not in cmd
        assert "--downloader-args" not in cmd

    def test_cookie_browser_included_when_specified(self, tmp_path):
        cmd = fit_dcmp.build_capture_cmd(
            ytdlp="yt-dlp",
            url="https://youtube.com/watch?v=AUTH",
            output_path=tmp_path / "out.mp4",
            duration_sec=150,
            seek_sec=0.0,
            is_live=True,
            cookie_browser="chrome",
        )
        assert "--cookies-from-browser" in cmd
        assert "chrome" in cmd

    def test_url_is_last_argument(self, tmp_path):
        url = "https://youtube.com/watch?v=TEST"
        cmd = fit_dcmp.build_capture_cmd(
            ytdlp="yt-dlp",
            url=url,
            output_path=tmp_path / "out.mp4",
            duration_sec=150,
            seek_sec=0.0,
            is_live=False,
        )
        assert cmd[-1] == url

    def test_height_limit_in_format_string(self, tmp_path):
        cmd = fit_dcmp.build_capture_cmd(
            ytdlp="yt-dlp",
            url="https://youtube.com/watch?v=X",
            output_path=tmp_path / "out.mp4",
            duration_sec=150,
            seek_sec=0.0,
            is_live=False,
            height=720,
        )
        fmt_idx = cmd.index("-f")
        fmt_str = cmd[fmt_idx + 1]
        assert "720" in fmt_str


# ===========================================================================
# 3. find_ytdlp / find_ffmpeg
# ===========================================================================

class TestBinaryFinders:
    def test_find_ytdlp_uses_shutil_which(self):
        with patch("shutil.which", return_value="/usr/bin/yt-dlp") as mock_which, \
             patch("fit_dcmp.Path.exists", return_value=False):
            result = fit_dcmp.find_ytdlp()
        assert result == "/usr/bin/yt-dlp"

    def test_find_ytdlp_exits_if_not_found(self):
        with patch("shutil.which", return_value=None), \
             patch("fit_dcmp.Path.exists", return_value=False):
            with pytest.raises(SystemExit):
                fit_dcmp.find_ytdlp()

    def test_find_ffmpeg_exits_if_not_found(self):
        with patch("shutil.which", return_value=None), \
             patch("fit_dcmp.Path.exists", return_value=False):
            with pytest.raises(SystemExit):
                fit_dcmp.find_ffmpeg()

    def test_find_ffmpeg_uses_shutil_which(self):
        with patch("shutil.which", return_value="/opt/homebrew/bin/ffmpeg"), \
             patch("fit_dcmp.Path.exists", return_value=False):
            result = fit_dcmp.find_ffmpeg()
        assert result == "/opt/homebrew/bin/ffmpeg"


# ===========================================================================
# 4. capture() — dry_run
# ===========================================================================

class TestCaptureDryRun:
    def test_dry_run_returns_output_path_without_executing(self, tmp_path, capsys):
        out = tmp_path / "fit_dcmp_2026-04-15_QM01_red.mp4"
        with patch.object(fit_dcmp, "find_ytdlp", return_value="yt-dlp"), \
             patch.object(fit_dcmp, "find_ffmpeg", return_value="ffmpeg"):
            result = fit_dcmp.capture(
                url="https://youtube.com/watch?v=TEST",
                output_path=out,
                duration_sec=150,
                seek_sec=0.0,
                is_live=False,
                dry_run=True,
            )
        assert result == out
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out

    def test_dry_run_does_not_call_subprocess(self, tmp_path):
        out = tmp_path / "capture.mp4"
        with patch.object(fit_dcmp, "find_ytdlp", return_value="yt-dlp"), \
             patch.object(fit_dcmp, "find_ffmpeg", return_value="ffmpeg"), \
             patch("subprocess.run") as mock_run:
            fit_dcmp.capture(
                url="https://youtube.com/watch?v=DRY",
                output_path=out,
                duration_sec=150,
                seek_sec=0.0,
                is_live=False,
                dry_run=True,
            )
        mock_run.assert_not_called()


# ===========================================================================
# 5. capture() — live execution paths
# ===========================================================================

class TestCaptureLive:
    def test_yt_dlp_failure_exits_nonzero(self, tmp_path):
        out = tmp_path / "capture.mp4"
        with patch.object(fit_dcmp, "find_ytdlp", return_value="yt-dlp"), \
             patch.object(fit_dcmp, "find_ffmpeg", return_value="ffmpeg"), \
             patch("subprocess.run",
                   return_value=_fake_completed(returncode=1, stderr="403 Forbidden")):
            with pytest.raises(SystemExit) as exc_info:
                fit_dcmp.capture(
                    url="https://youtube.com/watch?v=SABR",
                    output_path=out,
                    duration_sec=150,
                    is_live=False,
                )
        assert exc_info.value.code == 1

    def test_missing_output_file_exits(self, tmp_path):
        out = tmp_path / "capture.mp4"
        # subprocess succeeds but no file is created
        with patch.object(fit_dcmp, "find_ytdlp", return_value="yt-dlp"), \
             patch.object(fit_dcmp, "find_ffmpeg", return_value="ffmpeg"), \
             patch("subprocess.run", return_value=_fake_completed(returncode=0)):
            with pytest.raises(SystemExit) as exc_info:
                fit_dcmp.capture(
                    url="https://youtube.com/watch?v=NOFILE",
                    output_path=out,
                    duration_sec=150,
                    is_live=False,
                )
        assert exc_info.value.code == 1

    def test_successful_capture_returns_path(self, tmp_path):
        out = tmp_path / "capture.mp4"
        out.write_bytes(b"fake video" * 2000)  # > 1 KB so check passes

        with patch.object(fit_dcmp, "find_ytdlp", return_value="yt-dlp"), \
             patch.object(fit_dcmp, "find_ffmpeg", return_value="ffmpeg"), \
             patch("subprocess.run", return_value=_fake_completed(returncode=0)):
            result = fit_dcmp.capture(
                url="https://youtube.com/watch?v=GOOD",
                output_path=out,
                duration_sec=150,
                is_live=False,
            )
        assert result == out

    def test_timeout_exits(self, tmp_path):
        out = tmp_path / "capture.mp4"
        with patch.object(fit_dcmp, "find_ytdlp", return_value="yt-dlp"), \
             patch.object(fit_dcmp, "find_ffmpeg", return_value="ffmpeg"), \
             patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="yt-dlp", timeout=150)):
            with pytest.raises(SystemExit) as exc_info:
                fit_dcmp.capture(
                    url="https://youtube.com/watch?v=SLOW",
                    output_path=out,
                    duration_sec=150,
                    is_live=False,
                )
        assert exc_info.value.code == 1

    def test_vod_seek_offset_threaded_into_cmd(self, tmp_path):
        out = tmp_path / "capture.mp4"
        out.write_bytes(b"v" * 2000)

        captured_cmds = []

        def _capture(cmd, **kwargs):
            captured_cmds.append(cmd)
            return _fake_completed()

        with patch.object(fit_dcmp, "find_ytdlp", return_value="yt-dlp"), \
             patch.object(fit_dcmp, "find_ffmpeg", return_value="ffmpeg"), \
             patch("subprocess.run", side_effect=_capture):
            fit_dcmp.capture(
                url="https://youtube.com/watch?v=VOD",
                output_path=out,
                duration_sec=120,
                seek_sec=60.0,
                is_live=False,
            )

        # Among the captured commands, find the yt-dlp one (not the probe)
        ytdlp_calls = [c for c in captured_cmds if c and c[0] == "yt-dlp"]
        assert len(ytdlp_calls) >= 1
        final_cmd = ytdlp_calls[-1]
        # Verify download-sections contains the seek offset
        section_idx = final_cmd.index("--download-sections")
        section_str = final_cmd[section_idx + 1]
        assert "60.000" in section_str  # seek_sec
        assert "180.000" in section_str  # seek_sec + duration
