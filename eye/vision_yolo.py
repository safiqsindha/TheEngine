#!/usr/bin/env python3
"""
The Engine — Live Scout T2 Vision Wrapper (V1 → V2 pluggable registry)
Team 2950 — The Devastators

Thin wrapper around whatever YOLO-ish model is in vogue this week. Runs
per-frame inference and emits typed `VisionEvent` records that downstream
workers aggregate into per-team cycle counts, climb outcomes, and defense
tags on a `LiveMatch` record.

PLUGGABLE REGISTRY (new as of V0a resolution, 2026-04-11)
──────────────────────────────────────────────────────────
Vision models in the FRC ecosystem are dropping weekly — YOLO26,
YOLOv11, RF-DETR, MLX-exported Gemma/SAM variants, custom ONNX exports
from the 2027 auto-label data engine, ... — and committing to one
hard-coded loader means every new model needs a core code edit. Instead,
this module exposes a tiny registry so a new model is a one-line
`register_model(...)` or `register_model_prefix(...)` call made at
import time from `eye/vision_models/`.

  - `VisionModel` (Protocol): anything with `infer(frame_path) -> list[VisionEvent]`
  - `MODEL_REGISTRY`: dict mapping exact `model_name` strings to factories
  - `MODEL_PREFIX_REGISTRY`: list of (prefix, factory) handlers for
    `"ultralytics:yolov8n.pt"` / `"roboflow:workspace/project/1"` /
    `"onnx:/path/to/weights.onnx"` / `"mlx:mlx-community/..."` patterns
  - `register_model(name, factory)`: drop-in a new exact-match handler
  - `register_model_prefix(prefix, factory)`: drop-in a new prefix handler
  - `load_vision_model(model_name)`: consults exact registry → prefix
    registry → raises `VisionModelNotFoundError` if neither matches

This is the same pattern we use in `scout/state_backend.py::get_*_backend`
and `antenna/`: the core code never has to know what exists, modules
wire themselves in at import time.

Lazy SDK import pattern: the module itself still imports cleanly with
no vision SDKs installed. Each registered factory is free to lazy-import
its own SDK so only the handler actually being used pays the import cost.

The `"fake"` handler is always registered and is the default when no
`model_name` is supplied — safe no-op for tests and for prod when Safiq
hasn't wired in a real model yet.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md Phase 2 §T2, and
`scout/live_match.py` §Phase 2 vision field validation.
Decision reference: `design-intelligence/V0a_MODEL_SELECTION.md`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, runtime_checkable

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


# ─── VisionModel protocol ───


@runtime_checkable
class VisionModel(Protocol):
    """Structural type every registered model must satisfy.

    One method: `infer(frame_path: Path) -> list[VisionEvent]`. That's
    the only contract. Models are free to cache, batch, warm up, or
    short-circuit however they want — the wrapper doesn't care.
    """

    def infer(self, frame_path: Path) -> list[VisionEvent]:  # pragma: no cover
        ...


class VisionModelNotFoundError(KeyError):
    """Raised when `load_vision_model(model_name)` finds no handler.

    Uses KeyError so callers that already catch `KeyError` from dict
    lookups keep working, but the class name makes the failure mode
    obvious in tracebacks.
    """


# ─── Registry ───


# `MODEL_REGISTRY`: exact-match handlers. `model_name == key` wins.
# Factories take the model_name string and return a VisionModel.
MODEL_REGISTRY: dict[str, Callable[[str], VisionModel]] = {}

# `MODEL_PREFIX_REGISTRY`: ordered list of (prefix, factory) handlers.
# First prefix that `model_name.startswith()` matches wins. Ordering is
# insertion order; later registrations win only if earlier prefixes
# didn't match. Keep prefixes disjoint to avoid surprises.
MODEL_PREFIX_REGISTRY: list[tuple[str, Callable[[str], VisionModel]]] = []


def register_model(
    name: str,
    factory: Callable[[str], VisionModel],
) -> None:
    """Register an exact-match model handler.

    Idempotent — re-registering the same name silently replaces the
    previous factory. That's deliberate: it lets tests swap in fakes
    without hitting "already registered" errors.

    Example:
        register_model("fake", lambda _: FakeYOLOModel())
        register_model("frc2026-compound", _build_frc2026_compound)
    """
    MODEL_REGISTRY[name] = factory


def register_model_prefix(
    prefix: str,
    factory: Callable[[str], VisionModel],
) -> None:
    """Register a prefix-match model handler.

    Prefix match is `model_name.startswith(prefix)`. Use this for SDK
    families where the suffix is the actual model identifier:

        register_model_prefix("ultralytics:", _load_ultralytics)
        # Then "ultralytics:yolov8n.pt" routes to _load_ultralytics.

        register_model_prefix("roboflow:", _load_roboflow)
        # Then "roboflow:2026-wiredcat-fuel-detection/..." routes there.

    Later registrations of the same prefix REPLACE the older one
    (same idempotent semantics as `register_model`).
    """
    for i, (existing, _) in enumerate(MODEL_PREFIX_REGISTRY):
        if existing == prefix:
            MODEL_PREFIX_REGISTRY[i] = (prefix, factory)
            return
    MODEL_PREFIX_REGISTRY.append((prefix, factory))


def load_vision_model(model_name: str) -> VisionModel:
    """Resolve a model_name to a VisionModel via the registry.

    Resolution order:
      1. Exact match in MODEL_REGISTRY
      2. First matching prefix in MODEL_PREFIX_REGISTRY (insertion order)
      3. VisionModelNotFoundError

    This is the function `VisionYolo` calls when given a model_name
    string. Tests can monkeypatch either registry to inject a fake.
    """
    if model_name in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_name](model_name)
    for prefix, factory in MODEL_PREFIX_REGISTRY:
        if model_name.startswith(prefix):
            return factory(model_name)
    raise VisionModelNotFoundError(
        f"no vision model handler registered for {model_name!r}. "
        f"Known exact matches: {sorted(MODEL_REGISTRY)}; "
        f"known prefixes: {[p for p, _ in MODEL_PREFIX_REGISTRY]}. "
        "Register one with eye.vision_yolo.register_model() or "
        "register_model_prefix() at import time."
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


# ─── Built-in handler: "fake" (always available) ───


def _build_fake_model(model_name: str) -> VisionModel:
    """Default factory for the "fake" model name. Returns an empty
    FakeYOLOModel (no scripted events) that emits nothing for every
    frame. Tests that need scripted behavior construct FakeYOLOModel
    directly and pass it as `model=` to VisionYolo.
    """
    return FakeYOLOModel()


register_model("fake", _build_fake_model)


# ─── Built-in prefix handlers: lazy, SDK-gated, V0a-deferred ───
#
# These are stubs that raise NotImplementedError until Safiq picks a
# real model. They exist so that:
#
#   1. The prefix namespace is reserved — `ultralytics:`, `roboflow:`,
#      `onnx:`, `mlx:` — and a future PR can just swap the factory body
#      without moving any keys around.
#   2. A misconfigured `MODEL_NAME=ultralytics:yolov8n.pt` in prod fails
#      loudly with a prefix-specific error message instead of the
#      generic registry miss.
#   3. The 2027 off-season data engine can register a real handler via
#      `register_model_prefix("onnx:", _load_onnx_model)` at import time
#      without touching this file.


def _not_yet_implemented(prefix: str, hint: str) -> Callable[[str], VisionModel]:
    def _factory(model_name: str) -> VisionModel:
        raise NotImplementedError(
            f"{prefix} prefix handler is registered but not yet implemented "
            f"(requested model_name={model_name!r}). {hint} "
            "See design-intelligence/V0a_MODEL_SELECTION.md for the "
            "resolution plan (Path C → 2027 off-season data engine)."
        )
    return _factory


register_model_prefix(
    "ultralytics:",
    _not_yet_implemented(
        "ultralytics:",
        "To enable: `pip install ultralytics`, then register a real factory "
        "that returns a wrapper exposing .infer(frame_path).",
    ),
)
register_model_prefix(
    "roboflow:",
    _not_yet_implemented(
        "roboflow:",
        "To enable: `pip install inference` or `pip install roboflow`, "
        "then register a real factory. See V0a §Path A for the compound "
        "pipeline shape.",
    ),
)
register_model_prefix(
    "onnx:",
    _not_yet_implemented(
        "onnx:",
        "To enable: `pip install onnxruntime`, then register a factory "
        "that loads the .onnx file at the suffix path.",
    ),
)
register_model_prefix(
    "mlx:",
    _not_yet_implemented(
        "mlx:",
        "To enable: `pip install mlx mlx-vlm`, then register a factory "
        "for MLX-exported vision models (off-season auto-label engine).",
    ),
)


# ─── Backward-compatible _load_real_model shim ───


def _load_real_model(model_name: str) -> VisionModel:
    """Backward-compat wrapper around `load_vision_model`.

    Kept for the V1-era call sites and for tests that patch this
    symbol directly. New code should call `load_vision_model` or
    just pass `model_name=` to `VisionYolo`.
    """
    return load_vision_model(model_name)


# ─── VisionYolo — public wrapper ───


class VisionYolo:
    """Wrapper around whichever YOLO-ish model is loaded.

    Construct with either an injected `model` (tests) or a `model_name`
    string (prod). The default `model_name="fake"` builds an empty
    `FakeYOLOModel` via the registry — safe no-op for every frame.

    Any other `model_name` routes through `load_vision_model`, which
    consults `MODEL_REGISTRY` and then `MODEL_PREFIX_REGISTRY`. A new
    model = one `register_model(...)` or `register_model_prefix(...)`
    call; no changes to this class.
    """

    def __init__(
        self,
        model: Optional[VisionModel] = None,
        *,
        model_name: str = "fake",
    ) -> None:
        if model is not None:
            self._model = model
            self.model_name = model_name or type(model).__name__
            return

        self._model = load_vision_model(model_name)
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
