#!/usr/bin/env python3
"""
The Engine — Live Scout Mode A Worker (W2)
Team 2950 — The Devastators

Mode A is the high-frequency, opponent-focused branch of Live Scout.
On every cron tick (1 minute at our event, 5 minutes elsewhere) it:

  1. Reads dispatcher state — what's our event, where's the live stream?
  2. Asks TBA which match just finished (or is about to)
  3. Pulls a recent slice of the live broadcast
  4. OCRs frames for the post-match breakdown screen
  5. Builds a LiveMatch record (TBA-anchored team set, OCR scores)
  6. Calls append_live_match() + recompute_team_aggregates()
  7. Saves pick_board state

Source-of-truth pattern (important):
  - **Team set** is taken from TBA. OCR on team numbers in a breakdown
    screen is reliable for digits but order/grouping is fragile, and we
    already know which match this is from the cron context.
  - **Scores** come from OCR. The whole point of Live Scout is to beat
    TBA's post-match latency, so we cannot wait for TBA scores. We
    cross-validate with TBA later (Mode C anomaly check) if available.
  - **timer_state** comes from OCR (breakdown found → "post";
    otherwise → "teleop" as a placeholder).

Source-tier rules:
  - source_tier="live"  when the input was a live HLS pull
  - source_tier="vod"   when the input was a completed VOD slice
  - source_tier="backfill" only ever set by Gate 5's backfill worker

The HLS pull, frame extraction, OCR, and TBA fetch are all wired
through injectable callables so the whole pipeline can be exercised
end-to-end in unit tests against cached frames (see
tests/live_scout/test_mode_a.py and test_mode_a_integration.py).

Usage:
    # Process the most-recently-finalized match for our event
    python -m workers.mode_a --event 2026txbel

    # Process a specific match number (debug / replay)
    python -m workers.mode_a --event 2026txbel --match qm32

    # Use a local recorded VOD instead of pulling live HLS
    python -m workers.mode_a --event 2026txbel --match qm32 \\
        --frames-dir eye/.cache/WpzeaX1vgeQ/frames

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §W2.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

# ─── Path bootstrap so we can import from sibling top-level packages ───
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "eye"))
sys.path.insert(0, str(_ROOT / "scout"))

from live_match import LiveMatch  # noqa: E402
from overlay_ocr import OverlayOCR  # noqa: E402

# Constants
DEFAULT_PULL_DURATION_S = 300        # 5 minute slice per cron tick
DEFAULT_FRAME_INTERVAL_S = 5         # extract one frame every 5 seconds
DEFAULT_OCR_CONFIDENCE = 0.85        # confidence we report when scores look clean
INCOMPLETE_OCR_CONFIDENCE = 0.4      # confidence when no breakdown found yet


# ─── Match key helpers ───


_QM_RE = re.compile(r"^qm(\d+)$")
_PLAYOFF_RE = re.compile(r"^(qf|sf|f)(\d+)m(\d+)$")


def parse_match_short(short: str) -> tuple[str, int, Optional[int]]:
    """Parse a short match identifier ("qm32", "qf1m1") into
    (comp_level, match_num, set_num). Raises ValueError on bad input."""
    m = _QM_RE.match(short)
    if m:
        return ("qm", int(m.group(1)), None)
    m = _PLAYOFF_RE.match(short)
    if m:
        return (m.group(1), int(m.group(3)), int(m.group(2)))
    raise ValueError(f"unrecognized match short: {short!r}")


def build_match_key(event_key: str, comp_level: str, match_num: int,
                    set_num: Optional[int] = None) -> str:
    """Build a TBA-format match key from components."""
    if comp_level == "qm":
        return f"{event_key}_qm{match_num}"
    if set_num is None:
        raise ValueError(f"playoff comp_level {comp_level!r} requires set_num")
    return f"{event_key}_{comp_level}{set_num}m{match_num}"


# ─── TBA match resolution ───


def teams_from_tba_match(tba_match: dict[str, Any]) -> tuple[list[int], list[int]]:
    """Pull (red_teams, blue_teams) from a TBA match dict.

    TBA team_keys look like "frc2950"; we strip the prefix to get ints.
    Order is preserved (driver station 1, 2, 3 within each alliance).
    """
    alliances = tba_match.get("alliances", {})
    def _strip(keys):
        return [int(k.replace("frc", "")) for k in keys]
    red = _strip(alliances.get("red", {}).get("team_keys", []))
    blue = _strip(alliances.get("blue", {}).get("team_keys", []))
    return red, blue


def find_target_match(
    matches: list[dict[str, Any]],
    *,
    explicit_short: Optional[str] = None,
    our_team: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Pick the match Mode A should process from a TBA matches list.

    Selection rules:
      1. If `explicit_short` is given (e.g. "qm32"), find that exact match.
      2. Otherwise, find the most recent qm match that has a non-zero
         actual_time and complete scores. This is "the match that just
         finished and TBA has caught up on" — typical for Mode B replays.
      3. If nothing has actual_time, fall back to the latest match by
         match_number that has scores set.

    `our_team` is reserved for future Mode A selection logic that prefers
    matches involving 2950 or scheduled opponents; not used in Phase 1.
    """
    if explicit_short:
        comp_level, match_num, set_num = parse_match_short(explicit_short)
        for m in matches:
            if m.get("comp_level") != comp_level:
                continue
            if int(m.get("match_number", 0)) != match_num:
                continue
            if comp_level != "qm" and int(m.get("set_number", 0)) != set_num:
                continue
            return m
        return None

    # Mode B / autonomous default — most recently finalized qual
    quals = [m for m in matches if m.get("comp_level") == "qm"]
    finalized = [
        m for m in quals
        if int(m.get("actual_time") or 0) > 0
        and m.get("alliances", {}).get("red", {}).get("score", -1) >= 0
        and m.get("alliances", {}).get("blue", {}).get("score", -1) >= 0
    ]
    if finalized:
        return max(finalized, key=lambda m: int(m["actual_time"]))

    scored = [
        m for m in quals
        if m.get("alliances", {}).get("red", {}).get("score", -1) >= 0
        and m.get("alliances", {}).get("blue", {}).get("score", -1) >= 0
    ]
    if scored:
        return max(scored, key=lambda m: int(m.get("match_number", 0)))
    return None


# ─── Frame extraction ───


def extract_frames_from_video(
    video_path: Path,
    output_dir: Path,
    interval_s: int = DEFAULT_FRAME_INTERVAL_S,
) -> list[Path]:
    """Run ffmpeg to extract one frame every `interval_s` seconds.

    Returned paths are sorted by frame number.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame_%04d.jpg"
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", f"fps=1/{interval_s}",
        "-q:v", "2",
        str(pattern),
        "-y", "-loglevel", "error",
    ]
    subprocess.run(cmd, capture_output=True)
    return sorted(output_dir.glob("frame_*.jpg"))


def _list_cached_frames(frames_dir: Path) -> list[Path]:
    """Return frame_*.jpg paths from a directory in numeric order."""
    return sorted(frames_dir.glob("frame_*.jpg"))


# ─── Core OCR pipeline ───


@dataclass
class OCRResult:
    """What the OCR pipeline pulls out of a video segment."""
    breakdown_found: bool
    red_score: Optional[int]
    blue_score: Optional[int]
    winner: Optional[str]                       # "red" | "blue" | "tie" | None
    breakdown_frame: Optional[Path] = None      # path to the frame we matched on
    confidence: float = 0.0


def scan_frames_for_breakdown(
    frames: list[Path],
    ocr: OverlayOCR,
) -> OCRResult:
    """Walk frames looking for a post-match breakdown screen.

    Returns the *first* high-quality breakdown reading found. We don't
    cross-frame consensus here — that's a Phase 2 improvement. The bigger
    risk is finding a breakdown frame that's mid-fade-in (partial OCR);
    we filter on having BOTH alliance scores extracted to mitigate that.
    """
    for f in frames:
        bd = ocr.read_breakdown_screen(str(f))
        if not bd or not bd.get("is_breakdown"):
            continue
        scores = bd.get("scores", {}) or {}
        red = scores.get("red")
        blue = scores.get("blue")
        if red is None or blue is None:
            # Partial breakdown read — e.g. fade-in frame. Keep scanning.
            continue
        return OCRResult(
            breakdown_found=True,
            red_score=int(red),
            blue_score=int(blue),
            winner=bd.get("winner"),
            breakdown_frame=f,
            confidence=DEFAULT_OCR_CONFIDENCE,
        )

    return OCRResult(
        breakdown_found=False,
        red_score=None,
        blue_score=None,
        winner=None,
        breakdown_frame=None,
        confidence=INCOMPLETE_OCR_CONFIDENCE,
    )


# ─── Build LiveMatch from OCR + TBA ───


def build_live_match_from_ocr(
    *,
    event_key: str,
    tba_match: dict[str, Any],
    ocr_result: OCRResult,
    source_video_id: str,
    source_tier: str,
) -> LiveMatch:
    """Stitch a TBA-anchored team set + OCR-derived scores into a LiveMatch.

    Validates the result via LiveMatch.__post_init__ — bad inputs raise
    ValueError, which the caller should let propagate so the cron tick
    fails loudly rather than silently writing garbage.
    """
    comp_level = tba_match.get("comp_level", "qm")
    match_num = int(tba_match.get("match_number", 0))
    set_num = tba_match.get("set_number")
    if comp_level != "qm" and set_num is None:
        raise ValueError(f"playoff TBA match missing set_number: {tba_match}")

    match_key = build_match_key(
        event_key=event_key,
        comp_level=comp_level,
        match_num=match_num,
        set_num=int(set_num) if set_num is not None else None,
    )

    red_teams, blue_teams = teams_from_tba_match(tba_match)

    timer_state = "post" if ocr_result.breakdown_found else "teleop"

    return LiveMatch(
        event_key=event_key,
        match_key=match_key,
        match_num=match_num,
        comp_level=comp_level,
        red_teams=red_teams,
        blue_teams=blue_teams,
        red_score=ocr_result.red_score,
        blue_score=ocr_result.blue_score,
        winning_alliance=ocr_result.winner,
        timer_state=timer_state,
        source_video_id=source_video_id,
        source_tier=source_tier,
        confidence=ocr_result.confidence,
    )


# ─── Default I/O wiring (overridable for tests) ───


def _default_event_matches(event_key: str) -> list[dict[str, Any]]:
    """Default TBA match fetcher. Tests inject their own."""
    sys.path.insert(0, str(_ROOT / "scout"))
    from tba_client import event_matches
    return event_matches(event_key)


def _default_frame_source(
    video_id: str,
    is_live: bool,
    duration_s: int,
    extra_args: Optional[list[str]],
) -> tuple[list[Path], Path]:
    """Pull HLS, extract frames, return (frames, cleanup_handle).

    Caller MUST call cleanup_handle.unlink() / shutil.rmtree() after use.
    Tests bypass this entirely by calling the pipeline with a frame list.
    """
    from hls_pull import pull_hls_segment

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    mp4_path = pull_hls_segment(
        video_url,
        duration_sec=duration_s,
        is_live=is_live,
        extra_args=extra_args,
    )
    frames_dir = Path(tempfile.mkdtemp(prefix="mode_a_frames_"))
    frames = extract_frames_from_video(mp4_path, frames_dir)
    return frames, mp4_path


# ─── Top-level orchestrator ───


def run_mode_a(
    *,
    event_key: str,
    explicit_match_short: Optional[str] = None,
    source_video_id: str = "",
    source_tier: str = "live",
    frames: Optional[list[Path]] = None,
    duration_s: int = DEFAULT_PULL_DURATION_S,
    extra_args: Optional[list[str]] = None,
    ocr: Optional[OverlayOCR] = None,
    matches_fetcher: Callable[[str], list[dict[str, Any]]] = _default_event_matches,
    frame_source: Callable[..., tuple[list[Path], Any]] = _default_frame_source,
    state: Optional[dict[str, Any]] = None,
) -> Optional[LiveMatch]:
    """End-to-end Mode A pipeline: TBA → frames → OCR → LiveMatch → state.

    Args:
        event_key: TBA event key, e.g. "2026txbel"
        explicit_match_short: Optional "qm32" / "qf1m1" target. If None,
            picks the most recently finalized qm.
        source_video_id: YouTube video ID feeding this run. Used for the
            LiveMatch.source_video_id field and to drive HLS pulling.
        source_tier: "live" / "vod" / "backfill"
        frames: Pre-extracted frame list (skips HLS pull entirely). If
            given, source_video_id is still required for provenance.
        duration_s: Seconds of HLS to pull when frames is None.
        extra_args: Auth flags forwarded to yt-dlp (cookies, etc).
        ocr: OverlayOCR instance. Defaults to a fresh one (lazy-loads
            PaddleOCR).
        matches_fetcher: TBA match fetcher (injectable for tests).
        frame_source: HLS-pull + frame-extract callable (injectable).
        state: pick_board state dict to mutate. If None, the caller is
            expected to wire append_live_match() / save_state() themselves.

    Returns:
        The built LiveMatch, or None if no target match could be resolved.
    """
    # 1. Resolve which match to process
    matches = matches_fetcher(event_key)
    target = find_target_match(matches, explicit_short=explicit_match_short)
    if target is None:
        return None

    # 2. Get frames (cached or live pull)
    cleanup: Optional[Any] = None
    if frames is None:
        if not source_video_id:
            raise ValueError("source_video_id is required when frames is None")
        frames, cleanup = frame_source(
            source_video_id,
            source_tier == "live",
            duration_s,
            extra_args,
        )

    try:
        # 3. OCR pipeline
        if ocr is None:
            ocr = OverlayOCR()
        ocr_result = scan_frames_for_breakdown(frames, ocr)

        # 4. Stitch into a LiveMatch
        live_match = build_live_match_from_ocr(
            event_key=event_key,
            tba_match=target,
            ocr_result=ocr_result,
            source_video_id=source_video_id,
            source_tier=source_tier,
        )

        # 5. Optionally fold into pick_board state
        if state is not None:
            from pick_board import append_live_match, recompute_team_aggregates
            if append_live_match(state, live_match):
                recompute_team_aggregates(state)

        return live_match
    finally:
        if cleanup is not None and isinstance(cleanup, Path):
            cleanup.unlink(missing_ok=True)


# ─── CLI ───


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout Mode A worker")
    parser.add_argument("--event", required=True, help="TBA event key (e.g. 2026txbel)")
    parser.add_argument("--match", default=None, help="Match short (e.g. qm32)")
    parser.add_argument("--video-id", default="",
                        help="YouTube video ID for HLS pull (skip if using --frames-dir)")
    parser.add_argument("--frames-dir", default=None,
                        help="Use cached frames in this directory instead of pulling HLS")
    parser.add_argument("--source-tier", default="live", choices=["live", "vod"])
    parser.add_argument("--duration", type=int, default=DEFAULT_PULL_DURATION_S)
    parser.add_argument("--debug", action="store_true",
                        help="Print the resolved LiveMatch JSON instead of writing state")
    args = parser.parse_args(argv)

    cached_frames = None
    if args.frames_dir:
        cached_frames = _list_cached_frames(Path(args.frames_dir))
        if not cached_frames:
            print(f"  No frames found in {args.frames_dir}", file=sys.stderr)
            return 1

    live_match = run_mode_a(
        event_key=args.event,
        explicit_match_short=args.match,
        source_video_id=args.video_id or args.frames_dir or "",
        source_tier=args.source_tier,
        frames=cached_frames,
        duration_s=args.duration,
    )

    if live_match is None:
        print(f"  Could not resolve a target match for {args.event}", file=sys.stderr)
        return 1

    if args.debug:
        print(live_match.to_json())
        return 0

    # Real run: append to pick_board state and persist
    from pick_board import (
        append_live_match,
        load_state,
        recompute_team_aggregates,
        save_state,
    )
    state = load_state()
    if append_live_match(state, live_match):
        recompute_team_aggregates(state)
        save_state(state)
        print(f"  Wrote {live_match.match_key} to pick_board state")
    else:
        print(f"  No changes ({live_match.match_key} already in state)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
