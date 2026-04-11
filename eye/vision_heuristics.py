#!/usr/bin/env python3
"""
The Engine — Live Scout T2 Vision Heuristics (game-agnostic layer)
Team 2950 — The Devastators

The insight that makes this module possible:

    Almost every "physical" FRC scouting signal can be inferred from
    ONE robot detector plus a set of time + space rules. You don't need
    a custom-trained model per year; you need robots-on-a-field geometry.

    - Climb    = a robot that's on the ground at the start of endgame
                 and quickly leaves the ground and stays off.
    - Defense  = a robot that spends N consecutive frames inside the
                 opposing alliance's scoring zone (not its own).
    - Cycle    = (still game-specific; needs a game-piece detector)

Climb and defense are **game-agnostic** — the rules factor out every
class except "robot" and every field landmark except "scoring zone"
and "floor Y". That's the whole point of this module: it lets us ship
a vision pipeline for a new game's Week 0 broadcast with nothing more
than (a) a robot detector and (b) a 30-second zone-map redraw.

USAGE
─────
The vision worker calls this module AFTER `VisionYolo.infer_frames`
has produced a stream of raw detections. Convert the raw detections
into `FrameState` records (one per frame, carrying the bboxes + a
timestamp), then call:

    ground_y = GroundPlaneEstimator.from_frames(frames).estimate()
    climb_events = detect_climb_events(
        frames,
        ground_plane_y=ground_y,
        endgame_start_unix=match.start_unix + 135,  # 2:15 into a 2:30 match
    )
    defense_events = detect_defense_events(
        frames,
        zone_map=zone_map_for_event("2026txbel"),
    )

Both functions return plain `VisionEvent` lists (same type the rest of
the pipeline uses), so the worker just concatenates them with whatever
came out of `VisionYolo.infer_frames` before calling
`aggregate_cycle_counts` / `aggregate_climb_results`.

None of this raises on messy input — the heuristics are designed for
noisy detections (occasional missed frames, bbox jitter, one-frame
false positives). Minimum frame counts and persistence windows are
tunable per call.

DECOUPLING FROM GAME YEAR
─────────────────────────
The module deliberately does NOT import anything game-specific — no
`VALID_CLIMB_RESULTS` mapping to 2026 game pieces, no hardcoded chain
heights, no cage coordinates. Instead:

  - The `ground_plane_y` parameter is a pixel Y value you estimate
    once per camera feed. Cameras don't move during a match.
  - The `zone_map` parameter is a `ZoneMap` describing two alliance
    scoring polygons in image space. You draw this by hand once per
    broadcast camera angle, not once per game year.
  - The `endgame_start_unix` parameter is a timestamp, not a match
    phase enum. Use whatever phase boundary makes sense for this
    year's match length.

If the 2027 game drops and the FRC field is completely reshaped, this
module doesn't need a single code change — you re-draw the zones and
re-estimate the ground plane on a new VOD, and it keeps working.

Schema reference: `eye/vision_yolo.py::VisionEvent`,
`design-intelligence/V0a_MODEL_SELECTION.md` §Path A (the heuristic
layer sketch), `design-intelligence/VISION_2027_TRAINING_PLAN.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from vision_yolo import VisionEvent


# ─── Input types ───


@dataclass
class RobotDetection:
    """One robot bbox inside a single frame.

    Minimal info — just enough to estimate "what team" (if known),
    "where on screen" (bbox), and "how confident" (from the detector).

    `team_num` is optional because most robot detectors can't attribute
    a specific team without bumper-number OCR or cross-tracking; the
    heuristics below fall back to *alliance color* if `team_num` is
    None and `alliance` is set.
    """

    bbox: tuple[float, float, float, float]           # x1, y1, x2, y2
    confidence: float
    team_num: Optional[int] = None                    # None if not attributed
    alliance: Optional[str] = None                    # "red" | "blue" | None
    track_id: Optional[int] = None                    # persistent id across frames if available

    @property
    def bbox_bottom_y(self) -> float:
        """Y coordinate of the bottom edge of the bbox — the robot's
        approximate floor contact point in image space."""
        return float(self.bbox[3])

    @property
    def bbox_center_x(self) -> float:
        return 0.5 * (float(self.bbox[0]) + float(self.bbox[2]))

    @property
    def bbox_center_y(self) -> float:
        return 0.5 * (float(self.bbox[1]) + float(self.bbox[3]))


@dataclass
class FrameState:
    """One frame's worth of detector output, timestamped.

    The worker is responsible for filling in `unix_ts` (usually from
    the frame's cache filename or the HLS playlist PDT). Heuristics
    below gate behavior on wall-clock time, not `frame_idx`, so that
    irregular frame intervals don't break the rules.
    """

    frame_idx: int
    unix_ts: float
    robots: list[RobotDetection] = field(default_factory=list)


@dataclass
class ZoneMap:
    """Image-space polygons for the two alliance scoring zones.

    Polygons are lists of `(x, y)` vertices in the same coordinate
    system as the bboxes in `RobotDetection.bbox`. One polygon per
    alliance. Draw them by hand once per broadcast camera angle — FRC
    broadcast cameras are locked down during a match, so a single
    ZoneMap works for every match of the event.

    A robot is "inside" a zone if its bbox center is inside the polygon
    (point-in-polygon, even-odd rule). Simple and fast; good enough for
    the 5-frame persistence threshold used downstream.
    """

    red_scoring_zone: list[tuple[float, float]]
    blue_scoring_zone: list[tuple[float, float]]

    def zone_for_alliance(self, alliance: str) -> list[tuple[float, float]]:
        alliance = (alliance or "").lower()
        if alliance == "red":
            return self.red_scoring_zone
        if alliance == "blue":
            return self.blue_scoring_zone
        return []

    def opposing_zone(self, alliance: str) -> list[tuple[float, float]]:
        alliance = (alliance or "").lower()
        if alliance == "red":
            return self.blue_scoring_zone
        if alliance == "blue":
            return self.red_scoring_zone
        return []


# ─── Ground plane estimator ───


@dataclass
class GroundPlaneEstimator:
    """Estimate the floor Y (in pixels) from a stream of robot bboxes.

    The assumption: most frames contain at least one robot standing on
    the field floor. The bottom-Y of those bboxes clusters near the
    floor; we take a high percentile (default 90th) as the floor Y.

    Why percentile and not max: a robot climbing or on top of another
    robot would push the max down (image coordinates have Y growing
    downward), and we want to ignore those outliers. Percentile is
    stable against a few frames of weirdness.

    Why not the mean: the mean drifts upward as more robots climb or
    as foreshortening makes far-side robots look higher in the frame.

    Usage:
        gpe = GroundPlaneEstimator.from_frames(frames)
        floor_y = gpe.estimate(percentile=0.90)
    """

    bottom_ys: list[float] = field(default_factory=list)

    @classmethod
    def from_frames(cls, frames: Iterable[FrameState]) -> "GroundPlaneEstimator":
        est = cls()
        for f in frames:
            for r in f.robots:
                est.bottom_ys.append(r.bbox_bottom_y)
        return est

    def estimate(self, *, percentile: float = 0.90) -> Optional[float]:
        """Return the percentile-th bottom-Y, or None if no samples.

        `percentile` is a value in [0, 1]. Default 0.90 is aggressive
        enough to ignore a handful of climbing robots but low enough
        that one robot already on the cage at match end doesn't pull
        the floor line up.
        """
        if not self.bottom_ys:
            return None
        if not (0.0 <= percentile <= 1.0):
            raise ValueError(f"percentile must be in [0, 1], got {percentile}")
        # Image Y grows downward, so a larger bbox-bottom-Y means the
        # robot is lower on screen (closer to the field floor). Sort
        # ascending and take the percentile-th value: "90% of bbox-
        # bottoms are at or below this Y".
        sorted_ys = sorted(self.bottom_ys)
        idx = int(round(percentile * (len(sorted_ys) - 1)))
        return float(sorted_ys[idx])


# ─── Climb detection ───


@dataclass
class _RobotClimbTrack:
    """Internal per-robot tracker used by `detect_climb_events`."""

    key: str                                 # track_id or team_num or alliance+slot
    team_num: Optional[int]
    frames_grounded_pre_endgame: int = 0
    frames_above_floor_in_endgame: int = 0
    frames_on_floor_in_endgame: int = 0
    saw_above_floor_in_endgame: bool = False
    peak_above_floor_delta: float = 0.0       # max pixels above floor
    last_frame_idx: int = -1
    confidence_sum: float = 0.0
    confidence_n: int = 0

    def mean_conf(self) -> float:
        return self.confidence_sum / max(self.confidence_n, 1)


def _robot_key(r: RobotDetection, fallback: str) -> str:
    if r.track_id is not None:
        return f"track:{r.track_id}"
    if r.team_num is not None:
        return f"team:{r.team_num}"
    return fallback


def detect_climb_events(
    frames: list[FrameState],
    *,
    ground_plane_y: float,
    endgame_start_unix: float,
    match_end_unix: Optional[float] = None,
    threshold_px: float = 80.0,
    persist_frames: int = 3,
) -> list[VisionEvent]:
    """Game-agnostic climb detection.

    Rule:
      - Before `endgame_start_unix`: robots are on the floor. Track
        which robots exist.
      - At/after `endgame_start_unix`: a robot whose bbox bottom-Y
        rises at least `threshold_px` above `ground_plane_y` (i.e.
        is that many pixels HIGHER on screen than the floor line) for
        at least `persist_frames` consecutive frames has "left the
        ground".
      - At match end (last frame seen with unix_ts ≤ match_end_unix if
        given, else just the last frame in `frames`):
          * Robot is currently above the floor → climb_success
          * Robot was above the floor but came back down → climb_attempt
          * Robot never left the floor → (no event emitted)

    Note on image coordinates: Y grows downward in image space, so
    "above the floor" means `bbox_bottom_y < ground_plane_y - threshold_px`.

    Never raises; returns an empty list if input is empty or if no
    robot ever left the ground.

    `frame_idx` on emitted events is the frame where the CLASSIFICATION
    was made (typically the last frame). `team_num` is populated only
    if the detector attributed a team number.
    """
    if not frames:
        return []
    if persist_frames < 1:
        persist_frames = 1

    # One tracker per robot key. Robot identity is best-effort:
    # track_id > team_num > per-frame slot (which is lossy but never
    # collides across frames since we stabilize on the earlier key
    # for the same track_id/team_num).
    tracks: dict[str, _RobotClimbTrack] = {}

    for f in frames:
        in_endgame = f.unix_ts >= endgame_start_unix
        if match_end_unix is not None and f.unix_ts > match_end_unix:
            continue

        seen_this_frame: set[str] = set()
        for slot, robot in enumerate(f.robots):
            key = _robot_key(robot, fallback=f"frame:{f.frame_idx}:slot:{slot}")
            if key in seen_this_frame:
                continue
            seen_this_frame.add(key)
            tr = tracks.get(key)
            if tr is None:
                tr = _RobotClimbTrack(key=key, team_num=robot.team_num)
                tracks[key] = tr

            # "Above floor" = bbox bottom is at least threshold_px
            # HIGHER on screen (smaller Y) than the floor line.
            delta = ground_plane_y - robot.bbox_bottom_y
            above = delta >= threshold_px

            if not in_endgame:
                if not above:
                    tr.frames_grounded_pre_endgame += 1
            else:
                if above:
                    tr.frames_above_floor_in_endgame += 1
                    tr.saw_above_floor_in_endgame = True
                    if delta > tr.peak_above_floor_delta:
                        tr.peak_above_floor_delta = delta
                else:
                    tr.frames_on_floor_in_endgame += 1

            tr.last_frame_idx = f.frame_idx
            tr.confidence_sum += float(robot.confidence)
            tr.confidence_n += 1

    # Determine the last frame index we processed, for emitted events.
    last_frame_idx = max((f.frame_idx for f in frames), default=0)
    last_frame_robots_by_key: dict[str, RobotDetection] = {}
    # Walk frames in reverse to find, for each key, whether the
    # LAST observation was above-floor (success) or on-floor (attempt).
    for f in reversed(frames):
        if match_end_unix is not None and f.unix_ts > match_end_unix:
            continue
        for slot, robot in enumerate(f.robots):
            key = _robot_key(robot, fallback=f"frame:{f.frame_idx}:slot:{slot}")
            if key not in last_frame_robots_by_key:
                last_frame_robots_by_key[key] = robot
        if len(last_frame_robots_by_key) >= len(tracks):
            break

    out: list[VisionEvent] = []
    for key, tr in tracks.items():
        # Need the persist_frames threshold to count as "really climbed".
        if tr.frames_above_floor_in_endgame < persist_frames:
            continue

        final_robot = last_frame_robots_by_key.get(key)
        if final_robot is None:
            # Lost track of this robot before match end — conservative:
            # attempt rather than success.
            category = "climb_attempt"
            final_bbox = (0.0, 0.0, 0.0, 0.0)
        else:
            delta = ground_plane_y - final_robot.bbox_bottom_y
            if delta >= threshold_px:
                category = "climb_success"
            else:
                category = "climb_attempt"
            final_bbox = final_robot.bbox

        out.append(
            VisionEvent(
                frame_idx=last_frame_idx,
                event_type=category,
                team_num=tr.team_num,
                confidence=min(1.0, max(0.0, tr.mean_conf())),
                bbox=final_bbox,
            )
        )
    return out


# ─── Defense detection ───


def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Standard even-odd ray-casting point-in-polygon test.

    Returns False for empty / degenerate polygons. Vertices are
    inclusive on the lower-left, exclusive on the upper-right (the
    ambiguity only matters at pixel boundaries, which are noisy
    anyway).
    """
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        # Edge crosses the horizontal ray from (x, y) to +infinity.
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def detect_defense_events(
    frames: list[FrameState],
    *,
    zone_map: ZoneMap,
    persist_frames: int = 5,
    require_alliance: bool = True,
) -> list[VisionEvent]:
    """Game-agnostic defense detection.

    Rule: a robot is "playing defense" if its bbox center sits inside
    the OPPOSING alliance's scoring zone for at least `persist_frames`
    consecutive frames. We emit one `defense` VisionEvent per robot
    per "defense session" (a run of consecutive frames meeting the
    criteria); if a robot is in the opposing zone for the whole match
    that's still one event, not one per frame.

    If `require_alliance=True` (default), robots without an `alliance`
    field are skipped entirely — we can't decide "opposing" without
    knowing which side they're on. Flip to False for single-alliance
    drills or when the caller has already filtered to one alliance.

    The same robot can produce multiple defense events if it enters,
    leaves, and re-enters the opposing zone.
    """
    if not frames:
        return []
    if persist_frames < 1:
        persist_frames = 1

    # Per-robot run tracker: (consecutive_frames, starting_frame_idx,
    # peak_confidence, last_bbox, team_num, emitted_for_this_run).
    @dataclass
    class _Run:
        count: int = 0
        start_frame_idx: int = -1
        peak_conf: float = 0.0
        last_bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        team_num: Optional[int] = None
        emitted_for_this_run: bool = False

    runs: dict[str, _Run] = {}
    out: list[VisionEvent] = []

    for f in frames:
        seen_this_frame: set[str] = set()
        for slot, robot in enumerate(f.robots):
            if require_alliance and not robot.alliance:
                continue
            key = _robot_key(robot, fallback=f"frame:{f.frame_idx}:slot:{slot}")
            if key in seen_this_frame:
                continue
            seen_this_frame.add(key)

            opposing = zone_map.opposing_zone(robot.alliance or "")
            in_opposing = _point_in_polygon(
                robot.bbox_center_x,
                robot.bbox_center_y,
                opposing,
            )
            run = runs.get(key)
            if run is None:
                run = _Run(team_num=robot.team_num)
                runs[key] = run

            if in_opposing:
                if run.count == 0:
                    run.start_frame_idx = f.frame_idx
                    run.emitted_for_this_run = False
                run.count += 1
                if robot.confidence > run.peak_conf:
                    run.peak_conf = float(robot.confidence)
                run.last_bbox = robot.bbox
                if run.count >= persist_frames and not run.emitted_for_this_run:
                    out.append(
                        VisionEvent(
                            frame_idx=f.frame_idx,
                            event_type="defense",
                            team_num=run.team_num,
                            confidence=min(1.0, max(0.0, run.peak_conf)),
                            bbox=run.last_bbox,
                        )
                    )
                    run.emitted_for_this_run = True
            else:
                # Left the opposing zone — reset the run counter so a
                # future re-entry starts a new session.
                run.count = 0
                run.peak_conf = 0.0
                run.emitted_for_this_run = False

        # Robots not seen this frame keep their existing run state.
        # Their run resets naturally the next time they show up out-
        # of-zone; a momentary occlusion doesn't invalidate the run.

    return out
