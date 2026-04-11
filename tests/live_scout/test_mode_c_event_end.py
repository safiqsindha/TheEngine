"""Tests for workers/mode_c_event_end.py — W5 Mode C event-end worker.

All tests run offline. Mode B is stubbed as a no-op (it doesn't exist
in Gate 4 order yet); the digest backend is a LocalFileBackend rooted
in a tmp path; the Discord post is a recording callable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.mode_c_event_end import (  # noqa: E402
    ModeCEventEndResult,
    build_digest,
    compute_top_three,
    run_mode_c_event_end,
)
from workers.state_backend import LocalFileBackend  # noqa: E402


# ─── Fixtures ───


def _live_match(
    *,
    event_key: str,
    match_num: int,
    red_teams: list[int],
    blue_teams: list[int],
    red_score: int,
    blue_score: int,
) -> dict[str, Any]:
    return {
        "event_key": event_key,
        "match_key": f"{event_key}_qm{match_num}",
        "match_num": match_num,
        "comp_level": "qm",
        "red_teams": red_teams,
        "blue_teams": blue_teams,
        "red_score": red_score,
        "blue_score": blue_score,
        "red_breakdown": {},
        "blue_breakdown": {},
        "winning_alliance": "red" if red_score > blue_score else ("blue" if blue_score > red_score else "tie"),
        "timer_state": "post",
        "processed_at": 1_700_000_000,
        "source_video_id": "test",
        "source_tier": "vod",
        "confidence": 0.9,
    }


def _seeded_state(event_key: str = "2025txdal") -> dict[str, Any]:
    """Build a state with 3 teams, each with 3 matches and distinct avg
    scores so top-3 sorting is unambiguous."""
    lm = {}
    # Team 2950: 3 matches, always on red, scores 100, 110, 120 (avg 110)
    # Team 254:  3 matches, always on blue, scores 150, 160, 170 (avg 160)
    # Team 148:  3 matches, always on red, scores 130, 140, 150 (avg 140)
    for i, (red_score, blue_score) in enumerate(
        [(100, 150), (110, 160), (120, 170)], start=1
    ):
        m = _live_match(
            event_key=event_key, match_num=i,
            red_teams=[2950, 9001, 9002], blue_teams=[254, 9003, 9004],
            red_score=red_score, blue_score=blue_score,
        )
        lm[m["match_key"]] = m
    for i, (red_score, blue_score) in enumerate(
        [(130, 50), (140, 55), (150, 60)], start=4
    ):
        m = _live_match(
            event_key=event_key, match_num=i,
            red_teams=[148, 9005, 9006], blue_teams=[9007, 9008, 9009],
            red_score=red_score, blue_score=blue_score,
        )
        lm[m["match_key"]] = m

    teams = {
        "2950": {
            "team": 2950,
            "real_avg_score": 110.0,
            "match_count": 3,
            "live_match_keys": [f"{event_key}_qm1", f"{event_key}_qm2", f"{event_key}_qm3"],
        },
        "254": {
            "team": 254,
            "real_avg_score": 160.0,
            "match_count": 3,
            "live_match_keys": [f"{event_key}_qm1", f"{event_key}_qm2", f"{event_key}_qm3"],
        },
        "148": {
            "team": 148,
            "real_avg_score": 140.0,
            "match_count": 3,
            "live_match_keys": [f"{event_key}_qm4", f"{event_key}_qm5", f"{event_key}_qm6"],
        },
        "9001": {
            "team": 9001,
            # Missing real_avg_score → must be skipped.
            "match_count": 3,
            "live_match_keys": [f"{event_key}_qm1", f"{event_key}_qm2", f"{event_key}_qm3"],
        },
    }

    return {
        "event_key": event_key,
        "teams": teams,
        "live_matches": lm,
    }


class _RecordingPost:
    def __init__(self, return_value: bool = True):
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self._ret = return_value

    def __call__(self, webhook_url, payload, *, dedupe_key=None, **kwargs):
        self.calls.append((webhook_url, payload, {"dedupe_key": dedupe_key, **kwargs}))
        return self._ret


# ─── compute_top_three ───


def test_compute_top_three_sorts_descending_by_avg():
    state = _seeded_state()
    top = compute_top_three(state, "2025txdal")
    assert [t["team"] for t in top] == [254, 148, 2950]
    assert top[0]["avg_score"] == pytest.approx(160.0)


def test_compute_top_three_skips_teams_without_real_avg():
    state = _seeded_state()
    top = compute_top_three(state, "2025txdal")
    assert 9001 not in [t["team"] for t in top]


def test_compute_top_three_ties_broken_by_team_number():
    state = _seeded_state()
    # Tie 148 and 2950 at avg 150
    state["teams"]["2950"]["real_avg_score"] = 150.0
    state["teams"]["148"]["real_avg_score"] = 150.0
    top = compute_top_three(state, "2025txdal")
    # 254 still wins (160); then 148 before 2950 (ascending tie break).
    assert [t["team"] for t in top] == [254, 148, 2950]


def test_compute_top_three_filters_by_event_key():
    state = _seeded_state("2025txdal")
    # Team registered only for a DIFFERENT event — must not appear.
    state["teams"]["9999"] = {
        "team": 9999,
        "real_avg_score": 999.0,
        "match_count": 3,
        "live_match_keys": ["2025txaus_qm1", "2025txaus_qm2", "2025txaus_qm3"],
    }
    top = compute_top_three(state, "2025txdal")
    assert 9999 not in [t["team"] for t in top]


# ─── build_digest ───


def test_build_digest_basic_shape():
    state = _seeded_state()
    digest = build_digest(state, "2025txdal")
    assert digest["event_key"] == "2025txdal"
    assert digest["match_count"] == 6
    assert len(digest["top_three"]) == 3
    assert len(digest["alliance_briefs"]) == 3
    # Phase 2 hook is present and stubbed.
    assert digest["phase_2_synthesis"] is None
    # Each alliance brief has an empty (Phase-2-pending) brief string.
    for brief in digest["alliance_briefs"]:
        assert brief["brief"] == ""


def test_build_digest_ignores_matches_from_other_events():
    state = _seeded_state("2025txdal")
    # Inject a stray match from a different event.
    m = _live_match(
        event_key="2025txaus", match_num=42,
        red_teams=[254, 9100, 9101], blue_teams=[9102, 9103, 9104],
        red_score=200, blue_score=100,
    )
    state["live_matches"][m["match_key"]] = m
    digest = build_digest(state, "2025txdal")
    assert digest["match_count"] == 6  # unchanged


# ─── run_mode_c_event_end ───


def test_run_event_end_writes_digest_and_fires_post(tmp_path):
    state = _seeded_state()
    digest_path = tmp_path / "digest.json"
    digest_backend = LocalFileBackend(digest_path)
    post = _RecordingPost()

    result = run_mode_c_event_end(
        event_key="2025txdal",
        state=state,
        matches_fetcher=lambda ek: [],
        run_mode_b=lambda **kw: None,
        post_fn=post,
        webhook_url="https://discord.example/wh/abc",
        digest_backend=digest_backend,
        persist=False,
    )

    assert result.error is None
    assert result.match_count == 6
    assert [t["team"] for t in result.top_three] == [254, 148, 2950]
    assert result.posted is True

    stored = json.loads(digest_path.read_text())
    assert stored["event_key"] == "2025txdal"
    assert stored["match_count"] == 6
    assert len(stored["top_three"]) == 3

    assert len(post.calls) == 1
    url, payload, kwargs = post.calls[0]
    assert url == "https://discord.example/wh/abc"
    assert kwargs["dedupe_key"] == "event_end:2025txdal"
    assert "2025txdal" in payload["content"]
    assert "6" in payload["content"]


def test_run_event_end_no_discord_mode_skips_post(tmp_path):
    state = _seeded_state()
    digest_backend = LocalFileBackend(tmp_path / "digest.json")
    post = _RecordingPost()

    result = run_mode_c_event_end(
        event_key="2025txdal",
        state=state,
        matches_fetcher=lambda ek: [],
        run_mode_b=lambda **kw: None,
        post_fn=post,
        webhook_url="",  # --no-discord maps to empty URL
        digest_backend=digest_backend,
        persist=False,
    )

    assert result.error is None
    assert result.posted is False
    assert post.calls == []


def test_run_event_end_respects_stubbed_mode_b(tmp_path):
    """run_mode_b must be called with (event_key, state) kwargs."""
    state = _seeded_state()
    digest_backend = LocalFileBackend(tmp_path / "digest.json")
    calls = []

    def fake_mode_b(**kwargs):
        calls.append(kwargs)

    run_mode_c_event_end(
        event_key="2025txdal",
        state=state,
        matches_fetcher=lambda ek: [],
        run_mode_b=fake_mode_b,
        post_fn=_RecordingPost(),
        webhook_url="",
        digest_backend=digest_backend,
        persist=False,
    )
    assert len(calls) == 1
    assert calls[0]["event_key"] == "2025txdal"
    assert calls[0]["state"] is state


def test_run_event_end_reports_error_on_digest_write_failure(tmp_path):
    state = _seeded_state()
    post = _RecordingPost()

    class _BrokenBackend:
        name = "broken"
        def read(self): return None
        def write(self, payload): raise RuntimeError("disk full")

    result = run_mode_c_event_end(
        event_key="2025txdal",
        state=state,
        matches_fetcher=lambda ek: [],
        run_mode_b=lambda **kw: None,
        post_fn=post,
        webhook_url="",
        digest_backend=_BrokenBackend(),
        persist=False,
    )
    assert result.error is not None and "disk full" in result.error
    assert result.posted is False
