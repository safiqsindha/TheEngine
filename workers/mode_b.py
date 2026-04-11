#!/usr/bin/env python3
"""
The Engine — Live Scout Mode B Worker (W3)
Team 2950 — The Devastators

Mode B is the end-of-qual-day backfill worker. Mode A only processes
matches involving teams we care about right now (next-opponent focus,
fast cron). Mode B fills in everything else so that when alliance
selection comes around, every team in `state['teams']` has a complete
match history with cycle counts and breakdown subscores — no gaps.

Pipeline:
  1. Fetch every match at our event from TBA
  2. Drop matches already in `state['live_matches']` (Mode A's work)
  3. For each remaining match, ask the frame_resolver to materialize
     a frame slice from the match VOD (default: TBA's `videos` field)
  4. Run the same OCR + LiveMatch build pipeline Mode A uses
  5. append_live_match() + recompute_team_aggregates() at the end

Idempotency: append_live_match is keyed on match_key and skips writes
when the record is unchanged, so running Mode B twice produces the
same state. Mode B's cron schedule can fire generously (every 30 min
during qual day) without doubling work.

Source-tier rules:
  - Mode B always sets source_tier="vod"
  - Mode A leaves source_tier="live" alone — Mode B never overwrites
    a Mode A record because of the existing-match skip in step 2

Usage:
    # Replay an entire event from cached frames
    python -m workers.mode_b --event 2026txbel \\
        --frames-dir-pattern "eye/.cache/{event}/{match_short}/frames"

    # Live (uses TBA video keys + yt-dlp)
    python -m workers.mode_b --event 2026txbel

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §W3 / Gate 3.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ─── Path bootstrap ───
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "eye"))
sys.path.insert(0, str(_ROOT / "scout"))

from live_match import LiveMatch  # noqa: E402
from overlay_ocr import OverlayOCR  # noqa: E402
from workers.mode_a import (  # noqa: E402
    _default_event_matches,
    build_live_match_from_ocr,
    build_match_key,
    extract_frames_from_video,
    parse_match_short,
    scan_frames_for_breakdown,
)


# ─── Result type ───


@dataclass
class ModeBResult:
    """Counts from one Mode B run. Returned by `run_mode_b` so callers
    (CLI, Discord push, tests) can report what happened."""

    processed: list[str] = field(default_factory=list)        # match_keys we wrote
    skipped_existing: list[str] = field(default_factory=list)  # already in state
    skipped_no_video: list[str] = field(default_factory=list)  # resolver returned None
    skipped_no_breakdown: list[str] = field(default_factory=list)  # OCR found no breakdown
    errors: list[tuple[str, str]] = field(default_factory=list)  # (match_key, message)

    @property
    def total_seen(self) -> int:
        return (
            len(self.processed)
            + len(self.skipped_existing)
            + len(self.skipped_no_video)
            + len(self.skipped_no_breakdown)
            + len(self.errors)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "processed": list(self.processed),
            "skipped_existing": list(self.skipped_existing),
            "skipped_no_video": list(self.skipped_no_video),
            "skipped_no_breakdown": list(self.skipped_no_breakdown),
            "errors": list(self.errors),
            "total_seen": self.total_seen,
        }


# ─── Pure logic ───


def _comp_level_match_key(event_key: str, tba_match: dict[str, Any]) -> Optional[str]:
    """Build the canonical match_key for a TBA match dict, or None if the
    shape is unparseable. TBA already exposes match['key'] (e.g.
    '2026txbel_qm32'), but we re-derive it from comp_level/match_number/
    set_number so it's stable against any TBA-side key shape changes."""
    comp_level = tba_match.get("comp_level")
    if not comp_level:
        return None
    try:
        match_num = int(tba_match.get("match_number", 0))
    except (TypeError, ValueError):
        return None
    if match_num <= 0:
        return None
    set_num_raw = tba_match.get("set_number")
    set_num: Optional[int]
    if set_num_raw is None:
        set_num = None
    else:
        try:
            set_num = int(set_num_raw)
        except (TypeError, ValueError):
            return None
    try:
        return build_match_key(event_key, comp_level, match_num, set_num)
    except ValueError:
        return None


def find_missing_matches(
    tba_matches: list[dict[str, Any]],
    state: dict[str, Any],
    event_key: str,
    *,
    comp_levels: tuple[str, ...] = ("qm",),
) -> list[dict[str, Any]]:
    """Return TBA matches that aren't yet in `state['live_matches']`.

    By default only qualification matches are considered (Mode B's main
    job is filling out the alliance-selection picture). Pass
    `comp_levels=("qm", "qf", "sf", "f")` for end-of-event playoff fill.

    Match ordering is preserved (TBA returns them in scheduled order),
    which keeps the per-team `recent 3` streak window deterministic.
    """
    existing_keys: set[str] = set((state.get("live_matches") or {}).keys())
    out: list[dict[str, Any]] = []
    for m in tba_matches:
        if m.get("comp_level") not in comp_levels:
            continue
        match_key = _comp_level_match_key(event_key, m)
        if not match_key:
            continue
        if match_key in existing_keys:
            continue
        out.append(m)
    return out


def resolve_match_video_id(tba_match: dict[str, Any]) -> Optional[str]:
    """Pull the first YouTube video key from a TBA match dict, or None.

    TBA's match record exposes a `videos` array of `{type, key}` dicts;
    type "youtube" is the only one we know how to feed yt-dlp. Many
    matches have multiple — we just take the first; FRC events
    typically only have one full-event broadcast linked anyway.
    """
    for v in tba_match.get("videos", []) or []:
        if not isinstance(v, dict):
            continue
        if v.get("type") == "youtube" and v.get("key"):
            return str(v["key"])
    return None


# ─── Frame resolver ───


# A FrameResolver returns (frames, source_video_id, cleanup_handle) or None.
# cleanup_handle is anything callers can shutil.rmtree() / Path.unlink()
# after they're done with the frames; pass None when nothing needs cleanup
# (e.g. cached on-disk frames the caller wants preserved).
FrameResolver = Callable[
    [dict[str, Any]],
    Optional[tuple[list[Path], str, Optional[Any]]],
]


def make_directory_pattern_resolver(
    pattern: str,
    *,
    event_key: str,
) -> FrameResolver:
    """Return a FrameResolver that looks for cached frames at a path
    pattern with `{event}` and `{match_short}` placeholders.

    Example pattern:  "eye/.cache/{event}/{match_short}/frames"
                      → eye/.cache/2026txbel/qm32/frames

    Resolver returns None for matches whose directory doesn't exist or
    contains no frames — the caller treats that as `skipped_no_video`.
    """
    def _resolver(tba_match: dict[str, Any]) -> Optional[tuple[list[Path], str, Optional[Any]]]:
        comp_level = tba_match.get("comp_level", "")
        match_num = tba_match.get("match_number")
        set_num = tba_match.get("set_number")
        if comp_level == "qm":
            short = f"qm{match_num}"
        elif set_num is not None:
            short = f"{comp_level}{set_num}m{match_num}"
        else:
            return None
        path = Path(pattern.format(event=event_key, match_short=short))
        if not path.exists() or not path.is_dir():
            return None
        frames = sorted(path.glob("frame_*.jpg"))
        if not frames:
            return None
        # The video_id we record is the directory itself — provenance for
        # the LiveMatch.source_video_id field. No cleanup needed; these
        # frames live on disk and the caller didn't materialize them.
        return frames, str(path), None

    return _resolver


def make_tba_video_resolver(
    *,
    extra_args: Optional[list[str]] = None,
    duration_s: int = 300,
) -> FrameResolver:
    """Return a FrameResolver that pulls the YouTube VOD listed in TBA's
    match dict, runs it through hls_pull, and extracts a frame slice.

    The cleanup handle is the temp directory holding the extracted
    frames; the caller will shutil.rmtree() it after the match is
    processed. The mp4 itself is unlinked here so we don't double-store.
    """
    def _resolver(tba_match: dict[str, Any]) -> Optional[tuple[list[Path], str, Optional[Any]]]:
        video_id = resolve_match_video_id(tba_match)
        if not video_id:
            return None

        try:
            from hls_pull import pull_hls_segment  # lazy: tests don't need yt-dlp
        except ImportError:
            return None

        try:
            mp4_path = pull_hls_segment(
                f"https://www.youtube.com/watch?v={video_id}",
                duration_sec=duration_s,
                is_live=False,
                extra_args=extra_args,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            return None
        if mp4_path is None or not Path(mp4_path).exists():
            return None

        frames_dir = Path(tempfile.mkdtemp(prefix="mode_b_frames_"))
        frames = extract_frames_from_video(Path(mp4_path), frames_dir)
        # The mp4 itself isn't needed past frame extraction
        try:
            Path(mp4_path).unlink()
        except OSError:
            pass

        if not frames:
            shutil.rmtree(frames_dir, ignore_errors=True)
            return None
        return frames, video_id, frames_dir

    return _resolver


def _default_frame_resolver(event_key: str) -> FrameResolver:
    """Default resolver: try TBA video keys first, return None if none."""
    return make_tba_video_resolver()


# ─── Single-match processor ───


def process_match(
    *,
    event_key: str,
    tba_match: dict[str, Any],
    frame_resolver: FrameResolver,
    ocr: OverlayOCR,
    state: Optional[dict[str, Any]] = None,
) -> tuple[Optional[LiveMatch], str]:
    """Process one TBA match through the OCR pipeline and (optionally)
    fold the result into pick_board state.

    Returns (live_match, status) where status is one of:
        "processed"            — OCR succeeded, LiveMatch built and (if
                                 `state` was provided) appended
        "skipped_no_video"     — frame_resolver returned None
        "skipped_no_breakdown" — OCR scanned the frames but couldn't
                                 find a complete breakdown screen
        "error:<message>"      — exception during processing

    The function is its own try/finally guard so the cleanup handle from
    the resolver is always honored even when OCR raises.
    """
    try:
        resolved = frame_resolver(tba_match)
    except Exception as e:  # resolver bugs shouldn't kill the whole run
        return None, f"error:resolver:{e}"

    if resolved is None:
        return None, "skipped_no_video"

    frames, source_video_id, cleanup = resolved

    try:
        ocr_result = scan_frames_for_breakdown(frames, ocr)
        if not ocr_result.breakdown_found:
            return None, "skipped_no_breakdown"

        live_match = build_live_match_from_ocr(
            event_key=event_key,
            tba_match=tba_match,
            ocr_result=ocr_result,
            source_video_id=source_video_id,
            source_tier="vod",
        )

        if state is not None:
            from pick_board import append_live_match
            append_live_match(state, live_match)

        return live_match, "processed"
    except Exception as e:
        return None, f"error:ocr:{e}"
    finally:
        if cleanup is not None:
            try:
                if isinstance(cleanup, Path) and cleanup.exists():
                    if cleanup.is_dir():
                        shutil.rmtree(cleanup, ignore_errors=True)
                    else:
                        cleanup.unlink(missing_ok=True)
            except OSError:
                pass


# ─── Top-level orchestrator ───


def run_mode_b(
    event_key: str,
    *,
    matches_fetcher: Callable[[str], list[dict[str, Any]]] = _default_event_matches,
    frame_resolver: Optional[FrameResolver] = None,
    ocr: Optional[OverlayOCR] = None,
    state: Optional[dict[str, Any]] = None,
    comp_levels: tuple[str, ...] = ("qm",),
) -> ModeBResult:
    """End-to-end Mode B backfill: walk every match at the event, skip
    ones already in state, OCR the rest from VOD, append to state.

    Args:
        event_key: TBA event key
        matches_fetcher: Injection point for TBA. Default uses
            scout.tba_client.event_matches.
        frame_resolver: Returns frames for one TBA match. Default is
            the TBA-video-key resolver (yt-dlp under the hood). Tests
            inject a stub.
        ocr: OverlayOCR instance. Default lazy-loads PaddleOCR.
        state: pick_board state dict to mutate. If None, the worker
            still produces ModeBResult but writes nothing.
        comp_levels: Which TBA comp levels to backfill. Default qm only.

    Returns:
        ModeBResult counts. After this call, if a state dict was given
        and it lists `event_key` as the active event,
        `len(state['live_matches'])` should equal the count of qual
        matches at the event minus any matches whose VODs were missing
        or whose OCR failed (recorded as `skipped_*`).
    """
    if frame_resolver is None:
        frame_resolver = _default_frame_resolver(event_key)
    if ocr is None:
        ocr = OverlayOCR()

    try:
        tba_matches = matches_fetcher(event_key)
    except Exception as e:
        result = ModeBResult()
        result.errors.append(("__fetch__", f"matches_fetcher failed: {e}"))
        return result

    missing = find_missing_matches(
        tba_matches, state or {}, event_key, comp_levels=comp_levels
    )
    existing_keys = set(((state or {}).get("live_matches") or {}).keys())

    result = ModeBResult()

    # Record skipped-existing first so the result is a complete census
    for m in tba_matches:
        if m.get("comp_level") not in comp_levels:
            continue
        match_key = _comp_level_match_key(event_key, m)
        if match_key and match_key in existing_keys:
            result.skipped_existing.append(match_key)

    for m in missing:
        match_key = _comp_level_match_key(event_key, m) or "<unknown>"
        try:
            live_match, status = process_match(
                event_key=event_key,
                tba_match=m,
                frame_resolver=frame_resolver,
                ocr=ocr,
                state=state,
            )
        except Exception as e:
            result.errors.append((match_key, f"orchestrator:{e}"))
            continue

        if status == "processed" and live_match is not None:
            result.processed.append(live_match.match_key)
        elif status == "skipped_no_video":
            result.skipped_no_video.append(match_key)
        elif status == "skipped_no_breakdown":
            result.skipped_no_breakdown.append(match_key)
        else:
            result.errors.append((match_key, status))

    # Recompute aggregates only if we wrote anything new and a state was passed
    if state is not None and result.processed:
        from pick_board import recompute_team_aggregates
        recompute_team_aggregates(state)

    return result


# ─── CLI ───


def _format_result(event_key: str, result: ModeBResult) -> str:
    lines = [
        f"  Mode B backfill — {event_key}",
        f"  {'─' * 60}",
        f"  Total seen          : {result.total_seen}",
        f"  Processed (new)     : {len(result.processed)}",
        f"  Skipped (existing)  : {len(result.skipped_existing)}",
        f"  Skipped (no video)  : {len(result.skipped_no_video)}",
        f"  Skipped (no break)  : {len(result.skipped_no_breakdown)}",
        f"  Errors              : {len(result.errors)}",
    ]
    if result.errors:
        lines.append("")
        lines.append("  Errors:")
        for k, msg in result.errors[:10]:
            lines.append(f"    {k}  {msg}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout Mode B backfill worker")
    parser.add_argument("--event", required=True, help="TBA event key (e.g. 2026txbel)")
    parser.add_argument("--frames-dir-pattern", default=None,
                        help='Cached frames pattern with {event} + {match_short} '
                             '(e.g. "eye/.cache/{event}/{match_short}/frames"). '
                             'When set, overrides the default TBA video resolver.')
    parser.add_argument("--comp-levels", default="qm",
                        help="Comma-separated comp levels to backfill (default: qm)")
    parser.add_argument("--debug", action="store_true",
                        help="Print result JSON, don't save pick_board state")
    args = parser.parse_args(argv)

    comp_levels = tuple(s.strip() for s in args.comp_levels.split(",") if s.strip())

    frame_resolver: Optional[FrameResolver] = None
    if args.frames_dir_pattern:
        frame_resolver = make_directory_pattern_resolver(
            args.frames_dir_pattern, event_key=args.event
        )

    state: Optional[dict[str, Any]] = None
    if not args.debug:
        from pick_board import load_state
        state = load_state()

    result = run_mode_b(
        event_key=args.event,
        frame_resolver=frame_resolver,
        state=state,
        comp_levels=comp_levels,
    )

    print(_format_result(args.event, result))

    if args.debug:
        return 0

    if state is not None and result.processed:
        from pick_board import save_state
        save_state(state)
        print(f"\n  Wrote pick_board state with {len(result.processed)} new matches")
    else:
        print(f"\n  No new matches to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
