#!/usr/bin/env python3
"""
The Engine — THE EYE Stream Recorder
Team 2950 — The Devastators

Records live FRC event streams (Twitch/YouTube), detects match boundaries,
cuts individual match clips, and triggers analysis.

Designed to run autonomously on a cloud VM for the duration of an event.

Architecture:
  1. yt-dlp records the live stream in rolling segments (5 min chunks)
  2. Each segment is scanned for match boundaries (OCR on score overlay)
  3. When a match end is detected, the match clip is extracted
  4. The clip is passed to the_eye.py for analysis
  5. Results are saved and optionally pushed to Discord

Usage:
  # Record a live Twitch stream
  python3 stream_recorder.py record https://twitch.tv/firstinspires --event 2026txdri

  # Record a YouTube live stream
  python3 stream_recorder.py record https://youtube.com/watch?v=LIVE_ID --event 2026txdri

  # Process an already-recorded stream file
  python3 stream_recorder.py process recording.mp4 --event 2026txdri

  # Scan a recording for match boundaries only (no cutting)
  python3 stream_recorder.py scan recording.mp4

Environment:
  DISCORD_WEBHOOK_URL — optional, for posting results to Discord
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path(__file__).parent / ".cache"
SEGMENTS_DIR = CACHE_DIR / "segments"
MATCHES_DIR = CACHE_DIR / "matches"

SEGMENT_DURATION_S = 300  # 5-minute recording chunks
SCAN_INTERVAL_S = 5       # Check for frames every N seconds within segment
MATCH_DURATION_S = 210     # ~3.5 min expected match length (with buffer)
MATCH_GAP_S = 120          # Minimum gap between match ends


# ─── Stream Recording ───


def record_stream(url: str, output_dir: Path, segment_duration: int = SEGMENT_DURATION_S):
    """Record a live stream in segments using yt-dlp + ffmpeg.

    Yields segment file paths as they complete.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    segment_idx = 0

    # Find yt-dlp
    ytdlp = None
    for p in ["/Users/safiqsindha/Library/Python/3.9/bin/yt-dlp",
              "/usr/local/bin/yt-dlp", "yt-dlp"]:
        if Path(p).exists() or subprocess.run(
            ["which", p], capture_output=True).returncode == 0:
            ytdlp = p
            break

    if not ytdlp:
        print("  ERROR: yt-dlp not found. pip3 install yt-dlp")
        return

    print(f"  Recording stream: {url}")
    print(f"  Segments: {segment_duration}s each → {output_dir}")

    while True:
        segment_path = output_dir / f"segment_{segment_idx:04d}.mp4"
        print(f"\n  Recording segment {segment_idx}...")

        # yt-dlp can download a live stream; we use ffmpeg to limit duration
        # First get the direct stream URL from yt-dlp
        try:
            result = subprocess.run(
                [ytdlp, "-g", "-f", "best[height<=720]", url],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                # Try without format filter
                result = subprocess.run(
                    [ytdlp, "-g", url],
                    capture_output=True, text=True, timeout=30
                )
            stream_url = result.stdout.strip().split("\n")[0]
        except Exception as e:
            print(f"  ERROR getting stream URL: {e}")
            print(f"  Retrying in 30s...")
            time.sleep(30)
            continue

        if not stream_url:
            print(f"  No stream URL found. Stream may be offline.")
            print(f"  Retrying in 60s...")
            time.sleep(60)
            continue

        # Record segment with ffmpeg
        cmd = [
            "ffmpeg",
            "-i", stream_url,
            "-t", str(segment_duration),
            "-c", "copy",
            "-y",
            "-loglevel", "error",
            str(segment_path),
        ]

        try:
            proc = subprocess.run(cmd, timeout=segment_duration + 60)
        except subprocess.TimeoutExpired:
            print(f"  Segment {segment_idx} timed out, continuing...")
        except Exception as e:
            print(f"  Recording error: {e}")
            time.sleep(10)
            continue

        if segment_path.exists() and segment_path.stat().st_size > 10000:
            print(f"  Segment {segment_idx} saved: {segment_path.stat().st_size / 1e6:.1f}MB")
            yield segment_path
            segment_idx += 1
        else:
            print(f"  Segment {segment_idx} empty or too small, retrying...")
            if segment_path.exists():
                segment_path.unlink()
            time.sleep(10)


def record_from_file(video_path: Path, segment_duration: int = SEGMENT_DURATION_S):
    """Split an existing recording into segments for processing.

    Yields segment file paths.
    """
    # Get video duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    total_duration = float(result.stdout.strip()) if result.stdout.strip() else 0

    if total_duration <= 0:
        print(f"  ERROR: Could not determine video duration")
        return

    print(f"  Processing: {video_path} ({total_duration:.0f}s)")

    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    segment_idx = 0
    offset = 0

    while offset < total_duration:
        segment_path = SEGMENTS_DIR / f"segment_{segment_idx:04d}.mp4"

        cmd = [
            "ffmpeg",
            "-ss", str(offset),
            "-i", str(video_path),
            "-t", str(segment_duration),
            "-c", "copy",
            "-y",
            "-loglevel", "error",
            str(segment_path),
        ]
        subprocess.run(cmd)

        if segment_path.exists() and segment_path.stat().st_size > 10000:
            yield segment_path

        offset += segment_duration
        segment_idx += 1


# ─── Match Boundary Detection ───


class MatchDetector:
    """Detects match boundaries within video segments using OCR."""

    def __init__(self):
        try:
            import easyocr
            self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except ImportError:
            raise ImportError("pip3 install easyocr")

        self.last_match_end_time = 0
        self.match_count = 0

    def scan_segment(self, segment_path: Path, segment_offset_s: float = 0) -> list:
        """Scan a segment for match boundaries.

        Returns list of detected events:
          {type: "match_end", timestamp_s: <absolute>, frame_path: ..., data: ...}
        """
        import cv2

        frames_dir = CACHE_DIR / "scan_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Clear old scan frames
        for f in frames_dir.glob("scan_*.jpg"):
            f.unlink()

        # Extract frames at scan interval
        cmd = [
            "ffmpeg", "-i", str(segment_path),
            "-vf", f"fps=1/{SCAN_INTERVAL_S}",
            "-q:v", "3",
            str(frames_dir / "scan_%04d.jpg"),
            "-y", "-loglevel", "error"
        ]
        subprocess.run(cmd)

        frames = sorted(frames_dir.glob("scan_*.jpg"))
        events = []

        for i, frame_path in enumerate(frames):
            abs_time = segment_offset_s + (i * SCAN_INTERVAL_S)

            # Skip if too close to last match end
            if abs_time - self.last_match_end_time < MATCH_GAP_S:
                continue

            # Check for transition screen (ALLIANCE WINS)
            if self._is_transition(str(frame_path)):
                events.append({
                    "type": "transition",
                    "timestamp_s": abs_time,
                    "frame_path": str(frame_path),
                })

            # Check for breakdown screen (post-match scores)
            bd = self._read_breakdown(str(frame_path))
            if bd.get("is_breakdown"):
                self.match_count += 1
                self.last_match_end_time = abs_time
                events.append({
                    "type": "match_end",
                    "timestamp_s": abs_time,
                    "match_number": self.match_count,
                    "frame_path": str(frame_path),
                    "data": bd,
                })
                print(f"    MATCH {self.match_count} END at {abs_time:.0f}s — "
                      f"Red: {bd.get('teams', {}).get('red', [])} "
                      f"Blue: {bd.get('teams', {}).get('blue', [])}")

        # Cleanup
        for f in frames:
            f.unlink()

        return events

    def _is_transition(self, frame_path: str) -> bool:
        import cv2
        img = cv2.imread(frame_path)
        if img is None:
            return False
        h, w = img.shape[:2]
        center = img[int(h * 0.3):int(h * 0.7), int(w * 0.2):int(w * 0.8)]
        results = self.reader.readtext(center)
        text = " ".join(t for (_, t, c) in results if c > 0.5).upper()
        return "WINS" in text and "ALLIANCE" in text

    def _read_breakdown(self, frame_path: str) -> dict:
        import cv2
        img = cv2.imread(frame_path)
        if img is None:
            return {}

        results = self.reader.readtext(img)
        texts = [t for (_, t, c) in results if c > 0.5]
        text_str = " ".join(texts).upper()

        is_breakdown = ("WINNER" in text_str or
                        ("RANKING POINTS" in text_str and "FUEL" in text_str))
        if not is_breakdown:
            return {"is_breakdown": False}

        h, w = img.shape[:2]
        numbers = []
        for (bbox, text, conf) in results:
            if conf > 0.5 and text.isdigit():
                cx = (bbox[0][0] + bbox[2][0]) / 2
                numbers.append({"value": int(text), "x": cx})

        teams = {"red": [], "blue": []}
        for n in numbers:
            if 200 <= n["value"] <= 99999:
                if n["x"] < w * 0.4:
                    teams["red"].append(n["value"])
                elif n["x"] > w * 0.6:
                    teams["blue"].append(n["value"])

        return {"is_breakdown": True, "teams": teams, "raw_texts": texts}


# ─── Match Clip Extraction ───


def extract_match_clip(source_path: Path, match_end_s: float,
                       match_number: int, output_dir: Path) -> Path:
    """Extract a match clip from the source, ending at match_end_s."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Match is ~3 min + post-match screens (~30s)
    # Start 4 min before the breakdown screen
    start_s = max(0, match_end_s - 240)
    duration_s = 260  # 4 min + 20s buffer

    clip_path = output_dir / f"match_{match_number:03d}.mp4"

    cmd = [
        "ffmpeg",
        "-ss", str(start_s),
        "-i", str(source_path),
        "-t", str(duration_s),
        "-c", "copy",
        "-y",
        "-loglevel", "error",
        str(clip_path),
    ]
    subprocess.run(cmd)

    if clip_path.exists():
        size_mb = clip_path.stat().st_size / 1e6
        print(f"    Clip saved: {clip_path.name} ({size_mb:.1f}MB)")
        return clip_path
    return None


# ─── Discord Integration ───


def post_to_discord(webhook_url: str, match_data: dict):
    """Post match scouting summary to Discord webhook."""
    try:
        import requests
    except ImportError:
        return

    teams = match_data.get("teams", {})
    red_teams = teams.get("red", [])
    blue_teams = teams.get("blue", [])
    match_num = match_data.get("match_number", "?")

    content = (
        f"**Match {match_num}** detected\n"
        f"Red: {', '.join(str(t) for t in red_teams)}\n"
        f"Blue: {', '.join(str(t) for t in blue_teams)}\n"
    )

    try:
        requests.post(webhook_url, json={"content": content}, timeout=10)
    except Exception as e:
        print(f"    Discord post failed: {e}")


# ─── Main Pipeline ───


class StreamPipeline:
    """Full pipeline: record → detect → cut → analyze."""

    def __init__(self, event_key: str, discord_webhook: str = None):
        self.event_key = event_key
        self.discord_webhook = discord_webhook
        self.event_dir = CACHE_DIR / "events" / event_key
        self.matches_dir = self.event_dir / "matches"
        self.detector = MatchDetector()
        self.segment_offset = 0
        self.all_events = []
        self.running = True

        signal.signal(signal.SIGINT, self._handle_sigint)
        signal.signal(signal.SIGTERM, self._handle_sigint)

    def _handle_sigint(self, sig, frame):
        print(f"\n  Stopping pipeline...")
        self.running = False

    def process_segment(self, segment_path: Path):
        """Process a single segment: scan for matches, cut clips."""
        print(f"  Scanning segment for match boundaries...")
        events = self.detector.scan_segment(segment_path, self.segment_offset)
        self.all_events.extend(events)

        for evt in events:
            if evt["type"] == "match_end":
                match_num = evt["match_number"]
                match_end = evt["timestamp_s"]

                # Extract clip
                clip = extract_match_clip(
                    segment_path, match_end - self.segment_offset,
                    match_num, self.matches_dir
                )

                # Post to Discord if configured
                if self.discord_webhook and evt.get("data"):
                    post_to_discord(self.discord_webhook, {
                        "match_number": match_num,
                        "teams": evt["data"].get("teams", {}),
                    })

        # Get segment duration for offset tracking
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(segment_path)],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            self.segment_offset += float(result.stdout.strip())

    def run_live(self, stream_url: str):
        """Run the full live pipeline."""
        self.event_dir.mkdir(parents=True, exist_ok=True)
        segments_dir = self.event_dir / "segments"

        print(f"\n  THE EYE — STREAM RECORDER")
        print(f"  Event: {self.event_key}")
        print(f"  Stream: {stream_url}")
        print(f"  {'─' * 60}")
        print(f"  Recording... (Ctrl+C to stop)\n")

        for segment_path in record_stream(stream_url, segments_dir):
            if not self.running:
                break
            self.process_segment(segment_path)

            # Optionally delete old segments to save disk
            # (keep last 2 for match extraction spanning segments)

        self._print_summary()

    def run_file(self, video_path: Path):
        """Process an existing recording."""
        self.event_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n  THE EYE — STREAM PROCESSOR")
        print(f"  Event: {self.event_key}")
        print(f"  File: {video_path}")
        print(f"  {'─' * 60}\n")

        for segment_path in record_from_file(video_path):
            if not self.running:
                break
            self.process_segment(segment_path)

        self._print_summary()

    def _print_summary(self):
        """Print summary of detected matches."""
        match_events = [e for e in self.all_events if e["type"] == "match_end"]
        print(f"\n  {'═' * 60}")
        print(f"  SUMMARY — {self.event_key}")
        print(f"  {'─' * 60}")
        print(f"  Matches detected: {len(match_events)}")

        for evt in match_events:
            teams = evt.get("data", {}).get("teams", {})
            print(f"    Match {evt['match_number']:3d} at {evt['timestamp_s']:.0f}s — "
                  f"Red {teams.get('red', [])} vs Blue {teams.get('blue', [])}")

        # Save event log
        log_path = self.event_dir / "event_log.json"
        log_data = {
            "event_key": self.event_key,
            "matches_detected": len(match_events),
            "events": [
                {k: v for k, v in e.items() if k != "frame_path"}
                for e in self.all_events
            ],
            "recorded_at": datetime.now().isoformat(),
        }
        log_path.write_text(json.dumps(log_data, indent=2, default=str))
        print(f"\n  Log saved: {log_path}")

        clips = list(self.matches_dir.glob("match_*.mp4")) if self.matches_dir.exists() else []
        if clips:
            print(f"  Match clips: {self.matches_dir} ({len(clips)} files)")
        print()


# ─── CLI ───


def cmd_record(args):
    """Record a live stream and detect matches."""
    if not args:
        print("Usage: stream_recorder.py record <stream_url> --event <event_key> [--discord <webhook_url>]")
        return

    url = args[0]
    event_key = None
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    i = 1
    while i < len(args):
        if args[i] == "--event" and i + 1 < len(args):
            event_key = args[i + 1]; i += 2
        elif args[i] == "--discord" and i + 1 < len(args):
            discord_webhook = args[i + 1]; i += 2
        else:
            i += 1

    if not event_key:
        event_key = f"event_{int(time.time())}"
        print(f"  No --event specified, using: {event_key}")

    pipeline = StreamPipeline(event_key, discord_webhook)
    pipeline.run_live(url)


def cmd_process(args):
    """Process an already-recorded stream file."""
    if not args:
        print("Usage: stream_recorder.py process <video_file> --event <event_key>")
        return

    video_path = Path(args[0])
    if not video_path.exists():
        print(f"  ERROR: {video_path} not found")
        return

    event_key = None
    i = 1
    while i < len(args):
        if args[i] == "--event" and i + 1 < len(args):
            event_key = args[i + 1]; i += 2
        else:
            i += 1

    if not event_key:
        event_key = video_path.stem

    pipeline = StreamPipeline(event_key)
    pipeline.run_file(video_path)


def cmd_scan(args):
    """Scan a recording for match boundaries only."""
    if not args:
        print("Usage: stream_recorder.py scan <video_file>")
        return

    video_path = Path(args[0])
    if not video_path.exists():
        print(f"  ERROR: {video_path} not found")
        return

    print(f"\n  Scanning: {video_path}")

    detector = MatchDetector()
    offset = 0

    for segment_path in record_from_file(video_path, segment_duration=300):
        events = detector.scan_segment(segment_path, offset)

        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(segment_path)],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            offset += float(result.stdout.strip())

    print(f"\n  Matches found: {detector.match_count}")


COMMANDS = {
    "record":  ("Record live stream and detect matches", cmd_record),
    "process": ("Process recorded video file", cmd_process),
    "scan":    ("Scan video for match boundaries only", cmd_scan),
}


def main():
    print(f"\n  THE EYE — STREAM RECORDER")
    print(f"  Team 2950 The Devastators\n")

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("  Commands:")
        for name, (desc, _) in COMMANDS.items():
            print(f"    {name:10s}  {desc}")
        print()
        print("  Live recording:")
        print("    python3 stream_recorder.py record https://twitch.tv/firstinspires --event 2026txdri")
        print()
        print("  Process existing file:")
        print("    python3 stream_recorder.py process day1_stream.mp4 --event 2026txdri")
        print()
        print("  Environment:")
        print("    DISCORD_WEBHOOK_URL — optional, posts match alerts to Discord")
        print()
        return

    cmd = sys.argv[1]
    _, handler = COMMANDS[cmd]
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()
