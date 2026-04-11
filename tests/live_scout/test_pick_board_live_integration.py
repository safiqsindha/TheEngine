"""Tests for scout/pick_board.py Live Scout integration.

Covers append_live_match() + recompute_team_aggregates() — the two
functions Live Scout workers use to feed OCR-derived match data into
the live draft board. See LIVE_SCOUT_PHASE1_BUILD.md §F4.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scout"))

from live_match import LiveMatch  # noqa: E402
from pick_board import (  # noqa: E402
    _aggregate_scores,
    _blank_state,
    append_live_match,
    recompute_team_aggregates,
)


# ─── Fixtures ───


def _state_with_teams(*team_nums: int, event_key: str = "2026txbel") -> dict:
    state = _blank_state()
    state["event_key"] = event_key
    state["teams"] = {
        str(t): {
            "team": t,
            "name": f"Team {t}",
            "epa": 50.0,
            "sd": 10.0,
        }
        for t in team_nums
    }
    return state


def _qm(
    num: int,
    red: list[int],
    blue: list[int],
    red_score: int,
    blue_score: int,
    *,
    event_key: str = "2026txbel",
) -> LiveMatch:
    return LiveMatch(
        event_key=event_key,
        match_key=f"{event_key}_qm{num}",
        match_num=num,
        comp_level="qm",
        red_teams=red,
        blue_teams=blue,
        red_score=red_score,
        blue_score=blue_score,
        winning_alliance="red" if red_score > blue_score else ("blue" if blue_score > red_score else "tie"),
        timer_state="post",
        source_video_id=f"vid_{num}",
        source_tier="vod",
        confidence=0.97,
    )


# ─── append_live_match ───


def test_append_inserts_new_match():
    state = _state_with_teams(2950, 148)
    m = _qm(1, [2950, 1234, 5678], [148, 254, 1678], 88, 72)
    assert append_live_match(state, m) is True
    assert "2026txbel_qm1" in state["live_matches"]
    assert state["live_matches"]["2026txbel_qm1"]["red_score"] == 88


def test_append_is_idempotent_for_identical_record():
    state = _state_with_teams(2950)
    m = _qm(1, [2950, 1234, 5678], [148, 254, 1678], 88, 72)
    assert append_live_match(state, m) is True
    # Re-append same record → no mutation, returns False
    assert append_live_match(state, m) is False
    assert len(state["live_matches"]) == 1


def test_append_overwrites_prior_record_with_updated_data():
    """Matches finalize as more frames are processed. Re-appending with
    updated scores should replace the prior record."""
    state = _state_with_teams(2950)
    preliminary = _qm(1, [2950, 1234, 5678], [148, 254, 1678], 0, 0)
    preliminary.timer_state = "auto"
    # timer_state "auto" is re-validated but valid; rebuild to ensure clean
    final = _qm(1, [2950, 1234, 5678], [148, 254, 1678], 88, 72)

    append_live_match(state, preliminary)
    assert state["live_matches"]["2026txbel_qm1"]["red_score"] == 0

    assert append_live_match(state, final) is True
    assert state["live_matches"]["2026txbel_qm1"]["red_score"] == 88
    assert state["live_matches"]["2026txbel_qm1"]["blue_score"] == 72


def test_append_accepts_plain_dict():
    state = _state_with_teams(2950)
    record = _qm(1, [2950, 1234, 5678], [148, 254, 1678], 88, 72).to_dict()
    assert append_live_match(state, record) is True
    assert "2026txbel_qm1" in state["live_matches"]


def test_append_rejects_cross_event_records():
    """Defense against cross-contaminating boards from different events."""
    state = _state_with_teams(2950)
    other = _qm(1, [2950, 1234, 5678], [148, 254, 1678], 88, 72, event_key="2026txdri")
    assert append_live_match(state, other) is False
    assert state["live_matches"] == {}


def test_append_raises_on_missing_keys():
    state = _state_with_teams(2950)
    with pytest.raises(ValueError, match="missing event_key/match_key"):
        append_live_match(state, {"red_teams": [2950]})


# ─── recompute_team_aggregates ───


def test_recompute_ignores_teams_with_fewer_than_3_matches():
    state = _state_with_teams(2950)
    append_live_match(state, _qm(1, [2950, 1234, 5678], [148, 254, 1678], 80, 60))
    append_live_match(state, _qm(2, [2950, 1234, 5678], [148, 254, 1678], 85, 65))

    assert recompute_team_aggregates(state) == 0
    assert "real_sd" not in state["teams"]["2950"]


def test_recompute_writes_enrichment_fields_after_3_matches():
    state = _state_with_teams(2950)
    # 2950 plays red in all three, scoring 60, 90, 120 on the alliance
    append_live_match(state, _qm(1, [2950, 1234, 5678], [148, 254, 1678],  60, 50))
    append_live_match(state, _qm(2, [2950, 1234, 5678], [148, 254, 1678],  90, 50))
    append_live_match(state, _qm(3, [2950, 1234, 5678], [148, 254, 1678], 120, 50))

    assert recompute_team_aggregates(state) == 1
    td = state["teams"]["2950"]
    assert td["match_count"] == 3
    assert td["real_avg_score"] == pytest.approx(90.0)
    # variance = ((60-90)^2 + (90-90)^2 + (120-90)^2) / 3 = 600
    # per-robot sd = sqrt(600) / 3 ≈ 8.16 → rounded to 8.2
    assert td["real_sd"] == pytest.approx(8.2, abs=0.1)


def test_recompute_flags_hot_streak():
    """Recent 3 average > overall average * 1.15 → HOT."""
    state = _state_with_teams(2950)
    # Scores: 40, 40, 40, 40, 80, 80, 80 — avg 54.3, recent3=80 → HOT
    scores = [40, 40, 40, 40, 80, 80, 80]
    for i, s in enumerate(scores, start=1):
        append_live_match(state, _qm(i, [2950, 1234, 5678], [148, 254, 1678], s, 50))

    recompute_team_aggregates(state)
    assert state["teams"]["2950"]["streak"] == "HOT"


def test_recompute_flags_cold_streak():
    state = _state_with_teams(2950)
    # Scores: 100, 100, 100, 100, 40, 40, 40 → recent3=40, avg≈74 → 40 < 74*0.85 → COLD
    scores = [100, 100, 100, 100, 40, 40, 40]
    for i, s in enumerate(scores, start=1):
        append_live_match(state, _qm(i, [2950, 1234, 5678], [148, 254, 1678], s, 50))

    recompute_team_aggregates(state)
    assert state["teams"]["2950"]["streak"] == "COLD"


def test_recompute_orders_matches_by_match_num_not_insertion():
    """Streak window must be deterministic — sort by match_num regardless of
    insertion order."""
    state = _state_with_teams(2950)
    # Insert in scrambled order but numbering reflects true chronology
    entries = [
        (5, 80), (3, 40), (1, 40), (4, 80), (2, 40),
    ]
    for num, score in entries:
        append_live_match(state, _qm(num, [2950, 1234, 5678], [148, 254, 1678], score, 50))

    recompute_team_aggregates(state)
    # Chronological scores: [40, 40, 40, 80, 80]; recent3=[40,80,80]=66.67
    # avg=56, 66.67 > 56*1.15=64.4 → HOT
    assert state["teams"]["2950"]["streak"] == "HOT"


def test_recompute_uses_correct_alliance_score_per_team():
    """A team on the blue alliance should get blue's score, not red's."""
    state = _state_with_teams(148)
    # 148 plays blue in all three
    append_live_match(state, _qm(1, [2950, 1234, 5678], [148, 254, 1678], 200,  60))
    append_live_match(state, _qm(2, [2950, 1234, 5678], [148, 254, 1678], 200,  90))
    append_live_match(state, _qm(3, [2950, 1234, 5678], [148, 254, 1678], 200, 120))

    recompute_team_aggregates(state)
    # avg should be mean of blue scores (60, 90, 120) = 90, not red's 200
    assert state["teams"]["148"]["real_avg_score"] == pytest.approx(90.0)


def test_recompute_skips_incomplete_matches():
    """Matches without a final red_score/blue_score should not feed aggregates."""
    state = _state_with_teams(2950)
    append_live_match(state, _qm(1, [2950, 1234, 5678], [148, 254, 1678], 60, 50))
    append_live_match(state, _qm(2, [2950, 1234, 5678], [148, 254, 1678], 90, 50))

    # Inject an incomplete record (scores are None)
    incomplete = LiveMatch(
        event_key="2026txbel",
        match_key="2026txbel_qm3",
        match_num=3,
        comp_level="qm",
        red_teams=[2950, 1234, 5678],
        blue_teams=[148, 254, 1678],
        red_score=None,
        blue_score=None,
        winning_alliance=None,
        timer_state="teleop",
        source_video_id="vid_3",
        source_tier="live",
        confidence=0.6,
    )
    append_live_match(state, incomplete)

    # Only 2 complete qm matches → below the n>=3 threshold → no enrichment
    assert recompute_team_aggregates(state) == 0
    assert "real_sd" not in state["teams"]["2950"]


def test_recompute_skips_playoff_matches():
    """Qual-only enrichment matches cmd_enrich's scope."""
    state = _state_with_teams(2950)
    append_live_match(state, _qm(1, [2950, 1234, 5678], [148, 254, 1678], 60, 50))
    append_live_match(state, _qm(2, [2950, 1234, 5678], [148, 254, 1678], 90, 50))

    playoff = LiveMatch(
        event_key="2026txbel",
        match_key="2026txbel_qf1m1",
        match_num=1,
        comp_level="qf",
        red_teams=[2950, 1234, 5678],
        blue_teams=[148, 254, 1678],
        red_score=120,
        blue_score=90,
        winning_alliance="red",
        timer_state="post",
        source_video_id="vid_qf",
        source_tier="vod",
        confidence=0.95,
    )
    append_live_match(state, playoff)

    # Only 2 qual matches count → no enrichment
    assert recompute_team_aggregates(state) == 0


def test_recompute_ignores_teams_not_in_state_teams_db():
    """Teams appearing in a live match but not in state['teams'] (e.g., team
    played at a different event in the past) should not crash or create
    stub entries."""
    state = _state_with_teams(2950)  # only 2950 is in the teams db
    for i in range(1, 5):
        append_live_match(state, _qm(i, [2950, 1234, 5678], [148, 254, 1678], 80, 50))

    updated = recompute_team_aggregates(state)
    assert updated == 1  # only 2950
    assert "1234" not in state["teams"]
    assert "148" not in state["teams"]


# ─── _aggregate_scores ───


def test_aggregate_scores_empty_below_threshold():
    assert _aggregate_scores([]) == {}
    assert _aggregate_scores([50, 60]) == {}


def test_aggregate_scores_exact_math():
    out = _aggregate_scores([60, 90, 120])
    assert out["match_count"] == 3
    assert out["real_avg_score"] == pytest.approx(90.0)
    expected_sd = math.sqrt(600) / 3
    assert out["real_sd"] == round(expected_sd, 1)
    # recent3 == all3 == avg → no streak
    assert out["streak"] == ""
