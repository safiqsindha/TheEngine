#!/usr/bin/env python3
"""
The Engine — HLS Stream Puller
Team 2950 — The Devastators

Thin wrapper around yt-dlp for pulling a fixed-duration MP4 segment from
a YouTube live stream OR a YouTube VOD. Used by Live Scout workers
(Mode A pulls live segments; Mode B / event-end / backfill pulls
slices of completed VODs).

Why yt-dlp end-to-end (not yt-dlp -g + ffmpeg)?
    yt-dlp resolves a *signed* googlevideo URL bound to the requesting
    fingerprint. Handing that URL to a separate ffmpeg invocation
    routinely 403s because cookies / referer / user-agent don't match.
    Letting yt-dlp drive the download keeps all auth in one process.

For VODs we use yt-dlp's native --download-sections slicer.
For live streams we delegate to ffmpeg via yt-dlp's --downloader flag,
passing -t to limit the recording duration.

Known production risk — YouTube SABR enforcement (2026-04-10):
    YouTube currently forces SABR streaming for the default web client,
    which makes most non-cookied formats fall back to itag=18 (360p),
    and itag=18 routinely 403s when hit by ffmpeg directly. To make this
    module work in production, the caller must pass YouTube auth flags
    via `extra_args`. Tested working combinations from local dev:
        extra_args=["--cookies-from-browser", "chrome"]
        extra_args=["--cookies", "/path/to/yt-cookies.txt"]
    For Azure deploy, plan on baking a long-lived cookies.txt into the
    worker container secret. Tracked in:
        https://github.com/yt-dlp/yt-dlp/issues/12482

Schema reference: design-intelligence/LIVE_SCOUT_PHASE1_BUILD.md §F3.

Usage:
    from hls_pull import pull_hls_segment, HLSSegment

    # Function form — caller is responsible for cleanup
    path = pull_hls_segment("https://youtube.com/watch?v=...", duration_sec=60)
    try:
        process(path)
    finally:
        path.unlink(missing_ok=True)

    # Context manager form — auto-cleanup
    with HLSSegment("https://youtube.com/watch?v=...", duration_sec=60) as path:
        process(path)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

DEFAULT_HEIGHT_LIMIT = 720           # Cap quality so OCR pipelines don't drown in pixels
YTDLP_PROBE_TIMEOUT_S = 30           # Quick metadata probes
FFMPEG_OVERHEAD_S = 60               # Tolerance above duration_sec for the actual download


# ─── Locating yt-dlp + ffmpeg ───


def _find_binary(name: str, candidates: list[str]) -> Optional[str]:
    """Return absolute path of `name` if found in candidates or PATH, else None."""
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which(name)


def find_ytdlp() -> str:
    """Locate the yt-dlp binary or raise."""
    path = _find_binary("yt-dlp", [
        "/Users/safiqsindha/Library/Python/3.9/bin/yt-dlp",
        "/usr/local/bin/yt-dlp",
        "/opt/homebrew/bin/yt-dlp",
    ])
    if not path:
        raise RuntimeError("yt-dlp not found. pip install --user yt-dlp")
    return path


def find_ffmpeg() -> str:
    """Locate the ffmpeg binary or raise.

    yt-dlp invokes ffmpeg internally, so we don't pass this in directly,
    but we still verify it exists at startup so failures are loud.
    """
    path = _find_binary("ffmpeg", [
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
    ])
    if not path:
        raise RuntimeError("ffmpeg not found. brew install ffmpeg")
    return path


# ─── Live vs VOD detection ───


def is_live_stream(youtube_url: str) -> bool:
    """Return True if the URL is currently a live broadcast."""
    ytdlp = find_ytdlp()
    try:
        result = subprocess.run(
            [ytdlp, "--print", "is_live", "--no-warnings", "--skip-download", youtube_url],
            capture_output=True, text=True, timeout=YTDLP_PROBE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"yt-dlp probe timed out for {youtube_url}") from e

    if result.returncode != 0:
        raise RuntimeError(
            f"yt-dlp probe failed for {youtube_url}: "
            f"{result.stderr.strip() or '<no stderr>'}"
        )
    return result.stdout.strip().lower() == "true"


# ─── Pulling a segment ───


def _build_download_cmd(
    ytdlp: str,
    youtube_url: str,
    output_path: Path,
    duration_sec: int,
    seek_sec: float,
    is_live: bool,
    height_limit: int,
    extra_args: Optional[list[str]] = None,
) -> list[str]:
    """Construct the yt-dlp command line for either a live or VOD pull.

    extra_args is appended *before* the URL so it can carry auth flags
    like --cookies-from-browser or --extractor-args.
    """
    fmt = f"bv*[height<={height_limit}]+ba/b[height<={height_limit}]/best"

    if is_live:
        # Live: hand off to ffmpeg as the downloader, cap with -t
        cmd = [
            ytdlp,
            "-f", fmt,
            "--no-warnings",
            "--no-part",
            "--force-overwrites",
            "--downloader", "ffmpeg",
            "--downloader-args", f"ffmpeg_i:-t {int(duration_sec)}",
            "-o", str(output_path),
        ]
    else:
        # VOD: use yt-dlp's native section slicer
        start = max(0.0, float(seek_sec))
        end = start + float(duration_sec)
        cmd = [
            ytdlp,
            "-f", fmt,
            "--no-warnings",
            "--no-part",
            "--force-overwrites",
            "--download-sections", f"*{start:.3f}-{end:.3f}",
            "--force-keyframes-at-cuts",
            "-o", str(output_path),
        ]

    if extra_args:
        cmd.extend(extra_args)
    cmd.append(youtube_url)
    return cmd


def _run_ytdlp_download(cmd: list[str], duration_sec: int) -> subprocess.CompletedProcess:
    """Execute the yt-dlp download command. Factored out for monkeypatching in tests."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=duration_sec + FFMPEG_OVERHEAD_S,
    )


def pull_hls_segment(
    youtube_url: str,
    duration_sec: int,
    *,
    output_path: Optional[Path] = None,
    seek_sec: float = 0.0,
    height_limit: int = DEFAULT_HEIGHT_LIMIT,
    is_live: Optional[bool] = None,
    extra_args: Optional[list[str]] = None,
) -> Path:
    """Download `duration_sec` of `youtube_url` to a local MP4.

    Args:
        youtube_url: YouTube watch URL (live or VOD).
        duration_sec: How many seconds of video to capture.
        output_path: Where to write. If None, a temp file is created.
            Caller owns cleanup either way.
        seek_sec: Skip this many seconds into the source before recording.
            Only honored for VODs; ignored by live streams.
        height_limit: Max video height for the format selector.
        is_live: Skip the live/VOD probe by passing this in directly. Useful
            when the caller already knows (e.g., backfill workers always
            see VODs).
        extra_args: Additional yt-dlp flags appended before the URL.
            See module docstring for the SABR enforcement note — production
            invocations need to pass auth flags here.

    Returns:
        Path to the downloaded MP4. Caller is responsible for unlinking
        when done (or use the HLSSegment context manager for auto-cleanup).
    """
    if duration_sec <= 0:
        raise ValueError(f"duration_sec must be > 0, got {duration_sec}")

    ytdlp = find_ytdlp()
    find_ffmpeg()  # fail fast if missing

    if output_path is None:
        fd, tmp_name = tempfile.mkstemp(prefix="hls_pull_", suffix=".mp4")
        os.close(fd)
        output_path = Path(tmp_name)
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if is_live is None:
        is_live = is_live_stream(youtube_url)

    cmd = _build_download_cmd(
        ytdlp=ytdlp,
        youtube_url=youtube_url,
        output_path=output_path,
        duration_sec=duration_sec,
        seek_sec=seek_sec,
        is_live=is_live,
        height_limit=height_limit,
        extra_args=extra_args,
    )

    try:
        result = _run_ytdlp_download(cmd, duration_sec)
    except subprocess.TimeoutExpired as e:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"yt-dlp timed out pulling {duration_sec}s from {youtube_url}"
        ) from e

    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"yt-dlp failed pulling {duration_sec}s from {youtube_url}: "
            f"{result.stderr.strip() or result.stdout.strip() or '<no output>'}"
        )

    if not output_path.exists() or output_path.stat().st_size < 1024:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"yt-dlp produced no usable output for {youtube_url} "
            f"(file missing or < 1 KB)"
        )

    return output_path


# ─── Context manager wrapper ───


class HLSSegment:
    """Context manager that pulls an HLS segment and cleans up on exit.

    with HLSSegment(url, duration_sec=60) as path:
        process(path)
    # path is unlinked here, even on exception
    """

    def __init__(
        self,
        youtube_url: str,
        duration_sec: int,
        *,
        seek_sec: float = 0.0,
        height_limit: int = DEFAULT_HEIGHT_LIMIT,
        is_live: Optional[bool] = None,
        extra_args: Optional[list[str]] = None,
    ):
        self.youtube_url = youtube_url
        self.duration_sec = duration_sec
        self.seek_sec = seek_sec
        self.height_limit = height_limit
        self.is_live = is_live
        self.extra_args = extra_args
        self.path: Optional[Path] = None

    def __enter__(self) -> Path:
        self.path = pull_hls_segment(
            self.youtube_url,
            self.duration_sec,
            seek_sec=self.seek_sec,
            height_limit=self.height_limit,
            is_live=self.is_live,
            extra_args=self.extra_args,
        )
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.path is not None:
            self.path.unlink(missing_ok=True)
            self.path = None
