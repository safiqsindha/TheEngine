"""Tests for workers/mode_c_anomaly.py — W4 Mode C anomaly worker.

All tests run offline. TBA, events discovery, and Discord push are
injected as fakes; state is passed in-memory with `persist=False`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from workers.mode_c_anomaly import (  # noqa: E402
    MIN_SAMPLE_FOR_ZSCORE,
    ModeCAnomalyResult,
    classify_anomaly,
    compute_running_mean_std,
    is_finalized,
    run_mode_c_anomaly,
    total_score,
    zscore,
)


# ─── Fixtures ───


def _tba_match(
    *,
    key: str,
    match_number: int,
    red_score: int,
    blue_score: int,
    red_teams: list[int] | None = None,
    blue_teams: list[int] | None = None,
    actual_time: int = 0,
) -> dict[str, Any]:
    red_teams = red_teams or [111, 222, 333]
    blue_teams = blue_teams or [444, 555, 666]
    return {
        "key": key,
        "comp_level": "qm",
        "match_number": match_number,
        "actual_time": actual_time or (1_700_000_000 + match_number),
        "alliances": {
            "red": {
                "team_keys": [f"frc{t}" for t in red_teams],
                "score": red_score,
            },
            "blue": {
                "team_keys": [f"frc{t}" for t in blue_teams],
                "score": blue_score,
            },
        },
    }


class _RecordingPost:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def __call__(self, webhook_url, payload, *, dedupe_key=None, **kwargs):
        self.calls.append((webhook_url, payload, {"dedupe_key": dedupe_key, **kwargs}))
        return True


# ─── Pure helpers ───


def test_total_score_sums_red_and_blue():
    m = _tba_match(key="k", match_number=1, red_score=88, blue_score=72)
    assert total_score(m) == 160


def test_total_score_none_when_unfinalized():
    m = _tba_match(key="k", match_number=1, red_score=-1, blue_score=72)
    assert total_score(m) is None


def test_is_finalized_requires_actual_time_and_scores():
    m = _tba_match(key="k", match_number=1, red_score=88, blue_score=72, actual_time=1000)
    assert is_finalized(m)
    m["actual_time"] = 0
    assert not is_finalized(m)


def test_compute_running_mean_std_empty():
    assert compute_running_mean_std(0, 0, 0) == (0.0, 0.0)


def test_compute_running_mean_std_basic():
    # Three samples: 100, 120, 140 → mean 120, population std ≈ 16.33
    mean, std = compute_running_mean_std(3, 360, 100**2 + 120**2 + 140**2)
    assert mean == pytest.approx(120.0)
    assert std == pytest.approx(16.3299, abs=1e-3)


def test_zscore_returns_zero_on_flat_distribution():
    assert zscore(100.0, 100.0, 0.0) == 0.0


def test_classify_anomaly_absolute_floor_fires():
    hit, reason = classify_anomaly(280, score_n=20, mean=150.0, std=20.0, absolute_floor=250)
    assert hit
    assert "absolute" in reason


def test_classify_anomaly_z_score_fires_above_threshold():
    hit, reason = classify_anomaly(230, score_n=20, mean=150.0, std=20.0, z_threshold=3.0)
    assert hit
    assert "z-score" in reason


def test_classify_anomaly_normal_match_does_not_fire():
    hit, _ = classify_anomaly(155, score_n=20, mean=150.0, std=20.0, z_threshold=3.0)
    assert not hit


def test_classify_anomaly_small_sample_only_floor():
    """Below MIN_SAMPLE_FOR_ZSCORE the z-score branch must not fire."""
    assert MIN_SAMPLE_FOR_ZSCORE >= 2
    hit, _ = classify_anomaly(220, score_n=1, mean=100.0, std=5.0, z_threshold=3.0,
                              absolute_floor=250)
    assert not hit


# ─── Orchestrator — run_mode_c_anomaly ───


def test_zscore_anomaly_fires_for_outlier_match():
    """Seed stats so an incoming 230-pt match is a clear z-score outlier."""
    # 10 prior matches averaging 150 with ~10 stddev.
    prior_scores = [140, 145, 150, 155, 160, 150, 145, 155, 150, 150]
    n = len(prior_scores)
    s = sum(prior_scores)
    sq = sum(x * x for x in prior_scores)

    state = {
        "events": {
            "2025txdal": {
                "processed_match_keys": [f"2025txdal_qm{i}" for i in range(1, n + 1)],
                "score_sum": s,
                "score_sum_sq": sq,
                "score_n": n,
                "last_cursor": 1_700_000_000,
            }
        }
    }

    new_match = _tba_match(
        key="2025txdal_qm11",
        match_number=11,
        red_score=130, blue_score=100,  # total 230 → z ≈ 14
        actual_time=1_700_000_200,
    )

    post = _RecordingPost()
    result = run_mode_c_anomaly(
        our_event_key="2025txbel",
        matches_fetcher=lambda ek: [new_match] if ek == "2025txdal" else [],
        events_fetcher=lambda: ["2025txdal"],
        state=state,
        post_fn=post,
        webhook_url="https://discord.example/wh/abc",
        persist=False,
    )

    assert "2025txdal_qm11" in result.anomalies_fired
    assert result.processed == 1
    assert len(post.calls) == 1
    url, payload, kwargs = post.calls[0]
    assert url == "https://discord.example/wh/abc"
    assert kwargs["dedupe_key"] == "anomaly:2025txdal_qm11"
    assert "z-score" in payload["content"] or "anomaly" in payload["content"].lower()


def test_absolute_floor_fires_in_low_scoring_event():
    """A 280-pt match in an otherwise quiet event (small sample → no z
    branch) should still fire via the absolute-floor rule."""
    state = {"events": {}}
    matches = [
        _tba_match(key="2025txaus_qm1", match_number=1, red_score=40, blue_score=35,
                   actual_time=1_700_000_001),
        _tba_match(key="2025txaus_qm2", match_number=2, red_score=160, blue_score=120,
                   actual_time=1_700_000_002),
    ]

    post = _RecordingPost()
    result = run_mode_c_anomaly(
        our_event_key=None,
        matches_fetcher=lambda ek: matches if ek == "2025txaus" else [],
        events_fetcher=lambda: ["2025txaus"],
        state=state,
        post_fn=post,
        webhook_url="https://discord.example/wh/abc",
        absolute_floor=250,
        persist=False,
    )

    assert result.anomalies_fired == ["2025txaus_qm2"]
    assert result.processed == 2
    assert len(post.calls) == 1
    reason_text = post.calls[0][1]["content"]
    assert "280" in reason_text


def test_cursor_advances_and_second_run_is_noop():
    matches_first = [
        _tba_match(key="2025txaus_qm1", match_number=1, red_score=80, blue_score=70,
                   actual_time=1_700_000_001),
        _tba_match(key="2025txaus_qm2", match_number=2, red_score=85, blue_score=72,
                   actual_time=1_700_000_002),
    ]
    state: dict[str, Any] = {"events": {}}
    post = _RecordingPost()

    r1 = run_mode_c_anomaly(
        our_event_key=None,
        matches_fetcher=lambda ek: matches_first,
        events_fetcher=lambda: ["2025txaus"],
        state=state,
        post_fn=post,
        webhook_url="",
        persist=False,
    )
    assert r1.processed == 2
    assert r1.anomalies_fired == []

    # Second run with the same matches — already processed.
    r2 = run_mode_c_anomaly(
        our_event_key=None,
        matches_fetcher=lambda ek: matches_first,
        events_fetcher=lambda: ["2025txaus"],
        state=state,
        post_fn=post,
        webhook_url="",
        persist=False,
    )
    assert r2.processed == 0
    assert r2.anomalies_fired == []


def test_our_event_is_skipped():
    state: dict[str, Any] = {"events": {}}
    call_log: list[str] = []

    def fetcher(ek: str):
        call_log.append(ek)
        return [_tba_match(key=f"{ek}_qm1", match_number=1,
                           red_score=150, blue_score=150,
                           actual_time=1_700_000_010)]

    post = _RecordingPost()
    result = run_mode_c_anomaly(
        our_event_key="2025txbel",
        matches_fetcher=fetcher,
        events_fetcher=lambda: ["2025txbel", "2025txdal"],
        state=state,
        post_fn=post,
        webhook_url="",
        persist=False,
    )

    # Our event must never have been fetched.
    assert "2025txbel" not in call_log
    assert "2025txdal" in call_log
    assert result.events_seen == ["2025txdal"]


def test_webhook_empty_skips_discord_but_still_processes():
    state: dict[str, Any] = {"events": {}}
    matches = [
        _tba_match(key="2025txaus_qm1", match_number=1, red_score=160, blue_score=130,
                   actual_time=1_700_000_001),  # 290 total → floor hit
    ]
    post = _RecordingPost()
    result = run_mode_c_anomaly(
        our_event_key=None,
        matches_fetcher=lambda ek: matches,
        events_fetcher=lambda: ["2025txaus"],
        state=state,
        post_fn=post,
        webhook_url="",  # empty skips posting
        absolute_floor=250,
        persist=False,
    )
    # Anomaly logic still runs...
    assert result.processed == 1
    # ...but we still record it in anomalies_fired (match was flagged),
    # and post_fn is still called with the empty URL. Verify it was called
    # once so Mode C behavior is consistent.
    assert result.anomalies_fired == ["2025txaus_qm1"]
    assert len(post.calls) == 1
    assert post.calls[0][0] == ""  # empty URL propagated


def test_state_updates_across_matches_in_single_run():
    """After a run, per-event state should reflect all processed matches."""
    matches = [
        _tba_match(key=f"2025txaus_qm{i}", match_number=i,
                   red_score=75, blue_score=75,
                   actual_time=1_700_000_000 + i)
        for i in range(1, 6)
    ]
    state: dict[str, Any] = {"events": {}}
    post = _RecordingPost()
    run_mode_c_anomaly(
        our_event_key=None,
        matches_fetcher=lambda ek: matches,
        events_fetcher=lambda: ["2025txaus"],
        state=state,
        post_fn=post,
        webhook_url="",
        persist=False,
    )
    ev = state["events"]["2025txaus"]
    assert ev["score_n"] == 5
    assert ev["score_sum"] == 5 * 150
    assert ev["last_cursor"] == 1_700_000_005
    assert len(ev["processed_match_keys"]) == 5
