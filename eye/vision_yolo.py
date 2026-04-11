#!/usr/bin/env python3
"""
The Engine — Live Scout T2 Vision Wrapper (V1)
Team 2950 — The Devastators

Thin wrapper around a Roboflow Universe FRC YOLO model. Runs per-frame
inference and emits typed `VisionEvent` records that downstream workers
aggregate into per-team cycle counts, climb outcomes, and defense tags
on a `LiveMatch` record.

Lazy SDK import pattern: the module imports cleanly without
`roboflow`, `ultralytics`, or any other vision SDK installed. The real
model loader is gated behind a `NotImplementedError` until V0a (human
picks a Roboflow model) is resolved. Until then, tests and the Phase 2
cron job both run against `FakeYOLOModel`, a scripted stub that returns
deterministic `VisionEvent` lists keyed on frame filename.

V0 prerequisites (BLOCKED on human):
  - V0a: pick a Roboflow Universe FRC YOLO model (weights URL, class
         map, confidence threshold). Wire it into `_load_real_model`.
  - V0b: pick an Azure GPU SKU. Until then the Bicep template leaves
         `visionGpuSku` empty and the vision worker runs CPU-only.
  - V0c: confirm cached frame filename format. Mode A/B both use
         `frame_%04d.jpg` — we consume that shape directly.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md Phase 2 §T2, and
`scout/live_match.py` §Phase 2 vision field validation.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ─── Path bootstrap so we can pull schema constants from scout/ ───
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scout"))

from live_match import (  # noqa: E402
    VALID_CLIMB_RESULTS,
    VALID_VISION_EVENT_TYPES,
)


# ─── Typed event record ───


@dataclass
class VisionEvent:
    """One per-frame YOLO detection, ready to fold into a LiveMatch.

    Fields mirror what the T2 aggregator needs — they're NOT the same
    shape as the upstream Roboflow / ultralytics result objects; the
    real model loader translates those into `VisionEvent` instances.
    """

    frame_idx: int
    event_type: str                        # one of VALID_VISION_EVENT_TYPES
    team_num: Optional[int]                # None if not assignable to a team
    confidence: float
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels

    def __post_init__(self) -> None:
        if self.event_type not in VALID_VISION_EVENT_TYPES:
            raise ValueError(
                f"invalid event_type {self.event_type!r}; "
                f"must be one of {sorted(VALID_VISION_EVENT_TYPES)}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence out of range [0,1]: {self.confidence}")
        if self.team_num is not None and not (1 <= self.team_num <= 99999):
            raise ValueError(f"team_num out of range: {self.team_num}")
        if len(self.bbox) != 4:
            raise ValueError(f"bbox must be 4-tuple, got {self.bbox!r}")

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict, stable key order. Shape matches the
        LiveMatch.vision_events schema gate in scout/live_match.py."""
        return {
            "frame_idx": int(self.frame_idx),
            "event_type": self.event_type,
            "team_num": int(self.team_num) if self.team_num is not None else None,
            "confidence": float(self.confidence),
            "bbox": [float(v) for v in self.bbox],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisionEvent":
        bbox = data.get("bbox") or (0.0, 0.0, 0.0, 0.0)
        return cls(
            frame_idx=int(data["frame_idx"]),
            event_type=str(data["event_type"]),
            team_num=(int(data["team_num"]) if data.get("team_num") is not None else None),
            confidence=float(data["confidence"]),
            bbox=tuple(float(v) for v in bbox),  # type: ignore[arg-type]
        )


# ─── FakeYOLOModel — scripted stub ───


class FakeYOLOModel:
    """Drop-in replacement for the real Roboflow model.

    Used in two places:
      1. Production cron until V0a picks the real Roboflow model. The
         Container App Job imports this under `MODEL_NAME=fake` so the
         vision worker is wired end-to-end even with no real model.
      2. Tests — hermetic, deterministic, no external I/O.

    Pass a `scripted_events` dict of `{frame_filename: [VisionEvent, ...]}`.
    `infer(frame_path)` returns the list for `frame_path.name` or an empty
    list if the frame isn't scripted. The stub is stateless; calling
    `infer` twice on the same frame returns the same events.
    """

    def __init__(
        self,
        scripted_events: Optional[dict[str, list[VisionEvent]]] = None,
    ) -> None:
        self._scripted: dict[str, list[VisionEvent]] = dict(scripted_events or {})
        self.infer_calls: int = 0  # diagnostic counter for tests

    def infer(self, frame_path: Path) -> list[VisionEvent]:
        """Return the scripted events for this frame (by filename), or
        an empty list. Does no real inference."""
        self.infer_calls += 1
        return list(self._scripted.get(Path(frame_path).name, []))


# ─── Real model loader — BLOCKED on V0a ───


def _load_real_model(model_name: str) -> Any:
    """Placeholder for the real Roboflow / ultralytics loader.

    V0a hook: replace this function body with the actual weights fetch
    and return a wrapper that exposes `.infer(frame_path) -> list[VisionEvent]`.

    Until V0a is resolved, every call raises NotImplementedError so any
    accidental prod wiring surfaces loudly instead of silently falling
    back to fake inference.
    """
    raise NotImplementedError(
        f"V0a — Roboflow model not selected yet (requested model_name={model_name!r}). "
        "Pick a Roboflow Universe FRC YOLO model, wire the weights fetch + "
        "inference translator into eye/vision_yolo._load_real_model, then "
        "flip the MODEL_NAME env var in the vision-worker job from 'fake' "
        "to the real model id."
    )


# ─── VisionYolo — public wrapper ───


class VisionYolo:
    """Wrapper around whichever YOLO-ish model is loaded.

    Construct with either an injected `model` (tests) or a `model_name`
    string (prod). `model_name="fake"` builds a `FakeYOLOModel` with no
    scripted events (returns empty lists for every frame — safe no-op).
    Any other `model_name` routes to `_load_real_model`, which currently
    raises NotImplementedError pending V0a.
    """

    def __init__(
        self,
        model: Optional[Any] = None,
        *,
        model_name: str = "fake",
    ) -> None:
        if model is not None:
            self._model = model
            self.model_name = model_name or type(model).__name__
            return

        if model_name == "fake":
            self._model = FakeYOLOModel()
            self.model_name = "fake"
            return

        # Every non-fake path goes through the real loader, which is a
        # NotImplementedError stub until V0a is resolved.
        self._model = _load_real_model(model_name)
        self.model_name = model_name

    @property
    def model(self) -> Any:
        return self._model

    def infer_frames(self, frames: list[Path]) -> list[VisionEvent]:
        """Run inference across a list of frames, concatenating results.

        Order is preserved — the aggregator trusts frame ordering when
        it decides which climb outcome wins (later frames override
        earlier ones for the same team, for example).
        """
        out: list[VisionEvent] = []
        for f in frames:
            events = self._model.infer(Path(f))
            if not events:
                continue
            out.extend(events)
        return out


# ─── Aggregation helpers ───


def aggregate_cycle_counts(events: list[VisionEvent]) -> dict[str, int]:
    """Roll up per-team cycle counts.

    Only events with `event_type == "cycle"` and a non-None `team_num`
    contribute. Returns a dict shaped for `LiveMatch.cycle_counts`
    (keys are string team numbers, values are non-negative ints).
    """
    out: dict[str, int] = {}
    for ev in events:
        if ev.event_type != "cycle":
            continue
        if ev.team_num is None:
            continue
        key = str(ev.team_num)
        out[key] = out.get(key, 0) + 1
    return out


# Precedence used by aggregate_climb_results — higher beats lower.
_CLIMB_PRECEDENCE: dict[str, int] = {
    "none": 0,
    "failure": 1,
    "attempt": 2,
    "success": 3,
}

# Event type → climb category. Anything else is ignored by the climb
# roll-up.
_CLIMB_EVENT_TO_RESULT: dict[str, str] = {
    "climb_success": "success",
    "climb_attempt": "attempt",
    "climb_failure": "failure",
}


def aggregate_climb_results(events: list[VisionEvent]) -> dict[str, str]:
    """Per-team climb result using a fixed precedence.

    For each team with at least one climb event:
      success > attempt > failure > none
    Teams with no climb event at all are omitted (the worker leaves
    them unset in `LiveMatch.climb_results`, which downstream consumers
    treat as "unknown", not "no climb attempted").

    Only categories in VALID_CLIMB_RESULTS are ever written, so the
    output passes `LiveMatch.validate()` as-is.
    """
    best: dict[str, str] = {}
    for ev in events:
        category = _CLIMB_EVENT_TO_RESULT.get(ev.event_type)
        if category is None:
            continue
        if ev.team_num is None:
            continue
        key = str(ev.team_num)
        prior = best.get(key)
        if prior is None or _CLIMB_PRECEDENCE[category] > _CLIMB_PRECEDENCE[prior]:
            best[key] = category

    # Sanity: every value we wrote must be a valid climb result. (Belt
    # and suspenders — the event-type map is the real gate.)
    for k, v in best.items():
        if v not in VALID_CLIMB_RESULTS:
            raise ValueError(f"aggregated climb result for {k!r} not valid: {v!r}")
    return best
