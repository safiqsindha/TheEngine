"""Tests for workers/discovery.py — W1 dispatcher state builder.

All tests run offline by injecting fake TBA + stream_lister callables.
Covers pure logic (date filter, fuzzy match, stream pairing) and the
orchestrator's dependency wiring.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.discovery import (  # noqa: E402
    DispatcherState,
    StreamInfo,
    build_dispatcher_state,
    filter_active_events,
    identify_our_event,
    load_dispatcher_state,
    match_stream_to_event,
    pair_streams_with_events,
    save_dispatcher_state,
)


# ─── Fixtures ───


def _event(
    key: str,
    name: str,
    start: str,
    end: str,
    short_name: str = "",
    city: str = "",
) -> dict:
    return {
        "key": key,
        "name": name,
        "short_name": short_name,
        "city": city,
        "start_date": start,
        "end_date": end,
    }


TXBEL = _event(
    "2026txbel",
    "FIRST in Texas District Belton Event",
    "2026-04-10", "2026-04-12",
    short_name="Belton",
    city="Belton",
)
TXDRI = _event(
    "2026txdri",
    "FIRST in Texas District Driftwood Event",
    "2026-03-27", "2026-03-29",
    short_name="Driftwood",
    city="Driftwood",
)
TXCMP = _event(
    "2026txcmp",
    "FIRST in Texas District Championship",
    "2026-04-24", "2026-04-26",
    short_name="FiT Championship",
    city="Houston",
)


# ─── filter_active_events ───


def test_filter_active_events_picks_only_current_event():
    events = [TXDRI, TXBEL, TXCMP]
    today = dt.date(2026, 4, 11)
    active = filter_active_events(events, today)
    assert len(active) == 1
    assert active[0]["key"] == "2026txbel"


def test_filter_active_events_window_includes_day_before():
    today = dt.date(2026, 4, 9)  # day before Belton starts
    assert filter_active_events([TXBEL], today, window_days=0) == []
    assert filter_active_events([TXBEL], today, window_days=1)[0]["key"] == "2026txbel"


def test_filter_active_events_window_includes_day_after():
    today = dt.date(2026, 4, 13)  # day after Belton ends
    assert filter_active_events([TXBEL], today, window_days=0) == []
    assert filter_active_events([TXBEL], today, window_days=1)[0]["key"] == "2026txbel"


def test_filter_active_events_skips_malformed_dates():
    broken = {"key": "bad", "name": "x", "start_date": "", "end_date": "also-not-a-date"}
    today = dt.date(2026, 4, 11)
    assert filter_active_events([broken, TXBEL], today) == [TXBEL]


def test_filter_active_events_empty_when_nothing_today():
    assert filter_active_events([TXDRI, TXCMP], dt.date(2026, 4, 11)) == []


# ─── identify_our_event ───


def test_identify_our_event_picks_only_active():
    out = identify_our_event([TXBEL])
    assert out["key"] == "2026txbel"


def test_identify_our_event_returns_none_when_empty():
    assert identify_our_event([]) is None


def test_identify_our_event_picks_earliest_when_multiple():
    """If two events overlap (never happens in reality but defend against it),
    pick the one starting first."""
    overlapping = _event("2026txwac", "FiT Waco", "2026-04-10", "2026-04-11")
    out = identify_our_event([TXBEL, overlapping])
    # TXBEL starts 2026-04-10, wac starts 2026-04-10 — tiebreak by key alphabetical
    assert out["key"] in {"2026txbel", "2026txwac"}


# ─── match_stream_to_event ───


def test_match_stream_positive_by_city_name():
    assert match_stream_to_event(
        "2026 FIRST in Texas District Belton Event - Qualification Day 1",
        event_name=TXBEL["name"],
        event_short_name=TXBEL["short_name"],
        city=TXBEL["city"],
    )


def test_match_stream_negative_for_different_event():
    assert not match_stream_to_event(
        "2026 FIRST in Texas District Driftwood Event - Day 1",
        event_name=TXBEL["name"],
        event_short_name=TXBEL["short_name"],
        city=TXBEL["city"],
    )


def test_match_stream_handles_short_name_only():
    assert match_stream_to_event(
        "Belton Qualification Stream",
        event_name="",
        event_short_name="Belton",
        city="",
    )


def test_match_stream_rejects_pure_noise():
    assert not match_stream_to_event(
        "FIRST in Texas Live",
        event_name=TXBEL["name"],
        event_short_name=TXBEL["short_name"],
        city=TXBEL["city"],
    )


def test_match_stream_rejects_empty_event_sources():
    assert not match_stream_to_event(
        "Belton stream",
        event_name="",
        event_short_name="",
        city="",
    )


# ─── pair_streams_with_events ───


def test_pair_streams_builds_video_to_event_map():
    streams = [
        StreamInfo("aaa111", "Belton District Qual Day 2", "https://y/aaa111"),
        StreamInfo("bbb222", "Driftwood District Day 1", "https://y/bbb222"),
        StreamInfo("ccc333", "FIRST in Texas Live", "https://y/ccc333"),  # noise only
    ]
    events = [TXBEL, TXDRI]
    mapping = pair_streams_with_events(streams, events)
    assert mapping == {
        "aaa111": "2026txbel",
        "bbb222": "2026txdri",
    }
    assert "ccc333" not in mapping


def test_pair_streams_stops_at_first_matching_event():
    """A stream should map to exactly one event even if two share a word."""
    dup = _event(
        "2026txbe2",
        "Belton Alt Event",
        "2026-04-10", "2026-04-12",
        city="Belton",
    )
    streams = [StreamInfo("aaa111", "Belton District Qual", "https://y/aaa111")]
    mapping = pair_streams_with_events(streams, [TXBEL, dup])
    # Whichever came first in the events list wins — TXBEL in this case
    assert mapping == {"aaa111": "2026txbel"}


# ─── build_dispatcher_state orchestrator ───


def test_build_dispatcher_state_happy_path():
    def fake_tba(team, year):
        assert team == 2950
        assert year == 2026
        return [TXDRI, TXBEL, TXCMP]

    def fake_streams():
        return [
            StreamInfo("aaa111", "Belton District Qual Day 2", "https://y/aaa111"),
            StreamInfo("bbb222", "Driftwood Day 1", "https://y/bbb222"),  # not active
        ]

    state = build_dispatcher_state(
        our_team=2950,
        today=dt.date(2026, 4, 11),
        tba_fetcher=fake_tba,
        stream_lister=fake_streams,
        now=lambda: 1744387200,
    )

    assert state.today == "2026-04-11"
    assert state.our_event == "2026txbel"
    assert "Belton" in state.our_event_name
    assert state.active_events == ["2026txbel"]
    assert state.generated_at == 1744387200
    # Belton matches an active event; Driftwood does not (it's not in active_events)
    assert state.stream_to_event == {"aaa111": "2026txbel"}
    assert len(state.active_streams) == 2
    assert state.active_streams[0]["event_key"] == "2026txbel"
    assert state.active_streams[1]["event_key"] == ""


def test_build_dispatcher_state_no_active_event():
    def fake_tba(team, year):
        return [TXDRI, TXCMP]  # neither is active on 2026-04-11

    state = build_dispatcher_state(
        our_team=2950,
        today=dt.date(2026, 4, 11),
        tba_fetcher=fake_tba,
        stream_lister=lambda: [],
        now=lambda: 1744387200,
    )
    assert state.our_event is None
    assert state.active_events == []
    assert state.active_streams == []


def test_build_dispatcher_state_tba_failure_returns_empty():
    def broken_tba(team, year):
        raise RuntimeError("TBA unreachable")

    state = build_dispatcher_state(
        our_team=2950,
        today=dt.date(2026, 4, 11),
        tba_fetcher=broken_tba,
        stream_lister=lambda: [],
        now=lambda: 1,
    )
    assert state.our_event is None
    assert state.active_events == []


def test_build_dispatcher_state_stream_lister_failure_is_nonfatal():
    def broken_streams():
        raise RuntimeError("yt-dlp not installed")

    state = build_dispatcher_state(
        our_team=2950,
        today=dt.date(2026, 4, 11),
        tba_fetcher=lambda t, y: [TXBEL],
        stream_lister=broken_streams,
        now=lambda: 1,
    )
    # We still know our event even without streams
    assert state.our_event == "2026txbel"
    assert state.active_streams == []


# ─── Persistence round-trip ───


def test_save_and_load_dispatcher_state(tmp_path):
    state = DispatcherState(
        generated_at=1744387200,
        today="2026-04-11",
        our_event="2026txbel",
        our_event_name="Belton",
        active_events=["2026txbel"],
        active_streams=[{"video_id": "aaa111", "title": "Belton", "url": "u", "event_key": "2026txbel"}],
        stream_to_event={"aaa111": "2026txbel"},
    )
    target = tmp_path / "dispatcher.json"
    save_dispatcher_state(state, target)
    assert target.exists()

    data = json.loads(target.read_text())
    assert data["our_event"] == "2026txbel"

    restored = load_dispatcher_state(target)
    assert restored is not None
    assert restored.our_event == "2026txbel"
    assert restored.stream_to_event == {"aaa111": "2026txbel"}


def test_load_dispatcher_state_returns_none_when_missing(tmp_path):
    assert load_dispatcher_state(tmp_path / "nope.json") is None
