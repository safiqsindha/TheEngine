#!/usr/bin/env python3
"""
The Engine — Live Scout Mode C Anomaly Worker (W4)
Team 2950 — The Devastators

Mode C is the low-frequency, passive branch of Live Scout. Every five
minutes it scans *other* FIT events for newly-completed matches and
flags statistical outliers — matches whose total score is an extreme
outlier relative to the event's own rolling mean, or whose absolute
score exceeds a hard floor. When we spot one, we ping Discord so the
mentors can decide whether to queue the match for full OCR processing
later.

Stats-only, no OCR. The whole point of Mode C is to be cheap: we read
TBA scores (already computed) and compute a z-score. No HLS pull, no
paddle, no GPU.

Persistence:
  - Per-event state lives in the anomaly blob via `get_anomaly_backend()`:

        {
          "events": {
            "2026txdal": {
              "processed_match_keys": ["2026txdal_qm1", ...],
              "score_sum":  2415,
              "score_sum_sq": 410025,
              "score_n": 24,
              "last_cursor": 1712345678   # max actual_time seen
            },
            ...
          }
        }

  - Discord dedupe lives in the discord_dedupe blob (handled by D1).

Triggering: cron every 5 min outside our event, launched from the same
dispatcher state the other workers read.

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §W4.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scout"))

from workers import discord_push  # noqa: E402

# ─── Tunables ───

DEFAULT_Z_THRESHOLD = 3.0          # |z| above this → anomaly
DEFAULT_ABSOLUTE_FLOOR = 250       # total score above this → anomaly
MIN_SAMPLE_FOR_ZSCORE = 5          # below this, only the absolute floor fires


# ─── Result dataclass ───


@dataclass
class ModeCAnomalyResult:
    """What run_mode_c_anomaly returns to its CLI / caller."""
    processed: int = 0
    anomalies_fired: list[str] = field(default_factory=list)
    events_seen: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


# ─── Pure stats helpers ───


def total_score(tba_match: dict[str, Any]) -> Optional[int]:
    """Red+blue total from a TBA match dict, or None if either side
    lacks a finalized score."""
    alliances = tba_match.get("alliances", {}) or {}
    red = alliances.get("red", {}) or {}
    blue = alliances.get("blue", {}) or {}
    r = red.get("score", -1)
    b = blue.get("score", -1)
    if r is None or b is None:
        return None
    if int(r) < 0 or int(b) < 0:
        return None
    return int(r) + int(b)


def is_finalized(tba_match: dict[str, Any]) -> bool:
    """A match is finalized when actual_time is set and both scores are
    non-negative."""
    if int(tba_match.get("actual_time") or 0) <= 0:
        return False
    return total_score(tba_match) is not None


def compute_running_mean_std(
    score_n: int,
    score_sum: float,
    score_sum_sq: float,
) -> tuple[float, float]:
    """Return (mean, population-stddev) from running sums."""
    if score_n <= 0:
        return 0.0, 0.0
    mean = score_sum / score_n
    variance = max(0.0, (score_sum_sq / score_n) - (mean * mean))
    return mean, math.sqrt(variance)


def zscore(value: float, mean: float, std: float) -> float:
    """Return z-score of `value`. 0.0 if stddev is zero (not enough spread)."""
    if std <= 1e-9:
        return 0.0
    return (value - mean) / std


def classify_anomaly(
    total: int,
    *,
    score_n: int,
    mean: float,
    std: float,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    absolute_floor: int = DEFAULT_ABSOLUTE_FLOOR,
) -> tuple[bool, str]:
    """Decide whether `total` is an anomaly. Returns (hit, reason_string).

    Rules:
      - If total exceeds absolute_floor → always fires.
      - Otherwise, if we have ≥ MIN_SAMPLE_FOR_ZSCORE samples AND
        |z| > z_threshold → fires.
    """
    if total >= absolute_floor:
        return True, f"absolute floor ({total} >= {absolute_floor})"
    if score_n >= MIN_SAMPLE_FOR_ZSCORE:
        z = zscore(float(total), mean, std)
        if abs(z) > z_threshold:
            return True, f"z-score {z:+.2f} (|z| > {z_threshold})"
    return False, ""


# ─── Event state helpers ───


def _empty_event_state() -> dict[str, Any]:
    return {
        "processed_match_keys": [],
        "score_sum": 0,
        "score_sum_sq": 0,
        "score_n": 0,
        "last_cursor": 0,
    }


def _update_event_state(
    ev_state: dict[str, Any],
    *,
    match_key: str,
    total: int,
    actual_time: int,
) -> None:
    """Fold a new match's contribution into the per-event rolling stats."""
    processed = set(ev_state.get("processed_match_keys", []))
    if match_key in processed:
        return
    processed.add(match_key)
    ev_state["processed_match_keys"] = sorted(processed)
    ev_state["score_sum"] = int(ev_state.get("score_sum", 0)) + total
    ev_state["score_sum_sq"] = int(ev_state.get("score_sum_sq", 0)) + (total * total)
    ev_state["score_n"] = int(ev_state.get("score_n", 0)) + 1
    if actual_time > int(ev_state.get("last_cursor", 0)):
        ev_state["last_cursor"] = int(actual_time)


# ─── Default I/O ───


def _default_fit_event_matches(event_key: str) -> list[dict[str, Any]]:
    """Default TBA match fetcher. Tests inject their own."""
    from tba_client import event_matches
    return event_matches(event_key)


def _default_active_fit_events() -> list[str]:
    """Read active FIT event keys from dispatcher state (W1)."""
    from workers.discovery import load_dispatcher_state
    ds = load_dispatcher_state()
    if ds is None:
        return []
    return list(ds.active_events)


# ─── Orchestrator ───


def run_mode_c_anomaly(
    *,
    our_event_key: Optional[str],
    matches_fetcher: Callable[[str], list[dict[str, Any]]] = _default_fit_event_matches,
    events_fetcher: Callable[[], list[str]] = _default_active_fit_events,
    state: Optional[dict[str, Any]] = None,
    post_fn: Callable[..., bool] = discord_push.post,
    webhook_url: Optional[str] = None,
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    absolute_floor: int = DEFAULT_ABSOLUTE_FLOOR,
    persist: bool = True,
) -> ModeCAnomalyResult:
    """Scan newly-completed matches at non-our active FIT events for
    statistical anomalies and push Discord alerts on hits.

    Args:
        our_event_key: Event we're playing at — skipped entirely (Mode A
            owns that event). `None` means process every active event.
        matches_fetcher: (event_key) -> list[tba_match_dict]
        events_fetcher: () -> list[event_key]. Default pulls active FIT
            events from dispatcher state.
        state: In-memory anomaly-state dict. If None, loaded from the
            anomaly backend and written back at the end (when persist=True).
        post_fn: Discord push callable. Defaults to `discord_push.post`.
            Tests pass a stub that records calls.
        webhook_url: Discord webhook URL. If None, reads DISCORD_WEBHOOK_URL.
            Empty → no Discord calls, but the anomaly logic still runs.
        z_threshold: |z| threshold for the relative-anomaly branch.
        absolute_floor: Hard total-score threshold.
        persist: If True and state was loaded from the backend, writes
            the updated state back at the end. Tests pass False to pin
            their in-memory state.

    Returns:
        ModeCAnomalyResult summarizing the run.
    """
    result = ModeCAnomalyResult()

    # ─── Load state (if not provided) ───
    backend = None
    if state is None:
        from workers.state_backend import get_anomaly_backend
        backend = get_anomaly_backend()
        state = backend.read() or {}
    state.setdefault("events", {})

    # ─── Which events do we care about? ───
    try:
        active_events = events_fetcher()
    except Exception as e:  # pragma: no cover - defensive
        result.errors.append(("events_fetcher", str(e)))
        active_events = []

    target_events = [ek for ek in active_events if ek and ek != our_event_key]
    result.events_seen = list(target_events)

    # ─── Resolve webhook URL ───
    if webhook_url is None:
        import os
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")

    # ─── Per-event scan ───
    for ev_key in target_events:
        try:
            matches = matches_fetcher(ev_key)
        except Exception as e:
            result.errors.append((ev_key, f"fetch: {e}"))
            continue

        ev_state = state["events"].setdefault(ev_key, _empty_event_state())
        cursor = int(ev_state.get("last_cursor", 0))
        processed_keys: set[str] = set(ev_state.get("processed_match_keys", []))

        # Only consider finalized matches we haven't scored yet. We use
        # BOTH the cursor (actual_time) and the processed-keys set for
        # defense-in-depth — TBA occasionally back-fills actual_time on
        # older matches after the fact.
        finalized = [m for m in matches if is_finalized(m)]
        finalized.sort(key=lambda m: int(m.get("actual_time") or 0))

        new_matches = [
            m for m in finalized
            if m.get("key") not in processed_keys
            and int(m.get("actual_time") or 0) >= cursor
        ]

        for m in new_matches:
            total = total_score(m)
            if total is None:
                continue
            match_key = m.get("key") or ""
            if not match_key:
                continue

            # Use the rolling stats *as they were before this match* so
            # the anomaly decision is stable regardless of order.
            mean, std = compute_running_mean_std(
                int(ev_state.get("score_n", 0)),
                float(ev_state.get("score_sum", 0)),
                float(ev_state.get("score_sum_sq", 0)),
            )
            hit, reason = classify_anomaly(
                total,
                score_n=int(ev_state.get("score_n", 0)),
                mean=mean,
                std=std,
                z_threshold=z_threshold,
                absolute_floor=absolute_floor,
            )

            # Fold the match into the rolling stats regardless of hit.
            _update_event_state(
                ev_state,
                match_key=match_key,
                total=total,
                actual_time=int(m.get("actual_time") or 0),
            )
            result.processed += 1

            if not hit:
                continue

            # ─── Emit Discord alert ───
            # Pick a representative team — first red driver station.
            alliances = m.get("alliances", {}) or {}
            red_keys = (alliances.get("red", {}) or {}).get("team_keys", []) or []
            try:
                rep_team = int((red_keys[0] or "frc0").replace("frc", "")) if red_keys else 0
            except (TypeError, ValueError):
                rep_team = 0

            payload = discord_push.format_anomaly(
                team=rep_team,
                event_key=ev_key,
                match_key=match_key,
                score=total,
                reason=reason,
            )
            try:
                post_fn(
                    webhook_url,
                    payload,
                    dedupe_key=f"anomaly:{match_key}",
                )
            except Exception as e:
                result.errors.append((match_key, f"discord: {e}"))
                continue
            result.anomalies_fired.append(match_key)

    # ─── Persist ───
    if persist and backend is not None:
        backend.write(state)

    return result


# ─── CLI ───


def _replay_fetcher_from_event(event_key: str):
    """Build a matches_fetcher that returns real data for `event_key`
    only — everything else returns []. Used for `--replay-event`."""
    def _fetch(ek: str) -> list[dict[str, Any]]:
        if ek == event_key:
            return _default_fit_event_matches(ek)
        return []
    return _fetch


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout Mode C anomaly worker")
    parser.add_argument("--our-event", default="",
                        help="Our event key (skipped in the scan)")
    parser.add_argument("--replay-event", default=None,
                        help="Replay mode: scan this specific event (historical)")
    parser.add_argument("--z", type=float, default=DEFAULT_Z_THRESHOLD,
                        help="|z| threshold for anomaly flag")
    parser.add_argument("--floor", type=int, default=DEFAULT_ABSOLUTE_FLOOR,
                        help="Absolute total-score floor for anomaly flag")
    parser.add_argument("--no-discord", action="store_true",
                        help="Skip Discord posting (still updates state)")
    parser.add_argument("--debug", action="store_true",
                        help="Print the result dataclass without persisting state")
    args = parser.parse_args(argv)

    webhook = "" if args.no_discord else None

    if args.replay_event:
        fetcher = _replay_fetcher_from_event(args.replay_event)
        events_fetcher = lambda: [args.replay_event]  # noqa: E731
    else:
        fetcher = _default_fit_event_matches
        events_fetcher = _default_active_fit_events

    result = run_mode_c_anomaly(
        our_event_key=args.our_event or None,
        matches_fetcher=fetcher,
        events_fetcher=events_fetcher,
        webhook_url=webhook,
        z_threshold=args.z,
        absolute_floor=args.floor,
        persist=not args.debug,
    )

    print(f"  processed:       {result.processed}")
    print(f"  events seen:     {result.events_seen}")
    print(f"  anomalies fired: {result.anomalies_fired}")
    if result.errors:
        print(f"  errors: {result.errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
