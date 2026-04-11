#!/usr/bin/env python3
"""
The Engine — Live Scout Match Boundary Detector (Phase 2 U1)
Team 2950 — The Devastators

Walks the raw boundary event stream from `overlay_ocr.detect_match_boundaries`
(transition cards + breakdown screens) and stitches it into match-scoped
segments — one `MatchBoundary` per FRC match, carrying the start/end
frame indices and the video timestamps. Those boundaries are what the
TBA uploader (Phase 2 U3) reads to pair source VODs with match_keys
before POSTing to TBA Trusted v1.

Design:
  - The raw event stream alternates: transition → breakdown → transition →
    breakdown → ... FRC event broadcasts show an ALLIANCE WINS transition
    card between matches and a breakdown screen at the end of each match.
    Different venues/broadcasts sometimes skip one or the other, so we
    have to tolerate either pattern.
  - A "segment" is the frame range from (just after the previous match's
    end) to (this match's end). The FIRST segment starts at frame 0.
    The LAST segment runs to the final frame.
  - Match ordering is strictly sequential in time. Broadcast producers
    don't jump around, so the Nth detected boundary is the Nth scheduled
    qualification match on the broadcast day — modulo dropped matches
    the OCR failed to read, which `validate_against_tba_schedule` reports.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §U1 and Phase 2 §U.

Usage (in U3 tba_uploader):

    from eye.match_boundary import detect_boundaries_from_frames
    boundaries = detect_boundaries_from_frames(
        frames=[{"path": "frame_0001.jpg", "timestamp_s": 0}, ...],
        ocr=OverlayOCR(),
        video_key="WpzeaX1vgeQ",
    )
    aligned = validate_against_tba_schedule(boundaries, tba_matches)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Path bootstrap so we can pull match_key helpers from workers/
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


# ─── Dataclass ───


@dataclass
class MatchBoundary:
    """One detected match segment on a source video.

    After `detect_boundaries_from_frames` runs, `match_key` is empty —
    the detector doesn't know which TBA match it's looking at.
    `validate_against_tba_schedule` populates it by aligning 1:1 with
    the ordered TBA qual schedule.
    """

    start_frame_idx: int
    end_frame_idx: int
    start_timestamp_s: float
    end_timestamp_s: float
    video_key: str                       # YouTube video id
    match_key: str = ""                  # populated after TBA alignment
    comp_level: str = ""                 # "qm" | "qf" | "sf" | "f"
    match_num: int = 0
    boundary_type: str = "breakdown"     # which raw event closed this segment

    def __post_init__(self) -> None:
        if self.start_frame_idx < 0:
            raise ValueError(f"start_frame_idx must be >= 0, got {self.start_frame_idx}")
        if self.end_frame_idx < self.start_frame_idx:
            raise ValueError(
                f"end_frame_idx {self.end_frame_idx} must be >= start_frame_idx "
                f"{self.start_frame_idx}"
            )
        if self.end_timestamp_s < self.start_timestamp_s:
            raise ValueError(
                f"end_timestamp_s {self.end_timestamp_s} must be >= "
                f"start_timestamp_s {self.start_timestamp_s}"
            )
        if self.boundary_type not in {"breakdown", "transition", "final"}:
            raise ValueError(f"invalid boundary_type: {self.boundary_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_frame_idx": int(self.start_frame_idx),
            "end_frame_idx": int(self.end_frame_idx),
            "start_timestamp_s": float(self.start_timestamp_s),
            "end_timestamp_s": float(self.end_timestamp_s),
            "video_key": self.video_key,
            "match_key": self.match_key,
            "comp_level": self.comp_level,
            "match_num": self.match_num,
            "boundary_type": self.boundary_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchBoundary":
        return cls(
            start_frame_idx=int(data["start_frame_idx"]),
            end_frame_idx=int(data["end_frame_idx"]),
            start_timestamp_s=float(data["start_timestamp_s"]),
            end_timestamp_s=float(data["end_timestamp_s"]),
            video_key=str(data.get("video_key", "")),
            match_key=str(data.get("match_key", "")),
            comp_level=str(data.get("comp_level", "")),
            match_num=int(data.get("match_num", 0)),
            boundary_type=str(data.get("boundary_type", "breakdown")),
        )


# ─── State machine ───


class MatchBoundaryDetector:
    """Walks a raw boundary event stream and emits `MatchBoundary` segments.

    The raw stream is a list of dicts shaped like what
    `OverlayOCR.detect_match_boundaries` returns:
      {"frame_idx": int, "timestamp_s": float, "type": "transition"|"breakdown", "data": ...}

    The detector treats a "breakdown" as the end of a match. A
    "transition" that follows a "breakdown" is treated as padding
    (alliance wins card) and does NOT open a new segment — segments
    open implicitly on the first frame after the previous breakdown.

    If the stream has transitions but no breakdowns for a given match
    (some broadcasts skip the breakdown screen), the transition closes
    the segment instead. Two consecutive transitions with no breakdown
    between them are collapsed into one segment boundary.
    """

    def __init__(self, *, video_key: str, total_frames: int, frame_timestamps: list[float]):
        if total_frames <= 0:
            raise ValueError(f"total_frames must be > 0, got {total_frames}")
        if len(frame_timestamps) != total_frames:
            raise ValueError(
                f"frame_timestamps length {len(frame_timestamps)} "
                f"does not match total_frames {total_frames}"
            )
        self.video_key = video_key
        self.total_frames = total_frames
        self.frame_timestamps = list(frame_timestamps)

    def process(self, events: list[dict[str, Any]]) -> list[MatchBoundary]:
        """Turn raw boundary events into MatchBoundary segments."""
        segments: list[MatchBoundary] = []
        segment_start = 0
        last_boundary_type = ""

        for ev in events:
            ev_type = ev.get("type")
            frame_idx = int(ev.get("frame_idx", 0))
            if ev_type not in {"transition", "breakdown"}:
                continue
            # Clamp in-range. Garbage events outside [0, total_frames) get dropped.
            if frame_idx < 0 or frame_idx >= self.total_frames:
                continue

            # Collapse transition-after-breakdown: the transition belongs
            # to the match that just ended, don't open a new segment from it.
            if ev_type == "transition" and last_boundary_type == "breakdown":
                last_boundary_type = "transition"
                continue

            # Close the current segment on this boundary.
            if frame_idx < segment_start:
                # Out-of-order event. Skip it — the detector assumes
                # monotonic frame ordering from detect_match_boundaries.
                continue

            segments.append(
                MatchBoundary(
                    start_frame_idx=segment_start,
                    end_frame_idx=frame_idx,
                    start_timestamp_s=self.frame_timestamps[segment_start],
                    end_timestamp_s=self.frame_timestamps[frame_idx],
                    video_key=self.video_key,
                    boundary_type=ev_type,
                )
            )
            # Next segment starts right after this boundary.
            segment_start = min(frame_idx + 1, self.total_frames - 1)
            last_boundary_type = ev_type

        # If there are unused frames after the last boundary, they belong
        # to the final segment (probably a match that's still in progress
        # when the video cut off). Only emit this tail segment if it spans
        # a non-trivial range — skipping the degenerate "one frame" case.
        if segment_start < self.total_frames - 1:
            segments.append(
                MatchBoundary(
                    start_frame_idx=segment_start,
                    end_frame_idx=self.total_frames - 1,
                    start_timestamp_s=self.frame_timestamps[segment_start],
                    end_timestamp_s=self.frame_timestamps[self.total_frames - 1],
                    video_key=self.video_key,
                    boundary_type="final",
                )
            )

        return segments


# ─── High-level entry point ───


def detect_boundaries_from_frames(
    frames: list[dict[str, Any]],
    *,
    ocr: Any,
    video_key: str,
) -> list[MatchBoundary]:
    """Run the OCR boundary pass over a frame list and return MatchBoundary
    segments. `ocr` is an OverlayOCR-compatible object exposing
    `detect_match_boundaries(frames) -> list[dict]`.

    Each frame in `frames` must have `path` and `timestamp_s` keys.
    """
    if not frames:
        return []

    raw_events = ocr.detect_match_boundaries(frames)
    timestamps = [float(f.get("timestamp_s", 0.0)) for f in frames]

    detector = MatchBoundaryDetector(
        video_key=video_key,
        total_frames=len(frames),
        frame_timestamps=timestamps,
    )
    return detector.process(raw_events)


# ─── TBA schedule alignment ───


def _shape_match_key(event_key: str, tba_match: dict[str, Any]) -> Optional[str]:
    """Build a canonical match_key for a TBA match dict, mirroring the
    build_match_key helper in workers.mode_a."""
    comp_level = tba_match.get("comp_level")
    try:
        match_num = int(tba_match.get("match_number", 0))
    except (TypeError, ValueError):
        return None
    if not comp_level or match_num <= 0:
        return None
    if comp_level == "qm":
        return f"{event_key}_qm{match_num}"
    set_num = tba_match.get("set_number")
    try:
        set_num_int = int(set_num)
    except (TypeError, ValueError):
        return None
    return f"{event_key}_{comp_level}{set_num_int}m{match_num}"


@dataclass
class ScheduleAlignmentResult:
    """Summary from validate_against_tba_schedule."""

    aligned: list[MatchBoundary] = field(default_factory=list)
    extra_boundaries: int = 0     # boundaries with no matching schedule slot
    missing_matches: list[str] = field(default_factory=list)  # schedule slots that got no boundary

    def to_dict(self) -> dict[str, Any]:
        return {
            "aligned": [b.to_dict() for b in self.aligned],
            "extra_boundaries": int(self.extra_boundaries),
            "missing_matches": list(self.missing_matches),
        }


def validate_against_tba_schedule(
    boundaries: list[MatchBoundary],
    tba_matches: list[dict[str, Any]],
    *,
    event_key: str,
    comp_levels: tuple[str, ...] = ("qm",),
) -> ScheduleAlignmentResult:
    """Pair detected boundaries 1:1 with an ordered TBA schedule.

    Only `comp_levels` matches are considered (default: qualification
    only). The TBA schedule is sorted by (comp_level, set_number,
    match_number) so the alignment is deterministic regardless of how
    TBA returned them.

    Returns a ScheduleAlignmentResult:
      - `aligned`: boundaries with match_key/comp_level/match_num populated
      - `extra_boundaries`: count of tail boundaries that had no schedule slot
      - `missing_matches`: match_keys from the schedule with no boundary
    """
    # Strict schedule order: comp_level priority then set/num.
    level_order = {"qm": 0, "qf": 1, "sf": 2, "f": 3}

    def sort_key(m: dict[str, Any]) -> tuple[int, int, int]:
        return (
            level_order.get(m.get("comp_level", ""), 99),
            int(m.get("set_number") or 0),
            int(m.get("match_number") or 0),
        )

    scheduled = [
        m for m in sorted(tba_matches, key=sort_key)
        if m.get("comp_level") in comp_levels
    ]

    aligned: list[MatchBoundary] = []
    pair_count = min(len(boundaries), len(scheduled))

    for i in range(pair_count):
        b = boundaries[i]
        m = scheduled[i]
        match_key = _shape_match_key(event_key, m)
        if not match_key:
            continue
        aligned.append(
            MatchBoundary(
                start_frame_idx=b.start_frame_idx,
                end_frame_idx=b.end_frame_idx,
                start_timestamp_s=b.start_timestamp_s,
                end_timestamp_s=b.end_timestamp_s,
                video_key=b.video_key,
                match_key=match_key,
                comp_level=str(m.get("comp_level", "")),
                match_num=int(m.get("match_number", 0)),
                boundary_type=b.boundary_type,
            )
        )

    extra_boundaries = max(0, len(boundaries) - len(scheduled))
    missing = [
        _shape_match_key(event_key, m) or "<unknown>"
        for m in scheduled[pair_count:]
    ]
    return ScheduleAlignmentResult(
        aligned=aligned,
        extra_boundaries=extra_boundaries,
        missing_matches=missing,
    )
