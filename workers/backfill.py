#!/usr/bin/env python3
"""
The Engine — Live Scout Backfill Worker (W6 / Gate 5)
Team 2950 — The Devastators

Gate 5 closes the moat. The backfill worker iterates every FIT event for
a given season, runs the Mode B pipeline against each one, and writes
the resulting state to a dedicated backfill namespace so we can build
up a multi-season corpus without ever touching the live dispatcher or
pick_board state.

Design notes (important, do not redesign these):

  * Mode B is the OCR pipeline we already ship (W3 / workers/mode_b.py).
    This worker DOES NOT reimplement OCR or VOD pulling — it is a loop
    over events that calls `mode_b.run_mode_b` for each one with a fresh
    state dict. The mode_b module is imported lazily so tests (which
    inject `mode_b_runner`) never need the real module loaded.

  * State isolation is mandatory. Backfill results go through
    `workers.state_backend.get_backfill_backend(event_key=..., season=...)`
    which lives under `workers/.state/backfill/{season}/{event_key}.json`
    locally and `livescoutbackfill/backfill/{season}/{event_key}.json` in
    Azure — a separate container from live state by design.

  * Resilience is the whole ballgame. Production runs are long (hours).
    A single bad event — TBA 503, yt-dlp cookie expiry, an empty VOD —
    MUST NOT abort the whole job. Every per-event failure is captured
    in `events_failed` and the loop continues to the next event.

  * FIT-event filtering. TBA exposes FIT events via the district endpoint
    `/district/{season}fit/events`. We default to that. A `fit_keyword`
    knob exists as a defensive fallback for weirdly-tagged events (e.g.
    off-season scrimmages) — if `events_fetcher` returns events that
    don't have district metadata, we additionally accept events whose
    `event_code` / `name` contains the keyword.

Usage:
    python -m workers.backfill --season 2025
    python -m workers.backfill --season 2025 --only 2025txbel,2025txdri
    python -m workers.backfill --season 2025 --debug

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §W6.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# ─── Path bootstrap so we can import sibling top-level packages ───
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scout") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scout"))

from workers.state_backend import JsonStateBackend, get_backfill_backend  # noqa: E402

logger = logging.getLogger("workers.backfill")


# Comp levels processed by backfill. For live Mode B we only run quals
# (playoffs are handled by a different branch), but the backfill corpus
# wants every match we can get — playoffs included.
DEFAULT_COMP_LEVELS = ("qm", "qf", "sf", "f")


# ─── Types ───


@dataclass
class BackfillResult:
    """Outcome of a whole backfill run across one season.

    Keeps per-event success/failure granular so a human can go back and
    replay only the events that failed (e.g., the two events where the
    VOD hadn't been uploaded yet on first run)."""

    season: int
    events_total: int = 0
    events_succeeded: list[str] = field(default_factory=list)
    events_failed: list[tuple[str, str]] = field(default_factory=list)
    matches_processed: int = 0
    matches_skipped: int = 0

    def summary(self) -> str:
        return (
            f"season={self.season} events_total={self.events_total} "
            f"succeeded={len(self.events_succeeded)} "
            f"failed={len(self.events_failed)} "
            f"matches_processed={self.matches_processed} "
            f"matches_skipped={self.matches_skipped}"
        )


# ─── FIT event filtering ───


def is_fit_event(event: dict[str, Any], *, fit_keyword: str = "fit") -> bool:
    """Return True if a TBA event dict belongs to FIRST in Texas district.

    Order of checks (most-trusted first):
      1. event['district']['abbreviation'] == 'fit'
      2. event['district']['key'] endswith 'fit'  (e.g. '2025fit')
      3. Fallback: event_code / name substring match on the keyword.

    The fallback exists because TBA district metadata is sometimes null
    on off-season or scrimmage events that are still organizationally
    FIT. The fallback is intentionally permissive."""
    district = event.get("district")
    if isinstance(district, dict):
        abbr = (district.get("abbreviation") or "").lower()
        if abbr == fit_keyword.lower():
            return True
        key = (district.get("key") or "").lower()
        if key.endswith(fit_keyword.lower()):
            return True

    # Fallback: event_code / name substring
    code = (event.get("event_code") or "").lower()
    name = (event.get("name") or "").lower()
    key = (event.get("key") or "").lower()
    kw = fit_keyword.lower()
    return kw in code or kw in name or kw in key


def _default_events(season: int) -> list[dict[str, Any]]:
    """Default events fetcher — pulls FIT district events from TBA.

    Tests inject their own fetcher. This function is only called in
    production (and deliberately imports TBA lazily so pytest under
    `test_backfill.py` never hits the network)."""
    from tba_client import district_events  # type: ignore

    district_key = f"{season}fit"
    return list(district_events(district_key) or [])


def _default_mode_b_runner(**kwargs: Any) -> Any:
    """Default mode_b runner — imports the real Mode B worker lazily.

    Kept separate from run_backfill's default so tests can replace it
    without needing mode_b.py to exist in the dev environment."""
    from workers import mode_b  # type: ignore

    return mode_b.run_mode_b(**kwargs)


# ─── Orchestrator ───


def run_backfill(
    *,
    season: int,
    fit_keyword: str = "fit",
    events_fetcher: Callable[[int], list[dict[str, Any]]] = _default_events,
    mode_b_runner: Callable[..., Any] = _default_mode_b_runner,
    frame_resolver: Optional[Callable[..., Any]] = None,
    ocr: Optional[Any] = None,
    comp_levels: Iterable[str] = DEFAULT_COMP_LEVELS,
    only_events: Optional[list[str]] = None,
    state_factory: Optional[Callable[..., JsonStateBackend]] = None,
    clock: Callable[[], float] = time.monotonic,
) -> BackfillResult:
    """Iterate FIT events for a season and run Mode B against each one.

    Args:
        season: 4-digit FRC season, e.g. 2025.
        fit_keyword: District/code substring used to filter FIT events.
        events_fetcher: Callable(season) -> list of TBA event dicts.
            Defaults to TBA `/district/{season}fit/events`.
        mode_b_runner: The Mode B pipeline entry point. Signature matches
            `workers.mode_b.run_mode_b`. Injectable so tests don't need
            the real module. Must accept at minimum:
                event_key, state, frame_resolver, ocr, comp_levels
            and return an object with `.matches_processed` / `.matches_skipped`
            attributes (or a dict with those keys).
        frame_resolver: Optional per-match frame source passed through
            to Mode B. `None` means Mode B uses its default (VOD puller).
        ocr: Optional OCR instance passed through to Mode B.
        comp_levels: Which TBA comp_levels to process. Backfill defaults
            to all of them (quals AND playoffs) — the whole point of the
            corpus is to be comprehensive.
        only_events: Optional allow-list of event keys. If non-empty, only
            those events are processed (still filtered through is_fit_event
            for safety). Useful for replaying a specific failure.
        state_factory: Override for the per-event state backend builder.
            Default is `get_backfill_backend`. Tests use this to redirect
            writes to tmp_path.
        clock: Injectable monotonic clock for deterministic timing logs
            in tests.

    Returns:
        BackfillResult with per-event success/failure breakdown.

    Contract: this function NEVER raises on a per-event error. It logs
    the failure, records it in `events_failed`, and continues. The only
    way this function raises is if `events_fetcher` itself throws at the
    top (i.e., before any iteration) — which is the desired behavior,
    because then the whole run is garbage and we want to fail loud."""
    if state_factory is None:
        state_factory = get_backfill_backend

    comp_levels_tuple = tuple(comp_levels)

    result = BackfillResult(season=season)

    logger.info("backfill.start season=%s fit_keyword=%s", season, fit_keyword)

    # Top-level fetcher failures are fatal — no events at all means
    # nothing to iterate, and we want the human to see the TBA outage
    # immediately rather than writing an empty success result.
    events_raw = events_fetcher(season)

    fit_events = [e for e in events_raw if is_fit_event(e, fit_keyword=fit_keyword)]

    if only_events:
        only_set = set(only_events)
        fit_events = [e for e in fit_events if e.get("key") in only_set]

    result.events_total = len(fit_events)
    logger.info(
        "backfill.filtered events_raw=%d fit_events=%d only_events=%s",
        len(events_raw), result.events_total, only_events,
    )

    for event in fit_events:
        event_key = event.get("key") or ""
        if not event_key:
            logger.warning("backfill.skip event with no key: %r", event)
            result.events_failed.append(("<unknown>", "missing event key"))
            continue

        started = clock()
        logger.info("backfill.event.start %s", event_key)

        try:
            fresh_state: dict[str, Any] = {}
            mb_result = mode_b_runner(
                event_key=event_key,
                state=fresh_state,
                frame_resolver=frame_resolver,
                ocr=ocr,
                comp_levels=comp_levels_tuple,
            )

            # Extract match counts — support both dataclass-like and dict
            # return shapes so this worker is forward-compatible with
            # whatever mode_b.py ultimately lands on.
            processed = _get_attr_or_key(mb_result, "matches_processed", 0)
            skipped = _get_attr_or_key(mb_result, "matches_skipped", 0)

            # Persist the fresh state into the backfill namespace. We go
            # through the factory so swapping env vars re-routes storage
            # without touching this code.
            backend = state_factory(event_key=event_key, season=season)
            backend.write(fresh_state)

            result.events_succeeded.append(event_key)
            result.matches_processed += int(processed or 0)
            result.matches_skipped += int(skipped or 0)

            elapsed = clock() - started
            logger.info(
                "backfill.event.done %s processed=%d skipped=%d elapsed=%.2fs",
                event_key, processed, skipped, elapsed,
            )
        except Exception as exc:  # noqa: BLE001 — resilience is the point
            elapsed = clock() - started
            reason = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "backfill.event.fail %s reason=%s elapsed=%.2fs",
                event_key, reason, elapsed,
            )
            result.events_failed.append((event_key, reason))
            continue

    logger.info("backfill.done %s", result.summary())
    return result


def _get_attr_or_key(obj: Any, name: str, default: Any = None) -> Any:
    """Support both dataclass-like and dict-like mode_b result shapes."""
    if obj is None:
        return default
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


# ─── CLI ───


def _format_summary_table(result: BackfillResult) -> str:
    """Pretty-print the BackfillResult as a readable summary for humans."""
    lines = [
        "=" * 60,
        f"Backfill summary — season {result.season}",
        "=" * 60,
        f"  Events discovered: {result.events_total}",
        f"  Events succeeded:  {len(result.events_succeeded)}",
        f"  Events failed:     {len(result.events_failed)}",
        f"  Matches processed: {result.matches_processed}",
        f"  Matches skipped:   {result.matches_skipped}",
    ]
    if result.events_succeeded:
        lines.append("")
        lines.append("Succeeded:")
        for ek in result.events_succeeded:
            lines.append(f"  + {ek}")
    if result.events_failed:
        lines.append("")
        lines.append("Failed:")
        for ek, reason in result.events_failed:
            lines.append(f"  - {ek}: {reason}")
    lines.append("=" * 60)
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live Scout Backfill worker (W6 / Gate 5)",
    )
    parser.add_argument(
        "--season", type=int, required=True,
        help="FRC season year, e.g. 2025",
    )
    parser.add_argument(
        "--fit-keyword", default="fit",
        help="District keyword used to identify FIT events (default: fit)",
    )
    parser.add_argument(
        "--only", default=None,
        help="Comma-separated event keys to restrict the run "
             "(e.g. 2025txbel,2025txdri)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    only_events = None
    if args.only:
        only_events = [s.strip() for s in args.only.split(",") if s.strip()]

    result = run_backfill(
        season=args.season,
        fit_keyword=args.fit_keyword,
        only_events=only_events,
    )

    print(_format_summary_table(result))

    # Exit nonzero if *every* discovered event failed, so cron jobs can
    # notice a total outage. A partial success (some events pass, some
    # fail) is still considered a successful run — that's what the
    # BackfillResult is for.
    if result.events_total > 0 and not result.events_succeeded:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
