#!/usr/bin/env python3
"""
The Engine — Auto-Path Compatibility Scorer
Team 2950 — The Devastators

For alliance selection, two robots with auto paths that overlap in pickup zones
or timing can conflict during autonomous. This module scores whether a pair of
auto paths can co-execute safely based on path geometry and timing stagger.

Scoring rules (applied in order, penalties accumulate from 1.0, floor at 0.0):
  - Same start position       → -1.0  (hard conflict, irreversible)
  - Shared pickup zone        → -0.5  unless timing stagger > 2 sec
  - Both target same scoring zone at overlapping times → -0.3

Public API:
  compatibility_score(path_a, path_b) → float [0.0, 1.0]
  alliance_auto_compatibility(paths) → float — pairwise mean for 3 robots

AUTO_PATH_LIBRARY: keyed by (year, path_id) — 2024 Crescendo canonical paths.

NOTE: AUTO_PATH_LIBRARY is intentionally sparse. No authoritative published
path geometry data (pickup zones, exact durations, start positions) for named
canonical 2024 Crescendo paths was found in public datasets at the time of
writing. The library is left empty with path_id stubs as a TODO.
Community sources (Pathplanner community paths, 6328 Mechanical Advantage
auto notes, WPILib examples) do not publish machine-readable zone assignments.
Populate from your own scouting data or team-published path configs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Optional

# Timing stagger threshold (seconds): if two paths' start times differ by more
# than this, a shared pickup zone is considered safe.
STAGGER_THRESHOLD_SEC: float = 2.0

# Penalty constants
_PENALTY_SAME_START: float = 1.0       # Hard conflict — same starting position
_PENALTY_SHARED_PICKUP: float = 0.5    # Shared pickup zone (no stagger)
_PENALTY_SHARED_SCORING: float = 0.3   # Both target same scoring zone, overlapping

# Default score when a path is missing/unknown (conservative neutral).
_DEFAULT_UNKNOWN: float = 0.8


@dataclass
class AutoPath:
    """Descriptor for one robot's autonomous routine."""

    team_number: int
    path_id: str
    pickup_zones: list[str]
    scoring_zone: str
    duration_sec: float
    preferred_start_position: str
    # Optional: absolute start time offset in seconds for alliance timing (default 0.0).
    start_offset_sec: float = 0.0


def _paths_overlap_in_time(path_a: AutoPath, path_b: AutoPath) -> bool:
    """Return True if the two paths are active at any overlapping time window."""
    a_start = path_a.start_offset_sec
    a_end = a_start + path_a.duration_sec
    b_start = path_b.start_offset_sec
    b_end = b_start + path_b.duration_sec
    return a_start < b_end and b_start < a_end


def _timing_stagger(path_a: AutoPath, path_b: AutoPath) -> float:
    """Return absolute difference in start offsets (seconds)."""
    return abs(path_a.start_offset_sec - path_b.start_offset_sec)


def compatibility_score(path_a: AutoPath, path_b: AutoPath) -> float:
    """
    Score compatibility of two auto paths for co-execution on the same alliance.

    Returns
    -------
    float in [0.0, 1.0]:
        1.0 = fully compatible, no detected conflicts
        0.0 = hard conflict (e.g., same start position)

    Penalties applied (accumulated, clamped to [0, 1]):
        Same start position:               -1.0 (hard conflict)
        Shared pickup zone (no stagger):   -0.5 per shared zone
        Same scoring zone, overlapping:    -0.3
    """
    penalty: float = 0.0

    # Hard conflict: same start position means robots cannot both execute.
    if path_a.preferred_start_position == path_b.preferred_start_position:
        penalty += _PENALTY_SAME_START

    # Shared pickup zones: only penalize when timing stagger is insufficient.
    if path_a.pickup_zones and path_b.pickup_zones:
        stagger = _timing_stagger(path_a, path_b)
        if stagger <= STAGGER_THRESHOLD_SEC:
            shared_zones = set(path_a.pickup_zones) & set(path_b.pickup_zones)
            penalty += _PENALTY_SHARED_PICKUP * len(shared_zones)

    # Shared scoring zone at overlapping times.
    if (
        path_a.scoring_zone == path_b.scoring_zone
        and _paths_overlap_in_time(path_a, path_b)
    ):
        penalty += _PENALTY_SHARED_SCORING

    return max(0.0, min(1.0, 1.0 - penalty))


def alliance_auto_compatibility(
    paths: list[Optional[AutoPath]],
) -> float:
    """
    Compute mean pairwise compatibility score for an alliance of up to 3 robots.

    Parameters
    ----------
    paths : list of AutoPath or None
        Up to 3 entries. None entries represent robots with unknown auto paths.

    Returns
    -------
    float in [0.0, 1.0] — pairwise mean.
        Unknown paths contribute _DEFAULT_UNKNOWN (0.8) per pairing.
        Empty list returns 1.0 (no conflicts possible).
    """
    if not paths:
        return 1.0

    scores: list[float] = []

    # Enumerate all pairs (including pairs with None entries).
    indices = range(len(paths))
    for i, j in combinations(indices, 2):
        a = paths[i]
        b = paths[j]
        if a is None or b is None:
            scores.append(_DEFAULT_UNKNOWN)
        else:
            scores.append(compatibility_score(a, b))

    if not scores:
        return 1.0

    return sum(scores) / len(scores)


# ─── AUTO_PATH_LIBRARY ────────────────────────────────────────────────────────
# Keyed by (year, path_id).
#
# TODO: Populate with real path data from team scouting or published sources.
# No authoritative machine-readable zone assignments for canonical 2024
# Crescendo named paths were found in public datasets. The path_id strings
# below reflect naming conventions seen in Pathplanner community repos and
# event-scouting writeups, but zone/timing fields are NOT fabricated.
#
# Recommended sources to fill this:
#   - Your team's Pathplanner JSON exports (extract waypoint zones manually)
#   - 6328 Mechanical Advantage's 2024 auto strategy documents
#   - Chief Delphi "2024 autonomous paths" threads
#   - Blue Alliance match videos + timing analysis
#
AUTO_PATH_LIBRARY: dict[tuple[int, str], AutoPath] = {}

# ─── Placeholder stubs (all fields left at zero/empty until real data added) ──
# Uncomment and fill in once zone data is confirmed from published sources.
#
# _2024_PATHS = [
#     # path_id, pickup_zones, scoring_zone, duration_sec, start_position
#     ("source-2piece",   [...], "...", 0.0, "..."),
#     ("amp-2piece",      [...], "...", 0.0, "..."),
#     ("center-4piece",   [...], "...", 0.0, "..."),
#     ("center-5piece",   [...], "...", 0.0, "..."),
#     ("amp-3piece",      [...], "...", 0.0, "..."),
#     ("source-3piece",   [...], "...", 0.0, "..."),
#     ("amp-1piece-rush", [...], "...", 0.0, "..."),
#     ("source-mobility", [],    "...", 0.0, "..."),
# ]
# for _pid, _zones, _sz, _dur, _sp in _2024_PATHS:
#     AUTO_PATH_LIBRARY[(2024, _pid)] = AutoPath(
#         team_number=0, path_id=_pid, pickup_zones=_zones,
#         scoring_zone=_sz, duration_sec=_dur, preferred_start_position=_sp,
#     )
