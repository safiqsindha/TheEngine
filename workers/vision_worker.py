#!/usr/bin/env python3
"""
The Engine — Live Scout Vision Worker (Phase 2 T2 V3)
Team 2950 — The Devastators

The vision worker is a follow-on pass after Mode A / Mode B have written
LiveMatch records with OCR-derived scores. It walks `state['live_matches']`,
finds matches that are missing the Phase 2 vision fields
(`vision_events`, `cycle_counts`, `climb_results`), resolves cached
frames for each, runs the YOLO model from `eye/vision_yolo.py`, and
folds the typed vision output back into the LiveMatch dict.

Pipeline:
  1. Load pick_board state
  2. Filter live_matches → ones with no vision_events yet
  3. For each, ask the FrameResolver to materialize a frame slice
  4. Run VisionYolo.infer_frames on the slice
  5. aggregate_cycle_counts + aggregate_climb_results
  6. Mutate the LiveMatch dict in state with the typed vision fields
  7. Save state at the end (only if anything changed)

Idempotency: a match that already has `vision_events` populated is
skipped on subsequent runs. To re-run vision on a match, the operator
clears those three fields manually (or runs with --force, see CLI).

Source-tier rules: vision worker doesn't change `source_tier`. It only
adds vision data alongside whatever Mode A/B already wrote.

Usage:
    # Process every unprocessed match at our event from cached frames
    python -m workers.vision_worker --event 2026txbel \\
        --frames-dir-pattern "eye/.cache/{event}/{match_short}/frames"

    # Process a specific match (debug / replay)
    python -m workers.vision_worker --event 2026txbel --match qm32 \\
        --frames-dir-pattern "eye/.cache/{event}/{match_short}/frames"

    # Re-run vision on already-processed matches
    python -m workers.vision_worker --event 2026txbel --force \\
        --frames-dir-pattern "eye/.cache/{event}/{match_short}/frames"

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §T2 V3 / Phase 2.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ─── Path bootstrap ───
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "eye"))
sys.path.insert(0, str(_ROOT / "scout"))

from vision_yolo import (  # noqa: E402
    VisionYolo,
    aggregate_climb_results,
    aggregate_cycle_counts,
)
from workers.mode_b import FrameResolver, make_directory_pattern_resolver


# ─── Result type ───


@dataclass
class VisionWorkerResult:
    """Counts from one vision worker run, mirrors ModeBResult shape."""

    processed: list[str] = field(default_factory=list)        # match_keys updated
    skipped_existing: list[str] = field(default_factory=list)  # already had vision data
    skipped_no_frames: list[str] = field(default_factory=list)  # resolver returned None
    skipped_no_events: list[str] = field(default_factory=list)  # YOLO found nothing
    errors: list[tuple[str, str]] = field(default_factory=list)  # (match_key, message)

    @property
    def total_seen(self) -> int:
        return (
            len(self.processed)
            + len(self.skipped_existing)
            + len(self.skipped_no_frames)
            + len(self.skipped_no_events)
            + len(self.errors)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "processed": list(self.processed),
            "skipped_existing": list(self.skipped_existing),
            "skipped_no_frames": list(self.skipped_no_frames),
            "skipped_no_events": list(self.skipped_no_events),
            "errors": list(self.errors),
            "total_seen": self.total_seen,
        }


# ─── Pure logic ───


def find_unprocessed_matches(
    state: dict[str, Any],
    *,
    event_key: Optional[str] = None,
    only_match_key: Optional[str] = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Walk state['live_matches'] and return entries that need vision.

    Selection rules:
      - When `only_match_key` is given, return exactly that record (or
        nothing) regardless of vision status. The CLI uses this for
        targeted replay.
      - When `event_key` is given, restrict to matches whose event_key
        matches.
      - When `force=False`, skip records that already have a non-empty
        `vision_events` list. With `force=True`, every candidate is
        returned.
    """
    out: list[dict[str, Any]] = []
    matches = state.get("live_matches") or {}
    for key, record in matches.items():
        if only_match_key is not None:
            if key == only_match_key:
                out.append(record)
            continue
        if event_key is not None and record.get("event_key") != event_key:
            continue
        if not force and record.get("vision_events"):
            continue
        out.append(record)
    return out


def _shape_match_short(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Build the minimal TBA-shaped dict the FrameResolver expects.

    The mode_b directory-pattern resolver keys on `comp_level`,
    `match_number`, and `set_number`. LiveMatch records carry those
    same fields under different names (`comp_level`, `match_num`).
    """
    comp_level = record.get("comp_level")
    match_num = record.get("match_num")
    if comp_level is None or match_num is None:
        return None
    set_num = record.get("set_num")
    return {
        "comp_level": comp_level,
        "match_number": match_num,
        "set_number": set_num,
    }


def process_match_vision(
    *,
    record: dict[str, Any],
    frame_resolver: FrameResolver,
    vision: VisionYolo,
) -> tuple[Optional[dict[str, Any]], str]:
    """Run vision on one LiveMatch record. Mutates `record` on success.

    Returns (mutated_record, status) where status is one of:
        "processed"            — vision events written into record
        "skipped_no_frames"    — resolver returned None
        "skipped_no_events"    — YOLO returned no events
        "error:<message>"      — exception during processing
    """
    shaped = _shape_match_short(record)
    if shaped is None:
        return None, "error:bad_record_shape"

    try:
        resolved = frame_resolver(shaped)
    except Exception as e:
        return None, f"error:resolver:{e}"

    if resolved is None:
        return None, "skipped_no_frames"

    frames, _video_id, cleanup = resolved

    try:
        events = vision.infer_frames(frames)
    except Exception as e:
        return None, f"error:vision:{e}"
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

    if not events:
        return None, "skipped_no_events"

    record["vision_events"] = [e.to_dict() for e in events]
    record["cycle_counts"] = aggregate_cycle_counts(events)
    record["climb_results"] = aggregate_climb_results(events)
    return record, "processed"


# ─── Top-level orchestrator ───


def run_vision_worker(
    *,
    event_key: Optional[str] = None,
    only_match_key: Optional[str] = None,
    state: dict[str, Any],
    frame_resolver: FrameResolver,
    vision: Optional[VisionYolo] = None,
    force: bool = False,
) -> VisionWorkerResult:
    """End-to-end vision worker pass over a pick_board state dict.

    Args:
        event_key: Restrict to matches at this event. None means every
            event in state (rare, but supported for ad-hoc backfills).
        only_match_key: Process exactly this match_key, ignoring the
            event filter and the "already processed" skip.
        state: pick_board state dict to mutate in place.
        frame_resolver: Returns frames for one TBA-shaped match dict.
        vision: VisionYolo wrapper. Defaults to the fake model so the
            worker is wired end-to-end even before V0a is resolved.
        force: When True, re-run vision on already-processed matches.

    Returns:
        VisionWorkerResult counts. The caller is responsible for saving
        state — `run_vision_worker` only mutates the in-memory dict.
    """
    if vision is None:
        vision = VisionYolo(model_name="fake")

    candidates = find_unprocessed_matches(
        state,
        event_key=event_key,
        only_match_key=only_match_key,
        force=force,
    )
    candidate_keys = {c.get("match_key") for c in candidates}

    result = VisionWorkerResult()

    # Census every match in scope so the result is a complete picture.
    matches = state.get("live_matches") or {}
    if only_match_key is None:
        for key, record in matches.items():
            if event_key is not None and record.get("event_key") != event_key:
                continue
            if key in candidate_keys:
                continue
            # Already had vision_events and we're not forcing.
            result.skipped_existing.append(key)

    for record in candidates:
        match_key = record.get("match_key", "<unknown>")
        try:
            mutated, status = process_match_vision(
                record=record,
                frame_resolver=frame_resolver,
                vision=vision,
            )
        except Exception as e:
            result.errors.append((match_key, f"orchestrator:{e}"))
            continue

        if status == "processed":
            result.processed.append(match_key)
        elif status == "skipped_no_frames":
            result.skipped_no_frames.append(match_key)
        elif status == "skipped_no_events":
            result.skipped_no_events.append(match_key)
        else:
            result.errors.append((match_key, status))

    return result


# ─── CLI ───


def _format_result(event_key: Optional[str], result: VisionWorkerResult) -> str:
    label = event_key or "<all events>"
    lines = [
        f"  Vision worker — {label}",
        f"  {'─' * 60}",
        f"  Total seen          : {result.total_seen}",
        f"  Processed (new)     : {len(result.processed)}",
        f"  Skipped (existing)  : {len(result.skipped_existing)}",
        f"  Skipped (no frames) : {len(result.skipped_no_frames)}",
        f"  Skipped (no events) : {len(result.skipped_no_events)}",
        f"  Errors              : {len(result.errors)}",
    ]
    if result.errors:
        lines.append("")
        lines.append("  Errors:")
        for k, msg in result.errors[:10]:
            lines.append(f"    {k}  {msg}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout vision worker (Phase 2 T2)")
    parser.add_argument("--event", default=None,
                        help="TBA event key (e.g. 2026txbel). Omit to process all events.")
    parser.add_argument("--match", default=None,
                        help="Specific match_key (e.g. 2026txbel_qm32) to process")
    parser.add_argument("--frames-dir-pattern", required=True,
                        help='Cached frames pattern with {event} + {match_short} '
                             '(e.g. "eye/.cache/{event}/{match_short}/frames")')
    parser.add_argument("--model-name", default=None,
                        help='Vision model to use. Defaults to env MODEL_NAME or "fake".')
    parser.add_argument("--force", action="store_true",
                        help="Re-run vision on matches that already have vision_events")
    parser.add_argument("--debug", action="store_true",
                        help="Print result JSON, don't save pick_board state")
    args = parser.parse_args(argv)

    if args.match and not args.event:
        # Derive event from match_key prefix.
        event_for_resolver = args.match.rsplit("_", 1)[0]
    else:
        event_for_resolver = args.event or ""

    if not event_for_resolver:
        print("  --event or --match is required for the frame-dir resolver", file=sys.stderr)
        return 1

    frame_resolver = make_directory_pattern_resolver(
        args.frames_dir_pattern, event_key=event_for_resolver
    )

    model_name = args.model_name or os.environ.get("MODEL_NAME", "fake")
    vision = VisionYolo(model_name=model_name)

    from pick_board import load_state
    state = load_state()

    result = run_vision_worker(
        event_key=args.event,
        only_match_key=args.match,
        state=state,
        frame_resolver=frame_resolver,
        vision=vision,
        force=args.force,
    )

    print(_format_result(args.event, result))

    if args.debug:
        return 0

    if result.processed:
        from pick_board import save_state
        save_state(state)
        print(f"\n  Wrote pick_board state with vision data on {len(result.processed)} matches")
    else:
        print("\n  No new matches updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
