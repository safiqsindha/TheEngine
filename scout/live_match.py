#!/usr/bin/env python3
"""
The Engine — Live Scout Match Record
Team 2950 — The Devastators

Canonical data shape produced by the Live Scout cloud workers and consumed
by pick_board.py. One LiveMatch record per FRC qualification or playoff
match. Records are idempotent: re-processing a match overwrites the prior
record (matches finalize as more frames are processed).

Phase 1 fields cover OCR-derivable data only (scores, team sets, timer).
Phase 2 adds typed vision fields populated by the T2 vision worker:
`vision_events` (raw frame-level YOLO detections), `cycle_counts`
(per-team), `climb_results` (per-team). The legacy `red_breakdown` /
`blue_breakdown` dicts remain for game-specific OCR subscores; the
typed fields are the canonical Phase 2 vision surface.

Schema is locked in design-intelligence/LIVE_SCOUT_PHASE1_BUILD.md §F2
(Phase 1) and the Phase 2 scoping doc §V2.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# TBA match key formats:
#   qualification:  2026txbel_qm32
#   quarterfinal:   2026txbel_qf1m1   (qf<set>m<match>)
#   semifinal:      2026txbel_sf1m1
#   final:          2026txbel_f1m1
MATCH_KEY_RE = re.compile(
    r"^(?P<event>[0-9]{4}[a-z][a-z0-9]+)_"
    r"(?P<level>qm|qf|sf|f)"
    r"(?:(?P<set>\d+)m)?"
    r"(?P<num>\d+)$"
)
EVENT_KEY_RE = re.compile(r"^[0-9]{4}[a-z][a-z0-9]+$")

VALID_COMP_LEVELS = {"qm", "qf", "sf", "f"}
VALID_TIMER_STATES = {"auto", "teleop", "endgame", "post"}
VALID_SOURCE_TIERS = {"live", "vod", "backfill"}
VALID_WINNERS = {"red", "blue", "tie", None}

# Phase 2 — T2 vision event types produced by the YOLO model.
VALID_VISION_EVENT_TYPES = {
    "cycle", "climb_attempt", "climb_success", "climb_failure", "defense",
}
# Phase 2 — climb result categories used in cycle/climb roll-ups.
VALID_CLIMB_RESULTS = {"success", "attempt", "failure", "none"}


@dataclass
class LiveMatch:
    """One processed FRC match. See module docstring for context."""

    event_key: str                          # "2026txbel"
    match_key: str                          # "2026txbel_qm32"
    match_num: int                          # 32
    comp_level: str                         # "qm" | "qf" | "sf" | "f"
    red_teams: list[int]                    # [2950, 1234, 5678]
    blue_teams: list[int]
    red_score: Optional[int]                # None until match ends
    blue_score: Optional[int]
    red_breakdown: dict = field(default_factory=dict)   # OCR game-specific subscores
    blue_breakdown: dict = field(default_factory=dict)
    winning_alliance: Optional[str] = None  # "red" | "blue" | "tie" | None
    timer_state: str = "post"               # "auto" | "teleop" | "endgame" | "post"
    processed_at: int = 0                   # unix epoch (set by from_dict if 0)
    source_video_id: str = ""               # YouTube video ID
    source_tier: str = "vod"                # "live" | "vod" | "backfill"
    confidence: float = 1.0                 # 0..1, OCR cross-frame consensus
    # ─── Phase 2 — T2 vision worker output ───
    vision_events: list[dict] = field(default_factory=list)  # raw YOLO detections
    cycle_counts: dict[str, int] = field(default_factory=dict)  # team_str → count
    climb_results: dict[str, str] = field(default_factory=dict)  # team_str → result

    def __post_init__(self):
        self.validate()
        if self.processed_at == 0:
            self.processed_at = int(time.time())

    # ─── Validation ───

    def validate(self) -> None:
        """Raise ValueError if any field violates the schema."""
        if not EVENT_KEY_RE.match(self.event_key):
            raise ValueError(f"invalid event_key: {self.event_key!r}")

        m = MATCH_KEY_RE.match(self.match_key)
        if not m:
            raise ValueError(f"invalid match_key: {self.match_key!r}")
        if m.group("event") != self.event_key:
            raise ValueError(
                f"match_key event prefix {m.group('event')!r} does not match "
                f"event_key {self.event_key!r}"
            )
        if m.group("level") != self.comp_level:
            raise ValueError(
                f"match_key level {m.group('level')!r} does not match "
                f"comp_level {self.comp_level!r}"
            )
        if int(m.group("num")) != self.match_num:
            raise ValueError(
                f"match_key num {m.group('num')} does not match "
                f"match_num {self.match_num}"
            )

        if self.comp_level not in VALID_COMP_LEVELS:
            raise ValueError(f"invalid comp_level: {self.comp_level!r}")
        if self.timer_state not in VALID_TIMER_STATES:
            raise ValueError(f"invalid timer_state: {self.timer_state!r}")
        if self.source_tier not in VALID_SOURCE_TIERS:
            raise ValueError(f"invalid source_tier: {self.source_tier!r}")
        if self.winning_alliance not in VALID_WINNERS:
            raise ValueError(f"invalid winning_alliance: {self.winning_alliance!r}")

        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence out of range [0,1]: {self.confidence}")

        for label, teams in (("red_teams", self.red_teams),
                             ("blue_teams", self.blue_teams)):
            if not isinstance(teams, list) or not all(
                isinstance(t, int) and 1 <= t <= 99999 for t in teams
            ):
                raise ValueError(f"{label} must be list of int team numbers, got {teams!r}")

        # ─── Phase 2 vision field validation ───
        if not isinstance(self.vision_events, list):
            raise ValueError(f"vision_events must be a list, got {type(self.vision_events).__name__}")
        for ev in self.vision_events:
            if not isinstance(ev, dict):
                raise ValueError(f"vision_events entries must be dict, got {ev!r}")
            evt_type = ev.get("event_type")
            if evt_type is not None and evt_type not in VALID_VISION_EVENT_TYPES:
                raise ValueError(f"invalid vision event_type: {evt_type!r}")

        if not isinstance(self.cycle_counts, dict):
            raise ValueError(f"cycle_counts must be a dict, got {type(self.cycle_counts).__name__}")
        for k, v in self.cycle_counts.items():
            if not isinstance(k, str) or not isinstance(v, int) or v < 0:
                raise ValueError(f"cycle_counts entry must be str→non-negative int, got {k!r}: {v!r}")

        if not isinstance(self.climb_results, dict):
            raise ValueError(f"climb_results must be a dict, got {type(self.climb_results).__name__}")
        for k, v in self.climb_results.items():
            if not isinstance(k, str) or v not in VALID_CLIMB_RESULTS:
                raise ValueError(f"climb_results entry must be str→{VALID_CLIMB_RESULTS}, got {k!r}: {v!r}")

    # ─── Serialization ───

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict representation. Stable key order."""
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LiveMatch":
        """Construct from a dict (e.g., loaded from JSON state).

        Unknown keys are silently dropped so we can evolve the schema
        without breaking older state files.
        """
        known_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def from_json(cls, raw: str) -> "LiveMatch":
        return cls.from_dict(json.loads(raw))

    # ─── Convenience ───

    @property
    def is_complete(self) -> bool:
        """True once both scores have been resolved."""
        return self.red_score is not None and self.blue_score is not None

    @property
    def all_teams(self) -> list[int]:
        return list(self.red_teams) + list(self.blue_teams)

    def winner_from_scores(self) -> Optional[str]:
        """Compute winner from current scores; returns None if not complete."""
        if not self.is_complete:
            return None
        if self.red_score > self.blue_score:
            return "red"
        if self.blue_score > self.red_score:
            return "blue"
        return "tie"
