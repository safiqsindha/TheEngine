#!/usr/bin/env python3
"""
The Engine — Live Scout Discovery Worker (W1)
Team 2950 — The Devastators

First step in the Live Scout dispatch pipeline. Answers two questions:

  1. Which FRC event is our team playing at *right now*?
  2. Which YouTube broadcasts on the @FIRSTinTexas live channel
     correspond to that event?

The answer is written to a local dispatcher JSON file. Mode A reads
that file every cron tick and knows exactly which stream to pull.

Design — dependency injection everywhere:
  - TBA access is injected as a `tba_fetcher` callable so tests can
    avoid network calls.
  - YouTube channel scraping goes through `stream_lister`, another
    injectable callable so we can test the orchestrator without yt-dlp.
  - Pure logic (date filtering, our-event identification, stream⇄event
    matching) is factored into plain functions.

The real stream lister uses yt-dlp to dump channel metadata — no
YouTube Data API key required, which keeps the Azure deploy simpler.

Usage:
    # Dry run (no state written)
    python -m workers.discovery --dry-run

    # Normal run (writes workers/.state/dispatcher.json)
    python -m workers.discovery

    # Override current date for testing
    python -m workers.discovery --today 2026-04-10 --dry-run

Schema reference: LIVE_SCOUT_PHASE1_BUILD.md §W1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# Default channel: FIRST in Texas live broadcasts
FIT_LIVE_CHANNEL = "https://www.youtube.com/@FIRSTinTexas/streams"
OUR_TEAM_NUMBER = 2950

STATE_DIR = Path(__file__).parent / ".state"
DISPATCHER_STATE_PATH = STATE_DIR / "dispatcher.json"

YTDLP_LIST_TIMEOUT_S = 30


# ─── Types ───


@dataclass
class StreamInfo:
    """One live YouTube broadcast on the target channel."""
    video_id: str
    title: str
    url: str
    is_live: bool = True


@dataclass
class DispatcherState:
    """What Mode A reads on every cron tick."""
    generated_at: int                        # unix epoch
    today: str                               # ISO date, for debugging
    our_event: Optional[str]                 # e.g. "2026txbel" or None
    our_event_name: str = ""
    active_events: list[str] = field(default_factory=list)  # all active 2950-attended events
    active_streams: list[dict[str, Any]] = field(default_factory=list)
    # Stream→event mapping: {video_id: event_key}
    stream_to_event: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "today": self.today,
            "our_event": self.our_event,
            "our_event_name": self.our_event_name,
            "active_events": list(self.active_events),
            "active_streams": list(self.active_streams),
            "stream_to_event": dict(self.stream_to_event),
        }


# ─── Pure logic ───


def _parse_iso_date(s: str) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def filter_active_events(
    events: list[dict[str, Any]],
    today: dt.date,
    window_days: int = 0,
) -> list[dict[str, Any]]:
    """Return events whose date range includes `today`.

    `window_days` extends the range on both ends — useful for Friday-night
    pre-event discovery when qual day hasn't started yet.
    """
    out: list[dict[str, Any]] = []
    for e in events:
        start = _parse_iso_date(e.get("start_date", ""))
        end = _parse_iso_date(e.get("end_date", ""))
        if not start or not end:
            continue
        if (start - dt.timedelta(days=window_days)) <= today <= (end + dt.timedelta(days=window_days)):
            out.append(e)
    return out


def identify_our_event(
    active_events: list[dict[str, Any]],
    our_team: int = OUR_TEAM_NUMBER,
) -> Optional[dict[str, Any]]:
    """Pick the event our team is currently playing at.

    If multiple events match (extremely unlikely), returns the earliest-
    starting one. Event dicts come from TBA's /team/<key>/events/<year>,
    which only returns events the team is registered for — so in practice
    the filter above is already "our" events. Returns None when nothing
    is active.
    """
    if not active_events:
        return None
    # TBA's /team/<key>/events already scopes to our-team events.
    return sorted(
        active_events,
        key=lambda e: e.get("start_date", ""),
    )[0]


# Title-noise words that should not drive name matching
_NOISE_WORDS = {
    "FIRST", "IN", "TEXAS", "DISTRICT", "EVENT", "2025", "2026", "2027",
    "LIVE", "STREAM", "QUALS", "QUALIFICATION", "ELIMS", "PLAYOFFS",
    "CHAMPIONSHIP", "CHAMPS", "REGIONAL", "OFFICIAL", "DAY", "ROUND",
}

_TOKEN_RE = re.compile(r"[A-Z0-9]+")


def _tokenize(text: str) -> set[str]:
    tokens = set(_TOKEN_RE.findall(text.upper()))
    return {t for t in tokens if t not in _NOISE_WORDS and len(t) >= 3}


def match_stream_to_event(
    stream_title: str,
    event_name: str,
    event_short_name: str = "",
    city: str = "",
) -> bool:
    """Fuzzy match a YouTube broadcast title to a TBA event.

    Strategy: tokenize both sides, strip noise words, require ≥1 distinctive
    token in common. Short events or numeric-heavy titles fall through to
    a city-name check.
    """
    stream_tokens = _tokenize(stream_title)
    if not stream_tokens:
        return False

    event_sources = " ".join(filter(None, [event_name, event_short_name, city]))
    event_tokens = _tokenize(event_sources)
    if not event_tokens:
        return False

    # Any distinctive-token overlap is a match
    return bool(stream_tokens & event_tokens)


def pair_streams_with_events(
    streams: list[StreamInfo],
    events: list[dict[str, Any]],
) -> dict[str, str]:
    """Return {video_id: event_key} for streams we can confidently map to
    one of the active events."""
    mapping: dict[str, str] = {}
    for s in streams:
        for e in events:
            if match_stream_to_event(
                s.title,
                event_name=e.get("name", ""),
                event_short_name=e.get("short_name", ""),
                city=e.get("city", ""),
            ):
                mapping[s.video_id] = e.get("key", "")
                break
    return mapping


# ─── I/O: yt-dlp channel scrape ───


def list_channel_live_streams(
    channel_url: str = FIT_LIVE_CHANNEL,
    ytdlp: Optional[str] = None,
    max_items: int = 20,
) -> list[StreamInfo]:
    """Return currently-live broadcasts on `channel_url` using yt-dlp.

    yt-dlp's `--flat-playlist --print-json` dumps one JSON object per
    entry. We pick the ones flagged `is_live == True`. This avoids
    needing a YouTube Data API key.
    """
    if ytdlp is None:
        from hls_pull import find_ytdlp  # lazy: avoid import during tests
        ytdlp = find_ytdlp()

    cmd = [
        ytdlp,
        "--flat-playlist",
        "--print-json",
        "--playlist-items", f"1-{max_items}",
        "--no-warnings",
        channel_url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=YTDLP_LIST_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return []
    if result.returncode != 0:
        return []

    out: list[StreamInfo] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        # yt-dlp exposes `is_live` and `live_status` on flat-playlist entries
        is_live = bool(data.get("is_live")) or data.get("live_status") == "is_live"
        if not is_live:
            continue
        video_id = data.get("id", "")
        if not video_id:
            continue
        out.append(StreamInfo(
            video_id=video_id,
            title=data.get("title", ""),
            url=data.get("url") or f"https://www.youtube.com/watch?v={video_id}",
            is_live=True,
        ))
    return out


# ─── I/O: TBA wrapper ───


def fetch_team_events(our_team: int, year: int) -> list[dict[str, Any]]:
    """Fetch all events the team is registered for in `year` from TBA."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scout"))
    from tba_client import team_events, team_key
    return team_events(team_key(our_team), year)


# ─── Orchestrator ───


def build_dispatcher_state(
    our_team: int = OUR_TEAM_NUMBER,
    today: Optional[dt.date] = None,
    *,
    tba_fetcher: Callable[[int, int], list[dict[str, Any]]] = fetch_team_events,
    stream_lister: Callable[[], list[StreamInfo]] = list_channel_live_streams,
    window_days: int = 1,
    now: Optional[Callable[[], int]] = None,
) -> DispatcherState:
    """Full discovery pipeline. Side-effect free (no disk writes).

    Args:
        our_team: Team number to scope discovery to.
        today: Override current date. Defaults to dt.date.today().
        tba_fetcher: Injection point for TBA access. Signature:
            (team_number, year) -> list[event_dict]
        stream_lister: Injection point for channel scraping. Signature:
            () -> list[StreamInfo]
        window_days: Pad event date range by this many days on each side.
        now: Override for time.time() — mostly for tests.
    """
    import time
    if today is None:
        today = dt.date.today()
    if now is None:
        now = lambda: int(time.time())

    try:
        events = tba_fetcher(our_team, today.year)
    except Exception as e:
        print(f"  WARN: TBA fetch failed: {e}", file=sys.stderr)
        events = []

    active = filter_active_events(events, today, window_days=window_days)
    our_event_dict = identify_our_event(active, our_team=our_team)

    try:
        streams = stream_lister()
    except Exception as e:
        print(f"  WARN: stream list failed: {e}", file=sys.stderr)
        streams = []

    mapping = pair_streams_with_events(streams, active)

    state = DispatcherState(
        generated_at=now(),
        today=today.isoformat(),
        our_event=(our_event_dict or {}).get("key"),
        our_event_name=(our_event_dict or {}).get("name", ""),
        active_events=[e.get("key", "") for e in active if e.get("key")],
        active_streams=[
            {
                "video_id": s.video_id,
                "title": s.title,
                "url": s.url,
                "event_key": mapping.get(s.video_id, ""),
            }
            for s in streams
        ],
        stream_to_event=mapping,
    )
    return state


def save_dispatcher_state(
    state: DispatcherState,
    path: Optional[Path] = None,
    *,
    backend: Optional["JsonStateBackend"] = None,
) -> None:
    """Persist dispatcher state for Mode A to pick up.

    By default routes through the configured StateBackend (local file
    or Azure Table, depending on STATE_BACKEND env var). The legacy
    `path=` argument is retained for backwards compatibility — passing
    a path forces a LocalFileBackend at that location, which is what
    every existing test relies on.
    """
    from workers.state_backend import LocalFileBackend, get_dispatcher_backend
    if backend is None:
        backend = LocalFileBackend(path) if path is not None else get_dispatcher_backend()
    backend.write(state.to_dict())


def load_dispatcher_state(
    path: Optional[Path] = None,
    *,
    backend: Optional["JsonStateBackend"] = None,
) -> Optional[DispatcherState]:
    """Load dispatcher state if it exists.

    Mirrors `save_dispatcher_state`'s contract: defaults to the
    configured StateBackend, but accepts an explicit `path=` for
    legacy callers and tests."""
    from workers.state_backend import LocalFileBackend, get_dispatcher_backend
    if backend is None:
        backend = LocalFileBackend(path) if path is not None else get_dispatcher_backend()
    data = backend.read()
    if data is None:
        return None
    return DispatcherState(
        generated_at=data.get("generated_at", 0),
        today=data.get("today", ""),
        our_event=data.get("our_event"),
        our_event_name=data.get("our_event_name", ""),
        active_events=list(data.get("active_events", [])),
        active_streams=list(data.get("active_streams", [])),
        stream_to_event=dict(data.get("stream_to_event", {})),
    )


# ─── CLI ───


def _format_state(state: DispatcherState) -> str:
    lines = [
        f"  Dispatcher state @ {state.today}",
        f"  {'─' * 60}",
        f"  Our event:     {state.our_event or '<none active>'}",
    ]
    if state.our_event_name:
        lines.append(f"  Event name:    {state.our_event_name}")
    lines.append(f"  Active events: {', '.join(state.active_events) or '<none>'}")
    lines.append(f"  Live streams:  {len(state.active_streams)}")
    for s in state.active_streams:
        tag = f"→ {s['event_key']}" if s.get("event_key") else "(unmatched)"
        lines.append(f"    {s['video_id']}  {tag}  {s.get('title', '')[:50]}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Live Scout discovery worker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print state, don't write dispatcher file")
    parser.add_argument("--today", type=str, default=None,
                        help="Override current date (YYYY-MM-DD) for testing")
    parser.add_argument("--team", type=int, default=OUR_TEAM_NUMBER,
                        help="Team number to scope discovery to")
    args = parser.parse_args(argv)

    today = _parse_iso_date(args.today) if args.today else None

    state = build_dispatcher_state(our_team=args.team, today=today)
    print(_format_state(state))

    if args.dry_run:
        print(f"\n  (dry-run: dispatcher state NOT written)")
        return 0

    save_dispatcher_state(state)
    print(f"\n  Wrote {DISPATCHER_STATE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
