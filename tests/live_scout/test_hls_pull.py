"""Tests for eye/hls_pull.py — yt-dlp HLS segment puller.

Network-gated tests are skipped by default. Set HLS_NETWORK_TESTS=1 to
run them against a real public YouTube VOD.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eye"))

import hls_pull  # noqa: E402
from hls_pull import (  # noqa: E402
    HLSSegment,
    _build_download_cmd,
    find_ffmpeg,
    find_ytdlp,
    is_live_stream,
    pull_hls_segment,
)

SAMPLE_MP4 = ROOT / "eye" / ".cache" / "match_sample.mp4"
RUN_NETWORK_TESTS = os.environ.get("HLS_NETWORK_TESTS") == "1"
PUBLIC_FIT_VOD = "https://www.youtube.com/watch?v=WpzeaX1vgeQ"


# ─── Binary discovery ───


def test_find_ytdlp_resolves_to_existing_path():
    path = find_ytdlp()
    assert Path(path).exists(), f"yt-dlp not found at {path}"


def test_find_ffmpeg_resolves_to_existing_path():
    path = find_ffmpeg()
    assert Path(path).exists(), f"ffmpeg not found at {path}"


# ─── Validation ───


def test_pull_rejects_zero_duration():
    with pytest.raises(ValueError, match="duration_sec"):
        pull_hls_segment("https://youtube.com/anything", 0, is_live=False)


def test_pull_rejects_negative_duration():
    with pytest.raises(ValueError, match="duration_sec"):
        pull_hls_segment("https://youtube.com/anything", -5, is_live=False)


# ─── Command builder ───


def test_build_download_cmd_vod_uses_section_slicer():
    cmd = _build_download_cmd(
        ytdlp="/usr/bin/yt-dlp",
        youtube_url="https://youtube.com/watch?v=abc",
        output_path=Path("/tmp/out.mp4"),
        duration_sec=60,
        seek_sec=120.5,
        is_live=False,
        height_limit=720,
    )
    joined = " ".join(cmd)
    assert "--download-sections" in cmd
    assert "*120.500-180.500" in cmd
    assert "--force-keyframes-at-cuts" in cmd
    assert "--downloader" not in cmd  # VOD path doesn't use the ffmpeg downloader
    assert "bv*[height<=720]+ba/b[height<=720]/best" in joined


def test_build_download_cmd_threads_extra_args_before_url():
    """extra_args (e.g., auth flags) must appear after the yt-dlp flags
    but before the final URL so yt-dlp picks them up as flags, not as
    additional positional URLs."""
    cmd = _build_download_cmd(
        ytdlp="/usr/bin/yt-dlp",
        youtube_url="https://youtube.com/watch?v=abc",
        output_path=Path("/tmp/out.mp4"),
        duration_sec=10,
        seek_sec=0,
        is_live=False,
        height_limit=720,
        extra_args=["--cookies-from-browser", "chrome"],
    )
    assert cmd[-1] == "https://youtube.com/watch?v=abc"
    assert "--cookies-from-browser" in cmd
    chrome_idx = cmd.index("--cookies-from-browser") + 1
    assert cmd[chrome_idx] == "chrome"
    # Must come before the URL (auth flag, not a positional arg)
    assert cmd.index("--cookies-from-browser") < cmd.index(
        "https://youtube.com/watch?v=abc"
    )


def test_build_download_cmd_live_uses_ffmpeg_downloader():
    cmd = _build_download_cmd(
        ytdlp="/usr/bin/yt-dlp",
        youtube_url="https://youtube.com/watch?v=abc",
        output_path=Path("/tmp/out.mp4"),
        duration_sec=60,
        seek_sec=999,  # ignored for live
        is_live=True,
        height_limit=480,
    )
    assert "--downloader" in cmd
    assert "ffmpeg" in cmd
    downloader_args_idx = cmd.index("--downloader-args") + 1
    assert "ffmpeg_i:-t 60" == cmd[downloader_args_idx]
    assert "--download-sections" not in cmd  # Live path doesn't use the slicer
    assert "bv*[height<=480]+ba/b[height<=480]/best" in " ".join(cmd)


# ─── End-to-end via fake yt-dlp (no network) ───


@pytest.mark.skipif(not SAMPLE_MP4.exists(), reason="match_sample.mp4 not in cache")
def test_pull_via_fake_ytdlp(monkeypatch, tmp_path):
    """Replace _run_ytdlp_download with a stub that copies the local sample
    to the output path. Exercises the full pipeline (validation, dispatch,
    error handling) without needing the network."""

    def fake_run(cmd, duration_sec):
        # Find -o argument and copy sample to it
        out_idx = cmd.index("-o") + 1
        out_path = Path(cmd[out_idx])
        shutil.copy(SAMPLE_MP4, out_path)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(hls_pull, "_run_ytdlp_download", fake_run)

    out = tmp_path / "segment.mp4"
    result = pull_hls_segment(
        "https://youtube.com/fake",
        duration_sec=3,
        output_path=out,
        is_live=False,
    )
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 1024


def test_pull_raises_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(cmd, duration_sec):
        return subprocess.CompletedProcess(
            cmd, returncode=1, stdout="", stderr="ERROR: 403 Forbidden"
        )
    monkeypatch.setattr(hls_pull, "_run_ytdlp_download", fake_run)

    out = tmp_path / "should_not_exist.mp4"
    with pytest.raises(RuntimeError, match="403 Forbidden"):
        pull_hls_segment(
            "https://youtube.com/fake",
            duration_sec=2,
            output_path=out,
            is_live=False,
        )
    assert not out.exists()


def test_pull_raises_on_timeout(monkeypatch, tmp_path):
    def fake_run(cmd, duration_sec):
        raise subprocess.TimeoutExpired(cmd, duration_sec)
    monkeypatch.setattr(hls_pull, "_run_ytdlp_download", fake_run)

    out = tmp_path / "should_not_exist.mp4"
    with pytest.raises(RuntimeError, match="timed out"):
        pull_hls_segment(
            "https://youtube.com/fake",
            duration_sec=2,
            output_path=out,
            is_live=False,
        )
    assert not out.exists()


def test_pull_raises_on_empty_output(monkeypatch, tmp_path):
    """If yt-dlp exits 0 but produces no file (or a tiny stub), raise."""
    def fake_run(cmd, duration_sec):
        out_idx = cmd.index("-o") + 1
        Path(cmd[out_idx]).write_bytes(b"x")  # Tiny garbage file
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(hls_pull, "_run_ytdlp_download", fake_run)

    out = tmp_path / "tiny.mp4"
    with pytest.raises(RuntimeError, match="no usable output"):
        pull_hls_segment(
            "https://youtube.com/fake",
            duration_sec=2,
            output_path=out,
            is_live=False,
        )
    assert not out.exists()


# ─── Context manager ───


@pytest.mark.skipif(not SAMPLE_MP4.exists(), reason="match_sample.mp4 not in cache")
def test_context_manager_cleans_up(monkeypatch):
    def fake_run(cmd, duration_sec):
        out_idx = cmd.index("-o") + 1
        shutil.copy(SAMPLE_MP4, cmd[out_idx])
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(hls_pull, "_run_ytdlp_download", fake_run)

    captured: dict = {}
    with HLSSegment("https://youtube.com/fake", duration_sec=2, is_live=False) as path:
        captured["path"] = path
        assert path.exists()

    assert not captured["path"].exists(), "temp file should be unlinked on exit"


@pytest.mark.skipif(not SAMPLE_MP4.exists(), reason="match_sample.mp4 not in cache")
def test_context_manager_cleans_up_on_exception(monkeypatch):
    def fake_run(cmd, duration_sec):
        out_idx = cmd.index("-o") + 1
        shutil.copy(SAMPLE_MP4, cmd[out_idx])
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(hls_pull, "_run_ytdlp_download", fake_run)

    captured: dict = {}
    with pytest.raises(RuntimeError, match="boom"):
        with HLSSegment("https://youtube.com/fake", duration_sec=2, is_live=False) as path:
            captured["path"] = path
            raise RuntimeError("boom")

    assert not captured["path"].exists(), "temp file should be unlinked on exception"


# ─── Network-gated end-to-end (skipped unless HLS_NETWORK_TESTS=1) ───


@pytest.mark.skipif(not RUN_NETWORK_TESTS,
                    reason="set HLS_NETWORK_TESTS=1 to enable")
def test_is_live_stream_against_real_vod():
    assert is_live_stream(PUBLIC_FIT_VOD) is False


@pytest.mark.skipif(not RUN_NETWORK_TESTS,
                    reason="set HLS_NETWORK_TESTS=1 to enable")
def test_pull_60s_against_real_vod(tmp_path):
    out = tmp_path / "real_vod.mp4"
    pull_hls_segment(
        PUBLIC_FIT_VOD,
        duration_sec=60,
        output_path=out,
        seek_sec=30,
    )
    assert out.exists()
    assert out.stat().st_size > 100_000  # Real video, should be at least 100 KB
