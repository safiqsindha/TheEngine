#!/usr/bin/env python3
"""
eye/capture/fit_dcmp.py — FIT DCMP 2026 Stream Capture Harness
Team 2950 The Devastators

Thin wrapper that takes a match number + field and kicks off a yt-dlp
capture with consistent file naming. Designed for FIT District
Championship 2026-04-15 through 2026-04-18 remote capture.

Usage:
    # Capture a single live stream to a named file
    python -m eye.capture.fit_dcmp --event 2026txcmp --field red

    # Capture a specific YouTube URL (live or VOD) with an explicit match label
    python -m eye.capture.fit_dcmp --url "https://youtube.com/watch?v=LIVE_ID" \\
        --match QM01 --field red

    # VOD slice — download a 150-second window starting at 30s into the VOD
    python -m eye.capture.fit_dcmp --url "https://youtube.com/watch?v=VOD_ID" \\
        --match QM01 --field red --seek 30 --duration 150

    # Dry-run — print the yt-dlp command without executing
    python -m eye.capture.fit_dcmp --url "https://youtube.com/watch?v=..." \\
        --match QM01 --dry-run

File naming convention:
    fit_dcmp_2026-04-15_QM01_red.mp4
    fit_dcmp_2026-04-15_QM12_blue.mp4
    fit_dcmp_2026-04-16_SF1M1_red.mp4

Storage: eye/.capture/fit_dcmp_2026/ (≈ 300–600 MB per full-day session,
    ~30 MB per 2-min match at 720p30 h264)

Dependencies: yt-dlp, ffmpeg (both checked at startup)

NOTE: Do NOT run against FIT streams before Wed 2026-04-15 — event hasn't
started. Use --dry-run or point at any past FRC YouTube VOD for testing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Known FIT DCMP stream URLs (updated as the event approaches / streams go live)
# ---------------------------------------------------------------------------
# These are the channels to watch. Actual live stream URLs change per day.
# Find them on event morning at:
#   https://www.youtube.com/@FIRSTinTexas/streams
#   https://www.twitch.tv/firstinspires        (backup, lower quality)
#   https://www.thebluealliance.com/event/2026txcmp (links to streams)
#   https://ftc.events/2026/txcmp              (FIT-specific schedule)
#
# FIRST Updates Now (FUN) YouTube channel also simulcasts championship events:
#   https://www.youtube.com/@FIRSTUpdatesNow/streams
#
# For FIT DCMP specifically, @FIRSTinTexas is the authoritative source.
# Historically they run 1–2 concurrent streams (one per competition field).
# The stream URL format is: https://www.youtube.com/watch?v=<11-char-id>
# It does NOT change during the day — a single URL covers the whole day.

KNOWN_STREAMS: dict[str, str] = {
    # Fill these in on event morning by visiting @FIRSTinTexas/streams
    # Example format (replace with actual IDs when live):
    # "2026-04-15_field1": "https://www.youtube.com/watch?v=XXXXXXXXXX",
    # "2026-04-15_field2": "https://www.youtube.com/watch?v=YYYYYYYYYY",
    # "2026-04-16_field1": "https://www.youtube.com/watch?v=ZZZZZZZZZZ",
}

# Fallback: @texasFRC posts per-match VODs within 30 min of match end.
# These are the preferred capture source for Mode A (post-match analysis).
# URL format: https://www.youtube.com/watch?v=<video_id>
# Find via: https://www.youtube.com/@texasFRC/videos

CHANNEL_URLS = {
    "firstintexas": "https://www.youtube.com/@FIRSTinTexas/streams",
    "texasfrc":     "https://www.youtube.com/@texasFRC/videos",
    "fun":          "https://www.youtube.com/@FIRSTUpdatesNow/streams",
    "tba_event":    "https://www.thebluealliance.com/event/2026txcmp",
    "twitch":       "https://www.twitch.tv/firstinspires",
}

# ---------------------------------------------------------------------------
# Storage layout
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
CAPTURE_DIR = REPO_ROOT / "eye" / ".capture" / "fit_dcmp_2026"

# Target resolution cap — 720p is optimal: OCR readable, storage tolerable.
# 480p saves ~60% space but OCR on score overlays degrades noticeably.
# 1080p costs 3x storage with minimal OCR benefit on FRC scoreboards.
HEIGHT_LIMIT = 720

# ---------------------------------------------------------------------------
# Binary checks
# ---------------------------------------------------------------------------


def _find_binary(name: str, candidates: list[str]) -> str | None:
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which(name)


def find_ytdlp() -> str:
    path = _find_binary("yt-dlp", [
        "/Users/safiqsindha/Library/Python/3.9/bin/yt-dlp",
        "/usr/local/bin/yt-dlp",
        "/opt/homebrew/bin/yt-dlp",
    ])
    if not path:
        print("ERROR: yt-dlp not found.", file=sys.stderr)
        print("  Install: pip install --user yt-dlp  OR  brew install yt-dlp", file=sys.stderr)
        sys.exit(1)
    return path


def find_ffmpeg() -> str:
    path = _find_binary("ffmpeg", [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ])
    if not path:
        print("ERROR: ffmpeg not found.", file=sys.stderr)
        print("  Install: brew install ffmpeg", file=sys.stderr)
        sys.exit(1)
    return path


# ---------------------------------------------------------------------------
# Filename builder
# ---------------------------------------------------------------------------


def build_output_filename(match_label: str, field: str, capture_date: str | None = None) -> str:
    """Build the canonical output filename for a captured match segment.

    Args:
        match_label: e.g. "QM01", "QM12", "SF1M1", "F1M1"
        field:       e.g. "red", "blue", "field1", "field2"
        capture_date: ISO date string (YYYY-MM-DD). Defaults to today.

    Returns:
        Filename like "fit_dcmp_2026-04-15_QM01_red.mp4"
    """
    if capture_date is None:
        capture_date = date.today().isoformat()
    label = match_label.upper().replace(" ", "")
    field_clean = field.lower().replace(" ", "")
    return f"fit_dcmp_{capture_date}_{label}_{field_clean}.mp4"


# ---------------------------------------------------------------------------
# yt-dlp command builder
# ---------------------------------------------------------------------------


def build_capture_cmd(
    ytdlp: str,
    url: str,
    output_path: Path,
    duration_sec: int | None,
    seek_sec: float,
    is_live: bool,
    height: int = HEIGHT_LIMIT,
    cookie_browser: str | None = None,
) -> list[str]:
    """Build the yt-dlp invocation for live or VOD capture.

    For live streams: uses --downloader ffmpeg with -t <duration>.
    For VODs: uses --download-sections for precise slicing.
    If duration_sec is None, captures the whole VOD (useful for per-match VODs
    from @texasFRC which are already trimmed to match length).
    """
    fmt = f"bv*[height<={height}]+ba/b[height<={height}]/best"

    cmd = [
        ytdlp,
        "-f", fmt,
        "--no-warnings",
        "--no-part",
        "--force-overwrites",
        "-o", str(output_path),
    ]

    if is_live and duration_sec:
        cmd += [
            "--downloader", "ffmpeg",
            "--downloader-args", f"ffmpeg_i:-t {duration_sec}",
        ]
    elif not is_live and duration_sec:
        start = max(0.0, seek_sec)
        end = start + float(duration_sec)
        cmd += [
            "--download-sections", f"*{start:.3f}-{end:.3f}",
            "--force-keyframes-at-cuts",
        ]
    # else: no duration limit — download entire VOD

    if cookie_browser:
        cmd += ["--cookies-from-browser", cookie_browser]

    cmd.append(url)
    return cmd


# ---------------------------------------------------------------------------
# Main capture entry point
# ---------------------------------------------------------------------------


def capture(
    url: str,
    output_path: Path,
    duration_sec: int | None = 150,
    seek_sec: float = 0.0,
    is_live: bool | None = None,
    cookie_browser: str | None = None,
    dry_run: bool = False,
) -> Path:
    """Capture a match segment from a YouTube URL.

    Args:
        url:           YouTube live or VOD URL.
        output_path:   Where to write the MP4.
        duration_sec:  How many seconds to capture. None = full VOD.
        seek_sec:      Skip this many seconds into a VOD before starting.
        is_live:       Override live/VOD detection. None = auto-detect.
        cookie_browser: Browser name for --cookies-from-browser (e.g. "chrome").
                       Needed if YouTube SABR is blocking unauthenticated pulls.
        dry_run:       Print command without executing.

    Returns:
        Path to the captured file (may not exist in dry_run mode).
    """
    ytdlp = find_ytdlp()
    find_ffmpeg()  # fail-fast

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect live/VOD unless caller specifies
    if is_live is None:
        if dry_run:
            is_live = False  # safe default for dry-run
            print("  [dry-run] Skipping live/VOD probe — assuming VOD")
        else:
            print("  Probing stream type (live vs VOD)...")
            try:
                result = subprocess.run(
                    [ytdlp, "--print", "is_live", "--no-warnings",
                     "--skip-download", url],
                    capture_output=True, text=True, timeout=30,
                )
                is_live = result.stdout.strip().lower() == "true"
                print(f"  Stream type: {'LIVE' if is_live else 'VOD'}")
            except subprocess.TimeoutExpired:
                print("  WARNING: probe timed out — defaulting to VOD mode")
                is_live = False

    cmd = build_capture_cmd(
        ytdlp=ytdlp,
        url=url,
        output_path=output_path,
        duration_sec=duration_sec,
        seek_sec=seek_sec,
        is_live=is_live,
        cookie_browser=cookie_browser,
    )

    if dry_run:
        print("\n  DRY RUN — would execute:")
        print("  " + " ".join(cmd))
        print(f"\n  Output: {output_path}")
        return output_path

    print(f"\n  Capturing {'LIVE' if is_live else 'VOD'}: {url}")
    print(f"  Output: {output_path}")
    if duration_sec:
        print(f"  Duration: {duration_sec}s  |  Seek: {seek_sec}s")
    else:
        print("  Duration: full VOD")

    timeout = (duration_sec or 7200) + 120  # generous timeout
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print("  ERROR: capture timed out", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"  ERROR: yt-dlp exited {result.returncode}", file=sys.stderr)
        print(f"  stderr: {result.stderr.strip()[:500]}", file=sys.stderr)
        sys.exit(1)

    if not output_path.exists() or output_path.stat().st_size < 1024:
        print("  ERROR: output file missing or too small (< 1 KB)", file=sys.stderr)
        sys.exit(1)

    size_mb = output_path.stat().st_size / 1_000_000
    print(f"  Captured: {output_path.name}  ({size_mb:.1f} MB)")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="FIT DCMP 2026 stream capture harness (Eye E.1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture live stream (run on event morning after finding the stream URL)
  python -m eye.capture.fit_dcmp \\
      --url "https://youtube.com/watch?v=LIVE_ID" \\
      --match QM01 --field red --duration 150 --cookies chrome

  # Capture a per-match VOD from @texasFRC (preferred for post-match analysis)
  python -m eye.capture.fit_dcmp \\
      --url "https://youtube.com/watch?v=VOD_ID" \\
      --match QM01 --field red

  # Dry-run: see the yt-dlp command without executing
  python -m eye.capture.fit_dcmp \\
      --url "https://youtube.com/watch?v=..." \\
      --match QM01 --dry-run

  # List known stream channels
  python -m eye.capture.fit_dcmp --list-channels

Stream discovery on event morning:
  Visit https://www.youtube.com/@FIRSTinTexas/streams
  The top card(s) will be the live streams. Copy the URL.
""",
    )

    parser.add_argument("--url", help="YouTube URL (live or VOD)")
    parser.add_argument("--match", default="UNKNOWN",
                        help="Match label, e.g. QM01, SF1M1, F1M1 (default: UNKNOWN)")
    parser.add_argument("--field", default="field1",
                        help="Field identifier: red|blue|field1|field2 (default: field1)")
    parser.add_argument("--date", dest="capture_date",
                        help="Capture date YYYY-MM-DD (default: today)")
    parser.add_argument("--duration", type=int, default=None,
                        help="Seconds to capture (default: full VOD for VODs, 150 for live)")
    parser.add_argument("--seek", type=float, default=0.0,
                        help="Seek this many seconds into a VOD before starting (VOD only)")
    parser.add_argument("--live", action="store_true", default=None,
                        help="Force live-stream mode (skip auto-detect)")
    parser.add_argument("--cookies", dest="cookie_browser",
                        help="Browser for --cookies-from-browser (e.g. chrome, safari). "
                             "Use if you hit 403s.")
    parser.add_argument("--output-dir", type=Path, default=CAPTURE_DIR,
                        help=f"Directory to write captures (default: {CAPTURE_DIR})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print yt-dlp command without running it")
    parser.add_argument("--list-channels", action="store_true",
                        help="Print known stream channel URLs and exit")

    args = parser.parse_args()

    print("\n  THE EYE — FIT DCMP 2026 Capture Harness")
    print("  Team 2950 The Devastators\n")

    if args.list_channels:
        print("  Known stream channels for FIT DCMP 2026:\n")
        for name, url in CHANNEL_URLS.items():
            print(f"    {name:20s}  {url}")
        if KNOWN_STREAMS:
            print("\n  Pre-discovered stream URLs:")
            for key, url in KNOWN_STREAMS.items():
                print(f"    {key:30s}  {url}")
        else:
            print("\n  No pre-discovered stream URLs yet.")
            print("  Find live streams on event morning at:")
            print(f"    {CHANNEL_URLS['firstintexas']}")
        print()
        return

    if not args.url:
        parser.error("--url is required (or use --list-channels)")

    # Build output filename
    filename = build_output_filename(
        match_label=args.match,
        field=args.field,
        capture_date=args.capture_date,
    )
    output_path = args.output_dir / filename

    # Duration logic: default to full VOD unless --live or --duration specified
    is_live = True if args.live else None
    duration = args.duration
    if is_live and duration is None:
        duration = 150  # default 2.5 min segment for live capture

    capture(
        url=args.url,
        output_path=output_path,
        duration_sec=duration,
        seek_sec=args.seek,
        is_live=is_live,
        cookie_browser=args.cookie_browser,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        print(f"\n  Next step — run the Eye pipeline against this capture:")
        print(f"    cd \"{REPO_ROOT}\"")
        print(f"    python3 eye/the_eye.py analyze '{output_path}' \\")
        print(f"        --tier scored --backend haiku")
        print()


if __name__ == "__main__":
    main()
